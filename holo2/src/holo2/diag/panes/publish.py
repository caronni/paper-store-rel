"""Terminal artifacts on disk: the ``<state-dir>.diag/`` sibling.

Carried from the v1 receiver's ``diag/transport.CurrentFiles`` +
``ReceiveDiagnostics.finalize``: at run termination the observer replaces
a fixed, small set of current files — one composed frame per page, the
final status payload, and a compact report — so a headless run stays
readable after the endpoint is gone, and a browser that polled the live
server keeps the terminal picture it already fetched.

**Disjoint from authoritative state, by construction.** The directory is
a SIBLING of the state directory (``<state-dir>.diag``), never a child.
:class:`~holo2.core.store.Store` opens strictly — exact top-level envelope
fields, known record types, every referenced blob present — and it must
never be handed a directory that also holds observer scribbles. Making
the diag output a sibling means the store's strict open cannot see it at
all, rather than being taught to ignore it.

Everything here is disposable and overwritten in place on the next run:
these are *current* files, not an accumulating log. Nothing here is
durable in the DESIGN §5.6 sense — no fsync, no atomic-directory dance
beyond one temp-and-replace so a reader never sees a torn frame.
"""
from __future__ import annotations

from pathlib import Path

from ...core import canonical_json_bytes
from ...engine import RunOutcome

DIAG_DIR_SUFFIX = ".diag"
STATUS_NAME = "status.json"
REPORT_NAME = "report.json"
REPORT_SCHEMA = "holo2-panes-1"


def diag_directory(state_dir: Path) -> Path:
    """``<state-dir>.diag`` — a sibling, never a child (see module note)."""
    state_dir = Path(state_dir)
    return state_dir.parent / (state_dir.name + DIAG_DIR_SUFFIX)


def frame_name(page: int) -> str:
    return f"frame_p{int(page):03d}.png"


def replace_file(path: Path, data: bytes) -> None:
    """Overwrite in place through a temp file, so no reader sees a tear."""
    temp = path.with_name(path.name + ".partial")
    temp.write_bytes(data)
    temp.replace(path)


def build_report(status: dict, outcome: RunOutcome | None,
                 failures: tuple[str, ...] = ()) -> dict:
    """The compact machine-readable summary beside the frames.

    Scalars only, and every field is taken from the observer surface that
    already exists — the commit stream, the orchestrator snapshot and the
    pane catalog. Nothing here recomputes a receiver fact.
    """
    session = status.get("session") or {}
    counters = session.get("counters") or {}
    report = {
        "diag_schema": REPORT_SCHEMA,
        "provisional": True,
        "format": status.get("panes") or {},
        "rows": list(status.get("rows") or ()),
        "outcome": _outcome_summary(outcome, session, counters),
        "commit_stream": _commit_summary(status.get("commit_stream") or {}),
        "tiles": session.get("tiles") or {},
        "close": session.get("close") or {},
        "done_coverage": session.get("done_coverage") or {},
        "workers": _worker_summary(session),
        "failures": list(failures),
    }
    return report


def _commit_summary(stream: dict) -> dict:
    """The commit stream WITHOUT its per-worker tail.

    ``status.json`` carries the live payload verbatim, tail included; the
    report is the compact one, and a real page has thousands of workers —
    a per-worker wake map would be most of the file and would say nothing
    the two summary numbers below do not.
    """
    by_worker = stream.get("wakes_by_worker") or {}
    return {
        "commits": stream.get("commits"),
        "changed_keys": stream.get("changed_keys"),
        "wakes": stream.get("wakes"),
        "wakes_per_commit": stream.get("wakes_per_commit"),
        "changed_by_kind": stream.get("changed_by_kind") or {},
        "distinct_workers_woken": len(by_worker),
        "max_wakes_per_worker": max(by_worker.values()) if by_worker else 0,
    }


def _outcome_summary(outcome: RunOutcome | None, session: dict,
                     counters: dict) -> dict:
    """What the run did. ``None`` = the run never returned one (L4)."""
    if outcome is None:
        return {
            "status": "unavailable",
            "note": "the run did not return an outcome to the observer",
            "certified": (session.get("close") or {}).get("certified"),
            "commits": counters.get("commits"),
            "fires": counters.get("fires"),
        }
    return {
        "status": str(outcome.status),
        "verified": outcome.verified,
        "certified": outcome.certified,
        "commits": outcome.commits,
        "fires": outcome.fires,
        "exhausted": outcome.exhausted,
        "resumed_terminal": outcome.resumed_terminal,
        "reason": outcome.reason,
        "payload_bytes": (None if outcome.payload is None
                          else len(outcome.payload)),
    }


def _worker_summary(session: dict) -> dict:
    workers = session.get("workers") or {}
    ready = session.get("ready") or {}
    fires = workers.get("fires_by_worker") or {}
    return {
        "ready_depth": ready.get("depth"),
        # "family" is the glossary word, and B4 renamed the engine
        # snapshot's own key to it too: the descriptor's vocabulary is
        # what the queue buckets by, so both sides now say the same word.
        "ready_by_family": ready.get("by_family") or {},
        "total": workers.get("total"),
        "sleeping": workers.get("sleeping"),
        "retired": workers.get("retired"),
        # DG-1: the orchestrator's two REAL decline numbers. A permanent
        # decline and a re-offerable one are different facts, and the key
        # that used to stand here (``declined_done_gate``) has had no
        # publisher since R1, so the report carried a null and omitted both.
        "declined": workers.get("declined"),
        "declined_pending": workers.get("declined_pending"),
        "distinct_workers_fired": len(fires),
        "max_fires_per_worker": max(fires.values()) if fires else 0,
        "sleeping_by_subscription_key": (
            session.get("sleeping_by_subscription_key") or {}),
    }


def write_artifacts(directory: Path, *, status: dict,
                    frames: dict[int, bytes], report: dict,
                    ) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """Replace the current files; return ``(written, failures)``.

    Each artifact is attempted independently: one unwritable frame does
    not cost the operator the status or the report. Nothing raises.
    """
    written: list[Path] = []
    failures: list[str] = []
    directory = Path(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return (), (f"{directory.name}: {type(exc).__name__}: {exc}",)
    items: list[tuple[str, bytes]] = [
        (frame_name(page), frames[page]) for page in sorted(frames)]
    for name, payload in (("status", status), ("report", report)):
        try:
            items.append((STATUS_NAME if name == "status" else REPORT_NAME,
                          canonical_json_bytes(payload)))
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    for name, data in items:
        path = directory / name
        try:
            replace_file(path, data)
            written.append(path)
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    return tuple(written), tuple(failures)


__all__ = [
    "DIAG_DIR_SUFFIX", "REPORT_NAME", "REPORT_SCHEMA", "STATUS_NAME",
    "build_report", "diag_directory", "frame_name", "replace_file",
    "write_artifacts",
]
