"""V1 Lane-W address words over E022 observation windows.

Cold Stage A is the result-exact batched form of the historical E022
shortcut, widened to the complete slot grid: for each orientation it sweeps
every full 64-cell slot of the patch (row-major slot order), BCH-decodes the
hard samples at every fitting phase of every slot, then keeps candidates with
at least 90 visible word sites.  Candidates are returned in one global
errors-first trial order across every slot and orientation (ties break by
oriented row-major slot index, then rot_k, then row-major phase).  Visibility
does not turn hidden samples into erasures at this cold-search rung; the
independent pilot-parity gates remain the authority for accepting a decoded
seed.

Word trust is one-way: a certified word may seed or label geometry, while a
failure/conflict is reported and never invalidates an independently accepted
Lane-C placement.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..core import bch
from ..format import pilots
from ..format.descriptor import FormatSpec
from .placement.geometry import AddressPatch
from .placement.model import KnownWord, PilotObservation


@dataclass(frozen=True, slots=True)
class WordAttemptBudget:
    """Complete multi-slot domain and single-word union-bound declaration.

    A random 100-bit word lies within radius 13 of one of the 2^18
    pad-valid counter codewords with probability

      2^18 * sum(C(100,i), i=0..13) / 2^100.

    For ``H`` declared phase hypotheses the conservative family-wise bound
    is ``H*p``.  The declared domain may exceed the phases physically
    attempted (trailing slots admit fewer fitting phases than the uniform
    per-slot declaration); the union bound only requires the declaration to
    dominate the attempts.  The receiver does not narrow this declared
    domain or assume independence between overlapping phases.
    """

    max_hypotheses: int
    familywise_false_accept: float
    qualification_id: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_hypotheses, (bool, np.bool_))
            or not isinstance(self.max_hypotheses, (int, np.integer))
            or int(self.max_hypotheses) < 0
        ):
            raise ValueError("max_hypotheses must be a nonnegative integer")
        if not 0.0 < float(self.familywise_false_accept) < 1.0:
            raise ValueError("familywise_false_accept must be in (0,1)")
        if not isinstance(self.qualification_id, str) or not self.qualification_id:
            raise ValueError("qualification_id must name gate provenance")
        if self.random_union_bound > self.familywise_false_accept:
            raise ValueError(
                "declared Stage-A domain exceeds its false-accept spend: "
                f"bound={self.random_union_bound:.3g}, "
                f"alpha={self.familywise_false_accept:.3g}"
            )

    @property
    def single_word_probability(self) -> float:
        sphere = sum(math.comb(pilots.N_WORD_SITES, errors)
                     for errors in range(bch.T + 1))
        return math.ldexp(float(sphere), pilots.COUNTER_BITS - pilots.N_WORD_SITES)

    @property
    def random_union_bound(self) -> float:
        return min(1.0, self.max_hypotheses * self.single_word_probability)


@dataclass(frozen=True, slots=True)
class DecodedWordCandidate:
    oriented_origin_yx: tuple[int, int]
    rot_k: int
    counter: int
    page: int
    tile_yx: tuple[int, int]
    errors: int
    page_origin_yx: tuple[int, int]


@dataclass(frozen=True, slots=True)
class StageAResult:
    candidates: tuple[DecodedWordCandidate, ...]
    hypotheses: int
    reason: str


def _slot_grid(shape: tuple[int, int]) -> tuple[tuple[int, int], ...]:
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


def _slot_phase_capacity(shape: tuple[int, int]) -> int:
    """Declared per-slot phase count: the base slot's fitting-phase room.

    Every full slot is declared at this uniform single-slot capacity
    ``min(64, H-63) * min(64, W-63)``.  Trailing slots physically admit
    fewer fitting phases, so the declared Stage-A domain is a conservative
    ceiling on decode attempts; see :class:`WordAttemptBudget`.
    """
    height, width = shape
    period = pilots.TILE_CELLS
    if height < period or width < period:
        return 0
    return (
        min(period, height - period + 1) * min(period, width - period + 1)
    )


def _centre_slot(shape: tuple[int, int]) -> tuple[int, int] | None:
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


def _slot_phase_shape(
    shape: tuple[int, int], slot: tuple[int, int]
) -> tuple[int, int]:
    height, width = shape
    period = pilots.TILE_CELLS
    base_y, base_x = slot[0] * period, slot[1] * period
    return (
        min(period, height - base_y - period + 1),
        min(period, width - base_x - period + 1),
    )


def stage_a_hypotheses(shape: tuple[int, int]) -> int:
    """Sum over every full slot of its declared phase domain, four rot90s.

    A 200x200 window declares 9 slots x 64x64 phases x 4 orientations =
    147,456; a 70x70 window declares its single slot's 7x7 fitting phases
    x 4 = 196.  The per-slot declaration is the uniform base-slot capacity
    (:func:`_slot_phase_capacity`), an exact count for every slot except
    the trailing row/column, where it conservatively over-declares.
    """
    if len(shape) != 2 or any(
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, np.integer))
        or int(value) < 0
        for value in shape
    ):
        raise ValueError("Stage-A shape must contain two nonnegative integers")
    total = 0
    for rot_k in range(4):
        oriented_shape = shape if rot_k % 2 == 0 else shape[::-1]
        total += (
            len(_slot_grid(oriented_shape))
            * _slot_phase_capacity(oriented_shape)
        )
    return total


def _gather_slot(
    grid: np.ndarray,
    mask: np.ndarray,
    slot: tuple[int, int],
    positions: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """Gather all phases in one disjoint slot, following old Stage A."""
    height, width = grid.shape
    period = pilots.TILE_CELLS
    base_y, base_x = slot[0] * period, slot[1] * period
    row_limit, col_limit = _slot_phase_shape((height, width), slot)
    if row_limit <= 0 or col_limit <= 0:
        return None
    phase_y = np.arange(row_limit)
    phase_x = np.arange(col_limit)
    iy = base_y + phase_y[:, None] + positions[None, :, 0]
    ix = base_x + phase_x[:, None] + positions[None, :, 1]
    values = grid[iy[:, None, :], ix[None, :, :]]
    visible = mask[iy[:, None, :], ix[None, :, :]]
    return (
        values.reshape(-1, positions.shape[0]),
        visible.reshape(-1, positions.shape[0]),
        base_y + np.repeat(phase_y, col_limit),
        base_x + np.tile(phase_x, row_limit),
    )


def _decode_candidates(
    bits: np.ndarray,
    mask: np.ndarray,
    spec: FormatSpec,
    slots: str = "all",
) -> tuple[DecodedWordCandidate, ...]:
    if slots not in ("all", "centre", "rest"):
        raise ValueError("Stage-A slot stage must be all, centre, or rest")
    positions = pilots.word_site_cells_yx(spec.family_seed)
    scramble = pilots.value_scramble_bits(spec.seed, spec.plane)
    keyed: list[
        tuple[tuple[int, int, int, int], DecodedWordCandidate]
    ] = []
    for rot_k in range(4):
        oriented_bits = np.rot90(np.asarray(bits, np.uint8), rot_k)
        oriented_mask = np.rot90(np.asarray(mask, bool), rot_k)
        centre = _centre_slot(oriented_bits.shape)
        for slot_index, slot in enumerate(_slot_grid(oriented_bits.shape)):
            if slots == "centre" and slot != centre:
                continue
            if slots == "rest" and slot == centre:
                continue
            gathered = _gather_slot(
                oriented_bits, oriented_mask, slot, positions)
            if gathered is None:
                continue
            words, visible, origins_y, origins_x = gathered
            decoded = bch.decode_many(words ^ scramble)
            for phase_index, result in enumerate(decoded):
                # Historical try_bch_seed decoded the hard samples first
                # and applied only this per-phase visibility floor to the
                # surviving candidate.
                if result is None or int(
                        np.count_nonzero(visible[phase_index])) < 90:
                    continue
                corrected, errors = result
                message = bch.message_from_word(corrected)
                if message[pilots.COUNTER_BITS:].any():
                    continue             # authoritative five-zero-pad gate
                counter = 0
                for bit in message[:pilots.COUNTER_BITS]:
                    counter = (counter << 1) | int(bit)
                page, tile_y, tile_x = spec.tile_address(counter)
                if page >= spec.max_pages:
                    continue
                # BCH's correction count is exactly the printed-word
                # Hamming distance: XOR by the fixed scramble preserves
                # distance and the accepted zero-pad message re-encodes to
                # ``corrected``.
                errors = int(errors)
                if errors > bch.T:
                    continue
                origin = (
                    int(origins_y[phase_index]),
                    int(origins_x[phase_index]),
                )
                page_origin = (
                    tile_y * pilots.TILE_CELLS - origin[0],
                    tile_x * pilots.TILE_CELLS - origin[1],
                )
                keyed.append((
                    (errors, slot_index, rot_k, phase_index),
                    DecodedWordCandidate(
                        origin, rot_k, int(counter), int(page),
                        (int(tile_y), int(tile_x)), errors, page_origin,
                    ),
                ))
    # Global errors-first trial order: a clean rot1 seed precedes a
    # 13-error rot0 seed.  Equal-error ties break deterministically by
    # oriented row-major slot index, then rot_k, then the slot's row-major
    # phase enumeration.
    keyed.sort(key=lambda row: row[0])
    return tuple(candidate for _key, candidate in keyed)


def stage_a(
    bits: np.ndarray,
    mask: np.ndarray,
    spec: FormatSpec,
    budget: WordAttemptBudget,
    *,
    slots: str = "all",
) -> StageAResult:
    """Return legal single-word candidates, errors-first within the stage.

    ``slots`` selects the v0.26 staged sweep: ``"centre"`` decodes only the
    historical most-interior slot per orientation, ``"rest"`` the remaining
    slots, ``"all"`` everything.  The declared domain (and the budget
    refusal) is always the full multi-slot ceiling — the union bound only
    requires the declaration to dominate the attempts actually made, so a
    stage that decodes fewer slots under the same declaration is
    conservative.
    """
    bits = np.asarray(bits, np.uint8)
    mask = np.asarray(mask, bool)
    if bits.ndim != 2 or mask.shape != bits.shape:
        raise ValueError("Stage-A bits/mask must be equal 2-D arrays")
    hypotheses = stage_a_hypotheses(bits.shape)
    if hypotheses > budget.max_hypotheses:
        return StageAResult((), hypotheses, "attempt_budget_exceeded")
    candidates = _decode_candidates(bits, mask, spec, slots)
    return StageAResult(
        candidates, hypotheses, "candidates" if candidates else "no_word_candidate"
    )


def stage_a_patch(
    patch: AddressPatch,
    spec: FormatSpec,
    budget: WordAttemptBudget,
    *,
    slots: str = "all",
) -> StageAResult:
    """Run multi-slot Stage A on one independently sampled E022 window."""
    return stage_a(patch.bits, patch.mask, spec, budget, slots=slots)


def known_position_words(
    observations: tuple[PilotObservation, ...],
    spec: FormatSpec,
) -> tuple[KnownWord, ...]:
    """Errors-first/known-erasure reads; failures never veto placement."""
    grouped: dict[
        tuple[int, int, int], dict[int, list[PilotObservation]]
    ] = {}
    for observation in observations:
        key = (
            observation.page,
            observation.tile_yx[0], observation.tile_yx[1],
        )
        grouped.setdefault(key, {}).setdefault(
            observation.site_index, []
        ).append(observation)
    rows: list[KnownWord] = []
    scramble = pilots.value_scramble_bits(spec.seed, spec.plane)
    for (page, tile_y, tile_x), sites in sorted(grouped.items()):
        printed = np.zeros(pilots.N_WORD_SITES, np.uint8)
        known: list[int] = []
        contributors: set[int] = set()
        for site_index, reads in sites.items():
            # Same-scan overlaps are correlated: one strongest read per scan.
            per_scan: dict[str, PilotObservation] = {}
            for read in reads:
                current = per_scan.get(read.scan_id)
                if current is None or abs(read.evidence) > abs(current.evidence):
                    per_scan[read.scan_id] = read
            selected = tuple(per_scan.values())
            contributors.update(
                read.patch_id for read in selected if read.patch_id is not None)
            vote = sum(
                (1.0 if read.bit else -1.0) * max(abs(read.evidence), 1e-3)
                for read in selected
            )
            printed[site_index] = np.uint8(vote >= 0.0)
            known.append(site_index)
        erasures = np.setdiff1d(
            np.arange(pilots.N_WORD_SITES), np.asarray(known, np.int64)
        )
        decoded_counter: int | None = None
        errors: int | None = None
        if erasures.size <= 2 * bch.T:
            unscrambled = printed ^ scramble
            result = (
                bch.decode(unscrambled)
                if erasures.size == 0
                else bch.decode_erasures(unscrambled, erasures)
            )
            # The format wrapper is the authoritative pad/message gate.
            decoded_counter = pilots.decode_word(
                printed, spec.seed, spec.plane,
                None if erasures.size == 0 else erasures,
            )
            if result is not None and decoded_counter is not None:
                errors = int(result[1])
            else:
                decoded_counter = None
        expected_counter = spec.tile_counter(page, tile_y, tile_x)
        rows.append(KnownWord(
            page, (tile_y, tile_x), expected_counter, decoded_counter,
            errors, int(erasures.size),
            tuple(sorted(contributors)),
        ))
    return tuple(rows)
