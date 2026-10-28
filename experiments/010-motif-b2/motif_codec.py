"""motif_codec — the shared core for a MOTIF-based B2 (i2w3) data mode.

Thesis (this experiment's premise, agreed 2026-07-07): the free-running RLL
sampler is a SEQUENTIAL code — one dot error desyncs the whole decode, and
004.0a showed the dominant channel error is a constraint-CONSISTENT
whole-feature dropout (a 2-dot ink run fades to legal white) that a trellis
cannot even flag. The motif frame trades a little rate for LOCALITY: tile the
field with independent B x B blocks, each carrying one symbol = which of D
legal motifs it is. Each block fails independently and yields a per-symbol
posterior (matched filter over the dictionary) -> label-bit LLRs -> L3 LDPC,
the same MLC frame A3/A4 use. NO error correction lives here (L1 only).

Key structural fact (why juxtaposition closure is FREE): i2w3 has only
MINIMUM run constraints (ink>=2, white>=3), no maxima. A block that is legal
in isolation with border-runs-counted stays legal under ANY tiling, because a
boundary-crossing run only CONCATENATES two already->=min runs -> still >=min.
So the dictionary is exactly the border-legal B x B blocks, and they tile
freely. (Verified against the row-DP count in exp010 capacity study.)

Data mapping is therefore trivial + robust: symbol = motif index in
[0, 2**k), k = floor(log2 D); no arithmetic coding, no cross-block state.
"""
from __future__ import annotations

import numpy as np

MIN_INK = 2
MIN_WHITE = 3


def runs_border_legal(vec: np.ndarray | tuple[int, ...]) -> bool:
    """True iff every maximal run (border-counted) is ink>=MIN_INK / white>=
    MIN_WHITE. Border runs are counted as-is (stricter than needed for tiling,
    which is what makes juxtaposition safe)."""
    v = tuple(int(x) for x in vec)
    n = len(v)
    i = 0
    while i < n:
        j = i
        while j < n and v[j] == v[i]:
            j += 1
        need = MIN_INK if v[i] == 1 else MIN_WHITE
        if j - i < need:
            return False
        i = j
    return True


def legal_rows(b: int) -> list[tuple[int, ...]]:
    """All width-b rows that are horizontally border-legal (deterministic
    order: ascending as binary integers, MSB = column 0)."""
    import itertools
    return [r for r in itertools.product((0, 1), repeat=b) if runs_border_legal(r)]


def _col_min(color: int) -> int:
    return MIN_INK if color == 1 else MIN_WHITE


def build_dictionary(b: int) -> np.ndarray:
    """Enumerate ALL border-legal (both axes) b x b blocks, deterministic order.

    DFS over rows (each a legal_row), carrying per-column vertical run state
    (color, capped length); a row is appendable iff every column's colour
    either continues or changes only after its run met its min; a completed
    block is kept iff every column's final run is >= its min. Returns an
    (D, b, b) uint8 array, ink=1, in row-append DFS order (stable = the index
    space). D matches the exp010 capacity DP exactly."""
    rows = legal_rows(b)
    capw, capi = MIN_WHITE, MIN_INK
    out: list[np.ndarray] = []
    stack_block = np.empty((b, b), np.uint8)

    def cap(color: int, length: int) -> int:
        return min(length, capw if color == 0 else capi)

    def recurse(depth: int, col_state: tuple[tuple[int, int], ...]) -> None:
        if depth == b:
            if all(length >= _col_min(color) for color, length in col_state):
                out.append(stack_block.copy())
            return
        for r in rows:
            ok = True
            ns: list[tuple[int, int]] = []
            for c in range(b):
                oc, ol = col_state[c]
                nc = r[c]
                if depth == 0:
                    ns.append((nc, 1))
                elif nc == oc:
                    ns.append((oc, cap(oc, ol + 1)))
                else:
                    if ol < _col_min(oc):
                        ok = False
                        break
                    ns.append((nc, 1))
            if not ok:
                continue
            stack_block[depth] = r
            recurse(depth + 1, tuple(ns))

    recurse(0, tuple((0, 0) for _ in range(b)))
    arr = np.array(out, np.uint8)
    assert all(block_legal(arr[i]) for i in range(min(len(arr), 64)))
    return arr


def block_legal(block: np.ndarray) -> bool:
    """Border-legal in BOTH axes — the tiling-safe legality predicate."""
    for i in range(block.shape[0]):
        if not runs_border_legal(block[i]):
            return False
    for j in range(block.shape[1]):
        if not runs_border_legal(block[:, j]):
            return False
    return True


def tiling_legal(field_cells: np.ndarray, dictionary: np.ndarray, b: int) -> bool:
    """Assert a full tiled field (rows*b x cols*b dots) is globally i2w3-legal
    — the empirical check that juxtaposition closure holds as built."""
    return block_legal(field_cells)   # whole assembled field, both axes


def dropout_pairs(dictionary: np.ndarray, b: int) -> list[tuple[int, int]]:
    """Pairs (i, j) where motif j == motif i with exactly one 2-dot ink run
    turned to white AND j is itself a legal motif (in the dictionary). These
    are the constraint-CONSISTENT dropout confusions the trellis could not see
    (004.0a) — the Q2 probe. Returns index pairs into `dictionary`."""
    key = {dictionary[i].tobytes(): i for i in range(len(dictionary))}
    pairs: list[tuple[int, int]] = []
    for i in range(len(dictionary)):
        m = dictionary[i]
        # find horizontal 2-dot ink runs isolated by white on both sides
        for r in range(b):
            row = m[r]
            c = 0
            while c < b:
                if row[c] == 1:
                    c0 = c
                    while c < b and row[c] == 1:
                        c += 1
                    if (c - c0) == 2 and (c0 == 0 or row[c0 - 1] == 0) \
                            and (c >= b or row[c] == 0):
                        cand = m.copy()
                        cand[r, c0:c] = 0
                        j = key.get(cand.tobytes())
                        if j is not None:
                            pairs.append((i, j))
                else:
                    c += 1
    return pairs


def bits_per_motif(dictionary: np.ndarray) -> int:
    return int(np.floor(np.log2(len(dictionary))))


def symbols_to_field(symbols: np.ndarray, dictionary: np.ndarray,
                     b: int) -> np.ndarray:
    """Tile a (rows, cols) motif-index array into a (rows*b, cols*b) dot field
    (ink=1). Indices must be < len(dictionary)."""
    rows, cols = symbols.shape
    field = np.empty((rows * b, cols * b), np.uint8)
    for i in range(rows):
        for j in range(cols):
            field[i * b:(i + 1) * b, j * b:(j + 1) * b] = dictionary[symbols[i, j]]
    return field
