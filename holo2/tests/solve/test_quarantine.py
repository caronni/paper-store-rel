"""W5's verdict: what a constructed contradiction actually condemns.

The reduce's own arithmetic is ``test_words_reduce.py``; this file is
the CONSUMER half — the rulings, asserted over DURABLE records rather
than over return values, because "quarantined" is a fact a resume has to
be able to read back.

What is pinned here, one ruling at a time:

* **both sides, identically** (R6-Q16) — the fact's two contributor
  sets, the markings on the standing side, the born-quarantined decoded
  side, and the payload exclusion that follows from them;
* **DONE IS INVIOLABLE** (ruling 1) — a condemnation projects the same
  done array, cell for cell, and a CERTIFIED position is never
  quarantine's case at all;
* **staleness via quarantine data** (ruling 3) — a STAGED race: an
  in-flight reader takes its identity, the condemnation lands, and the
  identity no longer binds at the wall's existing check;
* **terminality** — the marking is one-way at the wall, and the fact is
  frozen under its position.

The contradiction itself is built the way v1 builds it
(``test_words_reduce.py``'s construction, which is v1's own): one tile's
word printed for the counter NEXT DOOR, so the decode is legal and its
address is wrong.
"""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import numpy as np
import pytest

from holo2.capture import CaptureRecord, FootingSpec, RegionRecord
from holo2.capture import capture_key, region_key
from holo2.core import CommitRefusal, ResourceKey
from holo2.core.blobs import stage_array
from holo2.core.commit import CommitBatch, CommitEngine, Write
from holo2.core.store import Store
from holo2.format import pilots
from holo2.solve import quarantine
from holo2.solve.contradiction import WordContradiction, contradiction_key
from holo2.solve.geometry import CellLattice, scale_translation_affine
from holo2.solve.payload import route_evidence_keys
from holo2.solve.records import (CalibrationRecord, EvidenceObservation,
                                 HeldoutGate, MintRef, PoseRecord, TileRecord,
                                 WindowRecord, WindowStatus, calibration_key,
                                 evidence_key, pack_observed_cells, pose_key,
                                 tile_key, window_key)
from holo2.solve.tilemap import StoreIndex, TileMap, project_done
from holo2.solve.words import known_position_words
from holo2.solve.place_model import PilotObservation
from holo2.format.format_v1 import tile_format

SPEC = tile_format("c2-k-r0550", (8, 8))
STREAM = "main"

CAPTURE = "ef" * 32
FOOTING = "cap:1/1"
OTHER_FOOTING = "cap:2/1"
REGION = region_key(CAPTURE, (0, 0), 8, (128, 128))
LATTICE = CellLattice((0, 0), Fraction(1), (128, 128))
SUPPORT = np.ones((128, 128), bool)
IDENTITY = scale_translation_affine(1.0, (0.0, 0.0))

_MASK = stage_array(np.ones(16, np.uint8))
_PARAMS = stage_array(np.zeros(2, np.float64))
_BITS = stage_array(np.zeros(4, np.uint8))
_SEEN = stage_array(pack_observed_cells(np.ones(4, bool)))
CALIBRATION = calibration_key(capture_key(CAPTURE), "pava-v1",
                              _PARAMS.ref.sha256)

#: The contradicted position and a second one the same pose observed —
#: the second is what proves quarantine condemns the WHOLE placement.
SUBJECT = (0, 0, 0)
SIBLING = (0, 0, 1)


def _window_key(extent: tuple[int, int, int, int],
                footing: str = FOOTING) -> ResourceKey:
    return window_key(footing, REGION, extent)


def _pose(extent: tuple[int, int, int, int], *,
          footing: str = FOOTING) -> PoseRecord:
    return PoseRecord(_window_key(extent, footing), footing, 0, IDENTITY)


STANDING = _pose((0, 0, 64, 64))
ARRIVING = _pose((0, 64, 64, 128))


def _ground() -> list[Write]:
    return [
        Write(capture_key(CAPTURE), CaptureRecord(
            source_sha256=CAPTURE, dpi_true=1200.0, shape_px=(128, 128),
            dtype="uint8", channels=1, platen_backing=200.0,
            footings=(FootingSpec(FOOTING, Fraction(1), CAPTURE),
                      FootingSpec(OTHER_FOOTING, Fraction(2), CAPTURE)))),
        Write(REGION, RegionRecord(
            capture_sha256=CAPTURE, support_mask_ref=_MASK.ref, pitch_in_vote=Fraction(8, 600),
            support_origin_px=(0, 0), support_step_px=8,
            support_extent_px=(128, 128))),
        Write(CALIBRATION, CalibrationRecord(
            scope=capture_key(CAPTURE), algorithm="pava-v1",
            params_ref=_PARAMS.ref,
            heldout=HeldoutGate(adopted=True, logloss_delta=-0.1))),
    ]


def _piece(pose: PoseRecord, address: tuple[int, int, int],
           footing: str = FOOTING) -> Write:
    page, ty, tx = address
    return Write(
        evidence_key(footing, page, ty, tx, STREAM, pose.resource_key()),
        EvidenceObservation(footing, page, ty, tx, STREAM,
                            pose.resource_key(), _BITS.ref, _SEEN.ref,
                            CALIBRATION))


def _seed(store: Store, *, certified: tuple[tuple[int, int, int], ...] = (),
          extra: tuple[Write, ...] = ()) -> CommitEngine:
    """Commit the ground, ONE standing placement, and its two pieces."""
    engine = CommitEngine(store)
    writes = _ground()
    writes.append(Write(_window_key(STANDING.window_id.parts and
                                    (0, 0, 64, 64)),
                        WindowRecord(FOOTING, REGION, (0, 0, 64, 64),
                                     WindowStatus.ACTIVE)))
    writes.append(Write(STANDING.resource_key(), STANDING))
    writes.append(_piece(STANDING, SUBJECT))
    writes.append(_piece(STANDING, SIBLING))
    for address in (SUBJECT, SIBLING):
        page, ty, tx = address
        record = (TileRecord(minting=MintRef(STANDING.resource_key(), "scan",
                                             "fixture-decoder"),
                             bits_ref=_BITS.ref, metadata_bit=1,
                             observed_by=(FOOTING,))
                  if address in certified else TileRecord(
                      observed_by=(FOOTING,)))
        writes.append(Write(tile_key(page, ty, tx, STREAM), record))
    engine.apply(CommitBatch(writes=tuple(writes) + extra,
                             blobs=(_MASK, _PARAMS, _BITS, _SEEN)))
    return engine


class _View:
    """Exactly the four plane reads ``quarantine`` makes, over a store."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._index = StoreIndex.build(store)
        self._tiles = TileMap(self._index, (STREAM,), (8, 8))

    def index(self) -> StoreIndex:
        return self._index

    def record(self, key: ResourceKey) -> object | None:
        return self._store.get(key)

    def tile(self, key: ResourceKey) -> TileRecord | None:
        return self._tiles.record(key)

    def evidence_on(self, key: ResourceKey) -> tuple[ResourceKey, ...]:
        return self._index.evidence_by_tile.get(key, ())

    # what the payload exclusion asks beside the three above
    def has_footing(self, footing_id: str) -> bool:
        return True


def _contradicting_words(page: int = 0, tile_yx: tuple[int, int] = (0, 0)):
    """v1's construction: this position's word, printed one counter over."""
    expected = SPEC.tile_counter(page, *tile_yx)
    values = pilots.word_values(SPEC.seed, (expected + 1,), SPEC.plane)[0]
    return known_position_words(tuple(
        PilotObservation(page, tile_yx, site, int(values[site]), 2.0,
                         CAPTURE, ARRIVING.resource_key())
        for site in range(pilots.N_WORD_SITES)), SPEC)


def _verdict(view: _View) -> quarantine.Contradicted:
    return quarantine.contradiction_writes(
        view, footing_id=FOOTING, stream=STREAM,
        pose_id=ARRIVING.resource_key(), words=_contradicting_words())


def _fire(verdict: quarantine.Contradicted) -> CommitBatch:
    """The whole batch a contradicting fire proposes (``place_job``).

    The verdict's writes plus the two the JOB adds: its own pose, BORN
    QUARANTINED so the fact's contributor set names a record, and the
    window retired with the reason. They ride one batch because the
    fact's F-07 reference resolves against the decided batch.
    """
    return CommitBatch(writes=verdict.writes + (
        Write(ARRIVING.resource_key(), replace(ARRIVING, quarantined=True)),
        Write(_window_key((0, 64, 64, 128)),
              WindowRecord(FOOTING, REGION, (0, 64, 64, 128),
                           WindowStatus.RETIRED,
                           quarantine.OUTCOME_CONTRADICTION))))


# ------------------------------------------------- both sides, identically

def test_a_constructed_contradiction_names_both_sides_in_full(
        new_store) -> None:
    engine = _seed(new_store())
    verdict = _verdict(_View(engine.store))

    fact, = verdict.facts
    assert fact.resource_key() == contradiction_key(FOOTING, 0, 0, 0)
    assert fact.expected_counter == SPEC.tile_counter(0, 0, 0)
    assert fact.decoded_counter == fact.expected_counter + 1
    # BOTH sides, each a full contributor set in MintRef's own shape.
    assert fact.decoded_contributors == (ARRIVING.resource_key(),)
    assert fact.geometry_contributors == (STANDING.resource_key(),)
    assert fact.condemned() == tuple(sorted(
        {ARRIVING.resource_key(), STANDING.resource_key()}))


def test_the_condemnation_marks_the_whole_standing_placement(
        new_store) -> None:
    """v1 condemns the PATCH, not the tile: every piece of it goes."""
    engine = _seed(new_store())
    verdict = _verdict(_View(engine.store))
    marked = {write.key: write.record for write in verdict.writes}

    assert marked[STANDING.resource_key()] == replace(STANDING,
                                                      quarantined=True)
    for address in (SUBJECT, SIBLING):
        page, ty, tx = address
        key = evidence_key(FOOTING, page, ty, tx, STREAM,
                           STANDING.resource_key())
        assert quarantine.is_quarantined(marked[key])
    assert len(verdict.writes) == 4                # fact, pose, two pieces


def test_both_sides_are_durably_quarantined_and_leave_the_payload(
        new_store) -> None:
    """The whole shape, committed: R6-Q16 read back off the store.

    The DECODED side is committed BORN QUARANTINED — retained as a
    record so the fact's contributor set names something real, never
    offered, and emitting no evidence of its own — and the GEOMETRY side
    is marked in place. Neither is preferred; both lose.
    """
    engine = _seed(new_store())
    engine.apply(_fire(_verdict(_View(engine.store))))

    store = engine.store
    assert quarantine.is_quarantined(store.get(STANDING.resource_key()))
    assert quarantine.is_quarantined(store.get(ARRIVING.resource_key()))
    assert store.get(contradiction_key(FOOTING, 0, 0, 0)) is not None
    # The arriving side wrote NO evidence at all, which is why there is
    # nothing of its to exclude.
    assert not quarantine.evidence_of_pose(_View(store),
                                           ARRIVING.resource_key())
    # The payload exclusion: the condemned pieces leave the read-set, so
    # they leave the attempt's IDENTITY too.
    view = _View(store)
    for address in (SUBJECT, SIBLING):
        page, ty, tx = address
        assert route_evidence_keys(view, tile_key(page, ty, tx, STREAM),
                                   "scan", FOOTING) == ()


# ------------------------------------------------------ DONE IS INVIOLABLE

def _done(store: Store) -> np.ndarray:
    index = StoreIndex.build(store)
    return project_done(index, TileMap(index, (STREAM,), (8, 8)),
                        capture_sha256=CAPTURE, region_id=REGION,
                        lattice=LATTICE, support=SUPPORT,
                        pose_ids=tuple(index.poses)).cells


def test_quarantining_a_pose_moves_zero_done_pixels(new_store) -> None:
    """Ruling 1, as CODE: done pixels are certificate-backed.

    The projection does not know ``quarantine`` exists — that is the
    whole argument, and it is what keeps the F-23 cache key (committed
    poses x certified keys) correct, since a condemnation moves neither
    count.

    The write here is deliberately ADVERSARIAL: it condemns a pose whose
    own tile is certified, which is the one thing
    :func:`contradiction_writes` refuses to do (ruling 1's jurisdiction,
    pinned below). It is the only configuration in which the projection
    and the marking could possibly have disagreed, so it is the one
    worth pinning — a done pixel must survive even a marking that should
    never have been made.
    """
    engine = _seed(new_store(), certified=(SUBJECT,))
    before = _done(engine.store)
    assert before.any(), "the fixture projects no done pixels to compare"

    engine.apply(CommitBatch(writes=(
        Write(STANDING.resource_key(), replace(STANDING, quarantined=True)),)))

    assert np.array_equal(_done(engine.store), before)


def test_a_certified_position_is_vindicated_and_never_quarantined(
        new_store) -> None:
    """Ruling 1's jurisdiction: quarantine touches UNCERTIFIED material.

    "If payload is decoded, we know with much higher probability the
    correct address" — so a contradiction over a certified tile is the
    fatal layer's case and this layer writes nothing at all.
    """
    engine = _seed(new_store(), certified=(SUBJECT,))
    verdict = _verdict(_View(engine.store))
    assert not verdict and verdict.writes == ()


# --------------------------------------------------- staleness, as a race

def test_an_in_flight_reader_of_condemned_evidence_dies_stale(
        new_store) -> None:
    """Ruling 3, STAGED: identity taken, condemnation lands, identity dies.

    The read-set is the one a payload attempt really binds — the pieces
    ``route_evidence_keys`` hands it (§7, PROVIDERS PY2) — so this is
    the actual race and not a proxy for it: the reader is mid-flight
    when the write it depends on moves, and the wall's EXISTING
    staleness check discards its proposal. No new mechanism was built
    for this; the condemnation IS the version bump.
    """
    engine = _seed(new_store())
    page, ty, tx = SUBJECT
    work = tile_key(page, ty, tx, STREAM)
    keys = route_evidence_keys(_View(engine.store), work, "scan", FOOTING)
    assert keys, "the reader must be reading something for the race to exist"

    identity = engine.attempt_identity(keys)        # the fire is in flight
    assert engine.is_current(keys, identity)        # ... and would land now

    engine.apply(_fire(_verdict(_View(engine.store))))

    assert not engine.is_current(keys, identity)    # ... and now cannot
    # And it never comes back: the pieces have left the read-set, so the
    # re-armed attempt is a DIFFERENT attempt over the survivors.
    assert route_evidence_keys(_View(engine.store), work, "scan",
                               FOOTING) == ()


# ------------------------------------------------------------ terminality

def test_the_marking_is_one_way_at_the_wall(new_store) -> None:
    engine = _seed(new_store())
    condemned = replace(STANDING, quarantined=True)
    engine.apply(CommitBatch(writes=(
        Write(STANDING.resource_key(), condemned),)))
    with pytest.raises(CommitRefusal, match="one direction"):
        engine.apply(CommitBatch(writes=(
            Write(STANDING.resource_key(), STANDING),)))


def test_a_contradiction_is_frozen_under_its_position(new_store) -> None:
    engine = _seed(new_store())
    verdict = _verdict(_View(engine.store))
    engine.apply(_fire(verdict))
    fact, = verdict.facts
    engine.apply(CommitBatch(writes=(
        Write(fact.resource_key(), fact),)))        # an equal write: a no-op
    with pytest.raises(CommitRefusal, match="frozen"):
        engine.apply(CommitBatch(writes=(
            Write(fact.resource_key(), replace(fact, errors=fact.errors + 1)),
        )))


def test_a_contradiction_that_agrees_with_itself_is_unrepresentable() -> None:
    with pytest.raises(ValueError, match="must DIFFER"):
        WordContradiction(footing_id=FOOTING, page=0, ty=0, tx=0,
                          expected_counter=7, decoded_counter=7, errors=0,
                          erasures=0, decoded_contributors=(
                              ARRIVING.resource_key(),))
    with pytest.raises(ValueError, match="either side"):
        WordContradiction(footing_id=FOOTING, page=0, ty=0, tx=0,
                          expected_counter=7, decoded_counter=8, errors=0,
                          erasures=0)
    with pytest.raises(ValueError, match="pose keys"):
        WordContradiction(footing_id=FOOTING, page=0, ty=0, tx=0,
                          expected_counter=7, decoded_counter=8, errors=0,
                          erasures=0,
                          decoded_contributors=(tile_key(0, 0, 0, STREAM),))


# ------------------------------------------------------------ ruling 4

def test_the_condemnation_never_reaches_across_footings(new_store) -> None:
    """Ruling 4: the geometry side is drawn AT THIS FOOTING and no other.

    A second footing observing the same printed tile is not compared —
    the certificate layer is the only cross-scope arbiter, and it is
    fatal.
    """
    other = _pose((0, 0, 64, 64), footing=OTHER_FOOTING)
    engine = _seed(new_store(), extra=(
        Write(_window_key((0, 0, 64, 64), OTHER_FOOTING),
              WindowRecord(OTHER_FOOTING, REGION, (0, 0, 64, 64),
                           WindowStatus.ACTIVE)),
        Write(other.resource_key(), other),
        _piece(other, SUBJECT, OTHER_FOOTING)))

    fact, = _verdict(_View(engine.store)).facts
    assert fact.geometry_contributors == (STANDING.resource_key(),)
    assert other.resource_key() not in fact.condemned()
