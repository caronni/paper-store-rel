"""A/B arm runner: committed-pose REPLAY (dev signal) and FULL decode.

    cd <checkout>
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.ab_runner replay \
            --capture xerox-c3-cmy7 --arm baseline --force-null
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.ab_runner full \
            --capture xerox-c3-cmy7 --arm candidate

REPLAY re-runs the payload side over the archived state's committed
geometry (see :mod:`replay`); it is DEVELOPMENT SIGNAL, and for any stage
that conditions on certified content it is a KILL TEST only (the archived
final frontier is available from lane 0, which a fresh decode never has).
FULL runs the complete ladder through ``run_receive`` with the archived
flags from ``provenance.json`` and is the ONLY source of qualification
numbers (COLOR-UPLIFT-PLAN §4).

``--force-null`` exports ``HOLO_COLOR_STACK_FORCE_NULL=1`` for the
process and records it in the run JSON.  That is the ONE environment
contract left: it can only REMOVE behaviour, and it has to reach code
paths that never see a configuration object.

Every SWEPT constant reaches the receiver as an explicit
``holo.receive.color_stack.StackConfig``, threaded from this entry point
through ``replay_lanes`` into the production payload processor
(PK-CLEAN's hatch consolidation, the ``arm_override`` pattern).  The
sweep flags are therefore REPLAY-ONLY: the full-decode path goes through
``run_receive``, which has no configuration seam, so ``full`` refuses
them loudly instead of accepting a flag it would silently ignore.

Every run JSON records the capture SHA (verified against provenance
before any work), the worktree HEAD, the LIVE
``COLOR_PAYLOAD_POLICY_ID``, mode, flags, per-lane and total timings.
Timing doctrine: never profile through pytest; CPU is
``time.process_time`` (the run's own thread) plus rusage, and the
production stage events' ``timing.processor_seconds`` are recorded in
full mode where the runtime emits them.

``--diag [--diag-port N]`` attaches the production diagnostics observer
and live viewer to EITHER mode, exactly as ``confetti.py decode --diag
--diag-port N`` does for a real decode:

    … ab_runner replay --capture xerox-c3-cmy7 --arm baseline \
        --force-null --close --diag --diag-port 8023   # localhost:8023
    … ab_runner full --capture xerox-c3-cmy7 --arm candidate \
        --diag --diag-port 8024                        # localhost:8024

The observer is strictly downstream (RECEIVE-DESIGN §10) — it cannot
change a decode outcome, only wall time.  A replay runs ONLY the payload
stage, so the survey/address panes stay sparse by construction; no event
is ever fabricated to fill them.  A FULL run drives the whole ladder, so
every pane is fed by the runtime's own event stream; the harness's own
stage-timing observer is chained ahead of the diagnostics instance and
the final report is written through ``ReceiveDiagnostics.finalize``.

``--workers N`` (replay) sets the process-wide pooled-kernel worker count
through ``holo.receive._parallel.set_worker_count`` — the same seam
``confetti.py decode --workers`` uses.  It is execution-only: pooled
kernels are bit-identical at any worker count
(``tests/holo/test_parallel_exactness.py``), so an A/B comparison stays
valid across worker counts.  Default 1 = sequential.  A full run inherits
the archived invocation's own default (the CLI records no argv, so the
baselines' worker counts are unknown — provenance.json says so).

``--lane ID`` (repeatable, replay) restricts the replayed barrier
sequence to the named lanes.  Because certificates accumulate in barrier
order, an ``--lane l00-…`` run reproduces the full run's FIRST barrier
exactly (it has no priors to condition on); restricting to a LATER lane
alone does not reproduce that lane from a full run, and any such run must
say so.  ``--record-attempts`` adds the payload stage's own attempt rows
so a comparison can read tile-level decode margin rather than only
certificate counts.

Archived states are opened READ-ONLY and nothing is ever written beside
them; all output goes to ``<work>/runs`` and ``<work>/full``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
import warnings
from pathlib import Path

from . import corpus, state_cache
from .corpus import CaptureRow
from .replay import replay_lanes

SCHEMA = "color-uplift-run-1"
FORCE_NULL_ENV = "HOLO_COLOR_STACK_FORCE_NULL"


def _apply_force_null(force_null: bool) -> None:
    """Bind the hatch to the FLAG, both directions — refuse, don't ignore.

    Exporting it when asked was always here; the inverse matters just as
    much.  An inherited ``HOLO_COLOR_STACK_FORCE_NULL`` from a previous
    shell command silently turns a LIVE arm into the null, and the run
    JSON would then record ``force_null: false`` beside a null decode —
    an unfalsifiable row.  Same style as this tier's sweep-flag refusal.
    """
    from holo.receive.color_stack import force_null_enabled

    if force_null:
        os.environ[FORCE_NULL_ENV] = "1"
        return
    # The RECEIVER's own predicate, so the harness cannot disagree with
    # the code it is measuring about what "set" means.
    if force_null_enabled():
        raise SystemExit(
            f"{FORCE_NULL_ENV} is set but --force-null was not requested "
            "— unset it or pass --force-null. A run cannot record "
            "force_null: false while the receiver reads the null hatch.")


def _stack_config(args) -> object | None:
    """The sweep flags as ONE explicit ``StackConfig``, or ``None``.

    PK-CLEAN: ``--window-phot`` / ``--head-satfloor`` / ``--ctx`` used to
    export three environment variables that the arms read from inside
    production modules.  They now build a configuration record that is
    passed down the call chain, so a run's arm configuration is an
    argument the harness can print, record and reproduce rather than
    ambient process state.  ``None`` = the frozen constants, which is
    what the policy id names.
    """
    from holo.receive.color_context import ContextConfig
    from holo.receive.color_locality import WindowPhotometryConfig
    from holo.receive.color_stack import StackConfig

    if not (args.window_phot or args.head_satfloor or args.ctx):
        return None
    fields: dict = {}
    if args.window_phot:
        fields["window_photometry"] = WindowPhotometryConfig(
            float(args.window_phot))
    if args.head_satfloor:
        fields["head_saturation_floor"] = float(args.head_satfloor)
    if args.ctx:
        variant, _, floors = str(args.ctx).partition(":")
        if not floors:
            fields["context"] = ContextConfig(variant=variant)
        else:
            parts = [int(item) for item in floors.split(",")]
            if len(parts) != 4:
                raise SystemExit(
                    "--ctx floors are SEARCH,PER_CLASS,VALIDATION,PER_CLASS")
            fields["context"] = ContextConfig(
                variant=variant, min_search=parts[0],
                min_search_per_class=parts[1], min_validation=parts[2],
                min_validation_per_class=parts[3])
    return StackConfig(**fields)


def _describe(config) -> dict | None:
    """The effective sweep record, for the run JSON."""
    if config is None:
        return None
    return {
        "window_photometry_prior_labels":
            config.window_photometry.prior_labels,
        "head_saturation_floor": config.head_saturation_floor,
        "context": config.context.policy_token,
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _git(*args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, check=True).stdout.strip()


def _worktree_identity() -> dict:
    return {
        "head": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(_git("status", "--porcelain")),
    }


def _tree_state() -> dict:
    """The §8.5 content fingerprint, from the ONE implementation of it.

    HEAD is not the code: this worktree is shared, and a run's arm is
    whatever ``src/holo`` held while it executed.  ``feature_library``
    already owns the content hash and the producer/arm identities, so a
    replay records the same fields rather than growing a second copy
    that could drift from it.  Recorded at entry AND exit — different
    snapshots mean the tree moved under the run and it is VOID.
    """
    from .feature_library import tree_state

    return tree_state()


def _environment(force_null: bool, workers: int | None = None,
                 stack_config: dict | None = None) -> dict:
    import numpy

    from holo.receive import _parallel

    return {
        "python": sys.version.split()[0],
        "numpy": numpy.__version__,
        "platform": platform.platform(),
        # The EFFECTIVE count the pooled kernels will read (override or
        # HOLO_RECEIVE_WORKERS fallback); ``workers_requested`` is the
        # harness flag that produced it, ``None`` = flag absent.
        "workers": int(_parallel.worker_count())
        if hasattr(_parallel, "worker_count") else "unknown",
        "workers_requested": None if workers is None else int(workers),
        "HOLO_RECEIVE_WORKERS": os.environ.get("HOLO_RECEIVE_WORKERS"),
        FORCE_NULL_ENV: os.environ.get(FORCE_NULL_ENV),
        "force_null_requested": force_null,
        # PK-CLEAN: the swept constants are no longer environment state.
        # ``run_replay`` records the EFFECTIVE record under
        # ``stack_config``; ``None`` there means the frozen constants.
        "stack_config": stack_config,
    }


def _certificate_rows(certificates, lane_by_certificate: dict) -> list[dict]:
    return [
        {
            "certificate_id": row.certificate_id,
            "page": int(row.page),
            "tile_yx": [int(row.tile_yx[0]), int(row.tile_yx[1])],
            "stream_id": row.stream_id,
            "lane_id": lane_by_certificate.get(row.certificate_id),
            "packed_user_bits_hex": row.packed_user_bits.hex(),
        }
        for row in certificates
    ]


def _attempt_rows(rows) -> list[dict]:
    """Serialize the payload stage's OWN attempt records, untouched.

    Tile-level decode margin lives here and nowhere else: ``n_iters``
    against the 60 (baseline) / 150 (retry150) BP caps, ``syndrome_ok``,
    ``crc_ok`` and the per-child ``(n_iters, syndrome_ok)`` pairs.  A
    certificate count cannot separate "the tile got harder" from "the
    tile was always marginal"; these rows can.
    """
    return [
        {
            "attempt_id": row.attempt_id,
            "lane_id": row.lane_id,
            "page": int(row.page),
            "tile_yx": [int(row.tile_yx[0]), int(row.tile_yx[1])],
            "stream_id": row.stream_id,
            "stage": row.stage.value,
            "state": row.state.value,
            "n_informative": int(row.n_informative),
            "n_iters": int(row.n_iters),
            "syndrome_ok": row.syndrome_ok,
            "crc_ok": row.crc_ok,
            "certificate_id": row.certificate_id,
            "child_outcomes": [
                [int(iters), bool(ok)] for iters, ok in row.child_outcomes],
        }
        for row in rows
    ]


def _by_stream(certificates) -> dict:
    counts: dict[str, int] = {}
    for row in certificates:
        counts[row.stream_id] = counts.get(row.stream_id, 0) + 1
    return dict(sorted(counts.items()))


def _archived_facts(cache: state_cache.CaptureCache) -> dict:
    return {
        "certificates": cache.n_state_certificates,
        "close_status": cache.close_status,
        "certificates_by_lane": {
            level.lane_id: len(level.certificate_ids)
            for level in cache.levels},
        "certificate_ids": sorted(cache.certificates_by_id),
        "by_stream": _by_stream(tuple(cache.certificates_by_id.values())),
    }


def _open_native(row: CaptureRow, cache: state_cache.CaptureCache):
    """Open the capture and REFUSE unless its SHA is the frozen one."""
    from holo.receive.scan import open_capture

    recorded = corpus.provenance_row(row.key)["artifacts"]["tiff"]["sha256"]
    native = open_capture(str(row.tiff_path()), row.scan_dpi)
    if native.source_sha256 != recorded:
        raise SystemExit(
            f"{row.key}: capture sha {native.source_sha256[:16]}… != "
            f"provenance {recorded[:16]}… — REFUSING to run")
    if native.source_sha256 != cache.capture_sha256:
        raise SystemExit(
            f"{row.key}: capture sha differs from the archived state's "
            f"capture id — REFUSING to run")
    return native


def _close_report(spec, certificates) -> dict:
    """Solve the fountain over the accumulated frontier (report-only)."""
    from holo.receive.fountain_close import close_volume
    from holo.receive.records import certificate_for_close

    if not certificates:
        return {"status": "open", "reason": "no certificates"}
    inputs = tuple(certificate_for_close(row, spec) for row in certificates)
    outcome = close_volume(inputs, spec)
    payload = getattr(outcome, "payload", None)
    return {
        "status": outcome.status,
        "bytes": None if payload is None else len(payload),
        "sha256": (None if payload is None
                   else hashlib.sha256(payload).hexdigest()),
    }


def _live_pipeline(row: CaptureRow, spec):
    """The live receiver composition (for identity/qualification only).

    A replay executes only the payload stage, but the diagnostics header
    must name a real composition; this is the same pipeline a full decode
    of this capture would build under the CURRENT worktree.
    """
    from holo.receive.production import production_pipeline
    from holo.receive.runtime import ReceiveRequest
    from holo.receive.types import CaptureInput

    request = ReceiveRequest(
        spec, (CaptureInput(str(row.tiff_path()), row.scan_dpi),),
        page_hypotheses=None)
    return production_pipeline(request)


def _build_diagnostics(row: CaptureRow, spec, pages, pipeline, *, arm: str,
                       port: int | None, interval: float,
                       panel_width: int, directory: Path):
    """Build the production diagnostics observer + live viewer.

    Strictly downstream (RECEIVE-DESIGN §10): the observer sees events, it
    never feeds the decode.  Both modes use this identical wiring; only
    the event SOURCE differs (a replay hand-feeds an ``EventSink``, a full
    run is driven by the runtime's own sink through ``run_receive``).
    """
    from holo.receive.diag import ReceiveDiagnostics

    return ReceiveDiagnostics(
        directory, spec,
        receiver_policy_id=pipeline.policy_id,
        page_domain=pages,
        qualification_status=pipeline.qualification_status,
        qualification_notes=pipeline.qualification_notes,
        interval_s=interval,
        panel_width=panel_width,
        port=port,
        on_server=lambda url: print(
            f"diagnostics live [{row.key}/{arm}]: {url}",
            file=sys.stderr, flush=True),
    )


def _diag_report(directory: Path, port: int | None, interval: float,
                 panel_width: int, policy_id: str, note: str) -> dict:
    return {
        "enabled": True,
        "directory": str(directory),
        "port": port,
        "interval_s": interval,
        "panel_width": int(panel_width),
        "receiver_policy_id": policy_id,
        "note": note,
    }


def _attach_diagnostics(row: CaptureRow, spec, pages, *, arm: str,
                        port: int | None, interval: float,
                        panel_width: int, directory: Path):
    """Replay flavour: diagnostics plus the hand-driven ``EventSink``."""
    from holo.receive.observer import EventSink

    pipeline = _live_pipeline(row, spec)
    diagnostics = _build_diagnostics(
        row, spec, pages, pipeline, arm=arm, port=port, interval=interval,
        panel_width=panel_width, directory=directory)
    sink = EventSink(
        diagnostics,
        pipeline.qualification_status.value,
        pipeline.qualification_notes)
    sink.bind_session(spec.spec_id, pipeline.policy_id, tuple(pages))
    return diagnostics, sink, pipeline


def run_replay(row: CaptureRow, *, arm: str, force_null: bool,
               lanes: tuple[str, ...] | None, close: bool,
               rebuild_cache: bool, diag: bool = False,
               diag_port: int | None = None, diag_dir: Path | None = None,
               diag_interval: float = 3.0,
               diag_panel_width: int = 600,
               workers: int | None = None,
               record_attempts: bool = False,
               seed_archived_certificates: bool = False,
               stack_config=None) -> dict:
    from holo.receive import _parallel
    from holo.receive.color_payload import COLOR_PAYLOAD_POLICY_ID
    from holo.receive.observer import ProvisionalReceiverWarning

    if workers is not None:
        # Execution-only knob, identical seam to `confetti.py decode
        # --workers` (cli.py:483): the pooled receiver kernels — payload
        # sampling among them — are bit-identical at every worker count,
        # so this never enters policy, schema, or the A/B verdict.
        _parallel.set_worker_count(workers)
    if not row.is_color:
        raise SystemExit(
            f"{row.key}: replay is color-only (kind={row.kind}); the K "
            "payload path is out of PK0 replay scope — use `full` mode")
    cache = state_cache.load(row, rebuild=rebuild_cache)
    state_cache.verify_against_provenance(row, cache)
    recorded = corpus.provenance_row(row.key)
    spec = corpus.resolve_spec(row, cache.format_row_id)
    defer = recorded["baseline"]["flags"]["complete"]
    defer_close = True if defer == "unknown" else bool(defer)
    native = _open_native(row, cache)

    lane_filter = (None if lanes is None
                   else (lambda lane: lane.lane_id in lanes))
    pages = (cache.page_hypotheses if cache.page_hypotheses is not None
             else tuple(range(spec.max_pages)))
    diagnostics = None
    sink = None
    diag_report: dict = {"enabled": False}
    if diag:
        directory = diag_dir or (
            corpus.work_dir("runs")
            / f"{row.key}-replay-{arm}.diag")
        diagnostics, sink, pipeline = _attach_diagnostics(
            row, spec, pages, arm=arm, port=diag_port,
            interval=diag_interval, panel_width=diag_panel_width,
            directory=Path(directory))
        diag_report = _diag_report(
            Path(directory), diag_port, diag_interval, diag_panel_width,
            pipeline.policy_id,
            "observer/viewer are strictly downstream (RECEIVE-DESIGN "
            "§10): they cannot change a decode outcome, only wall "
            "time. Only the payload stage runs in a replay, so the "
            "survey/address panes stay sparse by construction.")
    tree_before = _tree_state()
    started = time.perf_counter()
    cpu_started = time.process_time()
    rusage_started = resource.getrusage(resource.RUSAGE_SELF)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ProvisionalReceiverWarning)
            outcomes, certificates = replay_lanes(
                cache, spec, native,
                defer_fountain_close=defer_close,
                lane_filter=lane_filter,
                sink=sink,
                stack_config=stack_config,
                record_attempts=record_attempts,
                seed_archived_certificates=seed_archived_certificates,
                progress=lambda text: print(
                    f"    {text}", file=sys.stderr, flush=True))
    finally:
        if diagnostics is not None:
            diag_report["viewer_failures"] = list(diagnostics.failures)
            diagnostics.close()
    wall = time.perf_counter() - started
    cpu = time.process_time() - cpu_started
    rusage_end = resource.getrusage(resource.RUSAGE_SELF)

    lane_by_certificate = {
        certificate.certificate_id: lane.lane_id
        for lane in outcomes for certificate in lane.certificates}
    report = {
        "schema": SCHEMA,
        "mode": "replay",
        "arm": arm,
        "capture": row.key,
        "kind": row.kind,
        "engine": row.engine,
        "role": row.role,
        "force_null": force_null,
        "replay_is_development_signal": True,
        "worktree": _worktree_identity(),
        "tree_state_before": tree_before,
        "tree_state_after": _tree_state(),
        "color_payload_policy_id": COLOR_PAYLOAD_POLICY_ID,
        "format_row_id": cache.format_row_id,
        "codec_id": spec.codec_id,
        "stream_ids": list(spec.stream_ids),
        "capture_sha256": cache.capture_sha256,
        "state_sha256": cache.state_sha256,
        "provenance_verified": True,
        "defer_fountain_close": defer_close,
        "lane_filter": None if lanes is None else list(lanes),
        "diagnostics": diag_report,
        "environment": _environment(
            force_null, workers, _describe(stack_config)),
        "totals": {
            "certificates": len(certificates),
            "by_stream": _by_stream(certificates),
            "wall_s": round(wall, 1),
            "cpu_s": round(cpu, 1),
            "rusage_cpu_s": round(
                (rusage_end.ru_utime - rusage_started.ru_utime)
                + (rusage_end.ru_stime - rusage_started.ru_stime), 1),
            "peak_rss_mib": round(rusage_end.ru_maxrss / 2**20),
        },
        "archived": _archived_facts(cache),
        "lanes": [
            {
                "ordinal": lane.ordinal,
                "lane_id": lane.lane_id,
                "lane_kind": lane.lane_kind,
                "evidence_lane_id": lane.evidence_lane_id,
                "placements": lane.placements,
                "label_placements": lane.label_placements,
                "prior_certificates": lane.prior_certificates,
                "blocks": lane.blocks,
                "attempts": lane.attempts,
                "certificates": len(lane.certificates),
                "certificates_by_stream": _by_stream(lane.certificates),
                # PK4.3: a supplemental lane has NO archived level (the
                # archived decode never scheduled it), so its archived
                # count is null, not zero — an absent baseline and a
                # baseline of zero are different facts.
                "archived_certificates": (
                    len(cache.levels[lane.ordinal].certificate_ids)
                    if lane.ordinal < len(cache.levels) else None),
                "wall_s": round(lane.wall_s, 1),
                "cpu_s": round(lane.cpu_s, 1),
                # Included in cpu_s; arm-invariant (replay.py docstring).
                # Absent from pre-PK2 baseline run JSONs.
                "build_address_s": round(lane.build_address_s, 2),
                "details": lane.details,
                **({"attempt_rows": _attempt_rows(lane.attempt_rows)}
                   if record_attempts else {}),
            }
            for lane in outcomes
        ],
        "certificates": _certificate_rows(certificates, lane_by_certificate),
    }
    report["record_attempts"] = bool(record_attempts)
    report["seed_archived_certificates"] = bool(seed_archived_certificates)
    if seed_archived_certificates:
        report["kill_test"] = (
            "PRIORS SEEDED WITH THE ARCHIVED FINAL FRONTIER: maximal "
            "conditioning, structurally unreachable in deployment. A null "
            "result kills the packet; a positive one measures NOTHING and "
            "is not comparable to any other row.")
    if close:
        report["close"] = _close_report(spec, certificates)
    return report


def run_full(row: CaptureRow, *, arm: str, force_null: bool,
             out_dir: Path | None, page_override: tuple[int, ...] | None,
             smoke: bool, diag: bool = False, diag_port: int | None = None,
             diag_dir: Path | None = None, diag_interval: float = 3.0,
             diag_panel_width: int = 600) -> dict:
    """Fresh-state full ladder through ``run_receive`` (qualification).

    Flags come from ``provenance.json`` so a full run is comparable to the
    archived baseline by construction.  This function deliberately does
    NOT bound the work: a real full decode is hours, so PK0 only wires and
    smoke-tests it (``--smoke`` builds the request and stops before
    ``run_receive``).

    ``diag`` attaches the same ``ReceiveDiagnostics`` a replay attaches
    and the same one ``confetti.py decode --diag`` attaches; the harness's
    own stage-timing observer runs FIRST in the chained observer, so a
    diagnostics fault can never cost the run its timing record.
    """
    from holo.receive.color_payload import COLOR_PAYLOAD_POLICY_ID
    from holo.receive.observer import ProvisionalReceiverWarning
    from holo.receive.production import production_pipeline
    from holo.receive.runtime import ReceiveRequest, run_receive
    from holo.receive.types import CaptureInput

    recorded = corpus.provenance_row(row.key)
    flags = recorded["baseline"]["flags"]
    spec = corpus.resolve_spec(row, recorded["format_row_id"])
    pages = page_override
    if pages is None and isinstance(flags["page"], list):
        pages = tuple(int(value) for value in flags["page"])
    complete = flags["complete"]
    directory = out_dir or corpus.work_dir("full", f"{row.key}-{arm}")
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / "receive.state"
    if state_path.exists():
        raise SystemExit(
            f"{state_path} exists; full runs never resume a foreign state")
    # BIND the capture, don't just report it: the header copies the
    # provenance digest below, but only ``expected_sha256`` makes the
    # runtime itself refuse a TIFF that is not the one provenance names
    # (runtime enforces it in-process, at ingest, before any decode work).
    capture_sha = str(recorded["artifacts"]["tiff"]["sha256"])
    request = ReceiveRequest(
        spec,
        (CaptureInput(str(row.tiff_path()), row.scan_dpi,
                      expected_sha256=capture_sha),),
        state_path=state_path,
        page_hypotheses=pages,
        defer_fountain_close=True if complete == "unknown" else bool(complete),
        run_mopup=True,
        run_refine=bool(flags["refine"]),
    )
    header = {
        "schema": SCHEMA,
        "mode": "full",
        "arm": arm,
        "capture": row.key,
        "force_null": force_null,
        "worktree": _worktree_identity(),
        "color_payload_policy_id": COLOR_PAYLOAD_POLICY_ID,
        "format_row_id": recorded["format_row_id"],
        "capture_sha256": capture_sha,
        "capture_sha256_enforced": True,
        "state_path": str(state_path),
        "environment": _environment(force_null),
        "diagnostics": {"enabled": False},
        "request": {
            "page_hypotheses": None if pages is None else list(pages),
            "defer_fountain_close": request.defer_fountain_close,
            "run_mopup": request.run_mopup,
            "run_refine": request.run_refine,
            "scan_dpi": row.scan_dpi,
        },
        "archived_flags": flags,
    }
    if smoke:
        header["smoke"] = True
        header["note"] = (
            "request built and validated; run_receive deliberately not "
            "started (a full decode is hours — PK0 wires it only)")
        return header

    stage_seconds: dict[str, float] = {}
    counters = {"barriers": 0}

    def observe(event) -> None:
        if event.name == "barrier.committed":
            counters["barriers"] += 1
            return
        if event.name in ("stage.complete", "stage.refused"):
            details = {row_.name: row_.value for row_ in event.details}
            seconds = details.get("timing.processor_seconds")
            lane = str(details.get("lane.id", "?"))
            if isinstance(seconds, (int, float)):
                # A u-lane is NEW scheduled work, not part of the ordinary
                # ladder: folding it into "base" would charge the arms'
                # supplemental tail to the standard lanes and make the
                # cross-epoch CPU column meaningless.
                kind = ("uplift" if lane.startswith("u")
                        else "mopup" if lane.startswith("m")
                        else "refine" if lane.startswith("r") else "base")
                key = f"{kind}.{event.stage.value}"
                stage_seconds[key] = stage_seconds.get(key, 0.0) + float(
                    seconds)

    pipeline = production_pipeline(request)
    diagnostics = None
    observer = observe
    if diag:
        diag_directory = Path(diag_dir) if diag_dir else (
            corpus.work_dir("runs") / f"{row.key}-full-{arm}.diag")
        requested_pages = (
            tuple(range(spec.max_pages)) if pages is None else pages)
        diagnostics = _build_diagnostics(
            row, spec, requested_pages, pipeline, arm=arm, port=diag_port,
            interval=diag_interval, panel_width=diag_panel_width,
            directory=diag_directory)
        header["diagnostics"] = _diag_report(
            diag_directory, diag_port, diag_interval, diag_panel_width,
            pipeline.policy_id,
            "observer/viewer are strictly downstream (RECEIVE-DESIGN "
            "§10): they cannot change a decode outcome, only wall time. "
            "A full run drives every stage, so every pane is fed by the "
            "runtime's own event stream.")

        def observer(event) -> None:  # noqa: F811 — chained, timing first
            observe(event)
            diagnostics(event)

    started = time.perf_counter()
    cpu_started = time.process_time()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ProvisionalReceiverWarning)
            result = run_receive(
                request, pipeline=pipeline, observer=observer)
    except BaseException:
        if diagnostics is not None:
            diagnostics.close()
        raise
    if diagnostics is not None:
        header["diagnostics"]["reports"] = [
            str(path) for path in diagnostics.finalize(result.state)]
        header["diagnostics"]["viewer_failures"] = list(diagnostics.failures)
        diagnostics.close()
    header["totals"] = {
        "wall_s": round(time.perf_counter() - started, 1),
        "cpu_s": round(time.process_time() - cpu_started, 1),
        "peak_rss_mib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20),
        "certificates": len(result.state.certificates),
        "by_stream": _by_stream(result.state.certificates),
        "barriers": counters["barriers"],
        "close_status": result.state.close.status.value,
        "verified": bool(result.verified),
    }
    header["stage_seconds"] = {
        key: round(value, 1) for key, value in sorted(stage_seconds.items())}
    header["certificates"] = _certificate_rows(
        result.state.certificates, _lane_by_certificate(result.state))
    return header


def _lane_by_certificate(state) -> dict[str, str]:
    """Which lane minted each certificate, read off the produced state.

    A replay gets this from the lane outcomes it drove; a full run does
    not see them, so it reads the same fact from the durable record —
    each committed level's payload names its certificate ids, and the
    capture's plan names the level's lane at the same ordinal.  Without
    it every certificate row in a full run's JSON carries ``lane_id:
    null`` and the per-lane split has to be re-derived by hand (this is
    the mapping ``pkfinal_lanes.py`` had to do from outside).
    """
    lanes: dict[str, str] = {}
    for record in state.captures:
        for ordinal, level in enumerate(record.levels):
            if level.payload is None or ordinal >= len(record.plan):
                continue
            lane_id = record.plan[ordinal].lane_id
            for identity in level.payload.certificate_ids:
                lanes[identity] = lane_id
    return lanes


def _run_path(row: CaptureRow, mode: str, arm: str, force_null: bool) -> Path:
    suffix = "-forcenull" if force_null else ""
    return corpus.work_dir("runs") / f"{row.key}-{mode}-{arm}{suffix}.json"


def _write(report: dict, path: Path) -> None:
    path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    totals = report.get("totals", {})
    print(json.dumps({
        "capture": report["capture"],
        "mode": report["mode"],
        "arm": report["arm"],
        "force_null": report["force_null"],
        "certificates": totals.get("certificates"),
        "by_stream": totals.get("by_stream"),
        "archived": report.get("archived", {}).get("certificates"),
        "wall_s": totals.get("wall_s"),
        "cpu_s": totals.get("cpu_s"),
        "out": str(path),
    }))


def cmd_replay(args: argparse.Namespace) -> int:
    _apply_force_null(bool(args.force_null))
    stack_config = _stack_config(args)
    row = corpus.capture(args.capture)
    if not args.diag and (args.diag_port is not None or args.diag_dir):
        raise SystemExit("--diag-port/--diag-dir require --diag")
    report = run_replay(
        row, arm=args.arm, force_null=bool(args.force_null),
        lanes=tuple(args.lane) if args.lane else None,
        close=bool(args.close), rebuild_cache=bool(args.rebuild_cache),
        diag=bool(args.diag), diag_port=args.diag_port,
        diag_dir=Path(args.diag_dir) if args.diag_dir else None,
        diag_interval=float(args.diag_interval),
        diag_panel_width=int(args.diag_panel_width),
        workers=args.workers,
        record_attempts=bool(args.record_attempts),
        seed_archived_certificates=bool(args.seed_archived_certificates),
        stack_config=stack_config)
    if any(report["tree_state_before"].get(key)
           != report["tree_state_after"].get(key)
           for key in ("receiver_tree_sha256", "producer_identity",
                       "arm_identity")):
        print("!! THE TREE MOVED DURING THIS RUN — the result is VOID",
              file=sys.stderr, flush=True)
    _write(report, Path(args.out) if args.out
           else _run_path(row, "replay", args.arm, bool(args.force_null)))
    return 0


def cmd_full(args: argparse.Namespace) -> int:
    _apply_force_null(bool(args.force_null))
    if args.window_phot or args.head_satfloor or args.ctx:
        # PK-CLEAN: a full decode runs the production ``run_receive``
        # ladder, which constructs its own payload processor and has no
        # configuration seam.  Accepting a sweep flag here would silently
        # run the FROZEN constants under a swept label, so it refuses.
        raise SystemExit(
            "sweep flags (--window-phot/--head-satfloor/--ctx) are "
            "REPLAY/LIBRARY-tier only: the full ladder takes the frozen "
            "constants the policy id names. Re-run in `replay` mode, or "
            "drop the flag.")
    row = corpus.capture(args.capture)
    if not args.diag and (args.diag_port is not None or args.diag_dir):
        raise SystemExit("--diag-port/--diag-dir require --diag")
    report = run_full(
        row, arm=args.arm, force_null=bool(args.force_null),
        out_dir=Path(args.state_dir) if args.state_dir else None,
        page_override=tuple(args.page) if args.page else None,
        smoke=bool(args.smoke),
        diag=bool(args.diag), diag_port=args.diag_port,
        diag_dir=Path(args.diag_dir) if args.diag_dir else None,
        diag_interval=float(args.diag_interval),
        diag_panel_width=int(args.diag_panel_width))
    _write(report, Path(args.out) if args.out
           else _run_path(row, "full", args.arm, bool(args.force_null)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.ab_runner", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--capture", required=True,
                        help="capture key (see corpus.CAPTURES)")
    common.add_argument("--arm", default="baseline",
                        help="arm label recorded in the run JSON")
    common.add_argument("--force-null", action="store_true",
                        help=f"export {FORCE_NULL_ENV}=1 for this process "
                             "(every uplift gate off => today's receiver)")
    common.add_argument("--out", default=None,
                        help="run JSON path (default <work>/runs/…)")
    common.add_argument("--window-phot", default=None, metavar="PRIOR",
                        help="A3 sweep (REPLAY ONLY): the arm's shrinkage "
                             "prior, in effective labels, off its frozen "
                             "20. Threaded as StackConfig."
                             "window_photometry and published per region "
                             "as color.window_maps.prior_labels, so a "
                             "swept run never relies on the policy id "
                             "(which names the FROZEN value) to say what "
                             "it ran. PK4.1's raw dispersion floor and "
                             "PK4.2's normalized one are RETIRED "
                             "(MEASUREMENTS §12) and no longer accepted.")
    common.add_argument("--ctx", default=None, metavar="VARIANT",
                        help="A5 neighbourhood corrector (REPLAY ONLY): "
                             "matrix|off[:SEARCH,PER_CLASS,VALIDATION,"
                             "PER_CLASS]. Absent = the frozen variant the "
                             "policy id names. The per-plane K port "
                             "(`planes`) is RETIRED — 0 of 17 lanes "
                             "adopted on the uplift target, §11.4/§12.")
    common.add_argument("--head-satfloor", default=None, metavar="FRACTION",
                        help="A4 sweep (REPLAY ONLY): the cmy7 head's "
                             "deployment saturation floor, off its frozen "
                             "0.30. The effective value is published per "
                             "region as color.cmy7_head.saturation_floor.")

    # One diagnostics flag family, one wiring, both modes.
    diag = argparse.ArgumentParser(add_help=False)
    diag.add_argument("--diag", action="store_true",
                      help="attach the production diagnostics observer "
                           "(events.jsonl + composed frames); strictly "
                           "downstream of the decode")
    diag.add_argument("--diag-port", type=int, default=None,
                      help="serve the live viewer on this localhost port")
    diag.add_argument("--diag-dir", default=None,
                      help="diagnostic directory (default "
                           "<work>/runs/<capture>-<mode>-<arm>.diag)")
    diag.add_argument("--diag-interval", type=float, default=3.0)
    diag.add_argument("--diag-panel-width", type=int, default=600)

    item = sub.add_parser("replay", parents=[common, diag])
    item.add_argument("--lane", action="append", default=[],
                      help="replay only this lane id (repeatable)")
    item.add_argument("--close", action="store_true",
                      help="solve the fountain over the replayed frontier")
    item.add_argument("--record-attempts", action="store_true",
                      help="write each lane's own TileAttemptRecord rows "
                           "into the run JSON (tile-level decode margin: "
                           "n_iters vs the 60/150 BP caps, syndrome_ok, "
                           "crc_ok, per-child outcomes); off by default")
    item.add_argument("--seed-archived-certificates", action="store_true",
                      help="THE KILL TEST (PK10): hand every lane the "
                           "archived FINAL certificate frontier as priors, "
                           "so a stage that conditions on certified "
                           "content sees maximal knowledge from lane 0. "
                           "Structurally optimistic and unreachable in "
                           "deployment: a NULL result kills a packet, a "
                           "positive one measures nothing. Seeds are "
                           "priors only — they are never minted, never "
                           "counted, and never joined to the run's own "
                           "certificate set.")
    item.add_argument("--rebuild-cache", action="store_true")
    item.add_argument("--workers", type=_positive_int, default=None,
                      metavar="N",
                      help="worker threads for the pooled receiver kernels "
                           "(holo.receive._parallel, the `confetti.py "
                           "decode --workers` seam); execution-only — "
                           "results are bit-identical for any value; "
                           "default 1 = sequential")
    item.set_defaults(handler=cmd_replay)

    item = sub.add_parser("full", parents=[common, diag])
    item.add_argument("--state-dir", default=None)
    item.add_argument("--page", action="append", type=int, default=[])
    item.add_argument("--smoke", action="store_true",
                      help="build and validate the request, then stop")
    item.set_defaults(handler=cmd_full)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
