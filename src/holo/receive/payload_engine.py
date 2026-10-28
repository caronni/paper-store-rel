"""Stream-generic payload attempt orchestration (RECEIVE-DESIGN §6.4).

One engine owns the E023b attempt schedule for every coding: each physical
acquisition is first judged by itself (``scan``), unresolved same-lane
stragglers are judged from the complete acquisition frontier (``union``),
an optional advisory pre-close may prove further work moot, and the latest
failed baseline view per (address, stream) gets exactly one selective
``retry150``.  The engine never decodes, never mints identities, and never
touches persistence: the per-codec leaf owns detection, decode, attempt
identity, certificate minting, and conflict checks.  K runs this with the
single stream ``"main"``; CMY7 with its packed single stream; CMY8 with the
three presence-bit streams ``C``/``M``/``Y``.

The engine guarantees the doctrine invariants the two historical
implementations each enforced by hand: deterministic address order, one
attempt per exact (view, stream, stage) identity, retry never tunnelling
past its baseline evidence, and retry silence after a terminal pre-close.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Protocol, Sequence

from .evidence import (
    AttemptStage,
    AttemptState,
    TileAttemptRecord,
    TileCertificateRecord,
)
from .evidence_blocks import (
    EvidenceBlock,
    TileAttemptView,
    blocks_by_address,
    tile_attempt_view,
)
from .records import CertificateStore
from . import _parallel


class AttemptLeaf(Protocol):
    """Per-codec numerical leaf driven by the engine.

    ``unresolved_streams`` names the streams still needing work at one tile
    address.  ``attempt`` evaluates one stream from one exact evidence view,
    records the outcome in the leaf's own ledgers (dedup included), and
    returns the durable attempt row — or ``None`` when the exact attempt
    identity was already recorded (a true no-op).
    """

    def unresolved_streams(
        self, address: tuple[int, int, int]) -> tuple[str, ...]: ...

    def attempt(
        self,
        view: TileAttemptView,
        stream_id: str,
        stage: AttemptStage,
    ) -> TileAttemptRecord | None: ...



class RecordingLeaf:
    """Shared leaf bookkeeping: dedup, store ledger, progress emission.

    The per-codec ``decode`` callable is the only branch:
    ``decode(view, stream_id, stage) -> (TileAttemptRecord,
    TileCertificateRecord | None)``.  Certificate conflicts surface from
    the store (fatal by doctrine, never voted).
    """

    def __init__(
        self,
        store: CertificateStore,
        decode: Callable[
            [TileAttemptView, str, AttemptStage],
            tuple[TileAttemptRecord, TileCertificateRecord | None],
        ],
        *,
        attempt_progress: Callable[
            [TileAttemptRecord, TileAttemptView], None] | None = None,
        retry_attempt_progress: Callable[
            [TileAttemptRecord, TileAttemptView], None] | None = None,
    ) -> None:
        self._store = store
        self._decode = decode
        self._progress = attempt_progress
        self._retry_progress = (
            attempt_progress
            if retry_attempt_progress is None
            else retry_attempt_progress)
        self._seen: set[str] = set()
        self.attempts: list[TileAttemptRecord] = []
        self.certificates: list[TileCertificateRecord] = []
        self.retry_certificates: list[TileCertificateRecord] = []

    def unresolved_streams(
        self, address: tuple[int, int, int]) -> tuple[str, ...]:
        return self._store.unresolved_streams(address)

    def attempt(
        self,
        view: TileAttemptView,
        stream_id: str,
        stage: AttemptStage,
    ) -> TileAttemptRecord | None:
        record, certificate = self._decode(view, stream_id, stage)
        return self._record(view, stage, record, certificate)

    def attempt_batch(
        self,
        items: Sequence[tuple[TileAttemptView, str, AttemptStage]],
    ) -> list[TileAttemptRecord | None]:
        """Batch form of :meth:`attempt`: pooled pure decode, then the
        exact sequential recording (ledger order, dedup, store, progress
        emission) in item order — value-identical to per-item calls for
        any worker count because every item addresses a distinct tile
        (the engine's stage contracts) and ``decode`` is a pure
        function of its arguments."""
        decoded = _parallel.ordered_map(
            lambda item: self._decode(item[0], item[1], item[2]), items)
        return [
            self._record(view, stage, record, certificate)
            for (view, _stream_id, stage), (record, certificate)
            in zip(items, decoded, strict=True)
        ]

    def _record(
        self,
        view: TileAttemptView,
        stage: AttemptStage,
        record: TileAttemptRecord,
        certificate: TileCertificateRecord | None,
    ) -> TileAttemptRecord | None:
        if record.attempt_id in self._seen:
            return None
        self._seen.add(record.attempt_id)
        self._store.record_attempt(record, certificate)
        self.attempts.append(record)
        if certificate is not None:
            self.certificates.append(certificate)
            if stage is AttemptStage.RETRY150:
                self.retry_certificates.append(certificate)
        progress = (self._retry_progress
                    if stage is AttemptStage.RETRY150 else self._progress)
        if progress is not None:
            progress(record, view)
        return record


@dataclass(frozen=True, slots=True)
class EngineRun:
    """What the engine scheduled; the leaf owns the durable ledgers."""

    attempts: tuple[TileAttemptRecord, ...]
    retry_frontier: tuple[TileAttemptRecord, ...]
    terminal_close: bool


def run_attempts(
    new_blocks: Iterable[EvidenceBlock],
    frontier_blocks: Iterable[EvidenceBlock],
    *,
    lane_id: str,
    leaf: AttemptLeaf,
    preclose: Callable[[], bool] | None = None,
    retry_open: Callable[
        [tuple[TileAttemptRecord, ...]], None] | None = None,
) -> EngineRun:
    """Run the complete scan -> union -> (preclose) -> retry150 schedule.

    ``new_blocks`` are this capture's frozen one-owner evidence blocks;
    ``frontier_blocks`` the complete retained same-lane frontier (prior
    captures merged with ``new_blocks``).  ``preclose``, when given, runs
    once after the ordinary stages and returns True when a rank/SHA close
    already succeeded — in that case the retry budget is not spent.
    """
    current = tuple(sorted(
        new_blocks,
        key=lambda row: (row.source_sha256, row.lane_id, row.address)))
    frontier = tuple(frontier_blocks)
    if any(row.lane_id != lane_id for row in (*current, *frontier)):
        raise ValueError("payload engine: evidence from another lane")
    recorded: list[TileAttemptRecord] = []

    def run(view: TileAttemptView, stream_id: str,
            stage: AttemptStage) -> TileAttemptRecord | None:
        record = leaf.attempt(view, stream_id, stage)
        if record is not None:
            recorded.append(record)
        return record

    def run_batch(
        items: Sequence[tuple[TileAttemptView, str, AttemptStage]],
    ) -> list[TileAttemptRecord | None]:
        """One stage's attempts: pooled decode when the leaf supports it.

        Legal exactly because every item in one batch addresses a
        distinct tile (stage contracts below), so no item's decode or
        ``unresolved_streams`` consult depends on another item's
        recording; results are recorded in item order, reproducing the
        sequential ledger bit for bit.
        """
        attempt_batch = getattr(leaf, "attempt_batch", None)
        if attempt_batch is None:
            return [run(*item) for item in items]
        rows: list[TileAttemptRecord | None] = attempt_batch(items)
        recorded.extend(row for row in rows if row is not None)
        return rows

    # Stage 1: every current physical acquisition is first judged by
    # itself.  One block per address per capture (the v0.28 SCAN
    # contract) makes the per-block ``unresolved_streams`` consults
    # independent, so they hoist above the batched decodes; the guard
    # below falls back to the interleaved sequential form if that
    # contract were ever violated upstream.
    if len({block.address for block in current}) == len(current):
        scan_items: list[tuple[TileAttemptView, str, AttemptStage]] = []
        for block in current:
            needed = leaf.unresolved_streams(block.address)
            if not needed:
                continue
            view = tile_attempt_view((block,))
            scan_items.extend(
                (view, stream_id, AttemptStage.SCAN)
                for stream_id in needed)
        run_batch(scan_items)
    else:
        for block in current:
            needed = leaf.unresolved_streams(block.address)
            if not needed:
                continue
            view = tile_attempt_view((block,))
            for stream_id in needed:
                run(view, stream_id, AttemptStage.SCAN)

    # Stage 2: the complete same-lane physical-acquisition frontier, one
    # visit per address.  ``current`` is the committing capture's blocks
    # ONLY (the v0.28 SCAN contract, both codecs — one block per address
    # per capture); ``frontier`` merges every retained same-lane capture
    # at the v0.33 evidence-lane key, so an address may hold components
    # from several captures.  Addresses are distinct by construction, so
    # the consults hoist above the batched decodes exactly as in SCAN.
    frontier_by_address = blocks_by_address(frontier, lane_id=lane_id)
    union_items: list[tuple[TileAttemptView, str, AttemptStage]] = []
    for address in sorted({block.address for block in current}):
        needed = leaf.unresolved_streams(address)
        if not needed:
            continue
        components = frontier_by_address.get(address, ())
        if len(components) < 2:
            continue
        view = tile_attempt_view(components)
        union_items.extend(
            (view, stream_id, AttemptStage.UNION)
            for stream_id in needed)
    run_batch(union_items)

    # Advisory pre-close: counts can only prove close is impossible; a full
    # rank/SHA success here makes the retry budget moot.  The runtime
    # barrier remains the sole authoritative durable close.  Whether a close
    # was genuinely evaluated is the caller's bookkeeping, not the engine's.
    terminal_close = bool(preclose()) if preclose is not None else False

    # Selective retry150: the latest ordinary failed view per
    # (address, stream), never tunnelling past its baseline evidence.
    latest: dict[tuple[int, int, int, str], TileAttemptRecord] = {}
    for row in recorded:
        if row.stage in (AttemptStage.SCAN, AttemptStage.UNION):
            latest[row.work_key] = row
    retry_frontier = tuple(
        row for _key, row in sorted(latest.items())
        if row.state is AttemptState.ATTEMPTED_FAILED
        and row.certificate_id is None
    )
    retained = {row.block_id: row for row in frontier}
    # Observer-only announcement of the frontier about to be retried
    # (RECEIVE-DESIGN v0.27 pane-D in-flight layer).  Pure emission: it
    # receives the already-frozen tuple and cannot affect order or results.
    if retry_open is not None and retry_frontier and not terminal_close:
        retry_open(retry_frontier)
    retry_parents: list[TileAttemptRecord] = []
    retry_items: list[tuple[TileAttemptView, str, AttemptStage]] = []
    for parent in (() if terminal_close else retry_frontier):
        missing = [identity for identity in parent.component_block_ids
                   if identity not in retained]
        if missing:
            raise ValueError(
                "payload engine: retry parent lost retained compact evidence")
        view = tile_attempt_view(tuple(
            retained[identity] for identity in parent.component_block_ids))
        retry_parents.append(parent)
        retry_items.append((view, parent.stream_id, AttemptStage.RETRY150))
    # One retry per distinct (address, stream) baseline: batch-legal.
    for parent, record in zip(
            retry_parents, run_batch(retry_items), strict=True):
        if record is None:
            continue
        if (record.component_block_ids != parent.component_block_ids
                or record.dependency_certificate_ids
                != parent.dependency_certificate_ids):
            raise ValueError(
                "payload engine: retry changed its baseline evidence")

    return EngineRun(tuple(recorded), retry_frontier, terminal_close)


__all__ = ["AttemptLeaf", "EngineRun", "RecordingLeaf", "run_attempts"]
