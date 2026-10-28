"""The provider protocol's own mechanisms, over a captureless session.

Three R1 capabilities that no adapted provider exercises yet, pinned here
so the mechanism is proven before a family depends on it:

* **M2 re-offerable declines** — a provider may refuse a descriptor and
  name the keys that would change its mind; the engine sleeps it and
  offers it again when one of them moves. A decline with no keys is
  permanent and is never re-offered.
* **M3 provider-minted subjects** — a provider may commit a
  ``SubjectSpec`` and have work appear on it, without the session having
  been opened with that subject. The split provider below proves the
  mechanism (a durable subject fact plus a collection bump that drives
  expansion); it is deliberately a test fixture, because the production
  subdivision algorithm is H4/H5's domain work and inventing one here
  would be a fabricated default.
* **M5 lease residency** — a descriptor's declared leases are held for
  the duration of its fire and visible to the observer.

Also pinned: a recipe entry whose family nothing provides is a loud
refusal, not a quietly empty queue.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from holo2.core.records import SubjectSpec, subject_collection_key, subject_key
from holo2.solve import tile_key

from holo2.core.work import (Decline, Lease, WorkDescriptor, WorkResult,
                             WorkScope)
from holo2.core.commit import Write
from holo2.engine.orchestrator import NoProviderError
from holo2.engine.recipe import (COST_PAYLOAD, FOOTING_ALL, GATE_ALWAYS,
                                 GATE_COUNT_READY, Recipe, RecipeEntry,
                                 TASK_CLOSE, TASK_PAYLOAD)
from conftest import FOOTING, REGION, lattice_seed_key, make_seed
from test_orchestrator import (RECIPE, make_orchestrator, make_session,
                               seed_addressed)

PROBE = lattice_seed_key(FOOTING, REGION)
GATED = tile_key(0, 0, 0, "main")
ARRIVING = tile_key(0, 0, 1, "main")

RECIPE_SUBJECTS = Recipe("recipe-subjects", (
    RecipeEntry("split", FOOTING_ALL, GATE_ALWAYS, COST_PAYLOAD),
    RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_COUNT_READY, COST_PAYLOAD),
))


# ------------------------------------------------------------- scaffolding

class _Worker:
    """Fires once, writes what it was handed, and retires."""

    def __init__(self, keys, writes=()) -> None:
        self._keys = tuple(keys)
        self._writes = tuple(writes)
        self.fires = 0

    def read_keys(self, view):
        return self._keys

    def run(self, view, identity, progress):
        self.fires += 1
        progress.emit(1, "fire")
        return WorkResult(outcome="done", writes=self._writes, retire=True)


class DecliningProvider:
    """One key waits for a probe another key's worker writes (M2).

    ``GATED`` is refused while the probe key is absent; ``ARRIVING`` fires
    and writes it. So the wake happens mid-run, from an ordinary commit —
    which is the case a permanent decline would lose.
    """

    family = TASK_PAYLOAD
    sources = ("tile",)
    provider_id = "unit-declining"

    def __init__(self, *, permanent: bool = False) -> None:
        self.permanent = permanent
        self.mints = 0
        self.declines = 0

    def expand(self, view, request):
        return tuple(
            WorkDescriptor(family=self.family, subject=key, route="unit",
                           entry=request.entry)
            for key in view.open_work_keys())

    def worker(self, view, descriptor):
        if descriptor.subject == ARRIVING:
            return _Worker((descriptor.subject,), writes=_probe_writes())
        if view.record(PROBE) is None:
            self.declines += 1
            return Decline("waiting for the probe",
                           wake_on=() if self.permanent else (PROBE,))
        self.mints += 1
        return _Worker((descriptor.subject, PROBE))


class SplitProvider:
    """Mints durable child SUBJECTS, then work on them (M3).

    The first fire commits one ``SubjectSpec``; the collection bump makes
    the subject visible to the next expansion, which offers work on a
    subject the session never knew about. That is the whole mechanism —
    a subdivision algorithm would only decide WHICH children to mint.
    """

    family = "split"
    sources = ("tile", "collection:subjects")
    provider_id = "unit-split"

    def __init__(self, parent) -> None:
        self._parent = parent
        self.children: list[str] = []

    def expand(self, view, request):
        descriptors = [WorkDescriptor(
            family=self.family, subject=self._parent, route="mint",
            entry=request.entry)]
        for subject in view.subjects(self.family):
            descriptors.append(WorkDescriptor(
                family=self.family, subject=subject_key(subject.subject_id),
                route="child", scope=WorkScope(profile=subject.parent or ""),
                entry=request.entry,
                leases=(Lease(subject_collection_key(self.family)),)))
        return tuple(descriptors)

    def worker(self, view, descriptor):
        if descriptor.route == "mint":
            child = SubjectSpec(subject_id="child-1", family=self.family,
                                parent="/".join(self._parent.parts),
                                parameters=(("half", "upper"),))
            return _Worker(
                (self._parent, subject_collection_key(self.family)),
                writes=(Write(subject_key(child.subject_id), child),))
        self.children.append(descriptor.subject.parts[0])
        return _Worker((descriptor.subject,))

    def __iter__(self):
        return iter((self,))


# ------------------------------------------------------------------ tests

def test_a_decline_that_names_its_wake_is_re_offered(tmp_path: Path) -> None:
    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0), (0, 0, 1)))
        provider = DecliningProvider()
        orchestrator = make_orchestrator(session, RECIPE, (provider,))
        orchestrator.run()
    assert provider.declines >= 1, "the first offer must have been refused"
    assert provider.mints == 1, "the re-offer never happened"
    assert orchestrator.snapshot().workers.declined_pending == 0


def test_a_permanent_decline_is_never_re_offered(tmp_path: Path) -> None:
    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0), (0, 0, 1)))
        provider = DecliningProvider(permanent=True)
        orchestrator = make_orchestrator(session, RECIPE, (provider,))
        orchestrator.run()
    assert provider.mints == 0
    snapshot = orchestrator.snapshot()
    assert snapshot.workers.declined == 1
    assert snapshot.workers.declined_pending == 0


def test_a_provider_may_mint_a_subject_and_get_work_on_it(
        tmp_path: Path) -> None:
    """M3: a durable subject fact expands the authoritative domain."""
    parent = tile_key(0, 0, 0, "main")
    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0),))
        provider = SplitProvider(parent)
        make_orchestrator(session, RECIPE_SUBJECTS, provider).run()
        assert session.store.get(subject_key("child-1")) is not None
        assert session.view().subjects("split")[0].parameter("half") == "upper"
    assert provider.children == ["child-1"], "the child never became work"


def test_leases_are_held_for_the_duration_of_a_fire(tmp_path: Path) -> None:
    """M5: the scheduler refcounts a declared shared resource around a fire."""
    parent = tile_key(0, 0, 0, "main")
    seen: list[dict] = []
    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0),))
        provider = SplitProvider(parent)
        orchestrator = make_orchestrator(session, RECIPE_SUBJECTS, provider)

        original = _Worker.run

        def spy(self, view, identity, progress):
            seen.append(orchestrator.snapshot().leases)
            return original(self, view, identity, progress)

        _Worker.run = spy
        try:
            orchestrator.run()
        finally:
            _Worker.run = original
    held = [residency for residency in seen if residency]
    assert held, "a leased fire never showed residency"
    assert held[0] == {"collection/subjects/split": 1}
    assert orchestrator.snapshot().leases == {}, "a lease outlived its fire"


def test_a_family_nothing_provides_is_a_loud_refusal(tmp_path: Path) -> None:
    """A QUEUED family with no provider is loud; the close entry needs none.

    The recipe under test schedules payload and one close consult. With an
    empty roster the payload entry is the refusal — and the close entry is
    silent about it, because since B12 it names no provider family at all:
    its consumer arrives on the engine's own argument.
    """
    with make_session(tmp_path) as session:
        with pytest.raises(NoProviderError, match="payload"):
            make_orchestrator(session, RECIPE, ())


def _probe_writes():
    return (Write(PROBE, make_seed()),)
