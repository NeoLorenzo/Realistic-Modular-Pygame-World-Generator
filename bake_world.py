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
import pygame
import hashlib

# Add project root to Python path to allow importing from world_generator
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from world_generator.generator import WorldGenerator
from world_generator import color_maps
from world_generator import config as DEFAULTS

# --- Helper for Uniform Chunk Compression ---
def save_chunk_surface(color_array: np.ndarray, directory: str, file_hash: str) -> bool:
    """
    Saves a chunk surface using its hash as the filename. If the chunk is a
    uniform color, saves a 1x1 pixel PNG. Otherwise, saves the full-resolution
    surface.

    Args:
        color_array (np.ndarray): The full-resolution color data for the chunk.
        directory (str): The base directory to save the chunk in (e.g., '.../terrain/chunks').
        file_hash (str): The hash of the chunk content, used as the filename.

    Returns:
        bool: True if the chunk was uniform, False otherwise.
    """
    file_path = os.path.join(directory, f"{file_hash}.png")
    # Check if all color values in the array are identical to the first one.
    if (color_array == color_array[0, 0]).all():
        # Uniform chunk: create a 1x1 surface and save it.
        uniform_color = tuple(color_array[0, 0])
        surface = pygame.Surface((1, 1))
        surface.fill(uniform_color)
        pygame.image.save(surface, file_path)
        return True
    else:
        # Non-uniform chunk: create and save the full surface.
        surface = pygame.surfarray.make_surface(color_array)
        pygame.image.save(surface, file_path)
        return False

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

    # 3. --- Initialize World Generator ---
    logger.info(f"Initializing WorldGenerator with seed: {seed}")
    generator = WorldGenerator(config=world_params, logger=logger)

    # 4. --- Prepare Output Directories ---
    base_output_dir = f"baked_worlds/seed_{seed}"
    view_modes = ["terrain", "temperature", "humidity"]
    chunk_dirs = {}
    for mode in view_modes:
        # Unique chunk images will be stored in a 'chunks' subdirectory.
        mode_dir = os.path.join(base_output_dir, mode, "chunks")
        if not os.path.exists(mode_dir):
            os.makedirs(mode_dir)
            logger.info(f"Created directory: {mode_dir}")
        chunk_dirs[mode] = mode_dir

    # 5. --- Pre-compute Color LUTs (Rule 11) ---
    logger.info("Pre-computing color lookup tables...")
    temp_lut = color_maps.create_temperature_lut()
    humidity_lut = color_maps.create_humidity_lut()

        # 6. --- Main Baking Loop ---
    chunk_res = DEFAULTS.CHUNK_RESOLUTION
    chunk_size_cm = generator.settings['chunk_size_cm']
    width_chunks = generator.settings['world_width_chunks']
    height_chunks = generator.settings['world_height_chunks']
    total_chunks = width_chunks * height_chunks
    
    logger.info(f"Starting bake for a {width_chunks}x{height_chunks} world ({total_chunks} chunks)...")
    
    # --- Deduplication Data Structures ---
    # The manifest maps coordinates to content hashes.
    manifest = {mode: np.empty((height_chunks, width_chunks), dtype=object) for mode in view_modes}
    # This tracks which hashes have already been saved to disk for each mode.
    saved_hashes = {mode: set() for mode in view_modes}
    
    start_time = time.perf_counter()
    chunks_processed = 0

    # Create a reusable coordinate grid template
    wx_template = np.linspace(0, chunk_size_cm, chunk_res)
    wy_template = np.linspace(0, chunk_size_cm, chunk_res)
    
    for cy in range(height_chunks):
        for cx in range(width_chunks):
            wx = wx_template + (cx * chunk_size_cm)
            wy = wy_template + (cy * chunk_size_cm)
            wx_grid, wy_grid = np.meshgrid(wx, wy)

            # --- Generate all data layers first for reuse (Rule 11) ---
            elevation_data = generator.get_elevation(wx_grid, wy_grid)
            temp_data = generator.get_temperature(wx_grid, wy_grid, elevation_data=elevation_data)
            humidity_data = generator.get_humidity(wx_grid, wy_grid, temperature_data_c=temp_data)

            # --- Process each view mode with deduplication ---
            data_map = {
                "terrain": elevation_data,
                "temperature": temp_data,
                "humidity": humidity_data
            }
            for mode in view_modes:
                # 1. Get color array for the current mode
                if mode == "terrain":
                    color_array = color_maps.get_terrain_color_array(data_map[mode])
                elif mode == "temperature":
                    color_array = color_maps.get_temperature_color_array(data_map[mode], temp_lut)
                else: # humidity
                    color_array = color_maps.get_humidity_color_array(data_map[mode], humidity_lut)

                # 2. Calculate content hash
                file_hash = hashlib.md5(color_array.tobytes()).hexdigest()

                # 3. Update manifest
                manifest[mode][cy, cx] = file_hash

                # 4. Save chunk only if it's a new, unique piece of content
                if file_hash not in saved_hashes[mode]:
                    save_chunk_surface(color_array, chunk_dirs[mode], file_hash)
                    saved_hashes[mode].add(file_hash)

            chunks_processed += 1
            if chunks_processed % 100 == 0:
                elapsed = time.perf_counter() - start_time
                percent_done = (chunks_processed / total_chunks) * 100
                logger.info(f"Progress: {chunks_processed}/{total_chunks} chunks ({percent_done:.2f}%) processed in {elapsed:.2f}s")

    # --- Finalization ---
    # Convert NumPy arrays in manifest to lists for JSON serialization
    final_manifest = {mode: manifest[mode].tolist() for mode in view_modes}
    manifest_path = os.path.join(base_output_dir, "manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(final_manifest, f, indent=2)
    
    end_time = time.perf_counter()
    logger.info(f"Baking complete! Total time: {end_time - start_time:.2f} seconds.")
    logger.info("--- Deduplication Stats ---")
    for mode in view_modes:
        unique_count = len(saved_hashes[mode])
        logger.info(f"  - {mode.capitalize()}: {total_chunks} total -> {unique_count} unique chunks saved.")
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
    
    # Initialize Pygame modules required for image saving, but not display
    pygame.init()
    
    bake_world(args.config)
    
    pygame.quit()