#!/usr/bin/env python
"""Run E024 certified feedback over an immutable E023b receiver state."""
from __future__ import annotations

import argparse
import copy
import io
import json
import os
import pickle
import sys
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from paperholo import (feedback, feedbackstate, payloaddec,  # noqa: E402
                       receiver, receiverdiag)
from paperholo.formats import FORMAT_REGISTRY  # noqa: E402


DEFAULT_STATE = HERE / "build" / "session.pkl"
DEFAULT_REPORT = HERE / "build" / "session.json"
DEFAULT_OUT = HERE / "build" / "session_e024.png"
DEFAULT_DIAG = HERE / "build" / "session_diag"


def _descriptor(format_id: str):
    rows = [
        descriptor for descriptor in FORMAT_REGISTRY
        if descriptor.format_id == format_id]
    if len(rows) != 1:
        raise ValueError(
            f"format registry has {len(rows)} entries for {format_id!r}")
    return rows[0]


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(
        f"not JSON serializable: {type(value).__name__}")


def save_report(
    path: Path,
    session: feedbackstate.E024Session,
    baseline: receiver.ReceiverSession,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(
        feedback.report_dict(session, baseline),
        indent=2, sort_keys=True, default=_json_default) + "\n")
    os.replace(tmp, path)


def _display_result(
    session: feedbackstate.E024Session,
    scan: receiver.ScanRecord,
    active_map=None,
):
    result = copy.deepcopy(scan.result)
    active = (
        session.active_revision_map if active_map is None else active_map)
    for ordinal, placed in enumerate(result.placements):
        revision_id = active.get((scan.scan_id, ordinal))
        if revision_id is None:
            continue
        revision = session.revisions[revision_id]
        result.placements[ordinal] = replace(
            placed, pose=revision.pose)
    return result


def diagnostic_pngs(
    session: feedbackstate.E024Session,
    baseline: receiver.ReceiverSession,
    *,
    active_tile=None,
    active_map=None,
    scan_id: str | None = None,
    display_generation: int | None = None,
    phase: str,
    panel_width: int,
) -> dict[int, bytes]:
    if not baseline.scans:
        return {}
    scans = {scan.scan_id: scan for scan in baseline.scans}
    if scan_id is not None and scan_id not in scans:
        raise ValueError(
            f"diagnostic requested unknown scan {scan_id!r}")
    scan = baseline.scans[-1] if scan_id is None else scans[scan_id]
    if receiver.file_identity(scan.source_path) != (
            scan.source_sha256, scan.source_size):
        raise payloaddec.FatalIntegrityError(
            f"diagnostic source TIFF changed for scan {scan.scan_id}")
    image = receiver.load_image(scan.source_path)
    if (tuple(image.shape[:2]) != scan.image_shape
            or str(image.dtype) != scan.image_dtype):
        raise payloaddec.FatalIntegrityError(
            f"diagnostic source metadata changed for scan {scan.scan_id}")
    view = feedback.materialize_receiver_view(
        session, baseline, active_map=active_map)
    descriptor = _descriptor(session.baseline.format_id)
    combined = receiver._combined_pilot_result(baseline)
    display = _display_result(
        session, scan, active_map=active_map)
    progress = receiverdiag.DiagProgress(phase=phase)
    if active_tile is not None:
        progress.active_tiles = {tuple(active_tile)}
    pages = {}
    footer = (
        f"E024 {session.envelope.profile} · generation "
        f"{session.head.ordinal if display_generation is None else display_generation} "
        f"· certificates {len(session.certificates)} · "
        f"accepted revisions "
        f"{sum(row.accepted for row in session.revisions.values())} · "
        f"feedback CRC calls {session.crc_calls}")
    for page in session.baseline.pages:
        canvas = receiverdiag.compose_diagnostic(
            image, scan.survey.unpack(), display, combined, descriptor, view,
            page=page, progress=progress, panel_width=panel_width)
        framed = Image.new(
            "RGB", (canvas.width, canvas.height + 28), (24, 24, 24))
        framed.paste(canvas, (0, 0))
        ImageDraw.Draw(framed).text(
            (8, canvas.height + 7), footer, fill=(225, 225, 225))
        stream = io.BytesIO()
        framed.save(stream, format="PNG")
        pages[int(page)] = stream.getvalue()
    return pages


def render_final(
    path: Path,
    session: feedbackstate.E024Session,
    baseline: receiver.ReceiverSession,
    *,
    panel_width: int,
) -> list[Path]:
    pages = diagnostic_pngs(
        session, baseline, phase="feedback_complete",
        panel_width=panel_width)
    outputs = []
    for page, png in pages.items():
        target = (
            path if len(pages) == 1 else
            path.with_name(f"{path.stem}_p{page:04d}{path.suffix}"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(png)
        outputs.append(target)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-e023b", type=Path, default=None,
        help="immutable E023b generation-zero state; required with --fresh")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument(
        "--profile", choices=sorted(feedbackstate.FEEDBACK_PROFILES),
        default=None,
        help="fresh default: combined; resume default: state profile")
    parser.add_argument(
        "--certificate-union", type=Path, default=None,
        help="optional conflict-checked E023b merge bundle; fresh import only")
    parser.add_argument("--max-generations", type=int, default=None)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--diag", nargs="?", const=str(DEFAULT_DIAG), default=None,
        metavar="DIR")
    parser.add_argument("--diag-port", type=int, default=8024)
    parser.add_argument("--panel-width", type=int, default=600)
    args = parser.parse_args()

    if args.fresh and args.from_e023b is None:
        parser.error("--fresh requires --from-e023b")
    if args.fresh and args.state.exists():
        parser.error(
            "--fresh refuses to overwrite an existing --state")
    if not args.fresh and not args.state.exists():
        parser.error(
            "resume requires an existing --state; use --fresh")
    if not args.fresh and args.certificate_union is not None:
        parser.error("--certificate-union is frozen at fresh import")

    try:
        if args.fresh:
            baseline = receiver.load_session(args.from_e023b)
            session = feedback.create_session(
                args.from_e023b, baseline,
                profile=(args.profile
                         or feedbackstate.PROFILE_COMBINED),
                certificate_union=args.certificate_union)
            baseline_path = args.from_e023b
        else:
            session, baseline = feedbackstate.load_session(
                args.state, baseline_path=args.from_e023b)
            baseline_path = Path(
                args.from_e023b or session.baseline.path)
            if (args.profile is not None
                    and session.envelope.profile != args.profile):
                raise ValueError(
                    f"state profile is {session.envelope.profile!r}, "
                    f"not {args.profile!r}")
    except payloaddec.FatalIntegrityError as exc:
        print(f"FATAL integrity violation: {exc}", file=sys.stderr)
        return 3
    except (OSError, ValueError, pickle.UnpicklingError, EOFError) as exc:
        print(f"state/config error: {exc}", file=sys.stderr)
        return 2

    if not args.fresh and session.head.fixed_point:
        print(
            f"E024: profile={session.envelope.profile} "
            f"generation={session.head.ordinal} "
            f"certified={len(session.certificates)} "
            f"feedback_calls={session.crc_calls} fixed_point=True "
            f"authoritative="
            f"{feedbackstate.authoritative_digest(session)[:16]}")
        print(f"  state {args.state}")
        print(
            "  unchanged feedback frontier "
            "(exact no-op; report/image/diag not rewritten)")
        return 0

    diag = None
    diag_failed = False
    if args.diag is not None:
        try:
            import e024_diag
            diag = e024_diag.DiagViewer(
                Path(args.diag), args.diag_port)
        except Exception as exc:
            print(f"  [diag] unavailable: {exc!r}; receiver continues",
                  flush=True)

    def publish(
        phase, view_session, active_tile=None, active_map=None,
        scan_id=None, display_generation=None,
    ):
        nonlocal diag_failed
        if diag is None or diag_failed:
            return
        try:
            pages = diagnostic_pngs(
                view_session, baseline, active_tile=active_tile,
                active_map=active_map, scan_id=scan_id,
                display_generation=display_generation,
                phase=phase, panel_width=args.panel_width)
            diag.publish(pages, {
                "phase": phase,
                "generation": (
                    view_session.head.ordinal
                    if display_generation is None
                    else display_generation),
                "certified": len(view_session.certificates),
                "revisions": sum(
                    row.accepted for row in view_session.revisions.values()),
                "attempts": view_session.crc_calls,
            })
        except Exception as exc:
            diag_failed = True
            try:
                diag.disable(exc)
            except Exception:
                pass

    published_attempts = 0
    last_saved_generation_id = None

    def on_attempt(view_session, attempt, active_map=None):
        nonlocal published_attempts
        published_attempts += 1
        if published_attempts == 1 or published_attempts % 10 == 0:
            scan_id = (
                attempt.source
                if attempt.source in {
                    scan.scan_id for scan in baseline.scans}
                else next((
                    view_session.revisions[revision_id].scan_id
                    for revision_id in attempt.input_revision_ids
                    if revision_id in view_session.revisions
                ), None))
            publish(
                attempt.stage, view_session,
                active_tile=attempt.tile_key,
                active_map=active_map, scan_id=scan_id,
                display_generation=attempt.generation)

    def on_generation(view_session, report):
        nonlocal last_saved_generation_id
        feedbackstate.save_session(
            args.state, view_session, baseline,
            baseline_path=baseline_path)
        last_saved_generation_id = view_session.head.generation_id
        save_report(args.report, view_session, baseline)
        publish(
            f"generation_{view_session.head.ordinal}_complete",
            view_session)
        print(
            f"  generation {view_session.head.ordinal}: "
            f"accepted={report['revision'].get('accepted', 0)} "
            f"changed_cells={report['changed_cells']} "
            f"calls={report['decode'].get('crc_calls', 0)} "
            f"new_certificates={report['new_certificates']} "
            f"total={len(view_session.certificates)}", flush=True)

    try:
        publish(f"generation_{session.head.ordinal}", session)
        result, run_report = feedback.run_feedback(
            session, baseline, baseline_path=baseline_path,
            max_generations=args.max_generations,
            on_attempt=on_attempt, on_generation=on_generation)
        if (result is session
                or last_saved_generation_id
                != result.head.generation_id):
            feedbackstate.save_session(
                args.state, result, baseline,
                baseline_path=baseline_path)
        session = result
        save_report(args.report, session, baseline)
        outputs = render_final(
            args.out, session, baseline, panel_width=args.panel_width)
    except payloaddec.FatalIntegrityError as exc:
        print(f"FATAL integrity violation: {exc}", file=sys.stderr)
        return 3
    except (OSError, ValueError) as exc:
        print(f"feedback error: {exc}", file=sys.stderr)
        return 2
    finally:
        if diag is not None:
            try:
                diag.close()
            except Exception as exc:
                print(
                    f"  [diag] close failed: {exc!r}; "
                    "receiver continues", flush=True)

    summary = session.summary()
    print(
        f"E024: profile={session.envelope.profile} "
        f"generation={session.head.ordinal} "
        f"certified={len(session.certificates)} "
        f"feedback_calls={session.crc_calls} "
        f"fixed_point={session.head.fixed_point} "
        f"authoritative={feedbackstate.authoritative_digest(session)[:16]}")
    print(f"  state {args.state}\n  JSON {args.report}")
    for path in outputs:
        print(f"  PNG {path}")
    if run_report["noop"]:
        print("  unchanged feedback frontier (exact no-op)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
