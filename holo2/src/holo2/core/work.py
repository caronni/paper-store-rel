"""The work protocol: descriptors, providers, workers, proposals.

One mechanism for every family (DESIGN §7, §8, §10.3), and — since R1 —
one mechanism the engine can be *generic* over.

**The genericity is a COMPLEXITY BOUND, not an extension surface**
(user ruling 2026-08-12, worklist B14/Q1: "VERY in-tree only"). It buys
narrow interfaces, one uniform observable behaviour across families, and
a family that can be reasoned about, debugged and optimized on its own —
so the receiver stays manageable as families multiply. It does NOT
promise third-party providers: out-of-tree implementors are unsupported,
nothing here is versioned or defended for them, and protocol slack whose
only customer was that unpromised case is deleted rather than kept. The
two :func:`typing.runtime_checkable` protocols survive on in-tree
evidence alone — the orchestrator's ``isinstance(minted, Worker)`` reads
one; the provider contract battery that read the other
(``holo2/measure/_provider_kit.py``, applied by
``test_provider_contracts.py``) was deleted with the measure cleanup —
the claim has no surviving holder (no in-tree ``isinstance(..., Provider)``
check remains) — history has the driver.

The vocabulary is
deliberately stage-free (user ruling 2026-08-10): there are descriptors,
gates, routes and prices, and no scheduler-visible notion of a phase, a
pass, a lane or a mop-up. What v1 carried as stages survives here as
properties of ordinary work: eligibility (a decline that names its wake),
identity (footing and contributor sets inside the read-set), and price.

The four pieces, in the order a round uses them (PROVIDERS.md §8.1):

1. **P1 Declaration.** A :class:`Provider` declares the task family it
   serves, the frontier resources it expands from, and the descriptor
   scheme it mints. The engine holds providers, never solvers.
2. **P2 Expansion.** ``expand(view, request)`` turns durable facts into
   :class:`WorkDescriptor` values — ``(family, subject, route, scope)``
   plus the recipe entry that offered it. The engine never branches on a
   family name; it enumerates providers.
3. **P3 Worker input.** ``worker(view, descriptor)`` returns a
   :class:`Worker` or a :class:`Decline`. A worker sees a read-only
   :class:`~holo2.core.view.SolveView`: no store, no commit engine, no
   blob append, no clock, no RNG.
4. **P4 Proposal.** ``run`` returns a :class:`WorkResult`: staged blobs,
   fact writes, an outcome. The orchestrator binds the identity, applies
   the spend-once test, re-derives the read-set at commit time, and
   materialises the blobs of proposals it accepts. A worker therefore
   cannot forget to spend, cannot spend twice, cannot write, and cannot
   go to sleep unsubscribed.

**No silent stages** (§10.3, user ruling 2026-08-09) is enforced here,
not merely documented: a worker that reports it fired must have emitted
at least one progress quantum, and no single quantum may exceed
:data:`MAX_WORK_UNITS` work units. Quanta are work-counted, never
clock-based, so an attached observer changes wall time and nothing else.

Choices where DESIGN is silent (for adjudication):

- ``MAX_WORK_UNITS`` is a *contract* constant, not a tuned one: it exists
  so a leaf that sweeps a page or decodes thousands of tiles in one
  uninterruptible call fails a test instead of going dark.
- **The route is part of the descriptor, not of the worker** (M1). A
  family with several ways of attempting one subject mints one
  descriptor per route, so each route's spend, decline and subscription
  are independent — which is what makes every attempt separately
  resumable and schedulable. **True of the tree since 2026-08-11**, not
  merely of the protocol: the payload family mints one descriptor per
  scan/union/retry150 route (``solve.payload``), and it needed no
  protocol change to do it — which is the property this bullet was
  written to buy. A route whose law forbids it does not exist as a
  descriptor at all, so the scheduler needs no route ordering:
  eligibility is expansion (there are no ladders — DESIGN §3a).
- **The recipe entry is provenance, not identity.** ``work_id`` excludes
  it, so a subject offered by two entries is ONE piece of work admitted
  at the higher priority (the pre-R1 behaviour), while the descriptor
  still records which entry offered it.
- **A decline names its own wake** (M2). ``Decline(wake_on=keys)`` is
  re-offerable and sleeps on those keys; ``Decline()`` with no keys is
  permanent, which is honest exactly where the reason cannot un-happen
  (the §6 done gate: done only grows).
- **A lease is declared, refcounted, and not yet scheduled on** (M5).
  The engine holds a weight per leased resource around a fire so the
  observer can see residency; admission control against those weights is
  the cold route's, and arrives with it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol, TYPE_CHECKING, runtime_checkable

from .blobs import StagedBlob
from .commit import Write
from .keys import AttemptIdentity, ResourceKey, WorkId, WorkScope

if TYPE_CHECKING:                                  # pragma: no cover
    from .view import SolveView

MAX_WORK_UNITS = 4096


class SilentStage(RuntimeError):
    """A leaf did work without reporting it, or reported it too coarsely."""


class ProtocolViolation(RuntimeError):
    """A provider or worker broke the protocol's own contract.

    core's, not engine's: the promises it reports broken are declared in
    THIS module — ``Provider.worker`` returns a worker or a decline and
    nothing else (raised by the orchestrator), and a ``provider_id``
    names one provider (raised by :func:`providers_identity` at
    composition) — and a package forbidden to import engine must still
    catch it.
    """


# ------------------------------------------------------------- progress

class ProgressSink:
    """The observer hook every worker holds while it runs (§10.3).

    Two counters, not a list: the contract is "a fire reported at least
    one bounded quantum", which is a count and a sum. The live progress
    CHANNEL is a separate, unbuilt thing (F-22.3).
    """

    def __init__(self, worker_id: str, *, cap: int = MAX_WORK_UNITS) -> None:
        self._worker_id = worker_id
        self._cap = cap
        self._units = 0
        self._count = 0

    def emit(self, units: int, label: str) -> None:
        """Report ``units`` of work done since the previous report."""
        if units < 0:
            raise ValueError("work units are non-negative")
        if units > self._cap:
            raise SilentStage(
                f"{self._worker_id}: {units} work units in one quantum "
                f"exceeds the {self._cap}-unit bound ({label}) — no leaf may "
                "run dark between observer events (DESIGN §10.3)")
        self._units += units
        self._count += 1

    @property
    def count(self) -> int:
        """Quanta reported by this fire."""
        return self._count

    @property
    def units(self) -> int:
        return self._units


# ------------------------------------------------------------ descriptors

@dataclass(frozen=True)
class Lease:
    """A shared resource a fire holds while it runs (M5, declaration only)."""

    resource: ResourceKey
    weight: int = 1

    def __post_init__(self) -> None:
        if self.weight < 1:
            raise ValueError("a lease weighs at least one unit")


@dataclass(frozen=True)
class WorkDescriptor:
    """One schedulable unit: family x subject x route x scope.

    The subject is any :class:`ResourceKey` (M7) — a window, a work key,
    a pose, a label pool, a region, a capture, the close — so a family
    whose subject is not a tile needs no new machinery.
    """

    family: str
    subject: ResourceKey
    route: str
    scope: WorkScope = WorkScope()
    entry: str = ""                                   # provenance, not identity
    leases: tuple[Lease, ...] = ()
    #: WHAT THIS ATTEMPT ADDS TO ITS ENTRY'S PRICE (H4-LANES stage 2).
    #: Pricing is the recipe's, and stays the recipe's: an entry declares
    #: what its class of work costs, and this is the one thing about a
    #: particular attempt that the entry cannot know — which RUNG of a
    #: capture's ladder it reads through. A payload scan on the coarsest
    #: lane and the same scan on the native lane are the same class of
    #: work at different points in one cost order, and the provider is
    #: the only party that can say which is which.
    #:
    #: It is PROVENANCE, exactly like ``entry``: ``work_id`` excludes it,
    #: so re-pricing a lane cannot fork a work id, and a subject offered
    #: twice is still one piece of work. The placement source charges the
    #: same term on its own side (``solve.place_sched.LANE_COST_PER_RUNG``)
    #: and the two are pinned to one table
    #: (``tests/engine/test_cost_vocabulary.py``).
    premium: int = 0

    def __post_init__(self) -> None:
        if not self.family or not self.route:
            raise ValueError("a descriptor names a family and a route")
        if self.premium < 0:
            raise ValueError("a lane term is not a discount")

    @property
    def work_id(self) -> WorkId:
        """The durable name: this descriptor's own values, structured.

        The recipe entry is provenance and stays out (a subject offered
        by two entries is ONE piece of work); so is the lane term, for
        the same reason and with the same consequence. Everything else
        that makes two descriptors different is in here, as values.
        """
        return WorkId(self.family, self.subject, self.route, self.scope)


@dataclass(frozen=True)
class ExpansionRequest:
    """What the engine asks a provider to expand, from one recipe entry.

    ``selector`` and ``arm`` are the entry's policy data; ``entry`` is its
    identity, stamped onto every descriptor the expansion yields. A
    provider that ignores a selector is not wrong — it is a provider whose
    frontier does not slice that way.
    """

    entry: str
    selector: str = ""
    arm: str = ""

    def mint(self, family: str, subject: ResourceKey, route: str, *,
             profile: str = "", premium: int = 0) -> WorkDescriptor:
        """The descriptor this request supports, with the request's arm on it.

        Every provider was hand-building the same three lines — the arm
        lifted out of the request into a :class:`WorkScope`, and an
        ``entry=request.entry`` the orchestrator overwrites unconditionally
        with the identical value a few lines later. So the arm rides here
        (it is the request's data, not the provider's) and the entry does
        not ride at all: it is provenance the ORCHESTRATOR stamps, and a
        provider that never writes it cannot write it wrong.

        ``profile`` is named for what it is — ``WorkScope``'s
        provider-owned discriminator — rather than the ``scope`` the two
        duplicate helpers called it while building a scope around it.

        ``premium`` is the LANE TERM (see :class:`WorkDescriptor`): what
        this attempt adds to its entry's declared price because of which
        rung it reads. Zero for a family with no lanes, which is every
        family that does not read pixels through a footing.
        """
        return WorkDescriptor(
            family=family, subject=subject, route=route,
            scope=WorkScope(arm=self.arm, profile=profile), premium=premium)


@dataclass(frozen=True)
class Decline:
    """A provider's refusal to mint work for a descriptor (M2).

    ``wake_on`` makes the refusal re-offerable: the engine sleeps the
    descriptor on those keys and offers it again when one of them moves.
    An empty ``wake_on`` is permanent and says so — use it only where the
    reason cannot un-happen.
    """

    reason: str
    wake_on: tuple[ResourceKey, ...] = ()

    @property
    def permanent(self) -> bool:
        return not self.wake_on


# --------------------------------------------------------------- results

@dataclass(frozen=True)
class WorkResult:
    """What one fire proposes; the orchestrator turns it into a commit.

    ``retire`` is the worker's own statement that it has nothing further
    to contribute (a certificate is terminal, a window is done-covered);
    the orchestrator drops it from the queue rather than re-deriving why.

    ``blobs`` are staged, not written (M6): the commit authority
    materialises them for accepted proposals only, so a stale proposal
    costs nothing and no worker touches the sidecar.

    ``report`` is a JSON-able, provider-rendered observation the engine
    passes through untouched — the one channel by which a family whose
    result the engine cannot type (the close's fountain state) reaches
    the observer and the composition root without the engine importing
    it.

    ``exposure`` is the worker's statement that THIS attempt consumed a
    false-accept budget draw (for payload: a decoder ran, so one CRC-32
    comparison could have accepted). The ledger accumulates it
    as a monotone count per spend row, so the count survives a later outcome
    overwriting the same ``(worker, route)`` row.

    There is deliberately NO per-fire prose field (worklist B1, ruled
    2026-08-12: the old ``note`` was written at ~20 sites and read by
    nothing). The operator's decline surface is the outcome vocabulary
    plus the ledger's ``declined_by_reason`` counts; replay is unaffected
    because a note never reached the commit batch, the trace, the
    envelope or a spend row. A family that still wants a rendered
    observation has ``report``, which the engine passes through.
    """

    outcome: str
    writes: tuple[Write, ...] = ()
    blobs: tuple[StagedBlob, ...] = ()
    fired: bool = True
    retire: bool = False
    report: dict[str, Any] | None = None
    exposure: bool = False


# -------------------------------------------------------------- protocol

@runtime_checkable
class Worker(Protocol):
    """One bound computation: declare a read-set, propose once (§7)."""

    def read_keys(self, view: "SolveView") -> tuple[ResourceKey, ...]:
        """The exact keyed inputs this attempt consumes, sorted + unique."""

    def run(self, view: "SolveView", identity: AttemptIdentity,
            progress: ProgressSink) -> WorkResult:
        """Propose; never commit, never mutate, never read a clock."""


class LeasedWorker(Worker, Protocol):
    """A :class:`Worker` that also DECLARES its shared-resource leases (M5, W4/W5).

    Only :class:`WorkSource`'s pull-model workers need this member. A push
    descriptor mints its leases straight onto the :class:`WorkDescriptor`
    at P2 — the provider knows them before any worker exists — so an
    ordinary ``Worker`` never has anything to say about leases: the name
    would be dead weight on every ingest/payload fire, and plain
    ``Worker`` stays exactly what the frontier's runtime
    ``isinstance(minted, Worker)`` check has always verified (adding a
    required ``leases`` member THERE would make that check demand it of
    every push-path worker too — confirmed by probe: an
    ``@runtime_checkable`` protocol's ``isinstance`` tests every declared
    member by ``hasattr``, defaulted or not, so a leaseless worker like
    ``IngestWorker`` would stop satisfying ``Worker`` at all). A source
    job (:meth:`WorkSource.claim`) has no descriptor until the
    orchestrator synthesises one at arm time
    (``engine/orchestrator.py:_arm_job``), so the WORKER is the only
    party that can say what that pass will hold — which is what this
    refinement exists to type.

    Absence-as-empty stays LAWFUL: most pull workers hold nothing, and
    ``leases = ()`` says so plainly. What the W4 finding condemned is
    that ``getattr(worker, "leases", ())`` cannot tell "declares none"
    from "declared it wrong" — a worker that misspells the attribute
    silently under-reports its residency forever. Typing
    :meth:`WorkSource.claim` to return ``LeasedWorker | None`` instead of
    ``Worker | None`` turns that typo into a ``mypy --strict`` failure at
    the perimeter (verified with a deliberate-misspelling probe: a class
    missing or misnaming ``leases`` fails structural conformance the
    moment it is used where a ``LeasedWorker`` is expected, whether or
    not this attribute carries a default value in the protocol body —
    the default is inert for a duck-typed conformer either way, since
    Python never copies a Protocol's class-body default onto a class
    that does not literally inherit from it).
    """

    leases: tuple[Lease, ...]


@dataclass(frozen=True)
class SourceJob:
    """One ready job a :class:`WorkSource` offers — its price and subject.

    ONE JOB, and no priority field: ordering WITHIN a cost class is the
    source's own currency (H4 W2 ruling R-A: best-available-seed distance
    first, a round-robin ordinal as the tie-break) and the source has
    already applied it — a source exposes its HEAD, so the engine never
    holds two jobs of one class to compare. The field this class used to
    carry was read by no production code, and protocol slack whose only
    customer is an unpromised case is deleted rather than kept (B14).

    ``entry`` is the recipe-entry ordinal the ADMITTING caller handed the
    source, returned untouched: the source has no business knowing what a
    recipe is, and the engine needs it back to price the fire.

    ``gated`` is the expensive-tier rule as data (Q3+Q6): a gated job is
    admissible only when nothing cheaper is ready OR in flight anywhere —
    "if we devolve into 'let's run a cold search on everything remaining'
    before all payload is decoded, we are going to burn ourselves".
    """

    cost: int
    entry: int
    subject: ResourceKey
    gated: bool = False


@runtime_checkable
class WorkSource(Protocol):
    """The second admission source: in-memory scheduling state (H4 W2).

    A :class:`Provider` mints DESCRIPTORS whose eligibility is a durable
    fact and whose repetition is bounded by a spend row. A SOURCE keeps a
    monotone-shrinking set of subjects in memory, each with a readiness
    flag, and prices the ready ones; repetition is bounded by the flag
    protocol (a claim test-and-CLEARS, so one subject has one owner) and
    by the source's own tried set, not by the ledger.

    Both shapes admit through one loop, ordered by one global cost. The
    difference is where "may this run again?" is decided — the wall for a
    descriptor, the source's own memory for a job — and that is exactly
    the pull model's point: readiness and seed lists are DERIVED, so a
    resume rebuilds them from the store and re-tries at worst
    (H4-W2-PLAN, "THE PULL MODEL", Q1/Q4).

    The engine calls, in order: :meth:`admit` (per enumerable recipe
    entry, from the same refresh that expands providers), :meth:`peek`
    (the cheapest ready job), :meth:`claim` (bind it — the source clears
    the flag here, BEFORE the fire consults anything), and
    :meth:`settle` after the commit lands. ``settle(result=None)`` is the
    abandoned-fire path (a cancelled or dropped proposal) and restores
    what the claim took.
    """

    source_id: str
    family: str

    def admit(self, view: "SolveView", *, entry: int, selector: str) -> None:
        """Enter the subjects one recipe entry's selector makes eligible."""

    def peek(self) -> SourceJob | None:
        """The cheapest ready job, or None when the source is dry."""

    def job(self, subject: ResourceKey) -> SourceJob | None:
        """What ONE named subject would offer right now, consuming nothing.

        ``peek`` for a subject the caller already knows. Replay is why it
        exists (H4 W2's start markers): a recorded dispatch NAMES the
        subject it launched, and the ready ORDER at that instant was a
        live-schedule artifact no replay should have to reproduce. Same
        answer shape, same "nothing is consumed" contract — a source may
        legitimately implement ``peek`` as ``job(head)``.
        """

    def claim(self, view: "SolveView",
              subject: ResourceKey) -> LeasedWorker | None:
        """Test-and-clear one subject's flag and bind its worker.

        Returns a :class:`LeasedWorker`, not a bare ``Worker`` (W5): a
        source job has no descriptor to carry leases on, so the WORKER is
        the only party that can declare what a pull-model fire will
        hold, and typing the return this way is what makes a misspelled
        ``leases`` attribute a ``mypy --strict`` failure instead of a
        silently empty one (§ the type's own docstring).
        """

    def settle(self, view: "SolveView", subject: ResourceKey,
               result: WorkResult | None) -> None:
        """The fire landed (or was abandoned): retire, re-arm, or ping."""

    def counters(self) -> dict[str, int]:
        """What the observer reads off the source (L12: derived, never state)."""


@runtime_checkable
class Provider(Protocol):
    """A family's expansion + minting authority (P1/P2/P3).

    ``sources`` names the frontier resources this family's work DEPENDS
    on — resource kinds and collection names — as a declaration a
    reviewer can check against the code. Two kinds of entry, and a
    declaration should say which it is (amended 2026-08-23, F1 review):
    what ``expand`` itself reads to derive descriptors, and what an
    attempt's ``read_keys`` names for STALENESS — a resource whose
    version change re-arms a standing attempt without ``expand`` ever
    touching it (``solve.payload``'s ``collection:poses-window``, F1's
    supersede wake). Both are real dependencies of the family's work;
    only the first is visible in ``expand``. It is documentation with a
    test behind it (the contract kit), not a mechanism the engine
    enforces at runtime.
    """

    provider_id: str
    family: str
    sources: tuple[str, ...]

    def expand(self, view: "SolveView",
               request: ExpansionRequest) -> Iterable[WorkDescriptor]:
        """The descriptors this frontier currently supports."""

    def worker(self, view: "SolveView",
               descriptor: WorkDescriptor) -> Worker | Decline:
        """A worker for one descriptor, or a decline that names its wake."""


def check_progress(worker_id: str, result: WorkResult,
                   progress: ProgressSink) -> None:
    """The no-silent-stages contract, enforced on every fire."""
    if result.fired and not progress.count:
        raise SilentStage(
            f"{worker_id}: fired without reporting a work quantum "
            "(DESIGN §10.3 has no silent stages)")


def providers_by_family(
        providers: Iterable[Provider]) -> dict[str, tuple[Provider, ...]]:
    """Group providers for the engine's enumeration, order preserved."""
    grouped: dict[str, list[Provider]] = {}
    for provider in providers:
        grouped.setdefault(provider.family, []).append(provider)
    return {family: tuple(members) for family, members in grouped.items()}


def providers_identity(providers: Iterable[Provider]) -> tuple[str, ...]:
    """The composed binding, as it lands in ``SessionIdentity``.

    ORDERED, never sorted: within a family the first provider that mints
    a worker for a descriptor owns it, so the order IS policy and a
    reordered binding is a different executable policy. Two providers
    sharing a ``provider_id`` are refused here rather than silently
    collapsed — the identity would name one and the run would hold two.
    """
    identity = tuple(provider.provider_id for provider in providers)
    duplicates = sorted({name for name in identity
                         if identity.count(name) > 1})
    if duplicates:
        raise ProtocolViolation(
            f"provider id(s) {duplicates} bound twice; a composition names "
            "each provider once, and the session identity records the order")
    return identity


@dataclass
class LeaseBook:
    """Scheduler-side refcount over leased shared resources (M5).

    Minimal on purpose: a fire takes its descriptor's leases, a finished
    fire releases them, and the observer can read residency. There is no
    admission control here — the memory-weighted, interference-aware
    admission the cold route needs is measured work that arrives with
    that route, and inventing its policy now would be a fabricated
    default.
    """

    held: dict[ResourceKey, int] = field(default_factory=dict)

    def take(self, leases: Iterable[Lease]) -> None:
        for lease in leases:
            self.held[lease.resource] = self.held.get(
                lease.resource, 0) + lease.weight

    def release(self, leases: Iterable[Lease]) -> None:
        for lease in leases:
            remaining = self.held.get(lease.resource, 0) - lease.weight
            if remaining > 0:
                self.held[lease.resource] = remaining
            else:
                self.held.pop(lease.resource, None)

    def residency(self) -> dict[str, int]:
        return {str(key): weight for key, weight in sorted(self.held.items())}


# ``MAX_WORK_UNITS`` stays a module constant and off this surface: it is
# the default of ``ProgressSink``'s own cap, and no caller anywhere binds
# the value.
__all__ = [
    "Decline", "ExpansionRequest", "Lease", "LeaseBook", "LeasedWorker",
    "ProgressSink", "ProtocolViolation", "Provider", "SilentStage",
    "SourceJob", "WorkDescriptor", "WorkResult", "WorkSource", "Worker",
    "check_progress", "providers_by_family", "providers_identity",
]
