#!/usr/bin/env python
"""P4-perplane-registration probe (zero print).

Measures, on real e004 color scans, whether sparse keystream-known
'training dust' can measure per-plane (C/M/Y) registration offsets.

Method:
  * register the scan with the e004 manifest (cal_core, exp 002 machinery);
  * per A3 tile (7-state c3 composite): lock the patch ONCE on a composite
    (C|M|Y union) GT template in grey — this is the 'common grid' a pilot
    lock would give the receiver;
  * per plane P in C/M/Y, in its absorbing RGB channel (C->r, M->g, Y->b):
      - whole-tile xcorr of the plane GT vs the locked raster = high-SNR
        tile-level per-plane offset (the 'truth' field, 16 samples/page);
      - per-CELL absorption centroids on KNOWN pure-P cells whose 4-neighbors
        carry no P ink (dust idiom: sparse known cells, sub-cell anchor);
  * dump everything to an npz for the fit/dust-simulation stage
    (probe17_dust_fit.py).

Usage:
  env/bin/python experiments/017-color-channel/probes/probe17_perplane_reg.py \\
      --e004-build <gen_e004's build> <evidence>/scans/finalists.png [more...]
Writes experiments/017-color-channel/build/probe17_reg_<scanstem>.npz
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
for rel in ("experiments/002-calibration-page",
            "experiments/003-modulation-probes",
            "experiments/001-engine-characterization",
            "src"):
    p = str(_REPO / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

import cal_core as cc  # noqa: E402
import scanlab  # noqa: E402
from scipy.ndimage import uniform_filter  # noqa: E402

BUILD = Path()     # gen_e004's build dir, set from --e004-build
MANIFEST = Path()  # BUILD / "e004_manifest.json"

STATES7 = ("W", "C", "M", "Y", "CM", "CY", "MY")
PURE = {"C": 1, "M": 2, "Y": 3}
INKY = {"C": {1, 4, 5}, "M": {2, 4, 6}, "Y": {3, 5, 6}}
CH = {"C": "r", "M": "g", "Y": "b"}
SUB = 2
WIN = 5          # centroid window half-width in SUB-samples (+-2.5 dots)
SRCH = 3         # matched-filter peak search half-width in samples (+-1.5
                 # dots around the per-tile prior; +-2.5 lets the DIAGONAL
                 # same-ink neighbour's box-sum shoulder win the corner —
                 # measured: 334-521/600 corner-edge rejections per tile)
CELL = 3
# bias calibration, end-to-end on synthetic shifted blobs through
# cell_anchors itself: the even-size box filter's half-sample offset and the
# integer cell-centre convention (cy = 6i+3 vs geometric 6i+2.5) CANCEL —
# raw estimator reads true 0.0 as 0.000, true +-0.4/0.9 with ~4%
# multiplicative overshoot (0.438/-0.938). No additive correction needed.
BOX_BIAS = 0.0


def _parabolic(v: np.ndarray, i: int) -> float:
    if 0 < i < len(v) - 1:
        den = 2 * (v[i - 1] - 2 * v[i] + v[i + 1])
        if abs(den) > 1e-12:
            return i + (v[i - 1] - v[i + 1]) / den
    return float(i)


def cell_anchors(crop: np.ndarray, states: np.ndarray, plane: str,
                 e: dict, prior_dots: tuple[float, float] = (0.0, 0.0)) -> dict:
    """Per-cell matched-filter anchors for isolated pure-`plane` cells.

    The dust idiom (acquire measure_pilot_anchors architecture): the known
    content of a pure c3 cell is a solid CELLxCELL ink blob; its matched
    filter against the absorption raster is a box sum. We take the box-sum
    peak within +-WIN samples of the nominal cell centre, parabolic subpixel.
    A plain fixed-window centroid (dyc/dxc, kept for comparison) shrinks
    displaced blobs toward 0 — measured 1.6-dot disagreement vs whole-tile
    xcorr on the Y plane; the matched filter has no such truncation bias.

    crop: locked raster of the plane's channel, shape (h*SUB, w*SUB), ink dark.
    """
    inky = np.isin(states, sorted(INKY[plane]))
    pure = states == PURE[plane]
    # 4-neighbour P-ink-free (interior cells only)
    ok = pure.copy()
    ok[0, :] = ok[-1, :] = ok[:, 0] = ok[:, -1] = False
    ok[1:-1, 1:-1] &= (~inky[:-2, 1:-1] & ~inky[2:, 1:-1]
                       & ~inky[1:-1, :-2] & ~inky[1:-1, 2:])
    iy, ix = np.nonzero(ok)

    bg = float(np.percentile(crop, 85))
    absr = np.clip(bg - crop, 0.0, None)
    S = uniform_filter(absr, size=CELL * SUB, mode="constant")
    off = np.arange(-WIN, WIN + 1, dtype=np.float64)
    # coarse per-tile prior recentres the per-cell search window (receiver
    # would get this from the joint dust ensemble; keeps the +-WIN refine
    # range from censoring large plane offsets). Integer-sample shift.
    py = int(round(np.clip(prior_dots[0], -3, 3) * SUB))
    px = int(round(np.clip(prior_dots[1], -3, 3) * SUB))

    dys, dxs, dycs, dxcs, mass, keep_y, keep_x = [], [], [], [], [], [], []
    for i, j in zip(iy, ix):
        cy = i * CELL * SUB + (CELL * SUB) // 2 + py
        cx = j * CELL * SUB + (CELL * SUB) // 2 + px
        if (cy - WIN < 0 or cx - WIN < 0 or cy + WIN >= crop.shape[0]
                or cx + WIN >= crop.shape[1]):
            continue
        win = S[cy - SRCH: cy + SRCH + 1, cx - SRCH: cx + SRCH + 1]
        ky, kx = np.unravel_index(int(np.argmax(win)), win.shape)
        if ky in (0, 2 * SRCH) or kx in (0, 2 * SRCH):
            continue                       # peak at the search edge: reject
        m = float(win[ky, kx])
        if m <= 0.05 * bg:
            continue                       # dropout guard
        dys.append((_parabolic(win[:, kx], ky) - SRCH + py) / SUB + BOX_BIAS)
        dxs.append((_parabolic(win[ky, :], kx) - SRCH + px) / SUB + BOX_BIAS)
        # comparison centroid (fixed window, known-biased; same prior shift)
        w = absr[cy - WIN: cy + WIN + 1, cx - WIN: cx + WIN + 1]
        ms = float(w.sum())
        dycs.append(((w.sum(axis=1) * off).sum() / ms + py) / SUB if ms > 0 else 0.0)
        dxcs.append(((w.sum(axis=0) * off).sum() / ms + px) / SUB if ms > 0 else 0.0)
        mass.append(m)
        keep_y.append(i)
        keep_x.append(j)
    keep_y = np.asarray(keep_y)
    keep_x = np.asarray(keep_x)
    return {
        "dy": np.asarray(dys), "dx": np.asarray(dxs),
        "dyc": np.asarray(dycs), "dxc": np.asarray(dxcs),
        "mass": np.asarray(mass),
        "y_page": e["y_dots"] + keep_y * CELL + CELL / 2.0,
        "x_page": e["x_dots"] + keep_x * CELL + CELL / 2.0,
    }


def tile_xcorr(crop: np.ndarray, gt: np.ndarray) -> tuple[float, float, float]:
    tpl = np.kron(1.0 - gt.astype(np.float32), np.ones((SUB, SUB), np.float32)) * 255.0
    dy, dx, q = scanlab.xcorr_offset(crop, tpl, max_shift=8 * SUB)
    return dy / SUB, dx / SUB, q


def main(scan_paths: list[str]) -> None:
    manifest = cc.load_manifest(MANIFEST)
    a3 = [t["name"] for t in manifest["tiles"] if t["class"] == "A3"]
    print(f"A3 tiles: {len(a3)}")
    for spath in scan_paths:
        spath = Path(spath)
        scan = cc.load_scan(spath)
        reg = cc.register(scan, manifest)
        st = cc.affine_stats(scan["affine"])
        print(f"{spath.name}: registered kind={scan['kind']} {st}")
        out: dict[str, np.ndarray] = {}
        for name in a3:
            eC = cc.entry(manifest, f"{name}_C")
            states = cc.load_gt_named(eC["params"]["states_gt"], BUILD).astype(int)
            gts = {p: cc.load_gt(cc.entry(manifest, f"{name}_{p}")) for p in "CMY"}
            comp = (gts["C"] | gts["M"] | gts["Y"]).astype(np.float32)
            view = cc.patch_view(scan, eC, template_dots=comp, channel="grey",
                                 margin_dots=8, sub=SUB)
            tname = name.replace("/", "_")
            out[f"{tname}/lock"] = np.array(
                [*view.local_offset_dots, view.local_quality or -1.0,
                 float(view.local_locked)])
            if not view.local_locked:
                print(f"  {name}: composite lock FAILED q={view.local_quality}")
                continue
            for p in "CMY":
                crop = view.crop(CH[p])
                dyt, dxt, q = tile_xcorr(crop, gts[p])
                out[f"{tname}/{p}/tile"] = np.array([dyt, dxt, q])
                cres = cell_anchors(crop, states, p, eC, prior_dots=(dyt, dxt))
                for k, v in cres.items():
                    out[f"{tname}/{p}/{k}"] = v
            n = {p: len(out[f'{tname}/{p}/dy']) for p in 'CMY'}
            print(f"  {name}: lock={view.local_offset_dots} "
                  f"q={view.local_quality:.2f} n_cells={n} "
                  f"tileY(dy,dx)={out[f'{tname}/Y/tile'][:2].round(3)}")
        dest = _REPO / "experiments/017-color-channel/build" / f"probe17_reg_{spath.stem}.npz"
        dest.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(dest, **out)
        print(f"  -> {dest}")


if __name__ == "__main__":
    _ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    _ap.add_argument("--e004-build", type=Path, required=True)
    _ap.add_argument("scans", nargs="+")
    _args = _ap.parse_args()
    BUILD = _args.e004_build
    MANIFEST = BUILD / "e004_manifest.json"
    main(_args.scans)
