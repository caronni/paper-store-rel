# Throwaway debugging instrument for the first real-capture decode failure.
# Runs the real engine in-process on a crop of the e028 scan, then compares
# calibrated window evidence and frozen tile evidence against the emitted
# page GT (printed domain, positive LLR = printed 1).
from __future__ import annotations

import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from holo3 import data, engine  # noqa: E402
from holo3.engine_types import DecodeRequest  # noqa: E402
from holo3.format import identity  # noqa: E402
from holo3.plugins import calibrate  # noqa: E402

SCAN = Path("scratch/e028/hp-canon-c2-ink-counting.tiff")
GT = Path("scratch/e028/holo-c2-r0700-q07-ink-counting/page000_gt.npy")
FORMAT_REF = "L:c2-r0700@3392x2368"
CROP_Y0, CROP_Y1 = 12000, 17400
CROP_X0, CROP_X1 = 12000, 17400
TILE = 64


def load_gt(row) -> np.ndarray:
    packed = np.load(GT)
    dots = np.unpackbits(packed, axis=1)
    cells = dots[::2, ::2]
    assert cells.shape == row.cells_yx, (cells.shape, row.cells_yx)
    return cells


def main() -> None:
    row = identity.resolve_format_ref(FORMAT_REF, 1)
    gt = load_gt(row)

    scratch = Path(tempfile.mkdtemp(prefix="dbg-crop-"))
    crop_path = scratch / "crop.tiff"
    with tifffile.TiffFile(SCAN) as tiff:
        page = tiff.pages[0].asarray(out="memmap")
        crop = np.asarray(page[CROP_Y0:CROP_Y1, CROP_X0:CROP_X1])
    tifffile.imwrite(crop_path, crop)
    print(f"crop {crop.shape} written to {crop_path}", flush=True)

    events: list[data.Event] = []
    request = DecodeRequest(
        scans=(crop_path,), dpi=4800.0, format_ref=FORMAT_REF, n_pages=1,
        workers=8, complete=False, no_close=True, diag_port=None,
        run_dir=scratch / "run")
    eng = engine._Engine(request, events)
    result = eng.run()
    print(f"engine done: status={result.status} certified={result.certified}",
          flush=True)

    lookup = eng._lookup

    # --- window-level printed-domain BER (calibrate output) ---
    print("\n== window evidence (accepted) vs GT, payload cells only ==")
    by_level: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for wid in sorted(eng._evidence):
        ev = eng._evidence[wid]
        if not ev.accepted or not ev.page_cells_yx.size:
            continue
        cells = np.asarray(ev.page_cells_yx, np.int64)
        payload = calibrate.payload_cell_mask(lookup, cells)
        sel = payload & (np.asarray(ev.printed_llr) != 0.0)
        if not sel.any():
            continue
        pred = (np.asarray(ev.printed_llr)[sel] > 0).astype(np.uint8)
        truth = gt[cells[sel, 0], cells[sel, 1]]
        ber = float((pred != truth).mean())
        by_level[wid[1]].append((ber, int(sel.sum())))
    for level in sorted(by_level):
        rows = by_level[level]
        bers = np.array([b for b, _ in rows])
        print(f"level {level}: {len(rows)} windows  BER "
              f"min={bers.min():.4f} med={np.median(bers):.4f} "
              f"max={bers.max():.4f}  "
              f"n>0.25: {(bers > 0.25).sum()}")

    # also reference-cell (word/filler) mismatch per window as sanity
    print("\n== window reference-cell mismatch (known sites) ==")
    for level in sorted(by_level):
        mism = []
        for wid in sorted(eng._evidence):
            ev = eng._evidence[wid]
            if wid[1] != level or not ev.accepted:
                continue
            cells = np.asarray(ev.page_cells_yx, np.int64)
            known = np.asarray(ev.reference_values) >= 0
            if not known.any():
                continue
            truth = gt[cells[known, 0], cells[known, 1]]
            mism.append(float((truth != ev.reference_values[known]).mean()))
        if mism:
            arr = np.array(mism)
            print(f"level {level}: ref-vs-GT mismatch med={np.median(arr):.4f} "
                  f"max={arr.max():.4f} over {len(arr)} windows")

    # --- tile-level frozen evidence vs GT ---
    print("\n== frozen TileEvidence vs GT (printed domain) ==")
    stats: dict[int, list[float]] = defaultdict(list)
    per_tile: list[tuple[int, int, int, float, int]] = []
    for key in sorted(eng._tile_evidence):
        page, ty, tx, cap, level, arm = key
        ev = eng._tile_evidence[key]
        flat = np.asarray(ev.observed_flat, np.int64)
        values = np.asarray(ev.values, np.float64)[:, 0]
        nz = values != 0.0
        if not nz.any():
            continue
        local_y = flat // TILE
        local_x = flat % TILE
        cell_y = ty * TILE + local_y
        cell_x = tx * TILE + local_x
        pred = (values > 0).astype(np.uint8)
        truth = gt[cell_y, cell_x]
        ber = float((pred[nz] != truth[nz]).mean())
        stats[level].append(ber)
        per_tile.append((level, ty, tx, ber, int(nz.sum())))
    for level in sorted(stats):
        arr = np.array(stats[level])
        print(f"level {level}: {arr.size} tiles  BER min={arr.min():.4f} "
              f"med={np.median(arr):.4f} max={arr.max():.4f}  "
              f"n<0.10: {(arr < 0.10).sum()}  n~0.5(0.4-0.6): "
              f"{((arr > 0.4) & (arr < 0.6)).sum()}")
    print("\nworst/best tiles per level:")
    for level in sorted(stats):
        rows = [r for r in per_tile if r[0] == level]
        rows.sort(key=lambda r: r[3])
        for r in rows[:3] + rows[-3:]:
            print(f"  L{r[0]} tile({r[1]},{r[2]}) ber={r[3]:.4f} n={r[4]}")
    print(f"\nscratch dir: {scratch}")


if __name__ == "__main__":
    main()
