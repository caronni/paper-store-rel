"""The ORDINARY payload rows: `tiles.scan`, `tiles.union`, `tiles.retry`,
and `tiles.cond`, the conditioned label stream priced beside them.

Split out of ``tiles`` at the 1000-line seam (L1, 2026-09-21), along
the seam `place`/`place_sched` already uses: ``tiles`` keeps the format
law — how a cut is assembled, how a tile is decoded, what a certificate
is — and this module keeps the SCHEDULING of it: what wakes a row, when
it is eligible, what it costs and what job it prepares.  Nothing here
touches a codeword; everything here is a `PluginDescriptor` hook.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from fractions import Fraction

from .. import sched_trace
from ..data import (
    AttemptFact,
    Certificate,
    ColorEvidenceRow,
    JobResult,
    WindowEvidence,
)
from ..descriptor import (
    FactKey,
    Job,
    KEY_ATTEMPT,
    KEY_COLOR_ROW,
    KEY_EVIDENCE_FIT,
    KEY_EVIDENCE_READ,
    KEY_TILE,
    PluginDescriptor,
    RETIRE_CERTIFIED,
    Subject,
)
from ..format.identity import Family, FormatRow, StreamFact
from . import color_sites, tiles

STAGE_PAYLOAD: str = "payload"
#: Payload is the CHEAPEST recovery, under every placement rung: a
#: certificate deletes placement work outright.  Measured the other way
#: round on a nine-platen run -- 1,287 armed payload workers, 431
#: fires, ZERO tiles attempted, because placement never dries.
PAYLOAD_COST: int = 20
RUNG_COST: int = 2
PRICES: tuple[tuple[str, int], ...] = ((STAGE_PAYLOAD, PAYLOAD_COST),)
#: THE cmy RETRY, priced into the residue band (the owner's price
#: balance, 2026-10-18; measure/sched_trace/YIELD-OVER-CPU-2026-10-18.md
#: §2).  On the e044 cmy pages `tiles.retry` spent 20-25 % of the run's
#: CPU for 3-11 certificates -- its first fire minted at 300-600 cpu-s
#: per certificate, its later fires 2 at 2,500 and then nothing (M4), 6
#: at 264 (M3) -- while `tiles.local`'s
#: first fire minted at 1.2 cpu-s per certificate and `tiles.swim`'s at
#: 6.  So on cmy alone the retry waits for both: 241 is ONE ABOVE swim's
#: first fire (swim.SWIM_COST = 240, local's 220 below it), and
#: 241 + RUNG_COST x 4 = 249 -- the bound ASSUMES the five-level ladder
#: (rung index <= 4: decimate.auto_ppc_levels at 4800 dpi lays c3 at
#: 2/4/8/12/24, c4 at 2/4/8/16/32; a c5 pitch or a forced dpi above 4800
#: lays a sixth level and its index-5 retry, 251, would sit above
#: cold_live) -- stays under cold placement (place.STAGE_COST["cold_live"] = 250 at lane
#: depth 0), so a cmy retry never waits behind a cold search.  Both
#: inequalities are pinned from the literals in test_h3_plugins_tiles.
#: K, cmy7 and cmy8 keep the payload price: there the retry pays (cmy8's
#: re-fires after a refit, confetti's first fires at 13 cpu-s per
#: certificate).  `tiles.cond`, the productive conditioned decode on cmy,
#: keeps the scan's price on every family (`_cond_cost`).
STAGE_RETRY_CMY: str = "retry_cmy"
RETRY_CMY_COST: int = 241
RETRY_PRICES: tuple[tuple[str, int], ...] = (
    (STAGE_PAYLOAD, PAYLOAD_COST), (STAGE_RETRY_CMY, RETRY_CMY_COST))

PLUGIN_SCAN: str = "tiles.scan"
PLUGIN_UNION: str = "tiles.union"
PLUGIN_RETRY: str = "tiles.retry"
PLUGIN_COND: str = "tiles.cond"

def _uncertified_streams(store: object, page: int, ty: int,
                         tx: int) -> tuple[str, ...]:
    return tuple(
        stream.stream_id for stream in store.row.streams
        if not store.has_certificate((page, ty, tx, stream.stream_id)))


#: The trace's redundancy probe (sched_trace, DEFAULT OFF): the digest
#: is of the ACTUAL decode input -- the assembled cut's values and cell
#: map, the component signature, the stage and the pending streams --
#: and it is RECORDED, NEVER ACTED ON.  The job below is submitted
#: whatever the digest says; only the trace record carries
#: `redundant_input`.
def _note_cut(components: Sequence[tiles.TileCut], stage: str,
              pending: Sequence[str]) -> None:
    trace = sched_trace.TRACE
    if not trace.enabled:
        return
    bare: list[object] = [tiles.component_signature(components)]
    for cut in components:
        bare.append(cut.values)
        bare.append(cut.observed_flat)
    trace.note_input("tile_cut", (stage, tuple(pending), *bare),
                     bare_parts=tuple(bare))


#: ALREADY READ AT THIS GENERATION (2026-10-03, S9).  A scan's reads
#: are its tile cover AT BIRTH, and reads are fixed at birth: when a
#: re-fit of window W shrinks W's cover off tile T, T's scan keeps W's
#: evidence keys, and every later re-fit of W wakes it although T's cut
#: did not move (`_advance_tile_lanes` bumps the old cover once, on the
#: fit that left).  The job assembled the IDENTICAL cut at the same
#: generation, `_fold_attempt` refused the verdict -- pure waste, and
#: concurrent with the retry already on that cut.  So: when every
#: pending stream already holds a scan verdict (any outcome) at the
#: tile-lane's CURRENT generation, there is nothing to read -- the same
#: generation test `_retry_eligible` uses.  The stale subscription
#: stays: over-declaring costs a wake, and this is what that wake costs
#: now.  The generation is monotone within a run and AttemptFact is
#: never snapshotted, so a verdict from another run is never compared.
def _scanned_at(store: object, page: int, ty: int, tx: int,
                lane: tuple[str, int], pending: Sequence[str],
                generation: int) -> bool:
    for stream_id in pending:
        verdict = store.attempt_verdict(page, ty, tx, stream_id,
                                        tiles.STAGE_SCAN, lane)
        if verdict is None or verdict[1] != generation:
            return False
    return True


#: SCAN judges ONE capture by itself; the merged frontier is UNION's
#: input.  Passing the frontier here minted scan attempts over prior
#: captures' components and crashed the second same-lane K capture
#: (12-tiles-payload.md:397-399).
def prepare_scan(store: object, subject: Subject,
                 stage: str) -> Job | None:
    page, ty, tx, capture_id, level_index = subject
    pending = _uncertified_streams(store, page, ty, tx)
    if not pending:
        return None
    # The store stamps the cell, the plugin REPORTS the number it read:
    # every verdict this job emits says which generation of this tile's
    # cut it was decoded from, so a later rung can tell a live verdict
    # from a stale one.
    generation = store.tile_lane_generation(
        (page, ty, tx, capture_id, level_index))
    if _scanned_at(store, page, ty, tx, (capture_id, level_index), pending,
                   generation):
        return None
    cut = tiles.assemble_tile(store, page, ty, tx, capture_id, level_index)
    if cut is None:
        return None
    components = (cut,)
    row = store.row
    site_geometry = store.geometry
    _note_cut(components, tiles.STAGE_SCAN, pending)

    def job() -> JobResult:
        return tiles.attempt_many(row, site_geometry, components, pending,
                                  tiles.STAGE_SCAN, generation)

    return job


#: ALREADY READ AT THIS GENERATION, the summed cut's turn (review
#: 2026-10-17 D2, R2).  `_scanned_at`'s waste exactly, one footing up:
#: a union's reads are its covers' evidence keys AT BIRTH, a re-fit
#: that leaves the tile keeps waking it, and the job re-assembled and
#: re-decoded the IDENTICAL summed cut at the same generation -- beside
#: the union-origin retry already on that cut.  So: when every pending
#: stream already holds a union verdict (any outcome) at the footing's
#: CURRENT `union_generation`, there is nothing to read.  The footing
#: counter is bumped once per lane event at this footing and so is
#: monotone (`store.union_generation`), and AttemptFact is never
#: snapshotted: a verdict from another run is never compared.
def _unioned_at(store: object, page: int, ty: int, tx: int, ppc: Fraction,
                pending: Sequence[str], generation: int) -> bool:
    for stream_id in pending:
        verdict = store.attempt_verdict(page, ty, tx, stream_id,
                                        tiles.STAGE_UNION, ppc)
        if verdict is None or verdict[1] != generation:
            return False
    return True


def prepare_union(store: object, subject: Subject,
                  stage: str) -> Job | None:
    page, ty, tx, ppc = subject
    pending = _uncertified_streams(store, page, ty, tx)
    if not pending:
        return None
    generation = store.union_generation(page, ty, tx, ppc)
    # Before the cut is assembled: the skip and an unarmed union both
    # answer None, so the order changes no outcome, only the work.  A
    # union verdict comes from an armed cut, and a cover losing a lane
    # is a lane event that moves the footing, so an unarmed union holds
    # no current verdict, falls through and returns None at `arms_union`.
    if _unioned_at(store, page, ty, tx, ppc, pending, generation):
        return None
    components = tiles.assemble_union(store, page, ty, tx, ppc)
    if not tiles.arms_union(components):
        return None
    row = store.row
    site_geometry = store.geometry
    _note_cut(components, tiles.STAGE_UNION, pending)

    def job() -> JobResult:
        return tiles.attempt_many(row, site_geometry, components, pending,
                                  tiles.STAGE_UNION, generation)

    return job


#: The CURRENT generation of the cut a baseline-shaped subject names:
#: the exact lane's for a scan origin, the footing's for a union one.
def _origin_generation(store: object, subject: Subject) -> int:
    origin, page, ty, tx, _stream_id, lane, capture_id = subject
    if origin == tiles.STAGE_SCAN:
        return store.tile_lane_generation((page, ty, tx, capture_id, lane))
    return store.union_generation(page, ty, tx, lane)


#: The ordinary verdicts a baseline-shaped subject stands on.  A retry
#: re-runs the decoder on the same marginal, so it needs one that ran
#: and lost (`tiles.arms_retry`).  The conditioned attempt changes the
#: evidence itself -- a zero marginal can be decisive given the sibling
#: -- so a below-floor read is its baseline too, and its own attempt
#: floors the conditional LLRs (the 2026-10-12 implementation review,
#: F2).
RETRY_BASELINES: frozenset[str] = frozenset({tiles.OUTCOME_FAILED})
COND_BASELINES: frozenset[str] = frozenset({tiles.OUTCOME_FAILED,
                                            tiles.OUTCOME_BELOW_FLOOR})


#: The cut a baseline-shaped subject re-reads, at its current
#: generation, and only while its stream is uncertified and the
#: component-keyed ledger still holds a baseline in `outcomes` on
#: exactly these components -- `tiles.retry`'s and `tiles.cond`'s one
#: floor.
def _baseline_cut(store: object, subject: Subject,
                  outcomes: frozenset[str],
                  ) -> tuple[tuple[tiles.TileCut, ...], int] | None:
    origin, page, ty, tx, stream_id, lane, capture_id = subject
    if origin == tiles.STAGE_SCAN:
        cut = tiles.assemble_tile(store, page, ty, tx, capture_id, lane)
        components = () if cut is None else (cut,)
    else:
        components = tiles.assemble_union(store, page, ty, tx, lane)
        if not tiles.arms_union(components):
            return None
    if not components:
        return None
    if store.has_certificate((page, ty, tx, stream_id)):
        return None
    baseline = tiles.attempt_key(page, ty, tx, stream_id, origin, components)
    if store.attempt_outcome(baseline) not in outcomes:
        return None
    return components, _origin_generation(store, subject)


#: Retry is ordinary priced work.  v1 suppressed it on a terminal
#: pre-close and holo3's contract copied that (ruling 12-5); the v2 gate
#: law took it back -- work knows only "always", count_ready and
#: exhaustion belong to the close alone (SCHEDULE.md:10-12, 355-357).
def prepare_retry(store: object, subject: Subject,
                  stage: str) -> Job | None:
    _origin, _page, _ty, _tx, stream_id, _lane, _capture_id = subject
    baseline_cut = _baseline_cut(store, subject, RETRY_BASELINES)
    if baseline_cut is None:
        return None
    components, generation = baseline_cut
    row = store.row
    site_geometry = store.geometry
    _note_cut(components, tiles.STAGE_RETRY150, (stream_id,))

    def job() -> JobResult:
        return tiles.attempt_many(row, site_geometry, components,
                                  (stream_id,), tiles.STAGE_RETRY150,
                                  generation)

    return job


def _static_stage(name: str) -> Callable[[object, Subject], str | None]:
    def stage(store: object, subject: Subject) -> str | None:
        return name

    return stage


def _scan_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if isinstance(fact, WindowEvidence):
        return store.window_cover_tiles(fact.window_id)
    return store.color_row_cover_tiles(
        (fact.capture_id, fact.level_index, fact.page, fact.patch_ordinal))


def _scan_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    k_wids, color_keys = store.tile_cover(subject)
    keys: list[FactKey] = []
    for wid in k_wids:
        keys.append((KEY_EVIDENCE_FIT, wid))
        keys.append((KEY_EVIDENCE_READ, wid))
    for row_key in color_keys:
        keys.append((KEY_COLOR_ROW,) + row_key)
    return tuple(keys)


def _scan_eligible(store: object, subject: Subject) -> bool:
    return bool(_uncertified_streams(store, subject[0], subject[1],
                                     subject[2]))


def _scan_retire(store: object, subject: Subject) -> str | None:
    return None if _scan_eligible(store, subject) else RETIRE_CERTIFIED


def _scan_cost(store: object, subject: Subject, stage: str,
               attempts: int, last_cost: int) -> int:
    return PAYLOAD_COST + RUNG_COST * subject[4]


def _union_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    subjects: list[Subject] = []
    for page, ty, tx, capture_id, level_index in _scan_subjects(store,
                                                                fact):
        ppc = store.level(capture_id, level_index).ppc
        lanes = store.cover_lanes(page, ty, tx, ppc)
        if len({lane_capture for lane_capture, _index in lanes}) >= 2:
            subjects.append((page, ty, tx, ppc))
    return tuple(dict.fromkeys(subjects))


def _union_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    page, ty, tx, ppc = subject
    keys: list[FactKey] = []
    for capture_id, level_index in store.cover_lanes(page, ty, tx, ppc):
        keys.extend(_scan_reads(store,
                                (page, ty, tx, capture_id, level_index)))
    return tuple(keys)


def _union_cost(store: object, subject: Subject, stage: str,
                attempts: int, last_cost: int) -> int:
    return PAYLOAD_COST + RUNG_COST * store.union_rung_ordinal(subject[3])


def _retry_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if not fact.components:
        return ()
    certified = store.has_certificate(
        (fact.page, fact.ty, fact.tx, fact.stream_id))
    if not tiles.arms_retry(fact, certified):
        return ()
    return _baseline_subject(store, fact)


def _baseline_subject(store: object, fact: object) -> tuple[Subject, ...]:
    if fact.stage == tiles.STAGE_SCAN:
        capture_id, lane = fact.components[0]
    else:
        capture_id = None
        lane = store.level(*fact.components[0]).ppc
    return ((fact.stage, fact.page, fact.ty, fact.tx, fact.stream_id,
             lane, capture_id),)


#: The LANE this subject's baseline was read on, spelled the way
#: `tiles.attempt_lane` spells it: the exact lane for a scan origin, the
#: shared footing's ppc for a union one.
def _retry_at(subject: Subject) -> object:
    origin, _page, _ty, _tx, _stream_id, lane, capture_id = subject
    return (capture_id, lane) if origin == tiles.STAGE_SCAN else lane


#: ONE KEY: this tile-stream's own verdict at its own origin stage on
#: its own lane.  It used to be `_scan_reads(...)` verbatim -- literally
#: the chain head's read set at the same price -- so on every colour
#: re-fit scan and retry woke together and decoded the SAME cut
#: concurrently: 65 % of scan's re-fires decoded a cut a retry already
#: had (sheet H, 2026-09-17; 4,662 scan->retry and 4,297 retry->scan
#: same-cut repeats, 2,547 cpu-s).  Subscribed to the verdict instead,
#: a retry cannot exist before its baseline does.
def _retry_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    origin, page, ty, tx, stream_id, _lane, _capture_id = subject
    return ((KEY_ATTEMPT, page, ty, tx, stream_id, origin,
             _retry_at(subject)),)


#: A retry is due when the baseline it retries is BOTH failed and
#: CURRENT.  The generation test is what makes "at most once per
#: generation" structural: a verdict taken off a cut that has since
#: moved is not a baseline any more, and the scan that re-reads the
#: moved cut is what produces the next one (INV-G1).
def _baseline_current(store: object, subject: Subject,
                      outcomes: frozenset[str]) -> bool:
    origin, page, ty, tx, stream_id, _lane, _capture_id = subject
    if store.has_certificate((page, ty, tx, stream_id)):
        return False
    verdict = store.attempt_verdict(page, ty, tx, stream_id, origin,
                                    _retry_at(subject))
    if verdict is None or verdict[0] not in outcomes:
        return False
    return verdict[1] == _origin_generation(store, subject)


def _retry_eligible(store: object, subject: Subject) -> bool:
    return _baseline_current(store, subject, RETRY_BASELINES)


#: The MONOTONE half alone.  `retire` is consulted at every wake as well
#: as every pop, so it may never read the generation clause above: a
#: stale baseline comes back current the moment scan re-reads the lane,
#: while a certificate is terminal.
def _retry_retire(store: object, subject: Subject) -> str | None:
    _origin, page, ty, tx, stream_id, _lane, _capture_id = subject
    return (RETIRE_CERTIFIED
            if store.has_certificate((page, ty, tx, stream_id)) else None)


def _baseline_rung(store: object, subject: Subject) -> int:
    if subject[0] == tiles.STAGE_SCAN:
        return subject[5]
    return store.union_rung_ordinal(subject[5])


def _retry_stage(store: object, subject: Subject) -> str | None:
    return (STAGE_RETRY_CMY if store.row.family is Family.CMY
            else STAGE_PAYLOAD)


def _retry_cost(store: object, subject: Subject, stage: str,
                attempts: int, last_cost: int) -> int:
    base = (RETRY_CMY_COST if store.row.family is Family.CMY
            else PAYLOAD_COST)
    return base + RUNG_COST * _baseline_rung(store, subject)


#: The SCAN's price of the baseline's lane, on every family: on cmy the
#: conditioned decode is the productive one (75 and 131 certificates on
#: e044 at 2.6-5.5 cpu-s each), so it does not follow the retry up.
def _cond_cost(store: object, subject: Subject, stage: str,
               attempts: int, last_cost: int) -> int:
    return PAYLOAD_COST + RUNG_COST * _baseline_rung(store, subject)


#: THE SIBLING a label stream is decoded given: the row's other label
#: stream.  A toner stream -- cmy8's planes, K's and cmy7's one stream --
#: has none (`tiles.stream_llrs` refuses a sibling there), and that is
#: what keeps `tiles.cond` unborn outside a label family.
def _label_sibling(row: FormatRow, stream_id: str) -> StreamFact | None:
    labels = tuple(fact for fact in row.streams
                   if fact.label_index is not None)
    if stream_id not in {fact.stream_id for fact in labels}:
        return None
    others = tuple(fact for fact in labels if fact.stream_id != stream_id)
    return others[0] if len(others) == 1 else None


#: The baseline-shaped subjects of every cut this stream read without a
#: certificate (`COND_BASELINES`) at the cut's current generation: each
#: scan lane of every capture, each summed footing.  What a sibling
#: certificate births.
def _cond_baselines(store: object, page: int, ty: int, tx: int,
                    stream_id: str) -> tuple[Subject, ...]:
    subjects: list[Subject] = []
    footings: set[object] = set()
    for capture_id in sorted(store.captures()):
        for level in store.capture(capture_id).levels:
            footings.add(level.ppc)
            subjects.append((tiles.STAGE_SCAN, page, ty, tx, stream_id,
                             level.index, capture_id))
    subjects.extend((tiles.STAGE_UNION, page, ty, tx, stream_id, ppc, None)
                    for ppc in sorted(footings))
    return tuple(subject for subject in subjects
                 if _baseline_current(store, subject, COND_BASELINES))


#: BORN BY WHICHEVER LANDS SECOND (CMY-DESIGN R5): the stream's own
#: failed or below-floor ordinary verdict with its sibling already
#: certified -- the retry's subject -- or the sibling's certificate with
#: that verdict already standing and current.  So whichever stream
#: certifies first, by any stage, births the other's conditioned
#: attempt, and both orders come out of this one row.
def _cond_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if isinstance(fact, Certificate):
        sibling = _label_sibling(store.row, fact.stream_id)
        if sibling is None:
            return ()
        return _cond_baselines(store, fact.page, fact.ty, fact.tx,
                               sibling.stream_id)
    sibling = _label_sibling(store.row, fact.stream_id)
    if sibling is None or not store.has_certificate(
            (fact.page, fact.ty, fact.tx, sibling.stream_id)):
        return ()
    if (not fact.components or fact.stage not in tiles.ORDINARY_STAGES
            or fact.outcome not in COND_BASELINES
            or store.has_certificate(
                (fact.page, fact.ty, fact.tx, fact.stream_id))):
        return ()
    return _baseline_subject(store, fact)


#: The retry's one key, its own baseline verdict, and the sibling's
#: certificate key the certificate fold already emits (R5: direct, it
#: does not wait for the colour region's refit).
def _cond_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    _origin, page, ty, tx, stream_id, _lane, _capture_id = subject
    sibling = _label_sibling(store.row, stream_id)
    return _retry_reads(store, subject) + (
        (KEY_TILE, page, ty, tx, sibling.stream_id),)


#: The retry's test on `COND_BASELINES` -- the baseline failed or below
#: the floor, current, the stream uncertified -- with the sibling
#: certified, and AT MOST ONCE PER
#: GENERATION by construction: a conditioned verdict of any outcome
#: already standing at the cut's current generation means this cut has
#: been conditioned, as `_scanned_at` says for the scan.  A later
#: capture, a field re-solve or a region refit moves the generation,
#: the scan re-reads, and its new failed verdict is a wake of this row.
def _cond_eligible(store: object, subject: Subject) -> bool:
    _origin, page, ty, tx, stream_id, _lane, _capture_id = subject
    if not _baseline_current(store, subject, COND_BASELINES):
        return False
    sibling = _label_sibling(store.row, stream_id)
    if not store.has_certificate((page, ty, tx, sibling.stream_id)):
        return False
    conditioned = store.attempt_verdict(page, ty, tx, stream_id,
                                        tiles.STAGE_COND150,
                                        _retry_at(subject))
    return (conditioned is None
            or conditioned[1] != _origin_generation(store, subject))


#: The retry's cut, decoded given the sibling: its label bits re-encoded
#: from its certificate (`color_sites.certified_stream_bits`, sequential,
#: what the demap reads) in the job, off the engine thread.  A
#: certificate it mints is an ordinary one, and a conflicting one raises
#: as every certificate does.
def prepare_cond(store: object, subject: Subject,
                 stage: str) -> Job | None:
    _origin, page, ty, tx, stream_id, _lane, _capture_id = subject
    baseline_cut = _baseline_cut(store, subject, COND_BASELINES)
    if baseline_cut is None:
        return None
    components, generation = baseline_cut
    row = store.row
    sibling = _label_sibling(row, stream_id)
    certificate = store.certificate((page, ty, tx, sibling.stream_id))
    if certificate is None:
        return None
    counter = row.tile_counter(page, ty, tx)
    site_geometry = store.geometry
    _note_cut(components, tiles.STAGE_COND150, (stream_id,))

    def job() -> JobResult:
        bits = color_sites.certified_stream_bits(row, sibling, counter,
                                                 certificate)
        return tiles.attempt_many(row, site_geometry, components,
                                  (stream_id,), tiles.STAGE_COND150,
                                  generation, bits)

    return job


SCAN_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN_SCAN,
    subject_kind="tile",
    born_by=(WindowEvidence, ColorEvidenceRow),
    subjects_of=_scan_subjects,
    reads=_scan_reads,
    eligible=_scan_eligible,
    stage=_static_stage(STAGE_PAYLOAD),
    cost=_scan_cost,
    retire=_scan_retire,
    prepare=prepare_scan,
    produces=(AttemptFact, Certificate),
    prices=PRICES,
)

UNION_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN_UNION,
    subject_kind="tile",
    born_by=(WindowEvidence, ColorEvidenceRow),
    subjects_of=_union_subjects,
    reads=_union_reads,
    eligible=_scan_eligible,
    stage=_static_stage(STAGE_PAYLOAD),
    cost=_union_cost,
    retire=_scan_retire,
    prepare=prepare_union,
    produces=(AttemptFact, Certificate),
    prices=PRICES,
)

RETRY_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN_RETRY,
    subject_kind="tile",
    born_by=(AttemptFact,),
    subjects_of=_retry_subjects,
    reads=_retry_reads,
    eligible=_retry_eligible,
    stage=_retry_stage,
    cost=_retry_cost,
    retire=_retry_retire,
    prepare=prepare_retry,
    produces=(AttemptFact, Certificate),
    prices=RETRY_PRICES,
)

COND_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN_COND,
    subject_kind="tile",
    born_by=(AttemptFact, Certificate),
    subjects_of=_cond_subjects,
    reads=_cond_reads,
    eligible=_cond_eligible,
    stage=_static_stage(STAGE_PAYLOAD),
    cost=_cond_cost,
    retire=_retry_retire,
    prepare=prepare_cond,
    produces=(AttemptFact, Certificate),
    prices=PRICES,
)
