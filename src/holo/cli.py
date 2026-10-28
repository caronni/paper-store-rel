"""The holo CLI: registry | fit | capacity | generate | decode | discover.

Track 3 decode is session-oriented: source bytes are content-authenticated at
ingest, and ``--diag`` is observer-only.
Until the v1 physical/null placement policy is frozen, ``decode`` runs with
the registered historical stand-ins and emits a prominent provisional warning
on every invocation; generation remains production-active.
Invocation (no console script — the venv stays clean):

    ./confetti.py <cmd> ...                   # repo-root wrapper
    env/bin/python src/holo/cli.py <cmd> ...
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import warnings
from pathlib import Path

if __package__ in (None, ""):   # executed as a file: put src/ on the path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from holo.cli_gen import (
    _SOURCE_FRACTION_HELP,
    cmd_capacity,
    cmd_fit,
    cmd_generate,
    cmd_registry,
)
from holo.devices.profiles import make_spec
from holo.devices.registry import PRINTERS, SCANNERS
from holo.format.descriptor import CODINGS
from holo.format.profiles import Family
from holo.gen.emit import default_out_dir, emit_volume
from holo.gen.plan import max_payload_bytes, plan_volume, pooled_plane_tier
from holo.gen.sheet import (
    DEFAULT_ENGINE_DPI,
    DEFAULT_PAPER,
    PAPER_PROFILES,
    dots_per_cell,
    fit,
    get_paper,
    page_dots_xy,
    sheet_layout,
    usable_dots_xy,
)

_SOURCE_FRACTION_HELP = (
    "fraction of printed tiles that carry SOURCE data; the rest are "
    "repair (fountain redundancy). 0.5 means any ~half of the printed "
    "tiles recovers the whole payload; lower = more robust, less "
    "capacity. Profiles set this — override it only when you know why.")


def _finite_nonnegative(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        raise argparse.ArgumentTypeError("must be a finite non-negative number")
    return parsed


def _diag_interval(value: str) -> float:
    """Pane-frame throttle: a positive floor keeps §10.8's throttle
    boundaries testable; 0 would silently mean render-every-event."""
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.25:
        raise argparse.ArgumentTypeError("must be at least 0.25 seconds")
    return parsed


def _diagnostic_panel_width(value: str) -> int:
    parsed = int(value)
    if parsed < 80:
        raise argparse.ArgumentTypeError("must be at least 80 pixels")
    return parsed


def _tcp_port(value: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= 65535:
        raise argparse.ArgumentTypeError("must be in [0, 65535]")
    return parsed


def _engine_dpi(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive dpi")
    return parsed


def _worker_count(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _validate_diagnostic_directory(
    directory: str | Path,
    *,
    state_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Return an isolated resolved diagnostic directory.

    Diagnostics are observer state.  They therefore may neither occupy nor
    contain an authoritative receiver path, and no authoritative path may
    contain them.  Resolving first also catches aliases through existing
    symlinks without requiring any of the targets to exist.
    """
    diagnostic = Path(directory).resolve()
    authorities = (
        ("--state", Path(state_path).resolve()),
        ("--out", Path(output_path).resolve()),
    )
    for label, authority in authorities:
        overlap = (
            diagnostic == authority
            or diagnostic in authority.parents
            or authority in diagnostic.parents
        )
        if overlap:
            raise SystemExit(
                f"--diag-dir must be isolated from {label}: "
                f"{diagnostic} overlaps {authority}"
            )
    return diagnostic


def _print_parked_inventory(res) -> None:
    """v0.33 durable-advice epilogue (RECEIVE-DESIGN §10.7 parked row).

    Parked mop-up windows persist in state, so a cold resume still
    reports the pending tail — the operator's rescan decision should see
    unattempted work before paying for new scans.
    """
    state = getattr(res, "state", None)
    parked = getattr(state, "parked", ())
    if not parked:
        return
    by_lane: dict[tuple[str, str], list[int]] = {}
    for row in parked:
        by_lane.setdefault(
            (row.capture_id, row.lane_id), []).append(int(row.support_cells))
    print(f"mop-up tail parked: {len(parked)} window(s) across "
          f"{len(by_lane)} capture lane(s) (--mopup)")
    for (capture_id, lane_id), cells in sorted(by_lane.items()):
        cells.sort()
        print(f"  {capture_id[:12]}/{lane_id}: {len(cells)} window(s), "
              f"support cells min {cells[0]} median "
              f"{cells[len(cells) // 2]} max {cells[-1]}")
    print(
        "hint: the mop-up tail has not been attempted — a rerun with "
        "--mopup may close without new scans."
    )


def _print_pending_refinement(res) -> None:
    """v0.42 flag-family epilogue: pending refinement lanes, by flag name.

    Derived from durable state (capture plans vs retained level prefixes),
    so a cold resume still reports the parked family.  Advisory only.

    PK4.3: supplemental lanes ride ``--refine`` (they are the plan's last
    family), so they are counted here and named separately — an operator
    reading "3 eligible" should know one of them forces a campaign arm.
    """
    state = getattr(res, "state", None)
    pending = 0
    supplemental = 0
    for capture in getattr(state, "captures", ()):
        done = len(capture.levels)
        for ordinal, lane in enumerate(capture.plan):
            if ordinal < done:
                continue
            if getattr(lane, "refine_of", None) is not None:
                pending += 1
            elif getattr(lane, "uplift_of", None) is not None:
                pending += 1
                supplemental += 1
    if not pending:
        return
    tail = (f", incl. {supplemental} supplemental" if supplemental else "")
    print(f"refinement pending: {pending} eligible lane(s){tail} (--refine)")


def _print_close_shortfall(res, *, suppress_rescan_hint: bool = False) -> None:
    """Advisory epilogue from the last LIVE close (never durable state).

    Counts and ranks are advice, not a success condition (RECEIVE-DESIGN
    requirement 8); durable state cannot reconstruct per-block shortfall,
    so a factory-less or failing result simply prints nothing extra.  The
    rescan guidance is the measured 004.0b/016 multi-scan law: 3-4
    repositioned scans are the knee, worth +12-15% capacity.
    """
    try:
        progress = res.close_progress()
    except Exception:
        return
    if progress is None or not progress.blocks:
        return
    if progress.count_only:
        # Count-only projection (a deferred barrier or a count-gated
        # skip): rank/solve were never computed, so report the exact
        # distinct-symbol reach and never a fake rank shortfall.
        have = sum(row.have for row in progress.blocks)
        needed = sum(row.needed for row in progress.blocks)
        count_shortfall = sum(
            max(0, row.needed - row.have) for row in progress.blocks)
        line = (
            f"close progress: distinct-symbol reach {have}/{needed} over "
            f"{len(progress.blocks)} fountain block(s)"
            f"; count shortfall {count_shortfall}"
            f"; rank/solve not computed"
        )
    else:
        unsolved = [row for row in progress.blocks if not row.solved]
        shortfall = sum(max(0, row.needed - row.rank) for row in unsolved)
        line = (
            f"close progress: {len(progress.blocks) - len(unsolved)}"
            f"/{len(progress.blocks)} fountain blocks solved"
            f"; symbol-rank shortfall {shortfall}"
        )
    metadata = progress.metadata
    if metadata is not None and metadata.rank_shortfall:
        line += f"; metadata rank shortfall {metadata.rank_shortfall}"
    print(line)
    if not suppress_rescan_hint:
        print(
            "hint: acquire more scans — RE-PLACE (reposition/rotate) the "
            "sheet between scans and feed every scan; 3-4 independent scans "
            "is the measured knee (docs/PRINT-DAY.md)."
        )


def _print_mopup_drops(res) -> None:
    """D5 drop report (2026-08-02 ruling, replacing the v0.36
    byte-inequality canary; docs/CANARY-D5-DISAGREEMENTS.md).

    Mop-up re-observations at committed cells are dropped by the
    extension-only supersession — committed evidence is never revised —
    and dropping is expected overlap geometry, never an alarm by count.
    The health signal is the WINNER-FLIP rate: dropped cells whose
    implied decision (K sign / CMY7 state / CMY8 plane pattern) differs
    from the committed owner's.  Measured anchors: 5.35% healthy real
    scrap, 0% clean synthetic, ~50%+ for a misplaced window.  Advice
    only; thresholds/doctrine deferred to post-08-04 incidence data.
    Never a gate; exit codes and payload bytes never change here.
    """
    counters = getattr(getattr(res, "state", None), "counters", None)
    dropped = (0 if counters is None
               else int(getattr(counters, "mopup_dropped_observations", 0)))
    if not dropped:
        return
    flips = int(getattr(counters, "mopup_winner_flips", 0))
    print(
        f"NOTE: mop-up supersession dropped {dropped} re-observation(s) "
        f"at committed cells; winner flips {flips} "
        f"({100.0 * flips / dropped:.1f}%) (two-view consistency canary "
        f"— a high flip rate suggests a misplaced mop-up window or "
        f"physical damage; committed evidence unchanged)")


def _print_surplus_audit(res, *, verified: bool) -> None:
    """D16 report-only surplus-audit epilogue (advisory, never authoritative).

    The fountain's GF(2) solve never checks dependent (surplus) equations,
    so a wrong certified symbol can hide behind redundancy (verified run)
    or brick a close without naming a culprit (integrity failure).  The
    close-time audit re-encodes every certified symbol of solved blocks;
    this prints its findings.  Pure observation: exit codes, payload
    bytes, and durable state are decided elsewhere and never change here.
    """
    try:
        progress = res.close_progress()
    except Exception:
        return
    entries = (
        () if progress is None
        else getattr(progress, "surplus_inconsistencies", ()))
    if not entries:
        return
    print(
        f"WARNING: surplus-consistency audit — {len(entries)} certified "
        f"symbol(s) disagree with the reconstructed volume:")
    for row in entries:
        print(f"  stream {row.stream_id} page {row.page} "
              f"tile ({row.ty},{row.tx}) counter {row.counter}")
    if verified:
        print(
            "the payload verified by SHA-256 and is unaffected; each "
            "listed certificate is a wrong equation that redundant "
            "evidence masked. Investigate the flagged tiles (mixed "
            "sheets or an upstream certificate fault).")
    else:
        print(
            "these certificates contradict the solved fountain system — "
            "start any integrity postmortem at the flagged tiles.")


def _print_plane_certificates(state, spec, requested_pages) -> None:
    """P1 (docs/INDEPENDENT-PLANES.md §6): per-plane certificate and
    open-slot counts for a colour row.

    A one-stream row (K, and the packed cmy7 rows, whose base-7 symbol has
    no per-plane certificate to count) prints nothing at all, so K output
    is unchanged.  For a cmy8 row the planes ARE the streams, and the
    split is the first number every colour question needs: the 2026-08
    campaign answered "how far behind is Y?" by loading multi-GB states
    because neither the epilogue nor the live view said.

    The denominator is the page domain actually in play — pages carrying a
    certificate, plus any explicitly requested with ``--page`` — never
    ``spec.max_pages``, which is the addressing capacity (133 pages at
    1961 tiles), not this volume's page count.
    """
    streams = tuple(getattr(spec, "stream_ids", ()) or ())
    if len(streams) < 2:
        return
    certificates = tuple(getattr(state, "certificates", ()) or ())
    counts = dict.fromkeys(streams, 0)
    pages = set(requested_pages or ())
    for row in certificates:
        pages.add(int(row.page))
        if row.stream_id in counts:
            counts[row.stream_id] += 1
    per_page = int(spec.tiles_per_page)
    if not pages:
        # Never print zero where the fact is unavailable: with no page
        # reached and none requested there is no slot denominator.
        print("planes: "
              + " · ".join(f"{stream} {counts[stream]} certified"
                           for stream in streams)
              + " · open slots unavailable (no page reached)")
        return
    slots = len(pages) * per_page
    print(
        f"planes ({len(pages)} page(s) × {per_page} tiles"
        f" = {slots} slots/plane): "
        + " · ".join(
            f"{stream} {counts[stream]} certified,"
            f" {slots - counts[stream]} open"
            for stream in streams))


def _print_plane_fields(rows) -> None:
    """W5 epilogue (docs/PLANE-FIELDS.md §6.2): per-plane delta RMS/peak in
    dots, coverage, and adopted-plane tallies for a run that carried
    plane_fields.* Details -- ``holo.receive.diag.field_stats.FieldStats``
    rows, replayed from this invocation's own ``events.jsonl`` (see the
    diagnostics-finalize block in :func:`cmd_decode`: the diagnostic log
    already has every stage.complete Detail, so reading it back is the
    least-invasive way to reach these numbers without a second live
    observer).  Never called with an empty ``rows`` -- the caller gates
    on that -- so a run without the field arm (the W2 dial default) prints
    nothing here, dial off meaning zero output change.
    """
    for row in rows:
        planes = [plane for plane in ("C", "M", "Y") if plane in row.rms_dots]
        detail = ", ".join(
            f"{plane} rms {row.rms_dots[plane]:.2f}d peak "
            f"{row.peak_dots.get(plane, row.rms_dots[plane]):.2f}d"
            for plane in planes
        ) or "no per-plane rms reported"
        coverage = "n/a" if row.coverage is None else f"{row.coverage:.1%}"
        adopted = ", ".join(
            f"{name or '(none)'}×{count}"
            for name, count in sorted(row.adopted_counts.items())
        ) or "(none)"
        capture = row.capture_id[:12] if row.capture_id else "-"
        print(
            f"plane fields {capture}/{row.lane_id or '-'} "
            f"({row.calls} event(s)): {detail} "
            f"· coverage {coverage} · adopted {adopted}"
        )


def cmd_decode(args) -> int:
    from holo.receive import (
        CaptureInput,
        DiscoveryReceiveRequest,
        ProvisionalReceiverWarning,
        ReceiveRequest,
        run_discovery_receive,
        run_receive,
    )
    if args.workers is not None:
        # Execution-only knob (the --profile-timing family): pooled
        # numeric kernels produce bit-identical results at any worker
        # count (tests/holo/test_parallel_exactness.py); never policy,
        # schema, or durable state.
        from holo.receive import _parallel
        _parallel.set_worker_count(args.workers)
    from holo.format.registry import (
        DEFAULT_DISCOVERY_ROW_IDS,
        FORMAT_ROWS,
        get_format_row,
    )
    from holo.receive.discovery_state import (
        DISCOVERY_MAGIC,
        state_file_magic,
    )
    from holo.receive.production import production_pipeline
    from holo.receive.session import STATE_MAGIC, load_session

    n = len(args.scans)
    if len(args.scan_dpi) != n:
        raise SystemExit(
            f"got {n} scans but {len(args.scan_dpi)} --scan-dpi values; "
            "declare the true dpi of every source")
    expected = args.source_sha256 or [None] * n
    if len(expected) != n:
        raise SystemExit(
            f"got {n} scans but {len(expected)} --source-sha256 values")
    captures = tuple(
        CaptureInput(source=source, dpi=dpi, expected_sha256=sha256)
        for source, dpi, sha256 in zip(
            args.scans, args.scan_dpi, expected, strict=True)
    )
    state_path = Path(args.state)
    established_magic = (
        state_file_magic(state_path) if state_path.exists() else None)
    if established_magic not in (None, STATE_MAGIC, DISCOVERY_MAGIC):
        raise SystemExit("state file is not a supported Holo receiver state")
    if args.format_ref is not None and args.coding is not None:
        raise SystemExit("--format replaces --coding; pick one")
    if args.format_ref is not None and args.printer is not None:
        raise SystemExit(
            "--format carries its geometry; --printer is the legacy "
            "--coding route")
    if (args.coding is not None or args.format_ref is not None) \
            and established_magic == DISCOVERY_MAGIC:
        raise SystemExit(
            "an automatic-discovery state cannot resume with an explicit "
            "format")

    discovery_mode = (
        args.coding is None and args.format_ref is None
        and established_magic != STATE_MAGIC)
    if args.no_close and discovery_mode:
        raise SystemExit(
            "--no-close is an exact-session knob; discovery decides "
            "format rows before any close policy applies")
    page_hypotheses = (
        None if args.page is None else tuple(args.page))
    spec = None
    pipeline = None
    exact_request = None
    discovery_request = None
    if discovery_mode:
        candidate_row_ids = None
        if args.printer is not None:
            candidate_row_ids = tuple(sorted({
                make_spec(
                    FORMAT_ROWS[row_id].coding.coding_id,
                    args.printer,
                ).spec_id
                for row_id in DEFAULT_DISCOVERY_ROW_IDS
            }))
            unavailable = set(candidate_row_ids) - set(FORMAT_ROWS)
            if unavailable:
                raise SystemExit(
                    "selected printer has no registered receive rows: "
                    + ", ".join(sorted(unavailable)))
        discovery_request = DiscoveryReceiveRequest(
            captures,
            state_path=state_path,
            candidate_row_ids=candidate_row_ids,
            page_hypotheses=page_hypotheses,
            defer_fountain_close=args.complete,
            run_mopup=args.mopup,
            run_refine=args.refine,
        )
    else:
        if args.format_ref is not None:
            from holo.format.resolve import resolve_format_ref
            try:
                spec = resolve_format_ref(args.format_ref)
            except (KeyError, ValueError) as exc:
                raise SystemExit(str(exc)) from None
            # The canonical id is what the state is named by, and since
            # FORMAT-SPACE §16 it is almost never the string an operator
            # types.  Print both: the short spelling they recognize and
            # the id their state will carry.  A byte-exact L: line prints
            # nothing (the two are equal).
            if spec.spec_id != args.format_ref.removeprefix("L:"):
                print(f"format {spec.display_id} -> state {spec.spec_id}")
            if spec.coding.namespace == "v2" \
                    and spec.coding.cell_dots is None:
                raise SystemExit(
                    f"{spec.display_id}: pitch {spec.coding.pitch} is off "
                    f"the 600 grid — the receiver's raster path for "
                    f"off-600 pitches is pending (emission works; "
                    f"decoding such a sheet needs the pitch-general "
                    f"survey, FORMAT-SPACE §15.3)")
        elif args.coding is not None:
            spec = make_spec(args.coding, args.printer or "default")
        else:
            established = (
                load_session(
                    state_path,
                    defer_fountain_validation=True,
                )
                if args.complete or args.no_close
                else load_session(state_path)
            )
            if args.no_close and established.status.value != "open":
                print(
                    f"detaching {established.status.value} close "
                    f"(--no-close): the state reopens; a later closing "
                    f"run recomputes the close from all certificates")
            from holo.format.resolve import resolve_format_ref
            try:
                # Total over catalog rows, fossils (bare or L:) and v2
                # format ids (FORMAT-SPACE §10): a state file alone
                # names its format completely.
                spec = resolve_format_ref(established.format_row_id)
            except (KeyError, ValueError):
                raise SystemExit(
                    "this exact state uses an unresolvable format; supply "
                    "--coding and --printer to resume it") from None
        exact_request = ReceiveRequest(
            spec,
            captures,
            state_path=state_path,
            page_hypotheses=page_hypotheses,
            defer_fountain_close=args.complete or args.no_close,
            run_mopup=args.mopup,
            run_refine=args.refine,
        )
        pipeline = production_pipeline(exact_request)

    observer = None
    observer_factory = None
    diagnostics = {}
    diag_dir = None
    timing_observer = None
    if args.profile_timing:
        if args.diag:
            # Doctrine: the profiling harness is a minimal single-decode
            # observer; pane rendering would inflate every wall number.
            raise SystemExit("--profile-timing conflicts with --diag")
        from holo.receive.diag.timing import TimingObserver
        timing_observer = TimingObserver()
        if discovery_mode:
            observer_factory = (
                lambda report_spec, report_pipeline: timing_observer)
        else:
            observer = timing_observer
    if args.diag:
        diag_dir = (Path(args.diag_dir) if args.diag_dir else
                    Path(str(args.state) + ".diag"))
        diag_dir = _validate_diagnostic_directory(
            diag_dir, state_path=args.state, output_path=args.out)
        from holo.receive.diag import ReceiveDiagnostics
        def make_diagnostics(report_spec, report_pipeline):
            row_id = report_spec.spec_id
            if row_id in diagnostics:
                return diagnostics[row_id]
            directory = (
                diag_dir if not discovery_mode
                else diag_dir / row_id.replace("@", "_"))
            pipeline_pages = getattr(
                report_pipeline, "page_hypotheses", page_hypotheses)
            requested_pages = (
                tuple(range(report_spec.max_pages))
                if pipeline_pages is None else pipeline_pages)
            route_domains = None
            address_stage = getattr(
                getattr(report_pipeline, "lanes", None), "address", None)
            reporter = getattr(address_stage, "route_domain_report", None)
            if reporter is not None:
                try:
                    route_domains = reporter(report_spec, requested_pages)
                except Exception as exc:
                    print(
                        f"route-domain report unavailable for {row_id}: "
                        f"{type(exc).__name__}: {exc}",
                        file=sys.stderr,
                    )
            try:
                instance = ReceiveDiagnostics(
                    directory,
                    report_spec,
                    receiver_policy_id=report_pipeline.policy_id,
                    page_domain=requested_pages,
                    qualification_status=report_pipeline.qualification_status,
                    qualification_notes=report_pipeline.qualification_notes,
                    route_domains=route_domains,
                    interval_s=args.diag_interval,
                    panel_width=args.diag_panel_width,
                    port=(args.diag_port if not diagnostics else None),
                    on_server=lambda url, row=row_id: print(
                        f"diagnostics live [{row}]: {url}",
                        file=sys.stderr),
                )
                diagnostics[row_id] = instance
                return instance
            except Exception as exc:
                print(
                    f"diagnostics unavailable for {row_id}: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                return None

        if discovery_mode:
            observer_factory = make_diagnostics
        else:
            assert spec is not None and pipeline is not None
            observer = make_diagnostics(spec, pipeline)
    elif (args.diag_dir or args.diag_port is not None
          or args.diag_interval != 3.0 or args.diag_panel_width != 600):
        option = (
            "--diag-dir" if args.diag_dir else
            "--diag-port" if args.diag_port is not None else
            "--diag-interval" if args.diag_interval != 3.0 else
            "--diag-panel-width")
        raise SystemExit(f"{option} requires --diag")

    # Library callers retain ordinary warnings-filter control. A CLI run is
    # an operator action, so never let Python's once-per-location default hide
    # this unqualified production status on a resume.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("always", ProvisionalReceiverWarning)
            if discovery_mode:
                assert discovery_request is not None
                res = run_discovery_receive(
                    discovery_request,
                    observer_factory=observer_factory,
                )
            else:
                assert exact_request is not None and pipeline is not None
                res = run_receive(
                    exact_request, pipeline=pipeline, observer=observer,
                    finalize_deferred_close=not args.no_close)
    except BaseException:
        for diagnostic in diagnostics.values():
            diagnostic.close()
        raise
    if timing_observer is not None:
        from holo.receive.diag.timing import render_timing_table
        print(render_timing_table(timing_observer), file=sys.stderr)
    diag_report_written = False
    field_summary: tuple = ()
    if diagnostics and diag_dir is not None:
        written = []
        for row_id, diagnostic in diagnostics.items():
            report_state = (
                res.state if not discovery_mode
                else res.state.branch(row_id))
            written.extend(diagnostic.finalize(report_state))
        diag_report_written = any(
            path.name == "report.json" for path in written)
        failures = tuple(
            failure
            for diagnostic in diagnostics.values()
            for failure in diagnostic.failures
        )
        failures = tuple(dict.fromkeys(
            (*res.observer_failures, *failures)))
        if failures:
            report_status = (
                f"final report written to {diag_dir}"
                if diag_report_written else "final report unavailable"
            )
            print(
                "diagnostic capabilities degraded: "
                + "; ".join(failures)
                + f"; {report_status}",
                file=sys.stderr,
            )
        # W5 (docs/PLANE-FIELDS.md §6.2): read the plane_fields.* Details
        # back from each row's own events.jsonl -- ReceiveDiagnostics
        # already logs every event's Details unconditionally (JsonlDiagnostics
        # writes the scalar log regardless of the live view), so this reuses
        # that existing persisted channel instead of composing a second live
        # observer alongside diagnostics on cmd_decode's single `observer=`
        # slot. A run without the field arm writes no such Details, so
        # replay yields an empty summary and nothing prints below.  Some
        # tests substitute a bare stub for ReceiveDiagnostics (no
        # events_path), so this is best-effort, never load-bearing.
        from holo.receive.diag.field_stats import FieldStats, replay_jsonl_row
        field_stats = FieldStats()
        for diagnostic in diagnostics.values():
            events_path = getattr(diagnostic, "events_path", None)
            if events_path is None or not events_path.exists():
                continue
            with events_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    field_stats(replay_jsonl_row(json.loads(line)))
        field_summary = field_stats.summary()
    if discovery_mode:
        for survey in res.state.surveys:
            c_dots = "?" if survey.c_dots is None else str(survey.c_dots)
            print(
                f"capture {survey.facts.source_sha256}: c={c_dots}")
        selected = res.state.selected_row_id or "unresolved"
        print(
            f"format: {selected}; "
            f"{len(res.state.candidate_row_ids)} registered candidate(s); "
            f"status={res.state.status.value}; "
            f"CRC attempts={res.state.decoder_invocations}")
    else:
        for row in res.captures:
            changed = "committed" if row.state_changed else "unchanged"
            print(
                f"capture {row.source_sha256}: "
                f"{row.status.value}; {changed}")
    print(f"state: {args.state}  sha256 {res.authoritative_sha256}")
    if diag_report_written:
        print(f"diagnostics: {diag_dir}")
    if spec is not None:
        _print_plane_certificates(res.state, spec, page_hypotheses)
    if field_summary:
        _print_plane_fields(field_summary)
    if not res.verified:
        _print_parked_inventory(res)
        _print_pending_refinement(res)
        if not args.no_close:
            _print_close_shortfall(
                res,
                suppress_rescan_hint=bool(
                    getattr(res.state, "parked", ())))
        _print_mopup_drops(res)
        _print_surplus_audit(res, verified=False)
        if args.no_close:
            n_certs = len(res.state.certificates)
            print(f"close skipped (--no-close): {n_certs} certificates "
                  f"accumulated; no closing record was read, attempted, "
                  f"or written. Close with a plain or --complete run.")
            return 2
        print("NOT RECOVERED — no payload SHA has verified.")
        return 2
    if res.payload is None:
        raise RuntimeError("verified receiver omitted payload bytes")
    _print_mopup_drops(res)
    _print_surplus_audit(res, verified=True)
    output = Path(args.out)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(res.payload)
            stream.flush()
            os.fsync(stream.fileno())
        # A same-directory hard link is an atomic no-overwrite publication:
        # disk-full/interruption can leave only the private temporary, never
        # a partial file at the requested payload path.
        os.link(temporary, output)
        try:
            directory = os.open(output.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    except FileExistsError:
        raise SystemExit(f"refusing to overwrite existing payload: {output}")
    except OSError as exc:
        raise SystemExit(f"could not write recovered payload {output}: {exc}")
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    print(f"VERIFIED: wrote {len(res.payload)} bytes to {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    effective_argv = sys.argv[1:] if argv is None else list(argv)
    if effective_argv and effective_argv[0] == "discover":
        # Characterization is an isolated instrument.  This composition-root
        # import exposes it without coupling generator, receiver, format, or
        # device-library code to its implementation.
        from holo.characterize.__main__ import main as characterize_main

        return characterize_main(
            effective_argv[1:], prog="holo discover"
        )

    ap = argparse.ArgumentParser(
        prog="holo",
        description="Store files on plain printed paper. `fit` sizes a "
                    "field for a sheet; `capacity` plans volumes; "
                    "`generate` writes printable PostScript; "
                    "`decode` ingests scans into a resumable receiver "
                    "session; `discover` characterizes a print/scan path.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_selection(p: argparse.ArgumentParser) -> None:
        p.add_argument("--format", metavar="ID",
                       help="the printed format, in full: "
                            "PITCH-FAMILY[-RUNGS][-pSITES][-vGEN]@TYxTX "
                            "(e.g. c2-k-r0700@53x37, "
                            "c2-cmy8-r0700@53x37); `fit` derives the "
                            "matrix for a paper. Requires "
                            "--source-fraction; excludes "
                            "--profile/--coding/--printer")
        p.add_argument("--paper", metavar="NAME", default=None,
                       help="paper bundle for a --format field: "
                            + " | ".join(sorted(PAPER_PROFILES))
                            + f" (default {DEFAULT_PAPER})")
        p.add_argument("--dpi", type=_engine_dpi, metavar="N", default=None,
                       help="engine dot grid for a --format field "
                            f"(default {DEFAULT_ENGINE_DPI}, the only "
                            "measured class); pitch x dpi must be a whole "
                            "number of dots per cell")
        p.add_argument("--profile", metavar="NAME",
                       help="what to optimize for: rocksolid | resilient "
                            "| high-volume | max (see `registry`)")
        p.add_argument("--coding", metavar="ID",
                       help="LEGACY identity: cell size + code rate (e.g. "
                            "c3-r0550); requires --source-fraction. "
                            "Legacy rows are fossils — they decode via "
                            "--format L:<id>; sunset pending")
        p.add_argument("--printer", default=None, metavar="ID",
                       help="printer whose margins set the printable "
                            "area for a legacy --profile/--coding row "
                            "(default: the locked conservative "
                            "600dpi/6mm target)")
        p.add_argument("--source-fraction", type=float, default=None,
                       metavar="Q", help=_SOURCE_FRACTION_HELP)

    pr = sub.add_parser("registry",
                        help="list codings, printers, scanners, and "
                             "profiles")
    pr.add_argument("-v", "--verbose", action="store_true",
                    help="full detail: cell/tile pitch, code + word "
                         "internals, per-printer derived geometry and "
                         "page capacity, resolved profile numbers")

    pfit = sub.add_parser(
        "fit",
        help="largest tile matrix for a paper + cell pitch, with the "
             "ready-to-use format ids")
    pfit.add_argument("--paper", default=DEFAULT_PAPER, metavar="NAME",
                      help="paper bundle: "
                           + " | ".join(sorted(PAPER_PROFILES))
                           + f" (default {DEFAULT_PAPER})")
    pfit.add_argument("--pitch", required=True, metavar="TOKEN",
                      help="cell pitch: a registered class (c1..c4) or an "
                           "exact rational NiD = N/D inch (e.g. 1i400)")
    pfit.add_argument("--dpi", type=_engine_dpi, default=DEFAULT_ENGINE_DPI,
                      metavar="N",
                      help=f"engine dot grid (default {DEFAULT_ENGINE_DPI})")

    pc = sub.add_parser(
        "capacity",
        help="plan a payload (--payload-bytes) or show the max payload "
             "for a page count (--pages)")
    add_selection(pc)
    pc.add_argument("--payload-bytes", type=int, default=None, metavar="N",
                    help="plan for a payload of N bytes: pages needed, "
                         "source/repair split")
    pc.add_argument("--pages", type=int, default=1, metavar="N",
                    help="without --payload-bytes: max payload for an "
                         "N-page volume (default 1)")
    pc.add_argument("--json", action="store_true",
                    help="machine-readable output")

    pg = sub.add_parser(
        "generate",
        help="write a printable volume: one .ps per page + a ground-truth "
             "bitmap + an optional sidecar manifest")
    add_selection(pg)
    pg.add_argument("payload", help="payload file (stored verbatim; "
                                    "length and hash ride inside the "
                                    "printed stream)")
    pg.add_argument("-o", "--out", default=None, metavar="DIR",
                    help="output directory; refused if it exists (default "
                         "build/holo-<spec>-<payload-sha12>, "
                         "content-addressed)")

    pd = sub.add_parser(
        "decode",
        help="recover a payload from scans of printed sheets (blind: the "
             "sheets carry their own addresses; provisional historical "
             "placement constants are used until physical qualification)",
        description=(
            "Recover a payload from scans of printed sheets. The Track-3 "
            "receiver currently uses provisional historical placement "
            "constants from E021-E023c; every run warns because production "
            "qualification remains outstanding."
        ))
    pd.add_argument("scans", nargs="+",
                    help="original scanner acquisition(s) of printed pages; "
                         "do not supply externally resized or derived views")
    pd.add_argument("--scan-dpi", type=float, action="append", required=True,
                    metavar="DPI",
                    help="TRUE scanner dpi; repeat once per scan (never "
                         "guessed from metadata)")
    pd.add_argument("--format", dest="format_ref", default=None,
                    metavar="ID",
                    help="format identity: a v2 format id (e.g. "
                         "c2-cmy8-r0700@53x37) or an L:-prefixed fossil "
                         "reference (e.g. L:c2-cmy8-r0700-p120-x1"
                         "@3392x2368); replaces --coding/--printer")
    pd.add_argument("--coding", default=None, metavar="ID",
                    help="exact coding selection (default: discover only "
                         "the qualified default row set; provisional "
                         "catalog rows require this option)")
    pd.add_argument("--printer", default=None, metavar="ID",
                    help="optional printer/geometry hint; discovery remains "
                         "within the qualified default row set (with "
                         "--coding, the locked default geometry is used "
                         "when omitted)")
    pd.add_argument("--source-sha256", action="append", default=None,
                    metavar="HEX",
                    help="optional manifest SHA-256; if used, repeat once "
                         "per scan")
    pd.add_argument("--state", required=True, metavar="FILE",
                    help="schema-versioned receive state (atomic/resumable)")
    pd.add_argument("-o", "--out", required=True, metavar="FILE",
                    help="recovered payload path; refused if it exists")
    pd.add_argument("--page", type=int, action="append", default=None,
                    metavar="N",
                    help="optional legal page hypothesis; repeat to narrow "
                         "the cold Lane-C domain (default: complete "
                         "addressable page set)")
    pd.add_argument("--no-close", dest="no_close", action="store_true",
                    help="never enter the fountain-close layer: no "
                         "closing record is read on replay, none is "
                         "attempted or written, and a VERIFIED state is "
                         "DETACHED back to open so more captures can "
                         "accumulate; close later with a plain or "
                         "--complete run. Implies --complete's deferral "
                         "(giving both is fine)")
    pd.add_argument("--complete", action="store_true",
                    help="defer fountain close (checks and solves) until "
                         "this invocation's flag-bounded work is exhausted, "
                         "then close once; does not extend the plan — "
                         "combine with --mopup/--refine to run those "
                         "families, otherwise the run may legally end open "
                         "with parked lane families and remains resumable")
    pd.add_argument("--mopup", action="store_true",
                    help="run the parked mop-up levels after the ordinary "
                         "ladder (default: stop before the first mop-up "
                         "level; scheduling-only, resumable either way)")
    pd.add_argument("--refine", action="store_true",
                    help="run everything: ordinary ladder, any pending "
                         "mop-up levels (plan-prefix law), the refinement "
                         "levels, and — on a color coding — the "
                         "supplemental U(off/a3/a4b/field) tail that "
                         "follows them (scheduling-only, resumable)")
    pd.add_argument("--workers", type=_worker_count, default=None,
                    metavar="N",
                    help="worker threads for the pooled receiver kernels "
                         "(cold search, survey tensor, payload sampling, "
                         "BP batches); execution-only — results are "
                         "bit-identical for any value; default 1 = "
                         "sequential (HOLO_RECEIVE_WORKERS honored)")
    pd.add_argument("--profile-timing", action="store_true",
                    help="attach the doctrine profiling observer to this "
                         "single decode and print per-stage processor "
                         "seconds to stderr (conflicts with --diag)")
    pd.add_argument("--diag", action="store_true",
                    help="write observer-only operational diagnostics")
    pd.add_argument("--diag-dir", default=None, metavar="DIR",
                    help="diagnostic directory (default <state>.diag)")
    pd.add_argument("--diag-port", type=_tcp_port, default=None, metavar="PORT",
                    help="serve the live view on this localhost port; "
                         "0 requests an ephemeral port")
    pd.add_argument("--diag-interval", type=_diag_interval, default=3.0,
                    metavar="SECONDS",
                    help="maximum transient pane refresh rate, at least "
                         "0.25; semantic milestones still render and the "
                         "status rows update unthrottled (default: 3)")
    pd.add_argument("--diag-panel-width", type=_diagnostic_panel_width,
                    default=600,
                    metavar="PIXELS",
                    help="rendered width of each A/B/C/D pane; the browser "
                         "scales the composed frame to the window, so this "
                         "is raster detail, not layout (default: 600 — the "
                         "narrowest width at which every registered row can "
                         "print pane C's 3-digit site counts)")

    sub.add_parser(
        "discover",
        help="emit and analyze printer/scanner characterization sheets")

    args = ap.parse_args(effective_argv)
    return {"registry": cmd_registry, "fit": cmd_fit,
            "capacity": cmd_capacity, "generate": cmd_generate,
            "decode": cmd_decode}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
