"""Ingest: one acquisition becomes durable capture facts.

The physical half of what ``engine/runtime.py`` used to call session
assembly, moved here in R2 because every step of it is this package's
business: open and authenticate the file, derive the footing ladder,
survey the payload regions, and write the facts (L1) — one
``CaptureRecord`` per authenticated acquisition, one ``RegionRecord`` per
surveyed region with its support mask in the blob sidecar.

What ingest does NOT do is derive a cell lattice or a window: a lattice
needs the printed row's cell size, and windows are geometry. Those live in
``solve`` and read the :class:`IngestedCapture` this module returns.

It runs no algorithms of its own beyond the carried survey and the one
scalar below (:func:`platen_backing`), reads no clock, and draws no
random numbers.

STREAMING INGESTION (H4, 2026-08-17)
-------------------------------------
Ingest used to be session ASSEMBLY: ``open_plane`` opened, surveyed and
committed every declared capture before the orchestrator's first fire, so
a nine-platen session spent minutes surveying before any placement began.
It is WORK now — one spendable attempt per declared scan — and this module
is split along the only line that matters for that:

* :func:`capture_facts` DERIVES, and commits nothing. It is the whole of
  the old body minus the wall: open, authenticate, ladder, survey, and
  the writes plus staged blobs those facts imply.
* :class:`IngestWorker` is that derivation as an ordinary worker (P3/P4).
  It holds no session state, proposes like any other fire, and the raster
  it opened dies with the fire — the plane gets its own handle by
  ATTACH-BY-REOPEN on the committing thread (``solve.plane``), which is
  what keeps "workers propose, the main thread owns state" intact.
* :func:`ingest_capture` is the two together, for a caller that is not a
  session: derive, then commit through a given authority.

Choices where DESIGN is silent (for adjudication, carried from the module
this split):

- **Ingest WAS session assembly, not a scheduled worker.** That choice
  was made when it was idempotent, content-addressed and unconditional,
  and it named its own expiry: "H3 may promote it when captures start
  arriving mid-session." Streaming ingestion (H4) is that promotion, and
  the reason is not mid-session arrival but the SERIAL COST of the
  survey — the one part of a capture that is neither cheap nor already
  durable.
- **The survey runs once per capture, not once per footing.** §5.3 keys a
  ``RegionRecord`` by (capture, region) and §1 lists the survey products
  as capture facts; every footing of a capture shares one region set and
  one capture-cell lattice, because a printed cell has one physical size.
- **The fire's writes are UNCONDITIONAL facts, and the wall filters
  them.** A re-derivation of bytes already ingested proposes exactly the
  records that stand (F-08 makes that a law, not a hope), and
  ``SessionContext.changed`` drops them, so a redundant ingest commits no
  facts. What it cannot avoid is its own spend row — which is the point:
  the ledger is what makes the NEXT run skip the survey entirely.
- **The platen backing is a CAPTURE FACT, recorded here** (2026-08-17).
  It is one median over the raster's four borders, and placement needs it
  to name a prepared plane (``solve.prepared`` hashes it into the file's
  name). Computed per session from the raster it was durable nowhere, so
  a resume without the file could not even NAME the prepared planes it
  already had on disk. The arithmetic is ``solve.pose_fit.platen_backing``
  transcribed exactly — capture may not import ``solve``, and the
  duplication is pinned bit-equal rather than trusted
  (``tests/solve/test_pose_fit.py`` — the side of the test DAG that may
  name both packages).
- **The SUB-NATIVE RUNGS are ingest products too** (H4-LANES stage 1,
  2026-08-17). The fire already holds the authenticated pixels and
  already pays one full pass over them, so it is where the ladder's
  coarse rungs get derived — native to decimated, always, never
  level-from-level (ruling 2), through the carried
  ``scale_space`` arm whose bytes are oracle-pinned. The whole sub-native
  ladder sums to about a third of the native pixel count, the decimation
  is large-array numpy that releases the GIL, and under streaming
  ingestion it overlaps placement on the captures that already landed.
  :func:`footing_raster_for` is the ONE door: it opens the rung if it
  stands and derives it if it does not, so the fire and a later session
  that needs a rung the fire never wrote run the same code.
  ``directory`` is handed IN rather than derived, exactly as
  ``solve.prepared`` is handed one — the caller knows where this
  lineage's derived pixels live, and a fire that is handed none writes
  none (the unit lane and the qualification oracles).
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from ..core import (AttemptIdentity, CaptureSha, CommitBatch, CommitEngine,
                    FootingId, ProgressSink, ResourceKey, SolveView,
                    StagedBlob, WorkResult, Write, stage_array)
from .footing_raster import (FootingRaster, footing_plan, footing_transform,
                             open_footing_raster, write_footing_raster)
from .records import (CaptureRecord, FootingSpec, RegionRecord, capture_key)
from .scale_space import auto_ppc_levels
from .scan import Raster, open_capture
from .survey import RegionCandidate, region_candidates, survey_raster

#: The task family and its single route (M1: the route is part of the
#: descriptor). One acquisition has exactly one way of being read.
FAMILY_INGEST = "ingest"
ROUTE_SURVEY = "survey"

#: The one outcome an ingest attempt can report. It says what the fire
#: DID, not what the wall did with it: a re-derivation of standing facts
#: also surveys, and the no-op filter is the commit layer's business
#: (L10), not a second outcome name here.
OUTCOME_INGESTED = "ingested"


@dataclass(frozen=True)
class IngestedCapture:
    """One acquisition's facts, with its pixels attached or ABSENT (B9).

    ``raster`` is ``None`` for a capture assembled from durable records
    alone (``catalog.catalog_capture``): footings, regions, lattices,
    poses and evidence are all durable, so the only question a detached
    capture cannot answer is a question about pixels — and M12's
    decline-with-wake on ``attachment_key`` is how a worker asks that
    question without dying.

    ``footings`` is READ OFF the record since B9's ``FootingView``
    collapse. It used to be a second copy of ``record.footings`` that
    only an ingest could build; now the lanes carry their own capture, so
    a footing has one home and there is no view to rebuild.
    """

    raster: Raster | None
    record: CaptureRecord
    candidates: tuple[RegionCandidate, ...]

    @property
    def source_sha256(self) -> CaptureSha:
        return self.record.source_sha256

    @property
    def footings(self) -> tuple[FootingSpec, ...]:
        return self.record.footings


@dataclass(frozen=True)
class CaptureFacts:
    """What one acquisition IS — derived, staged, and not yet committed.

    The value :func:`capture_facts` hands back and :class:`IngestWorker`
    proposes: the capture as the plane will see it, plus the durable form
    of it (``writes``) and the bulk values those writes cite (``blobs``,
    STAGED — the commit authority materialises them for accepted
    proposals only, so a discarded proposal leaves no mask behind).
    """

    ingested: IngestedCapture
    writes: tuple[Write, ...]
    blobs: tuple[StagedBlob, ...]


def footing_id_for(capture_sha256: CaptureSha, ppc: Fraction) -> FootingId:
    """§5.1: ``f"{capture_short}:{ppc_num}/{ppc_den}"``."""
    return FootingId(
        f"{capture_sha256[:12]}:{ppc.numerator}/{ppc.denominator}")


def platen_backing(raster: Raster, border_px: int = 32) -> float:
    """Median native luma at the four platen borders, mmap-safe.

    ``solve.pose_fit.platen_backing``'s body, transcribed CHARACTER FOR
    CHARACTER because the layering forbids the import and the value is a
    digest input: ``solve.prepared`` names a prepared plane partly by this
    float, so a drift of one ULP would rename every file on disk and cost
    a full rebuild — and, worse, would make the recorded value disagree
    with what a session that still holds the raster would compute.

    It lives HERE because the producer already holds the pixels: an
    ingest opens the raster once, and the one scalar every placement fire
    needs from the WHOLE raster (rather than from a region's bbox) is
    cheaper to record than to re-derive. The pin that keeps the two
    honest is ``tests/solve/test_pose_fit.py``'s bit-equality check
    against ``pose_fit``'s own answer, on five awkward shapes.
    """
    height, width = raster.shape
    border = max(1, min(int(border_px), height, width))
    strips = (
        raster.crop_luma(0, border, 0, width).ravel(),
        raster.crop_luma(height - border, height, 0, width).ravel(),
        raster.crop_luma(0, height, 0, border).ravel(),
        raster.crop_luma(0, height, width - border, width).ravel(),
    )
    return float(np.median(np.concatenate(strips)))


def footing_raster_for(raster: Raster | None, ppc: Fraction,
                       native_ppc: Fraction, *, capture_sha256: CaptureSha,
                       shape_px: tuple[int, int], dtype: str,
                       directory: Path) -> FootingRaster | None:
    """One SUB-NATIVE rung's pixels: opened if they stand, else derived.

    The one door onto a coarse rung, and the reason it is one: a rung is
    a pure function of the authenticated bytes and an exact rational
    scale, so "already on disk" and "derive it now" must produce the same
    file under the same name or the ladder is not a ladder. Both halves
    therefore share ``footing_plan``'s single expression for that name.

    ``raster=None`` is the REUSE-ONLY call: a session holding no pixels
    can open the rungs an earlier run derived (everything the name is a
    function of is durable — ``CaptureRecord``'s sha, shape and dtype)
    and can never build one. ``None`` comes back when neither is possible,
    which is a statement about THIS session and not about the rung.

    It lives in ``ingest`` rather than in ``footing_raster`` for one
    reason: it is the only path that reads the authenticated raster's own
    pixels, and §6.8 entitles this module to do that.
    """
    plan = footing_plan(capture_sha256, footing_transform(ppc, native_ppc),
                        shape_px, dtype, directory=directory)
    standing = open_footing_raster(plan, ppc)
    if standing is not None or raster is None:
        return standing
    height, width = raster.shape
    write_footing_raster(raster.crop_native(0, height, 0, width),
                         footing_transform(ppc, native_ppc), plan)
    return open_footing_raster(plan, ppc)


def derive_footing_rasters(raster: Raster, ppcs: tuple[Fraction, ...], *,
                           directory: Path) -> tuple[Fraction, ...]:
    """Every sub-native rung of one capture's ladder, onto disk.

    The ingest fire's own half of the lanes. The finest rung is native by
    construction (``auto_ppc_levels`` ends AT native sampling and never
    upsamples), and native is the authenticated scan itself — nobody
    copies it — so this walks the ladder minus its last entry. Rungs
    already standing cost one ``stat`` each, which is what makes a
    re-ingest of bytes this lineage has seen cheap on the pixel side too.
    """
    native_ppc = max(ppcs)
    derived: list[Fraction] = []
    for ppc in ppcs:
        if ppc >= native_ppc:
            continue
        footing_raster_for(
            raster, ppc, native_ppc, capture_sha256=CaptureSha(
                raster.source_sha256), shape_px=raster.shape,
            dtype=str(raster.native_dtype), directory=directory)
        derived.append(ppc)
    return tuple(derived)


def capture_facts(path: Path, dpi: float, pitch_in: Fraction, *,
                  directory: Path | None = None) -> CaptureFacts:
    """Authenticate, derive footings, survey — and COMMIT NOTHING.

    The derivation, alone. It reads a file, hashes it, lays the footing
    ladder over the declared dpi and runs the carried survey; everything
    it learns comes back as values, so the caller decides whether that
    becomes a commit (:func:`ingest_capture`) or a proposal
    (:class:`IngestWorker`).

    The source is re-authenticated before the facts are handed over
    (``verify_source_unchanged``), exactly where it always was: at the
    retention barrier, which for a proposing worker is the moment its
    facts stop being about pixels it is still holding — so the sub-native
    rungs are derived BEFORE it, while the pixels are still this fire's.

    ``directory`` is where this lineage's derived pixels live
    (``<state-dir>.prepared``); handed one, the fire emits the ladder's
    sub-native rungs as a by-product. They are DERIVED SCRIBBLES and not
    facts: they are content-named, so a proposal the wall later refuses
    leaves nothing that could be mistaken for state, and deleting them
    costs one rebuild. A caller that names no directory — the unit lane,
    the qualification oracles — emits none and is otherwise identical.
    """
    raster = open_capture(path, dpi)
    record = CaptureRecord(
        # What was AUTHENTICATED, not what the caller passed: the raster
        # carries the dpi the source id was built with.
        source_sha256=raster.source_sha256,
        dpi_true=float(raster.dpi),
        shape_px=raster.shape,
        dtype=raster.source.dtype,
        channels=raster.source.channels,
        platen_backing=platen_backing(raster),
        footings=tuple(
            FootingSpec(footing_id_for(raster.source_sha256, ppc), ppc,
                        raster.source_sha256)
            for ppc in auto_ppc_levels(dpi, pitch_in)),
    )
    # THE DECLARED PITCH IS EVIDENCE, NOT A GUESS (C3b, RULINGS H1(b),
    # 2026-08-22).  The same ``pitch_in`` that just laid the footing
    # ladder is handed to the survey, which adds it to its blind
    # candidate set: this stage has been TOLD the answer, and a survey
    # that voted ``None`` because the row's pitch was no registered
    # class would leave ``solve.plans.region_view`` carrying every
    # region of that capture as unschedulable.  A declared c1..c4 row
    # changes nothing at all — ``candidate_pitches`` returns the blind
    # tuple itself.
    survey = survey_raster(raster, declared_pitch_in=pitch_in)
    candidates = region_candidates(raster.source_sha256, survey)
    if directory is not None:
        derive_footing_rasters(
            raster, tuple(footing.ppc for footing in record.footings),
            directory=directory)
    raster.verify_source_unchanged()

    writes = [Write(capture_key(record.source_sha256), record)]
    blobs = []
    for candidate in candidates:
        # STAGED, not appended: a batch the commit authority refuses must
        # leave no mask behind in the sidecar (the house pattern since
        # R1/M6 — ``WorkResult.blobs``).
        mask = stage_array(candidate.support.cells)
        blobs.append(mask)
        # OR-12: the support grid's own geometry travels WITH the mask, so
        # durable state alone places the region's lattice — and since the
        # identity law those same numbers ARE the region's name, so the
        # record and its key cannot drift apart (the family validates it).
        region = RegionRecord(
            capture_sha256=candidate.capture_sha256,
            support_mask_ref=mask.ref,
            pitch_in_vote=candidate.pitch_in_vote,
            support_origin_px=(int(candidate.support.origin_yx[0]),
                               int(candidate.support.origin_yx[1])),
            support_step_px=int(candidate.support.step_px),
            support_extent_px=(int(candidate.support.extent_px[0]),
                               int(candidate.support.extent_px[1])))
        writes.append(Write(region.resource_key(), region))
    return CaptureFacts(IngestedCapture(raster, record, tuple(candidates)),
                        tuple(writes), tuple(blobs))


def ingest_capture(engine: CommitEngine, path: Path, dpi: float,
                   pitch_in: Fraction, *,
                   directory: Path | None = None) -> IngestedCapture:
    """One capture: authenticate, derive footings, survey, commit.

    Derivation plus wall, for a caller holding a commit authority rather
    than a scheduler — the qualification oracles and the unit lane, and
    the shape the streaming provider composes out of the same two halves.
    ``directory`` relays :func:`capture_facts`' own: a caller that names
    none gets the native rung and nothing else.
    """
    facts = capture_facts(path, dpi, pitch_in, directory=directory)
    # The filter exists to avoid the EMPTY COMMIT, not the empty write:
    # ``Store.apply`` bumps ``commit_seq`` for any batch it accepts, so a
    # re-opened state that writes nothing must not commit at all (L10).
    store = engine.store
    pending = tuple(write for write in facts.writes
                    if store.get(write.key) != write.record)
    if pending:
        engine.apply(CommitBatch(writes=pending, blobs=facts.blobs))
    return facts.ingested


class IngestWorker:
    """ONE declared scan, read: open + survey, proposed like any fire.

    P3/P4 with nothing special about it, which is the whole design
    (streaming-ingestion point 3). It holds no session state, reads no
    durable fact, takes no lease and touches no plane: it opens the file
    the descriptor names, derives the capture facts, and hands back
    writes and staged blobs for the main thread to commit. The raster
    dies with the fire —
    the plane opens its OWN handle when it absorbs the capture record,
    which is what keeps the memory model ("workers propose, the main
    thread owns state") untouched by an ingest that now runs beside
    placement.

    THE EMPTY READ-SET IS THE POINT. This attempt's inputs are the
    DECLARED scan — a path and a DPI — which are session inputs, not
    durable facts, so there is no key whose version could make its answer
    stale and nothing for §7 to re-derive. What the empty read-set buys
    is exactly the semantics streaming ingestion needs: the identity of
    the attempt is constant, so the spend row the ledger holds under this
    scan's work id says "this lineage has already read these bytes", and
    a resumed session's spend-once test refuses the re-survey outright
    rather than paying for it and dropping the result at the wall.

    RAM is bounded by the DERIVATION CHAIN, not by a gate: the provider
    mints scan N+1's descriptor only once scan N's capture record stands
    (``solve.ingest``), so at most one survey — the ~8x-raster transient —
    is ever in flight, whatever the pool width. The sub-native rungs the
    fire also emits (H4-LANES stage 1) do not move that bound: each is
    streamed chunk by chunk into its own file, so the decimation's peak
    is one chunk, not one rung.

    ``directory`` is where this lineage's derived pixels live, handed in
    at binding time by the provider (``solve.ingest``) because only
    ``solve`` knows a state directory. ``None`` is the fire that emits no
    rungs, which is what a caller with no session composes.
    """

    task_class = FAMILY_INGEST

    def __init__(self, path: Path, dpi: float, pitch_in: Fraction,
                 directory: Path | None = None) -> None:
        self.path = Path(path)
        self.dpi = float(dpi)
        #: The printed cell's PHYSICAL pitch, in inches — the whole of
        #: what the footing ladder takes from the format row (RULINGS
        #: G4, C3, 2026-08-22; was ``cell_dots``).  Stored AS GIVEN, with
        #: no coercion: ``scale_space._fraction`` is the one conversion
        #: rule on this path, and it is the one ``capture_facts`` and
        #: ``ingest_capture`` reach too.  ``Fraction(pitch_in)`` here
        #: would have been a SECOND rule — it takes a float's exact
        #: binary expansion where ``_fraction`` deliberately takes the
        #: decimal the caller wrote — so an off-type caller would get two
        #: different footing ladders, hence two different ``footing_id``
        #: strings and two evidence namespaces, for one declared sheet
        #: (review fix, C3, 2026-08-22).
        self.pitch_in = pitch_in
        self.directory = None if directory is None else Path(directory)

    def read_keys(self, view: SolveView) -> tuple[ResourceKey, ...]:
        """Nothing durable: see the class docstring's empty-read-set note."""
        return ()

    def run(self, view: SolveView, identity: AttemptIdentity,
            progress: ProgressSink) -> WorkResult:
        # Two quanta, at the two boundaries this fire actually has: the
        # arm, and the survey that produced the regions. The carried
        # calls between them are single numpy passes with no interior to
        # report from, and §10.3's contract is that a fire reports, not
        # that it reports often.
        progress.emit(1, "arm")
        facts = capture_facts(self.path, self.dpi, self.pitch_in,
                              directory=self.directory)
        progress.emit(1, f"regions:{len(facts.ingested.candidates)}")
        return WorkResult(outcome=OUTCOME_INGESTED, retire=True,
                          writes=facts.writes, blobs=facts.blobs)


__all__ = ["CaptureFacts", "FAMILY_INGEST", "IngestWorker", "IngestedCapture",
           "OUTCOME_INGESTED", "ROUTE_SURVEY", "capture_facts",
           "derive_footing_rasters", "footing_id_for", "footing_raster_for",
           "ingest_capture", "platen_backing"]
