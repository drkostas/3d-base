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
    except TypeError:
        # Older trimesh has no seed argument. Sampling without one would break the promise above,
        # so sample here: pick faces by area, then a uniform point inside each.
        return _seeded_sample(mesh, n, rng)


def _seeded_sample(mesh, n, rng):
    cum = np.cumsum(np.asarray(mesh.area_faces, float))
    face = np.searchsorted(cum, rng.random(n) * cum[-1])
    tri = np.asarray(mesh.triangles, float)[face]
    r = rng.random((n, 2))
    over = r.sum(axis=1) > 1
    r[over] = 1 - r[over]                       # fold the square onto the triangle
    return tri[:, 0] + r[:, :1] * (tri[:, 1] - tri[:, 0]) + r[:, 1:] * (tri[:, 2] - tri[:, 0])


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


def as_written(mesh: trimesh.Trimesh, file_type: str = "stl", loose_mm3: float = 0.5) -> dict:
    """The mesh as a slicer will read it: written to `file_type`, read back, and counted.

    A boolean engine can leave two vertices a hundred millionth of a millimetre apart, kept separate
    only by their index, so a mesh can be one closed body in memory. An STL stores 32-bit coordinates
    and has no indices, and a reader joins vertices by position, so those pairs weld together. Read
    back, the mesh can have holes, extra pieces, or edges shared by four faces.

    Returns `bodies` (the pieces joined face to face; two closed sheets that only touch along an
    edge are two pieces), `holes` (edges with an odd number of faces, where a slicer has to guess),
    `touches` (edges with four faces, two closed sheets touching, which still slice as they are),
    `loose_mm3` (the volume of every piece outside the largest one; a piece whose centre is inside
    it overlaps it, and a slicer prints overlapping shells as one solid) and `ok`, which is no hole
    and nothing loose beyond `loose_mm3`: a boolean's slivers pass, a real second piece does not.
    """
    import io
    buf = io.BytesIO()
    mesh.export(buf, file_type=file_type)
    buf.seek(0)
    back = trimesh.load(buf, file_type=file_type, force="mesh")
    edges = np.sort(np.asarray(back.edges), axis=1)
    _uniq, inverse, count = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
    inverse = np.asarray(inverse).ravel()
    holes = int((count % 2 == 1).sum())
    touches = int(((count > 2) & (count % 2 == 0)).sum())
    # pieces joined face to face: faces adjacent across an edge shared by exactly two, counted
    # here rather than by `split`, which fills holes first and needs networkx for that
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    face = np.asarray(back.edges_face)
    order = np.argsort(inverse, kind="stable")
    inv, fac = inverse[order], face[order]
    same = (inv[1:] == inv[:-1]) & (count[inv[1:]] == 2)
    n = len(back.faces)
    adj = coo_matrix((np.ones(int(same.sum())), (fac[:-1][same], fac[1:][same])), shape=(n, n))
    bodies, label = connected_components(adj, directed=False)
    pieces = [trimesh.Trimesh(back.vertices, back.faces[label == k], process=False) for k in range(bodies)]
    pieces.sort(key=lambda q: -abs(float(q.volume)))
    loose = 0.0
    for q in pieces[1:]:
        # a closed piece whose centre lies inside the largest piece overlaps it, and a slicer
        # prints overlapping shells as one solid; a piece outside the largest one is loose
        inside = False
        if holes == 0:
            try:
                inside = bool(pieces[0].contains([np.asarray(q.centroid, float)])[0])
            except Exception:
                inside = False
        if not inside:
            loose += abs(float(q.volume))
    return {"ok": holes == 0 and loose <= loose_mm3, "bodies": int(bodies), "holes": holes,
            "touches": touches, "loose_mm3": float(loose)}
