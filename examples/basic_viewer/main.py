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
import pygame_gui
import subprocess
import time

# To import from the parent directory (Modular_Pygame_World_Generator),
# we add it to the Python path.
# This is necessary because 'examples' is not in the same package as 'world_generator'.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from world_generator.generator import WorldGenerator
from renderer import WorldRenderer
from camera import Camera

# --- UI Constants (Rule 1) ---
UI_PANEL_WIDTH = 320
UI_ELEMENT_HEIGHT = 25
UI_SLIDER_HEIGHT = 50
UI_PADDING = 10
UI_BUTTON_HEIGHT = 40
# An estimated average size for a 100x100 chunk PNG in KB.
# This is a scientifically-grounded abstraction (Rule 8) for the UI estimate.
ESTIMATED_CHUNK_SIZE_KB = 15.0

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
        self.frame_count = 0

        # --- UI Setup ---
        self.ui_manager = None # To be initialized in _setup_ui
        self.ui_panel = None
        # Sliders
        self.temp_slider = None
        self.roughness_slider = None
        self.lapse_rate_slider = None
        self.continent_size_slider = None
        self.terrain_amplitude_slider = None
        self.polar_drop_slider = None
        # World Size Inputs
        self.world_width_input = None
        self.world_height_input = None
        self.apply_size_button = None
        # Bake Controls
        self.bake_button = None
        self.size_estimate_label = None
        self._setup_ui()

        # --- Profiling Setup (Rule 11) ---
        self.profiler = None
        if self.config.get('profiling', {}).get('enabled', False):
            self.profiler = cProfile.Profile()
            self.logger.info("Profiling is ENABLED.")
        else:
            self.logger.info("Profiling is DISABLED.")

        # --- Performance Test State (Rule 11) ---
        self.perf_test_config = self.config.get('performance_test', {})
        self.is_perf_test_running = self.perf_test_config.get('enabled', False)
        
        # --- Benchmark Mode State ---
        self.benchmark_config = self.config.get('benchmark', {})
        self.is_benchmark_running = self.benchmark_config.get('enabled', False)

        self._perf_test_path = []
        self._perf_test_current_action = None
        self._perf_test_action_frame_count = 0
        if self.is_perf_test_running:
            self.logger.info("Performance test mode is ENABLED. User input will be ignored.")
            # Create a simple, expanded path for easier processing
            for step in self.perf_test_config.get('path', []):
                for _ in range(step['frames']):
                    self._perf_test_path.append(step)

        # --- State for Live Preview Mode ---
        self.live_preview_surface = None
        self.world_params_dirty = True # Flag to trigger regeneration

        # --- Dependency Injection (Rule 7, DIP) ---
        # The Generator is the authority on world data, but is now used on-demand by the renderer.
        self.world_generator = WorldGenerator(
            config=self.config.get('world_generation_parameters', {}),
            logger=self.logger
        )
        # The camera still needs the generator for world dimensions.
        self.camera = Camera(self.config, self.world_generator)
        # The renderer is now independent of a generator instance at startup.
        self.world_renderer = WorldRenderer(
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
        
        # Load the zoom threshold from config and set it as an instance attribute.
        # This fixes the AttributeError crash.
        self.high_res_threshold = self.config['camera']['high_res_request_zoom_threshold']
        
        self.logger.info("Pygame initialized successfully.")

    def _setup_ui(self):
        """Initializes the pygame_gui manager and creates the UI layout."""
        self.ui_manager = pygame_gui.UIManager((self.screen_width, self.screen_height))
        self.logger.info("UI Manager initialized.")

        # --- Create the main UI Panel ---
        panel_rect = pygame.Rect(
            self.screen_width - UI_PANEL_WIDTH, 0,
            UI_PANEL_WIDTH, self.screen_height
        )
        self.ui_panel = pygame_gui.elements.UIPanel(
            relative_rect=panel_rect,
            manager=self.ui_manager,
            starting_height=1
        )

        # --- UI Element Layout Variables ---
        current_y = UI_PADDING
        element_width = UI_PANEL_WIDTH - (3 * UI_PADDING) # Width inside the panel

        # --- Get world parameters for setting initial slider values ---
        world_params = self.config['world_generation_parameters']

        # --- Slider 1: Target Sea Level Temperature ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Sea Level Temp (°C)",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.temp_slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_SLIDER_HEIGHT),
            start_value=world_params.get('target_sea_level_temp_c', 15.0),
            value_range=(-20.0, 40.0),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_SLIDER_HEIGHT + UI_PADDING

        # --- Slider 2: Detail Noise Weight (Mountain Roughness) ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Mountain Roughness",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.roughness_slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_SLIDER_HEIGHT),
            start_value=world_params.get('detail_noise_weight', 0.25),
            value_range=(0.0, 1.0),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_SLIDER_HEIGHT + UI_PADDING

        # --- Slider 3: Lapse Rate (Mountain Coldness) ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Mountain Coldness (°C Drop)",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.lapse_rate_slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_SLIDER_HEIGHT),
            start_value=world_params.get('lapse_rate_c_per_unit_elevation', 40.0),
            value_range=(0.0, 100.0),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_SLIDER_HEIGHT + UI_PADDING

        # --- Slider 4: Continent Size ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Continent Size (km)",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.continent_size_slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_SLIDER_HEIGHT),
            start_value=world_params.get('terrain_base_feature_scale_km', 40.0),
            value_range=(5.0, 200.0),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_SLIDER_HEIGHT + UI_PADDING

        # --- Slider 5: Terrain Amplitude (Sharpness) ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Terrain Amplitude (Sharpness)",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.terrain_amplitude_slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_SLIDER_HEIGHT),
            start_value=world_params.get('terrain_amplitude', 2.5),
            value_range=(0.5, 5.0),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_SLIDER_HEIGHT + UI_PADDING

        # --- Slider 6: Polar Temperature Drop ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Equator-to-Pole Temp Drop (°C)",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.polar_drop_slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_SLIDER_HEIGHT),
            start_value=world_params.get('polar_temperature_drop_c', 30.0),
            value_range=(0.0, 80.0),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_SLIDER_HEIGHT + (UI_PADDING * 2)

        # --- World Size Inputs ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="World Size (Width x Height in Chunks)",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        input_width = (element_width - UI_PADDING) // 2
        self.world_width_input = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(UI_PADDING, current_y, input_width, UI_ELEMENT_HEIGHT),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        self.world_width_input.set_text(str(world_params.get('world_width_chunks', 800)))

        self.world_height_input = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(UI_PADDING + input_width + UI_PADDING, current_y, input_width, UI_ELEMENT_HEIGHT),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        self.world_height_input.set_text(str(world_params.get('world_height_chunks', 450)))
        current_y += UI_ELEMENT_HEIGHT + UI_PADDING

        self.apply_size_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_BUTTON_HEIGHT),
            text="Apply Size Changes",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_BUTTON_HEIGHT + (UI_PADDING * 2)

        # --- Bake Button and Size Estimate ---
        self.size_estimate_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Estimated size: calculating...",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.bake_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_BUTTON_HEIGHT),
            text="Bake World",
            manager=self.ui_manager,
            container=self.ui_panel
        )

        # Set the initial size estimate
        self._update_bake_size_estimate()

    def run(self):
        """The main application loop."""
        # Profiler is now enabled conditionally based on the run mode.

        # --- Benchmark Mode Execution (Rule 11) ---
        if self.is_benchmark_running:
            import time
            self.logger.info("Benchmark mode ENABLED. Application will exit after generation.")
            
            # Profile ONLY the loading screen.
            if self.profiler:
                self.profiler.enable()

            start_time = time.perf_counter()
            # This is a placeholder for a future benchmark of the live preview generation
            self.world_renderer.generate_live_preview_surface(
                world_params=self.config['world_generation_parameters'],
                view_mode=self.view_mode
            )
            end_time = time.perf_counter()
            
            if self.profiler:
                self.profiler.disable() # Disable immediately to isolate the measurement.

            duration = end_time - start_time
            self.logger.info(f"Benchmark complete. Live preview generation took: {duration:.3f} seconds.")
            
            self.is_running = False
        else:
            # The loading screen is no longer called.
            self.logger.info("Entering main loop.")
            
            # Profile ONLY the interactive session.
            if self.profiler:
                self.profiler.enable()

        try:
            while self.is_running:
                time_delta = self.clock.tick(self.tick_rate) / 1000.0
                
                self._handle_events()
                self._update()

                # --- Live Preview Regeneration (Rule 5) ---
                # If any parameter has changed, regenerate the single preview surface.
                if self.world_params_dirty:
                    self.logger.info(f"World parameters changed. Regenerating live preview for view mode: '{self.view_mode}'...")
                    # Pass the complete, current world parameters to the renderer.
                    self.live_preview_surface = self.world_renderer.generate_live_preview_surface(
                        world_params=self.config['world_generation_parameters'],
                        view_mode=self.view_mode
                    )
                    self.world_params_dirty = False
                    self.logger.info("Live preview regeneration complete.")

                # The new drawing method uses the pre-generated surface.
                self.world_renderer.draw_live_preview(self.screen, self.camera, self.live_preview_surface)
                
                # --- UI Processing ---
                self.ui_manager.update(time_delta)
                self.ui_manager.draw_ui(self.screen)

                pygame.display.flip()
                self.frame_count += 1

                # Performance test exit condition
                if self.is_perf_test_running and self.frame_count >= self.perf_test_config.get('duration_frames', 1000):
                    self.logger.info(f"Performance test complete after {self.frame_count} frames.")
                    self.is_running = False

        except Exception as e:
            self.logger.critical("An unhandled exception occurred!", exc_info=True)
        finally:
            # The profiler is disabled here for the normal run case.
            # For the benchmark case, it's already disabled, but this call is safe.
            if self.profiler:
                self.profiler.disable()
                self._report_profiling_results()

            self.logger.info("Exiting application.")
            pygame.quit()
            sys.exit()

    def _handle_events(self):
        """Processes user input and other events."""
        for event in pygame.event.get():
            # Pass events to the UI Manager first
            self.ui_manager.process_events(event)

            if event.type == pygame.QUIT:
                self.is_running = False
            # Allow manual exit via ESC key even during a performance test
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.logger.info("Event: ESC key pressed. Exiting.")
                self.is_running = False

            # --- Ignore user input during performance test (Rule 11) ---
            if self.is_perf_test_running:
                continue  # Skip to the next event

            # --- Handle UI Events for Live Editing ---
            if event.type == pygame_gui.UI_HORIZONTAL_SLIDER_MOVED:
                new_value = event.value
                params = self.config['world_generation_parameters']
                
                if event.ui_element == self.temp_slider:
                    params['target_sea_level_temp_c'] = new_value
                elif event.ui_element == self.roughness_slider:
                    params['detail_noise_weight'] = new_value
                elif event.ui_element == self.lapse_rate_slider:
                    params['lapse_rate_c_per_unit_elevation'] = new_value
                elif event.ui_element == self.continent_size_slider:
                    params['terrain_base_feature_scale_km'] = new_value
                elif event.ui_element == self.terrain_amplitude_slider:
                    params['terrain_amplitude'] = new_value
                elif event.ui_element == self.polar_drop_slider:
                    params['polar_temperature_drop_c'] = new_value
                
                self.world_params_dirty = True
            
            if event.type == pygame_gui.UI_BUTTON_PRESSED:
                if event.ui_element == self.bake_button:
                    self._start_background_bake()
                elif event.ui_element == self.apply_size_button:
                    self._apply_world_size_changes()

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
                    self.world_params_dirty = True # Trigger regeneration on view change
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

    def _apply_world_size_changes(self):
        """
        Parses text inputs for world size, updates the config, and re-initializes
        core components that depend on world dimensions.
        """
        try:
            new_width = int(self.world_width_input.get_text())
            new_height = int(self.world_height_input.get_text())

            if new_width <= 0 or new_height <= 0:
                self.logger.warning("World dimensions must be positive integers.")
                return

            self.logger.info(f"Applying new world size: {new_width}x{new_height} chunks.")

            # 1. Update the configuration dictionary
            self.config['world_generation_parameters']['world_width_chunks'] = new_width
            self.config['world_generation_parameters']['world_height_chunks'] = new_height

            # 2. Re-initialize the WorldGenerator with the updated config
            self.world_generator = WorldGenerator(
                config=self.config.get('world_generation_parameters', {}),
                logger=self.logger
            )

            # 3. Re-initialize the Camera, which depends on the generator's dimensions
            self.camera = Camera(self.config, self.world_generator)

            # 4. Update the bake size estimate label
            self._update_bake_size_estimate()

            # 5. Trigger a full regeneration of the live preview
            self.world_params_dirty = True

        except ValueError:
            self.logger.error("Invalid world size input. Please enter integers only.")
            # Optionally, reset the text to the current valid values
            self.world_width_input.set_text(str(self.config['world_generation_parameters']['world_width_chunks']))
            self.world_height_input.set_text(str(self.config['world_generation_parameters']['world_height_chunks']))

    def _update_bake_size_estimate(self):
        """Calculates and displays the estimated disk space for a full bake."""
        if not self.size_estimate_label:
            return

        w_params = self.config['world_generation_parameters']
        width_chunks = w_params.get('world_width_chunks', 800)
        height_chunks = w_params.get('world_height_chunks', 450)
        
        total_chunks = width_chunks * height_chunks
        num_view_modes = len(self.view_modes)
        
        total_kb = total_chunks * num_view_modes * ESTIMATED_CHUNK_SIZE_KB
        total_gb = total_kb / (1024 * 1024)

        self.size_estimate_label.set_text(f"Estimated Bake Size: {total_gb:.2f} GB")

    def _start_background_bake(self):
        """
        Saves the current configuration and launches the bake_world.py script
        as a separate, non-blocking process.
        """
        self.logger.info("Bake process requested by user.")
        
        # 1. Create a temp directory if it doesn't exist
        temp_dir = "temp"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # 2. Save the current, modified config to a temporary file
        timestamp = int(time.time())
        temp_config_path = os.path.join(temp_dir, f"bake_config_{timestamp}.json")
        
        with open(temp_config_path, 'w') as f:
            json.dump(self.config, f, indent=4)
        
        self.logger.info(f"Saved temporary bake config to: {temp_config_path}")

        # 3. Launch the baker script as a new process
        bake_script_path = "bake_world.py"
        command = [sys.executable, bake_script_path, "--config", temp_config_path]
        
        try:
            subprocess.Popen(command)
            self.logger.info(f"Successfully launched background bake process: {' '.join(command)}")
            
            # 4. Provide UI feedback
            self.bake_button.set_text("Baking in Progress...")
            self.bake_button.disable()
        except FileNotFoundError:
            self.logger.error(f"Could not find the baker script at '{bake_script_path}'. Is it in the project root?")
        except Exception as e:
            self.logger.critical(f"Failed to launch bake process: {e}")

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