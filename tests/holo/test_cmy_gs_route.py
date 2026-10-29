"""G7 (docs/CMY-DESIGN.md §11; docs/CMY-GENERATOR-PLAN.md W2a): the ``rgb``
route's page, rendered by ghostscript (``ppmraw -r600``) under the default
ICC path and under ``-dUseFastColor``, reads back to the plane GT — every
field dot classifies to its GT toner by the nearest of white and the
engine's three values, and no ink lands outside the field.  The engine is
the registry's hp-m281, read at run time: this is a render gate, not a
golden.  Measured 2026-10-11 (gs 10.08.0): both colour paths render the
three values exactly; the jobs are 1,689,241 B (c3) and 769,384 B (c2),
the printed-size ones in test_cmy_emission's ledger (~14-15 MB).

Gated: HOLO_RUN_GS_TESTS=1 with ghostscript on PATH.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from holo.devices.registry import PRINTERS
from holo.format.lattice import parse_format_id
from holo.gen.emit import emit_volume

pytestmark = pytest.mark.skipif(
    shutil.which("gs") is None or os.environ.get("HOLO_RUN_GS_TESTS") != "1",
    reason="set HOLO_RUN_GS_TESTS=1 with ghostscript for the rgb route's "
           "render gate (G7)")

ENGINE = PRINTERS["hp-m281"]


@pytest.mark.parametrize("colour_path", [(), ("-dUseFastColor",)],
                         ids=["default-icc", "fast-color"])
@pytest.mark.parametrize("ref", ["c3-cmy-r0850@10x10",
                                 "c2-cmy-r0775x0700@10x10"])
def test_the_rgb_page_renders_to_the_plane_gt(
        ref: str, colour_path: tuple[str, ...], tmp_path: Path) -> None:
    spec = parse_format_id(ref)
    vol = emit_volume(spec, bytes(i % 251 for i in range(20_000)), 0.5,
                      tmp_path / "v", paper="A4-4mm", printer=ENGINE)
    page = vol.pages[0]
    ppm = tmp_path / "page.ppm"
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-dSAFER",
                    "-sDEVICE=ppmraw", "-r600", *colour_path, "-o", str(ppm),
                    str(page.ps_path)], check=True, timeout=600)
    img = np.asarray(Image.open(ppm).convert("RGB")).astype(np.int32)
    manifest = json.loads((tmp_path / "v" / "manifest.json").read_text())
    assert img.shape[:2] == tuple(manifest["page_dots_xy"][::-1])

    packed = np.load(page.gt_path)
    h = packed.shape[1]
    w = spec.cells_yx[1] * spec.cell_dots
    gt = np.unpackbits(packed, axis=2, count=w, bitorder="big")
    oy, ox = manifest["origin_dots_yx"]
    field = img[oy:oy + h, ox:ox + w]
    palette = np.asarray(((255, 255, 255), *ENGINE.rgb_solid), np.int32)
    distance = ((field[..., None, :] - palette) ** 2).sum(axis=-1)
    nearest = np.argmin(distance, axis=-1)
    residual = int(np.sqrt(distance.min(axis=-1)).max())
    for plane in range(3):
        got = nearest == plane + 1
        assert np.array_equal(got, gt[plane] == 1), (
            f"plane {'CMY'[plane]}: {int((got != (gt[plane] == 1)).sum())} "
            f"dots differ (largest palette residual {residual})")
    img[oy:oy + h, ox:ox + w] = 255
    assert np.all(img == 255), "ink outside the field"
