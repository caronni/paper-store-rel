# Discriminating test: color_region.region_window scan points must match
# calibrate.scan_points_yx (the K convention) for the same page cells through
# the same Placement, for every rot_k.
from fractions import Fraction
from types import SimpleNamespace

import numpy as np

from holo3 import data
from holo3.plugins import color_region
from holo3.format.identity import resolve_format_ref
from holo3.plugins import calibrate

row = resolve_format_ref("L:c3-cmy7-p120-v0@2240x1536", 1)
rng = np.random.default_rng(7)

for rot_k in range(4):
    shape = (48, 48)
    extent = (100, 200, 100 + shape[0], 200 + shape[1])
    local = np.stack(np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    local = local[rng.choice(local.shape[0], 200, replace=False)]
    native_affine = (12.03, 0.021, 5000.0, -0.019, 12.05, 4000.0)
    placement = data.Placement(
        window_id=("cap", 3, 0, extent),
        capture_id="cap", level_index=3, region_index=0,
        patch_ordinal=17, page=0, rot_k=rot_k,
        page_origin_yx=(400, 300), native_affine=native_affine,
        pitch_px=12.04, route="word",
        local_cells_yx=local)
    engine = SimpleNamespace(
        _placements={placement.window_id: placement},
        _levels={("cap", 3): SimpleNamespace(scale=Fraction(1))},
        _row=row)
    rw = color_region.region_window(engine, placement.window_id)
    truth = calibrate.scan_points_yx(native_affine, Fraction(1),
                                     rw.page_cells_yx)
    delta = rw.scan_points_yx - truth
    print(f"rot_k={rot_k}  n={rw.page_cells_yx.shape[0]}  "
          f"max|dy|={np.abs(delta[:, 0]).max():.6f} px  "
          f"max|dx|={np.abs(delta[:, 1]).max():.6f} px  "
          f"mean dy={delta[:, 0].mean():+.4f}  "
          f"mean dx={delta[:, 1].mean():+.4f}")
