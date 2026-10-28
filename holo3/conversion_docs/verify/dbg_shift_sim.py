# Same half-cell-shift sweep on the K SIM capture (which decodes VERIFIED).
# Truth = reference labels at known cells (no page GT needed).
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from holo3 import data, engine  # noqa: E402
from holo3.engine_types import DecodeRequest  # noqa: E402
from holo3.plugins import calibrate  # noqa: E402
from holo3.engine_types import sampling_planes  # noqa: E402

SIM = Path(__file__).resolve().parent / "sim" / "sim-k-1200dpi.tiff"
RUN_DIR = Path("<tmp>")


def main() -> None:
    events: list[data.Event] = []
    request = DecodeRequest(
        scans=(SIM,), dpi=1200.0, format_ref="c3-k-r0550@7x7", n_pages=1,
        workers=8, complete=False, no_close=True, diag_port=None,
        run_dir=RUN_DIR)
    eng = engine._Engine(request, events)
    eng.run()
    print(f"certified={len(eng._certificates)}")

    deltas = [(-0.5, -0.5), (-0.5, 0.0), (0.0, -0.5), (0.0, 0.0),
              (0.0, 0.5), (0.5, 0.0), (0.5, 0.5)]
    shown = 0
    for wid in sorted(eng._evidence):
        ev = eng._evidence[wid]
        if not ev.accepted or not ev.page_cells_yx.size:
            continue
        placement = eng._placements[wid]
        level = eng._levels[(wid[0], wid[1])]
        pitch_native = eng._region_pitch[wid[:3]]
        pitch_level = pitch_native / float(level.scale)
        planes = tuple(r.open() for r in sampling_planes(
            eng, (wid[0], wid[1])))
        cells = np.asarray(ev.page_cells_yx, np.int64)
        known = np.asarray(ev.reference_values) >= 0
        labels = np.asarray(ev.reference_values)
        raster_shape = (int(planes[0].shape[0]), int(planes[0].shape[1]))
        print(f"win L{wid[1]} extent={wid[3]} route={placement.route} "
              f"hll={ev.heldout_logloss} pitch_level={pitch_level}")
        for dy, dx in deltas:
            shifted = cells.astype(np.float64) + np.asarray([dy, dx])
            points = calibrate.scan_points_yx(
                placement.native_affine, level.scale, shifted)
            if not calibrate.points_inside_raster(points, raster_shape):
                print(f"  d=({dy:+.1f},{dx:+.1f})  outside")
                continue
            crop_w = calibrate.window_crop(
                planes, points, raster_shape, pitch_level)
            scores = calibrate.window_scores(
                calibrate.sample_points(crop_w, points))
            pred = (scores > 0).astype(np.uint8)
            bk = float((pred[known] != labels[known]).mean())
            tag = " <-- engine" if (dy, dx) == (0.0, 0.0) else ""
            print(f"  d=({dy:+.1f},{dx:+.1f})  knownBER={bk:.4f}{tag}")
        shown += 1
        if shown >= 6:
            break


if __name__ == "__main__":
    main()
