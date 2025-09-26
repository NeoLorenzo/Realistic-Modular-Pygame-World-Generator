# editor/main.py

import sys
import os
import json
import logging
import logging.config
import time
import cProfile
import pstats
import io
from datetime import datetime
import numpy as np
from scipy.ndimage import zoom
from PIL import Image
import pygame
import math
import multiprocessing

from world_generator.generator import WorldGenerator
# Import the color_maps module to access its functions.
from world_generator import color_maps
from world_generator import tectonics
from editor.baker import bake_master_data
from editor.package_builder import chunk_master_data
from editor.worker import bake_and_chunk_worker

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

# --- Viewer Application Constants (Rule 1) ---
PAN_SPEED_PIXELS = 15
ZOOM_SPEED = 0.1
MAX_ZOOM = 2.0
MIN_ZOOM = 0.01

class EditorState:
    """The main application state for the live editor."""

    def bake_and_chunk_worker(generator_settings: dict, master_data_path: str, logger: logging.Logger):
        """
        A worker function that first bakes the master data and then chunks it.
        This is designed to be run in a separate process to avoid freezing the UI.
        """
        try:
            logger.info("WORKER: Starting master bake...")
            bake_master_data(generator_settings, logger)
            logger.info("WORKER: Master bake complete. Starting chunking...")
            chunk_master_data(master_data_path, logger)
            logger.info("WORKER: Chunking complete.")
            return True
        except Exception as e:
            logger.critical(f"WORKER: An exception occurred during bake/chunk process: {e}", exc_info=True)
            return False

    def __init__(self, app):
        # --- Core Application References ---
        self.app = app
        self.logger = app.logger
        self.config = app.config
        self.screen = app.screen
        self.clock = app.clock
        self.tick_rate = app.tick_rate
        
        self.logger.info("EditorState starting.")

        # --- 1. ESTABLISH THE SINGLE SOURCE OF TRUTH ---
        self.master_data_path = "baked_worlds/MyWorld_Seed42" # Hardcoded for now
        generation_config_path = os.path.join(self.master_data_path, "generation_config.json")
        
        world_gen_params = {}
        if os.path.isfile(generation_config_path):
            self.logger.info(f"Found generation config. Loading settings from '{generation_config_path}'.")
            with open(generation_config_path, 'r') as f:
                world_gen_params = json.load(f)
        else:
            self.logger.warning(f"No generation config found at '{generation_config_path}'. Using default settings.")
            world_gen_params = self.config.get('world_generation_parameters', {})

        # --- 2. INITIALIZE CORE COMPONENTS USING THE "TRUTH" ---
        self.world_generator = WorldGenerator(config=world_gen_params, logger=self.logger)
        self.camera = Camera(self.config, self.world_generator)
        self.world_renderer = WorldRenderer(logger=self.logger)

        # --- 3. INITIALIZE STATE VARIABLES ---
        self.view_modes = ["terrain", "temperature", "humidity", "elevation", "tectonic", "soil_depth"]
        self.current_view_mode_index = 0
        self.view_mode = self.view_modes[self.current_view_mode_index]
        self.frame_count = 0
        self.live_preview_surface = None
        self.terrain_maps_dirty = True # Start dirty to trigger initial preview generation
        self.go_to_menu = False

        # --- 4. LOAD MASTER DATA (if available) ---
        self.master_data = {}
        self._load_master_data() # This will populate self.master_data

        # --- 5. SETUP UI AND OTHER COMPONENTS ---
        self.ui_manager = None
        self.ui_panel = None
        self.temp_slider = None
        self.roughness_slider = None
        self.lapse_rate_slider = None
        self.continent_size_slider = None
        self.terrain_amplitude_slider = None
        self.polar_drop_slider = None
        self.mountain_smoothness_slider = None
        self.mountain_width_slider = None
        self.tectonic_strength_slider = None
        self.world_width_input = None
        self.world_height_input = None
        self.apply_size_button = None
        self.km_size_label = None
        self.bake_button = None
        self.size_estimate_label = None
        self.calculate_size_button = None
        self.tooltip = None
        self.last_mouse_world_pos = (None, None)
        self.world_edge_dropdown = None
        self.decrease_plates_button = None
        self.plate_count_label = None
        self.increase_plates_button = None
        self.main_menu_button = None

        # Pre-compute color LUTs
        self.temp_lut = color_maps.create_temperature_lut()
        self.humidity_lut = color_maps.create_humidity_lut()
        self.biome_lut = color_maps.create_biome_color_lut()

        # --- Package Builder State ---
        self.is_packaging = False
        self.packaging_pool = None
        self.packaging_result = None

        # Actually create the UI
        self._setup_ui()
        self._create_reverse_color_map()

        # Profiling Setup
        self.profiler = None
        if self.config.get('profiling', {}).get('enabled', False):
            self.profiler = cProfile.Profile()
            self.logger.info("Profiling is ENABLED.")
        else:
            self.logger.info("Profiling is DISABLED.")

        # --- CORRECTED ORDER: DEFINE THESE BEFORE THEY ARE USED ---
        # Performance Test State
        self.perf_test_config = self.config.get('performance_test', {})
        self.is_perf_test_running = self.perf_test_config.get('enabled', False)
        
        # Benchmark Mode State
        self.benchmark_config = self.config.get('benchmark', {})
        self.is_benchmark_running = self.benchmark_config.get('enabled', False)

        # Live Editor Benchmark State
        self.live_editor_benchmark_config = self.config.get('live_editor_benchmark', {})
        self.is_live_editor_benchmark_running = self.live_editor_benchmark_config.get('enabled', False)
        
        self._perf_test_path = []
        self._perf_test_current_action = None
        self._perf_test_action_frame_count = 0
        if self.is_perf_test_running:
            self.logger.info("Performance test mode is ENABLED. User input will be ignored.")
            for step in self.perf_test_config.get('path', []):
                for _ in range(step['frames']):
                    self._perf_test_path.append(step)

        self.is_running = True

        # --- Handle Special Run Modes ---
        if self.is_live_editor_benchmark_running:
            self.logger.warning("Live editor benchmark is not supported in the new architecture yet.")
        elif self.is_benchmark_running:
            self.logger.warning("Benchmark mode is not supported in the new architecture yet.")
            self.is_packaging = False
            self.packaging_pool = None
            self.packaging_result = None
        else:
            self.logger.info("Entering interactive editor mode.")
            if self.profiler:
                self.profiler.enable()
        
        # --- Frame the initial world view ---
        self._frame_world_in_camera()

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

        # --- Bake Button ---
        # This button is now a placeholder for triggering the external chunker script.
        self.bake_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(UI_PADDING, current_y, element_width, UI_BUTTON_HEIGHT),
            text="Package World for Distribution",
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

    def _load_master_data(self):
        """Loads all .npy files from the master_data directory."""
        self.logger.info(f"Loading master data from '{self.master_data_path}'...")
        data_dir = os.path.join(self.master_data_path, "master_data")
        if not os.path.isdir(data_dir):
            self.logger.error(f"Master data directory not found at '{data_dir}'. Cannot load.")
            return

        for filename in os.listdir(data_dir):
            if filename.endswith(".npy"):
                name = filename.split('.')[0]
                try:
                    self.master_data[name] = np.load(os.path.join(data_dir, filename))
                    self.logger.info(f"  - Loaded {name}.npy (shape: {self.master_data[name].shape})")
                except Exception as e:
                    self.logger.error(f"Failed to load {filename}: {e}")
        
        # Trigger a redraw
        self.terrain_maps_dirty = True # Re-using this flag is fine

    def _load_master_data(self):
        """Loads all .npy files from the master_data directory."""
        self.logger.info(f"Loading master data from '{self.master_data_path}'...")
        data_dir = os.path.join(self.master_data_path, "master_data")
        if not os.path.isdir(data_dir):
            self.logger.error(f"Master data directory not found at '{data_dir}'. Cannot load.")
            return

        for filename in os.listdir(data_dir):
            if filename.endswith(".npy"):
                name = filename.split('.')[0]
                try:
                    self.master_data[name] = np.load(os.path.join(data_dir, filename))
                    self.logger.info(f"  - Loaded {name}.npy (shape: {self.master_data[name].shape})")
                except Exception as e:
                    self.logger.error(f"Failed to load {filename}: {e}")
        
        # Trigger a redraw
        self.terrain_maps_dirty = True # Re-using this flag is fine

    def _frame_world_in_camera(self):
        """Calculates the correct zoom and position to fit the entire world in the viewport."""
        self.logger.info("Framing world in camera...")
        
        # The drawable area is the screen minus the UI panel
        drawable_width = self.app.screen_width - UI_PANEL_WIDTH
        drawable_height = self.app.screen_height
        
        # Prevent division by zero if world size is invalid
        if self.world_generator.world_width_cm == 0 or self.world_generator.world_height_cm == 0:
            return

        zoom_x = drawable_width / self.world_generator.world_width_cm
        zoom_y = drawable_height / self.world_generator.world_height_cm
        
        self.camera.zoom = min(zoom_x, zoom_y)
        self.camera.x = self.world_generator.world_width_cm / 2
        self.camera.y = self.world_generator.world_height_cm / 2
        
        self.logger.info(f"Camera framed. Zoom set to {self.camera.zoom:.6f}.")

    def handle_events(self, events):
        """Processes user input and other events for this state."""
        for event in events:
            # Pass events to the UI Manager first
            self.ui_manager.process_events(event)

            if event.type == pygame.QUIT:
                self.is_running = False
            # Allow manual exit via ESC key even during a performance test
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.logger.info("Event: ESC key pressed. Returning to main menu.")
                self.go_to_menu = True

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
                    # --- OPTIMIZATION: Trigger a fast preview refresh, not a full bake ---
                    self.terrain_maps_dirty = True
            
            if event.type == pygame_gui.UI_BUTTON_PRESSED:
                if event.ui_element == self.apply_size_button:
                    self._apply_world_size_changes()
                elif event.ui_element == self.bake_button:
                    if self.is_packaging:
                        self.logger.warning("Packaging is already in progress.")
                        return
                    
                    self.logger.info("Starting background bake and packaging process...")
                    self.is_packaging = True
                    self.bake_button.set_text("Baking & Packaging...")
                    self.bake_button.disable() # Prevent double-clicking

                    # We only need one worker for this single task
                    self.packaging_pool = multiprocessing.Pool(processes=1)
                    # The worker no longer needs the old, hardcoded path.
                    self.packaging_result = self.packaging_pool.apply_async(
                        bake_and_chunk_worker,
                        (self.world_generator.settings, self.logger)
                    )
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
                    # --- OPTIMIZATION: Trigger a fast preview refresh, not a full bake ---
                    self.terrain_maps_dirty = True

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
                    # The underlying master data is unchanged, but we need to re-colorize.
                    # Set the one and only dirty flag to trigger a preview regeneration.
                    self.terrain_maps_dirty = True
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

        # --- Check for packaging completion ---
        if self.is_packaging and self.packaging_result and self.packaging_result.ready():
            self.logger.info("Packaging process has completed.")
            # Clean up the pool
            self.packaging_pool.close()
            self.packaging_pool.join()
            
            # Reset state
            self.is_packaging = False
            self.packaging_pool = None
            self.packaging_result = None
            
            # Update UI
            self.bake_button.enable()
            self.bake_button.set_text("Packaging Complete!")

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
        if self.terrain_maps_dirty: # Simplified dirty flag
            self.logger.info(f"Change detected. Regenerating preview data for view mode: '{self.view_mode}'...")
            color_array = self._generate_preview_color_array()
            self.live_preview_surface = self.world_renderer.create_surface_from_color_array(color_array)
            self.terrain_maps_dirty = False
            self.logger.info("Live preview regeneration complete.")

        self.world_renderer.draw_live_preview(screen, self.camera, self.live_preview_surface)

        self.ui_manager.draw_ui(screen)

    def _apply_world_size_changes(self):
        """
        Parses text inputs for world size, updates the generator's state,
        and triggers a fast live preview refresh.
        """
        try:
            new_width = int(self.world_width_input.get_text())
            new_height = int(self.world_height_input.get_text())

            if new_width <= 0 or new_height <= 0:
                self.logger.warning("World dimensions must be positive integers.")
                return

            self.logger.info(f"Applying new world size: {new_width}x{new_height} chunks.")

            # 1. Update the settings in the current generator instance.
            self.world_generator.settings['world_width_chunks'] = new_width
            self.world_generator.settings['world_height_chunks'] = new_height
            
            # We also need to update the generator's internal cm dimensions
            chunk_size_cm = self.world_generator.settings['chunk_size_cm']
            self.world_generator.world_width_cm = new_width * chunk_size_cm
            self.world_generator.world_height_cm = new_height * chunk_size_cm
            
            # 2. Re-initialize the Camera, which depends on the new dimensions.
            self.camera = Camera(self.config, self.world_generator)
            
            # 3. Frame the new world size in the camera view.
            self._frame_world_in_camera()
            
            # 4. Update the UI label.
            self._update_km_size_label()

            # 5. Trigger a fast preview refresh.
            self.terrain_maps_dirty = True

        except ValueError:
            self.logger.error("Invalid world size input. Please enter integers only.")
            # Reset the text to the current valid values
            self.world_width_input.set_text(str(self.world_generator.settings['world_width_chunks']))
            self.world_height_input.set_text(str(self.world_generator.settings['world_height_chunks']))

    def _update_world_parameter(self, name: str, value):
        """A centralized method to update a world parameter."""
        settings = self.world_generator.settings
        settings[name] = value

        # Handle special cases that require more than just a value change
        if name == 'terrain_base_feature_scale_km':
            from world_generator.config import CM_PER_KM
            settings['base_noise_scale'] = value * CM_PER_KM
        elif name == 'mountain_uplift_feature_scale_km':
            from world_generator.config import CM_PER_KM
            settings['mountain_uplift_noise_scale'] = value * CM_PER_KM
        elif name == 'num_tectonic_plates':
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
        Generates all world data directly at preview resolution for fast iteration.
        This is the core of the live editor's performance optimization.
        """
        self.logger.info("Generating live preview data at preview resolution...")
        
        # 1. Create the coordinate grid AT PREVIEW RESOLUTION.
        # This is the key optimization. We ask the generator for the exact
        # number of points we need, not the millions for the full bake.
        wx_grid, wy_grid = self.world_generator.get_coordinate_grid(
            world_x_cm=0,
            world_y_cm=0,
            width_cm=self.world_generator.world_width_cm,
            height_cm=self.world_generator.world_height_cm,
            resolution_w=PREVIEW_RESOLUTION_WIDTH,
            resolution_h=PREVIEW_RESOLUTION_HEIGHT
        )

        # 2. Run the entire data generation pipeline on the low-resolution grid.
        # The logic is identical to the master baker, ensuring fidelity.
        
        # Tectonics
        _, dist1, dist2 = self.world_generator.get_tectonic_data(wx_grid, wy_grid, self.world_generator.world_width_cm, self.world_generator.world_height_cm, self.world_generator.settings['num_tectonic_plates'], self.world_generator.settings['seed'])
        radius_cm = self.world_generator.settings['mountain_influence_radius_km'] * 100000.0
        influence_map = tectonics.calculate_influence_map(dist1, dist2, radius_cm)
        uplift_map = self.world_generator.get_tectonic_uplift(wx_grid, wy_grid, influence_map)

        # Terrain
        bedrock_map = self.world_generator._get_bedrock_elevation(wx_grid, wy_grid, tectonic_uplift_map=uplift_map)
        slope_map = self.world_generator._get_slope(bedrock_map)
        soil_depth_map_raw = self.world_generator._get_soil_depth(slope_map)
        water_level = self.world_generator.settings['terrain_levels']['water']
        land_mask = bedrock_map >= water_level
        soil_depth_map = np.copy(soil_depth_map_raw)
        soil_depth_map[~land_mask] = 0.0
        final_elevation_map = np.clip(bedrock_map + soil_depth_map, 0.0, 1.0)

        # Climate
        climate_noise_map = self.world_generator._generate_base_noise(wx_grid, wy_grid, seed_offset=self.world_generator.settings['temp_seed_offset'], scale=self.world_generator.settings['climate_noise_scale'])
        temperature_map = self.world_generator.get_temperature(wx_grid, wy_grid, final_elevation_map, base_noise=climate_noise_map)
        coastal_factor_map = self.world_generator.calculate_coastal_factor_map(final_elevation_map, wx_grid.shape)
        shadow_factor_map = self.world_generator.calculate_shadow_factor_map(final_elevation_map, wx_grid.shape)
        humidity_map = self.world_generator.get_humidity(wx_grid, wy_grid, final_elevation_map, temperature_map, coastal_factor_map, shadow_factor_map)

        self.logger.info("Live preview data generation complete.")

        # 3. Colorize the preview-resolution data.
        if self.view_mode == "terrain":
            biome_map = color_maps.calculate_biome_map(final_elevation_map, temperature_map, humidity_map, soil_depth_map)
            return color_maps.get_terrain_color_array(biome_map, self.biome_lut)
        elif self.view_mode == "temperature":
            return color_maps.get_temperature_color_array(temperature_map, self.temp_lut)
        elif self.view_mode == "humidity":
            return color_maps.get_humidity_color_array(humidity_map, self.humidity_lut)
        elif self.view_mode == "elevation":
            return color_maps.get_elevation_color_array(final_elevation_map)
        elif self.view_mode == "soil_depth":
            max_depth = self.world_generator.settings['max_soil_depth_units']
            normalized_soil = soil_depth_map / max_depth if max_depth > 0 else np.zeros_like(soil_depth_map)
            return color_maps.get_elevation_color_array(normalized_soil)
        else: # tectonic
            THEORETICAL_MAX_UPLIFT = 10.0
            normalized_map = uplift_map / THEORETICAL_MAX_UPLIFT
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
        if self.live_preview_surface:
            # The old live data arrays no longer exist.
            # For now, we can only get the terrain type.
            # A future step will be to sample from the downsampled master data.
            surface_w, surface_h = self.live_preview_surface.get_size()

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
            # --- OPTIMIZATION: Trigger a fast preview refresh, not a full bake ---
            self.terrain_maps_dirty = True

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
                elif event.ui_element == self.browser_button:
                    self.logger.info("Event: 'Browse Baked Worlds' button pressed.")
                    self.next_state = ("GOTO_STATE", "browser")

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
            "editor": EditorState(self),
            "browser": WorldBrowserState(self)
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
                        # Check if the data is a tuple (state_name, payload)
                        if isinstance(data, tuple):
                            state_name, payload = data
                            self.logger.info(f"Transitioning to new state '{state_name}' with data...")
                            if state_name == "viewer":
                                # Create the ViewerState on-the-fly with the package path
                                self.active_state = ViewerState(self, package_path=payload)
                                self.active_state_name = state_name
                        else: # It's just a string (state_name)
                            state_name = data
                            self.logger.info(f"Transitioning from state '{self.active_state_name}' to '{state_name}'...")
                            self.active_state_name = state_name
                            self.active_state = self.states[self.active_state_name]

                self.active_state.draw(self.screen)
                pygame.display.flip()
                
        except Exception as e:
            self.logger.critical("An unhandled exception occurred in the main loop!", exc_info=True)
        finally:
            self.logger.info("Exiting application.")
            if hasattr(self.active_state, 'profiler') and self.active_state.profiler:
                self.active_state._report_profiling_results()
            pygame.quit()
            sys.exit()

class WorldBrowserState:
    """
    A state for browsing, selecting, and loading baked world packages.
    """
    def __init__(self, app):
        self.app = app
        self.logger = app.logger
        self.ui_manager = pygame_gui.UIManager((app.screen_width, app.screen_height))
        
        self.next_state = None
        self.baked_worlds = {} # Dict to store name -> path mapping
        self.selected_world_path = None

        self._scan_for_worlds()
        self._setup_ui()

    def _scan_for_worlds(self):
        """Scans the 'baked_worlds' directory for valid packages."""
        self.logger.info("Scanning for baked world packages...")
        browse_dir = "baked_worlds"
        if not os.path.isdir(browse_dir):
            self.logger.warning(f"'{browse_dir}' directory not found. Creating it.")
            os.makedirs(browse_dir)
            return

        for item_name in os.listdir(browse_dir):
            item_path = os.path.join(browse_dir, item_name)
            manifest_path = os.path.join(item_path, "manifest.json")
            if os.path.isdir(item_path) and os.path.isfile(manifest_path):
                try:
                    with open(manifest_path, 'r') as f:
                        manifest = json.load(f)
                        world_name = manifest.get("world_name", item_name)
                        self.baked_worlds[world_name] = item_path
                        self.logger.info(f"Found valid package: '{world_name}' at {item_path}")
                except (json.JSONDecodeError, KeyError):
                    self.logger.warning(f"Could not parse manifest for '{item_name}'. Skipping.")
        
        if not self.baked_worlds:
            self.logger.info("No valid baked world packages found.")

    def _setup_ui(self):
        """Creates the UI for the browser."""
        self.back_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(10, 10, 200, 40),
            text="Back to Main Menu",
            manager=self.ui_manager
        )

        self.refresh_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(220, 10, 150, 40),
            text="Refresh List",
            manager=self.ui_manager
        )

        # --- Create the Selection List ---
        list_width = 400
        list_height = self.app.screen_height - 150
        list_x = (self.app.screen_width - list_width) // 2
        self.world_list = pygame_gui.elements.UISelectionList(
            relative_rect=pygame.Rect(list_x, 60, list_width, list_height),
            item_list=list(self.baked_worlds.keys()), # Populate with world names
            manager=self.ui_manager
        )

        # --- Create the Load Button (initially disabled) ---
        button_width = 200
        button_x = (self.app.screen_width - button_width) // 2
        self.load_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(button_x, self.app.screen_height - 80, button_width, 50),
            text="Load Selected World",
            manager=self.ui_manager
        )
        self.load_button.disable()

    def _refresh_world_list(self):
        """Re-scans the directory and updates the UI selection list."""
        self.logger.info("Refreshing world list...")
        
        # Clear the old data
        self.baked_worlds.clear()
        self.selected_world_path = None
        
        # Re-run the scan to populate self.baked_worlds
        self._scan_for_worlds()
        
        # Update the UI element with the new list of names
        self.world_list.set_item_list(list(self.baked_worlds.keys()))
        
        # Ensure the load button is disabled as the selection is now cleared
        self.load_button.disable()

    def handle_events(self, events):
        """Processes user input for the browser."""
        for event in events:
            self.ui_manager.process_events(event)

            if event.type == pygame.QUIT:
                self.next_state = ("QUIT", None)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.next_state = ("GOTO_STATE", "main_menu")
            elif event.type == pygame_gui.UI_BUTTON_PRESSED:
                if event.ui_element == self.back_button:
                    self.next_state = ("GOTO_STATE", "main_menu")
                elif event.ui_element == self.refresh_button:
                    self._refresh_world_list()
                elif event.ui_element == self.load_button:
                    if self.selected_world_path:
                        self.logger.info(f"Load button pressed for world: {self.selected_world_path}")
                        # Signal to go to the viewer, passing the selected path as data.
                        self.next_state = ("GOTO_STATE", ("viewer", self.selected_world_path))
            
            # --- Handle list selection events ---
            elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
                if event.ui_element == self.world_list:
                    selected_world_name = event.text
                    self.selected_world_path = self.baked_worlds.get(selected_world_name)
                    if self.selected_world_path:
                        self.logger.info(f"Selected world: '{selected_world_name}'")
                        self.load_button.enable()
                    else:
                        self.load_button.disable()

    def update(self, time_delta):
        """Update state logic. Returns a signal for the state machine."""
        self.ui_manager.update(time_delta)
        
        if self.next_state:
            signal = self.next_state
            self.next_state = None
            return signal
        return None

    def draw(self, screen):
        """Renders the browser."""
        screen.fill((40, 20, 20)) # A different background color for the browser
        self.ui_manager.draw_ui(screen)

class ViewerCamera:
    """A simple camera for the viewer to handle pan and zoom."""
    def __init__(self, screen_width, screen_height, world_pixel_width, world_pixel_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.world_pixel_width = world_pixel_width
        self.world_pixel_height = world_pixel_height

        zoom_x = self.screen_width / self.world_pixel_width if self.world_pixel_width > 0 else 1
        zoom_y = self.screen_height / self.world_pixel_height if self.world_pixel_height > 0 else 1
        self.zoom = min(zoom_x, zoom_y) if min(zoom_x, zoom_y) > 0 else MIN_ZOOM

        self.x = self.world_pixel_width / 2
        self.y = self.world_pixel_height / 2

    def world_to_screen(self, world_x, world_y):
        screen_x = (world_x - self.x) * self.zoom + self.screen_width / 2
        screen_y = (world_y - self.y) * self.zoom + self.screen_height / 2
        return screen_x, screen_y

    def pan(self, dx, dy):
        if self.zoom > 0:
            self.x += dx / self.zoom
            self.y += dy / self.zoom

    def zoom_in(self):
        self.zoom = min(MAX_ZOOM, self.zoom * (1 + ZOOM_SPEED))

    def zoom_out(self):
        self.zoom = max(MIN_ZOOM, self.zoom * (1 - ZOOM_SPEED))

class BakedWorld:
    """
    Represents a loaded Baked World Package.
    Handles loading the manifest and on-demand loading/caching of chunk images.
    """
    def __init__(self, package_path: str):
        self.package_path = package_path
        self.chunks_path = os.path.join(self.package_path, "chunks")
        self.manifest_path = os.path.join(self.package_path, "manifest.json")
        self.logger = logging.getLogger(__name__)
        self.chunk_cache = {}

        if not os.path.exists(self.manifest_path):
            raise FileNotFoundError(f"Could not find manifest.json in '{package_path}'")

        with open(self.manifest_path, 'r') as f:
            manifest_data = json.load(f)

        self.world_name = manifest_data.get("world_name", "Unnamed World")
        self.dimensions_chunks = tuple(manifest_data.get("world_dimensions_chunks", (0, 0)))
        self.chunk_resolution = manifest_data.get("chunk_resolution_pixels", 100)
        self.chunk_map = manifest_data.get("chunk_map", {}) # Load all view maps

        self.world_pixel_width = self.dimensions_chunks[0] * self.chunk_resolution
        self.world_pixel_height = self.dimensions_chunks[1] * self.chunk_resolution
        
        self.logger.info(f"Successfully loaded world: '{self.world_name}' ({self.world_pixel_width}x{self.world_pixel_height} pixels).")

    def get_chunk_surface(self, cx: int, cy: int, view_mode: str) -> pygame.Surface:
        """
        Retrieves a chunk's pygame.Surface for a specific view mode.
        Handles on-demand loading from disk and caching.
        """
        view_chunk_map = self.chunk_map.get(view_mode)
        if not view_chunk_map:
            return None # This view mode doesn't exist

        coord_key = f"{cx},{cy}"
        chunk_hash = view_chunk_map.get(coord_key)
        if not chunk_hash:
            return None

        if chunk_hash in self.chunk_cache:
            return self.chunk_cache[chunk_hash]

        try:
            filename = f"{chunk_hash}.png"
            filepath = os.path.join(self.chunks_path, filename)
            surface = pygame.image.load(filepath).convert()
            self.chunk_cache[chunk_hash] = surface
            return surface
        except pygame.error:
            self.logger.error(f"Failed to load chunk image for hash '{chunk_hash}' at '{filepath}'")
            return None
        
class ViewerState:
    """
    A state for viewing and exploring a single baked world package.
    """
    def __init__(self, app, package_path: str):
        self.app = app
        self.logger = app.logger
        self.screen = app.screen
        self.ui_manager = pygame_gui.UIManager((app.screen_width, app.screen_height))
        
        self.next_state = None
        
        try:
            self.world = BakedWorld(package_path)
            self.camera = ViewerCamera(app.screen_width, app.screen_height, self.world.world_pixel_width, self.world.world_pixel_height)
            
            # --- View Mode State ---
            self.view_modes = list(self.world.chunk_map.keys())
            self.current_view_mode_index = 0
            if not self.view_modes:
                self.logger.warning("Baked world has no viewable maps in its manifest.")
                # Default to a dummy view to prevent crashes
                self.view_modes = ["unknown"]

            self._setup_ui()
        except FileNotFoundError:
            self.logger.critical(f"Failed to load world at '{package_path}'. Returning to browser.")
            self.next_state = ("GOTO_STATE", "browser")

    def _setup_ui(self):
        """Creates the UI for the viewer (e.g., a back button)."""
        self.back_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(10, 10, 200, 40),
            text="Back to World Browser",
            manager=self.ui_manager
        )

    def handle_events(self, events):
        """Processes user input for the viewer."""
        for event in events:
            self.ui_manager.process_events(event)

            if event.type == pygame.QUIT:
                self.next_state = ("QUIT", None)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.next_state = ("GOTO_STATE", "browser")
            elif event.type == pygame.MOUSEWHEEL:
                if event.y > 0: self.camera.zoom_in()
                elif event.y < 0: self.camera.zoom_out()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_v:
                self.current_view_mode_index = (self.current_view_mode_index + 1) % len(self.view_modes)
                self.logger.info(f"Switched viewer to '{self.view_modes[self.current_view_mode_index]}' mode.")
            elif event.type == pygame_gui.UI_BUTTON_PRESSED:
                if event.ui_element == self.back_button:
                    self.next_state = ("GOTO_STATE", "browser")

    def update(self, time_delta):
        """Handles continuous input and returns signals."""
        self.ui_manager.update(time_delta)
        
        keys = pygame.key.get_pressed()
        if keys[pygame.K_w]: self.camera.pan(0, -PAN_SPEED_PIXELS)
        if keys[pygame.K_s]: self.camera.pan(0, PAN_SPEED_PIXELS)
        if keys[pygame.K_a]: self.camera.pan(-PAN_SPEED_PIXELS, 0)
        if keys[pygame.K_d]: self.camera.pan(PAN_SPEED_PIXELS, 0)
        
        if self.next_state:
            signal = self.next_state
            self.next_state = None
            return signal
        return None

    def draw(self, screen):
        """Renders the baked world."""
        screen.fill((10, 10, 20))

        chunk_pixel_size = self.world.chunk_resolution
        scaled_chunk_size = chunk_pixel_size * self.camera.zoom
        if scaled_chunk_size <= 0: return

        # --- CRITICAL FIX: Use self.app for screen dimensions ---
        top_left_world_x = self.camera.x - (self.app.screen_width / 2) / self.camera.zoom
        top_left_world_y = self.camera.y - (self.app.screen_height / 2) / self.camera.zoom
        
        start_cx = math.floor(top_left_world_x / chunk_pixel_size)
        start_cy = math.floor(top_left_world_y / chunk_pixel_size)
        
        chunks_on_screen_x = math.ceil(self.app.screen_width / scaled_chunk_size) + 1
        chunks_on_screen_y = math.ceil(self.app.screen_height / scaled_chunk_size) + 1
        
        end_cx = start_cx + chunks_on_screen_x
        end_cy = start_cy + chunks_on_screen_y

        current_view = self.view_modes[self.current_view_mode_index]
        rendered_chunks = 0
        for cy in range(start_cy, end_cy):
            for cx in range(start_cx, end_cx):
                chunk_surface = self.world.get_chunk_surface(cx, cy, current_view)
                if chunk_surface:
                    screen_pos = self.camera.world_to_screen(cx * chunk_pixel_size, cy * chunk_pixel_size)
                    if screen_pos[0] < self.app.screen_width and screen_pos[1] < self.app.screen_height and \
                       screen_pos[0] + scaled_chunk_size > 0 and screen_pos[1] + scaled_chunk_size > 0:
                        scaled_surface = pygame.transform.scale(chunk_surface, (math.ceil(scaled_chunk_size), math.ceil(scaled_chunk_size)))
                        screen.blit(scaled_surface, screen_pos)
                        rendered_chunks += 1
        
        # Update caption to show current view mode
        caption = (f"Baked World Viewer | View: {current_view.title()} | "
                   f"Rendering {rendered_chunks} chunks | Zoom: {self.camera.zoom:.2f}")
        pygame.display.set_caption(caption)

        self.ui_manager.draw_ui(screen)

if __name__ == '__main__':
    app = Application()
    app.run()