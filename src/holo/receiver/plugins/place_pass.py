"""ONE WINDOW PASS over pixels -- the executor side of `place`.

Split out of `place.py` 2026-09-21, when the quartering became a rung
and the file went past the 1000-line seam signal.  The cut is the
module's own: `place` is the placement LAW (the admission algebra, the
rung ladder and its prices, the region frame, the window plan and the
consult portfolio), all of it pure over the store; this file is the
JOB that ladder schedules -- the crop, the pose fit, the address
search, the straddle audit and the `Placement` they mint.  It reads
`place`; `place` never reads it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .. import data
from ..format import pilots
from ..format.identity import FormatRow
from ..lib import geometry
from ..lib.decimate import plane_mean_luma_f32
from . import cold, pose, words
from .place import (
    E022_SUPPORT_FLOOR_SITES,
    GATE_MINIMUM_GAP,
    GATE_RIVAL_DECOY,
    GATE_SEARCH_TRUE,
    GATE_VALIDATION_TRUE,
    NEIGHBOR_RADIUS_CELLS,
    OUTCOME_SUBDIVIDED,
    ROUTE_CHAIN,
    ROUTE_COLD,
    ROUTE_WORD,
    WINDOW_CELLS,
    RegionFrame,
    Seed,
    cold_tried_id,
    local_search,
    min_support_for,
    page_affine_terms,
    pass_budget_hypotheses,
    predict_from_page_affine,
    word_address,
)

@dataclass(frozen=True)
class WindowPass:
    window: data.Window
    frame: RegionFrame
    planes: tuple[np.ndarray, ...]
    row: FormatRow
    reference: words.ReferenceField
    page_domain: tuple[int, ...]
    stage: str | None
    wide: bool
    cold_flavour: str | None
    cold_pages: tuple[int, ...]
    seeds: tuple[Seed, ...]
    tried_count: int
    lattice_seed: tuple[float, float, float, float] | None
    patch_ordinal: int
    cold_h_pages: int = 0


@dataclass(frozen=True)
class WindowPassResult:
    outcome: str
    route: str | None
    placement: data.Placement | None
    lattice_seed: data.LatticeSeed | None
    tried_now: tuple[str, ...]
    stage_spent: str | None
    wide_spent: bool
    cold_spent: str | None
    hypotheses: int
    events: tuple[object, ...]


# Addressing runs ONCE per capture, on equal-channel luma for K, cmy7
# and cmy8 and on the R plane alone for cmy (R24: `_window_crop` hands
# it `planes[:1]`, the one-plane branch) -- the poses every plane view
# reads downstream are this one fit.  Per-plane addressing is not a
# variant of this function; it would fork the pose record.
def _crop_luma(planes: tuple[np.ndarray, ...], y0: int, y1: int,
               x0: int, x1: int) -> np.ndarray:
    if len(planes) == 3:
        return plane_mean_luma_f32(
            planes[0][y0:y1, x0:x1], planes[1][y0:y1, x0:x1],
            planes[2][y0:y1, x0:x1])
    return np.asarray(planes[0][y0:y1, x0:x1], np.float32)


def support_pixels(frame: RegionFrame, y0: int, y1: int, x0: int,
                   x1: int) -> np.ndarray:
    scale = frame.scale
    native_y = (np.arange(y0, y1, dtype=np.int64) * scale + scale // 2
                - frame.origin_native_yx[0])
    native_x = (np.arange(x0, x1, dtype=np.int64) * scale + scale // 2
                - frame.origin_native_yx[1])
    iy = native_y // frame.survey_step_px
    ix = native_x // frame.survey_step_px
    valid_y = ((native_y >= 0) & (native_y < frame.survey_extent_px[0])
               & (iy < frame.survey_cells.shape[0]))
    valid_x = ((native_x >= 0) & (native_x < frame.survey_extent_px[1])
               & (ix < frame.survey_cells.shape[1]))
    out = np.zeros((y1 - y0, x1 - x0), bool)
    if not valid_y.any() or not valid_x.any():
        return out
    picked = frame.survey_cells[np.ix_(iy[valid_y], ix[valid_x])]
    out[np.ix_(np.flatnonzero(valid_y), np.flatnonzero(valid_x))] = picked
    return out


def _window_crop(job: WindowPass) -> tuple[pose.WindowPixels,
                                           tuple[int, int]] | None:
    frame = job.frame
    cy0, cx0, cy1, cx1 = job.window.extent_cells
    cells = (cy1 - cy0, cx1 - cx0)
    pitch = frame.pitch_level_px
    wy = frame.origin_level_yx[0] + int(round(cy0 * pitch))
    wx = frame.origin_level_yx[1] + int(round(cx0 * pitch))
    halo = int(math.ceil(pose.HALO_CELLS * pitch))
    py1 = wy + int(round(cells[0] * pitch))
    px1 = wx + int(round(cells[1] * pitch))
    plane_shape = job.planes[0].shape
    y0 = max(0, wy - halo)
    y1 = min(int(plane_shape[0]), py1 + halo)
    x0 = max(0, wx - halo)
    x1 = min(int(plane_shape[1]), px1 + halo)
    if y1 <= y0 or x1 <= x0:
        return None
    planes = (job.planes[:1] if job.row.family in words.ADDRESSING_ON_R
              else job.planes)
    luma = _crop_luma(planes, y0, y1, x0, x1)
    support = support_pixels(frame, y0, y1, x0, x1)
    pixels = pose.window_pixels(
        luma, support, (wy - y0, wx - x0), cells, pitch, frame.backing,
        job.row)
    if pixels is None:
        return None
    return pixels, (y0, x0)


def _seed_fact(job: WindowPass,
               fit: pose.WindowFit) -> data.LatticeSeed | None:
    if fit.unconditioned_seed is None:
        return None
    return data.LatticeSeed(
        capture_id=job.frame.capture_id,
        level_index=job.frame.level_index,
        region_index=job.frame.region_index,
        rows=np.asarray(fit.unconditioned_seed, np.float64),
        support_cells=job.window.supported_cells,
        window_ordinal=job.window.ordinal)


def _settled(job: WindowPass, outcome: str,
             seed_fact: data.LatticeSeed | None = None,
             tried_now: tuple[str, ...] = (),
             stage_spent: str | None = None,
             wide_spent: bool = False,
             cold_spent: str | None = None,
             hypotheses: int = 0) -> WindowPassResult:
    event = data.WindowSettled(
        capture=job.frame.capture_id,
        level_index=job.frame.level_index,
        region_index=job.frame.region_index,
        extent_cells=job.window.extent_cells,
        state=outcome)
    return WindowPassResult(
        outcome, None, None, seed_fact, tried_now, stage_spent,
        wide_spent, cold_spent, hypotheses, (event,))


#: The `subdivide` rung's verdict, and the whole of its job's output
#: beside the four children.  No `WindowSettled` event: this window has
#: not settled, it has spent a rung.
def subdivided_result() -> WindowPassResult:
    return WindowPassResult(
        outcome=OUTCOME_SUBDIVIDED, route=None, placement=None,
        lattice_seed=None, tried_now=(), stage_spent=None,
        wide_spent=False, cold_spent=None, hypotheses=0, events=())


#: The one producer of `data.Placement.local_cells_yx`.  int16 because
#: the stored pose is window-LOCAL: the coordinates are non-negative and
#: bounded by the window extent, and this array alone is 94-98% of a
#: fact snapshot.  A window that could overflow the width is a bug in
#: the frame, not a case to wrap silently, so it raises.
def local_cells_of(audited: np.ndarray) -> np.ndarray:
    cells = np.argwhere(np.asarray(audited, bool))
    limit = int(np.iinfo(np.int16).max)
    if cells.size and int(cells.max()) > limit:
        raise ValueError(
            f"place: window-local cell {int(cells.max())} exceeds int16")
    return cells.astype(np.int16, copy=False)


def _address_coverage(placement: data.Placement,
                      local_shape_yx: tuple[int, int],
                      row: FormatRow) -> data.AddressCoverage | None:
    local = np.asarray(placement.local_cells_yx, np.int64)
    if not local.size:
        return None
    mapped = geometry.rotated_points(local, local_shape_yx, placement.rot_k)
    mapped = mapped + np.asarray(placement.page_origin_yx, np.int64)
    height, width = row.cells_yx
    inside = ((mapped[:, 0] >= 0) & (mapped[:, 0] < height)
              & (mapped[:, 1] >= 0) & (mapped[:, 1] < width))
    mapped = mapped[inside]
    if not mapped.size:
        return None
    period = pilots.TILE_CELLS
    site_index = words.word_site_index(row.sites_seed)
    sites = site_index[mapped[:, 0] % period, mapped[:, 1] % period]
    keep = sites >= 0
    if not bool(keep.any()):
        return None
    tiles_x = row.tiles_yx[1]
    flat = ((mapped[keep, 0] // period) * tiles_x
            + (mapped[keep, 1] // period))
    site_ids = sites[keep].astype(np.int64)
    rows_out: list[tuple[int, int, bytes]] = []
    for tile_flat in np.unique(flat):
        mask = np.zeros(pilots.N_WORD_SITES, bool)
        mask[site_ids[flat == tile_flat]] = True
        rows_out.append((int(tile_flat // tiles_x), int(tile_flat % tiles_x),
                         np.packbits(mask).tobytes()))
    return data.AddressCoverage(page=placement.page, tiles=tuple(rows_out))


def run_window_pass(job: WindowPass) -> WindowPassResult:
    """One placement pass over one window.

    NO DONE GATE HERE.  Done-geometry SUPPRESSES at the scheduler door:
    `place_sched.worker_stage` returns no stage while
    `store.window_fully_done` holds, and `engine._fill` asks the stage
    before it builds this job — a done window never reaches this
    function, so a second copy of the test here would be unreachable by
    construction and was deleted with the evidence
    (`measure/donegeo_realstate.py`).  It is not a retire cause since
    56928c45 (2026-10-03): the pose-free verdict can be re-opened by a
    pose revision, and a retirement cannot.
    """
    frame = job.frame
    extent = job.window.extent_cells
    seeds = job.seeds
    will_word = (not seeds) and job.stage is not None
    if not seeds and not will_word and not job.cold_pages:
        if job.cold_flavour is not None:
            return _settled(job, f"cold_refused_{job.cold_flavour}",
                            wide_spent=job.wide,
                            cold_spent=job.cold_flavour)
        return _settled(job, "nothing_to_try", wide_spent=job.wide)
    budget_hypotheses = pass_budget_hypotheses(job.tried_count, len(seeds))
    floor = min_support_for(budget_hypotheses)
    crop = _window_crop(job)
    if crop is None:
        return _settled(job, "insufficient_support")
    pixels, crop_origin = crop
    seed_rows = (None if job.lattice_seed is None
                 else np.asarray(job.lattice_seed,
                                 np.float64).reshape(2, 2))
    fit = pose.fit_window_pose(pixels, seed_rows)
    seed_fact = _seed_fact(job, fit)
    if fit.segment is None:
        return _settled(job, "pose_refused", seed_fact=seed_fact)
    sample = pose.sample_segment(pixels, fit.segment)
    if sample is None or int(sample.mask.sum()) < E022_SUPPORT_FLOOR_SITES:
        return _settled(job, "insufficient_support", seed_fact=seed_fact)
    core = pose.address_core(sample.mask)
    memo = pose.ScoreMemo(job.reference)
    tried_now: tuple[str, ...] = ()
    stage_spent: str | None = None
    cold_spent: str | None = None
    address: tuple[int, int, tuple[int, int]] | None = None
    route: str | None = None
    word_candidate: words.WordCandidate | None = None
    mismatch = 0.0
    hypotheses = budget_hypotheses
    audit_floor = floor
    if seeds:
        tried_now = tuple(seed.candidate_id for seed in seeds)
        for seed in seeds:
            rot_k, predicted = predict_from_page_affine(
                seed.affine, sample.segment.pose.matrix(),
                (crop_origin[0] + sample.segment.pose.origin_yx[0],
                 crop_origin[1] + sample.segment.pose.origin_yx[1]),
                pixels.shape_yx_cells, frame.scale)
            outcome = local_search(
                memo, sample.evidence, sample.bits, core, seed.page,
                rot_k, predicted, floor, budget_hypotheses)
            if outcome.accepted and outcome.best is not None:
                address = (seed.page, rot_k, outcome.best.origin_yx)
                route = ROUTE_CHAIN
                mismatch = outcome.best.search_mismatch
                break
    if address is None and will_word and job.stage is not None:
        result = words.stage_a(sample.bits, core, job.row, job.stage)
        stage_spent = job.stage
        hypotheses = result.hypotheses
        if result.reason != "attempt_budget_exceeded":
            admitted = word_address(
                memo, sample.evidence, sample.bits, core,
                result.candidates, job.page_domain, floor)
            if admitted is not None:
                word_candidate, mismatch = admitted
                address = (word_candidate.page, word_candidate.rot_k,
                           word_candidate.page_origin_yx)
                route = ROUTE_WORD
    if address is None and job.cold_pages:
        tried_now = tried_now + tuple(
            cold_tried_id(page, job.cold_flavour or "")
            for page in job.cold_pages)
        cold_spent = job.cold_flavour
        declared = cold.hypothesis_count(
            (WINDOW_CELLS, WINDOW_CELLS), job.row.cells_yx,
            job.cold_h_pages)
        cold_floor = min_support_for(declared)
        outcome = cold.correlate_patch(
            sample.evidence, sample.bits, core, job.reference,
            job.cold_pages, declared, cold_floor, memo,
            GATE_SEARCH_TRUE, GATE_VALIDATION_TRUE, GATE_RIVAL_DECOY,
            GATE_MINIMUM_GAP, NEIGHBOR_RADIUS_CELLS)
        hypotheses = outcome.hypotheses
        if outcome.accepted and outcome.best is not None:
            address = (outcome.best.page, outcome.best.rot_k,
                       outcome.best.origin_yx)
            route = ROUTE_COLD
            mismatch = outcome.best.search_mismatch
            # The audit is judged at the floor of the DOMAIN THAT ADMITTED the
            # address: cold declares a far larger domain than the 49-hypothesis
            # chain, so a cold acceptance carries its own min_support into
            # audit_segment rather than the pass's.
            audit_floor = cold_floor
    if address is None:
        if cold_spent is not None:
            reason = f"cold_refused_{cold_spent}"
        elif seeds:
            reason = "wide_refused" if job.wide else "consult_refused"
        else:
            reason = f"no_word_candidate_{stage_spent}"
        return _settled(job, reason, seed_fact=seed_fact,
                        tried_now=tried_now, stage_spent=stage_spent,
                        wide_spent=job.wide, cold_spent=cold_spent,
                        hypotheses=hypotheses)
    page, rot_k, origin_yx = address
    refined = pose.refine_patch_pose(
        pixels, sample, job.reference, page, origin_yx, rot_k)
    if (refined is not None
            and int(refined.sample.mask.sum()) >= E022_SUPPORT_FLOOR_SITES):
        sample = refined.sample
        core = pose.address_core(refined.sample.mask)
    audited, refused, _kept, _residual = pose.audit_segment(
        sample, core, job.reference, page, origin_yx, rot_k, audit_floor)
    if refused:
        return _settled(job, "straddle_audit_refused", seed_fact=seed_fact,
                        tried_now=tried_now, stage_spent=stage_spent,
                        wide_spent=job.wide, cold_spent=cold_spent,
                        hypotheses=hypotheses)
    final_pose = sample.segment.pose
    native = page_affine_terms(
        final_pose.matrix(),
        (crop_origin[0] + final_pose.origin_yx[0],
         crop_origin[1] + final_pose.origin_yx[1]),
        pixels.shape_yx_cells, rot_k, origin_yx, frame.scale)
    pitch_native = 0.5 * (float(np.hypot(native[0], native[3]))
                          + float(np.hypot(native[1], native[4])))
    local_cells = local_cells_of(audited)
    placement = data.Placement(
        window_id=job.window.window_id,
        capture_id=frame.capture_id,
        level_index=frame.level_index,
        region_index=frame.region_index,
        patch_ordinal=job.patch_ordinal,
        page=int(page),
        rot_k=int(rot_k),
        page_origin_yx=(int(origin_yx[0]), int(origin_yx[1])),
        native_affine=native,
        pitch_px=pitch_native,
        route=str(route),
        local_cells_yx=local_cells,
        quality=float(mismatch))
    local_shape = (int(np.asarray(audited).shape[0]),
                   int(np.asarray(audited).shape[1]))
    event = data.PoseCommitted(
        capture=frame.capture_id,
        level_index=frame.level_index,
        region_index=frame.region_index,
        extent_cells=extent,
        page=int(page),
        route=str(route),
        mismatch=float(mismatch),
        accepted=True,
        page_origin_yx=(int(origin_yx[0]), int(origin_yx[1])),
        rot_k=int(rot_k),
        pitch_px=float(pitch_native),
        native_affine=native,
        shape_yx=local_shape)
    pass_events: list[object] = [event]
    try:
        if route == ROUTE_WORD and word_candidate is not None:
            pass_events.append(data.WordOutcome(
                page=int(word_candidate.page),
                ty=int(word_candidate.tile_yx[0]),
                tx=int(word_candidate.tile_yx[1]),
                errors=int(word_candidate.errors),
                sites=int(word_candidate.visible)))
        coverage = _address_coverage(placement, local_shape, job.row)
        if coverage is not None:
            pass_events.append(coverage)
    except Exception:
        pass
    return WindowPassResult(
        "accepted", route, placement, seed_fact, tried_now, stage_spent,
        job.wide, cold_spent, hypotheses, tuple(pass_events))
