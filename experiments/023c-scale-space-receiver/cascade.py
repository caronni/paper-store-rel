"""Production kernels for the E023c coarse-to-fine receiver.

The module deliberately keeps the qualified lower layers intact:

* E021 owns segmentation at every scale;
* E022 owns current-raster pose fitting, pilot gates and placement;
* E023b owns context/PAVA, one-owner evidence and LDPC+CRC attempts.

E023c changes orchestration.  A lower level may suggest a bounded placement
route and already certified payload may propose a bounded pose refinement,
but current pixels are always sampled afresh.  Scale lanes never exchange or
sum LLRs.  They meet only at the syndrome+CRC certificate boundary.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np

from paperholo import (compose, feedback, ldpc, payloaddec, pilotsearch,
                       platen, receiver)
from paperholo.feedbackstate import FeedbackConfig

import scale_space


TileKey = tuple[int, int, int]
Observer = Callable[[str, dict], None]


@dataclass(frozen=True)
class Certificate:
    """One conflict-checked LDPC+CRC certificate in the scale portfolio."""

    key: TileKey
    user_bits: np.ndarray
    lanes: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass
class LevelRun:
    """Complete provisional result of one scale before capture commit."""

    level: scale_space.ScaleLevel
    lane_key: str
    source_path: Path
    source_sha256: str
    source_size: int
    survey: platen.PayloadSurvey
    result: pilotsearch.SearchResult
    record: receiver.ScanRecord
    lane_session: receiver.ReceiverSession
    apply_counts: dict
    feedback: dict
    timings: dict


def lane_key(level: scale_space.ScaleLevel) -> str:
    """Stable independent-lane name for one scale level."""
    ppc = level.ppc
    return f"ppc-{ppc.numerator}-{ppc.denominator}"


def certificate_id(key: TileKey, bits: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(bits, np.uint8).ravel())
    digest = hashlib.sha256()
    digest.update(b"e023c/certificate/v1\0")
    digest.update(repr(tuple(int(v) for v in key)).encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest()


def lane_certificates(
    session: receiver.ReceiverSession,
    *,
    lane: str,
) -> dict[TileKey, Certificate]:
    """Extract only certified E023b outcomes from one independent lane."""
    out: dict[TileKey, Certificate] = {}
    for raw_key, outcome in sorted(session.decode.tiles.items()):
        if outcome.state != "certified":
            continue
        key = tuple(int(value) for value in raw_key)
        bits = np.asarray(outcome.user_bits, np.uint8).ravel().copy()
        if bits.size == 0 or np.any((bits != 0) & (bits != 1)):
            raise payloaddec.FatalIntegrityError(
                f"lane {lane}: malformed certificate {key}")
        out[key] = Certificate(
            key=key, user_bits=bits, lanes=(str(lane),),
            sources=(str(outcome.certified_by),))
    return out


def merge_certificates(
    *parts: Mapping[TileKey, Certificate],
) -> dict[TileKey, Certificate]:
    """Union correlated lanes at the certificate boundary; conflicts fatal."""
    merged: dict[TileKey, Certificate] = {}
    for part in parts:
        for raw_key, row in sorted(part.items()):
            key = tuple(int(value) for value in raw_key)
            bits = np.asarray(row.user_bits, np.uint8).ravel()
            old = merged.get(key)
            if old is None:
                merged[key] = Certificate(
                    key, bits.copy(), tuple(row.lanes), tuple(row.sources))
                continue
            if not np.array_equal(old.user_bits, bits):
                raise payloaddec.FatalIntegrityError(
                    f"conflicting cross-scale certificates for {key}: "
                    f"{old.lanes} vs {row.lanes}")
            merged[key] = Certificate(
                key=key, user_bits=old.user_bits,
                lanes=tuple(dict.fromkeys(old.lanes + tuple(row.lanes))),
                sources=tuple(dict.fromkeys(
                    old.sources + tuple(row.sources))))
    return merged


def portfolio_from_lanes(
    lanes: Mapping[str, receiver.ReceiverSession],
) -> dict[TileKey, Certificate]:
    """Rebuild the authoritative conflict-checked portfolio from lanes."""
    return merge_certificates(*(
        lane_certificates(session, lane=name)
        for name, session in sorted(lanes.items())
    ))


def _copy_hint(
    placed: pilotsearch.PlacedWindow,
    source_level: scale_space.ScaleLevel,
    target_level: scale_space.ScaleLevel,
    *,
    method: str,
) -> pilotsearch.PlacedWindow:
    native_pose = source_level.transform.from_view_pose(placed.pose)
    target_pose = target_level.transform.to_view_pose(native_pose)
    diagnostics = dict(placed.diagnostics)
    diagnostics.update({
        "hint_source_level": source_level.label,
        "hint_target_level": target_level.label,
        "hint_source_method": placed.method,
    })
    return replace(
        placed, pose=target_pose, method=method,
        diagnostics=diagnostics, page_cells_yx=np.zeros((0, 2), np.int32),
        redundant=False)


def _runner_up_hints(
    result: pilotsearch.SearchResult,
    *,
    per_region: int,
) -> list[pilotsearch.PlacedWindow]:
    """Reify a small losing-address ledger from E022's fitted poses."""
    if per_region <= 0:
        return []
    audit = result.diagnostics.get("window_audit", {})
    hints: list[pilotsearch.PlacedWindow] = []
    for raw_region, rows in sorted(audit.items(), key=lambda item: int(item[0])):
        candidates = []
        for row in rows:
            candidate = row.get("best_candidate")
            pose_row = row.get("pose_field")
            window = row.get("window")
            if (row.get("outcome") != "unresolved" or candidate is None
                    or pose_row is None or not isinstance(window, list)
                    or len(window) != 4):
                continue
            validation = candidate.get("validation_mismatch")
            candidates.append((
                float("inf") if validation is None else float(validation),
                float(row.get("mismatch", 1.0)),
                -int(candidate.get("support", 0)),
                row, candidate, pose_row,
            ))
        for _validation, mismatch, _support, row, candidate, pose_row in (
                sorted(candidates)[:per_region]):
            y, x, h, w = (int(value) for value in row["window"])
            pose = pilotsearch.AffinePose(
                origin_yx=tuple(float(v) for v in pose_row["origin_yx"]),
                jacobian_yx=tuple(tuple(float(v) for v in values)
                                  for values in pose_row["jacobian_yx"]),
                angle_deg=float(pose_row["angle_deg"]),
                pitch_px=float(pose_row["pitch_px"]),
                phase_yx=tuple(float(v) for v in pose_row["phase_yx"]),
            )
            hints.append(pilotsearch.PlacedWindow(
                region_index=int(raw_region),
                window=pilotsearch.Window(
                    y, x, h, w, int(candidate.get("support", 0)),
                    int(row.get("depth", 0))),
                page=int(candidate["page"]),
                origin_yx=tuple(int(v) for v in candidate["origin_yx"]),
                rot_k=int(candidate["rot_k"]), method="lower_runner_up",
                mismatch=float(mismatch),
                validation_mismatch=float(
                    candidate.get("validation_mismatch", 1.0)),
                rival_mismatch=(None if candidate.get("rival_mismatch")
                                is None else
                                float(candidate["rival_mismatch"])),
                support=int(candidate.get("support", 0)), pose=pose,
                elapsed_s=0.0, component=-1, rival_searched=True,
                scan_id=str(result.diagnostics.get("scan_id", "")),
                diagnostics={
                    "hint_kind": "retained_runner_up",
                    "mismatch_gap": candidate.get("mismatch_gap"),
                }))
    return hints


def continuation_hints(
    previous: pilotsearch.SearchResult,
    source_level: scale_space.ScaleLevel,
    target_level: scale_space.ScaleLevel,
    *,
    runner_up_per_region: int = 2,
) -> tuple[pilotsearch.PlacedWindow, ...]:
    """Transfer accepted poses plus a bounded losing tail to a finer view."""
    if target_level.ppc <= source_level.ppc:
        raise ValueError("continuation target must be finer than its source")
    accepted = [
        _copy_hint(row, source_level, target_level,
                   method="lower_accepted")
        for row in previous.placements
    ]
    runners = [
        _copy_hint(row, source_level, target_level,
                   method="lower_runner_up")
        for row in _runner_up_hints(
            previous, per_region=runner_up_per_region)
    ]
    return tuple(accepted + runners)


def _label_field(
    certificates: Mapping[TileKey, Certificate],
    baseline: receiver.ReceiverSession,
) -> feedback.LabelField:
    """Regenerate exact printed labels from the lower-level certificates."""
    shape = tuple(int(v) for v in baseline.decode.spec.page_cells_yx)
    values = {
        int(page): np.full(shape, -1, np.int8)
        for page in baseline.envelope.pages
    }
    inverse = payloaddec._payload_inverse(
        baseline.decode.spec, baseline.decode.seed)
    pim = compose.payload_index_map(
        baseline.decode.spec, baseline.decode.seed)
    keystream = {
        int(page): compose.payload_keystream(
            baseline.decode.spec, baseline.decode.seed, int(page))
        for page in baseline.envelope.pages
    }
    ids: dict[TileKey, str] = {}
    indices: dict[TileKey, np.ndarray] = {}
    for key, certificate in sorted(certificates.items()):
        page, ty, tx = key
        if page not in values:
            continue
        mask = baseline.decode.shorten_mask((ty, tx))
        bits = np.asarray(certificate.user_bits, np.uint8).ravel()
        _word, transmitted = ldpc.encode_tile(
            bits, mask, baseline.decode.ldpc_spec)
        pidx = ldpc._tile_payload_indices(
            (ty, tx), baseline.decode.spec, baseline.decode.seed, mask)
        cells = inverse[pidx]
        printed = (
            np.asarray(transmitted, np.uint8)
            ^ keystream[page][cells[:, 0], cells[:, 1]])
        old = values[page][cells[:, 0], cells[:, 1]]
        if np.any((old >= 0) & (old != printed)):
            raise payloaddec.FatalIntegrityError(
                f"conflicting printed labels at certified tile {key}")
        values[page][cells[:, 0], cells[:, 1]] = printed.astype(np.int8)
        ids[key] = certificate_id(key, bits)
        indices[key] = np.asarray(pidx, np.int64)
    return feedback.LabelField(
        values=values, certificate_ids=ids, payload_indices=indices,
        payload_index_map=pim, keystream_pages=keystream)


def refine_result_from_certificates(
    image: np.ndarray,
    result: pilotsearch.SearchResult,
    generation0: receiver.ScanRecord,
    certificates: Mapping[TileKey, Certificate],
    baseline: receiver.ReceiverSession,
    *,
    config: FeedbackConfig = FeedbackConfig(),
    on_window: Callable[[dict], None] | None = None,
) -> tuple[pilotsearch.SearchResult, dict]:
    """Bounded E024 pose-only proposal before final current-level emission.

    Discrete page/origin/orientation and the E022 pilot evidence stay frozen.
    A proposal is trained and held-out gated exactly as in E024.  If adopted,
    only the pose changes; the ordinary registered E023b detector is then run
    once from scratch on the newly sampled current-level pixels.
    """
    summary = {
        "eligible": 0, "adopted": 0, "windows": [],
        "certificate_frontier": len(certificates),
    }
    if not certificates or not result.placements:
        return result, summary
    field = _label_field(certificates, baseline)
    evidence_by_ordinal = {
        int(row.placement_ordinal): row
        for row in generation0.window_evidence
    }
    revised = copy.copy(result)
    revised.placements = list(result.placements)
    by_region: dict[int, list[int]] = {}
    for ordinal, placed in enumerate(result.placements):
        by_region.setdefault(int(placed.region_index), []).append(ordinal)
    for region_index in sorted(by_region):
        ordinals = by_region[region_index]
        crop = payloaddec.region_extent_crop(
            image, [result.placements[index] for index in ordinals])
        for ordinal in ordinals:
            placed = result.placements[ordinal]
            generation = evidence_by_ordinal[ordinal]
            labels = feedback.collect_window_labels(
                placed, field, baseline, config)
            pose, _means, metrics = feedback.refine_pose_on_labels(
                crop, placed, generation, labels, config,
                search_config=baseline.envelope.search_config)
            eligible = bool(metrics.get("eligible", False))
            adopted = pose is not None and bool(metrics.get("adopted", False))
            summary["eligible"] += int(eligible)
            summary["adopted"] += int(adopted)
            dependencies = sorted({
                key for key in labels.tile_keys if key is not None
            })
            summary["windows"].append({
                "ordinal": ordinal, "region_index": region_index,
                "eligible": eligible, "adopted": adopted,
                "reason": metrics.get("reason"),
                "dependencies": dependencies,
                "metrics": metrics,
            })
            if adopted:
                diagnostics = dict(placed.diagnostics)
                diagnostics["e023c_forward_pose_refine"] = {
                    "dependencies": dependencies,
                    "metrics": metrics,
                }
                revised.placements[ordinal] = replace(
                    placed, pose=pose, diagnostics=diagnostics)
            if on_window is not None:
                active_pose = pose if adopted else placed.pose
                corners = active_pose.points(np.asarray([
                    [0.0, 0.0],
                    [0.0, float(placed.window.w)],
                    [float(placed.window.h), 0.0],
                    [float(placed.window.h), float(placed.window.w)],
                ], np.float64))
                y0, x0 = np.min(corners, axis=0)
                y1, x1 = np.max(corners, axis=0)
                on_window({
                    "ordinal": int(ordinal + 1),
                    "queue_total": int(len(result.placements)),
                    "total": int(len(result.placements)),
                    "region_index": int(region_index),
                    "depth": int(placed.window.depth),
                    "stage": "pose_refine",
                    "outcome": "adopted" if adopted else str(
                        metrics.get("reason", "retained")),
                    "eligible": bool(eligible),
                    "adopted": bool(adopted),
                    "reason": metrics.get("reason"),
                    "angle_deg": float(active_pose.angle_deg),
                    "pitch_px": float(active_pose.pitch_px),
                    "pose_origin_yx": tuple(
                        float(value) for value in active_pose.origin_yx),
                    "jacobian_yx": tuple(
                        tuple(float(value) for value in row)
                        for row in active_pose.jacobian_yx),
                    "scan_bbox_yxhw_px": (
                        float(y0), float(x0), float(y1 - y0),
                        float(x1 - x0)),
                    "window_origin_yx_px": (
                        int(placed.window.y), int(placed.window.x)),
                    "window_shape_yx_cells": (
                        int(placed.window.h), int(placed.window.w)),
                })
    return revised if summary["adopted"] else result, summary


def process_level(
    *,
    image: np.ndarray,
    source_path: Path,
    level: scale_space.ScaleLevel,
    descriptor,
    pages: tuple[int, ...],
    capture_id: str,
    lane_session: receiver.ReceiverSession,
    lower_hints: Sequence[pilotsearch.PlacedWindow] = (),
    prior_certificates: Mapping[TileKey, Certificate] | None = None,
    bp_retry: bool = False,
    observer: Observer | None = None,
) -> LevelRun:
    """Run one complete E021 -> E022 -> E023b level transaction."""
    source = Path(source_path).resolve()
    source_sha, source_size = receiver.file_identity(source)
    if source_sha in lane_session.source_hashes:
        raise ValueError(f"derived view {source} is already in lane state")
    if capture_id in lane_session.capture_ids:
        raise ValueError(
            f"capture {capture_id!r} already exists in {lane_key(level)}")
    # Use physical capture identity as the scan voter identity at every
    # scale.  This lets the final pilot sheet combine scale observations
    # without pretending deterministic views are independent votes.
    scan_id = str(capture_id)
    timings: dict[str, float] = {}

    observer_s = 0.0

    def emit(event: str, **payload) -> None:
        nonlocal observer_s
        if observer is not None:
            t_observer = perf_counter()
            try:
                observer(event, {
                    "level": level, "lane": lane_key(level),
                    "scan_id": scan_id, "capture_id": capture_id,
                    **payload,
                })
            finally:
                observer_s += perf_counter() - t_observer

    started = perf_counter()
    emit("level_open", image=image)
    t0 = perf_counter()
    survey = platen.detect_payload_regions(image, dpi=float(level.dpi))
    timings["e021_s"] = perf_counter() - t0
    emit("e021_complete", image=image, survey=survey)

    def on_region(current: pilotsearch.SearchResult, region_index: int) -> None:
        emit("e022_region_complete", image=image, survey=survey,
             result=current, region_index=int(region_index))

    def on_window(
        current: pilotsearch.SearchResult,
        progress: pilotsearch.WindowProgress,
    ) -> None:
        emit("e022_window_progress", image=image, survey=survey,
             result=current, region_index=int(progress.region_index),
             window_progress=progress)

    t0 = perf_counter()
    observer_before = observer_s
    result = pilotsearch.search_survey(
        image, survey, descriptor, pages=pages,
        config=lane_session.envelope.search_config, scan_id=scan_id,
        scan_dpi=float(level.dpi), lower_hints=tuple(lower_hints),
        on_window=(on_window if observer is not None else None),
        on_region=(on_region if observer is not None else None))
    e022_wall = perf_counter() - t0
    timings["e022_s"] = float(result.timings.get(
        "total_s", e022_wall - (observer_s - observer_before)))
    emit("pilot_final", image=image, survey=survey, result=result)

    def make_record(active_result: pilotsearch.SearchResult,
                    phase: str) -> receiver.ScanRecord:
        t_payload = perf_counter()
        observer_before = observer_s
        payload_callback = (
            None if observer is None else
            lambda region, rows, all_rows: emit(
                phase, image=image, survey=survey, result=active_result,
                region_index=int(region), windows=len(rows)))
        context_callback = (
            None if observer is None else
            lambda region, fit: emit(
                "context_region_complete", image=image, survey=survey,
                result=active_result, region_index=int(region),
                context_fit=fit))
        record = receiver.make_scan_record(
            scan_id=scan_id, source_path=source,
            source_sha256=source_sha, source_size=source_size,
            dpi=float(level.dpi), image=image, capture_id=capture_id,
            survey=survey, result=active_result, descriptor=descriptor,
            pages=pages, rate_id=lane_session.envelope.rate_id,
            detector_profile=lane_session.envelope.detector_profile,
            on_payload_region=payload_callback,
            on_context=context_callback,
            timings=dict(timings))
        timings[f"{phase}_s"] = (
            perf_counter() - t_payload - (observer_s - observer_before))
        return record

    generation0 = make_record(result, "payload_generation0")
    certificate_frontier = (
        {} if prior_certificates is None else prior_certificates)
    refine_callback = (
        None if observer is None else
        lambda progress: emit(
            "pose_refine_window_progress", image=image, survey=survey,
            result=result, pose_refine_progress=progress))
    refined_result, refine_summary = refine_result_from_certificates(
        image, result, generation0, certificate_frontier, lane_session,
        on_window=refine_callback)
    if refined_result is result:
        record = generation0
    else:
        emit("pose_refine_adopted", image=image, survey=survey,
             result=refined_result, feedback=refine_summary)
        record = make_record(refined_result, "payload_refined")
        result = refined_result
    emit("owner_frozen", image=image, survey=survey, result=result,
         record=record, feedback=refine_summary)
    # A certificate from a coarser/currently committed lane is final for the
    # global objective.  Preserve this level's complete frozen emission for
    # replay and future independent captures, but do not spend LDPC/CRC work
    # re-decoding those already solved tile keys.
    attempt_ordinal = 0

    def on_attempt(
        view_session: receiver.ReceiverSession,
        attempt: receiver.TileAttempt,
    ) -> None:
        nonlocal attempt_ordinal
        attempt_ordinal += 1
        emit("ldpc_attempt", image=image, survey=survey, result=result,
             record=record, lane_session=view_session, attempt=attempt,
             attempt_ordinal=int(attempt_ordinal),
             feedback=refine_summary)

    working, counts = receiver.apply_scan(
        lane_session, record, skip_tiles=certificate_frontier,
        on_attempt=(on_attempt if observer is not None else None))
    if bp_retry:
        retry_ordinal = 0

        def on_retry_attempt(
            view_session: receiver.ReceiverSession,
            attempt: receiver.TileAttempt,
        ) -> None:
            nonlocal retry_ordinal
            retry_ordinal += 1
            emit("bp_retry_attempt", image=image, survey=survey,
                 result=result, record=record, lane_session=view_session,
                 attempt=attempt, attempt_ordinal=int(retry_ordinal),
                 feedback=refine_summary)

        working, retry = receiver.retry_failed_bp(
            working, skip_tiles=certificate_frontier,
            on_attempt=(
                on_retry_attempt if observer is not None else None))
        counts = dict(counts)
        counts["retry150"] = retry
        emit("bp_retry_complete", image=image, survey=survey, result=result,
             record=record, lane_session=working, retry=retry,
             feedback=refine_summary)
    # apply_scan binds the semantic residual-NeedMap marker to its stored
    # immutable ScanRecord.  Return that exact record, not the pre-bind copy.
    record = working.scans[-1]
    timings["total_s"] = perf_counter() - started - observer_s
    record.timings.update(timings)
    emit("level_complete", image=image, survey=survey, result=result,
         record=record, lane_session=working, counts=counts,
         feedback=refine_summary)
    return LevelRun(
        level=level, lane_key=lane_key(level), source_path=source,
        source_sha256=source_sha, source_size=source_size, survey=survey,
        result=result, record=record, lane_session=working,
        apply_counts=counts, feedback=refine_summary, timings=timings)


def retry_lane_frontiers(
    lanes: Mapping[str, receiver.ReceiverSession],
    *,
    observer: Observer | None = None,
) -> tuple[dict[str, receiver.ReceiverSession], dict]:
    """Explicit one-time max-150 retry for every lane's current frontier."""
    updated = dict(lanes)
    reports = {}
    for name in sorted(updated):
        session, report = receiver.retry_failed_bp(updated[name])
        updated[name] = session
        reports[name] = report
        if observer is not None:
            observer("bp_retry_lane", {"lane": name, "report": report})
    return updated, reports


def certificate_arrays(
    portfolio: Mapping[TileKey, Certificate],
) -> dict[TileKey, np.ndarray]:
    """Read-only adapter for the outer fountain completion policy."""
    return {
        key: np.asarray(row.user_bits, np.uint8).copy()
        for key, row in portfolio.items()
    }
