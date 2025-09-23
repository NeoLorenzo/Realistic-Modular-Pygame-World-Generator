# editor/main.py

import sys
import os
import json
import logging
import logging.config
import time
import cProfile
import multiprocessing
from baker_worker import run_chunk_baking_job
import pstats
import io
from datetime import datetime
import numpy as np
import hashlib
from PIL import Image
import pygame

from world_generator.generator import WorldGenerator
# Import the color_maps module to access its functions.
from world_generator import color_maps

# --- UI Constants (Rule 1) ---
UI_PANEL_WIDTH = 320
UI_ELEMENT_HEIGHT = 25
UI_SLIDER_HEIGHT = 25
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

class EditorState:
    """The main application state for the live editor."""

    def __init__(self, app):
        # --- Core Application References ---
        self.go_to_menu = False
        self.app = app
        self.logger = app.logger
        self.config = app.config
        self.screen = app.screen
        self.clock = app.clock
        self.tick_rate = app.tick_rate
        
        self.logger.info("EditorState starting.")

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
        # Tooltip
        self.tooltip = None
        self.last_mouse_world_pos = (None, None)
        # World Edge UI
        self.world_edge_dropdown = None
        
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
        self.cached_coastal_factor_map = None
        self.cached_shadow_factor_map = None
        self.cached_climate_noise_map = None
        self.cached_biome_map = None

        # This will hold the raw data arrays for the live preview, allowing the
        # tooltip to sample from the exact same data the renderer uses.
        self.live_preview_elevation_data = None # This will now be a pointer to the cache
        self.live_preview_temp_data = None
        self.live_preview_humidity_data = None
        # Pre-compute color LUTs once to avoid doing it every frame (Rule 11)
        self.temp_lut = color_maps.create_temperature_lut()
        self.humidity_lut = color_maps.create_humidity_lut()
        self.biome_lut = color_maps.create_biome_color_lut()

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

        # --- Visual Baker State ---
        self.is_baking = False
        self.baking_setup_done = False
        self.baking_pool = None
        self.baking_pending_results = []
        self.baking_background_surface = None
        self.baking_background_pos = (0, 0)
        self.baking_overlay_surface = None

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

        # --- Handle Special Run Modes ---
        if self.is_live_editor_benchmark_running:
            if self.profiler:
                self.logger.info("Disabling cProfile for benchmark to ensure accurate timing.")
                self.profiler = None
            self._run_live_editor_benchmark()
            self.is_running = False # Signal immediate exit after benchmark
        elif self.is_benchmark_running:
            self.logger.info("Benchmark mode ENABLED. Application will exit after generation.")
            if self.profiler: self.profiler.enable()
            start_time = time.perf_counter()
            # This is a placeholder for a future benchmark of the live preview generation
            self.world_renderer.generate_live_preview_surface(
                world_params=self.config['world_generation_parameters'],
                view_mode=self.view_mode
            )
            end_time = time.perf_counter()
            if self.profiler: self.profiler.disable()
            duration = end_time - start_time
            self.logger.info(f"Benchmark complete. Live preview generation took: {duration:.3f} seconds.")
            self.is_running = False # Signal immediate exit after benchmark
        else:
            self.logger.info("Entering interactive editor mode.")
            if self.profiler:
                self.profiler.enable()

    def _setup_ui(self):
        """Initializes the pygame_gui manager and creates the UI layout."""
        self.ui_manager = pygame_gui.UIManager((self.app.screen_width, self.app.screen_height))
        self.logger.info("UI Manager initialized.")

        # --- Create the main UI Panel ---
        panel_rect = pygame.Rect(
            self.app.screen_width - UI_PANEL_WIDTH, 0,
            UI_PANEL_WIDTH, self.app.screen_height
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
            text="Tectonic Width (% of World)",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.mountain_width_slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_SLIDER_HEIGHT),
            start_value=world_settings.get('mountain_influence_radius_km', 0.05),
            value_range=(0.01, 1.0),
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

        # --- World Edge Controls ---
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_ELEMENT_HEIGHT),
            text="World Edge Shape",
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_ELEMENT_HEIGHT

        self.world_edge_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=['Default', 'Island', 'Valley'],
            starting_option='Default',
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_BUTTON_HEIGHT),
            manager=self.ui_manager,
            container=self.ui_panel
        )
        current_y += UI_BUTTON_HEIGHT + UI_PADDING

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

    # --- Add a "Return to Main Menu" button at the very bottom ---
        # Position it just above the bottom of the panel
        self.main_menu_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(UI_PADDING, self.app.screen_height - UI_BUTTON_HEIGHT - UI_PADDING, element_width, UI_BUTTON_HEIGHT),
            text="Return to Main Menu",
            manager=self.ui_manager,
            container=self.ui_panel
        )

    def handle_events(self, events):
        """Processes user input and other events for this state."""
        # --- Block all input if in baking mode, except for the ESC key ---
        if self.is_baking:
            for event in events:
                if event.type == pygame.QUIT:
                    self.is_running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.logger.info("Bake cancelled by user.")
                    self.is_baking = False
                    self.ui_panel.show() # Re-show the UI
            return # Ignore all other event processing

        for event in events:
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
                if event.ui_element == self.apply_size_button:
                    self._apply_world_size_changes()
                elif event.ui_element == self.calculate_size_button:
                    self._calculate_and_display_bake_size()
                elif event.ui_element == self.bake_button:
                    if self.is_baking:
                        self.logger.warning("A bake is already in progress.")
                        return
                    self.logger.info("Event: 'Bake World' button pressed. Initializing bake.")
                    self.is_baking = True
                    self.baking_setup_done = False

                    # --- Initialize all state for the new bake ---
                    width = self.world_generator.settings['world_width_chunks']
                    height = self.world_generator.settings['world_height_chunks']
                    
                    # Create a queue of all chunk coordinates to be processed
                    self.baking_queue = [(cx, cy) for cy in range(height) for cx in range(width)]
                    self.completed_chunks = set()
                    self.seen_hashes = set()
                    
                    # --- Initialize all state for the new multi-view bake ---
                    self.view_modes_to_bake = list(self.view_modes)
                    self.current_baking_view_index = 0
                    
                    width = self.world_generator.settings['world_width_chunks']
                    height = self.world_generator.settings['world_height_chunks']
                    
                    self.completed_chunks = set()
                    self.seen_hashes = set()
                    
                    self.baking_manifest = {
                        "world_name": f"MyWorld_Seed{self.world_generator.settings['seed']}",
                        "world_dimensions_chunks": [width, height],
                        "chunk_resolution_pixels": self.world_generator.settings.get('chunk_resolution', 100),
                        "chunk_map": {}
                    }
                    
                    # --- CRITICAL FIX: Initialize the output directory path HERE ---
                    self.bake_output_dir = "BakedWorldPackage_Live"
                    os.makedirs(os.path.join(self.bake_output_dir, "chunks"), exist_ok=True)

                    # --- Start the multiprocessing pool ---
                    cpu_count = max(1, multiprocessing.cpu_count() - 1)
                    self.logger.info(f"Starting multiprocessing pool with {cpu_count} workers.")
                    self.baking_pool = multiprocessing.Pool(processes=cpu_count)
                    
                    # --- Submit the first batch of jobs ---
                    self._start_baking_next_view()
                    self.completed_chunks = set()
                    self.seen_hashes = set()
                    
                    # Prepare the in-memory manifest for multiple views
                    self.baking_manifest = {
                        "world_name": f"MyWorld_Seed{self.world_generator.settings['seed']}",
                        "world_dimensions_chunks": [width, height],
                        "chunk_resolution_pixels": self.world_generator.settings.get('chunk_resolution', 100),
                        "chunk_map": {} # Will be populated with view modes as we go
                    }
                    
                    # --- CRITICAL FIX: Initialize the output directory path ---
                    self.bake_output_dir = "BakedWorldPackage_Live"
                    os.makedirs(os.path.join(self.bake_output_dir, "chunks"), exist_ok=True)
                    # Initialize the map for the first view
                    first_view = self.view_modes_to_bake[self.current_baking_view_index]
                    self.baking_manifest["chunk_map"][first_view] = {}
                    
                    # Prepare the output directory
                    self.bake_output_dir = "BakedWorldPackage_Live"
                    os.makedirs(os.path.join(self.bake_output_dir, "chunks"), exist_ok=True)
                elif event.ui_element == self.main_menu_button:
                    self.logger.info("Event: 'Return to Main Menu' button pressed.")
                    self.go_to_menu = True
                else:
                    self._handle_plate_button_press(event.ui_element)
            
            elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
                if event.ui_element == self.world_edge_dropdown:
                    # Convert the user-friendly text to the lowercase key the generator expects.
                    selected_mode = event.text.lower()
                    self._update_world_parameter('world_edge_mode', selected_mode)

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

    def update(self, time_delta):
        """Update state logic. Returns a signal for the state machine."""
        if not hasattr(self, 'go_to_menu'): self.go_to_menu = False
        
        self._update()
        self.ui_manager.update(time_delta)

        # --- Handle Visual Baker Mode ---
        if self.is_baking:
            # --- One-time setup for the entire bake process ---
            if not self.baking_setup_done:
                self.logger.info("Performing one-time setup for baking mode.")
                self.ui_panel.hide()
                drawable_width = self.app.screen_width
                drawable_height = self.app.screen_height
                zoom_x = drawable_width / self.world_generator.world_width_cm
                zoom_y = drawable_height / self.world_generator.world_height_cm
                self.camera.zoom = min(zoom_x, zoom_y)
                self.camera.x = self.world_generator.world_width_cm / 2
                self.camera.y = self.world_generator.world_height_cm / 2
                
                # --- Pre-render the background surface ONCE ---
                self.logger.info("Pre-rendering static background for bake...")
                scaled_width = max(1, int(self.camera.world_width * self.camera.zoom))
                scaled_height = max(1, int(self.camera.world_height * self.camera.zoom))
                self.baking_background_surface = pygame.transform.scale(self.live_preview_surface, (scaled_width, scaled_height))
                self.baking_background_pos = self.camera.world_to_screen(0, 0)
                self._create_baking_overlay_surface()
                self.baking_setup_done = True

            # --- Handle Visual Baker Mode ---
        if self.is_baking:
            # --- One-time setup ---
            if not self.baking_setup_done:
                # ... (setup logic is unchanged) ...
                self.baking_setup_done = True

            # --- Non-Blocking, Incremental Bake Progress Check ---
            remaining_results = []
            for result_obj in self.baking_pending_results:
                if result_obj.ready():
                    # This job is done, get its result and process it
                    res_cx, res_cy, res_view, chunk_hash, needs_saving = result_obj.get()
                    
                    if needs_saving:
                        self.seen_hashes.add(chunk_hash)
                    
                    self.baking_manifest["chunk_map"][res_view][f"{res_cx},{res_cy}"] = chunk_hash
                    self.completed_chunks.add((res_cx, res_cy))

                    # --- OPTIMIZED DRAWING ---
                    # Draw one green square onto the overlay surface, only once.
                    self._draw_completed_chunk_on_overlay(res_cx, res_cy)
                else:
                    # This job is not done yet, keep it for the next frame
                    remaining_results.append(result_obj)
            
            self.baking_pending_results = remaining_results

            # --- Check if the CURRENT VIEW is complete ---
            if not self.baking_pending_results:
                # Check if there are more views to bake
                if self.current_baking_view_index < len(self.view_modes_to_bake) - 1:
                    # If yes, transition to the next view
                    self.current_baking_view_index += 1
                    next_view = self.view_modes_to_bake[self.current_baking_view_index]
                    
                    self.completed_chunks.clear()
                    self.baking_manifest["chunk_map"][next_view] = {}
                    self.view_mode = next_view
                    self.climate_maps_dirty = True
                    
                    # --- Regenerate and re-cache the background for the new view ---
                    # This requires a single frame draw cycle to update the surface
                    color_array = self._generate_preview_color_array()
                    self.live_preview_surface = self.world_renderer.create_surface_from_color_array(color_array)
                    scaled_width = max(1, int(self.camera.world_width * self.camera.zoom))
                    scaled_height = max(1, int(self.camera.world_height * self.camera.zoom))
                    self.baking_background_surface = pygame.transform.scale(self.live_preview_surface, (scaled_width, scaled_height))
                    self._create_baking_overlay_surface()
                    self._start_baking_next_view()
                else:
                    # If no, this was the last view. Finalize the entire bake.
                    self.logger.info("All view modes baked. Finalizing...")
                    manifest_path = os.path.join(self.bake_output_dir, "manifest.json")
                    with open(manifest_path, 'w') as f:
                        json.dump(self.baking_manifest, f)
                    
                    gen_config_path = os.path.join(self.bake_output_dir, "generation_config.json")
                    with open(gen_config_path, 'w') as f:
                        json.dump(self.world_generator.settings, f, indent=4)
                    
                    self.logger.info(f"Bake complete! Output saved to '{self.bake_output_dir}'.")
                    
                    self.is_baking = False
                    self.ui_panel.show()
                    self.baking_pool.close()
                    self.baking_pool.join()
                    self.baking_pool = None
                    self.baking_results = None

        # Performance test exit condition
        if self.is_perf_test_running and self.frame_count >= self.perf_test_config.get('duration_frames', 1000):
            self.logger.info(f"Performance test complete after {self.frame_count} frames.")
            self.is_running = False
        
        if self.go_to_menu:
            self.go_to_menu = False # Reset flag
            return ("GOTO_STATE", "main_menu")

        if not self.is_running:
            return ("QUIT", None)
        return None

    def draw(self, screen):
        """Renders the scene for this state."""
        # --- Staged Preview Regeneration (Rule 5 & 11) ---
        is_dirty = self.tectonic_params_dirty or self.terrain_maps_dirty or self.climate_maps_dirty
        if is_dirty and not self.is_baking: # Don't regenerate preview during a bake
            self.logger.info(f"Change detected. Regenerating preview data for view mode: '{self.view_mode}'...")
            color_array = self._generate_preview_color_array()
            self.live_preview_surface = self.world_renderer.create_surface_from_color_array(color_array)
            self.size_estimate_label.set_text("Estimated Size: (Recalculate Needed)")
            self.tectonic_params_dirty = False
            self.terrain_maps_dirty = False
            self.climate_maps_dirty = False
            self.logger.info("Live preview regeneration complete.")

        # --- CRITICAL FIX: Only draw the expensive preview when NOT baking ---
        if not self.is_baking:
            self.world_renderer.draw_live_preview(screen, self.camera, self.live_preview_surface)
        else:
            # During a bake, blit the pre-scaled, cached background. This is very fast.
            screen.fill((10, 0, 20)) # Fill borders first
            if self.baking_background_surface:
                screen.blit(self.baking_background_surface, self.baking_background_pos)

        # --- Draw the baking overlay if baking is active ---
        if self.is_baking and self.baking_overlay_surface:
            screen.blit(self.baking_overlay_surface, (0, 0))

        self.ui_manager.draw_ui(screen)

    def _create_baking_overlay_surface(self):
        """Creates the initial transparent overlay with the grid."""
        self.logger.info("Creating static grid overlay surface.")
        # Create a surface the size of the screen that supports transparency
        self.baking_overlay_surface = pygame.Surface(self.app.screen.get_size(), pygame.SRCALPHA)
        
        width_chunks = self.world_generator.settings['world_width_chunks']
        height_chunks = self.world_generator.settings['world_height_chunks']
        chunk_size_cm = self.world_generator.settings['chunk_size_cm']
        grid_color = (255, 255, 255, 100) # White, semi-transparent

        for cy in range(height_chunks):
            for cx in range(width_chunks):
                world_x_cm = cx * chunk_size_cm
                world_y_cm = cy * chunk_size_cm
                screen_x, screen_y = self.camera.world_to_screen(world_x_cm, world_y_cm)
                scaled_chunk_size = chunk_size_cm * self.camera.zoom
                chunk_rect = pygame.Rect(screen_x, screen_y, scaled_chunk_size, scaled_chunk_size)
                pygame.draw.rect(self.baking_overlay_surface, grid_color, chunk_rect, 1)

    def _draw_completed_chunk_on_overlay(self, cx, cy):
        """Draws a single green square for a completed chunk onto the overlay."""
        chunk_size_cm = self.world_generator.settings['chunk_size_cm']
        world_x_cm = cx * chunk_size_cm
        world_y_cm = cy * chunk_size_cm
        screen_x, screen_y = self.camera.world_to_screen(world_x_cm, world_y_cm)
        scaled_chunk_size = chunk_size_cm * self.camera.zoom
        
        fill_color = (0, 255, 0, 100)
        s = pygame.Surface((scaled_chunk_size, scaled_chunk_size), pygame.SRCALPHA)
        s.fill(fill_color)
        # Blit this single square onto our persistent overlay surface
        self.baking_overlay_surface.blit(s, (screen_x, screen_y))

    def _start_baking_next_view(self):
        """Prepares and submits all chunk baking jobs for the current view mode to the pool."""
        current_view = self.view_modes_to_bake[self.current_baking_view_index]
        self.logger.info(f"Submitting jobs for view mode: '{current_view}'")

        # Initialize the manifest for the new view
        self.baking_manifest["chunk_map"][current_view] = {}

        width = self.world_generator.settings['world_width_chunks']
        height = self.world_generator.settings['world_height_chunks']
        
        job_args_list = [{
            'cx': cx, 'cy': cy,
            'view_mode': current_view,
            'world_gen_settings': self.world_generator.settings,
            'output_dir': self.bake_output_dir,
            'seen_hashes': self.seen_hashes
        } for cy in range(height) for cx in range(width)]
        
        self.baking_pending_results = [
            self.baking_pool.apply_async(run_chunk_baking_job, (args,))
            for args in job_args_list
        ]

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
            'terrain_amplitude', # Sharpness
            'world_edge_mode' # World shape
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
        # The live preview pipeline requires the default 'xy' indexing for its
        # non-square, frame-based calculations. This is DIFFERENT from the baker.
        wx_grid, wy_grid = np.meshgrid(wx, wy)

        # --- Stage 1: Tectonic Generation (Decoupled & Cached) ---
        # Stage 1a: Recalculate the expensive Voronoi data ONLY if the plate layout has changed.
        if self.plate_layout_dirty or self.cached_plate_ids is None:
            self.logger.info("Plate layout changed. Recalculating Voronoi data...")
            plate_ids, dist1, dist2 = self.world_generator.get_tectonic_data(
                wx_grid, wy_grid,
                self.world_generator.world_width_cm,
                self.world_generator.world_height_cm,
                self.world_generator.settings['num_tectonic_plates'],
                self.world_generator.settings['seed']
            )
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

            # --- Cache all terrain-dependent factors ---
            self.logger.info("Recalculating all terrain-dependent factors (humidity, climate noise)...")
            self.cached_coastal_factor_map = self.world_generator.calculate_coastal_factor_map(
                self.cached_final_elevation_map, wx_grid.shape
            )
            self.cached_shadow_factor_map = self.world_generator.calculate_shadow_factor_map(
                self.cached_final_elevation_map, wx_grid.shape
            )
            self.cached_climate_noise_map = self.world_generator._generate_base_noise(
                wx_grid, wy_grid,
                seed_offset=self.world_generator.settings['temp_seed_offset'],
                scale=self.world_generator.settings['climate_noise_scale']
            )
            self.logger.info("Terrain-dependent factor caching complete.")

        # --- Stage 3: Climate Generation ---
        # This runs if any parameter changes, using the cached elevation map and factors.
        self.live_preview_temp_data = self.world_generator.get_temperature(
            wx_grid, wy_grid, self.cached_final_elevation_map,
            base_noise=self.cached_climate_noise_map
        )
        self.live_preview_humidity_data = self.world_generator.get_humidity(
            wx_grid, wy_grid, self.cached_final_elevation_map, self.live_preview_temp_data,
            coastal_factor_map=self.cached_coastal_factor_map,
            shadow_factor_map=self.cached_shadow_factor_map
        )

        # --- Stage 4: Biome Classification (if needed) ---
        # The expensive biome calculation is now part of the main data pipeline
        # and is only re-run when climate or terrain data has changed.
        if self.climate_maps_dirty or self.cached_biome_map is None:
            self.logger.info("Climate or terrain changed, recalculating biome map...")
            self.cached_biome_map = color_maps.calculate_biome_map(
                self.cached_final_elevation_map,
                self.live_preview_temp_data,
                self.live_preview_humidity_data,
                self.cached_soil_depth_map
            )
            self.logger.info("Biome map caching complete.")

        # --- Stage 5: Colorization ---
        # This always runs, but is now extremely fast for all view modes.
        if self.view_mode == "terrain":
            return color_maps.get_terrain_color_array(self.cached_biome_map, self.biome_lut)
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
            # The maximum possible value for the uplift map is when influence is 1,
            # noise is 1, and strength is at its max (5.0). So, 1 * (1+1) * 5.0 = 10.0.
            # We normalize against this fixed theoretical maximum to ensure the
            # visualization correctly reflects changes in strength.
            THEORETICAL_MAX_UPLIFT = 10.0
            normalized_map = self.cached_tectonic_uplift_map / THEORETICAL_MAX_UPLIFT
            return color_maps.get_elevation_color_array(np.clip(normalized_map, 0.0, 1.0))

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

    def _update(self):
        """Update application state. Runs the performance test if active."""
        self._update_tooltip()

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
        try:
            # Sort by cumulative time spent in the function
            # Load the stats from the file that was just saved. This is more robust
            # than passing the profiler object directly and avoids potential TypeErrors.
            ps = pstats.Stats(filepath, stream=s).sort_stats('cumulative')
            ps.print_stats(log_count)
            self.logger.info(f"--- Top {log_count} Profiling Results ---\n{s.getvalue()}")
        except (TypeError, EOFError) as e:
            self.logger.warning(f"Could not read profiling data from {filepath}. "
                              f"The file might be empty or corrupted. Reason: {e}")

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

class MainMenuState:
    """The main menu state, acting as the application's central hub."""

    def __init__(self, app):
        self.app = app
        self.logger = app.logger
        self.screen = app.screen
        self.ui_manager = pygame_gui.UIManager((app.screen_width, app.screen_height))
        
        self.next_state = None
        self._setup_ui()

    def _setup_ui(self):
        """Creates the UI for the main menu."""
        # Center the buttons vertically
        button_width = 300
        button_height = 50
        button_y_start = (self.app.screen_height - (2 * button_height + UI_PADDING)) // 2
        button_x = (self.app.screen_width - button_width) // 2

        self.editor_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(button_x, button_y_start, button_width, button_height),
            text="Live World Editor",
            manager=self.ui_manager
        )

        self.browser_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(button_x, button_y_start + button_height + UI_PADDING, button_width, button_height),
            text="Browse Baked Worlds",
            manager=self.ui_manager
        )
        # The browser button is disabled for now, as the feature is not implemented yet.
        self.browser_button.disable()

    def handle_events(self, events):
        """Processes user input for the main menu."""
        for event in events:
            self.ui_manager.process_events(event)

            if event.type == pygame.QUIT:
                self.next_state = ("QUIT", None)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.next_state = ("QUIT", None)
            elif event.type == pygame_gui.UI_BUTTON_PRESSED:
                if event.ui_element == self.editor_button:
                    self.logger.info("Event: 'Live World Editor' button pressed.")
                    self.next_state = ("GOTO_STATE", "editor")

    def update(self, time_delta):
        """Update state logic. Returns a signal for the state machine."""
        self.ui_manager.update(time_delta)
        
        if self.next_state:
            signal = self.next_state
            self.next_state = None  # Reset signal
            return signal
        return None

    def draw(self, screen):
        """Renders the main menu."""
        screen.fill((20, 20, 40)) # A different background color for the menu
        self.ui_manager.draw_ui(screen)


class Application:
    """The main application class, responsible for managing states and the main loop."""

    def __init__(self):
        self._setup_logging()
        self.logger.info("Application starting.")
        self.config = self._load_config()

        global pygame, pygame_gui, WorldRenderer, Camera
        import pygame
        import pygame_gui
        from .renderer import WorldRenderer
        from .camera import Camera

        self._setup_pygame()

        # --- State Machine ---
        self.states = {
            "main_menu": MainMenuState(self),
            "editor": EditorState(self)
            # Future states like "browser" and "viewer" will be added here
        }
        self.active_state_name = "main_menu"
        self.active_state = self.states[self.active_state_name]
        self.is_running = True

    def _setup_logging(self):
        """Initializes the logging system from a config file."""
        log_config_path = 'editor/logging_config.json'
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        with open(log_config_path, 'rt') as f:
            log_config = json.load(f)
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
            self.screen = pygame.display.set_mode((0, 0), flags)
            self.screen_width, self.screen_height = self.screen.get_size()
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
        """The main application loop that drives the active state."""
        try:
            while self.is_running:
                time_delta = self.clock.tick(self.tick_rate) / 1000.0
                
                events = pygame.event.get()
                self.active_state.handle_events(events)

                signal = self.active_state.update(time_delta)
                
                # --- Handle State Transitions ---
                if signal:
                    signal_type, data = signal
                    if signal_type == "QUIT":
                        self.is_running = False
                    elif signal_type == "GOTO_STATE":
                        self.logger.info(f"Transitioning from state '{self.active_state_name}' to '{data}'...")
                        self.active_state_name = data
                        self.active_state = self.states[self.active_state_name]

                self.active_state.draw(self.screen)
                pygame.display.flip()
                
        except Exception as e:
            self.logger.critical("An unhandled exception occurred in the main loop!", exc_info=True)
        finally:
            self.logger.info("Exiting application.")
            # --- Ensure the multiprocessing pool is always cleaned up ---
            if hasattr(self.active_state, 'baking_pool') and self.active_state.baking_pool:
                self.logger.info("Closing the multiprocessing pool...")
                self.active_state.baking_pool.close()
                self.active_state.baking_pool.join()

            if hasattr(self.active_state, 'profiler') and self.active_state.profiler:
                self.active_state._report_profiling_results()
            pygame.quit()
            sys.exit()

if __name__ == '__main__':
    # CRITICAL FIX for Windows multiprocessing
    # This must be the first call in the main entry point.
    multiprocessing.freeze_support()
    
    app = Application()
    app.run()