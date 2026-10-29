"""What the pixels MEAN — the mixing model and the six unmixing modes of
DESIGN §4.6.

BLIND.  Nothing here may import :mod:`analyzer.truth` or
:mod:`analyzer.oracle`.

This is the half of DESIGN §4.6 that answers "how much of the target
plane's ink is at this cell"; `arms.py` is the half that answers "where
do I sample it".  They split here because the line cap said so and
because the seam is real: nothing below reads a pose, and nothing in
`arms.py`'s registration searches knows a channel from a plane.

REUSE (DESIGN §4.1), per function:

* `plane_k.fit_lane_mix` — CALLED, at BOTH scopes.  It wants a sequence
  of `WindowRead`s and touches exactly three attributes of each
  (`values`, `rows.known_component_bits`, `rows.known_component_mask`),
  so :func:`shim_read` presents a `KnownFrame` + `Read` under those names
  and the production function does the fit — footprint scope with one
  shim, lane scope with one per sampled tile.
* `plane_k.isolated_scores` — CALLED by :func:`isolated_scores`.  It
  cannot serve :func:`unmix_score` directly: it hard-codes `spectral`'s
  `subtract` mode and fuses the `window_scores` standardisation that
  DESIGN §4.7 gives to the calibration step.  A test asserts the two
  paths agree exactly on `subtract`.
* `spectral.fit_plane_mix` / `spectral.plane_score` — CALLED for
  `raw`, `project`, `subtract` and (on the lane mix) `global`.
* `color_region_head.fit_region_stack` — NOT called; see `head`.

THE `head` ARM IS THE ANALYZER'S OWN (declared deviation, PLAN §6).
`color_region_head.fit_region_stack` cannot be driven from a
footprint-sized structure: it needs an `OwnerSelection`, a tuple of
`WindowRows`, per-window feature stacks, emission masks and a
`StackConfig` — the region-scope pipeline — and it returns the production
row's evidence rather than one plane's score.  What DESIGN §4.6 actually
asks for, "the two-of-three relaxation: cells with two planes known enter
as regressors", is built here directly: a Gaussian classifier over the
eight printed states under the fitted mixing model, each cell's state
hypotheses RESTRICTED to those consistent with whatever planes that cell
already proves.  A cell proving two planes therefore contributes as a
two-hypothesis test instead of falling back to the projection.

THE LANE-SCOPE FIT IS SAMPLED, NOT EXHAUSTIVE (declared deviation,
PLAN §6).  DESIGN §4.6 says "the whole page's regressors"; a page is
1,961 footprints per lane and stream.  :func:`lane_mix` pools a
DETERMINISTIC, seeded sample of fully covered tiles instead, with the
target's own tile removed, and records which tiles it used.  The memo
key carries the excluded tile, so a target never sees a fit containing
its own certificates and two targets still share a fit whenever neither
is in the sample.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.special import logsumexp

from holo.receiver.format import tile_codec
from holo.receiver.lib import spectral
from holo.receiver.plugins import color_model, color_sites, plane_k

from . import calibrate as cal
from . import frame as frame_mod
from . import patch as patch_mod
from . import sample as sample_mod
from .types import (Key, KnownFrame, Lane, PLANE_OF, RunInputs,
                    TileFootprint)

TILE_CELLS = 64

#: The six modes of DESIGN §4.6 plus the patch family (W8 B1,
#: `analyzer.patch`), which needs a READ CONTEXT — the raw crop, the
#: posed read, the lane footprint, the folds and its spec — and refuses
#: without one.
UNMIX_MODES: tuple[str, ...] = (
    "raw", "project", "subtract", "global", "conditional", "head",
) + tuple(patch_mod.PATCH_MODES)

MIX_SCOPES: tuple[str, ...] = ("footprint", "lane")

#: How many tiles the lane-scope mixing fit pools (see the deviation
#: above).  12 tiles is ~1,500 payload-certified cells per plane, well
#: past `spectral.MIN_FULL_ROWS`.
LANE_MIX_TILES: int = 12

#: `head`'s log-odds are unbounded where a cell proves the target plane;
#: they are clipped before PAVA ever sees them so one certain cell cannot
#: set the standardisation's scale.
HEAD_CLIP: float = 40.0


class UnmixError(RuntimeError):
    """The plane cannot be isolated as asked."""


# ----------------------------------------------------------- the shim

@dataclass(frozen=True)
class _ShimRows:
    known_component_bits: np.ndarray
    known_component_mask: np.ndarray
    page_cells_yx: np.ndarray


@dataclass
class _ShimRead:
    """What `plane_k`'s lane-scope functions actually read off a read."""

    values: np.ndarray
    rows: _ShimRows
    labels: np.ndarray


def shim_read(frame: KnownFrame, values_rgb: np.ndarray,
              cells_yx: np.ndarray, *,
              usable: np.ndarray | None = None) -> _ShimRead:
    """A `WindowRead`-shaped view of a footprint, for `plane_k` reuse."""
    keep = (np.ones(cells_yx.shape[0], bool) if usable is None
            else np.asarray(usable, bool))
    bits = np.asarray(frame.bits, np.uint8)[keep]
    known = np.asarray(frame.known, bool)[keep]
    labels = np.full(int(np.count_nonzero(keep)), -1, np.int8)
    return _ShimRead(
        values=np.asarray(values_rgb, np.float64)[keep],
        rows=_ShimRows(known_component_bits=bits,
                       known_component_mask=known,
                       page_cells_yx=np.asarray(cells_yx, np.int64)[keep]),
        labels=labels)


def isolated_scores(mix: spectral.PlaneMix, frame: KnownFrame,
                    values_rgb: np.ndarray, cells_yx: np.ndarray,
                    plane: int) -> np.ndarray:
    """`plane_k.isolated_scores`, CALLED (the `subtract` seam, standardised)."""
    read = shim_read(frame, values_rgb, cells_yx)
    return np.asarray(
        plane_k.isolated_scores(mix, read, read.values, plane), np.float64)


# ------------------------------------------------------------- the mix

def fit_mix(values_rgb: np.ndarray, frame: KnownFrame, *,
            scope_ladder: Sequence[str] = ("footprint", "lane"),
            lane_mix: spectral.PlaneMix | None = None,
            cells_yx: np.ndarray | None = None,
            usable: np.ndarray | None = None,
            ) -> tuple[spectral.PlaneMix, str]:
    """DESIGN §4.6's mixing-fit refusal ladder, first accepted wins.

    Never None: a `PlaneMix` with ``accepted=False`` and its reason is the
    refusal, exactly as `spectral.fit_plane_mix` spells it.
    """
    cells = (np.zeros((np.asarray(values_rgb).shape[0], 2), np.int64)
             if cells_yx is None else np.asarray(cells_yx, np.int64))
    attempts: list[tuple[str, spectral.PlaneMix]] = []
    for scope in scope_ladder:
        if scope not in MIX_SCOPES:
            raise UnmixError(f"unknown mix scope {scope!r}")
        if scope == "footprint":
            read = shim_read(frame, values_rgb, cells, usable=usable)
            candidate = plane_k.fit_lane_mix((read,))
        else:
            candidate = lane_mix
        if candidate is None:
            attempts.append((scope, None))
            continue
        attempts.append((scope, candidate))
        if candidate.accepted:
            return candidate, scope
    for scope, candidate in attempts:
        if candidate is not None:
            return candidate, scope
    return spectral.fit_plane_mix(
        np.zeros((0, 3)), np.zeros((0, 3), np.uint8),
        np.zeros((0, 3), bool)), "refused"


def mix_detail(mix: spectral.PlaneMix, scope: str) -> dict:
    return {"mix_scope": scope, "mix_accepted": bool(mix.accepted),
            "mix_reason": str(mix.reason),
            "mix_n_full_rows": int(mix.n_full_rows),
            "mix_class_counts": tuple(tuple(int(v) for v in pair)
                                      for pair in mix.class_counts)}


def _stable_seed(lane_id: Any, page: int, stream: str) -> int:
    """A seed that is the same in every process (DESIGN §0, determinism).

    Python's built-in `hash` of a string is salted per interpreter, so a
    seed built from it makes the lane-scope tile SAMPLE — and therefore
    the mixing model every arm on that lane uses — differ between runs.
    A blake2b digest of the same identity is stable, which is what
    "every random draw is a hash of (seed, key, ...)" asks for.
    """
    material = f"{tuple(lane_id)!r}|{int(page)}|{str(stream)}".encode()
    return int.from_bytes(
        hashlib.blake2b(material, digest_size=8).digest(), "big"
    ) & ((1 << 62) - 1) or 1


def _sample_tiles(inputs: RunInputs, lane: Lane, page: int, stream: str,
                  n_tiles: int, exclude: tuple[int, int] | None,
                  ) -> tuple[tuple[int, int], ...]:
    """A deterministic, seeded tile sample for the lane-scope mixing fit."""
    from .inputs import lane_tile_coverage
    counts = lane_tile_coverage(inputs, lane.lane_id, page)
    tiles = [(int(ty), int(tx))
             for ty, tx in zip(*np.nonzero(counts >= TILE_CELLS ** 2))
             if exclude is None or (int(ty), int(tx)) != exclude]
    if not tiles:
        tiles = [(int(ty), int(tx))
                 for ty, tx in zip(*np.nonzero(counts > 0))
                 if exclude is None or (int(ty), int(tx)) != exclude]
    if not tiles:
        return ()
    seed = _stable_seed(lane.lane_id, page, stream)
    draw = cal.fold_hash(np.asarray(tiles, np.int64), seed)
    order = np.argsort(draw, kind="stable")[:int(n_tiles)]
    return tuple(sorted(tiles[int(index)] for index in order))


def _sample_frame(inputs: RunInputs, certs: Mapping[Key, Any],
                  fp: TileFootprint,
                  forbidden: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Furniture plus certified projections over a NON-target tile.

    `frame.known_frame` cannot serve here: it is built around excluding
    ONE target key from its own tile, and the lane-scope mixing fit needs
    the opposite — every certificate a tile has, over tiles that are not
    the target's.  The refusal is explicit: this function will not touch
    the target's tile at all, and the caller's sample never contains it.
    """
    if (int(fp.ty), int(fp.tx)) == forbidden:
        raise UnmixError(
            f"lane-scope mix asked for the TARGET tile {forbidden} — the "
            f"sample must exclude it (DESIGN §4.5)")
    cells = np.asarray(fp.page_cells_yx, np.int64)
    bits = np.zeros((cells.shape[0], 3), np.uint8)
    known = np.zeros((cells.shape[0], 3), bool)
    states, kinds = color_model.reference_states(
        inputs.row, inputs.geometry, int(fp.page), cells)
    furniture = np.asarray(kinds, np.int8) >= 0
    if np.any(furniture):
        rows = np.flatnonzero(furniture)
        bits[rows] = tile_codec.states_to_planes(
            np.asarray(states, np.int8)[rows])
        known[rows] = True
    projection = frame_mod._projection(inputs, certs, int(fp.page),
                                       int(fp.ty), int(fp.tx), None)
    if projection is not None:
        tile_bits, tile_known = projection
        flat_bits = tile_bits.reshape(-1, 3)
        flat_known = tile_known.reshape(-1, 3)
        take = ((cells[:, 0] % TILE_CELLS) * TILE_CELLS
                + cells[:, 1] % TILE_CELLS)
        hit = flat_known[take]
        bits = np.where(hit, flat_bits[take], bits)
        known |= hit
    return bits, known


def lane_mix(inputs: RunInputs, lane: Lane, certs: Mapping[Key, Any],
             stream: str, *, page: int = 0,
             exclude_tile: tuple[int, int] | None = None,
             n_tiles: int = LANE_MIX_TILES,
             ) -> tuple[spectral.PlaneMix, dict]:
    """The LANE-scope mixing model — one fit per (lane, stream), memoised.

    DESIGN §4.6 wants it over the whole page's regressors; PLAN §6 records
    the deviation this takes instead — a deterministic sample of
    `n_tiles` fully covered tiles, the target's tile removed, each read
    once through the ordinary crop-and-read path.  The memo key carries
    the excluded tile, so the fit a target sees never contains that
    target's own certificates and two targets still share a fit whenever
    neither is in the sample.
    """
    plane = PLANE_OF[str(stream)]
    token = frame_mod._certs_token(inputs, certs)
    tiles = _sample_tiles(inputs, lane, page, stream, n_tiles, exclude_tile)
    memo = inputs._cache.setdefault("arms_lane_mix", {})
    cache_key = (lane.lane_id, str(stream), token, int(page), tiles)
    hit = memo.get(cache_key)
    if hit is not None:
        return hit
    cell_dots = color_sites.cell_dots_of(inputs.row)
    reads: list[_ShimRead] = []
    for ty, tx in tiles:
        fp = frame_mod.tile_footprint(inputs.row, page, ty, tx, 0,
                                      geometry=inputs.geometry)
        lfp = sample_mod.lane_footprint(lane, fp)
        if lfp is None or not np.any(lfp.observed):
            continue
        try:
            crops = sample_mod.open_crops(lane, lfp, bound_dots=0.0,
                                          cell_dots=cell_dots)
        except sample_mod.SampleError:
            continue
        read = sample_mod.read_rgb(crops, lfp, arm="lane-mix")
        if read.refusal is not None:
            continue
        bits, known = _sample_frame(
            inputs, certs, fp,
            exclude_tile if exclude_tile is not None else (-1, -1))
        shim = _ShimRead(
            values=np.asarray(read.values_rgb, np.float64)[lfp.observed],
            rows=_ShimRows(
                known_component_bits=bits[lfp.observed],
                known_component_mask=known[lfp.observed],
                page_cells_yx=fp.page_cells_yx[lfp.observed]),
            labels=np.full(int(np.count_nonzero(lfp.observed)), -1, np.int8))
        reads.append(shim)
    if not reads:
        mix = spectral.fit_plane_mix(np.zeros((0, 3)),
                                     np.zeros((0, 3), np.uint8),
                                     np.zeros((0, 3), bool))
    else:
        mix = plane_k.fit_lane_mix(tuple(reads))
    detail = {"lane_mix_tiles": tiles, "lane_mix_reads": len(reads),
              "lane_mix_plane": plane, **mix_detail(mix, "lane")}
    memo[cache_key] = (mix, detail)
    return mix, detail


# ---------------------------------------------------------- the unmixing

def _state_means(mix: spectral.PlaneMix) -> np.ndarray:
    """(8, 3) channel mean of every printed state under the fitted model."""
    bits = tile_codec.states_to_planes(
        np.arange(8, dtype=np.uint8)).astype(np.float64)
    return np.asarray(mix.m0, np.float64)[None, :] + bits @ np.asarray(
        mix.coef, np.float64).T


def _head_score(mix: spectral.PlaneMix, values: np.ndarray,
                frame: KnownFrame, plane: int) -> np.ndarray:
    """The analyzer's per-plane head, with the two-of-three relaxation."""
    v = np.asarray(values, np.float64)
    means = _state_means(mix)
    precision = np.linalg.inv(np.asarray(mix.covariance, np.float64))
    residual = v[:, None, :] - means[None, :, :]
    quad = np.einsum("nsc,cd,nsd->ns", residual, precision, residual)
    log_weight = -0.5 * quad
    state_bits = tile_codec.states_to_planes(
        np.arange(8, dtype=np.uint8)).astype(bool)
    bits = np.asarray(frame.bits, np.uint8).astype(bool)
    known = np.asarray(frame.known, bool)
    # ONLY the siblings restrict the hypothesis set.  Restricting on the
    # TARGET plane's own known bit would make the head read the answer off
    # the frame at every label cell — a self-referential score that reads
    # 0.0000 error on labels and says nothing about cargo (measured
    # 2026-09-03 on sheet I before this line existed; the same circularity
    # INDEPENDENT-PLANES section 2.12 and the E4 context arm hit).
    allowed = np.ones((v.shape[0], 8), bool)
    for other in spectral.siblings_of(plane):
        matches = state_bits[None, :, other] == bits[:, other, None]
        allowed &= ~known[:, other, None] | matches
    ones = allowed & state_bits[None, :, plane]
    zeros = allowed & ~state_bits[None, :, plane]
    with np.errstate(divide="ignore", invalid="ignore"):
        top = logsumexp(np.where(ones, log_weight, -np.inf), axis=1)
        bottom = logsumexp(np.where(zeros, log_weight, -np.inf), axis=1)
    score = np.where(np.isfinite(top - bottom), top - bottom,
                     np.where(np.isfinite(top), HEAD_CLIP, -HEAD_CLIP))
    return np.clip(score, -HEAD_CLIP, HEAD_CLIP)


def _conditional_score(mix: spectral.PlaneMix, values: np.ndarray,
                       frame: KnownFrame, plane: int,
                       fit_mask: np.ndarray | None) -> np.ndarray:
    """Per-cell classification against EMPIRICAL per-sibling-state clusters.

    The model-level version of this is algebraically `subtract` (the same
    linear functional on the same cleaned residual), so it would be a
    duplicate row.  What makes it a distinct arm is that the two cluster
    means of each sibling state are estimated FROM THE DATA — the shape
    `swim.fit_window` uses for its level table — on the fit fold's labels
    only, falling back to the model where a condition has no support and
    to `project` where the siblings are not known at all.
    """
    v = np.asarray(values, np.float64)
    left, right = spectral.siblings_of(plane)
    bits = np.asarray(frame.bits, np.uint8)
    known = np.asarray(frame.known, bool)
    cleanable = known[:, left] & known[:, right]
    out = np.asarray(spectral.plane_score(
        mix, v, bits, known, plane, spectral.MODE_PROJECT), np.float64)
    labelled = known[:, plane] & cleanable
    if fit_mask is not None:
        labelled = labelled & np.asarray(fit_mask, bool)
    precision = np.linalg.inv(np.asarray(mix.covariance, np.float64))
    direction = np.asarray(mix.coef, np.float64)[:, plane]
    gain = float(direction @ precision @ direction)
    if gain <= 0.0:
        return out
    means = _state_means(mix)
    for sibling_left in (0, 1):
        for sibling_right in (0, 1):
            condition = (cleanable & (bits[:, left] == sibling_left)
                         & (bits[:, right] == sibling_right))
            if not np.any(condition):
                continue
            centres = []
            for target_bit in (0, 1):
                state = np.zeros(3, np.uint8)
                state[left], state[right] = sibling_left, sibling_right
                state[plane] = target_bit
                model = means[int(state[0] | (state[1] << 1)
                                  | (state[2] << 2))]
                rows = np.flatnonzero(
                    condition & labelled & (bits[:, plane] == target_bit))
                centres.append(v[rows].mean(axis=0)
                               if rows.size >= spectral.MIN_PER_CLASS
                               else model)
            midpoint = 0.5 * (centres[0] + centres[1])
            rows = np.flatnonzero(condition)
            out[rows] = ((v[rows] - midpoint) @ precision @ direction) / gain
            out[rows] = out[rows] + 0.5
    return out


def unmix_score(mode: str, target_plane: int, mix: spectral.PlaneMix,
                values_rgb: np.ndarray, frame: KnownFrame, *,
                fit_mask: np.ndarray | None = None,
                context: tuple[Any, ...] | None = None) -> np.ndarray:
    """One plane's PRESENCE, high = ink (PLAN §1.3's ink-dark convention).

    `calibrate.calibrate` standardises it with
    `calibrate.window_scores(-score)`, which is `plane_k.isolated_scores`'s
    second line, so this is the same quantity the production arm hands to
    the black-and-white machinery.

    A patch mode (W8) reads pixels, not `values_rgb`: `context` is
    ``(crops, read, lfp, folds, spec)`` and its absence is an ERROR, never
    a silent fall-back to another mode.
    """
    if mode not in UNMIX_MODES:
        raise UnmixError(f"unknown unmix mode {mode!r}; known: {UNMIX_MODES}")
    values = np.asarray(values_rgb, np.float64)
    if not mix.accepted:
        return np.full(values.shape[0], np.nan)
    if mode in patch_mod.PATCH_MODES:
        if context is None:
            raise UnmixError("patch modes need a read context "
                             "(crops, read, lfp, folds, spec)")
        crops, read, lfp, folds, spec = context
        return patch_mod.patch_score(spec, target_plane, frame, mix, crops,
                                     read, lfp, folds, mode=mode)[0]
    if mode in ("raw", "project", "subtract"):
        return np.asarray(spectral.plane_score(
            mix, values, frame.bits, frame.known, target_plane, mode),
            np.float64)
    if mode == "global":
        # DESIGN §4.6: `global` IS `subtract`, on the LANE-scope mix; the
        # caller is the one that hands the lane mix in.
        return np.asarray(spectral.plane_score(
            mix, values, frame.bits, frame.known, target_plane,
            spectral.MODE_SUBTRACT), np.float64)
    if mode == "conditional":
        return _conditional_score(mix, values, frame, target_plane, fit_mask)
    return _head_score(mix, values, frame, target_plane)

