"""The volume close: a TERMINAL CONSUMER, not a provider (worklist B12).

The close was modelled as a provider family and the tree half-admitted it
was not one: the orchestrator TIMED the consult itself, never queued it,
minted a descriptor nothing scheduled, and bound the worker slotless into
its in-flight map. The type checker said the same thing from the other
side — ``CloseProvider`` did not satisfy ``core.Provider``, because its
``expand`` narrowed the view (contravariance) and the mismatch could not
be caught by a ``runtime_checkable`` ``isinstance``, which reads names and
never signatures. **RULED 2026-08-12**: the close is the engine's own
narrow terminal consumer, and the provider costume — expansion, minting,
routes, declines, a work id, a spend row — is gone.

What is left is the smallest interface that does the job (the engine
declares it structurally as ``engine.orchestrator.CloseConsult``; solve
implements it without importing engine, exactly as ``SessionPlane``
implements ``engine.Plane``):

* :data:`VolumeClose.frontier` — the derived key whose VERSION is the
  consult's input digest. It keeps the M11 property the spend test used
  to provide: the certified frontier is a membership count, certificates
  are terminal and immutable (L5), so a version that has not moved means
  the SAME equations and the engine can refuse a re-consult in integer
  time, before anything is materialised.
* :meth:`VolumeClose.consult` — one look at the certified frontier under
  one of three MODES. The engine defines the vocabulary on its side of
  the wall and decides WHEN to consult and with which mode, which is
  scheduling; the strings are pinned equal from both sides by
  ``holo2/tests/engine/test_close_vocabulary.py`` (the footing-selector
  precedent, WP-4/16):

  - ``observe`` — count, never close. What ``--complete`` runs mid-run
    (user ruling 2026-08-13): §9 says the solvable fountain state must
    not stop the session, but that suppresses the DECISION, not the
    OBSERVATION — K, the metadata rank and every block's have/needed
    stay live on the report while the close stays deferred.
  - ``close`` — close when the count gate opens; count otherwise.
  - ``final`` — close now, skipping the count gate (the exhaustion
    consult; ``--complete``'s one deferred close).

**P3-1 — the incremental close state** (ruled 2026-08-12, built
2026-08-13). Every consult used to rebuild the close's whole input:
O(certified) blob reads for symbols the count gate never consumes, the
full metadata GF(2) elimination (twice on a not-ready consult — once in
the gate, once for the counting report), and one ``VolumeCode`` per
stream, per consult. Measured on the real sheet: 1,358 consults = 34.1 s
= 6.0% of wall, linear at ~30 µs/certificate. The consult now keeps
:class:`_CloseState` — in-memory, derived, DISPOSABLE — and pays O(new
certificates) per consult:

* the metadata equations run through an incremental eliminator
  (:class:`_MetadataGate`, same algebra as the carried
  ``decode_metadata``: echelon basis of augmented 25-bit rows). At rank
  24 the word is UNIQUE — a full-rank GF(2) system has one solution — so
  a later equation can never revise K; it either checks out or proves
  the certificate SET inconsistent, which is an integrity event (L5),
  terminal, never voted. The 48-distinct-equation floor is a
  false-accept budget, not a convergence wait: with exactly rank-many
  equations no contradiction is even possible, and every equation past
  rank 24 is one surplus parity check (≥24 of them at the floor,
  residual ≤ ~2⁻²⁴). Interpretation is never re-implemented here: ONE
  call to the carried ``decode_metadata`` at the trust transition, and
  its verdict is cached (the word cannot move).
* per-(stream, block) distinct-ESI counts are bumped per certificate
  through the ONE authoritative mapping (``format.volume_code_for``,
  built once per stream when K becomes trusted); count-ready is a
  monotone shortfall counter reaching zero.
* ZERO payload-symbol blob reads before a close attempt: the gate
  consumes ``(counter, stream, metadata bit)`` off the tile records.
  Symbols are materialised only for ``close_volume``.
* once count-ready, a re-close runs only when it could answer
  differently (:meth:`_CloseState.close_is_new`): a solved block stays
  solved — adding GF(2) equations never lowers rank — so an OPEN attempt
  can only improve when a block it could not solve gains a distinct
  symbol, or metadata has since become terminal. Exact, not heuristic.

Authority is unchanged: every durable outcome — verified payload,
integrity failure, unsupported — is still the carried ``close_volume``
computing from the full certificate set (its own metadata elimination
included), and the counting state is never an input to it. A fresh
:class:`VolumeClose` (resume) rebuilds the state from the tile map in
one pass.

Two properties are worth restating because they are easy to lose:

* **The engine never sees a format object.** The report is plain JSON the
  orchestrator carries into ``RunOutcome.close`` and the diag snapshot
  untouched; the durable answer travels the ordinary way, as a write plus
  a staged blob, and a terminal record freezes the session by itself
  (§5.5). The engine reads terminality off the STORE, never off this
  verdict — which is why the verdict carries no status field of its own.
* **One consult per certified frontier, never per stream** — a per-stream
  consult could report a partial close (PROVIDERS.md §9.9).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core import (CLOSE_KEY, ResourceKey, SolveView, StagedBlob, Write,
                    stage_bytes)
from ..format import (METADATA_WORD_BITS, MIN_METADATA_EQUATIONS,
                      SUPPORTED_METADATA_VERSIONS, CertifiedStreamSymbol,
                      CloseResult, CloseSpec, Family, MetadataDecode,
                      VolumeCode, close_record_from_result, close_volume,
                      coefficient_mask, decode_metadata, volume_code_for)
from .records import COLLECTION_CERTIFIED, parse_tile_key
from .tilemap import TileMapError
from .view import PlaneView, as_plane

#: The consult modes, as solve spells them. The engine declares the same
#: three strings on its side of the import wall (`engine.orchestrator`);
#: a data pin asserts the vocabularies match (WP-4/16 precedent).
CONSULT_OBSERVE = "observe"
CONSULT_CLOSE = "close"
CONSULT_FINAL = "final"
_CONSULT_MODES = (CONSULT_OBSERVE, CONSULT_CLOSE, CONSULT_FINAL)

_WORD_MASK = (1 << METADATA_WORD_BITS) - 1


def certified_symbols(view: PlaneView,
                      spec: CloseSpec) -> tuple[CertifiedStreamSymbol, ...]:
    """Certified work keys as the close's input equations (§5.5, L9)."""
    symbols: list[CertifiedStreamSymbol] = []
    for key in view.certified_work_keys():
        page, ty, tx, stream = parse_tile_key(key)
        record = view.tile(key)
        if record is None or record.bits_ref is None or record.metadata_bit is None:
            raise TileMapError(
                f"{key}: CERTIFIED without bits or metadata bit (L5)")
        symbols.append(CertifiedStreamSymbol(
            counter=spec.tile_counter(page, ty, tx),
            page=page, ty=ty, tx=tx, stream_id=stream,
            symbol=view.read_array(record.bits_ref),
            metadata_bit=int(record.metadata_bit)))
    return tuple(symbols)


def _close_report(result: CloseResult, certified: int) -> dict[str, Any]:
    """The close's own numbers, JSON-able, for the observer and the CLI."""
    return {
        "status": result.status,
        "k_total": result.k_total,
        "symbols_used": result.symbols_used,
        "reason": result.reason,
        "metadata_rank": result.diagnostics.get("metadata_rank"),
        "metadata_counters": result.diagnostics.get(
            "n_unique_metadata_counters"),
        "blocks": [
            {"stream": row.stream_id, "block": row.block, "needed": row.needed,
             "have": row.have, "rank": row.rank, "solved": row.solved,
             "shortfall": row.rank_shortfall}
            for row in result.blocks
        ],
        "certified": certified,
    }


class _MetadataGate:
    """Incremental mirror of the carried metadata elimination (P3-1).

    Same algebra as ``format.decode_metadata`` — an echelon basis of
    augmented 25-bit integer rows (bit 24 is the right-hand side), lowest
    set bit as the pivot — maintained one equation at a time: ≤24 integer
    XORs per NEW counter, and a redundant equation reduces to zero where
    a nonzero right-hand side flips :attr:`inconsistent`. Interpretation
    (version, K, reserved bits, the 48-equation trust floor) is never
    re-implemented: :meth:`settle` calls the carried ``decode_metadata``
    exactly ONCE, at the trust transition, and caches its verdict — the
    word cannot move after rank 24, so nothing later can revise it,
    only contradict the set (terminal, L5).
    """

    def __init__(self) -> None:
        self.seen: dict[int, int] = {}
        self._basis: dict[int, int] = {}
        self.inconsistent = False
        self.decode: MetadataDecode | None = None

    @property
    def rank(self) -> int:
        return len(self._basis)

    @property
    def unique(self) -> int:
        return len(self.seen)

    def observe(self, counter: int, bit: int) -> None:
        """One certified metadata equation; duplicates must agree."""
        previous = self.seen.get(counter)
        if previous is not None:
            if previous != bit:
                self.inconsistent = True
            return
        self.seen[counter] = bit
        if self.inconsistent:
            return
        row = coefficient_mask(counter) | (bit << METADATA_WORD_BITS)
        while row & _WORD_MASK:
            lowest = (row & _WORD_MASK) & -(row & _WORD_MASK)
            pivot = lowest.bit_length() - 1
            held = self._basis.get(pivot)
            if held is None:
                self._basis[pivot] = row
                return
            row ^= held
        if (row >> METADATA_WORD_BITS) & 1:
            self.inconsistent = True

    def settle(self) -> None:
        """The one carried-interpretation call, at the trust transition."""
        if (self.decode is None and not self.inconsistent
                and self.rank == METADATA_WORD_BITS
                and self.unique >= MIN_METADATA_EQUATIONS):
            decode = decode_metadata(sorted(self.seen.items()))
            if decode.inconsistent:
                self.inconsistent = True
                return
            if decode.rank != self.rank:
                raise TileMapError(
                    "the incremental metadata rank disagrees with the "
                    f"carried elimination ({self.rank} vs {decode.rank})")
            self.decode = decode

    @property
    def k_total(self) -> int | None:
        """K exactly when the carried gate would yield it (trusted)."""
        if (self.decode is None or not self.decode.ok
                or self.decode.version not in SUPPORTED_METADATA_VERSIONS):
            return None
        return self.decode.k

    @property
    def terminal(self) -> bool:
        """Metadata-terminal: ``close_volume`` owes a durable answer now.

        Mirrors ``close_count_status``: an inconsistent system is
        terminal at ANY count, while a malformed word (nonzero reserved
        bits, K = 0) or an unsupported version becomes terminal only once
        the 48-equation trust floor is met — below it the carried state
        is ``incomplete`` and the gate keeps counting.
        """
        if self.inconsistent:
            return True
        return self.decode is not None and self.k_total is None


class _StreamCounts:
    """Distinct-ESI counts per fountain block of ONE stream (P3-1).

    ``short`` is the count-shortfall blocks still below their K_b; it is
    monotone downward under distinct-counter adds, so count-ready is one
    integer compare. Counts are NECESSARY, never sufficient — solvability
    is per-block GF(2) rank, which only ``close_volume``'s decoder knows.
    """

    def __init__(self, code: VolumeCode) -> None:
        self.code = code
        self.have = [0] * code.n_blocks
        self.short = code.n_blocks

    def add(self, counter: int) -> None:
        block, _row = self.code.block_row_of(counter)
        self.have[block] += 1
        if self.have[block] == self.code.k_per_block[block]:
            self.short -= 1


@dataclass(frozen=True)
class _Attempt:
    """What the last ``close_volume`` run knew, for :meth:`close_is_new`."""

    solved: frozenset[tuple[str, int]]
    have: dict[tuple[str, int], int]
    metadata_terminal: bool


class _CloseState:
    """P3-1: the consult's incremental derived state. DISPOSABLE.

    Nothing here is durable or authoritative: every durable outcome is
    the carried close computing from the full certificate set, and a
    fresh instance rebuilds from the tile map in one pass (what a resume
    pays). Certificates are terminal and immutable (L5), so the state
    only ever grows and a processed key can never change under it. The
    gate reads ``(counter, stream, metadata bit)`` off the tile records —
    no payload-symbol blob is touched before a close attempt.
    """

    def __init__(self, spec: CloseSpec) -> None:
        self.spec = spec
        self.processed: set[ResourceKey] = set()
        self.metadata = _MetadataGate()
        self.counters_by_stream: dict[str, set[int]] = {
            stream_id: set() for stream_id in spec.stream_ids}
        self.counts: dict[str, _StreamCounts] | None = None
        self.last_attempt: _Attempt | None = None

    # -- growth ----------------------------------------------------------

    def absorb(self, plane: PlaneView) -> None:
        """Fold every not-yet-seen certified work key into the state."""
        for key in plane.certified_work_keys():
            if key in self.processed:
                continue
            page, ty, tx, stream = parse_tile_key(key)
            record = plane.tile(key)
            if (record is None or record.bits_ref is None
                    or record.metadata_bit is None):
                raise TileMapError(
                    f"{key}: CERTIFIED without bits or metadata bit (L5)")
            self._ingest(key, stream, self.spec.tile_counter(page, ty, tx),
                         int(record.metadata_bit))
        self._settle()

    def _ingest(self, key: ResourceKey, stream: str, counter: int,
                bit: int) -> None:
        counters = self.counters_by_stream.get(stream)
        if counters is None:
            raise TileMapError(
                f"{key}: certified stream {stream!r} is not declared by "
                f"the printed row ({self.spec.stream_ids})")
        self.metadata.observe(counter, bit)
        if counter not in counters:
            counters.add(counter)
            if self.counts is not None:
                self.counts[stream].add(counter)
        self.processed.add(key)

    def _settle(self) -> None:
        self.metadata.settle()
        k_total = self.metadata.k_total
        if self.counts is None and k_total is not None:
            counts: dict[str, _StreamCounts] = {}
            for stream_id in self.spec.stream_ids:
                per_stream = _StreamCounts(
                    volume_code_for(self.spec, stream_id, k_total))
                for counter in self.counters_by_stream[stream_id]:
                    per_stream.add(counter)
                counts[stream_id] = per_stream
            self.counts = counts

    # -- the gate ---------------------------------------------------------

    @property
    def count_ready(self) -> bool:
        return (self.counts is not None
                and all(c.short == 0 for c in self.counts.values()))

    @property
    def ready(self) -> bool:
        """``close_count_ready``, incrementally: counts, or a metadata
        state only ``close_volume`` can turn into its durable answer."""
        return self.count_ready or self.metadata.terminal

    def close_is_new(self) -> bool:
        """Could ``close_volume`` answer differently than last time?

        A solved block stays solved — adding GF(2) equations never lowers
        rank — so an OPEN attempt can only improve when a block it could
        not solve gains a distinct symbol, or metadata has since become
        terminal. Exact, not heuristic; a skipped consult keeps
        publishing the counting report, and the surplus audit of any
        skipped symbol still happens at the eventual deciding close
        (it re-encodes every certified symbol of every solved block).
        """
        last = self.last_attempt
        if last is None:
            return True
        if self.metadata.terminal and not last.metadata_terminal:
            return True
        if self.counts is None:
            return False
        for stream_id, counts in self.counts.items():
            for block in range(counts.code.n_blocks):
                if (stream_id, block) in last.solved:
                    continue
                if counts.have[block] > last.have.get((stream_id, block), 0):
                    return True
        return False

    def record_attempt(self, result: CloseResult) -> None:
        """Freeze what this ``close_volume`` run knew.

        Recorded for EVERY attempt: only an open result is ever read back
        (:meth:`close_is_new` gates the next attempt), because a terminal
        result freezes the session and no further consult happens — but
        recording unconditionally keeps this method decision-free.
        """
        fallback = self.spec.stream_ids[0]
        self.last_attempt = _Attempt(
            solved=frozenset((row.stream_id or fallback, row.block)
                             for row in result.blocks if row.solved),
            have={(stream_id, block): counts.have[block]
                  for stream_id, counts in (self.counts or {}).items()
                  for block in range(counts.code.n_blocks)},
            metadata_terminal=self.metadata.terminal)

    # -- reports ----------------------------------------------------------

    def counting_report(self) -> dict[str, Any]:
        """The observer's view of a consult that decided nothing (yet).

        Key-compatible with the 2026-08-12 counting report; the per-block
        rows (``needed``/``have``, no rank — rank is the decoder's) join
        it once K is trusted, so the operator watches every block fill
        (user ask 2026-08-13). ``metadata_inconsistent`` appears only
        when true: under ``observe`` a terminal metadata state is still
        DEFERRED, and the report is where that state stays visible.

        ``reason`` here is always ``counting``; :meth:`VolumeClose.consult`
        overrides it for the two READY-but-undecided cases — ``deferred``
        (observe holds a ready state back) and ``no_new_answer`` (a
        close-mode re-attempt could not answer differently) — because
        only the consult knows the mode (review observation 2,
        2026-08-13).
        """
        gate = self.metadata
        report: dict[str, Any] = {
            "status": "open",
            "reason": "counting",
            "k_total": gate.k_total,
            "symbols_used": None,
            "metadata_rank": gate.rank,
            "metadata_counters": gate.unique,
            "blocks": self._count_rows(),
            "certified": len(self.processed),
        }
        if gate.inconsistent:
            report["metadata_inconsistent"] = True
        return report

    def _count_rows(self) -> list[dict[str, Any]]:
        if self.counts is None:
            return []
        single = self.spec.codec_family is Family.K
        rows: list[dict[str, Any]] = []
        for stream_id in self.spec.stream_ids:
            counts = self.counts[stream_id]
            rows.extend(
                {"stream": None if single else stream_id, "block": block,
                 "needed": int(counts.code.k_per_block[block]),
                 "have": counts.have[block]}
                for block in range(counts.code.n_blocks))
        return rows


@dataclass(frozen=True)
class VolumeVerdict:
    """What one consult answers: durable facts, staged bytes, and prose.

    The engine's ``CloseVerdict`` protocol is exactly these three members,
    all of them core types or JSON — which is what lets a package the
    engine may not import hand it an answer.
    """

    writes: tuple[Write, ...] = ()
    blobs: tuple[StagedBlob, ...] = ()
    report: dict[str, Any] = field(default_factory=dict)


class VolumeClose:
    """The volume close, K single-stream and multi-stream alike (CL1/CL2)."""

    #: The consult's input digest, as ONE derived membership key (M11).
    frontier: ResourceKey = COLLECTION_CERTIFIED

    def __init__(self) -> None:
        self._state: _CloseState | None = None

    def consult(self, view: SolveView, *, mode: str) -> VolumeVerdict:
        """Look at the certified frontier once and answer under ``mode``.

        The parameter is typed as core's ``SolveView`` because that is
        what the engine holds and hands over; the close legitimately needs
        the physical half (the printed row, the tile records), so it
        narrows with :func:`~holo2.solve.view.as_plane` — a statement
        about how the root wires one object, not a runtime branch.
        """
        if mode not in _CONSULT_MODES:
            raise ValueError(f"unknown consult mode {mode!r}")
        plane: PlaneView = as_plane(view)
        if self._state is None:
            self._state = _CloseState(plane.format_row.close_spec())
        state = self._state
        state.absorb(plane)
        if mode == CONSULT_OBSERVE or (
                mode == CONSULT_CLOSE
                and not (state.ready and state.close_is_new())):
            report = state.counting_report()
            if state.ready:
                # A ready state that is not being decided: say WHY the
                # report is still "open" — observe defers the decision,
                # a gated close-mode re-attempt could not answer
                # differently (review observation 2, 2026-08-13).
                report["reason"] = ("deferred" if mode == CONSULT_OBSERVE
                                    else "no_new_answer")
            return VolumeVerdict(report=report)
        certificates = certified_symbols(plane, state.spec)
        result = close_volume(certificates, state.spec)
        state.record_attempt(result)
        writes: tuple[Write, ...] = ()
        blobs: tuple[StagedBlob, ...] = ()
        if result.status == "verified":
            assert result.payload is not None
            blob = stage_bytes(result.payload)
            blobs = (blob,)
            writes = (Write(CLOSE_KEY,
                            close_record_from_result(result, blob.ref)),)
        elif result.status in ("integrity_failure", "unsupported"):
            writes = (Write(CLOSE_KEY, close_record_from_result(result)),)
        return VolumeVerdict(writes=writes, blobs=blobs,
                             report=_close_report(result, len(certificates)))


__all__ = ["CONSULT_CLOSE", "CONSULT_FINAL", "CONSULT_OBSERVE",
           "VolumeClose", "VolumeVerdict", "certified_symbols"]
