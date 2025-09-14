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
    "deep_water": (0, 0, 50),
    "shallow_water": (26, 102, 255),
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
    """Converts an array of elevation data into an RGB color array."""
    color_map = COLOR_MAP_TERRAIN
    levels = DEFAULTS.TERRAIN_LEVELS
    bins = [levels["water"], levels["sand"], levels["grass"], levels["dirt"]]
    color_lookup = np.array([
        color_map["shallow_water"], color_map["sand"], color_map["grass"],
        color_map["dirt"], color_map["mountain"]
    ], dtype=np.uint8)
    indices = np.digitize(elevation_values, bins=bins)
    colors = color_lookup[indices]
    water_mask = indices == 0
    if np.any(water_mask):
        t = (elevation_values[water_mask] / levels["water"])[..., np.newaxis]
        c1 = np.array(color_map["deep_water"])
        c2 = np.array(color_map["shallow_water"])
        colors[water_mask] = ((1 - t) * c1 + t * c2).astype(np.uint8)
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