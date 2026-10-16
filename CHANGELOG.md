# Changelog

## Unreleased

- `as_written` reports `loose_mm3`, the volume of every piece but the largest, and is `ok` when there is no hole and nothing loose beyond it (0.5 mm3 by default). A boolean's slivers at a touching edge pass, a real second piece does not.
- `print_thin_spots` reads a place's `typical_width_mm` from the points short of the bar it names. A group split evenly between an upright wall and a nearly flat plate averaged the two and reported a width of thousands of millimetres.
- `base3d.mesh.as_written(mesh)` writes the mesh as an STL, reads it back as a slicer would, and counts bodies, holes (edges with an odd number of faces) and touches (edges shared by four faces). A boolean can leave vertices apart only by their index, and a 32-bit file welds them.
- The skill has a section on walls that print, the read-back check, and booleans that leave touching surfaces.
- `print_thin_spots(..., backed_mm=1.0)` leaves out ridges, teeth and grooves on a thick wall. A point whose ray meets the part again within `backed_mm` after leaving it is detail, which the slicer draws as a bump in the outer line, and a free wall has open space behind it.
- `print_thin_spots(mesh)` judges each wall as the part lies on the plate. A wall standing upright needs two lines across a layer (`line_mm`, 0.8) and a plate lying flat needs two layers through it (`layer_mm`, 0.4), and a sloping wall is judged both ways. Each place says which it is short of. `3d-base thickness part.stl --printed` does the same from the command line, with the part's +z up.
- `thin_spots` gives each place its median reading as `typical_mm`, beside the thinnest one. Material is really thin right next to a sharp edge, so a small place with a low `mm` is an edge. A wall too thin to print is large and thin throughout.
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
