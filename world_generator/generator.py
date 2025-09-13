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
            'noise_scale': self.user_config.get('noise_scale', DEFAULTS.NOISE_SCALE),
            'noise_octaves': self.user_config.get('noise_octaves', DEFAULTS.NOISE_OCTAVES),
            'noise_persistence': self.user_config.get('noise_persistence', DEFAULTS.NOISE_PERSISTENCE),
            'noise_lacunarity': self.user_config.get('noise_lacunarity', DEFAULTS.NOISE_LACUNARITY),
            'terrain_amplitude': self.user_config.get('terrain_amplitude', DEFAULTS.TERRAIN_AMPLITUDE),
            'chunk_size_cm': self.user_config.get('chunk_size_cm', DEFAULTS.CHUNK_SIZE_CM),
            'world_width_chunks': self.user_config.get('world_width_chunks', DEFAULTS.DEFAULT_WORLD_WIDTH_CHUNKS),
            'world_height_chunks': self.user_config.get('world_height_chunks', DEFAULTS.DEFAULT_WORLD_HEIGHT_CHUNKS),
        }

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

    def _generate_base_noise(self, x_coords: np.ndarray, y_coords: np.ndarray, seed_offset: int = 0) -> np.ndarray:
        """A generic helper to produce a normalized noise map."""
        self.logger.debug(f"Generating base noise for {x_coords.size} points with offset {seed_offset}.")
        
        # Applying a seed offset to the coordinates ensures each map is unique.
        scaled_x = (x_coords + seed_offset) / self.settings['noise_scale']
        scaled_y = (y_coords + seed_offset) / self.settings['noise_scale']

        noise_values = noise.perlin_noise_2d(
            self._p, scaled_x, scaled_y,
            octaves=self.settings['noise_octaves'],
            persistence=self.settings['noise_persistence'],
            lacunarity=self.settings['noise_lacunarity']
        )
        # Normalize values to range [0, 1]
        return (noise_values + 1) / 2

    def get_elevation(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """Generates elevation data, applying terrain-specific amplitude."""
        normalized_noise = self._generate_base_noise(x_coords, y_coords, seed_offset=0)
        # Apply amplitude to shape the terrain (e.g., flatten valleys, sharpen peaks)
        return np.power(normalized_noise, self.settings['terrain_amplitude'])

    def get_temperature(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """Generates temperature data."""
        return self._generate_base_noise(x_coords, y_coords, seed_offset=self.settings['temp_seed_offset'])

    def _generate_base_noise(self, x_coords: np.ndarray, y_coords: np.ndarray, seed_offset: int = 0) -> np.ndarray:
        """A generic helper to produce a normalized noise map."""
        # Applying a seed offset to the coordinates ensures each map is unique.
        scaled_x = (x_coords + seed_offset) / self.settings['noise_scale']
        scaled_y = (y_coords + seed_offset) / self.settings['noise_scale']

        noise_values = noise.perlin_noise_2d(
            self._p, scaled_x, scaled_y,
            octaves=self.settings['noise_octaves'],
            persistence=self.settings['noise_persistence'],
            lacunarity=self.settings['noise_lacunarity']
        )
        # Normalize values to range [0, 1]
        return (noise_values + 1) / 2

    def get_elevation(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """Generates elevation data, applying terrain-specific amplitude."""
        normalized_noise = self._generate_base_noise(x_coords, y_coords, seed_offset=0)
        # Apply amplitude to shape the terrain (e.g., flatten valleys, sharpen peaks)
        return np.power(normalized_noise, self.settings['terrain_amplitude'])

    def get_temperature(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """Generates temperature data."""
        return self._generate_base_noise(x_coords, y_coords, seed_offset=self.settings['temp_seed_offset'])

    def get_humidity(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """Generates humidity data."""
        return self._generate_base_noise(x_coords, y_coords, seed_offset=self.settings['humidity_seed_offset'])