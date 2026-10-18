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


def test_a_shell_inside_the_part_is_not_loose():
    # two closed shells, one inside the other, print as one solid
    from base3d.mesh import as_written
    outer = trimesh.creation.box(bounds=[[0, 0, 0], [10, 10, 10]])
    inner = trimesh.creation.box(bounds=[[4, 4, 4], [6, 6, 6]])
    got = as_written(trimesh.util.concatenate([outer, inner]))
    assert got["bodies"] == 2 and got["holes"] == 0 and got["loose_mm3"] == 0.0 and got["ok"]


def test_a_sound_part_has_no_faults_and_a_bad_one_names_each():
    from base3d.mesh import sound
    assert sound(trimesh.creation.box(extents=(10, 10, 10)))["faults"] == []
    hollow = trimesh.creation.box(extents=(10, 10, 10))
    pocket = trimesh.creation.box(extents=(4, 4, 4))
    pocket.invert()                                    # a sealed void inside
    plate = trimesh.creation.box(extents=(10, 10, 0.5))
    plate.apply_translation((0, 0, 8))                 # a thin second piece outside
    got = sound(trimesh.util.concatenate([hollow, pocket, plate]))
    text = " ".join(got["faults"])
    assert "sealed void" in text and "pieces of real volume" in text and "a wall 0.5" in text
    assert got["voids"] == 1 and got["bodies"] == 2


def test_the_command_line_says_whether_a_part_is_sound(tmp_path, capsys):
    import json
    from base3d.cli import main
    p = tmp_path / "box.stl"
    trimesh.creation.box(extents=(10, 10, 10)).export(p)
    assert main(["sound", str(p)]) == 0
    assert json.loads(capsys.readouterr().out)["faults"] == []


def test_a_hollow_dome_becomes_a_solid_one_from_its_skin():
    from base3d.mesh import solid_from_skin
    # a dome shell 10 mm out, 9 mm in, open at the bottom, as a solid of revolution
    t = np.linspace(0, np.pi / 2, 24)
    outer = np.c_[10 * np.cos(t), 10 * np.sin(t)][::-1]       # from the top down to the rim
    inner = np.c_[9 * np.cos(t), 9 * np.sin(t)]                 # from the rim back up to the top
    profile = np.vstack([outer, inner, outer[:1]])
    dome = trimesh.creation.revolve(profile, sections=64)
    if dome.volume < 0:
        dome.invert()
    assert dome.is_watertight
    solid = solid_from_skin(dome, centre=(0, 0, 0))
    assert solid.is_watertight and solid.euler_number == 2
    assert abs(solid.volume - 2.0 / 3.0 * np.pi * 1000) < 0.03 * 2094   # a solid half ball
    assert abs(solid.bounds[1][2] - 10.0) < 1e-6                        # the outside is kept


def _bell_profiles():
    """A bell: 1 mm thick at the top, flaring to a 0.4 mm wall at the rim, open at the bottom, with
    its inner surface at the flare further from the centre than at the top, as a cap's is round the
    ears. (outer from the top down to the rim, inner from the rim back up to the top), in (r, z)."""
    t = np.linspace(0, np.pi / 2, 48)
    flare = np.sin(t) ** 4
    outer = np.c_[(10 + 3.0 * flare) * np.sin(t), (10 + 3.0 * flare) * np.cos(t)]
    inner = np.c_[(9 + 3.6 * flare) * np.sin(t), (9 + 3.6 * flare) * np.cos(t)][::-1]
    return outer, inner


def _revolved(profile, sections=96):
    part = trimesh.creation.revolve(profile, sections=sections)
    if part.volume < 0:
        part.invert()
    assert part.is_watertight
    return part


def test_the_whole_inner_surface_goes_where_it_flares_out_and_the_thin_wall_with_it():
    from base3d.mesh import solid_from_skin
    from base3d.thickness import thin_spots
    outer, inner = _bell_profiles()
    bell = _revolved(np.vstack([outer, inner, outer[:1]]))
    solid = solid_from_skin(bell, centre=(0, 0, 0))
    assert solid.is_watertight and solid.is_winding_consistent and solid.euler_number == 2
    thin = [s for s in thin_spots(solid, 0.8) if s["points"] >= 8]
    assert thin == [], "the 0.4 mm wall at the flare is still there"
    full = _revolved(np.vstack([outer, [[0.0, 0.0]], outer[:1]]))      # a solid bell
    assert abs(solid.volume - full.volume) < 0.03 * full.volume


def test_a_face_behind_a_wall_is_not_part_of_the_inner_surface():
    from base3d.mesh import solid_from_skin
    from base3d.thickness import thin_spots
    # a dome shell with a brim: seen from a centre 5 mm up, the brim's top faces the centre, but the
    # dome's wall stands between
    t = np.linspace(0, np.pi / 2, 24)
    outer = np.c_[10 * np.sin(t), 10 * np.cos(t)]                    # top to the rim at (10, 0)
    brim = np.array([[16.0, 0.0], [16.0, -1.0], [9.0, -1.0]])      # out along the rim, under, back in
    inner = np.c_[9 * np.sin(t), 9 * np.cos(t)][::-1]               # rim back up to the top
    dome = _revolved(np.vstack([outer, brim, inner, outer[:1]]), sections=64)
    solid = solid_from_skin(dome, centre=(0, 0, 5))
    assert solid.is_watertight and solid.is_winding_consistent and solid.euler_number == 2
    assert [s for s in thin_spots(solid, 0.8) if s["points"] >= 8] == []
    assert abs(solid.bounds[1][0] - 16.0) < 1e-6                     # the brim is still there
    # the same solid drawn as one profile: the dome, the brim, and the fan from the brim's inner
    # edge under the rim up to the centre (the brim's inner side faces the centre and is seen)
    want = _revolved(np.vstack([outer, brim, [[0.0, 5.0]], outer[:1]]), sections=64)
    assert abs(solid.volume - want.volume) < 0.03 * want.volume


def test_a_fan_that_is_not_flat_is_wound_with_the_skin():
    from base3d.mesh import solid_from_skin
    # a dome shell made solid about a centre above its rim: the fan is a cone, and the solid's volume
    # is the half ball less that cone only when the cone faces the right way
    t = np.linspace(0, np.pi / 2, 24)
    outer = np.c_[10 * np.sin(t), 10 * np.cos(t)]
    inner = np.c_[9 * np.sin(t), 9 * np.cos(t)][::-1]
    dome = _revolved(np.vstack([outer, inner, outer[:1]]), sections=64)
    solid = solid_from_skin(dome, centre=(0, 0, 4))
    assert solid.is_winding_consistent
    want = 2.0 / 3.0 * np.pi * 1000 - np.pi * 81 * 4 / 3.0
    assert abs(solid.volume - want) < 0.03 * want


def test_what_the_centre_sees_matches_a_ray_cast_through_the_tree():
    from base3d.mesh import _seen_from
    t = np.linspace(0, np.pi / 2, 24)
    outer = np.c_[10 * np.sin(t), 10 * np.cos(t)]
    brim = np.array([[16.0, 0.0], [16.0, -1.0], [9.0, -1.0]])
    inner = np.c_[9 * np.sin(t), 9 * np.cos(t)][::-1]
    dome = _revolved(np.vstack([outer, brim, inner, outer[:1]]), sections=64)
    dome.apply_transform(trimesh.transformations.rotation_matrix(0.7, [1, 2, 3]))   # off the axes
    centre = dome.centroid + [0.3, -0.2, 2.0]
    which = np.arange(len(dome.faces))
    c = dome.triangles_center
    d = c - centre
    d /= np.linalg.norm(d, axis=1)[:, None]
    first = np.asarray(dome.ray.intersects_first(np.repeat(centre[None, :], len(which), axis=0), d))
    want = first == which
    got = _seen_from(dome, centre, which)
    assert (got == want).all(), f"{int((got != want).sum())} faces differ of {len(which)}"
    assert 0 < got.sum() < len(which)


def test_a_bill_seen_through_the_opening_is_kept_when_named():
    from base3d.mesh import solid_from_skin
    # a dome with a flat bill out to 20 mm, made solid about a centre 8 mm below the rim: the bill's
    # underside faces that centre and is seen from it through the opening, so without being told the
    # fill takes it for inner surface and fans the air under the bill solid
    t = np.linspace(0, np.pi / 2, 24)
    outer = np.c_[10 * np.sin(t), 10 * np.cos(t)]
    bill = np.array([[20.0, 0.0], [20.0, -1.0], [9.0, -1.0]])
    inner = np.c_[9 * np.sin(t), 9 * np.cos(t)][::-1]
    dome = _revolved(np.vstack([outer, bill, inner, outer[:1]]), sections=64)
    under = np.array([[15.0, 0.0, -2.0]])
    c, n = dome.triangles_center, dome.face_normals
    underside = (np.abs(c[:, 2] + 1.0) < 1e-6) & (np.linalg.norm(c[:, :2], axis=1) > 9.5) & (n[:, 2] < -0.9)
    assert underside.sum() > 0
    blind = solid_from_skin(dome, centre=(0, 0, -8))
    assert blind.contains(under)[0], "the air under the bill was not filled, so the test proves nothing"
    told = solid_from_skin(dome, centre=(0, 0, -8), keep=underside)
    assert told.is_watertight and told.is_winding_consistent and told.euler_number == 2
    assert not told.contains(under)[0]
    assert abs(told.bounds[1][0] - 20.0) < 1e-6


def test_a_sliver_just_inside_the_inner_surface_neither_hides_it_nor_stays():
    from base3d.mesh import solid_from_skin
    # a dome shell with a closed sliver, 0.2 mm thick, lying 0.05 mm under the top of its inner
    # surface: the kind of second copy a boolean or a vertex displacement leaves. Its far side faces
    # outward and stands in front of the dome's top as seen from the centre
    t = np.linspace(0, np.pi / 2, 24)
    outer = np.c_[10 * np.sin(t), 10 * np.cos(t)]
    inner = np.c_[9 * np.sin(t), 9 * np.cos(t)][::-1]
    dome = _revolved(np.vstack([outer, inner, outer[:1]]), sections=64)
    sliver = trimesh.creation.box(extents=(2.0, 2.0, 0.2))
    sliver.apply_translation([0, 0, 9.0 - 0.05 - 0.1])
    both = trimesh.util.concatenate([dome, sliver])
    # the dome's faces keep their indices in the joined mesh; the top of its inner surface lies in
    # the sliver's shadow, hidden by 0.05 mm with no skin and seen through it with the default
    from base3d.mesh import _seen_from
    c = dome.triangles_center
    top = np.flatnonzero((c[:, 2] > 8.5) & (c[:, 2] < 9.2) & (np.linalg.norm(c[:, :2], axis=1) < 0.6))
    assert len(top) > 0
    assert not _seen_from(both, (0, 0, 0), top, skin=0.0).any()
    assert _seen_from(both, (0, 0, 0), top, skin=0.5).all()
    solid = solid_from_skin(both, centre=(0, 0, 0))
    assert solid.is_watertight and solid.is_winding_consistent and solid.euler_number == 2
    assert solid.contains([[0.0, 0.0, 8.9], [0.0, 0.0, 5.0]]).all()       # the top is solid through
    assert abs(solid.volume - 2.0 / 3.0 * np.pi * 1000) < 0.03 * 2094


def _block_with_hole(side, hole, height=4.0):
    # a square block with a square hole through it, built from a polygon with a hole (no boolean
    # backend needed), so it is a genus-1 solid: watertight with a handle
    from shapely.geometry import Polygon
    h, s = hole / 2.0, side / 2.0
    shell = [(-s, -s), (s, -s), (s, s), (-s, s)]
    inner = [(-h, -h), (h, -h), (h, h), (-h, h)]
    return trimesh.creation.extrude_polygon(Polygon(shell, [inner]), height=height)


def test_remanifold_closes_a_sub_pitch_tunnel_to_a_simple_solid():
    from base3d.mesh import remanifold
    holed = _block_with_hole(10.0, 0.3)                     # a 0.3 mm tunnel through a 10 mm block
    assert holed.euler_number == 0                          # genus 1: a handle, not a simple solid
    fixed = remanifold(holed, pitch=0.6, close=1, smooth=0)
    assert fixed.is_watertight and fixed.euler_number == 2  # the sub-pitch tunnel is gone
    assert 400.0 < fixed.volume < 800.0          # voxelising inflates the surface; it never shrinks the solid


def test_remanifold_keeps_a_hole_wider_than_the_pitch():
    from base3d.mesh import remanifold
    frame = _block_with_hole(12.0, 3.0)                     # a 3 mm hole, far wider than the pitch
    kept = remanifold(frame, pitch=0.6, close=1, smooth=0)
    assert kept.is_watertight and kept.euler_number == 0    # the real hole is still a hole
