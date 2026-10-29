"""The one colour render the two printed-page gates close at.

test_backbone_payload_gates and test_pooled_dead_plane_gate rendered the
same page the same way and differed in one line — the dead-plane gate
erased a plane first — so the copy was folded into one helper with a
dead-plane dial (2026-09-20).  The gates stay two: one is the backbone's
representative colour row end to end, the other is the pooling change's
own reason.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from holo.qualification.color_synthetic import render_color_scan


def colour_raster(spec, gt_path: Path, *,
                  dead_plane: int | None = None) -> np.ndarray:
    """2 px/dot (1200 dpi): the footing the production color gate closes at.

    MEASURED 2026-07-30: finer footings added ZERO color certificates —
    the limiter is placement coverage, not sampling.  A paper border
    keeps the field out of the edge-desert zone.

    ``dead_plane`` erases that plane's coverage EVERYWHERE before the
    forward model sees it: the compose-level blanking the dead-plane
    gate needs.
    """
    packed = np.load(gt_path, allow_pickle=False)
    assert packed.shape[0] == 3
    if dead_plane is not None:
        packed = packed.copy()
        packed[dead_plane] = 0
    field_h = spec.cells_yx[0] * spec.cell_dots
    field_w = spec.cells_yx[1] * spec.cell_dots
    coverage = np.stack([
        np.unpackbits(packed[plane], axis=1, count=field_w,
                      bitorder="big").astype(np.float64)
        for plane in range(3)
    ], axis=-1)
    border = 60
    padded = np.zeros((field_h + 2 * border, field_w + 2 * border, 3),
                      np.float64)
    padded[border:-border, border:-border] = coverage
    source = np.repeat(np.repeat(padded, 2, axis=0), 2, axis=1)
    rgb = np.clip(np.asarray(render_color_scan(source).rgb), 0.0, 1.0)
    return np.round(rgb * 255.0).astype(np.uint8)
