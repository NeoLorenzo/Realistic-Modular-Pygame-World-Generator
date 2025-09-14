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

# Add project root to Python path to allow importing from world_generator
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from world_generator.generator import WorldGenerator
from world_generator import color_maps
from world_generator import config as DEFAULTS

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
    for mode in view_modes:
        mode_dir = os.path.join(base_output_dir, mode)
        if not os.path.exists(mode_dir):
            os.makedirs(mode_dir)
            logger.info(f"Created directory: {mode_dir}")

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
    start_time = time.perf_counter()
    chunks_processed = 0

    # Create a reusable coordinate grid template
    wx_template = np.linspace(0, chunk_size_cm, chunk_res)
    wy_template = np.linspace(0, chunk_size_cm, chunk_res)
    
    for cy in range(height_chunks):
        for cx in range(width_chunks):
            # Create the specific coordinate grid for this chunk
            wx = wx_template + (cx * chunk_size_cm)
            wy = wy_template + (cy * chunk_size_cm)
            wx_grid, wy_grid = np.meshgrid(wx, wy)

            # --- Generate and save each view mode ---
            # Generate all data first to reuse it (Rule 11)
            elevation_data = generator.get_elevation(wx_grid, wy_grid)
            temp_data = generator.get_temperature(wx_grid, wy_grid, elevation_data=elevation_data)
            humidity_data = generator.get_humidity(wx_grid, wy_grid, temperature_data_c=temp_data)

            # Terrain
            terrain_colors = color_maps.get_terrain_color_array(elevation_data)
            terrain_surface = pygame.surfarray.make_surface(terrain_colors)
            pygame.image.save(terrain_surface, os.path.join(base_output_dir, 'terrain', f'chunk_{cx}_{cy}.png'))

            # Temperature
            temp_colors = color_maps.get_temperature_color_array(temp_data, temp_lut)
            temp_surface = pygame.surfarray.make_surface(temp_colors)
            pygame.image.save(temp_surface, os.path.join(base_output_dir, 'temperature', f'chunk_{cx}_{cy}.png'))

            # Humidity
            humidity_colors = color_maps.get_humidity_color_array(humidity_data, humidity_lut)
            humidity_surface = pygame.surfarray.make_surface(humidity_colors)
            pygame.image.save(humidity_surface, os.path.join(base_output_dir, 'humidity', f'chunk_{cx}_{cy}.png'))

            chunks_processed += 1
            if chunks_processed % 100 == 0:
                elapsed = time.perf_counter() - start_time
                percent_done = (chunks_processed / total_chunks) * 100
                logger.info(f"Progress: {chunks_processed}/{total_chunks} chunks ({percent_done:.2f}%) baked in {elapsed:.2f}s")

    end_time = time.perf_counter()
    logger.info(f"Baking complete! Total time: {end_time - start_time:.2f} seconds.")
    logger.info(f"Baked world saved to: {base_output_dir}")


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