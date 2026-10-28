#!/usr/bin/env python
"""Persistent coarse-to-fine E021/E022/E023b scale-space receiver.

Each physical capture is derived directly into a short pixels-per-cell
ladder.  Levels run coarse to native.  Per-scale E023b lanes accumulate only
independent physical captures; correlated scales never sum LLR evidence.
Only matching LDPC syndrome+CRC certificates enter the global portfolio.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import pickle
import sys
from dataclasses import asdict, replace
from fractions import Fraction
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import cascade  # noqa: E402
import cascade_state  # noqa: E402
import completion  # noqa: E402
import e023c_diag  # noqa: E402
import scale_space  # noqa: E402
from paperholo import (payloaddec, pilotcombine, pilotsearch, receiver,  # noqa:E402
                       receiverdiag)
from paperholo.formats import FORMAT_REGISTRY  # noqa: E402


DEFAULT_STATE = HERE / "build" / "session_e023c.pkl"
DEFAULT_OUT = HERE / "build" / "session_e023c.png"
DEFAULT_DIAG = HERE / "build" / "diag"

DIAG_EVENT_NAMES = {
    "pilot_final": "pilot_level_final",
    "payload_generation0": "payload_region_emitted",
    "payload_refined": "payload_region_emitted",
    "owner_frozen": "level_owner_frozen",
    "bp_retry_lane": "ldpc_batch",
    "level_portfolio_complete": "level_complete",
    "capture_level_committed": "capture_committed",
}

DIAG_FORCE_RENDER_EVENTS = frozenset({
    "level_open", "e021_complete", "e022_region_complete", "pilot_final",
    "context_region_complete", "payload_generation0", "payload_refined",
    "pose_refine_adopted", "owner_frozen", "bp_retry_complete",
    "level_complete", "level_portfolio_complete", "fountain_check",
    "capture_level_committed",
})


def resolve_format(format_id: str):
    for descriptor in FORMAT_REGISTRY:
        if descriptor.format_id == format_id:
            return descriptor
    names = ", ".join(row.format_id for row in FORMAT_REGISTRY)
    raise ValueError(f"unknown format {format_id!r}; choose one of: {names}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def implementation_fingerprints() -> tuple[tuple[str, str], ...]:
    """Pin the complete numerical and completion-policy source surface."""
    files = {
        "e023c:run": HERE / "run_e023c.py",
        "e023c:cascade": HERE / "cascade.py",
        "e023c:state": HERE / "cascade_state.py",
        "e023c:completion": HERE / "completion.py",
        "e023c:scale_space": HERE / "scale_space.py",
        "paperholo:feedback": ROOT / "src/paperholo/feedback.py",
        "paperholo:feedbackstate": ROOT / "src/paperholo/feedbackstate.py",
        "paperholo:fountain": ROOT / "src/paperholo/fountain.py",
        "production:score_e023b": (
            ROOT / "experiments/023b-integrated-receiver/score_e023b.py"),
    }
    rows = [(name, _sha256_file(path)) for name, path in files.items()]
    # ReceiverSession.create() pins this same transitive E021--E023b closure
    # inside every scale lane.  Pin it at the outer envelope too, including
    # levels which have not yet been materialised at a resume boundary.
    rows.extend(
        (f"lower:{name}", digest)
        for name, digest in receiver.implementation_fingerprints())
    return tuple(rows)


def _validate_manifest(manifest, descriptor, pages: tuple[int, ...]) -> None:
    """Require the stop oracle to describe this exact printed format."""
    registered = descriptor.spec()
    supplied = manifest.descriptor.spec()
    if (
        manifest.descriptor.format_id != descriptor.format_id
        or manifest.descriptor.seed != descriptor.seed
        or supplied != registered
        or manifest.descriptor.ldpc_rate != descriptor.ldpc_rate
    ):
        raise ValueError(
            "manifest format/layout/encoding/geometry/rate differs from "
            "--format")
    if tuple(pages) != tuple(range(manifest.volume.n_pages)):
        raise ValueError(
            "--pages must enumerate every manifest volume page")


def _fraction_list(value: str) -> tuple[Fraction, ...]:
    try:
        values = tuple(Fraction(part.strip()) for part in value.split(","))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("--ppc-levels must be comma-separated rationals") from exc
    if not values or any(row <= 0 for row in values):
        raise ValueError("--ppc-levels must contain positive values")
    return values


def make_schedule(
    native_dpi: float,
    cell_dots: int,
    *,
    minimum_ppc: str,
    explicit_ppc: str | None,
) -> scale_space.ScaleSchedule:
    if explicit_ppc is None:
        return scale_space.ScaleSchedule.auto(
            native_dpi, cell_dots, Fraction(minimum_ppc))
    native_ppc = scale_space.native_pixels_per_cell(native_dpi, cell_dots)
    values = list(_fraction_list(explicit_ppc))
    if any(row > native_ppc for row in values):
        raise ValueError("--ppc-levels cannot upsample above native ppc")
    if native_ppc not in values:
        values.append(native_ppc)
    values = sorted(set(values))
    if tuple(values) != tuple(sorted(values)) or values[-1] != native_ppc:
        raise ValueError("--ppc-levels must increase through native ppc")
    dpi = Fraction(str(float(native_dpi)))
    levels = tuple(
        scale_space.ScaleLevel(
            index=index, ppc=ppc, dpi=ppc * 600 / int(cell_dots),
            transform=scale_space.AreaPixelTransform(native_ppc / ppc))
        for index, ppc in enumerate(values))
    return scale_space.ScaleSchedule(
        native_dpi=dpi, cell_factor=int(cell_dots),
        minimum_ppc=values[0], native_ppc=native_ppc, levels=levels)


def _scale_specs(
    schedule: scale_space.ScaleSchedule,
) -> tuple[cascade_state.ScaleSpec, ...]:
    rows = []
    for level in schedule.levels:
        scale = level.transform.source_per_output
        rows.append(cascade_state.ScaleSpec(
            level_id=level.label, ordinal=level.index,
            target_ppc=float(level.ppc), effective_dpi=float(level.dpi),
            native_per_view_yx=(
                (scale.numerator, scale.denominator),
                (scale.numerator, scale.denominator)),
            resampler_id=("e018-integer-box-v1" if
                          level.transform.is_integer_box else
                          "rational-area-v1")))
    return tuple(rows)


def _make_envelope(
    descriptor,
    pages: tuple[int, ...],
    native_dpi: float,
    schedule: scale_space.ScaleSchedule,
    detector_profile: str,
    config: pilotsearch.SearchConfig,
    manifest_sha256: str | None,
    run_policy: dict,
) -> cascade_state.CascadeEnvelope:
    spec = descriptor.spec()
    policy_sha256 = hashlib.sha256(json.dumps(
        run_policy, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("ascii")).hexdigest()
    return cascade_state.CascadeEnvelope(
        algorithm_id=cascade_state.ALGORITHM_ID,
        format_id=descriptor.format_id, seed=descriptor.seed,
        cell_dots=int(descriptor.cell_dots),
        page_cells_yx=tuple(int(v) for v in spec.page_cells_yx),
        pages=pages, native_dpi=float(native_dpi),
        rate_id=str(descriptor.ldpc_rate),
        detector_profile=detector_profile,
        search_config_sha256=receiver.search_config_digest(config),
        scale_plan=_scale_specs(schedule),
        implementation_sha256=(
            implementation_fingerprints()
            + (("run_policy", policy_sha256),)),
        manifest_sha256=manifest_sha256)


def _source_record(
    path: Path,
    capture_id: str,
    image: np.ndarray,
    native_dpi: float,
) -> cascade_state.SourceIdentity:
    sha256, size = receiver.file_identity(path)
    shape = tuple(int(v) for v in image.shape[:2])
    identity = cascade_state.source_identity(
        source_sha256=sha256, source_size=size, image_shape=shape,
        image_dtype=str(np.asarray(image).dtype), native_dpi=native_dpi)
    return cascade_state.SourceIdentity(
        source_id=identity, capture_id=str(capture_id),
        source_path=str(path.resolve()), source_sha256=sha256,
        source_size=size, image_shape=shape,
        image_dtype=str(np.asarray(image).dtype), native_dpi=native_dpi)


def _fork_session(
    session: cascade_state.CascadeSession,
) -> cascade_state.CascadeSession:
    working = copy.copy(session)
    working.captures = list(session.captures)
    working.decoder_lanes = dict(session.decoder_lanes)
    working.lane_sessions = dict(session.lane_sessions)
    working.dependency_sets = dict(session.dependency_sets)
    working.certificate_union = dict(session.certificate_union)
    working.attempts = list(session.attempts)
    working.attempt_ids = set(session.attempt_ids)
    working.fatal = list(session.fatal)
    working.observer_state = dict(session.observer_state)
    working.timings = dict(session.timings)
    return working


def _materialize_view(
    native: np.ndarray,
    native_path: Path,
    native_sha256: str,
    level: scale_space.ScaleLevel,
    cache_dir: Path,
) -> tuple[np.ndarray, Path]:
    if level.is_native:
        return native, native_path.resolve()
    directory = cache_dir / native_sha256[:24]
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{level.label}.png"
    derived = scale_space.area_decimate(native, level.transform)
    tmp = target.with_name(f".{target.stem}.{os.getpid()}.tmp.png")
    try:
        Image.fromarray(derived, mode="L").save(
            tmp, format="PNG", optimize=False, compress_level=6)
        replay = receiver.load_image(tmp)
        if not np.array_equal(replay, derived):
            raise ValueError("derived scale cache did not round-trip exactly")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()
    return derived, target.resolve()


def _receiver_lane(
    session: cascade_state.CascadeSession,
    level: scale_space.ScaleLevel,
    descriptor,
    pages: tuple[int, ...],
    config: pilotsearch.SearchConfig,
) -> tuple[str, receiver.ReceiverSession]:
    lane_id = cascade_state.lane_identity(level.label, "primary")
    if lane_id not in session.lane_sessions:
        lane = receiver.ReceiverSession.create(
            descriptor, pages, float(level.dpi),
            detector_profile=session.envelope.detector_profile,
            search_config=config)
        return lane_id, lane
    lane = session.lane_sessions[lane_id]
    if not isinstance(lane, receiver.ReceiverSession):
        raise ValueError(f"lane {lane_id} is not an E023b receiver session")
    lane.validate(
        descriptor, pages, float(level.dpi),
        detector_profile=session.envelope.detector_profile,
        search_config=config)
    return lane_id, lane


def _state_portfolio(
    session: cascade_state.CascadeSession,
) -> dict[cascade.TileKey, cascade.Certificate]:
    return {
        tuple(key): cascade.Certificate(
            key=tuple(key), user_bits=row.user_bits(),
            lanes=tuple(row.provenance.get("lanes", (row.born_lane_id,))),
            sources=tuple(row.provenance.get("sources", ())))
        for key, row in session.certificate_union.items()
    }


def _feedback_dependency_keys(level_run: cascade.LevelRun) -> set[cascade.TileKey]:
    keys = set()
    for row in level_run.feedback.get("windows", ()):
        if not row.get("adopted"):
            continue
        keys.update(tuple(int(v) for v in key)
                    for key in row.get("dependencies", ()))
    return keys


def _sync_attempts_and_certificates(
    session: cascade_state.CascadeSession,
    *,
    lane_id: str,
    level_run: cascade.LevelRun,
    attempt_start: int,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    prior_by_key = dict(session.certificate_union)
    dependency_keys = _feedback_dependency_keys(level_run)
    attempt_ids: list[str] = []
    new_certificate_ids: list[str] = []
    lane = level_run.lane_session
    scans_by_id = {scan.scan_id: scan for scan in lane.scans}
    for source_attempt in lane.attempts[attempt_start:]:
        key = (int(source_attempt.page), *map(int, source_attempt.tile_yx))
        dependency_ids = tuple(sorted(
            prior_by_key[dep].certificate_id
            for dep in dependency_keys
            if dep != key and dep in prior_by_key))
        dependency_set_id = cascade_state.intern_dependency_set(
            session, dependency_ids)
        state_attempt_id = cascade_state.attempt_identity(
            key, level_run.record.capture_id, level_run.level.label,
            lane_id, source_attempt.stage, source_attempt.decoder_profile,
            source_attempt.evidence_digest, dependency_set_id)
        if state_attempt_id in session.attempt_ids:
            continue

        output_id = None
        global_new = False
        if source_attempt.state == "certified":
            outcome = lane.decode.tiles[key]
            bits = np.asarray(outcome.user_bits, np.uint8).ravel()
            identity, bits_sha, packed = cascade_state.certificate_identity(
                session.envelope.format_id, session.envelope.seed, key,
                session.envelope.rate_id, bits)
            old = session.certificate_union.get(key)
            if old is None:
                global_new = True
                output_id = identity
                session.certificate_union[key] = cascade_state.PayloadCertificate(
                    certificate_id=identity, tile_key=key,
                    rate_id=session.envelope.rate_id,
                    n_user_bits=int(bits.size), packed_user_bits=packed,
                    user_bits_sha256=bits_sha,
                    origin_attempt_id=state_attempt_id,
                    born_capture_id=level_run.record.capture_id,
                    born_level_id=level_run.level.label,
                    born_lane_id=lane_id,
                    dependency_set_id=dependency_set_id,
                    provenance={
                        "lanes": [lane_id],
                        "sources": [str(source_attempt.source)],
                        "e023b_attempt_id": source_attempt.attempt_id,
                    })
                new_certificate_ids.append(identity)
            else:
                if old.certificate_id != identity:
                    raise payloaddec.FatalIntegrityError(
                        f"conflicting E023c certificate for {key}")
                output_id = old.certificate_id
                provenance = dict(old.provenance)
                provenance["lanes"] = list(dict.fromkeys(
                    list(provenance.get("lanes", ())) + [lane_id]))
                provenance["sources"] = list(dict.fromkeys(
                    list(provenance.get("sources", ()))
                    + [str(source_attempt.source)]))
                session.certificate_union[key] = replace(
                    old, provenance=provenance)

        components = []
        for scan_id, component_capture_id in zip(
                source_attempt.scan_ids, source_attempt.capture_ids,
                strict=True):
            scan = scans_by_id.get(scan_id)
            if scan is None or key not in scan.tile_evidence_digests:
                raise ValueError(
                    f"E023b attempt {source_attempt.attempt_id} lost "
                    f"component evidence for {scan_id}/{key}")
            components.append((
                str(component_capture_id),
                str(scan.tile_evidence_digests[key])))

        record = cascade_state.AttemptRecord(
            attempt_id=state_attempt_id, tile_key=key,
            capture_id=level_run.record.capture_id,
            level_id=level_run.level.label, lane_id=lane_id,
            stage=str(source_attempt.stage), source=str(source_attempt.source),
            decoder_profile=str(source_attempt.decoder_profile),
            numeric_evidence_sha256=str(source_attempt.evidence_digest),
            component_sha256=tuple(components),
            dependency_set_id=dependency_set_id,
            state=str(source_attempt.state),
            decoder_invoked=bool(source_attempt.decoder_invoked),
            k_eff=int(source_attempt.k_eff),
            n_nonshort=int(source_attempt.n_nonshort),
            n_informative=int(source_attempt.n_informative),
            coverage=float(source_attempt.coverage),
            n_iters=int(source_attempt.n_iters),
            syndrome_ok=source_attempt.syndrome_ok,
            crc_ok=source_attempt.crc_ok,
            n_erased=int(source_attempt.n_erased),
            certified_new=global_new,
            output_certificate_id=output_id,
            metrics={
                "e023b_attempt_id": source_attempt.attempt_id,
                "scan_ids": list(source_attempt.scan_ids),
                "capture_ids": list(source_attempt.capture_ids),
            })
        session.attempts.append(record)
        session.attempt_ids.add(record.attempt_id)
        attempt_ids.append(record.attempt_id)
    return tuple(attempt_ids), tuple(new_certificate_ids)


def _pilot_summary(
    session: cascade_state.CascadeSession,
    descriptor,
) -> cascade_state.PilotKnowledgeSummary:
    by_key: dict[tuple[int, int, int], list] = {}
    contributing = []
    substrate = []
    for lane_id, meta in sorted(session.decoder_lanes.items(),
                                key=lambda item: item[1].level_id):
        lane = session.lane_sessions[lane_id]
        if not isinstance(lane, receiver.ReceiverSession) or not lane.scans:
            continue
        contributing.append(meta.level_id)
        for scan in lane.scans:
            for key, tile in scan.result.tiles.items():
                by_key.setdefault(tuple(key), []).append(tile)
                substrate.append((
                    meta.level_id, scan.capture_id, tuple(key),
                    tile.observed_sites, tile.bch_ok, tile.bch_erasures))
    combined = _combined_pilots(session, descriptor)
    total = int(np.prod(descriptor.spec().page_tiles_yx))
    pages = []
    for page in session.envelope.pages:
        keys = {key for key in combined.tiles if key[0] == page}
        solved = sum(combined.tiles[key].bch_ok is True for key in keys)
        conflicted = sum(combined.tiles[key].bch_ok is False for key in keys)
        addressed = len(keys) - solved - conflicted
        pages.append(cascade_state.PilotPageSummary(
            page=int(page), total=total, unseen=total - len(keys),
            addressed=addressed, bch_solved=solved,
            conflicted=conflicted))
    return cascade_state.PilotKnowledgeSummary(
        pages=tuple(pages),
        knowledge_sha256=cascade_state.semantic_digest(substrate),
        contributing_level_ids=tuple(dict.fromkeys(contributing)))


def _completion_check(
    report: dict | None,
    certificate_digest: str,
    manifest_sha256: str | None,
) -> cascade_state.CompletionCheck | None:
    if report is None:
        return None
    payload = report["payload"]
    fountain = report["fountain"]
    if payload["verified"]:
        status = "volume_verified"
    elif payload["recovered"]:
        status = "hash_mismatch"
    else:
        status = "insufficient"
    return cascade_state.CompletionCheck(
        status=status, certificate_union_sha256=certificate_digest,
        manifest_sha256=manifest_sha256,
        block_rank=tuple(
            (str(row["block"]), int(row["rank"]), int(row["needed"]))
            for row in fountain["blocks"]),
        shortfall=int(fountain["rank_shortfall"]),
        volume_sha256=payload["actual_sha256"],
        expected_volume_sha256=report["manifest"]["expected_data_sha256"],
        details=report)


def _complete_level_record(
    session: cascade_state.CascadeSession,
    level_run: cascade.LevelRun,
    base: cascade_state.LevelRecord,
    *,
    input_digest: str,
    attempt_ids: tuple[str, ...],
    new_certificate_ids: tuple[str, ...],
    completion_report: dict | None,
    lower_hint_count: int,
) -> cascade_state.LevelRecord:
    output_digest = cascade_state.certificate_union_digest(
        session.certificate_union)
    pilot = _pilot_summary(session, resolve_format(
        session.envelope.format_id))
    artifacts = {
        "lane_key": level_run.lane_key,
        "scan_id": level_run.record.scan_id,
        "view_path": str(level_run.source_path),
        "survey_regions": len(level_run.survey.regions),
        "placements": len(level_run.result.placements),
        "pilot_tiles": len(level_run.result.tiles),
        "lower_hint_count": int(lower_hint_count),
        "feedback": level_run.feedback,
        "apply_counts": level_run.apply_counts,
        "certificate_count": len(session.certificate_union),
    }
    row = replace(
        base, status="complete", view_sha256=level_run.source_sha256,
        view_shape=tuple(int(v) for v in level_run.record.image_shape),
        view_dtype=str(level_run.record.image_dtype),
        input_certificate_sha256=input_digest,
        output_certificate_sha256=output_digest,
        pilot_knowledge=pilot, attempt_ids=attempt_ids,
        new_certificate_ids=new_certificate_ids,
        completion=_completion_check(
            completion_report, output_digest,
            session.envelope.manifest_sha256),
        timings=dict(level_run.timings))
    row = cascade_state.with_level_artifacts(row, artifacts)
    complete_checkpoint = cascade_state.make_checkpoint(
        ordinal=0, stage="level_complete",
        input_certificate_sha256=input_digest,
        output_certificate_sha256=output_digest,
        pilot_knowledge_sha256=pilot.knowledge_sha256,
        artifacts_sha256=row.artifacts_sha256,
        attempt_ids=attempt_ids, new_certificate_ids=new_certificate_ids,
        statistics={
            "placements": len(level_run.result.placements),
            "certificates": len(session.certificate_union)})
    checkpoints = [complete_checkpoint]
    if completion_report is not None:
        checkpoints.append(cascade_state.make_checkpoint(
            ordinal=1, stage="fountain_check",
            input_certificate_sha256=input_digest,
            output_certificate_sha256=output_digest,
            pilot_knowledge_sha256=pilot.knowledge_sha256,
            artifacts_sha256=row.artifacts_sha256,
            attempt_ids=attempt_ids,
            new_certificate_ids=new_certificate_ids,
            statistics={
                "rank": completion_report["fountain"]["rank"],
                "shortfall": completion_report["fountain"][
                    "rank_shortfall"],
                "verified": completion_report["payload"]["verified"],
            }))
    return replace(row, checkpoints=tuple(checkpoints))


def _combined_pilots(
    session: cascade_state.CascadeSession,
    descriptor,
    *,
    current: tuple[str, int, pilotsearch.SearchResult] | None = None,
) -> pilotsearch.SearchResult:
    parts = []
    for lane_id, meta in sorted(session.decoder_lanes.items(),
                                key=lambda item: item[1].level_id):
        lane = session.lane_sessions[lane_id]
        if not isinstance(lane, receiver.ReceiverSession):
            continue
        for scan in lane.scans:
            parts.append(pilotcombine.SearchResultPart(
                scan.capture_id, scan.region_count, scan.result))
    if current is not None:
        parts.append(pilotcombine.SearchResultPart(*current))
    return pilotcombine.combine_search_results(
        parts, descriptor, pages=session.envelope.pages,
        decode_words=True)


def _portfolio_view(
    lane: receiver.ReceiverSession,
    session: cascade_state.CascadeSession,
) -> receiver.ReceiverSession:
    view = lane.fork()
    for key, certificate in session.certificate_union.items():
        out = view.decode.outcome(key[0], key[1:])
        if out.state == "certified" and not np.array_equal(
                out.user_bits, certificate.user_bits()):
            raise payloaddec.FatalIntegrityError(
                f"diagnostic certificate conflict at {key}")
        out.state = "certified"
        out.user_bits = certificate.user_bits()
        out.certified_by = "e023c-certificate-portfolio"
    return view


def _contact_png(frames: dict[int, bytes]) -> bytes:
    """Return one PNG containing every logical-page diagnostic frame."""
    ordered = []
    for page, payload in sorted(frames.items()):
        with Image.open(io.BytesIO(payload)) as source:
            ordered.append((page, source.convert("RGB").copy()))
    if not ordered:
        raise ValueError("cannot compose an empty diagnostic page set")
    if len(ordered) == 1:
        return bytes(frames[ordered[0][0]])
    width = max(image.width for _page, image in ordered)
    height = sum(image.height for _page, image in ordered)
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    y = 0
    for _page, image in ordered:
        canvas.paste(image, (0, y))
        y += image.height
    stream = io.BytesIO()
    canvas.save(stream, format="PNG")
    return stream.getvalue()


def _diagnostic_event_status(
    event: str,
    payload: dict,
) -> tuple[dict, object | None]:
    """Return detached, compact browser status and an A/B pose overlay."""
    extra: dict = {}
    pilot_progress = None
    window = payload.get("window_progress")
    if window is not None:
        row = asdict(window)
        pilot_progress = row
        angle = row.get("angle_deg")
        pitch = row.get("pitch_px")
        routes = ",".join(row.get("attempted_routes", ())) or "pose"
        stage = {
            "window_open": "pose/FFT fit",
            "pose_fitted": "pose fitted / sample",
            "window_complete": "window complete",
        }.get(row["stage"], row["stage"])
        detail = (
            f"region {row['region_index']} · window "
            f"{row['ordinal']}/{row['queue_total']} depth {row['depth']} · "
            f"{stage} · route {routes} · anchors {row['anchors']} · "
            f"placements {row['placements']}")
        if angle is not None:
            detail += f" · angle {float(angle):+.3f}°"
        if pitch is not None:
            detail += f" · pitch {float(pitch):.4f}px"
        if row.get("outcome"):
            detail += f" · {row['outcome']}"
        extra.update({"detail": detail, "window": row})
        return extra, pilot_progress

    refine = payload.get("pose_refine_progress")
    if refine is not None:
        row = dict(refine)
        pilot_progress = row
        detail = (
            f"certificate feedback · region {row['region_index']} · window "
            f"{row['ordinal']}/{row['total']} · "
            f"{'adopted' if row['adopted'] else 'retained'} · "
            f"{row.get('reason')} · angle {row['angle_deg']:+.3f}° · "
            f"pitch {row['pitch_px']:.4f}px")
        extra.update({"detail": detail, "pose_refine": row})
        return extra, pilot_progress

    attempt = payload.get("attempt")
    if attempt is not None:
        key = (int(attempt.page), *(int(v) for v in attempt.tile_yx))
        row = {
            "ordinal": int(payload.get("attempt_ordinal", 0)),
            "tile": list(key),
            "stage": str(attempt.stage),
            "state": str(attempt.state),
            "decoder_profile": str(attempt.decoder_profile),
            "decoder_invoked": bool(attempt.decoder_invoked),
            "coverage": float(attempt.coverage),
            "informative": int(attempt.n_informative),
            "nonshort": int(attempt.n_nonshort),
            "k_eff": int(attempt.k_eff),
            "iterations": int(attempt.n_iters),
            "syndrome_ok": attempt.syndrome_ok,
            "crc_ok": attempt.crc_ok,
            "certified_new": bool(attempt.certified_new),
        }
        kind = "BP retry" if event == "bp_retry_attempt" else "LDPC"
        detail = (
            f"{kind} #{row['ordinal']} · tile p{key[0]}/"
            f"{key[1]},{key[2]} · {row['stage']} → {row['state']} · "
            f"coverage {row['coverage']:.3f} · informative "
            f"{row['informative']}/{row['nonshort']} · "
            f"k_eff {row['k_eff']} · iterations {row['iterations']}")
        if row["syndrome_ok"] is not None:
            detail += f" · syndrome {row['syndrome_ok']}"
        if row["crc_ok"] is not None:
            detail += f" · CRC {row['crc_ok']}"
        extra.update({"detail": detail, "ldpc": row})
        return extra, None

    fit = payload.get("context_fit")
    if fit is not None:
        valid = (float(fit.n_context_valid_cells)
                 / max(1, int(fit.n_context_cells)))
        row = {
            "region_index": int(fit.region_index),
            "eligible": bool(fit.eligible),
            "adopted": bool(fit.adopted),
            "reason": str(fit.reason),
            "valid_fraction": valid,
            "windows": int(fit.n_windows),
            "refused_windows": int(fit.n_refused_windows),
        }
        extra.update({
            "detail": (
                f"context/PAVA region {row['region_index']} · "
                f"eligible {row['eligible']} · adopted {row['adopted']} · "
                f"{row['reason']} · valid {valid:.3f} · "
                f"windows {row['windows']} refused "
                f"{row['refused_windows']}"),
            "context": row,
        })
        return extra, None

    survey = payload.get("survey")
    if event == "level_open":
        extra["detail"] = "opening scale raster; E021 segmentation next"
    elif event == "e021_complete" and survey is not None:
        extra["detail"] = (
            f"E021 found {len(survey.regions)} region(s) · measured pitch "
            f"{survey.cell_pitch_px if survey.cell_pitch_px is not None else '?'} px")
    elif event == "pilot_final":
        result = payload.get("result")
        extra["detail"] = (
            f"E022 complete · {len(result.placements)} placements · "
            f"{len(result.tiles)} addressed pilot tiles")
    elif event in {"payload_generation0", "payload_refined"}:
        extra["detail"] = (
            f"payload sampling region {payload.get('region_index', '?')} · "
            f"{payload.get('windows', '?')} windows")
    elif event == "owner_frozen":
        record = payload.get("record")
        extra["detail"] = (
            f"payload owner field frozen · {len(record.work_plan)} potential "
            "LDPC tiles")
    elif event == "bp_retry_complete":
        retry = payload.get("retry", {})
        extra["detail"] = (
            f"BP retry complete · attempted {retry.get('attempted', 0)} · "
            f"certified {retry.get('certified', 0)}")
    elif payload.get("completion") is not None:
        row = payload["completion"]
        extra["detail"] = (
            f"volume check · rank {row.get('rank')} · shortfall "
            f"{row.get('shortfall')} · verified {row.get('verified')}")
    else:
        extra["detail"] = str(DIAG_EVENT_NAMES.get(event, event))
    return extra, pilot_progress


def _active_ldpc_progress(
    record: receiver.ScanRecord | None,
    event: str,
    attempt: receiver.TileAttempt | None,
) -> receiverdiag.DiagProgress | None:
    if record is None:
        return None
    progress = receiverdiag.work_plan_progress(record, phase=event)
    if attempt is not None:
        key = (int(attempt.page), *(int(value) for value in attempt.tile_yx))
        progress.active_tiles.add(key)
        if attempt.decoder_invoked:
            progress.attempt_ready.add(key)
        progress.phase = (
            f"latest {event} p{key[0]}/{key[1]},{key[2]} "
            f"{attempt.state} i={attempt.n_iters}")
    return progress


def _final_diagnostic(
    session: cascade_state.CascadeSession,
    descriptor,
    *,
    panel_width: int,
) -> tuple[dict[int, bytes], dict]:
    """Reconstruct the final committed four-pane state from persistence."""
    selected = None
    for capture in reversed(session.captures):
        for level in reversed(capture.levels):
            if level.status == "complete":
                selected = capture, level
                break
        if selected is not None:
            break
    if selected is None:
        raise ValueError("state has no completed level to render")
    capture, level = selected
    lane_id = cascade_state.lane_identity(level.level_id, "primary")
    lane = session.lane_sessions.get(lane_id)
    if not isinstance(lane, receiver.ReceiverSession):
        raise ValueError("final diagnostic lane is unavailable")
    scans = [row for row in lane.scans
             if row.capture_id == capture.source.capture_id]
    if len(scans) != 1:
        raise ValueError("final diagnostic scan is ambiguous")
    scan = scans[0]
    image = receiver.load_image(scan.source_path)
    survey = scan.survey.unpack()
    combined = _combined_pilots(session, descriptor)
    display = _portfolio_view(lane, session)
    completion_row = level.completion
    completion_meta = None
    completion_progress = None
    if completion_row is not None:
        completion_meta = {
            "status": completion_row.status,
            "rank": sum(row[1] for row in completion_row.block_rank),
            "shortfall": completion_row.shortfall,
            "verified": completion_row.status == "volume_verified",
        }
        completion_progress = receiverdiag.DiagProgress(
            phase=(
                f"volume: rank={completion_meta['rank']} "
                f"shortfall={completion_meta['shortfall']} "
                f"verified={completion_meta['verified']}"))
    frames = {
        page: receiverdiag.diagnostic_png_bytes(
            image, survey, scan.result, combined, descriptor, display,
            page=page, progress=completion_progress,
            panel_width=panel_width)
        for page in session.envelope.pages
    }
    meta = {
        "capture_id": capture.source.capture_id,
        "level_index": level.ordinal,
        "levels_total": len(session.envelope.scale_plan),
        "ppc": session.envelope.scale_plan[level.ordinal].target_ppc,
        "effective_dpi": (
            session.envelope.scale_plan[level.ordinal].effective_dpi),
        "regions": len(survey.regions),
        "regions_done": len(scan.result.region_states),
        "placements": len(scan.result.placements),
        "pilots_solved": sum(
            row.bch_ok is True for row in combined.tiles.values()),
        "certified": len(session.certificate_union),
        "attempts": len(session.attempts),
        "completion": completion_meta,
        "session_status": session.status,
        "authoritative_sha256": cascade_state.authoritative_digest(session),
        "scale_ladder": [{
            "ppc": spec.target_ppc,
            "status": capture.levels[spec.ordinal].status,
        } for spec in session.envelope.scale_plan],
    }
    return frames, meta


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Fraction):
        return f"{value.numerator}/{value.denominator}"
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def report_dict(session: cascade_state.CascadeSession) -> dict:
    lanes = {}
    for lane_id, meta in sorted(session.decoder_lanes.items(),
                                key=lambda item: item[1].level_id):
        lane = session.lane_sessions[lane_id]
        states = payloaddec.full_tile_states(lane.decode)
        counts = {}
        for state in states.values():
            counts[state] = counts.get(state, 0) + 1
        lanes[meta.level_id] = {
            "lane_id": lane_id, "scans": len(lane.scans),
            "captures": [scan.capture_id for scan in lane.scans],
            "placements": sum(len(scan.result.placements)
                              for scan in lane.scans),
            "attempts": len(lane.attempts),
            "crc_calls": lane.decode.n_attempts,
            "bp_iterations": sum(row.n_iters for row in lane.attempts),
            "states": dict(sorted(counts.items())),
        }
    return {
        "magic": cascade_state.STATE_MAGIC,
        "version": cascade_state.STATE_VERSION,
        "algorithm_id": session.envelope.algorithm_id,
        "authoritative_sha256": cascade_state.authoritative_digest(session),
        "status": session.status,
        "format_id": session.envelope.format_id,
        "pages": list(session.envelope.pages),
        "native_dpi": session.envelope.native_dpi,
        "detector_profile": session.envelope.detector_profile,
        "scale_plan": [asdict(row) for row in session.envelope.scale_plan],
        "captures": [{
            "capture_id": row.source.capture_id,
            "source_path": row.source.source_path,
            "source_sha256": row.source.source_sha256,
            "status": row.status,
            "first_verified_level_id": row.first_verified_level_id,
            "levels": [{
                "level_id": level.level_id, "status": level.status,
                "view_sha256": level.view_sha256,
                "attempts": len(level.attempt_ids),
                "new_certificates": len(level.new_certificate_ids),
                "certificate_count": level.artifacts.get(
                    "certificate_count"),
                "certificate_frontier_sha256": (
                    level.output_certificate_sha256),
                "completion": (
                    None if level.completion is None else {
                        "status": level.completion.status,
                        "rank": sum(row[1] for row in
                                    level.completion.block_rank),
                        "shortfall": level.completion.shortfall,
                        "volume_sha256": level.completion.volume_sha256,
                        "expected_volume_sha256": (
                            level.completion.expected_volume_sha256),
                    }),
                "artifacts": {
                    "survey_regions": level.artifacts.get(
                        "survey_regions"),
                    "placements": level.artifacts.get("placements"),
                    "pilot_tiles": level.artifacts.get("pilot_tiles"),
                    "lower_hint_count": level.artifacts.get(
                        "lower_hint_count"),
                    "feedback": {
                        name: level.artifacts.get("feedback", {}).get(name)
                        for name in (
                            "certificate_frontier", "eligible", "adopted")
                    },
                    "apply_counts": level.artifacts.get("apply_counts"),
                },
                "timings": level.timings,
            } for level in row.levels],
        } for row in session.captures],
        "pilot_knowledge": asdict(session.pilot_knowledge),
        "lanes": lanes,
        "certificate_union": {
            "count": len(session.certificate_union),
            "sha256": cascade_state.certificate_union_digest(
                session.certificate_union),
        },
        "attempts": len(session.attempts),
        "first_verified_at": session.first_verified_at,
    }


def _save_report(path: Path, session: cascade_state.CascadeSession) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        report_dict(session), indent=2, sort_keys=True,
        default=_json_default) + "\n"
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(payload)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _capture_index(
    session: cascade_state.CascadeSession,
    source: cascade_state.SourceIdentity,
) -> int | None:
    for index, row in enumerate(session.captures):
        if row.source.source_sha256 == source.source_sha256:
            if replace(
                    row.source, source_path=source.source_path) != source:
                raise ValueError("same source bytes arrived under new metadata")
            return index
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="*", type=Path)
    parser.add_argument("--dpi", type=float, required=True,
                        help="true native capture DPI")
    parser.add_argument("--format", default="e018b-v3-c3")
    parser.add_argument("--pages", default="0")
    parser.add_argument("--capture-groups", default=None,
                        help="one physical capture id per input image")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--detector-profile",
                        choices=sorted(payloaddec.DETECTOR_PROFILES),
                        default=payloaddec.DETECTOR_CTX_PAVA_V1)
    parser.add_argument("--no-bch-first", action="store_true")
    parser.add_argument("--minimum-ppc", default="2")
    parser.add_argument("--ppc-levels", default=None,
                        help="explicit comma-separated ppc ladder; native is appended")
    parser.add_argument("--no-lower-hints", action="store_true")
    parser.add_argument("--no-runner-ups", action="store_true")
    parser.add_argument("--no-forward-refine", action="store_true")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="optional outer volume verification oracle")
    parser.add_argument("--complete", action="store_true",
                        help="continue to native after verified recovery")
    parser.add_argument("--bp-retry", action="store_true",
                        help="max-150 retry each changed per-scale frontier")
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--diag", nargs="?", const=str(DEFAULT_DIAG),
                        default=None, metavar="DIR")
    parser.add_argument("--diag-port", type=int, default=8023)
    parser.add_argument(
        "--diag-interval", type=float, default=3.0,
        help="seconds between expensive transient diagnostic PNG renders")
    parser.add_argument("--panel-width", type=int, default=600)
    args = parser.parse_args()

    if args.images and args.capture_groups is None:
        print("--capture-groups is required for image ingestion",
              file=sys.stderr)
        return 2
    capture_groups = (() if not args.images else
                      tuple(args.capture_groups.split(",")))
    if len(capture_groups) != len(args.images):
        print("--capture-groups must have one id per image", file=sys.stderr)
        return 2
    if len(set(capture_groups)) != len(capture_groups):
        print("--capture-groups contains a duplicate physical capture id",
              file=sys.stderr)
        return 2

    report_path = args.report or args.out.with_suffix(".json")
    cache_dir = (args.cache_dir or
                 args.state.with_suffix("").with_name(
                     args.state.stem + "-views"))
    diag = None
    try:
        descriptor = resolve_format(args.format)
        pages = tuple(int(value) for value in args.pages.split(","))
        config = pilotsearch.SearchConfig(
            bch_first=not args.no_bch_first)
        schedule = make_schedule(
            args.dpi, descriptor.cell_dots,
            minimum_ppc=args.minimum_ppc,
            explicit_ppc=args.ppc_levels)
        manifest = (None if args.manifest is None else
                    completion.load_manifest(args.manifest))
        if manifest is not None:
            _validate_manifest(manifest, descriptor, pages)
        manifest_sha = None if manifest is None else manifest.file_sha256
        envelope = _make_envelope(
            descriptor, pages, args.dpi, schedule,
            args.detector_profile, config, manifest_sha, {
                "lower_hints": not args.no_lower_hints,
                "runner_up_per_region": (
                    0 if args.no_runner_ups else 2),
                "forward_refine": not args.no_forward_refine,
                "bp_retry_each_changed_level_frontier": bool(args.bp_retry),
            })
        if args.diag is not None:
            # Validate the observer-only throttle even before the first
            # capture so a typo fails as a configuration error.
            e023c_diag.ProgressThrottle(args.diag_interval)
            diag = e023c_diag.DiagViewer(
                Path(args.diag), args.diag_port,
                panel_width=args.panel_width)
    except Exception as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    session = None
    if args.state.exists() and not args.fresh:
        try:
            session = cascade_state.load_session(args.state)
            if session.envelope != envelope:
                raise ValueError(
                    "state envelope differs from format/DPI/scales/options")
        except Exception as exc:
            print(f"state error: {exc}", file=sys.stderr)
            return 2
    elif not args.images:
        print("a fresh E023c state requires at least one image", file=sys.stderr)
        return 2

    # Resume every persisted unfinished transaction before admitting a new
    # physical capture.  A user-supplied path for the same capture id may
    # replace a moved stored path, but its bytes are still checked below.
    requested = list(zip(args.images, capture_groups, strict=True))
    request_by_capture = {
        capture_id: path for path, capture_id in requested
    }
    work_items: list[tuple[Path, str]] = []
    if session is not None:
        for capture in session.captures:
            needs_resume = capture.status in {"pending", "in_progress"}
            needs_resume |= bool(
                args.complete and capture.status == "early_stopped")
            if not needs_resume:
                continue
            path = request_by_capture.pop(
                capture.source.capture_id,
                Path(capture.source.source_path))
            work_items.append((path, capture.source.capture_id))
    work_items.extend(
        (path, capture_id) for path, capture_id in requested
        if capture_id in request_by_capture)

    last_frame: bytes | None = None
    stop_after_capture = False
    try:
        for image_path, capture_id in work_items:
            if stop_after_capture:
                break
            native_path = image_path.resolve()
            native = receiver.load_image(native_path)
            source = _source_record(native_path, capture_id, native, args.dpi)
            if session is None:
                session = cascade_state.create_session(envelope, (source,))
                capture_index = 0
            else:
                capture_index = _capture_index(session, source)
                if capture_index is None:
                    if (session.first_verified_at is not None
                            and not args.complete):
                        print(f"{native_path}: volume already verified; skipped")
                        continue
                    blockers = [
                        row.source.capture_id for row in session.captures
                        if row.status not in {"exhausted", "early_stopped",
                                              "skipped_volume_verified"}
                    ]
                    if blockers:
                        raise ValueError(
                            "cannot append a new capture before earlier "
                            f"transactions finish: {blockers}")
                    working = _fork_session(session)
                    working.captures.append(
                        cascade_state.pending_capture(envelope, source))
                    working.status = "open"
                    session = working
                    capture_index = len(session.captures) - 1
                else:
                    existing = session.captures[capture_index]
                    if existing.status == "exhausted":
                        print(f"{native_path}: already exhausted -- exact no-op")
                        continue
                    if existing.status == "early_stopped" and not args.complete:
                        print(f"{native_path}: already verified -- exact no-op")
                        continue
                    if existing.status == "early_stopped" and args.complete:
                        levels = tuple(
                            replace(row, status="pending", skip_reason=None)
                            if row.status == "skipped_volume_verified" else row
                            for row in existing.levels)
                        working = _fork_session(session)
                        working.captures[capture_index] = replace(
                            existing, status="in_progress", levels=levels,
                            exhaustive_requested=True)
                        working.status = "open"
                        session = working
                    if (session.captures[capture_index].status
                            in {"pending", "in_progress"}
                            and session.captures[capture_index].source
                            != source):
                        working = _fork_session(session)
                        working.captures[capture_index] = replace(
                            working.captures[capture_index], source=source)
                        session = working

            capture = session.captures[capture_index]
            if capture.source.capture_id != capture_id:
                raise ValueError("capture identity changed on resume")
            print(f"capture {capture_id}: {native_path} {native.shape} "
                  f"dpi={args.dpi:g}", flush=True)
            prior_results: list[tuple[
                pilotsearch.SearchResult, scale_space.ScaleLevel]] = []
            for old_level, spec_row in zip(
                    schedule.levels, capture.levels, strict=True):
                if spec_row.status == "complete":
                    lane_id = cascade_state.lane_identity(
                        old_level.label, "primary")
                    lane = session.lane_sessions[lane_id]
                    records = [row for row in lane.scans
                               if row.capture_id == capture_id]
                    if len(records) != 1:
                        raise ValueError("completed level lost its lane record")
                    prior_results.append((records[0].result, old_level))
                    continue
                if spec_row.status == "skipped_volume_verified":
                    continue
                level = old_level
                working = _fork_session(session)
                input_digest = cascade_state.certificate_union_digest(
                    working.certificate_union)
                lane_id, lane = _receiver_lane(
                    working, level, descriptor, pages, config)
                attempt_start = len(lane.attempts)
                view, view_path = _materialize_view(
                    native, native_path, source.source_sha256,
                    level, cache_dir)
                hints = ()
                if not args.no_lower_hints:
                    # Prefer the nearest productive lower level, but do not
                    # let an empty intermediate view erase an older accepted
                    # pose or retained runner-up ledger.
                    for candidate_result, candidate_level in reversed(
                            prior_results):
                        candidate_hints = cascade.continuation_hints(
                            candidate_result, candidate_level, level,
                            runner_up_per_region=(
                                0 if args.no_runner_ups else 2))
                        if candidate_hints:
                            hints = candidate_hints
                            break
                prior = ({} if args.no_forward_refine else
                         _state_portfolio(working))
                render_gate = e023c_diag.ProgressThrottle(
                    args.diag_interval)
                rendered_window_frame = False
                rendered_attempt_kinds: set[str] = set()
                level_processing = True

                def observer(event: str, payload: dict) -> None:
                    nonlocal last_frame, rendered_window_frame
                    nonlocal rendered_attempt_kinds
                    if diag is None or diag.broken:
                        return
                    try:
                        diag_event = DIAG_EVENT_NAMES.get(event, event)
                        image = payload.get("image", view)
                        survey = payload.get("survey")
                        current = payload.get("result")
                        if current is None:
                            current = pilotsearch.SearchResult()
                        if survey is None:
                            from paperholo import platen
                            survey = platen.PayloadSurvey((), None, None)
                        display_lane = payload.get("lane_session", lane)
                        if not isinstance(
                                display_lane, receiver.ReceiverSession):
                            display_lane = lane
                        live_change = (
                            level_processing and event in {
                                "ldpc_attempt", "bp_retry_attempt",
                                "bp_retry_complete", "level_complete"})
                        new_lane_attempts = (
                            max(0, len(display_lane.attempts) - attempt_start)
                            if live_change else 0)
                        live_attempts = (
                            len(working.attempts) + new_lane_attempts)
                        if live_change:
                            lane_certificates = {
                                key for key, outcome
                                in display_lane.decode.tiles.items()
                                if outcome.state == "certified"
                            }
                            live_certified = len(
                                set(working.certificate_union)
                                | lane_certificates)
                        else:
                            live_certified = len(
                                working.certificate_union)
                        completion_meta = payload.get("completion")
                        current_capture = working.captures[capture_index]
                        status_extra, pilot_progress = (
                            _diagnostic_event_status(event, payload))
                        meta = {
                            "capture_id": capture_id,
                            "level_index": level.index,
                            "levels_total": len(schedule.levels),
                            "ppc": float(level.ppc),
                            "effective_dpi": float(level.dpi),
                            "regions": len(survey.regions),
                            "regions_done": len(current.region_states),
                            "placements": len(current.placements),
                            "certified": live_certified,
                            "attempts": live_attempts,
                            "completion": completion_meta,
                            "scale_ladder": [{
                                "ppc": float(item.ppc),
                                "status": (
                                    "active" if item.index == level.index else
                                    current_capture.levels[
                                        item.index].status),
                            } for item in schedule.levels],
                            **status_extra,
                        }
                        # The 1 Hz browser status follows every route/attempt;
                        # expensive combined-state and PNG work is gated below.
                        if not diag.update_status(meta, event=diag_event):
                            return
                        force = event in DIAG_FORCE_RENDER_EVENTS
                        window_row = status_extra.get("window")
                        window_overlay_ready = (
                            window_row is not None
                            and (window_row.get("pose_origin_yx") is not None
                                 or window_row.get("stage")
                                 == "window_complete"))
                        if (not rendered_window_frame
                                and window_overlay_ready):
                            force = True
                        attempt_kind = (
                            event if event in {
                                "ldpc_attempt", "bp_retry_attempt"}
                            else None)
                        if (attempt_kind is not None
                                and attempt_kind not in
                                rendered_attempt_kinds):
                            force = True
                        if not render_gate.allow(force=force):
                            return
                        already_attached = any(
                            scan.capture_id == capture_id
                            and scan.result is current
                            for current_lane in working.lane_sessions.values()
                            if isinstance(current_lane,
                                          receiver.ReceiverSession)
                            for scan in current_lane.scans)
                        combined = _combined_pilots(
                            working, descriptor,
                            current=(None if already_attached else (
                                capture_id, len(survey.regions), current)))
                        display = _portfolio_view(display_lane, working)
                        active_region = payload.get("region_index")
                        record = payload.get("record")
                        attempt = payload.get("attempt")
                        progress = _active_ldpc_progress(
                            record, diag_event, attempt)
                        if progress is None and event.startswith("payload_"):
                            progress = receiverdiag.DiagProgress(
                                phase=diag_event)
                        elif progress is None and completion_meta is not None:
                            progress = receiverdiag.DiagProgress(
                                phase=(
                                    f"{diag_event}: rank="
                                    f"{completion_meta.get('rank')} "
                                    f"shortfall="
                                    f"{completion_meta.get('shortfall')} "
                                    f"verified="
                                    f"{completion_meta.get('verified')}"))
                        frames = {
                            page: receiverdiag.diagnostic_png_bytes(
                                image, survey, current, combined,
                                descriptor, display, page=page,
                                active_region=active_region,
                                pilot_progress=pilot_progress,
                                progress=progress,
                                panel_width=args.panel_width)
                            for page in pages}
                        meta["pilots_solved"] = sum(
                            row.bch_ok is True
                            for row in combined.tiles.values())
                        diag.publish(frames, meta, event=diag_event)
                        last_frame = _contact_png(frames)
                        render_gate.mark_rendered()
                        if window_overlay_ready:
                            rendered_window_frame = True
                        if attempt_kind is not None:
                            rendered_attempt_kinds.add(attempt_kind)
                    except Exception as exc:
                        diag.disable(exc)

                print(f"  {level.label}: derive {view.shape}, "
                      f"{float(level.ppc):g} ppc @ {float(level.dpi):g} dpi",
                      flush=True)
                run = cascade.process_level(
                    image=view, source_path=view_path, level=level,
                    descriptor=descriptor, pages=pages,
                    capture_id=capture_id, lane_session=lane,
                    lower_hints=hints, prior_certificates=prior,
                    bp_retry=args.bp_retry,
                    observer=(
                        observer if diag is not None and not diag.broken
                        else None))
                level_processing = False
                cascade_state.attach_lane_session(
                    working, level_id=level.label, lane_kind="primary",
                    lane_session=run.lane_session)
                attempt_ids, new_ids = _sync_attempts_and_certificates(
                    working, lane_id=lane_id, level_run=run,
                    attempt_start=attempt_start)
                observer("level_portfolio_complete", {
                    "image": view, "survey": run.survey,
                    "result": run.result,
                    "lane_session": run.lane_session,
                })
                completion_report = None
                if manifest is not None:
                    completion_report = completion.completion_report(
                        {key: row.user_bits()
                         for key, row in working.certificate_union.items()},
                        manifest)
                    payload_check = completion_report["payload"]
                    if (payload_check["recovered"]
                            and not payload_check["verified"]):
                        raise payloaddec.FatalIntegrityError(
                            "fountain reconstruction completed but failed "
                            "the registered length/SHA-256 check")
                    observer("fountain_check", {
                        "image": view, "survey": run.survey,
                        "result": run.result,
                        "lane_session": run.lane_session,
                        "completion": {
                            "rank": completion_report["fountain"]["rank"],
                            "shortfall": completion_report["fountain"][
                                "rank_shortfall"],
                            "verified": payload_check["verified"],
                        },
                    })
                completed = _complete_level_record(
                    working, run, capture.levels[level.index],
                    input_digest=input_digest, attempt_ids=attempt_ids,
                    new_certificate_ids=new_ids,
                    completion_report=completion_report,
                    lower_hint_count=len(hints))
                levels = list(capture.levels)
                levels[level.index] = completed
                verified = bool(
                    completion_report is not None
                    and completion_report["payload"]["verified"])
                if verified and capture.first_verified_level_id is None:
                    first_verified = level.label
                else:
                    first_verified = capture.first_verified_level_id
                early = bool(
                    verified and not args.complete
                    and level.index < len(schedule.levels) - 1)
                if early:
                    for tail in range(level.index + 1, len(levels)):
                        levels[tail] = replace(
                            levels[tail], status="skipped_volume_verified",
                            skip_reason=(
                                f"volume verified at {level.label}"))
                    capture_status = "early_stopped"
                elif level.index == len(schedule.levels) - 1:
                    capture_status = "exhausted"
                else:
                    capture_status = "in_progress"
                updated_capture = replace(
                    capture, status=capture_status, levels=tuple(levels),
                    first_verified_level_id=first_verified,
                    exhaustive_requested=bool(args.complete))
                working.captures[capture_index] = updated_capture
                working.pilot_knowledge = completed.pilot_knowledge
                if verified and working.first_verified_at is None:
                    working.first_verified_at = (capture_id, level.label)
                if early:
                    working.status = "early_stopped"
                elif all(row.status == "exhausted"
                         for row in working.captures):
                    working.status = "exhausted"
                else:
                    working.status = "open"
                commit_sha, commit_size = receiver.file_identity(native_path)
                if (commit_sha, commit_size) != (
                        source.source_sha256, source.source_size):
                    raise ValueError(
                        "native source changed during level transaction")
                cascade_state.save_session(args.state, working)
                session = working
                capture = updated_capture
                _save_report(report_path, session)
                observer("capture_level_committed", {
                    "image": view, "survey": run.survey,
                    "result": run.result,
                    "lane_session": run.lane_session,
                    "completion": (None if completion_report is None else {
                        "rank": completion_report["fountain"]["rank"],
                        "shortfall": completion_report["fountain"][
                            "rank_shortfall"],
                        "verified": completion_report["payload"]["verified"],
                    }),
                })
                print(
                    f"    placements={len(run.result.placements)} "
                    f"new-cert={len(new_ids)} total-cert="
                    f"{len(session.certificate_union)} "
                    f"hints={len(hints)} refine="
                    f"{run.feedback.get('adopted', 0)} "
                    f"[{run.timings['total_s']:.1f}s]", flush=True)
                prior_results.append((run.result, level))
                if early:
                    stop_after_capture = True
                    break

        if session is None:
            raise ValueError("no E023c state was produced")
        _save_report(report_path, session)
        # Re-render from the committed state even when live diagnostics were
        # disabled or this invocation was an exact no-op.  Observer failures
        # are warnings and can never roll back or fail the receiver result.
        try:
            final_frames, final_meta = _final_diagnostic(
                session, descriptor, panel_width=args.panel_width)
            last_frame = _contact_png(final_frames)
            if diag is not None and not diag.broken:
                diag.publish(
                    final_frames, final_meta, event="session_complete")
        except Exception as exc:
            print(f"  [diag] final rendering unavailable: {exc!r}",
                  file=sys.stderr, flush=True)
        if last_frame is not None:
            try:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_bytes(last_frame)
            except Exception as exc:
                print(f"  [diag] final PNG unavailable: {exc!r}",
                      file=sys.stderr, flush=True)
        print(
            f"E023c: captures={len(session.captures)} "
            f"certified={len(session.certificate_union)} "
            f"attempts={len(session.attempts)} "
            f"authoritative={cascade_state.authoritative_digest(session)[:16]}",
            flush=True)
        print(f"  state {args.state}")
        print(f"  report {report_path}")
        if last_frame is not None:
            print(f"  PNG {args.out}")
        if diag is not None:
            diag.close(grace_s=0.5)
        return 0
    except (ValueError, OSError, pickle.UnpicklingError,
            payloaddec.FatalIntegrityError) as exc:
        print(f"E023c failed: {exc}", file=sys.stderr)
        if diag is not None:
            diag.close(grace_s=0.0)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
