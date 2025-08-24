# Realistic Modular Pygame World Generator

A standalone Python library for generating complex, scientifically-grounded worlds. Designed from the ground up for modularity and performance, this package allows developers to seamlessly integrate a powerful world-generation engine into any Python-based simulation, game, or project. It provides a clear separation between the data generation backend and an optional, efficient Pygame-based rendering frontend.

## Table of Contents

*   [Core Philosophy](#core-philosophy)
    *   [1. True Modularity (Plug-and-Play)](#1-true-modularity-plug-and-play)
    *   [2. Scientifically-Grounded Realism](#2-scientifically-grounded-realism)
    *   [3. Efficiency and Performance](#3-efficiency-and-performance)
*   [Project Structure](#project-structure)
*   [How It Works: A Deeper Dive](#how-it-works-a-deeper-dive)
    *   [Configuration System](#configuration-system)
    *   [The `WorldGenerator` Core](#the-worldgenerator-core)
    *   [The `basic_viewer` Example](#the-basic_viewer-example)
*   [Getting Started](#getting-started)
    *   [Prerequisites](#prerequisites)
    *   [Installation & Running the Example](#installation--running-the-example)
    *   [Controls](#controls)
*   [Using the Generator in Your Project](#using-the-generator-in-your-project)
*   [Architectural Principles](#architectural-principles)
*   [Dependencies](#dependencies)

## Core Philosophy

The primary objective of this project is to create a world generator that is not just a feature of a larger application, but an atomic, reusable, and high-quality component. The design is built on three pillars:

### 1. True Modularity (Plug-and-Play)

The generator is architected as a self-contained Python package (`world_generator/`) that has no knowledge of the application consuming it. This is the cornerstone of the project.

*   **Decoupled Backend:** The core `WorldGenerator` class is a data-only engine. It works exclusively with NumPy arrays and has zero dependencies on Pygame or any other visualization library. You can use it in a headless server simulation, a data analysis script, or a 3D engine with equal ease.
*   **Dependency Injection (Rule 7, DIP):** The generator is initialized by passing in its dependencies—a configuration dictionary and a logger. It does not rely on global state or hardcoded file paths, making it trivial to drop into any existing project.
*   **Clear Data Contract:** The package exposes a simple, well-documented interface for requesting world data (e.g., `get_elevation()`, `get_temperature()`, `get_humidity()`). Its inputs and outputs are explicit NumPy arrays, ensuring predictable and testable behavior.

To prove this model, the repository includes a sister folder, `examples/basic_viewer/`, which contains a complete Pygame application. This viewer is a **consumer** of the `world_generator` library, not a part of it. It demonstrates how to import, instantiate, and visualize the data from the generator, serving as a practical blueprint for integration.

### 2. Scientifically-Grounded Realism

The goal is not just to create random noise, but to generate worlds with believable and emergent characteristics, guided by a "realism first" principle (Rule 3).

*   **Layered Simulation:** The world is built from multiple, independent layers—elevation, temperature, and humidity. Each is generated using its own unique but deterministic noise function derived from a single **master seed** (Rule 12). This ensures that for a given seed, the world is perfectly reproducible.
*   **Procedural Generation:** The generator uses a robust implementation of Perlin noise (`world_generator/noise.py`) to create the natural-looking fractal patterns found in real-world terrain and other natural phenomena.
*   **Foundation for Complexity:** This generator is designed to be the foundational canvas for more complex simulations. The data it provides (e.g., elevation, temperature gradients) can directly influence higher-level systems like biome distribution, resource placement, or AI agent behavior.

### 3. Efficiency and Performance

A world generator is useless if it's too slow to be interactive. Performance is a key design consideration, driven by profiling rather than guesswork (Rule 11).

*   **Vectorized Operations (Rule 11.2):** All heavy-duty mathematical calculations are performed on NumPy arrays. This leverages highly-optimized, pre-compiled C code for maximum speed, avoiding slow Python loops in critical paths.
*   **Chunk-Based System:** The world is processed in discrete "chunks." Data is only ever generated for the specific chunks that are requested. The included `basic_viewer` example only renders chunks visible to the camera, allowing for massive worlds without incurring prohibitive performance costs.
*   **Intelligent Caching:** The example renderer (`examples/basic_viewer/renderer.py`) implements a cache for chunk surfaces. Once a chunk's visual representation is generated, it is stored and reused, eliminating redundant calculations and scaling operations to ensure a smooth user experience during panning and zooming.

## Project Structure

The repository is organized with a clear separation between the core library and the example implementation.

```
Realistic-Modular-Pygame-World-Generator/
├── world_generator/                # The core, standalone, data-only library.
│   ├── __init__.py
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

## How It Works: A Deeper Dive

### Configuration System

The project uses a two-tiered configuration system to separate static constants from simulation-specific parameters (Rule 1).

1.  **Application Constants:** Default, fallback values are defined within the library in `world_generator/config.py`. These are considered internal to the generator.
2.  **Simulation Parameters:** The `basic_viewer` application loads all its parameters from `examples/basic_viewer/config.json`. This file defines everything needed for a specific run, such as screen resolution, camera speeds, and the world generation seed. This allows for different experiments without modifying any code.

### The `WorldGenerator` Core

The heart of the library is the `WorldGenerator` class in `world_generator/generator.py`.

*   **Initialization:** It is instantiated with a user-provided configuration dictionary and a Python logger instance. It merges the user's config with its internal defaults, making the user's settings take precedence.
*   **Seeding:** It uses the `seed` from its configuration to initialize a master random number generator. All subsequent noise generation is derived deterministically from this seed.
*   **Data Access:** It exposes public methods like `get_elevation(x, y)`, `get_temperature(x, y)`, and `get_humidity(x, y)`. These methods accept NumPy arrays of coordinates and return a corresponding NumPy array of data, normalized to a range of.

### The `basic_viewer` Example

The `main.py` file in the viewer acts as the **composition root** of the application, demonstrating the Dependency Injection principle (Rule 7, DIP).

1.  **Loading:** It first loads the configuration from `config.json` and sets up logging from `logging_config.json`.
2.  **Instantiation:** It creates an instance of the `WorldGenerator`, passing it the world parameters and a logger.
3.  **Dependency Injection:** It then creates instances of the `Camera` and `WorldRenderer`, injecting the `WorldGenerator` instance into them. This is a key design choice: the renderer and camera are not tightly coupled to the generator; they simply query its public properties and methods.
4.  **Main Loop:** The application enters a standard Pygame loop, handling user input, updating state, and drawing the world. In the draw call, the `WorldRenderer` asks the `Camera` for the visible world area, calculates which chunks are needed, requests the corresponding data from the `WorldGenerator`, and renders it to the screen.

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
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
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
*   **Cycle View Mode:** `V` key (switches between Terrain, Temperature, and Humidity)
*   **Exit:** `ESC` key or close the window

## Using the Generator in Your Project

Because the `world_generator` is a standalone package, using it in your own project is straightforward. Simply ensure the `world_generator` directory is in your Python path.

Here is a minimal, non-Pygame example of how to use the library:

```python
import numpy as np
import logging
from world_generator.generator import WorldGenerator

# 1. Set up a basic logger for the generator to use
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("my_simulation")

# 2. Define your simulation parameters (at minimum, a seed)
my_config = {
    "seed": 12345,
    "noise_scale": 25000.0,
    "noise_octaves": 5
}

# 3. Instantiate the generator, injecting the config and logger
world_gen = WorldGenerator(config=my_config, logger=logger)

# 4. Request data for a specific area.
# Let's get elevation for a 10x10 grid at world coordinates (0,0) to (100,100).
x_coords, y_coords = np.meshgrid(
    np.linspace(0, 100, 10),
    np.linspace(0, 100, 10)
)
elevation_data = world_gen.get_elevation(x_coords, y_coords)

print("--- Generated 10x10 Elevation Grid ---")
# Print with fixed precision for readability
with np.printoptions(precision=3, suppress=True):
    print(elevation_data)

# You can now use this `elevation_data` array for any purpose in your application.
```

## Architectural Principles

This project is developed under a strict set of internal rules that enforce high code quality, maintainability, and robustness. Key principles include:

*   **No Magic Numbers (Rule 1):** Configuration is strictly separated from code.
*   **Structured Logging (Rule 2):** All runtime output uses the Python `logging` module. No `print()` statements are used in the core logic.
*   **SOLID Principles (Rule 7):** The codebase is highly modular and adheres to SOLID principles, especially Single Responsibility and Dependency Inversion.
*   **Deterministic by Default (Rule 12):** All randomness is controlled by a single master seed, ensuring that simulations are fully reproducible.
*   **Performance by Profiling (Rule 11):** Performance optimizations are guided by data from profiling tools, not by assumption.

## Dependencies

The main dependencies for the project and its example viewer are:

*   `pygame`: Used by the `basic_viewer` example for rendering and window management.
*   `numpy`: The core dependency for the `world_generator` library, used for all numerical operations.