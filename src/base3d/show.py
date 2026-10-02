"""A small software renderer for judging a 3D model from pictures, with numpy and nothing else.

Matplotlib's 3D axes sort whole polygons from back to front and then draw them, so faces that
overlap or pass through each other come out in the wrong order. A limb shows through a body, and a
model that is correct looks broken. A depth buffer decides for each pixel, which is the only way to
get that right.

The picture is the mesh itself, shaded by its own normals. Nothing is smoothed or simplified for
the picture, so if a part looks wrong here, the part is wrong (with one exception, the shading of
smooth surfaces, described at CREASE_DEG).
"""
from __future__ import annotations

import struct
import zlib

import numpy as np
import trimesh

# How much of the light comes from the camera. This term keeps every view readable: a face you can
# see is a face that faces the camera, so it always receives some light. Without it, views from
# below and from behind come out close to black with a fixed key light.
HEADLIGHT = 0.60

# Smooth shading with real edges kept sharp.
#
# Shading with one normal per triangle makes every sphere look like a quilt of flat facets, even
# when the mesh is within a few microns of a true sphere (much less than one pixel, and much less
# than one printed layer). That reads as a modelling defect that does not exist. So the normal is
# interpolated across each triangle from its corners, but only where the surface is really smooth.
# A neighbouring face that turns more than CREASE_DEG away is on the other side of a real edge and
# is left out of the average, so box corners, cuts and seams stay crisp.
CREASE_DEG = 32.0


def look_at(eye, target, up=(0.0, 0.0, 1.0)):
    """A 4x4 view matrix for a camera at `eye` looking at `target`."""
    eye, target = np.asarray(eye, float), np.asarray(target, float)
    f = target - eye
    f /= np.linalg.norm(f)
    u = np.asarray(up, float)
    s = np.cross(f, u)
    if np.linalg.norm(s) < 1e-9:  # looking straight along `up`
        s = np.cross(f, [0.0, 1.0, 0.0])
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    M = np.eye(4)
    M[0, :3], M[1, :3], M[2, :3] = s, u, -f
    M[:3, 3] = -M[:3, :3] @ eye
    return M


def display_mesh(mesh, crease_deg=None):
    """The same mesh with per-vertex normals baked in, for viewers that shade from stored normals.

    A GLB exported by trimesh carries positions and colours but no normals, and a web viewer such as
    three.js then renders it unlit when smooth shading is on. These are the same crease-aware
    normals this renderer uses, so the viewer and the pictures agree. Vertices are split per corner
    and then merged back where both position and normal agree, so only real edges duplicate.
    """
    deg = CREASE_DEG if crease_deg is None else float(crease_deg)
    F = np.asarray(mesh.faces)
    cn = corner_normals(mesh, deg).reshape(-1, 3)
    V = np.asarray(mesh.vertices, float)[F].reshape(-1, 3)
    key = np.hstack([np.round(V, 5), np.round(cn, 4)])
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    out = trimesh.Trimesh(V[first], inverse.reshape(-1, 3), process=False)
    out.vertex_normals = cn[first]
    return out


def corner_normals(mesh, crease_deg=CREASE_DEG, naive=False):
    """A normal for each corner of each face, shape (faces, 3, 3).

    For each corner, the normals of the faces at that vertex are averaged (weighted by area), but
    only those within `crease_deg` of THIS face. Comparing each face to the plain average of all
    faces at the vertex looks similar and is wrong at the rim of a cut, because there the average is
    pulled toward the cut's walls. A rim triangle is then smoothed as if it faced the light and
    shows as a bright spike that is not in the model.

    `naive=True` returns that wrong version. It is kept so a test can show the difference.

    The result is cached on the mesh, keyed by the angle and by the mesh's hash. The hash changes
    when the mesh is moved or rotated, so a transformed mesh is never shaded with stale normals.
    """
    if naive:
        n0 = np.asarray(mesh.face_normals, float)
        F0 = np.asarray(mesh.faces)
        vn = np.asarray(mesh.vertex_normals, float)[F0]
        fn3 = np.repeat(n0[:, None, :], 3, axis=1)
        dot = np.clip((vn * fn3).sum(axis=2), -1.0, 1.0)
        cn0 = np.where((dot < np.cos(np.radians(crease_deg)))[..., None], fn3, vn)
        ln0 = np.linalg.norm(cn0, axis=2, keepdims=True)
        return cn0 / np.where(ln0 < 1e-9, 1.0, ln0)
    key = "_base3d_corner_normals"
    ck = (round(float(crease_deg), 1), hash(mesh))
    got = getattr(mesh, key, None)
    if got is not None and got[0] == ck:
        return got[1]
    n = np.asarray(mesh.face_normals, float)
    F = np.asarray(mesh.faces)
    try:
        # Which faces touch each vertex. trimesh's `vertex_faces` raises on meshes with degenerate
        # faces, so it is built here directly: sort the (vertex, face) pairs by vertex and put each
        # vertex's faces in its own row, padded with -1.
        F_flat = F.ravel()
        f_of = np.repeat(np.arange(len(F)), 3)
        order = np.argsort(F_flat, kind="stable")
        vs, fs = F_flat[order], f_of[order]
        V = int(F.max()) + 1
        counts = np.bincount(vs, minlength=V)
        start = np.concatenate([[0], np.cumsum(counts)[:-1]])
        vf = np.full((V, int(counts.max())), -1, dtype=np.int64)
        vf[vs, np.arange(len(vs)) - start[vs]] = fs
        area = np.asarray(mesh.area_faces, float)
        cosc = np.cos(np.radians(crease_deg))
        cn = np.empty((len(F), 3, 3), float)
        # In blocks of faces, so memory stays bounded on large meshes (the full neighbour array for
        # a few hundred thousand faces is several gigabytes).
        step = max(1, int(4_000_000 // max(vf.shape[1] * 3, 1)))
        for a in range(0, len(F), step):
            b = min(a + step, len(F))
            nb = vf[F[a:b]]                             # (B, 3, max valence)
            valid = nb >= 0
            nbi = np.where(valid, nb, 0)
            nbn = n[nbi]                                # (B, 3, max valence, 3)
            d = np.einsum("fkmc,fc->fkm", nbn, n[a:b])
            w = area[nbi] * (valid & (d >= cosc))
            acc = np.einsum("fkmc,fkm->fkc", nbn, w)
            ln = np.linalg.norm(acc, axis=2, keepdims=True)
            flat = ln < 1e-9
            cn[a:b] = np.where(flat, np.repeat(n[a:b, None, :], 3, axis=1),
                               acc / np.where(flat, 1.0, ln))
    except Exception as e:  # noqa: BLE001
        # Say so. A silent fallback to flat shading would look like a faceted model.
        print(f"3d-base: smooth normals failed ({type(e).__name__}: {e}), this mesh is shaded flat")
        cn = np.repeat(n[:, None, :], 3, axis=1)
    try:
        setattr(mesh, key, (ck, cn))
    except Exception:  # noqa: BLE001
        pass
    return cn


def render(mesh, eye, target, size=(1400, 1000), fov=26.0, up=(0, 0, 1),
           light=(0.4, -0.7, 0.75), base=(0.94, 0.94, 0.91), bg=(1.0, 1.0, 1.0),
           face_colors=None, ao=0.35, headlight=None, naive_normals=False):
    """Render one mesh with a depth buffer and return an RGB image (H, W, 3) of uint8.

    The light is a fixed key light, a soft light from the sky (+Z), and a headlight from the
    camera. The key light gives the shapes their form. The headlight keeps faces turned away from
    the key light readable, which matters for views from below and from behind. Measured without
    it, the model pixels in a view from below averaged about a fifth of full brightness.

    `face_colors` is an (F, 3) array of RGB values from 0 to 1, one colour per face. `headlight`
    overrides HEADLIGHT for this call. `ao` is accepted for compatibility and not used.
    """
    W, H = size
    V = np.asarray(mesh.vertices, float)
    F = np.asarray(mesh.faces)
    M = look_at(eye, target, up)
    cam = (M @ np.c_[V, np.ones(len(V))].T).T[:, :3]

    f = 1.0 / np.tan(np.radians(fov) / 2.0)
    z = -cam[:, 2]
    z = np.where(z < 1e-6, 1e-6, z)
    sx = (cam[:, 0] * f / z) * (H / 2) + W / 2
    sy = (-cam[:, 1] * f / z) * (H / 2) + H / 2
    P = np.column_stack([sx, sy, z])

    n = np.asarray(mesh.face_normals, float)
    cn = corner_normals(mesh, CREASE_DEG, naive=naive_normals)
    L = np.asarray(light, float)
    L /= np.linalg.norm(L)
    lam = np.clip(cn @ L, 0, 1)
    sky = np.clip(cn[:, :, 2] * 0.5 + 0.5, 0, 1)
    # Read at call time, not as a default argument, so changing render.HEADLIGHT takes effect.
    k = HEADLIGHT if headlight is None else float(headlight)
    view = np.asarray(eye, float) - np.asarray(target, float)
    vn = float(np.linalg.norm(view))
    head = np.clip(cn @ (view / vn), 0, 1) if vn > 1e-9 else np.zeros((len(n), 3))
    shade = np.clip(0.14 + 0.46 * lam + 0.22 * sky + k * head, 0, 1.25)   # (F, 3), per corner
    if face_colors is None:
        col = np.tile(np.asarray(base, float), (len(F), 1))
    else:
        col = np.asarray(face_colors, float)
    col = np.clip(col, 0, 1)                    # colour is flat per face, only the light varies

    img = np.tile(np.asarray(bg, float), (H, W, 1))
    depth = np.full((H, W), np.inf)

    tri = P[F]
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    area2 = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])
    keep = np.abs(area2) > 1e-9                 # skip faces seen exactly edge-on
    tri, col, area2, shade = tri[keep], col[keep], area2[keep], shade[keep]

    order = np.argsort(-tri[:, :, 2].min(axis=1))       # far to near
    for i in order:
        t, cc, sh = tri[i], col[i], shade[i]
        x0 = max(int(np.floor(t[:, 0].min())), 0)
        x1 = min(int(np.ceil(t[:, 0].max())) + 1, W)
        y0 = max(int(np.floor(t[:, 1].min())), 0)
        y1 = min(int(np.ceil(t[:, 1].max())) + 1, H)
        if x1 <= x0 or y1 <= y0:
            continue
        xs = np.arange(x0, x1) + 0.5
        ys = np.arange(y0, y1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        d = area2[i]
        w0 = ((t[1, 0] - t[0, 0]) * (gy - t[0, 1]) - (gx - t[0, 0]) * (t[1, 1] - t[0, 1])) / d
        w1 = ((gx - t[0, 0]) * (t[2, 1] - t[0, 1]) - (t[2, 0] - t[0, 0]) * (gy - t[0, 1])) / d
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w0 + w1 <= 1 + 1e-9)
        if not inside.any():
            continue
        zz = t[0, 2] + w1 * (t[1, 2] - t[0, 2]) + w0 * (t[2, 2] - t[0, 2])
        sub = depth[y0:y1, x0:x1]
        hit = inside & (zz < sub)
        if not hit.any():
            continue
        sub[hit] = zz[hit]
        # the same barycentric weights as the depth, so the light varies across the triangle
        ss = sh[0] + w1 * (sh[1] - sh[0]) + w0 * (sh[2] - sh[0])
        img[y0:y1, x0:x1][hit] = np.clip(cc[None, :] * ss[hit][:, None], 0, 1)
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def frame_on(mesh, azim, elev, pad=1.22):
    """(eye, target) that puts the whole mesh in frame from a direction in degrees.

    `azim` turns around +Z starting from +X, and `elev` is the angle above the XY plane.
    """
    c = mesh.bounds.mean(axis=0)
    r = float(np.linalg.norm(mesh.bounds[1] - mesh.bounds[0])) / 2.0
    a, e = np.radians(azim), np.radians(elev)
    d = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    return c + d * r * 3.4 * pad, c


def tile(images, cols=None, gap=16, bg=255, titles=None, title_h=0):
    """Lay out images of equal size in a grid. `bg` is one grey value or an RGB tuple, and `title_h` leaves that many pixels above each one."""
    cols = cols or len(images)
    rows = int(np.ceil(len(images) / cols))
    h, w = images[0].shape[:2]
    out = np.full((rows * (h + title_h) + (rows + 1) * gap,
                   cols * w + (cols + 1) * gap, 3), bg, np.uint8)
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        y = gap + r * (h + title_h + gap) + title_h
        x = gap + c * (w + gap)
        out[y:y + h, x:x + w] = im
    return out


VIEWS = {
    "front": (-90, 10), "back": (90, 10), "left": (180, 10), "right": (0, 10),
    "top": (-90, 89), "below": (-90, -60), "front-right": (-45, 25), "back-left": (135, 25),
}


SHEET_BG = (0.83, 0.85, 0.88)


def sheet(mesh, views=("front", "right", "back", "left", "top", "below"), size=(600, 450), cols=3, **kw):
    """Render the mesh from several named views (see VIEWS) and lay them out in a grid.

    The background is a light grey (SHEET_BG) unless `bg` is given, because the brightest faces of a
    light model are drawn close to white and would disappear against a white background.
    """
    kw.setdefault("bg", SHEET_BG)
    imgs = []
    for v in views:
        azim, elev = VIEWS[v] if isinstance(v, str) else v
        eye, target = frame_on(mesh, azim, elev)
        imgs.append(render(mesh, eye, target, size=size, **kw))
    return tile(imgs, cols=cols, bg=tuple(int(255 * c) for c in kw["bg"]))


def save_png(img, path):
    """Write an (H, W, 3) uint8 image as PNG with the standard library only."""
    img = np.ascontiguousarray(img, dtype=np.uint8)
    h, w = img.shape[:2]
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


# The name used before this was a package.
_corner_normals = corner_normals
