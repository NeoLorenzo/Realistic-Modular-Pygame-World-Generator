# Realistic Modular Pygame World Generator

A standalone Python library and interactive design tool for generating complex, scientifically-grounded worlds. Designed from the ground up for modularity, performance, and realism, this package allows developers to seamlessly integrate a powerful world-generation engine into any Python-based simulation, game, or project.

The core philosophy is to create a data-first engine that produces emergent, believable climate and geological systems based on interconnected physical principles. The world features a **layered terrain model** with bedrock and slope-based soil deposition, a dynamic climate model with **prevailing winds** and **rain shadows**, and **climate-driven biomes**. The interactive editor allows for rapid iteration and design.

## Table of Contents

*   [Core Philosophy](#core-philosophy)
    *   [1. True Modularity (Plug-and-Play)](#1-true-modularity-plug-and-play)
    *   [2. Scientifically-Grounded Realism](#2-scientifically-grounded-realism)
    *   [3. Rapid, Interactive Design](#3-rapid-interactive-design)
*   [Project Structure](#project-structure)
*   [System Architecture: The Live Editor](#system-architecture-the-live-editor)
    *   [The Generation Pipeline: From Seed to Climate](#the-generation-pipeline-from-seed-to-climate)
*   [Configuration Deep Dive](#configuration-deep-dive)
*   [Performance & Optimization](#performance--optimization)
*   [Getting Started](#getting-started)
    *   [Prerequisites](#prerequisites)
    *   [Installation & Running the Editor](#installation--running-the-editor)
    *   [How to Use the Editor](#how-to-use-the-editor)
*   [Using the Generator in Your Project](#using-the-generator-in-your-project)
    *   [Basic Usage](#basic-usage)
    *   [Advanced Usage: Generating and Visualizing a Region](#advanced-usage-generating-and-visualizing-a-region)
*   [Roadmap: Rebuilding the Baker](#roadmap-rebuilding-the-baker)
*   [Architectural Principles](#architectural-principles)
*   [Contributing](#contributing)
*   [Dependencies](#dependencies)
*   [License](#license)

## Core Philosophy

The project's design is built on three core pillars, enforced by a strict set of internal development rules.

### 1. True Modularity (Plug-and-Play)

The generator is architected as a self-contained Python package (`world_generator/`) that has no knowledge of the application consuming it. Its data-only backend works exclusively with NumPy arrays and real-world scientific units (e.g., Celsius, g/m³), and has zero dependencies on Pygame or any other GUI framework. This means you can import and use the `WorldGenerator` class in any project—a web backend, a scientific model, or a different game engine—with full confidence that you are only getting the data generation engine.

### 2. Scientifically-Grounded Realism

The goal is to generate worlds with believable and emergent characteristics, not just random noise. Terrain is a two-layer system: a foundational **bedrock** layer is generated first, then a **soil** layer is deposited on top, with deeper soil accumulating in flatter areas. Climate is an emergent property of this final terrain, with temperature affected by altitude (adiabatic lapse rate) and humidity driven by **prevailing winds**, **rain shadows**, and distance from water. This creates realistic biomes and geological features—like arid deserts behind mountain ranges or exposed rock on steep slopes—that are a direct consequence of the underlying physics, not just pre-programmed rules.

### 3. Rapid, Interactive Design

The project is more than just a generator; it's a design tool. The **Live Editor** provides a real-time, full-world preview that updates instantly as you adjust parameters, allowing for fast iteration and artistic direction. A **real-time data tooltip** provides direct quantitative feedback on the climate at any point on the map, turning abstract parameters into tangible results. This workflow empowers designers to craft a specific world rather than just accepting a random seed.

## System Architecture: A Complete Design & Viewing Suite

The application is a multi-state suite that provides a complete workflow for world creation, from initial design to final exploration.

1.  **Main Menu:** The application starts at a main menu, allowing you to choose between the `Live Editor` and the `World Browser`.

2.  **The Live Editor (Design Phase):** This is the interactive design environment for rapid iteration.
    *   **Real-Time Feedback:** A full-world preview is regenerated instantly whenever you adjust a parameter, providing immediate visual feedback.
    *   **Master Bake on Change:** Every parameter change triggers a full, blocking "master bake" using `baker.py`. This generates the full-resolution, canonical NumPy data arrays for the entire world, ensuring the preview is always a downsampled version of the "source of truth."
    *   **Packaging:** From the editor, you can initiate the packaging process. This runs `package_builder.py` in the background to convert the high-resolution master data into an optimized, distributable format with chunked PNGs.

3.  **The World Browser & Viewer (Exploration Phase):**
    *   **Browse Packages:** The browser scans for completed world packages and displays them in a list.
    *   **High-Performance Viewing:** Selecting a world opens it in the viewer, which is designed for high-performance exploration. It only loads the pre-rendered image chunks that are currently on-screen, allowing for smooth panning and zooming across massive, high-resolution worlds without any real-time generation overhead.

### The Generation Pipeline: From Seed to Climate

The underlying data generation is a multi-stage process where each step builds upon the last. This entire pipeline is executed for every data request to ensure all systems respond correctly to parameter changes:
1.  **Bedrock Generation:** A foundational bedrock layer is created by combining continental noise, detail noise, and tectonic uplift noise. This raw noise is then normalized and shaped by an amplitude curve to create the base landforms.
2.  **Soil Deposition:** The slope (steepness) of the bedrock is calculated. A soil depth map is then generated where depth is inversely proportional to the slope—flatter areas accumulate deep soil, while steep cliffs are left as exposed rock. Soil is only deposited on land, not on the sea floor.
3.  **Final Elevation:** The final, absolute elevation is calculated by adding the soil depth map to the bedrock layer. This is the "true" ground level of the world.
4.  **Climate Calculation:** Temperature (in Celsius) and Humidity (in g/m³) are calculated based on the **final elevation**. This critical step ensures that climate accurately reflects the soil-modified terrain. The model accounts for altitude, latitude, prevailing winds, and rain shadows.
5.  **Biome & Final Colors:** The final terrain color is determined by a soil-aware process. Areas with very little soil are rendered as exposed rock. Soil-covered areas are colored based on a set of prioritized rules that factor in the final elevation, temperature, and humidity to create biomes like ice, snow, sand deserts, and various grasslands.

## Configuration Deep Dive

Configuration is split into two distinct types, following Rule 1.
*   **Simulation Parameters (`editor/config.json`):** These are the variables that define a specific world. The most important of these are exposed in the Live Editor's UI for real-time tuning.
*   **Application Constants (`world_generator/config.py`):** These are the "deep magic" values that define the physics and core behavior of the generator. They are not meant to be changed between runs but can be tuned by developers to alter the fundamental nature of the worlds being generated (e.g., changing the thresholds for biome transitions).

| Parameter                         | Unit                  | Default | UI Control        | Description                                                                                                                            |
| --------------------------------- | --------------------- | ------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `TARGET_SEA_LEVEL_TEMP_C`         | Celsius               | `15.0`  | Slider            | The "thermostat" for the world. Higher values create warmer worlds.                                                                    |
| `DETAIL_NOISE_WEIGHT`             | float                 | `0.25`  | Slider            | How much the detail layer influences the base terrain. Higher values create rougher, more mountainous bedrock.                       |
| `LAPSE_RATE_C_PER_UNIT_ELEVATION` | °C / ΔE               | `40.0`  | Slider            | Temperature drop for a full elevation change. Controls how cold mountains get.                                                         |
| `TERRAIN_BASE_FEATURE_SCALE_KM`   | km                    | `40.0`  | Slider            | The size of continents. Increase for larger, more sprawling landmasses.                                                                |
| `TERRAIN_AMPLITUDE`               | float                 | `2.5`   | Slider            | The sharpness of the bedrock. Higher values create more dramatic, steeper mountains and deeper valleys.                                |
| `POLAR_TEMPERATURE_DROP_C`        | Celsius               | `30.0`  | Slider            | The total temperature difference between the equator and the poles.                                                                    |
| `MOUNTAIN_UPLIFT_STRENGTH`        | float                 | `0.8`   | Slider            | Controls the height of mountains formed by tectonic uplift. This is a purely additive effect on the bedrock.                         |
| `world_width_chunks`              | chunks                | `800`   | Text Input        | The width of the world in chunks. Requires clicking "Apply Size Changes".                                                              |
| `world_height_chunks`             | chunks                | `450`   | Text Input        | The height of the world in chunks. Requires clicking "Apply Size Changes".                                                               |
| `MAX_SOIL_DEPTH_UNITS`            | Normalized Units      | `0.05`  | Config File       | The maximum depth of soil that can accumulate in perfectly flat, land-based areas.                                                     |
| `SNOW_LINE_TEMP_C`                | Celsius               | `0.0`   | Config File       | The temperature at or below which snow appears on land.                                                                                |
| `ICE_FORMATION_TEMP_C`            | Celsius               | `-2.0`  | Config File       | The temperature at or below which water freezes into ice.                                                                              |
| `PREVAILING_WIND_DIRECTION_DEGREES` | Degrees               | `180.0` | Config File       | The global wind direction (0=E, 90=N, 180=W, 270=S). Controls rain shadows.                                                            |
| `HUMIDITY_COASTAL_FALLOFF_RATE`   | float                 | `2.5`   | Config File       | A power factor for humidity dissipation. Higher values create a very sharp drop-off from the coast.                                    |
| `BIOME_THRESHOLDS`                | dict                  | varies  | Config File       | A dictionary of temperature and humidity values that control all biome transitions (e.g., where lush grass becomes normal grass).      |

## Performance & Optimization

*   **Live Editor:** The editor's responsiveness is achieved by performing all generation on downsampled versions of the master data arrays. The final preview surface resolution is controlled by `PREVIEW_RESOLUTION_WIDTH` and `PREVIEW_RESOLUTION_HEIGHT` in `main.py`. Critical code paths in the noise generation algorithms are JIT-compiled with Numba for C-like speed.
*   **Baked World Viewer:** The viewer is designed for maximum performance. It performs zero on-the-fly generation. By loading only the small, pre-rendered PNG chunks visible to the camera, it allows for smooth, real-time exploration of massive worlds with minimal memory and CPU usage.
*   **Packaging:** The `package_builder.py` script uses hashing to deduplicate identical chunks. A world with large, uniform oceans or deserts will result in a smaller final package size, as the same image file is referenced multiple times in the manifest.

## Getting Started

### Prerequisites

*   Python 3.8+
*   Git

### Installation & Running the Editor

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/your-username/Realistic-Modular-Pygame-World-Generator.git
    cd Realistic-Modular-Pygame-World-Generator
    ```2.  **Create and activate a virtual environment (recommended):**
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
    From the project's root directory, run the editor as a module. This is the correct way to launch the application to ensure all internal imports work correctly.
    ```sh
    python -m editor.main
    ```

### How to Use the Application

1.  **Main Menu:** Launching the application presents a main menu. Choose "Live World Editor" to design a new world or "Browse Baked Worlds" to explore a completed one.

2.  **In the Editor:**
    *   **Live Parameter Tuning:** Use the sliders on the right-hand panel to adjust world parameters. The preview will update automatically after each change.
    *   **Custom World Size:** Enter new dimensions (in chunks) into the text boxes and click **"Apply Size Changes"** to re-bake the world with the new size.
    *   **Package for Distribution:** Once you are satisfied with the design, click the **"Package World for Distribution"** button. This will run the chunking process in the background.
    *   **Real-Time Data:** Hover the mouse over the map to see a **real-time data tooltip** showing key climate and terrain information.
    *   **Controls:** Pan with `W, A, S, D`, zoom with the `Mouse Wheel`, and cycle view modes with the `V` key.

3.  **In the Browser/Viewer:**
    *   **Select a World:** Click on a world name from the list and click "Load Selected World".
    *   **Explore:** Pan and zoom across the high-resolution world smoothly. Use the `V` key to cycle through the different data maps (Terrain, Temperature, etc.) that were baked into the package.
    *   **Return:** Press `ESC` to return to the browser, and again to return to the main menu.

## Using the Generator in Your Project

The core library in the `world_generator/` folder is fully independent. You can use it in any project for procedural data generation.

### Basic Usage

Here is a minimal example of instantiating the generator.

```python
import numpy as np
import logging
from world_generator.generator import WorldGenerator

# It's good practice to set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("my_simulation")

# You can override any default parameter by passing a config dictionary
my_config = {
    "seed": 999,
    "target_sea_level_temp_c": 25.0,
    "world_width_chunks": 100, # A smaller world for this example
    "world_height_chunks": 100
}
world_gen = WorldGenerator(config=my_config, logger=logger)

print(f"Generator created for a world of size {world_gen.world_width_cm}x{world_gen.world_height_cm} cm.")
```

### Advanced Usage: Generating and Visualizing a Region

This example shows how to request all data layers for a specific 200x200 pixel area of the world and save it as a terrain map image, without using any Pygame code.

```python
import numpy as np
import logging
from PIL import Image
from world_generator.generator import WorldGenerator
from world_generator import color_maps # Use the shared color mapping utility

# --- 1. Setup Generator ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("my_data_app")
world_gen = WorldGenerator(config={"seed": 42}, logger=logger)

# --- 2. Define the Region of Interest ---
RESOLUTION = 200
X_START_CM = 500000
Y_START_CM = 500000
x_coords = np.linspace(X_START_CM, X_START_CM + 20000, RESOLUTION)
y_coords = np.linspace(Y_START_CM, Y_START_CM + 20000, RESOLUTION)
wx_grid, wy_grid = np.meshgrid(x_coords, y_coords)

# --- 3. Generate All Data Layers ---
print("Generating data for region...")
bedrock_data = world_gen._get_bedrock_elevation(wx_grid, wy_grid)
elevation_data = world_gen.get_elevation(wx_grid, wy_grid, bedrock_elevation=bedrock_data)
temp_data = world_gen.get_temperature(wx_grid, wy_grid, elevation_data)
soil_depth_data = world_gen._get_soil_depth(world_gen._get_slope(bedrock_data))
humidity_data = world_gen.get_humidity(wx_grid, wy_grid, elevation_data, temp_data)
print("Data generation complete.")

# --- 4. Convert Raw Data to a Color Image ---
print("Creating terrain color map...")
biome_map = color_maps.calculate_biome_map(elevation_data, temp_data, humidity_data, soil_depth_data)
biome_lut = color_maps.create_biome_color_lut()
color_array = color_maps.get_terrain_color_array(biome_map, biome_lut)
img_data = np.transpose(color_array, (1, 0, 2))

# --- 5. Save the Image ---
img = Image.fromarray(img_data, 'RGB')
img.save("output_terrain_map.png")
print("Saved terrain map to output_terrain_map.png")
```

## The End-to-End Workflow

The project provides a complete, end-to-end workflow for creating and using procedurally generated worlds.

1.  **Design in the Live Editor:** Use the powerful, real-time editor to design the world. Adjust parameters like climate, continent size, and tectonic activity until the desired look and feel is achieved. The instant preview makes this a fast and intuitive process.

2.  **Bake and Package:** With a single click on the **"Package World for Distribution"** button, the editor orchestrates the full creation pipeline:
    *   First, the `baker` generates the full-resolution "master data" for all layers (elevation, temperature, etc.) as raw NumPy arrays. This is the world's single source of truth.
    *   Next, the `package_builder` takes this master data and processes it. It slices the world into a grid of smaller chunks, converts each chunk into an optimized PNG for every view mode (Terrain, Temperature, etc.), and saves them into a self-contained "Baked World Package" directory.

3.  **Browse and View:** Once a world is packaged, it can be explored in the high-performance viewer. From the main menu, select the **World Browser**, choose your creation, and explore the final, high-resolution world with smooth panning and zooming. This viewer is what a final game or simulation would use to interact with the generated world.

## Architectural Principles

This project is developed under a strict set of internal rules that enforce high code quality, maintainability, and robustness. Key principles include:

*   **No Magic Numbers (Rule 1):** Configuration is strictly separated from code into `config.json` (for experiments) and `config.py` (for core constants).
*   **Structured Logging (Rule 2):** All runtime output uses the Python `logging` module. No `print()` statements are used in the core engine.
*   **Realism First (Rule 3):** The simulation prioritizes behavioral realism. Abstractions are only used when a 1:1 model is too complex or slow, and they must be scientifically grounded.
*   **SOLID Principles (Rule 7):** The codebase is highly modular and adheres to SOLID principles, ensuring components are decoupled and reusable.
*   **Deterministic by Default (Rule 12):** All randomness is controlled by a single master seed. Given the same seed and configuration, the output is 100% reproducible.

## Contributing

Contributions are welcome. Please adhere to the established architectural principles when proposing changes.

## Dependencies

*   `pygame-ce`: Used by the `editor` for rendering and UI.
*   `pygame-gui`: Used for the interactive UI elements in the editor.
*   `numpy`: The core dependency for all numerical operations.
*   `numba`: Used to JIT-compile the performance-critical Perlin noise function.
*   `scipy`: Used for tectonic plate generation (`cKDTree`) and other scientific computations.
*   `Pillow`: Used for data visualization examples.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.