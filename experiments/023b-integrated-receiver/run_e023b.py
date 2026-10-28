#!/usr/bin/env python
"""Persistent E021 -> E022 -> payload/LDPC receiver session.

One or more TIFFs may be supplied in one command; each is processed and
committed as an independent transaction.  Reinvoke later with the same state
to append scans.  E023b ends at CRC-certified LDPC tiles.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from paperholo import (payloaddec, pilotcombine, pilotsearch, platen,  # noqa:E402
                       receiver, receiverdiag)
from paperholo.formats import FORMAT_REGISTRY  # noqa:E402


DEFAULT_STATE = HERE / "build" / "session.pkl"
DEFAULT_OUT = HERE / "build" / "session_e023b.png"
DEFAULT_DIAG = HERE / "build" / "session_diag"

def resolve_format(format_id: str):
    for descriptor in FORMAT_REGISTRY:
        if descriptor.format_id == format_id:
            return descriptor
    names = ", ".join(row.format_id for row in FORMAT_REGISTRY)
    raise ValueError(f"unknown format {format_id!r}; choose one of: {names}")


def combined_result(
    session: receiver.ReceiverSession,
    descriptor,
    *,
    current: tuple[str, int, pilotsearch.SearchResult] | None = None,
    decode_words: bool,
) -> pilotsearch.SearchResult:
    parts = [pilotcombine.SearchResultPart(
        scan.scan_id, scan.region_count, scan.result)
        for scan in session.scans]
    if current is not None:
        parts.append(pilotcombine.SearchResultPart(*current))
    return pilotcombine.combine_search_results(
        parts, descriptor, pages=session.envelope.pages,
        decode_words=decode_words)


def _check_combined_bch(result: pilotsearch.SearchResult, *, where: str) -> None:
    bad = [key for key, tile in result.tiles.items() if tile.bch_ok is False]
    if bad:
        raise payloaddec.FatalIntegrityError(
            f"{where}: contradictory combined BCH reads at {bad[:8]}")


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def report_dict(session: receiver.ReceiverSession) -> dict:
    states = payloaddec.full_tile_states(session.decode)
    baseline_decoder = receiver.decoder_profile(
        session.envelope.rate_id, receiver.BASELINE_BP_MAX_ITERS,
        receiver.BP_ALPHA)
    retry_decoder = receiver.decoder_profile(
        session.envelope.rate_id, receiver.RETRY_BP_MAX_ITERS,
        receiver.BP_ALPHA)
    return {
        "state_version": receiver.STATE_VERSION,
        "algorithm_id": session.envelope.algorithm_id,
        "authoritative_sha256": receiver.authoritative_digest(session),
        "format_id": session.envelope.format_id,
        "pages": list(session.envelope.pages),
        "dpi": session.envelope.dpi,
        "rate_id": session.envelope.rate_id,
        "detector_profile": session.envelope.detector_profile,
        "decoder_profiles": {
            "baseline": baseline_decoder,
            "retry150": retry_decoder,
            "observed": sorted({row.decoder_profile
                                for row in session.attempts}),
        },
        "search_config_sha256": session.envelope.search_config_sha256,
        "implementation_sha256": dict(
            session.envelope.implementation_sha256),
        "summary": session.summary(),
        "scans": [{
            "scan_id": scan.scan_id,
            "source_path": scan.source_path,
            "source_sha256": scan.source_sha256,
            "source_size": scan.source_size,
            "capture_id": scan.capture_id,
            "image_shape": list(scan.image_shape),
            "image_dtype": scan.image_dtype,
            "detector_profile": scan.detector_profile,
            "context_fits": [asdict(fit) for fit in scan.context_fits],
            "regions": scan.region_count,
            "placements": len(scan.result.placements),
            "pilot_tiles": len(scan.result.tiles),
            "window_evidence": len(scan.window_evidence),
            "payload_tiles": len(scan.tile_evidence_digests),
            "work_plan": {
                repr(key): {
                    "n_geometric": row.n_geometric,
                    "n_nonshort": row.n_nonshort,
                    "coverage": row.geometric_coverage,
                    "degenerate": row.degenerate,
                    "placements": list(row.placement_ids),
                } for key, row in sorted(scan.work_plan.items())
            },
            "timings": scan.timings,
        } for scan in session.scans],
        "tiles": [{
            "page_tile": list(key), "state": state,
            "certified_by": (session.decode.tiles[key].certified_by
                             if key in session.decode.tiles else ""),
            "n_user_bits": (0 if key not in session.decode.tiles
                            or session.decode.tiles[key].user_bits is None
                            else int(session.decode.tiles[key].user_bits.size)),
            "attempts": (0 if key not in session.decode.tiles
                         else session.decode.tiles[key].attempts),
            "divergence": ({} if key not in session.decode.tiles
                           else session.decode.tiles[key].divergence),
        } for key, state in sorted(states.items())],
        "attempt_ledger": [{
            "attempt_id": row.attempt_id,
            "page_tile": [row.page, *row.tile_yx],
            "stage": row.stage,
            "source": row.source,
            "scan_ids": list(row.scan_ids),
            "capture_ids": list(row.capture_ids),
            "evidence_digest": row.evidence_digest,
            "decoder_profile": row.decoder_profile,
            "state": row.state,
            "decoder_invoked": row.decoder_invoked,
            "k_eff": row.k_eff,
            "n_informative": row.n_informative,
            "coverage": row.coverage,
            "n_iters": row.n_iters,
            "syndrome_ok": row.syndrome_ok,
            "crc_ok": row.crc_ok,
            "certified_new": row.certified_new,
        } for row in session.attempts],
    }


def save_report(path: Path, session: receiver.ReceiverSession) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(report_dict(session), indent=2, sort_keys=True,
                              default=_json_default) + "\n")
    os.replace(tmp, path)


def _out_for_page(path: Path, page: int, n_pages: int) -> Path:
    if n_pages == 1:
        return path
    return path.with_name(f"{path.stem}_p{page:04d}{path.suffix}")


def render_final(
    session: receiver.ReceiverSession,
    descriptor,
    out: Path,
    *,
    panel_width: int = 600,
) -> list[Path]:
    if not session.scans:
        return []
    scan = session.scans[-1]
    image = receiver.load_image(Path(scan.source_path))
    survey = scan.survey.unpack()
    combined = combined_result(session, descriptor, decode_words=True)
    paths = []
    for page in session.envelope.pages:
        canvas = receiverdiag.compose_diagnostic(
            image, survey, scan.result, combined, descriptor, session,
            page=page, panel_width=panel_width)
        target = _out_for_page(out, page, len(session.envelope.pages))
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target)
        paths.append(target)
    return paths


def _counts(session: receiver.ReceiverSession) -> dict[str, int]:
    states = payloaddec.full_tile_states(session.decode)
    out = {}
    for state in states.values():
        out[state] = out.get(state, 0) + 1
    return out


def _bp_retry_display_scan(
    session: receiver.ReceiverSession,
    attempt: receiver.TileAttempt | None,
) -> receiver.ScanRecord:
    """Choose the image whose evidence a retry frame is explaining.

    Scan-only retry parents retain one scan id and are drawn on that scan.
    Union retries—and the global completion frame represented by ``None``—
    use the latest scan as the common field view.
    """
    if not session.scans:
        raise ValueError("BP retry diagnostic has no scans")
    if attempt is None or len(attempt.scan_ids) != 1:
        return session.scans[-1]
    scan_id = attempt.scan_ids[0]
    matches = [scan for scan in session.scans if scan.scan_id == scan_id]
    if len(matches) != 1:
        raise ValueError(
            f"BP retry diagnostic source {scan_id!r} is unavailable")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="*", type=Path)
    parser.add_argument("--dpi", type=float, required=True)
    parser.add_argument("--format", default="e018-v3-c3")
    parser.add_argument("--pages", default="0",
                        help="comma-separated legal logical page ids")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--rate", default=None,
                        help="experimental override; default registry rate")
    parser.add_argument(
        "--detector-profile", choices=sorted(payloaddec.DETECTOR_PROFILES),
        default=payloaddec.DETECTOR_PAVA_V1,
        help="frozen detector arm for this state")
    parser.add_argument(
        "--bp-retry", action="store_true",
        help="state-only explicit max-150 retry over failed BP frontiers")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--diag", nargs="?", const=str(DEFAULT_DIAG),
                        default=None, metavar="DIR")
    parser.add_argument("--diag-port", type=int, default=8023)
    parser.add_argument("--panel-width", type=int, default=600)
    parser.add_argument("--no-bch-first", action="store_true")
    parser.add_argument(
        "--capture-groups", default=None,
        help="comma-separated physical-capture ids aligned with TIFFs; "
             "required for ingestion so derived files cannot silently count "
             "as independent evidence")
    args = parser.parse_args()
    report_path = args.report or args.out.with_suffix(".json")

    if args.bp_retry and args.images:
        print("--bp-retry is a state-only action; do not pass TIFFs",
              file=sys.stderr)
        return 2
    if args.bp_retry and args.fresh:
        print("--bp-retry requires an existing state; omit --fresh",
              file=sys.stderr)
        return 2
    if args.bp_retry and not args.state.exists():
        print("--bp-retry requires an existing --state", file=sys.stderr)
        return 2

    try:
        descriptor = resolve_format(args.format)
        pages = tuple(int(value) for value in args.pages.split(","))
        config = pilotsearch.SearchConfig(bch_first=not args.no_bch_first)
        if args.fresh or not args.state.exists():
            session = receiver.ReceiverSession.create(
                descriptor, pages, args.dpi, rate_id=args.rate,
                detector_profile=args.detector_profile,
                search_config=config)
        else:
            session = receiver.load_session(args.state)
            session.validate(
                descriptor, pages, args.dpi, rate_id=args.rate,
                detector_profile=args.detector_profile,
                search_config=config)
    except (ValueError, pickle.UnpicklingError, EOFError,
            payloaddec.FatalIntegrityError) as exc:
        print(f"state/config error: {exc}", file=sys.stderr)
        return 2

    capture_groups = None
    if args.images and args.capture_groups is None:
        print("physical capture identity is required: pass "
              "--capture-groups with one id per TIFF (use the same id for "
              "derived files, which E023b will refuse to double-count)",
              file=sys.stderr)
        return 2
    if args.capture_groups is not None:
        capture_groups = tuple(args.capture_groups.split(","))
        if len(capture_groups) != len(args.images):
            print("--capture-groups must have one id per TIFF",
                  file=sys.stderr)
            return 2

    diag = None
    diag_failed = False
    if args.diag is not None:
        try:
            import e023b_diag
            diag = e023b_diag.DiagViewer(
                Path(args.diag), args.diag_port)
        except Exception as exc:
            print(f"  [diag] unavailable: {exc!r}; receiver continues",
                  flush=True)

    def disable_diag(exc: Exception) -> None:
        """Fail the complete observer path closed without touching state."""
        nonlocal diag_failed
        if diag_failed:
            return
        diag_failed = True
        try:
            if diag is not None:
                diag.disable(exc)
        except Exception as nested:
            print(f"  [diag] disable failed: {nested!r}; "
                  "receiver continues", flush=True)

    def publish(
        phase: str,
        image: np.ndarray,
        survey: platen.PayloadSurvey,
        current: pilotsearch.SearchResult,
        combined: pilotsearch.SearchResult,
        view_session: receiver.ReceiverSession,
        *,
        scan_id: str,
        active_region: int | None = None,
        progress: receiverdiag.DiagProgress | None = None,
    ) -> None:
        if diag is None or diag_failed:
            return
        try:
            frames = {page: receiverdiag.diagnostic_png_bytes(
                image, survey, current, combined, descriptor, view_session,
                page=page, active_region=active_region, progress=progress,
                panel_width=args.panel_width)
                for page in pages}
            counts = _counts(view_session)
            diag.publish(frames, {
                "phase": phase, "scan_id": scan_id,
                "regions_done": len(current.region_states),
                "regions": len(survey.regions),
                "certified": counts.get("certified", 0),
                "attempts": view_session.decode.n_attempts,
                "placements": len(current.placements),
                "pilot_tiles": len(combined.tiles),
                "detector_profile": view_session.envelope.detector_profile,
                "decoder_profiles": sorted({
                    row.decoder_profile for row in view_session.attempts}),
                "state_counts": counts,
                "attempt_records": len(view_session.attempts),
                "crc_false_accept_budget": (
                    view_session.decode.n_attempts
                    * payloaddec.CRC_FALSE_ACCEPT),
            })
        except Exception as exc:             # observer only
            disable_diag(exc)

    committed_any = False
    try:
        for image_index, image_path in enumerate(args.images):
            source_sha, source_size = receiver.file_identity(image_path)
            if source_sha in session.source_hashes:
                print(f"{image_path}: already ingested "
                      f"({source_sha[:12]}) -- exact no-op", flush=True)
                continue
            scan_id = f"s{len(session.scans):03d}"
            assert capture_groups is not None
            capture_id = capture_groups[image_index]
            if capture_id in session.capture_ids:
                raise ValueError(
                    f"capture_id {capture_id!r} already exists; refusing "
                    "correlated evidence before scan processing")
            image = receiver.load_image(image_path)
            print(f"{scan_id} E021: {image_path} {image.shape} "
                  f"dpi={args.dpi:g}", flush=True)
            empty = pilotsearch.SearchResult()
            if diag is not None and not diag_failed:
                try:
                    prior = combined_result(
                        session, descriptor, decode_words=False)
                    publish("scan_open", image,
                            platen.PayloadSurvey((), None, None), empty,
                            prior, session, scan_id=scan_id)
                except Exception as exc:     # observer only
                    disable_diag(exc)
            t_scan = perf_counter()
            t0 = perf_counter()
            survey = platen.detect_payload_regions(image, dpi=args.dpi)
            e021_s = perf_counter() - t0
            print(f"  regions={len(survey.regions)} c={survey.c_dots} "
                  f"pitch={survey.cell_pitch_px}", flush=True)
            if diag is not None and not diag_failed:
                try:
                    provisional = combined_result(
                        session, descriptor,
                        current=(scan_id, len(survey.regions), empty),
                        decode_words=False)
                    publish("e021_complete", image, survey, empty,
                            provisional, session, scan_id=scan_id)
                except Exception as exc:     # observer only
                    disable_diag(exc)

            def on_region(result, region_index):
                state = result.region_states[region_index]
                n_placed = sum(row.region_index == region_index
                               for row in result.placements)
                print(f"  E022 region {region_index}: {state}, "
                      f"placements={n_placed}", flush=True)
                if diag is None or diag_failed:
                    return
                try:
                    reference = combined_result(
                        session, descriptor,
                        current=(scan_id, len(survey.regions), result),
                        decode_words=False)
                    publish("e022_region_complete", image, survey, result,
                            reference, session, scan_id=scan_id,
                            active_region=region_index)
                except Exception as exc:     # observer only
                    disable_diag(exc)

            t0 = perf_counter()
            result = pilotsearch.search_survey(
                image, survey, descriptor, pages=pages, config=config,
                scan_id=scan_id, scan_dpi=args.dpi, on_region=on_region)
            e022_s = perf_counter() - t0
            pilot_final = combined_result(
                session, descriptor,
                current=(scan_id, len(survey.regions), result),
                decode_words=True)
            _check_combined_bch(pilot_final, where=f"{scan_id} pilot_final")
            publish("pilot_final", image, survey, result, pilot_final,
                    session, scan_id=scan_id)

            active_payload_tiles: set[tuple[int, int, int]] = set()
            refused_windows = 0

            def on_payload_region(region_index, region_rows, all_rows):
                nonlocal active_payload_tiles, refused_windows
                print(f"  payload region {region_index}: "
                      f"windows={len(region_rows)}", flush=True)
                if diag is None or diag_failed:
                    return
                try:
                    active_payload_tiles = set()
                    for row in region_rows:
                        refused_windows += int(row.refused)
                        if not row.refused and row.payload_index.size:
                            active_payload_tiles.update(
                                receiver.payload_indices_to_tiles(
                                    row.page, row.payload_index,
                                    descriptor.spec(), descriptor.seed))
                    progress = receiverdiag.DiagProgress(
                        phase=f"payload_region_{region_index}",
                        active_tiles=active_payload_tiles,
                        refused_windows=refused_windows)
                    publish("payload_region_emitted", image, survey, result,
                            pilot_final, session, scan_id=scan_id,
                            active_region=region_index, progress=progress)
                except Exception as exc:     # observer only
                    disable_diag(exc)

            def on_context(region_index, fit):
                print(
                    f"  context region {region_index}: "
                    f"eligible={fit.eligible} adopted={fit.adopted} "
                    f"reason={fit.reason} valid="
                    f"{fit.context_valid_coverage:.3f}", flush=True)

            t0 = perf_counter()
            record = receiver.make_scan_record(
                scan_id=scan_id, source_path=image_path,
                source_sha256=source_sha, source_size=source_size,
                dpi=args.dpi, image=image, capture_id=capture_id,
                survey=survey, result=result, descriptor=descriptor,
                pages=pages, rate_id=session.envelope.rate_id,
                detector_profile=session.envelope.detector_profile,
                on_payload_region=on_payload_region,
                on_context=on_context,
                timings={"e021_s": e021_s, "e022_s": e022_s})
            payload_s = perf_counter() - t0
            record.timings["payload_s"] = payload_s
            progress = None
            if diag is not None and not diag_failed:
                try:
                    progress = receiverdiag.work_plan_progress(
                        record, phase="scan_owner_frozen")
                    progress.attempt_ready = receiver.attempt_ready_tiles(
                        record, session.decode)
                except Exception as exc:     # observer only
                    disable_diag(exc)
            publish("payload_plan", image, survey, result, pilot_final,
                    session, scan_id=scan_id, progress=progress)
            publish("scan_owner_frozen", image, survey, result, pilot_final,
                    session, scan_id=scan_id, progress=progress)

            published_attempts = 0
            last_stage = None

            def on_attempt(view_session, attempt):
                nonlocal published_attempts, last_stage
                if diag is None or diag_failed:
                    return
                published_attempts += 1
                should_publish = (attempt.stage != last_stage
                                  or published_attempts % 40 == 0)
                last_stage = attempt.stage
                if not should_publish:
                    return
                try:
                    tile_key = (attempt.page, *attempt.tile_yx)
                    live = receiverdiag.work_plan_progress(
                        record, phase=f"ldpc_{attempt.stage}")
                    live.active_tiles = {tile_key}
                    if progress is not None:
                        live.attempt_ready = progress.attempt_ready
                    publish(f"ldpc_{attempt.stage}", image, survey, result,
                            pilot_final, view_session, scan_id=scan_id,
                            progress=live)
                except Exception as exc:     # observer only
                    disable_diag(exc)

            working, counts = receiver.apply_scan(
                session, record, on_attempt=on_attempt)
            final_progress = None
            if diag is not None and not diag_failed:
                try:
                    final_progress = receiverdiag.work_plan_progress(
                        record, phase="union_complete")
                except Exception as exc:     # observer only
                    disable_diag(exc)
            publish("union_complete", image, survey, result, pilot_final,
                    working, scan_id=scan_id, progress=final_progress)
            commit_sha, commit_size = receiver.file_identity(image_path)
            if (commit_sha, commit_size) != (source_sha, source_size):
                raise ValueError(
                    f"{image_path} changed while it was being processed; "
                    "transaction discarded")
            # The transaction becomes authoritative only here.
            receiver.save_session(args.state, working)
            session = working
            committed_any = True
            save_report(report_path, session)
            publish("scan_committed", image, survey, result, pilot_final,
                    session, scan_id=scan_id)
            elapsed = perf_counter() - t_scan
            print(
                f"  committed {scan_id}: stage1 "
                f"{counts['stage1']['certified']} cert / "
                f"{counts['stage1']['attempted']} calls; union "
                f"{counts['union']['certified']} cert / "
                f"{counts['union']['attempted']} calls; total "
                f"{counts['total_certified']} [{elapsed:.1f}s, payload "
                f"{payload_s:.1f}s]", flush=True)

        if args.bp_retry:
            retry_views = {}
            unavailable_retry_views = set()
            retry_pilots = None
            if diag is not None and not diag_failed:
                try:
                    retry_pilots = combined_result(
                        session, descriptor, decode_words=True)
                except Exception as exc:     # observer only
                    disable_diag(exc)

            def bp_retry_view(attempt):
                if (diag is None or diag_failed or retry_pilots is None
                        or not session.scans):
                    return None
                record = None
                try:
                    record = _bp_retry_display_scan(session, attempt)
                    if record.scan_id in unavailable_retry_views:
                        return None
                    if record.scan_id not in retry_views:
                        retry_views[record.scan_id] = (
                            receiver.load_image(record.source_path),
                            record.survey.unpack())
                    image, survey = retry_views[record.scan_id]
                    return record, image, survey, retry_pilots
                except Exception as exc:     # observer only
                    if record is not None:
                        unavailable_retry_views.add(record.scan_id)
                    disable_diag(exc)
                    return None

            published_retries = 0

            def on_bp_attempt(view_session, attempt):
                nonlocal published_retries
                if diag is None or diag_failed:
                    return
                published_retries += 1
                if (published_retries != 1
                        and published_retries % 20):
                    return
                try:
                    retry_view = bp_retry_view(attempt)
                    if retry_view is None:
                        return
                    record, image, survey, pilots = retry_view
                    progress = receiverdiag.work_plan_progress(
                        record, phase="ldpc_retry150")
                    progress.active_tiles = {
                        (attempt.page, *attempt.tile_yx)}
                    publish("ldpc_retry150", image, survey, record.result,
                            pilots, view_session, scan_id=record.scan_id,
                            progress=progress)
                except Exception as exc:     # observer only
                    disable_diag(exc)

            working, counts = receiver.retry_failed_bp(
                session, on_attempt=on_bp_attempt)
            if working is not session:
                receiver.save_session(args.state, working)
                session = working
                committed_any = True
            save_report(report_path, session)
            if diag is not None and not diag_failed:
                try:
                    retry_view = bp_retry_view(None)
                    if retry_view is not None:
                        last, image, survey, _pilots = retry_view
                        pilots = combined_result(
                            session, descriptor, decode_words=True)
                        progress = receiverdiag.work_plan_progress(
                            last, phase="bp_retry_complete")
                        publish("bp_retry_complete", image, survey,
                                last.result, pilots, session,
                                scan_id=last.scan_id, progress=progress)
                except Exception as exc:     # observer only
                    disable_diag(exc)
            print(
                "  BP retry: "
                f"eligible={counts['eligible']} "
                f"calls={counts['attempted']} "
                f"certified={counts['certified']} "
                f"total={counts['total_certified']}", flush=True)
    except payloaddec.FatalIntegrityError as exc:
        print(f"FATAL integrity violation: {exc}", file=sys.stderr)
        return 3
    except (ValueError, OSError) as exc:
        print(f"receiver error: {exc}", file=sys.stderr)
        return 2
    finally:
        if diag is not None:
            try:
                diag.close()
            except Exception as exc:         # observer only
                print(f"  [diag] close failed: {exc!r}; receiver continues",
                      flush=True)

    if args.fresh and not committed_any:
        receiver.save_session(args.state, session)
    save_report(report_path, session)
    try:
        outputs = render_final(
            session, descriptor, args.out, panel_width=args.panel_width)
    except Exception as exc:
        outputs = []
        print(f"  final PNG observer failed: {exc!r}; state is committed",
              flush=True)
    summary = session.summary()
    print(f"E023b: scans={len(session.scans)} tiles={summary['tiles']} "
          f"attempts={summary['n_attempts']} authoritative="
          f"{receiver.authoritative_digest(session)[:16]}")
    print(f"  state {args.state}\n  JSON {report_path}")
    for path in outputs:
        print(f"  PNG {path}")
    if args.images and not committed_any:
        print("  no new TIFFs committed (state was unchanged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
