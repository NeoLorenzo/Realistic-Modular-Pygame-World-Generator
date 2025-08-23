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
        self.config = config
        self.logger.info("WorldGenerator initializing...")

        # --- Load Configuration ---
        # We use .get() to fall back to our internal defaults (Rule 1)
        self.seed = self.config.get('seed', DEFAULTS.DEFAULT_SEED)
        self.temp_seed_offset = self.config.get('temp_seed_offset', DEFAULTS.TEMP_SEED_OFFSET)
        self.humidity_seed_offset = self.config.get('humidity_seed_offset', DEFAULTS.HUMIDITY_SEED_OFFSET)
        
        self.noise_scale = self.config.get('noise_scale', DEFAULTS.NOISE_SCALE)
        self.noise_octaves = self.config.get('noise_octaves', DEFAULTS.NOISE_OCTAVES)
        self.noise_persistence = self.config.get('noise_persistence', DEFAULTS.NOISE_PERSISTENCE)
        self.noise_lacunarity = self.config.get('noise_lacunarity', DEFAULTS.NOISE_LACUNARITY)
        self.terrain_amplitude = self.config.get('terrain_amplitude', DEFAULTS.TERRAIN_AMPLITUDE)

        # --- Initialize Noise ---
        # All randomness is controlled by the master seed (Rule 12)
        p = np.arange(256, dtype=int)
        rng = np.random.default_rng(self.seed)
        rng.shuffle(p)
        self._p = np.stack([p, p]).flatten() # Permutation table for noise

        self.logger.info(f"WorldGenerator initialized with seed: {self.seed}")

    def _generate_base_noise(self, x_coords: np.ndarray, y_coords: np.ndarray, seed_offset: int = 0) -> np.ndarray:
        """A generic helper to produce a normalized noise map."""
        self.logger.debug(f"Generating base noise for {x_coords.size} points with offset {seed_offset}.")
        
        # Applying a seed offset to the coordinates ensures each map is unique.
        scaled_x = (x_coords + seed_offset) / self.noise_scale
        scaled_y = (y_coords + seed_offset) / self.noise_scale

        noise_values = noise.perlin_noise_2d(
            self._p, scaled_x, scaled_y,
            octaves=self.noise_octaves,
            persistence=self.noise_persistence,
            lacunarity=self.noise_lacunarity
        )
        # Normalize values to range [0, 1]
        return (noise_values + 1) / 2

    def get_elevation(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """Generates elevation data, applying terrain-specific amplitude."""
        normalized_noise = self._generate_base_noise(x_coords, y_coords, seed_offset=0)
        # Apply amplitude to shape the terrain (e.g., flatten valleys, sharpen peaks)
        return np.power(normalized_noise, self.terrain_amplitude)

    def get_temperature(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """Generates temperature data."""
        return self._generate_base_noise(x_coords, y_coords, seed_offset=self.temp_seed_offset)

    def get_humidity(self, x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
        """Generates humidity data."""
        return self._generate_base_noise(x_coords, y_coords, seed_offset=self.humidity_seed_offset)

    # We will add get_temperature() and get_humidity() methods later.