"""e041 S11 — synthetic 2400 dpi scans of a mixture-probe page, for e041_mixture_readout's smoke test.

Writes a small manifest + patterns npz to the S11 contract (tag "S11-synth": five black fiducials, ten
patches covering c3 and c2, cmy4 with replicates, the two dot-mixed arms, a toner-black cmyk5 arm, the
cmy8-engine arm under both magentas and the white-free {C,M} arm) and paints a page from the npz's DOT-LEVEL
planes: each plane's dots in that toner's colour (--toner-rgb, default a printed-looking C, M, Y, K),
overlaps multiply reflectances, K black; the bar in the planes of the alphabet's first non-white
state.  The 600 dpi raster is mapped through a pose by e041_probe_synth.paint (imported: shift, scale,
rotation, optional 180 deg turn, Gaussian blur, seeded noise).  The synthetic dots_sha256 hashes a plane
code (C + 2M + 4Y + 8K) per dot, not the generator's palette index; the readout never reads it.
--plane-offset PLANE DY DX (repeatable, scan px, page-aligned) paints that plane's ink displaced by a
sub-dot offset (paint_offset_planes: every plane through the pose plus its own shift at scan resolution,
layers multiplied, then blur and noise) — the per-plane registration smoke test.

    PYTHONPATH=src:. env/bin/python -m measure.e041_mixture_synth --out /tmp/x --name clean
    PYTHONPATH=src:. env/bin/python -m measure.e041_mixture_synth --out /tmp/x --name blur \\
        --blur-px 3 --noise-sd 8 --rot180 --shift-mm 1.2 -0.7 --rot-deg 0.2 --scale 1.003
    PYTHONPATH=src:. env/bin/python -m measure.e041_mixture_synth --out /tmp/x --name offs \\
        --blur-px 1.5 --noise-sd 4 --plane-offset Y -6 0 --plane-offset M 0 2
    (--manifest M paints the generator's own manifest + <tag>-patterns.npz beside it, at its page size.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage

from measure.e041_probe_synth import SCAN_DPI, dot_to_mm, mm_to_dot, paint

DPI = 600
PAGE_MM = (100.0, 80.0)
PATTERN_DOTS, SOLID_DOTS = 93, 24
PLANES = ("C", "M", "Y", "K")
TONER_RGB = {"C": (30, 150, 225), "M": (215, 40, 120), "Y": (245, 225, 30), "K": (25, 25, 30)}
M_SOLID, M_CORNER = (240, 0, 192), (255, 0, 255)
SINGLE_RGB = {"W": (255, 255, 255), "C": (0, 255, 255), "Y": (255, 255, 0), "K": (0, 0, 0)}
ENGINE_RGB = {"CM": (0, 0, 255), "CY": (0, 255, 0), "MY": (255, 0, 0), "CMY": (0, 0, 0)}
CMY8 = ["W", "C", "M", "Y", "CM", "CY", "MY", "CMY"]
# (arm, alphabet, M rgb, cell_dots, mix, fraction, method, neutral, replicate)
SYNTH_PATCHES: list[tuple[str, list[str], tuple[int, int, int], int, str, str, str, str, int]] = [
    ("A09", ["W", "C", "M", "Y"], M_SOLID, 3, "", "uniform", "default", "process", 0),
    ("A09", ["W", "C", "M", "Y"], M_SOLID, 3, "", "uniform", "default", "process", 1),
    ("A12", ["W", "C", "M", "Y"], M_SOLID, 2, "", "uniform", "default", "process", 0),
    ("A20", CMY8, M_SOLID, 3, "dotmix", "uniform", "default", "process", 0),
    ("A20", CMY8, M_SOLID, 3, "dotmix", "uniform", "default", "process", 1),
    ("A21", CMY8, M_SOLID, 2, "dotmix", "whiteheavy", "highlpi", "process", 0),
    ("A14", ["W", "C", "M", "Y", "K"], M_SOLID, 3, "", "uniform", "default", "toner", 0),
    ("A17", CMY8, M_CORNER, 3, "engine", "uniform", "default", "process", 0),
    ("A16", ["C", "M"], M_SOLID, 3, "", "uniform", "default", "process", 0),
    ("A18", CMY8, M_SOLID, 3, "engine", "uniform", "default", "process", 0),
]


def dotmix_masks(cd: int) -> dict[str, dict[str, np.ndarray]]:
    """Fixed dot layouts of the overlap states inside one cell: state -> plane -> (cd, cd) bool."""
    i, j = np.indices((cd, cd))
    if cd == 3:
        chk = (i + j) % 2 == 0                                  # 5 dots
        diag = (i + j) % 3
        return {"CM": {"C": chk, "M": ~chk}, "CY": {"C": chk, "Y": ~chk}, "MY": {"M": chk, "Y": ~chk},
                "CMY": {"C": diag == 0, "M": diag == 1, "Y": diag == 2}}
    d = i == j                                                  # 2 dots
    return {"CM": {"C": d, "M": ~d}, "CY": {"C": d, "Y": ~d}, "MY": {"M": d, "Y": ~d},
            "CMY": {"C": d, "M": (i == 0) & (j == 1), "Y": (i == 1) & (j == 0)}}


def state_planes(name: str, cd: int, mix: str, neutral: str) -> np.ndarray:
    """(4, cd, cd) uint8 ink of one cell in state `name`."""
    out = np.zeros((4, cd, cd), np.uint8)
    if name == "W":
        return out
    if mix == "dotmix" and len(name) > 1:
        for pl, m in dotmix_masks(cd)[name].items():
            out[PLANES.index(pl)][m] = 1
        return out
    letters = "CMY" if name == "K" and neutral == "process" else name
    for ch in letters:
        out[PLANES.index(ch)] = 1
    return out


def compose(states: np.ndarray, alphabet: list[str], cd: int, mix: str, neutral: str) -> np.ndarray:
    cells = states.shape[0]
    lut = np.stack([state_planes(s, cd, mix, neutral) for s in alphabet])        # (S, 4, cd, cd)
    blk = lut[states]                                                            # (cells, cells, 4, cd, cd)
    planes = np.zeros((4, PATTERN_DOTS, PATTERN_DOTS), np.uint8)
    n = cells * cd
    planes[:, :n, :n] = blk.transpose(2, 0, 3, 1, 4).reshape(4, n, n)
    return planes


def probs(alphabet: list[str], fraction: str) -> np.ndarray:
    S = len(alphabet)
    if fraction == "whiteheavy" and "W" in alphabet:
        p = np.full(S, 0.5 / (S - 1))
        p[alphabet.index("W")] = 0.5
        return p
    return np.full(S, 1.0 / S)


def build(seed0: int = 41000) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    W, H = PAGE_MM
    fids = [("F0", 6.0, 6.0, 3.0), ("F1", W - 9.0, 6.0, 3.0), ("F2", 6.0, H - 9.0, 3.0),
            ("F3", W - 9.0, H - 9.0, 3.0), ("F4", 30.0, 7.0, 6.0)]
    fiducials = [{"id": i, "x_mm": dot_to_mm(mm_to_dot(x)), "y_mm": dot_to_mm(mm_to_dot(y)),
                  "w_mm": 3.0, "h_mm": h, "rgb": [0, 0, 0]} for i, x, y, h in fids]
    patches, arrays = [], {}
    for k, (arm, alpha, m_rgb, cd, mix, frac, method, neutral, rep) in enumerate(SYNTH_PATCHES):
        cells = PATTERN_DOTS // cd
        seed = seed0 + k
        draw = np.random.default_rng(seed).choice(len(alpha), size=cells * cells, p=probs(alpha, frac))
        states = draw.astype(np.uint8).reshape(cells, cells)
        planes = compose(states, alpha, cd, mix, neutral)
        code = (planes * np.array([1, 2, 4, 8], np.uint8)[:, None, None]).sum(0).astype(np.uint8)
        pal = {s: list(m_rgb if s == "M" else SINGLE_RGB.get(s, ENGINE_RGB.get(s, (0, 0, 0))))
               for s in alpha if mix != "dotmix" or len(s) == 1}
        arrays[f"states_{k}"], arrays[f"planes_{k}"] = states, planes
        patches.append({"id": k, "x_mm": dot_to_mm(mm_to_dot(14.0 + (k % 6) * 12.5)),
                        "y_mm": dot_to_mm(mm_to_dot(22.0 + (k // 6) * 22.0)), "arm": arm, "alphabet": alpha,
                        "palette": pal, "cell_dots": cd, "cells": cells, "fraction": frac, "method": method,
                        "neutral": neutral, "band": k // 6, "seed": seed, "replicate": rep,
                        "states_sha256": hashlib.sha256(states.tobytes()).hexdigest(),
                        "dots_sha256": hashlib.sha256(code.tobytes()).hexdigest()})
    man = {"tag": "S11-synth", "dpi": DPI, "page_mm": [W, H], "bytes": 0, "sha256": "",
           "fiducials": fiducials, "patch_px": {"pattern_dots": PATTERN_DOTS, "solid_dots": SOLID_DOTS},
           "bands": [], "patches": patches,
           "arms": {}, "novelty": [], "notes": ["synthetic, e041_mixture_synth"]}
    return man, arrays


def page_raster(man: dict[str, Any], npz: Any, toner: dict[str, tuple[int, int, int]]) -> np.ndarray:
    W, H = man["page_mm"]
    refl = np.ones((mm_to_dot(H), mm_to_dot(W), 3), np.float32)
    for f in man["fiducials"]:
        y, x = mm_to_dot(f["y_mm"]), mm_to_dot(f["x_mm"])
        refl[y:y + mm_to_dot(f["h_mm"]), x:x + mm_to_dot(f["w_mm"])] = np.array(f["rgb"], np.float32) / 255
    tr = np.array([toner[p] for p in PLANES], np.float32) / 255.0                  # (4, 3)
    for p in man["patches"]:
        y, x = mm_to_dot(p["y_mm"]), mm_to_dot(p["x_mm"])
        planes = np.asarray(npz[f"planes_{p['id']}"], np.float32)
        bar_name = next((s for s in p["alphabet"] if s != "W"), "W")
        bar = state_planes(bar_name, 1, "", p.get("neutral", "process"))[:, 0, 0].astype(np.float32)
        sq = np.ones((PATTERN_DOTS, PATTERN_DOTS, 3), np.float32)
        for k in range(4):
            sq *= 1.0 - planes[k][..., None] * (1.0 - tr[k])
        refl[y:y + PATTERN_DOTS, x:x + PATTERN_DOTS] = sq
        refl[y + PATTERN_DOTS:y + PATTERN_DOTS + SOLID_DOTS, x:x + PATTERN_DOTS] = np.prod(
            1.0 - bar[:, None] * (1.0 - tr), axis=0)
    return np.clip(np.round(refl * 255.0), 0, 255).astype(np.uint8)


def page_planes(man: dict[str, Any], npz: Any) -> tuple[np.ndarray, np.ndarray]:
    """(base RGB uint8 with the fiducials only, (4, H, W) uint8 data-plane ink incl. the bars' planes)."""
    W, H = man["page_mm"]
    base = np.full((mm_to_dot(H), mm_to_dot(W), 3), 255, np.uint8)
    for f in man["fiducials"]:
        y, x = mm_to_dot(f["y_mm"]), mm_to_dot(f["x_mm"])
        base[y:y + mm_to_dot(f["h_mm"]), x:x + mm_to_dot(f["w_mm"])] = f["rgb"]
    planes = np.zeros((4,) + base.shape[:2], np.uint8)
    for p in man["patches"]:
        y, x = mm_to_dot(p["y_mm"]), mm_to_dot(p["x_mm"])
        planes[:, y:y + PATTERN_DOTS, x:x + PATTERN_DOTS] = np.asarray(npz[f"planes_{p['id']}"], np.uint8)
        bar_name = next((s for s in p["alphabet"] if s != "W"), "W")
        bar = state_planes(bar_name, 1, "", p.get("neutral", "process"))[:, 0, 0]
        planes[:, y + PATTERN_DOTS:y + PATTERN_DOTS + SOLID_DOTS, x:x + PATTERN_DOTS] = bar[:, None, None]
    return base, planes


def paint_offset_planes(base: np.ndarray, planes: np.ndarray, toner: dict[str, tuple[int, int, int]],
                        offsets_px: dict[str, tuple[float, float]], *, rot180: bool,
                        shift_mm: tuple[float, float], scale: float, rot_deg: float, pad_mm: float,
                        blur_px: float, noise_sd: float, white: float, seed: int) -> np.ndarray:
    """base (H, W, 3) uint8 = everything that is not data-plane ink; planes (4, H, W) 0/1.  Each plane is
    painted through the pose plus its own (dy, dx) scan-px offset (page-aligned; the sign flips with
    --rot180; with --rot-deg the offset is applied in scan axes), the layers multiply as reflectances, then
    Gaussian blur and seeded noise as e041_probe_synth.paint."""
    pose: dict[str, Any] = {"rot180": rot180, "scale": scale, "rot_deg": rot_deg, "pad_mm": pad_mm,
                            "blur_px": 0.0, "noise_sd": 0.0, "white": 255.0, "seed": seed}
    out = paint(base, shift_mm=shift_mm, **pose).astype(np.float32) / 255.0
    sgn = -1.0 if rot180 else 1.0
    for k, pl in enumerate(PLANES):
        if not planes[k].any():
            continue
        dy, dx = offsets_px.get(pl, (0.0, 0.0))
        sh = (shift_mm[0] + sgn * dx * 25.4 / SCAN_DPI, shift_mm[1] + sgn * dy * 25.4 / SCAN_DPI)
        blank = np.repeat(((1 - planes[k]) * 255).astype(np.uint8)[..., None], 3, axis=2)
        cov = 1.0 - paint(blank, shift_mm=sh, **pose)[..., 0].astype(np.float32) / 255.0
        tr = np.array(toner[pl], np.float32) / 255.0
        out *= 1.0 - cov[..., None] * (1.0 - tr)
        del blank, cov
    out *= white
    if blur_px > 0:
        for c in range(3):
            out[..., c] = ndimage.gaussian_filter(out[..., c], blur_px, mode="nearest")
    if noise_sd > 0:
        out += np.random.default_rng(seed).normal(0.0, noise_sd, out.shape).astype(np.float32)
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def plane_offsets(spec: list[list[str]] | None) -> dict[str, tuple[float, float]]:
    out = {}
    for pl, dy, dx in spec or []:
        if pl not in PLANES:
            raise SystemExit(f"--plane-offset: plane {pl!r} not in {PLANES}")
        out[pl] = (float(dy), float(dx))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--rot180", action="store_true")
    ap.add_argument("--shift-mm", type=float, nargs=2, default=(0.0, 0.0))
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--rot-deg", type=float, default=0.0)
    ap.add_argument("--pad-mm", type=float, default=8.0)
    ap.add_argument("--blur-px", type=float, default=0.0)
    ap.add_argument("--noise-sd", type=float, default=0.0)
    ap.add_argument("--white", type=float, default=255.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--toner-rgb", type=int, nargs=12, default=None, metavar="V",
                    help="C, M, Y, K toner colours as 12 integers (default a printed-looking set)")
    ap.add_argument("--manifest", default=None, help="paint this S11 manifest (+ its patterns npz) instead")
    ap.add_argument("--plane-offset", nargs=3, action="append", metavar=("PLANE", "DY_PX", "DX_PX"),
                    help="displace one plane's ink by (dy, dx) scan px, page-aligned (repeatable)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    toner = dict(TONER_RGB)
    if args.toner_rgb:
        toner = {p: tuple(args.toner_rgb[3 * k:3 * k + 3]) for k, p in enumerate(PLANES)}
    if args.manifest:
        man = json.loads(Path(args.manifest).read_text())
        npz: Any = np.load(Path(args.manifest).parent / f"{man['tag']}-patterns.npz")
    else:
        man, npz = build()
        (out / "S11-synth.manifest.json").write_text(json.dumps(man, indent=1))
        np.savez_compressed(out / "S11-synth-patterns.npz", **npz)
    pose: dict[str, Any] = {"rot180": args.rot180, "shift_mm": tuple(args.shift_mm), "scale": args.scale,
                            "rot_deg": args.rot_deg, "pad_mm": args.pad_mm, "blur_px": args.blur_px,
                            "noise_sd": args.noise_sd, "white": args.white, "seed": args.seed}
    if args.plane_offset:
        img = paint_offset_planes(*page_planes(man, npz), toner, plane_offsets(args.plane_offset), **pose)
    else:
        img = paint(page_raster(man, npz, toner), **pose)
    Image.fromarray(img).save(out / f"{args.name}.tiff")
    print(f"wrote {out / (args.name + '.tiff')} {img.shape[1]} x {img.shape[0]} px")


if __name__ == "__main__":
    main()
