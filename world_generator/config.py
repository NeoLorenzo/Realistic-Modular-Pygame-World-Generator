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
DETAIL_SEED_OFFSET = 98761 # New offset for the detail layer

# --- Unit Conversion ---
# Define a constant to avoid magic numbers in the code (Rule 1)
CM_PER_KM = 100000.0

# --- Feature Scales in Kilometers ---
# These values are now intuitive. A larger number means a larger feature.
# Base layer settings (large features, e.g., continents)
TERRAIN_BASE_FEATURE_SCALE_KM = 40.0 # Continents are ~40km across
BASE_NOISE_OCTAVES = 4
BASE_NOISE_PERSISTENCE = 0.5
BASE_NOISE_LACUNARITY = 2.0

# Detail layer settings (small features, e.g., mountains, coastlines)
TERRAIN_DETAIL_FEATURE_SCALE_KM = 2.5 # Mountains are ~2.5km across
DETAIL_NOISE_OCTAVES = 6
DETAIL_NOISE_PERSISTENCE = 0.5
DETAIL_NOISE_LACUNARITY = 2.0
DETAIL_NOISE_WEIGHT = 0.25 # How much the detail layer influences the base

# Climate features (temperature, humidity) are generally very large.
CLIMATE_FEATURE_SCALE_KM = 120.0

TERRAIN_AMPLITUDE = 2.5

# --- Terrain & Biome Levels (Normalized 0.0 to 1.0) ---
# A dictionary is used to make it easy to pass this as a single config item.
TERRAIN_LEVELS = {
    "water": 0.1,
    "sand": 0.11,
    "grass": 0.13,
    "dirt": 0.3,
    "mountain": 0.5 # The rest is mountain
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
PLACEHOLDER_RESOLUTION = 16 # Lower-res version for instant previews (Rule 8)
CHUNK_SIZE_CM = 10000   # 100m = 10,000 cm. This is the core unit.
DEFAULT_WORLD_WIDTH_CHUNKS = 400
DEFAULT_WORLD_HEIGHT_CHUNKS = 275