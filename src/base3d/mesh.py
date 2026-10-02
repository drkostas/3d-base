"""Load an exported STL and tell real defects from tessellation noise.

OpenCascade (and CAD tools built on it, such as build123d and CadQuery) writes zero-area triangles at
every sphere pole when it exports STL. They make a correct solid report `is_watertight=False` with
two or three extra bodies, so a plain `Sphere(20)` already looks broken. The slivers are an
artefact of the tessellation and it is correct to drop them.

Dropping them is also what makes the body count useful. Once the slivers are gone, a second body is
real. A shell with negative volume is a sealed cavity (a socket that never reached the surface, for
example), and that is a design defect worth catching before printing.
"""
from __future__ import annotations

import numpy as np
import trimesh

SLIVER_AREA = 1e-9

# Any fixed value. What matters is that it does not change between runs.
SAMPLE_SEED = 11


def clean(mesh: trimesh.Trimesh, sliver_area: float = SLIVER_AREA) -> trimesh.Trimesh:
    """Drop zero-area faces and merge the vertices they leave behind. Changes the mesh in place."""
    areas = mesh.area_faces
    if (areas <= sliver_area).any():
        mesh.update_faces(areas > sliver_area)
        mesh.remove_unreferenced_vertices()
        mesh.merge_vertices()
    return mesh


def load_clean(path):
    """Load a mesh file, drop tessellation slivers, and return (mesh, bodies).

    `bodies` is the list of connected pieces. After cleaning, more than one means more than one
    real piece.
    """
    m = trimesh.load(str(path))
    if isinstance(m, trimesh.Scene):  # a GLB or OBJ with several parts
        m = m.to_geometry() if hasattr(m, "to_geometry") else m.dump(concatenate=True)
    clean(m)
    bodies = m.split(only_watertight=False)
    return m, bodies


def voids(bodies):
    """Pieces with negative volume, which are closed cavities inside another piece."""
    return [b for b in bodies if b.volume < 0]


def surface_points(mesh, n=4000, seed=SAMPLE_SEED):
    """Points on the surface of a mesh, the same points on every run.

    An unseeded sample makes a design change between two builds of the same input whenever the
    points decide something (where a support or a contact goes, for example).
    """
    rng = np.random.default_rng(seed)
    try:
        return mesh.sample(n, seed=rng)
    except TypeError:  # older trimesh has no seed argument
        return mesh.sample(n)


def report(path) -> dict:
    """A short health report for a mesh file."""
    m, bodies = load_clean(path)
    return {
        "faces": int(len(m.faces)),
        "bodies": len(bodies),
        "voids": len(voids(bodies)),
        "watertight": bool(m.is_watertight),
        "volume": float(m.volume) if m.is_watertight else None,
        "extents": [float(x) for x in m.extents],
    }
