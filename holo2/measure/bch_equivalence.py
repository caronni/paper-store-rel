#!/usr/bin/env python
"""Bit-equivalence of the two Stage-A word decoders — RUN BY PATH.

    env/bin/python holo2/measure/bch_equivalence.py [--fault NAME]

NOT A TEST and not collectable as one: no ``test_`` name, no pytest
fixtures, a ``__main__`` entry point, and it lives outside ``testpaths``
twice over — the same standing the user gave
``measure/refine_equivalence.py``.

WHAT IT PROVES.  ``PlacementConfig.batched_word_sweep`` chooses between
two implementations of one arithmetic — ``format.bch.decode_many`` (the
CARRIED scalar path, and THE ORACLE) and ``format.bch_batch.decode_many``
(the twin, which batches BOTH per-candidate loops — Berlekamp-Massey and
the Chien search — across the candidate block).
Every claim the twin makes is that they are the SAME decoder, not a close
one, so the bar is bit-identity and nothing weaker: no tolerance, no
epsilon, no "same number of candidates".  For every row of every batch it
compares

* **the verdict** — decoded or refused, which is where a mis-copied
  acceptance clause shows first;
* **the corrected word** — array for array, dtype and shape included;
* **the error positions** — ``flatnonzero(input ^ corrected)``, stated
  separately even though the word equality implies it, because positions
  are what a locator bug actually gets wrong;
* **the error count** — value AND python type;
* **the order** — result ``k`` answers input row ``k``, batch length
  included.

THE POPULATIONS, and one section of evidence that is not a population:
(a) intercepted real sweeps, (b) synthetic vectors, (b2) the rule-4
drive, (c) the boundary vectors, (d) the two-step card's own measurements.

**(a) INTERCEPTED REAL SWEEPS.**  It does not synthesise Stage-A calls;
it hooks the seam.  ``bch.decode_many`` is wrapped so that every batch
the real receiver decodes runs BOTH arms on the identical candidate block
and returns the ORACLE's answer — the decode proceeds entirely on the old
path and the twin never influences the population it is measured on.
That requires pinning the receiver to the oracle arm for the run (see
:func:`force_oracle_arm`): the switch's production default is now ON, and
a decode on the default routes past this seam entirely.  The
arms are rendered pages from ``verdicts/_fixtures.py``'s own builders
(which emit through the real ``src/holo`` generator), chosen to make cold
Stage A actually run: a clean page, the measured e032 channel warp, and a
banded page whose right quarter kills the word code so window after
window falls through the consult to the word route.

**(b) SYNTHETIC VECTORS.**  Chien is format-adjacent and cheap, so the
synthetic sweep is where the RULES get exercised rather than merely
visited.  Seeded, every one of them:

* clean codewords (the all-zero-syndrome path that must skip BM);
* codewords with error patterns at every weight 0..T;
* codewords BEYOND the radius (weights T+1..T+12) — must-reject or
  must-agree-on-the-miscorrection, whichever the oracle says;
* uniform random 100-bit words, which is what the real sweep mostly
  sees and where the BM degree clause fires;
* **truncated FULL-length codewords** — a degree<127 codeword of the
  unshortened code whose x^100..x^126 tail is nonzero, cut to 100 bits.
  Its locator's roots land in the SHORTENED positions, which is the one
  refusal clause no amount of random noise reaches on purpose.

It classifies every synthetic input by which of the scalar decoder's five
rules disposed of it and prints the census, so "the populations agreed"
is never mistaken for "the populations reached anything".

**(c) THE BOUNDARY VECTORS — WORDS, since the two-step card.**  BM is
not proven merely THROUGH the decoder: population (c) compares
``bch_batch.berlekamp_massey_many`` against ``bch._berlekamp_massey``
DIRECTLY, row by row, on the returned triple — the trimmed coefficient
list, its length, and ``lfsr_len``.  It has to be direct, because the
five acceptance rules can MASK a BM divergence (two different locators
that both refuse are the same decode).

Until the two-step card these vectors were BARE syndrome rows — a
strictly larger space than the syndromes of 100-bit words, which was
then the point.  It is now the opposite of the point: the batched arm
takes two of the scalar's steps at a time and is exact only where
``S_2j == S_j^2``, which ``decode_many``'s 0/1 gate makes true of
everything it can ever be given.  A bare row is not a harder test of
that arm, it is an ILLEGAL one, and the general 26-step recurrence that
could have answered it is gone from src (nothing in production would
call it; the config switch falls back to the SCALAR).  So the corners
are rebuilt out of WORDS, and how far a word can push BM turned out to
be an open question worth settling rather than assuming:

* uniform, sparse and FIXED-WEIGHT words (2..100), the error ladder,
  the synthetic set, and the all-zero word;
* LEADING-RUN FAMILIES, built not sampled: the words whose first ``k``
  odd syndrome classes vanish are the nullspace of those classes'
  bits — the shortened BCH code at that radius — and one that does not
  also zero the next class holds ``lfsr_len`` at 0 for ``2k`` steps
  (provable, not hoped for: while ``L == 0`` the tap loop is empty, so
  ``d`` IS ``s_n``) and then jumps to ``2k+1``;
* MEASURED REACH (the census prints it every run): words reach
  ``lfsr_len`` 23 and a 24-coefficient locator.  Past that the
  shortened code's syndrome map STALLS in rank — no word has
  ``S_1..S_24 = 0`` with ``S_25 != 0`` — so ``lfsr_len`` 25, the
  26-coefficient locator, and the 27-wide width bound are UNREACHABLE
  through ``decode_many``, and the trailing-zero trim was measured
  never to pop on a 1 M-word sweep.  Those bare-row corners are not
  replaced by pretend ones: they are recorded as out of reach, the
  width-bound ``raise`` stays as the proved defensive tripwire it
  always was, and the trim clause is exercised at the degrees words DO
  reach (see the ``bm-no-trim`` entry in PROBES, which the finding
  demoted from a fault to a probe);
* the real sweep's OWN syndrome rows, sampled from the intercept, so
  the direct comparison also runs on the structured population.

**(d) THE TWO-STEP CARD'S OWN EVIDENCE.**  Two claims, measured on the
populations above and on the real rows: that every step the shipped arm
SKIPS carries a zero discrepancy, and that skipping them changed no
answer.  Both are measured against the 26-step general recurrence
rebuilt from the shipped source by two substitutions
(:data:`GENERAL`) — the development bridge the card was derived
through, kept on the evidence side rather than in src, where it would
be dead code.  A third substitution wires a per-step recorder into that
same source, so the discrepancy census exists without a second
transcription of the loop anywhere.  The premise itself is asserted as
a TRIPWIRE over every population and over every block the real decode
hands the arm, with a positive control each run proving the tripwire
can still fire.

**(b2) THE RULE-4 DRIVE, and why it needs one.**  The census reaches
every clause except ``recheck_failed`` — the final syndrome re-check —
and it is not for want of trying: 20,000 uniform words reach it zero
times, and the reason is algebraic, not statistical.  A BINARY word's
syndromes always satisfy ``S_2j == S_j^2``, so whenever BM's locator has
``L <= t`` distinct in-range roots the weight-``L`` pattern at those
roots is the unique one consistent with ``S_1..S_2t``; its own Frobenius
image is consistent too, so the pattern equals its image and every error
VALUE squares to itself, i.e. is 1.  A correction that flips exactly
those bits therefore always clears the syndromes: rule 4 is a defensive
clause that no 100-bit input can trip.  Since the branch still EXISTS in
both arms, this sub-population drives it directly — BOTH BM
implementations are replaced by ones that return a fixed, perfectly
legal locator (roots at 3, 17 and 42) for every syndrome, so both arms
walk into the re-check on identical inputs and must still agree.  Two
plants, not one, since the lockstep card: the twin owns its own BM now
and no longer calls ``bch._berlekamp_massey``.  Labelled as what it is:
an injected locator, not a reachable word.

FAULT INJECTION.  ``--fault NAME`` deliberately breaks one arm and the
run must FAIL; that is how a harness earns the right to report a pass.
``--fault list`` names them.  They break the twin (each acceptance rule
in turn), the oracle side (a dropped row), and the comparison itself.

The batched BM's faults are injected differently, and more precisely:
:func:`compile_from_source` recompiles ``bch_batch``'s REAL SOURCE with
one textual substitution and swaps the resulting function in.  So the
broken arm is the shipped code minus exactly one clause — the ``<=`` in
the length-update condition, the zero-operand poison, the snapshot
order, the shift offset — and the run must still fail.  The two-step
card adds four of its own, aimed at the collapse rather than the
recurrence: the skipped step's ``shift`` increment dropped (whole, or
only in the changing branch, or only in the carrying one), and the
doubled stride run one step out of phase so that the arm takes the
steps it is supposed to skip.  ``premise-blind`` is the fifth and is
harness-side: it blinds the ``S_2j == S_j^2`` tripwire, which nothing
in any population violates — so it is caught only by the positive
control, which is exactly why the positive control runs.

``--fault`` also runs the two REDUNDANCY PROBES, which are the same
mechanism pointed the other way: a mutation that is EXPECTED to change
nothing, because the loop's own invariant makes the clause it removes
unreachable.  A probe that bites would mean the invariant is false and
the clause is load-bearing; a probe that does not is the measurement
backing the claim that it is not.  Both outcomes are reported, and
neither is a pass or a fail of the twin.
"""
from __future__ import annotations

import dataclasses
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

# Self-locating, like ``./confetti.py`` and ``refine_equivalence.py``.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE / "verdicts", _ROOT / "src", _ROOT / "holo2" / "src"):
    sys.path.insert(0, str(_path))

from _fixtures import (CHANNEL_ROTATION_DEG, CHANNEL_SCALE_YX,  # noqa: E402
                       build_page, render)

from holo2 import cli  # noqa: E402
from holo2.cli import real_providers  # noqa: E402
from holo2.format import bch, bch_batch  # noqa: E402
from holo2.solve.place_model import PlacementConfig  # noqa: E402

# The two seams carved out 2026-08-17: word/syndrome population builders
# (no knowledge of the twin) and the bch_batch source-recompilation
# machinery (no knowledge of the comparison).  See their own module
# docstrings.
from bch_equivalence_populations import (  # noqa: E402
    RULES, DRIVE_ROOTS, boundary_words, fixed_locator, scalar_rule,
    synthetic_words)
from bch_equivalence_mutation import (  # noqa: E402
    MUTATIONS, PROBE_REASONS, PROBES, general_from_source, install_probe,
    instrumented_general, lockstep_from_source, trim_census)

PX_PER_DOT = 2


# ------------------------------------------------------- the bit comparison

def _row_differences(index: int, word: np.ndarray, oracle: Any,
                     twin: Any) -> list[str]:
    """Everything two answers for ONE input row disagree about."""
    where = f"row[{index}]"
    if oracle is None or twin is None:
        if oracle is None and twin is None:
            return []
        return [f"{where}: verdicts differ — oracle "
                f"{'refused' if oracle is None else 'decoded'}, twin "
                f"{'refused' if twin is None else 'decoded'}"]
    rows: list[str] = []
    left, right = oracle[0], twin[0]
    if left.dtype != right.dtype:
        rows.append(f"{where}.word.dtype: {left.dtype} vs {right.dtype}")
    if left.shape != right.shape:
        rows.append(f"{where}.word.shape: {left.shape} vs {right.shape}")
    elif not np.array_equal(left, right):
        bad = np.flatnonzero(left != right)
        rows.append(f"{where}.word: {bad.size} bits differ, first at "
                    f"{int(bad[0])}")
    if left.shape == word.shape and right.shape == word.shape:
        left_pos = np.flatnonzero(np.asarray(word, np.uint8) ^ left)
        right_pos = np.flatnonzero(np.asarray(word, np.uint8) ^ right)
        if not np.array_equal(left_pos, right_pos):
            rows.append(f"{where}.positions: {left_pos.tolist()} vs "
                        f"{right_pos.tolist()}")
    if oracle[1] != twin[1] or type(oracle[1]) is not type(twin[1]):
        rows.append(f"{where}.errors: {oracle[1]!r} vs {twin[1]!r}")
    return rows


def compare(words: np.ndarray, oracle: list[Any],
            twin: list[Any]) -> list[str]:
    """Bit-compare two whole batches, ORDER included."""
    if len(oracle) != len(twin):
        return [f"batch length {len(oracle)} vs {len(twin)}"]
    rows: list[str] = []
    for index in range(len(oracle)):
        rows += _row_differences(index, words[index], oracle[index],
                                 twin[index])
    return rows


# ------------------------------------------------------ the premise tripwire

#: ``square[v] == v^2`` in GF(2^7), through bch's own tables.
SQUARE = np.zeros(128, np.uint8)
_EXP, _LOG = bch.gf_tables()
for _value in range(1, 128):
    SQUARE[_value] = _EXP[(2 * int(_LOG[_value])) % bch._ORDER]


def frobenius_violations(rows: np.ndarray) -> int:
    """Rows where ``S_2j != S_j^2`` — the batched arm's whole premise.

    ``S_2j`` sits at index ``2j-1`` and ``S_j`` at ``j-1``, so the odd
    columns must be the squares of the first ``T``.  This is EVIDENCE,
    not a gate: production cannot violate it (``decode_many`` validates
    0/1 and computes the syndromes itself), and the arm does not check.
    """
    rows = np.asarray(rows, np.uint8)
    if rows.shape[0] == 0:
        return 0
    return int((rows[:, 1::2] != SQUARE[rows[:, :bch.T]]).any(axis=1).sum())


def run_bm_direct(populations: list[tuple[str, np.ndarray]],
                  divergences: list[str], label: str) -> None:
    """Population (c): the two Berlekamp-Masseys, compared DIRECTLY.

    The comparison is the whole returned triple — the trimmed
    coefficient LIST (not a padded array: the scalar's own
    ``c_poly``), its length, and ``lfsr_len``.  The census that follows
    is read off the SCALAR's answers, never the lockstep's, so it says
    what the population reached and not what the twin thinks it did.

    THE PREMISE IS CHECKED FIRST, on every row of every population: the
    batched arm is only a decoder for syndromes that obey
    ``S_2j == S_j^2``, so a population that quietly stopped obeying it
    would make the comparison meaningless rather than merely failing.
    """
    seen = accepted = over_t = mismatch = zero = extreme = 0
    max_lfsr = max_trim = 0
    print(f"[{label}] scalar vs two-step Berlekamp-Massey, row by row:",
          flush=True)
    for name, rows in populations:
        broken = frobenius_violations(rows)
        if broken:
            divergences.append(
                f"PREMISE[{name}]: {broken} of {rows.shape[0]} rows violate "
                "S_2j == S_j^2 — these are not word syndromes and the "
                "batched arm is not a decoder for them")
        sigma, trimmed, lengths = bch_batch.berlekamp_massey_many(rows)
        local = 0
        for index in range(rows.shape[0]):
            want, want_len = bch._berlekamp_massey(
                [int(value) for value in rows[index]])
            got = sigma[index, :int(trimmed[index])].tolist()
            if got != want or int(lengths[index]) != want_len:
                local += 1
                if local <= 4:
                    divergences.append(
                        f"BM[{name}][{index}]: sigma {want} vs {got}; "
                        f"lfsr_len {want_len} vs {int(lengths[index])}; "
                        f"synd {rows[index].tolist()}")
            seen += 1
            max_lfsr, max_trim = max(max_lfsr, want_len), max(max_trim,
                                                              len(want))
            extreme += len(want) == 2 * bch.T + 1
            zero += not rows[index].any()
            if want_len > bch.T:
                over_t += 1
            elif len(want) - 1 != want_len:
                mismatch += 1
            else:
                accepted += 1
        print(f"  {name}: {rows.shape[0]:,} rows, {local} divergences"
              + (f", {broken} PREMISE VIOLATIONS" if broken else ""),
              flush=True)
    print(f"[{label}] {seen:,} rows; scalar census: accepted shape "
          f"{accepted:,}, refused lfsr_len>T {over_t:,}, refused on the "
          f"TRIM ({mismatch:,}); max lfsr_len {max_lfsr}, max trimmed "
          f"length {max_trim} (width bound {2 * bch.T + 1} reached by "
          f"{extreme}); all-zero syndrome rows {zero}", flush=True)


# ------------------------------------------- (d) the two-step card's evidence

def run_two_step(populations: list[tuple[str, np.ndarray]],
                 divergences: list[str], label: str = "TWO-STEP") -> None:
    """The card's own two claims, measured on the same populations.

    1. THE SKIPPED STEPS ARE EMPTY.  The 26-step recurrence is rebuilt
       from the shipped source (:func:`general_from_source`) with a
       recorder wired into it, so the discrepancies counted are the ones
       the general arm would compute — no second transcription of the
       loop exists to drift.  Every ODD ``step`` must be zero on every
       row; the EVEN ones are reported too, because a halving that
       skipped nothing would be a tautology rather than a saving.
    2. THE COLLAPSE CHANGED NOTHING.  That same 26-step arm is compared
       against the shipped 13-step one on the whole returned triple.
       This is the BUILD-TIME BRIDGE the card was derived through, kept
       here (and only here) after the general arm was deleted from src:
       nothing in production calls it, so it lives where evidence lives.
    """
    general = general_from_source()
    recorded, recorder = instrumented_general()
    odd = even = rows_seen = 0
    print(f"[{label}] the skipped steps, and 13-vs-26 on the triple:",
          flush=True)
    for name, rows in populations:
        recorded.clear()
        recorder(rows)
        steps = np.stack([(block != 0).sum() for block in recorded])
        odd_here = int(steps[1::2].sum())
        odd += odd_here
        even += int(steps[0::2].sum())
        rows_seen += rows.shape[0]
        left, right = general(rows), bch_batch.berlekamp_massey_many(rows)
        differing = np.zeros(rows.shape[0], bool)
        for one, other in zip(left, right):          # sigma, trimmed, lengths
            delta = one != other
            differing |= delta.any(axis=1) if delta.ndim == 2 else delta
        differ = int(differing.sum())
        if odd_here:
            divergences.append(
                f"TWO-STEP[{name}]: {odd_here} nonzero discrepancies at "
                "steps the shipped arm SKIPS — the premise does not hold "
                "on this population")
        if differ:
            first = int(np.argmax(differing))
            divergences.append(
                f"TWO-STEP[{name}]: the 13-step and 26-step arms differ on "
                f"{differ} rows; first at {first}, synd "
                f"{rows[first].tolist()}")
        print(f"  {name}: {rows.shape[0]:,} rows — skipped-step "
              f"discrepancies nonzero {odd_here}, taken-step "
              f"{int(steps[0::2].sum()):,}; 13-vs-26 rows differing {differ}",
              flush=True)
    print(f"[{label}] {rows_seen:,} rows x {bch.T} skipped steps = "
          f"{rows_seen * bch.T:,} discrepancies the shipped arm never "
          f"computes, {odd} of them nonzero; the {bch.T} steps it DOES "
          f"compute were nonzero {even:,} times", flush=True)


def compare_positive_control(divergences: list[str]) -> None:
    """The bit comparison's own teeth, on the four things it claims to see.

    Same reasoning as the premise control below: on a healthy tree every
    population agrees, so a comparison that had quietly stopped comparing
    would look exactly like a pass.  This hands :func:`compare` pairs
    that differ in each way it promises to catch — the verdict, the
    corrected word, the error positions, the count's TYPE — and one pair
    that does not differ at all, and requires it to say so.
    """
    words = np.zeros((2, bch.N_WORD), np.uint8)
    clean = (words[0].copy(), 0)
    other = words[0].copy()
    other[7] = 1
    cases: dict[str, tuple[list[Any], list[Any]]] = {
        "verdict": ([clean, None], [clean, clean]),
        "word and positions": ([clean, clean], [clean, (other, 0)]),
        "count": ([clean, clean], [clean, (words[1].copy(), 1)]),
        "count type": ([clean, clean], [clean, (words[1].copy(), True)]),
    }
    before = len(divergences)
    for label, (left, right) in cases.items():
        if not compare(words, left, right):
            divergences.append(f"COMPARE-CONTROL: a {label} difference went "
                               "UNSEEN — the comparison has no teeth")
    if compare(words, [clean, clean], [clean, clean]):
        divergences.append("COMPARE-CONTROL: identical batches were reported "
                           "as differing")
    print("[compare] positive control: "
          + ("verdict, word, positions, count and count-type differences all "
             "seen; identical batches clean" if len(divergences) == before
             else f"{len(divergences) - before} FAILURES"), flush=True)


def premise_positive_control(divergences: list[str]) -> None:
    """The tripwire's own teeth, proven every run.

    A tripwire that cannot fire is decoration.  This breaks the premise
    on purpose — one even syndrome moved off its square — and the
    tripwire must SEE it.  (It is also what a ``--fault premise-blind``
    run trips over, which is how that fault is caught at all: no
    population violates the premise, so blinding the check is invisible
    everywhere else.)
    """
    rows = bch.syndromes_many(synthetic_words())
    if frobenius_violations(rows):
        divergences.append("PREMISE-CONTROL: the intact population already "
                           "violates S_2j == S_j^2")
    broken = rows.copy()
    broken[0, 1] ^= 1                       # S_2, one bit off its square
    if not frobenius_violations(broken):
        divergences.append("PREMISE-CONTROL: a deliberately broken row went "
                           "UNSEEN — the tripwire has no teeth")
    else:
        print("[premise] tripwire self-test: intact population clean, one "
              "corrupted S_2 caught", flush=True)


def arms(work: Path) -> list[tuple[str, Any, tuple[tuple[Path, float], ...]]]:
    """Five decodes whose windows really fall through to the word route.

    Stage A only runs when the consult comes up empty, so the population
    is driven by pages where placement has to cold-start: a clean page
    (its first windows), the measured e032 channel warp, a banded page
    whose right quarter never places, a damaged ring that drives the
    corner-retry windows, and a wider page that simply lays more windows
    down — the last two exist for the BATCH COUNT, since a page that
    places quickly stops feeding this seam.
    """
    clean = build_page("c3-k-r0550@8x8")
    channel = build_page("c2-k-r0700@8x8")
    wide = build_page("c3-k-r0550@12x12")
    clean_capture = render(clean.dots, work / "clean.png",
                           px_per_dot=PX_PER_DOT, cell_dots=clean.cell_dots,
                           noise_sigma=1.0)
    channel_capture = render(
        channel.dots, work / "channel.png", px_per_dot=PX_PER_DOT,
        cell_dots=channel.cell_dots, rotation_deg=CHANNEL_ROTATION_DEG,
        pitch_scale=CHANNEL_SCALE_YX, noise_sigma=2.0, cell_error_rate=0.02)
    banded = render(channel.dots, work / "banded.png", px_per_dot=PX_PER_DOT,
                    cell_dots=channel.cell_dots, rotation_deg=0.3,
                    pitch_scale=1.003, noise_sigma=2.0,
                    cell_error_rate=0.16, cell_error_band=(0.75, 1.0))
    ringed = render(channel.dots, work / "ringed.png", px_per_dot=PX_PER_DOT,
                    cell_dots=channel.cell_dots, noise_sigma=2.0,
                    rotation_deg=CHANNEL_ROTATION_DEG,
                    pitch_scale=CHANNEL_SCALE_YX,
                    damage_ring_tiles=1, damage_rate=0.5)
    wide_capture = render(wide.dots, work / "wide.png",
                          px_per_dot=PX_PER_DOT, cell_dots=wide.cell_dots,
                          rotation_deg=0.3, pitch_scale=1.003,
                          noise_sigma=2.0, cell_error_rate=0.02)
    return [
        ("clean c3-r0550", clean.row,
         ((clean_capture.path, clean_capture.dpi),)),
        ("e032 channel warp c2-r0700", channel.row,
         ((channel_capture.path, channel_capture.dpi),)),
        ("banded c2-r0700", channel.row, ((banded.path, banded.dpi),)),
        ("damaged-ring c2-r0700", channel.row,
         ((ringed.path, ringed.dpi),)),
        ("wide 12x12 c3-r0550", wide.row,
         ((wide_capture.path, wide_capture.dpi),)),
    ]


# ----------------------------------------------------------------- the ledger

class Ledger:
    """What the run saw: batches, rows, shapes, and any divergence at all."""

    def __init__(self) -> None:
        self.batches = 0
        self.rows = 0
        self.decoded = 0
        self.shapes: list[int] = []
        self.divergences: list[str] = []

    def record(self, words: np.ndarray, oracle: list[Any],
               twin: list[Any]) -> None:
        self.batches += 1
        self.rows += len(oracle)
        self.shapes.append(words.shape[0])
        self.decoded += sum(1 for row in oracle if row is not None)
        self.divergences += compare(words, oracle, twin)

    def report(self, label: str) -> str:
        span = (f"{min(self.shapes)}-{max(self.shapes)}"
                if self.shapes else "n/a")
        return (f"{label}: {self.batches} batches, {self.rows:,} rows "
                f"compared bit-for-bit ({self.decoded:,} decoded, "
                f"{self.rows - self.decoded:,} refused); batch H {span}; "
                f"{len(self.divergences)} divergences")


# ---------------------------------------------------------------- the faults

def _fault_twin_drop_shortened(twin: Callable[..., Any]) -> Callable[..., Any]:
    """Rule 3b deleted from the twin: roots in shortened positions accepted."""
    original = bch_batch.decode_many

    def broken(words: np.ndarray) -> list[Any]:
        results = original(words)
        # Re-admit exactly what rule 3b refuses, by hand.
        rows = bch._as_words(words, bch.N_WORD)
        for index, result in enumerate(results):
            if result is not None:
                continue
            syndrome = bch.syndromes(rows[index])
            if not syndrome.any():
                continue
            sigma, lfsr_len = bch._berlekamp_massey(
                [int(s) for s in syndrome])
            if lfsr_len > bch.T or len(sigma) - 1 != lfsr_len:
                continue
            positions = bch._chien_roots(sigma)
            if positions.size != lfsr_len:
                continue
            corrected = rows[index].copy()
            corrected[positions[positions < bch.N_WORD]] ^= 1
            results[index] = (corrected, int(lfsr_len))
        return results

    return broken


FAULTS: dict[str, str] = {
    "twin-clean-count": "the twin reports 1 error on a clean codeword",
    "twin-no-recheck": "the twin skips the final syndrome re-check",
    "twin-no-degree": "the twin drops BM's trimmed-degree clause",
    "twin-shortened": "the twin accepts roots in shortened positions",
    "oracle-drop-row": "the ORACLE side loses its last row",
    "compare-blind": "the comparison itself is made to return nothing",
    "premise-blind": "the S_2j == S_j^2 tripwire is made to see nothing",
    "bm-shift-accounting": "the skipped step's shift increment is dropped",
    "bm-shift-after-change": "…dropped only where the length changed",
    "bm-shift-carried": "…dropped only where it did not",
    "bm-stride-phase": "the two-step path runs the SKIPPED steps instead",
    "bm-strict-change": "the length update takes < where the scalar takes <=",
    "bm-no-zero-poison": "a zero locator coefficient stops being skipped",
    "bm-snapshot-late": "b_poly is captured AFTER the update, not before",
    "bm-shift-offset": "the update lands one coefficient low",
    "bm-discrepancy-ratio": "d/b becomes d*b in the update coefficient",
    "bm-update-every-row": "rows with a ZERO discrepancy get updated too",
}


def install_fault(name: str) -> None:
    """Break one arm on purpose.  A faulted run MUST fail."""
    global compare, frobenius_violations
    twin = bch_batch.decode_many
    oracle = bch.decode_many
    if name in MUTATIONS:
        # The shipped lockstep, minus exactly one clause.
        bch_batch.berlekamp_massey_many = lockstep_from_source(MUTATIONS[name])
    elif name == "premise-blind":
        def unseeing(rows: np.ndarray) -> int:
            return 0
        frobenius_violations = unseeing
    elif name == "twin-clean-count":
        def broken(words: np.ndarray) -> list[Any]:
            return [None if row is None else (row[0], row[1] + 1)
                    for row in twin(words)]
        bch_batch.decode_many = broken
    elif name == "twin-no-recheck":
        def broken(words: np.ndarray) -> list[Any]:
            rows = bch._as_words(words, bch.N_WORD)
            out = twin(words)
            for index, result in enumerate(out):
                if result is not None:
                    continue
                if scalar_rule(rows[index]) == "recheck_failed":
                    syndrome = bch.syndromes(rows[index])
                    sigma, length = bch._berlekamp_massey(
                        [int(s) for s in syndrome])
                    corrected = rows[index].copy()
                    corrected[bch._chien_roots(sigma)] ^= 1
                    out[index] = (corrected, int(length))
            return out
        bch_batch.decode_many = broken
    elif name == "twin-no-degree":
        def broken(words: np.ndarray) -> list[Any]:
            out = twin(words)
            rows = bch._as_words(words, bch.N_WORD)
            for index, result in enumerate(out):
                if result is None and scalar_rule(rows[index]) == "bm_refused":
                    out[index] = (rows[index].copy(), 0)
            return out
        bch_batch.decode_many = broken
    elif name == "twin-shortened":
        bch_batch.decode_many = _fault_twin_drop_shortened(twin)
    elif name == "oracle-drop-row":
        def broken(words: np.ndarray) -> list[Any]:
            return oracle(words)[:-1]
        bch.decode_many = broken
    elif name == "compare-blind":
        def blind(words: np.ndarray, left: list[Any],
                  right: list[Any]) -> list[str]:
            return []
        compare = blind
    else:
        raise SystemExit(f"unknown fault {name!r}; try --fault list")
    print(f"[FAULT] {name}: {FAULTS[name]} — this run MUST fail\n",
          flush=True)


# ----------------------------------------------------------------- the runs

def run_synthetic(ledger: Ledger) -> None:
    """Population (b): the seeded vectors, in one batch and in slices."""
    words = synthetic_words()
    census = {rule: 0 for rule in RULES}
    for row in words:
        census[scalar_rule(row)] += 1
    print(f"[synthetic] {words.shape[0]} vectors; scalar disposal census "
          + ", ".join(f"{rule} {census[rule]}" for rule in RULES), flush=True)
    missing = [rule for rule in RULES if census[rule] == 0]
    if missing == ["recheck_failed"]:
        print("[synthetic] recheck_failed unreached, as expected — no "
              "100-bit word can trip rule 4 (see the module docstring); "
              "the (b2) drive below exercises the branch directly.",
              flush=True)
    elif missing:
        print(f"[synthetic] WARNING: no vector reached {missing}", flush=True)
    # One whole batch, then odd-sized slices: a batched kernel that parts
    # company with a per-row one does it at a block edge, so the sweep
    # walks the block size (4096) rather than asserting past it.
    ledger.record(words, bch.decode_many(words), bch_batch.decode_many(words))
    for size in (1, 2, 3, 7, 63, 64, 65, 127, 128, 200):
        for start in (0, 5):
            block = words[start:start + size]
            if block.shape[0]:
                ledger.record(block, bch.decode_many(block),
                              bch_batch.decode_many(block))
    empty = np.zeros((0, bch.N_WORD), np.uint8)
    ledger.record(empty, bch.decode_many(empty), bch_batch.decode_many(empty))


def run_rule_four_drive(ledger: Ledger) -> None:
    """Population (b2): both arms walked into the final re-check by hand.

    BOTH BM implementations are replaced by ones that return a fixed,
    perfectly legal locator — ``bch._berlekamp_massey`` for the oracle
    and ``bch_batch.berlekamp_massey_many`` for the twin, which since
    the lockstep card owns its own and no longer calls bch's.  Both arms
    then reach rule 4 on identical inputs and must still agree.
    Restored before returning.
    """
    sigma = fixed_locator(DRIVE_ROOTS)
    original = bch._berlekamp_massey
    original_many = bch_batch.berlekamp_massey_many
    words = synthetic_words(seed=815)

    def planted(syndrome: list[int]) -> tuple[list[int], int]:
        return list(sigma), len(sigma) - 1

    def planted_many(
        syndrome_rows: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        height = np.asarray(syndrome_rows).shape[0]
        coefficients = np.zeros((height, bch_batch._BM_WIDTH), np.uint8)
        coefficients[:, :len(sigma)] = np.array(sigma, np.uint8)
        return (coefficients,
                np.full(height, len(sigma), np.int64),
                np.full(height, len(sigma) - 1, np.int64))

    bch._berlekamp_massey = planted
    bch_batch.berlekamp_massey_many = planted_many
    try:
        before = ledger.rows
        ledger.record(words, bch.decode_many(words),
                      bch_batch.decode_many(words))
        rows = ledger.rows - before
    finally:
        bch._berlekamp_massey = original
        bch_batch.berlekamp_massey_many = original_many
    census = {rule: 0 for rule in RULES}
    bch._berlekamp_massey = planted
    try:
        for row in words:
            census[scalar_rule(row)] += 1
    finally:
        bch._berlekamp_massey = original
    print(f"[rule-4 drive] locator roots {DRIVE_ROOTS}, {rows} vectors; "
          "scalar disposal census "
          + ", ".join(f"{rule} {census[rule]}" for rule in RULES), flush=True)
    if census["recheck_failed"] == 0:
        print("[rule-4 drive] WARNING: the drive reached no re-check; the "
              "rule-4 branch is UNPROVEN", flush=True)


#: Real Stage-A syndrome rows kept for the DIRECT BM comparison, and the
#: cap on them.  The whole-arm intercept already runs both decoders on
#: every real row, but the five acceptance rules can mask a BM
#: divergence, so a bounded sample is compared at BM's own boundary too.
REAL_SYNDROME_CAP: int = 8192
_REAL_SYNDROMES: list[np.ndarray] = []

#: THE CALL-GRAPH PIN, uncapped.  There is no routing decision left to
#: observe — one batched arm, and its precondition is a property of its
#: caller — so what gets observed is the consequence: every syndrome row
#: the REAL receiver hands the batched BM, checked against
#: ``S_2j == S_j^2`` as it goes by.  Blocks and rows are counted so that
#: "no violations" can never be a synonym for "nothing arrived".
PREMISE_SEEN: dict[str, int] = {"blocks": 0, "rows": 0, "violations": 0}


def install_intercept(ledger: Ledger) -> None:
    """Make every real Stage-A batch run both arms and compare them."""
    oracle = bch.decode_many
    twin = bch_batch.decode_many

    def both_arms(words: np.ndarray) -> list[Any]:
        left = oracle(words)
        right = twin(words)
        rows = np.asarray(words, np.uint8)
        ledger.record(rows, left, right)
        if rows.shape[0]:
            syndromes = bch._syndromes_many_words(rows)
            dirty = syndromes[syndromes.any(axis=1)]     # what BM is given
            PREMISE_SEEN["blocks"] += 1
            PREMISE_SEEN["rows"] += int(dirty.shape[0])
            PREMISE_SEEN["violations"] += frobenius_violations(dirty)
            kept = sum(block.shape[0] for block in _REAL_SYNDROMES)
            if kept < REAL_SYNDROME_CAP:
                _REAL_SYNDROMES.append(dirty[:REAL_SYNDROME_CAP - kept])
        # The decode proceeds on the ORACLE, always.
        return left

    bch.decode_many = both_arms


def force_oracle_arm() -> None:
    """Make the intercepted decode run on the ORACLE, whatever the default.

    ``PlacementConfig.batched_word_sweep`` DEFAULTS ON since the user's
    2026-08-17 ruling, which routes the real sweep straight into the
    twin — past the ``bch.decode_many`` seam this harness hooks.  The
    intercepted population would then be empty (measured: a clean
    ``c3-r0550`` decode makes 4 twin calls and 0 oracle calls), and
    while the emptiness guard in :func:`main` catches that loudly, an
    empty population proves nothing.  Every ``PlacementConfig`` field
    has a default, so the generated ``__init__``'s ``__defaults__``
    lines up one-for-one with ``fields()`` and rewriting the one entry
    turns it back off for every bare ``PlacementConfig()`` in the tree —
    driver-side, the same trick ``H4-measurements/drivers/run_decode_sweep.py``
    uses in the other direction, and src grows no hatch for it.

    The twin still runs on every batch the decode produces.  What this
    restores is that it does not STEER them: the population is the
    oracle's own trajectory, which is the only version of it that a
    twin bug cannot quietly reshape.
    """
    names = [field.name for field in dataclasses.fields(PlacementConfig)]
    defaults = list(PlacementConfig.__init__.__defaults__ or ())
    if len(defaults) != len(names):
        raise SystemExit("PlacementConfig has a field without a default; "
                         "the arm can no longer be forced from here")
    defaults[names.index("batched_word_sweep")] = False
    PlacementConfig.__init__.__defaults__ = tuple(defaults)
    if PlacementConfig().batched_word_sweep is not False:
        raise SystemExit("forcing the oracle arm did not take")


def run_intercepted(ledger: Ledger) -> None:
    """Population (a): real decodes, hooked at the Stage-A decode seam."""
    force_oracle_arm()
    install_intercept(ledger)
    with tempfile.TemporaryDirectory(prefix="bch-equiv-") as raw:
        work = Path(raw)
        for index, (name, row, scans) in enumerate(arms(work)):
            started, before = time.perf_counter(), ledger.batches
            cli.decode(
                cli.DecodeRequest(
                    scans=scans, workers=1, diag_port=0,
                    state_dir=work / f"state-{index}",
                    output=work / f"recovered-{index}.bin", complete=True),
                row, real_providers(row, scans), fsync=False, snapshot_every=32)
            print(f"  {name}: {ledger.batches - before} Stage-A batches, "
                  f"{time.perf_counter() - started:.1f} s", flush=True)


def main(argv: list[str]) -> int:
    fault = probe = None
    if len(argv) >= 2 and argv[0] == "--fault":
        name = argv[1]
        if name == "list":
            for label, what in FAULTS.items():
                print(f"  {label:22} {what}")
            print("  --- redundancy probes (expected NOT to bite) ---")
            for label, why in PROBE_REASONS.items():
                print(f"  {label:22} {why}")
            return 0
        if name in PROBES:
            probe = name
            install_probe(name)
        else:
            fault = name
            install_fault(name)

    # The two positive controls FIRST: on a healthy tree everything
    # agrees, so a detector that had stopped detecting would read as a
    # pass.  Each of these breaks something on purpose and requires the
    # detector to see it.
    bm_divergences: list[str] = []
    compare_positive_control(bm_divergences)
    premise_positive_control(bm_divergences)

    synthetic = Ledger()
    run_synthetic(synthetic)
    run_rule_four_drive(synthetic)
    print(synthetic.report("SYNTHETIC"), flush=True)

    populations = boundary_words()
    run_bm_direct(populations, bm_divergences, "BM")
    run_two_step(populations, bm_divergences)
    popped, total = trim_census(populations)
    print(f"[BM] the trailing-zero TRIM pops on {popped:,} of {total:,} "
          "rows (measured by re-running the arm from source with the "
          "trim removed) — a locator the trim did not shorten proves "
          "nothing about it", flush=True)

    intercepted = Ledger()
    run_intercepted(intercepted)
    print(intercepted.report("INTERCEPTED"), flush=True)
    print(f"[premise] the real decodes handed the batched BM "
          f"{PREMISE_SEEN['blocks']} blocks / {PREMISE_SEEN['rows']:,} "
          f"nonzero-syndrome rows; rows violating S_2j == S_j^2: "
          f"{PREMISE_SEEN['violations']}", flush=True)
    if PREMISE_SEEN["violations"]:
        bm_divergences.append(
            f"PREMISE[real]: {PREMISE_SEEN['violations']} rows reached the "
            "batched BM from a real decode without obeying S_2j == S_j^2")
    if _REAL_SYNDROMES:
        real = [("real Stage-A syndrome rows",
                 np.concatenate(_REAL_SYNDROMES))]
        run_bm_direct(real, bm_divergences, "BM-REAL")
        run_two_step(real, bm_divergences, "TWO-STEP-REAL")

    divergences = (synthetic.divergences + bm_divergences
                   + intercepted.divergences)
    if divergences:
        if probe:
            print(f"\nPROBE {probe!r} BIT — the clause it removed is "
                  "LOAD-BEARING and the invariant behind it is false:")
        else:
            print(f"\nFAULT {fault!r} DETECTED — the harness bites:" if fault
                  else "\nDIVERGENCE — the twin is NOT bit-identical:")
        for line in divergences[:12]:
            print(f"  {line}")
        print(f"\n({len(divergences)} in total)")
        return 0 if fault else 1
    if not intercepted.batches or not synthetic.batches:
        print("NOTHING COMPARED — a population was empty; the harness "
              "proved nothing. Check the fixtures.")
        return 1
    if fault:
        print(f"\nFAULT {fault!r} WENT UNDETECTED — the harness is blind.")
        return 1
    if probe:
        print(f"\nPROBE {probe!r} changed nothing, on every row of every "
              f"population — {PROBE_REASONS[probe]} is REDUNDANT here, for "
              "the reason claimed and measured rather than argued.")
        return 0
    print("BIT-IDENTICAL on every compared row of all three populations; "
          "the premise held on every row that reached the batched BM, and "
          "the 13-step arm answered what the 26-step one would have.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
