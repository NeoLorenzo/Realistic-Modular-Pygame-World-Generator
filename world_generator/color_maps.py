# world_generator/color_maps.py

"""
================================================================================
SHARED COLOR MAPPING UTILITIES
================================================================================
This module contains the color mapping constants and functions for converting
raw world data (elevation, temperature, humidity) into RGB color arrays.

It is designed to be a pure, stateless utility with no dependencies on Pygame,
allowing it to be used by both the real-time renderer and the offline
baker script.
================================================================================
"""
import numpy as np
from . import config as DEFAULTS

# --- Default Color Mappings ---
COLOR_MAP_TERRAIN = {
    # New 4-level water depth palette
    "abyss": (0, 0, 50),          # Deepest water
    "deep_water": (10, 20, 80),   # Deep
    "mid_water": (20, 40, 120),   # Medium
    "shallow_water": (26, 102, 255), # Shallowest
    "sand": (240, 230, 140),
    # "grass" is now the "normal" grass color
    "grass": (34, 139, 34),
    # New grass variants for different biomes
    "grass_lush": (0, 100, 0),
    "grass_dry": (154, 205, 50),
    "dirt": (139, 69, 19),
    "mountain": (112, 128, 144)
}

COLOR_MAP_TEMPERATURE = {
    "coldest": (0, 0, 100),
    "cold": (0, 0, 255),
    "temperate": (255, 255, 0),
    "hot": (255, 0, 0),
    "hottest": (150, 0, 0)
}

COLOR_MAP_HUMIDITY = {
    "dry": (210, 180, 140),
    "wet": (70, 130, 180)
}

# Define a single, constant color for snow (Rule 1).
COLOR_SNOW = (255, 255, 255)

# Define a constant color for sea ice. A light blue-grey distinguishes it from snow.
COLOR_ICE = (210, 225, 240)

HUMIDITY_STEPS = 100 # The number of discrete steps for the humidity map

# --- Color Lookup Table (LUT) Generation ---
def create_temperature_lut() -> np.ndarray:
    """Creates a 256-entry color LUT for the temperature map."""
    t = np.linspace(0.0, 1.0, 256)[..., np.newaxis]
    color_map = COLOR_MAP_TEMPERATURE
    temp_levels = DEFAULTS.TEMP_LEVELS
    
    colors = np.select(
        [t < temp_levels["cold"], t < temp_levels["temperate"], t < temp_levels["hot"]],
        [
            (1 - t/temp_levels["cold"]) * np.array(color_map["coldest"]) + (t/temp_levels["cold"]) * np.array(color_map["cold"]),
            (1 - (t-temp_levels["cold"])/(temp_levels["temperate"]-temp_levels["cold"])) * np.array(color_map["cold"]) + ((t-temp_levels["cold"])/(temp_levels["temperate"]-temp_levels["cold"])) * np.array(color_map["temperate"]),
            (1 - (t-temp_levels["temperate"])/(temp_levels["hot"]-temp_levels["temperate"])) * np.array(color_map["temperate"]) + ((t-temp_levels["temperate"])/(temp_levels["hot"]-temp_levels["temperate"])) * np.array(color_map["hot"])
        ],
        default=(1 - (t-temp_levels["hot"])/(1.0-temp_levels["hot"])) * np.array(color_map["hot"]) + ((t-temp_levels["hot"])/(1.0-temp_levels["hot"])) * np.array(color_map["hottest"])
    )
    return colors.astype(np.uint8)

def create_humidity_lut() -> np.ndarray:
    """Creates a 256-entry color LUT for the humidity map."""
    t = np.linspace(0.0, 1.0, 256)[..., np.newaxis]
    color_map = COLOR_MAP_HUMIDITY
    colors = (1 - t) * np.array(color_map["dry"]) + t * np.array(color_map["wet"])
    return colors.astype(np.uint8)

# --- Color Array Generation Functions ---
def get_terrain_color_array(elevation_values: np.ndarray, temperature_values: np.ndarray, humidity_values: np.ndarray) -> np.ndarray:
    """
    Converts elevation, temperature, and humidity data into an RGB color array,
    applying a full biome model for ground cover.
    """
    color_map = COLOR_MAP_TERRAIN
    levels = DEFAULTS.TERRAIN_LEVELS
    thresholds = DEFAULTS.BIOME_THRESHOLDS
    water_level = levels["water"]

    # 1. --- Base Elevation Coloring ---
    # First, establish the fundamental terrain based on elevation.
    land_bins = [levels["sand"], levels["grass"], levels["dirt"]]
    land_color_lookup = np.array([
        color_map["sand"], color_map["grass"], color_map["dirt"], color_map["mountain"]
    ], dtype=np.uint8)

    colors = np.full(elevation_values.shape + (3,), color_map["abyss"], dtype=np.uint8)
    land_mask = elevation_values >= water_level
    if np.any(land_mask):
        land_elevations = elevation_values[land_mask]
        indices = np.digitize(land_elevations, bins=land_bins)
        colors[land_mask] = land_color_lookup[indices]

    water_mask = ~land_mask
    if np.any(water_mask):
        water_bins = [water_level * 0.25, water_level * 0.50, water_level * 0.75]
        water_color_lookup = np.array([
            color_map["abyss"], color_map["deep_water"], color_map["mid_water"], color_map["shallow_water"]
        ], dtype=np.uint8)
        water_elevations = elevation_values[water_mask]
        water_indices = np.digitize(water_elevations, bins=water_bins)
        colors[water_mask] = water_color_lookup[water_indices]

    # 2. --- Climate-Driven Biome Logic (Final Robust Model) ---
    # This logic overrides the base elevation colors for non-mountain land.
    # This mask now covers all land from the end of the sand/beach level up
    # to the start of the mountain level. This is critical to ensure that
    # low-lying grasslands are correctly converted to desert in arid climates.
    biome_zone_mask = (elevation_values >= levels["sand"]) & (elevation_values < levels["dirt"])

    if np.any(biome_zone_mask):
        # Get climate data for the relevant zone.
        zone_temps = temperature_values[biome_zone_mask]
        zone_humidity = humidity_values[biome_zone_mask]

        # Define a color lookup table for the biomes. The order is important.
        # 0=Dirt, 1=Sand, 2=Dry Grass, 3=Normal Grass, 4=Lush Grass
        biome_color_lookup = np.array([
            color_map["dirt"],
            color_map["sand"],
            color_map["grass_dry"],
            color_map["grass"],
            color_map["grass_lush"]
        ], dtype=np.uint8)

        # Define conditions for each biome index. Order matters: harshest conditions first.
        conditions = [
            # Condition for Sand (Index 1): Must be hot AND barren.
            (zone_temps > thresholds["sand_desert_min_temp_c"]) &
            (zone_humidity < thresholds["normal_grass_min_humidity_g_m3"]),

            # Condition for Dirt (Index 0): Barren due to temp or humidity.
            (zone_humidity < thresholds["arid_grass_min_humidity_g_m3"]) |
            (zone_temps < thresholds["grass_min_temp_c"]) |
            (zone_temps > thresholds["grass_max_temp_c"]),

            # Condition for Lush Grass (Index 4): Very humid.
            (zone_humidity >= thresholds["lush_grass_min_humidity_g_m3"]),

            # Condition for Normal Grass (Index 3): Moderately humid.
            (zone_humidity >= thresholds["normal_grass_min_humidity_g_m3"])
        ]

        # Define the corresponding biome index for each condition.
        choices = [1, 0, 4, 3]

        # Use np.select. The default is Dry Grass (Index 2), the mildest non-normal condition.
        biome_indices = np.select(conditions, choices, default=2)

        # Use the generated indices to get the final colors from the lookup table.
        biome_colors = biome_color_lookup[biome_indices]

        # Apply the final calculated biome colors back to the main color array.
        colors[biome_zone_mask] = biome_colors

    # 3. --- Final Frost and Ice Layers ---
    # These are applied last, overlaying all other biome logic.
    ice_mask = (temperature_values <= DEFAULTS.ICE_FORMATION_TEMP_C) & water_mask
    if np.any(ice_mask):
        colors[ice_mask] = COLOR_ICE

    snow_mask = (temperature_values <= DEFAULTS.SNOW_LINE_TEMP_C) & land_mask
    if np.any(snow_mask):
        colors[snow_mask] = COLOR_SNOW

    return np.transpose(colors, (1, 0, 2))

def get_temperature_color_array(temp_values: np.ndarray, temp_lut: np.ndarray) -> np.ndarray:
    """Converts Celsius temperature data into an RGB color array using a pre-computed LUT."""
    # --- Quantization Step (Rule 8) ---
    # Round to the nearest whole degree to create discrete temperature bands.
    # This dramatically improves deduplication for a massive storage saving.
    quantized_temps = np.round(temp_values)

    min_temp_c = DEFAULTS.MIN_GLOBAL_TEMP_C
    temp_range_c = DEFAULTS.MAX_GLOBAL_TEMP_C - min_temp_c
    # Normalize the quantized data
    normalized_temp = (quantized_temps - min_temp_c) / temp_range_c
    indices = (normalized_temp * 255).astype(np.uint8)
    colors = temp_lut[indices]
    return np.transpose(colors, (1, 0, 2))

def get_humidity_color_array(humidity_values: np.ndarray, humidity_lut: np.ndarray) -> np.ndarray:
    """Converts absolute humidity data into an RGB color array using a pre-computed LUT."""
    min_humidity = DEFAULTS.MIN_ABSOLUTE_HUMIDITY_G_M3
    max_humidity = DEFAULTS.MAX_ABSOLUTE_HUMIDITY_G_M3
    humidity_range = max_humidity - min_humidity

    # --- Quantization Step (Rule 8) ---
    # Normalize to [0, 1], scale by the number of steps, round, then scale back.
    # This divides the humidity range into a fixed number of discrete levels.
    normalized_values = (humidity_values - min_humidity) / humidity_range
    stepped_values = np.round(normalized_values * HUMIDITY_STEPS) / HUMIDITY_STEPS
    quantized_humidity = (stepped_values * humidity_range) + min_humidity

    # Normalize the quantized data for color mapping
    normalized_humidity = (quantized_humidity - min_humidity) / humidity_range
    indices = (normalized_humidity * 255).astype(np.uint8)
    colors = humidity_lut[indices]
    return np.transpose(colors, (1, 0, 2))