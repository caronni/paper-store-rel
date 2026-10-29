"""The PAGE-FIELD stimuli: one displaced page, and that page cut up.

Split out of ``_h3_sims`` at the 1000-line seam (W6).  Everything here
is the W3b frame evidence for ``docs/PAGE-FIELD-DESIGN.md`` B1: the
clean colour emit with one plane out of register, and the same render
cut into four quadrant scraps pasted at all four quarter turns.  The
base sims, the renderer, the displacement shapes and the degraded
yield pair stay in ``_h3_sims``, which this module reads and which
never reads this one.

``_h3_fixture_build._cache_key`` hashes BOTH modules' sources: a stimulus that
moved here without the key following it would be served from a cache
keyed on the half it left behind.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import numpy as np

from ._h3_sims import (
    COLOR_BORDER_DOTS,
    COLOR_EMIT_DIRNAME,
    COLOR_FORMAT_REF,
    COLOR_GT_NAME,
    COLOR_GT_SHA256,
    COLOR_PAYLOAD_BYTES,
    COLOR_PAYLOAD_NAME,
    COLOR_PAYLOAD_SHA256,
    COLOR_PAYLOAD_TAG,
    COLOR_SOURCE_FRACTION,
    DPI,
    UPSAMPLE,
    SimCapture,
    _guard_outdir,
    _page_coverage,
    _render_coverage,
    det_bytes,
    plane_x_shift_dots,
    sha256_file,
    shift_plane_x,
)

SOURCE_DIGEST = hashlib.sha256(
    Path(__file__).resolve().read_bytes()).hexdigest()


# The CHEAP displaced page (2026-09-08, W3b): the clean colour sim's own
# emit with the Y plane out of register, and nothing else — no noise, no
# harder rung.  The expensive pair below is the yield instrument and it
# costs more wall than the whole slow lane; this one exists to ask the
# FRAME questions (does the field read the same displacement at a
# rotated placement, and off a confetti page mixing all four), which
# need a page the field can correct completely rather than one it
# struggles with.
#
# TWO DOTS is that: inside the anchor tier's own reach — Y's radius less
# its saturation margin, 2.24 dots (`field_tiers`) — and the largest
# whole dot that is, because a c3 cell is three dots and the displacement
# has to stay whole (`plane_x_shift_dots`: a fractional shift would
# interpolate, which blurs the plane as well as moving it).  One cycle
# down the page, the same mean-zero shape the hard pair uses, so a
# constant offset cannot be mistaken for it.
COLOR_SHIFTED_PLANE = 2
COLOR_SHIFTED_AMPLITUDE_DOTS = 2.0
COLOR_SHIFTED_CYCLES = 1.0
COLOR_SHIFTED_TIFF_NAME = "sim-color-shifted-clean-1200dpi.tiff"

# The CONFETTI page: the same displaced render cut into four quadrant
# scraps on tile boundaries, each pasted onto one platen at its own
# quarter turn.  Four windows of one page, four frames, one field —
# design §6 B1's second half.  The gutter is twice the render's own
# paper border, so no two scraps and no scrap edge share a region.
CONFETTI_CUTS = 2
CONFETTI_GUTTER_PX = 240
CONFETTI_SEED = 20260908
CONFETTI_TIFF_NAME = "sim-color-confetti-1200dpi.tiff"

# frozen 2026-09-08 from the first build of the displaced clean page and
# the confetti derived from it.  The PAYLOAD and the GROUND TRUTH are the
# clean sim's own frozen shas, which is the check that this stimulus is
# the same emit displaced and not a second volume: only the render moves.
COLOR_SHIFTED_TIFF_SHA256 = (
    "ffca8b0b0f9121e2a24d58a03c94a90d70f208d4767ec949ec8b90c3007e599e")
CONFETTI_TIFF_SHA256 = (
    "1ced3801f05be558af32446741becdd8a77791c35fc3fc5adddb8b22aba01329")
EXPECTED_COLOR_SHIFTED: dict[str, str] = {
    COLOR_SHIFTED_TIFF_NAME: COLOR_SHIFTED_TIFF_SHA256,
    COLOR_PAYLOAD_NAME: COLOR_PAYLOAD_SHA256,
    COLOR_GT_NAME: COLOR_GT_SHA256,
}
EXPECTED_CONFETTI: dict[str, str] = {
    CONFETTI_TIFF_NAME: CONFETTI_TIFF_SHA256,
}


def make_color_shifted(outdir: Path) -> Path:
    """The clean colour page again, with the Y plane out of register.

    Same emit as `make_color` — same spec, payload and source fraction,
    so the ground truth below carries the clean sim's own frozen sha —
    and the same noiseless render.  The one difference is applied to the
    COVERAGE, after the emit: Y's dots move along x by a whole-dot
    sinusoid, one cycle down the page.
    """
    import tifffile

    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import emit_volume

    outdir = _guard_outdir(outdir)
    spec = resolve_format_ref(COLOR_FORMAT_REF)
    payload = det_bytes(COLOR_PAYLOAD_TAG, COLOR_PAYLOAD_BYTES)
    emit_dir = outdir / COLOR_EMIT_DIRNAME
    if emit_dir.is_dir():
        shutil.rmtree(emit_dir)
    emit_volume(spec, payload, COLOR_SOURCE_FRACTION, emit_dir)
    coverage = _page_coverage(emit_dir, spec)
    shift_dots = plane_x_shift_dots(coverage.shape[1],
                                    COLOR_SHIFTED_AMPLITUDE_DOTS,
                                    COLOR_SHIFTED_CYCLES)
    displaced = shift_plane_x(coverage, COLOR_SHIFTED_PLANE, shift_dots)
    tifffile.imwrite(outdir / COLOR_SHIFTED_TIFF_NAME,
                     _render_coverage(displaced, COLOR_BORDER_DOTS))
    (outdir / COLOR_PAYLOAD_NAME).write_bytes(payload)
    return outdir


# The Y-DISPLACEMENT twin (2026-09-08, W8 R-E): the same emit, the same
# amplitude and the same period, turned a quarter — Y's dots move along
# the page's y axis by a whole-dot sinusoid, one cycle ACROSS the page.
# The M281's dominant registration term is in y and no stimulus in this
# tree has ever exercised it; the x page above and this one differ in
# exactly one thing, which axis the printer got wrong.
COLOR_SHIFTED_Y_TIFF_NAME = "sim-color-shifted-y-1200dpi.tiff"
COLOR_SHIFTED_Y_TIFF_SHA256 = (
    "9cdcb7921d157d2953bee38853e14da68ba8c182fc7f3774efa09a1693aecee2")
EXPECTED_COLOR_SHIFTED_Y: dict[str, str] = {
    COLOR_SHIFTED_Y_TIFF_NAME: COLOR_SHIFTED_Y_TIFF_SHA256,
    COLOR_PAYLOAD_NAME: COLOR_PAYLOAD_SHA256,
    COLOR_GT_NAME: COLOR_GT_SHA256,
}


def shift_plane_y(coverage: np.ndarray, plane: int,
                  shift_dots: np.ndarray) -> np.ndarray:
    """`_h3_sims.shift_plane_x` turned a quarter: each dot COLUMN moved.

    The x shifter applied to the transposed page IS the y shifter, so
    the whole-dot rule, the edge fill and the per-value grouping are the
    pinned code's and cannot drift away from it.
    """
    return np.swapaxes(
        shift_plane_x(np.swapaxes(coverage, 1, 2), plane, shift_dots),
        1, 2)


def make_color_shifted_y(outdir: Path) -> Path:
    """The clean colour page with Y out of register along Y.

    `make_color_shifted`'s page, one axis over: the displacement is the
    same rounded sinusoid at the same amplitude, indexed by the dot
    COLUMN rather than the dot row, so the two stimuli differ only in
    the axis the error lies along.
    """
    import tifffile

    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import emit_volume

    outdir = _guard_outdir(outdir)
    spec = resolve_format_ref(COLOR_FORMAT_REF)
    payload = det_bytes(COLOR_PAYLOAD_TAG, COLOR_PAYLOAD_BYTES)
    emit_dir = outdir / COLOR_EMIT_DIRNAME
    if emit_dir.is_dir():
        shutil.rmtree(emit_dir)
    emit_volume(spec, payload, COLOR_SOURCE_FRACTION, emit_dir)
    coverage = _page_coverage(emit_dir, spec)
    shift_dots = plane_x_shift_dots(coverage.shape[2],
                                    COLOR_SHIFTED_AMPLITUDE_DOTS,
                                    COLOR_SHIFTED_CYCLES)
    displaced = shift_plane_y(coverage, COLOR_SHIFTED_PLANE, shift_dots)
    tifffile.imwrite(outdir / COLOR_SHIFTED_Y_TIFF_NAME,
                     _render_coverage(displaced, COLOR_BORDER_DOTS))
    (outdir / COLOR_PAYLOAD_NAME).write_bytes(payload)
    return outdir


def capture_color_shifted_y(outdir: Path) -> SimCapture:
    outdir = Path(outdir)
    target = outdir / COLOR_SHIFTED_Y_TIFF_NAME
    return SimCapture(
        name="color-shifted-y", format_ref=COLOR_FORMAT_REF, dpi=DPI,
        rot_k=0, tiff=target, tiff_sha256=sha256_file(target),
        payload=outdir / COLOR_PAYLOAD_NAME,
        payload_sha256=COLOR_PAYLOAD_SHA256,
        payload_bytes=COLOR_PAYLOAD_BYTES,
        emit_dir=outdir / COLOR_EMIT_DIRNAME)


def capture_color_shifted(outdir: Path) -> SimCapture:
    outdir = Path(outdir)
    target = outdir / COLOR_SHIFTED_TIFF_NAME
    return SimCapture(
        name="color-shifted", format_ref=COLOR_FORMAT_REF, dpi=DPI,
        rot_k=0, tiff=target, tiff_sha256=sha256_file(target),
        payload=outdir / COLOR_PAYLOAD_NAME,
        payload_sha256=COLOR_PAYLOAD_SHA256,
        payload_bytes=COLOR_PAYLOAD_BYTES,
        emit_dir=outdir / COLOR_EMIT_DIRNAME)


def confetti_rotations(seed: int = CONFETTI_SEED) -> tuple[int, ...]:
    """Which quarter turn each quadrant is pasted at, in raster order.

    Seeded rather than chosen: the four rotations are dealt to the four
    scraps by one draw, so the arrangement is not a hand-picked easy
    one.  The SET is what the page asserts; which scrap wears which turn
    is the draw's business.
    """
    rng = np.random.default_rng(seed)
    return tuple(int(k) for k in rng.permutation(CONFETTI_CUTS ** 2))


def confetti_quadrant_px(image_shape: tuple[int, ...]) -> tuple[int, int]:
    """The printed page's origin and one quadrant's side, in pixels.

    One `side` for both axes, so the render has to be square — which the
    colour page is, and which is checked here rather than assumed.
    """
    if int(image_shape[0]) != int(image_shape[1]):
        raise ValueError(
            f"confetti quadrants are square: {image_shape[0]} x "
            f"{image_shape[1]} would cut different sides per axis")
    origin = COLOR_BORDER_DOTS * UPSAMPLE
    side = (int(image_shape[0]) - 2 * origin) // CONFETTI_CUTS
    return origin, side


def make_color_confetti(shifted_tiff: Path, outdir: Path) -> Path:
    """The displaced page cut into four scraps, each pasted turned.

    The cuts run on TILE boundaries, so every tile lands whole on one
    scrap and the page's certificate set is the uncut page's; what the
    cutting changes is the FRAME, four windows' worth of it at once.
    The scraps are laid on one platen with a paper gutter between and
    around them, which is the one capture the receiver is shown.
    """
    import tifffile

    outdir = _guard_outdir(outdir)
    image = np.asarray(tifffile.imread(shifted_tiff))
    origin, side = confetti_quadrant_px(image.shape)
    gutter = CONFETTI_GUTTER_PX
    span = CONFETTI_CUTS * side + (CONFETTI_CUTS + 1) * gutter
    platen = np.empty((span, span, image.shape[2]), image.dtype)
    platen[:, :] = image[0, 0]
    for quadrant, rot_k in enumerate(confetti_rotations()):
        qy, qx = divmod(quadrant, CONFETTI_CUTS)
        scrap = image[origin + qy * side:origin + (qy + 1) * side,
                      origin + qx * side:origin + (qx + 1) * side]
        turned = np.rot90(scrap, rot_k, axes=(0, 1))
        y0 = gutter + qy * (side + gutter)
        x0 = gutter + qx * (side + gutter)
        platen[y0:y0 + side, x0:x0 + side] = turned
    tifffile.imwrite(outdir / CONFETTI_TIFF_NAME, platen)
    return outdir


def capture_color_confetti(outdir: Path, base: SimCapture) -> SimCapture:
    """The platen as a capture.  `rot_k` is the RASTER's own turn, and
    the platen is not turned — the four quarter turns are inside it, one
    per scrap, and finding them is the receiver's job."""
    outdir = Path(outdir)
    target = outdir / CONFETTI_TIFF_NAME
    return SimCapture(
        name="color-confetti", format_ref=base.format_ref, dpi=DPI,
        rot_k=0, tiff=target, tiff_sha256=sha256_file(target),
        payload=base.payload, payload_sha256=base.payload_sha256,
        payload_bytes=base.payload_bytes, emit_dir=base.emit_dir)
