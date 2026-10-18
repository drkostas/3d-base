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


def solid_from_skin(mesh: trimesh.Trimesh, centre, lean: float = 0.3, keep=None, skin: float = 0.5) -> trimesh.Trimesh:
    """A hollow part made solid from its outer skin, by removing its inner surface.

    The inner surface is the largest connected region, by area, of faces that point toward `centre`
    (the cosine of the angle between the face normal and the direction to `centre` is above `lean`)
    and are seen from it: a ray from `centre` to the face's middle meets that face first. A face
    behind a wall (the top of a brim, as seen through the shell) is kept whichever way it faces.
    Removing the inner surface leaves the skin open along one or more loops (the inner edge of a rim,
    the root of a brim), and each loop is closed with a fan of triangles to `centre`. The result has
    the same outside and no inside, so a cavity cut into it afterwards (a bore for a part it sits on)
    is the only inside it has.

    A face is hidden only by a face more than `skin` nearer the centre along its ray. Nearer than
    that is a fold or a second copy of the surface, the kind a boolean or a vertex displacement
    leaves (a cap's seams, pressed in by half a millimetre, folded its inner skin over itself at
    the front and hid a patch of it), not a wall.

    `keep` names faces that stay whatever they face, as a boolean mask over the faces: a part the
    centre sees through the opening, such as the underside of a cap's bill, which faces the centre
    from outside the shell and would otherwise be taken for inner surface and have the air under it
    fanned solid.

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
    if keep is not None:
        cand &= ~np.asarray(keep, bool)
    if not cand.any():
        raise ValueError("no face points toward the centre")
    which = np.flatnonzero(cand)
    cand[which[~_seen_from(mesh, centre, which, skin=skin)]] = False
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


def remanifold(mesh: trimesh.Trimesh, pitch: float = 0.3, close: int = 1, smooth: int = 25,
               decimate_to: int = 25000) -> trimesh.Trimesh:
    """A mesh rebuilt as one simple solid on a voxel grid.

    A boolean operation can leave a mesh that is watertight but not a simple solid: a tunnel through a
    seam where two parts join (a handle, so the Euler number is not 2), or a near-coincident sheet
    where two surfaces meet at a grazing angle, which a thickness measure reads as a wall thinner than
    any line and a slicer cannot print. This turns the mesh into filled voxels of side `pitch`, which
    cannot carry a tunnel or a gap thinner than `pitch`; `close` passes of a morphological closing
    fill the sub-pitch tunnels and the thin grooves a surface would otherwise read as handles; the
    surface is taken from the voxels and, because it comes out stepped, smoothed with `smooth` Taubin
    iterations, which keep the volume and the topology. The mesh is decimated to about `decimate_to`
    faces first, because voxelising a high-resolution mesh is the memory cost and the grid resamples
    the surface anyway. The result is one watertight simple solid; a crisp cut such as a bore or a
    slot is re-cut by the caller afterwards, since the grid fills a gap thinner than its pitch.

    A hole wider than `pitch` is kept, so a part that is meant to have a hole stays as it is; only the
    tunnels and gaps narrower than the grid go. Needs `scipy`, `scikit-image` and `fast-simplification`.
    """
    from trimesh.voxel import ops as _vops
    from scipy import ndimage as _nd
    if decimate_to and len(mesh.faces) > decimate_to:
        try:
            mesh = mesh.simplify_quadric_decimation(percent=float(decimate_to) / len(mesh.faces))
        except Exception:
            pass
    vg = mesh.voxelized(float(pitch)).fill()
    mat = np.asarray(vg.matrix)
    if close:
        pad = int(close) + 1
        mat = _nd.binary_closing(np.pad(mat, pad), iterations=int(close))[pad:-pad, pad:-pad, pad:-pad]
    out = _vops.matrix_to_marching_cubes(mat)
    out.apply_transform(vg.transform)
    out.merge_vertices()
    out = max(out.split(only_watertight=False), key=lambda b: abs(b.volume))
    out.fix_normals()
    if smooth:
        trimesh.smoothing.filter_taubin(out, iterations=int(smooth))
    return out


def _seen_from(mesh: trimesh.Trimesh, centre, which, cells: int = 64, batch: int = 4_000_000, skin: float = 0.0):
    """Which of the faces `which` a ray from `centre` to their middles meets first, or within `skin`
    of first: a face less than that nearer the centre is a fold or a second copy of the surface.

    Every ray starts at the one point, so the triangles are binned by their direction from it on a
    cube map (six faces of `cells` by `cells`), and each ray is tested only against the triangles in
    its own cell, `batch` ray-triangle pairs at a time. Cast through the mesh's own tree instead,
    each ray was tested against every triangle whose box it crossed, thousands for a ray from the
    middle of a shell, and a shell of 70k faces took minutes and more than 8 GB.
    """
    centre = np.asarray(centre, float)
    V = np.asarray(mesh.vertices, float) - centre
    F = np.asarray(mesh.faces)
    which = np.asarray(which, int)
    tri = V[F]                                                        # (n, 3, 3)
    face_of, u_of, v_of = _cube_cells(tri.reshape(-1, 3), cells)     # per vertex of each triangle
    face_of, u_of, v_of = (a.reshape(-1, 3) for a in (face_of, u_of, v_of))
    # a triangle whose three vertices lie on one cube face projects onto that face as the triangle
    # of their projections, inside the box of their cells; one across an edge of the cube is put
    # on each face a vertex of it lies on, in a box widened by its own angular size in cells
    same = (face_of[:, 0] == face_of[:, 1]) & (face_of[:, 0] == face_of[:, 2])
    entries = []
    lo_u, hi_u = u_of.min(axis=1), u_of.max(axis=1)
    lo_v, hi_v = v_of.min(axis=1), v_of.max(axis=1)
    entries.append(_box_entries(np.flatnonzero(same), face_of[same, 0], lo_u[same], hi_u[same], lo_v[same], hi_v[same], cells))
    across = np.flatnonzero(~same)
    if len(across):
        d = tri[across] / np.maximum(np.linalg.norm(tri[across], axis=2), 1e-12)[:, :, None]
        cos = np.minimum.reduce([np.einsum("ij,ij->i", d[:, a], d[:, b]) for a, b in ((0, 1), (1, 2), (0, 2))])
        margin = np.ceil(np.arccos(np.clip(cos, -1, 1)) / (2.0 / cells / 3.0)).astype(int) + 1
        for k in range(3):
            entries.append(_box_entries(across, face_of[across, k], u_of[across, k] - margin, u_of[across, k] + margin,
                                        v_of[across, k] - margin, v_of[across, k] + margin, cells))
    cell_tri = np.unique(np.vstack(entries), axis=0)                 # (cell, triangle), sorted by cell
    starts = np.searchsorted(cell_tri[:, 0], np.arange(6 * cells * cells + 1))
    # the rays: one per face in `which`, to its middle, against the triangles of its cell
    mid = tri[which].mean(axis=1)
    dist = np.linalg.norm(mid, axis=1)
    rf, ru, rv = _cube_cells(mid, cells)
    rcell = (rf * cells + ru) * cells + rv
    counts = starts[rcell + 1] - starts[rcell]
    pair_ray = np.repeat(np.arange(len(which)), counts)
    offsets = np.repeat(starts[rcell] - np.cumsum(counts) + counts, counts)
    pair_tri = cell_tri[np.arange(len(pair_ray)) + offsets, 1]
    own = pair_tri == which[pair_ray]
    hidden = np.zeros(len(which), bool)
    for i in range(0, len(pair_ray), batch):
        r, t_idx = pair_ray[i:i + batch], pair_tri[i:i + batch]
        t = _ray_t(mid[r] / dist[r][:, None], tri[t_idx])
        before = (t < dist[r] - max(float(skin), 1e-7)) & ~own[i:i + batch]
        hidden[np.unique(r[before])] = True
    return ~hidden


def _cube_cells(d, cells):
    """The cube-map cell of each direction `d`: the face (0..5, the dominant axis and its sign) and
    the cell along the other two axes (0..cells-1)."""
    d = np.asarray(d, float)
    a = np.abs(d)
    ax = np.argmax(a, axis=1)
    idx = np.arange(len(d))
    m = np.maximum(a[idx, ax], 1e-12)
    face = ax * 2 + (d[idx, ax] < 0)
    other = np.array([[1, 2], [0, 2], [0, 1]])[ax]
    u = np.clip(((d[idx, other[:, 0]] / m + 1.0) / 2.0 * cells).astype(int), 0, cells - 1)
    v = np.clip(((d[idx, other[:, 1]] / m + 1.0) / 2.0 * cells).astype(int), 0, cells - 1)
    return face, u, v


def _box_entries(tri_idx, face, lo_u, hi_u, lo_v, hi_v, cells):
    """(cell, triangle) rows for every cell of each triangle's box on its cube face."""
    lo_u, hi_u = np.clip(lo_u, 0, cells - 1), np.clip(hi_u, 0, cells - 1)
    lo_v, hi_v = np.clip(lo_v, 0, cells - 1), np.clip(hi_v, 0, cells - 1)
    nu, nv = hi_u - lo_u + 1, hi_v - lo_v + 1
    n = nu * nv
    rep = np.repeat(np.arange(len(tri_idx)), n)
    k = np.arange(len(rep)) - np.repeat(np.cumsum(n) - n, n)
    uu = lo_u[rep] + k // nv[rep]
    vv = lo_v[rep] + k % nv[rep]
    cell = (face[rep] * cells + uu) * cells + vv
    return np.c_[cell, tri_idx[rep]]


def _ray_t(d, tri):
    """Where rays from the origin along `d` (m, 3) meet the triangles `tri` (m, 3, 3), as the
    distance along each ray, infinite where a ray misses its triangle (Moller-Trumbore)."""
    e1 = tri[:, 1] - tri[:, 0]
    e2 = tri[:, 2] - tri[:, 0]
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = -tri[:, 0]
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1)
    v = np.einsum("ij,ij->i", d, q) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1.0 + 1e-9) & (t > 1e-9)
    return np.where(hit, t, np.inf)
