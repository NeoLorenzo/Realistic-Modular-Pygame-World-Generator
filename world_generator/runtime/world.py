# world_generator/world.py

"""
================================================================================
WORLD RUNTIME
================================================================================
This module provides the user-facing `World` class, which is the primary
interface for interacting with a baked world package. It encapsulates all
runtime logic, including chunk rendering, time management, and the day/night
cycle, into a single, easy-to-use object.

This file is intended to be copied into the final baked package.
================================================================================
"""
import os
import json
import math
import logging
from typing import Protocol

# This module requires Pygame for rendering, as it is the runtime component.
import pygame

# Import the other runtime components that will be packaged alongside this one.
from .clock import GameClock
from .day_night_cycle import DayNightCycle

class Camera(Protocol):
    """
    A protocol defining the interface the World's renderer expects for a camera.
    This allows users to use their own camera class as long as it provides
    these attributes and methods, adhering to the Dependency Inversion Principle.
    """
    x: float
    y: float
    zoom: float
    screen_width: int
    screen_height: int

    def world_to_screen(self, world_x: float, world_y: float) -> tuple[float, float]: ...
    def screen_to_world(self, screen_x: float, screen_y: float) -> tuple[float, float]: ...

class World:
    """
    The main runtime class for a baked world. Handles rendering, time, and lighting.
    """
    def __init__(self, package_path: str):
        """
        Initializes the World from a baked world package.

        Args:
            package_path (str): The file path to the root of the baked world package.
        """
        self.package_path = package_path
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Initializing world from package: '{package_path}'")

        # --- 1. Load Configuration and Manifest ---
        manifest_path = os.path.join(self.package_path, "manifest.json")
        config_path = os.path.join(self.package_path, "generation_config.json")

        if not os.path.exists(manifest_path) or not os.path.exists(config_path):
            raise FileNotFoundError(
                f"Could not find 'manifest.json' or 'generation_config.json' in '{package_path}'"
            )

        with open(manifest_path, 'r') as f:
            self.manifest = json.load(f)
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        # --- 2. Initialize Core Components (Rule 7 - Composition) ---
        self.clock = GameClock(self.config)
        self.day_night_cycle = DayNightCycle(self.clock, self.config)

        # --- 3. Set World Properties ---
        self.world_name = self.manifest.get("world_name", "Unnamed World")
        self.dimensions_chunks = tuple(self.manifest.get("world_dimensions_chunks", (0, 0)))
        self.chunk_resolution = self.manifest.get("chunk_resolution_pixels", 100)
        self.chunk_map = self.manifest.get("chunk_map", {})
        
        self.world_pixel_width = self.dimensions_chunks[0] * self.chunk_resolution
        self.world_pixel_height = self.dimensions_chunks[1] * self.chunk_resolution

        # --- 4. Setup Rendering Cache and State ---
        self.chunks_path = os.path.join(self.package_path, "chunks")
        self._chunk_cache = {}
        self._overlay_surface = None # To be created on-demand

        # --- 5. View Mode State ---
        self.view_modes = list(self.chunk_map.keys())
        self.current_view_mode_index = 0
        if not self.view_modes:
            self.logger.warning("Baked world has no viewable maps in its manifest.")
            self.view_modes = ["terrain"] # Default to terrain to prevent crashes
        
        self.logger.info(f"World '{self.world_name}' loaded successfully.")

    def update(self, real_delta_time: float):
        """
        Updates the world's internal state. Should be called once per frame.

        Args:
            real_delta_time (float): The real-world time elapsed since the last frame, in seconds.
        """
        self.clock.update(real_delta_time)
        self.day_night_cycle.update()

    def draw(self, screen: pygame.Surface, camera: Camera):
        """
        Renders the world, including the day/night cycle overlay, to the screen.

        Args:
            screen (pygame.Surface): The main display surface to draw on.
            camera (Camera): A camera object that conforms to the Camera protocol.
        """
        # --- 1. Draw the World Chunks ---
        self._draw_world_chunks(screen, camera)

        # --- 2. Draw the Day/Night Lighting Overlay ---
        self._draw_lighting_overlay(screen)

    def _get_chunk_surface(self, cx: int, cy: int) -> pygame.Surface | None:
        """Retrieves a chunk's pygame.Surface, loading and caching it if necessary."""
        view_mode = self.view_modes[self.current_view_mode_index]
        view_chunk_map = self.chunk_map.get(view_mode)
        if not view_chunk_map:
            return None

        coord_key = f"{cx},{cy}"
        chunk_hash = view_chunk_map.get(coord_key)
        if not chunk_hash:
            return None

        # Return from cache if available
        if chunk_hash in self._chunk_cache:
            return self._chunk_cache[chunk_hash]

        # Otherwise, load from disk
        try:
            filename = f"{chunk_hash}.png"
            filepath = os.path.join(self.chunks_path, filename)
            surface = pygame.image.load(filepath).convert()
            self._chunk_cache[chunk_hash] = surface # Add to cache
            return surface
        except pygame.error:
            self.logger.error(f"Failed to load chunk image for hash '{chunk_hash}' at '{filepath}'")
            return None

    def _draw_world_chunks(self, screen: pygame.Surface, camera: Camera):
        """Calculates visible chunks and renders them to the screen."""
        scaled_chunk_size = self.chunk_resolution * camera.zoom
        if scaled_chunk_size <= 1: return # Don't render if chunks are too small

        # Determine which chunks are visible on screen
        top_left_world_x, top_left_world_y = camera.screen_to_world(0, 0)
        
        start_cx = math.floor(top_left_world_x / self.chunk_resolution)
        start_cy = math.floor(top_left_world_y / self.chunk_resolution)
        
        chunks_on_screen_x = math.ceil(camera.screen_width / scaled_chunk_size) + 1
        chunks_on_screen_y = math.ceil(camera.screen_height / scaled_chunk_size) + 1
        
        end_cx = start_cx + chunks_on_screen_x
        end_cy = start_cy + chunks_on_screen_y

        # Draw the visible chunks
        for cy in range(start_cy, end_cy):
            for cx in range(start_cx, end_cx):
                chunk_surface = self._get_chunk_surface(cx, cy)
                if chunk_surface:
                    screen_pos = camera.world_to_screen(cx * self.chunk_resolution, cy * self.chunk_resolution)
                    
                    # Scale and blit the chunk surface
                    scaled_surface = pygame.transform.scale(
                        chunk_surface,
                        (math.ceil(scaled_chunk_size), math.ceil(scaled_chunk_size))
                    )
                    screen.blit(scaled_surface, screen_pos)

    def _draw_lighting_overlay(self, screen: pygame.Surface):
        """Applies the day/night cycle effect as a semi-transparent overlay."""
        screen_size = screen.get_size()
        
        # Create or resize the overlay surface if needed
        if self._overlay_surface is None or self._overlay_surface.get_size() != screen_size:
            self._overlay_surface = pygame.Surface(screen_size, pygame.SRCALPHA)

        # The brightness value from the cycle is how much light is PRESENT.
        # The alpha value of our overlay is how much light is BLOCKED.
        # Therefore, alpha is the inverse of brightness.
        brightness = self.day_night_cycle.current_brightness
        
        # An alpha of 0 is fully transparent (full daylight).
        # An alpha of 255 is fully opaque.
        alpha = (1.0 - brightness) * 255
        
        # Fill the overlay with the current light color and calculated alpha
        color = self.day_night_cycle.current_color_tint
        self._overlay_surface.fill((color[0], color[1], color[2], alpha))
        
        # Blit the overlay onto the screen
        screen.blit(self._overlay_surface, (0, 0))

    # --- Public API for User Control ---
    def set_game_speed(self, new_scale: float):
        """
        Sets the speed of the in-game time.
        0 = paused, 1 = real-time, > 1 = fast-forward.
        """
        self.clock.set_speed(new_scale)
        self.logger.info(f"Game speed set to {new_scale}x.")

    def get_time_string(self) -> str:
        """Returns a formatted string of the current in-game date and time."""
        return self.clock.get_time_string()

    def cycle_view_mode(self):
        """Cycles through the available data maps (e.g., terrain, temperature)."""
        self.current_view_mode_index = (self.current_view_mode_index + 1) % len(self.view_modes)
        view_mode = self.view_modes[self.current_view_mode_index]
        self.logger.info(f"View mode switched to '{view_mode}'.")