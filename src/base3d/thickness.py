"""How thick a part is at each point of its surface, and where it is too thin to print.

A wall thinner than about two nozzle widths prints as a single line, or not at all, and nothing in a
bounding box, a volume or a watertight check says so. Here each sample point on the surface sends a
ray straight into the part, against the surface normal, and the distance to the first surface the ray
meets on the other side is the wall's thickness at that point. This is the usual ray estimate of a
part's local diameter. It reads a flat plate as its own thickness, a round rod as its diameter, and a
thin fin on a thick block as the fin's own width.

    pts, normals, mm = wall_thickness(mesh)          # one reading per sample point
    spots = thin_spots(mesh, bar_mm=0.8)             # the places under 0.8 mm, grouped

Use a closed mesh with outward normals. A ray that leaves through a hole in the surface meets nothing,
and its reading is `inf`.
"""
from __future__ import annotations

import numpy as np
import trimesh

from .mesh import SAMPLE_SEED

#: how far inside the surface each ray starts, so it does not hit the face it starts on
START_MM = 1e-3
#: hits closer than this are a second copy of the same surface (two shells on top of each other, or a
#: face written twice), not a wall, and the ray goes on to the next one
SKIP_MM = 0.01


def _samples(mesh, n, rng):
    """`n` points on the surface, picked by face area, with the face each one lies on."""
    cum = np.cumsum(np.asarray(mesh.area_faces, float))
    face = np.searchsorted(cum, rng.random(n) * cum[-1])
    face = np.minimum(face, len(mesh.faces) - 1)
    tri = np.asarray(mesh.triangles, float)[face]
    r = rng.random((n, 2))
    over = r.sum(axis=1) > 1
    r[over] = 1 - r[over]
    pts = tri[:, 0] + r[:, :1] * (tri[:, 1] - tri[:, 0]) + r[:, 1:] * (tri[:, 2] - tri[:, 0])
    return pts, face


def wall_thickness(mesh: trimesh.Trimesh, n: int = 4000, seed: int = SAMPLE_SEED, batch: int = 2000,
                   skip_mm: float = SKIP_MM):
    """(points, outward normals, thickness in the mesh's units) for `n` points on the surface.

    The same points come back on every run. Rays are cast `batch` at a time, which keeps memory flat
    on large meshes. A closed mesh written inside out (negative volume) is read from the inside of its
    material all the same. Hits nearer than `skip_mm` are taken as a second copy of the surface the ray
    starts on and passed through.
    """
    rng = np.random.default_rng(seed)
    pts, face = _samples(mesh, n, rng)
    normals = np.asarray(mesh.face_normals, float)[face]
    if mesh.is_watertight and mesh.volume < 0:
        normals = -normals
    out = np.full(len(pts), np.inf)
    for i in range(0, len(pts), batch):
        p, d = pts[i:i + batch], -normals[i:i + batch]
        origins = p + d * START_MM
        loc, ray, _tri = mesh.ray.intersects_location(origins, d, multiple_hits=True)
        if not len(ray):
            continue
        dist = np.linalg.norm(loc - origins[ray], axis=1) + START_MM
        keep = dist > skip_mm
        ray, dist = ray[keep], dist[keep]
        first = np.full(len(p), np.inf)
        np.minimum.at(first, ray, dist)
        out[i:i + len(p)] = first
    return pts, normals, out


def thin_spots(mesh: trimesh.Trimesh, bar_mm: float, n: int = 4000, seed: int = SAMPLE_SEED,
               group_mm: float = 1.5) -> list[dict]:
    """The places thinner than `bar_mm`, thinnest first.

    Thin points closer than `group_mm` to each other are one place. Each place is a dict with its
    thinnest reading (`mm`), where that reading is (`at`), how many sample points fall in it
    (`points`) and its extent (`size_mm`, the largest distance between two of its points).
    """
    pts, _normals, mm = wall_thickness(mesh, n=n, seed=seed)
    thin = np.nonzero(mm < bar_mm)[0]
    if not len(thin):
        return []
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    pairs = cKDTree(pts[thin]).query_pairs(group_mm, output_type="ndarray")
    import scipy.sparse as sp
    adj = sp.coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(thin), len(thin)))
    _n, label = connected_components(adj, directed=False)
    spots = []
    for g in np.unique(label):
        idx = thin[label == g]
        k = idx[np.argmin(mm[idx])]
        span = float(np.ptp(pts[idx], axis=0).max()) if len(idx) > 1 else 0.0
        spots.append({"mm": float(mm[k]), "at": [float(x) for x in pts[k]], "points": int(len(idx)),
                      "size_mm": span})
    return sorted(spots, key=lambda s: s["mm"])


def face_thickness(mesh: trimesh.Trimesh, points, mm) -> np.ndarray:
    """A reading for every face, from the sample point nearest its centre, for colouring a picture."""
    from scipy.spatial import cKDTree
    _d, k = cKDTree(np.asarray(points, float)).query(np.asarray(mesh.triangles_center, float))
    return np.asarray(mm, float)[k]
