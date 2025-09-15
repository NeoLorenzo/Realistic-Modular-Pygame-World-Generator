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
    "grass": (34, 139, 34),
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
def get_terrain_color_array(elevation_values: np.ndarray) -> np.ndarray:
    """
    Converts an array of elevation data into an RGB color array using
    4 distinct levels for water depth.
    """
    color_map = COLOR_MAP_TERRAIN
    levels = DEFAULTS.TERRAIN_LEVELS

    # Define the elevation boundaries for land terrain types only.
    # These values represent the upper bound of each category.
    water_level = levels["water"]
    land_bins = [
        levels["sand"],
        levels["grass"],
        levels["dirt"]
    ]
    
    # Define a corresponding color lookup table for land. The order must match
    # the categories defined by the bins: sand, grass, dirt, and finally mountain
    # for everything above the last bin.
    land_color_lookup = np.array([
        color_map["sand"],
        color_map["grass"],
        color_map["dirt"],
        color_map["mountain"]
    ], dtype=np.uint8)

    # --- Land Color Calculation ---
    # Initialize a color array filled with a default (e.g., abyss color).
    colors = np.full(elevation_values.shape + (3,), color_map["abyss"], dtype=np.uint8)
    
    # Create a mask for all land pixels.
    land_mask = elevation_values >= water_level
    
    # Digitize and color only the land pixels.
    if np.any(land_mask):
        land_elevations = elevation_values[land_mask]
        indices = np.digitize(land_elevations, bins=land_bins)
        colors[land_mask] = land_color_lookup[indices]

    # --- Water Color Calculation (4 Levels) ---
    # Create a mask for all water pixels.
    water_mask = ~land_mask
    if np.any(water_mask):
        # 1. Define the elevation boundaries for the 4 water depths.
        water_bins = [
            water_level * 0.25,  # Upper bound for abyss
            water_level * 0.50,  # Upper bound for deep_water
            water_level * 0.75   # Upper bound for mid_water
        ]
        
        # 2. Define a corresponding color lookup table.
        water_color_lookup = np.array([
            color_map["abyss"],
            color_map["deep_water"],
            color_map["mid_water"],
            color_map["shallow_water"] # Default for elevations > last bin
        ], dtype=np.uint8)

        # 3. Get the elevation values for only the water pixels.
        water_elevations = elevation_values[water_mask]
        
        # 4. Use np.digitize to get an index (0-3) for each water pixel.
        water_indices = np.digitize(water_elevations, bins=water_bins)
        
        # 5. Use the indices to look up the correct color and assign it.
        colors[water_mask] = water_color_lookup[water_indices]

    return np.transpose(colors, (1, 0, 2))

def get_temperature_color_array(temp_values: np.ndarray, temp_lut: np.ndarray) -> np.ndarray:
    """Converts Celsius temperature data into an RGB color array using a pre-computed LUT."""
    min_temp_c = DEFAULTS.MIN_GLOBAL_TEMP_C
    temp_range_c = DEFAULTS.MAX_GLOBAL_TEMP_C - min_temp_c
    normalized_temp = (temp_values - min_temp_c) / temp_range_c
    indices = (normalized_temp * 255).astype(np.uint8)
    colors = temp_lut[indices]
    return np.transpose(colors, (1, 0, 2))

def get_humidity_color_array(humidity_values: np.ndarray, humidity_lut: np.ndarray) -> np.ndarray:
    """Converts absolute humidity data into an RGB color array using a pre-computed LUT."""
    min_humidity_g_m3 = DEFAULTS.MIN_ABSOLUTE_HUMIDITY_G_M3
    humidity_range_g_m3 = DEFAULTS.MAX_ABSOLUTE_HUMIDITY_G_M3 - min_humidity_g_m3
    normalized_humidity = (humidity_values - min_humidity_g_m3) / humidity_range_g_m3
    indices = (normalized_humidity * 255).astype(np.uint8)
    colors = humidity_lut[indices]
    return np.transpose(colors, (1, 0, 2))