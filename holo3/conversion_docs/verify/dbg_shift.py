# Half-cell-shift discriminator: re-run the crop engine, then for accepted
# windows resample payload cells with (dy,dx) in {-0.5,0,+0.5}^2 CELL shifts
# through the SAME placement affine, and report midpoint-split BER vs GT.
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from holo3 import data, engine  # noqa: E402
from holo3.engine_types import DecodeRequest  # noqa: E402
from holo3.format import identity  # noqa: E402
from holo3.plugins import calibrate  # noqa: E402
from holo3.engine_types import sampling_planes  # noqa: E402

SCAN = Path("scratch/e028/hp-canon-c2-ink-counting.tiff")
GT = Path("scratch/e028/holo-c2-r0700-q07-ink-counting/page000_gt.npy")
FORMAT_REF = "L:c2-r0700@3392x2368"
CROP_Y0, CROP_Y1 = 12000, 17400
CROP_X0, CROP_X1 = 12000, 17400
CROP_CACHE = Path("<tmp>")
RUN_DIR = Path("<tmp>")


def load_gt(row) -> np.ndarray:
    packed = np.load(GT)
    dots = np.unpackbits(packed, axis=1)
    return dots[::2, ::2]


def main() -> None:
    row = identity.resolve_format_ref(FORMAT_REF, 1)
    gt = load_gt(row)

    if not CROP_CACHE.exists():
        with tifffile.TiffFile(SCAN) as tiff:
            page = tiff.pages[0].asarray(out="memmap")
            crop = np.asarray(page[CROP_Y0:CROP_Y1, CROP_X0:CROP_X1])
        CROP_CACHE.parent.mkdir(parents=True, exist_ok=True)
        tifffile.imwrite(CROP_CACHE, crop)

    events: list[data.Event] = []
    request = DecodeRequest(
        scans=(CROP_CACHE,), dpi=4800.0, format_ref=FORMAT_REF, n_pages=1,
        workers=8, complete=False, no_close=True, diag_port=None,
        run_dir=RUN_DIR)
    eng = engine._Engine(request, events)
    eng.run()

    lookup = eng._lookup
    deltas = [(-0.5, -0.5), (-0.5, 0.0), (-0.5, 0.5),
              (0.0, -0.5), (0.0, 0.0), (0.0, 0.5),
              (0.5, -0.5), (0.5, 0.0), (0.5, 0.5)]

    for wid in sorted(eng._evidence):
        ev = eng._evidence[wid]
        if not ev.accepted or not ev.page_cells_yx.size:
            continue
        placement = eng._placements[wid]
        level = eng._levels[(wid[0], wid[1])]
        pitch_native = eng._region_pitch[wid[:3]]
        pitch_level = pitch_native / float(level.scale)
        planes = tuple(r.open() for r in sampling_planes(
            eng, (wid[0], wid[1])).__iter__()) \
            if False else tuple(r.open() for r in sampling_planes(
                eng, (wid[0], wid[1])))
        cells = np.asarray(ev.page_cells_yx, np.int64)
        payload = calibrate.payload_cell_mask(lookup, cells)
        known = np.asarray(ev.reference_values) >= 0
        truth = gt[cells[:, 0], cells[:, 1]]
        raster_shape = (int(planes[0].shape[0]), int(planes[0].shape[1]))
        line = [f"win L{wid[1]} extent={wid[3]} route={placement.route} "
                f"hll={ev.heldout_logloss}"]
        results = []
        for dy, dx in deltas:
            shifted = cells.astype(np.float64) + np.asarray([dy, dx])
            points = calibrate.scan_points_yx(
                placement.native_affine, level.scale, shifted)
            if not calibrate.points_inside_raster(points, raster_shape):
                results.append((dy, dx, None, None))
                continue
            crop_w = calibrate.window_crop(
                planes, points, raster_shape, pitch_level)
            scores = calibrate.window_scores(
                calibrate.sample_points(crop_w, points))
            pred = (scores > 0).astype(np.uint8)
            ber_pay = float((pred[payload] != truth[payload]).mean())
            ber_known = float((pred[known] != truth[known]).mean())
            results.append((dy, dx, ber_pay, ber_known))
        print(line[0])
        for dy, dx, bp, bk in results:
            tag = " <-- engine" if (dy, dx) == (0.0, 0.0) else ""
            if bp is None:
                print(f"  d=({dy:+.1f},{dx:+.1f})  outside{tag}")
            else:
                print(f"  d=({dy:+.1f},{dx:+.1f})  payloadBER={bp:.4f} "
                      f"knownBER={bk:.4f}{tag}")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
