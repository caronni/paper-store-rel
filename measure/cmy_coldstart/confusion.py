"""The c2 stimulus's supervised context-free confusion, beside the paper's (CMY-RECEIVER-PLAN A9; CMY-DESIGN §11 G12).

What: the c2 cmy page of the suite (`holo.receiver.tests._h3_sims_cmy`, `c2-cmy-r0775x0700@10x10` at 2400 dpi, e043c
sheet 3's bars, M and Y +1.0 dot in x) read the way e043c and e044 read paper (measure/cmy_probe/bands.py): per cell
the mean over a centre box of half the cell, R at C's pose, G at M's, B at Y's -- here the render's TRUE per-plane
poses -- and one colour table, the nearest class mean in RGB fitted on every cell with its GT label.  The 4 x 4
confusion (rows true, columns decided; W, C, M, Y), the per-state errors and the two label bits' hard errors, for
the dot gain the stimulus ships and its neighbours (`--gains`, whole 2400-dpi pixels, one binary dilation per plane);
printed beside the committed `confusion_loo` of e041 S14 band B3 and S17 band U12 at 2400
(experiments/041-m281-screen-routes/results/measurements.json) and the e043c / e044 W rows the dilation was tuned
toward.
Why: G12 prints the sim's confusion beside the paper's as a RECORD, not a verdict (R19); the W row is what the
stimulus's dot gain was tuned toward.
How: `python -m measure.cmy_coldstart.confusion --out DIR [--gains 0,1,2,3,4]` renders each gain into memory through
the suite's own emission and renderer and writes DIR/confusion.json.

    cd <repo> && PYTHONPATH=src:. \\
        env/bin/python -u -m measure.cmy_coldstart.confusion --out <dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

STATES = ("W", "C", "M", "Y")
TILE_CELLS = 64
#: hi = C or M, lo = C or Y (design §2.2), per state in STATES order.
LABELS = np.array([[0, 0], [1, 1], [1, 0], [0, 1]], np.int64)
PAPER_RECORD = Path(__file__).resolve().parents[2] / "experiments/041-m281-screen-routes/results/measurements.json"
#: e043c sheet 3's c2 bands and e044 sheet A's page, W row (scratch2 readouts, summarised in the plan's §0).
PAPER_W_ROWS = {"e043c B1": 0.139, "e043c B14": 0.146, "e044 A": 0.149}


def cell_classes(coverage: np.ndarray, cell_dots: int) -> np.ndarray:
    """GT dot planes -> one class per cell, W C M Y = 0..3 (cells are solid, one toner at most)."""
    st = coverage[:, ::cell_dots, ::cell_dots]
    cls = np.zeros(st.shape[1:], np.int64)
    for k in range(3):
        cls[st[k] > 0] = k + 1
    if (st.sum(axis=0) > 1).any():
        raise SystemExit("a GT cell carries two toners -- not a cmy page")
    return cls


def features(image: np.ndarray, rows: int, cols: int, cell_px: int, border_px: int,
             offsets_px: tuple[tuple[int, int], ...]) -> np.ndarray:
    """Per cell the centre box of half the cell: channel k at plane k's true pose (render origin + offset)."""
    half = cell_px // 2
    quarter = cell_px // 4
    out = np.empty((rows, cols, 3))
    for channel, (dx, dy) in enumerate(offsets_px):
        y0, x0 = border_px + dy + quarter, border_px + dx + quarter
        block = image[y0:y0 + rows * cell_px, x0:x0 + cols * cell_px, channel].astype(np.float64)
        out[..., channel] = block.reshape(rows, cell_px, cols, cell_px)[:, :half, :, :half].mean(axis=(1, 3))
    return out


def supervised_confusion(x: np.ndarray, cls: np.ndarray) -> np.ndarray:
    """Nearest class mean in RGB, the means fitted on every cell with its GT label."""
    xs, ys = x.reshape(-1, 3), cls.ravel()
    means = np.stack([xs[ys == k].mean(axis=0) for k in range(4)])
    decided = ((xs[:, None, :] - means[None]) ** 2).sum(axis=-1).argmin(axis=1)
    conf = np.zeros((4, 4), np.int64)
    np.add.at(conf, (ys, decided), 1)
    return conf


def stats(conf: np.ndarray) -> dict[str, Any]:
    conf = np.asarray(conf, np.int64)
    n = conf.sum()
    per_state = 1.0 - np.diag(conf) / conf.sum(axis=1)
    bit_err = [float(sum(conf[t, d] for t in range(4) for d in range(4) if LABELS[t, b] != LABELS[d, b]) / n)
               for b in range(2)]
    return {"state_err": round(float(1.0 - np.trace(conf) / n), 5),
            "per_state_err": {s: round(float(e), 5) for s, e in zip(STATES, per_state)},
            "bit_err_hi_lo": [round(e, 5) for e in bit_err], "confusion": conf.tolist()}


def paper_confusions() -> dict[str, dict[str, Any]]:
    record = json.loads(PAPER_RECORD.read_text())["scale"]
    out = {}
    for label, sheet, band in (("S14 B3", "S14-ps-scale", "B3"), ("S17 U12 @2400", "S17-ps-layouts@2400", "U12")):
        row = next(b for b in record[sheet]["bands"] if b["name"] == band)
        out[label] = stats(row["confusion_loo"])
    return out


def row_text(label: str, s: dict[str, Any]) -> str:
    p = s["per_state_err"]
    return (f"| {label} | {100 * s['state_err']:.2f} | {100 * p['W']:.2f} | {100 * p['C']:.2f} | {100 * p['M']:.2f} | "
            f"{100 * p['Y']:.2f} | {100 * s['bit_err_hi_lo'][0]:.2f} / {100 * s['bit_err_hi_lo'][1]:.2f} | "
            f"{s['confusion']} |")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--gains", default="0,1,2,3,4", help="dot gains to render, whole 2400-dpi pixels")
    args = parser.parse_args(argv)
    from holo.receiver.tests import _h3_sims, _h3_sims_cmy as sims

    args.out.mkdir(parents=True, exist_ok=True)
    _spec, coverage = sims._emit_cmy_c2(args.out)
    cell_dots = sims.CMY_C2_TILE_DOTS // TILE_CELLS
    cls = cell_classes(coverage, cell_dots)
    cell_px = cell_dots * sims.CMY_C2_PX_PER_DOT
    border_px = sims.COLOR_BORDER_DOTS * sims.CMY_C2_PX_PER_DOT
    sim = {}
    for gain in (int(g) for g in args.gains.split(",")):
        image = _h3_sims._render_coverage(coverage, sims.COLOR_BORDER_DOTS, sims.cmy_c2_channel(),
                                          upsample=sims.CMY_C2_PX_PER_DOT, gain_px=gain)
        x = features(image, cls.shape[0], cls.shape[1], cell_px, border_px, sims.CMY_C2_OFFSET_PX)
        sim[f"sim gain {gain} px{' (shipped)' if gain == sims.CMY_C2_GAIN_PX else ''}"] = stats(
            supervised_confusion(x, cls))
    paper = paper_confusions()
    (args.out / "confusion.json").write_text(json.dumps(
        {"sim": sim, "paper": paper, "paper_w_rows": PAPER_W_ROWS, "sims_source": sims.SOURCE_DIGEST,
         "base_sims_source": _h3_sims.SOURCE_DIGEST}, indent=1))
    print("| read | state % | W % | C % | M % | Y % | hi / lo bit % | confusion (rows true W C M Y) |")
    print("|---|---|---|---|---|---|---|---|")
    for label, s in {**sim, **paper}.items():
        print(row_text(label, s))
    print("W rows on paper: " + ", ".join(f"{k} {100 * v:.1f} %" for k, v in PAPER_W_ROWS.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
