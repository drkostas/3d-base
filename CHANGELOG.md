# Changelog

## 0.3.1

- `solid_from_skin` takes the inner surface as what a ray from the centre meets first, among the faces that point toward it, and no longer takes `reach`. A brim's top is kept because the shell stands between it and the centre, not because it lies far out. A reach that cut across the inner surface left the part beyond the cut in place under a floor fanned above it, with the shell's own thin wall there, on a cap whose inside sits further from the centre round the ears than at the top.
- `solid_from_skin` winds the fan with the skin: each fan triangle runs its boundary edge the other way from the face that owns it. The edges were sorted before they were chained into loops, which lost their direction, so any fan that was not flat faced the wrong way, and the solid read with the wrong volume and could not be cut cleanly.
- `solid_from_skin` removes, with the inner surface, any island of faces inside it that the centre cannot see (the side of a groove hidden by its lip); fanned on its own, an island would have become a sealed pocket.
- The skill says that nothing prints at one line: a thickness that runs down to one line at an edge is changed at the thin end, never offered as a choice.
- `solid_from_skin` takes the inner surface as the largest connected region of candidate faces by area, not the region of the face nearest the centre, which could be a stray pair of faces.

## 0.3.0

- `show.sections` draws each cut face from the cut's outline (`show.cut_face`), so a hole in the part stays a hole in the picture. trimesh's own capping came back open on a mesh whose outline carried a zero-area loop and drew a hollow part as a solid disc.
- `mesh.solid_from_skin(mesh, centre, reach)` makes a hollow part solid by removing its inner surface and closing the skin, so a cavity cut afterwards is the only inside it has. Filling a hollow part by uniting a fill with it leaves air against the inner surface, which a slicer prints as tunnels.
- `show.sections` needs shapely and whichever triangulator trimesh finds, not mapbox-earcut by name.
- The skill has a section of trimesh calls that cost a build each to learn: the cut and section functions, batching `contains` and ray queries, `split` on an open mesh, booleans in 32 bits, icospheres sharing directions, revolve profiles, and `centroid`.
- `show.sections(mesh)` cuts the part in half three ways, across its own principal directions, and shows each half coloured by its wall thickness with the cut face in blue, for looking at a part before changing it. `3d-base sections part.stl -o cuts.png` writes the same. Needs shapely and mapbox-earcut, installed with `3d-base[sections]`.
- `mesh.sound(mesh)` is one call for whether a part is sound to print, with every reason it is not in plain words: not closed, more than one piece, a sealed void, a file that reads back with a hole or a loose piece, a wall too thin over a real distance. `3d-base sound part.stl` does the same and exits 1 on any fault.
- `show.caption(text, width)` draws a caption into an image to stack with pictures. It wraps words into lines at one type size rather than shrinking the type, and only a word wider than the band shrinks it. Needs Pillow, installed with `3d-base[captions]`.
- `as_written` counts as loose only the pieces outside the largest one. A closed shell inside the part overlaps it, and a slicer prints overlapping shells as one solid.
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
