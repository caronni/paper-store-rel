from __future__ import annotations

from dataclasses import dataclass

import numpy as np

METADATA_BITS = 24
VERSION_BITS = 1
K_BITS = 18
RESERVED_BITS = 5
MAX_K = 1 << K_BITS
VALID_VERSIONS = (0, 1)
SUPPORTED_METADATA_VERSIONS = frozenset({0})

COUNTER_BITS = 18
MAX_COUNTER = 1 << COUNTER_BITS
MIN_METADATA_EQUATIONS = 48

LFSR_POLYNOMIAL = 0x100001B
LFSR_FEEDBACK = 0x00001B
LFSR_INITIAL_STATE = 0x000001
_MASK = (1 << METADATA_BITS) - 1
_TOP = 1 << (METADATA_BITS - 1)

_TABLES: dict[int, np.ndarray] = {}


def _lfsr_step(state: int) -> int:
    return ((state << 1) & _MASK) ^ (LFSR_FEEDBACK if state & _TOP else 0)


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
