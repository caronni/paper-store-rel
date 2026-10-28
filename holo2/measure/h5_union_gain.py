#!/usr/bin/env python
"""H5 P3 (a) THE UNION-GAIN DIRECTION and (b) CROSS-DPI UNIONS — BY PATH.

    env/bin/python holo2/measure/h5_union_gain.py [--arms A,B] [--quiet]

NOT A TEST and not collectable as one: no ``test_`` name, no pytest
fixtures, a ``__main__`` entry point, and it lives outside ``testpaths``.
Same standing as ``or5_or7_census.py`` — it runs REAL decodes and counts
what they did.

BOTH ARMS ARE DIRECTIONS, NEVER BARS (H5-PLAN P3, and the ruling is the
plan's own words: "recorded as a direction, never a bar"). Single
synthetic sheets are existence and regression evidence; nothing here
promotes a rung, predicts recoverability, or becomes a gate.

(a) THE UNION-GAIN DIRECTION
----------------------------
E023b measured a multiview union at 769 certified tiles against two
single-view states at 757 and 752 — the union WON. The F1 o F6 law says
why that is not automatic: equal-weight combining LOSES to best-single
under a GLOBAL detector, because print errors are correlated across
scans of one sheet, and it WINS only after the ctx detector de-correlates
the context bias. H5 P1 put that detector in holo2's assembly path, so
the pre-registered expectation is that this reproduces e023b's DIRECTION.

**PRE-REGISTERED, and stated before the arm was ever run**: union >=
best-single, expected strictly greater. If the union LOSES, that is a
FINDING AGAINST THE PRE-REGISTRATION — it is reported as one, the arm
STOPS for a lead ruling, and nothing about the fixture is re-tuned to
make it pass.

THE FIXTURE IS PRE-REGISTERED TOO, by a criterion about DIFFICULTY and
not about outcome, chosen before the three-decode comparison was run:
the channel is ``_h5_context_channel``'s authored PSF (whose whole
argument is the ctx arm's non-vacuity, arm (d)'s subject), and its ramp
and sensor noise were set to the coarsest pair on a probe grid at which
ONE capture leaves a PARTIAL page — measured 40 of 64 tiles at
``INK_RAMP`` 0.65 / sensor 12, against 64 of 64 at ramp 0.55 and a total
placement collapse at sensor 22. A fixture that certified everything on
one capture would leave the union nothing to win, and a fixture whose
failures were wholly frozen in the ink would leave it nothing it COULD
win; this one is neither, by construction and not by search.

WHY BOTH HALVES OF THE ERROR ARE PRESENT is the sibling module's
docstring. Briefly: the ink (dots, ramp, PSF) is IDENTICAL in both
acquisitions, and only the POSE and the Gaussian sensor draw differ —
``_fixtures.render``'s own print/noise split, which is the multi-scan
law's whole subject.

TWO GAINS ARE COUNTED SEPARATELY, because they are different mechanisms
and pooling them would overstate the union:

* **MULTIVIEW gain** — a tile the joint state certified through an
  ordinary ``scan`` route on the second capture. Nothing was summed; the
  other acquisition simply read that tile better. This is real yield and
  it is what "declare both scans" buys even with no union path at all.
* **UNION gain** — a tile whose certificate was minted by the ``union``
  route (``MintRef.route``), i.e. by the cross-capture LLR sum itself,
  each footing's component corrected by its own region's adopted fit
  BEFORE the sum (L2 by construction).

(b) CROSS-DPI UNIONS — the first measured mixed-resolution union
-----------------------------------------------------------------
The same sheet, acquired at TWO scanner resolutions: 1200 dpi and 2400
dpi. Their footing ladders are different lengths and yet MEET, because a
footing's identity is its ppc — pixels per printed cell — and not its
dpi (``capture.scale_space.auto_ppc_levels``). On ``c3`` the 1200-dpi
capture lays ppc 2, 3, 6 and the 2400-dpi capture lays ppc 2, 4, 6, 12,
so ppc 2 and ppc 6 are reached by TWO DISTINCT captures and a union is
legal there — at ppc 6 between a NATIVE rung of one capture and a
DECIMATED rung of the other. That correspondence is what the lanes made
expressible, and this arm is the first time it is measured.

Arm (b) changes exactly ONE variable against arm (a): the second
acquisition's resolution. Same sheet, same ink, same two poses, same
sensor seeds. The A-only decode is literally the same decode and is run
ONCE and read by both arms (the verdicts' own run-once-check-many law).

WHAT NEITHER ARM CLAIMS. These are small synthetic pages under one
authored channel and one seed pair. They bound the DIRECTION and name
the mechanism behind it; they are not a population, not a rate, and not
a promotion of anything.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

# Self-locating, like ``./confetti.py`` and ``or5_or7_census.py``.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE, _HERE / "verdicts", _ROOT / "src",
              _ROOT / "holo2" / "src"):
    sys.path.insert(0, str(_path))

from _fixtures import build_page                              # noqa: E402
from _h5_context_channel import (BAND_COLUMNS,                # noqa: E402
                                 BAND_ERROR_RATE, NOISE_SEED_A,
                                 NOISE_SEED_B, PSF_SIGMA_CELLS,
                                 channel_line, context_capture)

from holo2 import cli                                         # noqa: E402
from holo2.capture import catalog_captures                    # noqa: E402
from holo2.cli import real_providers, real_source             # noqa: E402
from holo2.engine.recipe import RECIPE_V1                     # noqa: E402
from holo2.solve.calibration import (FAMILY_CALIBRATION,      # noqa: E402
                                     OUTCOME_ADOPTED)
from holo2.solve.payload import (FAMILY_PAYLOAD,              # noqa: E402
                                 ROUTE_UNION, ppc_tag)
from holo2.solve.tilemap import StoreIndex                    # noqa: E402

#: The page, as ONE v2 format id (C4, RULINGS G5, 2026-08-22; it was
#: ``CODING`` + ``TILES_YX``).  ``c3-k-r0550@8x8`` is ``_fixtures``' own
#: spine page: 64 tiles clears the L9 metadata floor (48 distinct
#: certified counters) with 16 to spare, and c3 lays a three-rung ppc
#: ladder at 1200 dpi, which is what arm (b)'s correspondence needs on
#: the coarse side.
FORMAT = "c3-k-r0550@8x8"

#: The two acquisitions' footings. 2 px/dot is the whole measure tree's
#: 1200-dpi footing; 4 px/dot is arm (b)'s one changed variable.
PX_PER_DOT_FINE = 2
PX_PER_DOT_FINER = 4

#: ONE POSE for both acquisitions — literally ``conftest.run_streaming``'s
#: shape ("same print seed, a different sensor draw"), and the
#: CONSERVATIVE choice for a union: a re-placed sheet would give the
#: second acquisition a different sampling phase and therefore MORE
#: de-correlation than this has. Measured reason for not re-placing:
#: placement on this page is knife-edge in the pose near its cliff
#: (rotation -0.05 and +0.05 place; -0.10 and +0.21 commit no pose at
#: all), so a pose difference would confound the union question with a
#: placement lottery. The measured e032 warp, as ``_fixtures`` declares
#: it.
POSE: dict[str, Any] = dict(rotation_deg=-0.13, pitch_scale=(1.0115, 1.0060))

#: Snapshot cadence, from ``verdicts/conftest.py``. Irrelevant to every
#: count here.
CADENCE = 32

ARMS = ("union", "cross-dpi")


# ------------------------------------------------------------- one decode

class Decoded:
    """One finished decode and everything this driver reads off it."""

    def __init__(self, name: str, outcome: Any, wall: float,
                 store: Any) -> None:
        self.name = name
        self.status = outcome.status
        self.certified = int(outcome.certified)
        self.wall = wall
        index = StoreIndex.build(store)
        #: work key -> the route its certificate was minted by.
        self.minted: dict[Any, str] = {
            key: record.minting.route
            for key, record in index.tiles.items()
            if record.minting is not None}
        #: Every work key this state holds committed evidence on, and the
        #: subset still OPEN — the union's reachable population. A tile
        #: whose window never placed carries no evidence at all, so it is
        #: not something a second acquisition could ever sum into.
        self.evidenced = set(index.evidence_by_tile)
        self.open_with_evidence = self.evidenced - set(self.minted)
        self.mint_routes = Counter(self.minted.values())
        self.fits = Counter(row.outcome for row in store.ledger.entries()
                            if row.worker_id.family == FAMILY_CALIBRATION)
        self.union_spends = Counter(
            str(row.worker_id.scope.profile)
            for row in store.ledger.entries()
            if row.worker_id.family == FAMILY_PAYLOAD
            and row.route == ROUTE_UNION)
        #: capture sha -> (its declared dpi, its ppc ladder), off the
        #: CAPTURE RECORDS — the durable answer, and the only one a
        #: terminal session has (a closed run ingests nothing, §5.5).
        self.ladder: dict[str, tuple[float, tuple[str, ...]]] = {}
        for ingested in catalog_captures(store):
            self.ladder[str(ingested.record.source_sha256)[:12]] = (
                float(ingested.record.dpi_true),
                tuple(ppc_tag(footing.ppc)
                      for footing in ingested.record.footings))

    @property
    def adopted_fits(self) -> int:
        return int(self.fits.get(OUTCOME_ADOPTED, 0))

    def line(self) -> str:
        return (f"    {self.name:<16} {self.status:<9} certified "
                f"{self.certified:>4}  {self.wall:6.1f} s  "
                f"mint {dict(self.mint_routes)}  fits {dict(self.fits)}")


def decode(work: Path, name: str, row: Any,
           scans: tuple[tuple[Path, float], ...]) -> Decoded:
    """One SERIAL, ``--complete`` decode of a declared scan list.

    SERIAL by the verdicts' own ruling: a pooled run commits in
    COMPLETION order (R9), so certified counts from a pool would be a
    race rather than a fact, and the whole arm is a comparison of counts.
    ``--complete`` for the reason ``conftest.run_streaming`` measured:
    without it a run stops the moment the fountain closes and the union
    tier is never consulted at all.
    """
    state = work / f"state-{name}"
    request = cli.DecodeRequest(
        scans=scans, workers=1, diag_port=0, state_dir=state,
        output=work / f"recovered-{name}.bin", complete=True)
    started = time.perf_counter()
    outcome, _observer = cli.decode(
        request, row, real_providers(row, request.scans),
        recipe=RECIPE_V1, fsync=False, snapshot_every=CADENCE)
    wall = time.perf_counter() - started
    with cli.open_receiver(
            request, row, recipe=RECIPE_V1,
            providers=real_providers(row, request.scans),
            source=real_source(row, RECIPE_V1), fsync=False) as session:
        return Decoded(name, outcome, wall, session.store)


# ------------------------------------------------------------- the report

def report_pair(label: str, single_a: Decoded, single_b: Decoded,
                joint: Decoded, tiles: int, failures: list[str]) -> None:
    """One arm's three decodes, as a DIRECTION with its mechanism split."""
    print(f"\n  {label}")
    for decoded in (single_a, single_b, joint):
        print(decoded.line())
    best = max(single_a.certified, single_b.certified)
    delta = joint.certified - best
    print(f"    best-single {best} / {tiles}   joint state "
          f"{joint.certified} / {tiles}   DELTA {delta:+d}")

    # THE MECHANISM SPLIT. A union-route mint is a cross-capture SUM; a
    # scan-route mint in the joint state that neither single state
    # certified is the other acquisition simply reading better. Pooling
    # them would credit the union with yield it did not produce.
    singles = set(single_a.minted) | set(single_b.minted)
    gained = set(joint.minted) - singles
    union_minted = {key for key, route in joint.minted.items()
                    if route == ROUTE_UNION}
    print(f"    joint mints by route: {dict(joint.mint_routes)}")
    print(f"    tiles the joint state certified and NEITHER single did: "
          f"{len(gained)}"
          f"{f' (of which union-route {len(gained & union_minted)})' if gained else ''}"
          f"{f', by route {dict(Counter(joint.minted[key] for key in gained))}' if gained else ''}")
    print(f"    union-route certificates in the joint state: "
          f"{len(union_minted)} (a union WON the race for these; it is "
          f"not by itself a gain)")
    print(f"    union attempts spent, by ppc: {dict(joint.union_spends)}")

    # THE UNION'S REACHABLE POPULATION. A tile whose window never placed
    # carries no evidence, so no acquisition count can ever sum it: the
    # honest denominator for a union claim is tiles that HAVE evidence
    # and are still open, not tiles that are open.
    print(f"    evidenced tiles: A {len(single_a.evidenced)}, B "
          f"{len(single_b.evidenced)}, joint {len(joint.evidenced)} "
          f"(of {tiles})")
    print(f"    OPEN BUT EVIDENCED (the union's reachable population): "
          f"A {len(single_a.open_with_evidence)}, B "
          f"{len(single_b.open_with_evidence)}, joint "
          f"{len(joint.open_with_evidence)}")
    disagreement = ((set(single_a.minted) - set(single_b.minted))
                    | (set(single_b.minted) - set(single_a.minted)))
    print(f"    the two acquisitions DISAGREE about {len(disagreement)} "
          f"tile(s) — the de-correlated margin; everything else is "
          f"print-frozen")
    print(f"    ctx fits adopted: single {single_a.adopted_fits}/"
          f"{single_b.adopted_fits}, joint {joint.adopted_fits}")
    for sha, (dpi, ladder) in sorted(joint.ladder.items()):
        print(f"      joint capture {sha} @ {dpi:g} dpi, ppc ladder "
              f"{list(ladder)}")
    shared = set.intersection(*[set(rungs) for _dpi, rungs
                                in joint.ladder.values()]) \
        if len(joint.ladder) > 1 else set()
    print(f"      ppc reached by BOTH captures (where a union is legal): "
          f"{sorted(shared)}")

    # -- the pre-registration, adjudicated in the driver ------------------
    if delta > 0:
        print(f"    PRE-REGISTRATION REPRODUCED: the union state beats "
              f"best-single by {delta} tile(s), e023b's direction "
              f"(757/752 -> 769).")
    elif delta == 0:
        print("    PRE-REGISTRATION NOT REPRODUCED (tie): the joint state "
              "matched best-single. Not a loss; not the expected strict "
              "gain either.")
    else:
        failures.append(
            f"{label}: FINDING AGAINST THE PRE-REGISTRATION — the joint "
            f"state certified {joint.certified}, BELOW best-single {best} "
            f"({delta:+d}). The arm STOPS here for a lead ruling; nothing "
            f"is re-tuned.")
    if single_a.certified >= tiles and single_b.certified >= tiles:
        failures.append(
            f"{label}: VACUOUS — both single captures certified every tile, "
            f"so the union had no headroom to win and the direction is not "
            f"a measurement of anything.")
    if not joint.open_with_evidence and joint.certified < tiles:
        failures.append(
            f"{label}: VACUOUS BY STRUCTURE — every uncertified tile "
            f"carries NO evidence at all (its window never placed), so "
            f"there is nothing for any acquisition count to sum. A tie "
            f"here measures the fixture, not the union.")
    if not joint.union_spends:
        failures.append(
            f"{label}: no union descriptor was ever spent, so the union "
            f"path was not exercised at all.")
    if not joint.adopted_fits:
        failures.append(
            f"{label}: NO ctx FIT ADOPTED — the whole premise of this arm "
            f"(ctx de-correlates the context bias first) was never in "
            f"force, so the direction is vacuous.")


# ------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arms", default=",".join(ARMS),
                        help=f"comma-separated arms ({', '.join(ARMS)})")
    parser.add_argument("--quiet", action="store_true",
                        help="omit the per-decode listings")
    args = parser.parse_args(argv)
    names = tuple(n.strip() for n in args.arms.split(",") if n.strip())
    unknown = set(names) - set(ARMS)
    if unknown:
        parser.error(f"unknown arm(s): {', '.join(sorted(unknown))}")

    page = build_page(FORMAT)
    tiles = int(page.tiles_per_page)
    print("H5 P3 (a)/(b) — UNION GAIN, real decodes, SERIAL, --complete.")
    print(f"  page {FORMAT} = {tiles} tiles, k_total "
          f"{page.k_total}")
    print(f"  {channel_line(PSF_SIGMA_CELLS, page.cell_dots, band_rate=BAND_ERROR_RATE, band_columns=BAND_COLUMNS)}")
    print(f"  ONE pose for every acquisition ({POSE}); the acquisitions "
          f"differ ONLY in their sensor seed (A {NOISE_SEED_A}, B "
          f"{NOISE_SEED_B}) and, in arm (b), in resolution.")
    print("  PRE-REGISTERED DIRECTION (a): union >= best-single, expected "
          "strictly greater (e023b 757/752 -> 769).")

    band: dict[str, Any] = dict(cell_error_rate=BAND_ERROR_RATE,
                                cell_error_band=BAND_COLUMNS)
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="h5-union-") as raw:
        work = Path(raw)
        scan_a = context_capture(page, work, "A-1200",
                                 px_per_dot=PX_PER_DOT_FINE,
                                 noise_seed=NOISE_SEED_A, **POSE, **band)
        a_only = decode(work, "A-1200", page.row,
                        ((scan_a.path, scan_a.dpi),))
        if "union" in names:
            scan_b = context_capture(page, work, "B-1200",
                                     px_per_dot=PX_PER_DOT_FINE,
                                     noise_seed=NOISE_SEED_B, **POSE, **band)
            b_only = decode(work, "B-1200", page.row,
                            ((scan_b.path, scan_b.dpi),))
            joint = decode(work, "A+B-1200", page.row,
                           ((scan_a.path, scan_a.dpi),
                            (scan_b.path, scan_b.dpi)))
            report_pair("(a) UNION GAIN — one sheet, two 1200-dpi "
                        "acquisitions", a_only, b_only, joint, tiles,
                        failures)
        if "cross-dpi" in names:
            scan_c = context_capture(page, work, "B-2400",
                                     px_per_dot=PX_PER_DOT_FINER,
                                     noise_seed=NOISE_SEED_B, **POSE, **band)
            c_only = decode(work, "B-2400", page.row,
                            ((scan_c.path, scan_c.dpi),))
            crossed = decode(work, "A1200+B2400", page.row,
                             ((scan_a.path, scan_a.dpi),
                              (scan_c.path, scan_c.dpi)))
            report_pair("(b) CROSS-DPI UNION — the same sheet at 1200 and "
                        "2400 dpi", a_only, c_only, crossed, tiles,
                        failures)

    if failures:
        print("\nFAILED / FINDINGS:")
        for line in failures:
            print(f"  {line}")
        return 1
    print("\nCOMPLETE — every arm exercised its union path with a live "
          "ctx fit and headroom to move.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
