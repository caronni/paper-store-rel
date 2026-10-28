"""Detached, non-authoritative fountain-close progress values."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fountain_close import CloseResult


@dataclass(frozen=True, slots=True)
class CloseBlockProgress:
    """THE per-fountain-block accounting row (the promise is per block).

    One dataclass serves both the numerical close (``CloseResult.blocks``)
    and its detached progress projection — the two field-identical mirrors
    merged in the Phase-2 rework.  ``needed`` is K_b source symbols,
    ``have`` the distinct certified symbols, ``rank`` the exact independent
    generator rows; ``stream_id`` only for stream-stratified codings
    (CMY8), K and CMY7 leave it ``None``."""

    block: int
    needed: int
    have: int
    rank: int
    solved: bool
    stream_id: str | None = None

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 0 for value in (
                self.block, self.needed, self.have, self.rank)):
            raise ValueError("close block progress must be non-negative")
        if type(self.solved) is not bool:
            raise TypeError("close block solved flag must be boolean")
        if self.stream_id is not None and (
                not isinstance(self.stream_id, str) or not self.stream_id):
            raise ValueError("close block stream_id must be non-empty")

    @property
    def rank_shortfall(self) -> int:
        """Independent generator rows still needed by this block."""
        return self.needed - self.rank


@dataclass(frozen=True, slots=True)
class CloseSurplusInconsistency:
    """One certified symbol that disagrees with the reconstructed volume.

    The D16 report-only post-solve surplus audit: a dependent (surplus)
    fountain equation whose certified value the GF(2) solve silently
    masked, identified by its certificate coordinates.  Advisory only —
    never a close outcome, never persisted.
    """

    stream_id: str
    counter: int
    page: int
    ty: int
    tx: int

    def __post_init__(self) -> None:
        if not isinstance(self.stream_id, str) or not self.stream_id:
            raise ValueError("surplus stream_id must be non-empty text")
        if any(type(value) is not int or value < 0 for value in (
                self.counter, self.page, self.ty, self.tx)):
            raise ValueError(
                "surplus inconsistency coordinates must be non-negative")


@dataclass(frozen=True, slots=True)
class CloseMetadataProgress:
    """Exact metadata facts already computed by numerical close."""

    rank: int
    rank_shortfall: int
    check_shortfall: int
    inconsistent: bool
    unique_counters: int

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 0 for value in (
                self.rank, self.rank_shortfall, self.check_shortfall,
                self.unique_counters)):
            raise ValueError("close metadata progress must be non-negative")
        if type(self.inconsistent) is not bool:
            raise TypeError("close metadata inconsistency flag must be boolean")


@dataclass(frozen=True, slots=True)
class CloseProgress:
    k_total: int | None
    symbols_used: int
    blocks: tuple[CloseBlockProgress, ...] = ()
    metadata: CloseMetadataProgress | None = None
    # D16 report-only surplus audit (transient advisory data; CloseProgress
    # is never persisted, so this field carries no durable-state weight).
    surplus_inconsistencies: tuple[CloseSurplusInconsistency, ...] = ()
    # Count-only marking: True when no decoder ran (a deferred barrier or a
    # count-gated skip), so block ``rank``/``solved`` were never computed
    # and must render as deferred, never as zero (§10.3.2 / §10.4).
    count_only: bool = False

    def __post_init__(self) -> None:
        if self.k_total is not None and (
                type(self.k_total) is not int or self.k_total < 0):
            raise ValueError("close K must be a non-negative integer")
        if type(self.symbols_used) is not int or self.symbols_used < 0:
            raise ValueError("close symbol count must be non-negative")
        if any(type(row) is not CloseBlockProgress for row in self.blocks):
            raise TypeError("close progress contains a foreign block")
        if (self.metadata is not None
                and type(self.metadata) is not CloseMetadataProgress):
            raise TypeError("close progress contains foreign metadata")
        if any(type(row) is not CloseSurplusInconsistency
               for row in self.surplus_inconsistencies):
            raise TypeError(
                "close progress contains a foreign surplus entry")
        if type(self.count_only) is not bool:
            raise TypeError("close progress count_only flag must be boolean")


def from_fountain_result(result: CloseResult) -> CloseProgress:
    """Detach exact block accounting from a numerical close result.

    ``CloseResult.blocks`` and ``surplus_inconsistencies`` already carry
    this module's row types (one dataclass, no mirror copies), so they
    pass through; only the metadata facts detach from the diagnostics
    mapping.
    """
    diagnostics = result.diagnostics
    metadata = None
    names = (
        "metadata_rank", "metadata_rank_shortfall",
        "metadata_check_shortfall", "metadata_inconsistent",
        "n_unique_metadata_counters",
    )
    if all(name in diagnostics for name in names):
        metadata = CloseMetadataProgress(
            int(diagnostics[names[0]]), int(diagnostics[names[1]]),
            int(diagnostics[names[2]]),
            bool(diagnostics[names[3]]), int(diagnostics[names[4]]),
        )
    return CloseProgress(
        result.k_total, int(result.symbols_used), tuple(result.blocks),
        metadata, tuple(result.surplus_inconsistencies))


__all__ = [
    "CloseBlockProgress", "CloseMetadataProgress", "CloseProgress",
    "CloseSurplusInconsistency", "from_fountain_result",
]
