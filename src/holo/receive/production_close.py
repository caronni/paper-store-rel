"""Production fountain-close stage (Track 3 close seam).

``ProductionClose`` adapts the E023c verified fountain close into the
runtime's typed close seam: the v0.33 close-attempt schedule
(RECEIVE-DESIGN §8.1), the v0.36 mint-once conversion memo, and the
count-only gated-skip progress.  Split from ``production.py`` in the
Phase 4 hammer batch (RECEIVE-DESIGN v0.38); behavior unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from ..format.descriptor import FormatSpec

from .close_progress import from_fountain_result
from .fountain_close import (
    CloseResult,
    close_count_status,
    close_record_from_result,
    close_volume,
    metadata_progress,
)
from .records import certificate_for_close
from .runtime import CloseContext, CloseExecution
from .types import CloseStatus


@dataclass(frozen=True, slots=True)
class ProductionClose:
    policy_id: ClassVar[str] = "holo/e023-close/fountain-v2-sha256-v1"

    _gate: dict = field(default_factory=dict, repr=False, compare=False)
    # Mint-once memo (records immutable + content-addressed): the close
    # reconstruction runs once per certificate_id, never once per consult.
    _close_certificates: dict = field(
        default_factory=dict, repr=False, compare=False)

    def _certificates_for_close(
        self, records: tuple, spec: FormatSpec,
    ) -> tuple:
        converted = []
        for row in records:
            cached = self._close_certificates.get(row.certificate_id)
            if cached is None:
                cached = certificate_for_close(row, spec)
                self._close_certificates[row.certificate_id] = cached
            converted.append(cached)
        return tuple(converted)

    def _gated(
        self, certificates: tuple, context: CloseContext,
    ) -> CloseExecution | None:
        """v0.33 close-attempt schedule (RECEIVE-DESIGN §8.1).

        A cheap open execution when this consult provably cannot verify;
        None when the fountain must be asked.  Precedence: metadata-
        terminal states consult unconditionally (``close_count_status``
        reports them ready with no counts — K is unknown there); then
        the count gate; then, after a want_more attempt on this
        instance, the exact per-(stream, block) shortfall baseline (rank
        gain is bounded by distinct-ESI gain, so every skip is provably
        open).  A rewound/foreign state resets the baseline and
        consults.  The skip's count-only progress runs over the
        already-converted ``certificates``.
        """
        # A retained VERIFIED close stores only SHA/length identity, not
        # payload bytes.  Resume / ``--complete`` replay must re-ask the
        # fountain.  Building CloseExecution(verified, payload=None) here
        # — even on a path that would later return None — trips the
        # verified-payload invariant (e028 ink-page rerun, 2026-08-04).
        if context.state.close.status is CloseStatus.VERIFIED:
            return None
        spec = context.spec
        skip: CloseExecution | None = CloseExecution(
            context.state.close, None,
            lambda: metadata_progress(certificates, spec))
        ready, counts = close_count_status(certificates, spec)
        if not ready:
            return skip
        if counts is None:
            return None
        baseline = self._gate.get("baseline")
        if not baseline:
            return None
        for key, (have_then, shortfall) in baseline.items():
            have_now = counts.get(key, 0)
            if have_now < have_then:
                self._gate.clear()
                return None
            if have_now - have_then < shortfall:
                return skip
        return None

    def _note(self, result: CloseResult, spec: FormatSpec) -> None:
        if result.status != "open":
            self._gate.clear()
            return
        # Key exactly as close_count_status does: a pooled row has ONE
        # stream-mixed block space named "pooled" (its rows carry no
        # stream label), every other row keys by stream — K's unlabeled
        # single stream stays "main".
        pooled = spec.pooled_fountain
        baseline: dict[tuple[str, int], tuple[int, int]] = {}
        for row in result.blocks:
            shortfall = int(row.needed) - int(row.rank)
            if shortfall > 0 and not row.solved:
                key = "pooled" if pooled else (row.stream_id or "main")
                baseline[(key, int(row.block))] = (
                    int(row.have), shortfall)
        self._gate["baseline"] = baseline or None

    def process(self, context: CloseContext) -> CloseExecution:
        certificates = self._certificates_for_close(
            context.state.certificates, context.spec)
        gated = self._gated(certificates, context)
        if gated is not None:
            return gated
        result = close_volume(certificates, context.spec)
        self._note(result, context.spec)
        progress = lambda: from_fountain_result(result)
        record = close_record_from_result(
            result,
            (None if result.status == "open"
             else context.certificate_frontier_sha256),
        )
        return CloseExecution(
            record,
            result.payload if result.status == "verified" else None,
            progress,
        )


__all__ = ["ProductionClose"]
