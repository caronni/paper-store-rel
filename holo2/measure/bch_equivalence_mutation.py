"""Source-level reconstruction of ``bch_batch``'s Berlekamp-Massey.

Carved out of ``bch_equivalence.py`` (seam identified 2026-08-17, split
per the user's "if it makes sense" ruling): the machinery that recompiles
``bch_batch``'s REAL source text with named one-clause substitutions
(:func:`compile_from_source`, :func:`lockstep_from_source`) rather than
hand-writing an imitation that could drift from the shipped code by
accident.  Three things are built from it: the named FAULTS and PROBES
(:data:`MUTATIONS`, :data:`PROBES`, :data:`PROBE_REASONS`,
:func:`install_probe` — the fault installer stays in ``bch_equivalence.py``
because it also rebinds that module's own ``compare``/``frobenius_violations``
globals, which only works co-resident with their definitions); the
pre-two-step 26-step general recurrence the shipped 13-step arm was
derived from, kept here as a development bridge rather than as resident
dead code in src (:data:`GENERAL`, :data:`RECORDER`,
:func:`general_from_source`, :func:`instrumented_general`); and the
trailing-zero trim census built by running the shipped arm from source
twice, with and without its trim (:func:`trim_census`).  Depends only on
``holo2.format.bch_batch`` — the shipped module whose text it reads and
recompiles.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np

from holo2.format import bch_batch

# ------------------------------------------------- mutating the shipped code

#: One-line mutations of ``bch_batch``'s REAL source, by name.  The
#: faults MUST bite; the probes are expected NOT to (see the module
#: docstring), and either outcome is a measurement.
MUTATIONS: dict[str, tuple[str, str]] = {
    "bm-shift-accounting": (
        "np.where(change, np.int16(2), shift + 2)",
        "np.where(change, np.int16(1), shift + 1)"),
    "bm-shift-after-change": (
        "np.where(change, np.int16(2), shift + 2)",
        "np.where(change, np.int16(1), shift + 2)"),
    "bm-shift-carried": (
        "np.int16(2), shift + 2)",
        "np.int16(2), shift + 1)"),
    "bm-stride-phase": (
        "for step in range(0, 2 * bch.T, 2)",
        "for step in range(1, 2 * bch.T, 2)"),
    "bm-strict-change": (
        "change = nonzero & (2 * lfsr_len <= step)",
        "change = nonzero & (2 * lfsr_len < step)"),
    "bm-no-zero-poison": (
        "index = _LOGZ[sigma[:, 1:step + 1]] + synd_log[:, step - 1::-1]",
        "index = _LOG16[sigma[:, 1:step + 1]] + synd_log[:, step - 1::-1]"),
    "bm-snapshot-late": (
        "            previous, previous_len = sigma.copy(), sigma_len.copy()\n"
        "            sigma ^= _EXPZ[scale[:, None] + _LOGZ[taken]]",
        "            sigma ^= _EXPZ[scale[:, None] + _LOGZ[taken]]\n"
        "            previous, previous_len = sigma.copy(), sigma_len.copy()"),
    "bm-shift-offset": (
        "taken = auxiliary[lane, padded[None, :] - shift[:, None]]",
        "taken = auxiliary[lane, padded[None, :] - shift[:, None] + 1]"),
    "bm-discrepancy-ratio": (
        "(_LOGZ[discrepancy] - _LOGZ[b_disc]) % bch._ORDER,",
        "(_LOGZ[discrepancy] + _LOGZ[b_disc]) % bch._ORDER,"),
    "bm-update-every-row": (
        "            scale = np.where(\n"
        "                nonzero,\n"
        "                (_LOGZ[discrepancy] - _LOGZ[b_disc]) % bch._ORDER,\n"
        "                _POISON).astype(np.int16)",
        "            scale = (((_LOGZ[discrepancy] - _LOGZ[b_disc])\n"
        "                      % bch._ORDER).astype(np.int16))"),
}

#: Mutations that should change NOTHING, and why.  The first two: the
#: discrepancy's tap bound ``min(lfsr_len, len(c_poly) - 1)`` cannot
#: bind.  Coefficients at or past ``len(c_poly)`` are zero, so
#: ``taps != 0`` already implies ``i <= len(c_poly) - 1``, and the loop
#: invariant (``_BM_WIDTH``'s docstring) puts ``len(c_poly) - 1 <=
#: lfsr_len``.  The clause is kept in the shipped code because the
#: SCALAR's arithmetic is what is being reproduced; these say what it
#: costs to be sure — nothing.
#:
#: ``bm-no-trim`` was a FAULT until this card and is now a probe, and the
#: demotion is a measurement rather than a convenience.  The trailing-zero
#: trim can only shorten a row that rule 2 then REFUSES: a pop puts
#: ``trimmed - 1`` strictly below ``len(c_poly) - 1``, which the loop
#: invariant already holds at or below ``lfsr_len``, so ``trimmed - 1 !=
#: lfsr_len`` — the refusal clause exactly.  And no 100-bit word reaches
#: that refusal (measured: 0 in a 1 M-word sweep, and 0 in 0.5 M bare
#: rows of the larger space the premise alone allows; the unconstrained
#: syndrome rows that reached it 320 times are no longer a legal input to
#: this arm at all, see population (c)).  So on the reachable domain the
#: trimmed length and the tracked list length are the same number, and
#: replacing
#: one by the other changes nothing.  The clause stays in the shipped
#: code because the scalar has it; what this probe reports is the price
#: of that honesty, which is again nothing.
PROBES: dict[str, tuple[str, str]] = {
    "bm-no-trim": (
        "    trimmed = _BM_WIDTH - np.argmax(live[:, ::-1], axis=1)",
        "    trimmed = sigma_len.astype(np.int64)"),
    "bm-drop-bound-mask": (
        "            index = np.where(\n"
        "                column[1:step + 1] <= np.minimum(lfsr_len,\n"
        "                                                 sigma_len - 1)"
        "[:, None],\n"
        "                index, np.int16(_POISON))",
        "            pass  # the tap bound, removed (redundancy probe)"),
    "bm-bound-lfsr-only": (
        "                column[1:step + 1] <= np.minimum(lfsr_len,\n"
        "                                                 sigma_len - 1)"
        "[:, None],",
        "                column[1:step + 1] <= lfsr_len[:, None],"),
}

#: Why each probe is expected to change nothing — different reasons, and
#: the difference is the finding: the tap-bound pair is unreachable by
#: the loop's own INVARIANT, the trim by the reachable DOMAIN.
PROBE_REASONS: dict[str, str] = {
    "bm-no-trim": "the trim, which no reachable row makes pop",
    "bm-drop-bound-mask": "the tap bound, which the invariant makes redundant",
    "bm-bound-lfsr-only": "half of that bound, same reason",
}


def compile_from_source(pairs: tuple[tuple[str, str], ...],
                        extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """``bch_batch``'s own source, recompiled with N substitutions.

    This is why a lockstep fault means something: the broken arm is the
    SHIPPED code minus exactly one clause, not a hand-written imitation
    of it that could differ in a second place by accident.  The count
    check refuses a mutation that has drifted off its site — a fault
    that silently stopped applying would be worse than no fault at all.
    """
    source = Path(bch_batch.__file__).read_text()
    for found, replacement in pairs:
        if source.count(found) != 1:
            raise SystemExit(f"mutation site matched {source.count(found)} "
                             f"times, not 1:\n{found}")
        source = source.replace(found, replacement)
    if source.count("from . import bch") != 1:
        raise SystemExit("bch_batch's relative import moved; the mutant "
                         "cannot bind bch")
    source = source.replace("from . import bch", "from holo2.format import bch")
    namespace: dict[str, Any] = {"__name__": "bch_batch_mutant",
                                 **(extra or {})}
    exec(compile(source, "<bch_batch mutant>", "exec"), namespace)
    return namespace


def lockstep_from_source(*pairs: tuple[str, str]) -> Callable[..., Any]:
    """The shipped two-step arm, optionally minus one clause."""
    return compile_from_source(pairs)[  # type: ignore[no-any-return]
        "berlekamp_massey_many"]


#: The substitutions that turn the shipped 13-step recurrence back into
#: the general 26-step one.  THE DEVELOPMENT BRIDGE: the two-step arm was
#: derived from the 26-step lockstep, so the derivation is checked
#: against it — but nothing in production would call a general batched
#: arm (``decode_many`` is binary by construction and the config switch
#: falls back to the SCALAR), so it is not kept in src as resident dead
#: code.  It is kept HERE, as two substitutions of the shipped source,
#: which is both smaller and harder to let drift.
GENERAL: tuple[tuple[str, str], ...] = (
    ("for step in range(0, 2 * bch.T, 2)",
     "for step in range(0, 2 * bch.T, 1)"),
    ("np.where(change, np.int16(2), shift + 2)",
     "np.where(change, np.int16(1), shift + 1)"),
)

#: One more substitution, on top of :data:`GENERAL`: record every step's
#: whole discrepancy vector into a list the caller owns.  It is how the
#: card's headline number is measured without a second copy of the loop
#: existing anywhere — the arm that computes those discrepancies IS the
#: shipped source, differing only in stride.
RECORDER: tuple[str, str] = (
    "        nonzero = discrepancy != 0",
    "        _RECORD.append(discrepancy.copy())\n"
    "        nonzero = discrepancy != 0")


def general_from_source() -> Callable[..., Any]:
    """The 26-step general recurrence, rebuilt from the shipped source."""
    return compile_from_source(GENERAL)[  # type: ignore[no-any-return]
        "berlekamp_massey_many"]


def instrumented_general() -> tuple[list[np.ndarray], Callable[..., Any]]:
    """``general_from_source`` plus the per-step discrepancy recorder."""
    recorded: list[np.ndarray] = []
    namespace = compile_from_source(GENERAL + (RECORDER,),
                                    {"_RECORD": recorded})
    return recorded, namespace["berlekamp_massey_many"]


def trim_census(populations: list[tuple[str, np.ndarray]]) -> tuple[int, int]:
    """How often the scalar's trailing-zero pop actually POPS.

    Measured, not asserted: the shipped arm is run twice from source,
    once as shipped and once with its trim replaced by the untrimmed
    length (the ``bm-no-trim`` probe), and the rows whose length differs
    are exactly the rows the scalar's ``while ... pop()`` shortened.
    Both sides come from source, so an installed ``--fault`` cannot
    colour this number.  On word syndromes the answer is 0 — see the
    PROBES table for why that is the reachable domain's own shape and
    not a gap in the population.
    """
    shipped = lockstep_from_source()
    untrimmed = lockstep_from_source(PROBES["bm-no-trim"])
    popped = total = 0
    for _name, rows in populations:
        popped += int((untrimmed(rows)[1] != shipped(rows)[1]).sum())
        total += rows.shape[0]
    return popped, total


def install_probe(name: str) -> None:
    """Remove a clause that should not matter.  A probed run MUST pass."""
    bch_batch.berlekamp_massey_many = lockstep_from_source(PROBES[name])
    print(f"[PROBE] {name}: a mutation expected to change NOTHING — this "
          "run must still be bit-identical; if it is not, the loop "
          "invariant is false and the clause is load-bearing.\n", flush=True)
