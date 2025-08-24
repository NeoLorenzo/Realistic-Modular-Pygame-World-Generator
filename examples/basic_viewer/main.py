# examples/basic_viewer/main.py

import sys
import os
import json
import logging
import logging.config
import pygame
import cProfile
import pstats
import io
from datetime import datetime

# To import from the parent directory (Modular_Pygame_World_Generator),
# we add it to the Python path.
# This is necessary because 'examples' is not in the same package as 'world_generator'.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from world_generator.generator import WorldGenerator
from renderer import WorldRenderer
from camera import Camera

class Application:
    """The main application class for the basic viewer."""

    def __init__(self):
        self._setup_logging()
        self.logger.info("Application starting.")

        self.config = self._load_config()
        self._setup_pygame()

        # --- Profiling Setup (Rule 11) ---
        self.profiler = None
        if self.config.get('profiling', {}).get('enabled', False):
            self.profiler = cProfile.Profile()
            self.logger.info("Profiling is ENABLED.")
        else:
            self.logger.info("Profiling is DISABLED.")

        # --- State ---
        self.view_modes = ["terrain", "temperature", "humidity"]
        self.current_view_mode_index = 0
        self.view_mode = self.view_modes[self.current_view_mode_index]
        self.frame_count = 0

        # --- Performance Test State (Rule 11) ---
        self.perf_test_config = self.config.get('performance_test', {})
        self.is_perf_test_running = self.perf_test_config.get('enabled', False)
        self._perf_test_path = []
        self._perf_test_current_action = None
        self._perf_test_action_frame_count = 0
        if self.is_perf_test_running:
            self.logger.info("Performance test mode is ENABLED. User input will be ignored.")
            # Create a simple, expanded path for easier processing
            for step in self.perf_test_config.get('path', []):
                for _ in range(step['frames']):
                    self._perf_test_path.append(step)

        # --- Dependency Injection (Rule 7, DIP) ---
        # The Generator is created first and becomes the authority on the world.
        self.world_generator = WorldGenerator(
            config=self.config.get('world_generation_parameters', {}),
            logger=self.logger
        )
        # Other components are given the generator instance to query for info.
        self.camera = Camera(self.config, self.world_generator)
        self.world_renderer = WorldRenderer(
            generator=self.world_generator,
            logger=self.logger
        )

        self.is_running = True

    def _setup_logging(self):
        """Initializes the logging system from a config file."""
        log_config_path = 'examples/basic_viewer/logging_config.json'
        # This path must match the relative path used in the JSON config.
        log_dir = 'logs'
        
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        with open(log_config_path, 'rt') as f:
            log_config = json.load(f)
        
        # Tell the logger where to create its file, overriding the JSON path.
        # This makes the script's behavior independent of the current working directory.
        log_config['handlers']['file']['filename'] = os.path.join(log_dir, 'viewer.log')
        
        logging.config.dictConfig(log_config)
        self.logger = logging.getLogger(__name__)

    def _load_config(self) -> dict:
        """Loads simulation parameters from the config file."""
        config_path = 'examples/basic_viewer/config.json'
        self.logger.info(f"Loading configuration from {config_path}")
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.critical(f"Configuration file not found at {config_path}. Exiting.")
            sys.exit(1)
        except json.JSONDecodeError:
            self.logger.critical(f"Error decoding JSON from {config_path}. Exiting.")
            sys.exit(1)

    def _setup_pygame(self):
        """Initializes Pygame and the display window."""
        pygame.init()
        display_config = self.config['display']
        self.screen_width = display_config['screen_width']
        self.screen_height = display_config['screen_height']
        
        flags = 0
        if display_config.get('fullscreen', False):
            flags = pygame.FULLSCREEN
            self.logger.info("Initializing display in Fullscreen mode.")
            # In fullscreen, we ignore width/height and use the native resolution
            self.screen = pygame.display.set_mode((0, 0), flags)
            # Update screen dimensions to the actual resolution chosen
            self.screen_width, self.screen_height = self.screen.get_size()
            # This is important for the camera's aspect ratio calculations
            self.config['display']['screen_width'] = self.screen_width
            self.config['display']['screen_height'] = self.screen_height
        else:
            self.logger.info(f"Initializing display in Windowed mode ({self.screen_width}x{self.screen_height}).")
            self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))

        pygame.display.set_caption("Realistic Modular World Generator")
        self.clock = pygame.time.Clock()
        self.tick_rate = display_config['clock_tick_rate']
        self.logger.info("Pygame initialized successfully.")

    def run(self):
        """The main application loop."""
        self.logger.info("Entering main loop.")
        try:
            if self.profiler:
                self.profiler.enable()

            while self.is_running:
                self._handle_events()
                self._update()
                self._draw()
                self.clock.tick(self.tick_rate)
                self.frame_count += 1

                # Performance test exit condition
                if self.is_perf_test_running and self.frame_count >= self.perf_test_config.get('duration_frames', 1000):
                    self.logger.info(f"Performance test complete after {self.frame_count} frames.")
                    self.is_running = False

        except Exception as e:
            self.logger.critical("An unhandled exception occurred!", exc_info=True)
        finally:
            if self.profiler:
                self.profiler.disable()
                self._report_profiling_results()

            # Cleanly shut down the renderer's worker thread before exiting
            self.world_renderer.shutdown()

            self.logger.info("Exiting application.")
            pygame.quit()
            sys.exit()

    def _handle_events(self):
        """Processes user input and other events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.is_running = False
            # Allow manual exit via ESC key even during a performance test
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.logger.info("Event: ESC key pressed. Exiting.")
                self.is_running = False

            # --- Ignore user input during performance test (Rule 11) ---
            if self.is_perf_test_running:
                continue  # Skip to the next event

            # --- Handle user-driven events only if test is not running ---
            if event.type == pygame.MOUSEWHEEL:
                if event.y > 0:
                    self.camera.zoom_in()
                elif event.y < 0:
                    self.camera.zoom_out()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_v:
                    self.current_view_mode_index = (self.current_view_mode_index + 1) % len(self.view_modes)
                    self.view_mode = self.view_modes[self.current_view_mode_index]
                    self.logger.info(f"Event: View switched to '{self.view_mode}'")

        # Handle continuous key presses for panning, but only if test is not running
        if not self.is_perf_test_running:
            keys = pygame.key.get_pressed()
            pan_speed = self.config['camera']['pan_speed_pixels']
            if keys[pygame.K_w]:
                self.camera.pan(0, -pan_speed)
            if keys[pygame.K_s]:
                self.camera.pan(0, pan_speed)
            if keys[pygame.K_a]:
                self.camera.pan(-pan_speed, 0)
            if keys[pygame.K_d]:
                self.camera.pan(pan_speed, 0)

    def _update(self):
        """Update application state. Runs the performance test if active."""
        if not self.is_perf_test_running:
            return

        if self.frame_count >= len(self._perf_test_path):
            # Path is complete, but we may be waiting for duration_frames to end
            return

        action_data = self._perf_test_path[self.frame_count]
        action = action_data.get('action')

        if action == 'pan':
            pan_speed_dx = action_data.get('dx', 0)
            pan_speed_dy = action_data.get('dy', 0)
            self.camera.pan(pan_speed_dx, pan_speed_dy)
        elif action == 'zoom_in':
            self.camera.zoom_in()
        elif action == 'zoom_out':
            self.camera.zoom_out()

    def _draw(self):
        """Renders the scene."""
        self.world_renderer.draw(self.screen, self.camera, self.view_mode)
        pygame.display.flip()

    def _report_profiling_results(self):
        """Saves and logs profiling data according to Rule 11."""
        if not self.profiler:
            return

        profiling_config = self.config['profiling']
        output_dir = profiling_config['output_dir']
        log_count = profiling_config['log_count']
        # Get the seed from the generator, which is the source of truth (Rule 7)
        seed = self.world_generator.seed
        
        # Ensure the output directory exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            self.logger.info(f"Created profiling output directory: {output_dir}")

        # --- Save full profiling data to a file (Rule 11.1) ---
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_str}_seed-{seed}_frames-{self.frame_count}_main.prof"
        filepath = os.path.join(output_dir, filename)
        self.profiler.dump_stats(filepath)
        self.logger.info(f"Full profiling data saved to {filepath}")

        # --- Log a summary to the console (User Request) ---
        s = io.StringIO()
        # Sort by cumulative time spent in the function
        ps = pstats.Stats(self.profiler, stream=s).sort_stats('cumulative')
        ps.print_stats(log_count)
        
        self.logger.info(f"--- Top {log_count} Profiling Results ---\n{s.getvalue()}")


if __name__ == '__main__':
    app = Application()
    app.run()