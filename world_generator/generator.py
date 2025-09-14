# world_generator/generator.py

"""
================================================================================
CORE WORLD GENERATOR
================================================================================
This module contains the main WorldGenerator class, responsible for creating
and providing access to raw world data (e.g., elevation, temperature).

Data Contract:
---------------
- Inputs (on initialization):
    - config (dict): A dictionary of simulation parameters which can override
      the internal defaults. Expected keys include 'seed', 'noise_scale', etc.
    - logger: A configured Python logging object for runtime messages.
- Outputs (from methods):
    - NumPy arrays containing normalized world data [0, 1].
- Side Effects: Logs messages using the provided logger.
- Invariants: Given the same seed and configuration, the output is deterministic.
================================================================================
"""

import numpy as np
import logging
import time
from scipy.ndimage import distance_transform_edt

from . import config as DEFAULTS
from . import noise

class WorldGenerator:
    """
    Generates and manages the raw data for a procedurally generated world.
    This class is backend-only and does not handle any visualization.
    """
    def __init__(self, config: dict, logger: logging.Logger):
        """
        Initializes the world generator.

        Args:
            config (dict): User-defined parameters to override defaults.
            logger (logging.Logger): The logger instance for all output.
        """
        self.logger = logger
        self.user_config = config
        self.logger.info("WorldGenerator initializing...")

        # --- Consolidate Configuration ---
        # The generator is now the single source of truth for its settings,
        # merging user overrides with its internal defaults.
        self.settings = {
            'seed': self.user_config.get('seed', DEFAULTS.DEFAULT_SEED),
            'temp_seed_offset': self.user_config.get('temp_seed_offset', DEFAULTS.TEMP_SEED_OFFSET),
            'humidity_seed_offset': self.user_config.get('humidity_seed_offset', DEFAULTS.HUMIDITY_SEED_OFFSET),
            'detail_seed_offset': self.user_config.get('detail_seed_offset', DEFAULTS.DETAIL_SEED_OFFSET),
            
            # Load human-readable feature scales (in km)
            'terrain_base_feature_scale_km': self.user_config.get('terrain_base_feature_scale_km', DEFAULTS.TERRAIN_BASE_FEATURE_SCALE_KM),
            'terrain_detail_feature_scale_km': self.user_config.get('terrain_detail_feature_scale_km', DEFAULTS.TERRAIN_DETAIL_FEATURE_SCALE_KM),
            'climate_feature_scale_km': self.user_config.get('climate_feature_scale_km', DEFAULTS.CLIMATE_FEATURE_SCALE_KM),

            'base_noise_octaves': self.user_config.get('base_noise_octaves', DEFAULTS.BASE_NOISE_OCTAVES),
            'base_noise_persistence': self.user_config.get('base_noise_persistence', DEFAULTS.BASE_NOISE_PERSISTENCE),
            'base_noise_lacunarity': self.user_config.get('base_noise_lacunarity', DEFAULTS.BASE_NOISE_LACUNARITY),

            'detail_noise_octaves': self.user_config.get('detail_noise_octaves', DEFAULTS.DETAIL_NOISE_OCTAVES),
            'detail_noise_persistence': self.user_config.get('detail_noise_persistence', DEFAULTS.DETAIL_NOISE_PERSISTENCE),
            'detail_noise_lacunarity': self.user_config.get('detail_noise_lacunarity', DEFAULTS.DETAIL_NOISE_LACUNARITY),
            'detail_noise_weight': self.user_config.get('detail_noise_weight', DEFAULTS.DETAIL_NOISE_WEIGHT),

            'terrain_amplitude': self.user_config.get('terrain_amplitude', DEFAULTS.TERRAIN_AMPLITUDE),
            'min_global_temp_c': self.user_config.get('min_global_temp_c', DEFAULTS.MIN_GLOBAL_TEMP_C),
            'max_global_temp_c': self.user_config.get('max_global_temp_c', DEFAULTS.MAX_GLOBAL_TEMP_C),
            'target_sea_level_temp_c': self.user_config.get('target_sea_level_temp_c', DEFAULTS.TARGET_SEA_LEVEL_TEMP_C),
            'seasonal_variation_c': self.user_config.get('seasonal_variation_c', DEFAULTS.SEASONAL_VARIATION_C),
            'lapse_rate_c_per_unit_elevation': self.user_config.get('lapse_rate_c_per_unit_elevation', DEFAULTS.LAPSE_RATE_C_PER_UNIT_ELEVATION),
            'terrain_levels': self.user_config.get('terrain_levels', DEFAULTS.TERRAIN_LEVELS),
            'distance_map_resolution_factor': self.user_config.get('distance_map_resolution_factor', DEFAULTS.DISTANCE_MAP_RESOLUTION_FACTOR),
            'max_coastal_distance_km': self.user_config.get('max_coastal_distance_km', DEFAULTS.MAX_COASTAL_DISTANCE_KM),
            'min_absolute_humidity_g_m3': self.user_config.get('min_absolute_humidity_g_m3', DEFAULTS.MIN_ABSOLUTE_HUMIDITY_G_M3),
            'max_absolute_humidity_g_m3': self.user_config.get('max_absolute_humidity_g_m3', DEFAULTS.MAX_ABSOLUTE_HUMIDITY_G_M3),
            'chunk_size_cm': self.user_config.get('chunk_size_cm', DEFAULTS.CHUNK_SIZE_CM),
            'world_width_chunks': self.user_config.get('world_width_chunks', DEFAULTS.DEFAULT_WORLD_WIDTH_CHUNKS),
            'world_height_chunks': self.user_config.get('world_height_chunks', DEFAULTS.DEFAULT_WORLD_HEIGHT_CHUNKS),
        }

        # --- Convert KM feature scales to internal CM noise scales ---
        # This is the core of the unit translation. The rest of the code can
        # continue to use the '_noise_scale' values without change.
        self.settings['base_noise_scale'] = self.settings['terrain_base_feature_scale_km'] * DEFAULTS.CM_PER_KM
        self.settings['detail_noise_scale'] = self.settings['terrain_detail_feature_scale_km'] * DEFAULTS.CM_PER_KM
        self.settings['climate_noise_scale'] = self.settings['climate_feature_scale_km'] * DEFAULTS.CM_PER_KM

        # --- Public Properties for easy access ---
        self.seed = self.settings['seed']
        self.world_width_cm = self.settings['world_width_chunks'] * self.settings['chunk_size_cm']
        self.world_height_cm = self.settings['world_height_chunks'] * self.settings['chunk_size_cm']

        # --- Initialize Noise ---
        p = np.arange(256, dtype=int)
        rng = np.random.default_rng(self.seed)
        rng.shuffle(p)
        self._p = np.stack([p, p]).flatten() # Permutation table for noise

        self.logger.info(f"WorldGenerator initialized with seed: {self.seed}")
        # Log dimensions in both base units (cm) and human-readable units (km) for clarity.
        world_width_km = self.world_width_cm / 100000.0
        world_height_km = self.world_height_cm / 100000.0
        self.logger.info(
            f"World dimensions: {self.settings['world_width_chunks']}x"
            f"{self.settings['world_height_chunks']} chunks "
            f"({self.world_width_cm}x{self.world_height_cm} cm / "
            f"{world_width_km:.1f}x{world_height_km:.1f} km)"
        )

        # --- Pre-computation Step for Distance-to-Water (Rule 8) ---
        self._distance_map = None
        self._distance_map_scale_x = 1.0
        self._distance_map_scale_y = 1.0
        self._precompute_distance_map()

    def get_elevation(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """
        Generates elevation data by stacking two layers of Perlin noise.
        - A low-frequency base layer for continents.
        - A high-frequency detail layer for mountains and coastal features.
        """
        # 1. Generate the low-frequency base noise for continental shapes
        base_noise = noise.perlin_noise_2d(
            self._p,
            (x_coords) / self.settings['base_noise_scale'],
            (y_coords) / self.settings['base_noise_scale'],
            octaves=self.settings['base_noise_octaves'],
            persistence=self.settings['base_noise_persistence'],
            lacunarity=self.settings['base_noise_lacunarity']
        )

        # 2. Generate high-frequency detail noise
        # We use a seed offset to ensure the detail layer is different from other layers.
        detail_noise = noise.perlin_noise_2d(
            self._p,
            (x_coords + self.settings['detail_seed_offset']) / self.settings['detail_noise_scale'],
            (y_coords + self.settings['detail_seed_offset']) / self.settings['detail_noise_scale'],
            octaves=self.settings['detail_noise_octaves'],
            persistence=self.settings['detail_noise_persistence'],
            lacunarity=self.settings['detail_noise_lacunarity']
        )

        # 3. Combine the layers. The detail layer is scaled by its weight.
        combined_noise = base_noise + (detail_noise * self.settings['detail_noise_weight'])

        # 4. Normalize the result back to the [0, 1] range using a fixed theoretical bound.
        # This is the critical fix to prevent seams between chunks.
        # The theoretical max value is 1.0 (from base) + weight (from detail).
        theoretical_max = 1.0 + self.settings['detail_noise_weight']
        normalized_noise = (combined_noise + theoretical_max) / (2 * theoretical_max)

        # 5. Apply amplitude to shape the final terrain (e.g., flatten valleys, sharpen peaks)
        return np.power(normalized_noise, self.settings['terrain_amplitude'])

    def _generate_base_noise(self, x_coords: np.ndarray, y_coords: np.ndarray, seed_offset: int = 0, scale: float = 1.0) -> np.ndarray:
        """A generic helper to produce a normalized noise map."""
        # self.logger.debug(f"Generating base noise for {x_coords.size} points with offset {seed_offset}.")
        
        # Applying a seed offset to the coordinates ensures each map is unique.
        scaled_x = (x_coords + seed_offset) / scale
        scaled_y = (y_coords + seed_offset) / scale

        # Note: Climate uses the 'base' octave/persistence settings for simplicity.
        # This could be expanded with 'climate_octaves' etc. if more control is needed.
        noise_values = noise.perlin_noise_2d(
            self._p, scaled_x, scaled_y,
            octaves=self.settings['base_noise_octaves'],
            persistence=self.settings['base_noise_persistence'],
            lacunarity=self.settings['base_noise_lacunarity']
        )
        # Normalize values to range [0, 1]
        return (noise_values + 1) / 2

    def get_temperature(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """
        Generates temperature data in Celsius using a real-world model.
        The final output is an array of Celsius values, NOT normalized data.
        """
        # 1. Generate base noise [0, 1] for temperature variation.
        noise = self._generate_base_noise(
            x_coords, y_coords,
            seed_offset=self.settings['temp_seed_offset'],
            scale=self.settings['climate_noise_scale']
        )

        # 2. Calculate the sea-level temperature in Celsius. This centers the
        #    temperature variation around the target "thermostat" setting.
        sea_level_temp_c = (
            self.settings['target_sea_level_temp_c'] +
            (noise - 0.5) * self.settings['seasonal_variation_c']
        )

        # 3. Get the corresponding elevation data [0, 1].
        elevation = self.get_elevation(x_coords, y_coords)

        # 4. Calculate the temperature drop due to altitude in Celsius.
        altitude_drop_c = elevation * self.settings['lapse_rate_c_per_unit_elevation']

        # 5. Calculate the final temperature by applying the altitude drop.
        final_temp_c = sea_level_temp_c - altitude_drop_c

        # 6. Clamp the result to the simulation's absolute min/max bounds.
        return np.clip(
            final_temp_c,
            self.settings['min_global_temp_c'],
            self.settings['max_global_temp_c']
        )

    def _precompute_distance_map(self):
        """
        Performs a one-time, low-resolution analysis of the entire world to
        generate a distance-to-water map. This is a powerful abstraction that
        enables realistic, distance-based climate effects.
        """
        self.logger.info("Pre-computing world distance map (this may take a moment)...")
        start_time = time.perf_counter()

        res_factor = self.settings['distance_map_resolution_factor']
        map_width = int(self.settings['world_width_chunks'] * res_factor)
        map_height = int(self.settings['world_height_chunks'] * res_factor)

        # 1. Create a low-resolution grid of the entire world.
        wx = np.linspace(0, self.world_width_cm, map_width)
        wy = np.linspace(0, self.world_height_cm, map_height)
        wx_grid, wy_grid = np.meshgrid(wx, wy)

        # 2. Get elevation data for this low-res grid.
        elevation_map = self.get_elevation(wx_grid, wy_grid)
        water_level = self.settings['terrain_levels']['water']

        # 3. Create a binary mask where `True` represents water.
        water_mask = elevation_map < water_level

        # 4. Use SciPy's highly optimized Euclidean Distance Transform.
        #    This calculates, for every non-water point, the distance to the
        #    nearest water point. The result is in grid units.
        distance_grid_units = distance_transform_edt(np.logical_not(water_mask))

        # 5. Convert grid unit distance to real-world kilometers.
        cm_per_grid_cell_x = self.world_width_cm / map_width
        km_per_grid_cell_x = cm_per_grid_cell_x / DEFAULTS.CM_PER_KM
        self._distance_map = distance_grid_units * km_per_grid_cell_x

        # 6. Store scaling factors for the sampling helper method.
        self._distance_map_scale_x = map_width / self.world_width_cm
        self._distance_map_scale_y = map_height / self.world_height_cm

        end_time = time.perf_counter()
        self.logger.info(f"Distance map pre-computation complete in {end_time - start_time:.2f} seconds.")

    def _sample_distance_map(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """
        Samples distance values from the pre-computed low-resolution map.
        Uses nearest-neighbor sampling for performance.
        """
        # Convert world coordinates (cm) to low-res map indices.
        map_x = (x_coords * self._distance_map_scale_x).astype(int)
        map_y = (y_coords * self._distance_map_scale_y).astype(int)

        # Clamp indices to be within the map bounds.
        map_x = np.clip(map_x, 0, self._distance_map.shape[1] - 1)
        map_y = np.clip(map_y, 0, self._distance_map.shape[0] - 1)

        # Return the distance values from the map.
        return self._distance_map[map_y, map_x]

    def get_humidity(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """
        Generates absolute humidity (g/m³) using a realistic model based on
        temperature, distance from water, and local noise.
        """
        # 1. Get temperature in Celsius, as it's the primary driver of humidity.
        temperature_c = self.get_temperature(x_coords, y_coords)

        # 2. Calculate saturation humidity (max possible g/m³) based on temperature.
        #    This is a simplified scientific abstraction (Rule 8) of the
        #    Clausius-Clapeyron relation. Hotter air can hold more moisture.
        saturation_humidity = 5.0 * np.exp(temperature_c / 15.0)

        # 3. Get distance to the nearest water source from the pre-computed map.
        distance_km = self._sample_distance_map(x_coords, y_coords)

        # 4. Calculate relative humidity [0, 1] based on distance.
        #    This creates a smooth, linear falloff from the coast to the arid limit.
        normalized_distance = distance_km / self.settings['max_coastal_distance_km']
        relative_humidity = 1.0 - np.clip(normalized_distance, 0, 1)

        # 5. Add local variation with Perlin noise.
        base_humidity_noise = self._generate_base_noise(
            x_coords, y_coords,
            seed_offset=self.settings['humidity_seed_offset'],
            scale=self.settings['climate_noise_scale']
        )

        # 6. Combine the factors to get the final absolute humidity.
        #    The noise here acts as a percentage of the potential humidity.
        final_humidity_g_m3 = (
            saturation_humidity * relative_humidity * base_humidity_noise
        )

        # 7. Clamp to the simulation's absolute min/max bounds.
        return np.clip(
            final_humidity_g_m3,
            self.settings['min_absolute_humidity_g_m3'],
            self.settings['max_absolute_humidity_g_m3']
        )