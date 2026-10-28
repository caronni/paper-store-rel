"""The two-step lockstep Berlekamp-Massey against the carried scalar one.

The EQUIVALENCE PROOF is ``holo2/measure/bch_equivalence.py`` — real and
synthetic populations, the boundary families below in bulk, fault
injections and redundancy probes, run by path and never collected.  This
is the cheap collected guard that keeps
``bch_batch.berlekamp_massey_many`` honest at suite speed: a few hundred
rows chosen so that every branch of the scalar's loop is walked, compared
on the WHOLE returned triple.

``bch._berlekamp_massey`` is the oracle here as everywhere: it is the
CARRIED function (pinned character for character against
``holo.core.bch`` by ``tests/holo2_oracles/``), so a divergence means
the lockstep is wrong, never that the scalar is.

EVERY ROW HERE IS THE SYNDROME OF A 0/1 WORD, and that is the point
rather than a convenience: the batched arm takes two of the scalar's
steps at a time, which is exact for binary-word syndromes
(``S_2j == S_j^2``) and wrong for anything else.  ``decode_many``'s own
input gate is what makes that a theorem in production — so the vectors
that probe BM's boundary are built as WORDS here, and the corners that
no word can reach are pinned as unreachable instead of being invented.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo2.format import bch, bch_batch

WIDTH = 2 * bch.T


def _scalar(rows: np.ndarray) -> list[tuple[list[int], int]]:
    return [bch._berlekamp_massey([int(value) for value in row])
            for row in rows]


def _lockstep(rows: np.ndarray) -> list[tuple[list[int], int]]:
    sigma, trimmed, lengths = bch_batch.berlekamp_massey_many(rows)
    return [(sigma[index, :int(trimmed[index])].tolist(),
             int(lengths[index]))
            for index in range(rows.shape[0])]


def _syndrome_bits() -> np.ndarray:
    """(91, 100) over GF(2): the map word -> (S_1, S_3, ..., S_25), by bit."""
    exp, _log = bch.gf_tables()
    rows = []
    for order in range(1, WIDTH, 2):
        values = np.array([int(exp[(order * i) % bch._ORDER])
                           for i in range(bch.N_WORD)], np.int64)
        rows += [((values >> bit) & 1).astype(np.uint8) for bit in range(7)]
    return np.stack(rows)


def _nullspace(matrix: np.ndarray) -> np.ndarray:
    """Basis (as rows) of {w : matrix @ w == 0 over GF(2)}."""
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


def _leading_run_words(classes: int, count: int = 8) -> np.ndarray:
    """Words with ``S_1..S_(2*classes) == 0`` and ``S_(2*classes+1) != 0``.

    Such a word holds ``lfsr_len`` at 0 for ``2*classes`` steps — while
    ``lfsr_len`` is 0 the discrepancy's tap loop is empty, so ``d`` IS
    ``s_n`` — and then takes ONE length change to ``lfsr_len =
    2*classes+1``.  It is the deepest trajectory a 100-bit word can drive
    BM through, and it is built rather than sampled: the words whose
    first ``classes`` odd syndrome classes vanish are the nullspace of
    those classes' bits, i.e. the shortened BCH code at that radius.
    """
    basis = _nullspace(_syndrome_bits()[:7 * classes])
    rng = np.random.default_rng(20260817 + classes)
    out: list[np.ndarray] = []
    for _ in range(200):
        word = ((rng.integers(0, 2, basis.shape[0], dtype=np.uint8) @ basis)
                % 2).astype(np.uint8)
        if bch.syndromes(word)[2 * classes]:
            out.append(word)
        if len(out) == count:
            break
    return np.stack(out) if out else np.zeros((0, bch.N_WORD), np.uint8)


def _corrupted_codewords() -> np.ndarray:
    """Codewords carrying every error weight 0..2T-1 — the ladder."""
    rng = np.random.default_rng(815)
    messages = rng.integers(0, 2, (8, bch.K_MSG), dtype=np.uint8)
    words = [bch.encode(message) for message in messages]
    out = []
    for weight in range(2 * bch.T):
        word = words[weight % len(words)].copy()
        if weight:
            word[rng.choice(bch.N_WORD, size=weight, replace=False)] ^= 1
        out.append(word)
    return np.stack(out)


def test_lockstep_matches_the_scalar_on_uniform_words() -> None:
    words = np.random.default_rng(20260817).integers(
        0, 2, (256, bch.N_WORD), dtype=np.uint8)
    rows = bch.syndromes_many(words)
    assert _lockstep(rows) == _scalar(rows)


def test_lockstep_matches_the_scalar_on_the_error_ladder() -> None:
    rows = bch.syndromes_many(_corrupted_codewords())
    answers = _scalar(rows)
    assert _lockstep(rows) == answers
    assert answers[0] == ([1], 0)                    # the clean codeword
    assert max(length for _, length in answers) >= bch.T


@pytest.mark.parametrize("classes", [1, 5, 9, 10, 11])
def test_lockstep_matches_the_scalar_on_the_deepest_words(
        classes: int) -> None:
    """The reachable corners: lfsr_len up to 23, and the runs below."""
    words = _leading_run_words(classes)
    assert words.shape[0], f"no word zeroes the first {classes} classes"
    rows = bch.syndromes_many(words)
    answers = _scalar(rows)
    assert _lockstep(rows) == answers
    # The construction's own claim, checked rather than trusted — but
    # only where the jump ENDS the trajectory: the length change lands
    # ``lfsr_len`` at ``2*classes+1``, and a later step can change it
    # again only if ``2*lfsr_len <= step`` is still satisfiable within
    # the 26 steps.  Below that the run is a floor, not the answer.
    lengths = {length for _, length in answers}
    if 2 * (2 * classes + 1) > 2 * bch.T - 2:
        assert lengths == {2 * classes + 1}
        assert {len(sigma) for sigma, _ in answers} == {2 * classes + 2}
    else:
        assert min(lengths) >= 2 * classes + 1


def test_the_deepest_run_a_word_can_drive_is_lfsr_len_23() -> None:
    """Past 23 the shortened code's syndrome map STALLS in rank.

    A longer leading run needs a word whose first 12 odd syndrome
    classes vanish while the 13th does not; the last class adds no rank
    over the first twelve, so no such word exists and ``lfsr_len`` 25 —
    legal for a bare syndrome sequence — is unreachable through
    ``decode_many``.  The 26-coefficient ceiling is the premise's, one
    inside the width bound the state array is sized by.
    """
    matrix = _syndrome_bits()
    assert _leading_run_words(12).shape[0] == 0
    assert (_nullspace(matrix[:7 * 12]).shape[0]
            == _nullspace(matrix).shape[0] == bch.K_MSG)
    assert _leading_run_words(11).shape[0] > 0


def test_word_syndromes_carry_the_two_step_premise() -> None:
    """``S_2j == S_j^2`` on everything the gate lets through — the theorem.

    Frobenius on 0/1 error values.  The batched arm skips the odd steps
    BECAUSE of this, so the suite states it about the same inputs the
    production path feeds, and states that the gate is what enforces it.
    """
    exp, log = bch.gf_tables()
    square = np.zeros(128, np.uint8)
    for value in range(1, 128):
        square[value] = exp[(2 * int(log[value])) % bch._ORDER]
    rng = np.random.default_rng(4242)
    words = np.vstack([
        rng.integers(0, 2, (512, bch.N_WORD), dtype=np.uint8),
        _corrupted_codewords(),
        _leading_run_words(11)])
    rows = bch.syndromes_many(words)
    assert np.array_equal(rows[:, 1::2], square[rows[:, :bch.T]])
    with pytest.raises(ValueError):          # the gate, in one line
        bch_batch.decode_many(np.full((2, bch.N_WORD), 2, np.uint8))


def test_empty_batch_keeps_its_shapes() -> None:
    sigma, trimmed, lengths = bch_batch.berlekamp_massey_many(
        np.zeros((0, WIDTH), np.uint8))
    assert sigma.shape == (0, bch_batch._BM_WIDTH)
    assert trimmed.shape == (0,) and lengths.shape == (0,)


@pytest.mark.parametrize("shape", [(4, WIDTH - 1), (4, WIDTH + 1), (WIDTH,)])
def test_a_wrong_syndrome_shape_is_refused(shape: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        bch_batch.berlekamp_massey_many(np.zeros(shape, np.uint8))
