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
from . import tectonics

class WorldGenerator:
    """
    Generates and manages the raw data for a procedurally generated world.
    This class is backend-only and does not handle any visualization.
    """
    def __init__(self, config: dict, logger: logging.Logger, permutation_table: np.ndarray = None):
        """
        Initializes the world generator.

        Args:
            config (dict): User-defined parameters to override defaults.
            logger (logging.Logger): The logger instance for all output.
            permutation_table (np.ndarray, optional): A pre-computed noise
                permutation table. If None, one will be generated from the seed.
        """
        self.logger = logger
        self.user_config = config
        self.logger.info("WorldGenerator initializing...")

        # --- Consolidate Configuration ---
        self.settings = {
            'seed': self.user_config.get('seed', DEFAULTS.DEFAULT_SEED),
            'temp_seed_offset': self.user_config.get('temp_seed_offset', DEFAULTS.TEMP_SEED_OFFSET),
            'detail_seed_offset': self.user_config.get('detail_seed_offset', DEFAULTS.DETAIL_SEED_OFFSET),
            'tectonic_plate_seed_offset': self.user_config.get('tectonic_plate_seed_offset', DEFAULTS.TECTONIC_PLATE_SEED_OFFSET),
            'mountain_uplift_seed_offset': self.user_config.get('mountain_uplift_seed_offset', DEFAULTS.MOUNTAIN_UPLIFT_SEED_OFFSET),
            
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
            'num_tectonic_plates': self.user_config.get('num_tectonic_plates', DEFAULTS.DEFAULT_NUM_TECTONIC_PLATES),
            'mountain_uplift_feature_scale_km': self.user_config.get('mountain_uplift_feature_scale_km', DEFAULTS.MOUNTAIN_UPLIFT_FEATURE_SCALE_KM),
            'mountain_influence_radius_km': self.user_config.get('mountain_influence_radius_km', DEFAULTS.MOUNTAIN_INFLUENCE_RADIUS_KM),
            'mountain_uplift_strength': self.user_config.get('mountain_uplift_strength', DEFAULTS.MOUNTAIN_UPLIFT_STRENGTH),
            'max_soil_depth_units': self.user_config.get('max_soil_depth_units', DEFAULTS.MAX_SOIL_DEPTH_UNITS),
            'world_edge_mode': self.user_config.get('world_edge_mode', DEFAULTS.WORLD_EDGE_MODE),
            'world_edge_blend_distance': self.user_config.get('world_edge_blend_distance', DEFAULTS.WORLD_EDGE_BLEND_DISTANCE),
        }

        # --- Convert KM feature scales to internal CM noise scales ---
        self.settings['base_noise_scale'] = self.settings['terrain_base_feature_scale_km'] * DEFAULTS.CM_PER_KM
        self.settings['detail_noise_scale'] = self.settings['terrain_detail_feature_scale_km'] * DEFAULTS.CM_PER_KM
        self.settings['climate_noise_scale'] = self.settings['climate_feature_scale_km'] * DEFAULTS.CM_PER_KM
        self.settings['mountain_uplift_noise_scale'] = self.settings['mountain_uplift_feature_scale_km'] * DEFAULTS.CM_PER_KM

        # --- Public Properties for easy access ---
        self.seed = self.settings['seed']
        self.world_width_cm = self.settings['world_width_chunks'] * self.settings['chunk_size_cm']
        self.world_height_cm = self.settings['world_height_chunks'] * self.settings['chunk_size_cm']

        # --- Initialize Noise ---
        if permutation_table is not None:
            self._p = permutation_table
            self.logger.debug("Initialized with injected permutation table.")
        else:
            self.logger.debug("No permutation table provided, generating new one from seed.")
            p = np.arange(256, dtype=int)
            rng = np.random.default_rng(self.seed)
            rng.shuffle(p)
            self._p = np.stack([p, p]).flatten()
        
        # --- Expose the permutation table for baking ---
        self.permutation_table = self._p

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

    def _get_bedrock_elevation(self, x_coords: np.ndarray, y_coords: np.ndarray, tectonic_uplift_map: np.ndarray = None) -> np.ndarray:
        """
        Generates the base bedrock layer by creating a stable continental terrain
        and then adding tectonic features as a final modification.
        """
        # 1. Generate the base continental terrain noise.
        base_noise = noise.perlin_noise_2d(
            self._p,
            x_coords / self.settings['base_noise_scale'],
            y_coords / self.settings['base_noise_scale'],
            octaves=self.settings['base_noise_octaves'],
            persistence=self.settings['base_noise_persistence'],
            lacunarity=self.settings['base_noise_lacunarity']
        )
        
        detail_noise = noise.perlin_noise_2d(
            self._p,
            (x_coords + self.settings['detail_seed_offset']) / self.settings['detail_noise_scale'],
            (y_coords + self.settings['detail_seed_offset']) / self.settings['detail_noise_scale'],
            octaves=self.settings['detail_noise_octaves'],
            persistence=self.settings['detail_noise_persistence'],
            lacunarity=self.settings['detail_noise_lacunarity']
        )
        
        # The raw terrain is a simple weighted sum. Its range is approx [-(1+weight), 1+weight].
        base_terrain_noise = base_noise + (detail_noise * self.settings['detail_noise_weight'])

        # 2. Normalize the base terrain noise to a stable [0, 1] range.
        # This is now completely independent of the tectonic strength.
        weight = self.settings['detail_noise_weight']
        theoretical_max_base = 1.0 + weight
        normalized_base_terrain = (base_terrain_noise + theoretical_max_base) / (2 * theoretical_max_base)

        # 3. Apply the amplitude shaping to the stable base terrain.
        shaped_base_terrain = np.power(normalized_base_terrain, self.settings['terrain_amplitude'])

        # 4. Add the tectonic modifier to the shaped base terrain.
        # The caller (live preview or baker) is now responsible for providing
        # the tectonic_uplift_map. This simplifies the logic and prevents
        # accidental, expensive recalculations inside this method.
        if tectonic_uplift_map is not None:
            final_bedrock = shaped_base_terrain + tectonic_uplift_map
        else:
            final_bedrock = shaped_base_terrain

        # 5. Apply world edge shaping if a non-default mode is selected.
        edge_mode = self.settings['world_edge_mode']
        
        # 6. Apply world edge shaping if a non-default mode is selected.
        edge_mode = self.settings['world_edge_mode']
        if edge_mode != 'default':
            falloff_map = self._generate_falloff_map(final_bedrock.shape)
            
            if edge_mode == 'island':
                # Multiply elevation by the falloff map to fade to zero (water).
                final_bedrock *= falloff_map
            elif edge_mode == 'valley':
                # Invert the falloff map to create a "bowl" shape.
                # Blend the current elevation towards 1.0 (mountains) at the edges.
                inverse_falloff = 1.0 - falloff_map
                final_bedrock = (final_bedrock * falloff_map) + inverse_falloff

        # 7. Clip the final result to the valid [0, 1] range.
        # This ensures all modifications cannot create impossible elevations.
        return np.clip(final_bedrock, 0.0, 1.0)

    def _generate_falloff_map(self, shape: tuple) -> np.ndarray:
        """
        Generates a 2D map that is 1.0 in the center and smoothly falls off
        to 0.0 at the edges. The falloff distance is controlled by the
        'world_edge_blend_distance' setting.
        """
        height, width = shape
        
        # Create 1D arrays representing normalized distance from the center for both axes.
        # The values go from 1.0 at the edge to 0.0 at the center and back to 1.0.
        x_dist_from_center = np.abs(np.linspace(-1, 1, width))
        y_dist_from_center = np.abs(np.linspace(-1, 1, height))
        
        # Create a 2D grid representing the distance from the center.
        # We use np.maximum to create a square-shaped falloff zone.
        xv, yv = np.meshgrid(x_dist_from_center, y_dist_from_center)
        dist_from_center = np.maximum(xv, yv)
        
        # Define the point where the blend to the edge begins.
        blend_dist = self.settings['world_edge_blend_distance']
        blend_start_point = 1.0 - blend_dist
        
        # Calculate the falloff value. It will be 0 for the central part of the map
        # and will increase from 0 to 1 inside the blend zone.
        falloff_value = (dist_from_center - blend_start_point) / blend_dist
        falloff_value = np.clip(falloff_value, 0, 1)
        
        # The final map should be 1.0 in the center and 0.0 at the edge.
        final_map = 1.0 - falloff_value
        
        # Apply a smoothing curve (power of 2) to make the transition less linear
        # and more natural.
        final_map = final_map**2
        
        return final_map

    def get_elevation(self, x_coords: np.ndarray, y_coords: np.ndarray, bedrock_elevation: np.ndarray = None) -> np.ndarray:
        """
        Generates the final elevation map by creating a bedrock layer and then
        depositing a variable-depth soil layer on top of it, only on land.
        """
        # 1. Generate the foundational bedrock if not provided.
        if bedrock_elevation is None:
            bedrock_elevation = self._get_bedrock_elevation(x_coords, y_coords)

        # 2. Determine which parts of the bedrock are land.
        water_level = self.settings['terrain_levels']['water']
        land_mask = bedrock_elevation >= water_level

        # 3. Calculate the slope of the bedrock to determine where soil can settle.
        slope = self._get_slope(bedrock_elevation)

        # 4. Calculate the potential depth of the soil based on the slope.
        soil_depth = self._get_soil_depth(slope)

        # 5. CRITICAL FIX: Apply the land_mask to the soil depth.
        # This removes all soil from areas that are underwater, preventing the sea floor from rising.
        soil_depth[~land_mask] = 0.0

        # 6. The final elevation is the sum of the bedrock and the soil on top.
        final_elevation = bedrock_elevation + soil_depth
        
        # We need to re-normalize the final elevation to ensure it stays within the [0, 1] range.
        # The theoretical max is 1.0 (max bedrock) + MAX_SOIL_DEPTH_UNITS.
        # Clipping is a safe and effective way to handle this.
        return np.clip(final_elevation, 0.0, 1.0)

    def _get_slope(self, bedrock_elevation_data: np.ndarray) -> np.ndarray:
        """
        Calculates the steepness (slope) of the given elevation data.
        Returns a normalized array where 0.0 is flat and 1.0 is the steepest.
        """
        # Calculate the gradient in the x and y directions
        dy, dx = np.gradient(bedrock_elevation_data)

        # Calculate the magnitude of the gradient at each point
        slope = np.sqrt(dx**2 + dy**2)

        # Normalize the slope to the range [0, 1] for visualization
        max_slope = np.max(slope)
        if max_slope > 0:
            return slope / max_slope
        else:
            return np.zeros_like(slope) # Return a black map if the terrain is perfectly flat

    def _get_soil_depth(self, slope_data: np.ndarray) -> np.ndarray:
        """
        Calculates the depth of the soil layer based on the slope of the bedrock.
        Flatter areas receive more soil.
        """
        # Invert the slope: 1.0 for flat areas, 0.0 for steepest areas.
        soil_potential = 1.0 - slope_data

        # Apply a power curve to make soil accumulate more in the flattest areas.
        # A power of 2 is a good starting point.
        soil_accumulation = np.power(soil_potential, 2)

        # Scale the result by the maximum possible soil depth.
        return soil_accumulation * self.settings['max_soil_depth_units']

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

    def calculate_coastal_factor_map(self, elevation_data: np.ndarray, grid_shape: tuple) -> np.ndarray:
        """Calculates the coastal humidity factor based on distance to water."""
        water_level = self.settings['terrain_levels']['water']
        water_mask = elevation_data < water_level
        distance_grid_units = distance_transform_edt(np.logical_not(water_mask))
        grid_falloff_dist = self.settings['max_coastal_distance_km'] * (grid_shape[1] / (self.world_width_cm / DEFAULTS.CM_PER_KM))
        normalized_distance = distance_grid_units / grid_falloff_dist
        coastal_factor = 1.0 - np.clip(normalized_distance, 0, 1)
        return np.power(coastal_factor, self.settings['humidity_coastal_falloff_rate'])

    def calculate_shadow_factor_map(self, elevation_data: np.ndarray, grid_shape: tuple) -> np.ndarray:
        """Calculates the rain shadow factor based on prevailing winds."""
        map_height, map_width = elevation_data.shape
        wind_angle_rad = np.radians(self.settings['prevailing_wind_direction_degrees'])
        wind_dx, wind_dy = -np.cos(wind_angle_rad), np.sin(wind_angle_rad)
        grid_falloff_dist = self.settings['max_coastal_distance_km'] * (grid_shape[1] / (self.world_width_cm / DEFAULTS.CM_PER_KM))
        y_indices, x_indices = np.mgrid[0:map_height, 0:map_width]
        upwind_x = x_indices + wind_dx * grid_falloff_dist
        upwind_y = y_indices + wind_dy * grid_falloff_dist
        coords = np.array([upwind_y.ravel(), upwind_x.ravel()])
        upwind_elevations = map_coordinates(elevation_data, coords, order=1, mode='nearest').reshape(map_height, map_width)
        elevation_diff = upwind_elevations - elevation_data
        mountain_height = self.settings['rain_shadow_mountain_threshold']
        shadow_map = np.clip((elevation_diff - mountain_height) / (1.0 - mountain_height), 0, 1)
        return 1.0 - (shadow_map * self.settings['rain_shadow_strength'])

    def get_humidity(self, x_coords: np.ndarray, y_coords: np.ndarray, elevation_data: np.ndarray, temperature_data_c: np.ndarray, coastal_factor_map: np.ndarray = None, shadow_factor_map: np.ndarray = None) -> np.ndarray:
        """
        Generates absolute humidity (g/m³). Can accept pre-computed coastal
        and shadow factor maps to dramatically improve performance.
        """
        # 1. --- Calculate Environmental Factors (if not provided) ---
        if coastal_factor_map is None:
            coastal_factor_map = self.calculate_coastal_factor_map(elevation_data, x_coords.shape)

        if shadow_factor_map is None:
            shadow_factor_map = self.calculate_shadow_factor_map(elevation_data, x_coords.shape)

        # 2. --- Combine factors to get relative humidity ---
        final_relative_humidity = np.clip(coastal_factor_map * shadow_factor_map, 0, 1)

        # 3. --- Final Absolute Humidity Calculation ---
        saturation_humidity = 5.0 * np.exp(temperature_data_c / 15.0)
        final_humidity_g_m3 = saturation_humidity * final_relative_humidity

        return np.clip(
            final_humidity_g_m3,
            self.settings['min_absolute_humidity_g_m3'],
            self.settings['max_absolute_humidity_g_m3']
        )
    
    def get_tectonic_data(self, x_coords: np.ndarray, y_coords: np.ndarray, world_width_cm: float, world_height_cm: float, num_plates: int, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generates the raw Voronoi data for tectonic plates.
        This is an expensive operation that should be cached by the caller.
        """
        # CRITICAL FIX: Use the dedicated tectonic plate seed offset
        plate_seed = seed + self.settings['tectonic_plate_seed_offset']
        
        plate_ids, dist1, dist2 = tectonics.get_voronoi_data(
            x_coords, y_coords,
            world_width_cm, world_height_cm,
            num_plates,
            plate_seed
        )
        return plate_ids, dist1, dist2
    
    def get_tectonic_uplift(self, x_coords: np.ndarray, y_coords: np.ndarray, influence_map: np.ndarray) -> np.ndarray:
        """
        Generates a self-contained noise map representing mountain ranges that
        form along tectonic plate boundaries. The map is 0 in plate interiors.
        The caller MUST provide a pre-calculated influence_map.
        """
        # 1. Generate the noise pattern for the mountains' surface texture.
        uplift_noise = noise.perlin_noise_2d(
            self._p,
            (x_coords + self.settings['mountain_uplift_seed_offset']) / self.settings['mountain_uplift_noise_scale'],
            (y_coords + self.settings['mountain_uplift_seed_offset']) / self.settings['mountain_uplift_noise_scale'],
            octaves=self.settings['base_noise_octaves'],
            persistence=self.settings['base_noise_persistence'],
            lacunarity=self.settings['base_noise_lacunarity']
        )

        # 2. Create the final uplift map using the provided influence map.
        # The influence_map creates the solid mountain shape.
        # The (1 + uplift_noise) term shifts the noise from [-1, 1] to [0, 2].
        # The result is a solid mountain range whose height is modulated by noise,
        # which is then scaled by the user-defined strength.
        return influence_map * (1 + uplift_noise) * self.settings['mountain_uplift_strength']
    
    def get_coordinate_grid(self, world_x_cm, world_y_cm, width_cm, height_cm, resolution_w, resolution_h):
        """
        Generates a high-precision coordinate grid for an arbitrary rectangle.
        This is the single authoritative method for coordinate generation.
        """
        pixel_w_cm = width_cm / resolution_w
        pixel_h_cm = height_cm / resolution_h
        
        start_x = world_x_cm
        start_y = world_y_cm
        
        # Use the baker's proven, precise calculation
        end_x = start_x + ((resolution_w - 1) * pixel_w_cm)
        end_y = start_y + ((resolution_h - 1) * pixel_h_cm)
        
        x_coords = np.linspace(start_x, end_x, resolution_w)
        y_coords = np.linspace(start_y, end_y, resolution_h)
        
        return np.meshgrid(x_coords, y_coords)