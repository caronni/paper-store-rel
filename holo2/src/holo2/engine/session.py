"""One open session: its lineage, its commit authority, its lifecycle.

Three duties, and nothing else:

1. **binding a run to a lineage** — the ``SessionIdentity`` of §5.1
   (format row id, receiver policy, the recipe's entries and the ordered
   provider ids as DATA, declared page domain) and the state directory
   that holds it;
2. **the commit authority** — one ``CommitEngine`` over one ``Store``,
   the no-op filter that keeps a resumed run from burning a commit
   sequence number (L10), and the cache invalidation a commit implies;
3. **lifecycle** — terminality, the durable close record, and closing the
   store.

What it deliberately does NOT own is the derived world it schedules over:
captures, regions, footings, window plans, the tile map, the done
projection. Those are ``format``/``capture``/``solve`` types, and a
scheduler that named them would know what a printed sheet and a pixel
are. They arrive as a :class:`Plane`, built by the composition root, and
the engine relays it to providers and workers as ``core.SolveView``.

Choices where DESIGN is silent, argued in ``engine/DESIGN.md``: the plane
is built by a factory rather than passed in, and the blob read lock lives
on the plane, where the concurrent readers are (§10.1).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Protocol, runtime_checkable

# The cadences are core's rulings, and this signature RELAYS them: a
# literal here is a default that a change to the constant never reaches.
# They ride core's public surface, like every other cross-package name.
from ..core import (DEFAULT_SNAPSHOT_EVERY, DEFAULT_TRACE_SAMPLE_EVERY,
                    BlobRef, CloseRecord, CommitBatch, CommitEngine,
                    CommitResult, RecordRegistry, ResourceKey, SolveView,
                    Store, TraceWriter, WorkId, Write)
from .recipe import Recipe
from .records import SessionIdentity

#: THE RECEIVER POLICY LINEAGE, as it lands in ``SessionIdentity``.
#:
#: FORKED AT H4 W6 (2026-08-18): it read ``holo2-h2c-spine-v0`` — two
#: dead codenames, H2c and "spine", naming a receiver policy that has
#: since had its placement family, its scheduling model and its wall
#: replaced. The new string says what is true: the H4 PULL MODEL, v1 of
#: it. Nothing about the value's ROLE changed — like the provider ids
#: beside it, this rides the identity BY VALUE, so every state directory
#: minted under the old name now REFUSES TO OPEN
#: (``Store.open_or_create``: "session identity differs from the
#: expected lineage", naming the directory; the differing FIELD is not
#: printed, and the reader is expected to know it changed from here).
#: That is the fork discipline the freshness doctrine asks for: loud and
#: un-migrated, never a quiet reinterpretation of state under a policy it
#: was not built with.
POLICY_ID = "holo2-h4-pull-v1"


@runtime_checkable
class Plane(SolveView, Protocol):
    """The derived world a session schedules over, owned outside the engine.

    Every type on this protocol is core's or JSON. That is the whole
    point: the engine hands the plane to providers and workers as a
    ``SolveView`` (which is why the protocol extends it), tells it when a
    commit killed its derived views, and reads one JSON summary off it for
    the observer. What a raster, a region, a window or a printed row IS
    belongs to the packages that know pixels and format
    (``holo2.solve.SessionPlane`` is the v1 implementation).
    """

    def read_blob(self, ref: BlobRef, *,
                  verify: bool = False) -> memoryview: ...

    def invalidate(self,
                   changed_keys: Iterable[ResourceKey] | None = None, *,
                   spent: Iterable[WorkId] = ()) -> None:
        """A commit landed: drop the views derived from the store.

        ``changed_keys`` is the commit's own delta, handed over so the
        plane can ADVANCE a derived view instead of rebuilding it from
        the whole store (F-17). The engine states what moved and nothing
        more — which views are maintainable from a delta is entirely the
        plane's business — and ``None`` is the honest "I do not know",
        which a plane must answer with a full rebuild.

        ``spent`` is the same commit's spend work ids (H4 streaming
        ingestion's duplicate-scan fix, 2026-08-17), relayed for the
        symmetric reason: a family's own attempt is durable the moment
        its spend lands, even on a run whose every WRITE was an
        equal-rewrite ``SessionContext.changed`` dropped (L10) — so a
        plane that needs to react to the ATTEMPT, not to what it wrote,
        needs the work id, not the (possibly empty) delta. Relayed like
        ``changed_keys``: a raw core value, uninterpreted here — what a
        family's work id means is entirely the plane's business.
        """

    def detached_captures(self) -> tuple[str, ...]:
        """The acquisitions this session holds facts for and no pixels for.

        A bare list of opaque identifiers — the engine neither parses them
        nor knows what a pixel is; it QUOTES them. The one caller is
        recovery (``engine.replay``), and only when the recorded tail
        holds a pass this run cannot offer: at that point "which inputs
        are missing?" is the operator's whole question, and the plane is
        the only object that can answer it. Ordinary and harmless
        otherwise — a resume handed fewer files than the store knows is a
        supported mode, and the work that needs those pixels sleeps.
        """

    def observer_summary(self) -> dict[str, object]:
        """Everything the observer reads off the plane, as ONE mapping.

        The tile map's per-state counts, the §6 done coverage per capture
        and region, and the lineage's COUNTED false-accept exposure (L5)
        are all here for one reason — the engine has no business typing a
        tile state, a cell lattice or a decoder outcome — so they arrive
        under the plane's own key names, in one call, and the snapshot
        spreads them into the published session mapping untouched. Three
        protocol methods that differed only in which JSON they handed
        back were three ways of writing this one.
        """


PlaneFactory = Callable[[Store, CommitEngine], Plane]


class SessionContext:
    """One open session: durable state, commit authority, and its plane."""

    def __init__(self, store: Store, engine: CommitEngine,
                 plane: Plane) -> None:
        self._store = store
        self._engine = engine
        self._plane = plane

    # -- identity ----------------------------------------------------------

    @property
    def store(self) -> Store:
        return self._store

    @property
    def registry(self) -> RecordRegistry:
        """The record vocabulary this session was composed with (R3)."""
        return self._store.registry

    @property
    def engine(self) -> CommitEngine:
        return self._engine

    @property
    def plane(self) -> Plane:
        return self._plane

    @property
    def terminal(self) -> bool:
        return self._store.is_terminal()

    def close_record(self) -> CloseRecord | None:
        return self._store.close_record()

    # -- what the scheduler reads ------------------------------------------

    def view(self) -> SolveView:
        """The read-only view providers and workers are handed (R1)."""
        return self._plane

    # -- writing -----------------------------------------------------------

    def changed(self, writes: Iterable[Write]) -> tuple[Write, ...]:
        """Drop writes whose record already stands, so no-ops cost nothing.

        The commit layer would drop them too (version-bump-iff-changed),
        but it would still burn a commit sequence number, and a resumed
        run that changes nothing must change *nothing* (L10).
        """
        return tuple(write for write in writes
                     if self._store.get(write.key) != write.record)

    def apply(self, batch: CommitBatch) -> CommitResult:
        result = self._engine.apply(batch)
        self._plane.invalidate(
            result.changed_keys,
            spent=tuple(spend.worker_id for spend in batch.spends))
        return result

    # -- reads -------------------------------------------------------------

    def read_blob(self, ref: BlobRef, *, verify: bool = False) -> memoryview:
        return self._plane.read_blob(ref, verify=verify)

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> "SessionContext":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def open_session(state_dir: Path, *, format_row_id: str,
                 page_domain: tuple[int, ...], recipe: Recipe,
                 providers: tuple[str, ...],
                 plane: PlaneFactory, registry: RecordRegistry,
                 policy_id: str = POLICY_ID,
                 fsync: bool = True,
                 no_close: bool = False,
                 snapshot_every: int = DEFAULT_SNAPSHOT_EVERY,
                 trace_sample_every: int = DEFAULT_TRACE_SAMPLE_EVERY,
                 ) -> SessionContext:
    """Open (or create) the session and derive the plane over its state.

    ``registry`` is the composed record vocabulary (R3): the engine writes
    the session identity and knows nothing else about record shapes, so
    the set of families a run can store is the composition root's
    declaration, handed through.

    ``recipe`` and ``providers`` are the executable policy, and they land
    in the identity AS DATA: the store compares the whole value on
    resume, so a moved gate, a re-ordered provider binding or a changed
    price is a refused open rather than a state reinterpreted under a
    policy it was not built with.

    ``no_close`` is the run's CLOSE POLICY (`--no-close`, ruled
    2026-08-22) and is deliberately NOT in the identity — like
    ``complete``, it is a per-run argument, not a lineage fork: the whole
    point is that one state directory accumulates under it and closes
    under an ordinary run later. Here it does one thing: the store folds
    no close record, so the session opens OPEN and the wall admits
    commits (``core.store``'s "what the fold admits of a CLOSE"). The
    other half — never consulting in a deciding mode — is the
    orchestrator's.
    """
    session = SessionIdentity(
        format_row_id=format_row_id,
        receiver_policy_id=policy_id,
        recipe_entries=recipe.entries,
        providers=providers,
        page_domain=page_domain,
    )
    store = Store.open_or_create(state_dir, session, registry,
                                 snapshot_every=snapshot_every, fsync=fsync,
                                 skip_close=no_close)
    engine = CommitEngine(store, trace=TraceWriter(
        store.trace_path, sample_every=trace_sample_every))
    return SessionContext(store, engine, plane(store, engine))


__all__ = ["POLICY_ID", "Plane", "PlaneFactory", "SessionContext",
           "open_session"]
