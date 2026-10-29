from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Word M = [version:1][K:18 big-endian][reserved:5 zeros].  TWO bit
#: orders coexist and both are law: K is BE across M[1..19], while the
#: integer mask packs M[i] at integer bit i.  Conflating them is the
#: easiest silent metadata fork (conversion_docs/03-keystream-metadata.md:340).
METADATA_BITS = 24
VERSION_BITS = 1
K_BITS = 18
RESERVED_BITS = 5
MAX_K = 1 << K_BITS
VALID_VERSIONS = (0, 1)
#: VALID_VERSIONS is what the WORD may lawfully carry; this is what
#: this decoder will act on.  A structurally valid future version read
#: by today's decoder would silently reinterpret data, so version 1
#: refuses (conversion_docs/03-keystream-metadata.md:246-247).
SUPPORTED_METADATA_VERSIONS = frozenset({0})

#: The printed flat tile counter is 18 bits ONCE, but holo3 declares
#: that width twice — here and at pilots.COUNTER_BITS, which is the
#: BCH message width.  They must move together or the address word
#: and the metadata equation index address different spaces.
COUNTER_BITS = 18
MAX_COUNTER = 1 << COUNTER_BITS
#: 24 and 48 are different KINDS of number.  Rank 24 makes the word
#: UNIQUE (algebra); 48 distinct equations is a false-accept budget —
#: >= 24 surplus parity checks past rank, residual ~2^-24 — not a
#: convergence wait (conversion_docs/03-keystream-metadata.md:243-245).
MIN_METADATA_EQUATIONS = 48

#: Maximal-length degree-24 LFSR, x^24+x^4+x^3+x+1, initial state 1 =
#: equation index 0.  The coefficient row of index c is state c, so
#: any 24 CONSECUTIVE indices are independent — that is the frozen
#: rank-24 property (conversion_docs/03-keystream-metadata.md:152-158).
LFSR_POLYNOMIAL = 0x100001B
LFSR_FEEDBACK = 0x00001B
LFSR_INITIAL_STATE = 0x000001
_MASK = (1 << METADATA_BITS) - 1
_TOP = 1 << (METADATA_BITS - 1)

#: Build-once-per-bound memo, ~1 MiB single-stream and ~3 MiB pooled.
#: Safe to share across workers only because the tables are frozen
#: read-only and a racing rebuild produces an identical array — do not
#: turn this into an lru_cache or hand out a writeable view.
_TABLES: dict[int, np.ndarray] = {}


def _lfsr_step(state: int) -> int:
    return ((state << 1) & _MASK) ^ (LFSR_FEEDBACK if state & _TOP else 0)


#: Pooled rows index equations at `counter*n + stream_idx`, which is
#: BIT-IDENTICAL to the counter at n=1 — the format-fork guard.  The
#: bound must stay inside the LFSR's 2^24-1 nonzero period, so n <= 63
#: (conversion_docs/03-keystream-metadata.md:164-172).
def max_equation_index(n_streams: int) -> int:
    bound = n_streams * MAX_COUNTER
    if bound >= (1 << METADATA_BITS) - 1:
        raise ValueError(
            f"{n_streams} streams exceed the LFSR's nonzero state budget")
    return bound


def equation_index(counter: int, stream_idx: int, n_streams: int) -> int:
    return counter * n_streams + stream_idx


def coefficient_table(max_index: int = MAX_COUNTER) -> np.ndarray:
    table = _TABLES.get(max_index)
    if table is None:
        table = np.empty(max_index, dtype=np.uint32)
        state = LFSR_INITIAL_STATE
        for index in range(max_index):
            table[index] = state
            state = _lfsr_step(state)
        table.flags.writeable = False
        _TABLES[max_index] = table
    return table


@dataclass(frozen=True)
class MetadataResult:
    ok: bool
    version: int | None
    k: int | None
    rank: int
    n_unique: int
    inconsistent: bool


def _solve_word(basis: dict[int, int]) -> int:
    solution = 0
    for pivot in range(METADATA_BITS - 1, -1, -1):
        row = basis[pivot]
        rhs = (row >> METADATA_BITS) & 1
        known = ((row & _MASK) & solution).bit_count() & 1
        if rhs ^ known:
            solution |= 1 << pivot
    return solution


#: ALL supplied equations are eliminated before a full-rank word is
#: accepted: an early-out at rank 24 skips the surplus consistency
#: checks and silently weakens the integrity gate.  The content gates
#: below are ordered law (conversion_docs/03-keystream-metadata.md:190-192).
def decode_metadata(equations: dict[int, int],
                    max_index: int = MAX_COUNTER) -> MetadataResult:
    n_unique = len(equations)
    table = coefficient_table(max_index)
    basis: dict[int, int] = {}
    for index in sorted(equations):
        row = int(table[index]) | (int(equations[index]) << METADATA_BITS)
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
                return MetadataResult(
                    False, None, None, len(basis), n_unique, True)
    rank = len(basis)
    if rank < METADATA_BITS:
        return MetadataResult(False, None, None, rank, n_unique, False)
    word = _solve_word(basis)
    version = word & 1
    k = 0
    for i in range(K_BITS):
        k = (k << 1) | ((word >> (1 + i)) & 1)
    if word >> (1 + K_BITS):
        return MetadataResult(False, version, k, rank, n_unique, False)
    if k == 0:
        return MetadataResult(False, version, k, rank, n_unique, False)
    if n_unique < MIN_METADATA_EQUATIONS:
        return MetadataResult(False, version, k, rank, n_unique, False)
    if version not in SUPPORTED_METADATA_VERSIONS:
        return MetadataResult(False, version, k, rank, n_unique, False)
    return MetadataResult(True, version, k, rank, n_unique, False)
