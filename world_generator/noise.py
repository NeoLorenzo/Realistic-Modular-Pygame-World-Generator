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

# Pre-defined gradient vectors for performance.
_GRADIENT_VECTORS = np.array([[0, 1], [0, -1], [1, 0], [-1, 0]])

def _lerp(a, b, x):
    "Linear interpolation."
    return a + x * (b - a)

def _fade(t):
    "6t^5 - 15t^4 + 10t^3"
    return t * t * t * (t * (t * 6 - 15) + 10)

def _gradient(h, x, y):
    """Calculates the dot product between a gradient vector and coordinates."""
    g = _GRADIENT_VECTORS[h % 4]
    return g[..., 0] * x + g[..., 1] * y

def perlin_noise_2d(p, x, y, octaves=1, persistence=0.5, lacunarity=2.0):
    """
    Generate 2D Perlin noise using a pre-computed permutation table.

    Args:
        p (np.ndarray): The pre-shuffled permutation table.
        x (np.ndarray): 2D array of x-coordinates.
        y (np.ndarray): 2D array of y-coordinates.
        octaves (int): The number of noise layers to combine.
        persistence (float): The factor by which amplitude decreases each octave.
        lacunarity (float): The factor by which frequency increases each octave.

    Returns:
        np.ndarray: A 2D array of Perlin noise values.
    """
    total_noise = np.zeros(x.shape)
    amplitude = 1.0
    
    for _ in range(octaves):
        xi = np.floor(x).astype(int)
        yi = np.floor(y).astype(int)
        xf = x - xi
        yf = y - yi
        u = _fade(xf)
        v = _fade(yf)

        px0 = xi % 256
        px1 = (px0 + 1) % 256
        py0 = yi % 256
        py1 = (py0 + 1) % 256

        g00 = _gradient(p[p[px0] + py0], xf, yf)
        g01 = _gradient(p[p[px0] + py1], xf, yf - 1)
        g10 = _gradient(p[p[px1] + py0], xf - 1, yf)
        g11 = _gradient(p[p[px1] + py1], xf - 1, yf - 1)

        x1 = _lerp(g00, g10, u)
        x2 = _lerp(g01, g11, u)
        octave_noise = _lerp(x1, x2, v)
        
        total_noise += octave_noise * amplitude
        amplitude *= persistence
        
        x *= lacunarity
        y *= lacunarity

    return total_noise