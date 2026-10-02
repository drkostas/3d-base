"""3d-base command line."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .mesh import load_clean, report
from .show import SHEET_BG, VIEWS, frame_on, render, save_png, sheet


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="3d-base", description="Pictures of a 3D mesh, and a health check.")
    p.add_argument("--version", action="version", version=f"3d-base {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render one view, or a sheet of views, to PNG")
    r.add_argument("mesh")
    r.add_argument("-o", "--out", default="render.png")
    r.add_argument("--view", default="front-right", help=f"one of {', '.join(VIEWS)}, or 'sheet'")
    r.add_argument("--azim", type=float)
    r.add_argument("--elev", type=float)
    r.add_argument("--size", default="1400x1000")

    k = sub.add_parser("skill", help="install the Claude Code skill for judging models from pictures")
    k.add_argument("--dir", default="~/.claude/skills")

    c = sub.add_parser("check", help="faces, bodies, closed cavities and volume, after dropping slivers")
    c.add_argument("mesh")

    a = p.parse_args(argv)
    if a.cmd == "skill":
        dest = Path(a.dir).expanduser() / "3d-base"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(__file__).parent / "skill" / "SKILL.md", dest / "SKILL.md")
        print(f"installed {dest / 'SKILL.md'}")
        return 0
    if a.cmd == "check":
        rep = report(a.mesh)
        print(json.dumps(rep, indent=1))
        return 1 if rep["voids"] else 0
    m, _ = load_clean(a.mesh)
    w, h = (int(x) for x in a.size.lower().split("x"))
    if a.view == "sheet":
        img = sheet(m, size=(w // 2, h // 2))
    else:
        azim, elev = (a.azim, a.elev) if a.azim is not None and a.elev is not None else VIEWS[a.view]
        eye, target = frame_on(m, azim, elev)
        img = render(m, eye, target, size=(w, h), bg=SHEET_BG)
    save_png(img, a.out)
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
