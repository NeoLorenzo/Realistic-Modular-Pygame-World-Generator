# Realistic Modular Pygame World Generator

A standalone Python library and interactive design tool for generating complex, scientifically-grounded worlds. Designed from the ground up for modularity, performance, and realism, this project produces **fully self-contained, runnable world packages** that can be used as the foundation for any Python-based simulation, game, or project.

The core philosophy is to create a data-first engine that produces emergent, believable systems. The world features a layered terrain model with bedrock and soil, a dynamic climate model with prevailing winds and rain shadows, and a fully integrated **in-game clock and day/night cycle**. The interactive editor allows for rapid iteration and design, and the final output is a "plug-and-play" package that works out of the box.

## Table of Contents

*   [Core Philosophy](#core-philosophy)
    *   [1. Truly Plug-and-Play](#1-truly-plug-and-play)
    *   [2. Scientifically-Grounded Realism](#2-scientifically-grounded-realism)
    *   [3. Rapid, Interactive Design](#3-rapid-interactive-design)
*   [System Architecture: A Complete Design & Viewing Suite](#system-architecture-a-complete-design--viewing-suite)
    *   [The Generation Pipeline: From Seed to Climate](#the-generation-pipeline-from-seed-to-climate)
*   [Configuration Deep Dive](#configuration-deep-dive)
*   [Performance & Optimization](#performance--optimization)
*   [Getting Started](#getting-started)
    *   [Prerequisites](#prerequisites)
    *   [Installation & Running the Editor](#installation--running-the-editor)
    *   [How to Use the Application](#how-to-use-the-application)
*   [Using the Generator in Your Project](#using-the-generator-in-your-project)
    *   [Option A: Using a Baked World Package (Recommended)](#option-a-using-a-baked-world-package-recommended)
    *   [Option B: Using the Core Generator Library](#option-b-using-the-core-generator-library)
*   [The End-to-End Workflow](#the-end-to-end-workflow)
*   [Architectural Principles](#architectural-principles)
*   [Dependencies](#dependencies)
*   [License](#license)

## Core Philosophy

The project's design is built on three core pillars, enforced by a strict set of internal development rules.

### 1. Truly Plug-and-Play

The final output of the baking process is not just a folder of data—it's a self-contained, runnable application. Each baked world package includes the world data, a high-performance renderer, a configurable game clock, a smooth day/night cycle, and automation scripts that handle the entire setup process. A user can download a baked world, run a single script, and instantly have a working, interactive visualization of their creation.

### 2. Scientifically-Grounded Realism

The goal is to generate worlds with believable and emergent characteristics. Terrain is a two-layer system: a foundational **bedrock** layer is generated first, then a **soil** layer is deposited on top, with deeper soil accumulating in flatter areas. Climate is an emergent property of this final terrain, with temperature affected by altitude and humidity driven by **prevailing winds** and **rain shadows**. This creates realistic biomes and geological features that are a direct consequence of the underlying physics.

### 3. Rapid, Interactive Design

The project is more than just a generator; it's a design tool. The **Live Editor** provides a real-time, full-world preview that updates instantly as you adjust parameters. A **real-time data tooltip** provides direct quantitative feedback on the climate at any point on the map, turning abstract parameters into tangible results. This workflow empowers designers to craft a specific world rather than just accepting a random seed.

## System Architecture: A Complete Design & Viewing Suite

The application is a multi-state suite that provides a complete workflow for world creation, from initial design to final exploration.

1.  **Main Menu:** The application starts at a main menu, allowing you to choose between the `Live Editor` and the `World Browser`.

2.  **The Live Editor (Design Phase):** This is the interactive design environment for rapid iteration.
    *   **Real-Time Feedback:** A full-world preview is regenerated instantly whenever you adjust a parameter.
    *   **Packaging:** From the editor, you can initiate the packaging process. This runs `package_builder.py` in the background to convert the high-resolution master data into a complete, runnable world package with chunked PNGs and all necessary runtime logic.

3.  **The World Browser & Viewer (Exploration Phase):**
    *   **Browse Packages:** The browser scans for completed world packages and displays them in a list.
    *   **High-Performance Viewing:** Selecting a world opens it in the viewer, which is designed for high-performance exploration. It only loads the pre-rendered image chunks that are currently on-screen, allowing for smooth panning and zooming across massive worlds.

### The Generation Pipeline: From Seed to Climate

The underlying data generation is a multi-stage process where each step builds upon the last:
1.  **Bedrock Generation:** A foundational bedrock layer is created by combining continental noise, detail noise, and tectonic uplift noise.
2.  **Soil Deposition:** The slope of the bedrock is calculated. A soil depth map is then generated where depth is inversely proportional to the slope.
3.  **Final Elevation:** The final, absolute elevation is calculated by adding the soil depth map to the bedrock layer.
4.  **Climate Calculation:** Temperature and Humidity are calculated based on the **final elevation**, accounting for altitude, latitude, prevailing winds, and rain shadows.
5.  **Biome & Final Colors:** The final terrain color is determined by a soil-aware process that factors in the final elevation, temperature, and humidity.

## Configuration Deep Dive

Configuration is split into two distinct types, following Rule 1.
*   **Simulation Parameters (`editor/config.json`):** These are the variables that define a specific world, exposed in the Live Editor's UI.
*   **Application Constants (`world_generator/config.py`):** These are the "deep magic" values that define the physics and core behavior of the generator.

| Parameter                         | Unit                  | Default | UI Control        | Description                                                                                                                            |
| --------------------------------- | --------------------- | ------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `TARGET_SEA_LEVEL_TEMP_C`         | Celsius               | `15.0`  | Slider            | The "thermostat" for the world. Higher values create warmer worlds.                                                                    |
| `DETAIL_NOISE_WEIGHT`             | float                 | `0.25`  | Slider            | How much the detail layer influences the base terrain. Higher values create rougher, more mountainous bedrock.                       |
| `LAPSE_RATE_C_PER_UNIT_ELEVATION` | °C / ΔE               | `40.0`  | Slider            | Temperature drop for a full elevation change. Controls how cold mountains get.                                                         |
| `TERRAIN_BASE_FEATURE_SCALE_KM`   | km                    | `40.0`  | Slider            | The size of continents. Increase for larger, more sprawling landmasses.                                                                |
| `TERRAIN_AMPLITUDE`               | float                 | `2.5`   | Slider            | The sharpness of the bedrock. Higher values create more dramatic, steeper mountains and deeper valleys.                                |
| `POLAR_TEMPERATURE_DROP_C`        | Celsius               | `30.0`  | Slider            | The total temperature difference between the equator and the poles.                                                                    |
| `MOUNTAIN_UPLIFT_STRENGTH`        | float                 | `0.8`   | Slider            | Controls the height of mountains formed by tectonic uplift.                                                                            |
| `world_width_chunks`              | chunks                | `800`   | Text Input        | The width of the world in chunks.                                                                                                      |
| `world_height_chunks`             | chunks                | `450`   | Text Input        | The height of the world in chunks.                                                                                                     |
| `SUNRISE_HOUR`                    | Hour (0-24)           | `7.0`   | Config File       | The time when the sun begins to rise.                                                                                                  |
| `SUNSET_HOUR`                     | Hour (0-24)           | `19.0`  | Config File       | The time when the sun has fully set.                                                                                                   |
| `DAY_NIGHT_TRANSITION_DURATION_HOURS` | Hours               | `1.0`   | Config File       | The duration of the sunrise and sunset fade effects.                                                                                   |
| `NIGHT_COLOR`                     | (R, G, B)             | varies  | Config File       | The color of the darkness overlay at night.                                                                                            |
| `INITIAL_TIME_SCALE`              | float                 | `60.0`  | Config File       | The initial speed of the in-game clock (1 real second = 60 game seconds).                                                              |

## Performance & Optimization

*   **Live Editor:** The editor's responsiveness is achieved by performing all generation on downsampled data arrays. Critical code paths in the noise generation algorithms are JIT-compiled with Numba for C-like speed.
*   **Baked World Viewer:** The viewer is designed for maximum performance. It performs zero on-the-fly generation. By loading only the small, pre-rendered PNG chunks visible to the camera, it allows for smooth, real-time exploration of massive worlds.
*   **Packaging:** The `package_builder.py` script uses hashing to deduplicate identical chunks. A world with large, uniform oceans or deserts will result in a smaller final package size.

## Getting Started

### Prerequisites

*   Python 3.8+
*   Git

### Installation & Running the Editor

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/your-username/Realistic-Modular-Pygame-World-Generator.git
    cd Realistic-Modular-Pygame-World-Generator
    ```
2.  **Create and activate a virtual environment (recommended):**
    ```sh
    python -m venv venv
    # On Windows: venv\Scripts\activate
    # On macOS/Linux: source venv/bin/activate
    ```
3.  **Install the required dependencies:**
    ```sh
    pip install -r requirements.txt
    ```
4.  **Run the Live Editor application:**
    ```sh
    python -m editor.main
    ```

### How to Use the Application

1.  **Main Menu:** Launching the application presents a main menu. Choose "Live World Editor" to design a new world or "Browse Baked Worlds" to explore a completed one.

2.  **In the Editor:**
    *   **Live Parameter Tuning:** Use the sliders on the right-hand panel to adjust world parameters. The preview will update automatically.
    *   **Package for Distribution:** Once you are satisfied, click **"Package World for Distribution"**. This will run the full baking and packaging process in the background.

3.  **Running a Baked World:**
    *   Navigate to the output folder (e.g., `baked_worlds/MyWorld_Seed42_Chunked/`).
    *   **On Windows:** Double-click `run.bat`.
    *   **On macOS/Linux:** Open a terminal and run `./run.sh`.
    *   The script will automatically create a virtual environment, install dependencies, and launch the world viewer.

## Using the Generator in Your Project

### Option A: Using a Baked World Package (Recommended)

The baked package is a standard Python package. You can import the `World` class and integrate it into your own Pygame application.

```python
import pygame
from runtime.world import World # Import from the local runtime package
from my_game.camera import MyCamera # Use your own camera

# --- In your main game setup ---
pygame.init()
screen = pygame.display.set_mode((1920, 1080))
my_world = World(package_path='.') # Assumes your game runs from the world dir
my_camera = MyCamera()

# --- In your main game loop ---
def game_loop():
    # ... handle your game's events ...
    
    # Update the world's clock and lighting
    my_world.update(time_delta)

    # Draw your game
    screen.fill((0,0,0))
    my_world.draw(screen, my_camera) # The world draws itself
    # ... draw your players, UI, etc. on top ...

    pygame.display.flip()
```

### Option B: Using the Core Generator Library

The core library in `world_generator/` is fully independent and can be used for raw data generation in any project.

```python
import logging
from world_generator.generator import WorldGenerator

# Minimal example of instantiating the generator
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("my_simulation")
my_config = {"seed": 999}
world_gen = WorldGenerator(config=my_config, logger=logger)
```

## The End-to-End Workflow

1.  **Design:** Use the Live Editor to design the world with real-time feedback.
2.  **Package:** Click the "Package" button. The editor orchestrates the full creation pipeline, producing a self-contained, runnable world package.
3.  **Run & Integrate:** Run the packaged world instantly using the provided scripts, or import the `World` class from the package into your own application.

## Architectural Principles

This project is developed under a strict set of internal rules that enforce high code quality, maintainability, and robustness. Key principles include:
*   **No Magic Numbers (Rule 1):** Configuration is strictly separated from code.
*   **Structured Logging (Rule 2):** All runtime output uses the Python `logging` module.
*   **Realism First (Rule 3):** The simulation prioritizes behavioral realism.
*   **SOLID Principles (Rule 7):** The codebase is highly modular and reusable.
*   **Deterministic by Default (Rule 12):** All randomness is controlled by a single master seed.

## Dependencies

*   **Editor & Generator:** `pygame-ce`, `pygame-gui`, `numpy`, `numba`, `scipy`, `Pillow`.
*   **Baked World Package:** `pygame-ce`, `numpy`.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.