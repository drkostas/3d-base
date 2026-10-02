---
name: 3d-base
description: Use when judging or checking a 3D model, a mesh, an STL or a design for 3D printing from pictures, or when rendering views of a mesh headlessly (no display, no OpenGL, no browser). Covers which views to render, how to read a contact sheet, what pictures get wrong and what to measure instead, how to check an exported STL for slivers, extra bodies and sealed cavities, and how to show pictures to a person who has to decide.
---

# Judging a 3D model from pictures with 3d-base

3d-base renders a mesh with a depth buffer, a key light, a headlight from the camera and
crease-aware smooth shading, and it checks exported STL files. The library is small. The hard part
is reading the pictures honestly, and most of this skill is about that.

The one rule everything else follows from. Your eye is reliable about shape and absence (is the
limb bent or straight, is a part there at all, is a view black). It is unreliable about contact,
bulges, lengths and surface quality (do two parts touch, does that bump stand proud, is that
sphere faceted). Say what the pixels show, measure before changing anything, and when the
measurement disagrees with the picture, say so plainly instead of dropping the observation.

## Install and the two commands

```bash
pip install 3d-base          # imported as base3d
3d-base render part.stl -o part.png                  # one view, front right
3d-base render part.stl --view below -o below.png    # any key of base3d.show.VIEWS
3d-base render part.stl --azim 30 --elev 20 -o x.png
3d-base render part.stl --view sheet -o sheet.png    # six views in a grid
3d-base check part.stl       # faces, bodies, voids, watertight, volume, extents; exit 1 on a void
```

```python
import trimesh
from base3d import frame_on, render, save_png, sheet, tile, load_clean, voids, report, surface_points
from base3d.show import VIEWS, SHEET_BG, display_mesh, corner_normals

mesh, bodies = load_clean("part.stl")          # always load through this, see the STL section
eye, target = frame_on(mesh, azim=-45, elev=25)  # azim turns about +Z from +X, elev above XY
img = render(mesh, eye, target, size=(1400, 1000), bg=SHEET_BG)   # (H, W, 3) uint8
save_png(img, "part.png")
```

`render` also takes `face_colors` (one RGB per face, 0 to 1), `headlight`, `fov` (vertical,
degrees) and `naive_normals`. `sheet(mesh, views=..., size=..., cols=...)` accepts view names from
`VIEWS` or `(azim, elev)` tuples. `tile(images, cols=...)` lays out any images of equal size.

## Render enough views, including from below and behind

A single three-quarter view hides exactly the things that go wrong. A part sunk into another part
is invisible from the front and obvious from below. A limb on the wrong side of a body is invisible
from the side and obvious from above. Every time the model changes, render the whole set and look
at all of it.

```python
VIEWS13 = [(-60, 26), (0, 0), (-45, 8), (45, 8), (180, 0), (-135, 8), (135, 8),
           (90, 0), (-90, 0), (-60, 89), (-60, 55), (-60, -89), (-60, -40)]
# default, front, front diagonals, back, back diagonals, two sides, top, top diagonal,
# below, below diagonal (here "front" is +X, set it to wherever your model faces)
img = sheet(mesh, views=VIEWS13, size=(620, 520), cols=3)
```

- The four square views miss what a three-quarter view is for. A rim that overhangs, a limb held away
  from a body and the splay of two limbs read at 45 degrees and hide at 0 and 90.
- Below and behind are the views that catch parts hanging under a surface, a support gate below a
  base, and a small part under the surface it should stand on. They are also the views a fixed lamp leaves
  dark. With only a key light, the model's pixels in a view from below averaged about 0.19 of full
  brightness (0.11 on another model), against 0.42 to 0.84 for readable views. `HEADLIGHT` fixes
  this by construction, because any face you can see faces the camera.
- Do not trust your eye to find dark views. Looking at thirteen views, the eye flagged the black
  one and missed three that were dim rather than black. Measure it.

```python
import numpy as np
def lit(img, bg=SHEET_BG):
    """Mean brightness of the model's own pixels, 0 to 1. Below about 0.34, do not judge from it."""
    g = img.astype(float)
    on = np.linalg.norm(g - np.array(bg) * 255, axis=2) > 14
    return float(g[on].mean() / 255) if on.sum() > 150 else None
```

- If the mesh carries colours, pass them as `face_colors`. A one-grey sheet hid the extra rim the slicer
  added, because added material and model looked the same.
- The names in `VIEWS` describe where the camera is in the world (`"front"` is the camera on
  minus Y). They say nothing about which way your part faces.

## Framing and picture size

`frame_on` places the eye at `3.4 * pad * r` from the centre of the bounding box, where `r` is half
the bounding box diagonal and `pad` defaults to 1.22. With the default `fov` of 26 degrees
(vertical) that fits the whole mesh in a picture wider than it is tall, and not in a tall one. A
long part rendered at 560 by 760 runs off the left and right edges even at the default pad, and
lowering `pad` to make the part bigger makes it worse (ten of twelve tiles were cut that way). Read
the pixels back instead of trusting the framing.

```python
def touches_edge(img, bg=SHEET_BG, border=3):
    """Which sides of the picture the model runs off. Empty means the whole part is in view."""
    g = np.linalg.norm(img.astype(float) - np.array(bg) * 255, axis=2)
    sides = {"top": g[:border], "bottom": g[-border:], "left": g[:, :border], "right": g[:, -border:]}
    return [s for s, a in sides.items() if a.max() > 14]
```

Size decides what a picture can answer. A part forty pixels long cannot show its thickness or its
bend. A 200 pixel tile of a fifteen-part assembly cannot tell "bent" from "foreshortened" or
"touching" from "in front of". Keep two kinds of picture. The assembled sheet is for posture and
placement (what stands on what, which way things face). A sheet of one part, large, is for that
part's own shape and for whether two parts touch. Before claiming a fault in a part's shape, open
its own sheet at full size. Three faults read off an assembled sheet in one sitting (a limb "bent",
a held part "stuck to the body", a base "tilted") were all projection, and the dedicated sheets
showed each one correct.

## How to read a sheet

1. Open the image and look at it. A file that exists, serves and passes its checks can still be
   black, stale, too small or cropped.
2. Go through every view by its label, not by position and not by picking the interesting cells.
   Choosing three cells out of thirteen by eye once skipped the only view that looked at an engraved
   detail, and the reading "the detail is missing" came from that.
3. For each observation, decide which kind it is. Shape and absence you can act on. Contact,
   bulges, lengths, proportions, surface and left versus right need a measurement first.
4. Measure, then report both. "The picture shows X, the measurement says Y" is a finding.
5. Value what the eye finds that no check asks about. A straight limb among three bent ones, one
   small part turned in, a black view, and a whole part covered by another (a correct depth buffer once
   showed that a cap was larger than the part it sat on and hid it completely) were all found by
   looking.

In one session the record was two real faults found by eye that measurement had missed, and three
eye readings that measurement disproved. Use both, and trust neither alone.

## What to measure instead of looking

| the picture seems to show | what it was | measure this instead |
|---|---|---|
| a bump standing proud of a rod | an oblique slice, radius inflated by 1/cos(angle) | width perpendicular to the local direction (uniform to 0.01 mm) |
| a part floating 3.8 mm above a surface | one ray from the centre hit a concave valley | nearest distance from many surface points (0.26 mm) |
| limbs that read short | foreshortening | lengths along each part's own axis |
| a part hanging off an edge | the intended diagonal placement | where the contact points are, in plan |
| a part 40% too wide | an axis-aligned box on a part turned 45 degrees | extents in the part's own frame (7%) |
| a sphere that is not round | spread of vertices, dense around sockets | spread of evenly sampled surface points (`surface_points`) |
| limbs "out" at 78 and 72 degrees | out in the wrong plane, aimed at the camera | the angle in the plane the person meant, next to a reference |

- Probe a region, not a point. A single point or ray on a thin or curved feature can say anything.
- A bounding box centre is dragged by anything that sticks out, and "top minus radius" fails when
  the top is cut. Fit a sphere to points on the part instead, and drop outliers. A centre found the
  first two ways was 1.08 mm low and made a round part read as an oval.
- Measure the thing the requirement is about. A smoothness check reported 83.7 degrees on a rod
  that is 7.5 degrees bare, because it was measuring the socket cut into it. Exclude joints and
  added hardware, or measure the part before they are added.

## Surface is the renderer's opinion

Shape lives in the silhouette, which a renderer cannot invent. Surface (facets, dimples, burrs,
seams) is entirely the shading model, and a wrong shading model looks exactly like a defect.

- First check the scale. A flat facet on a sphere sinks `L**2 / (8 * r)` below the true surface
  (`L` is the edge length). On a 17.95 mm sphere with 1.04 mm edges that is 0.008 mm, 0.13 of a
  pixel at the scale it was viewed and a fortieth of a 0.2 mm print layer. Anything below a pixel
  and below a layer cannot be what you see.
- Then render the same mesh two ways and put them side by side. `CREASE_DEG` is read at render
  time, so setting it to 0 gives flat shading from the same code.

```python
import base3d.show as show
smooth = render(mesh, eye, target, size=(600, 600))
show.CREASE_DEG = 0.0
flat = render(mesh, eye, target, size=(600, 600))
show.CREASE_DEG = 32.0
naive = render(mesh, eye, target, size=(600, 600), naive_normals=True)
g = lambda im: im.astype(float).mean(axis=2) / 255
on = np.abs(g(flat) - g(flat)[0, 0]) > 0.02
spurs = lambda im: int(((g(im) - g(flat)) > 0.15)[on].sum())   # bright detail flat shading lacks
```

- Smoothing must not add bright detail that flat shading does not have. On a sphere with three
  small cuts, the default shading produced 0 pixels brighter than flat by 0.15, and the naive
  method (`naive_normals=True`, which averages over every face at a vertex) produced 320, seen as
  bright spikes round every cut. That naive version once made clean recesses look like boolean
  burrs, and the mirrored pair of cuts look unequal. Keep the faulty method as a red case so the
  check proves it can still see the fault.
- If smoothing fails on a mesh, `corner_normals` prints "smooth normals failed" and the mesh is
  shaded flat. Read the output. A silent fall back to flat once put the faceted look back on three
  sheets for a whole rebuild.
- Render the mesh that will be printed, not a lighter copy. A viewer that served 14% of the faces
  turned two spheres into polyhedra and split the model into 74 pieces. After fixing such a thing,
  look again at full detail, in case the light copy had hidden a real fault.
- For a web viewer, export `display_mesh(mesh)`. A GLB with no normals renders unlit when smooth
  shading is on, and these normals make the viewer agree with the pictures.

## Traps

**Render a downloaded mesh before measuring it.** A sourced part was fitted upside down for an hour
(a table said turn minus 90 degrees about X where plus 90 was right), and four repairs were written
against measurements that were all true of the inverted part. The "bottom slice" was the button
and the "cavity" was the dome seen from the wrong end. Rendering the raw mesh with the eye on +x, +y
and +z took a minute and answered it. Say out loud which way is up and which way it faces, then
measure. The same goes for any orientation that is declared rather than derived. Deriving "up"
from features failed twice on one part (the largest flat area was a top panel, not the base).

**A name is not a direction.** Of two parts named front and back, the one named back sat 13.4 mm
further forward. A vertex centroid moved forward when engraved detail added thousands of vertices
there, which reversed a facing vector. A view picker that chose a side by where the dark pixels sat
picked the mirror image. Reasoning about signs failed eight times in one day, and every sign
settled by doing it both ways and looking worked first time. Rotate both ways and keep the one
nearer the target, or render plus and minus 36 degrees side by side. Take facing from a feature that
is already aimed, through a fitted centre. Check left and right by projecting a known vector onto
the camera's axes, never by reading handedness off the picture.

**A part's own frame hides wrong placement.** Turning each part onto its own principal axes makes it
legible, and it makes a wrongly placed part look exactly like a correctly placed one. A part lying
90 degrees on its side survived a dozen reviews that way, and was obvious in the first picture drawn
in world orientation. When the question is what a part is, use its own frame. When the question is
where it sits or which way it faces, draw it in world orientation, on the assembly, and say in the
caption which one it is. The reverse also bites. A part whose long axis is diagonal looks like a
featureless block from every world-axis camera, so align the camera to the part when judging its
shape.

**Stale pictures.** A picture can be out of date because the camera changed, not only the model.
After a shading fix not one vertex moved, so a freshness check over the geometry said every picture
was current while all of them still showed the invented facets. Compare each picture against
everything that decides it (the mesh, the renderer, the sheet script). Turning on the extended check
should immediately mark old pictures stale, and if it does not, it is not measuring the new inputs.
Build any fingerprint over files sorted by full path. Sorted by bare name, two files with the same
name made the hash differ between processes, and the pictures were redrawn for ever.

**Draw the mesh the product uses.** A sheet rendered a recorded copy of two limbs that bowed 5.04
mm where the limbs in the assembly bowed 3.70, so the reviewer was shown a part 36% more bent than
the real one. Another sheet drew a part from the state before a grip was added to it and was missing 63%
of its volume. Check that the volume of what is drawn matches what is built.

**Compare against the named reference.** When the person names or implies a reference model, find
it, render or screenshot it, measure it and put it next to yours before asking anything. One glance
at the two side by side settled what three rounds of questions had not, and turned taste into
numbers that can be hit (limbs 43 and 20 degrees below horizontal, contact points 47% of the base apart). When
a number and a picture disagree, suspect the number answers a different question (another plane,
frame or end).

**Pick the baseline by name.** Seven wrong readings in one session all came from a bad comparison,
never a bad subject. A nearby point used as "smooth surface" on a sphere that curves away, a fit
contaminated by the cut it was meant to measure, a parts dictionary picked because it was in scope.
Index views, parts and cells by their label. Prefer a reference that proves itself (build the
object with and without the feature and subtract, which reads 0.00 where there is no feature). Run
a new check against both candidate baselines and confirm which one makes it mean what its sentence
says.

## Checking an exported STL

OpenCascade (and tools on it such as build123d and CadQuery) writes zero-area triangles at sphere
poles. A plain sphere then reports `is_watertight=False` and splits into pieces like `[1, 1, 2202]`
faces. `load_clean` drops those faces, and after that a second body is real.

```python
mesh, bodies = load_clean("part.stl")
print(report("part.stl"))           # faces, bodies, voids, watertight, volume, extents
assert len(bodies) == 1, [round(float(b.volume), 3) for b in bodies]
assert not voids(bodies)            # negative volume means a sealed cavity
```

- A body with negative volume is a sealed cavity. The first one found was a 332-face inward shell of
  minus 0.12 cubic centimetres, a socket buried 3 mm under the surface that no post could enter.
  Start every bore slightly proud of the surface.
- `is_watertight` alone is close to worthless. Two detached pieces are each watertight, a slot that
  cuts a part in two leaves two watertight shells, and concatenating cutters instead of uniting them
  left three sealed voids in a mesh that was still watertight. Assert the body count and the
  dimensions you expect.
- One body is not the same as a sound solid. A single connected piece with nine broken faces
  (Euler number minus 93) was not watertight, and boolean tools refused it. Read the `watertight`
  field of `report`, not only `bodies`.
- If the body count is close to the face count, the mesh is unwelded (a textured export gave one
  body per face, 15,488 of them). Call `mesh.merge_vertices()` and count again.
- Tiny bodies of near-zero volume are noise from a union or a download, not defects. An absolute
  threshold of 0.001 cubic millimetres let them through, so compare each body to the largest one.
  Before calling a negative body a cavity, check that it has real size.
- Any "keep the largest piece" cleanup must refuse to discard much. One such step deleted 7,794
  cubic millimetres of model and then reported a clean single body. Refuse above about 5%.
- A bounding box is not a feature. A box height of 18.24 mm was a raised end of the part, while the
  surface to fit measured 4.19 mm thick.
- Use `surface_points(mesh, n)` when points decide anything (where a support or contact goes). It
  is seeded, so the same input gives the same design on every run.

## Showing pictures to a person for a decision

- Never ask about a shape in prose. Render each candidate and show the pictures. A question with
  options written in words asks the person to imagine two shapes and compare them from memory.
- Build every option the same way, so the only difference is the thing in question. A first
  comparison rendered the current part from its source mesh and the alternatives as fresh
  geometry, and the numbers moved for that reason.
- Put the numbers on the picture. Values printed to stdout are not in the image the person opens.
  Fit the caption to the width (shrink the font until it fits) and fail if it cannot fit.
- Open what you built before sending it. The disguises seen so far are black, stale, too small,
  not reachable, and present but saying nothing. Every automated check was green through all five.
- Give each picture a guard that can fail on its own (the edge check, the brightness check, the
  freshness check), and prove each one goes red on the broken picture before trusting it.
- Show the exact element the person named. A fix on one of a mirrored pair goes on both, shown side
  by side, because the person sees both at once.
- Say in the caption whether a view is in world orientation or in the part's own frame.

## Before you say a model is right

- [ ] All thirteen views rendered from the current mesh and current renderer, each one opened.
- [ ] Every view at least 0.34 bright on the model's pixels and not touching an edge.
- [ ] Each shape claim checked on a single-part sheet at full size, each contact or bulge claim measured.
- [ ] Any surface defect rendered flat and smooth side by side before it is called real.
- [ ] Orientation checked by rendering the raw mesh on three axes and by projection, not by name.
- [ ] `3d-base check` shows the bodies and voids you expect, with dimensions asserted.
