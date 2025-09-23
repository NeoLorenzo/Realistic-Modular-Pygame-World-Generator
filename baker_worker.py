# baker_worker.py

import logging
import os
import numpy as np
import hashlib
from PIL import Image

# We can import from the world_generator package because it has no GUI dependencies
from world_generator.generator import WorldGenerator
from world_generator import color_maps

def run_chunk_baking_job(args: dict) -> tuple:
    """
    A top-level, pickle-able function designed to be run in a worker process.
    It generates the data for a single chunk and returns the results.
    THIS FILE MUST NOT IMPORT PYGAME OR PYGAME_GUI.
    """
    # --- Recreate the necessary environment inside the worker ---
    worker_logger = logging.getLogger(f"Worker-{os.getpid()}")
    world_gen = WorldGenerator(config=args['world_gen_settings'], logger=worker_logger)
    
    from world_generator import tectonics # Local import for the process
    
    cx, cy, view_mode = args['cx'], args['cy'], args['view_mode']
    
    CHUNK_RESOLUTION = world_gen.settings.get('chunk_resolution', 100)
    PADDING = 1

    padded_resolution = CHUNK_RESOLUTION + (2 * PADDING)
    chunk_size_cm = world_gen.settings['chunk_size_cm']
    pixel_size_cm = chunk_size_cm / CHUNK_RESOLUTION

    start_x_cm = (cx * chunk_size_cm) - (PADDING * pixel_size_cm)
    start_y_cm = (cy * chunk_size_cm) - (PADDING * pixel_size_cm)
    end_x_cm = start_x_cm + ((padded_resolution - 1) * pixel_size_cm)
    end_y_cm = start_y_cm + ((padded_resolution - 1) * pixel_size_cm)

    x_coords = np.linspace(start_x_cm, end_x_cm, padded_resolution)
    y_coords = np.linspace(start_y_cm, end_y_cm, padded_resolution)
    wx_grid, wy_grid = np.meshgrid(x_coords, y_coords)

    _, dist1, dist2 = world_gen.get_tectonic_data(wx_grid, wy_grid, world_gen.world_width_cm, world_gen.world_height_cm, world_gen.settings['num_tectonic_plates'], world_gen.settings['seed'])
    radius_cm = world_gen.settings['mountain_influence_radius_km'] * 100000.0
    influence_map = tectonics.calculate_influence_map(dist1, dist2, radius_cm)
    uplift_map = world_gen.get_tectonic_uplift(wx_grid, wy_grid, influence_map)

    bedrock_map = world_gen._get_bedrock_elevation(wx_grid, wy_grid, tectonic_uplift_map=uplift_map)
    slope_map = world_gen._get_slope(bedrock_map)
    soil_depth_map = world_gen._get_soil_depth(slope_map)
    
    water_level = world_gen.settings['terrain_levels']['water']
    land_mask = bedrock_map >= water_level
    soil_depth_map[~land_mask] = 0.0
    
    final_elevation_map = np.clip(bedrock_map + soil_depth_map, 0.0, 1.0)

    climate_noise_map = world_gen._generate_base_noise(wx_grid, wy_grid, seed_offset=world_gen.settings['temp_seed_offset'], scale=world_gen.settings['climate_noise_scale'])
    temp_map = world_gen.get_temperature(wx_grid, wy_grid, final_elevation_map, base_noise=climate_noise_map)
    
    coastal_factor_map = world_gen.calculate_coastal_factor_map(final_elevation_map, wx_grid.shape)
    shadow_factor_map = world_gen.calculate_shadow_factor_map(final_elevation_map, wx_grid.shape)
    humidity_map = world_gen.get_humidity(wx_grid, wy_grid, final_elevation_map, temp_map, coastal_factor_map, shadow_factor_map)

    temp_lut = color_maps.create_temperature_lut()
    humidity_lut = color_maps.create_humidity_lut()
    biome_lut = color_maps.create_biome_color_lut()

    if view_mode == "terrain":
        biome_map = color_maps.calculate_biome_map(final_elevation_map, temp_map, humidity_map, soil_depth_map)
        padded_color_array = color_maps.get_terrain_color_array(biome_map, biome_lut)
    elif view_mode == "temperature":
        padded_color_array = color_maps.get_temperature_color_array(temp_map, temp_lut)
    elif view_mode == "humidity":
        padded_color_array = color_maps.get_humidity_color_array(humidity_map, humidity_lut)
    elif view_mode == "elevation":
        padded_color_array = color_maps.get_elevation_color_array(final_elevation_map)
    elif view_mode == "soil_depth":
        max_depth = world_gen.settings['max_soil_depth_units']
        normalized_soil = soil_depth_map / max_depth if max_depth > 0 else np.zeros_like(soil_depth_map)
        padded_color_array = color_maps.get_elevation_color_array(normalized_soil)
    elif view_mode == "tectonic":
        THEORETICAL_MAX_UPLIFT = 10.0
        normalized_map = uplift_map / THEORETICAL_MAX_UPLIFT
        padded_color_array = color_maps.get_elevation_color_array(np.clip(normalized_map, 0.0, 1.0))
    else:
        padded_color_array = np.zeros((padded_resolution, padded_resolution, 3), dtype=np.uint8)

    pixel_data_whc = padded_color_array[PADDING:-PADDING, PADDING:-PADDING, :]
    chunk_hash = hashlib.sha256(pixel_data_whc.tobytes()).hexdigest()

    # --- WORKER HANDLES FILE SAVING ---
    output_dir = args['output_dir']
    seen_hashes_worker_copy = args['seen_hashes']
    
    needs_saving = False
    if chunk_hash not in seen_hashes_worker_copy:
        needs_saving = True
        pixel_data_hwc = np.transpose(pixel_data_whc, (1, 0, 2))
        img = Image.fromarray(pixel_data_hwc, 'RGB').convert('P', palette=Image.ADAPTIVE, colors=256)
        filename = f"{chunk_hash}.png"
        output_path = os.path.join(output_dir, "chunks", filename)
        img.save(output_path, optimize=True)

    # Return the hash and whether the main thread needs to update its seen_hashes set
    return (cx, cy, view_mode, chunk_hash, needs_saving)