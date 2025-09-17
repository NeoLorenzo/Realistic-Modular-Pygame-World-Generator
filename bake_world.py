# bake_world.py

"""
================================================================================
OFFLINE WORLD BAKER SCRIPT
================================================================================
This script is a command-line tool for pre-rendering a world's visual data
to a directory of chunk images ("baking"). This is a slow, one-time process
that enables the main application to run in a high-performance "baked" mode
by simply loading these images instead of generating them in real-time.

Usage:
    python bake_world.py --config path/to/your/config.json
================================================================================
"""
import os
import sys
import json
import logging
import argparse
import time
import numpy as np
from PIL import Image
import hashlib
import collections
import multiprocessing
from tqdm import tqdm

# Add project root to Python path to allow importing from world_generator
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from world_generator.generator import WorldGenerator
from world_generator import color_maps
from world_generator import config as DEFAULTS

# --- Helper for Uniform Chunk Compression ---
def save_chunk_surface(color_array: np.ndarray, directory: str, file_hash: str) -> str:
    """
    Saves a chunk surface using a tiered, lossless compression strategy with Pillow.
    """
    os.makedirs(directory, exist_ok=True)
    file_path = os.path.join(directory, f"{file_hash}.png")

    # Pillow works with (height, width, channels) arrays, so we need to transpose
    # the input array from (width, height, channels) to what Pillow expects.
    img_data = np.transpose(color_array, (1, 0, 2))

    # Tier 1: Check for perfectly uniform color.
    if (img_data == img_data[0, 0]).all():
        # Create a 1x1 image with the uniform color.
        uniform_color = tuple(img_data[0, 0])
        img = Image.new('RGB', (1, 1), uniform_color)
        img.save(file_path, 'PNG')
        return 'uniform'

    # Create an RGB image from the numpy array.
    img = Image.fromarray(img_data, 'RGB')

    # Tier 2: Check for low color count and convert to palettized mode.
    # The quantize method is Pillow's way of creating a palettized image.
    # It's fast and effective.
    num_colors = len(img.getcolors(257)) if img.getcolors(257) else 0
    if 0 < num_colors <= 256:
        img = img.quantize(colors=256)
        img.save(file_path, 'PNG')
        return 'palettized'

    # Tier 3: Fallback for high-color chunks (save as standard RGB PNG).
    else:
        img.save(file_path, 'PNG')
        return 'full'

# --- Global variables for worker processes ---
worker_generator = None
worker_luts = {}
worker_chunk_dirs = {} # This will be populated by the initializer
worker_view_modes = []
worker_chunk_res = 0
worker_chunk_size_cm = 0

def init_worker(config, luts, chunk_dirs, view_modes, chunk_res, chunk_size_cm, distance_map_data):
    """Initializes the global state for each worker process."""
    global worker_generator, worker_luts, worker_chunk_dirs, worker_view_modes
    global worker_chunk_res, worker_chunk_size_cm
    
    worker_logger = logging.getLogger(f"Worker-{os.getpid()}")
    # Pass the pre-computed map to the worker's generator instance
    worker_generator = WorldGenerator(config=config, logger=worker_logger, distance_map_data=None)
    worker_luts = luts
    worker_chunk_dirs = chunk_dirs
    worker_view_modes = view_modes
    worker_chunk_res = chunk_res
    worker_chunk_size_cm = chunk_size_cm

def process_chunk(coords):
    """
    Processes and SAVES a single chunk. Returns only minimal metadata.
    """
    cx, cy = coords
    
    wx_template = np.linspace(0, worker_chunk_size_cm, worker_chunk_res, dtype=np.float32)
    wy_template = np.linspace(0, worker_chunk_size_cm, worker_chunk_res, dtype=np.float32)
    wx = wx_template + (cx * worker_chunk_size_cm)
    wy = wy_template + (cy * worker_chunk_size_cm)
    wx_grid, wy_grid = np.meshgrid(wx, wy)

    elevation_data = worker_generator.get_elevation(wx_grid, wy_grid)
    
    temp_noise = worker_generator._generate_base_noise(
        wx_grid, wy_grid,
        seed_offset=worker_generator.settings['temp_seed_offset'],
        scale=worker_generator.settings['climate_noise_scale']
    )

    temp_data = worker_generator.get_temperature(wx_grid, wy_grid, elevation_data=elevation_data, base_noise=temp_noise)
    humidity_data = worker_generator.get_humidity(wx_grid, wy_grid, elevation_data, temperature_data_c=temp_data)

    data_map = {"terrain": elevation_data, "temperature": temp_data, "humidity": humidity_data}
    
    chunk_results = {'cx': cx, 'cy': cy, 'hashes': {}, 'compression_types': {}}

    for mode in worker_view_modes:
        if mode == "terrain":
            # Pass all three climate layers to the function for full biome calculation.
            color_array = color_maps.get_terrain_color_array(data_map["terrain"], data_map["temperature"], data_map["humidity"])
        elif mode == "temperature":
            color_array = color_maps.get_temperature_color_array(data_map["temperature"], worker_luts['temp'])
        elif mode == "humidity":
            color_array = color_maps.get_humidity_color_array(data_map["humidity"], worker_luts['humidity'])
        else: # elevation
            color_array = color_maps.get_elevation_color_array(data_map["terrain"])

        file_hash = hashlib.md5(color_array.tobytes()).hexdigest()
        compression_type = save_chunk_surface(color_array, worker_chunk_dirs[mode], file_hash)
        
        chunk_results['hashes'][mode] = file_hash
        chunk_results['compression_types'][mode] = compression_type

    return chunk_results

# --- Main Baking Function ---
def bake_world(config_path: str):
    """
    Loads a configuration, generates all world chunk surfaces, and saves them
    as PNG images to a structured output directory.
    """
    # 1. --- Setup Logging (Rule 2) ---
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    logger = logging.getLogger("Baker")

    # 2. --- Load Configuration (Rule 1) ---
    logger.info(f"Loading configuration from: {config_path}")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.critical(f"Failed to load or parse config file: {e}")
        return

    world_params = config.get('world_generation_parameters', {})
    seed = world_params.get('seed', DEFAULTS.DEFAULT_SEED)

    # 3. --- Initialize a temporary World Generator for main thread info ---
    logger.info(f"Initializing WorldGenerator with seed: {seed}")
    # This generator is now used for the one-time distance map calculation
    main_generator = WorldGenerator(config=world_params, logger=logger)

    # --- Prepare data for workers ---
    distance_map_data = {
        'distance_map': main_generator._distance_map,
        'rain_shadow_map': main_generator._rain_shadow_map,
        'scale_x': main_generator._map_scale_x,
        'scale_y': main_generator._map_scale_y
    }

    # 4. --- Prepare Output Directories ---
    base_output_dir = f"baked_worlds/seed_{seed}"
    view_modes = ["terrain", "temperature", "humidity", "elevation"]
    chunk_dirs = {}
    for mode in view_modes:
        # Define the paths, but do not create the directories here.
        # The workers will handle directory creation on-demand and safely.
        mode_dir = os.path.join(base_output_dir, mode, "chunks")
        chunk_dirs[mode] = mode_dir

    # 5. --- Pre-compute Color LUTs (Rule 11) ---
    logger.info("Pre-computing color lookup tables...")
    temp_lut = color_maps.create_temperature_lut()
    humidity_lut = color_maps.create_humidity_lut()
    luts = {'temp': temp_lut, 'humidity': humidity_lut}

    # 6. --- Main Baking Loop (Parallelized) ---
    chunk_res = DEFAULTS.CHUNK_RESOLUTION
    chunk_size_cm = main_generator.settings['chunk_size_cm']
    width_chunks = main_generator.settings['world_width_chunks']
    height_chunks = main_generator.settings['world_height_chunks']
    total_chunks = width_chunks * height_chunks
    
    logger.info(f"Starting parallel bake for a {width_chunks}x{height_chunks} world ({total_chunks} chunks)...")
    
    manifest = {mode: np.empty((height_chunks, width_chunks), dtype=object) for mode in view_modes}
    saved_hashes = {mode: set() for mode in view_modes}
    compression_stats = {mode: collections.Counter() for mode in view_modes}
    
    start_time = time.perf_counter()

    tasks = [(cx, cy) for cy in range(height_chunks) for cx in range(width_chunks)]
    
    num_workers = max(1, multiprocessing.cpu_count() - 1)
    logger.info(f"Using {num_workers} worker processes.")

    init_args = (world_params, luts, chunk_dirs, view_modes, DEFAULTS.CHUNK_RESOLUTION, main_generator.settings['chunk_size_cm'], distance_map_data)
    with multiprocessing.Pool(processes=num_workers, initializer=init_worker, initargs=init_args) as pool:
        results_iterator = pool.imap_unordered(process_chunk, tasks)
        
        for result in tqdm(results_iterator, total=total_chunks, desc="Baking Chunks"):
            cx, cy = result['cx'], result['cy']
            
            for mode in view_modes:
                file_hash = result['hashes'][mode]
                manifest[mode][cy, cx] = file_hash
                
                if file_hash not in saved_hashes[mode]:
                    saved_hashes[mode].add(file_hash)
                    compression_type = result['compression_types'][mode]
                    compression_stats[mode][compression_type] += 1

    # --- Finalization ---
    # Convert NumPy arrays in manifest to lists for JSON serialization
    final_manifest = {mode: manifest[mode].tolist() for mode in view_modes}
    manifest_path = os.path.join(base_output_dir, "manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(final_manifest, f, indent=2)
    
    end_time = time.perf_counter()
    logger.info(f"Baking complete! Total time: {end_time - start_time:.2f} seconds.")
    logger.info("--- Deduplication & Compression Stats ---")
    for mode in view_modes:
        stats = compression_stats[mode]
        unique_count = len(saved_hashes[mode])
        logger.info(
            f"  - {mode.capitalize()}: {total_chunks} total -> {unique_count} unique chunks saved "
            f"({stats['uniform']} uniform, {stats['palettized']} palettized, {stats['full']} full)"
        )
    logger.info(f"Baked world and manifest.json saved to: {base_output_dir}")


# --- Command-Line Interface ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Offline World Baker for the Realistic Modular World Generator.")
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to the JSON configuration file for the world to be baked."
    )
    args = parser.parse_args()
    
    bake_world(args.config)