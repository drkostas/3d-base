import pytest
import trimesh

from base3d import thickness as T
from base3d.nozzle import DEFAULT, Nozzle


def test_the_bars_are_counts_of_lines_and_layers():
    assert DEFAULT.wall == 0.8 and DEFAULT.plate == 0.4 and DEFAULT.lines(5) == 2.0
    fine = Nozzle(0.2, layer=0.1)
    assert fine.wall == 0.4 and fine.plate == 0.2 and fine.layers(4) == 0.4
    assert Nozzle(0.6, layer=0.3).line_width == 0.63


def test_a_nozzle_that_cannot_print_is_refused():
    with pytest.raises(ValueError):
        Nozzle(0.0)
    with pytest.raises(ValueError):
        Nozzle(0.2, layer=0.3)


def test_the_check_reads_the_bars_from_the_nozzle():
    # a 0.6 mm wall standing upright is one line of a 0.4 mm nozzle and three of a 0.2 mm nozzle
    wall = trimesh.creation.box(extents=(0.6, 10, 10))
    assert T.print_thin_spots(wall, nozzle=Nozzle(0.4), n=3000)[0]["short_of"] == "lines"
    assert T.print_thin_spots(wall, nozzle=Nozzle(0.2, layer=0.1), n=3000) == []
    assert T.print_thin_spots(wall, n=3000) == T.print_thin_spots(wall, nozzle=DEFAULT, n=3000)
