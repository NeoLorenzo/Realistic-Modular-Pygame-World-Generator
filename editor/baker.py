# editor/baker.py

import json
import logging
import numpy as np
import sys
import os
import time

# Ensure the project root is in the path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from world_generator.generator import WorldGenerator
from world_generator import tectonics

def bake_master_data(config: dict, logger: logging.Logger):
    """
    Generates and saves the full-resolution, raw NumPy data arrays for an entire world.
    This is the "Single Source of Truth" bake.
    
    Returns:
        str: The path to the created master data package directory.
    """
    start_time = time.time()
    
    # 1. Initialize the generator with the given configuration
    world_gen = WorldGenerator(config=config, logger=logger)
    
    # 2. Calculate full-world dimensions in pixels
    width_chunks = world_gen.settings['world_width_chunks']
    height_chunks = world_gen.settings['world_height_chunks']
    chunk_res = world_gen.settings.get('chunk_resolution', 100)
    
    world_res_w = width_chunks * chunk_res
    world_res_h = height_chunks * chunk_res
    
    logger.info(f"Starting master bake for a {width_chunks}x{height_chunks} chunk world ({world_res_w}x{world_res_h} pixels).")

    # 3. Create the full-world, high-resolution coordinate grid
    logger.info("Generating coordinate grid...")
    wx_grid, wy_grid = world_gen.get_coordinate_grid(
        world_x_cm=0,
        world_y_cm=0,
        width_cm=world_gen.world_width_cm,
        height_cm=world_gen.world_height_cm,
        resolution_w=world_res_w,
        resolution_h=world_res_h
    )

    # 4. Run the entire data generation pipeline ONCE on the full grid
    logger.info("Generating master data arrays...")
    
    # Tectonics
    _, dist1, dist2 = world_gen.get_tectonic_data(wx_grid, wy_grid, world_gen.world_width_cm, world_gen.world_height_cm, world_gen.settings['num_tectonic_plates'], world_gen.settings['seed'])
    radius_cm = world_gen.settings['mountain_influence_radius_km'] * 100000.0
    influence_map = tectonics.calculate_influence_map(dist1, dist2, radius_cm)
    uplift_map = world_gen.get_tectonic_uplift(wx_grid, wy_grid, influence_map)

    # Terrain
    bedrock_map = world_gen._get_bedrock_elevation(wx_grid, wy_grid, tectonic_uplift_map=uplift_map)
    slope_map = world_gen._get_slope(bedrock_map)
    soil_depth_map_raw = world_gen._get_soil_depth(slope_map)
    water_level = world_gen.settings['terrain_levels']['water']
    land_mask = bedrock_map >= water_level
    soil_depth_map = np.copy(soil_depth_map_raw)
    soil_depth_map[~land_mask] = 0.0
    final_elevation_map = np.clip(bedrock_map + soil_depth_map, 0.0, 1.0)

    # Climate
    climate_noise_map = world_gen._generate_base_noise(wx_grid, wy_grid, seed_offset=world_gen.settings['temp_seed_offset'], scale=world_gen.settings['climate_noise_scale'])
    temperature_map = world_gen.get_temperature(wx_grid, wy_grid, final_elevation_map, base_noise=climate_noise_map)
    coastal_factor_map = world_gen.calculate_coastal_factor_map(final_elevation_map, wx_grid.shape)
    shadow_factor_map = world_gen.calculate_shadow_factor_map(final_elevation_map, wx_grid.shape)
    humidity_map = world_gen.get_humidity(wx_grid, wy_grid, final_elevation_map, temperature_map, coastal_factor_map, shadow_factor_map)

    logger.info("Master data generation complete.")

    # 5. Save all raw data arrays to disk
    world_name = f"MyWorld_Seed{world_gen.settings['seed']}"
    output_dir = os.path.join("baked_worlds", world_name)
    master_data_dir = os.path.join(output_dir, "master_data")
    os.makedirs(master_data_dir, exist_ok=True)
    
    logger.info(f"Saving master data to '{master_data_dir}'...")
    
    data_to_save = {
        "elevation": final_elevation_map,
        "temperature": temperature_map,
        "humidity": humidity_map,
        "uplift": uplift_map,
        "soil_depth": soil_depth_map
    }
    
    for name, data_array in data_to_save.items():
        filepath = os.path.join(master_data_dir, f"{name}.npy")
        np.save(filepath, data_array)
        logger.info(f"  - Saved {name}.npy (shape: {data_array.shape})")

    # 6. Save the generation config
    gen_config_path = os.path.join(output_dir, "generation_config.json")
    with open(gen_config_path, 'w') as f:
        json.dump(world_gen.settings, f, indent=4)
    logger.info(f"Saved generation_config.json to '{output_dir}'")
    
    end_time = time.time()
    logger.info(f"Master bake complete in {end_time - start_time:.2f} seconds.")
    
    return output_dir

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("MasterBaker")

    logger.info("Loading base configuration from editor/config.json...")
    with open('editor/config.json', 'r') as f:
        config = json.load(f)

    # Use a small world size for the initial test
    world_gen_params = config.get('world_generation_parameters', {})
    world_gen_params['world_width_chunks'] = 5
    world_gen_params['world_height_chunks'] = 5
    
    bake_master_data(world_gen_params, logger)