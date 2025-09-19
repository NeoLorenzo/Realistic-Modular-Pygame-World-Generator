# editor/main.py

import sys
import os
import json
import logging
import logging.config
import queue
# import pygame # MOVED
import cProfile
import pstats
import io
from datetime import datetime
# import pygame_gui # MOVED
import subprocess
import time
import hashlib
import numpy as np
import threading
from . import baker

# The sys.path manipulation is no longer needed when running as a module.

from world_generator.generator import WorldGenerator
# Import the color_maps module to access its functions.
from world_generator import color_maps
# from renderer import WorldRenderer # MOVED
# from camera import Camera # MOVED

# --- UI Constants (Rule 1) ---
UI_PANEL_WIDTH = 320
UI_ELEMENT_HEIGHT = 25
UI_SLIDER_HEIGHT = 50
UI_PADDING = 10
UI_BUTTON_HEIGHT = 40

# --- Live Preview Application Constants (Rule 1) ---
# The resolution of the single surface used for the live preview.
PREVIEW_RESOLUTION_WIDTH = 1600
PREVIEW_RESOLUTION_HEIGHT = 900

# --- Bake Estimation Constants (Rule 8) ---
# An estimated average size for a 100x100 chunk PNG in KB.
ESTIMATED_CHUNK_SIZE_KB = 15.0
# An estimated average size for a 100x100 8-bit palettized PNG in KB.
ESTIMATED_PALETTIZED_CHUNK_SIZE_KB = 4.0
# An estimated size for a compressed 1x1 uniform chunk PNG in KB.
ESTIMATED_COMPRESSED_CHUNK_SIZE_KB = 0.5
# The grid size for the bake size estimation analysis.
ESTIMATE_GRID_WIDTH = 160
ESTIMATE_GRID_HEIGHT = 90

class Application:
    """The main application class for the basic viewer."""

    def __init__(self):
        self._setup_logging()
        self.logger.info("Application starting.")

        self.config = self._load_config()
        self._setup_pygame()

                # --- State ---
        self.view_modes = ["terrain", "temperature", "humidity", "elevation", "tectonic", "soil_depth"]
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
        self.km_size_label = None # New label for KM dimensions
        # Bake Controls
        self.bake_button = None
        self.size_estimate_label = None
        self.bake_progress_bar = None
        self.bake_status_label = None
        # Tooltip
        self.tooltip = None
        self.last_mouse_world_pos = (None, None)
        
        # --- Bake Communication ---
        self.bake_progress_queue = None
        
        # --- State for Live Preview Mode ---
        # This MUST be initialized before _setup_ui() is called.
        self.live_preview_surface = None
        # This will hold the result of the bake size analysis.
        self.estimated_uniform_ratio = 0.0

        # --- Hierarchical Caching (Rule 11) ---
        # Dirty flags to control the regeneration pipeline
        self.plate_layout_dirty = True # NEW: For expensive Voronoi calculation
        self.tectonic_params_dirty = True
        self.terrain_maps_dirty = True
        self.climate_maps_dirty = True

        # Cached data maps to avoid recalculation
        self.cached_plate_ids = None # NEW
        self.cached_dist1 = None # NEW
        self.cached_dist2 = None # NEW
        self.cached_tectonic_influence_map = None
        self.cached_tectonic_uplift_map = None
        self.cached_bedrock_map = None
        self.cached_slope_map = None
        self.cached_soil_depth_map = None
        self.cached_final_elevation_map = None

        # This will hold the raw data arrays for the live preview, allowing the
        # tooltip to sample from the exact same data the renderer uses.
        self.live_preview_elevation_data = None # This will now be a pointer to the cache
        self.live_preview_temp_data = None
        self.live_preview_humidity_data = None
        # Pre-compute color LUTs once to avoid doing it every frame (Rule 11)
        self.temp_lut = color_maps.create_temperature_lut()
        self.humidity_lut = color_maps.create_humidity_lut()

        # --- Dependency Injection (Rule 7, DIP) ---
        # This block MUST be executed before _setup_ui() because the UI
        # now depends on the world_generator for its initial values.
        self.world_generator = WorldGenerator(
            config=self.config.get('world_generation_parameters', {}),
            logger=self.logger
        )
        self.camera = Camera(self.config, self.world_generator)
        self.world_renderer = WorldRenderer(
            logger=self.logger
        )

        self._setup_ui()
        self._create_reverse_color_map()

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

        # --- Live Editor Benchmark State ---
        self.live_editor_benchmark_config = self.config.get('live_editor_benchmark', {})
        self.is_live_editor_benchmark_running = self.live_editor_benchmark_config.get('enabled', False)

        self._perf_test_path = []
        self._perf_test_current_action = None
        self._perf_test_action_frame_count = 0
        if self.is_perf_test_running:
            self.logger.info("Performance test mode is ENABLED. User input will be ignored.")
            # Create a simple, expanded path for easier processing
            for step in self.perf_test_config.get('path', []):
                for _ in range(step['frames']):
                    self._perf_test_path.append(step)

        self.is_running = True

    def _setup_logging(self):
        """Initializes the logging system from a config file."""
        log_config_path = 'editor/logging_config.json'
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
        config_path = 'editor/config.json'
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

        # --- Get world parameters from the generator, the single source of truth ---
        world_settings = self.world_generator.settings

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
            start_value=world_settings.get('target_sea_level_temp_c', 15.0),
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
            start_value=world_settings.get('detail_noise_weight', 0.25),
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
            start_value=world_settings.get('lapse_rate_c_per_unit_elevation', 40.0),
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
            start_value=world_settings.get('terrain_base_feature_scale_km', 40.0),
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
            start_value=world_settings.get('terrain_amplitude', 2.5),
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
            start_value=world_settings.get('polar_temperature_drop_c', 30.0),
            value_range=(0.0, 80.0),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_SLIDER_HEIGHT + UI_PADDING

        # --- Slider 8: Tectonic Smoothness ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Tectonic Smoothness (km)",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.mountain_smoothness_slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_SLIDER_HEIGHT),
            start_value=world_settings.get('mountain_uplift_feature_scale_km', 15.0),
            value_range=(2.0, 75.0),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_SLIDER_HEIGHT + UI_PADDING

        # --- Slider 9: Tectonic Width ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Tectonic Width (km)",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.mountain_width_slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_SLIDER_HEIGHT),
            start_value=world_settings.get('mountain_influence_radius_km', 5.0),
            value_range=(5.0, 250.0),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_SLIDER_HEIGHT + UI_PADDING

        # --- Slider 10: Tectonic Strength ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Tectonic Strength",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.tectonic_strength_slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_SLIDER_HEIGHT),
            start_value=world_settings.get('mountain_uplift_strength', 0.8),
            value_range=(0.0, 5.0),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_SLIDER_HEIGHT + UI_PADDING

                # --- Tectonic Plate Controls ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Number of Tectonic Plates",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        # Define layout for the button group
        button_width = 40
        label_width = element_width - (2 * button_width) - (2 * UI_PADDING)
        
        self.decrease_plates_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(UI_PADDING, current_y, button_width, UI_BUTTON_HEIGHT),
            text="-",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        
        self.plate_count_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING + button_width + UI_PADDING, current_y, label_width, UI_BUTTON_HEIGHT),
            text=str(world_settings.get('num_tectonic_plates', 40)),
            manager=self.ui_manager,
            container=self.ui_panel
        )

        self.increase_plates_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(UI_PADDING + button_width + UI_PADDING + label_width + UI_PADDING, current_y, button_width, UI_BUTTON_HEIGHT),
            text="+",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_BUTTON_HEIGHT + (UI_PADDING * 2)

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
        self.world_width_input.set_text(str(world_settings.get('world_width_chunks', 800)))

        self.world_height_input = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(UI_PADDING + input_width + UI_PADDING, current_y, input_width, UI_ELEMENT_HEIGHT),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        self.world_height_input.set_text(str(world_settings.get('world_height_chunks', 450)))
        current_y += UI_ELEMENT_HEIGHT + UI_PADDING

        self.apply_size_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_BUTTON_HEIGHT),
            text="Apply Size Changes",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_BUTTON_HEIGHT

        # --- New Label for KM Display ---
        self.km_size_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="(calculating km...)",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        self._update_km_size_label() # Set initial value
        current_y += UI_ELEMENT_HEIGHT + (UI_PADDING * 2)

        # --- Bake Button and Size Estimate ---
        self.size_estimate_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="Estimated Size: (Not Calculated)",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.calculate_size_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_BUTTON_HEIGHT),
            text="Calculate Bake Size",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_BUTTON_HEIGHT + UI_PADDING

        self.bake_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_BUTTON_HEIGHT),
            text="Bake World",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_BUTTON_HEIGHT + UI_PADDING

        # --- Bake Progress UI ---
        self.bake_progress_bar = pygame_gui.elements.UIProgressBar(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            manager=self.ui_manager,
            container=self.ui_panel,
            visible=False  # Initially hidden
        )
        current_y += UI_ELEMENT_HEIGHT

        self.bake_status_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="",
            manager=self.ui_manager,
            container=self.ui_panel,
            visible=False  # Initially hidden
        )

        # --- Tooltip Initialization ---
        # Create the tooltip using a UITextBox, which is the correct element for
        # handling dynamic, multi-line content. It will resize automatically.
        # A width of 250 provides enough space to prevent the layout engine from
        # crashing when rendering longer text strings like "Humidity:".
        self.tooltip = pygame_gui.elements.UITextBox(
            relative_rect=pygame.Rect(0, 0, 250, -1),
            html_text="",
            manager=self.ui_manager,
            visible=False
        )

    def run(self):
        """The main application loop."""
        # Profiler is now enabled conditionally based on the run mode.

        # --- Live Editor Performance Test Execution ---
        if self.is_live_editor_benchmark_running:
            # The benchmark measures its own timings; profiler overhead would skew results.
            if self.profiler:
                self.logger.info("Disabling cProfile for benchmark to ensure accurate timing.")
                self.profiler = None
            self._run_live_editor_benchmark()
            self.is_running = False # Ensure the app exits after the test
        # --- Benchmark Mode Execution (Rule 11) ---
        elif self.is_benchmark_running:
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

                # --- Staged Preview Regeneration (Rule 5 & 11) ---
                # If any parameter has changed, regenerate the necessary parts of the pipeline.
                is_dirty = self.tectonic_params_dirty or self.terrain_maps_dirty or self.climate_maps_dirty
                if is_dirty:
                    self.logger.info(f"Change detected. Regenerating preview data for view mode: '{self.view_mode}'...")

                    # The Application now orchestrates data generation for the preview.
                    color_array = self._generate_preview_color_array()

                    # Pass the final color data to the renderer to create the surface.
                    self.live_preview_surface = self.world_renderer.create_surface_from_color_array(color_array)

                    # Reset the estimate label as the world has changed.
                    self.size_estimate_label.set_text("Estimated Size: (Recalculate Needed)")

                    # Reset all flags now that the regeneration is complete.
                    self.tectonic_params_dirty = False
                    self.terrain_maps_dirty = False
                    self.climate_maps_dirty = False
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
                param_map = {
                    self.temp_slider: 'target_sea_level_temp_c',
                    self.roughness_slider: 'detail_noise_weight',
                    self.lapse_rate_slider: 'lapse_rate_c_per_unit_elevation',
                    self.continent_size_slider: 'terrain_base_feature_scale_km',
                    self.terrain_amplitude_slider: 'terrain_amplitude',
                    self.polar_drop_slider: 'polar_temperature_drop_c',
                    self.mountain_smoothness_slider: 'mountain_uplift_feature_scale_km',
                    self.mountain_width_slider: 'mountain_influence_radius_km',
                    self.tectonic_strength_slider: 'mountain_uplift_strength'
                }
                param_name = param_map.get(event.ui_element)
                if param_name:
                    self._update_world_parameter(param_name, event.value)
            
            if event.type == pygame_gui.UI_BUTTON_PRESSED:
                if event.ui_element == self.bake_button:
                    self._start_threaded_bake()
                elif event.ui_element == self.apply_size_button:
                    self._apply_world_size_changes()
                elif event.ui_element == self.calculate_size_button:
                    self._calculate_and_display_bake_size()
                else:
                    self._handle_plate_button_press(event.ui_element)

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
                    # The underlying data is unchanged, only the colorization needs to be redone.
                    # Setting the climate flag is the cheapest way to trigger the regeneration pipeline.
                    self.climate_maps_dirty = True
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

            # 1. Get the current settings from the existing generator to preserve slider changes.
            current_settings = self.world_generator.settings
            current_settings['world_width_chunks'] = new_width
            current_settings['world_height_chunks'] = new_height

            # 2. Re-initialize the WorldGenerator with the updated settings dictionary.
            self.world_generator = WorldGenerator(
                config=current_settings,
                logger=self.logger
            )

            # 3. Re-initialize the Camera, which depends on the generator's dimensions
            self.camera = Camera(self.config, self.world_generator)

            # 4. Update the new KM label and reset the bake size estimate
            self._update_km_size_label()
            self.size_estimate_label.set_text("Estimated Size: (Recalculate Needed)")

            # 5. Trigger a full regeneration of the live preview
            # Set all dirty flags to true to force a full rebuild.
            self.tectonic_params_dirty = True
            self.terrain_maps_dirty = True
            self.climate_maps_dirty = True

        except ValueError:
            self.logger.error("Invalid world size input. Please enter integers only.")
            # Optionally, reset the text to the current valid values
            self.world_width_input.set_text(str(self.config['world_generation_parameters']['world_width_chunks']))
            self.world_height_input.set_text(str(self.config['world_generation_parameters']['world_height_chunks']))

    def _update_world_parameter(self, name: str, value):
        """
        A centralized method to update a world parameter and set the correct
        dirty flags for the renderer and cache systems.
        """
        settings = self.world_generator.settings
        
        # 1. Update the setting's value
        settings[name] = value

# 2. Define parameter categories
        # NEW: Split tectonic keys into layout vs. non-layout
        plate_layout_keys = ['num_tectonic_plates']
        tectonic_keys = [
            'mountain_influence_radius_km',
            'mountain_uplift_feature_scale_km', # Tectonic smoothness affects uplift noise
            'mountain_uplift_strength' # Controls the result of the uplift calculation
        ]
        terrain_keys = [
            'detail_noise_weight', # Roughness
            'terrain_base_feature_scale_km', # Continent size
            'terrain_amplitude' # Sharpness
        ]
        
        # 3. Set dirty flags in a cascading manner
        if name in plate_layout_keys:
            self.plate_layout_dirty = True
            self.tectonic_params_dirty = True
            self.terrain_maps_dirty = True
            self.climate_maps_dirty = True
            self.logger.info(f"Plate layout parameter '{name}' changed. Invalidating all caches.")
        elif name in tectonic_keys:
            # This no longer invalidates the plate layout cache
            self.tectonic_params_dirty = True
            self.terrain_maps_dirty = True
            self.climate_maps_dirty = True
            self.logger.info(f"Tectonic parameter '{name}' changed. Invalidating tectonic, terrain and climate caches.")
        elif name in terrain_keys:
            self.terrain_maps_dirty = True
            self.climate_maps_dirty = True
            self.logger.info(f"Terrain parameter '{name}' changed. Invalidating terrain and climate caches.")
        else: # Assume it's a climate-only parameter
            self.climate_maps_dirty = True

        # 4. Handle special cases that require more than just a value change
        if name == 'terrain_base_feature_scale_km':
            from world_generator.config import CM_PER_KM
            settings['base_noise_scale'] = value * CM_PER_KM
        elif name == 'mountain_uplift_feature_scale_km':
            from world_generator.config import CM_PER_KM
            settings['mountain_uplift_noise_scale'] = value * CM_PER_KM
        elif name == 'num_tectonic_plates':
            # Also update the UI label when the plate count changes
            self.plate_count_label.set_text(str(int(value)))

    def _update_km_size_label(self):
        """Calculates and displays the world size in kilometers."""
        if not self.km_size_label:
            return

        from world_generator.config import CM_PER_KM
        
        width_km = self.world_generator.world_width_cm / CM_PER_KM
        height_km = self.world_generator.world_height_cm / CM_PER_KM

        self.km_size_label.set_text(f"({width_km:.1f} km x {height_km:.1f} km)")

    def _generate_preview_color_array(self) -> np.ndarray:
        """
        Generates the raw data and color array for the current preview state.
        This method implements a staged, cached pipeline to ensure only the
        necessary calculations are performed.
        """
        # Create a coordinate grid for the entire world at preview resolution.
        # This is cheap and always needed.
        wx = np.linspace(0, self.world_generator.world_width_cm, PREVIEW_RESOLUTION_WIDTH)
        wy = np.linspace(0, self.world_generator.world_height_cm, PREVIEW_RESOLUTION_HEIGHT)
        wx_grid, wy_grid = np.meshgrid(wx, wy)

        # --- Stage 1: Tectonic Generation (Decoupled & Cached) ---
        # Stage 1a: Recalculate the expensive Voronoi data ONLY if the plate layout has changed.
        if self.plate_layout_dirty or self.cached_plate_ids is None:
            self.logger.info("Plate layout changed. Recalculating Voronoi data...")
            plate_ids, dist1, dist2 = self.world_generator.get_tectonic_data(wx_grid, wy_grid)
            self.cached_plate_ids = plate_ids
            self.cached_dist1 = dist1
            self.cached_dist2 = dist2
            self.plate_layout_dirty = False # Reset the flag
            self.logger.info("Voronoi data caching complete.")

        # Stage 1b: Recalculate the cheap influence and uplift maps if any tectonic param has changed.
        if self.tectonic_params_dirty or self.cached_tectonic_influence_map is None:
            self.logger.info("Tectonic parameters changed. Recalculating influence and uplift maps...")
            # This now uses the cached distance data and is very fast.
            from world_generator import tectonics # Import the module directly
            from world_generator.config import CM_PER_KM
            radius_cm = self.world_generator.settings['mountain_influence_radius_km'] * CM_PER_KM
            self.cached_tectonic_influence_map = tectonics.calculate_influence_map(
                self.cached_dist1, self.cached_dist2, radius_cm
            )
            
            # The uplift map also depends on the influence map, so it's recalculated here.
            self.cached_tectonic_uplift_map = self.world_generator.get_tectonic_uplift(
                wx_grid, wy_grid, influence_map=self.cached_tectonic_influence_map
            )
            self.logger.info("Tectonic map caching complete.")

        # --- Stage 2: Terrain Generation ---
        # This runs if terrain or tectonic params change.
        if self.terrain_maps_dirty or self.cached_final_elevation_map is None:
            self.logger.info("Terrain parameters changed. Recalculating bedrock, soil, and final elevation...")
            self.cached_bedrock_map = self.world_generator._get_bedrock_elevation(
                wx_grid, wy_grid, tectonic_uplift_map=self.cached_tectonic_uplift_map
            )
            
            # Manually perform the steps of get_elevation to cache intermediate maps
            water_level = self.world_generator.settings['terrain_levels']['water']
            land_mask = self.cached_bedrock_map >= water_level
            self.cached_slope_map = self.world_generator._get_slope(self.cached_bedrock_map)
            self.cached_soil_depth_map = self.world_generator._get_soil_depth(self.cached_slope_map)
            self.cached_soil_depth_map[~land_mask] = 0.0
            self.cached_final_elevation_map = np.clip(self.cached_bedrock_map + self.cached_soil_depth_map, 0.0, 1.0)
            
            self.live_preview_elevation_data = self.cached_final_elevation_map
            self.logger.info("Terrain map caching complete.")

        # --- Stage 3: Climate Generation ---
        # This runs if any parameter changes, using the cached elevation map.
        self.live_preview_temp_data = self.world_generator.get_temperature(
            wx_grid, wy_grid, self.cached_final_elevation_map
        )
        self.live_preview_humidity_data = self.world_generator.get_humidity(
            wx_grid, wy_grid, self.cached_final_elevation_map, self.live_preview_temp_data
        )

        # --- Stage 4: Colorization ---
        # This always runs to reflect the latest data, using the final cached maps.
        if self.view_mode == "terrain":
            return color_maps.get_terrain_color_array(
                self.cached_final_elevation_map, 
                self.live_preview_temp_data, 
                self.live_preview_humidity_data, 
                self.cached_soil_depth_map
            )
        elif self.view_mode == "temperature":
            return color_maps.get_temperature_color_array(self.live_preview_temp_data, self.temp_lut)
        elif self.view_mode == "humidity":
            return color_maps.get_humidity_color_array(self.live_preview_humidity_data, self.humidity_lut)
        elif self.view_mode == "elevation":
            return color_maps.get_elevation_color_array(self.cached_final_elevation_map)
        elif self.view_mode == "soil_depth":
            max_depth = self.world_generator.settings['max_soil_depth_units']
            if max_depth > 0:
                normalized_soil = self.cached_soil_depth_map / max_depth
            else:
                normalized_soil = np.zeros_like(self.cached_soil_depth_map)
            return color_maps.get_elevation_color_array(normalized_soil)
        else: # tectonic
            strength = self.world_generator.settings['mountain_uplift_strength']
            if strength > 0:
                normalized_map = self.cached_tectonic_uplift_map / (2 * strength)
            else:
                normalized_map = np.zeros_like(self.cached_tectonic_uplift_map)
            return color_maps.get_elevation_color_array(normalized_map)

    def _calculate_and_display_bake_size(self):
        """
        Performs an on-demand analysis of the world to provide a hyper-accurate
        bake size estimate that accounts for both uniform chunk compression and
        content-based deduplication.
        """
        self.logger.info("Calculating bake size estimate...")
        self.size_estimate_label.set_text("Estimating... Please Wait")

        # 1. Generate preview data for terrain, which serves as our proxy.
        color_array = self._generate_preview_color_array()

        # 2. Analyze the preview data by simulating the baker's logic.
        h, w, _ = color_array.shape
        grid_h, grid_w = ESTIMATE_GRID_HEIGHT, ESTIMATE_GRID_WIDTH
        cell_h, cell_w = h // grid_h, w // grid_w

        if cell_h == 0 or cell_w == 0:
            self.logger.warning("Preview resolution too small for analysis.")
            self.size_estimate_label.set_text("Error: Preview too small")
            return

        unique_hashes = set()
        unique_uniform_count = 0
        unique_palettized_count = 0
        unique_full_count = 0

        for i in range(grid_h):
            for j in range(grid_w):
                cell = color_array[i*cell_h:(i+1)*cell_h, j*cell_w:(j+1)*cell_w]
                # Skip empty cells that can result from integer division
                if cell.size == 0:
                    continue
                
                cell_hash = hashlib.md5(cell.tobytes()).hexdigest()

                if cell_hash not in unique_hashes:
                    unique_hashes.add(cell_hash)
                    
                    # Tier 1: Check for uniform.
                    if (cell == cell[0, 0]).all():
                        unique_uniform_count += 1
                    else:
                        # Tier 2: Check for low color count.
                        num_colors = len(np.unique(cell.reshape(-1, 3), axis=0))
                        if num_colors <= 256:
                            unique_palettized_count += 1
                        else:
                            # Tier 3: Fallback to full.
                            unique_full_count += 1
        
        # 3. Use the absolute count of unique patterns from the preview as the estimate.
        if not unique_hashes: return

        num_view_modes = len(self.view_modes)

        # 4. Calculate the final size based on the absolute number and mix of unique chunks.
        size_kb_uniform = unique_uniform_count * ESTIMATED_COMPRESSED_CHUNK_SIZE_KB
        size_kb_palettized = unique_palettized_count * ESTIMATED_PALETTIZED_CHUNK_SIZE_KB
        size_kb_full = unique_full_count * ESTIMATED_CHUNK_SIZE_KB
        
        # The total size is the sum of the sizes of all unique chunks found,
        # multiplied by the number of view modes (terrain, temp, etc.).
        total_kb = (size_kb_uniform + size_kb_palettized + size_kb_full) * num_view_modes
        total_gb = total_kb / (1024 * 1024)

        self.size_estimate_label.set_text(f"Estimated Bake Size: {total_gb:.2f} GB")
        self.logger.info(f"Bake size estimation complete. Result: {total_gb:.2f} GB")

    def _update_tooltip(self):
        """
        Updates the tooltip's position, content, and visibility based on the
        mouse cursor's location.
        """
        mouse_pos = pygame.mouse.get_pos()
        
        # Check if the mouse is over the UI panel. If so, hide the tooltip.
        is_over_ui = self.ui_panel.get_abs_rect().collidepoint(mouse_pos)
        if is_over_ui:
            self.tooltip.hide()
            return

        # Show the tooltip if it was hidden
        if not self.tooltip.visible:
            self.tooltip.show()

        # --- Position Update ---
        self.tooltip.set_position((mouse_pos[0] + 15, mouse_pos[1] + 15))

        # --- Content Update ---
        world_x, world_y = self.camera.screen_to_world(mouse_pos[0], mouse_pos[1])

        # For performance, only recalculate data if the mouse has moved to a new world pixel.
        if (int(world_x), int(world_y)) == self.last_mouse_world_pos:
            return
        self.last_mouse_world_pos = (int(world_x), int(world_y))
        
        # --- Initialize default values ---
        temp = 0.0
        humidity = 0.0
        terrain_type = "Unknown"

        # --- Sample Data from Cached Preview Arrays ---
        # This is the definitive method. It guarantees the tooltip matches the render.
        if self.live_preview_surface and self.live_preview_humidity_data is not None:
            # Get the dimensions of the data array and the surface
            data_h, data_w = self.live_preview_humidity_data.shape
            surface_w, surface_h = self.live_preview_surface.get_size()

            # Convert world coordinates to pixel coordinates on the preview data grid
            px_data = int((world_x / self.world_generator.world_width_cm) * data_w)
            py_data = int((world_y / self.world_generator.world_height_cm) * data_h)

            # Ensure data coordinates are within bounds for sampling raw values
            if 0 <= px_data < data_w and 0 <= py_data < data_h:
                # Sample the raw data values directly from the pre-computed arrays.
                # NumPy arrays are indexed (row, col), which corresponds to (y, x).
                temp = self.live_preview_temp_data[py_data, px_data]
                humidity = self.live_preview_humidity_data[py_data, px_data]

            # --- Determine Terrain Type String by Sampling Pixel Color ---
            # Convert world coordinates to pixel coordinates on the preview surface
            px_surf = int((world_x / self.world_generator.world_width_cm) * surface_w)
            py_surf = int((world_y / self.world_generator.world_height_cm) * surface_h)

            # Ensure surface coordinates are within bounds for sampling color
            if 0 <= px_surf < surface_w and 0 <= py_surf < surface_h:
                sampled_rgba = self.live_preview_surface.get_at((px_surf, py_surf))
                sampled_rgb = tuple(sampled_rgba[:3])

                # First, try a direct, fast lookup
                terrain_type = self.color_to_terrain_map.get(sampled_rgb)

                # If not found (due to scaling interpolation), find the nearest known color
                if terrain_type is None:
                    distances = np.sum((self.known_colors_array - sampled_rgb)**2, axis=1)
                    closest_color_index = np.argmin(distances)
                    closest_color = self.known_colors_list[closest_color_index]
                    terrain_type = self.color_to_terrain_map[closest_color]
        
        # Format the final string as simple HTML and update the tooltip.
        tooltip_text = (
            f"<b>Terrain:</b> {terrain_type}<br>"
            f"<b>Temp:</b> {temp:.1f}°C<br>"
            f"<b>Humidity:</b> {humidity:.1f} g/m3"
        )
        self.tooltip.set_text(tooltip_text)
        
        # The UITextBox handles its own resizing and positioning.
        self.tooltip.set_position((mouse_pos[0] + 15, mouse_pos[1] + 15))
        if not self.tooltip.visible:
            self.tooltip.show()

    def _run_live_editor_benchmark(self):
        """
        Executes a series of automated, VISUAL tests to demonstrate the performance
        of the live preview regeneration pipeline. This is not for timing, but for
        visual confirmation.
        """
        self.logger.info("Live editor visual benchmark ENABLED. Running tests...")

        # --- Fit world to screen for better viewing ---
        drawable_width = self.screen_width - UI_PANEL_WIDTH
        drawable_height = self.screen_height
        
        # Calculate the required zoom to fit the world width and height into the drawable area
        zoom_x = drawable_width / self.camera.world_width
        zoom_y = drawable_height / self.camera.world_height
        
        # Use the smaller of the two zoom levels to ensure the entire world is visible
        self.camera.zoom = min(zoom_x, zoom_y)
        self.logger.info(f"Camera zoom adjusted to {self.camera.zoom:.6f} to fit screen.")
        
        # --- Map parameter names from config to the actual UI slider objects ---
        param_to_slider_map = {
            "target_sea_level_temp_c": self.temp_slider,
            "detail_noise_weight": self.roughness_slider,
            "lapse_rate_c_per_unit_elevation": self.lapse_rate_slider,
            "terrain_base_feature_scale_km": self.continent_size_slider,
            "terrain_amplitude": self.terrain_amplitude_slider,
            "polar_temperature_drop_c": self.polar_drop_slider,
            "mountain_uplift_feature_scale_km": self.mountain_smoothness_slider,
            "mountain_influence_radius_km": self.mountain_width_slider,
            "mountain_uplift_strength": self.tectonic_strength_slider,
        }

        test_steps = self.live_editor_benchmark_config.get('steps', [])
        
        for step in test_steps:
            description = step['description']
            param_name = step['parameter_name']
            test_values = step['test_values']
            
            self.logger.info(f"--- Visually Testing Parameter: {description} ---")

            # --- Start Profiling for the entire set of values ---
            profiler = cProfile.Profile()
            profiler.enable()

            for value in test_values:
                # --- Allow user to exit mid-benchmark ---
                for event in pygame.event.get():
                    if (event.type == pygame.QUIT or
                       (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE)):
                        self.logger.warning("Benchmark terminated early by user.")
                        self.is_running = False
                        profiler.disable() # Ensure profiler is stopped on early exit
                        return
                
                self.logger.info(f"Setting '{description}' to value: {value}")
                
                # --- Programmatically update the UI and settings ---
                slider = param_to_slider_map.get(param_name)
                if slider:
                    slider.set_current_value(value)
                    self._update_world_parameter(param_name, value)
                elif param_name == 'num_tectonic_plates':
                    self._update_world_parameter(param_name, int(value))
                else:
                    self.logger.warning(f"No UI element found for parameter '{param_name}'. Skipping.")
                    continue

                # --- Force a single frame update and render ---
                time_delta = self.clock.tick(self.tick_rate) / 1000.0

                # 1. Regenerate the world preview if dirty (which it is)
                is_dirty = self.tectonic_params_dirty or self.terrain_maps_dirty or self.climate_maps_dirty
                if is_dirty:
                    self.logger.debug("Regenerating preview for benchmark step...")
                    
                    # The profiler is already running, so we just call the function.
                    color_array = self._generate_preview_color_array()

                    self.live_preview_surface = self.world_renderer.create_surface_from_color_array(color_array)
                    self.size_estimate_label.set_text("Estimated Size: (Recalculate Needed)")
                    
                    # Reset all flags after regeneration
                    self.tectonic_params_dirty = False
                    self.terrain_maps_dirty = False
                    self.climate_maps_dirty = False
                    self.logger.debug("Regeneration complete.")

                # 2. Draw the world and UI to the screen
                self.world_renderer.draw_live_preview(self.screen, self.camera, self.live_preview_surface)
                self.ui_manager.update(time_delta)
                self.ui_manager.draw_ui(self.screen)
                pygame.display.flip()

                # 3. Pause briefly so the change is visible
                pygame.time.wait(100) # Wait 100 milliseconds

            # --- Stop Profiling and Report for the entire set ---
            profiler.disable()
            s = io.StringIO()
            ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
            ps.print_stats(5)
            # The log message now refers to the entire parameter test.
            self.logger.info(f"\n--- Profiling Report for '{description}' (all values) ---\n{s.getvalue()}")

        self.logger.info("Visual benchmark complete.")

    def _create_reverse_color_map(self):
        """
        Creates a mapping from RGB color tuples to terrain name strings.
        This is used by the tooltip to identify terrain by sampling pixel colors.
        It also handles cases where scaling might slightly alter colors by finding
        the "closest" known color.
        """
        from world_generator import color_maps
        
        # Create a simple forward map from the constants file
        forward_map = {
            **color_maps.COLOR_MAP_TERRAIN,
            "snow": color_maps.COLOR_SNOW,
            "ice": color_maps.COLOR_ICE
        }
        
        # Invert the map and format the names
        self.color_to_terrain_map = {
            tuple(v): k.replace("_", " ").title() for k, v in forward_map.items()
        }
        
        # Store the raw color values for our "nearest color" calculation
        self.known_colors_list = list(self.color_to_terrain_map.keys())
        self.known_colors_array = np.array(self.known_colors_list)

    def _start_threaded_bake(self):
        """
        Launches the baker function in a separate, non-blocking thread and
        establishes a queue for progress updates.
        """
        self.logger.info("Bake process requested by user.")
        self.bake_button.set_text("Baking in Progress...")
        self.bake_button.disable()

        # Reset and show the progress UI
        self.bake_progress_bar.set_current_progress(0)
        self.bake_progress_bar.show()
        self.bake_status_label.set_text("Baking...")
        self.bake_status_label.show()

        bake_config = self.config.copy()
        bake_config['world_generation_parameters'] = self.world_generator.settings

        # Create the communication queue for this bake instance.
        self.bake_progress_queue = queue.Queue()

        # Create and start the background thread.
        bake_thread = threading.Thread(
            target=baker.bake_world,
            args=(bake_config, self.bake_progress_queue),
            daemon=True
        )
        bake_thread.start()
        self.logger.info("Successfully launched background bake thread.")

    def _update(self):
        """Update application state. Runs the performance test if active."""
        self._update_tooltip()
        self._check_bake_progress()

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
        # Load the stats from the file that was just saved. This is more robust
        # than passing the profiler object directly and avoids potential TypeErrors.
        ps = pstats.Stats(filepath, stream=s).sort_stats('cumulative')
        ps.print_stats(log_count)
        
        self.logger.info(f"--- Top {log_count} Profiling Results ---\n{s.getvalue()}")

    def _handle_plate_button_press(self, ui_element):
        """Handles clicks on the tectonic plate adjustment buttons."""
        settings = self.world_generator.settings
        current_plates = settings['num_tectonic_plates']
        new_plates = current_plates

        if ui_element == self.increase_plates_button:
            new_plates = min(250, current_plates + 1)
        elif ui_element == self.decrease_plates_button:
            new_plates = max(2, current_plates - 1)
        
        if new_plates != current_plates:
            self._update_world_parameter('num_tectonic_plates', new_plates)

    def _check_bake_progress(self):
        """Polls the bake progress queue and updates the UI."""
        if self.bake_progress_queue:
            try:
                message = self.bake_progress_queue.get_nowait()
                self.logger.info(f"BAKER MSG: {message}") # Keep logging for debug

                status = message.get("status")
                if status == "running":
                    progress = message.get("progress", 0.0)
                    self.bake_progress_bar.set_current_progress(progress)
                    self.bake_status_label.set_text(f"Baking... {int(progress * 100)}%")
                
                elif status in ["complete", "error"]:
                    self.bake_status_label.set_text(message.get("message", "Done!"))
                    self.bake_progress_bar.hide()
                    self.bake_button.set_text("Bake World")
                    self.bake_button.enable()
                    self.bake_progress_queue = None

            except queue.Empty:
                pass

if __name__ == '__main__':
    # --- Lazy Imports (Rule 7 / Performance) ---
    # These are imported here so that worker processes spawned by the baker
    # do not import heavy GUI libraries they don't need.
    import pygame
    import pygame_gui
    from renderer import WorldRenderer
    from camera import Camera

    app = Application()
    app.run()