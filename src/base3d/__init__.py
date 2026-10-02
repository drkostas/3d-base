"""Headless pictures of 3D meshes, and an honest health check for exported STL files."""
from .mesh import load_clean, report, surface_points, voids
from .show import frame_on, render, save_png, sheet, tile

__version__ = "0.1.0"
__all__ = ["frame_on", "load_clean", "render", "report", "save_png", "sheet", "surface_points", "tile", "voids"]
