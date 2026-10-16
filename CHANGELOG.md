# Changelog

## Unreleased

- `base3d.thickness`: how thick a part is at each point of its surface (a ray straight in from each sample point to the far side), `thin_spots(mesh, bar_mm)` for the places thinner than a printer can draw, grouped and thinnest first, and `face_thickness` to colour a picture by it. A surface written twice is passed through rather than read as a wall, and a closed mesh written inside out is read from the right side. `3d-base thickness part.stl --bar 0.8` prints the same as JSON and exits 1 when anything is under the bar. `rtree` is now a dependency, for trimesh's ray queries.

## 0.2.0

- A Claude Code skill for judging models from pictures, installed with `3d-base skill`

## 0.1.0

First release.

- `render`, a headless depth-buffer renderer with a headlight and crease-aware smooth shading
- `frame_on`, `tile`, `sheet` and `save_png` (PNG with the standard library only)
- `display_mesh`, the mesh with the same normals stored for web viewers
- `load_clean`, `voids`, `report` and `surface_points` for exported STL files
- The `3d-base` command with `render` and `check`
