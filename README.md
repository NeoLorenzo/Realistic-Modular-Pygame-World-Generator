# Realistic Modular Pygame World Generator

A standalone Python library and interactive design tool for generating complex, scientifically-grounded worlds. Designed from the ground up for modularity, performance, and realism, this package allows developers to seamlessly integrate a powerful world-generation engine into any Python-based simulation, game, or project.

The core philosophy is to create a data-first engine that produces emergent, believable climate systems based on interconnected physical principles. The world now features a dynamic climate model with **prevailing winds**, **rain shadows**, and **climate-driven biomes**, creating realistic deserts and varied grasslands. The interactive editor allows for rapid iteration and design before committing to a final, high-performance "baked" world.

## Table of Contents

*   [Core Philosophy](#core-philosophy)
    *   [1. True Modularity (Plug-and-Play)](#1-true-modularity-plug-and-play)
    *   [2. Scientifically-Grounded Realism](#2-scientifically-grounded-realism)
    *   [3. Rapid, Interactive Design](#3-rapid-interactive-design)
    *   [4. Efficiency and Performance](#4-efficiency-and-performance)
*   [Project Structure](#project-structure)
*   [System Architecture: The Two-Tier Workflow](#system-architecture-the-two-tier-workflow)
    *   [Tier 1: The Live Editor](#tier-1-the-live-editor)
    *   [Tier 2: The Offline Baker](#tier-2-the-offline-baker)
    *   [The Generation Pipeline: From Seed to Climate](#the-generation-pipeline-from-seed-to-climate)
*   [Configuration Deep Dive](#configuration-deep-dive)
*   [Performance & Optimization](#performance--optimization)
    *   [The Optimization Journey & Architectural Lessons](#the-optimization-journey--architectural-lessons)
*   [Getting Started](#getting-started)
    *   [Prerequisites](#prerequisites)
    *   [Installation & Running the Editor](#installation--running-the-editor)
    *   [How to Use the Editor](#how-to-use-the-editor)
*   [Using the Generator in Your Project](#using-the-generator-in-your-project)
*   [Roadmap & Future Features](#roadmap--future-features)
*   [Architectural Principles](#architectural-principles)
*   [Contributing](#contributing)
*   [Dependencies](#dependencies)
*   [License](#license)

## Core Philosophy

The project's design is built on four pillars:

### 1. True Modularity (Plug-and-Play)

The generator is architected as a self-contained Python package (`world_generator/`) that has no knowledge of the application consuming it. Its data-only backend works with NumPy arrays and real-world scientific units (e.g., Celsius, g/m³).

### 2. Scientifically-Grounded Realism

The goal is to generate worlds with believable and emergent characteristics. Climate is an emergent property of the terrain, with temperature affected by altitude (adiabatic lapse rate) and humidity driven by **prevailing winds**, **rain shadows**, and distance from water. This creates realistic biomes, from lush jungles to arid deserts, that are a direct consequence of the underlying physics.

### 3. Rapid, Interactive Design

The project is more than just a generator; it's a design tool. The **Live Edit Mode** provides a real-time, full-world preview that updates instantly as you adjust parameters, allowing for fast iteration. A new **real-time data tooltip** provides direct quantitative feedback on the climate at any point on the map.

### 4. Efficiency and Performance

Performance is a key design consideration, driven by profiling (Rule 11). The editor uses a single, low-resolution preview for interactivity, while the final output is a "baked" set of image tiles, enabling a potential viewer to run with maximum performance by offloading all generation to a one-time, offline process.

## Project Structure

```
Realistic-Modular-Pygame-World-Generator/
├── bake_world.py                   # Standalone, highly parallel script for offline world rendering.
│
├── examples/basic_viewer/          # The interactive world design tool.
│   ├── main.py                     # Application entry point and main loop.
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
    ├── config.py                   # Default internal constants for the generator.
    └── color_maps.py               # Shared color mapping utilities.
```

## System Architecture: The Two-Tier Workflow

The project now operates using a powerful two-tier workflow that separates the creative design process from the final, high-performance output.

### Tier 1: The Live Editor

When you run `main.py`, you enter the Live Editor. Its purpose is rapid design and iteration.
*   **Single Preview Surface:** Instead of rendering thousands of chunks, the editor generates one single, moderately-sized image of the entire world.
*   **Real-Time Feedback:** This preview image is regenerated whenever you change a parameter using the UI sliders, providing instant visual feedback.
*   **Pixelated Zoom:** Zooming is fast but pixelated, as it simply scales the single preview image. This is by design to maintain interactivity.
*   **Non-Destructive:** All changes are made in memory. The original `config.json` is never modified.

### Tier 2: The Offline Baker

When you are satisfied with your world design in the editor, you can use the "Bake World" feature.
*   **Asynchronous & Parallel:** Clicking the "Bake World" button launches the `bake_world.py` script as a separate, non-blocking background process that utilizes all available CPU cores for maximum speed.
*   **Configuration Snapshot:** The baker is given a temporary configuration file containing the exact parameters you set with the sliders.
*   **Highly Optimized Output:** The baker script generates full-resolution data for every chunk and saves it using a tiered, lossless compression strategy (including content deduplication and PNG palettization) to minimize storage size.
*   **Performance Goal:** This fast, one-time process does all the heavy lifting upfront, enabling a future "Baked Viewer" to load these images for a perfectly smooth, high-detail experience with zero generation overhead.

### The Generation Pipeline: From Seed to Climate

The underlying data generation is now fully dynamic to ensure that all climate effects respond in real-time to terrain changes in the editor. The pipeline is always executed in this order for every frame:
1.  **Elevation:** The foundational terrain is generated. This is the single source of truth for the frame.
2.  **Temperature (Celsius):** Calculated as a function of noise, altitude, and latitude.
3.  **Humidity (Absolute, g/m³):** This is now an emergent property calculated **on-the-fly** from the final elevation and temperature data:
    *   **Water Sources:** The system first identifies all bodies of water based on the final elevation map.
    *   **Distance-to-Water:** A distance map is calculated in real-time.
    *   **Rain Shadow:** A moisture occlusion map is calculated based on prevailing winds and mountain ranges.
    *   **Final Humidity:** The absolute humidity is determined by combining the air's temperature-driven capacity for moisture with the environment's availability of moisture (from coasts and rain shadows).
4.  **Biome & Final Colors:** The final terrain color (ice, snow, lush grass, sand desert, etc.) is determined by applying a set of prioritized rules based on the final elevation, temperature, and humidity.

## Configuration Deep Dive

The Live Editor allows you to modify key parameters in real-time. Other advanced parameters can be tuned in `world_generator/config.py`.

| Parameter                         | Unit    | Default | UI Control        | Description                                                                                                                            |
| --------------------------------- | ------- | ------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `TARGET_SEA_LEVEL_TEMP_C`         | Celsius | `15.0`  | Slider            | The "thermostat" for the world. Higher values create warmer worlds.                                                                    |
| `DETAIL_NOISE_WEIGHT`             | float   | `0.25`  | Slider            | How much the detail layer influences the base terrain. Higher values create rougher, more mountainous worlds.                          |
| `LAPSE_RATE_C_PER_UNIT_ELEVATION` | °C / ΔE | `40.0`  | Slider            | Temperature drop for a full elevation change. Controls how cold mountains get.                                                         |
| `TERRAIN_BASE_FEATURE_SCALE_KM`   | km      | `40.0`  | Slider            | The size of continents. Increase for larger, more sprawling landmasses.                                                                |
| `TERRAIN_AMPLITUDE`               | float   | `2.5`   | Slider            | The sharpness of the terrain. Higher values create more dramatic, steeper mountains and deeper valleys.                                |
| `POLAR_TEMPERATURE_DROP_C`        | Celsius | `30.0`  | Slider            | The total temperature difference between the equator and the poles.                                                                    |
| `world_width_chunks`              | chunks  | `800`   | Text Input        | The width of the world in chunks. Requires clicking "Apply Size Changes".                                                              |
| `world_height_chunks`             | chunks  | `450`   | Text Input        | The height of the world in chunks. Requires clicking "Apply Size Changes".                                                               |
| `SNOW_LINE_TEMP_C`                | Celsius | `0.0`   | Config File       | The temperature at or below which snow appears on land.                                                                                |
| `ICE_FORMATION_TEMP_C`            | Celsius | `-2.0`  | Config File       | The temperature at or below which water freezes into ice.                                                                              |
| `PREVAILING_WIND_DIRECTION_DEGREES` | Degrees | `180.0` | Config File       | The global wind direction (0=E, 90=N, 180=W, 270=S). Controls rain shadows.                                                            |
| `HUMIDITY_COASTAL_FALLOFF_RATE`   | float   | `2.5`   | Config File       | A power factor for humidity dissipation. Higher values create a very sharp drop-off from the coast.                                    |
| `BIOME_THRESHOLDS`                | dict    | varies  | Config File       | A dictionary of temperature and humidity values that control all biome transitions (e.g., where lush grass becomes normal grass).      |

## Performance & Optimization

*   **Live Editor:** The editor's responsiveness is determined by the `PREVIEW_RESOLUTION_WIDTH` and `PREVIEW_RESOLUTION_HEIGHT` constants in `main.py`. The on-the-fly climate calculations are performed on this preview-sized array, maintaining interactivity.
*   **Baking:** The baking process is a highly optimized, CPU-bound task that is parallelized across all available cores. Its duration is primarily determined by the total number of chunks and the raw processing power of the host machine.

### The Optimization Journey & Architectural Lessons

The current high performance of the `bake_world.py` script is the result of a rigorous optimization process that involved overcoming several critical bottlenecks. This journey provides valuable lessons for future development.

**Successful Optimizations Implemented:**
1.  **Parallelization:** The core task was parallelized using Python's `multiprocessing` module, distributing the work of processing individual chunks across all available CPU cores.
2.  **Advanced Compression:** A tiered, lossless compression strategy was implemented using the Pillow library. This includes content deduplication via hashing, 1x1 pixel compression for uniform chunks, and 8-bit PNG palettization for low-color chunks, dramatically reducing storage size.
3.  **Data Quantization:** The smooth gradients of temperature and humidity data were quantized into discrete steps (e.g., one step per degree Celsius). This massively increased the effectiveness of content deduplication with minimal impact on visual quality.
4.  **On-the-Fly Correctness:** The architecture was refactored to calculate climate data (distance-to-water, rain shadows) in real-time. This fixed a critical architectural flaw where climate was not responding to terrain changes, trading a negligible performance cost for a massive gain in correctness.
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
    ```sh
    python examples/basic_viewer/main.py
    ```

### How to Use the Editor

*   **Live Parameter Tuning:** Use the sliders on the right-hand panel to adjust world parameters. The preview will update automatically.
*   **Custom World Size:** Enter new dimensions (in chunks) into the text boxes and click **"Apply Size Changes"** to re-initialize the world.
*   **Real-Time Data:** Hover the mouse over the map to see a **real-time data tooltip** showing the terrain type, temperature, and humidity at that exact point.
*   **Baking Your World:** When you are satisfied with the design, click **"Bake World"**. This will start the fast, offline rendering process in the background. The editor will remain responsive.
*   **Standard Controls:**
    *   **Pan:** `W`, `A`, `S`, `D` keys
    *   **Zoom:** Mouse Wheel Up/Down
    *   **Cycle View Mode:** `V` key (Terrain, Temperature, Humidity)
    *   **Exit:** `ESC` key or close the window

## Using the Generator in Your Project

The core library in the `world_generator/` folder remains fully independent. You can use it in any project for procedural data generation, as shown in the minimal example below:

```python
import numpy as np
import logging
from world_generator.generator import WorldGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("my_simulation")

my_config = { "seed": 999, "target_sea_level_temp_c": 25.0 }
world_gen = WorldGenerator(config=my_config, logger=logger)

# ... request data from world_gen ...
```

## Roadmap & Future Features

*   **Baked World Viewer Mode:** The logical counterpart to the baker. A new application mode to load and explore a pre-baked world at maximum performance and detail.
*   **Advanced Biome Detailing:** A system to classify areas into more specific biomes (e.g., Tundra, Desert, Rainforest) and potentially spawn representative flora or features.
*   **Hydraulic Erosion & River Networks:** An algorithm to simulate water flow, carving rivers from mountains to the sea.

## Architectural Principles

This project is developed under a strict set of internal rules that enforce high code quality, maintainability, and robustness. Key principles include:

*   **No Magic Numbers (Rule 1):** Configuration is strictly separated from code.
*   **Structured Logging (Rule 2):** All runtime output uses the Python `logging` module.
*   **SOLID Principles (Rule 7):** The codebase is highly modular and adheres to SOLID principles.
*   **Deterministic by Default (Rule 12):** All randomness is controlled by a single master seed.

## Contributing

Contributions are welcome. Please adhere to the established architectural principles when proposing changes.

## Dependencies

*   `pygame-ce`: Used by the `basic_viewer` example for rendering and UI.
*   `pygame-gui`: Used for the interactive UI elements in the editor.
*   `numpy`: The core dependency for all numerical operations.
*   `numba`: Used to JIT-compile the performance-critical Perlin noise function.
*   `scipy`: Used for the Euclidean Distance Transform to enable the realistic humidity model.
*   `Pillow`: Used for robust, high-performance image saving in the parallel baker.
*   `tqdm`: Used to display a progress bar for the command-line baker.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.