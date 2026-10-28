"""The payload units a page-level e2e cannot localise.

The family itself is gated end to end in ``holo2/measure/verdicts/`` (where
a real generator may be imported). What is pinned here is what is a DECISION
rather than arithmetic: how one cell's owner is chosen when several poses
saw it, which attempts the frontier makes eligible, and how the CRC
exposure of a lineage is counted.

R2 split ``real_workers`` in two; this file went with the payload half.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction

import numpy as np

from holo2.capture import region_key
from holo2.core import (AttemptIdentity, ExpansionRequest, ProgressSink,
                        ResourceKey, SpendRecord, WorkId, WorkScope)
from holo2.solve import payload
from holo2.solve.payload import (FAMILY_PAYLOAD, OUTCOME_BELOW_FLOOR,
                                 OUTCOME_CRC_FAILED, OUTCOME_CRC_PASSED,
                                 ROUTE_RETRY150, ROUTE_SCAN, ROUTE_UNION,
                                 _Piece)
from holo2.solve import (MintRef, TileRecord, evidence_key, pose_key,
                         tile_key, window_key)
from holo2.solve.tilemap import StoreIndex
from holo2.format.registry_rows import format_row

#: One printed row is all a payload provider needs of the format.
ROW = format_row("c3-k-r0550", (2, 4))

REGION_A = region_key("ab" * 32, (0, 0), 8, (8, 128))
REGION_B = region_key("cd" * 32, (0, 0), 8, (8, 128))
AFFINE = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
KEY = tile_key(0, 1, 2, "main")


def _pose(footing: str, region: ResourceKey) -> ResourceKey:
    return pose_key(window_key(footing, region, (0, 0, 8, 128)), 0, AFFINE)


def _evidence(footing: str, region: ResourceKey) -> ResourceKey:
    return evidence_key(footing, 0, 1, 2, "main", _pose(footing, region))


@dataclass(frozen=True)
class _Footing:
    """Exactly what an attempt asks a footing: its aperture and capture."""

    ppc: Fraction
    capture_sha256: str


class _View:
    """The frontier a payload provider expands over, and nothing else."""

    def __init__(self, evidence: dict[ResourceKey, tuple[ResourceKey, ...]],
                 footings: dict[str, _Footing],
                 tiles: dict[ResourceKey, TileRecord],
                 pieces: dict[ResourceKey, object] | None = None) -> None:
        self._evidence = evidence
        self._footings = footings
        self._tiles = tiles
        # W5: the payload exclusion reads the PIECE to ask whether it is
        # quarantined, so the stub has to be able to hand one back. A
        # frontier test that names no piece records has none quarantined,
        # which is what every case here means.
        self._pieces = dict(pieces or {})
        # The frontier memo keys on the objects the INDEX hands out
        # (F-17), so the stub holds one instead of minting a fresh tuple
        # per read: a stub whose every read is a new object would
        # exercise only the miss path.
        self._index = StoreIndex(
            tiles=dict(tiles),
            evidence_by_tile={key: tuple(sorted(keys))
                              for key, keys in evidence.items()})

    def index(self) -> StoreIndex:
        return self._index

    def open_work_keys(self) -> tuple[ResourceKey, ...]:
        return tuple(sorted(self._evidence))

    def evidence_on(self, key: ResourceKey) -> tuple[ResourceKey, ...]:
        return self._index.evidence_by_tile.get(key, ())

    def record(self, key: ResourceKey) -> object | None:
        return self._pieces.get(key)

    def footing(self, footing_id: str) -> _Footing:
        return self._footings[footing_id]

    def has_footing(self, footing_id: str) -> bool:
        return footing_id in self._footings

    def footing_depth(self, footing_id: str) -> int:
        """``SessionPlane.footing_depth``'s rule over this stub's ladder.

        H4-LANES stage 2 prices an attempt by the RUNG it decodes, so the
        frontier asks the plane how deep the footing sits in its own
        capture's ladder — the index of its ppc among that capture's,
        coarsest first.
        """
        footing = self._footings[footing_id]
        ladder = sorted({item.ppc for item in self._footings.values()
                         if item.capture_sha256 == footing.capture_sha256})
        return ladder.index(footing.ppc)

    def tile(self, key: ResourceKey) -> TileRecord | None:
        return self._tiles.get(key)


def _attempts(view: _View) -> list[tuple[str, str]]:
    provider = payload.RealPayloadProvider(ROW)
    descriptors = provider.expand(view, ExpansionRequest(entry="e"))
    assert all(item.family == FAMILY_PAYLOAD and item.subject == KEY
               for item in descriptors)
    return [(item.route, item.scope.profile) for item in descriptors]


def test_a_minted_descriptor_carries_the_request_arm_and_no_entry() -> None:
    """Every route mints through ``ExpansionRequest.mint`` — one shape.

    The arm is the REQUEST's data and rides the scope; the recipe entry
    is provenance the ORCHESTRATOR stamps, so a provider writes none —
    which is exactly why it cannot write the wrong one.
    """
    view = _View({KEY: (_evidence("a:2/1", REGION_A),)},
                 {"a:2/1": _Footing(Fraction(2), "ab" * 32)}, {})
    provider = payload.RealPayloadProvider(ROW)
    descriptors = provider.expand(
        view, ExpansionRequest(entry="payload-scan", arm="a2"))
    assert descriptors
    for descriptor in descriptors:
        assert descriptor.scope.arm == "a2"
        assert descriptor.scope.profile, "the route's discriminator"
        assert descriptor.entry == ""


# --------------------------------------------------------- the ownership freeze

# THESE FOUR PINS EXERCISE THE TIE PATH, and say so (review fix,
# 2026-08-23). Their fixtures construct ``_Piece`` without
# ``window_loss``, so every piece carries ``inf`` and the freeze falls
# through v1's ranking key to the DECLARED tie-break, the pose id — which
# is exactly the case they were written for and the case a real component
# hits when its pool has published no loss. The RANKED path (F1, ruling
# J2-1: the covering window's context-corrected held-out log-loss) is
# pinned in ``test_freeze_ownership.py``.

def _seen(rows: slice | None = None) -> np.ndarray:
    """A 4x4 observed mask: every cell, or one row band of them."""
    mask = np.zeros((4, 4), bool)
    mask[slice(None) if rows is None else rows] = True
    return mask


def test_the_freeze_is_per_cell_and_evidence_independent() -> None:
    """L3 at the TIE-BREAK: one owner per cell, and never the LLR value.

    Both pieces carry the default ``inf`` window loss, so this pins the
    geometric order among pieces whose pools published no ranking
    statistic — pose id, ascending. It does NOT pin the production order,
    which is ``(window_loss, pose_id)`` since F1
    (``test_freeze_ownership.py``); the docstring said "chosen by
    geometry id" until the 2026-08-23 review caught it.
    """
    first = np.zeros((4, 4))
    first[:2] = 3.0                       # this pose saw only the top half
    second = np.full((4, 4), -9.0)        # a later pose saw everything
    owner = payload.RealPayloadWorker._freeze([
        _Piece("f", "pose-zzz", second, _seen()),
        _Piece("f", "pose-aaa", first, _seen(slice(0, 2)))])
    assert owner.pose_id == "pose-aaa", "pose id order, not LLR magnitude"
    assert np.array_equal(owner.llr[:2], first[:2])
    assert np.array_equal(owner.llr[2:], second[2:]), (
        "cells the owner never saw fall through instead of being erased")
    assert owner.observed.all(), "between them the poses observed every cell"


def test_an_observed_zero_is_owned_not_borrowed_over() -> None:
    """F-09, fixed 2026-08-12: a measured 0.0 is evidence, not absence.

    PAVA legitimately emits 0.0 at p = 0.5, so the pre-fix
    ``gap = owner == 0.0`` handed an OBSERVED neutral cell to a later
    pose — owner selection that depended on the evidence's own value.
    Ownership now reads the durable masks alone: the first pose observed
    the whole tile, so it owns every cell, and the boundary cell reaches
    the decoder as the erasure it is.
    """
    first = np.full((4, 4), 2.0)
    first[3, 3] = 0.0                     # observed, scored exactly at p=0.5
    second = np.full((4, 4), -9.0)
    owner = payload.RealPayloadWorker._freeze([
        _Piece("f", "pose-b", second, _seen()),
        _Piece("f", "pose-a", first, _seen())])
    assert owner.pose_id == "pose-a"
    assert np.array_equal(owner.llr, first), "no cell was borrowed"
    assert owner.llr[3, 3] == 0.0


def test_a_cell_no_piece_observed_stays_an_erasure() -> None:
    """Owned-with-zero and never-observed both reach the decoder as 0.0;
    the composite mask is what tells them apart afterwards."""
    values = np.full((4, 4), 5.0)
    owner = payload.RealPayloadWorker._freeze([
        _Piece("f", "pose-a", values, _seen(slice(0, 1)))])
    assert np.array_equal(owner.llr[0], values[0])
    assert not owner.llr[1:].any(), "unobserved cells stay 0.0"
    assert owner.observed[0].all() and not owner.observed[1:].any()


def test_a_single_piece_freezes_to_itself() -> None:
    piece = _Piece("f", "pose-a", np.arange(16.0).reshape(4, 4), _seen())
    owner = payload.RealPayloadWorker._freeze([piece])
    assert owner.pose_id == "pose-a"
    assert np.array_equal(owner.llr, piece.llr)
    assert np.array_equal(owner.observed, piece.observed)


# ---------------------------------------------------- attempt eligibility

def test_one_scan_per_footing_deterministically_derived() -> None:
    """PY1: a scan exists exactly where a resident footing observed the
    key. The (ppc, footing) order pins DERIVATION determinism only — the
    ready queue orders execution by work id, and no payload semantics may
    depend on which attempt runs first (DESIGN §3a)."""
    view = _View(
        {KEY: (_evidence("a:2/1", REGION_A), _evidence("a:8/1", REGION_A))},
        {"a:2/1": _Footing(Fraction(2), "ab" * 32),
         "a:8/1": _Footing(Fraction(8), "ab" * 32)},
        {KEY: TileRecord()})
    assert _attempts(view) == [(ROUTE_SCAN, "a:2/1"), (ROUTE_SCAN, "a:8/1")]


def test_every_attempt_is_priced_by_the_rung_it_decodes() -> None:
    """H4-LANES stage 2: one attempt per (tile, footing), lane-priced.

    The eligibility rules did not move — a scan per resident footing, a
    retry per baselined one, a union per multi-capture ppc — and what
    joined them is the ``premium`` the descriptor carries into the queue:
    ``LANE_COST_PER_RUNG`` times the rung's depth in its capture's own
    ladder, so a coarse lane's evidence is decoded before a fine lane's
    inside one global order and no barrier arranges it.

    The union takes the DEEPEST of the rungs it will read: an attempt is
    not cheaper than its dearest component, and here both captures sit at
    the same depth, which is the ordinary case.
    """
    from holo2.solve.place_sched import LANE_COST_PER_RUNG

    view = _View(
        {KEY: (_evidence("a:2/1", REGION_A), _evidence("a:8/1", REGION_A),
               _evidence("b:8/1", REGION_B))},
        {"a:2/1": _Footing(Fraction(2), "ab" * 32),
         "a:8/1": _Footing(Fraction(8), "ab" * 32),
         "b:2/1": _Footing(Fraction(2), "cd" * 32),
         "b:8/1": _Footing(Fraction(8), "cd" * 32)},
        {KEY: TileRecord(baselined=("a:2/1", "a:8/1"))})
    provider = payload.RealPayloadProvider(ROW)
    priced = {(item.route, item.scope.profile): item.premium
              for item in provider.expand(view, ExpansionRequest(entry="e"))}
    assert priced[(ROUTE_SCAN, "a:2/1")] == 0, "the coarsest lane is free"
    assert priced[(ROUTE_SCAN, "a:8/1")] == LANE_COST_PER_RUNG
    assert priced[(ROUTE_RETRY150, "a:2/1")] == 0
    assert priced[(ROUTE_RETRY150, "a:8/1")] == LANE_COST_PER_RUNG
    assert priced[(ROUTE_UNION, "8/1")] == LANE_COST_PER_RUNG, (
        "a union is priced by the deepest rung it reads")
    # And the price is PROVENANCE: two attempts differing only in lane
    # term would be one work id, which is what keeps a re-pricing from
    # forking a lineage's work.
    scan = next(item for item in provider.expand(
        view, ExpansionRequest(entry="e"))
        if (item.route, item.scope.profile) == (ROUTE_SCAN, "a:8/1"))
    assert replace(scan, premium=99).work_id == scan.work_id


def test_a_certified_key_mints_nothing_on_any_lane() -> None:
    """Certificates are footing-free, so they retire a tile everywhere.

    Worth pinning at stage 2 and not before: with one reading lane a
    certified tile could only have stopped enumerating once, and with
    several it would be several descriptors per commit if the frontier
    were keyed on anything but the OPEN set.
    """
    footings = {"a:2/1": _Footing(Fraction(2), "ab" * 32),
                "a:8/1": _Footing(Fraction(8), "ab" * 32)}
    evidence = {KEY: (_evidence("a:2/1", REGION_A),
                      _evidence("a:8/1", REGION_A))}
    assert _attempts(_View(evidence, footings, {KEY: TileRecord()}))

    class _Certified(_View):
        def open_work_keys(self) -> tuple[ResourceKey, ...]:
            return ()                     # the tile map's own OPEN answer

    assert not _attempts(_Certified(evidence, footings, {KEY: TileRecord()}))


def test_two_footings_of_one_capture_mint_no_union() -> None:
    """L2 as ELIGIBILITY: correlated footings have nothing to sum under."""
    view = _View(
        {KEY: (_evidence("a:2/1", REGION_A), _evidence("a:8/1", REGION_A))},
        {"a:2/1": _Footing(Fraction(2), "ab" * 32),
         "a:8/1": _Footing(Fraction(8), "ab" * 32)},
        {KEY: TileRecord()})
    assert not [rung for rung in _attempts(view) if rung[0] == ROUTE_UNION]


def test_equal_ppc_views_of_two_captures_mint_one_union() -> None:
    """PY2: the union's scope is the ppc the captures combine at."""
    view = _View(
        {KEY: (_evidence("a:2/1", REGION_A), _evidence("b:2/1", REGION_B),
               _evidence("b:8/1", REGION_B))},
        {"a:2/1": _Footing(Fraction(2), "ab" * 32),
         "b:2/1": _Footing(Fraction(2), "cd" * 32),
         "b:8/1": _Footing(Fraction(8), "cd" * 32)},
        {KEY: TileRecord()})
    minted = _attempts(view)
    assert [item for item in minted if item[0] == ROUTE_UNION] == [
        (ROUTE_UNION, "2/1")], "one union, at the ppc two captures reached"


def test_a_retry_exists_only_behind_its_own_failed_baseline() -> None:
    """PY3: ``baselined`` is the durable PER-FOOTING fact a retry needs.

    A tile-level ATTEMPTED rank could not say WHICH baseline failed —
    deriving retries from it armed BP-150 on footings whose baseline
    never ran (the 2026-08-11 review's P1) — and since tile family v4
    there is no such rank to be tempted by. The ``baselined`` gain is
    also the fact that WAKES: a spend has no version to sleep on, so an
    attempt gated on the ledger could never be re-offered.
    """
    evidence = {KEY: (_evidence("a:2/1", REGION_A),
                      _evidence("b:2/1", REGION_B))}
    footings = {"a:2/1": _Footing(Fraction(2), "ab" * 32),
                "b:2/1": _Footing(Fraction(2), "cd" * 32)}
    no_baseline = _View(evidence, footings, {KEY: TileRecord()})
    assert [item for item in _attempts(no_baseline)
            if item[0] == ROUTE_RETRY150] == [], (
        "a failed union leaves no baseline, so it arms no per-footing retry")
    one_baseline = _View(
        evidence, footings, {KEY: TileRecord(baselined=("a:2/1",))})
    assert [item for item in _attempts(one_baseline)
            if item[0] == ROUTE_RETRY150] == [(ROUTE_RETRY150, "a:2/1")], (
        "only the footing whose OWN scan ran a decoder and failed retries")


def test_a_detached_baseline_mints_no_retry() -> None:
    """A baselined footing this run never ingested has nothing to read."""
    view = _View(
        {KEY: (_evidence("a:2/1", REGION_A),)},
        {"a:2/1": _Footing(Fraction(2), "ab" * 32)},
        {KEY: TileRecord(baselined=("a:2/1", "gone:2/1"))})
    assert [item for item in _attempts(view) if item[0] == ROUTE_RETRY150]         == [(ROUTE_RETRY150, "a:2/1")]


def test_detached_evidence_is_skipped_not_fatal() -> None:
    """F-05/D5c: a piece whose footing is not resident derives nothing.

    The 2026-08-11 review proved the frontier used to raise ``KeyError``
    inside expansion — killing the whole session on any resume that was
    not handed every capture. Incomplete, not corrupt: skip it.
    """
    view = _View(
        {KEY: (_evidence("a:2/1", REGION_A), _evidence("gone:2/1", REGION_B))},
        {"a:2/1": _Footing(Fraction(2), "ab" * 32)},
        {KEY: TileRecord()})
    assert _attempts(view) == [(ROUTE_SCAN, "a:2/1")]


def test_a_key_with_no_evidence_mints_nothing() -> None:
    view = _View({KEY: ()}, {},
                 {KEY: TileRecord()})
    assert _attempts(view) == []


def test_each_attempt_reads_only_its_own_pieces() -> None:
    """§7: the read-set IS the identity, so a union names its components.

    Every attempt also names the work key and the evidence COLLECTION —
    the collection is the wake mechanism (M4), and asserting it here is
    what the review found the evidence-only filter missing.
    """
    view = _View(
        {KEY: (_evidence("a:2/1", REGION_A), _evidence("b:2/1", REGION_B),
               _evidence("b:8/1", REGION_B))},
        {"a:2/1": _Footing(Fraction(2), "ab" * 32),
         "b:2/1": _Footing(Fraction(2), "cd" * 32),
         "b:8/1": _Footing(Fraction(8), "cd" * 32)},
        {KEY: TileRecord()})
    provider = payload.RealPayloadProvider(ROW)
    read: dict[tuple[str, str], set[ResourceKey]] = {}
    for descriptor in provider.expand(view, ExpansionRequest(entry="e")):
        worker = provider.worker(view, descriptor)
        read[(descriptor.route, descriptor.scope.profile)] = set(
            worker.read_keys(view))
    from holo2.solve.records import evidence_collection_key
    collection = evidence_collection_key(KEY)
    for keys in read.values():
        assert KEY in keys, "the work key is part of every identity"
        assert collection in keys, "the collection wake rides every identity"
    pieces = {key for keys in read.values() for key in keys
              if key.kind == "evidence"}
    assert len(pieces) == 3
    assert read[(ROUTE_SCAN, "b:8/1")] & pieces == {
        _evidence("b:8/1", REGION_B)}
    assert read[(ROUTE_UNION, "2/1")] & pieces == {
        _evidence("a:2/1", REGION_A), _evidence("b:2/1", REGION_B)}


# ------------------------------------------------------ the counted exposure

def _spend(route: str, outcome: str, *, family: str = FAMILY_PAYLOAD,
           attempts: int = 1, exposures: int = 0,
           scope: str = "f") -> SpendRecord:
    identity: AttemptIdentity = ((KEY, 1),)
    return SpendRecord(WorkId(family, KEY, route, WorkScope(profile=scope)),
                       route, identity, outcome, attempts, exposures)


def test_crc_exposure_sums_the_monotone_counters() -> None:
    """Exposure is the rows' durable ``exposures``, never their outcome.

    HARDENING-SYSTEMIC-REVIEW P1 asked for a count; the 2026-08-11
    review then proved a latest-outcome filter LOSES it (a race-loser's
    ``already_certified`` folds over its own earlier ``crc_failed``).
    The counter survives any overwrite, so the arithmetic is exact.
    """
    exposure = payload.crc_exposure((
        _spend(ROUTE_SCAN, OUTCOME_CRC_PASSED, exposures=1),
        _spend(ROUTE_SCAN, OUTCOME_CRC_FAILED, attempts=3, exposures=3,
               scope="g"),
        _spend(ROUTE_RETRY150, OUTCOME_CRC_FAILED, exposures=1),
        _spend(ROUTE_SCAN, OUTCOME_BELOW_FLOOR, scope="h"),  # never decoded
        _spend("h3bis-word", OUTCOME_CRC_PASSED, family="place",
               exposures=1),                    # not the payload family
    ))
    assert exposure == {"spends": 3, "attempts": 5,
                        "by_route": {ROUTE_RETRY150: 1, ROUTE_SCAN: 4}}


def test_exposure_survives_a_non_crc_outcome_folding_over_it() -> None:
    """The review's P1 scenario, pinned: the budget once drawn stays."""
    raced = _spend(ROUTE_SCAN, "already_certified", attempts=2, exposures=1)
    exposure = payload.crc_exposure((raced,))
    assert exposure == {"spends": 1, "attempts": 1,
                        "by_route": {ROUTE_SCAN: 1}}, (
        "one decoder ran before the race was lost; the count keeps it")


def test_a_lineage_with_no_decode_is_zero_exposure() -> None:
    assert payload.crc_exposure(()) == {
        "spends": 0, "attempts": 0, "by_route": {}}
    assert payload.crc_exposure(
        (_spend(ROUTE_SCAN, "certified"),))["spends"] == 0, (
        "a provider whose decode carries no CRC never flags exposure")


# --------------------------------------------------- the race-loser's duty

def test_a_race_loser_still_contributes_its_observation() -> None:
    """§6: done projection needs every committed observation.

    An attempt that arms, loses the race to a certificate and takes the
    terminal early-out is the only worker that will ever look through
    its footing at this tile — retiring without writing loses the
    observation forever (the 2026-08-11 review's P2). The early-out
    grows ``observed_by`` as a monotone set; certified content never moves.
    """
    certified = TileRecord(minting=MintRef(_pose("a:2/1", REGION_A), "scan", "bp-60"),
                           observed_by=("a:2/1",), baselined=("a:2/1",))
    view = _View({KEY: (_evidence("b:2/1", REGION_B),)},
                 {"b:2/1": _Footing(Fraction(2), "cd" * 32)},
                 {KEY: certified})
    provider = payload.RealPayloadProvider(ROW)
    worker = provider.worker(view, next(
        d for d in provider.expand(view, ExpansionRequest(entry="e"))
        if d.route == ROUTE_SCAN))
    result = worker.run(view, ((KEY, 1),), ProgressSink("t"))
    assert result.outcome == "already_certified" and result.retire
    assert not result.exposure, "no decoder ran; no budget was drawn"
    assert len(result.writes) == 1
    merged = result.writes[0].record
    assert merged.certified
    assert merged.observed_by == ("a:2/1", "b:2/1")
    assert merged.baselined == ("a:2/1",)


def test_a_race_loser_with_nothing_new_writes_nothing() -> None:
    certified = TileRecord(minting=MintRef(_pose("a:2/1", REGION_A), "scan", "bp-60"),
                           observed_by=("b:2/1",))
    view = _View({KEY: (_evidence("b:2/1", REGION_B),)},
                 {"b:2/1": _Footing(Fraction(2), "cd" * 32)},
                 {KEY: certified})
    provider = payload.RealPayloadProvider(ROW)
    worker = provider.worker(view, next(
        d for d in provider.expand(view, ExpansionRequest(entry="e"))))
    result = worker.run(view, ((KEY, 1),), ProgressSink("t"))
    assert result.outcome == "already_certified" and result.writes == ()
