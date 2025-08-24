# world_generator/noise.py

"""
================================================================================
NOISE GENERATION UTILITIES
================================================================================
This module provides functions for generating 2D Perlin noise. It is designed
to be a pure, stateless utility.

Data Contract:
---------------
- Inputs:
    - p: A pre-shuffled NumPy permutation table (int array).
    - x, y: NumPy arrays of coordinates.
    - octaves, persistence, lacunarity: Standard noise parameters.
- Outputs:
    - A NumPy array of noise values (typically in the range [-1, 1]).
- Side Effects: None.
- Invariants: The shape of the output array matches the shape of input x and y.
================================================================================
"""

import numpy as np
from numba import njit

# Pre-defined gradient vectors for performance.
_GRADIENT_VECTORS = np.array([[0, 1], [0, -1], [1, 0], [-1, 0]])

@njit
def _lerp(a, b, x):
    "Linear interpolation."
    return a + x * (b - a)

@njit
def _fade(t):
    "6t^5 - 15t^4 + 10t^3"
    return t * t * t * (t * (t * 6 - 15) + 10)

@njit
def _gradient(h, x, y):
    """Calculates the dot product between a gradient vector and coordinates."""
    g = _GRADIENT_VECTORS[h % 4]
    # Use explicit indexing for Numba compatibility
    return g[0] * x + g[1] * y

@njit
def perlin_noise_2d(p, x, y, octaves=1, persistence=0.5, lacunarity=2.0):
    """
    Generate 2D Perlin noise using a pre-computed permutation table.
    This function is JIT-compiled with Numba for maximum performance.
    It uses explicit loops, which Numba compiles to efficient machine code.
    """
    rows, cols = x.shape
    total_noise = np.zeros((rows, cols))
    
    for i in range(rows):
        for j in range(cols):
            noise_val = 0.0
            amplitude = 1.0
            frequency = 1.0
            
            for _ in range(octaves):
                x_sample = x[i, j] * frequency
                y_sample = y[i, j] * frequency

                xi = int(np.floor(x_sample))
                yi = int(np.floor(y_sample))
                
                xf = x_sample - xi
                yf = y_sample - yi
                
                u = _fade(xf)
                v = _fade(yf)

                px0 = xi % 256
                px1 = (px0 + 1) % 256
                py0 = yi % 256
                py1 = (py0 + 1) % 256

                # Numba requires scalar indexing
                idx00 = p[p[px0] + py0]
                idx01 = p[p[px0] + py1]
                idx10 = p[p[px1] + py0]
                idx11 = p[p[px1] + py1]

                g00 = _gradient(idx00, xf, yf)
                g01 = _gradient(idx01, xf, yf - 1)
                g10 = _gradient(idx10, xf - 1, yf)
                g11 = _gradient(idx11, xf - 1, yf - 1)

                x1 = _lerp(g00, g10, u)
                x2 = _lerp(g01, g11, u)
                octave_noise = _lerp(x1, x2, v)
                
                noise_val += octave_noise * amplitude
                amplitude *= persistence
                frequency *= lacunarity
                
            total_noise[i, j] = noise_val

    return total_noise