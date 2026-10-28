# Run the real engine on the failed scan with the colour descriptor's prepare
# replaced by a recorder: dumps committed placements (rot_k!), the
# RegionWindows, level scales and plane raster paths for offline measurement,
# then refuses the job so the run costs only intake+survey+place.
import pickle
import sys
from pathlib import Path

import numpy as np

import dataclasses

from holo3 import engine
from holo3.engine_types import DecodeRequest
from holo3.plugins import color_region

OUT = Path(sys.argv[1])
captured: dict = {}


def recording_prepare_color(eng, subject, tier):
    key = tuple(subject)
    if "placements" not in captured:
        captured["placements"] = {
            wid: {
                "rot_k": p.rot_k,
                "page": p.page,
                "page_origin_yx": p.page_origin_yx,
                "native_affine": p.native_affine,
                "pitch_px": p.pitch_px,
                "route": p.route,
                "local_cells_yx": np.asarray(p.local_cells_yx),
            }
            for wid, p in eng._placements.items()
        }
        captured["levels"] = {
            k: {"scale": v.scale, "ppc": v.ppc, "shape_px": v.shape_px}
            for k, v in eng._levels.items()
        }
        captured["planes"] = {
            lane: {name: (str(pr.path), pr.shape_px)
                   for name, pr in planes.items()}
            for lane, planes in eng._planes_by_lane.items()
        }
        captured["format_ref"] = eng._request.format_ref \
            if hasattr(eng, "_request") else None
    if key not in captured.setdefault("subjects", {}):
        capture_id, level_index, page = subject
        wids = tuple(
            wid for wid in sorted(eng._placements)
            if wid[0] == capture_id and wid[1] == level_index
            and eng._placements[wid].page == page)
        windows = []
        for wid in wids:
            rw = color_region.region_window(eng, wid)
            windows.append({
                "patch_ordinal": rw.patch_ordinal,
                "window_id": rw.window_id,
                "page": rw.page,
                "local_cells_yx": np.asarray(rw.local_cells_yx),
                "page_cells_yx": np.asarray(rw.page_cells_yx),
                "scan_points_yx": np.asarray(rw.scan_points_yx),
                "shape_yx_cells": rw.shape_yx_cells,
                "affine": rw.affine,
                "pitch_px": rw.pitch_px,
            })
        captured["subjects"][key] = windows
    return None


engine.DESCRIPTORS = tuple(
    dataclasses.replace(d, prepare=recording_prepare_color)
    if d.name == "color" else d
    for d in engine.DESCRIPTORS)
engine.DESCRIPTOR_BY_NAME = {d.name: d for d in engine.DESCRIPTORS}

request = DecodeRequest(
    scans=(Path("scratch/in/"
                "xerox-canon-c3-cmy7-2400dpi.tiff"),),
    dpi=2400.0,
    format_ref="L:c3-cmy7-p120-v0@2240x1536",
    n_pages=1,
    workers=8,
    complete=False,
    no_close=True,
    diag_port=None,
    run_dir=OUT.parent / "capture_run_dir",
)
request.run_dir.mkdir(parents=True, exist_ok=True)
result = engine.decode(request)
print("status:", result.status if hasattr(result, "status") else result)

rots = {}
for wid, p in captured.get("placements", {}).items():
    rots[p["rot_k"]] = rots.get(p["rot_k"], 0) + 1
print("placements:", len(captured.get("placements", {})),
      "rot_k histogram:", rots)
print("colour subjects captured:", sorted(captured.get("subjects", {})))
with open(OUT, "wb") as fh:
    pickle.dump(captured, fh)
print("dumped ->", OUT)
