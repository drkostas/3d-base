"""The GPU path of `render` against the CPU path, and how the path is chosen.

The comparisons need moderngl and an OpenGL context. Where none opens (a CI runner without a GPU or
a display), they are skipped and only the tests of the choice run.
"""
import numpy as np
import pytest
import trimesh

from base3d import show as R

needs_gpu = pytest.mark.skipif(not R.gpu_available(), reason="no OpenGL context opens here")


def sphere():
    return trimesh.creation.icosphere(subdivisions=4), None


def sharp_box():
    return trimesh.creation.box(extents=(3.0, 2.0, 1.0)), None


def two_parts():
    """A box and a sphere passing through it, each in its own colour."""
    box = trimesh.creation.box(extents=(2, 2, 2))
    ball = trimesh.creation.icosphere(subdivisions=3, radius=1.2)
    ball.apply_translation((0.8, 0.3, 0.4))
    both = trimesh.util.concatenate([box, ball])
    fc = np.vstack([np.tile([0.85, 0.2, 0.2], (len(box.faces), 1)),
                    np.tile([0.2, 0.4, 0.9], (len(ball.faces), 1))])
    return both, fc


def both_paths(mesh, fc, azim, elev, size=(400, 300), bg=R.SHEET_BG):
    eye, target = R.frame_on(mesh, azim, elev)
    cpu = R.render(mesh, eye, target, size=size, face_colors=fc, bg=bg, backend="cpu")
    gpu = R.render(mesh, eye, target, size=size, face_colors=fc, bg=bg, backend="gpu")
    return cpu, gpu


def silhouette(img, bg):
    return (img != np.array([int(255 * c) for c in bg])).any(axis=2)


@needs_gpu
@pytest.mark.parametrize("make", [sphere, sharp_box, two_parts])
@pytest.mark.parametrize("view", [(-45, 25), (-90, 10), (-90, -60), (135, 25)])
def test_the_gpu_draws_the_same_picture(make, view):
    mesh, fc = make()
    cpu, gpu = both_paths(mesh, fc, *view)
    assert gpu.shape == cpu.shape and gpu.dtype == np.uint8
    diff = np.abs(cpu.astype(int) - gpu.astype(int))
    a, b = silhouette(cpu, R.SHEET_BG), silhouette(gpu, R.SHEET_BG)
    iou = (a & b).sum() / (a | b).sum()
    assert diff.mean() < 0.01, diff.mean()                # in levels of 255, over every channel
    assert (diff.max(axis=2) > 1).mean() < 0.001          # a pixel off by more than a level is rare
    assert iou > 0.999, iou


@needs_gpu
def test_the_gpu_keeps_the_nearer_part_in_front():
    red = trimesh.creation.box()
    blue = trimesh.creation.box()
    blue.apply_translation((0, 3, 0))
    both = trimesh.util.concatenate([red, blue])
    colors = np.vstack([np.tile([1, 0, 0], (12, 1)), np.tile([0, 0, 1], (12, 1))])
    img = R.render(both, eye=(0, -10, 0), target=(0, 0, 0), size=(60, 60), face_colors=colors, backend="gpu")
    assert img[30, 30, 0] > 0 and img[30, 30, 2] == 0


@needs_gpu
def test_the_gpu_keeps_the_background_and_an_empty_mesh():
    m = trimesh.Trimesh(np.zeros((0, 3)), np.zeros((0, 3), int))
    img = R.render(m, (0, -5, 0), (0, 0, 0), size=(20, 10), bg=(0.83, 0.85, 0.88), backend="gpu")
    cpu = R.render(m, (0, -5, 0), (0, 0, 0), size=(20, 10), bg=(0.83, 0.85, 0.88), backend="cpu")
    assert (img == cpu).all()


def test_the_choice_follows_the_argument_then_the_environment(monkeypatch):
    m = trimesh.creation.icosphere(subdivisions=2)
    eye, target = R.frame_on(m, -45, 25)
    cpu = R.render(m, eye, target, size=(80, 60), backend="cpu")
    monkeypatch.setenv("BASE3D_RENDER", "cpu")
    assert (R.render(m, eye, target, size=(80, 60)) == cpu).all()
    monkeypatch.setenv("BASE3D_RENDER", "fast")
    with pytest.raises(ValueError):
        R.render(m, eye, target, size=(80, 60))
    with pytest.raises(ValueError):
        R.render(m, eye, target, size=(80, 60), backend="opengl")


def test_without_a_gpu_auto_draws_on_the_cpu_and_gpu_raises(monkeypatch):
    m = trimesh.creation.icosphere(subdivisions=2)
    eye, target = R.frame_on(m, -45, 25)
    cpu = R.render(m, eye, target, size=(80, 60), backend="cpu")
    monkeypatch.setattr(R, "_gl", lambda: None)            # where no context opens
    monkeypatch.delenv("BASE3D_RENDER", raising=False)
    assert (R.render(m, eye, target, size=(80, 60)) == cpu).all()
    assert not R.gpu_available()
    with pytest.raises(RuntimeError):
        R.render(m, eye, target, size=(80, 60), backend="gpu")
