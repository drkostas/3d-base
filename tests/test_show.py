import struct
import zlib

import numpy as np
import pytest
import trimesh

from base3d import show as R


def box_at(x, size=1.0):
    b = trimesh.creation.box(extents=(size, size, size))
    b.apply_translation((x, 0, 0))
    return b


def test_image_shape_background_and_object():
    m = trimesh.creation.icosphere(subdivisions=3)
    eye, target = R.frame_on(m, -90, 10)
    img = R.render(m, eye, target, size=(80, 60), bg=(0, 0, 0))
    assert img.shape == (60, 80, 3) and img.dtype == np.uint8
    assert (img[0, 0] == 0).all()                         # corner is background
    assert (img[30, 40] > 0).all()                        # centre is the sphere


def test_nearer_object_hides_farther_one():
    red, blue = box_at(0), box_at(0)
    blue.apply_translation((0, 3, 0))                     # behind red, seen from -Y
    both = trimesh.util.concatenate([red, blue])
    colors = np.vstack([np.tile([1, 0, 0], (len(red.faces), 1)), np.tile([0, 0, 1], (len(blue.faces), 1))])
    img = R.render(both, eye=(0, -10, 0), target=(0, 0, 0), size=(60, 60), face_colors=colors)
    px = img[30, 30].astype(int)
    assert px[0] > 0 and px[2] == 0                        # red in front, no blue showing through
    # and the far box alone, from the other side, is blue
    img2 = R.render(both, eye=(0, 13, 0), target=(0, 3, 0), size=(60, 60), face_colors=colors)
    assert img2[30, 30, 2] > 0 and img2[30, 30, 0] == 0


def test_headlight_keeps_a_view_from_below_readable():
    m = trimesh.creation.icosphere(subdivisions=3)
    eye, target = R.frame_on(m, -90, -80)
    with_head = R.render(m, eye, target, size=(60, 60))
    without = R.render(m, eye, target, size=(60, 60), headlight=0)
    mask = (with_head < 255).any(axis=2)
    assert with_head[mask].mean() > without[mask].mean() + 40
    old = R.HEADLIGHT
    try:
        R.HEADLIGHT = 0                                   # the module knob is read at call time
        assert (R.render(m, eye, target, size=(60, 60)) == without).all()
    finally:
        R.HEADLIGHT = old


def test_sphere_is_smooth_and_box_edges_stay_sharp():
    s = trimesh.creation.icosphere(subdivisions=2)
    cn = R.corner_normals(s)
    fn = np.repeat(s.face_normals[:, None, :], 3, axis=1)
    assert np.abs(cn - fn).max() > 0.05                   # corners differ from the flat normal
    b = trimesh.creation.box()
    cb = R.corner_normals(b)
    assert np.allclose(cb, np.repeat(b.face_normals[:, None, :], 3, axis=1), atol=1e-9)


def rim():
    """A vertex on an edge: a flat fan on top, and one narrow wall face below the edge."""
    ang = np.linspace(0, np.pi, 7)
    pts = [(0, 0, 0)] + [(np.cos(t), np.sin(t), 0) for t in ang] + [(0.3, 0, -1), (-0.3, 0, -1)]
    faces = [(0, i, i + 1) for i in range(1, 7)] + [(0, 9, 8)]
    return trimesh.Trimesh(pts, faces, process=False)


def test_the_wall_does_not_bend_the_top_surface_at_a_rim():
    m = rim()
    assert np.allclose(m.face_normals[:6], (0, 0, 1)) and np.allclose(np.abs(m.face_normals[6]), (0, 1, 0))
    good = R.corner_normals(m)[0, 0]
    naive = R.corner_normals(m, naive=True)[0, 0]
    assert np.allclose(good, (0, 0, 1))
    assert naive[2] < 0.999                               # pulled toward the wall: a false highlight


def test_cached_normals_follow_a_rotation():
    b = trimesh.creation.box()
    before = R.corner_normals(b).copy()
    b.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (1, 0, 0)))
    after = R.corner_normals(b)
    assert not np.allclose(before, after)
    assert np.allclose(after, np.repeat(b.face_normals[:, None, :], 3, axis=1), atol=1e-9)
    assert R._corner_normals is R.corner_normals


def test_display_mesh_carries_normals_and_merges_smooth_vertices():
    s = trimesh.creation.icosphere(subdivisions=2)
    d = R.display_mesh(s)
    assert len(d.vertices) == len(s.vertices)             # smooth everywhere, nothing split
    b = R.display_mesh(trimesh.creation.box())
    assert len(b.vertices) == 24                          # every box corner splits into 3


def test_tile_and_sheet():
    a = np.zeros((10, 20, 3), np.uint8)
    out = R.tile([a, a, a], cols=2, gap=2)
    assert out.shape == (2 * 10 + 3 * 2, 2 * 20 + 3 * 2, 3)
    s = R.sheet(trimesh.creation.box(), views=("front", "top"), size=(30, 20), cols=2)
    assert s.shape == (20 + 2 * 16, 2 * 30 + 3 * 16, 3)
    assert tuple(s[0, 0]) == tuple(int(255 * c) for c in R.SHEET_BG)  # grey, so white faces stay visible
    with pytest.raises(KeyError):
        R.sheet(trimesh.creation.box(), views=("nowhere",))


def test_png_is_valid(tmp_path):
    img = np.zeros((3, 4, 3), np.uint8)
    img[1, 2] = (10, 20, 30)
    p = tmp_path / "x.png"
    R.save_png(img, p)
    data = p.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (4, 3)
    idat_len = struct.unpack(">I", data[33:37])[0]
    raw = zlib.decompress(data[41:41 + idat_len])
    row = raw[1 * 13 + 1:(1 * 13) + 13]
    assert row[6:9] == bytes((10, 20, 30))
