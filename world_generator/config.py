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
    "grass": 0.18,
    "dirt": 0.19,
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

# --- Climate Physics Abstractions (Rule 8) ---
# These constants control the temperature model using real-world units (Celsius).

# The absolute coldest and hottest temperatures the simulation can produce.
# These are used by the renderer to normalize the color map.
MIN_GLOBAL_TEMP_C = -50.0
MAX_GLOBAL_TEMP_C = 50.0

# The "thermostat" setting for the world. This is the target average
# temperature at sea level (elevation 0.1). Earth's average is ~15°C.
TARGET_SEA_LEVEL_TEMP_C = 15.0

# Controls the temperature swing from the target average based on noise.
# A value of 30 means the sea-level temperature can vary by +/- 15°C.
SEASONAL_VARIATION_C = 30.0

# The temperature drop in Celsius for a 1.0 change in elevation.
# A value of 40 means the highest peaks (elevation 1.0) will be 40°C
# colder than they would be at sea level.
LAPSE_RATE_C_PER_UNIT_ELEVATION = 40.0

# The total temperature reduction in Celsius applied at the poles.
# This creates the equator-to-pole temperature gradient.
POLAR_TEMPERATURE_DROP_C = 30.0

# The vertical position of the equator as a factor of world height (0.0=bottom, 1.0=top).
# 0.5 is the default, placing it in the middle.
EQUATOR_Y_POS_FACTOR = 0.5


# --- Humidity Realism Constants (Rule 3 & 8) ---

# Resolution factor for the pre-computed distance-to-water map.
# 0.1 means the map is 1/10th the resolution of a normal chunk.
DISTANCE_MAP_RESOLUTION_FACTOR = 0.1

# The maximum distance (in km) from a water source that influences humidity.
# Beyond this distance, the land is considered fully arid.
MAX_COASTAL_DISTANCE_KM = 150.0

# The absolute min/max humidity in grams of water per cubic meter of air.
# Used for the real-world model and for renderer normalization.
MIN_ABSOLUTE_HUMIDITY_G_M3 = 0.1
MAX_ABSOLUTE_HUMIDITY_G_M3 = 30.0

# --- Rendering & Performance ---
CHUNK_RESOLUTION = 100  # The number of pixels on one side of a chunk texture
PLACEHOLDER_RESOLUTION = 16 # Lower-res version for instant previews (Rule 8)
CHUNK_SIZE_CM = 10000   # 100m = 10,000 cm. This is the core unit.
DEFAULT_WORLD_WIDTH_CHUNKS = 400
DEFAULT_WORLD_HEIGHT_CHUNKS = 275