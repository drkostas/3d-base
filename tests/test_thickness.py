import numpy as np
import trimesh

from base3d import thickness as T


def test_a_plate_reads_its_own_thickness_and_is_found_thin():
    plate = trimesh.creation.box(extents=(10, 10, 0.6))
    _p, _n, mm = T.wall_thickness(plate, n=2000)
    assert abs(float(np.median(mm)) - 0.6) < 0.02
    spots = T.thin_spots(plate, bar_mm=0.8, n=2000)
    assert len(spots) == 1 and abs(spots[0]["mm"] - 0.6) < 0.02 and spots[0]["size_mm"] > 9


def test_a_rod_reads_its_diameter():
    rod = trimesh.creation.cylinder(radius=1.5, height=10, sections=96)
    _p, _n, mm = T.wall_thickness(rod, n=3000)
    assert abs(float(np.median(mm)) - 3.0) < 0.05


def test_a_thin_fin_on_a_thick_block_is_the_only_thin_place():
    block = trimesh.creation.box(extents=(10, 10, 10))
    fin = trimesh.creation.box(extents=(0.5, 6, 6))
    fin.apply_translation((5.25, 0, 0))                 # standing on the block's +x face
    part = trimesh.util.concatenate([block, fin])
    spots = T.thin_spots(part, bar_mm=0.8, n=6000)
    assert len(spots) == 1
    assert abs(spots[0]["mm"] - 0.5) < 0.02 and 4.99 < spots[0]["at"][0] < 5.51   # on the fin


def test_nothing_thin_on_a_bulky_part():
    assert T.thin_spots(trimesh.creation.box(extents=(4, 5, 6)), bar_mm=0.8, n=2000) == []


def test_the_same_points_and_readings_on_every_run():
    plate = trimesh.creation.box(extents=(10, 10, 0.6))
    a, b = T.wall_thickness(plate, n=500), T.wall_thickness(plate, n=500)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[2], b[2])


def test_every_face_gets_the_reading_of_its_nearest_point():
    plate = trimesh.creation.box(extents=(10, 10, 0.6))
    pts, _n, mm = T.wall_thickness(plate, n=2000)
    per_face = T.face_thickness(plate, pts, mm)
    assert per_face.shape == (len(plate.faces),) and np.isfinite(per_face).all()


def test_a_surface_written_twice_is_not_a_wall():
    plate = trimesh.creation.box(extents=(10, 10, 2.0))
    doubled = trimesh.util.concatenate([plate, plate.copy()])        # every face twice
    _p, _n, mm = T.wall_thickness(doubled, n=1500)
    assert abs(float(np.median(mm)) - 2.0) < 0.02 and float(mm.min()) > 1.9


def test_a_part_written_inside_out_reads_the_same():
    plate = trimesh.creation.box(extents=(10, 10, 0.6))
    flipped = plate.copy()
    flipped.invert()
    _p, _n, mm = T.wall_thickness(flipped, n=1500)
    assert abs(float(np.median(mm)) - 0.6) < 0.02


def test_the_command_line_names_the_thin_places(tmp_path, capsys):
    import json
    from base3d.cli import main
    p = tmp_path / "plate.stl"
    trimesh.creation.box(extents=(10, 10, 0.6)).export(p)
    assert main(["thickness", str(p), "--bar", "0.8", "-n", "1500"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert abs(out["thinnest_mm"] - 0.6) < 0.02 and len(out["thin_spots"]) == 1


def test_a_thin_place_says_how_thin_it_is_throughout():
    plate = trimesh.creation.box(extents=(10, 10, 0.6))
    spot = T.thin_spots(plate, bar_mm=0.8, n=2000)[0]
    assert abs(spot["typical_mm"] - 0.6) < 0.02 and spot["typical_mm"] >= spot["mm"]


def test_a_thin_plate_prints_lying_flat_and_not_on_its_edge():
    plate = trimesh.creation.box(extents=(12, 12, 0.5))          # lying flat: two and a half layers
    assert T.print_thin_spots(plate, n=3000) == []
    standing = plate.copy()
    standing.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    spots = T.print_thin_spots(standing, n=3000)
    assert len(spots) == 1 and spots[0]["short_of"] == "lines" and spots[0]["size_mm"] > 11
    assert abs(spots[0]["typical_width_mm"] - 0.5) < 0.02


def test_a_plate_thinner_than_two_layers_is_short_of_layers():
    sheet = trimesh.creation.box(extents=(12, 12, 0.3))
    spots = T.print_thin_spots(sheet, n=3000)
    assert len(spots) == 1 and spots[0]["short_of"] == "layers"
    assert abs(spots[0]["typical_width_mm"] - 0.3) < 0.02


def test_a_sloping_wall_is_judged_across_the_layer():
    # 0.6 mm thick at 30 degrees from upright: 0.69 mm across a layer, so short of two lines
    wall = trimesh.creation.box(extents=(12, 0.6, 12))
    wall.apply_transform(trimesh.transformations.rotation_matrix(np.radians(30), [1, 0, 0]))
    spots = T.print_thin_spots(wall, n=3000)
    assert spots and spots[0]["short_of"] == "lines"
    assert abs(spots[0]["typical_width_mm"] - 0.6 / np.cos(np.radians(30))) < 0.03
    # the same wall at 60 degrees is 1.2 mm across a layer and 0.69 mm through them: it prints
    flatter = trimesh.creation.box(extents=(12, 0.6, 12))
    flatter.apply_transform(trimesh.transformations.rotation_matrix(np.radians(60), [1, 0, 0]))
    assert T.print_thin_spots(flatter, n=3000) == []


def test_up_can_be_any_direction():
    plate = trimesh.creation.box(extents=(12, 12, 0.5))
    assert T.print_thin_spots(plate, up=(1, 0, 0), n=3000)[0]["short_of"] == "lines"


def test_the_command_line_can_judge_the_part_as_it_lies(tmp_path, capsys):
    import json
    from base3d.cli import main
    p = tmp_path / "plate.stl"
    trimesh.creation.box(extents=(10, 10, 0.6)).export(p)
    assert main(["thickness", str(p), "--printed", "-n", "1500"]) == 0
    assert json.loads(capsys.readouterr().out)["thin_spots"] == []


def test_a_plate_with_the_part_close_behind_it_is_detail_and_a_free_fin_is_not():
    # three 0.4 mm plates 0.3 mm apart, as ridges stand on a wall, and a free 0.5 mm fin far away.
    # Built from separate solids, so the test needs no boolean engine.
    plates = []
    for k in range(3):
        p = trimesh.creation.box(extents=(0.4, 10, 10))
        p.apply_translation((k * 0.7, 0, 0))
        plates.append(p)
    fin = trimesh.creation.box(extents=(0.5, 10, 10))
    fin.apply_translation((20, 0, 0))
    part = trimesh.util.concatenate(plates + [fin])
    middle = lambda s: 0.5 < s["at"][0] < 0.9
    every = T.print_thin_spots(part, n=8000)
    assert any(middle(s) for s in every)                 # without backed_mm the middle plate reads thin
    kept = T.print_thin_spots(part, n=8000, backed_mm=1.0)
    assert not any(middle(s) for s in kept)              # with it the middle plate is detail
    assert any(s["at"][0] > 19 for s in kept)            # and the free fin is still thin
