"""The fact snapshot and the resume replay.

The pin that matters most is the subjects one: a family replayed out of
a snapshot has to birth exactly the subjects the same facts birth when
they are folded live, because that is the entire resume mechanism —
there is no separate replay path, no journal and no bookmark
persistence, only `_ingest` in a canonical order.  The replay event is
held to the same standard from the other side: it must change nothing.
"""

from __future__ import annotations

import dataclasses
import types
from pathlib import Path

import numpy as np
import pytest

from holo3 import data, engine, snapshot
from holo3.plugins import calibrate
from holo3.tests import _h3_facts, _h3_support

DURABLE = ("CaptureSurvey", "Window", "LatticeSeed", "Placement",
           "CtxOutcome", "PlaneField", "PooledColorCtx", "Certificate")

# what the store folds and the snapshot deliberately leaves behind
LEFT_BEHIND = ("Capture", "PlaceOutcome", "WindowEvidence",
               "ColorEvidenceRow", "ColorCtxPopulation", "RefineOutcome",
               "AttemptFact",
               # ColorLaneFit is scheduling-shaped state, like
               # PlaceOutcome: the head-fit ordinal and assembly-debt
               # coverage price the lane's re-fires. On resume the head
               # re-fits once per lane from regenerated evidence, and
               # the never-price-at-zero rule keeps that first re-fit
               # at full price.
               "ColorLaneFit")

REGION_KEY = (_h3_facts.CAPTURE_ID, 0, 0)


def _attempt() -> data.AttemptFact:
    """The probe attempt, on this fixture's own lane — `_h3_facts.attempt`
    names a capture the seeded store has never heard of."""
    return dataclasses.replace(_h3_facts.attempt(),
                               components=((_h3_facts.CAPTURE_ID, 0),))


def _probe(name: str) -> object:
    return _attempt() if name == "AttemptFact" else _h3_facts.BUILD[name]()


def _standing_ctx_outcome() -> calibrate.CtxOutcome:
    """A CtxOutcome shaped the way `collect` emits one: the standing
    region fit alone, with no evidence rows riding along."""
    return calibrate.CtxOutcome(REGION_KEY, (), (), _h3_facts.region_ctx())


def _durable_facts() -> tuple[object, ...]:
    built = []
    for name in DURABLE:
        built.append(_standing_ctx_outcome() if name == "CtxOutcome"
                     else _h3_facts.BUILD[name]())
    return tuple(built)


def _same(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, np.ndarray):
        return (left.dtype == right.dtype and left.shape == right.shape
                and np.array_equal(left, right))
    if dataclasses.is_dataclass(left):
        return all(_same(getattr(left, held.name), getattr(right, held.name))
                   for held in dataclasses.fields(left))
    if isinstance(left, tuple):
        return (len(left) == len(right)
                and all(_same(a, b) for a, b in zip(left, right)))
    return left == right


def test_the_durable_families_are_the_declared_set():
    _h3_support.assert_golden(
        "snapshot families",
        tuple(cls.__name__ for cls in snapshot.FAMILIES), DURABLE)


def test_the_families_left_behind_are_still_families_the_store_folds():
    folded = set(_h3_facts.BUILD)
    assert set(DURABLE) | set(LEFT_BEHIND) == folded, sorted(
        folded.symmetric_difference(set(DURABLE) | set(LEFT_BEHIND)))
    assert not set(LEFT_BEHIND) & {cls.__name__
                                   for cls in snapshot.FAMILIES}


def test_every_durable_family_round_trips_byte_for_byte(tmp_path: Path):
    facts = _durable_facts()
    path = tmp_path / snapshot.NAME
    snapshot.write(path, facts)
    back = snapshot.read(path)
    assert len(back) == len(facts)
    for before, after in zip(facts, back):
        assert _same(before, after), type(before).__name__


def test_an_empty_snapshot_round_trips(tmp_path: Path):
    path = tmp_path / snapshot.NAME
    snapshot.write(path, ())
    assert snapshot.read(path) == ()


def test_the_writer_refuses_exactly_what_the_reader_cannot_rebuild():
    with pytest.raises(TypeError, match="WindowEvidence"):
        snapshot.write(Path("unreachable.npz"), (_h3_facts.evidence(),))


def _stored_copy(deflated: Path, plain: Path) -> Path:
    """The same snapshot as the old writer laid it down: identical
    members, stored instead of deflated."""
    with np.load(deflated) as handle:
        np.savez(plain, meta=handle["meta"], blob=handle["blob"])
    return plain


def test_the_snapshot_is_written_compressed(tmp_path: Path):
    deflated = tmp_path / snapshot.NAME
    snapshot.write(deflated, _durable_facts())
    stored = _stored_copy(deflated, tmp_path / "plain.npz")
    assert deflated.stat().st_size < stored.stat().st_size


def test_a_plain_uncompressed_snapshot_still_resumes(tmp_path: Path):
    """The reader is untouched by the compression ruling: `np.load`
    takes a stored member and a deflated one alike, so every snapshot an
    operator already holds still folds."""
    facts = _durable_facts()
    deflated = tmp_path / snapshot.NAME
    snapshot.write(deflated, facts)
    back = snapshot.read(_stored_copy(deflated, tmp_path / "plain.npz"))
    assert len(back) == len(facts)
    for before, after in zip(facts, back):
        assert _same(before, after), type(before).__name__


def _live_engine() -> engine._Engine:
    instance = _h3_facts.new_engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.survey())
    instance._ingest(_h3_facts.window())
    instance._ingest(_h3_facts.placement())
    instance._ingest(_h3_facts.lattice_seed())
    instance._ingest(_h3_facts.ctx_outcome())
    instance._ingest(_h3_facts.certificate())
    return instance


def _replayed_engine(path: Path) -> engine._Engine:
    instance = _h3_facts.new_engine()
    instance._ingest(_h3_facts.capture())
    for fact in snapshot.read(path):
        instance._ingest(fact)
    return instance


def _regenerate(instance: engine._Engine) -> None:
    """What a resumed run gets back from the rasters on its own."""
    instance._ingest(_h3_facts.evidence(ctx_adopted=True))
    instance._ingest(_attempt())


def _pair(tmp_path: Path) -> tuple[engine._Engine, engine._Engine]:
    live = _live_engine()
    path = tmp_path / snapshot.NAME
    snapshot.write(path, snapshot.collect(live))
    replayed = _replayed_engine(path)
    _regenerate(live)
    _regenerate(replayed)
    return live, replayed


def test_collect_publishes_the_standing_cells_and_nothing_bulk(
        tmp_path: Path):
    live = _live_engine()
    facts = snapshot.collect(live)
    kinds = [type(fact).__name__ for fact in facts]
    assert set(kinds) <= set(DURABLE), kinds
    assert kinds.count("Certificate") == 1
    assert kinds.count("Placement") == 1
    assert kinds.index("CaptureSurvey") == 0
    assert kinds.index("Certificate") == len(kinds) - 1
    assert kinds.index("Window") < kinds.index("Placement")
    for fact in facts:
        if isinstance(fact, calibrate.CtxOutcome):
            assert fact.inputs == () and fact.outputs == ()


def test_a_replayed_family_births_the_subjects_the_live_fold_births(
        tmp_path: Path):
    live, replayed = _pair(tmp_path)
    checks = _h3_support.Checks("subjects_of over replay")
    for descriptor in engine.DESCRIPTORS:
        for name in sorted(_h3_facts.BUILD):
            fact = _probe(name)
            if not isinstance(fact, descriptor.born_by):
                continue
            checks.equal(
                f"{descriptor.name} subjects of {name}",
                descriptor.subjects_of(replayed, fact),
                descriptor.subjects_of(live, fact))
    checks.assert_clean()


def test_the_replayed_run_holds_the_same_workers_as_the_live_one(
        tmp_path: Path):
    live, replayed = _pair(tmp_path)
    assert set(replayed._bookmarks) == set(live._bookmarks)


def test_the_replayed_store_carries_the_same_standing_decisions(
        tmp_path: Path):
    live, replayed = _pair(tmp_path)
    wid = _h3_facts.WINDOW_ID
    assert _same(replayed.placement(wid), live.placement(wid))
    assert _same(replayed.window(wid), live.window(wid))
    assert _same(replayed.region_ctx(REGION_KEY),
                 live.region_ctx(REGION_KEY))
    assert _same(replayed.lattice_seed(REGION_KEY),
                 live.lattice_seed(REGION_KEY))
    assert replayed.certificate_keys() == live.certificate_keys()
    assert replayed.done_grid(0).tolist() == live.done_grid(0).tolist()
    assert replayed.window_reach(wid) == live.window_reach(wid)


def test_a_second_snapshot_of_the_replayed_run_is_the_same_snapshot(
        tmp_path: Path):
    live, replayed = _pair(tmp_path)
    again = snapshot.collect(replayed)
    once = snapshot.collect(live)
    assert [type(fact).__name__ for fact in again] == [
        type(fact).__name__ for fact in once]
    for before, after in zip(once, again):
        assert _same(before, after), type(before).__name__


def _seeded_lane() -> engine._Engine:
    instance = _h3_facts.new_engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.survey())
    instance._ingest(_h3_facts.window())
    instance._ingest(_h3_facts.placement())
    return instance


def test_an_attempt_ahead_of_its_evidence_would_orphan_its_retry_row():
    """Why AttemptFact is NOT durable.

    `tiles.retry` is born by the attempt, and its read set is
    materialised at birth out of the tile cover that the EVIDENCE
    builds.  Replayed ahead of the evidence it is born deaf; the
    identical attempt that comes back with the regenerated evidence
    folds as no change, so it never re-births and nothing ever wakes
    it.  The memo costs a retry row; the re-run scan rebuilds it for
    free.
    """
    early = _seeded_lane()
    early._ingest(_attempt())
    early._ingest(_h3_facts.evidence())
    early._ingest(_attempt())

    ordinary = _seeded_lane()
    ordinary._ingest(_h3_facts.evidence())
    ordinary._ingest(_attempt())

    keys = [key for key in ordinary._bookmarks if key[0] == "tiles.retry"]
    assert len(keys) == 1, keys
    assert ordinary._bookmarks[keys[0]].reads != ()
    assert keys[0] in early._bookmarks
    assert early._bookmarks[keys[0]].reads == ()


def test_the_run_writes_its_snapshot_into_the_run_dir_at_run_done():
    instance = _live_engine()
    result = instance._finish(None)
    assert result.status == "open"
    path = instance._request.run_dir / snapshot.NAME
    assert path.is_file()
    kinds = [type(fact).__name__ for fact in snapshot.read(path)]
    assert set(kinds) <= set(DURABLE) and "Certificate" in kinds
    assert isinstance(instance._events[-1], data.RunDone)


def test_a_refused_final_write_costs_the_run_nothing_but_says_so(capsys):
    """Best effort at the exit: the payload is already recovered, and a
    run dir that will not take the file does not take that away."""
    instance = _live_engine()
    run_dir = instance._request.run_dir
    run_dir.chmod(0o555)
    try:
        result = instance._finish(
            types.SimpleNamespace(payload=b"the recovered volume"))
    finally:
        run_dir.chmod(0o755)
    assert result.status == "verified"
    assert result.payload == b"the recovered volume"
    assert not (run_dir / snapshot.NAME).exists()
    assert "snapshot" in capsys.readouterr().err


def test_the_replay_event_changes_nothing_but_the_event_list(tmp_path: Path):
    """The one synthetic event is diag accounting.  An engine that
    replayed a snapshot holds exactly the state of one that folded the
    same facts by hand; the whole difference is one appended event."""
    path = tmp_path / snapshot.NAME
    snapshot.write(path, snapshot.collect(_live_engine()))
    facts = snapshot.read(path)

    hand = _h3_facts.new_engine()
    hand._ingest(_h3_facts.capture())
    for fact in facts:
        hand._ingest(fact)
    replayed = _h3_facts.new_engine()
    replayed._ingest(_h3_facts.capture())
    replayed._replay(facts)

    assert replayed._bookmarks == hand._bookmarks
    assert replayed._frontier == hand._frontier
    assert replayed.certificate_keys() == hand.certificate_keys()
    assert replayed._index == hand._index
    assert replayed._events[:len(hand._events)] == hand._events
    assert [type(event).__name__
            for event in replayed._events[len(hand._events):]] == [
        "SnapshotReplayed"]


def test_the_replay_event_counts_the_families_and_the_certificates(
        tmp_path: Path):
    path = tmp_path / snapshot.NAME
    facts = snapshot.collect(_live_engine())
    snapshot.write(path, facts)
    instance = _h3_facts.new_engine()
    instance._ingest(_h3_facts.capture())
    instance._replay(snapshot.read(path))
    event = instance._events[-1]
    counted: dict[str, int] = {}
    for fact in facts:
        name = type(fact).__name__
        counted[name] = counted.get(name, 0) + 1
    assert event.facts == tuple(sorted(counted.items()))
    assert event.certified == len(instance.certificate_keys()) == 1
    assert set(name for name, _count in event.facts) <= set(DURABLE)
