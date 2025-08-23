# world_generator/config.py

"""
================================================================================
INTERNAL DEFAULT CONFIGURATION
================================================================================
This module contains the default, fallback internal constants for the world
generator. These values are used if they are not explicitly provided by the
user's configuration.

DO NOT MODIFY THIS FILE FOR A SPECIFIC SIMULATION.
Instead, pass a configuration dictionary to the WorldGenerator instance.
================================================================================
"""

# --- Noise Generation ---
DEFAULT_SEED = 1337
# Large prime numbers used to offset seeds for different layers, ensuring
# they are unique but deterministic from the master seed.
TEMP_SEED_OFFSET = 12347
HUMIDITY_SEED_OFFSET = 54323
NOISE_SCALE = 20000.0
NOISE_OCTAVES = 4
NOISE_PERSISTENCE = 0.5
NOISE_LACUNARITY = 2.0
TERRAIN_AMPLITUDE = 1.5

# --- Terrain & Biome Levels (Normalized 0.0 to 1.0) ---
# A dictionary is used to make it easy to pass this as a single config item.
TERRAIN_LEVELS = {
    "water": 0.31,
    "sand": 0.32,
    "grass": 0.57,
    "dirt": 0.59,
    "mountain": 1.0 # The rest is mountain
}

# --- Temperature Levels (Normalized 0.0 to 1.0) ---
TEMP_LEVELS = {
    "coldest": 0.05,
    "cold": 0.25,
    "temperate": 0.75,
    "hot": 0.95,
    "hottest": 1.0
}

# --- Default Color Mappings ---
# These are used by the renderer if no other color map is provided.
# Format: (R, G, B)
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

# --- Rendering & Performance ---
CHUNK_RESOLUTION = 100  # The number of pixels on one side of a chunk texture