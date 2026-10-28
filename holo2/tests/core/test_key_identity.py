"""F-07's cheap half: the key IS the record's identity, for four more families.

The mechanism was already built and adopted by five families (evidence,
region, window, pose, calibration); these are the ones that declared no
key check and could have — capture, subject, pool and the lattice seed —
each landing as a one-line ``validate=`` on ``core.require_own_key``.
(The fourth case was the HINT state until H4 W2's clean-slate sweep
deleted that family; R5's seed takes its place here, and it is the same
claim: a record filed under another legal key of its own kind is
refused.)

What each case pins is that a record filed under another legal key of its
own kind is refused **at the commit wall** — which, since F-16 rider r1
landed, is the ONLY place it is refused. The load half of this battery is
deleted with the rest of the at-load validation: the wall is the unique
point where unlawfulness is catchable, and re-running its validators over
the store's own disposable memo was the doctrine's last standing
exception. A tampered cache is not a state to refuse, it is a cache to
delete.

The records come from ``conftest.sample_records()`` — the one instance of
every family at a legal key — so a record-shape change cannot leave a
second spelling of them here to drift.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from holo2.core.commit import CommitBatch, CommitEngine, CommitRefusal, Write
from holo2.core.keys import ResourceKey
from holo2.core.store import Store
from conftest import (CAPTURE_SHA, FOOTING, REGION, capture_key,
                      ground_batch, lattice_seed_key, make_session, pool_key,
                      registry, sample_records, subject_key)

_SAMPLES = sample_records()

#: ``(type tag, its legal key, another legal key of the same kind, the
#: refusal, the ground the LEGAL write stands on)``. The foreign key is
#: always one a minting worker really could build — the point is
#: AGREEMENT, not parseability, so a malformed key would prove a weaker
#: thing (that case is `test_publication`'s probe). The ground is empty
#: for every family that declares no references and ``"region"`` for the
#: lattice seed, which stands on the region it is the lattice of.
CASES = (
    ("CaptureRecord", capture_key(CAPTURE_SHA), capture_key("cd" * 32),
     "record identifies", None),
    ("SubjectSpec", subject_key("subject-1"), subject_key("subject-2"),
     "record identifies", None),
    ("LabelPool", pool_key("pool-1"), pool_key("pool-2"),
     "record identifies", None),
    # A seed's key is ``(footing, region)``, so the foreign key of its own
    # kind is the SAME region seen at another footing of the same capture
    # — the confusion a two-footing run really could make, and the one
    # that would put a 2:1 lattice under an 8:1 window's fit.
    ("LatticeSeedRecord", lattice_seed_key(FOOTING, REGION),
     lattice_seed_key("cap:2/1", REGION), "record identifies", "region"),
)


@pytest.mark.parametrize("tag,own,foreign,refusal,ground_upto", CASES,
                         ids=[case[0] for case in CASES])
def test_a_record_under_another_families_key_is_refused_at_the_wall(
        tmp_path: Path, tag: str, own: ResourceKey, foreign: ResourceKey,
        refusal: str, ground_upto: str | None) -> None:
    store = Store.create(tmp_path / "state", make_session(), registry(),
                         snapshot_every=1)
    engine = CommitEngine(store)
    if ground_upto is not None:
        engine.apply(ground_batch(ground_upto))
    with pytest.raises(CommitRefusal, match=refusal):
        engine.apply(CommitBatch(writes=(Write(foreign, _SAMPLES[own]),)))
    assert store.get(foreign) is None
    engine.apply(CommitBatch(writes=(Write(own, _SAMPLES[own]),)))
    assert store.get(own) == _SAMPLES[own]          # and its own key is fine
    store.close()
