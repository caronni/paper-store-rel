"""F-19: one live writer owns a state directory (the lock file).

Two live processes appending to one journal and one sidecar would
interleave into garbage no reader could detect until far too late; the
claim is refused at the door instead. A DEAD holder is a crash's
residue and is taken over silently — the journal tail re-earn is
already the designed recovery for everything else a crash leaves.
"""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from holo2.core.registry import RecordRegistry
from holo2.core.store import LOCK_NAME, Store, StoreError

from conftest import make_session, registry


def test_a_live_owner_refuses_a_second_writer(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    store = Store.create(state_dir, make_session(), registry())
    assert (state_dir / LOCK_NAME).read_text() == str(os.getpid())
    with pytest.raises(StoreError, match="owned by live process"):
        Store.open(state_dir, registry())
    store.close()
    assert not (state_dir / LOCK_NAME).exists()
    Store.open(state_dir, registry()).close()


def test_a_dead_holders_lock_is_taken_over_silently(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    Store.create(state_dir, make_session(), registry()).close()
    (state_dir / LOCK_NAME).write_text("999999999")   # no such pid
    with Store.open(state_dir, registry()) as reopened:
        assert (state_dir / LOCK_NAME).read_text() == str(os.getpid())
        assert reopened.commit_seq == 0


def test_a_refused_open_releases_the_lock(tmp_path: Path) -> None:
    """A refused open is not a claim (measured 2026-08-15, W1 close-out).

    ``Store.open`` used to release the lock on a journal error but on no
    other refusal, so a manifest mismatch left a lock naming the CURRENT
    pid behind. Across processes that is a dead holder's residue and is
    taken over silently; inside ONE long-lived process — a test session,
    an operator tool that retries — the next open of the same dir refused
    with "owned by live process N", which misreports a schema refusal as
    a concurrent writer. Every refusal must repeat itself instead.
    """
    state_dir = tmp_path / "state"
    Store.create(state_dir, make_session(), registry()).close()
    bumped = RecordRegistry(
        replace(family, version=family.version + 1)
        if family.kind is not None else family
        for family in registry().families())
    for _ in range(2):   # the SAME refusal twice, in the same process
        with pytest.raises(StoreError, match="manifest mismatch"):
            Store.open(state_dir, bumped)
        assert not (state_dir / LOCK_NAME).exists()
    other = replace(make_session(), providers=("someone-else-v0",))
    with pytest.raises(StoreError, match="session identity differs"):
        Store.open(state_dir, registry(), expect_session=other)
    assert not (state_dir / LOCK_NAME).exists()
    Store.open(state_dir, registry()).close()   # a true open still claims


def test_a_create_that_fails_past_the_lock_leaves_no_lock(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``create`` had the exact lock-leak class ``open`` was cured of
    (measured 2026-08-16, alongside the ``open`` fd leak below): only its
    journal-exists arm released the lock explicitly, so any LATER failure
    — a bad header, a disk error building the journal/cache/sidecar, a
    session-identity mismatch in the constructor — left the lock naming
    this (dead, for a fresh ``tmp_path``) pid behind. Now the whole body
    past the acquire shares ``open``'s release-on-any-failure discipline.
    """
    state_dir = tmp_path / "state"
    import holo2.core.store as store_module

    def boom(session: object, registry: object) -> None:
        raise RuntimeError("boom past the lock")

    with monkeypatch.context() as patch:
        patch.setattr(store_module, "starting_point", boom)
        with pytest.raises(RuntimeError, match="boom past the lock"):
            Store.create(state_dir, make_session(), registry())
    assert not (state_dir / LOCK_NAME).exists()
    # And a real create still succeeds afterwards — nothing wedged.
    Store.create(state_dir, make_session(), registry()).close()


def test_a_refused_open_closes_its_open_handles(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A refusal past ``_open_cache`` used to leak the journal/sidecar/cache
    fds it had already opened, releasing only the lock (measured
    2026-08-16, alongside the lock-leak above): the position-consistency
    check ("the memo cannot know more than the fold") fires after all
    three are open, and nothing closed them on that arm. Cheapest honest
    check: wrap each class's own ``close`` and assert every one the
    refused open actually opened got called.
    """
    from holo2.core.blobs import BlobSidecar
    from holo2.core.cache import CacheWriter
    from holo2.core.journal import Journal
    import holo2.core.store as store_module

    state_dir = tmp_path / "state"
    Store.create(state_dir, make_session(), registry()).close()

    closed: list[str] = []
    with monkeypatch.context() as patch:
        for cls, name in ((Journal, "journal"), (BlobSidecar, "sidecar"),
                          (CacheWriter, "cache")):
            original = cls.close

            def wrapper(self: object, *, _original: object = original,
                       _name: str = name) -> None:
                closed.append(_name)
                _original(self)

            patch.setattr(cls, "close", wrapper)
        # Force the deep "cache claims more than the journal" refusal,
        # which only fires once the journal, sidecar AND cache are open.
        patch.setattr(store_module, "commit_count", lambda ordering: -1)
        with pytest.raises(StoreError, match="cannot know more than the fold"):
            Store.open(state_dir, registry())
    assert set(closed) == {"journal", "sidecar", "cache"}
    assert not (state_dir / LOCK_NAME).exists()
    # A clean open+close afterwards proves nothing stayed wedged open.
    Store.open(state_dir, registry()).close()
