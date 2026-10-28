"""Family ``place``: the WORD KERNEL — Stage A plus the coupled bars.

H4 W1 brought the real E022 word route in (replacing the H3bis stand-in
whose region-seeded sweep and single per-window word fit were
holo2-original and never v1's); H4 W2's pull model took its PROVIDER
away and kept its arithmetic. What this file owns now is the word half
as a function — :func:`decode_word_address` — and the family's own name:

    the sampled window's bits (``place_shared.sample_window``)
    -> multi-slot Stage A over them (``words``)
    -> the coupled parity gate over each decoded address (``pose_audit``
       ``ScoreMemo.candidate``, bars from ``place_model``'s policy)

Everything around it lives where it always did: the preamble
(``sample_window``), the address->placement block (``place_addressed``)
and the emission are ``place_shared``'s, and what CALLS this is the pull
job's ladder (``place_job``), when a window's consult comes up empty.

**FIRST-HIT-WINS IS GONE — and W5 is where the LAST of it went.**
The H3bis placer took the first in-domain BCH decode as the answer and
rested on the algebraic d = 27 argument. W1 made every decoded candidate
a HYPOTHESIS that must clear the coupled E022 bars on two disjoint
parity populations, and then survive the straddle audit, before a single
cell of evidence is written. W5 adds the half that
``V1_WHOLEWORD_RIVAL_GATE``'s identity had always named and no code had
yet asked (DESIGN L8): **the winner must out-score its complete rival
set on WHOLE WORDS** (:func:`_rival_bar`). A word that decodes and does
not place is one-way evidence and nothing else.

THE TWO STAGES, AND WHERE THEIR MEMORY WENT (H4 W2, ruling Q2)
---------------------------------------------------------------
``centre`` decodes the historical most-interior slot of each
orientation; ``rest`` decodes the remaining slots. W1 made those two
DESCRIPTORS, staged by a durable ``WindowRecord.SLEEPING`` between them —
"the cheap half is spent" — because a spend row carries no version and
work gated on one could never be woken (the PY3 lesson).

The pull model has no descriptor to gate and no wake to arrange: a
window is a member of a scheduling set with a stage memory in it, so the
staging is one boolean in ``place_slot.Slot`` and the two stages are
two COST CLASSES rather than two spends. ``WordPlacementProvider`` and
``WordPlacementWorker`` are therefore gone rather than dormant — the
status they staged on is not in the record vocabulary any more (window
family v5), so they could not have been left standing truthfully.

R5's lattice seed is unchanged and now reaches its consumers the same
way: a fit that measured its own lattice proposes it back, the family's
transition law keeps the best-supported one, and a window whose fit
refused is re-armed when the seed improves (``place_sched._seed_ping``,
where a read-set subscription used to do it).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core import ProgressSink
from ..format import FormatRowSpec, TileFormat
from . import pose_audit, words
from .place_model import AttemptBudget, PlacementConfig, WordAttemptBudget
from .pose_fit import AddressPatch
from .reference import V1ReferenceField
from .words import SlotStage

FAMILY_PLACE = "place"
ROUTE_WORD = "word"

STAGE_CENTRE: SlotStage = "centre"
STAGE_REST: SlotStage = "rest"
#: The stages one window's word sweep is split into, cheapest first;
#: ``words`` also knows ``"all"``, which nothing here ever asks for (the
#: two stages are two COST CLASSES since H4 W2).
STAGES: tuple[SlotStage, ...] = (STAGE_CENTRE, STAGE_REST)

#: THE WINDOW'S OWN FIT REFUSED — no lattice cleared the geometric gates
#: over this rectangle, so no route ever ran (``place_shared.
#: sample_window``). Named here, with the rest of the family's shared
#: vocabulary, because W3 made it the first of v1's subdivision-eligible
#: refusals (``place_job.SUBDIVISION_REFUSALS``) and three files now
#: share the word.
REFUSAL_POSE = "pose_refused"

#: THE POSE STOOD AND THE SAMPLE WAS TOO THIN — fewer than
#: ``E022_SUPPORT_FLOOR_SITES`` supported sites under it. Named for the
#: same reason and the opposite verdict: v1 subdivides on
#: :data:`REFUSAL_POSE` and deliberately does NOT subdivide on this one
#: (``src/holo/receive/place.py:1259-1271`` returns without a call), so
#: the eligibility set has to be able to say which is which.
REFUSAL_SUPPORT = "insufficient_support"


@dataclass(frozen=True)
class WordAddress:
    """One decoded word that cleared the coupled parity bars."""

    page: int
    rot_k: int
    origin_yx: tuple[int, int]
    errors: int


def decode_word_address(patch: AddressPatch, spec: TileFormat,
                        row: FormatRowSpec, *, stage: SlotStage,
                        word_budget: WordAttemptBudget, budget: AttemptBudget,
                        reference: V1ReferenceField,
                        progress: ProgressSink,
                        config: PlacementConfig,
                        batched_sweep: bool = False) -> WordAddress | None:
    """Stage A over one stage's slots, then the coupled parity bars.

    THE WORD HALF, as a function (H4 W2's pull model): the durable
    staging that used to wrap it — two descriptors, a ``SLEEPING`` record
    between them — is now the pull job's in-memory stage memory, so what
    the two callers share had to become nameable. Nothing about the
    arithmetic moved: it is W1's ``WordPlacementWorker._decode`` verbatim,
    with the worker around it deleted.

    The declared Stage-A domain is the full multi-slot ceiling for either
    stage — the union bound only requires the declaration to dominate the
    attempts, so a stage that decodes fewer slots is conservative under
    the same declaration (``words.stage_a``). Within a stage candidates
    arrive errors-first, and the first one that PASSES is the answer; a
    candidate that fails is one-way evidence and never vetoes anything.

    ``batched_sweep`` is carried through to ``words.stage_a`` and picks
    the BCH decoder's arm; the two are bit-identical, so it may not move
    a candidate, a score or an answer (``solve/words.py``'s two-arms
    note).  The pull job sources it from its ``PlacementConfig``.
    """
    result = words.stage_a_patch(patch, spec, word_budget, slots=stage,
                                 batched_sweep=batched_sweep)
    progress.emit(1, f"stage-a-{stage}")
    if result.reason == "attempt_budget_exceeded":
        return None
    memo = pose_audit.ScoreMemo(reference)
    in_domain = tuple(candidate for candidate in result.candidates
                      if candidate.page in row.page_domain)
    for candidate in in_domain:
        scored = memo.candidate(
            0, patch.evidence, patch.bits, patch.mask, candidate.page,
            candidate.page_origin_yx, candidate.rot_k, budget, ROUTE_WORD)
        if not scored.passes:
            continue
        if not _rival_bar(memo, patch, candidate, in_domain, row=row,
                          budget=budget, config=config):
            return None
        return WordAddress(candidate.page, candidate.rot_k,
                           candidate.page_origin_yx, int(candidate.errors))
    return None


def _whole_word(memo: pose_audit.ScoreMemo, patch: AddressPatch, page: int,
                origin_yx: tuple[int, int], rot_k: int) -> float:
    """One hypothesis's WHOLE-WORD mismatch: all sites, both parities."""
    return memo.parity_score(0, patch.evidence, patch.bits, patch.mask,
                             page, origin_yx, rot_k,
                             pose_audit.WHOLE_WORD_PARITY)[0]


def _rivals(winner: words.DecodedWordCandidate,
            candidates: tuple[words.DecodedWordCandidate, ...],
            page_domain: tuple[int, ...],
            radius: int) -> tuple[tuple[int, tuple[int, int], int], ...]:
    """THE COMPLETE RIVAL SET this winner must out-score (L7, L8).

    Two populations, and both are the word route's own — nothing here
    sweeps a correlation map:

    * **the other decoded candidates**, minus the winner's own
      neighbourhood, by v1's cold rule (``cold.correlate_patch``: same
      page, same orientation, within ``neighbor_radius_cells`` is the
      SAME answer, not a rival).  A truthful window's sibling slots all
      imply the identical ``page_origin_yx``, so they dedup here by
      construction and only a genuinely different reading survives;
    * **the winner's own geometry on every OTHER declared page**, which
      is the population the 0.176 diagnosis named: a
      PARITY-CONCENTRATED CROSS-PAGE ALIAS is by definition a rival that
      the word decode itself cannot see, because the counter it decoded
      names one page.  Asking the same rectangle of the other pages is
      what makes the d=27 floor bind (RECEIVE-DESIGN v0.25/v0.30,
      docs/FULL-DOMAIN-RIVAL-ANALYSIS.md).

    Alias pressure scales with the DECLARED page domain, so a
    single-page session has no cross-page population at all and the
    gate's real customers are large-domain archive sessions.  The set is
    never truncated (L7): a rival set trimmed to fit is a domain
    narrowed by current pixels.
    """
    identity = (winner.page, winner.page_origin_yx, winner.rot_k)
    rows: list[tuple[int, tuple[int, int], int]] = []
    seen = {identity}
    for candidate in candidates:
        row_id = (candidate.page, candidate.page_origin_yx, candidate.rot_k)
        if row_id in seen:
            continue
        if (candidate.page == winner.page
                and candidate.rot_k == winner.rot_k
                and max(abs(candidate.page_origin_yx[0]
                            - winner.page_origin_yx[0]),
                        abs(candidate.page_origin_yx[1]
                            - winner.page_origin_yx[1])) <= radius):
            continue
        seen.add(row_id)
        rows.append(row_id)
    for page in page_domain:
        row_id = (int(page), winner.page_origin_yx, winner.rot_k)
        if row_id in seen:
            continue
        seen.add(row_id)
        rows.append(row_id)
    return tuple(rows)


def _rival_bar(memo: pose_audit.ScoreMemo, patch: AddressPatch,
               winner: words.DecodedWordCandidate,
               candidates: tuple[words.DecodedWordCandidate, ...], *,
               row: FormatRowSpec, budget: AttemptBudget,
               config: PlacementConfig) -> bool:
    """L8's rule change: the WHOLE-WORD rival gate over decoded words.

    **This is what replaced first-hit-wins** (H4 W5). v1's word route
    returns the first candidate that clears the coupled parity bars
    (``receive/place.py:433-447``) and rests the rest of the argument on
    d = 27; v1's COLD route additionally makes every winner out-score
    its rival set, and the v0.30 ruling moved that arithmetic to whole
    words after the complete-domain 0.176 refusal was diagnosed as a
    parity-concentrated cross-page alias.  L8 says both routes get the
    bar; W5 is where the word route gets it.

    THE SEAM IS ABOVE THE BATCHED BCH KERNEL — this reads
    :class:`~holo2.solve.words.DecodedWordCandidate` values and never a
    codeword, so ``format.bch_batch``, its scalar oracle and the
    ``holo2/measure/bch_equivalence*`` populations are untouched by it
    and need no re-proving.

    The arithmetic is ``cold.correlate_patch``'s, verbatim: the decoy
    bar binds the MOST DANGEROUS member of the rival set (the MINIMUM
    whole-word mismatch over it), the winner's own mismatch is measured
    whole-word too, and an EMPTY rival set scores 1.0 against the
    winner's search-class mismatch — which is why a single-page session
    with one legal reading decides exactly as it did before this wave.
    Selection is unchanged; only the decoy/gap arithmetic is new here.
    """
    rivals = _rivals(winner, candidates, tuple(row.page_domain),
                     config.neighbor_radius_cells)
    if not rivals:
        return pose_audit.rival_gate(
            memo.parity_score(0, patch.evidence, patch.bits, patch.mask,
                              winner.page, winner.page_origin_yx,
                              winner.rot_k, 0)[0], 1.0, budget.gate)
    rival_mismatch = min(
        _whole_word(memo, patch, page, origin_yx, rot_k)
        for page, origin_yx, rot_k in rivals)
    best_whole = _whole_word(memo, patch, winner.page,
                             winner.page_origin_yx, winner.rot_k)
    return pose_audit.rival_gate(best_whole, rival_mismatch, budget.gate)


__all__ = [
    "FAMILY_PLACE", "REFUSAL_POSE", "REFUSAL_SUPPORT", "ROUTE_WORD",
    "STAGES", "STAGE_CENTRE", "STAGE_REST",
    "WordAddress", "decode_word_address",
]
