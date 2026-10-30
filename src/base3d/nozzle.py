"""The nozzle a part is printed with, and the smallest sizes that follow from it.

A slicer draws a wall as lines about as wide as the nozzle, and stacks a part in layers of the layer
height. A feature narrower than two lines prints as one weak, wavy line or not at all, and a plate
thinner than two layers is a single layer. `Nozzle` holds the nozzle's diameter and the layer height
and gives every minimum as a count of lines or layers, so a design written against it follows the
nozzle it is printed with and a check reads the same bars.

    n = Nozzle(0.4)               # a 0.4 mm nozzle at 0.2 mm layers
    n.wall                        # 0.8, two lines across
    n.plate                       # 0.4, two layers through
    n.lines(5)                    # 2.0
    Nozzle(0.2, layer=0.1).wall   # 0.4

Counts are in nozzle diameters. A slicer's own line is a little wider (about 1.05 times the diameter
by default, `line_width`), so a size of two diameters always fits two of its lines.
"""
from __future__ import annotations

from dataclasses import dataclass

#: a slicer's default extrusion width, as a share of the nozzle's diameter
LINE_SHARE = 1.05


@dataclass(frozen=True)
class Nozzle:
    diameter: float = 0.4
    layer: float = 0.2

    def __post_init__(self):
        if not (self.diameter > 0 and self.layer > 0):
            raise ValueError(f"a nozzle needs a positive diameter and layer height, not {self}")
        if self.layer > self.diameter:
            raise ValueError(f"a layer of {self.layer} mm is thicker than a {self.diameter} mm nozzle can lay")

    def lines(self, n: float) -> float:
        """The width of `n` lines side by side, in mm."""
        return round(n * self.diameter, 6)

    def layers(self, n: float) -> float:
        """The height of `n` layers, in mm."""
        return round(n * self.layer, 6)

    @property
    def line_width(self) -> float:
        """The width of one line as a slicer draws it by default."""
        return round(LINE_SHARE * self.diameter, 6)

    @property
    def wall(self) -> float:
        """The thinnest wall that prints as two lines."""
        return self.lines(2)

    @property
    def plate(self) -> float:
        """The thinnest plate lying flat that prints as two layers."""
        return self.layers(2)


#: the common nozzle, 0.4 mm at 0.2 mm layers
DEFAULT = Nozzle()
