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
DETAIL_SEED_OFFSET = 98761
TECTONIC_PLATE_SEED_OFFSET = 54321
MOUNTAIN_UPLIFT_SEED_OFFSET = 25391 # New offset for mountain range noise

# HUMIDITY_SEED_OFFSET is deprecated as humidity is now deterministic.

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
    "grass": 0.38,
    "dirt": 0.49,
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

# The temperature in Celsius at or below which snow will appear on land.
# 0.0 is the freezing point of water, a realistic default (Rule 3).
SNOW_LINE_TEMP_C = 0.0

# The temperature in Celsius at or below which water will turn to ice.
# Set slightly below 0.0 to account for water's thermal properties.
ICE_FORMATION_TEMP_C = -2.0


# --- Prevailing Winds & Rain Shadow (Rule 8) ---
# The global direction from which the wind blows, in degrees (0=E, 90=N, 180=W, 270=S).
# A westerly wind (coming from the west) is a common mid-latitude pattern on Earth.
PREVAILING_WIND_DIRECTION_DEGREES = 180.0

# The distance in km that is checked "upwind" to see if mountains are blocking moisture.
RAIN_SHADOW_CHECK_DISTANCE_KM = 200.0

# The strength of the rain shadow effect. 0.0 means no effect, 1.0 is a very strong effect.
RAIN_SHADOW_STRENGTH = 0.8

# The minimum height difference (normalized elevation) to be considered a mountain for occlusion.
RAIN_SHADOW_MOUNTAIN_THRESHOLD = 0.3


# --- Biome Thresholds (Rule 3 & 8) ---
# A dictionary to hold all climate parameters that define biome transitions.
# These values are based on a simplified Whittaker biome model.
BIOME_THRESHOLDS = {
    # Temperature Bands (°C)
    "tundra_max_temp": -5.0,
    "taiga_max_temp": 3.0,
    "temperate_max_temp": 18.0,
    # tropical is anything above temperate_max_temp

    # Humidity Bands (g/m³)
    "desert_max_humidity": 5.0,
    "grassland_max_humidity": 10.0,
    "forest_max_humidity": 17.0,
    # rainforest is anything above forest_max_humidity

    # Special Overrides
    "hot_desert_min_temp": 20.0,
}


# --- Humidity Realism Constants (Rule 3 & 8) ---

# Resolution factor for the pre-computed distance-to-water map.
# 0.1 means the map is 1/10th the resolution of a normal chunk.
DISTANCE_MAP_RESOLUTION_FACTOR = 0.1

# The maximum distance (in km) from a water source that influences humidity.
# Beyond this distance, the land is considered fully arid.
MAX_COASTAL_DISTANCE_KM = 150.0

# A power factor for the coastal humidity falloff.
# Values > 1.0 make humidity drop off very quickly near the coast.
# Values < 1.0 create a more gradual, gentle slope.
HUMIDITY_COASTAL_FALLOFF_RATE = 2.5

# The absolute min/max humidity in grams of water per cubic meter of air.
# Used for the real-world model and for renderer normalization.
MIN_ABSOLUTE_HUMIDITY_G_M3 = 0.0
MAX_ABSOLUTE_HUMIDITY_G_M3 = 30.0

# --- Tectonics & Geology (Rule 8) ---
DEFAULT_NUM_TECTONIC_PLATES = 2
# The maximum possible depth of soil, in normalized elevation units [0, 1].
# This is the value added to bedrock in perfectly flat areas.
MAX_SOIL_DEPTH_UNITS = 0.05
# The feature scale for the noise that creates the mountain ranges themselves.
MOUNTAIN_UPLIFT_FEATURE_SCALE_KM = 15.0
# The radius, in km, around a plate boundary where mountains will form.
MOUNTAIN_INFLUENCE_RADIUS_KM = 0.05
# A multiplier for how high mountains get at the peak of a plate boundary.
# This now controls the blending of the dedicated uplift noise layer.
MOUNTAIN_UPLIFT_STRENGTH = 2.5

# --- Rendering & Performance ---
CHUNK_RESOLUTION = 100  # The number of pixels on one side of a chunk texture
PLACEHOLDER_RESOLUTION = 8 # Lower-res version for instant previews (Rule 8)
CHUNK_SIZE_CM = 10000   # 100m = 10,000 cm. This is the core unit.
DEFAULT_WORLD_WIDTH_CHUNKS = 10
DEFAULT_WORLD_HEIGHT_CHUNKS = 10

# --- World Edge Control (Rule 8) ---
# The generation mode for the world's edges.
# 'default': No change, terrain generates to the edge.
# 'island': Fades the terrain elevation to water level at the edges.
# 'valley': Fades the terrain elevation to mountain level at the edges.
WORLD_EDGE_MODE = 'default'
# The distance from the edge, as a percentage of the world's shorter dimension,
# over which the blend effect occurs. 0.1 means the fade happens over the outer 10%.
WORLD_EDGE_BLEND_DISTANCE = 0.1