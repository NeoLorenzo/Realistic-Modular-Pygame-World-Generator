# FOLDER: /

# fidelity_probe.py

import json
import logging
import numpy as np
from PIL import Image
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'editor')))
from editor.main import PREVIEW_RESOLUTION_WIDTH, PREVIEW_RESOLUTION_HEIGHT

from world_generator.generator import WorldGenerator
from world_generator import color_maps
from world_generator import tectonics

def run_probe_on_chunk(logger, live_preview_colors, world_gen, bake_dir, target_cx, target_cy, manifest):
    """Helper function to run the fidelity probe on a single specified chunk."""
    
    logger.info(f"\n--- Probing Chunk ({target_cx}, {target_cy}) ---")
    
    # --- 1. Load the specific baked chunk using the manifest ---
    coord_key = f"{target_cx},{target_cy}"
    try:
        # The filename is now a hash
        chunk_hash = manifest["chunk_map"]["terrain"][coord_key]
        filename = f"{chunk_hash}.png"
        chunk_path = os.path.join(bake_dir, "chunks", filename)
        # IMPORTANT: Palettized images must be converted back to RGB to get pixel data
        baked_chunk_img = Image.open(chunk_path).convert('RGB')
        baked_chunk_pixels = np.array(baked_chunk_img)
    except (KeyError, FileNotFoundError):
        logger.error(f"❌ FAILURE: Could not find or load chunk for coordinate ({target_cx}, {target_cy}) from manifest.")
        return False

    # --- 2. Define probe points and run comparison (logic is unchanged) ---
    chunk_res = manifest['chunk_resolution_pixels']
    chunk_size_cm = world_gen.settings['chunk_size_cm']
    
    probe_points_local = [
        (0, 0), (chunk_res - 1, 0), (0, chunk_res - 1), (chunk_res - 1, chunk_res - 1),
        (chunk_res // 2, chunk_res // 2)
    ]

    chunk_passed = True
    for px, py in probe_points_local:
        baked_color = tuple(baked_chunk_pixels[py, px])

        world_x_cm = (target_cx * chunk_size_cm) + ((px / chunk_res) * chunk_size_cm)
        world_y_cm = (target_cy * chunk_size_cm) + ((py / chunk_res) * chunk_size_cm)

        preview_px = int((world_x_cm / world_gen.world_width_cm) * PREVIEW_RESOLUTION_WIDTH)
        preview_py = int((world_y_cm / world_gen.world_height_cm) * PREVIEW_RESOLUTION_HEIGHT)
        preview_px = min(preview_px, PREVIEW_RESOLUTION_WIDTH - 1)
        preview_py = min(preview_py, PREVIEW_RESOLUTION_HEIGHT - 1)
        live_color = tuple(live_preview_colors[preview_px, preview_py])

        result = "PASS" if baked_color == live_color else "FAIL"
        if result == "FAIL":
            chunk_passed = False
        
        report = (f"  - Probing local pixel ({px}, {py}): Baked={baked_color}, Live={live_color} -> {result}")
        logger.info(report)
        
    return chunk_passed

def run_full_probe():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("FidelityProbe")

    # --- 1. Load Baked World Manifest ---
    bake_dir = "BakedWorldPackage_Optimized"
    manifest_path = os.path.join(bake_dir, "manifest.json")
    logger.info(f"Loading manifest from '{manifest_path}'...")
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except FileNotFoundError:
        logger.critical(f"Manifest not found. Run baker.py first to create '{bake_dir}'.")
        return

    # --- 2. Load the GENERATION config, not the editor config ---
    gen_config_path = os.path.join(bake_dir, "generation_config.json")
    logger.info(f"Loading generation config from '{gen_config_path}' for a perfect match...")
    with open(gen_config_path, 'r') as f:
        world_gen_params = json.load(f)
    
    world_gen = WorldGenerator(config=world_gen_params, logger=logger)

    # --- 3. Generate "Ground Truth" Live Preview Data ---
    logger.info("Generating full-world live preview data for comparison...")
    wx = np.linspace(0, world_gen.world_width_cm, PREVIEW_RESOLUTION_WIDTH)
    wy = np.linspace(0, world_gen.world_height_cm, PREVIEW_RESOLUTION_HEIGHT)
    wx_grid, wy_grid = np.meshgrid(wx, wy)

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
    biome_map = color_maps.calculate_biome_map(final_elevation_map, temp_map, humidity_map, soil_depth_map)
    biome_lut = color_maps.create_biome_color_lut()
    live_preview_colors = color_maps.get_terrain_color_array(biome_map, biome_lut)
    logger.info("Ground truth data generated.")

    # --- 4. Run Probe on a Set of Chunks ---
    baked_dims = manifest['world_dimensions_chunks']
    chunks_to_probe = [
        (0, 0),
        (baked_dims[0] - 1, baked_dims[1] - 1),
        (baked_dims[0] // 2, baked_dims[1] // 2)
    ]
    
    all_probes_passed = True
    for cx, cy in chunks_to_probe:
        if not run_probe_on_chunk(logger, live_preview_colors, world_gen, bake_dir, cx, cy, manifest):
            all_probes_passed = False

    logger.info("\n--- Full Probe Complete ---")
    if all_probes_passed:
        logger.info("✅ SUCCESS: All tested chunks are faithful to the live preview.")
    else:
        logger.error("❌ FAILURE: Mismatch detected in one or more chunks.")

if __name__ == '__main__':
    run_full_probe()