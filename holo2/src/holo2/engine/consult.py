"""What the orchestrator PROMISES: the two contracts and the outcome.

Declarations only — the modes it consults its terminal consumer under,
the two protocols that consumer and the observer satisfy structurally,
the outcome one run reports, and the two errors it raises. They live
beside the loop rather than inside it because ``orchestrator.py`` is a
control loop and this is a vocabulary; splitting them is what kept the
loop under the file cap when H4 W2 gave it a second work source.

Every type named here is core's or JSON. That is the point of the file:
the engine may not import ``solve`` or ``diag``, so what it needs from
each is DECLARED here and satisfied by shape (``solve.VolumeClose`` is
the close consult; ``diag``'s status provider is the observer).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..core import ResourceKey, SolveView, StagedBlob, Write
from .snapshot import CommitLedger, RunSnapshot


#: The close-consult modes (2026-08-13). The engine owns the vocabulary
#: (it is scheduling); solve spells the same three strings on its side of
#: the import wall and a data test pins the two equal.
CONSULT_OBSERVE = "observe"   # count and report; never close (--complete)
CONSULT_CLOSE = "close"       # close when the count gate opens
CONSULT_FINAL = "final"       # close now, skipping the count gate

#: The route a source job's synthesised descriptor carries (H4 W2). It is
#: not an identity and never reaches a spend row — a pull job has one
#: job and reaches its address by whatever is true when it fires — so
#: this is the honest name for HOW the work was admitted.
ROUTE_PULL = "pull"


class FireCountTripwire(RuntimeError):
    """A worker fired more often than its recipe price allows (choice 4)."""


class NoProviderError(RuntimeError):
    """A recipe entry names a task family nothing provides."""


# ------------------------------------------------ the terminal consumer

@runtime_checkable
class CloseVerdict(Protocol):
    """What one consult answers (worklist B12).

    Three members, every one a core type or JSON, because neither of the
    two packages may import the other. There is deliberately NO status
    field: a terminal answer is read off the STORE (the ``CloseRecord``
    these writes carry), never off the consumer. READ-ONLY properties,
    because a settable member would refuse the obvious implementation —
    a frozen dataclass.
    """

    @property
    def writes(self) -> tuple[Write, ...]: ...

    @property
    def blobs(self) -> tuple[StagedBlob, ...]: ...

    @property
    def report(self) -> dict[str, Any]: ...


@runtime_checkable
class CloseConsult(Protocol):
    """The engine's terminal consumer: the volume close (worklist B12).

    **Not a provider, and no longer dressed as one** (the argument is
    ``engine/DESIGN.md``'s): a provider expands a frontier into queued,
    priced, spend-once work; the close does none of that — the
    orchestrator TIMES it (§9: a verified close preempts everything),
    asks it once, and stops.

    :attr:`frontier` is the whole eligibility mechanism, and it keeps the
    property the spend row used to provide (M11): its VERSION is a
    membership count, certificates are terminal and immutable (L5), so a
    version that has not moved means the same equations, refused in
    integer time. The engine records that version per gate.

    ``mode`` is the engine's second scheduling word (2026-08-13) —
    ``observe`` counts and reports, ``close`` decides when the count gate
    opens, ``final`` skips that gate — spelled on both sides of the
    engine↔solve wall and pinned equal by a data test.
    """

    @property
    def frontier(self) -> ResourceKey: ...

    def consult(self, view: SolveView, *, mode: str) -> CloseVerdict:
        """Answer over the certified frontier under one consult mode."""


@runtime_checkable
class RunObserver(Protocol):
    """The diag surface, as the engine is allowed to know it (L12).

    Push-only and inert: the run hands over its commit ledger once, asks
    whether anyone is watching, and publishes frozen instants. The engine
    may not import ``diag``, so what it needs is declared here and
    satisfied structurally.
    """

    def adopt_ledger(self, ledger: CommitLedger) -> None: ...

    def wants_snapshot(self) -> bool: ...

    def publish(self, snapshot: RunSnapshot | None = None, *,
                error: str | None = None) -> None: ...


@dataclass(frozen=True)
class RunOutcome:
    """What one session run did. Status honesty is L15's, not the caller's.

    ``close`` is the terminal consumer's own JSON-able report
    (``CloseVerdict.report``), carried through untouched: the engine has
    no business typing a fountain state.
    """

    status: str                       # open | verified | integrity_failure |
                                      # unsupported
    payload: bytes | None = None
    close: dict[str, Any] | None = None
    commits: int = 0
    fires: int = 0
    certified: int = 0
    exhausted: bool = False
    resumed_terminal: bool = False
    reason: str | None = None

    @property
    def verified(self) -> bool:
        return self.status == "verified"


def close_progress(last: dict[str, Any] | None, certified: int
                   ) -> dict[str, Any]:
    """The terminal consumer's own report, or "not consulted" (R1).

    The engine renders nothing: exactly the last consult's own report,
    or the one fact it can state without having asked.
    """
    if last is None:
        return {"status": "not_consulted", "certified": certified}
    return dict(last)


__all__ = [
    "CONSULT_CLOSE", "CONSULT_FINAL", "CONSULT_OBSERVE", "CloseConsult",
    "CloseVerdict", "FireCountTripwire", "NoProviderError", "ROUTE_PULL",
    "RunObserver", "RunOutcome", "close_progress",
]
