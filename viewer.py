# FOLDER: /

# viewer.py

import pygame
import json
import os
import logging
import sys
import math

# --- Application Constants (Rule 1) ---
PAN_SPEED_PIXELS = 15
ZOOM_SPEED = 0.1
MAX_ZOOM = 2.0
MIN_ZOOM = 0.01

class Camera:
    """A simple camera for the viewer to handle pan and zoom."""
    def __init__(self, screen_width, screen_height, world_pixel_width, world_pixel_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.world_pixel_width = world_pixel_width
        self.world_pixel_height = world_pixel_height

        zoom_x = self.screen_width / self.world_pixel_width
        zoom_y = self.screen_height / self.world_pixel_height
        self.zoom = min(zoom_x, zoom_y) if min(zoom_x, zoom_y) > 0 else MIN_ZOOM

        self.x = self.world_pixel_width / 2
        self.y = self.world_pixel_height / 2

    def world_to_screen(self, world_x, world_y):
        screen_x = (world_x - self.x) * self.zoom + self.screen_width / 2
        screen_y = (world_y - self.y) * self.zoom + self.screen_height / 2
        return screen_x, screen_y

    def pan(self, dx, dy):
        # Panning speed should be independent of zoom level
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
    (This class is unchanged from Step 5)
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
        self.chunk_map = manifest_data.get("chunk_map", {}).get("terrain", {})

        self.world_pixel_width = self.dimensions_chunks[0] * self.chunk_resolution
        self.world_pixel_height = self.dimensions_chunks[1] * self.chunk_resolution
        
        self.logger.info(f"Successfully loaded world: '{self.world_name}' ({self.world_pixel_width}x{self.world_pixel_height} pixels).")

    def get_chunk_surface(self, cx: int, cy: int) -> pygame.Surface:
        coord_key = f"{cx},{cy}"
        chunk_hash = self.chunk_map.get(coord_key)
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

class ViewerApp:
    """The main application class for the baked world viewer."""
    def __init__(self, package_path: str):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

        self.logger.info("Initializing Pygame...")
        pygame.init()

        self.screen_width = 1280
        self.screen_height = 720
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Baked World Viewer")

        self.clock = pygame.time.Clock()
        self.is_running = True

        try:
            self.world = BakedWorld(package_path)
            self.camera = Camera(self.screen_width, self.screen_height, self.world.world_pixel_width, self.world.world_pixel_height)
        except FileNotFoundError:
            self.is_running = False

    def run(self):
        """The main application loop."""
        while self.is_running:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(60)

        self.logger.info("Exiting viewer.")
        pygame.quit()
        sys.exit()

    def handle_events(self):
        """Processes user input and other events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.is_running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.is_running = False
            elif event.type == pygame.MOUSEWHEEL:
                if event.y > 0:
                    self.camera.zoom_in()
                elif event.y < 0:
                    self.camera.zoom_out()

    def update(self):
        """Handles continuous input like key presses for panning."""
        keys = pygame.key.get_pressed()
        if keys[pygame.K_w]:
            self.camera.pan(0, -PAN_SPEED_PIXELS)
        if keys[pygame.K_s]:
            self.camera.pan(0, PAN_SPEED_PIXELS)
        if keys[pygame.K_a]:
            self.camera.pan(-PAN_SPEED_PIXELS, 0)
        if keys[pygame.K_d]:
            self.camera.pan(PAN_SPEED_PIXELS, 0)

    def draw(self):
        """Handles all rendering for the application."""
        self.screen.fill((10, 10, 20))

        chunk_pixel_size = self.world.chunk_resolution
        # Prevent division by zero if zoom is extremely small
        scaled_chunk_size = chunk_pixel_size * self.camera.zoom
        if scaled_chunk_size <= 0: return

        top_left_world_x = self.camera.x - (self.screen_width / 2) / self.camera.zoom
        top_left_world_y = self.camera.y - (self.screen_height / 2) / self.camera.zoom
        
        start_cx = math.floor(top_left_world_x / chunk_pixel_size)
        start_cy = math.floor(top_left_world_y / chunk_pixel_size)
        
        chunks_on_screen_x = math.ceil(self.screen_width / scaled_chunk_size) + 1
        chunks_on_screen_y = math.ceil(self.screen_height / scaled_chunk_size) + 1
        
        end_cx = start_cx + chunks_on_screen_x
        end_cy = start_cy + chunks_on_screen_y

        rendered_chunks = 0
        for cy in range(start_cy, end_cy):
            for cx in range(start_cx, end_cx):
                chunk_surface = self.world.get_chunk_surface(cx, cy)
                if chunk_surface:
                    screen_pos = self.camera.world_to_screen(cx * chunk_pixel_size, cy * chunk_pixel_size)
                    
                    # Only blit if the chunk is actually on screen
                    if screen_pos[0] < self.screen_width and screen_pos[1] < self.screen_height and \
                       screen_pos[0] + scaled_chunk_size > 0 and screen_pos[1] + scaled_chunk_size > 0:
                        
                        scaled_surface = pygame.transform.scale(chunk_surface, (math.ceil(scaled_chunk_size), math.ceil(scaled_chunk_size)))
                        self.screen.blit(scaled_surface, screen_pos)
                        rendered_chunks += 1
        
        pygame.display.set_caption(f"Baked World Viewer | Rendering {rendered_chunks} chunks | Zoom: {self.camera.zoom:.2f}")
        pygame.display.flip()

if __name__ == '__main__':
    BAKED_WORLD_PATH = "BakedWorldPackage_Optimized"
    
    if not os.path.isdir(BAKED_WORLD_PATH):
        print(f"Error: Baked world package not found at '{BAKED_WORLD_PATH}'")
        print("Please run 'python -m baker' first.")
    else:
        app = ViewerApp(package_path=BAKED_WORLD_PATH)
        app.run()