#!/usr/bin/env python
"""RF1's yield BY RESUME — the W2 measurement (RULINGS I5/I4/I4a, 2026-08-23).

    env/bin/python holo2/measure/rf1_resume.py \\
        --state scratch/holo2-catchup/real/e029-state-complete-rf1 \\
        --scan scratch/e028/hp-canon-c2-ink-counting.tiff \\
        --dpi 4800 --format L:c2-r0700@3392x2368 --label e029 \\
        --workers 8 --expect-sha e5021f8d… \\
        --out scratch/holo2-catchup/real/rf1-e029.md

NOT A TEST and not collectable as one — the same standing as
``tile_differential.py`` and the other by-path drivers in this directory
(``holo2/measure/README.md``). It RESUMES an exhausted holo2 state
directory in-process with the production provider roster, one substitution:
``refine.PoseRefineProvider(row, revise=True)``. Nothing under
``holo2/src`` changes; the dial is a constructor flag and is NOT in the
session identity (``core.work.providers_identity`` reads
``provider.provider_id`` alone), which is precisely why RULINGS I5 says a
resume is the lawful way to price RF1 without forking the lineage.

WHY THE RUN IS TWO PHASES, and why that is forced rather than chosen.
An exhausted ``--complete`` state holds a TERMINAL ``CloseRecord``, and a
terminal session is immutable: ``Orchestrator.run`` returns
``_terminal_outcome()`` before a single provider is asked to expand
(``orchestrator.py:212``). So a resume that intends to COMMIT must open
with the close set aside — ``--no-close``, the user's 2026-08-22 ruling:
the journal is never rewritten, the close line is skipped on ingestion
(``Store.open_or_create(skip_close=True)``) and the session opens OPEN.
But a skipped close also means no close is decided, so no payload comes
back. Hence:

* **phase 1** — ``no_close=True, complete=True``: the state is re-opened
  OPEN, RF1 is live, and the run goes to exhaustion. Every certificate
  this measures is minted here.
* **phase 2** — ``no_close=False, complete=True``, the SAME roster: the
  work is already spent, so this run re-derives the close from every
  certificate then standing and hands back the payload. Its commits and
  its certified count are reported too, because "phase 2 did work" would
  be a finding about the exhaustion of phase 1, not a detail.

Both phases are the same lineage: same row, same recipe, same provider
ids, same work source. The identity is CHECKED before either runs
(:func:`identity_check`) — RULINGS I5's "if it refuses, STOP and report
why, do not fork".

WHAT IS COUNTED, and where each number comes from.

* certificates before/after — ``StoreIndex.certified`` on the state
  directory before phase 1 and after phase 2 (read-only ``Store.open``,
  the differential's own door).
* payload byte-identity — sha256 of phase 2's ``RunOutcome.payload``
  against the operator-supplied ``--expect-sha`` (the e029/xerox golden
  ``e5021f8d…``). The bytes are also written beside the report.
* commits / fires / wall — ``RunOutcome.commits``/``.fires`` per phase
  and ``time.monotonic`` around each ``cli.decode``. NEVER via pytest
  (measurement doctrine).
* PoseRecords minted — the pose-key set before phase 1 vs after phase 2.
  Grouped by ``PoseRecord.window_id`` (which IS the window extent: a
  window key is footing/region/extent, ``keys.parse_window_key``), so
  "poses per window extent" is a distribution over that grouping, both
  for the poses this run added and for the whole standing collection.
* refine fires, their outcomes, and the NO-OP share — from an
  instrumented subclass of the real provider (:class:`TallyingProvider`),
  which overrides ``expand``/``worker`` to count and delegates every
  decision to ``PoseRefineProvider``/``PoseRefineWorker`` unchanged.

THE ONE MEASUREMENT PATCH, stated plainly. ``PoseRefineWorker.run``
already refuses a revision whose canonical affine collides with a pose
that stands, under the single outcome string ``refused_pose_unmoved``
(``refine.py``, the "bounded search landed on geometry that already
stands" branch) — that IS the no-op guard RULINGS I4a describes, built.
But the string alone cannot say WHICH pose it collided with, and the
distinction the ruling asks about ("canonical affine equal to the
STANDING pose") is exactly that. So this driver temporarily rebinds
``refine.propose`` to a recording wrapper (:func:`recording_propose`)
that stashes each fire's verdict in a thread-local; the tally then
rebuilds the revised ``PoseRecord`` the same way the worker does and
reports ``unmoved_own`` (collided with its own parent) versus
``collides_existing`` (collided with a sibling already committed). The
wrapper returns the real verdict untouched, is installed only for the
duration of a phase, and is removed in a ``finally``. It changes no
decision — it observes one.

THE DIAL-OFF CONTROL (``--no-revise``). A resume is not inert on its own:
opening a session re-offers its scheduling set, and on one of the two
real sheets that alone moved the payload ledger. So the driver takes the
same arm with RF1 at its PRODUCTION default (``revise=False``), on its
own copy of the same state, and the difference between the two arms is
what may be attributed to RF1. Without it, resume churn reads as yield.

FLAGS ARE PART OF EVERY NUMBER (measurement doctrine): the report header
carries state dir, capture + declared dpi, format ref, workers, close
policy per phase, ``revise``, recipe id, fsync and snapshot cadence.
Run this against a COPY of an exhausted state — it commits, by design.
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
for _path in (_ROOT / "holo2" / "src", _ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from holo2 import cli                                        # noqa: E402
from holo2.cli import (DecodeRequest, real_providers, real_source,  # noqa: E402
                       record_registry)
from holo2.core import (ExpansionRequest, ResourceKey, SolveView,  # noqa: E402
                        Store, WorkDescriptor, providers_identity)
from holo2.engine import POLICY_ID, RECIPE_V1, SessionIdentity  # noqa: E402
from holo2.format import FormatRowSpec, format_row_for         # noqa: E402
from holo2.solve import refine                                 # noqa: E402
from holo2.solve.keys import KIND_WINDOW, WINDOW_KEY_PARTS     # noqa: E402
from holo2.solve.records import PoseRecord                     # noqa: E402
from holo2.solve.tilemap import StoreIndex                     # noqa: E402
from holo2.solve.view import as_plane                          # noqa: E402

#: The route every fire in this driver runs under (PROVIDERS RF1).
ROUTE = refine.ROUTE_REFINE_K


# ------------------------------------------------------- the recording patch

class _VerdictSlot(threading.local):
    """One fire's search verdict, per thread. See the module docstring."""

    verdict: Any = None


_SLOT = _VerdictSlot()

#: The real search, bound ONCE at import — before any rebinding, so the
#: wrapper can never wrap itself on a second install.
_REAL_PROPOSE = refine.propose


def recording_propose(*args: Any, **kwargs: Any) -> Any:
    """``refine.propose``, observed: the verdict is stashed, then returned."""
    verdict = _REAL_PROPOSE(*args, **kwargs)
    _SLOT.verdict = verdict
    return verdict


@contextmanager
def recording_verdicts() -> Iterator[None]:
    """Install :func:`recording_propose` for the duration of one phase."""
    refine.propose = recording_propose            # type: ignore[assignment]
    try:
        yield
    finally:
        refine.propose = _REAL_PROPOSE            # type: ignore[assignment]


# --------------------------------------------------------------- the tally

@dataclass
class RefineTally:
    """What RF1 did, counted at the provider/worker boundary.

    ``outcomes`` is the raw ``WorkResult.outcome`` histogram (``adopted``
    and every ``refused:<reason>``); ``no_op`` splits the built no-op
    guard's one string into the two cases the ruling asks about.
    """

    expansions: int = 0
    descriptors: int = 0
    descriptors_max: int = 0
    fires: int = 0
    fire_seconds: float = 0.0
    outcomes: Counter = field(default_factory=Counter)
    no_op: Counter = field(default_factory=Counter)
    fires_by_pose: Counter = field(default_factory=Counter)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def note_expansion(self, minted: int) -> None:
        with self._lock:
            self.expansions += 1
            self.descriptors += minted
            self.descriptors_max = max(self.descriptors_max, minted)

    def note_fire(self, pose_id: ResourceKey, outcome: str,
                  seconds: float, no_op: str | None) -> None:
        with self._lock:
            self.fires += 1
            self.fire_seconds += seconds
            self.outcomes[outcome] += 1
            self.fires_by_pose[pose_id] += 1
            if no_op is not None:
                self.no_op[no_op] += 1


class TallyingWorker(refine.PoseRefineWorker):
    """The real worker, timed and counted. Every decision is ``super()``'s."""

    def __init__(self, *args: Any, tally: RefineTally, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tally = tally

    def run(self, view: SolveView, identity: Any, progress: Any) -> Any:
        _SLOT.verdict = None
        started = time.monotonic()
        result = super().run(view, identity, progress)
        seconds = time.monotonic() - started
        self._tally.note_fire(self.pose_id, result.outcome, seconds,
                              self._no_op_case(view, result.outcome))
        return result

    def _no_op_case(self, view: SolveView, outcome: str) -> str | None:
        """Which pose the refused revision collided with, or None.

        Rebuilt exactly as ``PoseRefineWorker.run`` builds it — same
        record shape, same ``resource_key()`` — from the verdict the
        recording wrapper stashed. Anything unexpected (no verdict, no
        affine, no live pose) reports ``unclassified`` rather than
        guessing, so a gap in the observation can never masquerade as a
        measured case.
        """
        if outcome != refine.OUTCOME_REFUSED_PREFIX + "pose_unmoved":
            return None
        verdict = _SLOT.verdict
        affine = getattr(verdict, "affine", None)
        pose = as_plane(view).index().poses.get(self.pose_id)
        if affine is None or pose is None:
            return "unclassified"
        key = PoseRecord(window_id=pose.window_id, footing_id=pose.footing_id,
                         page=pose.page, native_affine=affine).resource_key()
        return "unmoved_own" if key == self.pose_id else "collides_existing"


class TallyingProvider(refine.PoseRefineProvider):
    """``PoseRefineProvider(row, revise=True)`` with a counter around it.

    ``provider_id`` is inherited unchanged (``refine-pose-v1``), which is
    what keeps the session identity — and therefore the resume — lawful.
    """

    def __init__(self, row: FormatRowSpec, tally: RefineTally, *,
                 revise: bool = True) -> None:
        super().__init__(row, revise=revise)
        self._tally = tally

    def expand(self, view: SolveView,
               request: ExpansionRequest) -> tuple[WorkDescriptor, ...]:
        minted = super().expand(view, request)
        self._tally.note_expansion(len(minted))
        return minted

    def worker(self, view: SolveView,
               descriptor: WorkDescriptor) -> TallyingWorker:
        return TallyingWorker(descriptor.subject, self._base, self._labels,
                              self._config, tally=self._tally)


def roster(row: FormatRowSpec, scans: Sequence[tuple[Path, float]],
           tally: RefineTally, *, revise: bool) -> tuple[Any, ...]:
    """The production roster with RF1 substituted, order preserved.

    ``cli.real_providers`` is the authority on WHICH families decode a K
    sheet and in WHICH order (the order is the arbitration order and rides
    the identity), so the roster is taken from it and the last member —
    RF1, which that function documents as last — is swapped for the
    instrumented one. Composing a tuple by hand here would fork the
    binding the moment production's changed.
    """
    real = list(real_providers(row, tuple(scans)))
    assert isinstance(real[-1], refine.PoseRefineProvider), (
        "cli.real_providers no longer ends with RF1; this driver's "
        "substitution assumes the census order")
    real[-1] = TallyingProvider(row, tally, revise=revise)
    return tuple(real)


# ------------------------------------------------------------ state reading

@dataclass(frozen=True)
class StateFacts:
    """One read-only snapshot of a state directory."""

    certified: int
    poses: frozenset[ResourceKey]
    poses_by_window: dict[ResourceKey, int]
    open_tiles: int
    #: family -> (rows, attempts, exposures) off ``core.identity.SpendLedger``.
    #: THE DOWNSTREAM QUESTION, and the reason it is read here: a revised
    #: pose is a PROPOSAL that an ordinary payload rerun must follow, so
    #: "did anything follow?" is answered by whether the payload family's
    #: attempts and CRC exposures MOVED — not by the certificate count,
    #: which is silent about work that ran and lost. A row is never pruned
    #: (``SpendLedger``), so before/after subtracts cleanly.
    spends: dict[str, tuple[int, int, int]]

    @property
    def pose_count(self) -> int:
        return len(self.poses)


def read_state(state_dir: Path) -> StateFacts:
    """The durable facts this measurement needs, READ-ONLY.

    ``Store.open`` directly (never ``cli.open_receiver``): a snapshot
    needs no session, no providers and no recipe. It still takes the
    directory's exclusive lock, so it must not run while a decode holds
    the state.

    READ-ONLY IS ABOUT CONTENT, NOT ABOUT mtime (W2 review, 2026-08-23):
    ``Store.open`` is not a read-only door. ``CacheWriter.resume`` does
    ``os.truncate(path, state.end)`` (``core/cache.py``), so opening a
    state — even only to read it — rewrites the ``cache`` file's mtime.
    The journal and blobs are untouched; verify an "untouched original"
    by content (``cmp``/sha), never by timestamp.
    """
    with Store.open(state_dir, record_registry(page_domain=()),
                    fsync=False) as store:
        index = StoreIndex.build(store)
        spends: dict[str, tuple[int, int, int]] = {}
        for spend in store.ledger.entries():
            rows, attempts, exposures = spends.get(spend.worker_id.family,
                                                   (0, 0, 0))
            spends[spend.worker_id.family] = (rows + 1,
                                              attempts + spend.attempts,
                                              exposures + spend.exposures)
        return StateFacts(
            certified=index.certified,
            poses=frozenset(index.poses),
            poses_by_window={window: len(keys) for window, keys
                             in index.poses_by_window.items()},
            open_tiles=len(index.open_tiles),
            spends=spends)


def window_of(pose_key: ResourceKey) -> ResourceKey:
    """The window extent a pose key names.

    A pose key's leading :data:`WINDOW_KEY_PARTS` parts ARE its window
    key (``keys.POSE_SPEC`` extends ``WINDOW_SPEC``), and a window key is
    footing/region/extent — so grouping on this IS grouping by window
    extent, which is what RULINGS I3/I4 ask the distribution to be over.
    Keys are grouped as KEYS, never as their ``__str__`` (display only,
    ``core/keys.py``).
    """
    return ResourceKey(KIND_WINDOW, pose_key.parts[:WINDOW_KEY_PARTS])


# -------------------------------------------------------------- the preflight

def composed_identity(row: FormatRowSpec, providers: Sequence[Any],
                      source: Any) -> SessionIdentity:
    """The identity ``cli.open_receiver`` would compose for this run."""
    return SessionIdentity(
        format_row_id=row.row_id, receiver_policy_id=POLICY_ID,
        recipe_entries=RECIPE_V1.entries,
        providers=providers_identity(providers) + (source.source_id,),
        page_domain=row.page_domain)


def identity_check(state_dir: Path, expected: SessionIdentity
                   ) -> tuple[bool, list[str]]:
    """Does the stored lineage compare EQUAL to this run's? (RULINGS I5.)

    The stored one is read with ``Store.peek_identity`` — ``cli._peek``'s
    own door, the cheapest read there is — and compared field by field so
    a refusal names what moved. ``Store.open_or_create`` would refuse a
    mismatch anyway; this is the same law stated before eight workers and
    a 4800-dpi capture are put behind it.
    """
    stored: SessionIdentity = Store.peek_identity(state_dir,
                                                  record_registry())
    lines: list[str] = []
    equal = stored == expected
    for name in ("format_row_id", "receiver_policy_id", "recipe_entries",
                 "providers", "page_domain"):
        was, now = getattr(stored, name), getattr(expected, name)
        mark = "==" if was == now else "!="
        lines.append(f"- `{name}` {mark} stored={was!r} run={now!r}")
    return equal, lines


# ------------------------------------------------------------------ the run

@dataclass
class PhaseResult:
    label: str
    seconds: float
    status: str
    commits: int
    fires: int
    certified: int
    exhausted: bool
    resumed_terminal: bool
    reason: str | None
    rows: tuple[str, ...]
    payload_sha: str | None
    payload_len: int | None
    payload_bytes: bytes | None
    close: dict[str, Any] | None


def run_phase(label: str, *, state_dir: Path, row: FormatRowSpec,
              scans: Sequence[tuple[Path, float]], workers: int,
              tally: RefineTally, revise: bool, no_close: bool,
              output: Path) -> PhaseResult:
    """One ``cli.decode`` over the state directory, timed and summarised.

    ``output`` rides the request because the record carries it; ``decode``
    itself publishes nothing (``cli.main`` is what calls ``publish_once``),
    so this driver writes the recovered bytes once, at the end.
    """
    request = DecodeRequest(scans=tuple(scans), workers=workers, diag_port=0,
                            state_dir=state_dir, output=output, complete=True,
                            no_close=no_close)
    providers = roster(row, scans, tally, revise=revise)
    source = real_source(row, RECIPE_V1)
    started = time.monotonic()
    with recording_verdicts():
        outcome, observer = cli.decode(request, row, providers, source=source,
                                       recipe=RECIPE_V1)
    seconds = time.monotonic() - started
    payload = outcome.payload
    return PhaseResult(
        label=label, seconds=seconds, status=outcome.status,
        commits=outcome.commits, fires=outcome.fires,
        certified=outcome.certified, exhausted=outcome.exhausted,
        resumed_terminal=outcome.resumed_terminal, reason=outcome.reason,
        rows=tuple(observer.status().get("rows") or ()),
        payload_sha=(hashlib.sha256(payload).hexdigest()
                     if payload is not None else None),
        payload_len=None if payload is None else len(payload),
        payload_bytes=payload, close=outcome.close)


# --------------------------------------------------------------- the report

def histogram(counts: Counter) -> str:
    if not counts:
        return "(none)"
    return ", ".join(f"`{name}` {n}" for name, n in counts.most_common())


def distribution(values: Sequence[int], counted: str = "pose",
                 per: str = "window") -> str:
    """``n <counted> per <per> -> how many <per>``, plus the max.

    The two nouns are parameters because this renders two different
    distributions — poses per window extent, and fires per pose — and a
    fixed pair mislabelled the second one.
    """
    if not values:
        return "(none)"
    counts = Counter(values)
    body = ", ".join(f"{k} {counted}(s): {counts[k]} {per}(s)"
                     for k in sorted(counts))
    return f"{body}; max {max(values)}"


def render(label: str, header: dict[str, Any], identity_lines: Sequence[str],
           identity_ok: bool, before: StateFacts, after: StateFacts,
           phases: Sequence[PhaseResult], tally: RefineTally,
           expect_sha: str) -> str:
    new_poses = sorted(after.poses - before.poses)
    lost_poses = sorted(before.poses - after.poses)
    new_by_window = Counter(window_of(key) for key in new_poses)
    lines: list[str] = []
    lines.append(f"# RF1 by resume — {label}")
    lines.append("")
    lines.append("## Flags (every number below carries these)")
    lines.append("")
    for name, value in header.items():
        lines.append(f"- {name}: `{value}`")
    lines.append("")
    lines.append("## (A) Identity — does the resume open?")
    lines.append("")
    lines.append(f"**SessionIdentity compares "
                 f"{'EQUAL' if identity_ok else 'UNEQUAL'}** "
                 "(stored vs this run's composed lineage).")
    lines.append("")
    lines.extend(identity_lines)
    lines.append("")
    lines.append("## (B) Certificates and poses, before and after")
    lines.append("")
    lines.append("| | before | after | delta |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| certified tiles | {before.certified} | {after.certified} "
                 f"| {after.certified - before.certified:+d} |")
    lines.append(f"| open (uncertified) tile keys | {before.open_tiles} | "
                 f"{after.open_tiles} | "
                 f"{after.open_tiles - before.open_tiles:+d} |")
    lines.append(f"| PoseRecords | {before.pose_count} | {after.pose_count} | "
                 f"{after.pose_count - before.pose_count:+d} |")
    lines.append("")
    lines.append(f"- PoseRecords MINTED by this resume: **{len(new_poses)}**"
                 + (f" (and {len(lost_poses)} disappeared — a finding, "
                    "records are never deleted)" if lost_poses else ""))
    lines.append(f"- their window extents: **{len(new_by_window)}** distinct; "
                 f"per-extent {distribution(list(new_by_window.values()))}")
    lines.append(f"- ALL poses per window extent, after: "
                 f"{distribution(list(after.poses_by_window.values()))}")
    lines.append(f"- ALL poses per window extent, before: "
                 f"{distribution(list(before.poses_by_window.values()))}")
    lines.append("")
    lines.append("### Did anything DOWNSTREAM follow the revisions?")
    lines.append("")
    lines.append("Spend rows / attempts / CRC exposures per family — a "
                 "revised pose is a proposal an ordinary payload rerun must "
                 "follow, so an unmoved `payload` row means nothing consumed "
                 "it (and `certified +0` alone could not say that).")
    lines.append("")
    lines.append("| family | rows before | rows after | attempts before | "
                 "attempts after | exposures before | exposures after |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for family in sorted(set(before.spends) | set(after.spends)):
        was = before.spends.get(family, (0, 0, 0))
        now = after.spends.get(family, (0, 0, 0))
        lines.append(f"| {family} | {was[0]} | {now[0]} | {was[1]} | {now[1]} "
                     f"| {was[2]} | {now[2]} |")
    lines.append("")
    lines.append("## (C) RF1: expansion, fires, outcomes")
    lines.append("")
    lines.append(f"- expansions asked of the provider: **{tally.expansions}**")
    lines.append(f"- descriptors minted (eligible poses, summed over "
                 f"expansions): **{tally.descriptors}**; most in one "
                 f"expansion: {tally.descriptors_max}")
    lines.append(f"- fires (worker runs): **{tally.fires}**, "
                 f"{tally.fire_seconds:.1f} s of fire time in total")
    lines.append(f"- outcomes: {histogram(tally.outcomes)}")
    lines.append(f"- no-op guard split (`refused_pose_unmoved`): "
                 f"{histogram(tally.no_op)}")
    fired = list(tally.fires_by_pose.values())
    lines.append(f"- distinct poses fired: **{len(fired)}**; fires per pose: "
                 f"{distribution(fired, 'fire', 'pose')}")
    lines.append("")
    lines.append("## (D) The two phases")
    lines.append("")
    lines.append("| phase | close policy | wall s | status | commits | fires "
                 "| certified | exhausted |")
    lines.append("|---|---|---:|---|---:|---:|---:|---|")
    for phase in phases:
        policy = "--no-close" if phase.label.startswith("1") else "close"
        lines.append(f"| {phase.label} | {policy} | {phase.seconds:.1f} | "
                     f"{phase.status} | {phase.commits} | {phase.fires} | "
                     f"{phase.certified} | {phase.exhausted} |")
    lines.append("")
    for phase in phases:
        lines.append(f"### phase {phase.label}")
        lines.append("")
        if phase.reason:
            lines.append(f"reason: {phase.reason}")
            lines.append("")
        if phase.resumed_terminal:
            lines.append("resumed TERMINAL: this run committed nothing.")
            lines.append("")
        for row in phase.rows:
            lines.append(f"    {row}")
        lines.append("")
    final = phases[-1]
    lines.append("## (E) Payload")
    lines.append("")
    lines.append(f"- expected sha256: `{expect_sha}`")
    lines.append(f"- recovered sha256: `{final.payload_sha}` "
                 f"({final.payload_len} bytes)")
    verdict = ("BYTE-IDENTICAL" if final.payload_sha == expect_sha
               else "MISMATCH — a finding")
    lines.append(f"- **{verdict}**")
    if final.close:
        lines.append("")
        lines.append("close report: `" + json.dumps(final.close,
                                                    sort_keys=True) + "`")
    lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------- driver

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rf1_resume",
        description="Resume an exhausted holo2 state and price RF1.")
    parser.add_argument("--state", type=Path, required=True,
                        help="the state directory to resume (USE A COPY)")
    parser.add_argument("--scan", type=Path, required=True,
                        help="the capture the state was decoded from")
    parser.add_argument("--dpi", type=float, required=True,
                        help="operator-declared true DPI of --scan")
    parser.add_argument("--format", dest="format_ref", required=True,
                        help="the printed format reference (L: fossil or v2)")
    parser.add_argument("--label", default="", help="report title")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--expect-sha", required=True,
                        help="the golden payload sha256 this volume must give")
    parser.add_argument("--out", type=Path, required=True,
                        help="where the markdown report is written")
    parser.add_argument("--preflight", action="store_true",
                        help="check the identity and read the state, then stop")
    parser.add_argument("--no-revise", dest="revise", action="store_false",
                        help="THE DIAL-OFF CONTROL: resume the same way with "
                             "RF1 at its production default (revise=False), "
                             "so churn a resume causes ANYWAY is not read as "
                             "RF1's yield")
    args = parser.parse_args(argv)

    state_dir: Path = args.state
    pages = len(Store.peek_identity(state_dir, record_registry()).page_domain)
    row = format_row_for(args.format_ref, pages)
    scans = ((args.scan, args.dpi),)
    tally = RefineTally()
    providers = roster(row, scans, tally, revise=args.revise)
    source = real_source(row, RECIPE_V1)
    identity_ok, identity_lines = identity_check(
        state_dir, composed_identity(row, providers, source))
    print(f"identity equal: {identity_ok}", file=sys.stderr)
    for line in identity_lines:
        print(line, file=sys.stderr)
    if not identity_ok:
        print("REFUSED: the composed lineage differs from the stored one; "
              "RULINGS I5 says STOP rather than fork.", file=sys.stderr)
        return 1

    before = read_state(state_dir)
    print(f"before: certified {before.certified}, poses {before.pose_count}, "
          f"open tiles {before.open_tiles}", file=sys.stderr)
    if args.preflight:
        return 0

    header = {
        "state dir": state_dir,
        "capture": f"{args.scan} @ {args.dpi} dpi",
        "format": args.format_ref,
        "workers": args.workers,
        "complete": True,
        "phase 1 close policy": "--no-close (the terminal close is skipped)",
        "phase 2 close policy": "ordinary close",
        "PoseRefineProvider.revise": args.revise,
        "recipe": "RECIPE_V1",
        "fsync": "True (cli.decode default, as the H6 CLI runs used)",
        "snapshot_every": cli.DEFAULT_SNAPSHOT_EVERY,
        "date": "2026-08-23",
    }
    arm = "RF1 live" if args.revise else "RF1 dialled off (control)"
    phases = [run_phase(f"1 ({arm})", state_dir=state_dir, row=row,
                        scans=scans, workers=args.workers, tally=tally,
                        revise=args.revise, no_close=True,
                        output=args.out.with_suffix(".phase1.bin"))]
    phases.append(run_phase("2 (close)", state_dir=state_dir, row=row,
                            scans=scans, workers=args.workers, tally=tally,
                            revise=args.revise, no_close=False,
                            output=args.out.with_suffix(".bin")))
    after = read_state(state_dir)
    payload_path = args.out.with_suffix(".bin")
    if phases[-1].payload_bytes is not None:
        if payload_path.exists():
            # W2 review, 2026-08-23: refuse-to-overwrite (publish_once's
            # contract) must SAY SO, or a re-run leaves a stale .bin from
            # an earlier arm sitting next to a fresh report.
            print(f"NOTE: {payload_path} exists — payload NOT rewritten; "
                  "the report's byte-identity verdict is computed from "
                  "this run's in-memory payload, the file on disk may be "
                  "an earlier arm's.", file=sys.stderr)
        else:
            payload_path.write_bytes(phases[-1].payload_bytes)
    report = render(args.label or str(state_dir), header, identity_lines,
                    identity_ok, before, after, phases, tally,
                    args.expect_sha)
    args.out.write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
