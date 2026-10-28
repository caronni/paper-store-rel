"""Lane-W address words: multi-slot Stage A over one observation window.

Cold Stage A is the result-exact batched form of the historical E022
shortcut, widened to the complete slot grid: for each orientation it sweeps
every full 64-cell slot of the patch (row-major slot order), BCH-decodes the
hard samples at every fitting phase of every slot, then keeps candidates with
at least :data:`STAGE_A_MIN_VISIBLE_SITES` visible word sites.  Candidates are
returned in one global errors-first trial order across every slot and
orientation (ties break by oriented row-major slot index, then ``rot_k``, then
row-major phase).  Visibility does not turn hidden samples into erasures at
this cold-search rung; the independent pilot-parity gates remain the authority
for accepting a decoded seed.

Word trust is one-way: a certified word may seed or label geometry, while a
failure/conflict is reported and never invalidates an independently accepted
Lane-C placement.

**The word decoder's two arms** (H4 W2-EXIT parallelism line: the batched
Chien card, then the lockstep BM card).  One call in this module —
:func:`_decode_candidates`'s
``decode_many`` over a slot's phases — measured ~72% of ALL receiver CPU
(the GIL diagnosis), because this sweep runs it 147,456 times per 200-cell
window.  It has TWO implementations of ONE arithmetic, chosen by the
``batched_sweep`` argument that
:attr:`~holo2.solve.place_model.PlacementConfig.batched_word_sweep`
sources: :func:`~holo2.format.bch.decode_many` (the carried scalar path,
this function's default, and THE ORACLE) and
:func:`~holo2.format.bch_batch.decode_many` (the twin, which batches BOTH
of the per-candidate loops — Berlekamp-Massey and the Chien search —
across the whole candidate block).  They are bit-identical by
construction — see ``format/bch_batch.py``'s docstring for the five
acceptance rules it reads off the scalar code — and the population
evidence is ``holo2/measure/bch_equivalence.py``, which is NOT a
collected test and is run by path.  The switch reaches nothing else: the
gates, the visibility floor and the global sort below are the same code
under either arm, which is the point.

Ported from ``src/holo/receive/words.py`` at ``594a465`` — W0 sub-wave A2
(H4-PLAN §3-W0) — under R4: the code is refactored along holo2's own seams,
the ARITHMETIC is untouched, and the pin is BEHAVIOURAL
(``holo2/tests/solve/test_words_kernel.py`` plus W0-B's cross-tree
differential, which drives the same bits/masks through both trees and
compares candidates in content AND order).  Nothing imports this module yet.

**Arithmetic deliberately NOT touched**: the slot grid's
``(extent - 64) // 64 + 1`` count and the uniform per-slot phase capacity
``min(64, H-63) * min(64, W-63)`` that deliberately OVER-declares the trailing
row/column (:class:`~holo2.solve.place_model.WordAttemptBudget` only requires
the declaration to dominate the attempts); :func:`_centre_slot`'s float
``height / 2`` centre distance and its ``slot`` secondary key; the gather's
``base + phase[:, None] + positions[None, :, axis]`` broadcast and its
row-major ``repeat``/``tile`` origin enumeration; the three gates in
:func:`_word_candidate` and their ORDER (five-zero pads, page domain, decode
radius); the sort key ``(errors, slot_index, rot_k, phase_index)``; the
visibility floor as a strict ``< 90`` on the per-phase count; and
``StageAResult.reason``'s three strings, which are audit data.

**R4 freedoms exercised (code only)**:

* v1's inline three-clause ``isinstance(..., (int, np.integer))`` shape
  validation is :func:`_is_cell_count` + :func:`_stage_shape`, which also
  normalises the pair to python ints once instead of threading a raw
  ``ndarray.shape`` through four helpers.  Its explicit ``np.bool_`` arm went
  for the reason A1 recorded in ``place_model``: ``np.bool_`` is an instance
  of neither ``int`` nor ``np.integer``, so the second clause already refuses
  it (same ``ValueError``, same message).
* ``_gather_slot``'s four-tuple return is the named :class:`_SlotGather`.
* the per-phase gate chain moved out of the triple loop into
  :func:`_word_candidate`, which returns the candidate or ``None``; the
  origin pair is built before the gates instead of after (pure integer
  arithmetic either way, no observable difference).
* the ``slots`` stage is the :data:`SlotStage` literal alias, still validated
  at runtime because the value reaches here from provider data.
* the bare literal ``90`` is the named :data:`STAGE_A_MIN_VISIBLE_SITES`,
  now landed as an ``OR9_FLOORS`` row (``stage_a_min_visible_sites``) that
  this module reads via
  :func:`~holo2.solve.place_model.admission_datum` — W0-B.
* the ``AddressPatchLike`` structural seam is gone; :func:`stage_a_patch`
  takes :class:`~holo2.solve.pose_fit.AddressPatch` directly — W0-B.

**TileFormat adaptation** (v1 took ``format.descriptor.FormatSpec``; holo2's
spec surface is ``format.format_v1.TileFormat``).  Stage A reads five members
and each is present with identical semantics: ``family_seed`` (the site
lattice's seed — both spell it ``holo/v1/sites/p{n_sites}``, in BOTH
identity namespaces; the asymmetry is deliberate and frozen,
FORMAT-SPACE P10), ``seed`` (the row keystream seed, which branches on
the coding's namespace on both sides since WP-1.2: a legacy row spells
it ``holo/v1/{coding_id}/{cells_y}x{cells_x}`` and a v2 row spells it
``holo/v2/{coding_id}@{tiles_y}x{tiles_x}`` — CELLS there, TILES here,
which is the second collision defence beside the differing prefix.
Stage A reads the bytes and never the spelling, so the branch is
invisible from here), ``plane`` (an ``int`` field defaulting to the K
plane on both),
``tile_address`` (the same ``divmod`` inverse of the flat counter, raising
outside ``0..2**18-1`` — a range Stage A cannot leave, since the counter comes
from an 18-bit message field), and ``max_pages`` (the same
``max_tiles_addressable // tiles_per_page`` floor).  The one shape difference
is upstream and invisible here: v1 DERIVES its tile grid from media and margin,
holo2 takes it as data — so the grid a decode names is the caller's, and this
module never asks how it was chosen.

**NOT PORTED** (deliberate, per H4-PLAN §3-W0 and A1's ``place_model``
docstring):

* ``known_position_words`` LANDED IN W5 (below), with R7(b)'s fix riding
  with it and its consumer beside it (``solve/contradiction.py``).  The
  deferral note that stood here is spent.
* :class:`~holo2.solve.place_model.WordAttemptBudget` — the union-bound
  declaration is a BUDGET, so A1 gave it a home in ``place_model`` (its
  declared deviation) and this module imports it.  The complementary half
  stays here: :func:`stage_a_hypotheses` is word-grid GEOMETRY (the slot grid
  is the decoder's), and it reaches the admission policy as an ``int``
  argument, never as a caller-supplied function.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

import numpy as np

from ..core import ResourceKey
from ..format import TileFormat, bch, bch_batch, pilots
from .place_model import (CellYX, KnownWord, PilotObservation,
                          WordAttemptBudget, admission_datum)
from .pose_fit import AddressPatch

#: Which slots of the patch one Stage-A spend sweeps (v0.26's staging).
SlotStage: TypeAlias = Literal["all", "centre", "rest"]

# Annotated as a plain string tuple on purpose: the membership check below
# is a RUNTIME gate on provider data, not a type-checker narrowing.
_SLOT_STAGES: tuple[str, ...] = ("all", "centre", "rest")


def _carried_int(name: str) -> int:
    """One carried OR-9 row as an int (mirrors ``pose_fit._carried_int``)."""
    datum = admission_datum(name)
    if datum.origin != "carried" or not isinstance(datum.value, int):
        raise TypeError(f"admission datum {name!r} is not a carried integer")
    return int(datum.value)


STAGE_A_MIN_VISIBLE_SITES = _carried_int("stage_a_min_visible_sites")
"""Per-phase visibility floor on the 100 word sites (v1 ``words.py:245``).

The historical ``try_bch_seed`` decoded the hard samples first and applied
only this floor to the surviving candidate — it is a per-phase protection,
not the window-wide mask gate PLACEMENT-IMPROVEMENTS 3.2 removed.
"""


@dataclass(frozen=True, slots=True)
class DecodedWordCandidate:
    """One legal word read: where it sat, what it said, how hard it was."""

    oriented_origin_yx: CellYX
    rot_k: int
    counter: int
    page: int
    tile_yx: CellYX
    errors: int
    page_origin_yx: CellYX


@dataclass(frozen=True, slots=True)
class StageAResult:
    """The stage's candidates, its DECLARED domain, and why it stopped."""

    candidates: tuple[DecodedWordCandidate, ...]
    hypotheses: int
    reason: str


# ------------------------------------------------------------- slot geometry

def _is_cell_count(value: object) -> bool:
    """v1's rule: a nonnegative int or numpy integer — never a bool."""
    return (not isinstance(value, bool)
            and isinstance(value, (int, np.integer))
            and int(value) >= 0)


def _stage_shape(shape: tuple[int, ...]) -> CellYX:
    """Validate an oriented patch shape and normalise it to python ints."""
    values = tuple(shape)
    if len(values) != 2 or not all(_is_cell_count(v) for v in values):
        raise ValueError("Stage-A shape must contain two nonnegative integers")
    return (int(values[0]), int(values[1]))


def _slot_grid(shape: CellYX) -> tuple[CellYX, ...]:
    """Every full 64-cell slot of the patch, in row-major slot order."""
    height, width = shape
    period = pilots.TILE_CELLS
    if height < period or width < period:
        return ()
    return tuple(
        (row, col)
        for row in range((height - period) // period + 1)
        for col in range((width - period) // period + 1)
    )


def _slot_phase_capacity(shape: CellYX) -> int:
    """Declared per-slot phase count: the base slot's fitting-phase room.

    Every full slot is declared at this uniform single-slot capacity
    ``min(64, H-63) * min(64, W-63)``.  Trailing slots physically admit fewer
    fitting phases, so the declared Stage-A domain is a conservative ceiling
    on decode attempts; see
    :class:`~holo2.solve.place_model.WordAttemptBudget`.
    """
    height, width = shape
    period = pilots.TILE_CELLS
    if height < period or width < period:
        return 0
    return min(period, height - period + 1) * min(period, width - period + 1)


def _centre_slot(shape: CellYX) -> CellYX | None:
    """The historical selected slot: nearest the oriented patch centre."""
    grid = _slot_grid(shape)
    if not grid:
        return None
    period = pilots.TILE_CELLS
    height, width = shape
    return min(
        grid,
        key=lambda slot: (
            abs(slot[0] * period + period - height / 2)
            + abs(slot[1] * period + period - width / 2),
            slot,
        ),
    )


def _slot_phase_shape(shape: CellYX, slot: CellYX) -> CellYX:
    """The phases one slot PHYSICALLY admits (<= the declared capacity)."""
    height, width = shape
    period = pilots.TILE_CELLS
    base_y, base_x = slot[0] * period, slot[1] * period
    return (min(period, height - base_y - period + 1),
            min(period, width - base_x - period + 1))


def stage_a_hypotheses(shape: tuple[int, ...]) -> int:
    """Sum over every full slot of its declared phase domain, four rot90s.

    A 200x200 window declares 9 slots x 64x64 phases x 4 orientations =
    147,456; a 70x70 window declares its single slot's 7x7 fitting phases x 4
    = 196.  The per-slot declaration is the uniform base-slot capacity
    (:func:`_slot_phase_capacity`), an exact count for every slot except the
    trailing row/column, where it conservatively over-declares.
    """
    oriented = _stage_shape(shape)
    total = 0
    for rot_k in range(4):
        shape_k = oriented if rot_k % 2 == 0 else (oriented[1], oriented[0])
        total += len(_slot_grid(shape_k)) * _slot_phase_capacity(shape_k)
    return total


# ------------------------------------------------------------- the sweep

@dataclass(frozen=True, slots=True)
class _SlotGather:
    """One slot's phases, gathered: (n_phases, 100) samples plus origins."""

    words: np.ndarray
    visible: np.ndarray
    origins_y: np.ndarray
    origins_x: np.ndarray


def _gather_slot(
    grid: np.ndarray,
    mask: np.ndarray,
    shape: CellYX,
    slot: CellYX,
    positions: np.ndarray,
) -> _SlotGather | None:
    """Gather all phases in one disjoint slot, following old Stage A."""
    period = pilots.TILE_CELLS
    base_y, base_x = slot[0] * period, slot[1] * period
    row_limit, col_limit = _slot_phase_shape(shape, slot)
    if row_limit <= 0 or col_limit <= 0:
        return None
    phase_y = np.arange(row_limit)
    phase_x = np.arange(col_limit)
    iy = base_y + phase_y[:, None] + positions[None, :, 0]
    ix = base_x + phase_x[:, None] + positions[None, :, 1]
    values = grid[iy[:, None, :], ix[None, :, :]]
    visible = mask[iy[:, None, :], ix[None, :, :]]
    return _SlotGather(
        values.reshape(-1, positions.shape[0]),
        visible.reshape(-1, positions.shape[0]),
        base_y + np.repeat(phase_y, col_limit),
        base_x + np.tile(phase_x, row_limit),
    )


def _word_candidate(
    corrected: np.ndarray,
    errors: int,
    spec: TileFormat,
    rot_k: int,
    origin: CellYX,
) -> DecodedWordCandidate | None:
    """Apply the three legality gates to one decoded word, in v1's order."""
    message = bch.message_from_word(corrected)
    if message[pilots.COUNTER_BITS:].any():
        return None                      # authoritative five-zero-pad gate
    counter = 0
    for bit in message[:pilots.COUNTER_BITS]:
        counter = (counter << 1) | int(bit)
    page, tile_y, tile_x = spec.tile_address(counter)
    if page >= spec.max_pages:
        return None
    # BCH's correction count is exactly the printed-word Hamming distance:
    # XOR by the fixed scramble preserves distance and the accepted
    # zero-pad message re-encodes to ``corrected``.
    errors = int(errors)
    if errors > bch.T:
        return None
    page_origin = (tile_y * pilots.TILE_CELLS - origin[0],
                   tile_x * pilots.TILE_CELLS - origin[1])
    return DecodedWordCandidate(
        origin, rot_k, int(counter), int(page),
        (int(tile_y), int(tile_x)), errors, page_origin,
    )


def _decode_candidates(
    bits: np.ndarray,
    mask: np.ndarray,
    spec: TileFormat,
    slots: SlotStage = "all",
    batched_sweep: bool = False,
) -> tuple[DecodedWordCandidate, ...]:
    """Sweep every requested slot of every orientation, errors-first."""
    if slots not in _SLOT_STAGES:
        raise ValueError("Stage-A slot stage must be all, centre, or rest")
    decode_many = bch_batch.decode_many if batched_sweep else bch.decode_many
    positions = pilots.word_site_cells_yx(spec.family_seed)
    scramble = pilots.value_scramble_bits(spec.seed, spec.plane)
    keyed: list[tuple[tuple[int, int, int, int], DecodedWordCandidate]] = []
    for rot_k in range(4):
        oriented_bits = np.rot90(np.asarray(bits, np.uint8), rot_k)
        oriented_mask = np.rot90(np.asarray(mask, bool), rot_k)
        shape = _stage_shape(oriented_bits.shape)
        centre = _centre_slot(shape)
        for slot_index, slot in enumerate(_slot_grid(shape)):
            if slots == "centre" and slot != centre:
                continue
            if slots == "rest" and slot == centre:
                continue
            gathered = _gather_slot(
                oriented_bits, oriented_mask, shape, slot, positions)
            if gathered is None:
                continue
            decoded = decode_many(gathered.words ^ scramble)
            for phase_index, result in enumerate(decoded):
                # Historical try_bch_seed decoded the hard samples first and
                # applied only this per-phase visibility floor to the
                # surviving candidate.
                visible = int(np.count_nonzero(gathered.visible[phase_index]))
                if result is None or visible < STAGE_A_MIN_VISIBLE_SITES:
                    continue
                origin = (int(gathered.origins_y[phase_index]),
                          int(gathered.origins_x[phase_index]))
                candidate = _word_candidate(
                    result[0], result[1], spec, rot_k, origin)
                if candidate is None:
                    continue
                keyed.append((
                    (candidate.errors, slot_index, rot_k, phase_index),
                    candidate,
                ))
    # Global errors-first trial order: a clean rot1 seed precedes a 13-error
    # rot0 seed.  Equal-error ties break deterministically by oriented
    # row-major slot index, then rot_k, then the slot's row-major phase
    # enumeration.
    keyed.sort(key=lambda row: row[0])
    return tuple(candidate for _key, candidate in keyed)


def stage_a(
    bits: np.ndarray,
    mask: np.ndarray,
    spec: TileFormat,
    budget: WordAttemptBudget,
    *,
    slots: SlotStage = "all",
    batched_sweep: bool = False,
) -> StageAResult:
    """Return legal single-word candidates, errors-first within the stage.

    ``slots`` selects the v0.26 staged sweep: ``"centre"`` decodes only the
    historical most-interior slot per orientation, ``"rest"`` the remaining
    slots, ``"all"`` everything.  The declared domain (and the budget
    refusal) is always the full multi-slot ceiling — the union bound only
    requires the declaration to dominate the attempts actually made, so a
    stage that decodes fewer slots under the same declaration is
    conservative.

    ``batched_sweep`` picks the word decoder's ARM and nothing else (see
    the module docstring's two-arms note): the two are bit-identical, so
    this argument may not change a single candidate, its errors, or its
    place in the trial order.  Production sources it from
    :attr:`~holo2.solve.place_model.PlacementConfig.batched_word_sweep`;
    the default here is the ORACLE, so every unit test that names this
    kernel directly keeps measuring the carried scalar path.
    """
    samples = np.asarray(bits, np.uint8)
    visibility = np.asarray(mask, bool)
    if samples.ndim != 2 or visibility.shape != samples.shape:
        raise ValueError("Stage-A bits/mask must be equal 2-D arrays")
    hypotheses = stage_a_hypotheses(samples.shape)
    if hypotheses > budget.max_hypotheses:
        return StageAResult((), hypotheses, "attempt_budget_exceeded")
    candidates = _decode_candidates(samples, visibility, spec, slots,
                                    batched_sweep)
    return StageAResult(
        candidates, hypotheses,
        "candidates" if candidates else "no_word_candidate",
    )


def stage_a_patch(
    patch: AddressPatch,
    spec: TileFormat,
    budget: WordAttemptBudget,
    *,
    slots: SlotStage = "all",
    batched_sweep: bool = False,
) -> StageAResult:
    """Run multi-slot Stage A on one independently sampled E022 window."""
    return stage_a(patch.bits, patch.mask, spec, budget, slots=slots,
                   batched_sweep=batched_sweep)


# ------------------------------------------------- the known-position reduce

def _selection_key(observation: PilotObservation) -> tuple[float, str, int]:
    """R7b's DECLARED ORDER over one site's reads — SMALLEST wins.

    Strongest evidence first (negated, so the sort is a minimum), then
    the contributing pose, then the bit. Every term is a VALUE, so two
    runs that harvested in different orders select the same read.
    """
    return (-abs(float(observation.evidence)),
            "" if observation.pose_id is None else str(observation.pose_id),
            int(observation.bit))


def known_position_words(
    observations: tuple[PilotObservation, ...],
    spec: TileFormat,
) -> tuple[KnownWord, ...]:
    """Errors-first/known-erasure reads; failures never veto placement.

    v1 ``src/holo/receive/words.py:329-394``, carried WHOLE (H4 W5,
    ruling 2). The arithmetic is v1's: one strongest read per capture
    per site (same-scan overlaps are correlated, so they are not
    double-counted), an evidence-weighted sign vote with v1's own
    ``max(|e|, 1e-3)`` floor, unobserved sites as ERASURES, and the
    format wrapper (``pilots.decode_word``) as the authoritative
    pad/message gate beside the raw BCH decode that supplies the
    correction count.

    SCOPE (ruling 4): one (capture, footing). v1's ``all_observations``
    is one capture-lane pass and v1 NEVER compares word observations
    across lanes or captures below the certificate layer; this function
    reduces exactly the set its caller hands it and knows nothing about
    any other.

    **R7(b), the one FIX the port carries** (H4-PLAN R7b — v1 sums votes
    in PLACEMENT order, which is arrival order, and float addition is
    not associative). Two order-dependencies died:

    * v1's per-capture selection keeps the FIRST-SEEN read at equal
      ``|evidence|`` (a strict ``>``); here the winner is the minimum of
      :func:`_selection_key`, which is a total order on VALUES;
    * v1 sums ``per_scan.values()`` in insertion order; here the
      selected reads are summed in sorted ``(capture_id, pose_id)``
      order.

    Single-capture sessions are unaffected either way — one term per
    site — which is why the defect was invisible to today's echo. The
    sort is DATA, not an accident: it is what makes two runs that
    harvested in different orders produce the same float.
    """
    grouped: dict[tuple[int, int, int],
                  dict[int, list[PilotObservation]]] = {}
    for observation in observations:
        key = (observation.page,
               observation.tile_yx[0], observation.tile_yx[1])
        grouped.setdefault(key, {}).setdefault(
            observation.site_index, []).append(observation)
    rows: list[KnownWord] = []
    for (page, tile_y, tile_x), sites in sorted(grouped.items()):
        printed = np.zeros(pilots.N_WORD_SITES, np.uint8)
        known: list[int] = []
        contributors: set[ResourceKey] = set()
        for site_index in sorted(sites):
            reads = sites[site_index]
            # Same-capture overlaps are correlated: one strongest read
            # per capture, chosen by the declared order above.
            per_capture: dict[str, PilotObservation] = {}
            for read in reads:
                current = per_capture.get(read.capture_id)
                if current is None or _selection_key(read) < _selection_key(
                        current):
                    per_capture[read.capture_id] = read
            selected = tuple(
                per_capture[capture_id] for capture_id in sorted(per_capture))
            contributors.update(read.pose_id for read in selected
                                if read.pose_id is not None)
            vote = sum(
                (1.0 if read.bit else -1.0) * max(abs(read.evidence), 1e-3)
                for read in selected)
            printed[site_index] = np.uint8(vote >= 0.0)
            known.append(site_index)
        erasures = np.setdiff1d(
            np.arange(pilots.N_WORD_SITES), np.asarray(known, np.int64))
        decoded_counter: int | None = None
        errors: int | None = None
        if erasures.size <= 2 * bch.T:
            unscrambled = printed ^ pilots.value_scramble_bits(
                spec.seed, spec.plane)
            result = (bch.decode(unscrambled) if erasures.size == 0
                      else bch.decode_erasures(unscrambled, erasures))
            # The format wrapper is the authoritative pad/message gate.
            decoded_counter = pilots.decode_word(
                printed, spec.seed, spec.plane,
                None if erasures.size == 0 else erasures)
            if result is not None and decoded_counter is not None:
                errors = int(result[1])
            else:
                decoded_counter = None
        rows.append(KnownWord(
            page, (tile_y, tile_x),
            spec.tile_counter(page, tile_y, tile_x),
            decoded_counter, errors, int(erasures.size),
            tuple(sorted(contributors))))
    return tuple(rows)


__all__ = [
    "DecodedWordCandidate", "STAGE_A_MIN_VISIBLE_SITES",
    "SlotStage", "StageAResult", "known_position_words", "stage_a",
    "stage_a_hypotheses", "stage_a_patch",
]
