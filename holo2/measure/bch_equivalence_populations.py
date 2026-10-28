"""Word and syndrome populations for the BCH twin-equivalence harness.

Carved out of ``bch_equivalence.py`` (seam identified 2026-08-17, split
per the user's "if it makes sense" ruling): everything that BUILDS a test
vector rather than compares one.  The scalar decoder's own five-rule
disposal path for a single word (:data:`RULES`, :func:`scalar_rule` —
reporting only, it never enters a comparison); population (b), the
seeded synthetic set that reaches every acceptance clause on purpose
(:func:`synthetic_words`, plus the full-codeword and fixed-locator
builders it and the rule-4 drive use); and population (c), the boundary
words rebuilt out of GF(2) nullspace algebra (:func:`boundary_words`, via
:func:`leading_run_words`) rather than bare syndrome rows, because a bare
row is not a legal input to the batched arm.  See ``bch_equivalence.py``'s
own module docstring for the full population taxonomy and what each one
is evidence of.  Depends only on ``holo2.format.bch``, the oracle;
nothing here knows the twin exists.
"""
from __future__ import annotations

import numpy as np

from holo2.format import bch

# ------------------------------------------------- which rule disposed of it

RULES = ("clean", "bm_refused", "chien_count", "chien_shortened",
         "recheck_failed", "accepted")


def scalar_rule(word: np.ndarray) -> str:
    """Name the scalar decoder's own disposal path for one word.

    Reporting only — it never enters a comparison.  It walks
    ``bch._decode_syndromes``'s clauses with bch's own functions so that
    the census says which branches the population actually reached.
    """
    syndrome = bch.syndromes(word)
    if not syndrome.any():
        return "clean"
    sigma, lfsr_len = bch._berlekamp_massey([int(s) for s in syndrome])
    if lfsr_len > bch.T or len(sigma) - 1 != lfsr_len:
        return "bm_refused"
    positions = bch._chien_roots(sigma)
    if positions.size != lfsr_len:
        return "chien_count"
    if bool((positions >= bch.N_WORD).any()):
        return "chien_shortened"
    corrected = word.copy()
    corrected[positions] ^= 1
    if bch.syndromes(corrected).any():
        return "recheck_failed"
    return "accepted"


# ----------------------------------------------------------- the populations

def _full_codeword_bits(message_int: int) -> np.ndarray:
    """A FULL 127-bit codeword: message polynomial times g(x) over GF(2)."""
    generator = bch._gpoly_int()
    product = 0
    for bit in range(message_int.bit_length()):
        if (message_int >> bit) & 1:
            product ^= generator << bit
    return np.array([(product >> i) & 1 for i in range(bch.N_FULL)], np.uint8)


def _gf_multiply(left: int, right: int) -> int:
    """One GF(2^7) product through bch's own tables (no second field here)."""
    if left == 0 or right == 0:
        return 0
    exp, log = bch.gf_tables()
    return int(exp[(int(log[left]) + int(log[right])) % bch._ORDER])


def fixed_locator(positions: tuple[int, ...]) -> list[int]:
    """``sigma(x) = prod (1 + alpha^i x)`` — a legal locator, chosen roots.

    Chien evaluates ``sigma(alpha^-i)``, so the roots ARE ``positions``:
    the returned coefficients pass rule 2's degree clause and rule 3's
    count and range clauses by construction, which is exactly what the
    rule-4 drive needs.
    """
    exp, _log = bch.gf_tables()
    poly = [1]
    for position in positions:
        root = int(exp[position % bch._ORDER])
        grown = [0] * (len(poly) + 1)
        for index, coefficient in enumerate(poly):
            grown[index] ^= coefficient
            grown[index + 1] ^= _gf_multiply(coefficient, root)
        poly = grown
    return poly


#: Roots the rule-4 drive plants.  Three, all inside the transmitted
#: word, so nothing but the final syndrome re-check can refuse them.
DRIVE_ROOTS = (3, 17, 42)


def synthetic_words(seed: int = 20260817) -> np.ndarray:
    """The seeded vector set.  No unseeded RNG anywhere in this file."""
    rng = np.random.default_rng(seed)
    rows: list[np.ndarray] = []

    messages = rng.integers(0, 2, size=(64, bch.K_MSG), dtype=np.uint8)
    codewords = np.stack([bch.encode(message) for message in messages])
    rows += list(codewords)                       # weight 0 — the clean path

    # every weight 0..T, then T+1..T+12 (beyond the radius, must agree)
    for weight in range(1, 2 * bch.T):
        for repeat in range(8):
            word = codewords[(weight * 8 + repeat) % len(codewords)].copy()
            word[rng.choice(bch.N_WORD, size=weight, replace=False)] ^= 1
            rows.append(word)

    # uniform noise: the shape the real sweep mostly sees
    rows += list(rng.integers(0, 2, size=(512, bch.N_WORD), dtype=np.uint8))

    # truncated FULL-length codewords: roots in the shortened positions
    planted = 0
    while planted < 24:
        full = _full_codeword_bits(int(rng.integers(1, 1 << 50)))
        tail = int(full[bch.N_WORD:].sum())
        if 1 <= tail <= bch.T:
            rows.append(full[:bch.N_WORD].copy())
            planted += 1
    return np.stack(rows)


# ------------------------------------- population (c): the boundary, as WORDS

def _syndrome_bits() -> np.ndarray:
    """(91, 100) over GF(2): the map word -> (S_1, S_3, .., S_25), by bit."""
    exp, _log = bch.gf_tables()
    rows = []
    for order in range(1, 2 * bch.T, 2):
        values = np.array([int(exp[(order * i) % bch._ORDER])
                           for i in range(bch.N_WORD)], np.int64)
        rows += [((values >> bit) & 1).astype(np.uint8) for bit in range(7)]
    return np.stack(rows)


def _nullspace(matrix: np.ndarray) -> np.ndarray:
    """Basis (as rows) of ``{w : matrix @ w == 0}`` over GF(2)."""
    work, pivots, row = matrix.copy() % 2, [], 0
    for column in range(work.shape[1]):
        candidates = np.flatnonzero(work[row:, column])
        if candidates.size == 0:
            continue
        source = row + int(candidates[0])
        work[[row, source]] = work[[source, row]]
        others = np.flatnonzero(work[:, column])
        work[others[others != row]] ^= work[row]
        pivots.append(column)
        row += 1
        if row == work.shape[0]:
            break
    free = [column for column in range(work.shape[1]) if column not in pivots]
    basis = np.zeros((len(free), work.shape[1]), np.uint8)
    for index, column in enumerate(free):
        basis[index, column] = 1
        for pivot_row, pivot_column in enumerate(pivots):
            basis[index, pivot_column] = work[pivot_row, column]
    return basis


def leading_run_words(classes: int, count: int,
                      rng: np.random.Generator) -> np.ndarray:
    """Words with ``S_1..S_(2*classes) == 0`` and ``S_(2*classes+1) != 0``.

    THE DEEPEST TRAJECTORY A WORD CAN DRIVE, and built rather than
    hunted.  While ``lfsr_len`` is 0 the discrepancy's tap loop is empty,
    so ``d`` IS ``s_n``: a word whose first ``classes`` odd syndrome
    classes vanish holds ``lfsr_len`` at 0 for ``2*classes`` steps and
    then takes one length change to ``2*classes+1``.  Those words are the
    nullspace of those classes' bits — the shortened BCH code at that
    radius — and the ones that also zero the NEXT class are excluded, so
    the jump is guaranteed rather than sampled for.  Returns an empty
    array where the rank stalls and the family does not exist.
    """
    basis = _nullspace(_syndrome_bits()[:7 * classes])
    out: list[np.ndarray] = []
    for _ in range(count * 40):
        word = ((rng.integers(0, 2, basis.shape[0], dtype=np.uint8) @ basis)
                % 2).astype(np.uint8)
        if bch.syndromes(word)[2 * classes]:
            out.append(word)
        if len(out) == count:
            break
    return np.stack(out) if out else np.zeros((0, bch.N_WORD), np.uint8)


def boundary_words(seed: int = 8172026) -> list[tuple[str, np.ndarray]]:
    """The seeded BM vector set — WORDS now, and why they have to be.

    See the module docstring's population (c): the batched arm's input
    domain is the syndromes of 0/1 words and nothing else, so a bare
    syndrome row is not a harder test of it but an ILLEGAL one.  The
    corners are therefore rebuilt out of words: uniform, sparse, heavy,
    the error ladder, and the leading-run families that walk ``lfsr_len``
    up to the deepest value a 100-bit word can reach.
    """
    rng = np.random.default_rng(seed)
    out: list[tuple[str, np.ndarray]] = [
        ("uniform random words",
         rng.integers(0, 2, (20000, bch.N_WORD), dtype=np.uint8)),
        ("the synthetic vectors", synthetic_words()),
        ("all-zero word", np.zeros((1, bch.N_WORD), np.uint8)),
    ]

    heavy: list[np.ndarray] = []
    for weight in (2, 7, 13, 14, 26, 40, 60, 80, 100):
        for _ in range(400):
            word = np.zeros(bch.N_WORD, np.uint8)
            word[rng.choice(bch.N_WORD, size=weight, replace=False)] = 1
            heavy.append(word)
    out.append(("fixed weights 2..100", np.stack(heavy)))

    for classes in range(1, bch.T):
        words = leading_run_words(classes, 64, rng)
        if words.shape[0]:
            out.append((f"leading run through S_{2 * classes} "
                        f"(lfsr_len {2 * classes + 1})", words))
    return [(name, bch.syndromes_many(words)) for name, words in out]
