# examples/basic_viewer/camera.py

import pygame

# Import type hint to avoid circular dependency
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from world_generator.generator import WorldGenerator

class Camera:
    def __init__(self, config: dict, generator: 'WorldGenerator'):
        self.config = config
        # World dimensions are now queried directly from the generator (Rule 7)
        self.world_width = generator.world_width_cm
        self.world_height = generator.world_height_cm
        self.screen_width = config['display']['screen_width']
        self.screen_height = config['display']['screen_height']
        
        self.x = self.world_width / 2
        self.y = self.world_height / 2
        self.zoom = 1.0
        
        self.zoom_speed = config['camera']['zoom_speed']
        self.max_zoom = config['camera']['max_zoom']
        self.min_zoom = config['camera']['min_zoom']

        self.zoom_changed = True

    def world_to_screen(self, world_x, world_y):
        screen_x = (world_x - self.x) * self.zoom + self.screen_width / 2
        screen_y = (world_y - self.y) * self.zoom + self.screen_height / 2
        return int(screen_x), int(screen_y)

    def screen_to_world(self, screen_x, screen_y):
        world_x = (screen_x - self.screen_width / 2) / self.zoom + self.x
        world_y = (screen_y - self.screen_height / 2) / self.zoom + self.y
        return world_x, world_y

    def pan(self, dx, dy):
        self.x += dx / self.zoom
        self.y += dy / self.zoom
        # Clamping logic can be added here later if needed

    def zoom_in(self):
        old_zoom = self.zoom
        self.zoom = min(self.max_zoom, self.zoom * (1 + self.zoom_speed))
        if self.zoom != old_zoom:
            self.zoom_changed = True

    def zoom_out(self):
        old_zoom = self.zoom
        self.zoom = max(self.min_zoom, self.zoom * (1 - self.zoom_speed))
        if self.zoom != old_zoom:
            self.zoom_changed = True