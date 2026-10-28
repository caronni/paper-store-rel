#!/usr/bin/env python
"""The maintained derived views against their from-scratch builders — BY PATH.

    env/bin/python holo2/measure/index_equivalence.py

NOT A TEST and not collectable as one: no ``test_`` name, no pytest
fixtures, a ``__main__`` entry point, and it lives outside ``testpaths``
twice over. Same standing as ``refine_equivalence.py``, and for the same
reason — it runs REAL decodes and compares two implementations of one
answer, which is a measurement, not a unit.

WHAT IT PROVES (F-17, the incremental-derived-views card). Two views that
used to be rebuilt from the whole durable store at every single commit
are now MAINTAINED from the commit's own ``changed_keys``:

* :class:`holo2.solve.tilemap.StoreIndex` — advanced by
  :meth:`StoreIndex.updated` on the committing thread, inside the serial
  section (``SessionPlane.invalidate``);
* the H3bis payload FRONTIER — ``RealPayloadProvider.expand``'s per-key
  memo, keyed on the identity of the objects the index hands out.

Both keep their from-scratch producer, and here that producer is the
ORACLE. At **every commit of every arm**, this driver builds
``StoreIndex.build(store)`` beside the maintained index and compares them
field for field; at **every expansion**, it re-runs the provider's own
derivation with an EMPTY memo beside the memoized one and compares the
descriptor tuples. The bar is exact equality, order included wherever
order is consumed (the two grouped read-set views and the descriptor
sequence). A single differing entry is a finding, not a rounding.

WHAT IT DOES NOT COMPARE, and why. The per-kind DICTS' iteration order
is not asserted: nothing consumes it (the audit is choice 5 in
``solve/tilemap.py`` — every exit sorts, and the remaining readers are
sets, sums and grid assignment). It USED to drift, the builder inserting
in the store's sorted-key order against the maintained index's
first-write order; since W3's choice 8 ``StoreIndex.build`` walks
``store.records()``, so both derivations are first-write order and there
is no drift left to tolerate (corrected 2026-08-23, W3 review). The
comparison is unchanged and deliberately stays the looser one: dict
CONTENTS exactly, dict ORDER not. The tuple-valued
groups, whose order IS consumed (an attempt identity is a tuple of
(key, version) pairs in that order), are compared as tuples.

THE POPULATION is real decodes over ``verdicts/_fixtures.py``'s own
builders — the same generator ``src/holo`` prints with — across four arms
chosen to move what the delta has to carry: a clean page (certificates
arrive fast, the certified-stream map fills), the measured e032 channel
warp (evidence piles up on keys that never certify), a banded page whose
right quarter kills the word code (windows retire, poses cluster), and a
two-page volume (two pages under one store, so the (page, ty, tx) map has
to keep them apart). All perturbation is seeded.

FAULT INJECTION is half the proof: a harness that cannot fail proves
nothing. Three deliberate breakages run at the end, each of which MUST be
caught by the comparison above —

1. **a dropped changed key** — one indexed key withheld from the delta at
   one commit, which is the maintenance bug this card could plausibly
   ship;
2. **a stalled generation** — a whole commit's delta withheld, which is
   the "the plane was never told" bug;
3. **a stale frontier memo** — the provider's identity test forced to
   accept, which is the "the memo outlived its input" bug.

A run in which any injection is NOT caught fails as loudly as a real
divergence, because it means the comparison is not looking at anything.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

# Self-locating, like ``./confetti.py``: neither package is pip-installed
# (env honesty), and a driver the operator runs BY PATH should not also
# demand a ``PYTHONPATH=`` prefix to find the tree it lives in.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE / "verdicts", _ROOT / "src", _ROOT / "holo2" / "src"):
    sys.path.insert(0, str(_path))

from _fixtures import (CHANNEL_ROTATION_DEG, CHANNEL_SCALE_YX,  # noqa: E402
                       build_page, build_volume, render)

from holo2 import cli                                          # noqa: E402
from holo2.cli import real_providers                           # noqa: E402
from holo2.solve import payload, plane as plane_module         # noqa: E402
from holo2.solve.tilemap import StoreIndex                     # noqa: E402

PX_PER_DOT = 2

#: The index fields whose ORDER is consumed (choice 5): read sets that
#: become attempt identities, and anchors a stable sort breaks ties on.
#: ``context_fits`` joined at H5 P1 — the adopted record keys enter the
#: payload attempt's read-set, so its grouped tuples are order-compared
#: like the other two.
ORDERED_FIELDS = ("evidence_by_tile", "poses_by_window", "context_fits")
#: The two work-key partitions (choice 7) — sorted tuples, not maps, and
#: their order reaches the descriptor sequence and the close's
#: materialisation order, so they are compared element for element.
PARTITION_FIELDS = ("open_tiles", "certified_tiles")
#: The rest: contents compared exactly, iteration order deliberately not.
#: ``live_poses`` (tilemap choice 8, W3 2026-08-23) is a DICT and its
#: iteration order is nobody's business, but its CONTENT is the "latest
#: committed pose wins" answer every geometry consumer reads — so it is
#: compared here entry for entry, which is what proves the maintained
#: write-order derivation equals the builder's first-write walk.
UNORDERED_FIELDS = ("tiles", "windows", "poses", "regions", "captures",
                    "subjects", "certified_streams", "evidence_footings",
                    "live_poses")


# ------------------------------------------------------- the comparisons

def index_differences(oracle: StoreIndex, live: StoreIndex) -> list[str]:
    """Every place the maintained index differs from the built one."""
    rows: list[str] = []
    if oracle.certified != live.certified:
        rows.append(f"certified: built {oracle.certified} vs "
                    f"maintained {live.certified}")
    for name in PARTITION_FIELDS:
        want, have = getattr(oracle, name), getattr(live, name)
        if want != have:
            rows.append(f"{name}: {len(want)} built vs {len(have)} "
                        "maintained, or a different order")
    for name in ORDERED_FIELDS + UNORDERED_FIELDS:
        want: dict = getattr(oracle, name)
        have: dict = getattr(live, name)
        missing = sorted(str(key) for key in want.keys() - have.keys())
        extra = sorted(str(key) for key in have.keys() - want.keys())
        if missing:
            rows.append(f"{name}: {len(missing)} entries missing, "
                        f"first {missing[0]}")
        if extra:
            rows.append(f"{name}: {len(extra)} entries invented, "
                        f"first {extra[0]}")
        for key in want.keys() & have.keys():
            if want[key] != have[key]:
                # Tuples compare with their order; records and frozensets
                # compare by value. One message either way.
                rows.append(f"{name}[{key}]: {want[key]!r} vs {have[key]!r}")
                break
    return rows


def descriptor_differences(fresh: tuple, memoized: tuple) -> list[str]:
    """The memoized expansion against the same derivation with no memo."""
    if len(fresh) != len(memoized):
        return [f"expand: {len(fresh)} descriptors from scratch vs "
                f"{len(memoized)} memoized"]
    for position, (want, have) in enumerate(zip(fresh, memoized)):
        if want != have:
            return [f"expand[{position}]: {want} vs {have}"]
    return []


class Ledger:
    """What the run saw: comparisons made, and any divergence at all."""

    def __init__(self) -> None:
        self.commits = 0
        self.maintained = 0            # deltas actually carried forward
        self.rebuilds = 0              # production StoreIndex.build calls
        self.expansions = 0
        self.memo_hits = 0
        self.descriptors = 0
        self.divergences: list[str] = []

    def index(self, oracle: StoreIndex, live: StoreIndex) -> None:
        self.commits += 1
        self.divergences += index_differences(oracle, live)

    def expand(self, fresh: tuple, memoized: tuple) -> None:
        self.expansions += 1
        self.descriptors += len(memoized)
        self.divergences += descriptor_differences(fresh, memoized)

    def report(self) -> str:
        return (f"{self.commits} commits compared against "
                f"StoreIndex.build ({self.maintained} deltas carried, "
                f"{self.rebuilds} production rebuilds), {self.expansions} "
                f"expansions compared against a memo-free derivation "
                f"({self.descriptors} descriptors), "
                f"{len(self.divergences)} divergences")


# ------------------------------------------------------------ the intercept

def install(ledger: Ledger, *,
            sabotage: Callable[[int, tuple], tuple | None] | None = None,
            stale_memo: bool = False) -> Callable[[], None]:
    """Run both arms at every commit and every expansion; return the undo.

    ``sabotage`` is the fault injector: it is handed the commit ordinal
    and the real delta and returns the delta to pass on (``None`` = pass
    the real one). ``stale_memo`` forces the provider's identity test to
    accept, which is the memo bug the descriptor comparison must catch.
    """
    plane_invalidate = plane_module.SessionPlane.invalidate
    index_build = StoreIndex.build.__func__            # the raw classmethod
    index_updated = StoreIndex.updated
    provider_expand = payload.RealPayloadProvider.expand
    commits = [0]

    def counted_build(cls, store):
        ledger.rebuilds += 1
        return index_build(cls, store)

    def counted_updated(self, store, changed_keys):
        ledger.maintained += 1
        return index_updated(self, store, changed_keys)

    def compared_invalidate(self, changed_keys=None, *, spent=()):
        delta = changed_keys
        if sabotage is not None and changed_keys is not None:
            replaced = sabotage(commits[0], tuple(changed_keys))
            delta = changed_keys if replaced is None else replaced
        commits[0] += 1
        plane_invalidate(self, delta, spent=spent)
        if changed_keys is None:
            return                       # not a commit: nothing to compare
        # ``SessionPlane`` has no public ``store`` and has not had one
        # since the H4 W2 wall landed; this driver kept asking for it and
        # died at the first commit of the first arm (found and fixed W3,
        # 2026-08-23 — pre-existing bit-rot, not a finding about the
        # index). The private attribute IS the oracle's input here: the
        # whole point is to rebuild from the same store the maintained
        # index was advanced against.
        ledger.index(index_build(StoreIndex, self._store), self.index())

    def compared_expand(self, view, request):
        """The arm under test, then the SAME derivation with no memo.

        The oracle runs second and on a scratch memo, so it re-derives
        every key from the index it is handed and cannot be helped by
        anything the arm cached; the arm's own memo is restored
        afterwards, so the decode proceeds exactly as an unwatched one
        would.
        """
        memoized = arm(self, view, request)
        saved = self._frontier
        self._frontier = {}
        try:
            fresh = provider_expand(self, view, request)
        finally:
            self._frontier = saved
        ledger.expand(fresh, memoized)
        return memoized

    def stale_expand(self, view, request):
        """The memo with its staleness test removed — injection 3."""
        plane = payload.as_plane(view)
        index = plane.index()
        groups, tiles = index.evidence_by_tile, index.tiles
        memo, out = self._frontier, []
        for key in plane.open_work_keys():
            evidence = groups.get(key, ())
            if not evidence:
                continue
            cached = memo.get(key)
            if cached is not None:                     # <- the bug: no test
                out.extend(cached[3])
                continue
            attempts = self._attempts(plane, request, key, evidence,
                                      tiles.get(key))
            memo[key] = (evidence, tiles.get(key), request.arm, attempts)
            out.extend(attempts)
        return tuple(out)

    # The arm the comparison watches: production, or the sabotaged memo.
    arm = stale_expand if stale_memo else provider_expand

    StoreIndex.build = classmethod(counted_build)
    StoreIndex.updated = counted_updated
    plane_module.SessionPlane.invalidate = compared_invalidate
    payload.RealPayloadProvider.expand = compared_expand

    def undo() -> None:
        StoreIndex.build = classmethod(index_build)
        StoreIndex.updated = index_updated
        plane_module.SessionPlane.invalidate = plane_invalidate
        payload.RealPayloadProvider.expand = provider_expand

    return undo


# ---------------------------------------------------------------- the arms

def arms(work: Path) -> list[tuple[str, Any, tuple[tuple[Path, float], ...]]]:
    """Four decodes whose DELTA shape differs on purpose."""
    clean = build_page("c3-k-r0550@8x8")
    channel = build_page("c2-k-r0700@8x8")
    volume = build_volume("c3-k-r0550@6x6", 2)
    clean_capture = render(clean.dots, work / "clean.png",
                           px_per_dot=PX_PER_DOT, cell_dots=clean.cell_dots,
                           noise_sigma=1.0)
    channel_capture = render(
        channel.dots, work / "channel.png", px_per_dot=PX_PER_DOT,
        cell_dots=channel.cell_dots, rotation_deg=CHANNEL_ROTATION_DEG,
        pitch_scale=CHANNEL_SCALE_YX, noise_sigma=2.0, cell_error_rate=0.02)
    banded = render(channel.dots, work / "banded.png", px_per_dot=PX_PER_DOT,
                    cell_dots=channel.cell_dots, rotation_deg=0.3,
                    pitch_scale=1.003, noise_sigma=2.0,
                    cell_error_rate=0.16, cell_error_band=(0.75, 1.0))
    sheets = tuple(
        render(page, work / f"volume-{number}.png", px_per_dot=PX_PER_DOT,
               cell_dots=volume.cell_dots, noise_sigma=1.0)
        for number, page in enumerate(volume.dots))
    return [
        ("clean c3-r0550", clean.row,
         ((clean_capture.path, clean_capture.dpi),)),
        ("e032 channel warp c2-r0700", channel.row,
         ((channel_capture.path, channel_capture.dpi),)),
        ("banded c2-r0700", channel.row, ((banded.path, banded.dpi),)),
        # TWO captures, two pages, one store: the only arm where the
        # delta has to keep two pages' (page, ty, tx) cells apart and
        # where two footing families land in one index.
        ("two-page volume c3-r0550", volume.row,
         tuple((sheet.path, sheet.dpi) for sheet in sheets)),
    ]


def run_decode(work: Path, tag: str, row: Any, scans: tuple) -> None:
    """One serial decode through the wrapped seams."""
    cli.decode(
        cli.DecodeRequest(
            scans=scans, workers=1, diag_port=0,
            state_dir=work / f"state-{tag}",
            output=work / f"recovered-{tag}.bin", complete=True),
        row, real_providers(row, scans), fsync=False, snapshot_every=32)


# ------------------------------------------------------- the fault injections

#: Kinds whose absence from a delta the maintained index must notice.
#: (``StoreIndex.INDEXED_KINDS`` also holds region/capture/subject and the
#: adopted pool fits; these four are the ones every arm commits often.)
_INJECTABLE = ("tile", "evidence", "pose", "window")


def injection_arms() -> list[tuple[str, dict]]:
    """Three deliberate breakages the comparison MUST catch.

    THE TWO DELTA INJECTIONS FIRE ON THE FIRST COMMIT THAT CARRIES AN
    INDEXED KEY, not at a fixed ordinal (fixed W3, 2026-08-23). They used
    to fire at commit 40 of the banded arm, whose delta carries no
    indexed key at all — so nothing was withheld, the maintained index
    matched the built one for the honest reason, and both injections were
    reported NOT CAUGHT. That was invisible for as long as the driver
    could not run at all (it died at the first commit of the first arm on
    ``SessionPlane.store``); reviving it surfaced it. A harness that
    cannot fail proves nothing, and a fixed ordinal is a fixture the
    fixtures moved out from under.
    """
    dropped: list[bool] = []
    stalled: list[bool] = []

    def drop_one(ordinal: int, delta: tuple) -> tuple | None:
        """Withhold ONE indexed key from the first commit that has one."""
        if dropped:
            return None
        indexed = [key for key in delta if key.kind in _INJECTABLE]
        if not indexed:
            return None
        dropped.append(True)
        return tuple(key for key in delta if key is not indexed[0])

    def stall(ordinal: int, delta: tuple) -> tuple | None:
        """Withhold a whole delta — the plane is never told that commit."""
        if stalled or not any(key.kind in _INJECTABLE for key in delta):
            return None
        stalled.append(True)
        return ()

    return [
        ("a dropped changed key", {"sabotage": drop_one}),
        ("a stalled generation", {"sabotage": stall}),
        ("a stale frontier memo", {"stale_memo": True}),
    ]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="index-equiv-") as raw:
        work = Path(raw)
        built = arms(work)

        ledger = Ledger()
        undo = install(ledger)
        try:
            for index, (name, row, scans) in enumerate(built):
                started, before = time.perf_counter(), ledger.commits
                run_decode(work, str(index), row, scans)
                print(f"  {name}: {ledger.commits - before} commits, "
                      f"{time.perf_counter() - started:.1f} s", flush=True)
        finally:
            undo()
        print(ledger.report())

        failures: list[str] = []
        if ledger.divergences:
            print("\nDIVERGENCE — a maintained view is NOT the built one:")
            for line in ledger.divergences[:40]:
                print(f"  {line}")
            failures.append("the maintained views diverged")
        if not ledger.commits or not ledger.expansions:
            failures.append("NOTHING COMPARED — the harness proved nothing")
        if ledger.maintained < ledger.commits:
            failures.append(
                f"only {ledger.maintained} of {ledger.commits} commits "
                "carried a delta: the incremental path is not being taken")

        # -- fault injection: each of these MUST be caught ----------------
        # The BANDED arm carries them: it is the only fixture where scans
        # fail (baselines land, retries mint, windows retire), so a key's
        # attempts genuinely grow AFTER its first expansion — which is the
        # only condition under which a stale memo can be wrong at all.
        print("\nfault injection (each MUST be caught):")
        name, row, scans = built[2]
        for label, kwargs in injection_arms():
            broken = Ledger()
            undo = install(broken, **kwargs)
            try:
                run_decode(work, f"fi-{label.replace(' ', '-')}", row, scans)
            except Exception as exc:            # a loud break is a CATCH
                broken.divergences.append(f"raised {type(exc).__name__}: {exc}")
            finally:
                undo()
            caught = bool(broken.divergences)
            print(f"  {label}: {'CAUGHT' if caught else 'NOT CAUGHT'} "
                  f"({broken.commits} commits / {broken.expansions} "
                  f"expansions compared, {len(broken.divergences)} "
                  f"divergences, first: "
                  f"{broken.divergences[0][:90] if caught else 'n/a'})")
            if not broken.commits or not broken.expansions:
                failures.append(
                    f"injection '{label}' compared nothing at all")
            elif not caught:
                failures.append(f"injection '{label}' was not caught")

    if failures:
        print("\nFAILED:")
        for line in failures:
            print(f"  {line}")
        return 1
    print("\nEQUAL on every compared commit and every compared expansion; "
          "every injected fault caught.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
