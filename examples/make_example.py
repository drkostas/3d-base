"""Builds docs/example.png: overlapping shapes, which matplotlib's 3D axes draw in the wrong order."""
from pathlib import Path

import numpy as np
import trimesh

from base3d import frame_on, render, save_png, tile
from base3d.show import SHEET_BG

box = trimesh.creation.box(extents=(40, 40, 12))
ball = trimesh.creation.icosphere(subdivisions=4, radius=14)
ball.apply_translation((0, 0, 12))
rod = trimesh.creation.cylinder(radius=4, height=70, sections=48)
rod.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (0, 1, 0)))
rod.apply_translation((0, 0, 12))
parts = [box, ball, rod]
colors = [(0.93, 0.93, 0.90), (0.95, 0.62, 0.35), (0.40, 0.62, 0.86)]
model = trimesh.util.concatenate(parts)
face_colors = np.vstack([np.tile(c, (len(p.faces), 1)) for p, c in zip(parts, colors)])

views = [(-60, 25), (120, 30), (-90, -55)]
imgs = []
for azim, elev in views:
    eye, target = frame_on(model, azim, elev, pad=0.9)
    imgs.append(render(model, eye, target, size=(520, 400), face_colors=face_colors, bg=SHEET_BG))
out = Path(__file__).resolve().parent.parent / "docs" / "example.png"
save_png(tile(imgs, cols=3, bg=tuple(int(255 * c) for c in SHEET_BG)), out)
print(out)
