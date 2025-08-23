# examples/basic_viewer/main.py

import sys
import os
import json
import logging
import logging.config
import pygame

# To import from the parent directory (Modular_Pygame_World_Generator),
# we add it to the Python path.
# This is necessary because 'examples' is not in the same package as 'world_generator'.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from world_generator.generator import WorldGenerator
from world_generator.renderer import WorldRenderer
from camera import Camera

class Application:
    """The main application class for the basic viewer."""

    def __init__(self):
        self._setup_logging()
        self.logger.info("Application starting.")

        self.config = self._load_config()
        self._setup_pygame()

        # --- State ---
        self.view_modes = ["terrain", "temperature", "humidity"]
        self.current_view_mode_index = 0
        self.view_mode = self.view_modes[self.current_view_mode_index]

        # --- Dependency Injection (Rule 7, DIP) ---
        # Create the core components, passing them the tools they need.
        self.camera = Camera(self.config)
        self.world_generator = WorldGenerator(
            config=self.config['world_generation_parameters'],
            logger=self.logger
        )
        self.world_renderer = WorldRenderer(
            generator=self.world_generator,
            config=self.config,
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
        self.screen_width = self.config['display']['screen_width']
        self.screen_height = self.config['display']['screen_height']
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Realistic Modular World Generator")
        self.clock = pygame.time.Clock()
        self.tick_rate = self.config['display']['clock_tick_rate']
        self.logger.info("Pygame initialized successfully.")

    def run(self):
        """The main application loop."""
        self.logger.info("Entering main loop.")
        try:
            while self.is_running:
                self._handle_events()
                self._update()
                self._draw()
                self.clock.tick(self.tick_rate)
        except Exception as e:
            self.logger.critical("An unhandled exception occurred!", exc_info=True)
        finally:
            self.logger.info("Exiting application.")
            pygame.quit()
            sys.exit()

    def _handle_events(self):
        """Processes user input and other events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.is_running = False
            elif event.type == pygame.MOUSEWHEEL:
                if event.y > 0:
                    self.camera.zoom_in()
                elif event.y < 0:
                    self.camera.zoom_out()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_v:
                    self.current_view_mode_index = (self.current_view_mode_index + 1) % len(self.view_modes)
                    self.view_mode = self.view_modes[self.current_view_mode_index]
                    self.logger.info(f"Event: View switched to '{self.view_mode}'")

        # Handle continuous key presses for panning
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
        """Update application state (currently unused)."""
        pass

    def _draw(self):
        """Renders the scene."""
        self.world_renderer.draw(self.screen, self.camera, self.view_mode)
        pygame.display.flip()

if __name__ == '__main__':
    app = Application()
    app.run()