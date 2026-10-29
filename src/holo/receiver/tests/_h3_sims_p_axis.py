"""The FURNITURE DENSITY stimuli: one colour volume and one K volume at p300.

Split out of ``_h3_sims`` at the 1000-line seam, on the ``_h3_sims_field``
precedent (W6).  ``p`` is the cells a tile spends on furniture — 100
indexed word sites plus ``p - 100`` known-content cells — and every other
sim in this tree sits at the printed p120, which is where the two
hardcoded furniture derivations the axis repaired happened to be right
(docs/FORMAT-SPACE.md §18).  These are the two captures that decode rows
where they were wrong.  The base sims, the renderers and the render
constants stay in ``_h3_sims``, which this module reads and which never
reads this one.

``_h3_fixture_build._cache_key`` hashes this module's source with the
other two: a stimulus that moved here without the key following it would
be served from a cache keyed on the half it left behind.

BOTH volumes are sized off their one-page cliff (the colour one at 58% of
its ceiling, K at 50%), because the planner's own p300 arithmetic is part
of what they exercise and a payload sized AT the ceiling would report a
planner error as a second page rather than as a failed assertion.  The
ceilings themselves are pinned on the generator's side of the import
firewall, in tests/holo/test_lattice_gen.py.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import numpy as np

from ._h3_sims import (
    COLOR_BORDER_DOTS,
    DPI,
    K_BLUR_SIGMA_PX,
    K_BORDER_DOTS,
    K_INK_LEVEL,
    K_PAPER_LEVEL,
    UPSAMPLE,
    SimCapture,
    _guard_outdir,
    _page_coverage,
    _render_coverage,
    det_bytes,
    sha256_file,
)

SOURCE_DIGEST = hashlib.sha256(
    Path(__file__).resolve().read_bytes()).hexdigest()

# The colour volume: the same cmy8 codec at p300 — 100 word sites and 200
# dust per tile, against the printed p120's 20 — so the payload is 3,796
# cells instead of 3,976.  12,000 bytes at q = 0.35 against a one-page
# ceiling of 20,702.
P_AXIS_FORMAT_REF = "c2-cmy8-r0550-p300@10x10"
P_AXIS_PAYLOAD_TAG = b"holo3-sim-p-axis"
P_AXIS_PAYLOAD_BYTES = 12000
P_AXIS_SOURCE_FRACTION = 0.35
P_AXIS_EMIT_DIRNAME = "p-axis-emit"
P_AXIS_TIFF_NAME = "sim-p-axis-1200dpi.tiff"
P_AXIS_PAYLOAD_NAME = "sim-p-axis-payload.bin"
P_AXIS_GT_NAME = "p-axis-emit/page000_gt.npy"

# The K volume, added 2026-09-16 with this module.  K reached lawful p
# on its own — its filler count always came from the row, so nothing in
# the repair touched it — but NO K row off p100 had ever been decoded,
# in sim or on paper, and K is the axis's only print candidate (engine-
# agnostic, MIC-free).  Same render path as the K base sim (ink and
# paper levels, border, blur), driven from an `emit_volume` page rather
# than from a hand-composed one: 200 filler cells per tile, 4,000 bytes
# at q = 0.5 against a one-page ceiling of 8,068.
P_AXIS_K_FORMAT_REF = "c3-k-r0550-p300@10x10"
P_AXIS_K_PAYLOAD_TAG = b"holo3-sim-p-axis-k"
P_AXIS_K_PAYLOAD_BYTES = 4000
P_AXIS_K_SOURCE_FRACTION = 0.5
P_AXIS_K_EMIT_DIRNAME = "p-axis-k-emit"
P_AXIS_K_TIFF_NAME = "sim-p-axis-k-1200dpi.tiff"
P_AXIS_K_PAYLOAD_NAME = "sim-p-axis-k-payload.bin"

# frozen 2026-09-16 from the first build of each capture
P_AXIS_TIFF_SHA256 = (
    "d761ad28aad351a497ac14720bf158817680a00602d035463b5551ab5da0fb2e")
P_AXIS_PAYLOAD_SHA256 = (
    "dc0e2136dd4e5f6c79aa891345587b9e73b871d84375ed5acd12eec8b70a7752")
P_AXIS_GT_SHA256 = (
    "1f1b414c804b01f61957ebb8a2bdaa891209f788fcd8a1654b177c73ec4db88c")
EXPECTED_P_AXIS: dict[str, str] = {
    P_AXIS_TIFF_NAME: P_AXIS_TIFF_SHA256,
    P_AXIS_PAYLOAD_NAME: P_AXIS_PAYLOAD_SHA256,
    P_AXIS_GT_NAME: P_AXIS_GT_SHA256,
}
P_AXIS_K_TIFF_SHA256 = (
    "69909d8a06b2569608cf449d5c31e052c2bbe522a8e403cdc198d879ec768d54")
P_AXIS_K_PAYLOAD_SHA256 = (
    "c5f6c87261777b6823de6c85d5c7c2688c3721e1a8d06526815545d259d2d260")
EXPECTED_P_AXIS_K: dict[str, str] = {
    P_AXIS_K_TIFF_NAME: P_AXIS_K_TIFF_SHA256,
    P_AXIS_K_PAYLOAD_NAME: P_AXIS_K_PAYLOAD_SHA256,
}


def make_p_axis(outdir: Path) -> Path:
    import tifffile

    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import emit_volume

    outdir = _guard_outdir(outdir)
    spec = resolve_format_ref(P_AXIS_FORMAT_REF)
    payload = det_bytes(P_AXIS_PAYLOAD_TAG, P_AXIS_PAYLOAD_BYTES)
    emit_dir = outdir / P_AXIS_EMIT_DIRNAME
    if emit_dir.is_dir():
        shutil.rmtree(emit_dir)
    volume = emit_volume(spec, payload, P_AXIS_SOURCE_FRACTION, emit_dir)
    if volume.plan.n_pages != 1:
        raise RuntimeError(f"the p300 colour capture planned "
                           f"{volume.plan.n_pages} pages, not 1")
    tifffile.imwrite(
        outdir / P_AXIS_TIFF_NAME,
        _render_coverage(_page_coverage(emit_dir, spec), COLOR_BORDER_DOTS))
    (outdir / P_AXIS_PAYLOAD_NAME).write_bytes(payload)
    return outdir


def make_p_axis_k(outdir: Path) -> Path:
    import tifffile
    from scipy import ndimage

    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import emit_volume

    outdir = _guard_outdir(outdir)
    spec = resolve_format_ref(P_AXIS_K_FORMAT_REF)
    payload = det_bytes(P_AXIS_K_PAYLOAD_TAG, P_AXIS_K_PAYLOAD_BYTES)
    emit_dir = outdir / P_AXIS_K_EMIT_DIRNAME
    if emit_dir.is_dir():
        shutil.rmtree(emit_dir)
    volume = emit_volume(spec, payload, P_AXIS_K_SOURCE_FRACTION, emit_dir)
    if volume.plan.n_pages != 1:
        raise RuntimeError(f"the p300 K capture planned "
                           f"{volume.plan.n_pages} pages, not 1")
    dots_h = spec.layout.cells_yx[0] * spec.cell_dots
    dots_w = spec.layout.cells_yx[1] * spec.cell_dots
    dots = np.unpackbits(np.load(emit_dir / "page000_gt.npy"),
                         axis=-1)[:dots_h, :dots_w]
    border = K_BORDER_DOTS
    canvas = np.full((dots_h + 2 * border, dots_w + 2 * border),
                     K_PAPER_LEVEL, np.uint8)
    canvas[border:border + dots_h, border:border + dots_w] = np.where(
        dots != 0, K_INK_LEVEL, K_PAPER_LEVEL)
    up = np.repeat(np.repeat(canvas, UPSAMPLE, axis=0), UPSAMPLE, axis=1)
    blurred = ndimage.gaussian_filter(up.astype(np.float32), K_BLUR_SIGMA_PX)
    tifffile.imwrite(outdir / P_AXIS_K_TIFF_NAME,
                     np.round(np.clip(blurred, 0, 255)).astype(np.uint8))
    (outdir / P_AXIS_K_PAYLOAD_NAME).write_bytes(payload)
    return outdir


def capture_p_axis(outdir: Path) -> SimCapture:
    outdir = Path(outdir)
    target = outdir / P_AXIS_TIFF_NAME
    return SimCapture(
        name="p-axis", format_ref=P_AXIS_FORMAT_REF, dpi=DPI, rot_k=0,
        tiff=target, tiff_sha256=sha256_file(target),
        payload=outdir / P_AXIS_PAYLOAD_NAME,
        payload_sha256=P_AXIS_PAYLOAD_SHA256,
        payload_bytes=P_AXIS_PAYLOAD_BYTES,
        emit_dir=outdir / P_AXIS_EMIT_DIRNAME)


def capture_p_axis_k(outdir: Path) -> SimCapture:
    outdir = Path(outdir)
    target = outdir / P_AXIS_K_TIFF_NAME
    return SimCapture(
        name="p-axis-k", format_ref=P_AXIS_K_FORMAT_REF, dpi=DPI, rot_k=0,
        tiff=target, tiff_sha256=sha256_file(target),
        payload=outdir / P_AXIS_K_PAYLOAD_NAME,
        payload_sha256=P_AXIS_K_PAYLOAD_SHA256,
        payload_bytes=P_AXIS_K_PAYLOAD_BYTES,
        emit_dir=outdir / P_AXIS_K_EMIT_DIRNAME)
