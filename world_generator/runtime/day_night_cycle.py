# world_generator/day_night_cycle.py

"""
================================================================================
DAY/NIGHT CYCLE
================================================================================
This module provides a class to manage the day/night cycle, calculating the
ambient light level and color tint based on the time from a GameClock.

Data Contract:
---------------
- Inputs (on initialization):
    - clock (GameClock): An instance of the GameClock.
    - config (dict): A dictionary of simulation parameters for lighting.
- Public Methods:
    - update(): Recalculates the lighting based on the clock's current time.
- Public Properties:
    - current_brightness (float): The calculated ambient light level [0,1].
    - current_color_tint (tuple): The (R,G,B) color of the ambient light.
- Side Effects: None.
- Invariants: The output is a deterministic function of the clock's time.
================================================================================
"""
import numpy as np
from typing import TYPE_CHECKING

# Use a forward reference for the type hint to avoid circular imports.
if TYPE_CHECKING:
    from .clock import GameClock

def _lerp_color(color1: tuple, color2: tuple, t: float) -> tuple:
    """Linearly interpolates between two RGB colors."""
    t = np.clip(t, 0.0, 1.0)
    c1 = np.array(color1)
    c2 = np.array(color2)
    interpolated_color = c1 * (1 - t) + c2 * t
    return tuple(interpolated_color.astype(int))

def _lerp_float(val1: float, val2: float, t: float) -> float:
    """Linearly interpolates between two float values."""
    t = np.clip(t, 0.0, 1.0)
    return val1 * (1 - t) + val2 * t

class DayNightCycle:
    """
    Manages the ambient lighting of the world based on the in-game time.
    """
    def __init__(self, clock: 'GameClock', config: dict):
        """
        Initializes the DayNightCycle.
        """
        self.clock = clock

        # --- 1. Load Lighting Configuration (Rule 1) ---
        self.sunrise_hour = config['SUNRISE_HOUR']
        self.sunset_hour = config['SUNSET_HOUR']
        self.transition_duration = config['DAY_NIGHT_TRANSITION_DURATION_HOURS']
        self.max_brightness = config['MAX_BRIGHTNESS']
        self.min_brightness = config['MIN_BRIGHTNESS']
        self.night_color = config['NIGHT_COLOR']

        # --- 2. Pre-calculate Key Time Points for the 5-stage cycle ---
        self.sunrise_start = self.sunrise_hour
        self.sunrise_end = self.sunrise_hour + self.transition_duration
        self.sunset_start = self.sunset_hour - self.transition_duration
        self.sunset_end = self.sunset_hour

        # --- 3. Public State Variables ---
        self.current_brightness = self.min_brightness
        self.current_color_tint = self.night_color

        # Perform an initial update to set the starting state correctly.
        self.update()

    def update(self):
        """
        Recalculates the current brightness based on a 5-stage cycle:
        Night -> Sunrise -> Full Day -> Sunset -> Night
        """
        current_hour = self.clock.hour + (self.clock.minute / self.clock.minutes_per_hour)

        if self.sunrise_start <= current_hour < self.sunrise_end:
            # --- Phase 2: Sunrise Transition ---
            # Interpolate from min to max brightness over the transition duration.
            time_into_segment = current_hour - self.sunrise_start
            t = time_into_segment / self.transition_duration
            self.current_brightness = _lerp_float(self.min_brightness, self.max_brightness, t)

        elif self.sunrise_end <= current_hour < self.sunset_start:
            # --- Phase 3: Full Day ---
            # Brightness is constant at its maximum.
            self.current_brightness = self.max_brightness

        elif self.sunset_start <= current_hour < self.sunset_end:
            # --- Phase 4: Sunset Transition ---
            # Interpolate from max to min brightness over the transition duration.
            time_into_segment = current_hour - self.sunset_start
            t = time_into_segment / self.transition_duration
            self.current_brightness = _lerp_float(self.max_brightness, self.min_brightness, t)

        else:
            # --- Phase 1 & 5: Night Time ---
            # Brightness is constant at its minimum.
            self.current_brightness = self.min_brightness