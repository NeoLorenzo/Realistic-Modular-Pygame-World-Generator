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

# --- Rendering & Performance ---
CHUNK_RESOLUTION = 100  # The number of pixels on one side of a chunk texture
PLACEHOLDER_RESOLUTION = 50 # Lower-res version for instant previews (Rule 8)
CHUNK_SIZE_CM = 4000
DEFAULT_WORLD_WIDTH_CHUNKS = 260
DEFAULT_WORLD_HEIGHT_CHUNKS = 260