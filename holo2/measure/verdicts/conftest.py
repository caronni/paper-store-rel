"""THE VERDICTS — eight verdicts over FIVE shared decodes, plus a ninth.

(THE NINTH is ``test_operator_path.py`` (C5, 2026-08-22, RULINGS G6),
and it is deliberately not in the count above: it drives ``cli.main``
with an ARGV where every other verdict drives ``cli.decode`` with a row
already built, so its decode IS its subject and cannot be shared. It
owns it, in its own file, and this one holds nothing for it.)

(The header said "six over four" until W3, and was already one behind
its own body: run union and the correlated-evidence verdict landed at
H4-LANES stage 2 without it — counted from the files, once. Now run
union is GONE — merged into run streaming, 2026-08-17 ruling, wall-time
complaint: its own decode cost ~75s of the ~131s pre-subdivision gate.
Six decodes become five; the eight verdict files are untouched, since
``test_correlated_evidence`` still exists, just reads a different run
for its positive half. Counted from the files, once more.)

Ruled 2026-08-16 (H4-W2-PLAN, "THE TEST LANDSCAPE"). The design law is
the user's: *"many execute the same things — run once, check multiple
things after the run."* So this file holds the DECODES and nothing else,
one session-scoped fixture each, and the check files beside it read what
those runs left behind (five over the channel, banded and partial runs;
run streaming joined with the streaming-ingestion build, alongside
``test_streaming`` — and, since the merge, carries the correlated-
evidence law's positive half too, on its own second scan of sheet 0;
run subdivision joined at W3 with ``test_subdivision``):

* **run channel — the channel-arm page** (``run_channel``): parameter
  for parameter what the now-deleted differential harness (measure
  cleanup, 2026-08-16) used as its own default arm — the measured e032
  channel (anisotropic pitch, a small rotation) plus a 2%
  hard cell error rate. It carries three verdicts: ``test_roundtrip``
  (byte-exact), ``test_v1_parity`` (pose-for-pose against v1's
  ``place_survey``) and ``test_durability`` (crash-cut re-earn, and a
  resume with no pixels). **The one run on the FINEST-ONLY reading set**
  (H4-LANES stage 2) — the fixture states why, and it is what keeps the
  pre-lanes configuration pinned rather than merely still spelled.
* **run banded — the banded page** (``run_banded``): the same page under
  a 16% cell error band over its right quarter, which kills the t = 13
  word code in those columns and leaves the seeded search's own
  admission intact. ``test_seeded`` is its verdict, and
  ``test_correlated_evidence`` reads it too — on the default reading set
  it is a single capture decoded through TWO rungs, which is what the
  no-cross-view-summing law is about.
* **run partial — the two-sheet partial volume** (``run_partial``):
  sheet 0 of a two-sheet volume on the platen, so the close CANNOT reach
  K. ``test_honesty`` is its verdict.
* **run streaming — the streamed volume, sheet 0 scanned TWICE**
  (``run_streaming``): BOTH sheets declared, decoded by a two-worker
  pool, so its captures arrive DURING the run (H4 streaming ingestion).
  ``test_streaming`` is its verdict, and it is the one decode here that
  is not serial — see the fixture for why its pins need a second slot
  to exist in. Sheet 0 is ALSO the multi-scan shape (the run-union
  merge, 2026-08-17): declared a third time under a narrow band of
  ``BAND_ERROR_RATE`` cell error (same print seed, a different sensor
  draw), which is what makes a payload UNION legal and reachable here.
  ``test_correlated_evidence`` reads it for both halves of the law now
  — sheet 1's tiles are observed once (no union possible), sheet 0's
  are observed twice (a union is legal, though the print-correlated
  band is never expected to be rescued by one).
* **run subdivision — the faded page** (``run_subdivision``): an 11x11
  field under the resurrected coverage ramp at 0.85, where the ink is
  legible at 100 cells and not at 200. One window's whole ladder runs
  out in the faded band and its corners place, which is the only shape
  in this file where the scheduling set GROWS. ``test_subdivision`` is
  its verdict, and the negative half of that verdict is read off run
  banded — a page that needs no subdivision and gets none.

CADENCE (ruled): the full verdicts at WAVE END exactly, run BY ITSELF —

    env/bin/python -m pytest holo2/measure/verdicts -q

Package hand-off and pre-merge run only ``test_roundtrip.py``. The verdicts
are never mixed into a ``testpaths`` invocation: pytest imports ``conftest``
by basename, so collecting this file beside ``holo2/tests/conftest.py``
would shadow it. Nothing under ``testpaths`` collects this directory, so
the conftest here is safe on its own terms and dangerous only in company.

EVERY DECODE IS SERIAL BUT ONE. Three of the older verdicts are exact
pins — the pose set against v1, the route split, the durable window
population — and under continuous admission a parallel run commits in
COMPLETION order (R9), so those numbers would be a race rather than a
fact. The serial lane is the reference lane by ruling, and these are
small pages. RUN STREAMING is the exception and states its own case at
the fixture: what it pins is an order PROPERTY — placement on one
capture does not wait for the next acquisition — which is not a number
and cannot be observed with a single slot.

Nothing here stages anything. The partial session of run partial is
produced by PHYSICS — a volume whose K does not fit on one sheet — and
the band of run banded is a channel fact the M281's known horizontal
banding produces.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pytest

# ``_fixtures`` is a sibling of this file (the carved subset of the former
# ``_real_fixtures.py`` — measure cleanup, 2026-08-16), and pytest's
# prepend import mode already puts THIS directory on ``sys.path`` (the
# verdicts have no ``__init__.py``, so its basedir is the insertion
# point) — no path surgery needed to reach it.
from _fixtures import (CHANNEL_ROTATION_DEG, CHANNEL_SCALE_YX, SPINE_FORMAT,
                       SUBDIVISION_FORMAT, SUBDIVISION_RAMP,
                       PageFixture, Render, VolumeFixture,
                       build_page, build_volume, record_placement_routes,
                       record_window_passes, render)

from holo2 import cli  # noqa: E402
from holo2.cli import real_providers, real_source  # noqa: E402
from holo2.engine.recipe import RECIPE_V1, RECIPE_V1_FINEST  # noqa: E402

#: A 1200-dpi capture of a 600-dpi print — the whole measure tree's footing.
PX_PER_DOT = 2

#: MEASURED originally by ``test_real_e2e`` (deleted with the measure
#: cleanup; the claim is held here directly, exercised by run partial's
#: render — history has the driver). An exactly two-valued raster is not
#: a capture, and the carried median detector has a measured cliff on one.
CLEAN_DITHER = 1.0

#: Small enough that a run frames several times, so a crash staged by
#: cutting one frame leaves a tail that is a fraction of the run.
CADENCE = 32

#: SERIAL, and by ruling (see the module docstring).
WORKERS = 1

#: RUN STREAMING's exception, argued at the fixture: two workers is the
#: smallest pool in which "placement does not wait for the next
#: acquisition" is expressible at all, and run streaming's pins are order
#: properties rather than schedule integers.
STREAM_WORKERS = 2

# --- run channel: the channel arm -------------------------------------------
# The differential's default lane, verbatim (originally
# ``_differential_kit.E2E_SPECS["channel"]``; the kit was deleted with the
# measure cleanup — the claim is held here directly now, this arm being
# its only surviving user — history has the driver): c2-r0700 on 8x8
# tiles, the measured e032 anisotropic pitch and rotation, sensor noise,
# and a 2% hard cell error rate inside the measured c2 2-5% envelope.
# Reused rather than re-invented, because ``test_v1_parity`` compares
# against v1 on exactly this arm.
#: The channel arm's page, as ONE v2 identity (C4, RULINGS G5,
#: 2026-08-22; it was ``CHANNEL_CODING`` + ``CHANNEL_TILES_YX``, and the
#: pair could name a sheet only with a media inversion in between).  The
#: printed twin of this coding is the ``L:c2-r0700@…`` line of e029/e032;
#: this is its SYNTHETIC 8x8 sibling, and the two seed apart on purpose.
CHANNEL_FORMAT = "c2-k-r0700@8x8"
CHANNEL_NOISE = 2.0
CHANNEL_CELL_ERROR_RATE = 0.02

# --- run banded (and run streaming's sheet-0 rescan): the band --------------
# MEASURED (carried from ``test_real_e2e``'s chain arm, deleted with the
# measure cleanup — the claim is held here directly, exercised by run
# banded; history has the driver): a Stage-A word is
# the seeded search's gate is a weighted mismatch over every site of the
# window against bars of 0.20/0.24 and survives to ~20%. A 16% band over
# the right quarter therefore kills the WORD in those columns and leaves
# the seeded admission intact — which is the whole regime the pull
# model's ladder exists for.
BAND_ERROR_RATE = 0.16
BAND_COLUMNS = (0.75, 1.0)
BAND_WARP: dict[str, Any] = dict(rotation_deg=0.3, pitch_scale=1.003,
                                 noise_sigma=2.0)

# MEASURED (2026-08-17, the run-union merge): run streaming's sheet 0
# reuses ``BAND_ERROR_RATE``/``BAND_WARP`` but NOT the full
# ``BAND_COLUMNS`` quarter — that band, driven with ``--complete`` (the
# quarter's own retry/search ladder has to be walked out, not just the
# LDPC), added 60-100s to the decode, more than the ~75s the merge is
# supposed to remove. This narrower band still fails a handful of
# sheet 0's tiles on one capture's own LDPC (not only the address word)
# and keeps the correlated-evidence law's positive half non-vacuous —
# measured 5-6 union attempts, 1 tile left permanently uncertified
# (print-correlated, never rescued) — for ~20-25s. The exact tile and
# attempt counts are NOT pinned: R9 says a two-worker pool commits in
# completion order, so they are schedule artifacts, the same discipline
# every other run-streaming count already carries.
STREAM_UNION_BAND = (0.95, 1.0)


# ------------------------------------------------------------- the harness

Scans = tuple[tuple[Path, float], ...]


def request_for(state_dir: Path, scans: Scans, *, workers: int = WORKERS,
                complete: bool = False) -> cli.DecodeRequest:
    """One decode request. ``scans=()`` is the pixel-free resume."""
    return cli.DecodeRequest(
        scans=scans, workers=workers, diag_port=0, state_dir=state_dir,
        output=state_dir.parent / "recovered.bin", complete=complete)


def decode(state_dir: Path, row: Any, scans: Scans, *, complete: bool = False,
           workers: int = WORKERS,
           recipe: Any = RECIPE_V1,
           providers: Sequence[Any] | None = None) -> tuple[Any, Any]:
    """Drive the REAL composition root: providers, source, close and all.

    The provider roster is composed from the REQUEST since streaming
    ingestion (H4): reading a declared scan is work, and the ingest
    provider closes over the scan list the way the payload provider
    closes over the printed row.

    ``recipe`` is the RUN'S POLICY and rides the lineage identity, so a
    run and every later re-open of its state must name the same one
    (:func:`open_state`, and the ``recipe`` each run carries). It exists
    as a parameter since H4-LANES stage 2: the default reads the whole
    footing ladder and run channel declares the finest-only reading,
    which is the configuration the pre-lanes receiver had.
    """
    request = request_for(state_dir, scans, workers=workers,
                          complete=complete)
    return cli.decode(
        request, row,
        real_providers(row, request.scans) if providers is None else providers,
        recipe=recipe, fsync=False, snapshot_every=CADENCE)


def open_state(state_dir: Path, row: Any, scans: Scans,
               recipe: Any = RECIPE_V1) -> Any:
    """Re-open a finished state to read what it holds. Commits nothing.

    ``recipe`` must be the one the state was DECODED under: the entries
    are the lineage identity, so re-opening a finest-only state under the
    cascade recipe is a whole-value mismatch the store refuses (which is
    the point of the reading set being data).
    """
    request = request_for(state_dir, scans)
    return cli.open_receiver(
        request, row, recipe=recipe,
        providers=real_providers(row, request.scans),
        source=real_source(row, recipe), fsync=False)


def copy_state(source: Path, target: Path) -> Path:
    """A COPY is what every durability check operates on (never run channel's own)."""
    shutil.copytree(source, target)
    return target


# ------------------------------------------------------------- the decodes

@dataclass(frozen=True)
class PageRun:
    """One finished single-sheet decode, and how to re-open it."""

    page: PageFixture
    capture: Render
    state_dir: Path
    outcome: Any
    observer: Any
    #: Pose key -> which half of the pull job's ladder proposed it
    #: (``WindowJob.route_taken``). Provenance, not a durable fact.
    routes: dict[Any, str]
    #: Every PASS this run made, in order: the window, the stage it was
    #: offered, the stage it SPENT, the route it reached an address by
    #: and its outcome. Also provenance — run banded's verdict needs to
    #: say what was tried, not only what landed.
    passes: tuple[dict, ...] = ()
    #: THE POLICY this state was built under (H4-LANES stage 2). It is
    #: the lineage identity, so every re-open names it.
    recipe: Any = RECIPE_V1
    # No ``rescans`` field: the one PageRun that ever carried a second
    # acquisition was run union, which is GONE (merged into run
    # streaming, 2026-08-17 — its rescan lives on ``StreamRun`` now,
    # where the multi-scan shape actually is). Every remaining PageRun
    # is single-scan; re-add here only if a future PageRun needs one.

    @property
    def scans(self) -> Scans:
        return ((self.capture.path, self.capture.dpi),)

    def open(self) -> Any:
        return open_state(self.state_dir, self.page.row, self.scans,
                          self.recipe)


@dataclass(frozen=True)
class VolumeRun:
    """One finished MULTI-sheet decode with only sheet 0 on the platen."""

    volume: VolumeFixture
    sheets: tuple[Render, ...]
    state_dir: Path
    outcome: Any
    observer: Any

    @property
    def scans(self) -> Scans:
        return ((self.sheets[0].path, self.sheets[0].dpi),)

    def open(self) -> Any:
        return open_state(self.state_dir, self.volume.row, self.scans)


@pytest.fixture(scope="session")
def run_channel(tmp_path_factory: pytest.TempPathFactory) -> PageRun:
    """RUN CHANNEL — the channel arm, driven to completion over its whole domain.

    ``--complete`` is not decoration: without it the run stops the moment
    the volume closes, and the set of windows that ever fired would be a
    schedule artifact rather than a comparable population — which is
    exactly what ``test_v1_parity`` compares.

    **THE FINEST-ONLY CONFIGURATION** (H4-LANES stage 2), and the reason
    is not shyness about the lanes: this is the run ``test_v1_parity``
    compares pose for pose against v1's ``place_survey``, and v1's
    placement in that comparison reads ONE lane. A cascade run has a
    second pose on the same window extent, a second lattice seed per
    region and a second reading of the same ink — all lawful, none of it
    comparable to a single-lane reference. So run channel carries the
    reading the receiver had before this wave, which makes it two things
    at once: the parity reference, and the standing pin that the
    finest-only configuration still decodes exactly what it decoded
    (byte-exact volume, pose-for-pose against v1, the same window
    population). The cascade's own closure is run banded/partial/
    streaming's.
    """
    work = tmp_path_factory.mktemp("verdicts-run-channel")
    page = build_page(CHANNEL_FORMAT)
    capture = render(page.dots, work / "channel.png", px_per_dot=PX_PER_DOT,
                     cell_dots=page.cell_dots,
                     rotation_deg=CHANNEL_ROTATION_DEG,
                     pitch_scale=CHANNEL_SCALE_YX, noise_sigma=CHANNEL_NOISE,
                     cell_error_rate=CHANNEL_CELL_ERROR_RATE)
    with pytest.MonkeyPatch.context() as patch:
        routes = record_placement_routes(patch)
        outcome, observer = decode(work / "state", page.row,
                                   ((capture.path, capture.dpi),),
                                   complete=True, recipe=RECIPE_V1_FINEST)
    return PageRun(page, capture, work / "state", outcome, observer,
                   dict(routes), recipe=RECIPE_V1_FINEST)


@pytest.fixture(scope="session")
def run_banded(tmp_path_factory: pytest.TempPathFactory) -> PageRun:
    """RUN BANDED — the banded page: the word code dies in the right quarter.

    ON THE DEFAULT READING SET since H4-LANES stage 2, so it is also the
    wave's SINGLE-CAPTURE cascade: c2 at 1200 dpi lays a two-rung ladder,
    both rungs place, and every count this run's verdict pins re-timed
    once for that reason (``test_seeded``'s own notes say which). It
    carries the correlated-evidence guard's first half —
    ``test_correlated_evidence`` — because one capture read through two
    lanes is exactly the shape the "LLRs never sum across two views of
    one physical capture" law is about.
    """
    work = tmp_path_factory.mktemp("verdicts-run-banded")
    page = build_page(CHANNEL_FORMAT)
    capture = render(page.dots, work / "banded.png", px_per_dot=PX_PER_DOT,
                     cell_dots=page.cell_dots,
                     cell_error_rate=BAND_ERROR_RATE,
                     cell_error_band=BAND_COLUMNS, **BAND_WARP)
    with pytest.MonkeyPatch.context() as patch:
        routes = record_placement_routes(patch)
        passes = record_window_passes(patch)
        outcome, observer = decode(work / "state", page.row,
                                   ((capture.path, capture.dpi),),
                                   complete=True)
    return PageRun(page, capture, work / "state", outcome, observer,
                   dict(routes), tuple(passes))


@dataclass(frozen=True)
class StreamRun:
    """RUN STREAMING's finished decode, plus what its commits were ABOUT.

    A journal entry is a batch id and nothing else — the content is
    regenerated by re-running the fold — so a verdict that asks WHERE a
    particular fact landed needs the id-to-content map the run itself
    saw. It is captured by wrapping the session's own commit call
    (test-side instrumentation, nothing production reads), and the
    ORDER is then read off the journal, which is the durable record.
    """

    volume: VolumeFixture
    sheets: tuple[Render, ...]
    state_dir: Path
    outcome: Any
    observer: Any
    #: batch id -> the kinds that commit changed, in this run's order.
    commit_kinds: dict[str, frozenset[str]]
    #: A FURTHER acquisition of sheet 0, declared THIRD (the run-union
    #: merge, 2026-08-17): the correlated-evidence law's positive half
    #: needs two DISTINCT captures reaching one work key, and this is
    #: where that shape now lives — ``PageRun.rescans``'s old job,
    #: transplanted to the run that is actually multi-scan. Empty on
    #: every OTHER StreamRun this file never builds; kept a tuple for
    #: the same reason ``PageRun`` did (a rescan is itself a ``Render``,
    #: not a bare scan tuple, so its truth pose stays reachable).
    rescans: tuple[Render, ...] = ()

    @property
    def scans(self) -> Scans:
        return (tuple((sheet.path, sheet.dpi) for sheet in self.sheets)
               + tuple((rescan.path, rescan.dpi) for rescan in self.rescans))

    def open(self) -> Any:
        return open_state(self.state_dir, self.volume.row, self.scans)


@pytest.fixture(scope="session")
def run_partial(tmp_path_factory: pytest.TempPathFactory) -> VolumeRun:
    """RUN PARTIAL — sheet 0 of a two-sheet volume: solved as far as pixels allow.

    The partial state is produced by PHYSICS, not by staging: at K/T = 0.8
    the source symbol count exceeds one sheet's tiles, so no single sheet
    can close this volume however well it decodes.
    """
    work = tmp_path_factory.mktemp("verdicts-run-partial")
    volume = build_volume(SPINE_FORMAT, 2)
    sheets = tuple(
        render(dots, work / f"sheet{index}.png", px_per_dot=PX_PER_DOT,
               cell_dots=volume.cell_dots, noise_sigma=CLEAN_DITHER)
        for index, dots in enumerate(volume.dots))
    outcome, observer = decode(work / "state", volume.row,
                               ((sheets[0].path, sheets[0].dpi),))
    return VolumeRun(volume, sheets, work / "state", outcome, observer)


@pytest.fixture(scope="session")
def run_subdivision(tmp_path_factory: pytest.TempPathFactory) -> PageRun:
    """RUN SUBDIVISION — the faded page: legible at 100 cells, not at 200.

    The only decode in this file in which the scheduling set GROWS. The
    coverage ramp (``_fixtures.SUBDIVISION_RAMP``, resurrected from the
    deleted differential kit and re-measured for this question) fades the
    ink across x, and in the band where it fades one 200-cell window runs
    its whole ladder out — ring consult, both word stages, the wide
    consult, and since W4 its own COLD PAIR — while three of its four
    100-cell corners place. That is the ruled subdivision shape exactly:
    a page whose edge window cannot place whole but whose corners can.

    ITS COUNTS ARE MOVABLE AT COLD'S LANDING, and W4 moved one of them
    (declared in advance by the wave's readiness ruling 6). Subdivision
    sits BEHIND the correlation now, as it does in v1 — so this run's
    parent sweeps a page before its corners exist, and a page it can
    correlate is a page it might place WHOLE, which would leave the arm
    with no subject. Measured at the landing: the parent's live-cold
    refuses, the parent/child counts are unchanged at 1 and 3, and the
    one cold pass is now pinned as a census of its own
    (``test_subdivision.EXPECTED_PARENT_COLD_PASSES``). A future change
    that places the parent whole re-declares all three together, or the
    arm needs a harder ramp.

    ``--complete`` for the same reason run channel takes it: without it
    the run stops the moment the volume closes, and subdivision is the
    LAST thing a window does — a schedule that ended early would decide
    whether this run has a subject at all.

    ON THE DEFAULT READING SET, and serial like every verdict but run
    streaming: the counts this run's verdict pins are exact.
    """
    work = tmp_path_factory.mktemp("verdicts-run-subdivision")
    page = build_page(SUBDIVISION_FORMAT)
    capture = render(page.dots, work / "faded.png", px_per_dot=PX_PER_DOT,
                     cell_dots=page.cell_dots,
                     rotation_deg=CHANNEL_ROTATION_DEG,
                     noise_sigma=CHANNEL_NOISE, ink_ramp=SUBDIVISION_RAMP)
    with pytest.MonkeyPatch.context() as patch:
        passes = record_window_passes(patch)
        outcome, observer = decode(work / "state", page.row,
                                   ((capture.path, capture.dpi),),
                                   complete=True)
    return PageRun(page, capture, work / "state", outcome, observer, {},
                   tuple(passes))


@pytest.fixture(scope="session")
def run_streaming(tmp_path_factory: pytest.TempPathFactory) -> StreamRun:
    """RUN STREAMING — the two-sheet volume, STREAMED, sheet 0 scanned TWICE.

    Run partial's volume with the second sheet on the platen too, which
    makes it the first decode in this file whose captures arrive DURING
    the run (H4 streaming ingestion): the session opens holding nothing,
    one ingest fire per declared scan reads them, and each capture record
    attaches on the committing thread.

    **The one POOLED decode here, and deliberately.** Every other verdict
    is serial by ruling, because its pins are exact integers and
    continuous admission commits in completion order. This one pins an
    ORDER PROPERTY — that placement on capture 1 does not wait for
    capture 2 — and that property is about concurrency: with one worker
    there is no second slot for placement to run in, and the cheapest
    ready work after scan 1 lands is scan 2. Two workers is the smallest
    pool that can express it, and what makes the property robust rather
    than a race is the size of the gap (a survey against a window pass),
    which the verdict measures rather than assumes. THREE captures now
    (below), and none of it moves: the pool still has no reason to wait
    on an acquisition it does not need, so the chain merely runs one
    link longer.

    **SHEET 0 IS DECLARED A THIRD TIME** — the run-union merge,
    2026-08-17 (H4-LANES ruling 6, user: "the correlated-evidence law's
    verdict-level pin gets back before multi-footing evidence is
    reachable"; run union's own decode was ~75s of the ~131s
    pre-subdivision gate, and the wall complaint is what closed it). The
    rescan carries ``STREAM_UNION_BAND``'s cell error — same print seed
    as sheet 0's first scan, a different sensor draw
    (``_fixtures.render``'s print/noise split) — which is run union's
    old shape transplanted onto sheet 0 rather than kept as a second
    fixture: a handful of sheet 0's tiles fail their own LDPC on one
    capture and stay open, so once the rescan lands the ppc they sit at
    has been reached by two DISTINCT acquisitions and a payload UNION is
    legal (``test_correlated_evidence``'s positive half).

    ``--complete`` is MEASURED necessary for that, contrary to the
    first-drafted plan: a bare run closes through sheet 1 and sheet 0's
    clean majority alone (well past K/T before the corrupted tiles are
    ever needed) and stops there, so the union tier is never even
    consulted — zero attempts. With ``--complete`` the run keeps going
    after verification and does consult it: measured 5-6 union attempts,
    minting nothing (the band is print-correlated, so the sum is lawful
    but never a rescue — the same finding run union always recorded).
    Neither the attempt count nor which tile stays open is pinned
    anywhere below: R9 says a two-worker pool commits in completion
    order, so counts this far into the exhaustion tail are schedule
    artifacts, same as every other run-streaming number past the
    ordering claims above.
    """
    work = tmp_path_factory.mktemp("verdicts-run-streaming")
    volume = build_volume(SPINE_FORMAT, 2)
    sheet0 = render(volume.dots[0], work / "sheet0.png", px_per_dot=PX_PER_DOT,
                    cell_dots=volume.cell_dots,
                    cell_error_rate=BAND_ERROR_RATE,
                    cell_error_band=STREAM_UNION_BAND,
                    print_seed=20260809, noise_seed=20260809, **BAND_WARP)
    sheet1 = render(volume.dots[1], work / "sheet1.png", px_per_dot=PX_PER_DOT,
                    cell_dots=volume.cell_dots, noise_sigma=CLEAN_DITHER)
    sheet0_rescan = render(
        volume.dots[0], work / "sheet0-rescan.png", px_per_dot=PX_PER_DOT,
        cell_dots=volume.cell_dots, cell_error_rate=BAND_ERROR_RATE,
        cell_error_band=STREAM_UNION_BAND, print_seed=20260809,
        noise_seed=20260818, **BAND_WARP)
    with pytest.MonkeyPatch.context() as patch:
        kinds = record_commit_kinds(patch)
        outcome, observer = decode(
            work / "state", volume.row,
            ((sheet0.path, sheet0.dpi), (sheet1.path, sheet1.dpi),
             (sheet0_rescan.path, sheet0_rescan.dpi)),
            workers=STREAM_WORKERS, complete=True)
    return StreamRun(volume, (sheet0, sheet1), work / "state", outcome,
                     observer, dict(kinds), rescans=(sheet0_rescan,))


def record_commit_kinds(patch: pytest.MonkeyPatch) -> dict[str, frozenset[str]]:
    """Wrap the session's commit call: batch id -> the kinds it changed.

    The journal records ORDER and identity, never content (``core.journal``
    — the content is regenerated by re-running the fold), so a verdict
    that wants to say "this commit is where capture 2 landed" has to have
    watched the run. Test-side only: production reads none of this, and
    the ordering every assertion is made against is still the durable
    journal's.
    """
    from holo2.engine.session import SessionContext

    seen: dict[str, frozenset[str]] = {}
    original = SessionContext.apply

    def apply(self: Any, batch: Any) -> Any:
        result = original(self, batch)
        seen[result.batch_id] = frozenset(
            key.kind for key in result.changed_keys)
        return result

    patch.setattr(SessionContext, "apply", apply)
    return seen
