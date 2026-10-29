"""The cmy stimuli (CMY-RECEIVER-PLAN A2, A5, A7, A9): a c3 page in
register, the same page with M and Y out of register, the same page with
M faded in one band; and a c2 page at 2400 dpi with its dead-plane twins
and its seeded fragments.

cmy is the four-state alphabet {W, C, M, Y}, white or ONE toner per cell,
read as two label-bit streams (docs/CMY-DESIGN.md).  Its furniture is laid
for the R channel (R7, R24): word '1' prints C, word '0' the keyed W or Y,
the dust M-first by the balance law, so in R the dark sites are exactly
the C ones.  This page is what addressing on R is proved against.

The page is the emitter's own (`emit_volume`), rendered through the base
sims' `_page_coverage` / `_render_coverage` with a MEASURED subtractive mix
instead of the renderer's identity one: the M281's solid bars from e043
sheet 3 (`e043c_sheet3_bars`).  In register, no blur, no noise -- the
stimulus the A2..A4 waves read before any channel defect is added.  The
offset page (A5) is the same emission with M and Y moved by whole pixels,
the one defect the page field under F_C = 0 exists to undo.  The faint
page (A7) is the same emission again with M faded over a band of dot
rows, in register otherwise -- cmy8's FAINT idiom (`_h3_sims.
fade_plane_band`), the residue the translated rows read.

The c2 page (A9) is the print-edge row at 2400 dpi, 4 px per dot, with
e043c B1's offsets and a dot gain; rendered again with each toner
`dropped` it is G8's dead-stream page, and cut into 1x2, 2x2 and 2x3-tile
scraps laid on paper, each rendered with its own plane offsets, it is
G12's cold start.

``_h3_fixture_build._cache_key`` hashes this module's source with the
other stimulus modules; the base sims, the renderers and the render
constants stay in ``_h3_sims``, which this module reads and which never
reads this one.
"""
from __future__ import annotations

import dataclasses
import hashlib
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from ._h3_sims import (
    COLOR_BORDER_DOTS,
    DPI,
    SimCapture,
    _guard_outdir,
    _page_coverage,
    _render_coverage,
    det_bytes,
    fade_plane_band,
    sha256_file,
)

if TYPE_CHECKING:
    from holo.qualification.color_synthetic import (ColorChannelParameters,
                                                    MeasuredBars)

SOURCE_DIGEST = hashlib.sha256(
    Path(__file__).resolve().read_bytes()).hexdigest()

# The c3 row at the top rung the cmy ladder promises (R15): the e044 sheet
# B codec (1i200-cmy-r0850-p120-v1, there at 35x24) on the 10x10 geometry
# of the cmy8 colour sim, at that sim's payload and source fraction --
# 20,000 bytes at q = 0.35 against a one-page ceiling of 22,691.
CMY_FORMAT_REF = "c3-cmy-r0850@10x10"
CMY_PAYLOAD_TAG = b"holo3-sim-cmy"
CMY_PAYLOAD_BYTES = 20000
CMY_SOURCE_FRACTION = 0.35
CMY_EMIT_DIRNAME = "cmy-emit"
CMY_TIFF_NAME = "sim-cmy-1200dpi.tiff"
CMY_PAYLOAD_NAME = "sim-cmy-payload.bin"
CMY_GT_NAME = "cmy-emit/page000_gt.npy"
#: Whole 1200-dpi pixels (x, y) per plane C, M, Y: in register.
CMY_OFFSETS_PX: tuple[tuple[int, int], ...] = ((0, 0), (0, 0), (0, 0))
#: The offset page (A5): e043c B1's measured x offsets from C, M +1.23 and
#: Y +1.06 dots (CMY-RECEIVER-PLAN §0), at the nearest half dot -- one
#: 1200-dpi pixel -- so both +1.0 dot, 2 px; C stays where the pose is.
CMY_OFFSET_PAGE_PX: tuple[tuple[int, int], ...] = ((0, 0), (2, 0), (2, 0))
CMY_OFFSET_TIFF_NAME = "sim-cmy-offset-1200dpi.tiff"
#: The faint page (A7): M (plane 1) at `_h3_sims.FAINT_SCALE` of its ink
#: over `_h3_sims.FAINT_BAND_ROWS` of the page's dot rows, C and Y whole.
CMY_FAINT_PLANE = 1
CMY_FAINT_TIFF_NAME = "sim-cmy-faint-1200dpi.tiff"

# frozen 2026-10-12 from the first build; the TIFF re-frozen the same day
# for the rounded bars (payload and GT unmoved)
CMY_TIFF_SHA256 = (
    "b154b456b3886f622c1164e5811f5fdb98339540f4d872c659c9e67e5413773b")
CMY_PAYLOAD_SHA256 = (
    "02644afbe3bb567713b0add130f857880cd3bb691f4a04e9b032774c71e18e06")
CMY_GT_SHA256 = (
    "a589127161b1ea2d73399f15cf0b3e97144a1301def9621c1d5ddb711be87952")
EXPECTED_CMY: dict[str, str] = {
    CMY_TIFF_NAME: CMY_TIFF_SHA256,
    CMY_PAYLOAD_NAME: CMY_PAYLOAD_SHA256,
    CMY_GT_NAME: CMY_GT_SHA256,
}
# frozen 2026-10-12 from the offset page's first build (A5); its payload
# and GT are the in-register page's, one emission
CMY_OFFSET_TIFF_SHA256 = (
    "c579808e48a48eaf0019b45117e548b5bc977931c9f2ef17c6c43e998961b61c")
EXPECTED_CMY_OFFSET: dict[str, str] = {
    CMY_OFFSET_TIFF_NAME: CMY_OFFSET_TIFF_SHA256,
    CMY_PAYLOAD_NAME: CMY_PAYLOAD_SHA256,
    CMY_GT_NAME: CMY_GT_SHA256,
}
# frozen 2026-10-12 from the faint page's first build (A7); its payload
# and GT are the in-register page's, one emission
CMY_FAINT_TIFF_SHA256 = (
    "d802b9781450ca91fa88a28b4741e0397db3a276e0f35dbb664a65883cd5022b")
EXPECTED_CMY_FAINT: dict[str, str] = {
    CMY_FAINT_TIFF_NAME: CMY_FAINT_TIFF_SHA256,
    CMY_PAYLOAD_NAME: CMY_PAYLOAD_SHA256,
    CMY_GT_NAME: CMY_GT_SHA256,
}


def e043c_sheet3_bars() -> MeasuredBars:
    """The M281's solid bars, e043 sheet 3 (2026-10-11, Canon 2400 RGB).

    The registry's solids as that sheet printed them, one bar per zone
    (scratch2/e043c/readout/bars.csv, e043 §043.6): C (0, 176, 255) read
    R 47-56 G 152-157 B 206-207, M (240, 0, 192) 216-218 / 69-73 / 122-128,
    Y (255, 255, 0) 230-231 / 221-222 / 91-95, the white bars 230-232 /
    231-232 / 234-235.  The rule: each toner and white is the mean of its
    three bars, rounded half up to integers -- C (51.3, 154.5, 206.8) ->
    (51, 155, 207), M (216.8, 70.8, 124.7) -> (217, 71, 125), Y (230.2,
    221.8, 93.1) -> (230, 222, 93), white (230.9, 231.3, 234.3) -> (231,
    231, 234).  The printed c3 field reads lower contrast cell by
    cell -- e044 sheet B's colour table (scratch2/e044/readout/B/
    summary.json): W (199, 190, 191), C (79, 162, 180), M (194, 88, 133),
    Y (202, 190, 103) -- the gap A9's dot gain and blur tune toward; this
    in-register page carries the solids.
    """
    from holo.qualification.color_synthetic import MeasuredBars

    return MeasuredBars(
        paper_rgb=(231, 231, 234),
        toner_rgb=((51, 155, 207), (217, 71, 125), (230, 222, 93)),
        record="e043c sheet 3 (M281, 2026-10-11) solid C/M/Y and white "
               "bars, scratch2/e043c/readout/bars.csv")


def cmy_channel(offsets_px: tuple[tuple[int, int], ...] = CMY_OFFSETS_PX
                ) -> ColorChannelParameters:
    from holo.qualification.color_synthetic import cmy_channel_parameters

    return cmy_channel_parameters(offsets_px, bars=e043c_sheet3_bars())


def make_cmy(outdir: Path) -> Path:
    return _make_cmy_page(outdir, CMY_OFFSETS_PX, CMY_TIFF_NAME)


def make_cmy_offset(outdir: Path) -> Path:
    return _make_cmy_page(outdir, CMY_OFFSET_PAGE_PX, CMY_OFFSET_TIFF_NAME)


def make_cmy_faint(outdir: Path) -> Path:
    return _make_cmy_page(outdir, CMY_OFFSETS_PX, CMY_FAINT_TIFF_NAME,
                          CMY_FAINT_PLANE)


def _make_cmy_page(outdir: Path, offsets_px: tuple[tuple[int, int], ...],
                   tiff_name: str, faded_plane: int | None = None) -> Path:
    import tifffile

    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import emit_volume

    outdir = _guard_outdir(outdir)
    spec = resolve_format_ref(CMY_FORMAT_REF)
    payload = det_bytes(CMY_PAYLOAD_TAG, CMY_PAYLOAD_BYTES)
    emit_dir = outdir / CMY_EMIT_DIRNAME
    if emit_dir.is_dir():
        shutil.rmtree(emit_dir)
    volume = emit_volume(spec, payload, CMY_SOURCE_FRACTION, emit_dir)
    if volume.plan.n_pages != 1:
        raise RuntimeError(f"the c3 cmy capture planned "
                           f"{volume.plan.n_pages} pages, not 1")
    # A9's hooks: dot gain is one binary dilation per plane of `coverage`
    # (a helper beside `_h3_sims.shift_plane_x`), a dead plane is
    # `PlaneParameters(dropped=True)` in the channel's planes.
    coverage = _page_coverage(emit_dir, spec)
    if faded_plane is not None:
        coverage = fade_plane_band(coverage, faded_plane)
    tifffile.imwrite(outdir / tiff_name,
                     _render_coverage(coverage, COLOR_BORDER_DOTS,
                                      cmy_channel(offsets_px)))
    (outdir / CMY_PAYLOAD_NAME).write_bytes(payload)
    return outdir


def capture_cmy(outdir: Path) -> SimCapture:
    return _capture_cmy_page(outdir, "cmy", CMY_TIFF_NAME)


def capture_cmy_offset(outdir: Path) -> SimCapture:
    return _capture_cmy_page(outdir, "cmy-offset", CMY_OFFSET_TIFF_NAME)


def capture_cmy_faint(outdir: Path) -> SimCapture:
    return _capture_cmy_page(outdir, "cmy-faint", CMY_FAINT_TIFF_NAME)


def _capture_cmy_page(outdir: Path, name: str, tiff_name: str) -> SimCapture:
    outdir = Path(outdir)
    target = outdir / tiff_name
    return SimCapture(
        name=name, format_ref=CMY_FORMAT_REF, dpi=DPI, rot_k=0,
        tiff=target, tiff_sha256=sha256_file(target),
        payload=outdir / CMY_PAYLOAD_NAME,
        payload_sha256=CMY_PAYLOAD_SHA256,
        payload_bytes=CMY_PAYLOAD_BYTES,
        emit_dir=outdir / CMY_EMIT_DIRNAME)


# The c2 page (A9): the e044 sheet A codec (1i300-cmy-r0775x0700-p120-v1,
# there at 53x37) on the 10x10 geometry, 16,000 bytes at q = 0.35 against
# a one-page ceiling of 16,722 and under the pair's any-one-stream ceiling
# 17/36 (the stream tier G8 reads), at the 2400 dpi the c2 sheets are
# scanned at.  M and Y sit at e043c B1's +1.23 / +1.06 dots in x at the
# nearest half dot, +1.0 dot = 4 px each.
CMY_C2_FORMAT_REF = "c2-cmy-r0775x0700@10x10"
CMY_C2_PAYLOAD_TAG = b"holo3-sim-cmy-c2"
CMY_C2_PAYLOAD_BYTES = 16000
CMY_C2_SOURCE_FRACTION = 0.35
CMY_C2_DPI = 2400.0
CMY_C2_PX_PER_DOT = 4
CMY_C2_TILES = 10
CMY_C2_TILE_DOTS = 64 * 2
CMY_C2_OFFSET_PX: tuple[tuple[int, int], ...] = ((0, 0), (4, 0), (4, 0))
#: Dot gain in 2400-dpi pixels, ONE binary dilation per plane, tuned
#: toward B1's W row (`measure/cmy_coldstart`, 2026-10-12): the
#: supervised context-free W-row error at the per-plane true poses reads
#: 0 % at 0-2 px, 5.88 % at 3 px and 47.7 % at 4 px, against sheet 3's
#: 13.9-14.6 % and sheet A's 14.9 %; 3 px (0.75 dot per edge, the
#: measured gain 0.31-0.39) is the nearest a whole pixel gets.
CMY_C2_GAIN_PX = 3
CMY_C2_EMIT_DIRNAME = "cmy-c2-emit"
CMY_C2_TIFF_NAME = "sim-cmy-c2-2400dpi.tiff"
CMY_C2_PAYLOAD_NAME = "sim-cmy-c2-payload.bin"
CMY_C2_GT_NAME = "cmy-c2-emit/page000_gt.npy"
#: G8's dead toners (design §2.2's death map): the page rendered with that
#: plane `dropped` -- Y kills lo, M kills hi, C both and the words' '1'.
CMY_C2_DEAD_PLANES = {"Y": 2, "M": 1, "C": 0}
CMY_C2_DEAD_TIFF_NAMES = {
    toner: f"sim-cmy-c2-dead-{toner.lower()}-2400dpi.tiff"
    for toner in CMY_C2_DEAD_PLANES}

# G12's fragments: a scrap of whole tiles cut from the c2 emission, laid
# on paper (`COLOR_BORDER_DOTS` all round), no certificates, its own
# (dM, dY) plane offsets in dots: Z (0, 0), A (0.5, -0.5), B (1.0, 1.0)
# and C (2.5, -2.5) -- whole 2400-dpi pixels.  "drift" moves M and Y
# against C by +-`CMY_C2_CROP_DRIFT_DOTS` from the scrap's top edge to its
# bottom (`y_drift_xy`, M one way, Y the other); its "control" moves all
# three planes by M's drift, so every plane is interpolated at the same
# sub-pixel phases and nothing moves against the pose, which absorbs a
# common shear; "none" interpolates nothing.  Where each scrap sits is
# one seeded draw per shape, so every condition of a shape cuts the same
# tiles.
CMY_C2_CROP_SEED = 20261012
CMY_C2_CROP_SHAPES: tuple[tuple[int, int], ...] = ((1, 2), (2, 2), (2, 3))
CMY_C2_CROP_PLANTS_DOTS: dict[str, tuple[float, float]] = {
    "Z": (0.0, 0.0), "A": (0.5, -0.5), "B": (1.0, 1.0), "C": (2.5, -2.5)}
CMY_C2_CROP_DRIFT_DOTS = 0.5
CMY_C2_DRIFT_MODES = ("drift", "control", "none")
#: The scraps the tests decode (A9: Z, A and C on 2x3, A with its
#: control too); the rest of the grid is `measure/cmy_coldstart`'s record.
CMY_C2_TESTED_CROPS: tuple[tuple[tuple[int, int], str, str], ...] = (
    ((2, 3), "Z", "drift"), ((2, 3), "A", "drift"), ((2, 3), "A", "control"),
    ((2, 3), "C", "none"))

# frozen 2026-10-12 from the first build of the page, its dead twins and
# the tested scraps (one emission: the scraps carry its payload and GT)
CMY_C2_TIFF_SHA256 = (
    "55d0120652b8867199d1a811997322efbdde5e5e27a4352f73780e9de55bd2f9")
CMY_C2_PAYLOAD_SHA256 = (
    "918ab6200f9afa95ed63c29dfedf5f845811de0d3f828f219cbe3eac5d9f7d02")
CMY_C2_GT_SHA256 = (
    "aa8e5dd0ceb80fc1f59b30abc3b823124fa56f9f59588b1f1b8628cd682ca24d")
CMY_C2_DEAD_TIFF_SHA256 = {
    "Y": "81de82c1f7e6d631b467de0c9442ab3499392b2573fe504c679c57ede1302428",
    "M": "4e8818921cb4ac75afbe91efe027d4c807e0f3997aecd5e81547974df19f351f",
    "C": "61f1f6ffa97234f54d8fa41fb854108590cab394bc714b80bcf35af48c74ce23"}
EXPECTED_CMY_C2: dict[str, str] = {
    CMY_C2_TIFF_NAME: CMY_C2_TIFF_SHA256,
    CMY_C2_PAYLOAD_NAME: CMY_C2_PAYLOAD_SHA256,
    CMY_C2_GT_NAME: CMY_C2_GT_SHA256,
    **{CMY_C2_DEAD_TIFF_NAMES[toner]: digest
       for toner, digest in CMY_C2_DEAD_TIFF_SHA256.items()},
}
CMY_C2_CROP_TIFF_SHA256 = (
    "e44bd5f74bb5f2eb9e57a814efc67dd76d0838681388aa80e615479f1a93ba30",
    "9eb90d1126197d2d5e900d5c44fc3897fc006d8c9675a66a6be55d9b8bc294a4",
    "1fb360bba6659d44fb2737008b94a01cf1690873f24450c52e6965bdcb0c6d94",
    "712467688630f33b2c348bd770d68918389514fc43465a22b290dd5d9244205f")


def cmy_c2_crop_name(shape: tuple[int, int], plant: str, drift: str) -> str:
    return f"cmy-c2-crop-{shape[0]}x{shape[1]}-{plant}-{drift}"


def cmy_c2_crop_tiff_name(shape: tuple[int, int], plant: str,
                          drift: str) -> str:
    return f"sim-{cmy_c2_crop_name(shape, plant, drift)}-2400dpi.tiff"


EXPECTED_CMY_C2_CROPS: dict[str, str] = {
    **{cmy_c2_crop_tiff_name(*crop): digest
       for crop, digest in zip(CMY_C2_TESTED_CROPS, CMY_C2_CROP_TIFF_SHA256,
                               strict=True)},
    CMY_C2_PAYLOAD_NAME: CMY_C2_PAYLOAD_SHA256,
    CMY_C2_GT_NAME: CMY_C2_GT_SHA256,
}


def cmy_c2_channel(offsets_px: tuple[tuple[int, int], ...] = CMY_C2_OFFSET_PX,
                   drift_px_per_px: tuple[float, float, float] = (0.0, 0.0,
                                                                   0.0),
                   dropped: int | None = None) -> ColorChannelParameters:
    """sheet 3's bars, whole-pixel plane offsets, each plane's x drift per
    source pixel row (`PlaneParameters.y_drift_xy`) and one plane
    `dropped`."""
    from holo.qualification.color_synthetic import cmy_channel_parameters

    base = cmy_channel_parameters(offsets_px, bars=e043c_sheet3_bars())
    return dataclasses.replace(base, planes=tuple(
        dataclasses.replace(plane, y_drift_xy=(float(drift), 0.0),
                            dropped=index == dropped)
        for index, (plane, drift) in enumerate(zip(base.planes,
                                                   drift_px_per_px))))


def _emit_cmy_c2(outdir: Path) -> tuple[object, np.ndarray]:
    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import emit_volume

    spec = resolve_format_ref(CMY_C2_FORMAT_REF)
    payload = det_bytes(CMY_C2_PAYLOAD_TAG, CMY_C2_PAYLOAD_BYTES)
    emit_dir = outdir / CMY_C2_EMIT_DIRNAME
    if emit_dir.is_dir():
        shutil.rmtree(emit_dir)
    volume = emit_volume(spec, payload, CMY_C2_SOURCE_FRACTION, emit_dir)
    if volume.plan.n_pages != 1:
        raise RuntimeError(f"the c2 cmy capture planned "
                           f"{volume.plan.n_pages} pages, not 1")
    # G8's premise: q under the pair's any-one-stream ceiling, where the
    # planner promises the stream tier (`plan.pooled_plane_tier`).
    if volume.plan.plane_tier != "guaranteed":
        raise RuntimeError(f"the c2 cmy capture's stream tier is "
                           f"{volume.plan.plane_tier!r}, not guaranteed")
    (outdir / CMY_C2_PAYLOAD_NAME).write_bytes(payload)
    return spec, _page_coverage(emit_dir, spec)


def _render_c2(coverage: np.ndarray,
               parameters: ColorChannelParameters) -> np.ndarray:
    return _render_coverage(coverage, COLOR_BORDER_DOTS, parameters,
                            upsample=CMY_C2_PX_PER_DOT,
                            gain_px=CMY_C2_GAIN_PX)


def make_cmy_c2(outdir: Path) -> Path:
    import tifffile

    outdir = _guard_outdir(outdir)
    _spec, coverage = _emit_cmy_c2(outdir)
    tifffile.imwrite(outdir / CMY_C2_TIFF_NAME,
                     _render_c2(coverage, cmy_c2_channel()))
    for toner, plane in CMY_C2_DEAD_PLANES.items():
        tifffile.imwrite(outdir / CMY_C2_DEAD_TIFF_NAMES[toner],
                         _render_c2(coverage, cmy_c2_channel(dropped=plane)))
    return outdir


def cmy_c2_crop_origin(shape: tuple[int, int]) -> tuple[int, int]:
    """The scrap's top-left tile: one seeded draw per shape."""
    rows, cols = shape
    rng = np.random.default_rng((CMY_C2_CROP_SEED, rows, cols))
    return (int(rng.integers(0, CMY_C2_TILES - rows + 1)),
            int(rng.integers(0, CMY_C2_TILES - cols + 1)))


def cmy_c2_crop_channel(shape: tuple[int, int], plant: str,
                        drift: str) -> ColorChannelParameters:
    """The scrap's plane offsets and drift, in 2400-dpi pixels."""
    d_m, d_y = CMY_C2_CROP_PLANTS_DOTS[plant]
    offsets = ((0, 0), (round(d_m * CMY_C2_PX_PER_DOT), 0),
               (round(d_y * CMY_C2_PX_PER_DOT), 0))
    height_px = shape[0] * CMY_C2_TILE_DOTS * CMY_C2_PX_PER_DOT
    slope = 2.0 * CMY_C2_CROP_DRIFT_DOTS * CMY_C2_PX_PER_DOT / height_px
    drifts = {"drift": (0.0, slope, -slope),
              "control": (slope, slope, slope),
              "none": (0.0, 0.0, 0.0)}[drift]
    return cmy_c2_channel(offsets, drifts)


def render_cmy_c2_crop(coverage: np.ndarray, shape: tuple[int, int],
                       plant: str, drift: str) -> np.ndarray:
    ty, tx = cmy_c2_crop_origin(shape)
    step = CMY_C2_TILE_DOTS
    scrap = coverage[:, ty * step:(ty + shape[0]) * step,
                     tx * step:(tx + shape[1]) * step]
    return _render_c2(scrap, cmy_c2_crop_channel(shape, plant, drift))


def make_cmy_c2_crops(outdir: Path,
                      crops: tuple[tuple[tuple[int, int], str, str], ...]
                      = CMY_C2_TESTED_CROPS) -> Path:
    import tifffile

    outdir = _guard_outdir(outdir)
    _spec, coverage = _emit_cmy_c2(outdir)
    for shape, plant, drift in crops:
        tifffile.imwrite(outdir / cmy_c2_crop_tiff_name(shape, plant, drift),
                         render_cmy_c2_crop(coverage, shape, plant, drift))
    return outdir


def capture_cmy_c2(outdir: Path) -> SimCapture:
    return _capture_cmy_c2_tiff(outdir, "cmy-c2", CMY_C2_TIFF_NAME)


def capture_cmy_c2_dead(outdir: Path, toner: str) -> SimCapture:
    return _capture_cmy_c2_tiff(outdir, f"cmy-c2-dead-{toner.lower()}",
                                CMY_C2_DEAD_TIFF_NAMES[toner])


def capture_cmy_c2_crop(outdir: Path, shape: tuple[int, int], plant: str,
                        drift: str) -> SimCapture:
    return _capture_cmy_c2_tiff(outdir, cmy_c2_crop_name(shape, plant, drift),
                                cmy_c2_crop_tiff_name(shape, plant, drift))


def _capture_cmy_c2_tiff(outdir: Path, name: str,
                         tiff_name: str) -> SimCapture:
    outdir = Path(outdir)
    target = outdir / tiff_name
    return SimCapture(
        name=name, format_ref=CMY_C2_FORMAT_REF, dpi=CMY_C2_DPI, rot_k=0,
        tiff=target, tiff_sha256=sha256_file(target),
        payload=outdir / CMY_C2_PAYLOAD_NAME,
        payload_sha256=CMY_C2_PAYLOAD_SHA256,
        payload_bytes=CMY_C2_PAYLOAD_BYTES,
        emit_dir=outdir / CMY_C2_EMIT_DIRNAME)
