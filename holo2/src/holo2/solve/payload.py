"""The payload family: frozen evidence in, real certificates out.

RENAMED FROM ``payload_h3bis`` at H4 W6 (2026-08-18), the promise
WORKPLAN:335-338 made when the H3bis stand-in placer died: this is not
the H3bis shell any more, it is the payload family, and the module name
now says so. The provider id forked with it —
``h3bis-payload-v0`` -> ``payload-v1`` — so the rename is LOUD rather
than cosmetic (see :class:`RealPayloadProvider`).

One half of the module R2 split in two (``placement`` is the
other). This half never touches a pixel: it reads the observation pieces
placement committed, freezes ONE owner per cell per (capture, footing),
and runs the format's own chain — LDPC + CRC — over the result. A
certificate is real or there is none (L5).

**Production, unchanged**: ``tiles.attempt_k_tile``, the bounded-LLR
invariant, the ownership freeze's single-provenance rule and the attempt
semantics are the carried v1 numerics.

One descriptor per ROUTE (PY1-PY3, built 2026-08-11)
----------------------------------------------------
The attempts used to run inside one fire under one route and one spend,
so a single spend could hide five CRC-32 tests and the certificate could
not say which attempt produced it (HARDENING-SYSTEMIC-REVIEW P1, F-06).
It is now what PROVIDERS.md specified at R1: **one descriptor, one
worker, one read-set, one spend and one attempt per route**, with the
route spelled exactly as the carried decoder spells its stages.

* **``scan``** (PY1), scope = a footing with committed evidence on the
  key. Judges one acquisition by itself.
* **``union``** (PY2), scope = a ppc value at which **two or more
  DISTINCT captures** observed the key. L2 is structural here: the
  descriptor exists only where the law allows the sum, and because the
  read-set IS the identity (§7), the contributor SET the census asks PY2
  to key on is free — the pieces the union summed are the keys it
  declared, and a new capture at that ppc is a new identity, not a new
  bookkeeping field.
* **``retry150``** (PY3), scope = a footing **in the key's
  ``baselined`` set** — THAT footing's scan ran a decoder and failed.
  One BP-150 retry of that footing's ordinary view, over the baseline's
  own evidence and never past it. The tile-level ATTEMPTED state cannot
  gate this (it cannot say WHICH baseline failed, and deriving retries
  from it armed BP-150 on footings whose baseline never ran — the
  2026-08-11 review's P1); the per-footing fact can, and a below-floor
  scan writes neither, because no decoder ran.

**Eligibility, not ordering, is the mechanism.** An attempt that cannot
legally run does not exist as a descriptor, so there is no route
ordering to enforce and no barrier to schedule: a retry cannot precede
its own failed baseline because the ``baselined`` entry is what mints
it, and a union cannot sum one capture because a one-capture ppc mints
no union descriptor. The wake that brings a descriptor into existence is
an ordinary version bump on the tile key (a ``baselined`` gain) or on
the evidence collection (a new piece) — which is exactly why eligibility
keys on those durable facts and NOT on the spend ledger: a spend has no
version to sleep on, so an attempt gated on one could never be woken.

What this does not change: the freeze, the numerics, the per-footing
(ppc, footing-id) component order a union sums in, and the certificates
that come out. Certification stays terminal per key — attempts that lose
the race fire once, read CERTIFIED, contribute their observation
(``observed_by`` is how done projection learns of them) and retire
without touching a decoder.

Counting the CRC exposure
-------------------------
Every attempt that ran a decoder landed exactly one CRC-32 comparison,
and flags it (``WorkResult.exposure``); the ledger folds the flag into a
monotone counter per spend row, so the count survives a later outcome
overwriting the row — the 2026-08-11 review proved that filtering rows
by their LATEST outcome silently erased the exposure of every attempt
that later re-fired into ``already_certified``. :func:`crc_exposure` is
therefore a sum of durable counters, not an estimate: ``crc_passed``
and ``crc_failed`` drew the budget (``decode_tile`` computes the CRC on
every call, so a failed syndrome is still an exposed test);
``below_floor`` refused before any decoder ran and drew nothing. L5's
per-attempt false-accept budget (~2^-32) multiplies by the landed count.
A proposal the scheduler discards as stale never lands — its writes are
dropped, so its CRC test cannot have accepted anything into state, and
it is deliberately not counted.

Choices where DESIGN is silent (for adjudication)
-------------------------------------------------
Numbered as in the module this split, so notes elsewhere still point at
the right ruling; choices 1, 3 and 4 went with the placement worker.

2. **The per-cell ownership freeze orders by the covering window's
   held-out log-loss, then by pose id.** L3 needs ONE owner per cell per
   (capture, footing) and needs it deterministic; the contested cell's
   own value must not choose (that would be self-confirming). Since F1
   (2026-08-23, ruling J2-1 "we implement v1") the order is v1's:
   ``(window_loss, pose_id)`` — the CONTEXT-CORRECTED held-out log-loss
   the covering window's pool fit publishes, then the content-derived
   pose id as the DECLARED tie-break (v1's is the E022 patch ordinal,
   which is arrival order and not rebuildable). The loss is an
   out-of-sample statistic over cells whose values the FORMAT fixes, so
   no payload-cell value and no payload truth chooses an owner. Every
   H3bis piece covers a whole tile, so the rule almost always degenerates
   to "the best-calibrated pose"; the per-cell form is what makes a
   partially-observed piece fall through to the next pose instead of
   erasing the cell.

   PRIOR (kept as history, superseded by F1): the order was ``pose_id``
   alone — "pose ids are content-derived, so the order is a property of
   the geometry, not of the pixels". It was, and that was the defect: a
   fixed GEOMETRIC preference handed the numerically-lowest extent
   90.3-94.1% of all contests (MEASURED) and cost 27 e029 + 27 xerox
   certificates.

   DONE (F-09, 2026-08-12): ownership is decided by the pieces' durable
   OBSERVED MASKS (``EvidenceObservation.observed_ref``, made durable by
   R3), never by an LLR value. The old reduce read a zero LLR as "this
   pose did not observe this cell", which is false for a cell it observed
   and scored exactly at the decision boundary — PAVA emits 0.0 at
   p = 0.5 — so an observed neutral cell could be reassigned to a later
   pose and owner selection was evidence-dependent. Yield can only move
   down-or-flat under the fix: the borrows it forfeits were the illegal
   ones, and union/retry are the lawful recovery paths. Decoder input
   semantics are otherwise unchanged — an owned cell scored 0.0 reaches
   the decoder as the erasure it is.

5. **A retry exists per FOOTING, not once per work key.** PY3 says
   "the latest failed ordinary view", and the pre-split behaviour this
   preserves retried every footing whose own baseline failed; keeping
   one retry per baselined footing is what makes "the same LDPC attempts
   on the same evidence" literally true. It used to be a distinction
   without a difference — placement read ONE lane per capture, so a key
   had one ordinary view and one retry — and H4-LANES stage 2 is where
   it starts biting: every rung a run reads can observe the same tile,
   so a key really does carry several scans and several retries, each
   scoped to the footing whose pixels it decodes.

ONE ATTEMPT PER (TILE, FOOTING), PRICED BY LANE (H4-LANES stage 2)
------------------------------------------------------------------
Nothing about the EVIDENCE law moved for the lanes — a piece names its
footing in its own key, the freeze is per (capture, footing), and a union
exists only where two DISTINCT captures reached one ppc — because that
law was written for exactly this and was merely unreachable while the
reading set was one lane. What stage 2 adds is a PRICE: an attempt that
decodes a coarse rung's evidence costs less than one that decodes a fine
rung's (``COST_PAYLOAD + 2*depth``, the same lane term the placement
source charges its windows), so the cheapest evidence a cascade produces
is also the first evidence it decodes, and the whole family still
undercuts every placement tier at the deepest realistic ladder.

Certified keys mint nothing at all, on any lane: the frontier is
``open_work_keys``, and certification is terminal per key and carries no
footing — one certificate retires the tile everywhere at once rather than
once per rung.

R1 adaptation (interfaces only; the algorithms are untouched)
-------------------------------------------------------------
This family became :class:`RealPayloadProvider` — the same work,
expressed as descriptors the engine can enumerate without knowing what a
payload attempt is. Two consequences worth naming:

* bulk values are STAGED (``WorkResult.blobs``) instead of appended, so a
  proposal the scheduler discards no longer leaves an orphan blob;
* the payload worker names the evidence COLLECTION of its work key, so a
  brand-new observation piece wakes it through the ordinary resource
  table instead of through the orchestrator parsing changed keys. Each
  attempt declares only the pieces it reads BESIDE that collection, so
  its identity moves when its own evidence moves.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import cached_property
from typing import Iterable

import numpy as np

from ..core import (AttemptIdentity, CaptureSha, Decline, ExpansionRequest,
                    FootingId, ProgressSink, ResourceKey, SolveView,
                    SpendRecord, WorkDescriptor, WorkResult, Write,
                    stage_array)
from ..format import (FormatRowSpec, TILE_CELLS, TileFormat,
                      tile_format_for)
from . import calibration
from . import ctx_apply
from . import generation
from .place_sched import LANE_COST_PER_RUNG
from .quarantine import is_quarantined
from .records import (EvidenceObservation, MintRef, TileRecord,
                      calibration_collection_key, carry_tile,
                      evidence_collection_key, parse_evidence_key,
                      parse_tile_key, pose_collection_key,
                      unpack_observed_cells, unpack_piece_halo)
from . import tiles as tile_chain
from .view import PlaneView, as_plane

FAMILY_PAYLOAD = "payload"

#: The routes, spelled as the carried decoder spells its stages — one
#: vocabulary for the descriptor, the spend and the certificate's
#: ``MintRef.route``.
ROUTE_SCAN = tile_chain.AttemptStage.SCAN.value
ROUTE_UNION = tile_chain.AttemptStage.UNION.value
ROUTE_RETRY150 = tile_chain.AttemptStage.RETRY150.value

#: Spend outcomes. The three decode outcomes say what happened to the
#: CRC, because that is the quantity L5 budgets and the review asked for.
OUTCOME_CRC_PASSED = "crc_passed"
OUTCOME_CRC_FAILED = "crc_failed"
OUTCOME_BELOW_FLOOR = "below_floor"
OUTCOME_ALREADY_CERTIFIED = "already_certified"


# ---------------------------------------------------- the attempt frontier

def evidence_footing(key: ResourceKey) -> FootingId:
    """The footing a piece was read through — §5.4 puts it IN the key."""
    return FootingId(parse_evidence_key(key)[0])


#: THE ONE DERIVATION of "which window is this piece's" (F2a,
#: 2026-08-23). The body moved to ``solve.generation``, where the live
#: generation reads it too; the name stays here because F1's supersede
#: wake spelled it here and its pins name it.
evidence_window = generation.window_of_evidence


def ppc_tag(ppc: Fraction) -> str:
    """A union's scope: the pixels-per-cell value it combines at."""
    return f"{ppc.numerator}/{ppc.denominator}"


def resident_footings(view: PlaneView,
                      evidence: Iterable[ResourceKey]) -> tuple[FootingId, ...]:
    """The footings holding evidence on one key AND resident this run.

    Durable evidence can outlive its capture's presence: a resumed
    invocation opens only the captures it was given (F-05/D5c), and a
    piece read through a footing this run never ingested is a fact
    nobody here can decode — incomplete, not corrupt. The frontier skips
    it rather than raising, so a partial resume solves what it can; the
    full resume semantics stay F-05's.

    Sorted by (ppc, footing id) for deterministic expansion output —
    determinism of the derived list, not an execution order: the ready
    queue orders by work id, and no payload semantics may depend on
    which attempt runs first (there are no ladders — DESIGN §3a).
    """
    footings = {evidence_footing(key) for key in evidence}
    resident = [fid for fid in footings if view.has_footing(fid)]
    return tuple(sorted(resident,
                        key=lambda fid: (view.footing(fid).ppc, fid)))


def union_tags(view: PlaneView,
               evidence: Iterable[ResourceKey]) -> tuple[str, ...]:
    """The ppc values where >=2 DISTINCT captures observed one key (L2).

    Footings of one capture are correlated, so a ppc reached by a single
    capture mints no union at all: the illegal sum has no descriptor to
    run under, which is stronger than a check inside one. Non-resident
    footings are skipped for the same reason as in
    :func:`resident_footings`.
    """
    captures: dict[str, set[CaptureSha]] = {}
    for key in evidence:
        fid = evidence_footing(key)
        if not view.has_footing(fid):
            continue
        footing = view.footing(fid)
        captures.setdefault(ppc_tag(footing.ppc), set()).add(
            footing.capture_sha256)
    return tuple(sorted(tag for tag, shas in captures.items()
                        if len(shas) > 1))


def route_evidence_keys(view: PlaneView, key: ResourceKey, route: str,
                        scope: str) -> tuple[ResourceKey, ...]:
    """The pieces ONE attempt reads: its footing's, or its ppc's.

    One rule for both payload families, because it is the rule that makes
    an attempt's read-set its identity (§7): a scan or retry reads the
    footing it is scoped to, a union reads every resident piece at its
    ppc, and nothing reads a piece it does not decode.

    **W5's payload exclusion sits here**, before either branch, because
    it is a statement about the PIECE and not about the route: evidence
    from a placement an address-word contradiction condemned is excluded
    from payload forever (R6-Q16, v1 ``session.py:442-446``). Excluding
    it in the READ-SET is what makes the exclusion total — a condemned
    piece is not merely skipped by the decoder, it is not part of the
    attempt's identity, so an attempt over the survivors is a genuinely
    different attempt and re-arms rather than counting as spent.

    **F2a'S LIVE-GENERATION REDUCTION IS DELIBERATELY *NOT* HERE**
    (ruling J2-3, 2026-08-23), and the reason is the commit wall's own
    law: an attempt's read-set may GROW but never shrink
    (``core.identity.fold_refusal`` — "a read-set may not shrink or
    regress"). A re-read emits new pieces at the live pose, so the
    superseded generation's pieces stay in this attempt's read-set —
    where they belong, because the attempt genuinely re-arms on any
    change to them (a quarantine, say). What the reduction governs is
    the DECODER INPUT, and it is applied one layer in, at
    :meth:`RealPayloadWorker._pieces`. The distinction is the whole of
    it: the read-set is what an attempt is IDENTIFIED by, the frozen
    pieces are what it DECODES, and only the second may narrow. MEASURED
    rather than reasoned: putting it here refused a real spend on the
    verdicts corpus the moment the re-read started emitting.
    """
    evidence = tuple(item for item in view.evidence_on(key)
                     if not is_quarantined(view.record(item)))
    if route == ROUTE_UNION:
        return tuple(
            item for item in evidence
            if view.has_footing(evidence_footing(item))
            and ppc_tag(view.footing(evidence_footing(item)).ppc) == scope)
    return tuple(item for item in evidence
                 if evidence_footing(item) == scope)


def lane_premium(view: PlaneView,
                 footings: Iterable[FootingId]) -> int:
    """What an attempt over these rungs adds to the payload entry's price.

    THE SAME LANE TERM the placement source charges its windows
    (``place_sched.LANE_COST_PER_RUNG``, whose value this restates on the
    solve side of nothing — both live in ``solve``, so this is an import
    and not a second spelling): ``2`` per rung above its capture's
    coarsest. The DEEPEST rung an attempt will read is what prices it,
    because an attempt is not cheaper than its dearest component; a
    single-footing attempt has one, and a union takes the max over the
    ppc's resident footings.

    An empty set answers 0. That is the coarsest lane's price, and the
    honest one: an attempt over no resident footing decodes nothing and
    is about to refuse, so making it dear would only delay the refusal.
    """
    depths = [view.footing_depth(footing_id) for footing_id in footings
              if view.has_footing(footing_id)]
    return LANE_COST_PER_RUNG * (max(depths) if depths else 0)


def crc_exposure(spends: Iterable[SpendRecord]) -> dict[str, object]:
    """The lineage's LANDED false-accept exposure, off the spend ledger.

    ``attempts`` sums the rows' monotone ``exposures`` counters — every
    committed attempt that ran a decoder, regardless of what outcome the
    row folded to afterwards; ``spends`` counts the rows that hold any.
    This is arithmetic over durable counters, not an estimate over fires
    and not a filter on latest outcomes (which the 2026-08-11 review
    proved lossy). L5's ~2^-32 per attempt multiplies by ``attempts``.
    A stale-discarded proposal never lands and is never counted — its
    writes were dropped, so its CRC test could not have accepted
    anything into state.

    Families other than payload never reach a decoder, and a payload
    provider whose decode carries no CRC never flags exposure — so such a
    lineage honestly reports zero.
    """
    rows = 0
    attempts = 0
    by_route: dict[str, int] = {}
    for spend in spends:
        if spend.worker_id.family != FAMILY_PAYLOAD or not spend.exposures:
            continue
        rows += 1
        attempts += spend.exposures
        by_route[spend.route] = by_route.get(spend.route, 0) + spend.exposures
    return {"spends": rows, "attempts": attempts,
            "by_route": dict(sorted(by_route.items()))}


def attempted_work_keys(spends: Iterable[SpendRecord]) -> frozenset[ResourceKey]:
    """The work keys a decoder has run on, off the same ledger rows.

    ATTEMPTED used to be a rank stored on the tile; since tile family v4
    it is this — the durable statement "a CRC-bearing attempt landed on
    this key", which is what the rank meant and what the exposure
    counters have recorded exactly since the per-route split. A payload
    spend's subject IS the work key, so no new channel is needed: the
    ledger the exposure count is already read from answers this too.
    """
    return frozenset(
        spend.worker_id.subject for spend in spends
        if spend.worker_id.family == FAMILY_PAYLOAD and spend.exposures)


# -------------------------------------------------------- payload worker

@dataclass(frozen=True)
class _Piece:
    """One observation piece as the ownership freeze sees it.

    ``observed`` is the piece's durable cell mask (``EvidenceObservation.
    observed_ref``, R3) at the LLR's own shape — the fact the freeze
    selects owners by (F-09). It is a separate field and not a derivation
    from ``llr`` precisely because a zero LLR is a MEASURED value: PAVA
    emits it at p = 0.5.

    ``window_loss`` is F1's addition (ruling J2-1): the held-out
    log-loss of the WINDOW this piece was cut from, under the ctx fit
    that governs it — v1's ownership key
    (``receive/payload.py:138-140``), read off the pool's adopted fit.
    ``inf`` means the pool published none (no adopted fit yet, or a
    pre-F1 blob), and such a piece ranks after every piece that has one.

    ``halo`` is F1's other half (ruling J2-2): the piece's durable
    one-cell context frame (``records.unpack_piece_halo``), from which
    :attr:`bins` derives this piece's ctx bins at v1's WINDOW scope.
    ``None`` when the piece carries no halo (a state written before F1),
    and then the component falls back to tile-scoped bins.

    THE BINS ARE DERIVED LAZILY, AT THE FREEZE (review fix, 2026-08-23).
    They were derived for every piece the attempt loads, but the freeze
    skips any piece that owns no cell (``take.any()``), and on the
    archived e029 store 30.9% of piece loads own nothing — a third of the
    derivations were never read. Deriving inside the loop, memoized per
    piece, removes them with no semantic change: the array a piece
    answers is a pure function of its own three durable fields.
    """

    footing_id: str
    pose_id: ResourceKey
    llr: np.ndarray
    observed: np.ndarray
    window_loss: float = float("inf")
    halo: tuple[np.ndarray, np.ndarray] | None = None

    @cached_property
    def bins(self) -> np.ndarray | None:
        """This piece's window-scoped ctx bins, derived once, or ``None``.

        ``cached_property`` writes straight into the instance dict, which
        a frozen dataclass still has — the freeze reads this at most once
        per piece today (a UNION partitions its pieces by footing), so
        the memo is insurance against a second caller, not a load-bearing
        saving.
        """
        if self.halo is None:
            return None
        return ctx_apply.window_context_bins(
            self.llr, self.observed, self.halo)


class RealPayloadWorker:
    """ONE ATTEMPT of one work key: owner evidence -> ``attempt_k_tile``."""

    task_class = FAMILY_PAYLOAD

    def __init__(self, key: ResourceKey, spec: TileFormat, *,
                 stage: tile_chain.AttemptStage, scope: str) -> None:
        self.key = key
        page, ty, tx, stream = parse_tile_key(key)
        self.address = (page, ty, tx)
        self.stream = stream
        self.stage = stage
        #: A footing id (scan, retry150) or a ppc tag (union).
        self.scope = scope
        self._spec = spec

    @property
    def route(self) -> str:
        return self.stage.value

    def read_keys(self, view: SolveView) -> tuple[ResourceKey, ...]:
        """The work key, its evidence COLLECTION, THIS attempt's pieces —
        and, since H5, the region calibration it decodes under.

        The collection (M4) is what makes a piece's ARRIVAL wake this
        worker: an evidence key that does not exist yet cannot be named,
        and before R1 the orchestrator papered over that by parsing
        changed keys and pushing a worker id it had constructed itself.
        Naming the collection makes the arrival an ordinary version bump
        and the wake an ordinary subscription.

        Beside it the attempt names only the pieces it actually reads,
        which is what makes a union's contributor set an identity rather
        than a record field: two unions over different component sets are
        different identities by construction (§7, PROVIDERS PY2).

        THE H5 SUBSCRIPTION SCOPING (user-confirmed law): per (footing,
        region) this attempt's pieces come from — derived by key
        arithmetic alone — exactly ONE region-scoped resource joins the
        set: the pool's calibration collection, which versions on
        ADOPTION only. Never sibling evidence, never the region's pieces,
        never the pool record (its writes track labels, and a decode must
        not wake per label). The already-adopted record keys the fire
        will read ride along too — frozen, so they wake nothing, but they
        make the read honest and the identity exact — and an adoption
        landing mid-flight moves the collection's version, which is
        precisely the staleness that re-decodes this tile calibrated.

        THE SUPERSEDE WAKE (F1, ruling J2-3, 2026-08-23). One more
        region-free key per covering WINDOW: that window's pose
        collection, which versions when a pose joins it — so when a
        revision becomes the live pose of an extent this attempt goes
        stale and the tile ACTS AGAIN at its turn, priced like any other
        payload attempt, no phase and no barrier. It is derived by the
        same key arithmetic as the pools (a piece key embeds its pose,
        a pose key embeds its window), it names no sibling evidence, and
        a certified tile retires — so the wake reaches exactly the
        window's UNCERTIFIED tiles.

        This is the minimal half. What makes the wake PRODUCTIVE is the
        re-sample: nothing in the tree emits evidence at a revised pose
        yet (``refine.py:52-56``), so today the re-armed attempt reads
        the same pieces and reaches the same answer. F2 owes the emitter
        and the live-generation scoping of the freeze candidates and the
        ctx pool (ledger row 7: per (tile, window) keep only the newest
        pose that HAS pieces — never ``index.live_pose``, which would
        delete 4,392/4,117 pieces today because the live pose is the one
        with none).
        """
        plane = as_plane(view)
        evidence = self._evidence_keys(plane)
        keys = {self.key, evidence_collection_key(self.key), *evidence}
        fits = plane.index().context_fits
        pools = {pool for pool in map(calibration.pool_of_evidence, evidence)
                 if pool is not None}
        for pool in sorted(pools):
            keys.add(calibration_collection_key(pool))
            keys.update(fits.get(pool, ()))
        windows = {window for window in map(evidence_window, evidence)
                   if window is not None}
        for window in sorted(windows):
            keys.add(pose_collection_key(window))
        return tuple(sorted(keys))

    def run(self, view: SolveView, identity: AttemptIdentity,
            progress: ProgressSink) -> WorkResult:
        plane = as_plane(view)
        current = plane.tile(self.key)
        progress.emit(1, "arm")
        if current is not None and current.certified:
            # A race-loser still contributes its observation: done
            # projection needs every committed observation of a certified
            # key (§6), and this attempt is the only worker that will
            # ever look through these footings at it.
            gain = tuple(sorted({evidence_footing(key)
                                 for key in self._evidence_keys(plane)}))
            merged = carry_tile(current, gain)
            return WorkResult(
                outcome=OUTCOME_ALREADY_CERTIFIED, retire=True,
                writes=() if merged == current else (Write(self.key, merged),))
        evidence = self._evidence_keys(plane)
        fits = self._fits(plane, evidence)
        pieces = self._pieces(plane, evidence, fits)
        observed = tuple(sorted(set(
            (current.observed_by if current is not None else ())
            + tuple(piece.footing_id for piece in pieces))))
        llr, pose_id, contributors = self._decoder_input(plane, pieces, fits)
        progress.emit(1, f"attempt:{self.stage.value}")
        attempt = tile_chain.attempt_k_tile(llr, self._spec, self.address,
                                            self.stage)
        if attempt.certified:
            bits = stage_array(np.asarray(attempt.symbol_bits, np.uint8))
            record = tile_chain.certified_tile_record(
                attempt,
                minting=MintRef(pose_id, route=self.route,
                                decoder_profile=attempt.decoder_profile,
                                contributors=contributors),
                bits_ref=bits.ref, observed_by=observed,
                baselined=(current.baselined if current is not None else ()))
            return WorkResult(
                outcome=OUTCOME_CRC_PASSED, retire=True, exposure=True,
                writes=(Write(self.key, record),), blobs=(bits,))
        if attempt.state is tile_chain.AttemptState.BELOW_ATTEMPT_FLOOR:
            # No decoder ran: no attempt happened, no baseline exists —
            # only the observation is a fact worth keeping.
            merged = carry_tile(current, observed)
            return WorkResult(
                outcome=OUTCOME_BELOW_FLOOR,
                writes=() if merged == current else (Write(self.key, merged),))
        baseline = (FootingId(self.scope)
                    if self.stage is tile_chain.AttemptStage.SCAN else None)
        attempted = carry_tile(current, observed, baseline=baseline)
        writes = () if attempted == current else (Write(self.key, attempted),)
        return WorkResult(
            outcome=OUTCOME_CRC_FAILED, writes=writes, exposure=True)

    # -- internals ---------------------------------------------------------

    def _evidence_keys(self, view: PlaneView) -> tuple[ResourceKey, ...]:
        return route_evidence_keys(view, self.key, self.route, self.scope)

    def _fits(self, view: PlaneView, keys: Iterable[ResourceKey]
              ) -> dict[ResourceKey, ctx_apply.AdoptedContextFit | None]:
        """This attempt's pools' adopted fits, read ONCE (F1).

        The fit answers two questions now — the offsets its component
        takes and the held-out loss each of its member windows ranks by —
        and they come out of one params blob, so the whole attempt reads
        it once and both the freeze and the correction consult the same
        object. Every key here is already in :meth:`read_keys`.
        """
        pools = {pool for pool in map(calibration.pool_of_evidence, keys)
                 if pool is not None}
        return {pool: ctx_apply.adopted_context_fit(view, pool)
                for pool in pools}

    def _pieces(self, view: PlaneView, evidence: Iterable[ResourceKey],
                fits: dict[ResourceKey,
                           ctx_apply.AdoptedContextFit | None],
                ) -> tuple[_Piece, ...]:
        """This attempt's decodable pieces: the LIVE generation of each.

        F2a (ruling J2-3, 2026-08-23). Per (tile, window) only the pieces
        of the newest pose that HAS pieces are decoded, so a read at a
        superseded geometry and a read at the live one never meet in one
        freeze — v1's lane separation reproduced without lanes
        (``production_refine.py:29-36``). The superseded pieces stay
        COMMITTED, stay in the read-set and stay readable; they simply
        stop owning cells the moment the re-read has spoken.

        IT IS HERE AND NOT IN THE READ-SET because a read-set may not
        shrink (:func:`route_evidence_keys` says why). The re-arm does
        not need it: a re-read's pieces are NEW KEYS, so the read-set
        GROWS and the standing attempt goes stale by the mechanism the
        wall already has.

        It is the IDENTITY on every state written before F2a — nothing
        re-sampled, so no window's live pose owns a piece
        (:mod:`holo2.solve.generation`).
        """
        pieces: list[_Piece] = []
        for key in generation.live_generation(view.index().live_poses,
                                              evidence):
            observation = view.record(key)
            if not isinstance(observation, EvidenceObservation):
                continue
            llr = np.asarray(view.read_array(observation.llr_ref), np.float64)
            packed = view.read_array(observation.observed_ref)
            observed = unpack_observed_cells(packed,
                                             (TILE_CELLS, TILE_CELLS))
            llr = llr.reshape(TILE_CELLS, TILE_CELLS)
            # The pool may be unnameable (a malformed key answers None);
            # expressed rather than absorbed by ``dict.get``, which would
            # take the None and answer None by accident.
            pool = calibration.pool_of_evidence(key)
            fit = None if pool is None else fits.get(pool)
            # NOT ``fit.loss_of`` DIRECTLY (F2a review fix, 2026-08-23):
            # between a re-read's commit and its pool's re-fit the live
            # pose has no published loss, and ``inf`` here loses the
            # window every contested cell. ``ctx_apply.window_loss``
            # falls back to the extent's other generation — same window,
            # same population — which is what v1 has because v1 re-fits
            # before it decodes.
            loss = ctx_apply.window_loss(view, fit, observation.pose_id)
            pieces.append(_Piece(
                observation.footing_id, observation.pose_id, llr, observed,
                float("inf") if loss is None else loss,
                unpack_piece_halo(packed)))
        return tuple(sorted(pieces, key=lambda p: (p.footing_id, p.pose_id)))

    def _decoder_input(self, view: PlaneView, pieces: tuple[_Piece, ...],
                       fits: dict[ResourceKey,
                                  ctx_apply.AdoptedContextFit | None],
                       ) -> tuple[np.ndarray, ResourceKey,
                                  tuple[ResourceKey, ...]]:
        """This attempt's decoder input and its provenance.

        SCAN and RETRY150 freeze one footing's pieces to one owner per
        cell; UNION sums the per-footing owners in (ppc, footing) order
        and names every component pose (M10) — recording only the first
        would lose the provenance a later quarantine needs.

        THE H5 CTX CORRECTION APPLIES HERE, at decode assembly (the
        load-bearing design sentence): each footing's frozen component
        takes its own regions' ADOPTED additive-logit correction —
        footing-scoped, over the cells each region's poses own — BEFORE
        any cross-capture sum, so L2 is respected by construction. The
        pieces themselves keep their marginal LLRs forever; a region with
        no adopted fit contributes no correction, and a component with
        none anywhere is the SAME array object it always was — the null
        correction is the identity, which is the refused path's
        bit-for-bit claim.

        Since F1 the BINS that correction indexes are the owner's
        window-scoped ones (ruling J2-2), assembled by the freeze.
        """
        if self.stage is not tile_chain.AttemptStage.UNION:
            owner, owners, bins = self._freeze_with_owners(list(pieces))
            return (self._corrected(view, owner, owners, bins, fits),
                    owner.pose_id, ())
        by_footing: dict[str, list[_Piece]] = {}
        for piece in pieces:
            by_footing.setdefault(piece.footing_id, []).append(piece)
        components: list[np.ndarray] = []
        poses: list[ResourceKey] = []
        for footing_id in sorted(
                by_footing,
                key=lambda fid: (view.footing(FootingId(fid)).ppc, fid)):
            owner, owners, bins = self._freeze_with_owners(
                by_footing[footing_id])
            components.append(
                self._corrected(view, owner, owners, bins, fits))
            poses.append(owner.pose_id)
        summed = np.sum(components, axis=0)
        return summed, poses[0], tuple(sorted(set(poses)))

    @staticmethod
    def _corrected(view: PlaneView, owner: _Piece,
                   owners: dict[ResourceKey, np.ndarray],
                   bins: np.ndarray | None,
                   fits: dict[ResourceKey,
                              ctx_apply.AdoptedContextFit | None],
                   ) -> np.ndarray:
        """One component's tensor, corrected by its regions' adopted fits."""
        return ctx_apply.apply_component_context(
            owner.llr, owner.observed,
            ctx_apply.component_corrections(view, owners, fits), bins)

    @staticmethod
    def _freeze(pieces: list[_Piece]) -> _Piece:
        """One owner per CELL per (capture, footing) — L3, never a sum.

        THE BEST-CALIBRATED WINDOW WINS A CONTESTED CELL (F1, ruling
        J2-1 "we implement v1", 2026-08-23). v1 orders freeze candidates
        by ``(heldout_logloss, patch_id)`` — the window's held-out
        log-loss on FORMAT-KNOWN sites, corrected by the region's adopted
        ctx offsets where it adopted (``receive/payload.py:138-140`` with
        ``_payload_context.py:284-295``) — and the first candidate to
        name a cell owns it. holo2 ordered by ``pose_id`` alone, which is
        ``window_key + page + affine`` and therefore a fixed GEOMETRIC
        preference (the numerically-lowest extent won 90.3-94.1% of all
        contests, MEASURED). On tiles at the CRC margin that handed about
        half the tile to the worse-calibrated window and read it at up to
        36% BER where the other window read the same cells at 2%.
        Re-freezing holo2's own committed evidence under v1's key
        certifies 26-27 of the 30 e029 gap tiles and 27 of the 48 xerox
        ones with ZERO regressions in the 1,910 + 1,882 tiles already
        certified; the anti-rule control (worst-first) rescues 4 and
        REGRESSES 64, and a coin rescues 20 — so it is the statistic and
        not the reshuffle (``detect/DETECTION-GAP.md`` §3,
        ``DETECTION-GAP-VERIFY.md`` §3.1 C3/C6).

        THIS IS STILL F-09, STATED PRECISELY (review fix, 2026-08-23).
        No PAYLOAD-cell value and no payload truth enters owner
        selection: the ranking statistic reads the evidence only at
        sites whose values the FORMAT fixes (``region_fit_inputs``'
        ``known & heldout`` mask, a subset of ``reference.page(...).
        sites``), out of sample, before any payload decision and durable
        in the pool's fit — exactly as v1's does. What F-09 closed is
        the per-cell property, and it is untouched: the contested cell's
        OWN value never decides who owns it (``take = piece.observed &
        ~owned`` reads masks alone). The earlier wording here — "no
        evidence VALUE enters owner selection" — was true of the pose-id
        order and is not true of v1's key, which is a statistic OF the
        evidence at format-known sites. A
        cell an earlier-ranked pose scored exactly at the decision
        boundary (LLR 0, which PAVA emits at p = 0.5) stays that pose's
        and stays 0.0 — an erasure the decoder is entitled to see, not a
        gap a later pose may fill. A cell no piece observed is 0.0 as
        well; the returned piece's own mask says which of the two it is.

        THE TIE-BREAK IS ``pose_id``, DECLARED (v1's is the numeric E022
        patch ordinal, which holo2 has no counterpart for and which is
        arrival order within a level, so it is not rebuildable). A pose
        id is content-derived and total, which the ordinal is not, and it
        is the key holo2 already sorted by — so the order stays total and
        run-independent, and a pool that publishes no loss simply keeps
        the pre-F1 order among its own pieces.

        WHAT THE FALLBACK IS, EXACTLY (review fix, 2026-08-23; the
        HANDOFF's §3.1 account of the WRITE side was wrong — the refused
        fit's marginal losses ARE committed, by ``_writes`` on the
        refused path, and what blocks reading them is the read-set:
        ``keys.calibration_collection_key`` admits ADOPTED fits only).
        A piece whose pool has no adopted fit carries ``inf``, so it
        ranks after every piece that has a published loss and keeps the
        pre-F1 pose-id order among its unpublished siblings. v1 would
        rank such a window by its MARGINAL held-out loss instead, so a
        component contested between an adopted-pool region and a
        refused-pool region is a DECLARED non-v1 tie class: the adopted
        region wins every contested cell there regardless of quality.
        MEASURED non-binding on the corpus (all 15/15 e029 and 12/12
        xerox pool fits adopted, ``v1audit/c3-pool-census.json``); a
        fully refused pool degrades cleanly to the pre-F1 order. Closing
        it is a READ-SET amendment (a second, any-fit collection the
        payload attempt names), with the wake cost per refit stated and
        measured — not a patch.
        """
        return RealPayloadWorker._freeze_with_owners(pieces)[0]

    @staticmethod
    def _freeze_with_owners(pieces: list[_Piece]
                            ) -> tuple[_Piece,
                                       dict[ResourceKey, np.ndarray],
                                       np.ndarray | None]:
        """:meth:`_freeze`, also reporting WHICH pose owns WHICH cells.

        The owner map is what the H5 ctx correction needs: the correction
        is region-scoped, a cell's region is its OWNER's, and the freeze
        is the one place per-cell ownership is decided — deriving it
        again anywhere else would be a second freeze that could drift.
        Same loop, same masks; the map is a by-product.

        The third value is F1's window-scoped BIN array (ruling J2-2):
        each cell binned in its OWNER's window, which is what v1 has
        because v1 corrects the whole window before it freezes. It is
        assembled in this same loop for the same reason the owner map is.
        ``None`` if ANY owning piece carries no halo — a component must
        not mix the two scopes, so a state written before F1 takes the
        tile-scoped derivation whole, exactly as it did. Each owning
        piece's bins are DERIVED HERE, at first read (``_Piece.bins``,
        review fix 2026-08-23): a piece that owns no cell never pays for
        them, which on the archived e029 store is 30.9% of piece loads.
        """
        ordered = sorted(pieces,
                         key=lambda piece: (piece.window_loss, piece.pose_id))
        shape = ordered[0].llr.shape
        owner = np.zeros(shape, np.float64)
        owned = np.zeros(shape, bool)
        bins = np.full(shape, -1, np.int8)
        haloed = True
        owners: dict[ResourceKey, np.ndarray] = {}
        for piece in ordered:
            take = piece.observed & ~owned
            if not take.any():
                continue
            owner[take] = piece.llr[take]
            # Reading ``bins`` is what DERIVES it (``_Piece.bins``), and
            # this is the first line that knows the piece owns anything —
            # which is the whole point of deriving it here.
            piece_bins = piece.bins
            if piece_bins is None:
                haloed = False
            else:
                bins[take] = piece_bins[take]
            owned |= take
            held = owners.get(piece.pose_id)
            owners[piece.pose_id] = take if held is None else (held | take)
            if owned.all():
                break
        return (_Piece(ordered[0].footing_id, ordered[0].pose_id, owner,
                       owned, ordered[0].window_loss),
                owners, bins if haloed else None)


# ------------------------------------------------------------ the provider

class RealPayloadProvider:
    """Every open work key's derivable attempts, one descriptor per
    (route, scope) — PY1-PY3."""

    family = FAMILY_PAYLOAD
    # Annotated, not inferred: ``core.Provider`` declares this
    # ``tuple[str, ...]``, and a bare literal infers ``tuple[str, str]``,
    # which does not satisfy it (worklist B12).
    # ``collection:poses-window`` is F1's supersede wake (ruling J2-3):
    # the attempt's read-set names each covering window's pose
    # collection, so a revision that becomes the extent's live pose makes
    # the standing attempt stale and the uncertified tile acts again.
    sources: tuple[str, ...] = ("tile", "collection:evidence",
                                "collection:poses-window")

    #: THE LINEAGE STRING, FORKED AT H4 W6 (2026-08-18) with the module
    #: rename. It is not a label: provider ids ride the session identity
    #: BY VALUE (``core.work.providers_identity`` -> ``SessionIdentity``),
    #: which the store compares on resume — so changing it makes every
    #: state directory minted under ``h3bis-payload-v0`` REFUSE TO OPEN
    #: ("session identity differs from the expected lineage", naming the
    #: directory but not the field). That is the intent: a dead
    #: codename is not worth carrying, and the freshness doctrine says a
    #: lineage change is loud and un-migrated rather than quiet. Nothing
    #: about the family, its routes, its spends or its numerics moved.
    PROVIDER_ID = "payload-v1"

    def __init__(self, row: FormatRowSpec, *,
                 provider_id: str = PROVIDER_ID) -> None:
        self.provider_id = provider_id
        self.spec = tile_format_for(row)
        #: work key -> (its evidence group, its record, the request arm,
        #: the attempts those three imply). The frontier memo (F-17); see
        #: :meth:`expand` for why object IDENTITY is the whole test.
        self._frontier: dict[ResourceKey, tuple[
            tuple[ResourceKey, ...], TileRecord | None, str,
            tuple[WorkDescriptor, ...]]] = {}

    # The two protocol methods take core's ``SolveView`` — the view the
    # engine promises — and narrow to the plane the root composed
    # (``as_plane``). Narrowing in the SIGNATURE is what made this class
    # fail to satisfy ``core.Provider`` at all (B12).

    def expand(self, view: SolveView,
               request: ExpansionRequest) -> tuple[WorkDescriptor, ...]:
        """The attempts the frontier currently supports, per open work key.

        An attempt with no evidence to read is not minted at all, so the
        derivable set is a property of the durable facts: resident
        footings that observed the key (scan), ppc values two distinct
        captures reached (union), and — per footing whose OWN scan ran a
        decoder and failed (``baselined``) — that footing's single
        BP-150 retry.

        **Per-key memo, on object identity** (F-17, 2026-08-17). One
        key's attempts are a function of exactly three things: its
        evidence group, its tile record, and the request's arm. The first
        two are frozen values the store index hands out — the index is
        maintained copy-on-write, so a group's tuple and a record are
        REPLACED when they change and are the same object when they did
        not — which makes ``is`` a sound staleness test and a
        conservative one (a rebuilt index misses every entry and simply
        re-derives). Before this, every refresh re-derived every open
        key's footings and union tags by re-parsing every evidence key:
        1.67 M ``resident_footings``/``union_tags`` calls and 5.4 M
        ``parse_evidence_key`` calls per serial run, for an answer that
        moved on ~2 keys per commit.

        The enumeration itself stays TOTAL, deliberately. A provider that
        emitted only the changed keys would have to know what the
        orchestrator has already minted, un-parked and skipped (a
        quiescent-gated entry can decline to expand for many commits and
        must not lose the descriptors those commits implied), and that is
        engine state a provider may not hold.
        """
        plane = as_plane(view)
        index = plane.index()
        groups, tiles = index.evidence_by_tile, index.tiles
        memo, arm = self._frontier, request.arm
        descriptors: list[WorkDescriptor] = []
        for key in plane.open_work_keys():
            evidence = groups.get(key, ())
            if not evidence:
                continue
            record = tiles.get(key)
            cached = memo.get(key)
            if (cached is not None and cached[0] is evidence
                    and cached[1] is record and cached[2] == arm):
                descriptors.extend(cached[3])
                continue
            attempts = self._attempts(plane, request, key, evidence, record)
            memo[key] = (evidence, record, arm, attempts)
            descriptors.extend(attempts)
        return tuple(descriptors)

    @staticmethod
    def _attempts(plane: PlaneView, request: ExpansionRequest,
                  key: ResourceKey, evidence: tuple[ResourceKey, ...],
                  record: TileRecord | None) -> tuple[WorkDescriptor, ...]:
        """One open work key's derivable attempts — the eligibility rules.

        Unchanged from what :meth:`expand` used to inline; it is a
        function now because the memo above needs a name to call on a
        miss, and because "what one key implies" is the whole rule.

        Every attempt carries its LANE TERM (H4-LANES stage 2). A scan
        and a retry are scoped to one footing, so the term is that
        footing's depth; a union is scoped to a ppc reached by several
        captures, so it takes the DEEPEST of the rungs it will read —
        a union is not cheaper than its dearest component, and on the
        ordinary case (captures at one declared dpi) every component sits
        at the same depth and the max is that depth.
        """
        attempts: list[WorkDescriptor] = []
        for footing_id in resident_footings(plane, evidence):
            attempts.append(request.mint(
                FAMILY_PAYLOAD, key, ROUTE_SCAN, profile=footing_id,
                premium=lane_premium(plane, (footing_id,))))
        for tag in union_tags(plane, evidence):
            attempts.append(request.mint(
                FAMILY_PAYLOAD, key, ROUTE_UNION, profile=tag,
                premium=lane_premium(plane, tuple(
                    evidence_footing(item)
                    for item in route_evidence_keys(plane, key, ROUTE_UNION,
                                                    tag)))))
        if record is not None:
            for footing_id in record.baselined:
                if plane.has_footing(footing_id):
                    attempts.append(request.mint(
                        FAMILY_PAYLOAD, key, ROUTE_RETRY150,
                        profile=footing_id,
                        premium=lane_premium(plane, (footing_id,))))
        return tuple(attempts)

    def worker(self, view: SolveView,
               descriptor: WorkDescriptor) -> RealPayloadWorker | Decline:
        return RealPayloadWorker(
            descriptor.subject, self.spec,
            stage=tile_chain.AttemptStage(descriptor.route),
            scope=descriptor.scope.profile)


__all__ = [
    "FAMILY_PAYLOAD", "OUTCOME_ALREADY_CERTIFIED",
    "OUTCOME_BELOW_FLOOR", "OUTCOME_CRC_FAILED", "OUTCOME_CRC_PASSED",
    "ROUTE_RETRY150", "ROUTE_SCAN", "ROUTE_UNION",
    "RealPayloadProvider", "RealPayloadWorker", "attempted_work_keys",
    "crc_exposure", "evidence_footing", "ppc_tag", "resident_footings",
    "route_evidence_keys", "union_tags",
]
