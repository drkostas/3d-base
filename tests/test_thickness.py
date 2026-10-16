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
