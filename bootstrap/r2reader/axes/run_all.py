#!/usr/bin/env python3
"""The DIAG-2026-10-22 capture set through instrument.py, in parallel.

Run from the worktree root:  python bootstrap/r2reader/axes/run_all.py
[NAME ...]  (no names = every capture; names select).  Renders it needs are
made first by make_renders() (camera.py, seeded, written under
bootstrap/build/axes/renders/); the print of record's pages are regenerated
under bootstrap/build/axes/record/ by d84a9637's gen.py (see the note)."""
from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

PY = sys.executable
ROOT = os.getcwd()
INS = "bootstrap/r2reader/axes/instrument.py"
S1 = "bootstrap/build/stage1/lower/r2"
REC = "bootstrap/build/axes/record"
RND = "bootstrap/build/axes/renders"
PHOTOS = "scratch/typed"


def s1(p: int) -> list[str]:
    return ["--page", f"{S1}/page_p{p}.json", "--grid",
            f"{S1}/page_p{p}.grid.txt"]


def rec(p: int) -> list[str]:
    return ["--page", f"{REC}/page_p{p}.json", "--grid",
            f"{REC}/page_p{p}.grid.txt"]


def render(name: str, p: int = 0) -> list[str]:
    return [f"{RND}/page_p{p}.{name}.pgm", "--kind", "render", "--sidecar",
            f"{RND}/page_p{p}.{name}.json"] + s1(p)


CAPTURES: dict[str, list[str]] = {
    "s1-p0-grid": [f"{S1}/page_p0.grid.txt", "--kind", "grid"] + s1(0),
    "rec-p0-grid": [f"{REC}/page_p0.grid.txt", "--kind", "grid"] + rec(0),
    "s1-p0-perfect-s2": render("perfect-s2"),
    "s1-p0-perfect-s3": render("perfect-s3"),
    "s1-p0-perfect-s7": render("perfect-s7"),
    "s1-p0-raster": [f"{S1}/page_p0.pbm", "--kind", "raster"] + s1(0),
    "s1-p0-nominal-b030": [f"{S1}/page_p0.nominal-b030.pgm", "--kind",
                           "render", "--sidecar",
                           f"{S1}/page_p0.nominal-b030.json"] + s1(0),
    "s1-p1-nominal-b030": [f"{S1}/page_p1.nominal-b030.pgm", "--kind",
                           "render", "--sidecar",
                           f"{S1}/page_p1.nominal-b030.json"] + s1(1),
    "s1-p2-nominal-b030": [f"{S1}/page_p2.nominal-b030.pgm", "--kind",
                           "render", "--sidecar",
                           f"{S1}/page_p2.nominal-b030.json"] + s1(2),
    "s1-p0-nominal-s7-b030": render("nominal-s7-b030"),
    "photo1": [f"{PHOTOS}/1.pgm", "--kind", "photo"] + rec(0),
    "photo2": [f"{PHOTOS}/2.pgm", "--kind", "photo"] + rec(1),
    "photo3": [f"{PHOTOS}/3.pgm", "--kind", "photo"] + rec(2),
    "photo4": [f"{PHOTOS}/4.pgm", "--kind", "photo"] + rec(2),
    # the genie truth checked where the warp is known
    "genie-s1-p0-nominal-b030": [f"{S1}/page_p0.nominal-b030.pgm", "--kind",
                                 "render", "--sidecar",
                                 f"{S1}/page_p0.nominal-b030.json", "--genie"]
    + s1(0),
    "genie-s1-p0-nominal-s7-b030": render("nominal-s7-b030") + ["--genie"],
}
# the same frames turned (does the failing diagonal follow the page or the
# image?) and the two COUNTERFACTUAL tie rules (not the reader)
for k in (1, 2, 3):
    CAPTURES[f"s1-p0-grid-rot{k}"] = CAPTURES["s1-p0-grid"] + ["--rot90",
                                                               str(k)]
    CAPTURES[f"s1-p0-perfect-s3-rot{k}"] = (CAPTURES["s1-p0-perfect-s3"]
                                            + ["--rot90", str(k)])
for base in ("s1-p0-grid", "s1-p0-perfect-s2", "s1-p0-perfect-s3",
             "s1-p0-perfect-s7", "s1-p0-raster", "s1-p0-nominal-b030",
             "photo1"):
    CAPTURES[f"cf-ft-{base}"] = CAPTURES[base] + ["--ft-rule", "centre"]
    CAPTURES[f"cf-fm-{base}"] = CAPTURES[base] + ["--fm-rule", "r0"]
    CAPTURES[f"cf-both-{base}"] = CAPTURES[base] + ["--ft-rule", "centre",
                                                    "--fm-rule", "r0"]


def make_renders() -> None:
    perfect = ["--persp", "0", "--blur", "0", "--noise", "0", "--illum", "0",
               "--rotate", "0"]
    jobs = [(f"perfect-s{spm}", ["--spm", str(spm)] + perfect)
            for spm in (2, 3, 7)]
    jobs.append(("nominal-s7-b030", ["--spm", "7", "--persp", "0.02",
                                     "--blur", "0.30"]))
    os.makedirs(RND, exist_ok=True)
    for name, args in jobs:
        out = f"{RND}/page_p0.{name}.pgm"
        if not os.path.exists(out):
            subprocess.run([PY, "bootstrap/r2/camera.py", f"{S1}/page_p0.pbm",
                            out, "--sidecar", f"{S1}/page_p0.json"] + args,
                           check=True)


def one(name: str) -> str:
    r = subprocess.run([PY, INS, "run"] + CAPTURES[name] + ["--name", name],
                       capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def main() -> None:
    make_renders()
    names = sys.argv[1:] or list(CAPTURES)
    with ThreadPoolExecutor(max_workers=9) as ex:
        for out in ex.map(one, names):
            print(out[-2000:], flush=True)


if __name__ == "__main__":
    main()
