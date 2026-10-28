#!/usr/bin/env python
"""F2a's yield BY RESUME — the re-read, measured on an archived sheet.

    env/bin/python holo2/measure/resample_resume.py \\
        --state scratch/holo2-catchup/real/f2/e029 \\
        --scan scratch/e028/hp-canon-c2-ink-counting.tiff \\
        --dpi 4800 --format L:c2-r0700@3392x2368 --label e029 \\
        --workers 8 --expect-sha e5021f8d… \\
        --out scratch/holo2-catchup/real/f2/resample-e029.md

NOT A TEST and not collectable as one — a by-path driver like its
siblings (``holo2/measure/README.md``). It is ``rf1_resume.py``'s idiom
and most of its machinery, pointed at the OTHER half of the mechanism:
W2 measured what a pose revision costs when nothing reads it, and this
measures what happens once something does. Everything it does not
re-state — the two-phase ``--no-close`` resume and why it is forced, the
identity check before eight workers are put behind a 4800-dpi capture,
"read-only is about content, not mtime" — is that module's, imported
rather than copied.

WHAT IT ADDS, and why each number is here.

* **the certified TILE SETS, before and after.** A count cannot see a
  swap, and F2a's acceptance is "zero regressions": the live-generation
  reduction stops a superseded reading from owning cells, so a revision
  that reads WORSE than its parent costs exactly the tiles the parent's
  reading would have won. Sets are what say whether that happened, and
  the lost/gained lists are printed in full.
* **the re-read census** — how many windows were offered a re-read, what
  each fire answered, and how many pieces it emitted. Taken by wrapping
  ``resample.resample_window`` where ``place_job`` reads it: the wrapper
  calls the real function, changes no argument and no result, and is
  removed in a ``finally``. It observes a decision; it makes none.
* **the two generations, counted in the store.** Poses per window
  extent, and how many poses own evidence — before and after. That is
  the mechanism's own signature: through F1 a revised extent held two
  poses and ONE of them owned pieces (A2: 269/272 windows, zero evidence
  on the live pose); after F2a it holds two poses and TWO generations of
  pieces, of which only the live one decodes.
* **a named tile COLUMN**, optional (``--column``). The Xerox residue is
  the ``tx = 0`` left edge — 19 tiles v1 certifies and holo2 does not —
  and it is the population F2a's mechanism is aimed at, so its
  before/after is reported separately from the sheet total. It is a
  POPULATION UNDER STUDY and never a bar: LEDGER-VERIFY C1 measured the
  oracle per-cell owner assignment certifying 0 of those 19, so no
  ownership rule reaches them and this is the only arm that could.

WHAT IT DOES NOT DO. It does not re-run v1 (RULINGS I5: v1's harvests
are READ, never re-run on paper), it does not touch the original state
directories (run it on a copy), and it makes no claim about a population
from one sheet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

_ROOT = Path(__file__).resolve().parents[2]
for _path in (_ROOT / "holo2" / "src", _ROOT / "src", _ROOT / "holo2" / "measure"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from holo2 import cli                                        # noqa: E402
from holo2.cli import DecodeRequest, real_providers, real_source  # noqa: E402
from holo2.cli import record_registry                        # noqa: E402
from holo2.core import ResourceKey, Store                    # noqa: E402
from holo2.engine import RECIPE_V1                           # noqa: E402
from holo2.format import FormatRowSpec, format_row_for       # noqa: E402
from holo2.solve import place_job, resample                  # noqa: E402
from holo2.solve.keys import parse_tile_key                  # noqa: E402
from holo2.solve.tilemap import StoreIndex                   # noqa: E402

import rf1_resume                                            # noqa: E402
from rf1_resume import composed_identity, identity_check, window_of  # noqa: E402


# ------------------------------------------------------- the recording patch

#: The census, and the lock that lets eight workers append to it. It is
#: a LIST and not a thread-local because what is wanted is the whole
#: run's fires in commit-ish order, not one thread's.
_ROWS: list[dict[str, Any]] = []
_LOCK = threading.Lock()
_REAL_RESAMPLE = resample.resample_window


def _recording_resample(view: Any, **kwargs: Any) -> Any:
    """``resample.resample_window``, observed: the verdict is recorded.

    The real function runs first and its result is returned untouched, so
    nothing about the decode changes. What is kept is the outcome, the
    window, and the number of evidence pieces the emission proposed —
    which is the difference between "the re-read fired" and "the re-read
    produced a reading", and only the second can move a certificate.
    """
    result = _REAL_RESAMPLE(view, **kwargs)
    plan = kwargs["plan"]
    pieces = sum(1 for write in result.writes
                 if write.key.kind == "evidence")
    with _LOCK:
        _ROWS.append({"window": str(plan.window_id),
                      "footing": str(plan.footing_id),
                      "outcome": result.outcome, "pieces": pieces})
    return result


@contextmanager
def _recording() -> Iterator[None]:
    """Install the wrapper for one phase, and take it out again."""
    place_job.resample.resample_window = _recording_resample     # type: ignore[assignment]
    try:
        yield
    finally:
        place_job.resample.resample_window = _REAL_RESAMPLE      # type: ignore[assignment]


# ------------------------------------------------------------ state reading

@dataclass(frozen=True)
class Facts:
    """One read-only snapshot of a state directory."""

    certified: frozenset[ResourceKey]
    poses: frozenset[ResourceKey]
    poses_by_window: dict[ResourceKey, int]
    posed_evidence: int
    pieces: int
    open_tiles: int

    @property
    def two_pose_windows(self) -> int:
        return sum(1 for count in self.poses_by_window.values() if count > 1)


def read_state(state_dir: Path) -> Facts:
    """The durable facts this measurement needs, READ-ONLY.

    ``Store.open`` directly, as ``rf1_resume.read_state`` does and for
    the same reasons — including its caveat: opening a state rewrites the
    cache file's mtime, so verify an untouched original by CONTENT.
    """
    with Store.open(state_dir, record_registry(page_domain=()),
                    fsync=False) as store:
        index = StoreIndex.build(store)
        return Facts(
            certified=frozenset(index.certified_tiles),
            poses=frozenset(index.poses),
            poses_by_window={window: len(keys) for window, keys
                             in index.poses_by_window.items()},
            posed_evidence=len(index.evidence_by_pose),
            pieces=len(index.evidence_footings),
            open_tiles=len(index.open_tiles))


def column_of(key: ResourceKey) -> int:
    """The tile COLUMN a work key names (``tx``)."""
    return parse_tile_key(key)[2]


# ------------------------------------------------------------------ the run

@dataclass
class Phase:
    label: str
    seconds: float
    status: str
    commits: int
    fires: int
    certified: int
    exhausted: bool
    reason: str | None
    rows: tuple[str, ...]
    payload_sha: str | None
    payload_len: int | None
    payload: bytes | None
    close: dict[str, Any] | None
    resamples: tuple[dict[str, Any], ...] = field(default_factory=tuple)


def run_phase(label: str, *, state_dir: Path, row: FormatRowSpec,
              scans: Sequence[tuple[Path, float]], workers: int,
              no_close: bool, output: Path) -> Phase:
    """One ``cli.decode`` over the state directory, timed and summarised."""
    request = DecodeRequest(scans=tuple(scans), workers=workers, diag_port=0,
                            state_dir=state_dir, output=output, complete=True,
                            no_close=no_close)
    providers = real_providers(row, tuple(scans))
    source = real_source(row, RECIPE_V1)
    del _ROWS[:]
    started = time.monotonic()
    with _recording():
        outcome, observer = cli.decode(request, row, providers, source=source,
                                       recipe=RECIPE_V1)
    seconds = time.monotonic() - started
    payload = outcome.payload
    return Phase(
        label=label, seconds=seconds, status=outcome.status,
        commits=outcome.commits, fires=outcome.fires,
        certified=outcome.certified, exhausted=outcome.exhausted,
        reason=outcome.reason,
        rows=tuple(observer.status().get("rows") or ()),
        payload_sha=(hashlib.sha256(payload).hexdigest()
                     if payload is not None else None),
        payload_len=None if payload is None else len(payload),
        payload=payload, close=outcome.close,
        resamples=tuple(_ROWS))


# --------------------------------------------------------------- the report

def distribution(counts: Counter) -> str:
    if not counts:
        return "(none)"
    return ", ".join(f"{key} pose(s): {counts[key]} window(s)"
                     for key in sorted(counts))


def render(label: str, header: dict[str, Any], identity: Sequence[str],
           before: Facts, after: Facts, phases: Sequence[Phase],
           expect_sha: str, column: int | None) -> str:
    out: list[str] = [f"# The re-read by resume — {label}", "",
                      "## Flags (every number below carries these)", ""]
    out += [f"- {key}: `{value}`" for key, value in header.items()]
    out += ["", "## (A) Identity — does the resume open?", ""]
    out += list(identity)

    gained = sorted(after.certified - before.certified)
    lost = sorted(before.certified - after.certified)
    out += ["", "## (B) Certificates — the whole sheet", "",
            "| | before | after | delta |", "|---|---:|---:|---:|",
            f"| certified tiles | {len(before.certified)} | "
            f"{len(after.certified)} | {len(after.certified) - len(before.certified):+d} |",
            f"| open (uncertified) work keys | {before.open_tiles} | "
            f"{after.open_tiles} | {after.open_tiles - before.open_tiles:+d} |",
            f"| PoseRecords | {len(before.poses)} | {len(after.poses)} | "
            f"{len(after.poses) - len(before.poses):+d} |",
            f"| poses OWNING evidence | {before.posed_evidence} | "
            f"{after.posed_evidence} | "
            f"{after.posed_evidence - before.posed_evidence:+d} |",
            f"| evidence pieces | {before.pieces} | {after.pieces} | "
            f"{after.pieces - before.pieces:+d} |",
            f"| windows with TWO committed poses | {before.two_pose_windows} "
            f"| {after.two_pose_windows} | "
            f"{after.two_pose_windows - before.two_pose_windows:+d} |",
            "",
            f"- **GAINED {len(gained)}**, **LOST {len(lost)}** "
            "(certified tile SETS, not counts)"]
    if lost:
        out.append("- lost: " + ", ".join(str(key) for key in lost))
    if gained:
        out.append("- gained: " + ", ".join(str(key) for key in gained))
    out += ["",
            "- poses per window extent, before: "
            + distribution(Counter(before.poses_by_window.values())),
            "- poses per window extent, after:  "
            + distribution(Counter(after.poses_by_window.values()))]

    if column is not None:
        was = {key for key in before.certified if column_of(key) == column}
        now = {key for key in after.certified if column_of(key) == column}
        out += ["", f"## (C) The `tx = {column}` column — population under "
                "study, NOT a bar", "",
                f"- certified before: **{len(was)}**, after: **{len(now)}** "
                f"({len(now) - len(was):+d})",
                "- gained: " + (", ".join(str(key)
                                          for key in sorted(now - was))
                                or "(none)"),
                "- lost: " + (", ".join(str(key)
                                        for key in sorted(was - now))
                              or "(none)")]

    for phase in phases:
        rows = phase.resamples
        outcomes = Counter(row["outcome"] for row in rows)
        emitted = [row for row in rows if row["pieces"]]
        out += ["", f"## (D) phase {phase.label} — the re-read census", "",
                f"- fires: **{len(rows)}** over "
                f"{len({row['window'] for row in rows})} window(s)",
                "- outcomes: " + (", ".join(f"`{name}` {n}" for name, n
                                            in outcomes.most_common())
                                  or "(none)"),
                f"- fires that EMITTED: **{len(emitted)}**, "
                f"pieces written: **{sum(row['pieces'] for row in emitted)}**"]

    out += ["", "## (E) The two phases", "",
            "| phase | close policy | wall s | status | commits | fires | "
            "certified | exhausted |",
            "|---|---|---:|---|---:|---:|---:|---|"]
    for phase in phases:
        policy = "--no-close" if phase.label.startswith("1") else "close"
        out.append(f"| {phase.label} | {policy} | {phase.seconds:.1f} | "
                   f"{phase.status} | {phase.commits} | {phase.fires} | "
                   f"{phase.certified} | {phase.exhausted} |")
    for phase in phases:
        out += ["", f"### phase {phase.label}", ""]
        if phase.reason:
            out += [f"reason: {phase.reason}", ""]
        out += ["    " + line for line in phase.rows]

    final = phases[-1]
    out += ["", "## (F) Payload", "",
            f"- expected sha256: `{expect_sha}`",
            f"- recovered sha256: `{final.payload_sha}` "
            f"({final.payload_len} bytes)",
            ("- **BYTE-IDENTICAL**" if final.payload_sha == expect_sha
             else "- **PAYLOAD DIFFERS**")]
    if final.close is not None:
        out += ["", f"close report: `{json.dumps(final.close, sort_keys=True)}`"]
    return "\n".join(out) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure F2a's re-read by resuming an archived state.")
    parser.add_argument("--state", type=Path, required=True,
                        help="the state directory to RESUME (use a copy)")
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--dpi", type=float, required=True)
    parser.add_argument("--format", dest="format_ref", required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--expect-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--column", type=int, default=None,
                        help="report this tile column separately (Xerox: 0)")
    parser.add_argument("--preflight", action="store_true",
                        help="check the identity and the state, run nothing")
    args = parser.parse_args(argv)

    row = format_row_for(args.format_ref, pages=1)
    scans = ((args.scan, args.dpi),)
    providers = real_providers(row, scans)
    source = real_source(row, RECIPE_V1)
    equal, lines = identity_check(args.state,
                                  composed_identity(row, providers, source))
    if not equal:
        print("REFUSED: the stored lineage differs from this run's.")
        print("\n".join(lines))
        return 2
    before = read_state(args.state)
    if args.preflight:
        print("\n".join(lines))
        print(f"certified {len(before.certified)}, poses {len(before.poses)}, "
              f"poses owning evidence {before.posed_evidence}, "
              f"two-pose windows {before.two_pose_windows}")
        return 0

    output = args.out.with_suffix(".bin")
    phases = [run_phase("1 (re-read live)", state_dir=args.state, row=row,
                        scans=scans, workers=args.workers, no_close=True,
                        output=output),
              run_phase("2 (close)", state_dir=args.state, row=row,
                        scans=scans, workers=args.workers, no_close=False,
                        output=output)]
    after = read_state(args.state)
    header = {"state dir": args.state, "capture": f"{args.scan} @ {args.dpi}",
              "format": args.format_ref, "workers": args.workers,
              "complete": True, "recipe": "RECIPE_V1",
              "phase 1 close policy": "--no-close (terminal close skipped)",
              "phase 2 close policy": "ordinary close",
              "PoseRefineProvider.revise": "True (production default)",
              "date": "2026-08-23"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(args.label or str(args.state), header, lines,
                               before, after, phases, args.expect_sha,
                               args.column))
    if phases[-1].payload is not None:
        output.write_bytes(phases[-1].payload)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":          # pragma: no cover
    raise SystemExit(main())

# ``rf1_resume`` is imported for its preflight and its window grouping, and
# the name is referenced here so a reader (and pyflakes) sees the tie.
_ = (rf1_resume.__doc__, window_of)
