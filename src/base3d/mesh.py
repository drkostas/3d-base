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


def _pieces(mesh, inverse=None, count=None):
    """The pieces of `mesh` joined face to face (across edges shared by exactly two faces), largest
    first. Counted here rather than by `split`, which fills holes first and needs networkx."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    if inverse is None:
        edges = np.sort(np.asarray(mesh.edges), axis=1)
        _u, inverse, count = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
        inverse = np.asarray(inverse).ravel()
    face = np.asarray(mesh.edges_face)
    order = np.argsort(inverse, kind="stable")
    inv, fac = inverse[order], face[order]
    same = (inv[1:] == inv[:-1]) & (count[inv[1:]] == 2)
    n = len(mesh.faces)
    adj = coo_matrix((np.ones(int(same.sum())), (fac[:-1][same], fac[1:][same])), shape=(n, n))
    k, label = connected_components(adj, directed=False)
    pieces = [trimesh.Trimesh(mesh.vertices, mesh.faces[label == i], process=False) for i in range(k)]
    pieces.sort(key=lambda q: -abs(float(q.volume)))
    return pieces


def sound(mesh: trimesh.Trimesh, bar_mm: float = 0.8, n: int = 4000, size_mm: float = 3.0,
          loose_mm3: float = 0.5) -> dict:
    """One call for whether a part is sound to print, and every reason it is not.

    `faults` lists, in plain words, each of: not closed; more than one piece of real volume; a
    sealed void (a closed piece of negative volume inside); the file reading back with a hole or a
    loose piece (`as_written`); and a wall thinner than `bar_mm` over more than `size_mm`, by its
    middle reading (`thickness.thin_spots`). An empty list is sound. The other keys carry the
    readings behind them, so a geometry function can end with `assert not sound(m)["faults"]`.
    """
    from .thickness import thin_spots
    faults = []
    pieces = _pieces(mesh)
    vols = [float(q.volume) for q in pieces]
    bodies = sum(1 for v in vols if v > loose_mm3)
    voids = sum(1 for v in vols if v < -loose_mm3)
    closed = bool(mesh.is_watertight)
    if not closed:
        faults.append("not closed")
    if bodies > 1:
        faults.append(f"{bodies} pieces of real volume")
    if voids:
        faults.append(f"{voids} sealed void(s)")
    written = as_written(mesh, loose_mm3=loose_mm3)
    if not written["ok"]:
        faults.append(f"reads back from a file with {written['holes']} holed edge(s) and "
                      f"{written['loose_mm3']:.2f} mm3 loose")
    thin = [t for t in thin_spots(mesh, bar_mm, n=n) if t["size_mm"] >= size_mm]
    thinnest = min((t["typical_mm"] for t in thin), default=None)
    if thin:
        worst = min(thin, key=lambda t: t["typical_mm"])
        faults.append(f"a wall {worst['typical_mm']:.2f} mm thick over {worst['size_mm']:.1f} mm "
                      f"(needs {bar_mm})")
    return {"faults": faults, "closed": closed, "bodies": bodies, "voids": voids,
            "as_written": written, "thinnest_wall_mm": thinnest}


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
    pieces = _pieces(back, inverse, count)
    bodies = len(pieces)
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


def solid_from_skin(mesh: trimesh.Trimesh, centre, lean: float = 0.3) -> trimesh.Trimesh:
    """A hollow part made solid from its outer skin, by removing its inner surface.

    The inner surface is the largest connected region, by area, of faces that point toward `centre`
    (the cosine of the angle between the face normal and the direction to `centre` is above `lean`)
    and are seen from it: a ray from `centre` to the face's middle meets that face first. A face
    behind a wall (the top of a brim, as seen through the shell) is kept whichever way it faces.
    Removing the inner surface leaves the skin open along one or more loops (the inner edge of a rim,
    the root of a brim), and each loop is closed with a fan of triangles to `centre`. The result has
    the same outside and no inside, so a cavity cut into it afterwards (a bore for a part it sits on)
    is the only inside it has.

    This exists because filling a hollow part by uniting a fill with it leaves air wherever the fill
    meets the inner surface at a grazing angle, which a slicer prints as tunnels. With no inner
    surface there is nothing for air to lie against. Raises ValueError when the skin cannot be closed.
    """
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    centre = np.asarray(centre, float)
    c = np.asarray(mesh.triangles_center, float)
    n = np.asarray(mesh.face_normals, float)
    to_c = centre - c
    dist = np.linalg.norm(to_c, axis=1)
    to_c = to_c / np.maximum(dist, 1e-12)[:, None]
    cand = np.einsum("ij,ij->i", n, to_c) > lean
    if not cand.any():
        raise ValueError("no face points toward the centre")
    which = np.flatnonzero(cand)
    cand[which[~_seen_from(mesh, centre, which)]] = False
    if not cand.any():
        raise ValueError("no face that points toward the centre is seen from it")
    adj = np.asarray(mesh.face_adjacency)
    both = cand[adj[:, 0]] & cand[adj[:, 1]]
    graph = sp.coo_matrix((np.ones(int(both.sum())), (adj[both, 0], adj[both, 1])), shape=(len(c), len(c)))
    _k, label = connected_components(graph, directed=False)
    # the inner surface is the largest connected region of candidates by area: the one nearest the
    # centre can be a stray pair of faces (a cap's two faces inside its button), and which faces go
    # must not depend on where the part happens to lie
    area = np.asarray(mesh.area_faces, float)
    by_region = np.bincount(label[cand], weights=area[cand], minlength=int(label.max()) + 1)
    inner = cand & (label == int(np.argmax(by_region)))
    # what stays is the one connected skin round the inner surface; an island of faces inside it that
    # the centre cannot see (the side of a groove hidden by its lip) would be fanned into a sealed
    # pocket, so it goes with the inner surface
    kept = ~inner
    both = kept[adj[:, 0]] & kept[adj[:, 1]]
    graph = sp.coo_matrix((np.ones(int(both.sum())), (adj[both, 0], adj[both, 1])), shape=(len(c), len(c)))
    _k, label = connected_components(graph, directed=False)
    by_region = np.bincount(label[kept], weights=area[kept], minlength=int(label.max()) + 1)
    kept &= label == int(np.argmax(by_region))
    faces = np.asarray(mesh.faces)[kept]
    skin = trimesh.Trimesh(np.asarray(mesh.vertices, float), faces, process=False)
    # the skin's boundary edges, each in the winding of the face it belongs to, so the fan triangle
    # across it runs the edge the other way and is wound with the skin. Chaining the edges into loops
    # after sorting them lost that direction, and a fan that is not flat then faced the wrong way.
    directed = np.asarray(skin.edges)
    _u, inverse, count = np.unique(np.sort(directed, axis=1), axis=0, return_inverse=True, return_counts=True)
    boundary = directed[count[np.asarray(inverse).reshape(-1)] == 1]
    V = np.vstack([skin.vertices, centre[None, :]])
    apex = len(V) - 1
    fan = np.c_[boundary[:, 1], boundary[:, 0], np.full(len(boundary), apex)]
    solid = trimesh.Trimesh(V, np.vstack([faces, fan.reshape(-1, 3)]), process=False)
    solid.merge_vertices()
    if not solid.is_watertight or not solid.is_winding_consistent:
        raise ValueError("the skin could not be closed")
    if solid.volume < 0:
        solid.invert()
    return solid


def _seen_from(mesh: trimesh.Trimesh, centre, which, batch: int = 2000):
    """Which of the faces `which` a ray from `centre` to their middles meets first.

    Rays are cast `batch` at a time, which keeps memory flat on large meshes.
    """
    centre = np.asarray(centre, float)
    which = np.asarray(which, int)
    c = np.asarray(mesh.triangles_center, float)[which]
    d = c - centre
    d /= np.maximum(np.linalg.norm(d, axis=1), 1e-12)[:, None]
    seen = np.zeros(len(which), bool)
    for i in range(0, len(which), batch):
        k = which[i:i + batch]
        first = mesh.ray.intersects_first(np.repeat(centre[None, :], len(k), axis=0), d[i:i + batch])
        seen[i:i + batch] = np.asarray(first) == k
    return seen

