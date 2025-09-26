# editor/package_builder.py

import json
import logging
import numpy as np
import sys
import os
import time
import hashlib
from PIL import Image
import shutil

# Ensure the project root is in the path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from world_generator import color_maps
from world_generator import config as DEFAULTS # Import the source of all default values

def chunk_master_data(master_package_path: str, logger: logging.Logger):
    """
    Loads a MasterDataPackage and chunks it into a final, optimized,
    game-ready BakedWorldPackage with PNGs.
    """
    start_time = time.time()
    
    # 1. Load the user's generation config
    logger.info(f"Loading user config from master package: '{master_package_path}'")
    gen_config_path = os.path.join(master_package_path, "generation_config.json")
    if not os.path.isfile(gen_config_path):
        logger.critical(f"generation_config.json not found in '{master_package_path}'. Aborting.")
        return
    with open(gen_config_path, 'r') as f:
        user_config = json.load(f)

    # 2. Load all master data arrays into memory
    master_data_dir = os.path.join(master_package_path, "master_data")
    logger.info(f"Loading master data arrays from '{master_data_dir}'...")
    master_data = {}
    try:
        for filename in os.listdir(master_data_dir):
            if filename.endswith(".npy"):
                name = filename.split('.')[0]
                master_data[name] = np.load(os.path.join(master_data_dir, filename))
                logger.info(f"  - Loaded {name}.npy (shape: {master_data[name].shape})")
    except FileNotFoundError:
        logger.critical(f"master_data directory not found in '{master_package_path}'. Aborting.")
        return

    # 3. Prepare the output package and manifest
    world_name = os.path.basename(master_package_path)
    output_dir = os.path.join("baked_worlds", f"{world_name}_Chunked")
    chunks_dir = os.path.join(output_dir, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)
    logger.info(f"Preparing output package at '{output_dir}'")

    width_chunks = user_config['world_width_chunks']
    height_chunks = user_config['world_height_chunks']
    chunk_res = user_config.get('chunk_resolution', 100)

    manifest = {
        "world_name": world_name,
        "world_dimensions_chunks": [width_chunks, height_chunks],
        "chunk_resolution_pixels": chunk_res,
        "chunk_map": {}
    }
    
    # 4. Main chunking loop
    view_modes = ["terrain", "temperature", "humidity", "elevation", "tectonic", "soil_depth"]
    seen_hashes = set()
    temp_lut = color_maps.create_temperature_lut()
    humidity_lut = color_maps.create_humidity_lut()
    biome_lut = color_maps.create_biome_color_lut()

    for view_mode in view_modes:
        logger.info(f"Chunking view mode: '{view_mode}'...")
        manifest["chunk_map"][view_mode] = {}
        
        for cy in range(height_chunks):
            for cx in range(width_chunks):
                # --- Slicing ---
                # Calculate the pixel slice for this chunk
                start_y, end_y = cy * chunk_res, (cy + 1) * chunk_res
                start_x, end_x = cx * chunk_res, (cx + 1) * chunk_res

                # Slice the required data from the master arrays
                elev_chunk = master_data["elevation"][start_y:end_y, start_x:end_x]
                temp_chunk = master_data["temperature"][start_y:end_y, start_x:end_x]
                hum_chunk = master_data["humidity"][start_y:end_y, start_x:end_x]
                soil_chunk = master_data["soil_depth"][start_y:end_y, start_x:end_x]
                uplift_chunk = master_data["uplift"][start_y:end_y, start_x:end_x]

                # --- Colorization ---
                if view_mode == "terrain":
                    biome_map = color_maps.calculate_biome_map(elev_chunk, temp_chunk, hum_chunk, soil_chunk)
                    color_array = color_maps.get_terrain_color_array(biome_map, biome_lut)
                elif view_mode == "temperature":
                    color_array = color_maps.get_temperature_color_array(temp_chunk, temp_lut)
                elif view_mode == "humidity":
                    color_array = color_maps.get_humidity_color_array(hum_chunk, humidity_lut)
                elif view_mode == "elevation":
                    color_array = color_maps.get_elevation_color_array(elev_chunk)
                elif view_mode == "soil_depth":
                    # CORRECTED: Use user_config to get the parameter used for this specific bake.
                    max_depth = user_config['max_soil_depth_units']
                    normalized_soil = soil_chunk / max_depth if max_depth > 0 else np.zeros_like(soil_chunk)
                    color_array = color_maps.get_elevation_color_array(normalized_soil)
                else: # tectonic
                    normalized_map = np.clip(uplift_chunk / 10.0, 0.0, 1.0)
                    color_array = color_maps.get_elevation_color_array(normalized_map)

                # --- Hashing and Saving ---
                chunk_hash = hashlib.sha256(color_array.tobytes()).hexdigest()
                manifest["chunk_map"][view_mode][f"{cx},{cy}"] = chunk_hash

                if chunk_hash not in seen_hashes:
                    seen_hashes.add(chunk_hash)
                    pixel_data_hwc = np.transpose(color_array, (1, 0, 2))
                    img = Image.fromarray(pixel_data_hwc, 'RGB').convert('P', palette=Image.ADAPTIVE, colors=256)
                    img.save(os.path.join(chunks_dir, f"{chunk_hash}.png"), optimize=True)

    # 5. Create and save the final, complete configuration
    # Start with a dictionary of all possible default values.
    # We filter out the dunder methods from the config module.
    final_config = {key: value for key, value in vars(DEFAULTS).items() if not key.startswith('__')}
    
    # Update the defaults with the user's specific settings.
    final_config.update(user_config)

    with open(os.path.join(output_dir, "manifest.json"), 'w') as f:
        json.dump(manifest, f)
    with open(os.path.join(output_dir, "generation_config.json"), 'w') as f:
        # Save the complete, merged config.
        json.dump(final_config, f, indent=4)
        
    # --- 6. Copy the Runtime Package and Example Script ---
    # Copy the runtime logic package
    source_runtime_path = os.path.join("world_generator", "runtime")
    dest_runtime_path = os.path.join(output_dir, "runtime")
    if os.path.exists(dest_runtime_path):
        shutil.rmtree(dest_runtime_path)
    shutil.copytree(source_runtime_path, dest_runtime_path)
    logger.info(f"Copied runtime package to '{dest_runtime_path}'")

    # Copy the runnable example script and its requirements
    source_template_dir = os.path.join("editor", "templates")
    
    # A list of all files to be copied from the templates directory
    template_files = [
        "run_world.py",
        "requirements.txt",
        "run.bat",
        "run.sh"
    ]

    for filename in template_files:
        source_path = os.path.join(source_template_dir, filename)
        dest_path = os.path.join(output_dir, filename)
        shutil.copy(source_path, dest_path)
        logger.info(f"Copied template file '{filename}' to '{output_dir}'")

    end_time = time.time()
    logger.info(f"Chunking complete in {end_time - start_time:.2f} seconds.")
    logger.info(f"Final game-ready package saved to '{output_dir}'")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("Chunker")
    
    # The chunker takes the path to the master package as input
    master_package_path = "baked_worlds/MyWorld_Seed42"
    
    if not os.path.isdir(master_package_path):
        logger.critical(f"Master package not found at '{master_package_path}'.")
        logger.critical("Please run the master_baker or use the editor to generate it first.")
    else:
        chunk_master_data(master_package_path, logger)