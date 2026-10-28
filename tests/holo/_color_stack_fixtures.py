"""Deterministic synthetic color fixtures for the PK2 stack refactor.

Four small single-region fixtures — ``{cmy7, cmy8} x {clean, residual}`` —
rendered through the qualification forward model
(:mod:`holo.qualification.color_synthetic`), each carrying nine E022
windows over a 3x3 tile field on one page.  They exist so the PK2
refactor (KnownField carrier + sampling split + region stack) can be
proved BYTE-IDENTICAL: the same fixtures were run through
``collect_color_evidence`` before the refactor and compared value-for-value
after it.

The ``residual`` variants displace the M and Y planes by ~0.6 print dots
on a softer, noisier render, which is what makes the region registration
arm a real choice rather than a formality: MEASURED 2026-08-07, the clean
channel REFUSES that arm (its baseline detector already separates every
class perfectly) and the residual channel ADOPTS it, so the fixture set
covers both verdicts of the held-out gate.  Certificates are deliberately
absent — the prior-certified overlay is exercised at scale by the
campaign's committed-pose replays, and its adversarial set belongs to
PK7.

Everything here is seeded (``render_color_scan`` takes its own seed; the
tile payload symbols come from an explicit ``default_rng``), so a fixture
is a pure function of its key.  Nothing in this module imports the
receiver modules under refactor beyond the public collection entry point's
own inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from holo.core import channel
from holo.format.descriptor import FormatSpec
from holo.format.registry import get_format_row
from holo.gen.color_compose import compose_color_tile
from holo.qualification.color_synthetic import (
    ColorChannelParameters,
    PlaneParameters,
    render_color_scan,
)
from holo.receive.payload_model import EvidenceSource
from holo.receive.placement.model import (
    AddressResult,
    AffinePose,
    CandidateScore,
    PlacedPatch,
    PlacedSegment,
    PoseSegment,
    PoseWindow,
)
from holo.receive.scan import open_capture


# Two scanner pixels per print dot: the footing the production color gate
# closes at (test_backbone_payload_gates), and enough sampling for the
# aperture filter to mean something.
PX_PER_DOT = 2
TILES_YX = (3, 3)
# The renderer's own default subtractive mix (cyan subtracts red, magenta
# green, yellow blue).  Named here so PK5's cross-plane channel can move
# ONE coefficient and leave everything else the bit-exact render every
# earlier fixture got — pinned in ``test_color_context``.
IDENTITY_MIX: tuple[tuple[float, float, float], ...] = (
    (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
# Two channels, chosen so BOTH arms of the region choice are exercised
# (measured 2026-08-07): the clean channel's baseline detector already
# separates every class, so the registration arm is REFUSED and the
# non-adopted path must pass the base features through unchanged (R3);
# the residual channel misregisters M and Y by ~0.6 print dots on top of
# a softer, noisier render, so the registration arm is ADOPTED.
_CLEAN = ((0.0, 0.0), (0.0, 0.0), (0.0, 0.0))
_RESIDUAL_OFFSETS_XY = ((0.0, 0.0), (1.4, -1.0), (-1.2, 1.2))
_CLEAN_BLUR_SIGMA = 0.5
_CLEAN_NOISE_STD = 0.004
_RESIDUAL_BLUR_SIGMA = 1.0
_RESIDUAL_NOISE_STD = 0.02

FIXTURE_ROWS: dict[str, tuple[str, bool]] = {
    "cmy7-clean": ("c3-cmy7-p120-v0@2240x1536", False),
    "cmy7-residual": ("c3-cmy7-p120-v0@2240x1536", True),
    "cmy8-clean": ("c3-cmy8-p120-v0@2240x1536", False),
    "cmy8-residual": ("c3-cmy8-p120-v0@2240x1536", True),
}
FIXTURE_KEYS = tuple(FIXTURE_ROWS)

# PK3 (P1) needs a LARGER field than the four PK2 fixtures: the cmy7
# head's floors are per-STATE (>=10 cal-search labels, >=3 cal-validation),
# and a 3x3-tile region carries only 14-21 held-out examples of the rarer
# dust states — measured, it refuses `search_class_starved` every time.
# Eight tiles square puts every state comfortably over both floors while
# staying a synthetic second-scale render.
HEAD_TILES_YX = (8, 8)
CMY7_ROW = "c3-cmy7-p120-v0@2240x1536"


@dataclass(frozen=True, slots=True)
class ColorFixture:
    """One rendered capture with its E022 address product."""

    key: str
    row_id: str
    residual: bool
    spec: FormatSpec
    field: np.ndarray
    raster: object
    address: AddressResult
    source: EvidenceSource
    pitch_px: float


def _tile_field(spec: FormatSpec, tiles_yx: tuple[int, int]) -> np.ndarray:
    """Canonical color states for a ``tiles_yx`` field of composed tiles."""
    rng = np.random.default_rng(0xC0102)
    height, width = tiles_yx[0] * 64, tiles_yx[1] * 64
    field = np.empty((height, width), np.uint8)
    for ty in range(tiles_yx[0]):
        for tx in range(tiles_yx[1]):
            counter = spec.tile_counter(0, ty, tx)
            symbols = {
                stream.stream_id: rng.integers(
                    0, 2, stream.symbol_bits, dtype=np.uint8)
                for stream in spec.stream_profiles
            }
            field[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64] = (
                compose_color_tile(spec, counter, symbols, 1))
    return field


def _mottle(shape: tuple[int, int], amplitude: float, period_px: float,
            seed: int) -> np.ndarray:
    """A smooth seeded multiplicative gain field, one plane per RGB channel.

    The e030 HP channel shows cm-scale C/M mottle plus process banding —
    the measured reason a PAGE-GLOBAL QDA is overconfident out of sample
    (COLOR-UPLIFT-PLAN §1).  A stationary synthetic render cannot exhibit
    that pathology at all: train and held-out rows are i.i.d., so the
    detector's confidence is honest and P1's head correctly refuses.  This
    is the smallest addition that reproduces the real mechanism — a few
    low-frequency sinusoids with seeded phases, so the field is a pure
    function of ``seed`` with no filtering and no unseeded draw.
    """
    rng = np.random.default_rng(seed)
    rows = np.arange(shape[0], dtype=np.float64)[:, None]
    columns = np.arange(shape[1], dtype=np.float64)[None, :]
    stack = np.empty((*shape, 3), np.float64)
    for channel_index in range(3):
        accumulated = np.zeros(shape, np.float64)
        for _harmonic in range(3):
            fy, fx = rng.uniform(0.5, 1.6, 2)
            phase_y, phase_x = rng.uniform(0.0, 2.0 * np.pi, 2)
            accumulated += (
                np.sin(2.0 * np.pi * fy * rows / period_px + phase_y)
                * np.sin(2.0 * np.pi * fx * columns / period_px + phase_x))
        stack[:, :, channel_index] = 1.0 + amplitude * accumulated / 3.0
    return stack


def _render_with(
    field: np.ndarray,
    pitch_px: int,
    offsets: tuple[tuple[float, float], ...],
    blur: float,
    noise: float,
    seed: int = 0x5EED,
    mottle_amplitude: float = 0.0,
    mottle_period_px: float = 512.0,
    outlier_fraction: float = 0.0,
    outlier_scale: float = 0.0,
    gain_gradient: tuple[tuple[float, float], ...] = (
        (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)),
    gain_scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    contrast: float = 1.0,
    paper: float = 1.0,
    subtractive_rgb: tuple[tuple[float, float, float], ...] = IDENTITY_MIX,
) -> np.ndarray:
    """Render one deterministic RGB scan of a solid-cell color field."""
    planes = channel.states_to_planes(field).astype(np.float64)
    coverage = np.repeat(
        np.repeat(planes, pitch_px, axis=0), pitch_px, axis=1)
    parameters = ColorChannelParameters(
        planes=tuple(
            PlaneParameters(
                offset_xy=offset, blur_sigma=blur, contrast=contrast)
            for offset in offsets
        ),  # type: ignore[arg-type]
        subtractive_rgb=subtractive_rgb,
        paper_rgb=(paper,) * 3,
        noise_std_rgb=(noise,) * 3,
        seed=seed,
        gain_gradient=gain_gradient,
        gain_scale_rgb=gain_scale,
    )
    scan = render_color_scan(coverage, parameters)
    rgb = np.asarray(scan.rgb, np.float64)
    if outlier_fraction:
        rgb = rgb + _cell_outliers(
            rgb.shape[:2], pitch_px, outlier_fraction, outlier_scale,
            seed ^ 0x0111)
    if mottle_amplitude:
        rgb = rgb * _mottle(
            rgb.shape[:2], mottle_amplitude, mottle_period_px,
            seed ^ 0x0FF7)
    rgb = np.clip(rgb, 0.0, 1.0)
    return np.ascontiguousarray(np.round(rgb * 255.0).astype(np.uint8))


def _cell_outliers(shape: tuple[int, int], pitch_px: int, fraction: float,
                   scale: float, seed: int) -> np.ndarray:
    """A seeded heavy tail: whole CELLS displaced far off their class.

    This is the mechanism behind the measured cmy7 pathology.  A Gaussian
    QDA's log-likelihood falls QUADRATICALLY away from a class mean, so a
    cell knocked off its class by a void, a speck, or a registration slip
    does not merely land in the wrong class — it lands there with an
    enormous score.  That is exactly the corpus fact P1 exists to fix:
    19% of cells at the L-infinity bound with the WRONG cells at median
    |score| 18.8/20.  Gaussian pixel noise cannot produce it (it is what
    the QDA models), so a positive control for the head needs this.

    The perturbation is applied to the SCAN, never to the printed
    coverage: the ground-truth field stays the truth, and the detector is
    simply wrong about those cells.
    """
    rng = np.random.default_rng(seed)
    cells = tuple(-(-length // pitch_px) for length in shape)
    hit = rng.random(cells) < fraction
    delta = rng.normal(0.0, scale, (*cells, 3)) * hit[..., None]
    spread = np.repeat(np.repeat(delta, pitch_px, axis=0), pitch_px, axis=1)
    return spread[:shape[0], :shape[1]]


def _render(field: np.ndarray, pitch_px: int, residual: bool) -> np.ndarray:
    return _render_with(
        field, pitch_px,
        _RESIDUAL_OFFSETS_XY if residual else _CLEAN,
        _RESIDUAL_BLUR_SIGMA if residual else _CLEAN_BLUR_SIGMA,
        _RESIDUAL_NOISE_STD if residual else _CLEAN_NOISE_STD,
    )


def _candidate(page: int) -> CandidateScore:
    return CandidateScore(
        page, (0, 0), 0, 0.0, 0.0, 0, 0, 1000, 1000, 20.0, True,
        "color-stack-fixture")


def _grid(shape: tuple[int, int]) -> np.ndarray:
    yy, xx = np.meshgrid(
        np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    return np.stack((yy, xx), axis=-1).reshape(-1, 2).astype(np.int32)


def _patch(
    patch_id: int,
    origin_yx_cells: tuple[int, int],
    pitch_px: float,
) -> PlacedPatch:
    """One 64x64-cell window placed at an exact tile origin."""
    local = _grid((64, 64))
    pose = AffinePose(
        (origin_yx_cells[0] * pitch_px + (pitch_px - 1.0) / 2.0,
         origin_yx_cells[1] * pitch_px + (pitch_px - 1.0) / 2.0),
        ((pitch_px, 0.0), (0.0, pitch_px)),
        (0.5, 0.5),
        pitch_px,
        0.0,
    )
    segment = PoseSegment(
        PoseWindow(patch_id, 0, origin_yx_cells, (64, 64)),
        pose, local.shape[0], 1.0, (pitch_px, pitch_px), 0.0)
    placed = PlacedSegment(segment, origin_yx_cells, 0, local)
    page_cells = local.astype(np.int64) + np.asarray(
        origin_yx_cells, np.int64)
    return PlacedPatch(
        patch_id, 0, 0, "color-stack-fixture", _candidate(0), (),
        placed, (), False, page_cells.astype(np.int32))


@lru_cache(maxsize=None)
def build_fixture(key: str) -> ColorFixture:
    """Build (and memoize) one named fixture."""
    row_id, residual = FIXTURE_ROWS[key]
    spec = get_format_row(row_id)
    pitch_px = PX_PER_DOT * spec.cell_dots
    field = _tile_field(spec, TILES_YX)
    raster = open_capture(_render(field, pitch_px, residual), 600.0 * PX_PER_DOT)
    patches = tuple(
        _patch(ty * TILES_YX[1] + tx, (ty * 64, tx * 64), float(pitch_px))
        for ty in range(TILES_YX[0])
        for tx in range(TILES_YX[1])
    )
    address = AddressResult(
        patches, (), (), ((0, "placed"),), len(patches))
    source = EvidenceSource(raster.source.sha256, "ppc-2")
    return ColorFixture(
        key=key,
        row_id=row_id,
        residual=residual,
        spec=spec,
        field=field,
        raster=raster,
        address=address,
        source=source,
        pitch_px=float(pitch_px),
    )


@lru_cache(maxsize=None)
def build_head_fixture(
    blur_sigma: float,
    noise_std: float,
    mottle_amplitude: float = 0.0,
    outlier_fraction: float = 0.0,
    outlier_scale: float = 0.0,
    tiles_yx: tuple[int, int] = HEAD_TILES_YX,
    row_id: str = CMY7_ROW,
    seed: int = 0x5EED,
) -> ColorFixture:
    """A cmy7 field big enough for P1's per-state floors, at a chosen SNR.

    Same forward model and same placement construction as the four PK2
    fixtures — only the field size and the channel severity are open, so
    a P1 test can ask for a channel the QDA is confidently wrong on
    without inventing a second rendering path.  Deterministic and cached:
    a fixture is a pure function of its arguments.
    """
    spec = get_format_row(row_id)
    pitch_px = PX_PER_DOT * spec.cell_dots
    field = _tile_field(spec, tiles_yx)
    raster = open_capture(
        _render_with(field, pitch_px, _CLEAN, blur_sigma, noise_std, seed,
                     mottle_amplitude, outlier_fraction=outlier_fraction,
                     outlier_scale=outlier_scale),
        600.0 * PX_PER_DOT)
    patches = tuple(
        _patch(ty * tiles_yx[1] + tx, (ty * 64, tx * 64), float(pitch_px))
        for ty in range(tiles_yx[0])
        for tx in range(tiles_yx[1])
    )
    return ColorFixture(
        key=f"cmy7-head-b{blur_sigma:g}-n{noise_std:g}-m{mottle_amplitude:g}"
            f"-o{outlier_fraction:g}x{outlier_scale:g}"
            f"-{tiles_yx[0]}x{tiles_yx[1]}",
        row_id=row_id,
        residual=False,
        spec=spec,
        field=field,
        raster=raster,
        address=AddressResult(patches, (), (), ((0, "placed"),), len(patches)),
        source=EvidenceSource(raster.source.sha256, "ppc-2"),
        pitch_px=float(pitch_px),
    )


NO_GAIN_GRADIENT: tuple[tuple[float, float], ...] = (
    (0.0, 0.0), (0.0, 0.0), (0.0, 0.0))
UNIT_GAIN_SCALE: tuple[float, float, float] = (1.0, 1.0, 1.0)
# PK4's faint-print tone: paper at 0.8 and ink absorbing 0.4, so white and
# a one-plane state sit 0.4 apart instead of a full unit.  A ±G gain ramp
# then makes the two classes overlap page-wide once G > a/(2p-a) = 1/3 —
# the algebra that turns "a gain gradient exists" into "a page-global
# model cannot separate these classes".
LOCALITY_PAPER = 0.8
LOCALITY_CONTRAST = 0.4


@lru_cache(maxsize=None)
def build_locality_fixture(
    blur_sigma: float,
    noise_std: float,
    gain_gradient: tuple[tuple[float, float], ...] = NO_GAIN_GRADIENT,
    gain_scale: tuple[float, float, float] = UNIT_GAIN_SCALE,
    tiles_yx: tuple[int, int] = HEAD_TILES_YX,
    row_id: str = CMY7_ROW,
    seed: int = 0x5EED,
    contrast: float = LOCALITY_CONTRAST,
    paper: float = LOCALITY_PAPER,
) -> ColorFixture:
    """PK4's cross-pathology pair: same channel, gain gradient on or off.

    A3's law is "treatments engage only where their disease exists", and a
    single fixture cannot state it — a channel that adopts proves the arm
    works, a channel that refuses proves it is not merely always-on.  So
    this builder takes the gradient as its ONE open variable: the same
    blur, the same noise, the same seeded field, the same faint-print
    tone, with and without a spatially varying gain.  ``gain_gradient``
    all zeros renders through the identical code path as every pre-PK4
    fixture (bit-exact, pinned in ``test_color_locality``).

    The tone is deliberately FAINT (:data:`LOCALITY_PAPER` /
    :data:`LOCALITY_CONTRAST`).  At the full-contrast tone of the other
    fixtures the seven classes sit a whole unit apart and a page-global
    QDA separates them through any gain a valid gradient can apply, so no
    photometric arm — right or wrong — could ever earn its gate.  Faint
    ink is what makes a cross-window gain drift comparable to the class
    spacing, which is exactly the measured HP regime this arm exists for
    (COLOR-UPLIFT-PLAN §1) and the only regime in which the question
    "does per-window photometry help?" has an answer at all.
    """
    spec = get_format_row(row_id)
    pitch_px = PX_PER_DOT * spec.cell_dots
    field = _tile_field(spec, tiles_yx)
    raster = open_capture(
        _render_with(field, pitch_px, _CLEAN, blur_sigma, noise_std, seed,
                     gain_gradient=gain_gradient, gain_scale=gain_scale,
                     contrast=contrast, paper=paper),
        600.0 * PX_PER_DOT)
    patches = tuple(
        _patch(ty * tiles_yx[1] + tx, (ty * 64, tx * 64), float(pitch_px))
        for ty in range(tiles_yx[0])
        for tx in range(tiles_yx[1])
    )
    gradient = "-".join(f"{gy:g}x{gx:g}" for gy, gx in gain_gradient)
    scale = "-".join(f"{value:g}" for value in gain_scale)
    return ColorFixture(
        key=f"locality-b{blur_sigma:g}-n{noise_std:g}-g{gradient}"
            f"-s{scale}-{tiles_yx[0]}x{tiles_yx[1]}",
        row_id=row_id,
        residual=False,
        spec=spec,
        field=field,
        raster=raster,
        address=AddressResult(patches, (), (), ((0, "placed"),), len(patches)),
        source=EvidenceSource(raster.source.sha256, "ppc-2"),
        pitch_px=float(pitch_px),
    )


@lru_cache(maxsize=None)
def build_context_fixture(
    blur_sigma: float,
    noise_std: float,
    subtractive_rgb: tuple[tuple[float, float, float], ...] = IDENTITY_MIX,
    tiles_yx: tuple[int, int] = HEAD_TILES_YX,
    row_id: str = CMY7_ROW,
    seed: int = 0x5EED,
) -> ColorFixture:
    """PK5's cross-pathology pair: neighbour bleed on or off (A5).

    A5's disease is NEIGHBOUR-DEPENDENT bias — a cell's reading carrying
    its neighbours' ink — and the qualification renderer already produces
    exactly that, per plane, with no extension at all: ``blur_sigma`` IS
    the print/scan spread.  At the other fixtures' 0.5 px against a 6 px
    cell the spread stays inside the cell and the arm has nothing to
    correct; at 3.0 px a cell's own aperture mean carries a measurable
    fraction of each inked neighbour, which is the corpus mechanism in
    its simplest identifiable form.

    ``subtractive_rgb`` is the ONE open second variable, and it is what
    separates the two VARIANTS rather than the two channels: off the
    diagonal, plane C's bleed lands in the channel plane M is read from,
    so the correct correction to an M-bearing state depends on the CYAN
    neighbour count — a term the per-plane form cannot write down and the
    multi-state matrix can.  The default is the renderer's own identity
    mix, so an unset argument renders bit-for-bit what
    :func:`build_head_fixture` renders (pinned).
    """
    spec = get_format_row(row_id)
    pitch_px = PX_PER_DOT * spec.cell_dots
    field = _tile_field(spec, tiles_yx)
    raster = open_capture(
        _render_with(field, pitch_px, _CLEAN, blur_sigma, noise_std, seed,
                     subtractive_rgb=subtractive_rgb),
        600.0 * PX_PER_DOT)
    patches = tuple(
        _patch(ty * tiles_yx[1] + tx, (ty * 64, tx * 64), float(pitch_px))
        for ty in range(tiles_yx[0])
        for tx in range(tiles_yx[1])
    )
    mix = "-".join(f"{value:g}" for row in subtractive_rgb for value in row)
    return ColorFixture(
        key=f"context-b{blur_sigma:g}-n{noise_std:g}-m{mix}"
            f"-{tiles_yx[0]}x{tiles_yx[1]}-{row_id}",
        row_id=row_id,
        residual=False,
        spec=spec,
        field=field,
        raster=raster,
        address=AddressResult(patches, (), (), ((0, "placed"),), len(patches)),
        source=EvidenceSource(raster.source.sha256, "ppc-2"),
        pitch_px=float(pitch_px),
    )


__all__ = [
    "CMY7_ROW", "FIXTURE_KEYS", "FIXTURE_ROWS", "HEAD_TILES_YX",
    "IDENTITY_MIX",
    "NO_GAIN_GRADIENT", "PX_PER_DOT", "TILES_YX", "UNIT_GAIN_SCALE",
    "ColorFixture", "build_context_fixture", "build_fixture",
    "build_head_fixture", "build_locality_fixture",
]
