# THE MEASUREMENT: for the captured level-3 (native) colour window,
#  (a) reference_states labels vs GT at the labeled page cells,
#  (b) per-state RGB feature means grouped by GT state at the LABELED cell
#      vs at the rot-2-SHIFTED cell (y-1, x-1) — the composition bug's
#      predicted true sampling location.
import pickle

import numpy as np

from holo3.format import tile_codec
from holo3.format.identity import resolve_format_ref, build_site_geometry
from holo3.plugins import color_model
from holo3.plugins import color_region_anchor as anchor

d = pickle.load(open(
    "<tmp>/color_inputs.pkl",
    "rb"))
row = resolve_format_ref("L:c3-cmy7-p120-v0@2240x1536", 1)
geometry = build_site_geometry(row)

gt = np.load("scratch/e030/"
             "holo-c3-cmy7-q05-counting/page000_gt.npy")
dots = np.unpackbits(gt, axis=2)
cell_bits = dots[:, 1::3, 1::3]
print("gt cell grid:", cell_bits.shape)
gt_states = tile_codec.planes_to_states(
    np.moveaxis(cell_bits, 0, -1).reshape(-1, 3)).reshape(
        cell_bits.shape[1], cell_bits.shape[2])

cap = "20fc40cd483277a4cad81d3299e228b2f89a16058c64666d8953b00ab0b6babf"
key = ("region", cap, 3, 0)
win = d["subjects"][key][0]
cells = win["page_cells_yx"]
points = win["scan_points_yx"]
pitch = win["pitch_px"]
print("window", win["window_id"][3], "cells", cells.shape[0],
      "pitch", pitch)

states, kinds = color_model.reference_states(row, geometry, 0, cells)
furniture = states >= 0
gt_at_label = gt_states[cells[:, 0], cells[:, 1]]
agree = np.mean(states[furniture] == gt_at_label[furniture])
print(f"(a) reference_states furniture labels vs GT: "
      f"{np.count_nonzero(furniture)} furniture cells, "
      f"agreement {agree:.4f}")

planes_meta = d["planes"][(cap, 3)]
planes = tuple(np.load(planes_meta[name][0], mmap_mode="r")
               for name in ("r", "g", "b"))
crop = anchor.native_crop(
    planes, anchor.window_points(win["shape_yx_cells"], win["affine"]),
    anchor.window_halo(pitch))
divisor = 255.0 if float(crop[2].max()) > 1.5 else 1.0
feats = anchor.crop_features(crop, points, pitch, divisor)

shifted = cells - 1
ok = (shifted[:, 0] >= 0) & (shifted[:, 1] >= 0)
gt_at_shift = np.full(cells.shape[0], -1, np.int64)
gt_at_shift[ok] = gt_states[shifted[ok, 0], shifted[ok, 1]]

for name, grouping in (("labeled cell", gt_at_label),
                       ("shifted cell (y-1,x-1)", gt_at_shift)):
    print(f"(b) per-state RGB means grouped by GT at the {name}:")
    spread = []
    for state in range(7):
        sel = grouping == state
        if not np.any(sel):
            continue
        mean = feats[sel].mean(axis=0)
        std = feats[sel].std(axis=0)
        spread.append(mean)
        print(f"    state {state}  n={np.count_nonzero(sel):6d}  "
              f"mean RGB {mean[0]:.3f} {mean[1]:.3f} {mean[2]:.3f}  "
              f"std {std[0]:.3f} {std[1]:.3f} {std[2]:.3f}")
    spread_arr = np.asarray(spread)
    print(f"    between-state mean spread (max-min per channel): "
          f"{(spread_arr.max(axis=0) - spread_arr.min(axis=0))}")
