"""How thick a part is at each point of its surface, and where it is too thin to print.

A wall thinner than about two nozzle widths prints as a single line, or not at all, and nothing in a
bounding box, a volume or a watertight check says so. Here each sample point on the surface sends a
ray straight into the part, against the surface normal, and the distance to the first surface the ray
meets on the other side is the wall's thickness at that point. This is the usual ray estimate of a
part's local diameter. It reads a flat plate as its own thickness, a round rod as its diameter, and a
thin fin on a thick block as the fin's own width.

    pts, normals, mm = wall_thickness(mesh)          # one reading per sample point
    spots = thin_spots(mesh, bar_mm=0.8)             # the places under 0.8 mm, grouped
    spots = print_thin_spots(mesh)                   # the same, for the part as it lies on the plate

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
    thinnest reading (`mm`), where that reading is (`at`), its median reading (`typical_mm`), how many
    sample points fall in it (`points`) and its extent (`size_mm`, the largest distance between two
    of its points).

    Read `typical_mm` and `size_mm` before `mm`. Material really is thin right next to a sharp edge
    (a knife edge, a rim, the lip of a bore), so a place of one or two points with a low `mm` is an
    edge, which printing only rounds. A wall too thin to print is a place that is large and thin
    throughout, and its `typical_mm` says how thin.
    """
    pts, _normals, mm = wall_thickness(mesh, n=n, seed=seed)
    return _group(pts, mm, np.nonzero(mm < bar_mm)[0], group_mm)


def _group(pts, mm, thin, group_mm, extra=None):
    """The thin points `thin` (indices) grouped into places, each a dict, thinnest first."""
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
        spot = {"mm": float(mm[k]), "at": [float(x) for x in pts[k]],
                "typical_mm": float(np.median(mm[idx])), "points": int(len(idx)), "size_mm": span}
        if extra is not None:
            spot.update(extra(idx))
        spots.append(spot)
    return sorted(spots, key=lambda s: s["mm"])


def _backed(mesh, pts, normals, mm, which, backed_mm, batch=2000):
    """For the points `which`, whether the ray that measured them meets the part again within
    `backed_mm` after leaving it."""
    out = np.zeros(len(pts), bool)
    idx = np.nonzero(which & np.isfinite(mm))[0]
    for i in range(0, len(idx), batch):
        k = idx[i:i + batch]
        d = -normals[k]
        origins = pts[k] + d * (mm[k][:, None] + START_MM)
        loc, ray, _tri = mesh.ray.intersects_location(origins, d, multiple_hits=False)
        if not len(ray):
            continue
        dist = np.linalg.norm(loc - origins[ray], axis=1)
        out[k[ray[dist < backed_mm]]] = True
    return out


#: a wall inside one layer needs two lines of a 0.4 mm nozzle, and a plate lying flat two 0.2 mm layers
LINE_MM = 0.8
LAYER_MM = 0.4


def print_thin_spots(mesh: trimesh.Trimesh, line_mm: float = LINE_MM, layer_mm: float = LAYER_MM,
                     up=(0.0, 0.0, 1.0), n: int = 4000, seed: int = SAMPLE_SEED,
                     group_mm: float = 1.5, backed_mm: float | None = None) -> list[dict]:
    """The places too thin to print, for the part as it lies on the plate, thinnest first.

    A slicer cuts the part into layers across `up`, and how much a wall gets depends on which way it
    faces. A wall standing upright is drawn with lines inside each layer, and needs `line_mm` across
    (two lines). A plate lying flat is drawn as a stack of layers, and needs `layer_mm` through (two
    layers). A wall at a slope is both at once: inside one layer it is as wide as its thickness over
    the sideways part of its normal, and through the layers as deep as its thickness over the upward
    part. A point is thin when either falls under its bar. So a flat 0.5 mm plate is fine, and the
    same plate stood on its edge is not.

    Each place is a dict like `thin_spots` gives (its `mm` and `typical_mm` are the wall's own
    thickness), with `lines` or `layers` as `short_of` (which bar most of its points miss) and
    `typical_width_mm` (the median of what they have of it, across the layer or through the layers).

    A ridge, a tooth or a row of grooves on a thick wall reads as thin, because the ray crosses one
    ridge and leaves it. The slicer draws such detail as a bump in the outer line of a wall that is
    thick behind it. With `backed_mm`, a point whose ray meets the part again within that distance
    after leaving it is taken as detail of that kind and left out. A free wall (a shell, a fin, a
    plate) has open space behind it and stays in.
    """
    up = np.asarray(up, float)
    up = up / float(np.linalg.norm(up))
    pts, normals, mm = wall_thickness(mesh, n=n, seed=seed)
    vert = np.abs(normals @ up)
    side = np.sqrt(np.clip(1.0 - vert ** 2, 0.0, 1.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        across = np.where(side > 1e-6, mm / side, np.inf)        # inside one layer
        through = np.where(vert > 1e-6, mm / vert, np.inf)       # through the layers
    short_lines = across < line_mm
    short_layers = through < layer_mm
    short = short_lines | short_layers
    if backed_mm is not None and short.any():
        short &= ~_backed(mesh, pts, normals, mm, short, backed_mm)
    thin = np.nonzero(short)[0]

    def extra(idx):
        lines = int(short_lines[idx].sum()) >= int(short_layers[idx].sum())
        have = across[idx] if lines else through[idx]
        return {"short_of": "lines" if lines else "layers",
                "typical_width_mm": float(np.median(have[np.isfinite(have)])) if np.isfinite(have).any()
                else float("inf")}

    return _group(pts, mm, thin, group_mm, extra)


def face_thickness(mesh: trimesh.Trimesh, points, mm) -> np.ndarray:
    """A reading for every face, from the sample point nearest its centre, for colouring a picture."""
    from scipy.spatial import cKDTree
    _d, k = cKDTree(np.asarray(points, float)).query(np.asarray(mesh.triangles_center, float))
    return np.asarray(mm, float)[k]
