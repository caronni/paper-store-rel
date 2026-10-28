from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol

import numpy as np

from .. import data
from . import fountain, metadata

SHA_BYTES = 32
LEN_BYTES = 4
OVERHEAD_BYTES = SHA_BYTES + LEN_BYTES


class StreamLike(Protocol):
    stream_id: str
    symbol_bits: int
    fountain_aux: int | None


class RowLike(Protocol):
    seed: bytes
    tiles_yx: tuple[int, int]
    streams: tuple[StreamLike, ...]
    pooled_fountain: bool


class CertificateLike(Protocol):
    page: int
    ty: int
    tx: int
    stream_id: str
    user_bits: np.ndarray
    source: str


@dataclass(frozen=True)
class CloseResult:
    status: str
    payload: bytes | None
    k_total: int | None
    blocks: tuple[data.CloseBlockRow, ...] = ()
    symbols_used: int = 0
    reason: str | None = None
    metadata_version: int | None = None


def source_symbol_count(payload_len_bytes: int, symbol_bits: int) -> int:
    return -(-((OVERHEAD_BYTES + payload_len_bytes) * 8) // symbol_bits)


def try_unwrap(stream: bytes) -> bytes | None:
    if len(stream) < OVERHEAD_BYTES:
        return None
    declared_len = int.from_bytes(stream[SHA_BYTES:OVERHEAD_BYTES], "big")
    if declared_len > len(stream) - OVERHEAD_BYTES:
        return None
    data = stream[OVERHEAD_BYTES:OVERHEAD_BYTES + declared_len]
    if hashlib.sha256(data).digest() != stream[:SHA_BYTES]:
        return None
    return data


def _write_bits(out: np.ndarray, bit_offset: int,
                source_bits: np.ndarray) -> None:
    n_bits = int(source_bits.size)
    if n_bits == 0:
        return
    packed = np.packbits(source_bits, bitorder="big")
    byte_offset, shift = divmod(bit_offset, 8)
    if shift == 0:
        out[byte_offset:byte_offset + packed.size] |= packed
        return
    first_count = min(packed.size, out.size - byte_offset)
    if first_count:
        out[byte_offset:byte_offset + first_count] |= (
            packed[:first_count] >> shift
        )
    next_offset = byte_offset + 1
    second_count = min(packed.size, out.size - next_offset)
    if second_count:
        out[next_offset:next_offset + second_count] |= (
            packed[:second_count] << (8 - shift)
        )


def _nonzero_bits(data: bytes, bit_start: int, bit_end: int) -> bool:
    view = memoryview(data)
    pos = bit_start
    while pos < bit_end and pos & 7:
        if view[pos >> 3] & (1 << (7 - (pos & 7))):
            return True
        pos += 1
    if pos == bit_end:
        return False
    whole_end = bit_end - (bit_end & 7)
    if pos < whole_end and any(view[pos >> 3:whole_end >> 3]):
        return True
    pos = max(pos, whole_end)
    while pos < bit_end:
        if view[pos >> 3] & (1 << (7 - (pos & 7))):
            return True
        pos += 1
    return False


def _reassemble(streams: tuple[tuple[np.ndarray, int], ...],
                k_total: int) -> bytes:
    total_bits = k_total * sum(s_bits for _rows, s_bits in streams)
    out = np.zeros(-(-total_bits // 8), dtype=np.uint8)
    bit_offset = 0
    for rows, symbol_bits in streams:
        chunk_rows = max(1, fountain.CHUNK_BITS // symbol_bits)
        for row0 in range(0, k_total, chunk_rows):
            chunk = np.asarray(
                rows[row0:row0 + chunk_rows], dtype=np.uint8
            ).reshape(-1)
            _write_bits(out, bit_offset, chunk)
            bit_offset += int(chunk.size)
    return out.tobytes()


def _unwrap_gates(packed: bytes, total_symbol_bits: int,
                  k: int) -> bytes | None:
    payload = try_unwrap(packed)
    if payload is None:
        return None
    used_bits = (OVERHEAD_BYTES + len(payload)) * 8
    capacity_bits = k * total_symbol_bits
    if used_bits > capacity_bits:
        return None
    if source_symbol_count(len(payload), total_symbol_bits) != k:
        return None
    if _nonzero_bits(packed, used_bits, capacity_bits):
        return None
    return payload


def _tile_counter(row: RowLike, cert: CertificateLike) -> int:
    tiles_y, tiles_x = row.tiles_yx
    return cert.page * (tiles_y * tiles_x) + cert.ty * tiles_x + cert.tx


def _volume_code(row: RowLike, stream: StreamLike,
                 k_total: int) -> fountain.VolumeCode:
    tiles_per_page = row.tiles_yx[0] * row.tiles_yx[1]
    if stream.fountain_aux is None:
        return fountain.VolumeCode(
            k_total, stream.symbol_bits, row.seed,
            tiles_per_page=tiles_per_page)
    return fountain.VolumeCode(
        k_total, stream.symbol_bits, row.seed,
        tiles_per_page=tiles_per_page,
        stream_id=stream.stream_id,
        fountain_aux=stream.fountain_aux)


def _pooled_volume_code(row: RowLike, k_total: int) -> fountain.VolumeCode:
    widths = tuple(stream.symbol_bits for stream in row.streams)
    return fountain.VolumeCode(
        k_total, max(widths), row.seed,
        tiles_per_page=row.tiles_yx[0] * row.tiles_yx[1],
        n_streams=len(widths), groups=fountain.column_groups(widths))


_POOLED = "pooled"


def _symbol_index(row: RowLike, cert: CertificateLike,
                  stream_index: int) -> int:
    counter = _tile_counter(row, cert)
    if not row.pooled_fountain:
        return counter
    return metadata.equation_index(counter, stream_index,
                                   len(tuple(row.streams)))


_WORD_MASK = (1 << metadata.METADATA_BITS) - 1


class _MetadataGate:

    def __init__(self, row: RowLike) -> None:
        self.pooled = row.pooled_fountain
        self.n_streams = len(tuple(row.streams))
        self.max_index = (metadata.max_equation_index(self.n_streams)
                          if self.pooled else metadata.MAX_COUNTER)
        self.seen: dict[int, int] = {}
        self._basis: dict[int, int] = {}
        self.result: metadata.MetadataResult | None = None

    @property
    def rank(self) -> int:
        return len(self._basis)

    @property
    def unique(self) -> int:
        return len(self.seen)

    def observe(self, index: int, bit: int) -> None:
        previous = self.seen.get(index)
        if previous is not None:
            if previous != bit:
                raise data.IntegrityError(
                    f"metadata integrity failure: conflicting certified "
                    f"metadata bits at equation index {index}")
            return
        self.seen[index] = bit
        table = metadata.coefficient_table(self.max_index)
        row = int(table[index]) | (bit << metadata.METADATA_BITS)
        while row & _WORD_MASK:
            lowest = (row & _WORD_MASK) & -(row & _WORD_MASK)
            pivot = lowest.bit_length() - 1
            held = self._basis.get(pivot)
            if held is None:
                self._basis[pivot] = row
                return
            row ^= held
        if (row >> metadata.METADATA_BITS) & 1:
            raise data.IntegrityError(
                f"metadata integrity failure: certified metadata equations "
                f"inconsistent at equation index {index}")

    def settle(self) -> None:
        if (self.result is not None
                or self.rank < metadata.METADATA_BITS
                or self.unique < metadata.MIN_METADATA_EQUATIONS):
            return
        decoded = metadata.decode_metadata(self.seen, self.max_index)
        if decoded.inconsistent:
            raise data.IntegrityError(
                "metadata integrity failure: certified metadata equations "
                "inconsistent")
        if decoded.rank != self.rank:
            raise data.IntegrityError(
                f"incremental metadata rank {self.rank} disagrees with "
                f"the carried elimination ({decoded.rank})")
        self.result = decoded

    def classify(self) -> tuple[int | None, int | None, str]:
        decoded = metadata.decode_metadata(self.seen, self.max_index)
        if decoded.inconsistent:
            raise data.IntegrityError(
                "metadata integrity failure: certified metadata equations "
                "inconsistent")
        if decoded.ok:
            k = decoded.k * (self.n_streams if self.pooled else 1)
            return decoded.version, k, "ready"
        if (decoded.rank < metadata.METADATA_BITS
                or decoded.n_unique < metadata.MIN_METADATA_EQUATIONS):
            return decoded.version, None, "incomplete"
        if decoded.version not in metadata.SUPPORTED_METADATA_VERSIONS:
            return decoded.version, None, "unsupported"
        return decoded.version, None, "malformed"

    @property
    def terminal(self) -> bool:
        return self.result is not None and not self.result.ok


class CloseProgress:

    def __init__(self, row: RowLike) -> None:
        self.row = row
        self._streams = tuple(row.streams)
        self._index_of = {s.stream_id: i for i, s in enumerate(self._streams)}
        self._metadata = _MetadataGate(row)
        self._processed: set[object] = set()
        self._pending: list[tuple[str, int, np.ndarray]] = []
        self._decoders: dict[str, fountain.Decoder] | None = None
        self._k_total: int | None = None
        self._n_used = 0
        self._last_attempt: tuple | None = None

    @property
    def k_total(self) -> int | None:
        return self._k_total

    def absorb(self, certificates: Mapping[object, CertificateLike]) -> None:
        for key, cert in certificates.items():
            if key not in self._processed:
                self._ingest(key, cert)
        self._settle()

    def _ingest(self, key: object, cert: CertificateLike) -> None:
        index = self._index_of.get(cert.stream_id)
        if index is None:
            raise data.IntegrityError(
                f"{key}: certified stream {cert.stream_id!r} is not "
                f"declared by the printed row ({tuple(self._index_of)})")
        esi = _symbol_index(self.row, cert, index)
        decoder = _POOLED if self.row.pooled_fountain else cert.stream_id
        self._metadata.observe(esi, int(cert.user_bits[0]))
        bits = np.asarray(cert.user_bits[1:], np.uint8)
        if self._decoders is None:
            self._pending.append((decoder, esi, bits))
        else:
            self._feed(decoder, esi, bits)
        self._processed.add(key)

    def _feed(self, decoder: str, esi: int, bits: np.ndarray) -> None:
        try:
            if self._decoders[decoder].add_symbol(esi, bits):
                self._n_used += 1
        except fountain.FountainIntegrityError as exc:
            raise data.IntegrityError(
                f"certified-symbol integrity failure: {exc}") from exc

    def _settle(self) -> None:
        self._metadata.settle()
        decoded = self._metadata.result
        if self._decoders is not None or decoded is None or not decoded.ok:
            return
        if self.row.pooled_fountain:
            self._k_total = len(self._streams) * decoded.k
            self._decoders = {_POOLED: fountain.Decoder(
                _pooled_volume_code(self.row, self._k_total))}
        else:
            self._k_total = decoded.k
            self._decoders = {
                stream.stream_id: fountain.Decoder(
                    _volume_code(self.row, stream, self._k_total))
                for stream in self._streams}
        for decoder, esi, bits in self._pending:
            self._feed(decoder, esi, bits)
        self._pending = []

    @property
    def metadata_rank(self) -> int:
        return self._metadata.rank

    @property
    def metadata_n_unique(self) -> int:
        return self._metadata.unique

    def _statuses(self) -> list[tuple[str, fountain.BlockStatus]]:
        return [(key, status)
                for key, decoder in (self._decoders or {}).items()
                for status in decoder.block_status()]

    def _label(self, key: str) -> str | None:
        if key == _POOLED:
            return None
        stream = self._streams[self._index_of[key]]
        return None if stream.fountain_aux is None else key

    def block_rows(self) -> tuple[data.CloseBlockRow, ...]:
        return tuple(
            data.CloseBlockRow(
                stream_id=self._label(key), block=status.block,
                have=status.have, needed=status.needed, rank=status.rank,
                solved=status.solved, short=status.short,
                groups_open=status.groups_open, n_groups=status.n_groups)
            for key, status in self._statuses())

    def block_counts(self) -> dict[tuple[str, int], int]:
        return {(key, status.block): status.min_rows
                for key, status in self._statuses()}

    @property
    def count_ready(self) -> bool:
        return (self._decoders is not None
                and all(status.min_rows >= status.needed
                        for _key, status in self._statuses()))

    @property
    def ready(self) -> bool:
        return self.count_ready or self._metadata.terminal

    def count_progress(self) -> tuple[bool, int | None,
                                      tuple[data.CloseBlockRow, ...]]:
        if self._decoders is None:
            return self.ready, None, ()
        rows = self.block_rows()
        return self.ready, sum(row.needed for row in rows), rows

    def _snapshot(self) -> tuple:
        return (self._metadata.terminal,
                tuple((key, status.block, status.have)
                      for key, status in self._statuses()
                      if not status.solved))

    def close_is_new(self) -> bool:
        return (self._last_attempt is None
                or self._snapshot() != self._last_attempt)

    def close(self) -> CloseResult:
        result = self._close()
        self._last_attempt = self._snapshot()
        return result

    def _close(self) -> CloseResult:
        if self._decoders is None:
            version, _k_total, state = self._metadata.classify()
            if state == "incomplete":
                return CloseResult("open", None, None,
                                   reason="metadata incomplete",
                                   metadata_version=version)
            if state == "unsupported":
                return CloseResult(
                    "unsupported", None, None,
                    reason=f"unsupported metadata version {version}",
                    metadata_version=version)
            return CloseResult("integrity_failure", None, None,
                               reason="metadata malformed",
                               metadata_version=version)
        version = self._metadata.result.version
        solved = {key: decoder.try_solve()
                  for key, decoder in self._decoders.items()}
        blocks = self.block_rows()
        k_total = self._k_total
        if any(source is None for source in solved.values()):
            unsolved = tuple(key for key, source in solved.items()
                             if source is None and self._label(key))
            return _open_result(blocks, k_total, self._n_used, version,
                                unsolved)
        if self.row.pooled_fountain:
            s_bits = self._decoders[_POOLED].code.s_bits
            n = len(self._streams)
            payload = _unwrap_gates(
                _reassemble(((solved[_POOLED], s_bits),), k_total),
                n * s_bits, k_total // n)
        else:
            payload = _unwrap_gates(
                _reassemble(tuple((solved[s.stream_id], s.symbol_bits)
                                  for s in self._streams), k_total),
                sum(s.symbol_bits for s in self._streams), k_total)
        if payload is None:
            return CloseResult(
                "integrity_failure", None, k_total, blocks, self._n_used,
                "envelope verification failed (payload SHA-256 mismatch, "
                "noncanonical K, or nonzero padding)", version)
        return CloseResult("verified", payload, k_total, blocks,
                           self._n_used, None, version)


def _open_result(blocks: tuple[data.CloseBlockRow, ...], k_total: int,
                 n_used: int, version: int | None,
                 unsolved_streams: tuple[str, ...] = ()) -> CloseResult:
    n_unsolved = sum(1 for b in blocks if not b.solved)
    short = sum(b.short for b in blocks)
    if all(b.n_groups == 1 for b in blocks):
        reason = (f"{n_unsolved} of {len(blocks)} blocks unsolved "
                  f"(at least {short} additional symbols required)")
    else:
        groups_open = sum(b.groups_open for b in blocks)
        n_groups = sum(b.n_groups for b in blocks)
        reason = (f"{n_unsolved} of {len(blocks)} blocks unsolved "
                  f"(scarcest groups short {short} rows; "
                  f"{groups_open} of {n_groups} groups open)")
    if unsolved_streams:
        reason += f"; streams {unsolved_streams}"
    return CloseResult("open", None, k_total, blocks, n_used,
                       reason, version)


def _progress_over(certs: Iterable[CertificateLike],
                   row: RowLike) -> CloseProgress:
    progress = CloseProgress(row)
    progress.absorb(dict(enumerate(certs)))
    return progress


def metadata_from_certificates(
        certs: Iterable[CertificateLike],
        row: RowLike) -> tuple[int | None, int | None, str]:
    gate = _MetadataGate(row)
    index_of = {s.stream_id: i for i, s in enumerate(row.streams)}
    for cert in certs:
        gate.observe(_symbol_index(row, cert, index_of[cert.stream_id]),
                     int(cert.user_bits[0]))
    return gate.classify()


def close_count_status(
        certs: Iterable[CertificateLike],
        row: RowLike) -> tuple[bool, dict[tuple[str, int], int] | None]:
    try:
        progress = _progress_over(certs, row)
    except data.IntegrityError:
        return True, None
    if progress.k_total is None:
        return progress.ready, None
    return progress.count_ready, progress.block_counts()


def close_count_ready(certs: Iterable[CertificateLike],
                      row: RowLike) -> bool:
    return close_count_status(certs, row)[0]


def close_count_progress(
        certs: Iterable[CertificateLike], row: RowLike
) -> tuple[bool, int | None, tuple[data.CloseBlockRow, ...]]:
    try:
        progress = _progress_over(certs, row)
    except data.IntegrityError:
        return True, None, ()
    return progress.count_progress()


def close_volume(certs: Iterable[CertificateLike],
                 row: RowLike) -> CloseResult:
    progress = CloseProgress(row)
    try:
        progress.absorb(dict(enumerate(certs)))
        return progress.close()
    except data.IntegrityError as exc:
        return CloseResult("integrity_failure", None, progress.k_total,
                           reason=str(exc))
