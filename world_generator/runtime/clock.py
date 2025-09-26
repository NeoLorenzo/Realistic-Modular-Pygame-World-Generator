# world_generator/clock.py

"""
================================================================================
GAME CLOCK
================================================================================
This module provides a self-contained, data-only class for tracking in-game
time. It is designed to be a plug-and-play component for any simulation that
requires a configurable and controllable sense of time.

Data Contract:
---------------
- Inputs (on initialization):
    - config (dict): A dictionary of simulation parameters which can override
      the internal defaults for the calendar and time scale.
- Public Methods:
    - update(real_delta_time): Advances the clock.
    - set_speed(new_scale): Changes the speed of time.
    - get_time_string(): Returns a formatted string of the current time.
- Public Properties:
    - year, month, day, hour, minute, second (read-only integers).
- Side Effects: None.
- Invariants: The clock's state is deterministic based on the total elapsed
  real time and the time scale. It does not depend on the frequency of updates.
================================================================================
"""

class GameClock:
    """Manages the passage of time in the simulation."""

    def __init__(self, config: dict):
        """
        Initializes the clock with calendar settings from the config.
        """
        # --- 1. Load Calendar Configuration (Rule 1) ---
        # The packager now guarantees these keys will exist in the config dictionary.
        self.seconds_per_minute = config['SECONDS_PER_MINUTE']
        self.minutes_per_hour = config['MINUTES_PER_HOUR']
        self.hours_per_day = config['HOURS_PER_DAY']
        self.days_per_month = config['DAYS_PER_MONTH']
        self.months_per_year = config['MONTHS_PER_YEAR']

        # --- 2. Calculate Time Conversion Factors ---
        # These are pre-calculated to make the update logic fast and clear.
        self._seconds_per_hour = self.seconds_per_minute * self.minutes_per_hour
        self._seconds_per_day = self._seconds_per_hour * self.hours_per_day
        self._seconds_per_month = self._seconds_per_day * self.days_per_month
        self._seconds_per_year = self._seconds_per_month * self.months_per_year

        # --- 3. Initialize State Variables ---
        self.time_scale = config['INITIAL_TIME_SCALE']
        self._total_seconds_elapsed = 0.0

        # --- 4. Public, Human-Readable Time Components ---
        # These are recalculated from the master accumulator each update.
        self.year = 1
        self.month = 1
        self.day = 1
        self.hour = 0
        self.minute = 0
        self.second = 0

        # Perform an initial calculation to set the starting time correctly.
        self._recalculate_time()

    def update(self, real_delta_time: float):
        """
        Advances the clock by a given amount of real-world time.

        Args:
            real_delta_time (float): The time elapsed in the real world, in seconds.
        """
        if self.time_scale <= 0:
            return # Time is paused or reversed, do nothing.

        game_delta_time = real_delta_time * self.time_scale
        self._total_seconds_elapsed += game_delta_time
        self._recalculate_time()

    def _recalculate_time(self):
        """
        Calculates the human-readable date and time from the total elapsed seconds.
        This method is deterministic and avoids floating-point drift that would
        occur from incrementally adding to each time component.
        """
        # Use a temporary variable for calculations
        remaining_seconds = self._total_seconds_elapsed

        # Calculate years
        self.year = int(remaining_seconds // self._seconds_per_year) + 1
        remaining_seconds %= self._seconds_per_year

        # Calculate months
        self.month = int(remaining_seconds // self._seconds_per_month) + 1
        remaining_seconds %= self._seconds_per_month

        # Calculate days
        self.day = int(remaining_seconds // self._seconds_per_day) + 1
        remaining_seconds %= self._seconds_per_day

        # Calculate hours
        self.hour = int(remaining_seconds // self._seconds_per_hour)
        remaining_seconds %= self._seconds_per_hour

        # Calculate minutes
        self.minute = int(remaining_seconds // self.seconds_per_minute)
        remaining_seconds %= self.seconds_per_minute

        # Calculate seconds
        self.second = int(remaining_seconds)

    def set_speed(self, new_scale: float):
        """
        Sets the speed of the in-game time.
        0 = paused, 1 = real-time, > 1 = fast-forward.
        """
        self.time_scale = max(0.0, new_scale)

    def get_time_string(self) -> str:
        """Returns a formatted string of the current date and time."""
        return (f"Year {self.year}, Month {self.month}, Day {self.day} - "
                f"{self.hour:02d}:{self.minute:02d}:{self.second:02d}")