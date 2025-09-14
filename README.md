# Realistic Modular Pygame World Generator

A standalone Python library for generating complex, scientifically-grounded worlds. Designed from the ground up for modularity, performance, and realism, this package allows developers to seamlessly integrate a powerful world-generation engine into any Python-based simulation, game, or project.

The core philosophy is to create a data-first engine that produces emergent, believable climate systems based on interconnected physical principles, rather than disconnected layers of noise.

## Table of Contents

*   [Core Philosophy](#core-philosophy)
    *   [1. True Modularity (Plug-and-Play)](#1-true-modularity-plug-and-play)
    *   [2. Scientifically-Grounded Realism](#2-scientifically-grounded-realism)
    *   [3. Efficiency and Performance](#3-efficiency-and-performance)
*   [Project Structure](#project-structure)
*   [System Architecture & Generation Pipeline](#system-architecture--generation-pipeline)
    *   [The Generation Pipeline: From Seed to Climate](#the-generation-pipeline-from-seed-to-climate)
    *   [The Configuration System](#the-configuration-system)
    *   [The `WorldGenerator` Core](#the-worldgenerator-core)
    *   [The `basic_viewer` Example](#the-basic_viewer-example)
*   [Configuration Deep Dive](#configuration-deep-dive)
*   [Performance Considerations](#performance-considerations)
*   [Getting Started](#getting-started)
    *   [Prerequisites](#prerequisites)
    *   [Installation & Running the Example](#installation--running-the-example)
    *   [Controls](#controls)
*   [Using the Generator in Your Project](#using-the-generator-in-your-project)
*   [Roadmap & Future Features](#roadmap--future-features)
*   [Architectural Principles](#architectural-principles)
*   [Contributing](#contributing)
*   [Dependencies](#dependencies)
*   [License](#license)

## Core Philosophy

The primary objective of this project is to create a world generator that is not just a feature of a larger application, but an atomic, reusable, and high-quality component. The design is built on three pillars:

### 1. True Modularity (Plug-and-Play)

The generator is architected as a self-contained Python package (`world_generator/`) that has no knowledge of the application consuming it.

*   **Decoupled Backend:** The core `WorldGenerator` class is a data-only engine. It works exclusively with NumPy arrays and has zero dependencies on Pygame or any other visualization library.
*   **Dependency Injection (Rule 7, DIP):** The generator is initialized by passing in its dependencies—a configuration dictionary and a logger. It does not rely on global state or hardcoded file paths.
*   **Clear Data Contract:** The package exposes a simple, well-documented interface for requesting world data. Its inputs are NumPy arrays of coordinates, and its outputs are NumPy arrays in **real-world scientific units** (e.g., Celsius for temperature, g/m³ for humidity).

### 2. Scientifically-Grounded Realism

The goal is to generate worlds with believable and emergent characteristics, guided by a "realism first" principle (Rule 3).

*   **Interconnected Climate Model:** Climate is an emergent property of the terrain. Temperature is realistically affected by altitude (adiabatic lapse rate), and humidity is driven by a pre-calculated **distance-to-water map** and the air's temperature-dependent saturation point.
*   **Procedural Generation:** The generator uses a robust implementation of Perlin noise to create the natural-looking fractal patterns that serve as the foundation for all layers.
*   **Reproducibility:** The entire generation process is derived from a single **master seed** (Rule 12), ensuring that for a given seed and configuration, the world is perfectly reproducible.

### 3. Efficiency and Performance

Performance is a key design consideration, driven by profiling rather than guesswork (Rule 11).

*   **Vectorized Operations (Rule 11.2):** All heavy-duty mathematical calculations are performed on NumPy arrays, leveraging highly-optimized, pre-compiled C code.
*   **Intelligent Pre-computation:** For complex global effects like coastal humidity, the generator performs a one-time, low-resolution analysis of the entire world at startup. This allows for extremely fast, high-quality results during interactive use.
*   **JIT Compilation:** The most performance-critical code, the Perlin noise algorithm, is Just-In-Time compiled to near-native speed using Numba.

## Project Structure

```
Realistic-Modular-Pygame-World-Generator/
├── world_generator/                # The core, standalone, data-only library.
│   ├── generator.py                # Contains the main WorldGenerator class.
│   ├── noise.py                    # Optimized Perlin noise implementation.
│   └── config.py                   # Default internal constants for the generator.
│
├── examples/basic_viewer/          # A sample Pygame application using the library.
│   ├── main.py                     # Application entry point and main loop.
│   ├── renderer.py                 # Pygame-specific rendering logic.
│   ├── camera.py                   # Handles view transformations (pan/zoom).
│   ├── config.json                 # Simulation parameters for the viewer.
│   └── logging_config.json         # Logging configuration for the viewer.
│
├── requirements.txt                # Project dependencies.
└── README.md                       # This file.
```

## System Architecture & Generation Pipeline

### The Generation Pipeline: From Seed to Climate

The generator follows a strict, ordered pipeline to ensure that climate is an emergent property of the terrain. Data for a given point is generated on-demand, but always in this sequence:

1.  **Elevation:** Two layers of Perlin noise are combined to form the base terrain. A low-frequency "base" layer creates continents, and a high-frequency "detail" layer adds mountains and roughness. The result is a normalized `[0, 1]` elevation value. This is the foundational data upon which everything else is built.

2.  **Distance-to-Water (Pre-computed):** During the `WorldGenerator`'s initialization, it analyzes the entire world's low-resolution elevation map. It identifies all water bodies and uses a Euclidean Distance Transform (`scipy.ndimage.distance_transform_edt`) to create a "distance map," where the value of each point is its real-world distance to the nearest coast. This map is a critical, performance-enabling abstraction (Rule 8).

3.  **Temperature (Celsius):** When temperature is requested, the generator first calculates a base sea-level temperature using Perlin noise, centered around the `TARGET_SEA_LEVEL_TEMP_C` from the config. It then fetches the **elevation** for the same point and applies the **adiabatic lapse rate**, reducing the temperature realistically. The final result is a value in Celsius.

4.  **Humidity (Absolute, g/m³):** This is the final and most complex step, combining all previous data:
    *   It first fetches the final **temperature (Celsius)**.
    *   Using a scientific formula (an abstraction of the Clausius-Clapeyron relation), it calculates the **saturation humidity**—the maximum amount of water vapor the air can hold at that temperature.
    *   It then fetches the **distance-to-water** value from the pre-computed map. This determines the **relative humidity** (from 100% at the coast to 0% far inland).
    *   A final layer of Perlin noise is applied to add local variation.
    *   The final result is the **absolute humidity** in grams per cubic meter (g/m³), a direct product of the interconnected terrain and climate systems.

### The Configuration System

The project uses a two-tiered configuration system (Rule 1):

1.  **Application Constants (`world_generator/config.py`):** This file contains the default, fallback values for the simulation. It is the canonical source for all tunable parameters and their real-world units.
2.  **Simulation Parameters (`examples/basic_viewer/config.json`):** This file allows a user to override any of the default constants for a specific run, enabling experiments without modifying the core codebase.

### The `WorldGenerator` Core

The `WorldGenerator` class is the heart of the library. It is initialized with a configuration dictionary and a logger. Its public methods (`get_elevation`, `get_temperature`, `get_humidity`) serve data in real-world units, enforcing a clean data contract.

### The `basic_viewer` Example

The `main.py` file in the viewer acts as the **composition root**. It instantiates the `WorldGenerator` and injects it as a dependency into the `WorldRenderer`. The renderer's job is to request data from the generator and **normalize** it from its real-world units (e.g., -50°C to +50°C) back to a `[0, 1]` range suitable for mapping to a color gradient.

## Configuration Deep Dive

The following key parameters in `world_generator/config.py` can be overridden in `config.json` to dramatically alter the generated world:

| Parameter                         | Unit    | Default | Description                                                                                                                            |
| --------------------------------- | ------- | ------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `TARGET_SEA_LEVEL_TEMP_C`         | Celsius | `15.0`  | The "thermostat" for the world. The average temperature at sea level. Higher values create warmer worlds.                              |
| `LAPSE_RATE_C_PER_UNIT_ELEVATION` | °C / ΔE | `40.0`  | Temperature drop for a full elevation change. Controls how cold mountains get.                                                         |
| `MAX_COASTAL_DISTANCE_KM`         | km      | `150.0` | The distance over which humidity falls from coastal to arid levels. A larger value creates wider, more humid coastal regions.            |
| `SEASONAL_VARIATION_C`            | Celsius | `30.0`  | The temperature swing (`+/- 15°C`) from the target average, driven by noise. Higher values create more extreme hot and cold zones.      |
| `TERRAIN_BASE_FEATURE_SCALE_KM`   | km      | `40.0`  | The size of continents. Increase for larger, more sprawling landmasses.                                                                |
| `TERRAIN_DETAIL_FEATURE_SCALE_KM` | km      | `2.5`   | The size of mountains and coastal features.                                                                                            |
| `DETAIL_NOISE_WEIGHT`             | float   | `0.25`  | How much the detail layer influences the base terrain. Higher values create rougher, more mountainous worlds.                          |

## Performance Considerations

The generator is highly optimized, but performance can be influenced by configuration:
*   **`DISTANCE_MAP_RESOLUTION_FACTOR`**: This setting (default `0.1`) has the most significant impact on startup time. A higher value (e.g., `0.25`) will create a more accurate distance-to-water map at the cost of a longer one-time pre-computation. A lower value will speed up startup but may result in a blockier, less precise humidity gradient. The core interactive loop is unaffected.
*   **Noise Octaves**: Increasing `BASE_NOISE_OCTAVES` or `DETAIL_NOISE_OCTAVES` will add visual complexity but has a direct, linear impact on the performance of all data generation calls.

## Getting Started

### Prerequisites

*   Python 3.8+
*   Git

### Installation & Running the Example

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
4.  **Run the basic viewer application:**
    ```sh
    python examples/basic_viewer/main.py
    ```

### Controls

*   **Pan:** `W`, `A`, `S`, `D` keys
*   **Zoom:** Mouse Wheel Up/Down
*   **Cycle View Mode:** `V` key (Terrain, Temperature, Humidity)
*   **Exit:** `ESC` key or close the window

## Using the Generator in Your Project

A minimal, non-Pygame example of using the library:

```python
import numpy as np
import logging
from world_generator.generator import WorldGenerator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("my_simulation")

my_config = { "seed": 999, "target_sea_level_temp_c": 25.0 }
world_gen = WorldGenerator(config=my_config, logger=logger)

x_coords, y_coords = np.meshgrid(
    np.linspace(1000000, 1001000, 5), # Coords are in cm
    np.linspace(1000000, 1001000, 5)
)
temperature_data_celsius = world_gen.get_temperature(x_coords, y_coords)

print("--- Generated 5x5 Temperature Grid (in Celsius) ---")
with np.printoptions(precision=2, suppress=True):
    print(temperature_data_celsius)
```

## Roadmap & Future Features

This generator provides a strong foundation for more complex simulations. Future development will focus on adding new, interconnected layers:

*   **Biome Generation:** A system to classify areas based on their final elevation, temperature, and humidity into distinct biomes (e.g., Tundra, Desert, Rainforest, etc.).
*   **Prevailing Winds & Rain Shadows:** A model for global wind patterns that would cause the windward side of mountain ranges to be wet and the leeward side to be arid deserts.
*   **Hydraulic Erosion & River Networks:** An algorithm to simulate water flow, carving rivers from mountains to the sea and forming lakes in basins.
*   **World Serialization:** Methods to save a generated world's seed and configuration, and potentially cache generated data to disk for faster re-loading.

## Architectural Principles

This project is developed under a strict set of internal rules that enforce high code quality, maintainability, and robustness. Key principles include:

*   **No Magic Numbers (Rule 1):** Configuration is strictly separated from code.
*   **Structured Logging (Rule 2):** All runtime output uses the Python `logging` module.
*   **SOLID Principles (Rule 7):** The codebase is highly modular and adheres to SOLID principles.
*   **Deterministic by Default (Rule 12):** All randomness is controlled by a single master seed.

## Contributing

Contributions are welcome. Please adhere to the established architectural principles when proposing changes. All new features should follow the incremental development pattern:
1.  Define a clear, testable hypothesis (Rule 6).
2.  Propose the change using the Before/After format (Rule 10).
3.  Ensure all new logic is covered by the project's principles of realism and performance.

## Dependencies

*   `pygame`: Used by the `basic_viewer` example for rendering.
*   `numpy`: The core dependency for all numerical operations.
*   `numba`: Used to JIT-compile the performance-critical Perlin noise function.
*   `scipy`: Used for the Euclidean Distance Transform to enable the realistic humidity model.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.