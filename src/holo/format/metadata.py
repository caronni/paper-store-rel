"""The one-bit addressed metadata channel for holo format v1.

The metadata word remains ``M = [version:1][K:18 BE][reserved:5 zeros]``.
Every tile donates exactly one CRC-certified LDPC user bit, but tile counter
``c`` now carries one dense addressed equation rather than a residue copy::

    bit(c) = <coefficient(c), M> over GF(2)

``coefficient(c)`` is state ``c`` of the maximal-length degree-24 LFSR with
primitive polynomial ``x^24 + x^4 + x^3 + x + 1``. Integer mask bit ``i``
multiplies metadata word bit ``M[i]``. The transparent state-1 recurrence is::

    s' = ((s << 1) & 0xffffff) ^ (0x1b if s & 0x800000 else 0)

The sequence visits every nonzero 24-bit row, and every 24 consecutive tile
counters are linearly independent. Arbitrary addressed sets recover exactly
when their coefficient rows reach rank 24; no stronger arbitrary-subset claim
is made. The receiver processes every supplied equation and requires 48
distinct counters before trusting the word, leaving at least 24 surplus
consistency equations under normal full-rank reception.

POOLED MULTISTREAM EQUATIONS (the -v1 colour rows;
docs/CMY8-POOLED-FOUNTAIN.md §2.4, adopted 2026-08-13). A pooled row's
tile carries one DISTINCT equation per stream instead of replicated
copies: the coefficient row for (counter ``c``, stream ``s``) is LFSR
state ``equation_index(c, s, n_streams) = c*n_streams + s``. Every 24
consecutive equation indices remain consecutive LFSR states, so the
frozen rank property carries verbatim; single-stream rows have
``equation_index == counter`` bit-identically. Callers on pooled rows
pass ``max_index=max_equation_index(n_streams)`` — the default bound
stays the frozen single-stream ``MAX_COUNTER`` so K/CMY7/-v0 call sites
are untouched. With one plane dead the surviving equations are a
punctured (non-consecutive) index set: the 48-distinct-equation floor
then needs ~24 tiles rather than ~16, pinned in tests.

FORMAT-AXIS (HOLO-DESIGN decision F6). The polynomial, initial state,
coefficient-bit mapping, 48-equation trust floor, and word layout are printed
format surface. Do not duplicate placement or recovery arithmetic elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

import numpy as np

METADATA_BITS = 24
VERSION_BITS = 1
K_BITS = 18
RESERVED_BITS = 5
MAX_K = 1 << K_BITS
VALID_VERSIONS = (0, 1)

COUNTER_BITS = 18
MAX_COUNTER = 1 << COUNTER_BITS
MIN_METADATA_EQUATIONS = 48

LFSR_POLYNOMIAL = 0x100001B
LFSR_FEEDBACK = 0x00001B
LFSR_INITIAL_STATE = 0x000001
_MASK = (1 << METADATA_BITS) - 1
_TOP = 1 << (METADATA_BITS - 1)


def _lfsr_step(state: int) -> int:
    """Multiply one nonzero GF(2^24) element by x."""
    return ((state << 1) & _MASK) ^ (LFSR_FEEDBACK if state & _TOP else 0)


def max_equation_index(n_streams: int) -> int:
    """The equation-index bound of a row with ``n_streams`` streams.

    Single-stream rows keep the frozen counter bound; a pooled row's
    indices reach ``counter*n_streams + stream_idx < n_streams * 2^18``,
    still far inside the LFSR's nonzero period of ``2^24 - 1`` states.
    """
    if isinstance(n_streams, (bool, np.bool_)) or not isinstance(
            n_streams, (int, np.integer)):
        raise TypeError("n_streams must be an integer")
    value = int(n_streams)
    if value < 1:
        raise ValueError("n_streams must be >= 1")
    bound = value * MAX_COUNTER
    if bound >= (1 << METADATA_BITS) - 1:
        raise ValueError(
            f"{value} streams exceed the LFSR's nonzero state budget")
    return bound


def equation_index(counter: int, stream_idx: int, n_streams: int) -> int:
    """The addressed-equation index of (counter, stream) on one row.

    ``counter*n_streams + stream_idx``; bit-identical to the counter for
    single-stream rows (``n_streams=1, stream_idx=0``).
    """
    bound = max_equation_index(n_streams)
    value = _counter(counter)                       # frozen counter bound
    if isinstance(stream_idx, (bool, np.bool_)) or not isinstance(
            stream_idx, (int, np.integer)):
        raise TypeError("stream_idx must be an integer")
    stream = int(stream_idx)
    if not 0 <= stream < int(n_streams):
        raise ValueError(
            f"stream_idx must be in 0..{int(n_streams) - 1}, got {stream}")
    index = value * int(n_streams) + stream
    assert index < bound
    return index


def equation_indices(counters, n_streams: int) -> np.ndarray:
    """(..., n_streams) equation indices for an integer counter array.

    The vector form of :func:`equation_index`; one row per counter,
    stream-minor. Single home for the ``counter*n + stream`` arithmetic
    (the module's no-duplication law covers it).
    """
    bound = max_equation_index(n_streams)
    values = np.asarray(counters)
    if values.dtype == np.bool_ or not np.issubdtype(
            values.dtype, np.integer):
        raise TypeError("metadata counters must be integers")
    flat = values.astype(np.int64, copy=False)
    if flat.size and (int(flat.min()) < 0
                      or int(flat.max()) >= MAX_COUNTER):
        raise ValueError(
            f"metadata counters must be in 0..{MAX_COUNTER - 1}")
    n = int(n_streams)
    out = (flat[..., None] * n
           + np.arange(n, dtype=np.int64))
    assert not out.size or int(out.max()) < bound
    return out


@lru_cache(maxsize=4)
def _coefficient_table(size: int = MAX_COUNTER) -> np.ndarray:
    """The first ``size`` coefficient masks, lazily materialized.

    ~1 MiB at the frozen counter bound; a pooled three-stream row uses
    the 3x table (~3 MiB). Cached per size."""
    masks = np.empty(size, dtype=np.uint32)
    state = LFSR_INITIAL_STATE
    for counter in range(size):
        masks[counter] = state
        state = _lfsr_step(state)
    masks.flags.writeable = False
    return masks


def _counter(counter: int, max_index: int = MAX_COUNTER) -> int:
    if isinstance(counter, (bool, np.bool_)) or not isinstance(
            counter, (int, np.integer)):
        raise TypeError("metadata counter must be an integer")
    value = int(counter)
    if not 0 <= value < max_index:
        raise ValueError(
            f"metadata equation index must be in 0..{max_index - 1}, "
            f"got {value}")
    return value


def coefficient_mask(counter: int, *,
                     max_index: int = MAX_COUNTER) -> int:
    """The nonzero 24-bit coefficient row for one equation index."""
    return int(_coefficient_table(max_index)[_counter(counter, max_index)])


def coefficient_masks(counters, *,
                      max_index: int = MAX_COUNTER) -> np.ndarray:
    """Coefficient rows for integer equation indices as a uint32 array."""
    values = np.asarray(counters)
    if values.dtype == np.bool_ or not np.issubdtype(values.dtype, np.integer):
        raise TypeError("metadata counters must be integers")
    flat = values.astype(np.int64, copy=False).ravel()
    if flat.size and (int(flat.min()) < 0 or int(flat.max()) >= max_index):
        raise ValueError(
            f"metadata equation indices must be in 0..{max_index - 1}")
    return _coefficient_table(max_index)[flat].reshape(values.shape)


def encode_metadata(version: int, k: int) -> np.ndarray:
    """The 24-bit word: M[0]=version, M[1:19]=K BE, M[19:24]=zero."""
    if version not in VALID_VERSIONS:
        raise ValueError(f"version must be one of {VALID_VERSIONS}, "
                         f"got {version}")
    if not 0 < k < MAX_K:
        raise ValueError(f"k must satisfy 0 < k < {MAX_K}, got {k}")
    word = np.zeros(METADATA_BITS, dtype=np.uint8)
    word[0] = version
    for i in range(K_BITS):
        word[1 + i] = (k >> (K_BITS - 1 - i)) & 1
    return word


def _word_bits(word) -> np.ndarray:
    values = np.asarray(word)
    if values.shape != (METADATA_BITS,):
        raise ValueError(f"metadata word must have shape ({METADATA_BITS},)")
    if values.dtype == np.bool_:
        return values.astype(np.uint8)
    if not np.issubdtype(values.dtype, np.integer):
        raise TypeError("metadata word must contain integer bits")
    if ((values < 0) | (values > 1)).any():
        raise ValueError("metadata word must contain only bits")
    return values.astype(np.uint8, copy=False)


def _word_mask(word) -> int:
    bits = _word_bits(word)
    return sum(int(bit) << i for i, bit in enumerate(bits))


def tile_bit(word, counter: int, *, max_index: int = MAX_COUNTER) -> int:
    """The metadata channel bit of one equation index.

    Single-stream rows pass the tile counter (frozen default bound);
    pooled rows pass ``equation_index(...)`` with
    ``max_index=max_equation_index(n_streams)``.
    """
    return (_word_mask(word)
            & coefficient_mask(counter, max_index=max_index)).bit_count() & 1


def tile_bits(word, counters, *,
              max_index: int = MAX_COUNTER) -> np.ndarray:
    """Metadata channel bits for an integer equation-index array."""
    word_mask = _word_mask(word)
    masks = coefficient_masks(counters, max_index=max_index)
    return np.fromiter(
        ((word_mask & int(mask)).bit_count() & 1 for mask in masks.ravel()),
        dtype=np.uint8, count=masks.size).reshape(masks.shape)


@dataclass(frozen=True)
class MetadataDecode:
    """Addressed-equation recovery result."""

    version: int | None
    k: int | None
    ok: bool
    rank: int
    n_observations: int
    n_unique_counters: int
    inconsistent: bool
    word: tuple[int, ...] | None
    reason: str | None

    @property
    def rank_shortfall(self) -> int:
        return max(0, METADATA_BITS - self.rank)

    @property
    def check_shortfall(self) -> int:
        return max(0, MIN_METADATA_EQUATIONS - self.n_unique_counters)


def _solve_word(basis: dict[int, int]) -> tuple[int, ...]:
    """Back-substitute a lowest-pivot echelon basis of augmented rows."""
    solution = 0
    for pivot in range(METADATA_BITS - 1, -1, -1):
        row = basis[pivot]
        rhs = (row >> METADATA_BITS) & 1
        known = ((row & _MASK) & solution).bit_count() & 1
        if rhs ^ known:
            solution |= 1 << pivot
    return tuple((solution >> i) & 1 for i in range(METADATA_BITS))


def _content(word: tuple[int, ...], *, rank: int, n_observations: int,
             n_unique: int) -> MetadataDecode:
    version = word[0]
    k = 0
    for bit in word[1:1 + K_BITS]:
        k = (k << 1) | bit
    nonzero_reserved = [
        1 + K_BITS + i for i, bit in enumerate(word[1 + K_BITS:]) if bit]
    if nonzero_reserved:
        return MetadataDecode(
            version, k, False, rank, n_observations, n_unique, False, word,
            f"reserved bits nonzero at indices {nonzero_reserved}")
    if k == 0:
        return MetadataDecode(version, k, False, rank, n_observations,
                              n_unique, False, word,
                              "decoded K = 0 (invalid)")
    if n_unique < MIN_METADATA_EQUATIONS:
        return MetadataDecode(
            version, k, False, rank, n_observations, n_unique, False, word,
            f"metadata needs {MIN_METADATA_EQUATIONS} distinct equations; "
            f"have {n_unique}")
    return MetadataDecode(version, k, True, rank, n_observations, n_unique,
                          False, word, None)


def decode_metadata(
        observations: Iterable[tuple[int, int]], *,
        max_index: int = MAX_COUNTER) -> MetadataDecode:
    """Recover metadata from ``(equation_index, certified_bit)`` pairs.

    Single-stream rows observe at tile counters (frozen default bound);
    pooled rows observe at ``equation_index(counter, stream, n)`` under
    ``max_index=max_equation_index(n)``. Duplicate observations at the
    same index are harmless only when their bits agree. Any opposite
    duplicate or algebraically inconsistent equation is an integrity
    failure. All supplied equations are processed before a full-rank
    word is accepted.
    """
    seen: dict[int, int] = {}
    n_observations = 0
    for observation in observations:
        try:
            counter, bit = observation
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "metadata observations must be (counter, bit) pairs") from exc
        counter = _counter(counter, max_index)
        if isinstance(bit, (bool, np.bool_)):
            bit = int(bit)
        if not isinstance(bit, (int, np.integer)) or int(bit) not in (0, 1):
            raise ValueError(f"metadata bit must be 0 or 1, got {bit!r}")
        bit = int(bit)
        n_observations += 1
        previous = seen.get(counter)
        if previous is not None and previous != bit:
            return MetadataDecode(
                None, None, False, 0, n_observations, len(seen), True, None,
                f"certified metadata bits disagree at counter {counter}")
        seen[counter] = bit

    basis: dict[int, int] = {}
    for counter in sorted(seen):
        row = (coefficient_mask(counter, max_index=max_index)
               | (seen[counter] << METADATA_BITS))
        while row & _MASK:
            lowest = (row & _MASK) & -(row & _MASK)
            pivot = lowest.bit_length() - 1
            existing = basis.get(pivot)
            if existing is None:
                basis[pivot] = row
                break
            row ^= existing
        else:
            if (row >> METADATA_BITS) & 1:
                return MetadataDecode(
                    None, None, False, len(basis), n_observations, len(seen),
                    True, None,
                    "certified metadata equations are inconsistent at "
                    f"counter {counter}")

    rank = len(basis)
    if rank < METADATA_BITS:
        return MetadataDecode(
            None, None, False, rank, n_observations, len(seen), False, None,
            f"metadata coefficient rank {rank}/{METADATA_BITS}")
    word = _solve_word(basis)
    return _content(word, rank=rank, n_observations=n_observations,
                    n_unique=len(seen))
