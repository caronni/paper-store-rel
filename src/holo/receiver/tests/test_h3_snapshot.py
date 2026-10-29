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

from holo.receiver import data, engine, snapshot
from holo.receiver.format.identity import resolve_format_ref
from holo.receiver.plugins import calibrate, tiles_sched
from holo.receiver.tests import _h3_facts, _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_the_durable_families_are_the_declared_set`.

DURABLE = ("CaptureSurvey", "Window", "LatticeSeed", "Placement",
           "CtxOutcome", "PlaneField", "PooledColorCtx", "Certificate",
           "EvidenceRevision")

# what the store folds and the snapshot deliberately leaves behind
LEFT_BEHIND = ("Capture", "PlaceOutcome", "WindowEvidence",
               "ColorEvidenceRow", "ColorCtxPopulation", "RefineOutcome",
               "AttemptFact",
               # FieldObservations is DERIVED: a resume re-declares the
               # placements and the certificates it is measured from, so
               # `fields.collect` re-arms and re-measures, while the
               # page's standing PlaneField folds back ahead of it and
               # the run starts from the last solve (I10).
               "FieldObservations",
               # ColorLaneFit is scheduling-shaped state, like
               # PlaceOutcome: the head-fit ordinal and assembly-debt
               # coverage price the lane's re-fires. On resume the head
               # re-fits once per lane from regenerated evidence, and
               # the never-price-at-zero rule keeps that first re-fit
               # at full price.
               "ColorLaneFit")

REGION_KEY = (_h3_facts.CAPTURE_ID, 0, 0)


def _attempt() -> data.AttemptFact:
    """The probe attempt, on this fixture's own lane (since 2026-10-03
    `_h3_facts.attempt` names that lane too: the fold reads its footing)."""
    return dataclasses.replace(_h3_facts.attempt(),
                               components=((_h3_facts.CAPTURE_ID, 0),))


def _probe(name: str) -> object:
    return _attempt() if name == "AttemptFact" else _h3_facts.BUILD[name]()


def _standing_ctx_outcome() -> calibrate.CtxOutcome:
    """A CtxOutcome shaped the way `collect` emits one: the standing
    region fit alone, with no evidence rows riding along."""
    return calibrate.CtxOutcome(REGION_KEY, _h3_facts.region_ctx())


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
    _h3_support.assert_measured(
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


def test_a_snapshot_hands_every_placement_back_at_its_own_width(
        tmp_path: Path):
    """The int16 pose of `data.Placement` and the int64 pose every
    snapshot written before 2026-09-13 carries, side by side.

    The reader restores the STORED dtype, so the narrowing is not a
    format fork: an archive resumes at the width it was written, a
    fresh run writes the narrow one, and `window_page_cells` — the door
    the receiver and both analyzer readers reach the page through —
    cannot tell the two apart, because it coerces first.
    """
    narrow = _h3_facts.placement()
    assert narrow.local_cells_yx.dtype == np.int16
    archived = dataclasses.replace(
        narrow, local_cells_yx=np.asarray(narrow.local_cells_yx, np.int64))
    path = tmp_path / snapshot.NAME
    snapshot.write(path, (narrow, archived))
    back = snapshot.read(path)
    assert back[0].local_cells_yx.dtype == np.int16
    assert back[1].local_cells_yx.dtype == np.int64
    assert np.array_equal(back[0].local_cells_yx, narrow.local_cells_yx)

    extent = _h3_facts.EXTENT
    window_shape = (extent[2] - extent[0], extent[3] - extent[1])
    page_shape = resolve_format_ref(_h3_facts.FORMAT_REF).cells_yx
    page_cells = tuple(
        calibrate.window_page_cells(fact, window_shape, page_shape)
        for fact in back)
    assert page_cells[0].dtype == np.int64
    assert np.array_equal(page_cells[0], page_cells[1])
    assert page_cells[0].shape[0] == narrow.local_cells_yx.shape[0]


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


#: One name per subject, 2026-09-05: the durable-kind set, the replay
#: ordering and the bulk stripping used to share one name (the ordering
#: was not in it at all).  Same `_live_engine()`, same seven assertions.
def test_collect_publishes_only_the_durable_standing_cells():
    live = _live_engine()
    kinds = [type(fact).__name__ for fact in snapshot.collect(live)]
    assert set(kinds) <= set(DURABLE), kinds
    assert kinds.count("Certificate") == 1
    assert kinds.count("Placement") == 1


def test_collect_orders_a_fact_after_the_facts_a_replay_needs_first():
    """Re-pinned 2026-09-08 (W8): the certificates are no longer last.

    The evidence revisions are (I12), and deliberately: the fold takes
    the HIGHER of the restored number and whatever the replayed
    placements and certificates counted on their way past, so the
    restored number is written after everything that could raise it.
    Certificates still come after every pose family, which is what this
    test was pinning.
    """
    live = _live_engine()
    kinds = [type(fact).__name__ for fact in snapshot.collect(live)]
    assert kinds.index("CaptureSurvey") == 0
    assert set(kinds[kinds.index("Certificate"):]) == {
        "Certificate", "EvidenceRevision"}
    assert kinds[-1] == "EvidenceRevision"
    assert kinds.index("Window") < kinds.index("Placement")


def test_the_ctx_outcome_keeps_its_old_wire_shape_on_both_sides():
    """`CtxOutcome` lost its window rows 2026-10-03; the wire did not.

    The encoded fact carries `inputs` and `outputs` at their old places,
    empty, so a tree from before the change reads THIS FACT as this one
    writes it; and a node written before it decodes here, an empty field
    dropped.  "Both sides" holds for `CtxOutcome` only: the snapshot as
    a whole is one-way since `b0fa4651` put `Window.parent` on the wire,
    which no tree before it can decode (SCHED-LIFECYCLE-REVIEW-2026-10-17
    D5; no shim, the owner's call).
    """
    outcome = _standing_ctx_outcome()
    arrays: list = []
    node = snapshot._encode(outcome, arrays)
    assert [name for name, _item in node[2]] == [
        "region_key", "inputs", "outputs", "ctx"]
    assert node[2][1][1] == ["t", []] and node[2][2][1] == ["t", []]
    back = snapshot._decode(node, arrays)
    assert back.region_key == outcome.region_key
    assert back.ctx.reason == outcome.ctx.reason
    node[2][1][1] = ["t", [["t", []]]]
    with pytest.raises(ValueError, match="retired wire field"):
        snapshot._decode(node, arrays)


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


def test_a_replayed_attempt_would_carry_another_run_s_generation():
    """Why AttemptFact is NOT durable, restated for the narrow key.

    The old reason was that `tiles.retry`'s read set was materialised at
    birth out of the tile cover the EVIDENCE builds, so an attempt
    replayed ahead of the evidence was born deaf.  Since 2026-09-21 the
    row's read is a CONSTANT of its subject -- one `attempt` key of its
    own -- so arrival order cannot deafen it, and the pin below says so.

    What makes the memo worthless now is the GENERATION.  A verdict
    carries the tile-lane counter of the run that decoded it, and that
    counter is derived: a fresh run starts at zero and counts its own
    evidence folds.  So a replayed verdict is a number about another
    run's history, and `_retry_eligible` -- which fires only on a
    baseline at the CURRENT generation -- can neither trust it nor be
    safely fooled by it.  The re-run scan rebuilds the verdict, at its
    own generation, for free.
    """
    early = _seeded_lane()
    early._ingest(_attempt())
    early._ingest(_h3_facts.evidence())
    early._ingest(_attempt())

    ordinary = _seeded_lane()
    ordinary._ingest(_h3_facts.evidence())
    lane = (0, 0, 0, _h3_facts.CAPTURE_ID, 0)
    # what `prepare_scan` would have read and the job would report back
    live = ordinary.tile_lane_generation(lane)
    assert live > 0, "the evidence fold advanced this tile-lane"
    ordinary._ingest(dataclasses.replace(_attempt(), generation=live))

    keys = [key for key in ordinary._bookmarks if key[0] == "tiles.retry"]
    assert len(keys) == 1, keys
    assert keys[0] in early._bookmarks
    assert (early._bookmarks[keys[0]].reads
            == ordinary._bookmarks[keys[0]].reads != ()), (
        "the narrow key is a constant of the subject: no arrival order "
        "can leave this row deaf")

    subject = keys[0][1]
    assert tiles_sched._retry_eligible(ordinary, subject) is True
    stale = _seeded_lane()
    stale._ingest(dataclasses.replace(_attempt(), generation=7))
    stale._ingest(_h3_facts.evidence())
    assert stale.attempt_verdict(*subject[1:5], subject[0],
                                 (subject[6], subject[5]))[1] == 7
    assert tiles_sched._retry_eligible(stale, subject) is False, (
        "a generation from another run is not this run's baseline"
    )


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
