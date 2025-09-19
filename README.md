# Realistic Modular Pygame World Generator

A standalone Python library and interactive design tool for generating complex, scientifically-grounded worlds. Designed from the ground up for modularity, performance, and realism, this package allows developers to seamlessly integrate a powerful world-generation engine into any Python-based simulation, game, or project.

The core philosophy is to create a data-first engine that produces emergent, believable climate and geological systems based on interconnected physical principles. The world features a **layered terrain model** with bedrock and slope-based soil deposition, a dynamic climate model with **prevailing winds** and **rain shadows**, and **climate-driven biomes**. The interactive editor allows for rapid iteration and design before committing to a final, high-performance "baked" world.

## Table of Contents

*   [Core Philosophy](#core-philosophy)
    *   [1. True Modularity (Plug-and-Play)](#1-true-modularity-plug-and-play)
    *   [2. Scientifically-Grounded Realism](#2-scientifically-grounded-realism)
    *   [3. Rapid, Interactive Design](#3-rapid-interactive-design)
    *   [4. Efficiency and Performance](#4-efficiency-and-performance)
*   [Project Structure](#project-structure)
*   [System Architecture: The Two-Tier Workflow](#system-architecture-the-two-tier-workflow)
    *   [Tier 1: The Live Editor](#tier-1-the-live-editor)
    *   [Tier 2: The Integrated Baker](#tier-2-the-integrated-baker)
    *   [The Generation Pipeline: From Seed to Climate](#the-generation-pipeline-from-seed-to-climate)
*   [Configuration Deep Dive](#configuration-deep-dive)
*   [Performance & Optimization](#performance--optimization)
    *   [The Optimization Journey & Architectural Lessons](#the-optimization-journey--architectural-lessons)
*   [Getting Started](#getting-started)
    *   [Prerequisites](#prerequisites)
    *   [Installation & Running the Editor](#installation--running-the-editor)
    *   [How to Use the Editor](#how-to-use-the-editor)
*   [Using the Generator in Your Project](#using-the-generator-in-your-project)
    *   [Basic Usage](#basic-usage)
    *   [Advanced Usage: Generating and Visualizing a Region](#advanced-usage-generating-and-visualizing-a-region)
*   [Roadmap & Future Features](#roadmap--future-features)
*   [Architectural Principles](#architectural-principles)
*   [Contributing](#contributing)
*   [Dependencies](#dependencies)
*   [License](#license)

## Core Philosophy

The project's design is built on four pillars, enforced by a strict set of internal development rules.

### 1. True Modularity (Plug-and-Play)

The generator is architected as a self-contained Python package (`world_generator/`) that has no knowledge of the application consuming it. Its data-only backend works exclusively with NumPy arrays and real-world scientific units (e.g., Celsius, g/m³), and has zero dependencies on Pygame or any other GUI framework. This means you can import and use the `WorldGenerator` class in any project—a web backend, a scientific model, or a different game engine—with full confidence that you are only getting the data generation engine.

### 2. Scientifically-Grounded Realism

The goal is to generate worlds with believable and emergent characteristics, not just random noise. Terrain is a two-layer system: a foundational **bedrock** layer is generated first, then a **soil** layer is deposited on top, with deeper soil accumulating in flatter areas. Climate is an emergent property of this final terrain, with temperature affected by altitude (adiabatic lapse rate) and humidity driven by **prevailing winds**, **rain shadows**, and distance from water. This creates realistic biomes and geological features—like arid deserts behind mountain ranges or exposed rock on steep slopes—that are a direct consequence of the underlying physics, not just pre-programmed rules.

### 3. Rapid, Interactive Design

The project is more than just a generator; it's a design tool. The **Live Editor** provides a real-time, full-world preview that updates instantly as you adjust parameters, allowing for fast iteration and artistic direction. A new **real-time data tooltip** provides direct quantitative feedback on the climate at any point on the map, turning abstract parameters into tangible results. This workflow empowers designers to craft a specific world rather than just accepting a random seed.

### 4. Efficiency and Performance

Performance is a key design consideration, driven by profiling (Rule 11). The editor uses a single, low-resolution preview for interactivity, while the final output is a "baked" set of image tiles. This two-tier system enables a potential viewer to run with maximum performance by offloading all generation to a one-time, offline process. The baker itself is highly parallelized to utilize all available CPU cores, and critical code paths in the noise generation algorithms are JIT-compiled with Numba for C-like speed.

## Project Structure

```
Realistic-Modular-Pygame-World-Generator/
├── editor/                         # The interactive world design tool and baker.
│   ├── main.py                     # Application entry point and main loop.
│   ├── baker.py                    # Integrated, multi-threaded world baking module.
│   ├── renderer.py                 # Pygame-specific rendering logic.
│   ├── camera.py                   # Handles view transformations (pan/zoom).
│   ├── config.json                 # Default simulation parameters for the editor.
│   └── logging_config.json         # Logging configuration for the editor.
│
├── requirements.txt                # Project dependencies.
│
└── world_generator/                # The core, standalone, data-only library.
    ├── generator.py                # Contains the main WorldGenerator class.
    ├── noise.py                    # Optimized Perlin noise implementation.
    ├── tectonics.py                # Tectonic plate and mountain generation.
    ├── config.py                   # Default internal constants for the generator.
    └── color_maps.py               # Shared color mapping utilities.
```

## System Architecture: The Two-Tier Workflow

The project operates using a powerful two-tier workflow that separates the creative design process from the final, high-performance output.

### Tier 1: The Live Editor

When you run `editor.main`, you enter the Live Editor. Its purpose is rapid design and iteration.
*   **Single Preview Surface:** Instead of rendering thousands of chunks, the editor generates one single, moderately-sized image of the entire world.
*   **Real-Time Feedback:** This preview image is regenerated whenever you change a parameter using the UI sliders, providing instant visual feedback.
*   **Pixelated Zoom:** Zooming is fast but pixelated, as it simply scales the single preview image. This is by design to maintain interactivity.
*   **Non-Destructive:** All changes are made in memory. The original `config.json` is never modified.

### Tier 2: The Integrated Baker

When you are satisfied with your world design in the editor, you can use the "Bake World" feature.
*   **Seamless & Multi-Threaded:** Clicking the "Bake World" button launches the baking process in a background thread within the editor itself. The main UI remains fully responsive, allowing you to continue interacting with the application while the bake is in progress.
*   **Rich UI Feedback:** The baking process provides real-time feedback directly in the UI, with a live progress bar and status messages, so you always know its state.
*   **Formalized Output Package:** The baker produces a self-contained "Baked World Package" in the `baked_worlds/` directory. Each package is a folder containing the full-resolution chunk images, a `manifest.json` file to map coordinates to images, and a `world_config.json` file that saves the exact parameters used for the bake, ensuring perfect reproducibility.
*   **Highly Optimized:** The baker utilizes all available CPU cores for maximum speed and generates highly optimized output using a tiered, lossless compression strategy (including content deduplication and PNG palettization) to minimize storage size.

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

*   **Live Editor:** The editor's responsiveness is determined by the `PREVIEW_RESOLUTION_WIDTH` and `PREVIEW_RESOLUTION_HEIGHT` constants in `main.py`. The on-the-fly climate and soil calculations are performed on this preview-sized array, maintaining interactivity.
*   **Baking:** The baking process is a highly optimized, CPU-bound task that is parallelized across all available cores. Its duration is primarily determined by the total number of chunks and the raw processing power of the host machine.

### The Optimization Journey & Architectural Lessons

The current high performance of the baker is the result of a rigorous optimization process that involved overcoming several critical bottlenecks. This journey provides valuable lessons for future development.

**Successful Optimizations Implemented:**
1.  **Parallelization:** The core task was parallelized using Python's `multiprocessing` module, distributing the work of processing individual chunks across all available CPU cores.
2.  **Advanced Compression:** A tiered, lossless compression strategy was implemented using the Pillow library. This includes content deduplication via hashing, 1x1 pixel compression for uniform chunks, and 8-bit PNG palettization for low-color chunks, dramatically reducing storage size.
3.  **Data Quantization:** The smooth gradients of temperature and humidity data were quantized into discrete steps (e.g., one step per degree Celsius). This massively increased the effectiveness of content deduplication with minimal impact on visual quality.
4.  **On-the-Fly Correctness:** The architecture was refactored to calculate climate and soil data in real-time. This fixed critical architectural flaws where climate was not responding to terrain changes, trading a negligible performance cost for a massive gain in correctness.
5.  **Low-Level CPU Speedup:** Numba's `fastmath=True` flag was applied to the core Perlin noise functions, allowing the JIT compiler to use faster, less-precise floating-point instructions, which provided a significant speed boost with no perceptible change in the visual output.

**The Failed Approach: Block-Based Processing**

An attempt was made to further optimize the CPU-bound work by having each worker process a large block of chunks (e.g., 4x4 or 8x8) at once.

*   **The Theory:** The hypothesis was that calculating noise for one large, contiguous array would be more efficient for the CPU cache and Numba's compiler than performing many smaller, separate calculations.
*   **The Failure in Practice:** This approach led to a catastrophic performance collapse. Each of the many worker processes attempted to allocate several massive NumPy arrays simultaneously, creating a sudden and enormous demand for RAM. This **memory saturation** forced the operating system to start "thrashing"—aggressively swapping memory to the much slower hard drive. The result was a system that was almost completely unresponsive, with CPUs spending all their time waiting for the disk.
*   **The Architectural Lesson:** For this type of "embarrassingly parallel" task, **maintaining a low memory footprint for each individual worker is far more critical to overall performance than micro-optimizing CPU cache efficiency.** The cost of memory swapping is orders of magnitude greater than any potential gains from larger batch processing. The current, stable architecture where each worker handles one memory-light chunk at a time is the correct and most scalable approach. **This path should not be pursued again.**

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
    From the project's root directory, run the editor as a module. This is the correct way to launch the application to ensure all internal imports work correctly.
    ```sh
    python -m editor.main
    ```

### How to Use the Editor

*   **Live Parameter Tuning:** Use the sliders on the right-hand panel to adjust world parameters. The preview will update automatically.
*   **Custom World Size:** Enter new dimensions (in chunks) into the text boxes and click **"Apply Size Changes"** to re-initialize the world.
*   **Real-Time Data:** Hover the mouse over the map to see a **real-time data tooltip** showing the terrain type, temperature, and humidity at that exact point.
*   **Baking Your World:** When you are satisfied with the design, click **"Bake World"**. This will start the fast, offline rendering process in a background thread. The editor will remain responsive, and you can monitor progress via the live progress bar in the UI.
*   **Standard Controls:**
    *   **Pan:** `W`, `A`, `S`, `D` keys
    *   **Zoom:** Mouse Wheel Up/Down
    *   **Cycle View Mode:** `V` key (Terrain, Temperature, Humidity, Elevation, Tectonic, Soil Depth)
    *   **Exit:** `ESC` key or close the window

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
# We want a 200x200 pixel area, starting at world coordinate (500000, 500000) cm.
RESOLUTION = 200
X_START_CM = 500000
Y_START_CM = 500000

# Create coordinate grids for the generator. The generator works with NumPy arrays.
x_coords = np.linspace(X_START_CM, X_START_CM + 20000, RESOLUTION) # 200m wide region
y_coords = np.linspace(Y_START_CM, Y_START_CM + 20000, RESOLUTION) # 200m high region
wx_grid, wy_grid = np.meshgrid(x_coords, y_coords)

# --- 3. Generate All Data Layers ---
print("Generating data for region...")
# Follow the same pipeline as the editor for correctness
bedrock_data = world_gen._get_bedrock_elevation(wx_grid, wy_grid)
slope_data = world_gen._get_slope(bedrock_data)
soil_depth_data = world_gen._get_soil_depth(slope_data)
elevation_data = world_gen.get_elevation(wx_grid, wy_grid)
temp_data = world_gen.get_temperature(wx_grid, wy_grid, elevation_data)
humidity_data = world_gen.get_humidity(wx_grid, wy_grid, elevation_data, temp_data)
print("Data generation complete.")

# --- 4. Convert Raw Data to a Color Image ---
print("Creating terrain color map...")
# Use the same color utility as the editor and baker for consistency
color_array = color_maps.get_terrain_color_array(
    elevation_data, temp_data, humidity_data, soil_depth_data
)

# The color_maps utility returns (width, height, channels),
# but Pillow needs (height, width, channels). So we transpose.
img_data = np.transpose(color_array, (1, 0, 2))

# --- 5. Save the Image ---
img = Image.fromarray(img_data, 'RGB')
img.save("output_terrain_map.png")
print("Saved terrain map to output_terrain_map.png")
```

## Roadmap & Future Features

The following features are planned to enhance the project's usability, realism, and creative potential. They are designed to build upon the existing modular architecture.

### Main Menu & Interactive Baked World Viewer

A top-priority feature to elevate the project from a tool to a complete application. This involves creating a unified starting point and a high-performance viewer for finished worlds.

*   **User Experience:** Upon launch, users will be greeted with a simple main menu offering two choices: "Create New World" (which launches the current Live Editor) and "View Baked Worlds".
*   **Baked World Browser:** The "View Baked Worlds" option will open a new screen that scans the `baked_worlds/` directory and presents a list of all completed worlds, perhaps with a small preview image and key parameters from its `world_config.json`.
*   **High-Performance Viewer:** Selecting a world will open it in a new, highly optimized viewing mode. This viewer will not generate any data. Instead, it will load the pre-rendered chunk images on-demand as the user pans and zooms. This will allow for a perfectly smooth, high-resolution experience even on massive worlds, fulfilling the primary purpose of the baking process. The viewer will be fully interactive, allowing the user to pan, zoom, and switch between all the baked data views (terrain, temperature, etc.) using the new UI.

### User-Driven Baking & UI Enhancements

These features focus on giving the user more direct control over the application's core functions and improving the clarity of the interface.

*   **Selective Map View Baking:** To save time and significant disk space, users will be able to choose exactly which data layers get baked.
    *   **Implementation:** A series of checkboxes ("Terrain", "Temperature", "Humidity", etc.) will be added to the editor's UI panel. Before starting a bake, the application will pass the list of selected views to the baker thread. The baker will then only generate, save, and create manifests for the requested views. The "Estimated Bake Size" calculation will be updated to dynamically reflect the number of selected views for an accurate prediction.

*   **Enhanced View Mode UI:** The current method of pressing the 'V' key to cycle through views will be replaced with a more intuitive and informative interface.
    *   **Implementation:** A large, clear `UILabel` will be added to the top-center of the screen, displaying the name of the current view mode (e.g., "Temperature View"). Additionally, a new `UIPanel` will be added to the bottom-right corner containing a dedicated `UIButton` for each available view mode, allowing users to switch directly to any view at any time.

### New Simulation & Generation Features

These features will deepen the simulation's realism and provide greater artistic control over the final world.

*   **New Simulation Layer: Air Pressure:** To enhance the scientific grounding of the climate model, a new air pressure layer will be added.
    *   **Implementation:** Following **Rule 8 (Scientifically-Grounded Abstraction)**, a new method `get_air_pressure(elevation_data)` will be added to the `WorldGenerator`. This will use a simplified version of the real-world barometric formula to calculate air pressure (in kPa or a similar unit) based on altitude. This new data layer will be available as a new view mode and can be used in the future to drive more complex wind and weather simulations.

*   **Hydraulic Erosion & River Networks:** An algorithm to simulate water flow, carving rivers from mountains to the sea and creating more realistic drainage basins and deltas.

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
*   `Pillow`: Used for robust, high-performance image saving in the parallel baker and for data visualization examples.
*   `tqdm`: Used to display a progress bar for the integrated baker.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.