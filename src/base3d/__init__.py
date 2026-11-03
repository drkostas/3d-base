"""Headless pictures of 3D meshes, and an honest health check for exported STL files."""
from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("3d-base")  # the one place the version is written is pyproject.toml
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0+unknown"
del _version, PackageNotFoundError

from .mesh import load_clean, report, surface_points, voids
from .nozzle import Nozzle
from .show import frame_on, render, save_png, sheet, tile

__all__ = ["Nozzle", "frame_on", "load_clean", "render", "report", "save_png", "sheet", "surface_points", "tile", "voids"]
