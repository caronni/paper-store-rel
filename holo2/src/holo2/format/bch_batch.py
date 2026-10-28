"""The Stage-A word sweep's BCH decode, batched — bch.py's TWIN, not heir.

``bch.py`` is FORMAT-AXIS and CARRIED: it is pinned character for
character against ``holo.core.bch`` by ``tests/holo2_oracles/
test_oracle_tiles.py``, so a changed line there is a printed-format fork.
This module therefore adds **nothing** to it and edits **nothing** in it.
It IMPORTS bch's tables, its constants, its Berlekamp-Massey and its
batched syndrome kernel, and re-expresses the ROUTING between them so
that the one stage which calls it 147,456 times per window
(``solve/words.py``'s slot sweep) pays numpy dispatch once per batch
instead of once per candidate.

WHY THIS EXISTS (the GIL diagnosis, ``measure/H4-measurements/reports/
holo2-gil-diagnosis-REPORT.md``): the Stage-A word sweep measured ~72% of ALL receiver CPU,
of which ``bch._chien_roots`` alone was 30.0% and
``bch._berlekamp_massey`` the other 25.1% — a python loop over
127-element numpy arrays and a python loop over a 27-element python
list, each run once per candidate, at a size where numpy is pure
dispatch overhead and where python is simply slow.  TWO cards, in that
order: the batched CHIEN search landed first and left BM as 83% of what
the batched decode still cost (89 ms of 106 at H=4096) and as the last
GIL-held bulk in the sweep; the LOCKSTEP BM is the second, and it is
what :func:`berlekamp_massey_many` below is.

**THE ARMS ARE ONE ARITHMETIC.**  :func:`decode_many` returns exactly
what ``bch.decode_many`` returns — same list length, same row order, same
``None``s, same corrected words, same error counts — and the bar is
bit-identity, never a tolerance.  The switch is
:attr:`~holo2.solve.place_model.PlacementConfig.batched_word_sweep`;
``bch.decode_many`` remains THE ORACLE, and the population evidence is
``holo2/measure/bch_equivalence.py`` (run by path, never collected).

THE FIVE RULES READ OFF THE SCALAR CODE, and reproduced here in order
(``bch._decode_syndromes``, lines 304-318):

1. **an all-zero syndrome is a clean codeword** — return ``(word.copy(),
   0)`` and DO NOT run BM.  The batched arm splits the batch on
   ``syndromes.any(axis=1)`` before BM for exactly this reason;
2. **the BM refusal is two clauses, both of them** — ``lfsr_len > T`` OR
   ``len(sigma) - 1 != lfsr_len``.  The second is a statement about the
   TRIMMED locator (BM pops trailing zeros before returning), so it is
   read off the trim and never re-derived: the lockstep RETURNS that
   trimmed length as its own second output for exactly this reason;
3. **the Chien refusal is two clauses, both of them** — the root count
   over the FULL 127 positions must equal ``lfsr_len``, and no root may
   land in a shortened position (``>= N_WORD``).  Both are refusals, so
   evaluating them as one conjunction is the same decision;
4. **the final syndrome re-check stands** — a locator that passes 2 and 3
   can still fail to correspond to a binary error pattern, and the scalar
   path re-syndromes the corrected word and refuses if anything is left;
5. **the reported error count is ``int(lfsr_len)``**, which rule 3 has
   already forced to equal the root count.

ORDERING.  ``decode_many`` is row-order-preserving and row-independent:
result ``k`` is a function of input row ``k`` alone.  This module
therefore reorders WORK freely (it partitions rows into clean /
BM-refused / Chien-refused / accepted and processes each group as one
array) while writing every answer back to its own index.  Nothing
downstream depends on evaluation order — ``words._decode_candidates``
enumerates the returned list positionally and does its own global sort.

THE THREE RESTATEMENTS, each exact and each in THIS file (bch.py is
untouched):

* **the 0/1 validation.** ``bch._as_words`` asks
  ``np.isin(words, (0, 1)).all()`` AFTER ``astype(np.uint8)``.  On a
  uint8 array that is elementwise ``(w == 0) | (w == 1)``, i.e.
  ``w <= 1`` — one pass instead of a set-membership sort.  Both test the
  POST-cast array, so an input that wraps (``-1 -> 255``, ``256 -> 0``)
  is judged identically by both.  Measured: this call alone was 7.0% of
  pool-thread samples.
* **the BM input.** The scalar path builds ``[int(s) for s in synd]``
  per row and walks it in python; the lockstep takes the uint8 syndrome
  ROWS as they already are, so the per-row list never gets built at all.
* **the final re-check.** The scalar path calls ``bch.syndromes`` per
  corrected word; this calls ``bch._syndromes_many_words`` on the
  accepted block.  That substitution is not new and not mine: the
  CARRIED ``bch.decode_many`` already makes it for the initial screen,
  and it is exact because ``syndromes`` XOR-reduces the syndrome
  matrix's columns at the set bits while the batched kernel multiplies
  by the binary word first — the cleared columns contribute nothing to
  an XOR.

WHAT IS *NOT* RESTATED: every GF(2^7) product, the locator, the
correction and the syndrome matrix are bch's own tables and bch's own
arithmetic, reached by import.  There is no second copy of the field in
this repository and this file does not start one.

WHAT *IS* RESTATED, and it is the one thing in this file that is not
routing: **the Berlekamp-Massey recurrence itself**, as
:func:`berlekamp_massey_many` — the same branches, the same masks and
the same trim, advanced step-synchronously over a whole batch where the
scalar has ``if``, and **two of the scalar's steps at a time**.  Half of
its 26 steps are provably empty for the syndromes of a BINARY word, and
a binary word is the only thing that can reach this module: see that
function's PRECONDITION, which is a theorem about ``decode_many``'s own
input gate and NOT a property tested at runtime.  bch's
``_berlekamp_massey`` is still the ORACLE, is still general, and is
still what the scalar arm runs — the switch in ``solve/words.py`` falls
back to *it*, never to a second batched arm, and there is no second
batched arm to fall back to.  The bar is bit-identity on the returned
triple, proven by population and by fault injection in
``measure/bch_equivalence.py``, never by argument.

Self-contained: numpy + ``.bch``.
"""
from __future__ import annotations

import numpy as np

from . import bch

#: Rows per Chien block.  Mirrors the carried syndrome kernel's bounded
#: working set (``bch._syndromes_many_words``'s 4096): every row is
#: processed and returned in its original order, so this is a memory
#: ceiling and never a limit on the batch.  At 4096 the Chien working
#: set is one (4096, 127) uint8 accumulator plus a (4096, 127) int16
#: index — about 1.6 MB, per call and per thread.
CHIEN_BLOCK_ROWS: int = 4096


def _exp_doubled() -> np.ndarray:
    """``exp`` concatenated with itself: ``EXP2[s] == exp[s % 127]``.

    The scalar Chien spells the reduction ``exp[(log[cj] + pow) % 127]``.
    Both addends are in ``0..126``, so the sum is in ``0..252`` and a
    254-entry doubled table answers the same question with the modulo
    deleted rather than approximated.  Exact by construction; the values
    are bch's own, and ``_EXPZ`` below is this table with a zero tail.
    """
    exp, _log = bch.gf_tables()
    return np.concatenate([exp, exp])


_EXP2 = _exp_doubled()
_LOG16 = bch.gf_tables()[1].astype(np.int16)          # (128,), log[0] unused
_CHIEN_POW16 = bch._chien_pow_matrix().astype(np.int16)   # (127, 2T+1)

#: The log a ZERO field element gets, and the reason it is 254: it is
#: past the doubled table, so any sum that includes it lands in the
#: POISONED tail below and produces 0.  Real logs are ``0..126``, so no
#: legal exponent can collide with it.
_POISON: int = 2 * bch._ORDER
#: ``_EXP2`` with a zero tail: ``_EXPZ[s] == exp[s % 127]`` for
#: ``s < 254`` and ``0`` for every ``s >= 254``.  The scalar spells "a
#: product with a zero operand contributes nothing" as ``if ci and sj``
#: — a BRANCH, which is what a lockstep cannot have.  Here it is spelled
#: as an index: ``log(0) = 254`` poisons the sum, the sum lands in the
#: tail, and the term is exactly the zero the scalar's skip contributes.
#: The largest sum is ``254 + 254 = 508``, so 512 entries close it.
_EXPZ = np.concatenate([_EXP2, np.zeros(512 - _EXP2.size, np.uint8)])
#: ``log`` with ``log[0] = _POISON``.  Everything else is bch's table.
_LOGZ = _LOG16.copy()
_LOGZ[0] = _POISON
#: Only the first ``T + 1`` locator coefficients can be nonzero: rule 2
#: forces ``len(sigma) - 1 == lfsr_len <= T`` before Chien ever runs.
_SIGMA_WIDTH: int = bch.T + 1
#: ``(T + 1, 127)``: the Chien exponent table, one contiguous row per
#: locator coefficient, which is the axis the batched loop walks.
_POW_COLUMNS = np.ascontiguousarray(_CHIEN_POW16[:, :_SIGMA_WIDTH].T)
#: Width of the lockstep's connection-polynomial row, and a BOUND rather
#: than a cap: the scalar's ``c_poly`` is a growing python list, and its
#: length never exceeds ``2T + 1``.
#:
#: PROOF (the loop's own invariant, ``len(c_poly) - 1 <= lfsr_len``).
#: At entry ``c_poly = b_poly = [1]``, ``lfsr_len = 0``, ``shift = 1``,
#: which is the state "``b_poly`` was captured at step ``-1`` with
#: ``L_b = 0``", so ``shift = n - n_b`` and ``lfsr_len = n_b + 1 - L_b``
#: hold from the start and are re-established at every length change.
#: With ``len(b_poly) - 1 <= L_b``, the extension the scalar may perform
#: satisfies ``len(b_poly) + shift - 1 <= L_b + (n - n_b) = n + 1 -
#: lfsr_len``.  A length-changing step (``2 * lfsr_len <= n``) sets
#: ``lfsr_len = n + 1 - lfsr_len``, and both the old length (``<=
#: lfsr_len + 1 <= n - lfsr_len + 1``) and the extension respect it; a
#: non-changing step has ``2 * lfsr_len > n``, i.e. ``n + 1 - lfsr_len
#: <= lfsr_len``, so the same extension bound respects the unchanged
#: ``lfsr_len``.  Since ``lfsr_len <= n + 1 <= 2T``, the list length
#: never passes ``2T + 1``.
#:
#: CHECKED, not assumed: :func:`berlekamp_massey_many` re-derives the
#: extension length at every step it takes and raises if it ever exceeds
#: this.  (Its own precondition bounds the polynomial at 26 coefficients
#: — one less — but that is a consequence of the binary premise, while
#: this bound holds for any syndrome sequence, so this is the one kept.)
_BM_WIDTH: int = 2 * bch.T + 1


def _as_words(words_bits: np.ndarray) -> np.ndarray:
    """``bch._as_words`` for ``N_WORD``, with its two ValueErrors verbatim.

    ``astype(..., copy=False)`` where the carried helper always copies:
    this module only ever READS the validated array (every returned word
    is a fresh ``copy()`` or the product of an XOR), so the copy bought
    nothing but a 400 kB memcpy per call.
    """
    words = np.asarray(words_bits)
    if words.ndim != 2 or words.shape[1] != bch.N_WORD:
        raise ValueError(f"expected (H, {bch.N_WORD}), got {words.shape}")
    words = words.astype(np.uint8, copy=False)
    if not bool((words <= 1).all()):
        raise ValueError("bits must be 0/1")
    return words


def berlekamp_massey_many(
    syndrome_rows: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``bch._berlekamp_massey`` for a stack of BINARY-WORD syndromes.

    **PRECONDITION — the syndromes of 0/1 words, and it is a THEOREM
    about the call graph, not a test.**  The one caller is
    :func:`decode_many`, which validates its input with
    :func:`_as_words` (``(w <= 1).all()``, a ValueError otherwise) and
    then computes these rows itself with ``bch._syndromes_many_words``.
    So every row that arrives here is the syndrome of a binary word, and
    ``S_2j == S_j^2`` holds on it by Frobenius: the syndrome
    ``S_m = sum_i r_i alpha^(m i)`` over error values ``r_i`` in {0, 1},
    squaring is a field automorphism of GF(2^7), and ``r_i^2 == r_i``.
    That identity is what makes half the recurrence empty (below).  It
    is asserted over every real and synthetic population by
    ``measure/bch_equivalence.py`` — a tripwire on the evidence side,
    where a statement about mathematics belongs, and never a per-block
    runtime check in here.  A caller that hands this function arbitrary
    syndrome rows gets a wrong locator, silently: use the scalar
    ``bch._berlekamp_massey``, which is general.

    ``syndrome_rows`` is ``(H, 2T)`` uint8 — one candidate per row, the
    same values the scalar receives as ``[int(s) for s in synd]``.
    Returns three row-aligned arrays:

    * ``sigma`` ``(H, 2T + 1)`` uint8 — connection-polynomial
      coefficients ascending, zero past the trim;
    * ``trimmed`` ``(H,)`` int64 — ``len(c_poly)`` AFTER the scalar's
      trailing-zero pop, so ``sigma[h, :trimmed[h]].tolist()`` IS the
      list the scalar returns, element for element;
    * ``lfsr_len`` ``(H,)`` int64 — the scalar's second return value.

    THE SCALAR, TRANSCRIBED (``bch._berlekamp_massey``, lines 242-281).
    Every clause below is quoted from it, because the difference between
    ``<`` and ``<=`` here is a different decoder:

    * the loop is ``for n, s_n in enumerate(synd)`` — a FIXED ``2T``
      steps with NO early exit, which is what makes a lockstep possible
      at all: which steps run does not depend on the row, so there is no
      row that finishes sooner and has to be carried.  (This arm runs 13
      of those 26 — see THE TWO-STEP COLLAPSE below — and the property
      that matters is untouched: it runs the same 13 for every row.)
    * the discrepancy is ``d = s_n`` XORed with ``c_poly[i] * synd[n-i]``
      for ``i in range(1, min(lfsr_len, len(c_poly) - 1) + 1)``.  The
      bound is that ``min``, spelled here as ``minimum(lfsr_len,
      sigma_len - 1)``, and it is applied even though the invariant
      above makes ``len(c_poly) - 1`` the smaller of the two every time:
      the scalar's arithmetic is what is being reproduced, not the
      invariant's consequences.  Products where ``ci`` or ``sj`` is zero
      are SKIPPED by the scalar and POISONED here (``_LOGZ``/``_EXPZ``),
      which contributes the same nothing to an XOR;
    * ``if d == 0: shift += 1; continue`` — nothing else in the state
      moves.  Here that is simply a row the update masks out;
    * otherwise ``coef_log = (log[d] - log[b_disc]) % 127`` and ``need =
      len(b_poly) + shift``;
    * the length-update condition is ``if 2 * lfsr_len <= n`` — ``<=``,
      so the EQUALITY case takes the length change (it is the case that
      fires at ``n = 0`` on any nonzero ``S_1``, and repeatedly after);
    * BOTH branches then extend ``c_poly`` to ``need`` if it is shorter
      and XOR ``alpha^coef_log * b_poly`` in at offset ``shift``.  This
      is one masked update for both, because they differ in nothing else;
    * the length-changing branch ALSO snapshots ``prev = c_poly[:]``
      BEFORE the extension and before that XOR, then sets ``lfsr_len =
      n + 1 - lfsr_len``, ``b_poly = prev``, ``b_disc = d``, ``shift =
      1``.  The snapshot's ORDER is load-bearing: ``b_poly`` becomes the
      connection polynomial as it was on entry to the step, never the
      updated one, and ``len(b_poly)`` becomes the length BEFORE the
      extension;
    * the non-changing branch does ``shift += 1``, which with the
      ``d == 0`` case makes the whole step's rule ``shift = 1`` where
      the length changed and ``shift + 1`` everywhere else;
    * the return TRIMS: ``while len(c_poly) > 1 and c_poly[-1] == 0:
      pop()``.  ``c_poly[0]`` is 1 at entry and no update can reach
      index 0 (``shift >= 1`` always), so the trim always stops at a
      nonzero coefficient and the ``> 1`` guard never binds; the trimmed
      length is therefore ``1 + the last nonzero index within
      len(c_poly)``, which is what this computes.

    **THE TWO-STEP COLLAPSE — why this loop runs 13 of those 26 steps.**
    Number the steps as the code does, ``step = 0..25``, so ``step``
    handles ``S_(step+1)``.  Under the precondition every ODD ``step``
    (the even-numbered syndrome ``S_2j``) has a ZERO discrepancy:

    * ALGEBRA.  Write ``f = sigma * S`` as formal series, so ``d`` at
      step ``n`` is ``f_(n+1)``.  Squaring is an automorphism, so
      ``f^2 = sigma^2 S^2``, and ``S_2j == S_j^2`` says exactly that
      ``S^2`` IS the even part of ``S``: ``S^2 = S + S_odd``.  Then
      ``sigma^2 S^2 = sigma * f + sigma^2 S_odd``, and ``sigma^2`` has
      only even degrees while ``S_odd`` has only odd ones, so their
      product cannot reach an even degree.  Reading off ``x^(2j)``:
      ``(f_j)^2 = f_2j + sum_(i>=1) sigma_i f_(2j-i)``.  When the state
      is in the length-change regime (``2 * lfsr_len <= step``) every
      ``f`` on the right lies in the window BM has already zeroed, and
      ``d = f_2j = 0`` follows with nothing else assumed.  In the other
      regime the survivors cancel in pairs ``k <-> 2j-k`` about ``j``
      over an interval symmetric in ``j`` — characteristic 2, so each
      pair vanishes — and the self-paired ``k = j`` term cancels against
      ``(f_j)^2``, which is the classical binary-BCH statement that the
      even syndromes carry no information the odd ones did not.
    * MEASURED, which is what this rests on: ``0`` nonzero odd-step
      discrepancies in 294,632 (22,664 real and synthetic word rows x 13
      steps), and the even steps are ~99% nonzero, so the halving is
      real work removed and not a tautology.

    **AND WHY A ZERO DISCREPANCY IS AN IDENTITY UPDATE HERE.**  Read off
    this function's own body, not a textbook: ``d == 0`` for a row makes
    ``nonzero`` False there, hence ``change`` False; when it is False for
    EVERY row the whole ``if nonzero.any():`` block is skipped, so
    ``sigma``, ``sigma_len``, ``auxiliary``, ``auxiliary_len``,
    ``b_disc`` and ``lfsr_len`` are all untouched — and even for a single
    row the masks (``np.where(nonzero, ...)``/``np.where(change, ...)``)
    write back the row's own previous value.  ONE state array still
    moves: ``shift``, which the last line advances by 1 on every
    non-changing step.  **The skipped step is therefore not a no-op, and
    its ``shift`` increment is not optional** — the next taken step
    gathers ``auxiliary`` at ``_BM_WIDTH + i - shift`` and reads
    ``need = auxiliary_len + shift``, so a shift short by one lands the
    whole update one coefficient low.  The collapse is exactly this:
    take step ``n``, whose own rule is ``shift = 1 if change else
    shift + 1``, then apply the skipped step ``n+1``'s ``shift + 1`` to
    the result, giving ``shift = 2 if change else shift + 2``.  That is
    the ``+ 2`` in the loop, and it is the whole of the arithmetic the
    13 skipped steps would have performed.  (Verified before it was
    written: the shipped 26-step arm's state arrays, snapshotted around
    all 13 odd steps on 4,096 real rows — every array identical,
    ``shift`` up by exactly 1.)

    WHAT THE PREMISE ALSO BOUNDS, measured and used nowhere: because a
    length change can now only happen on an even ``step``, ``lfsr_len``
    lands at ``step + 1 - lfsr_len <= 25`` and the connection polynomial
    at 26 coefficients, one inside :data:`_BM_WIDTH`; real 100-bit words
    reach at most ``lfsr_len`` 23 (higher runs are unreachable — the
    shortened code's syndrome map stalls in rank), and the trailing-zero
    trim was measured never to pop, over a 1 M-word sweep and over 0.5 M
    bare rows of the strictly larger space the premise alone allows.
    The width bound's ``raise`` stays the proved defensive tripwire it
    is: this paragraph is a census, not a licence to shrink anything.

    THE STATE, as arrays over the H rows: ``sigma`` and its live length
    ``sigma_len`` (the python list's ``len``, tracked because the
    discrepancy bound and the trim both read it), ``auxiliary`` and
    ``auxiliary_len`` for ``b_poly``, ``lfsr_len``, ``shift``,
    ``b_disc``.  ``auxiliary`` is kept SHIFT-PADDED — ``2 * _BM_WIDTH``
    wide with a permanently zero left half — so the scalar's
    ``c_poly[i + shift] ^= ... b_poly[i]`` becomes one gather at
    ``_BM_WIDTH + i - shift``: below ``shift`` it reads the zero pad and
    at or above ``len(b_poly) + shift`` it reads b's own zero tail,
    which are precisely the indices the scalar's loop does not write.
    """
    rows = np.asarray(syndrome_rows, np.uint8)
    if rows.ndim != 2 or rows.shape[1] != 2 * bch.T:
        raise ValueError(f"expected (H, {2 * bch.T}), got {rows.shape}")
    height = rows.shape[0]
    sigma = np.zeros((height, _BM_WIDTH), np.uint8)
    sigma[:, 0] = 1                                       # c_poly = [1]
    auxiliary = np.zeros((height, 2 * _BM_WIDTH), np.uint8)
    auxiliary[:, _BM_WIDTH] = 1                           # b_poly = [1]
    sigma_len = np.ones(height, np.int16)
    auxiliary_len = np.ones(height, np.int16)
    lfsr_len = np.zeros(height, np.int16)
    shift = np.ones(height, np.int16)
    b_disc = np.ones(height, np.uint8)
    synd_log = _LOGZ[rows]                                # (H, 2T) int16
    lane = np.arange(height)[:, None]
    column = np.arange(_BM_WIDTH, dtype=np.int16)
    padded = column + np.int16(_BM_WIDTH)

    for step in range(0, 2 * bch.T, 2):               # the odd ones are 0
        discrepancy = rows[:, step].copy()
        if step:
            # synd[n - i] for i = 1..n, against c_poly[1..n].
            index = _LOGZ[sigma[:, 1:step + 1]] + synd_log[:, step - 1::-1]
            index = np.where(
                column[1:step + 1] <= np.minimum(lfsr_len,
                                                 sigma_len - 1)[:, None],
                index, np.int16(_POISON))
            discrepancy ^= np.bitwise_xor.reduce(_EXPZ[index], axis=1)
        nonzero = discrepancy != 0
        change = nonzero & (2 * lfsr_len <= step)         # the ``<=``
        if nonzero.any():
            need = auxiliary_len + shift
            if int(np.max(need, initial=0, where=nonzero)) > _BM_WIDTH:
                raise RuntimeError(                       # unreachable
                    f"BM connection polynomial wants {int(need.max())} "
                    f"coefficients at step {step}, past the proved bound "
                    f"{_BM_WIDTH} — the state width is wrong, not the cap")
            scale = np.where(
                nonzero,
                (_LOGZ[discrepancy] - _LOGZ[b_disc]) % bch._ORDER,
                _POISON).astype(np.int16)
            taken = auxiliary[lane, padded[None, :] - shift[:, None]]
            previous, previous_len = sigma.copy(), sigma_len.copy()
            sigma ^= _EXPZ[scale[:, None] + _LOGZ[taken]]
            sigma_len = np.where(nonzero, np.maximum(sigma_len, need),
                                 sigma_len).astype(np.int16)
            grown = (step + 1 - lfsr_len).astype(np.int16)
            auxiliary[:, _BM_WIDTH:] = np.where(
                change[:, None], previous, auxiliary[:, _BM_WIDTH:])
            auxiliary_len = np.where(change, previous_len,
                                     auxiliary_len).astype(np.int16)
            b_disc = np.where(change, discrepancy, b_disc)
            lfsr_len = np.where(change, grown, lfsr_len).astype(np.int16)
        # This step's own rule (1 or +1), then the skipped step's +1.
        shift = np.where(change, np.int16(2), shift + 2).astype(np.int16)

    live = (sigma != 0) & (column[None, :] < sigma_len[:, None])
    trimmed = _BM_WIDTH - np.argmax(live[:, ::-1], axis=1)
    return sigma, trimmed.astype(np.int64), lfsr_len.astype(np.int64)


def chien_root_mask(sigma_rows: np.ndarray) -> np.ndarray:
    """``bch._chien_roots`` for a stack of locators: ``(S, 127)`` bool.

    ``sigma_rows`` is ``(S, T + 1)`` uint8, each row one locator's
    coefficients ascending, zero-padded past its degree.  Returns the
    mask of positions ``i`` where ``sigma(alpha^-i) == 0`` — so
    ``np.flatnonzero(mask[s])`` is the scalar function's return value for
    row ``s``, ascending, identical.

    The scalar loop skips a zero coefficient; this evaluates every
    ``j`` and multiplies the term by the coefficient's own nonzero-ness,
    which is the same accumulation because a skipped term and a zeroed
    term contribute the same nothing to an XOR.  Coefficient order is
    still ascending ``j``, though XOR makes that immaterial.
    """
    rows = np.asarray(sigma_rows, np.uint8)
    if rows.ndim != 2 or rows.shape[1] != _SIGMA_WIDTH:
        raise ValueError(f"expected (S, {_SIGMA_WIDTH}), got {rows.shape}")
    mask = np.empty((rows.shape[0], bch.N_FULL), dtype=bool)
    for lower in range(0, rows.shape[0], CHIEN_BLOCK_ROWS):
        block = rows[lower:lower + CHIEN_BLOCK_ROWS]
        logs = _LOG16[block]                             # (B, 14) int16
        live = (block != 0)
        values = np.zeros((block.shape[0], bch.N_FULL), dtype=np.uint8)
        for j in range(_SIGMA_WIDTH):
            column = live[:, j]
            if not column.any():
                continue
            term = _EXP2[logs[:, j, None] + _POW_COLUMNS[None, j, :]]
            values ^= term * column[:, None].astype(np.uint8)
        mask[lower:lower + block.shape[0]] = values == 0
    return mask


def decode_many(
    words_bits: np.ndarray,
) -> list[tuple[np.ndarray, int] | None]:
    """``bch.decode_many``, batched at BM and Chien — bit-identical.

    Same signature, same return type, same row order.  See the module
    docstring for the five acceptance rules this reproduces and for the
    three exact restatements it makes; every GF operation below is
    bch's own.
    """
    words = _as_words(words_bits)
    height = words.shape[0]
    out: list[tuple[np.ndarray, int] | None] = [None] * height
    if height == 0:
        return out
    syndromes = bch._syndromes_many_words(words)

    # RULE 1 — an all-zero syndrome is already a codeword, and BM never
    # sees it.  This is the scalar path's first line, as a partition.
    dirty = syndromes.any(axis=1)
    for index in np.flatnonzero(~dirty):
        out[int(index)] = (words[index].copy(), 0)

    # RULE 2 — BM in LOCKSTEP over every row with a nonzero syndrome,
    # then both refusal clauses as one mask.  ``trimmed`` is the length
    # of the TRIMMED locator, which is what the second clause reads.
    dirty_rows = np.flatnonzero(dirty)
    if dirty_rows.size == 0:
        return out
    sigma, trimmed, lengths = berlekamp_massey_many(syndromes[dirty_rows])
    kept = (lengths <= bch.T) & (trimmed - 1 == lengths)
    survivors = dirty_rows[kept]
    if survivors.size == 0:
        return out
    degrees = lengths[kept]
    # The kept rows have ``trimmed - 1 == lfsr_len <= T``, so every
    # coefficient at or past ``_SIGMA_WIDTH`` is zero and this slice is
    # the scalar's ``sigma`` zero-padded to the Chien width, exactly.
    coefficients = sigma[kept, :_SIGMA_WIDTH]

    # RULE 3 — the Chien search, batched: root count must equal the
    # locator degree AND no root may sit in a shortened position.
    roots = chien_root_mask(coefficients)
    accepted = np.flatnonzero(
        (roots.sum(axis=1) == degrees) & ~roots[:, bch.N_WORD:].any(axis=1))
    if accepted.size == 0:
        return out

    # RULE 4 — correct, then re-syndrome the corrected words and refuse
    # any locator that did not correspond to a binary error pattern.
    rows = survivors[accepted]
    corrected = words[rows] ^ roots[accepted, :bch.N_WORD].astype(np.uint8)
    clean = ~bch._syndromes_many_words(corrected).any(axis=1)

    # RULE 5 — the count reported is the locator degree, and each word is
    # returned as its own array, exactly as ``word.copy()`` gives one.
    for slot in np.flatnonzero(clean).tolist():
        out[int(rows[slot])] = (corrected[slot].copy(),
                                int(degrees[accepted[slot]]))
    return out


__all__ = ["CHIEN_BLOCK_ROWS", "berlekamp_massey_many", "chien_root_mask",
           "decode_many"]
