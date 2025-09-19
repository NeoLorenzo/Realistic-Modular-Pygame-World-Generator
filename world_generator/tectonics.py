# world_generator/tectonics.py

"""
================================================================================
TECTONIC PLATE GENERATION
================================================================================
This module provides functions for generating a tectonic plate map using
Voronoi diagrams. It is a scientifically-grounded abstraction (Rule 8) used
to create realistic, large-scale geological features like mountain ranges.

Data Contract:
---------------
- Inputs:
    - World dimensions, seed, number of plates.
    - NumPy arrays of coordinates.
- Outputs:
    - plate_ids (np.ndarray): An integer array where each value is the ID of the
      tectonic plate at that location.
    - influence_map (np.ndarray): A float array [0, 1] indicating proximity to a
      plate boundary (1 = on the boundary, 0 = center of a plate).
- Side Effects: None.
================================================================================
"""
import numpy as np
from scipy.spatial import cKDTree

def generate_plate_points(world_width_cm: float, world_height_cm: float, num_plates: int, seed: int) -> np.ndarray:
    """Generates the center points for tectonic plates deterministically."""
    rng = np.random.default_rng(seed)
    points_x = rng.uniform(0, world_width_cm, num_plates)
    points_y = rng.uniform(0, world_height_cm, num_plates)
    return np.column_stack((points_x, points_y))

def get_voronoi_data(
    x_coords: np.ndarray, y_coords: np.ndarray,
    world_width_cm: float, world_height_cm: float,
    num_plates: int, seed: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Performs the expensive Voronoi calculation to determine plate IDs and
    distances to the two nearest plate centers.
    """
    # 1. Generate the Voronoi points for the plates.
    plate_points = generate_plate_points(world_width_cm, world_height_cm, num_plates, seed)
    
    # 2. Use a cKDTree for highly efficient nearest-neighbor lookups.
    tree = cKDTree(plate_points)
    
    # 3. For each coordinate, find the two nearest plate points.
    query_points = np.column_stack((x_coords.ravel(), y_coords.ravel()))
    dist, indices = tree.query(query_points, k=2)
    
    dist1 = dist[:, 0].reshape(x_coords.shape)
    dist2 = dist[:, 1].reshape(x_coords.shape)
    plate_ids = indices[:, 0].reshape(x_coords.shape)

    return plate_ids, dist1, dist2

def calculate_influence_map(dist1: np.ndarray, dist2: np.ndarray, influence_radius_cm: float) -> np.ndarray:
    """
    Calculates the tectonic influence map from pre-computed Voronoi distances.
    This is a fast, pure-numpy operation.
    """
    # 1. Calculate the distance to the plate boundary.
    # An approximation of the true Voronoi edge distance is half the
    # difference in distances to the two nearest plate centers.
    boundary_dist = (dist2 - dist1) / 2.0

    # 2. Create the influence map.
    # The influence is 1.0 at the boundary and falls off to 0.0 as we move
    # away from it, based on the specified radius.
    influence_map = 1.0 - np.clip(boundary_dist / influence_radius_cm, 0.0, 1.0)
    
    # 3. Apply a smooth fade (cosine curve) to make the falloff more natural.
    influence_map = (1 - np.cos(influence_map * np.pi)) / 2

    return influence_map