# editor/templates/run_world.py

"""
================================================================================
REALISTIC MODULAR PYGAME WORLD - RUNNABLE EXAMPLE
================================================================================
This script provides a simple, runnable example of how to use the baked
world package.

To Run This Example:
- On Windows: Double-click the `run.bat` file.

This will automatically create a virtual environment, install the necessary
dependencies, and launch the application.

Controls:
- Pan: W, A, S, D
- Zoom: Mouse Wheel
- Cycle View Mode: V
- Change Game Speed: 1 (Paused), 2 (Normal), 3 (Fast), 4 (Very Fast)
- Quit: ESC or close window
================================================================================
"""
import sys
import logging
import pygame

# Import the World class from the local 'runtime' package.
from runtime.world import World

# --- Application Constants (Rule 1) ---
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
CLOCK_TICK_RATE = 60
PAN_SPEED_PIXELS = 10
ZOOM_SPEED = 0.1
MAX_ZOOM = 4.0
MIN_ZOOM = 0.02

class SimpleCamera:
    """
    A minimal camera class that fulfills the Camera protocol required by the World renderer.
    This demonstrates how a user can integrate their own camera system.
    """
    def __init__(self, screen_width, screen_height, world_pixel_width, world_pixel_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # Start zoomed out to see the whole world
        zoom_x = self.screen_width / world_pixel_width if world_pixel_width > 0 else 1
        zoom_y = self.screen_height / world_pixel_height if world_pixel_height > 0 else 1
        self.zoom = min(zoom_x, zoom_y)

        # Center the camera on the world
        self.x = world_pixel_width / 2
        self.y = world_pixel_height / 2

    def world_to_screen(self, world_x: float, world_y: float) -> tuple[float, float]:
        screen_x = (world_x - self.x) * self.zoom + self.screen_width / 2
        screen_y = (world_y - self.y) * self.zoom + self.screen_height / 2
        return screen_x, screen_y

    def screen_to_world(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        world_x = (screen_x - self.screen_width / 2) / self.zoom + self.x
        world_y = (screen_y - self.screen_height / 2) / self.zoom + self.y
        return world_x, world_y

    def pan(self, dx: float, dy: float):
        if self.zoom > 0:
            self.x += dx / self.zoom
            self.y += dy / self.zoom

    def zoom_in(self):
        self.zoom = min(MAX_ZOOM, self.zoom * (1 + ZOOM_SPEED))

    def zoom_out(self):
        self.zoom = max(MIN_ZOOM, self.zoom * (1 - ZOOM_SPEED))

def main():
    """The main application function."""
    # --- 1. Setup Logging (Rule 2) ---
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # --- 2. Initialize Pygame ---
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()
    # NEW: Initialize a font for the UI text
    try:
        ui_font = pygame.font.SysFont("monospace", 16)
    except pygame.error:
        ui_font = pygame.font.Font(None, 22) # Fallback to default font
    logging.info("Pygame initialized.")

    # --- 3. Instantiate the World ---
    # The World class is the main entry point. It loads all data and runtime logic
    # from the current directory ('.').
    try:
        world = World(package_path='.')
    except FileNotFoundError as e:
        logging.critical(f"Error loading world: {e}")
        logging.critical("Make sure this script is in the root of a baked world package.")
        pygame.quit()
        sys.exit(1)

    pygame.display.set_caption(f"World Viewer: {world.world_name}")

    # --- 4. Create the Camera ---
    camera = SimpleCamera(SCREEN_WIDTH, SCREEN_HEIGHT, world.world_pixel_width, world.world_pixel_height)

    # --- 5. Main Game Loop ---
    is_running = True
    while is_running:
        # Calculate delta time for smooth, framerate-independent updates
        time_delta = clock.tick(CLOCK_TICK_RATE) / 1000.0

        # --- Event Handling ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                is_running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    is_running = False
                if event.key == pygame.K_v:
                    world.cycle_view_mode()
                # Game speed controls
                if event.key == pygame.K_0: world.set_game_speed(0)      # Paused
                if event.key == pygame.K_1: world.set_game_speed(1)      # Real-Time (1x)
                if event.key == pygame.K_2: world.set_game_speed(60)     # Normal (60x)
                if event.key == pygame.K_3: world.set_game_speed(3600)   # Fast (3600x)
                if event.key == pygame.K_4: world.set_game_speed(86400)  # Very Fast (86400x)
            if event.type == pygame.MOUSEWHEEL:
                if event.y > 0: camera.zoom_in()
                elif event.y < 0: camera.zoom_out()

        # Continuous key presses for panning
        keys = pygame.key.get_pressed()
        if keys[pygame.K_w]: camera.pan(0, -PAN_SPEED_PIXELS)
        if keys[pygame.K_s]: camera.pan(0, PAN_SPEED_PIXELS)
        if keys[pygame.K_a]: camera.pan(-PAN_SPEED_PIXELS, 0)
        if keys[pygame.K_d]: camera.pan(PAN_SPEED_PIXELS, 0)

        # --- Update ---
        world.update(time_delta)

        # --- Draw ---
        screen.fill((0, 0, 0)) # Black background
        world.draw(screen, camera)
        
        # NEW: Draw the UI text overlay
        time_str = world.get_time_string()
        speed_str = f"Speed: {world.clock.time_scale}x"
        ui_text_str = f"{time_str} | {speed_str}"
        
        text_surface = ui_font.render(ui_text_str, True, (255, 255, 255))
        screen.blit(text_surface, (10, 10)) # Draw in top-left corner

        # The window title is now redundant, but we can leave it
        pygame.display.set_caption(f"World Viewer: {world.world_name}")

        pygame.display.flip()

    # --- Cleanup ---
    logging.info("Exiting application.")
    pygame.quit()
    sys.exit()

if __name__ == '__main__':
    main()