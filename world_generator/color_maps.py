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

# --- Biome ID Constants (Rule 1) ---
# An integer enum for each distinct terrain/biome type.
BIOME_ID_ABYSS = 0
BIOME_ID_DEEP_WATER = 1
BIOME_ID_MID_WATER = 2
BIOME_ID_SHALLOW_WATER = 3
BIOME_ID_SAND = 4
BIOME_ID_SUBTROPICAL_DESERT = 5
BIOME_ID_TEMPERATE_GRASSLAND = 6
BIOME_ID_SAVANNA = 7
BIOME_ID_DIRT = 8
BIOME_ID_MOUNTAIN = 9
BIOME_ID_SNOW = 10
BIOME_ID_ICE = 11
BIOME_ID_TUNDRA = 12
BIOME_ID_TAIGA = 13
BIOME_ID_TEMPERATE_FOREST = 14
BIOME_ID_TEMPERATE_RAINFOREST = 15
BIOME_ID_TROPICAL_SEASONAL_FOREST = 16
BIOME_ID_TROPICAL_RAINFOREST = 17


# --- Default Color Mappings ---
COLOR_MAP_TERRAIN = {
    # New 4-level water depth palette
    "abyss": (0, 0, 50),
    "deep_water": (10, 20, 80),
    "mid_water": (20, 40, 120),
    "shallow_water": (26, 102, 255),
    "sand": (240, 230, 140),
    "dirt": (139, 69, 19),
    "mountain": (112, 128, 144),
    # New Whittaker Biome Colors
    "subtropical_desert": (205, 170, 125),
    "temperate_grassland": (154, 205, 50),
    "savanna": (189, 183, 107),
    "tundra": (150, 150, 120),
    "taiga": (0, 80, 60),
    "temperate_forest": (34, 139, 34),
    "temperate_rainforest": (0, 100, 0),
    "tropical_seasonal_forest": (50, 150, 50),
    "tropical_rainforest": (0, 60, 0),
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

def create_biome_color_lut() -> np.ndarray:
    """Creates a LUT where the index is the Biome ID and the value is the RGB color."""
    return np.array([
        COLOR_MAP_TERRAIN["abyss"],                       # 0
        COLOR_MAP_TERRAIN["deep_water"],                  # 1
        COLOR_MAP_TERRAIN["mid_water"],                   # 2
        COLOR_MAP_TERRAIN["shallow_water"],               # 3
        COLOR_MAP_TERRAIN["sand"],                        # 4
        COLOR_MAP_TERRAIN["subtropical_desert"],          # 5
        COLOR_MAP_TERRAIN["temperate_grassland"],         # 6
        COLOR_MAP_TERRAIN["savanna"],                     # 7
        COLOR_MAP_TERRAIN["dirt"],                        # 8
        COLOR_MAP_TERRAIN["mountain"],                    # 9
        COLOR_SNOW,                                       # 10
        COLOR_ICE,                                        # 11
        COLOR_MAP_TERRAIN["tundra"],                      # 12
        COLOR_MAP_TERRAIN["taiga"],                       # 13
        COLOR_MAP_TERRAIN["temperate_forest"],            # 14
        COLOR_MAP_TERRAIN["temperate_rainforest"],        # 15
        COLOR_MAP_TERRAIN["tropical_seasonal_forest"],    # 16
        COLOR_MAP_TERRAIN["tropical_rainforest"],         # 17
    ], dtype=np.uint8)

# --- Biome & Color Array Generation Functions ---
EXPOSED_ROCK_SOIL_THRESHOLD = 0.001

def _classify_climate_biomes(biome_map: np.ndarray, temperature_values: np.ndarray, humidity_values: np.ndarray, biome_zone_mask: np.ndarray) -> np.ndarray:
    """Helper to apply climate-based biome classification to a specific zone."""
    thresholds = DEFAULTS.BIOME_THRESHOLDS
    if np.any(biome_zone_mask):
        zone_temps = temperature_values[biome_zone_mask]
        zone_humidity = humidity_values[biome_zone_mask]

        # --- Whittaker Biome Classification ---
        # The order of these conditions is critical. We start with the most
        # restrictive (e.g., coldest, driest, wettest) and work our way to the
        # more general temperate biomes.

        conditions = [
            # 1. Coldest Biomes (regardless of humidity)
            zone_temps < thresholds["tundra_max_temp"],
            zone_temps < thresholds["taiga_max_temp"],

            # 2. Driest Biomes (hot and cold deserts)
            (zone_humidity < thresholds["desert_max_humidity"]) & (zone_temps >= thresholds["hot_desert_min_temp"]),
            zone_humidity < thresholds["desert_max_humidity"],

            # 3. Wettest Biomes (rainforests)
            (zone_temps > thresholds["temperate_max_temp"]) & (zone_humidity > thresholds["forest_max_humidity"]),
            (zone_temps <= thresholds["temperate_max_temp"]) & (zone_humidity > thresholds["forest_max_humidity"]),

            # 4. Mid-range Tropical Biomes
            (zone_temps > thresholds["temperate_max_temp"]) & (zone_humidity > thresholds["grassland_max_humidity"]),
            (zone_temps > thresholds["temperate_max_temp"]), # Catches Savanna

            # 5. Mid-range Temperate Biomes (default cases)
            zone_humidity > thresholds["grassland_max_humidity"],
        ]

        choices = [
            BIOME_ID_TUNDRA,
            BIOME_ID_TAIGA,
            BIOME_ID_SUBTROPICAL_DESERT,
            BIOME_ID_DIRT, # Cold desert/barren
            BIOME_ID_TROPICAL_RAINFOREST,
            BIOME_ID_TEMPERATE_RAINFOREST,
            BIOME_ID_TROPICAL_SEASONAL_FOREST,
            BIOME_ID_SAVANNA,
            BIOME_ID_TEMPERATE_FOREST,
        ]

        # The final default is Temperate Grassland
        biome_map[biome_zone_mask] = np.select(conditions, choices, default=BIOME_ID_TEMPERATE_GRASSLAND)
    return biome_map

def calculate_biome_map(elevation_values: np.ndarray, temperature_values: np.ndarray, humidity_values: np.ndarray, soil_depth_data: np.ndarray) -> np.ndarray:
    """
    Performs the expensive biome classification and returns an integer array of biome IDs.
    """
    levels = DEFAULTS.TERRAIN_LEVELS
    thresholds = DEFAULTS.BIOME_THRESHOLDS
    water_level = levels["water"]

    # Initialize the biome map with a default value (e.g., abyss)
    biome_map = np.full(elevation_values.shape, BIOME_ID_ABYSS, dtype=np.uint8)

    # --- 1. Base Elevation Classification ---
    land_mask = elevation_values >= water_level
    water_mask = ~land_mask

    if np.any(land_mask):
        land_elevations = elevation_values[land_mask]
        conditions = [
            land_elevations < levels["sand"],
            land_elevations < levels["grass"],
            land_elevations < levels["dirt"]
        ]
        # Replace the old, undefined BIOME_ID_GRASS with its new equivalent.
        choices = [BIOME_ID_SAND, BIOME_ID_TEMPERATE_FOREST, BIOME_ID_DIRT]
        biome_map[land_mask] = np.select(conditions, choices, default=BIOME_ID_MOUNTAIN)

    if np.any(water_mask):
        water_elevations = elevation_values[water_mask]
        conditions = [
            water_elevations < water_level * 0.25,
            water_elevations < water_level * 0.50,
            water_elevations < water_level * 0.75
        ]
        choices = [BIOME_ID_ABYSS, BIOME_ID_DEEP_WATER, BIOME_ID_MID_WATER]
        biome_map[water_mask] = np.select(conditions, choices, default=BIOME_ID_SHALLOW_WATER)

    # --- 2. Bedrock Exposure Layer ---
    exposed_rock_mask = (soil_depth_data < EXPOSED_ROCK_SOIL_THRESHOLD) & land_mask
    if np.any(exposed_rock_mask):
        biome_map[exposed_rock_mask] = BIOME_ID_MOUNTAIN

    # --- 3. Climate-Driven Biome Logic ---
    biome_zone_mask = (elevation_values >= levels["sand"]) & (elevation_values < levels["dirt"]) & ~exposed_rock_mask
    biome_map = _classify_climate_biomes(biome_map, temperature_values, humidity_values, biome_zone_mask)

    # --- 4. Final Frost and Ice Layers (Override everything else) ---
    ice_mask = (temperature_values <= DEFAULTS.ICE_FORMATION_TEMP_C) & water_mask
    if np.any(ice_mask):
        biome_map[ice_mask] = BIOME_ID_ICE

    snow_mask = (temperature_values <= DEFAULTS.SNOW_LINE_TEMP_C) & land_mask
    if np.any(snow_mask):
        biome_map[snow_mask] = BIOME_ID_SNOW
        
    return biome_map

def get_terrain_color_array(biome_map: np.ndarray, biome_lut: np.ndarray) -> np.ndarray:
    """
    Converts a pre-calculated integer biome map into an RGB color array
    using a pre-computed lookup table. This is a very fast operation.
    """
    colors = biome_lut[biome_map]
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

def get_elevation_color_array(elevation_values: np.ndarray) -> np.ndarray:
    """Converts normalized elevation data [0, 1] into a grayscale RGB color array."""
    # Scale the normalized [0, 1] float values to [0, 255] integer grayscale values.
    gray_values = (elevation_values * 255).astype(np.uint8)
    
    # Create a 3-channel RGB array by stacking the grayscale values.
    # np.stack is efficient for this operation.
    colors = np.stack([gray_values] * 3, axis=-1)
    
    return np.transpose(colors, (1, 0, 2))

def get_tectonic_color_array(plate_id_map: np.ndarray, num_plates: int, seed: int) -> np.ndarray:
    """Generates a color array where each tectonic plate has a unique, deterministic color."""
    # 1. Create a deterministic but random color for each plate ID.
    rng = np.random.default_rng(seed)
    color_palette = rng.integers(0, 256, size=(num_plates, 3), dtype=np.uint8)
    
    # 2. Use the plate_id_map as indices to look up colors from the palette.
    colors = color_palette[plate_id_map]
    
    return np.transpose(colors, (1, 0, 2))