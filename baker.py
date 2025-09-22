# FOLDER: /

# baker.py

import logging
import os
import numpy as np
from PIL import Image
import json
import time
import hashlib

# Import the core generator and its utilities
from world_generator.generator import WorldGenerator
from world_generator import color_maps
from world_generator import tectonics
from world_generator import config as DEFAULTS

# --- Baking Constants (Rule 1) ---
CHUNK_RESOLUTION = DEFAULTS.CHUNK_RESOLUTION
PADDING = 1

def bake_chunk(
    world_generator: WorldGenerator,
    cx: int,
    cy: int
) -> np.ndarray:
    """
    Generates the raw pixel data for a single chunk using the "overlap-and-crop"
    method to ensure it is perfectly seamless with its neighbors.
    (This function is unchanged)
    """
    padded_resolution = CHUNK_RESOLUTION + (2 * PADDING)
    chunk_size_cm = world_generator.settings['chunk_size_cm']

    pixel_size_cm = chunk_size_cm / CHUNK_RESOLUTION
    start_x_cm = (cx * chunk_size_cm) - (PADDING * pixel_size_cm)
    start_y_cm = (cy * chunk_size_cm) - (PADDING * pixel_size_cm)
    
    end_x_cm = start_x_cm + ((padded_resolution - 1) * pixel_size_cm)
    end_y_cm = start_y_cm + ((padded_resolution - 1) * pixel_size_cm)

    x_coords = np.linspace(start_x_cm, end_x_cm, padded_resolution)
    y_coords = np.linspace(start_y_cm, end_y_cm, padded_resolution)
    wx_grid, wy_grid = np.meshgrid(x_coords, y_coords)

    _, dist1, dist2 = world_generator.get_tectonic_data(
        wx_grid, wy_grid,
        world_generator.world_width_cm,
        world_generator.world_height_cm,
        world_generator.settings['num_tectonic_plates'],
        world_generator.settings['seed']
    )
    radius_cm = world_generator.settings['mountain_influence_radius_km'] * DEFAULTS.CM_PER_KM
    influence_map = tectonics.calculate_influence_map(dist1, dist2, radius_cm)
    uplift_map = world_generator.get_tectonic_uplift(wx_grid, wy_grid, influence_map)

    bedrock_map = world_generator._get_bedrock_elevation(wx_grid, wy_grid, tectonic_uplift_map=uplift_map)
    slope_map = world_generator._get_slope(bedrock_map)
    soil_depth_map = world_generator._get_soil_depth(slope_map)
    
    water_level = world_generator.settings['terrain_levels']['water']
    land_mask = bedrock_map >= water_level
    soil_depth_map[~land_mask] = 0.0
    
    final_elevation_map = np.clip(bedrock_map + soil_depth_map, 0.0, 1.0)

    climate_noise_map = world_generator._generate_base_noise(
        wx_grid, wy_grid,
        seed_offset=world_generator.settings['temp_seed_offset'],
        scale=world_generator.settings['climate_noise_scale']
    )
    temp_map = world_generator.get_temperature(wx_grid, wy_grid, final_elevation_map, base_noise=climate_noise_map)
    
    coastal_factor_map = world_generator.calculate_coastal_factor_map(final_elevation_map, wx_grid.shape)
    shadow_factor_map = world_generator.calculate_shadow_factor_map(final_elevation_map, wx_grid.shape)
    humidity_map = world_generator.get_humidity(wx_grid, wy_grid, final_elevation_map, temp_map, coastal_factor_map, shadow_factor_map)

    biome_map = color_maps.calculate_biome_map(final_elevation_map, temp_map, humidity_map, soil_depth_map)
    biome_lut = color_maps.create_biome_color_lut()
    padded_color_array = color_maps.get_terrain_color_array(biome_map, biome_lut)

    cropped_color_array = padded_color_array[PADDING:-PADDING, PADDING:-PADDING, :]

    return cropped_color_array

def bake_world(world_generator: WorldGenerator, output_dir: str, logger: logging.Logger):
    """
    Bakes an entire world with content-hashing for deduplication and creates
    a complete, portable Baked World Package.
    """
    start_time = time.time()
    
    # 1. Create directory structure
    chunks_dir = os.path.join(output_dir, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)
    logger.info(f"Output directory set to '{output_dir}'")

    # 2. Get world dimensions and prepare manifest
    width_chunks = world_generator.settings['world_width_chunks']
    height_chunks = world_generator.settings['world_height_chunks']
    total_chunks = width_chunks * height_chunks
    logger.info(f"Starting optimized bake for a {width_chunks}x{height_chunks} world.")

    manifest = {
        "world_name": "MyAwesomeWorld_Optimized",
        "world_dimensions_chunks": [width_chunks, height_chunks],
        "chunk_resolution_pixels": CHUNK_RESOLUTION,
        "chunk_map": {
            "terrain": {}
        }
    }
    
    # 3. Main baking loop with deduplication
    seen_hashes = set()
    saved_chunks_count = 0
    for cy in range(height_chunks):
        for cx in range(width_chunks):
            chunk_index = (cy * width_chunks) + cx + 1
            
            # Generate the chunk's pixel data
            pixel_data_whc = bake_chunk(world_generator, cx, cy)
            
            # Calculate a hash of the chunk's content
            chunk_hash = hashlib.sha256(pixel_data_whc.tobytes()).hexdigest()
            
            # If we haven't seen this exact chunk before, save it
            if chunk_hash not in seen_hashes:
                seen_hashes.add(chunk_hash)
                saved_chunks_count += 1
                
                # Transpose from (W, H, C) to (H, W, C) for Pillow
                pixel_data_hwc = np.transpose(pixel_data_whc, (1, 0, 2))
                
                # Convert to palettized PNG (PNG-8) for massive space savings
                img = Image.fromarray(pixel_data_hwc, 'RGB').convert('P', palette=Image.ADAPTIVE, colors=256)
                
                filename = f"{chunk_hash}.png"
                output_path = os.path.join(chunks_dir, filename)
                img.save(output_path, optimize=True)

            # Always add an entry to the manifest, mapping coords to the content hash
            coord_key = f"{cx},{cy}"
            manifest["chunk_map"]["terrain"][coord_key] = chunk_hash
            
            if chunk_index % 10 == 0 or chunk_index == total_chunks:
                 logger.info(f"Processed chunk {chunk_index}/{total_chunks}...")

    # 4. Save the manifest file
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f) # Use compact JSON for the final manifest

    # 5. Save the "birth certificate" generation_config.json
    gen_config_path = os.path.join(output_dir, "generation_config.json")
    with open(gen_config_path, 'w') as f:
        json.dump(world_generator.settings, f, indent=4)

    end_time = time.time()
    logger.info("--- Bake Complete ---")
    logger.info(f"Total chunks processed: {total_chunks}")
    logger.info(f"Unique chunks saved:   {saved_chunks_count} ({(saved_chunks_count/total_chunks)*100:.2f}% of total)")
    logger.info(f"Total time: {end_time - start_time:.2f} seconds.")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("Baker")

    logger.info("Loading configuration from editor/config.json...")
    with open('editor/config.json', 'r') as f:
        config = json.load(f)

    world_gen_params = config.get('world_generation_parameters', {})
    # Use a larger world to better demonstrate the deduplication savings
    world_gen_params['world_width_chunks'] = 50
    world_gen_params['world_height_chunks'] = 50
    # Set a low amplitude to create large, uniform oceans
    world_gen_params['terrain_amplitude'] = 1.0
    
    world_gen = WorldGenerator(config=world_gen_params, logger=logger)

    # Run the Full World Bake with optimizations
    bake_world(world_gen, "BakedWorldPackage_Optimized", logger)
    
    logger.info("Next step: Run fidelity_probe.py to verify the optimized output.")