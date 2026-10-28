"""`emit-plane`: one greyscale capture per RGB capture, holding one plane.

WHAT IS EMITTED.  For every capture of a finished run dir, a single-band
uint8 TIFF the same shape as that capture's NATIVE raster, in which the
target plane's ink is DARK on bright paper — an ordinary grey scan of a
cyan-only page, as far as holo3 is concerned.  `intake.load_native`
squeezes a trailing axis of 1, `intake.derived_planes(1, family)` returns
`(("g", None),)` whatever the family, and `store.sampling_planes` hands
that single plane to the K samplers, so nothing about the ingest needs
patching.  `capture_id = sha256(file)`, so each emitted TIFF is a NEW
capture and the plane view runs its own survey and placement from
scratch — which is the point of the experiment.

HOW THE PLANE IS ISOLATED.  `holo3.lib.spectral` fits, per capture, the
first-order mixing model ``v = m0 + mC·C + mM·M + mY·Y`` over cells whose
three plane bits are known (format furniture plus the payload cells of
tiles certified in every stream — ordinary receiver knowledge, never an
oracle), and returns for each plane the minimum-variance linear
functional ``w`` with ``w·m_sibling = 0`` for BOTH siblings and
``w·m_plane = 1``.  That is exactly "the projection functional
annihilating M and Y".  The analyzer's `unmix.lane_mix` drives
`plane_k.fit_lane_mix` over a deterministic, seeded sample of fully
covered tiles (PLAN §6 deviation), and this module applies the resulting
``w`` to the whole native raster.

FILTERING COMMUTES (spectral.py's own docstring), so unmixing the raster
and then aperture-filtering it — which is what holo3's sampler will do —
equals unmixing the filtered means the fit saw.  The synthetic grey page
is therefore a faithful carrier of the same evidence.

THE PIXEL MAPPING, stated, and WHY IT IS NOT THE OBVIOUS ONE.  Sampled
values reach the fit as ``raw/255``
(`color_region_anchor.native_divisor`), so the unmixed score is
``s(px) = (rgb(px)/255 − m0) · w`` — nominally 0 at paper and 1 at one
layer of the target ink.  Nominally is not measured, so two anchors are:
`s` is evaluated at the furniture cells of the tiles the mixing fit used,
and `paper_anchor` / `ink_anchor` are the medians over the cells whose
reference state has the target plane off / on.  They fix the POLARITY and
prove the plane separates at all (`MIN_ANCHOR_SEPARATION`), and the
emitted levels they land on are reported.

They do NOT set the gain, and the first real capture said why.  The
anchors live in the sampler's APERTURE-FILTERED domain — a mean over
`APERTURE_CELLS × pitch` pixels — while the emission is per pixel, whose
spread is several times wider.  Mapping paper -> 200 and ink -> 60 off
the filtered anchors clipped 1.9% of sheet J's fragment scan at the dark
end (measured, 2026-09-03) — real signal lost to the byte.  So the gain
comes from a MEASURED per-pixel span instead: a strided pass over the
native raster takes the `SPAN_QUANTILES` of `s` over the SHEET population
(pixels no brighter than `paper_anchor − SHEET_MARGIN`, which drops the
platen and the lid), and the affine sends that span to
[`DARK_U8`, `BRIGHT_U8`] = [5, 250]:

    u8 = round(BRIGHT_U8 + (s − span_lo)/(span_hi − span_lo)
                           · (DARK_U8 − BRIGHT_U8)),  clipped to [0, 255]

Ink is DARK, which is the polarity `calibrate.window_scores`
(calibrate.py:255, ``(midpoint − means)/spread``) wants: its score grows
as pixel values DROP.  Absolute levels do not matter to holo3 — its
calibration standardises by median and MAD and then fits PAVA — so what
the mapping owes is monotonicity, polarity and dynamic range, and this
one spends the whole byte on the sheet.

CLIPPING is the one step in the chain that does not commute with
filtering, so both clip fractions and the exact 256-bin level histogram
go into the sidecar — and the two clips do NOT mean the same thing.  A
LOW clip is darker than the sheet span: real signal lost to the byte, and
the number to watch.  A HIGH clip is brighter than the sheet, which on a
platen scan is the lid and the bare glass around it; on sheet J's loose
fragments that is most of the raster and costs nothing.
`level_percentiles` reads p1/p50/p99 off the histogram, and
`fraction_inside_span` says how much of the raster landed inside the
sheet band at all.

The whole raster is processed in row blocks; nothing bigger than one
block is ever float.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from holo3.plugins import color_model, color_sites, intake
from holo3.format import tile_codec

from .. import frame as frame_mod
from .. import sample as sample_mod
from .. import unmix as unmix_mod
from ..types import CaptureFact, Lane, RunInputs
from .row import PLANE_OF

#: The emitted grey levels the measured sheet span is stretched onto.
BRIGHT_U8: float = 250.0
DARK_U8: float = 5.0

#: Quantiles of the per-pixel score that define the sheet's span.
SPAN_QUANTILES: tuple[float, float] = (0.0005, 0.9995)

#: How far brighter than `paper_anchor` a pixel may be and still count as
#: sheet rather than platen, in ink layers.
SHEET_MARGIN: float = 0.35

#: Every Nth raster row enters the span pass.
SPAN_ROW_STRIDE: int = 32

#: An unmixed score domain narrower than this (in ink layers) means the
#: fit did not separate ink from paper; refuse rather than emit noise.
MIN_ANCHOR_SEPARATION: float = 0.10

#: Row-block budget for the raster pass, in bytes of float64 work space.
BLOCK_BYTES: int = 64 << 20

#: How many tiles the page-scope mixing fit pools (`--unmix page`).  The
#: lane scope is `unmix.LANE_MIX_TILES` = 12.
PAGE_MIX_TILES: int = 96

UNMIX_SCOPES: tuple[str, ...] = ("lane", "page")


class EmitError(RuntimeError):
    """The plane cannot be emitted for this capture."""


@dataclass(frozen=True)
class PlaneEmission:
    """Everything the sidecar records about one emitted capture."""

    capture_id: str
    capture_sha12: str
    ordinal: int
    basename: str
    out_path: str
    out_sha256: str
    dpi: float
    shape_yx: tuple[int, int]
    stream_id: str
    plane_index: int
    source_ref: str
    unmix_scope: str
    mix_lane_id: tuple[str, int]
    mix_level_index: int
    mix_ppc: str
    mix_accepted: bool
    mix_reason: str
    mix_n_full_rows: int
    mix_tiles: tuple[tuple[int, int], ...]
    functional_w: tuple[float, float, float]
    paper_level_m0: tuple[float, float, float]
    score_offset: float
    paper_anchor: float
    ink_anchor: float
    n_paper_labels: int
    n_ink_labels: int
    span_bright_score: float
    span_dark_score: float
    span_pixels: int
    bright_u8: float
    dark_u8: float
    paper_level_u8: float
    ink_level_u8: float
    pixel_coefficients: tuple[float, float, float]
    pixel_constant: float
    clipped_low_fraction: float
    clipped_high_fraction: float
    level_percentiles_u8: tuple[int, ...]
    fraction_inside_span: float
    input_sha256: tuple[str, ...]

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------- the mix

def _native_level_index(capture: CaptureFact, pitch_in: Fraction) -> int:
    return len(intake.build_levels(
        capture.dpi, pitch_in, capture.shape_px)) - 1


def _mix_lane(inputs: RunInputs, capture_id: str) -> Lane:
    """The finest lane of this capture that carries placements.

    The mixing model's units are the raster's own (`raw/255`), and area
    decimation preserves means, so a fit made at a coarser level applies
    unchanged to the native raster.  The lane is recorded either way.
    """
    lanes = [lane for lane in inputs.lanes if lane.capture_id == capture_id]
    if not lanes:
        raise EmitError(
            f"capture {capture_id[:12]} has no placement in this run dir; "
            f"there is nothing to fit a mixing model on")
    return max(lanes, key=lambda lane: lane.level_index)


def _anchor_scores(inputs: RunInputs, lane: Lane, mix: Any,
                   tiles_yx: Sequence[tuple[int, int]], page: int,
                   plane_index: int) -> tuple[np.ndarray, np.ndarray]:
    """Unmixed scores at furniture cells, split by the plane's own bit."""
    functional = np.asarray(mix.projections, np.float64)[:, plane_index]
    offset = float(np.asarray(mix.m0, np.float64) @ functional)
    cell_dots = color_sites.cell_dots_of(inputs.row)
    paper: list[np.ndarray] = []
    ink: list[np.ndarray] = []
    for ty, tx in tiles_yx:
        footprint = frame_mod.tile_footprint(
            inputs.row, page, int(ty), int(tx), 0, geometry=inputs.geometry)
        lane_footprint = sample_mod.lane_footprint(lane, footprint)
        if lane_footprint is None or not np.any(lane_footprint.observed):
            continue
        try:
            crops = sample_mod.open_crops(lane, lane_footprint,
                                          bound_dots=0.0,
                                          cell_dots=cell_dots)
        except sample_mod.SampleError:
            continue
        read = sample_mod.read_rgb(crops, lane_footprint, arm="plane-anchor")
        if read.refusal is not None:
            continue
        states, kinds = color_model.reference_states(
            inputs.row, inputs.geometry, page, footprint.page_cells_yx)
        usable = (np.asarray(kinds, np.int8) >= 0) & lane_footprint.observed
        if not np.any(usable):
            continue
        bits = tile_codec.states_to_planes(
            np.asarray(states, np.int8)[usable])[:, plane_index]
        scores = (np.asarray(read.values_rgb, np.float64)[usable]
                  @ functional) - offset
        paper.append(scores[bits == 0])
        ink.append(scores[bits == 1])
    empty = np.zeros(0, np.float64)
    return (np.concatenate(paper) if paper else empty,
            np.concatenate(ink) if ink else empty)


# ------------------------------------------------------- the pixel map

def plane_functional(mix: Any, plane_index: int
                     ) -> tuple[np.ndarray, float]:
    """(w, w·m0) — the functional that annihilates the sibling planes."""
    functional = np.asarray(mix.projections, np.float64)[:, plane_index]
    return functional, float(np.asarray(mix.m0, np.float64) @ functional)


def pixel_affine(mix: Any, plane_index: int, bright_score: float,
                 dark_score: float, *, bright_u8: float = BRIGHT_U8,
                 dark_u8: float = DARK_U8,
                 ) -> tuple[np.ndarray, float, np.ndarray, float]:
    """(per-channel u8 coefficients, constant, functional w, its offset).

    Composes the two linear steps of the module docstring into one pass
    over the raster: the unmixing ``s = (rgb/255 − m0)·w`` and the affine
    that sends `bright_score` to `bright_u8` and `dark_score` (the inkier
    end, larger `s`) to `dark_u8`.
    """
    if not (dark_score - bright_score) > 0.0:
        raise EmitError(
            f"the inked end of the score span ({dark_score}) does not "
            f"exceed the bright end ({bright_score})")
    functional, score_offset = plane_functional(mix, plane_index)
    gain = (dark_u8 - bright_u8) / (dark_score - bright_score)
    intercept = bright_u8 - gain * bright_score
    coefficients = gain * functional / 255.0
    constant = intercept - gain * score_offset
    return coefficients, float(constant), functional, score_offset


def score_span(rasters: Sequence[np.ndarray], functional: np.ndarray,
               score_offset: float, paper_anchor: float, *,
               row_stride: int = SPAN_ROW_STRIDE,
               quantiles: tuple[float, float] = SPAN_QUANTILES,
               sheet_margin: float = SHEET_MARGIN,
               ) -> tuple[float, float, int]:
    """The per-pixel score span of the SHEET, from a strided pass.

    Pixels brighter than ``paper_anchor − sheet_margin`` are the platen
    and the lid, not the sheet, and are dropped before the quantiles —
    otherwise a bright lid sets the scale and the printed field is
    compressed into a handful of levels.  Returns
    (bright end, inked end, how many pixels were counted).
    """
    coefficients = np.asarray(functional, np.float64) / 255.0
    floor = float(paper_anchor) - float(sheet_margin)
    sampled: list[np.ndarray] = []
    height = int(rasters[0].shape[0])
    for y0 in range(0, height, max(1, int(row_stride))):
        row = np.asarray(rasters[0][y0], np.float64) * coefficients[0]
        row += np.asarray(rasters[1][y0], np.float64) * coefficients[1]
        row += np.asarray(rasters[2][y0], np.float64) * coefficients[2]
        row -= score_offset
        sampled.append(row[row >= floor])
    population = (np.concatenate(sampled) if sampled
                  else np.zeros(0, np.float64))
    if population.size < 1000:
        raise EmitError(
            f"only {population.size} sampled pixel(s) are at or below the "
            f"paper anchor; the plane's sheet population cannot be found")
    low, high = np.quantile(population, quantiles)
    return float(low), float(high), int(population.size)


# ---------------------------------------------------------- the raster

def _write_plane_raster(rasters: Sequence[np.ndarray],
                        coefficients: np.ndarray, constant: float,
                        ) -> tuple[np.ndarray, float, float, np.ndarray]:
    """Apply the affine map in row blocks.

    Returns the u8 page, the low and high clip fractions, and the exact
    256-bin histogram of the emitted levels.

    THE TWO CLIPS MEAN DIFFERENT THINGS.  A LOW clip is darker than one
    layer of the plane's ink by more than the headroom — real signal lost
    to the byte.  A HIGH clip is brighter than paper by more than the
    headroom, which on a platen scan is mostly the lid and the bare glass
    around the sheet: harmless, and on a scan of loose fragments it is
    most of the raster.  Read the histogram beside them.
    """
    height, width = int(rasters[0].shape[0]), int(rasters[0].shape[1])
    out = np.empty((height, width), np.uint8)
    rows = max(1, int(BLOCK_BYTES // max(1, width * 8 * 4)))
    histogram = np.zeros(256, np.int64)
    low = high = 0
    for y0 in range(0, height, rows):
        y1 = min(height, y0 + rows)
        block = np.asarray(rasters[0][y0:y1], np.float64) * coefficients[0]
        block += np.asarray(rasters[1][y0:y1], np.float64) * coefficients[1]
        block += np.asarray(rasters[2][y0:y1], np.float64) * coefficients[2]
        block += constant
        np.rint(block, out=block)
        low += int(np.count_nonzero(block < 0.0))
        high += int(np.count_nonzero(block > 255.0))
        np.clip(block, 0.0, 255.0, out=block)
        levels = block.astype(np.uint8)
        histogram += np.bincount(levels.ravel(), minlength=256)
        out[y0:y1] = levels
    total = float(height) * float(width)
    return out, low / total, high / total, histogram


def level_percentiles(histogram: np.ndarray,
                      fractions: Sequence[float] = (0.01, 0.5, 0.99),
                      ) -> tuple[int, ...]:
    """Exact percentiles of an emitted page, from its 256-bin histogram."""
    counts = np.asarray(histogram, np.int64)
    total = int(counts.sum())
    if total == 0:
        return tuple(0 for _ in fractions)
    cumulative = np.cumsum(counts)
    return tuple(int(np.searchsorted(cumulative, max(1, int(f * total))))
                 for f in fractions)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ------------------------------------------------------------- the door

def emit_capture(inputs: RunInputs, capture: CaptureFact, out_dir: Path, *,
                 stream_id: str = "C", page: int = 0,
                 unmix_scope: str = "lane",
                 basename: str | None = None) -> PlaneEmission:
    """Fit, apply, write the TIFF and its sidecar for one capture."""
    if unmix_scope not in UNMIX_SCOPES:
        raise EmitError(f"unmix scope {unmix_scope!r} not in {UNMIX_SCOPES}")
    plane_index = PLANE_OF[stream_id]
    lane = _mix_lane(inputs, capture.capture_id)
    n_tiles = (unmix_mod.LANE_MIX_TILES if unmix_scope == "lane"
               else PAGE_MIX_TILES)
    mix, detail = unmix_mod.lane_mix(
        inputs, lane, inputs.certificates, stream_id, page=page,
        n_tiles=n_tiles)
    if not mix.accepted:
        raise EmitError(
            f"capture {capture.sha12}: the mixing fit refused "
            f"({mix.reason}, {mix.n_full_rows} full rows) — no functional "
            f"annihilates the sibling planes here")
    tiles_used = tuple(detail["lane_mix_tiles"])
    paper_scores, ink_scores = _anchor_scores(
        inputs, lane, mix, tiles_used, page, plane_index)
    if paper_scores.size < 25 or ink_scores.size < 25:
        raise EmitError(
            f"capture {capture.sha12}: only {paper_scores.size} paper and "
            f"{ink_scores.size} ink labels among the fitted tiles' "
            f"furniture; the anchors would be noise")
    paper_anchor = float(np.median(paper_scores))
    ink_anchor = float(np.median(ink_scores))
    if ink_anchor - paper_anchor < MIN_ANCHOR_SEPARATION:
        raise EmitError(
            f"capture {capture.sha12}: unmixed ink anchor {ink_anchor:.4f} "
            f"is not above paper {paper_anchor:.4f} by "
            f"{MIN_ANCHOR_SEPARATION}; plane {stream_id} does not separate "
            f"in this capture")

    level_index = _native_level_index(capture, inputs.pitch_in)
    plane_dir = Path(inputs.run_dir) / capture.sha12
    rasters = []
    input_shas = []
    for name in ("r", "g", "b"):
        path = intake.plane_path(plane_dir, level_index, name)
        if not path.exists():
            raise EmitError(f"native raster {path} is absent")
        rasters.append(np.load(path, mmap_mode="r"))
        input_shas.append(_sha256_file(path))
    functional, score_offset = plane_functional(mix, plane_index)
    span_low, span_high, span_pixels = score_span(
        rasters, functional, score_offset, paper_anchor)
    coefficients, constant, functional, score_offset = pixel_affine(
        mix, plane_index, span_low, span_high)
    gain_check = (DARK_U8 - BRIGHT_U8) / (span_high - span_low)
    offset_check = BRIGHT_U8 - gain_check * span_low
    plane, clipped_low, clipped_high, histogram = _write_plane_raster(
        rasters, coefficients, constant)
    inside = float(histogram[int(DARK_U8):int(BRIGHT_U8) + 1].sum()
                   / max(1, int(histogram.sum())))
    percentiles = level_percentiles(histogram)

    import tifffile

    name = basename or capture.sha12
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}-plane-{stream_id}.tiff"
    tifffile.imwrite(out_path, plane)
    emission = PlaneEmission(
        capture_id=capture.capture_id,
        capture_sha12=capture.sha12,
        ordinal=int(capture.ordinal),
        basename=name,
        out_path=str(out_path),
        out_sha256=_sha256_file(out_path),
        dpi=float(capture.dpi),
        shape_yx=(int(plane.shape[0]), int(plane.shape[1])),
        stream_id=stream_id,
        plane_index=plane_index,
        source_ref=str(inputs.format_ref),
        unmix_scope=unmix_scope,
        mix_lane_id=(lane.capture_id, int(lane.level_index)),
        mix_level_index=int(lane.level_index),
        mix_ppc=str(lane.ppc),
        mix_accepted=bool(mix.accepted),
        mix_reason=str(mix.reason),
        mix_n_full_rows=int(mix.n_full_rows),
        mix_tiles=tiles_used,
        functional_w=tuple(float(value) for value in functional),
        paper_level_m0=tuple(float(value) for value in np.asarray(mix.m0)),
        score_offset=score_offset,
        paper_anchor=paper_anchor,
        ink_anchor=ink_anchor,
        n_paper_labels=int(paper_scores.size),
        n_ink_labels=int(ink_scores.size),
        span_bright_score=span_low,
        span_dark_score=span_high,
        span_pixels=span_pixels,
        bright_u8=BRIGHT_U8,
        dark_u8=DARK_U8,
        paper_level_u8=float(paper_anchor * gain_check + offset_check),
        ink_level_u8=float(ink_anchor * gain_check + offset_check),
        pixel_coefficients=tuple(float(v) for v in coefficients),
        pixel_constant=float(constant),
        clipped_low_fraction=float(clipped_low),
        clipped_high_fraction=float(clipped_high),
        level_percentiles_u8=percentiles,
        fraction_inside_span=inside,
        input_sha256=tuple(input_shas),
    )
    (out_dir / f"{name}-plane-{stream_id}.json").write_text(
        json.dumps(emission.as_json(), indent=2, sort_keys=True), "utf-8")
    return emission


def capture_basenames(run_dir: Path,
                      captures: Sequence[CaptureFact]) -> dict[str, str]:
    """The original TIFF basename per capture, from the run dir's argv."""
    from .. import mirror as mirror_mod

    argv_path = Path(run_dir) / "argv"
    names: dict[str, str] = {}
    if not argv_path.exists():
        return names
    try:
        scans, _dpis = mirror_mod.parse_decode_argv(
            argv_path.read_text("utf-8"))
    except mirror_mod.MirrorError:
        return names
    for capture in captures:
        if capture.ordinal < len(scans):
            names[capture.capture_id] = Path(scans[capture.ordinal]).stem
    return names


def emit_run(inputs: RunInputs, out_dir: Path, *, stream_id: str = "C",
             page: int = 0, unmix_scope: str = "lane",
             ) -> tuple[PlaneEmission, ...]:
    """One emitted capture per capture of the run dir, in ordinal order."""
    names = capture_basenames(Path(inputs.run_dir), inputs.captures)
    out: list[PlaneEmission] = []
    for capture in sorted(inputs.captures, key=lambda item: item.ordinal):
        out.append(emit_capture(
            inputs, capture, out_dir, stream_id=stream_id, page=page,
            unmix_scope=unmix_scope,
            basename=names.get(capture.capture_id)))
    return tuple(out)
