import numpy as np
import trimesh

from base3d import mesh as M
from base3d.cli import main


def with_slivers():
    """A closed sphere plus degenerate triangles at a pole, as OpenCascade writes them."""
    s = trimesh.creation.icosphere(subdivisions=2)
    top = int(np.argmax(s.vertices[:, 2]))
    extra = np.array([[top, top, top], [top, top, (top + 1) % len(s.vertices)]])
    return trimesh.Trimesh(s.vertices, np.vstack([s.faces, extra]), process=False)


def test_slivers_are_dropped_and_the_sphere_is_one_closed_body(tmp_path):
    p = tmp_path / "s.stl"
    with_slivers().export(p)
    m, bodies = M.load_clean(p)
    assert (m.area_faces > M.SLIVER_AREA).all()
    assert len(bodies) == 1 and m.is_watertight and M.voids(bodies) == []


def test_a_sealed_cavity_is_reported(tmp_path):
    outer = trimesh.creation.box(extents=(4, 4, 4))
    inner = trimesh.creation.box(extents=(1, 1, 1))
    inner.invert()                                       # faces inward: a closed hole in the solid
    p = tmp_path / "hollow.stl"
    trimesh.util.concatenate([outer, inner]).export(p)
    rep = M.report(p)
    assert rep["bodies"] == 2 and rep["voids"] == 1
    assert main(["check", str(p)]) == 1                  # the command fails on a cavity


def test_surface_points_are_the_same_every_run():
    s = trimesh.creation.icosphere()
    a, b = M.surface_points(s, 200), M.surface_points(s, 200)
    assert np.array_equal(np.asarray(a), np.asarray(b))
    assert not np.array_equal(np.asarray(a), np.asarray(M.surface_points(s, 200, seed=12)))


def test_old_trimesh_without_a_seed_still_gives_the_same_points(monkeypatch):
    s = trimesh.creation.icosphere()

    def old_sample(self, count, **kw):
        if kw:
            raise TypeError("sample() got an unexpected keyword argument 'seed'")
        return np.random.random((count, 3))             # what an unseeded call would return
    monkeypatch.setattr(trimesh.Trimesh, "sample", old_sample)
    a, b = M.surface_points(s, 300), M.surface_points(s, 300)
    assert np.array_equal(a, b)
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0, atol=0.02)  # on the sphere's surface
    assert not np.array_equal(a, M.surface_points(s, 300, seed=12))


def test_cli_render_and_sheet(tmp_path, capsys):
    p = tmp_path / "b.stl"
    trimesh.creation.box().export(p)
    out = tmp_path / "one.png"
    assert main(["render", str(p), "-o", str(out), "--size", "80x60"]) == 0
    assert out.read_bytes()[:4] == b"\x89PNG"
    assert main(["render", str(p), "-o", str(tmp_path / "s.png"), "--view", "sheet", "--size", "120x80"]) == 0
    assert main(["check", str(p)]) == 0


def test_skill_installs(tmp_path, capsys):
    assert main(["skill", "--dir", str(tmp_path)]) == 0
    text = (tmp_path / "3d-base" / "SKILL.md").read_text()
    assert text.startswith("---\nname: 3d-base\n")


def test_a_closed_box_reads_back_as_one_body():
    from base3d.mesh import as_written
    assert as_written(trimesh.creation.box()) == {"ok": True, "bodies": 1, "holes": 0, "touches": 0, "loose_mm3": 0.0}


def test_a_missing_face_reads_back_as_a_hole():
    from base3d.mesh import as_written
    m = trimesh.creation.box()
    m.update_faces([True] * 11 + [False])
    got = as_written(m)
    assert not got["ok"] and got["holes"] == 3


def test_two_blocks_kept_apart_by_index_weld_where_they_touch():
    # in memory these are two closed blocks with no shared vertex; written to an STL and read back,
    # the edge they share in space is shared by four faces
    from base3d.mesh import as_written
    a = trimesh.creation.box(bounds=[[0, 0, 0], [2, 3, 2]])
    b = trimesh.creation.box(bounds=[[2, 3, 0], [4, 5, 2]])
    both = trimesh.util.concatenate([a, b])
    assert both.is_watertight
    got = as_written(both)
    assert got["touches"] == 1 and got["holes"] == 0 and got["bodies"] == 2
    assert abs(got["loose_mm3"] - 8.0) < 1e-6 and not got["ok"]


def test_a_sliver_touching_the_part_is_not_a_second_body():
    from base3d.mesh import as_written
    a = trimesh.creation.box(bounds=[[0, 0, 0], [2, 3, 2]])
    crumb = trimesh.creation.box(bounds=[[2, 3, 0], [2.1, 3.1, 2]])        # 0.02 mm3, along the box edge
    got = as_written(trimesh.util.concatenate([a, crumb]))
    assert got["bodies"] == 2 and got["touches"] == 1 and got["holes"] == 0
    assert abs(got["loose_mm3"] - 0.02) < 0.001 and got["ok"]
