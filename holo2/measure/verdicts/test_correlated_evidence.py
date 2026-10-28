"""VERDICT 7 (runs banded + streaming): LLRs never sum two views of one capture.

THE WAVE'S NON-NEGOTIABLE GUARD (H4-LANES ruling 6, user, 2026-08-17):
"the correlated-evidence law gets its verdict-level pin BACK before
multi-footing evidence is reachable."

The law is L2 and it is old: two footings of one capture are two SAMPLINGS
of one physical acquisition, so their LLRs are correlated and summing them
would manufacture confidence the paper never carried — the false-accept
budget L5 declares would be a fiction. holo2 has always encoded it
STRUCTURALLY rather than as a check: a union descriptor exists only at a
ppc value **two or more distinct captures** reached, so the illegal sum
has nothing to run under (``solve.payload.union_tags``).

What made that a paper guarantee until this wave is that no capture had
two reading lanes: ``place_shared.working_footing_id`` exited every rung
but one, so a second footing of one capture could not carry evidence at
all, and since the measure cleanup the law's only defence was one unit
test over a synthetic view. Stage 2 makes it reachable — which is exactly
when a verdict has to hold it.

RUN-ONCE, CHECK-MANY (the verdicts' own law): TWO runs now, no decode
this file drives, and together they still hold every shape the law
needs — the run-union merge (2026-08-17, wall-time ruling: run union's
own decode cost ~75s of the suite's ~131s pre-subdivision wall) folded
the positive shape into run streaming's own sheet 0 rather than keeping
a third fixture (``conftest.run_streaming`` has the corruption and the
measured cost trade):

* **run banded — ONE capture, TWO rungs.** Every ppc on this sheet is
  reached by exactly one capture, so the lawful union count is ZERO and
  the guard is an absolute: no union descriptor was ever spent, no
  certificate was ever minted by one. The pre-condition is asserted
  first — tiles really do carry evidence from BOTH rungs of the one
  capture — so the zero is a refusal and not an absence of opportunity.
* **run streaming — THREE captures over TWO pages, one page scanned
  TWICE.** Sheet 1 is observed by exactly one capture, so every one of
  its (tile, ppc) pairs is lonely — the same shape run banded's own
  rungs are, exercised again on a different mechanism (a whole other
  PAGE rather than a second rung). Sheet 0 is observed by TWO captures,
  under a narrow cut of run banded's own band
  (``STREAM_UNION_BAND``, same print seed, a different sensor draw):
  the shape a union is lawful in. Here the claim is positive — every
  union that ran named a ppc two DISTINCT capture shas reached, and
  every certificate a union minted cites contributors sitting on at
  least two of them.

DIED WITH THE MERGE, stated rather than silently dropped: run
streaming's own former control, "two captures, different sheets, zero
for the OTHER reason" (asserting NO work key anywhere in the run is
ever observed twice). That premise is now FALSE of the merged fixture
— sheet 0's tiles ARE observed twice, by construction — so the test
would be pinning something the fixture no longer does. What it wanted
to separate ("the law refused" vs. "nothing collided") still gets
exercised: sheet 1's lonely pairs are exactly the "nothing collided"
shape, read inside the SAME run that also holds the positive collision,
via ``test_a_ppc_reached_by_one_capture_mints_no_union`` below — which
is a strictly stronger arrangement than a dedicated all-different-pages
run, since it proves the two mechanisms coexist in one store rather
than only in separate ones.

Everything is read off the store's own evidence records, tile records and
spend ledger — and off the CAPTURE RECORDS for the footing ladder, never
off the session plane, because a closed run is terminal and a terminal
session opens no captures at all (§5.5). No new record family, no
instrumentation, nothing staged: what is asserted is what the durable
state says happened.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from conftest import PageRun, StreamRun

from holo2.capture import catalog_captures
from holo2.solve import KIND_EVIDENCE, parse_evidence_key
from holo2.solve.payload import (FAMILY_PAYLOAD, ROUTE_RETRY150,
                                 ROUTE_SCAN, ROUTE_UNION, ppc_tag)
from holo2.solve.records import EvidenceObservation
from holo2.solve.tilemap import StoreIndex


def _ladder(store: Any) -> dict[str, tuple[str, str]]:
    """Footing id -> (its ppc tag, its capture sha), off CAPTURE RECORDS.

    The durable answer, and the only one available on a terminal state:
    a closed session ingests nothing, so its plane holds no captures, but
    every footing it ever read is still a field of the capture record it
    was declared on (§5.1).
    """
    return {str(footing.footing_id): (ppc_tag(footing.ppc),
                                      str(footing.capture_sha256))
            for ingested in catalog_captures(store)
            for footing in ingested.record.footings}


def _evidence_by_tile(store: Any) -> dict[Any, list[str]]:
    """Per work key, the footing each committed observation was read on.

    Read off the evidence RECORDS and their keys together, because the
    footing appears in both (§5.4 puts it in the key) and a disagreement
    between the two would itself be the defect this file is about.
    """
    index = StoreIndex.build(store)
    seen: dict[Any, list[str]] = {}
    for work_key, evidence in index.evidence_by_tile.items():
        rows: list[str] = []
        for key in evidence:
            footing_id, page, ty, tx, stream, _pose = parse_evidence_key(key)
            record = store.get(key)
            assert isinstance(record, EvidenceObservation), key
            # ONE FOOTING PER OBSERVATION, said twice and agreeing: an
            # observation is a piece read through one lane, and the key
            # and the record are two independent statements of which.
            assert record.footing_id == footing_id, (
                f"{key}: the key names footing {footing_id} and the record "
                f"names {record.footing_id}")
            assert (record.page, record.ty, record.tx, record.stream) == (
                page, ty, tx, stream)
            rows.append(str(footing_id))
        seen[work_key] = rows
    return seen


def _captures_per_ppc(ladder: dict[str, tuple[str, str]],
                      footings: list[str]) -> dict[str, set[str]]:
    """The distinct acquisitions these footings reach, per ppc value."""
    per_ppc: dict[str, set[str]] = {}
    for footing_id in footings:
        tag, capture = ladder[footing_id]
        per_ppc.setdefault(tag, set()).add(capture)
    return per_ppc


def _payload_spends(store: Any, route: str) -> list[Any]:
    return [row for row in store.ledger.entries()
            if row.worker_id.family == FAMILY_PAYLOAD and row.route == route]


def _no_union_anywhere(store: Any) -> None:
    """THE GUARD, as an absolute: not one union attempt, not one mint."""
    unions = _payload_spends(store, ROUTE_UNION)
    assert not unions, (
        f"{len(unions)} union attempt(s): "
        f"{sorted({str(row.worker_id.scope.profile) for row in unions})}")
    minted = Counter(record.minting.route
                     for record in StoreIndex.build(store).tiles.values()
                     if record.minting is not None)
    assert minted and ROUTE_UNION not in minted, dict(minted)
    assert set(minted) <= {ROUTE_SCAN, ROUTE_RETRY150}, dict(minted)


# ------------------------------------- run banded: one capture, two rungs

def test_a_single_capture_read_through_two_rungs_mints_no_union(
        run_banded: PageRun) -> None:
    """THE GUARD, in its absolute form.

    The pre-condition first, because a zero with no opportunity behind it
    proves nothing: this run's tiles carry evidence from BOTH rungs of
    the one capture, so the illegal sum is available as DATA. It was
    never made, on any tile, by any attempt, and no certificate cites
    one.
    """
    with run_banded.open() as session:
        store = session.store
        ladder = _ladder(store)
        by_tile = _evidence_by_tile(store)
        assert by_tile, "the run committed no evidence at all"

        assert len({capture for _tag, capture in ladder.values()}) == 1, (
            "run banded is supposed to be ONE capture; this is a different "
            "arm")
        multi_lane = [key for key, rows in by_tile.items()
                      if len(set(rows)) > 1]
        assert multi_lane, (
            "no tile carries evidence from two rungs of the one capture, so "
            "the correlated sum was never even available — this guard would "
            "be vacuous")

        # THE GUARD. Not "no union summed wrongly": no union ATTEMPT
        # exists at all, because eligibility is structural.
        _no_union_anywhere(store)

        # And every attempt that DID run named exactly one footing, which
        # is what "an observation is a piece read through one lane" means
        # on the scheduling side.
        for route in (ROUTE_SCAN, ROUTE_RETRY150):
            for row in _payload_spends(store, route):
                profile = str(row.worker_id.scope.profile)
                assert profile in ladder, (
                    f"{route} scoped to {profile!r}, which is not a footing")


def test_the_lanes_really_are_two_readings_of_one_acquisition(
        run_banded: PageRun) -> None:
    """Why the guard matters HERE and did not before: the shape exists.

    Both rungs of this capture certified tiles, and both wrote evidence
    on tiles the other also observed. That is precisely the correlated
    pair the law forbids summing — carried as durable data, decoded
    independently, and never combined.
    """
    with run_banded.open() as session:
        store = session.store
        by_tile = _evidence_by_tile(store)
        lanes = {footing for rows in by_tile.values() for footing in rows}
        assert len(lanes) == 2, f"{len(lanes)} reading lane(s): {lanes}"
        index = StoreIndex.build(store)
        observed = Counter(str(footing)
                           for record in index.tiles.values()
                           for footing in record.observed_by)
        assert set(observed) == lanes, (
            "a lane wrote evidence that no tile record observed")
        assert all(count > 0 for count in observed.values())


# DIED WITH THE MERGE (module docstring has the reason):
# ``test_two_captures_of_DIFFERENT_sheets_mint_no_union_either`` used to
# live here, asserting no work key in run streaming is EVER observed by
# two captures — true before the merge (sheets were different pages, and
# that was the whole point), false after it (sheet 0 now is). Its
# "nothing collided" half survives inside
# ``test_a_ppc_reached_by_one_capture_mints_no_union`` below, read off
# sheet 1's lonely pairs in the SAME run that also holds the positive
# collision.


# ---------------- run streaming: sheet 0's two scans (LAWFUL) --------------

def test_every_union_named_two_distinct_captures_at_one_ppc(
        run_streaming: StreamRun) -> None:
    """L2's positive half, on the run where the sum is LAWFUL.

    Every union attempt is scoped to a ppc tag; the evidence it reads is
    every resident piece at that ppc, and the law is that those pieces
    come from at least two DISTINCT acquisitions. Recomputed here from
    the finished state rather than trusted from the descriptor, so a
    provider that started minting unions on a correlated pair would fail
    here even though its own eligibility test said yes.
    """
    with run_streaming.open() as session:
        store = session.store
        ladder = _ladder(store)
        by_tile = _evidence_by_tile(store)
        unions = _payload_spends(store, ROUTE_UNION)
        assert unions, (
            "sheet 0's two scans summed nothing at all, so this half of "
            "the guard is vacuous — check the fixture, not the law")
        for row in unions:
            tag = str(row.worker_id.scope.profile)
            rows = by_tile.get(row.worker_id.subject, [])
            captures = _captures_per_ppc(ladder, rows).get(tag, set())
            assert len(captures) >= 2, (
                f"union at ppc {tag} on {row.worker_id.subject} read "
                f"{len(captures)} capture(s): a sum across two views of one "
                "acquisition")


def test_a_ppc_reached_by_one_capture_mints_no_union(
        run_banded: PageRun, run_streaming: StreamRun) -> None:
    """THE ELIGIBILITY FACT, across every shape the file holds.

    A (tile, ppc) pair reached by ONE acquisition may not be summed, and
    the rule is eligibility rather than a check: no descriptor exists, so
    there is nothing to run and nothing to get wrong. Asserted over both
    runs at once because neither alone has both kinds of pair — run
    streaming's sheet 0 reaches SOME ppcs twice (which is exactly what
    makes it the LAWFUL half, since the run-union merge), while every
    pair on run banded and on run streaming's sheet 1 is single-capture.
    Together they hold both halves: the lonely pairs exist in quantity,
    and not one of them carries a spend.
    """
    lonely = 0
    for run in (run_banded, run_streaming):
        with run.open() as session:
            store = session.store
            ladder = _ladder(store)
            spent: set[tuple[Any, str]] = {
                (row.worker_id.subject, str(row.worker_id.scope.profile))
                for row in _payload_spends(store, ROUTE_UNION)}
            here: list[tuple[Any, str]] = []
            for work_key, rows in _evidence_by_tile(store).items():
                for tag, captures in _captures_per_ppc(ladder, rows).items():
                    if len(captures) == 1:
                        here.append((work_key, tag))
            collisions = [pair for pair in here if pair in spent]
            assert not collisions, (
                f"{len(collisions)} union attempt(s) at a ppc one capture "
                f"reached: {collisions[:3]}")
            lonely += len(here)
    assert lonely, (
        "no (tile, ppc) pair anywhere was reached by a single capture, so "
        "the eligibility rule is not exercised at all")


def test_run_streaming_certified_nothing_wrong(run_streaming: StreamRun) -> None:
    """DESIGN §12 on the arm that sums ACROSS acquisitions. Never relaxed.

    The standing bar rides every run in this directory, and it matters
    most here: a union is the one attempt whose decoder input is built
    from more than one capture, so an unlawful sum would show up as a
    wrong certificate before it showed up anywhere else. Page-aware
    (run streaming is a two-page VOLUME, unlike run union's single
    page), same discipline ``test_honesty.py`` uses for run partial.
    """
    import numpy as np

    from holo2.solve import parse_tile_key
    from holo2.solve.tilemap import TileMap

    volume = run_streaming.volume
    with run_streaming.open() as session:
        tiles = TileMap(StoreIndex.build(session.store),
                        volume.row.stream_ids, volume.tiles_yx)
        certified = tiles.certified_keys()
        assert certified
        for key in certified:
            page, ty, tx, _stream = parse_tile_key(key)
            record = tiles.record(key)
            np.testing.assert_array_equal(
                session.store.read_array(record.bits_ref),
                volume.truth_bits(page, ty, tx))
            assert record.metadata_bit == volume.truth_metadata_bit(
                page, ty, tx)


def test_no_union_sums_condemned_evidence(run_streaming: StreamRun) -> None:
    """W5 on the arm that sums ACROSS acquisitions (R6-Q16).

    A union is the one attempt whose decoder input is built from more
    than one capture, so it is where an excluded piece would be hardest
    to notice: the sum would still produce a plausible LLR. The
    exclusion sits in ``route_evidence_keys``, which is the READ-SET —
    so a condemned piece is not merely skipped by the decoder, it is not
    part of the attempt's identity at all.

    On this fixture the count is ZERO on both sides (nothing is
    condemned, so nothing can be summed), which is the same conditional
    shape as the union-provenance verdict below: the zero says the
    sheets were good, and a non-zero would say the law had broken.
    """
    with run_streaming.open() as session:
        store = session.store
        index = StoreIndex.build(store)
        condemned = {key for key, pose in index.poses.items()
                     if pose.quarantined}
        pieces = [key for key in store.keys() if key.kind == KIND_EVIDENCE]
        assert pieces, "no evidence at all, so nothing is being checked"
        for key in pieces:
            piece = store.get(key)
            if piece.quarantined:
                assert piece.pose_id in condemned, (
                    "a piece is condemned but its pose is not — the two "
                    "halves of one marking disagree")
        for record in index.tiles.values():
            mint = record.minting
            if mint is None:
                continue
            assert not ({mint.pose_id, *mint.contributors} & condemned), (
                "a certificate stands on a condemned placement")


def test_a_union_certificate_cites_at_least_two_acquisitions(
        run_streaming: StreamRun) -> None:
    """The provenance half: a certificate says which captures made it.

    ``MintRef.contributors`` is M10's full provenance set, and for a
    union it is what a later quarantine would walk. If a union ever
    minted from one acquisition's own lanes, the contributors would sit
    on one capture — so this reads them back through their poses and
    counts the captures.

    RECORDED, not required: a union only CERTIFIES where the scans it
    sums reach the tile the ordinary routes could not, so a clean
    fixture can legitimately mint none. The claim is conditional and the
    count is reported, because a zero here says "the sheets were good",
    while a union certificate citing one acquisition would say the law
    had broken.
    """
    with run_streaming.open() as session:
        store = session.store
        ladder = _ladder(store)
        index = StoreIndex.build(store)
        union_certificates = [record for record in index.tiles.values()
                              if record.minting is not None
                              and record.minting.route == ROUTE_UNION]
        for record in union_certificates:
            mint = record.minting
            assert mint is not None
            witnesses = set(mint.contributors) or {mint.pose_id}
            captures = set()
            for pose_id in witnesses:
                pose = index.poses.get(pose_id)
                assert pose is not None, pose_id
                captures.add(ladder[str(pose.footing_id)][1])
            assert len(captures) >= 2, (
                f"a union certificate cites {len(captures)} acquisition(s): "
                f"{sorted(witnesses)}")
