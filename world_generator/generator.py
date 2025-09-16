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
from scipy.ndimage import distance_transform_edt, map_coordinates

from . import config as DEFAULTS
from . import noise

class WorldGenerator:
    """
    Generates and manages the raw data for a procedurally generated world.
    This class is backend-only and does not handle any visualization.
    """
    def __init__(self, config: dict, logger: logging.Logger, distance_map_data: dict = None):
        """
        Initializes the world generator.

        Args:
            config (dict): User-defined parameters to override defaults.
            logger (logging.Logger): The logger instance for all output.
            distance_map_data (dict, optional): Pre-computed distance map data to inject.
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
            'polar_temperature_drop_c': self.user_config.get('polar_temperature_drop_c', DEFAULTS.POLAR_TEMPERATURE_DROP_C),
            'equator_y_pos_factor': self.user_config.get('equator_y_pos_factor', DEFAULTS.EQUATOR_Y_POS_FACTOR),
            'terrain_levels': self.user_config.get('terrain_levels', DEFAULTS.TERRAIN_LEVELS),
            'distance_map_resolution_factor': self.user_config.get('distance_map_resolution_factor', DEFAULTS.DISTANCE_MAP_RESOLUTION_FACTOR),
            'max_coastal_distance_km': self.user_config.get('max_coastal_distance_km', DEFAULTS.MAX_COASTAL_DISTANCE_KM),
            'min_absolute_humidity_g_m3': self.user_config.get('min_absolute_humidity_g_m3', DEFAULTS.MIN_ABSOLUTE_HUMIDITY_G_M3),
            'max_absolute_humidity_g_m3': self.user_config.get('max_absolute_humidity_g_m3', DEFAULTS.MAX_ABSOLUTE_HUMIDITY_G_M3),
            'ice_formation_temp_c': self.user_config.get('ice_formation_temp_c', DEFAULTS.ICE_FORMATION_TEMP_C),
            'biome_thresholds': self.user_config.get('biome_thresholds', DEFAULTS.BIOME_THRESHOLDS),
            'prevailing_wind_direction_degrees': self.user_config.get('prevailing_wind_direction_degrees', DEFAULTS.PREVAILING_WIND_DIRECTION_DEGREES),
            'rain_shadow_check_distance_km': self.user_config.get('rain_shadow_check_distance_km', DEFAULTS.RAIN_SHADOW_CHECK_DISTANCE_KM),
            'rain_shadow_strength': self.user_config.get('rain_shadow_strength', DEFAULTS.RAIN_SHADOW_STRENGTH),
            'rain_shadow_mountain_threshold': self.user_config.get('rain_shadow_mountain_threshold', DEFAULTS.RAIN_SHADOW_MOUNTAIN_THRESHOLD),
            'humidity_coastal_falloff_rate': self.user_config.get('humidity_coastal_falloff_rate', DEFAULTS.HUMIDITY_COASTAL_FALLOFF_RATE),
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

        # --- Pre-computation Steps (Rule 8) ---
        # All pre-computation has been removed. The generator is now stateless
        # between calls, ensuring that changes to parameters like terrain_amplitude
        # are correctly reflected in the humidity calculations.
        pass

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

    def get_temperature(self, x_coords: np.ndarray, y_coords: np.ndarray, elevation_data: np.ndarray = None, base_noise: np.ndarray = None) -> np.ndarray:
        """
        Generates temperature data in Celsius.
        Can accept pre-computed elevation_data and base_noise to avoid recalculation.
        """
        # 1. Generate base noise [0, 1] for temperature variation if not provided.
        if base_noise is None:
            noise = self._generate_base_noise(
                x_coords, y_coords,
                seed_offset=self.settings['temp_seed_offset'],
                scale=self.settings['climate_noise_scale']
            )
        else:
            noise = base_noise

        # 2. Calculate the sea-level temperature in Celsius. This is re-calibrated
        #    to ensure the 'target_sea_level_temp_c' remains the true global average.
        #    We add half of the polar drop to the base to compensate for the
        #    average reduction that will be applied across the globe.
        average_latitude_offset = self.settings['polar_temperature_drop_c'] / 2.0
        sea_level_temp_c = (
            self.settings['target_sea_level_temp_c'] + average_latitude_offset +
            (noise - 0.5) * self.settings['seasonal_variation_c']
        )

        # 3. Get the corresponding elevation data [0, 1].
        #    If elevation_data is not provided, calculate it. Otherwise, use the cached version.
        if elevation_data is None:
            elevation_data = self.get_elevation(x_coords, y_coords)

        # 4. Calculate the temperature drop due to altitude in Celsius.
        altitude_drop_c = elevation_data * self.settings['lapse_rate_c_per_unit_elevation']

        # 5. Calculate the temperature after altitude adjustment.
        final_temp_c = sea_level_temp_c - altitude_drop_c

        # 6. NEW: Apply latitudinal temperature gradient (equator-to-pole effect).
        # This is a critical step for global realism.
        equator_y_cm = self.world_height_cm * self.settings['equator_y_pos_factor']
        pole_dist_cm = self.world_height_cm * (1.0 - self.settings['equator_y_pos_factor'])
        
        dist_from_equator_cm = np.abs(y_coords - equator_y_cm)
        
        # Normalize distance to [0, 1], where 0 is the equator and 1 is a pole.
        # We use a safe division to avoid errors if pole_dist_cm is zero.
        normalized_polar_dist = np.divide(
            dist_from_equator_cm,
            pole_dist_cm,
            out=np.zeros_like(dist_from_equator_cm, dtype=float),
            where=pole_dist_cm!=0
        )
        
        latitude_drop_c = normalized_polar_dist * self.settings['polar_temperature_drop_c']
        final_temp_c -= latitude_drop_c

        # 7. Clamp the result to the simulation's absolute min/max bounds.
        return np.clip(
            final_temp_c,
            self.settings['min_global_temp_c'],
            self.settings['max_global_temp_c']
        )

    def _sample_distance_map(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """
        Samples distance values from the pre-computed low-resolution map.
        Uses nearest-neighbor sampling for performance.
        """
        # Convert world coordinates (cm) to low-res map indices.
        map_x = (x_coords * self._map_scale_x).astype(int)
        map_y = (y_coords * self._map_scale_y).astype(int)

        # Clamp indices to be within the map bounds.
        map_x = np.clip(map_x, 0, self._distance_map.shape[1] - 1)
        map_y = np.clip(map_y, 0, self._distance_map.shape[0] - 1)

        # Return the distance values from the map.
        return self._distance_map[map_y, map_x]

    def get_humidity(self, x_coords: np.ndarray, y_coords: np.ndarray, elevation_data: np.ndarray, temperature_data_c: np.ndarray) -> np.ndarray:
        """
        Generates absolute humidity (g/m³) via on-the-fly analysis of the
        final elevation data. This ensures humidity is always perfectly
        synchronized with the current state of the world terrain.
        """
        # 1. --- On-the-fly Environmental Analysis ---
        
        # a) Find water sources from the provided, final elevation data.
        water_level = self.settings['terrain_levels']['water']
        water_mask = elevation_data < water_level

        # b) Calculate distance to the nearest water for every point.
        # If there is no water, all distances will be infinite.
        distance_grid_units = distance_transform_edt(np.logical_not(water_mask))
        
        # c) Calculate coastal factor with the new falloff rate.
        # This is now done in grid units for simplicity and performance.
        grid_falloff_dist = self.settings['max_coastal_distance_km'] * (x_coords.shape[1] / (self.world_width_cm / DEFAULTS.CM_PER_KM))
        normalized_distance = distance_grid_units / grid_falloff_dist
        
        coastal_factor = 1.0 - np.clip(normalized_distance, 0, 1)
        coastal_factor = np.power(coastal_factor, self.settings['humidity_coastal_falloff_rate'])

        # d) Calculate rain shadow on-the-fly.
        map_height, map_width = elevation_data.shape
        wind_angle_rad = np.radians(self.settings['prevailing_wind_direction_degrees'])
        wind_dx, wind_dy = -np.cos(wind_angle_rad), np.sin(wind_angle_rad)
        
        y_indices, x_indices = np.mgrid[0:map_height, 0:map_width]
        upwind_x = x_indices + wind_dx * grid_falloff_dist
        upwind_y = y_indices + wind_dy * grid_falloff_dist
        
        coords = np.array([upwind_y.ravel(), upwind_x.ravel()])
        upwind_elevations = map_coordinates(elevation_data, coords, order=1, mode='nearest').reshape(map_height, map_width)
        
        elevation_diff = upwind_elevations - elevation_data
        mountain_height = self.settings['rain_shadow_mountain_threshold']
        shadow_map = np.clip((elevation_diff - mountain_height) / (1.0 - mountain_height), 0, 1)
        shadow_factor = 1.0 - (shadow_map * self.settings['rain_shadow_strength'])

        # e) Combine factors to get relative humidity.
        # This is now the final, deterministic relative humidity.
        final_relative_humidity = np.clip(coastal_factor * shadow_factor, 0, 1)

        # 2. --- Final Humidity Calculation ---
        saturation_humidity = 5.0 * np.exp(temperature_data_c / 15.0)
        final_humidity_g_m3 = saturation_humidity * final_relative_humidity

        return np.clip(
            final_humidity_g_m3,
            self.settings['min_absolute_humidity_g_m3'],
            self.settings['max_absolute_humidity_g_m3']
        )