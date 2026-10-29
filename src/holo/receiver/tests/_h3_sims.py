from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from holo.qualification.color_synthetic import ColorChannelParameters

RENDER_CACHE_VERSION = 1

DPI = 1200.0
UPSAMPLE = 2

K_FORMAT_REF = "c3-k-r0550@7x7"
K_PAYLOAD_TAG = b"holo3-sim-k"
K_PAYLOAD_BYTES = 6000
K_SOURCE_FRACTION = 0.5
K_BORDER_DOTS = 96
K_INK_LEVEL = 35
K_PAPER_LEVEL = 245
K_BLUR_SIGMA_PX = 1.0

COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"
COLOR_PAYLOAD_TAG = b"holo3-sim-color"
COLOR_PAYLOAD_BYTES = 20000
COLOR_SOURCE_FRACTION = 0.35
COLOR_BORDER_DOTS = 60

# The registration-degraded colour PAIR: one emitted page rendered twice,
# once with every plane in register and once with ONE plane's dots
# displaced along x by a smooth function of y — the measured AltaLink
# Y-registration sinusoid in miniature (0.83 dot peak over ~100 mm there;
# one full cycle down the page here).  A mean-zero full cycle was chosen
# to be invisible to the {1,y} page-fraction residual the colour lane
# carried then; that residual RETIRED 2026-09-07 (W3a, I7) and the lane
# now reads at the page field or at the pose and nothing else, so the
# attribution is more direct than when this shape was picked, not less.
# What the displacement costs and what a tile-space field buys back are
# both attributable to the field alone.  The control
# carries the same noise draw, so the loss is charged to the
# displacement and not to the noise that makes it bite.
#
# THE AMPLITUDE IS THREE DOTS, not the two it was until 2026-08-31, and
# the reason is a receiver that outgrew two dots — the full episode is
# in the receiver's docs/WIDENED-MATRIX-RETIREMENT-2026-09-20.md, which
# carries the retired pair's ledger.  Three is not a free
# parameter: it is the first whole dot ABOVE the blind sampling-offset
# search `tiles.planek` runs (`SHIFT_MIN/MAX_DOTS` = +-2.0) and above
# what the colour head's own local re-fit absorbs.  At four dots the Y
# plane dies outright (measured: zero Y certificates), so the window
# this stimulus lives in is exactly one dot wide.  RE-POINTED
# 2026-09-07 with the page field: what bounds the field is its
# ESTIMATOR'S reach, `field_tiers.ANCHOR_RADIUS_DOTS[2]` less
# `ANCHOR_SATURATION_MARGIN_DOTS` (2.24 dots), and not the retired
# clamp — so at three dots the tiers refuse and the field reads exactly
# zero on this stimulus (measured, W2 report), which is why the retired
# pair held `tiles.swim` out rather than reading the field's correction.
#
# EPISODE 3 (2026-08-31, hours later) did NOT move this number, and why
# belongs here as well as in the test: three dots is ALSO exactly
# `tiles.swim`'s blind translation bound — that row searches within one
# printed CELL of its hint, and this is a c3 page — so it recovers the
# displaced page unaided with the field switched off (measured 300/300).
# A steeply displaced pair at 5.2 dots, where the FIELD is the row that
# comes up short, was the other end of that band; it retired 2026-09-20
# with the three decodes it took to say so, and the amplitude ladder
# behind it is in the record named above.  What is left here is the
# renderer itself, which `measure/local_ab` drives at any amplitude it
# declares — no fixture verifies these bytes any more.
SHIFTED_PLANE = 2
SHIFTED_AMPLITUDE_DOTS = 3.0
SHIFTED_CYCLES = 1.0
SHIFTED_NOISE_SD = 12.0
SHIFTED_SEED = 20260830
SHIFTED_TIFF_NAME = "sim-color-shifted-1200dpi.tiff"
CONTROL_TIFF_NAME = "sim-color-control-1200dpi.tiff"

# The page is the same geometry as the clean colour sim at the TOP cmy8
# rung, which is the regime sheet H prints in and the only one measured
# where a plane's registration is worth certificates: at r0550 the inner
# code absorbed a two-dot displacement AND 55 sd of sensor noise without
# losing a single tile (measured 2026-08-30).  At r0850, 3 dots + 12 sd
# costs 13 Y certificates (2026-08-31; 2 dots cost 16 when the pair was
# first built and cost nothing by the end of the month).
HARD_FORMAT_REF = "c3-cmy8-r0850x0850x0850@10x10"
HARD_PAYLOAD_TAG = b"holo3-sim-color-hard"
HARD_PAYLOAD_BYTES = 20000
HARD_SOURCE_FRACTION = 0.35
HARD_EMIT_DIRNAME = "color-hard-emit"
HARD_PAYLOAD_NAME = "sim-color-hard-payload.bin"

# The column-group colour pair (docs/CMY8-COLUMN-GROUPS.md, rulings
# 2026-09-04): the INDEPENDENT-PLANES §H Y lever — C and M at r0700, Y at
# r0547 — under ONE pooled fountain, rendered twice from one emit: in
# register, and with the Y plane printing NOTHING.  The second capture is
# the dead-plane gate of the pooled design carried to an uneven triplet:
# at q = 0.35, well under the lever's dead-Y ceiling of 34/47, the volume
# must close byte-exact with zero Y certificates.
GROUPS_FORMAT_REF = "c3-cmy8-r0700x0700x0547@10x10"
GROUPS_PAYLOAD_TAG = b"holo3-sim-color-groups"
GROUPS_PAYLOAD_BYTES = 20000
GROUPS_SOURCE_FRACTION = 0.35
GROUPS_DEAD_PLANE = 2
GROUPS_EMIT_DIRNAME = "color-groups-emit"
GROUPS_TIFF_NAME = "sim-color-groups-1200dpi.tiff"
GROUPS_DEAD_Y_TIFF_NAME = "sim-color-groups-dead-y-1200dpi.tiff"
GROUPS_PAYLOAD_NAME = "sim-color-groups-payload.bin"
GROUPS_GT_NAME = "color-groups-emit/page000_gt.npy"

# The same lever over THREE pages, sized so that page 0's systematic
# region runs past its C and M planes into Y: 49 Y tiles carry source
# chunks and one straddles the block boundary (the cases the one-page
# goldens never reach, their systematic region ending inside C).
PAGES_PAYLOAD_TAG = b"holo3-sim-color-groups-pages"
PAGES_PAYLOAD_BYTES = 80000
PAGES_N = 3
PAGES_EMIT_DIRNAME = "color-groups-pages-emit"
PAGES_PAYLOAD_NAME = "sim-color-groups-pages-payload.bin"
PAGES_TIFF_NAMES = tuple(f"sim-color-groups-page{p}-1200dpi.tiff"
                         for p in range(PAGES_N))

K_CELL_DOTS = 3
MIXED_DPI_B = DPI / 2
MIXED_NOISE_SD = 12.0
MIXED_SEED_A = 20260830
MIXED_SEED_B = 20260831
MIXED_TILE_CELLS = 64
MIXED_TILES = 7
MIXED_HOLE_A_TILE_COLUMN = 6
MIXED_HOLE_B_TILE_COLUMN = 0
MIXED_UNION_TILE_YX = (3, 3)
MIXED_UNION_KEEP_CELLS = 26

K_TIFF_NAME = "sim-k-1200dpi.tiff"
K_PAYLOAD_NAME = "sim-k-payload.bin"
COLOR_TIFF_NAME = "sim-color-1200dpi.tiff"
COLOR_PAYLOAD_NAME = "sim-color-payload.bin"
COLOR_EMIT_DIRNAME = "color-emit"
COLOR_GT_NAME = "color-emit/page000_gt.npy"
MIXED_A_TIFF_NAME = "sim-k-mixed-1200dpi.tiff"
MIXED_B_TIFF_NAME = "sim-k-mixed-600dpi.tiff"

# frozen 2026-08-29 from the oracle-confirmed acceptance-step-1
# artefacts (sims.json + acceptance.json steps 1k/1c); the tree they
# were lifted from no longer exists, and the shas are the record of it.
# RE-FROZEN 2026-09-02: FORMAT-SPACE §16 made the canonical id (hence the
# AES row seed) the explicit spelling, so every v2 render changes.  The
# PAYLOAD shas are UNCHANGED: they are det_bytes-derived and carry no
# format identity — the check that this is a re-key and not a payload
# drift.
K_TIFF_SHA256 = (
    "fcd59b575e31c8b4b8031e7defb1b729385622bcebaa8e8a6bde7d27611aa578")
K_PAYLOAD_SHA256 = (
    "59495601d00fa78145f5400e97eb53ee31424c57d6be905f00f2f62a7699848f")
COLOR_TIFF_SHA256 = (
    "e0a42b399c9c7ca51a5f79d5f8ea03775aeea2a7e3726274ee85a781161c934a")
COLOR_PAYLOAD_SHA256 = (
    "ddf7acebcd86ae52aea2a61224c80cf3dee3746083a616a4a28e9b333754e1d6")
COLOR_GT_SHA256 = (
    "75d8cae5aae2e35710eeb361fd2212dafc7837e0f494ba26af82a1f0be000222")

# frozen 2026-08-30: deterministic derivations of the frozen K render —
# capture A at the native class with complementary erasures, capture B
# the same render area-decimated 2:1 declared at half dpi
MIXED_A_TIFF_SHA256 = (
    "086ae013a97db69407ff6b19fa9718b0226b353f6f1d165be24361f3a0e77ea7")
MIXED_B_TIFF_SHA256 = (
    "19feaf3718dda1125440e5d75c4b40a018451a5edba2e6a9f9659edc4e1b598e")

EXPECTED_K: dict[str, str] = {
    K_TIFF_NAME: K_TIFF_SHA256,
    K_PAYLOAD_NAME: K_PAYLOAD_SHA256,
}
EXPECTED_COLOR: dict[str, str] = {
    COLOR_TIFF_NAME: COLOR_TIFF_SHA256,
    COLOR_PAYLOAD_NAME: COLOR_PAYLOAD_SHA256,
    COLOR_GT_NAME: COLOR_GT_SHA256,
}
EXPECTED_MIXED: dict[str, str] = {
    MIXED_A_TIFF_NAME: MIXED_A_TIFF_SHA256,
    MIXED_B_TIFF_NAME: MIXED_B_TIFF_SHA256,
}

# frozen 2026-09-04 from the first build of the column-group pair
GROUPS_TIFF_SHA256 = (
    "c550718b2b9b31ab12502720f666fced8242223491d569113c3ceeb128a55fa2")
GROUPS_DEAD_Y_TIFF_SHA256 = (
    "c8bad5e688d1d89336674714dfbfa7f86d1c9dab55d267078c2554be3de94749")
GROUPS_PAYLOAD_SHA256 = (
    "68e69038d474b05642567c183ffdc646a1168bbdce0ea836373eb23eca9a12a4")
GROUPS_GT_SHA256 = (
    "7e8acdff6a1fe5ed8b48499b8a7c6ba823a20d9e44a89da4191ac895bcc7a4a1")
EXPECTED_GROUPS: dict[str, str] = {
    GROUPS_TIFF_NAME: GROUPS_TIFF_SHA256,
    GROUPS_DEAD_Y_TIFF_NAME: GROUPS_DEAD_Y_TIFF_SHA256,
    GROUPS_PAYLOAD_NAME: GROUPS_PAYLOAD_SHA256,
    GROUPS_GT_NAME: GROUPS_GT_SHA256,
}
PAGES_PAYLOAD_SHA256 = (
    "b0246ed26c3e4be0f8d1851b37bd7bebfd05178d3f6eed115e7c5603427009b5")
PAGES_TIFF_SHA256 = (
    "152d6d57d8e64f43ba4e27e5990911cf305648ca1719f92c04a61cedf0cd8f87",
    "6360f849fc5faaebb6d351c571164ed0db6a7432912a478c4e8b44aa6a40c8db",
    "0f78d4da7d3fa3e3a69107c38291518697b23910867d44846acbcad30d9b3257")
EXPECTED_PAGES: dict[str, str] = {
    PAGES_PAYLOAD_NAME: PAGES_PAYLOAD_SHA256,
    **dict(zip(PAGES_TIFF_NAMES, PAGES_TIFF_SHA256)),
}

# frozen 2026-08-30: the top-rung colour pair, one emit rendered twice.
# No pytest fixture reads these any more — the two whole-page colour
# existence proofs retired 2026-09-20
# (docs/WIDENED-MATRIX-RETIREMENT-2026-09-20.md, which carries the steep
# pair's own table) — but `measure/h3_repricing.py` materialises the pair
# through `EXPECTED_HARD` so two trees decode the byte-identical capture,
# and `measure/local_ab/_sim.py` loads its payload against the sha, so
# the table stays for the instruments that read it.
HARD_PAYLOAD_SHA256 = (
    "7902836205689f47c7c2d80c53023b1a31442720b86d175d677e6b71f66155c9")
CONTROL_TIFF_SHA256 = (
    "d1531ec4109235fa5bd470efb25294e322d4f09595723ff56a6e26bd8c89ffe2")
SHIFTED_TIFF_SHA256 = (
    "31ed036ae09bf516d1675d0930f07488d99ef4869997747077f4e397deb0a5ab")
EXPECTED_HARD: dict[str, str] = {
    HARD_PAYLOAD_NAME: HARD_PAYLOAD_SHA256,
    CONTROL_TIFF_NAME: CONTROL_TIFF_SHA256,
    SHIFTED_TIFF_NAME: SHIFTED_TIFF_SHA256,
}

SOURCE_DIGEST = hashlib.sha256(
    Path(__file__).resolve().read_bytes()).hexdigest()


@dataclass(frozen=True)
class SimCapture:
    name: str
    format_ref: str
    dpi: float
    rot_k: int
    tiff: Path
    tiff_sha256: str
    payload: Path
    payload_sha256: str
    payload_bytes: int
    emit_dir: Path | None

    @property
    def payload_data(self) -> bytes:
        return self.payload.read_bytes()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def det_bytes(tag: bytes, n: int) -> bytes:
    out = b""
    chain = tag
    while len(out) < n:
        chain = hashlib.sha256(chain).digest()
        out += chain
    return out[:n]


PRODUCER_MODULES = (
    "tifffile", "scipy.ndimage", "holo.core.fountain", "holo.format.resolve",
    "holo.gen.compose", "holo.gen.emit", "holo.gen.plan",
    "holo.qualification.color_synthetic")


def producer_unavailable_reason() -> str | None:
    import importlib

    for module_name in PRODUCER_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            return (f"src/holo sim producer unavailable: "
                    f"{module_name}: {exc!r}")
    return None


def _guard_outdir(outdir: Path) -> Path:
    outdir = Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def make_k(outdir: Path) -> Path:
    import tifffile
    from scipy import ndimage

    from holo.core import fountain
    from holo.format.resolve import resolve_format_ref
    from holo.gen.compose import cells_to_dots, compose_page_cells
    from holo.gen.emit import METADATA_VERSION, source_packed_for
    from holo.gen.plan import plan_volume

    outdir = _guard_outdir(outdir)
    spec = resolve_format_ref(K_FORMAT_REF)
    payload = det_bytes(K_PAYLOAD_TAG, K_PAYLOAD_BYTES)
    plan = plan_volume(spec, len(payload), K_SOURCE_FRACTION)
    source = source_packed_for(payload, plan)
    code = fountain.VolumeCode(plan.k_total, plan.symbol_bits, spec.seed,
                               tiles_per_page=spec.tiles_per_page)
    esis = np.arange(spec.tiles_per_page, dtype=np.int64)
    cells = compose_page_cells(spec, 0, code.encode_symbols(source, esis),
                               plan.k_total, version=METADATA_VERSION)
    dots = cells_to_dots(cells, spec.cell_dots)
    border = K_BORDER_DOTS
    height, width = dots.shape
    canvas = np.full((height + 2 * border, width + 2 * border),
                     K_PAPER_LEVEL, np.uint8)
    canvas[border:border + height, border:border + width] = np.where(
        dots != 0, K_INK_LEVEL, K_PAPER_LEVEL)
    up = np.repeat(np.repeat(canvas, UPSAMPLE, axis=0), UPSAMPLE, axis=1)
    blurred = ndimage.gaussian_filter(up.astype(np.float32),
                                      K_BLUR_SIGMA_PX)
    image = np.round(np.clip(blurred, 0, 255)).astype(np.uint8)
    tifffile.imwrite(outdir / K_TIFF_NAME, image)
    (outdir / K_PAYLOAD_NAME).write_bytes(payload)
    return outdir


def make_color(outdir: Path) -> Path:
    import tifffile

    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import emit_volume
    from holo.qualification.color_synthetic import render_color_scan

    outdir = _guard_outdir(outdir)
    spec = resolve_format_ref(COLOR_FORMAT_REF)
    payload = det_bytes(COLOR_PAYLOAD_TAG, COLOR_PAYLOAD_BYTES)
    emit_dir = outdir / COLOR_EMIT_DIRNAME
    if emit_dir.is_dir():
        shutil.rmtree(emit_dir)
    emit_volume(spec, payload, COLOR_SOURCE_FRACTION, emit_dir)
    ground_truth = np.load(emit_dir / "page000_gt.npy")
    planes = np.unpackbits(ground_truth, axis=-1)
    dots_h = spec.layout.cells_yx[0] * spec.cell_dots
    dots_w = spec.layout.cells_yx[1] * spec.cell_dots
    coverage = planes[:, :dots_h, :dots_w].astype(np.float64)
    border = COLOR_BORDER_DOTS
    padded = np.zeros((3, dots_h + 2 * border, dots_w + 2 * border),
                      np.float64)
    padded[:, border:border + dots_h, border:border + dots_w] = coverage
    up = np.repeat(np.repeat(padded, UPSAMPLE, axis=1), UPSAMPLE, axis=2)
    rgb = render_color_scan(np.ascontiguousarray(up.transpose(1, 2, 0))).rgb
    image = np.round(np.clip(rgb * 255.0, 0, 255)).astype(np.uint8)
    tifffile.imwrite(outdir / COLOR_TIFF_NAME, image)
    (outdir / COLOR_PAYLOAD_NAME).write_bytes(payload)
    return outdir


def make_color_groups(outdir: Path) -> Path:
    import tifffile

    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import emit_volume

    outdir = _guard_outdir(outdir)
    spec = resolve_format_ref(GROUPS_FORMAT_REF)
    payload = det_bytes(GROUPS_PAYLOAD_TAG, GROUPS_PAYLOAD_BYTES)
    emit_dir = outdir / GROUPS_EMIT_DIRNAME
    if emit_dir.is_dir():
        shutil.rmtree(emit_dir)
    emit_volume(spec, payload, GROUPS_SOURCE_FRACTION, emit_dir)
    coverage = _page_coverage(emit_dir, spec)
    dead = coverage.copy()
    dead[GROUPS_DEAD_PLANE] = 0.0
    for name, page in ((GROUPS_TIFF_NAME, coverage),
                       (GROUPS_DEAD_Y_TIFF_NAME, dead)):
        tifffile.imwrite(outdir / name,
                         _render_coverage(page, COLOR_BORDER_DOTS))
    (outdir / GROUPS_PAYLOAD_NAME).write_bytes(payload)
    return outdir


def make_color_groups_pages(outdir: Path) -> Path:
    import tifffile

    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import emit_volume

    outdir = _guard_outdir(outdir)
    spec = resolve_format_ref(GROUPS_FORMAT_REF)
    payload = det_bytes(PAGES_PAYLOAD_TAG, PAGES_PAYLOAD_BYTES)
    emit_dir = outdir / PAGES_EMIT_DIRNAME
    if emit_dir.is_dir():
        shutil.rmtree(emit_dir)
    volume = emit_volume(spec, payload, GROUPS_SOURCE_FRACTION, emit_dir)
    if volume.plan.n_pages != PAGES_N:
        raise RuntimeError(f"the three-page lever planned "
                           f"{volume.plan.n_pages} pages, not {PAGES_N}")
    for page, name in enumerate(PAGES_TIFF_NAMES):
        coverage = _page_coverage(emit_dir, spec, page)
        tifffile.imwrite(outdir / name,
                         _render_coverage(coverage, COLOR_BORDER_DOTS))
    (outdir / PAGES_PAYLOAD_NAME).write_bytes(payload)
    return outdir


def capture_color_groups_pages(outdir: Path) -> tuple[SimCapture, ...]:
    outdir = Path(outdir)
    return tuple(
        SimCapture(
            name=f"color-groups-page{page}", format_ref=GROUPS_FORMAT_REF,
            dpi=DPI, rot_k=0, tiff=outdir / name,
            tiff_sha256=sha256_file(outdir / name),
            payload=outdir / PAGES_PAYLOAD_NAME,
            payload_sha256=PAGES_PAYLOAD_SHA256,
            payload_bytes=PAGES_PAYLOAD_BYTES,
            emit_dir=outdir / PAGES_EMIT_DIRNAME)
        for page, name in enumerate(PAGES_TIFF_NAMES))


def capture_color_groups(outdir: Path, dead_y: bool = False) -> SimCapture:
    outdir = Path(outdir)
    target = outdir / (GROUPS_DEAD_Y_TIFF_NAME if dead_y
                       else GROUPS_TIFF_NAME)
    return SimCapture(
        name="color-groups-dead-y" if dead_y else "color-groups",
        format_ref=GROUPS_FORMAT_REF, dpi=DPI, rot_k=0,
        tiff=target, tiff_sha256=sha256_file(target),
        payload=outdir / GROUPS_PAYLOAD_NAME,
        payload_sha256=GROUPS_PAYLOAD_SHA256,
        payload_bytes=GROUPS_PAYLOAD_BYTES,
        emit_dir=outdir / GROUPS_EMIT_DIRNAME)


#: None is the renderer's own default channel (identity mix, white
#: paper), which every stimulus here renders through; the cmy one
#: (`_h3_sims_cmy`) passes a measured mix.  `upsample` is pixels per
#: printed dot (2 at this module's 1200 dpi, 4 for a 2400-dpi page) and
#: `gain_px` the dot gain `gain_planes` lays on at that pixel scale.
def _render_coverage(coverage: np.ndarray, border: int,
                     parameters: ColorChannelParameters | None = None,
                     upsample: int = UPSAMPLE, gain_px: int = 0
                     ) -> np.ndarray:
    from holo.qualification.color_synthetic import (ColorChannelParameters,
                                                    render_color_scan)

    dots_h, dots_w = coverage.shape[1:]
    padded = np.zeros((3, dots_h + 2 * border, dots_w + 2 * border),
                      np.float64)
    padded[:, border:border + dots_h, border:border + dots_w] = coverage
    up = np.repeat(np.repeat(padded, upsample, axis=1), upsample, axis=2)
    if gain_px:
        up = gain_planes(up, gain_px)
    rgb = render_color_scan(
        np.ascontiguousarray(up.transpose(1, 2, 0)),
        ColorChannelParameters() if parameters is None else parameters).rgb
    return np.round(np.clip(rgb * 255.0, 0, 255)).astype(np.uint8)


def _page_coverage(emit_dir: Path, spec: object,
                   page: int = 0) -> np.ndarray:
    ground_truth = np.load(emit_dir / f"page{page:03d}_gt.npy")
    planes = np.unpackbits(ground_truth, axis=-1)
    dots_h = spec.layout.cells_yx[0] * spec.cell_dots
    dots_w = spec.layout.cells_yx[1] * spec.cell_dots
    return planes[:, :dots_h, :dots_w].astype(np.float64)


def plane_x_shift_dots(dots_h: int, amplitude_dots: float,
                       cycles: float) -> np.ndarray:
    """One plane's x displacement in WHOLE dots, per dot row.

    Whole dots on purpose: a fractional displacement would have to be
    interpolated, and interpolation blurs the plane as well as moving it
    — two changes at once, and the blur alone measurably moves this sim's
    yield.  Rounding a sinusoid keeps the stimulus a pure registration
    error: the dots are the same dots, printed in the wrong column.
    """
    rows = np.arange(dots_h, dtype=np.float64)
    return np.round(
        amplitude_dots * np.sin(2.0 * np.pi * cycles * rows / dots_h)
    ).astype(np.int64)


def plane_x_step_dots(dots_h: int, amplitude_dots: float,
                      cycles: float) -> np.ndarray:
    """One plane's x displacement as a mean-zero SQUARE wave, whole dots.

    Same amplitude and same period as `plane_x_shift_dots`, and sharp
    instead of smooth — the one variable that separates the standing
    plane field from a per-window local affine.  The field pools its
    evidence over a two-tile Gaussian (truncated at 3.5 sigma, so a
    seven-tile reach on a ten-tile page), which smears a step across
    most of the sheet; a window sitting inside a band sees a CONSTANT
    displacement, which is a thing six parameters can express exactly.

    Physically this is a plane whose registration jumps rather than
    drifts — a station handoff or a drum seam, against e033's measured
    sinusoid.  Whole dots for the same reason the sinusoid uses them:
    the dots are the same dots, printed in the wrong column, so the
    stimulus stays a pure registration error with no blur in it.
    """
    rows = np.arange(dots_h, dtype=np.float64)
    phase = np.mod(cycles * rows / float(dots_h), 1.0)
    return np.where(phase < 0.5,
                    round(amplitude_dots), -round(amplitude_dots)
                    ).astype(np.int64)


SHAPE_SINE: str = "sine"
SHAPE_STEP: str = "step"
DISPLACEMENT_SHAPES: dict[str, object] = {
    SHAPE_SINE: plane_x_shift_dots,
    SHAPE_STEP: plane_x_step_dots,
}


def shift_plane_x(coverage: np.ndarray, plane: int,
                  shift_dots: np.ndarray) -> np.ndarray:
    shifted = coverage.copy()
    width = coverage.shape[2]
    for value in np.unique(shift_dots):
        rows = np.flatnonzero(shift_dots == value)
        step = int(value)
        moved = np.zeros((rows.size, width), coverage.dtype)
        if step >= 0:
            moved[:, step:] = coverage[plane][rows, :width - step]
        else:
            moved[:, :step] = coverage[plane][rows, -step:]
        shifted[plane][rows] = moved
    return shifted


def gain_planes(coverage: np.ndarray, gain_px: int) -> np.ndarray:
    """Dot gain: each plane's ink grown by `gain_px` pixels, ONE binary
    dilation per plane (scipy's cross, so a corner rounds off).

    Pixels, not dots: the measured gain is a fraction of a dot per edge
    (+0.31-0.39 on e043 sheet 3), so it is laid on the upsampled
    coverage, and only on binary coverage -- a faded plane has no edge
    to grow.
    """
    from scipy import ndimage

    if not np.isin(coverage, (0.0, 1.0)).all():
        raise ValueError("dot gain grows binary coverage only")
    return np.stack([ndimage.binary_dilation(plane > 0.0,
                                             iterations=int(gain_px))
                     for plane in coverage]).astype(coverage.dtype)


def make_color_hard(outdir: Path) -> Path:
    """Emit the top-rung colour page: one emit, both captures.

    Everything the two captures differ by is applied AFTER the emit, so
    the displaced and in-register pages carry the same bytes, the same
    addresses and the same noise draw.
    """
    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import emit_volume

    outdir = _guard_outdir(outdir)
    spec = resolve_format_ref(HARD_FORMAT_REF)
    payload = det_bytes(HARD_PAYLOAD_TAG, HARD_PAYLOAD_BYTES)
    emit_dir = outdir / HARD_EMIT_DIRNAME
    if emit_dir.is_dir():
        shutil.rmtree(emit_dir)
    emit_volume(spec, payload, HARD_SOURCE_FRACTION, emit_dir)
    (outdir / HARD_PAYLOAD_NAME).write_bytes(payload)
    return outdir


#: The FAINT variant: one band of the page where the displaced plane
#: barely marks the paper at all.  A registration field built on
#: PHOTOMETRY reads a level against a level table and needs contrast to
#: see anything; a field built on CORRELATION normalizes it away.  This
#: is the dead-band regime of the AltaLink record (Y at r0700 is a
#: zero-margin plane) reproduced small enough to decode twice.
FAINT_TIFF_NAME = "sim-color-faint-1200dpi.tiff"
FAINT_BAND_ROWS = (0.30, 0.70)
FAINT_SCALE = 0.30


def faint_band_rows(dots_h: int) -> tuple[int, int]:
    return (int(round(FAINT_BAND_ROWS[0] * dots_h)),
            int(round(FAINT_BAND_ROWS[1] * dots_h)))


def fade_plane_band(coverage: np.ndarray, plane: int,
                    scale: float = FAINT_SCALE) -> np.ndarray:
    """Scale one plane's ink down over a band of dot rows."""
    faded = coverage.copy()
    low, high = faint_band_rows(coverage.shape[1])
    faded[plane, low:high] = coverage[plane, low:high] * float(scale)
    return faded


def render_hard_faint(outdir: Path, amplitude_dots: float = None,
                      noise_sd: float = None,
                      scale: float = FAINT_SCALE) -> Path:
    """The displaced page again, with the displaced plane faded in a band."""
    import tifffile

    from holo.format.resolve import resolve_format_ref

    outdir = _guard_outdir(outdir)
    amplitude = (SHIFTED_AMPLITUDE_DOTS if amplitude_dots is None
                 else amplitude_dots)
    noise = SHIFTED_NOISE_SD if noise_sd is None else noise_sd
    spec = resolve_format_ref(HARD_FORMAT_REF)
    coverage = _page_coverage(outdir / HARD_EMIT_DIRNAME, spec)
    shift_dots = plane_x_shift_dots(coverage.shape[1], amplitude,
                                    SHIFTED_CYCLES)
    degraded = fade_plane_band(
        shift_plane_x(coverage, SHIFTED_PLANE, shift_dots),
        SHIFTED_PLANE, scale)
    image = _render_coverage(degraded, COLOR_BORDER_DOTS)
    tifffile.imwrite(outdir / FAINT_TIFF_NAME,
                     _noisy(image, SHIFTED_SEED, noise))
    return outdir


def render_hard_pair(outdir: Path, amplitude_dots: float = None,
                     noise_sd: float = None,
                     shape: str = SHAPE_SINE) -> Path:
    import tifffile

    from holo.format.resolve import resolve_format_ref

    outdir = _guard_outdir(outdir)
    amplitude = (SHIFTED_AMPLITUDE_DOTS if amplitude_dots is None
                 else amplitude_dots)
    noise = SHIFTED_NOISE_SD if noise_sd is None else noise_sd
    spec = resolve_format_ref(HARD_FORMAT_REF)
    coverage = _page_coverage(outdir / HARD_EMIT_DIRNAME, spec)
    shift_dots = DISPLACEMENT_SHAPES[shape](coverage.shape[1], amplitude,
                                            SHIFTED_CYCLES)
    degraded = shift_plane_x(coverage, SHIFTED_PLANE, shift_dots)
    for name, page in ((CONTROL_TIFF_NAME, coverage),
                       (SHIFTED_TIFF_NAME, degraded)):
        image = _render_coverage(page, COLOR_BORDER_DOTS)
        tifffile.imwrite(outdir / name, _noisy(image, SHIFTED_SEED, noise))
    return outdir


# The pair at its own frozen amplitude, and one of its two rasters as a
# capture.  Both are `measure/h3_repricing.py`'s doors — it materialises
# `color-hard` through the same builder-and-digest contract the fixtures
# used, so a pristine tree and a working tree decode the same bytes.
def make_color_hard_pair(outdir: Path) -> Path:
    make_color_hard(outdir)
    return render_hard_pair(outdir)


def capture_color_hard(outdir: Path, tiff_name: str,
                       name: str) -> SimCapture:
    outdir = Path(outdir)
    target = outdir / tiff_name
    return SimCapture(
        name=name, format_ref=HARD_FORMAT_REF, dpi=DPI, rot_k=0,
        tiff=target, tiff_sha256=sha256_file(target),
        payload=outdir / HARD_PAYLOAD_NAME,
        payload_sha256=HARD_PAYLOAD_SHA256,
        payload_bytes=HARD_PAYLOAD_BYTES,
        emit_dir=outdir / HARD_EMIT_DIRNAME)


def _noisy(image: np.ndarray, seed: int, noise_sd: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noisy = image.astype(np.float32) + rng.normal(0.0, noise_sd,
                                                  image.shape)
    return np.round(np.clip(noisy, 0, 255)).astype(np.uint8)


Hole = tuple[int, int, int, int]


def _mixed_holes(px_per_dot: int, height_px: int,
                 hole_column: int, keep_left: bool) -> tuple[Hole, Hole]:
    cell_px = K_CELL_DOTS * px_per_dot
    border_px = K_BORDER_DOTS * px_per_dot
    tile_px = MIXED_TILE_CELLS * cell_px
    ty, tx = MIXED_UNION_TILE_YX
    y0 = border_px + ty * tile_px
    x0 = border_px + tx * tile_px
    erased_cells = MIXED_TILE_CELLS - MIXED_UNION_KEEP_CELLS
    if keep_left:
        strip = (y0, y0 + tile_px,
                 x0 + MIXED_UNION_KEEP_CELLS * cell_px, x0 + tile_px)
    else:
        strip = (y0, y0 + tile_px, x0, x0 + erased_cells * cell_px)
    column = (0, height_px, border_px + hole_column * tile_px,
              border_px + (hole_column + 1) * tile_px)
    return column, strip


def _mixed_capture(base: np.ndarray, holes: tuple[Hole, ...],
                   seed: int, noise_sd: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noisy = base.astype(np.float32) + rng.normal(0.0, noise_sd, base.shape)
    for y0, y1, x0, x1 in holes:
        noisy[y0:y1, x0:x1] = float(K_PAPER_LEVEL)
    return np.round(np.clip(noisy, 0, 255)).astype(np.uint8)


def make_k_mixed(k_tiff: Path, outdir: Path) -> Path:
    from fractions import Fraction

    import tifffile

    from holo.receiver.lib.decimate import AreaPixelTransform, area_decimate

    outdir = _guard_outdir(outdir)
    image = np.asarray(tifffile.imread(k_tiff))
    half = area_decimate(image, AreaPixelTransform(Fraction(2)))
    capture_a = _mixed_capture(
        image,
        _mixed_holes(UPSAMPLE, image.shape[0], MIXED_HOLE_A_TILE_COLUMN,
                     keep_left=True),
        MIXED_SEED_A, MIXED_NOISE_SD)
    capture_b = _mixed_capture(
        half,
        _mixed_holes(1, half.shape[0], MIXED_HOLE_B_TILE_COLUMN,
                     keep_left=False),
        MIXED_SEED_B, MIXED_NOISE_SD)
    tifffile.imwrite(outdir / MIXED_A_TIFF_NAME, capture_a)
    tifffile.imwrite(outdir / MIXED_B_TIFF_NAME, capture_b)
    return outdir


def capture_k_mixed(outdir: Path,
                    base: SimCapture) -> tuple[SimCapture, SimCapture]:
    outdir = Path(outdir)
    capture_a = SimCapture(
        name="k-mixed-a", format_ref=base.format_ref, dpi=DPI, rot_k=0,
        tiff=outdir / MIXED_A_TIFF_NAME, tiff_sha256=MIXED_A_TIFF_SHA256,
        payload=base.payload, payload_sha256=base.payload_sha256,
        payload_bytes=base.payload_bytes, emit_dir=None)
    capture_b = SimCapture(
        name="k-mixed-b", format_ref=base.format_ref, dpi=MIXED_DPI_B,
        rot_k=0, tiff=outdir / MIXED_B_TIFF_NAME,
        tiff_sha256=MIXED_B_TIFF_SHA256, payload=base.payload,
        payload_sha256=base.payload_sha256,
        payload_bytes=base.payload_bytes, emit_dir=None)
    return capture_a, capture_b


def verify(outdir: Path, expected: dict[str, str]) -> str | None:
    outdir = Path(outdir)
    for relative, digest in sorted(expected.items()):
        path = outdir / relative
        if not path.is_file():
            return f"missing artefact {relative}"
        actual = sha256_file(path)
        if actual != digest:
            return (f"{relative} sha256 {actual} != frozen {digest}")
    return None


def capture_k(outdir: Path) -> SimCapture:
    outdir = Path(outdir)
    return SimCapture(
        name="k", format_ref=K_FORMAT_REF, dpi=DPI, rot_k=0,
        tiff=outdir / K_TIFF_NAME, tiff_sha256=K_TIFF_SHA256,
        payload=outdir / K_PAYLOAD_NAME,
        payload_sha256=K_PAYLOAD_SHA256,
        payload_bytes=K_PAYLOAD_BYTES, emit_dir=None)


def capture_color(outdir: Path) -> SimCapture:
    outdir = Path(outdir)
    return SimCapture(
        name="color", format_ref=COLOR_FORMAT_REF, dpi=DPI, rot_k=0,
        tiff=outdir / COLOR_TIFF_NAME, tiff_sha256=COLOR_TIFF_SHA256,
        payload=outdir / COLOR_PAYLOAD_NAME,
        payload_sha256=COLOR_PAYLOAD_SHA256,
        payload_bytes=COLOR_PAYLOAD_BYTES,
        emit_dir=outdir / COLOR_EMIT_DIRNAME)


def rotated_capture(base: SimCapture, rot_k: int,
                    outdir: Path) -> SimCapture:
    import tifffile

    if rot_k not in (0, 1, 2, 3):
        raise ValueError(f"rot_k {rot_k} must be one of 0, 1, 2, 3")
    if base.rot_k != 0:
        raise ValueError("rotations are built from the rot0 base only")
    outdir = _guard_outdir(outdir)
    target = outdir / f"{base.name}-rot{rot_k}.tiff"
    if not target.is_file():
        image = tifffile.imread(base.tiff)
        turned = np.ascontiguousarray(np.rot90(image, rot_k, axes=(0, 1)))
        tifffile.imwrite(target, turned)
    return SimCapture(
        name=f"{base.name}-rot{rot_k}", format_ref=base.format_ref,
        dpi=base.dpi, rot_k=rot_k, tiff=target,
        tiff_sha256=sha256_file(target), payload=base.payload,
        payload_sha256=base.payload_sha256,
        payload_bytes=base.payload_bytes, emit_dir=base.emit_dir)


def load_emit_gt(capture: SimCapture) -> np.ndarray:
    if capture.emit_dir is None:
        raise ValueError(f"{capture.name} carries no emit ground truth")
    return np.load(capture.emit_dir / "page000_gt.npy")


# The PAGE-DOMAIN stimulus: one volume planned over three pages of which
# only 0 and 2 are ever presented, so the receiver has to open what it is
# shown and never allocate the page it is not.  Hoisted out of
# test_h3_page_domain.py 2026-09-05 (conftest.py wires its fixtures); the
# punched single-page variant of the same emit is the cold-rest stimulus.
PAGE_DOMAIN_BYTES = 12000
PAGE_DOMAIN_TAG = b"holo3-page-domain-3p"
PAGE_DOMAIN_PAGES = 3
PAGE_DOMAIN_PRESENTED = (0, 2)
PAGE_DOMAIN_BOUND = ("--max-pages", str(PAGE_DOMAIN_PAGES))
PAGE_DOMAIN_WORD_ERRORS = 24
PAGE_DOMAIN_PAYLOAD_NAME = "payload.bin"

# frozen 2026-09-05 from the first cached build; the emit and the render
# are deterministic, so a mismatch here is generator drift, never a
# receiver regression, and a deliberate change to either re-freezes them
EXPECTED_PAGE_DOMAIN: dict[str, str] = {
    PAGE_DOMAIN_PAYLOAD_NAME: (
        "8671ddae8f557ccd73bad9c1c8e0e10a8389149dc454a76cd0f0440c14e7134d"),
    "page0.tiff": (
        "2c8b055e01ae40c13482f4c1fb26652ac5c34bb9c470b0389354442ac992d46e"),
    "page2.tiff": (
        "5cf12f305e25322cebaf9e509bea752ec257d788b4f59e7f261e6acce3ec6f0f"),
}


def _page_domain_render(cells: np.ndarray, cell_dots: int) -> np.ndarray:
    from scipy import ndimage

    from holo.gen.compose import cells_to_dots

    dots = cells_to_dots(cells, cell_dots)
    border = K_BORDER_DOTS
    height, width = dots.shape
    canvas = np.full((height + 2 * border, width + 2 * border),
                     K_PAPER_LEVEL, np.uint8)
    canvas[border:border + height, border:border + width] = np.where(
        dots != 0, K_INK_LEVEL, K_PAPER_LEVEL)
    up = np.repeat(np.repeat(canvas, UPSAMPLE, axis=0),
                   UPSAMPLE, axis=1)
    blurred = ndimage.gaussian_filter(up.astype(np.float32),
                                      K_BLUR_SIGMA_PX)
    return np.round(np.clip(blurred, 0, 255)).astype(np.uint8)


def _punch_word_sites(cells: np.ndarray, family_seed: bytes) -> np.ndarray:
    from holo.receiver.format import pilots

    word = pilots.word_site_cells_yx(family_seed)[:PAGE_DOMAIN_WORD_ERRORS]
    tile = pilots.TILE_CELLS
    out = np.array(cells, copy=True)
    for ty in range(out.shape[0] // tile):
        for tx in range(out.shape[1] // tile):
            out[ty * tile + word[:, 0], tx * tile + word[:, 1]] ^= 1
    return out


def make_k_pages(outdir: Path, pages: tuple[int, ...] = PAGE_DOMAIN_PRESENTED,
                 *, punch_words: bool = False) -> Path:
    import tifffile

    from holo.core import fountain
    from holo.format.resolve import resolve_format_ref
    from holo.gen.compose import compose_page_cells
    from holo.gen.emit import METADATA_VERSION, source_packed_for
    from holo.gen.plan import plan_volume

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    spec = resolve_format_ref(K_FORMAT_REF)
    payload = det_bytes(PAGE_DOMAIN_TAG, PAGE_DOMAIN_BYTES)
    plan = plan_volume(spec, len(payload), K_SOURCE_FRACTION)
    if plan.n_pages != PAGE_DOMAIN_PAGES:
        raise RuntimeError(
            f"3-page probe planned {plan.n_pages} pages, not "
            f"{PAGE_DOMAIN_PAGES}")
    source = source_packed_for(payload, plan)
    tpp = spec.tiles_per_page
    code = fountain.VolumeCode(plan.k_total, plan.symbol_bits, spec.seed,
                               tiles_per_page=tpp)
    (outdir / PAGE_DOMAIN_PAYLOAD_NAME).write_bytes(payload)
    for page in pages:
        esis = np.arange(page * tpp, (page + 1) * tpp, dtype=np.int64)
        cells = compose_page_cells(
            spec, page, code.encode_symbols(source, esis),
            plan.k_total, version=METADATA_VERSION)
        if punch_words:
            cells = _punch_word_sites(cells, spec.family_seed)
        tifffile.imwrite(outdir / f"page{page}.tiff",
                         _page_domain_render(cells, spec.cell_dots))
    return outdir


def capture_k_pages(outdir: Path,
                    pages: tuple[int, ...] = PAGE_DOMAIN_PRESENTED,
                    ) -> tuple[SimCapture, ...]:
    outdir = Path(outdir)
    payload_path = outdir / PAGE_DOMAIN_PAYLOAD_NAME
    payload_sha = sha256_file(payload_path)
    captures = []
    for page in pages:
        tiff = outdir / f"page{page}.tiff"
        captures.append(SimCapture(
            name=f"k-page{page}", format_ref=K_FORMAT_REF,
            dpi=DPI, rot_k=0, tiff=tiff,
            tiff_sha256=sha256_file(tiff), payload=payload_path,
            payload_sha256=payload_sha,
            payload_bytes=PAGE_DOMAIN_BYTES, emit_dir=None))
    return tuple(captures)
