"""The pass driver — targets to certificates, to a fixed point (DESIGN §6b).

One call, one shape:

    targets -> per lane, the arm battery -> `calibrate.select_arm`
            -> per rule, `combine.combine` -> `ladder.run_ladder`
            -> fold the new certificates into the frame and RE-TARGET
               their 8-neighbourhood and sibling streams -> repeat.

e034 measured 82% of the production plane arm's mints as cascade, chains
seven generations deep, so a single pass is a lower bound several fold
below what the machinery does; every certificate here carries its
`generation` and its `predecessors`.

BLINDNESS (RULING, Germano, 2026-09-04).  Ground truth does not enter
this module at all — not as an argument, not as an import, not as a
verdict.  :func:`blind_key` is the whole decision path: it sees the
certificate mapping, the format row, the pixels and the blind metadata
bit, and it returns evidence, combinations and rung results.  A
gate-passing certificate is `certified` (direct rung) or `certified_list`
(list rung), full stop; the `wrong` / `false_accept` adjudication that
used to live here is the OFFLINE scorer's (`analyzer.score`), which
reads the ledger afterwards.  What the ledger must therefore CARRY for
that scorer is the certified user bits and, per rung, the packed exit
hard vector (`keep_hard`, base64 in `detail["hard_packed_b64"]`)
alongside the blind columns it already had.  An import-set test pins
that no module a run command can reach imports `truth` or `oracle`.

INDEPENDENT AGREEMENT (2026-09-04, leg 4).  Every gate-passing
certificate a key produces is collected with the physical captures its
combination leaned on, and `combine.independent_agreement` says how many
of them rest on DISJOINT captures and agree bit for bit.  Two that
DISAGREE are a contradiction — both passed syndrome and CRC, so one is a
false accept and nothing blind can say which — and the key is REFUSED:
no mint, no cascade, `refusal=independent_certificates_disagree` on the
row.  The row carries `independent_agreement` in `diag` and the ledger
header counts both.

THREADS.  Keys run on a `ThreadPoolExecutor` sharing one snapshot (it is
6.5 GB on sheet I and must never be loaded twice — DESIGN §10).  Results
are merged in the PINNED target order, not in completion order, so the
ledger is worker-count independent; the exposure ledger is one
lock-guarded object, because the bound of DESIGN §0 is a correctness
bound and correctness is not per-thread.

MEMORY.  Crops live inside `blind_key`'s crop memo — one per CUT of the
lane the battery is on, where every arm used to cut its own — and the
memo drops a lane's crops when the loop leaves it and dies with the key,
so a worker's resident pixels go from one crop to two and the pass holds
none between keys.  The ledger row keeps per-rung SUMMARIES (plus the
512-byte packed hard vector), never LLR vectors, unless
`config.keep_vectors` asks otherwise.
Since 2026-09-13 the rows themselves do not live here either: a pass
given a `ledger.LedgerWriter` streams each row to disk as its generation
folds it and keeps three values per key (`summary`), and each key's work
dict is POPPED as its row is built.  A row is 1.6 MB of JSON on the
four-capture sheet-J pass and about twice that alive, so the 2,700-target
pass that held 15-32 GB of them now holds none.
"""

from __future__ import annotations

import itertools
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace as dc_replace
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from . import arms as arms_mod
from . import calibrate as cal
from . import combine as combine_mod
from . import frame as frame_mod
from . import inputs as inputs_mod
from . import ladder as ladder_mod
from . import passfiles as passfiles_mod
from . import refit as refit_mod
from . import residue as residue_mod
from . import sample as sample_mod
from . import statecal
from . import stopdoor as doors_mod
from .types import (PLANE_OF, RESERVED_KNOBS, VERDICT_CERTIFIED,
                    VERDICT_CERTIFIED_LIST, VERDICT_OPEN, AnalyzerConfig,
                    Exposure, Key, Ledger, LedgerRow)


#: `L7` on the command line means both erasure rungs (DESIGN §6).
RUNG_ALIASES: dict[str, tuple[str, ...]] = {"L7": ("L7a", "L7b")}

#: The operator's doors live in `stopdoor` since the stop door joined
#: the status window there (2026-09-07): one subject, one module, and
#: this file is at its 1,000-line cap.  The names stay spelled HERE
#: because the CLI and the tests read them off the driver.
PROGRESS_EVERY = doors_mod.PROGRESS_EVERY
CHECKPOINT_MINUTES = doors_mod.CHECKPOINT_MINUTES
CHECKPOINT_NAME = doors_mod.CHECKPOINT_NAME
STATUS_SIGNALS = doors_mod.STATUS_SIGNALS
STOP_INTERRUPTED = doors_mod.STOP_INTERRUPTED
Checkpointer = doors_mod.Checkpointer
Progress = doors_mod.Progress
_hms = doors_mod._hms
_status_doors = doors_mod._status_doors
stop_door = doors_mod.stop_door

#: And the PRODUCTS live in `passfiles` since 2026-09-13, for the same
#: reason and under the same rule: a pass's four artefacts are one
#: subject, this file was 1,300 lines, and the names stay spelled HERE
#: because the CLI and the tests read them off the driver.
FIELD2_PRODUCT_NAME = passfiles_mod.FIELD2_PRODUCT_NAME
FIELD2_MM_PER_TILE = passfiles_mod.FIELD2_MM_PER_TILE
field2_mod = passfiles_mod.field2_mod
field2_product = passfiles_mod.field2_product
mint_record = passfiles_mod.mint_record
rung_dict = _rung_dict = passfiles_mod.rung_dict
write_field2_product = passfiles_mod.write_field2_product
_field2_sinusoid = passfiles_mod._field2_sinusoid
_jsonable_knobs = passfiles_mod._jsonable_knobs


#: Why the generation loop stopped — the ledger header's `stop_reason`
#: (ruling R1, 2026-09-06).  `STOP_FIXED_POINT` is the only one that says
#: the pass is COMPLETE: a generation re-attacked nothing, so another
#: generation would have done nothing.  `STOP_CAP_REACHED` says a cap cut
#: the cascade short with re-attacks still pending; WHICH cap is the
#: header's own `max_generations` and `fixed_point`, because nothing here
#: can tell an explicit `--max-generations 1` from the one-generation
#: default of a pass that spelled neither flag — the retired third reason
#: (`single generation`) claimed it could (follow-up review 2026-09-06).
#: `STOP_INTERRUPTED` (the stop door, 2026-09-07) beats both: the pass
#: ended where the operator asked it to, so neither the cap nor the
#: fixed point may claim it.
STOP_FIXED_POINT = "fixed point"
STOP_CAP_REACHED = "cap reached"


def shared_exposure(bound: float | None = None) -> Exposure:
    """One exposure ledger for every thread of a run.

    ONE object, shared, rather than per-thread sets merged afterwards:
    the exposure bound is a CORRECTNESS bound (DESIGN §0), not a budget,
    so it has to be live while the run consults.  What makes that safe
    is `Exposure.reserve`, which is atomic — a locked `set` was not
    enough, because the race was in the check-then-act pair `gate` made
    of two of its operations (review F13, 2026-09-13).
    """
    exposure = Exposure()
    if bound is not None:
        exposure.bound_expected_false = float(bound)
    return exposure


def expand_rungs(rungs: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    for name in rungs:
        out.extend(RUNG_ALIASES.get(str(name), (str(name),)))
    return tuple(out)


def _plane_field(inputs: Any, key: Key) -> Any:
    """The page's standing field for this key's plane, if one stands.

    (page, plane) and nothing else: one field per printed face and plane
    applies to every lane of that page, so the lane is not part of the
    lookup (PAGE-FIELD-PLAN A1).
    """
    page, _ty, _tx, stream_id = key
    return inputs.plane_fields.get((int(page), PLANE_OF[str(stream_id)]))


def _halo_for(config: AnalyzerConfig, stream_id: str) -> int:
    if config.halo_cells is None:
        return int(arms_mod.HALO_CELLS[str(stream_id)])
    return int(config.halo_cells[str(stream_id)])


#: One ordinal per `run` call in this process (M2, 2026-09-13).  It is
#: WHOSE a `field2` fit is, nothing more: the memo outlives a pass, so
#: without it a second pass over the same inputs could not tell a field
#: it fitted from one the first pass left behind.  A counter rather than
#: `id(...)`, because an id can be recycled and a pass's identity has to
#: outlive the pass.  `itertools.count` is atomic, so no lock.
_PASS_TOKENS = itertools.count(1)


def _knobs_for(inputs: Any, config: AnalyzerConfig, key: Key,
               metadata_bit: int | None,
               pass_token: Any = None) -> dict:
    return {
        "seed": int(config.seed),
        "ctx_mode": str(config.ctx_mode),
        "mix_scope_ladder": tuple(config.mix_scope_ladder),
        "lane_mix_tiles": int(config.lane_mix_tiles),
        "metadata_known": bool(config.metadata_known
                               and metadata_bit is not None),
        "metadata_bit": metadata_bit,
        "plane_field": _plane_field(inputs, key),
        # The pass's own worker count, handed to `field2`'s lazy pooled
        # fit (PAGE-FIELD-PLAN A2): the first key that asks for a
        # `field2` arm holds every other key behind that fit, and the
        # fit threads per LANE.  Publishing the FULL width is safe
        # because concurrent fits share one bound on reads in flight
        # (`field2.read_slots`), so the fits divide this number rather
        # than each taking it.  A knob bag that names it wins, so an
        # operator can still pin it.
        "field2_fit_workers": int(config.workers),
        **dict(config.knobs),
        # AFTER the knob bag, not before it: this one is provenance, so
        # it is the pass's to state and not an operator's to name (M2).
        "field2_pass_token": pass_token,
    }


# ---------------------------------------------------- the blind decision

def sequential_state_for(inputs: Any, certs: Mapping[Key, Any], key: Key
                         ) -> np.ndarray:
    """The tile's own SIBLING STATE per sequential position (W8 B2/B4).

    Built ONCE per key from a halo-0 frame — the state of an in-tile cell
    is its two sibling planes' certified bits, which the target tile's
    own M/Y certificates lay (only the target KEY is hidden), so the
    halo adds nothing to it — and handed to `combine` (`platt-state`),
    the ladder (`L7c`), and the refit closure.  From the FRAME, never
    from a decoder output; the projections are memoised by certificate
    token, so this costs one scatter.
    """
    page, ty, tx, _stream = key
    footprint = frame_mod.tile_footprint(inputs.row, int(page), int(ty),
                                         int(tx), 0,
                                         geometry=inputs.geometry)
    frame = frame_mod.known_frame(inputs, certs, footprint, key,
                                  metadata_known=False, metadata_bit=None)
    return statecal.sequential_state(frame, footprint, inputs.row,
                                     inputs.geometry, key)


def _derived_knobs(base: Mapping[str, Any], combined: Any,
                   state_seq: np.ndarray | None, refit: Any
                   ) -> dict[str, Any]:
    """One rule's ladder knobs: the base bag plus what THIS combination
    derived, ASSIGNED (never `setdefault` — a reserved name in the base
    bag is refused before this runs, W8 ruling 8)."""
    rule_knobs = dict(base)
    # L3 APPLIES the footprint's context offsets, it never refits them
    # (DESIGN §6 L3, RULED after W2); `combine` pooled them over the
    # lanes this rule actually used, so they ride the rule's own knobs.
    rule_knobs["ctx_offsets"] = combined.ctx_offsets
    # L7a's disagreement set is the same kind of knob: a blind product
    # of the combination this rule just made (DESIGN §6 L7a).  The pair
    # is (indices, agreement AT those indices) — parallel arrays, which
    # is what `_rung_erase_disagree` orders its erasures by.
    if combined.disagree is not None:
        rule_knobs["disagree"] = (combined.disagree,
                                  combined.agreement[combined.disagree])
    else:
        rule_knobs.pop("disagree", None)
    # W8 B2: the sibling state (L7c) and ruling 10's flag (L3 refuses a
    # row whose lanes adopted a per-state context); B4: the refit closure
    # (L3f), pixels behind it, one evidence budget per KEY inside it.
    rule_knobs["sibling_state"] = state_seq
    rule_knobs["ctx_state_adopted"] = bool(
        getattr(combined, "ctx_state_adopted", False))
    # RULING 10's OTHER half (review 2026-09-06).  `ctx_state_adopted` is
    # C2's flag — a LANE adopted a per-state context residual.  D1 breaks
    # L3's apply mode the same way from the other side: under
    # `platt-state` a state-s cell carries `w_s @ stack` while
    # `ctx_offsets` is the POOLED coefficient-weighted sum, so removing
    # one 9-vector at the channel's bins removes a correction those cells
    # never had.  Published as its own knob so the ledger separates the
    # two refusals rather than conflating them.
    rule_knobs["state_weighted"] = bool(
        getattr(combined, "coefficients_by_state", None))
    rule_knobs["refit"] = refit
    return rule_knobs


def blind_key(inputs: Any, certs: Mapping[Key, Any], key: Key,
              config: AnalyzerConfig, exposure: Exposure, *,
              metadata_bit: int | None = None,
              pass_token: Any = None) -> dict:
    """Everything the analyzer decides about one tile-stream, BLIND.

    No ground truth reaches this function or anything it calls; the
    certificate gate (syndrome + CRC) is the only thing that can say
    `certified` here, exactly as in production.

    `pass_token` is the caller's own identity, and the only thing it
    reaches is the `field2` memo entry a fit made under this key fills
    (M2): a library caller that names none leaves the entry unstamped,
    which is what "no pass fitted this" means.
    """
    started = time.perf_counter()
    page, ty, tx, stream_id = key
    out: dict[str, Any] = {"key": key, "evidence": {}, "combined": {},
                           "rungs": {}, "selected": {}}
    # W8 ruling 8: every derived knob is assigned below; a config that
    # carries one of their names is refused rather than overridden.
    reserved = [name for name in RESERVED_KNOBS if name in config.knobs]
    if reserved:
        out["refusal"] = f"reserved_knob:{reserved[0]}"
        out["seconds"] = time.perf_counter() - started
        return out
    lanes = sample_mod.lanes_for_tile(inputs, int(page), int(ty), int(tx),
                                      cover_fraction=config.cover_fraction)
    out["n_lanes"] = len(lanes)
    if not lanes:
        out["refusal"] = "no_lane_sees_this_tile"
        out["seconds"] = time.perf_counter() - started
        return out

    halo = _halo_for(config, str(stream_id))
    footprint = frame_mod.tile_footprint(inputs.row, int(page), int(ty),
                                         int(tx), halo,
                                         geometry=inputs.geometry)
    folds = cal.split_folds(footprint.page_cells_yx, int(config.seed))
    state_seq = sequential_state_for(inputs, certs, key)
    out["diag_state"] = statecal.state_summary(state_seq)
    battery = config.battery_for(str(stream_id))
    chosen: list[Any] = []
    #: GAPS-2026-09-03's re-roll: every arm's evidence is computed for the
    #: selection anyway, so the ones the select fold did not pick are kept
    #: rather than dropped.  They cost nothing more to hold and they are
    #: what the re-roll below spends.
    usable_by_lane: dict[Any, list[Any]] = {}
    #: W8 B4: what the refit closure re-runs an evidence with — the SAME
    #: knobs and the same `Lane` — kept per lane id, not recomputed.
    knobs_by_lane: dict[Any, dict] = {}
    lanes_by_id: dict[Any, Any] = {}
    #: THE CROP MEMO (2026-09-13).  `open_crops` cuts by knobs that are
    #: per LANE, so the battery below asks for exactly TWO crops per
    #: (key, lane) — the box arms' and the patch/pure arms' wider
    #: keep-raw one — and used to cut one per ARM.  This hands the second
    #: asker the first's pixels; it holds one lane at a time (see
    #: `sample.LaneCropMemo`) and dies with the key, so a worker's
    #: resident pixels go from one crop to two, not to two per lane.
    crop_memo = sample_mod.LaneCropMemo()
    for lane in lanes:
        knobs = _knobs_for(inputs, config, key, metadata_bit, pass_token)
        knobs_by_lane[lane.lane_id] = knobs
        lanes_by_id[lane.lane_id] = lane
        candidates = []
        #: THE COLLAPSED-FIELD ECONOMY (PAGE-FIELD-PLAN finding 3).  A
        #: `field` arm whose field reads zero over every observed cell
        #: of the footprint IS the arm it collapses to, cell for cell —
        #: `register` renames the row and samples the committed pose.
        #: The collapse does not depend on the unmix mode, so the FIRST
        #: `field` arm evaluated here says what the others would do, and
        #: an arm whose twin is already computed for this (key, lane)
        #: takes that row instead of paying for a byte-identical
        #: duplicate — one 26-evaluation offset grid per (key, lane)
        #: where the field reads zero.  The candidate set is UNCHANGED
        #: — the same row under the same name, in the same order — so
        #: nothing the select fold sees moves; the row says where it
        #: came from, and keeps what the field itself said
        #: (`field_ordinal`, `field_uncertainty_dots`: WHICH revision
        #: stood over this tile, which a reader needs whether or not
        #: the delta was zero).
        computed: dict[str, Any] = {}
        collapse_reason: str | None = None
        stood: dict[str, Any] = {}
        for arm in battery:
            twin = None
            head, tail = arms_mod.parse_arm(arm)
            if collapse_reason is not None and tail in arms_mod.FIELD_COLLAPSE:
                twin = f"{head}+{arms_mod.FIELD_COLLAPSE[tail]}"
            if twin is not None and twin in computed:
                held = computed[twin]
                evidence = dc_replace(
                    held, arm=arm,
                    blind={**dict(held.blind), "arm": arm,
                           "register_arm": tail, "field_applied": False,
                           "field_reason": collapse_reason, **stood,
                           "register_arm_effective":
                               arms_mod.FIELD_COLLAPSE[tail],
                           "reused_from_arm": twin})
                out["reused_arms"] = int(out.get("reused_arms", 0)) + 1
            else:
                evidence = arms_mod.evidence_for(
                    inputs, certs, key, lane, arm, halo_cells=halo,
                    knobs=knobs,
                    crop_memo=crop_memo.for_lane(lane.lane_id))
                computed[arm] = evidence
                if (tail in arms_mod.FIELD_COLLAPSE
                        and evidence.blind.get("register_arm_effective")
                        == arms_mod.FIELD_COLLAPSE[tail]):
                    collapse_reason = str(evidence.blind.get(
                        "field_reason", "field_collapsed"))
                    stood = {name: evidence.blind[name]
                             for name in ("field_ordinal",
                                          "field_uncertainty_dots",
                                          "field_collapse_over")
                             if name in evidence.blind}
            candidates.append(evidence)
            out["evidence"][(lane.lane_id, arm)] = dict(evidence.blind)
        usable = [item for item in candidates
                  if item.blind.get("refusal") is None
                  and bool(np.any(item.observed))]
        if not usable:
            continue
        usable_by_lane[lane.lane_id] = list(usable)
        winner, detail = cal.select_arm(usable, folds)
        out["selected"][lane.lane_id] = dict(detail)
        chosen.append(winner)

    if not chosen:
        out["refusal"] = "every_arm_refused"
        out["seconds"] = time.perf_counter() - started
        return out

    rungs = expand_rungs(config.rungs)
    knobs = {"keep_hard": True, **dict(config.knobs)}
    #: W8 B4: ONE evidence budget per KEY, shared by every rule and every
    #: re-roll set — with 13 lanes one refit round of one rule is 13
    #: recomputations, so the default 26 is two rounds of one rule.
    refit_limit = int(knobs.get("refit_max_evidence",
                                refit_mod.DEFAULT_MAX_EVIDENCE))
    budget: list[int] = [refit_limit]
    certified: tuple[str, str, np.ndarray] | None = None
    #: Every gate-passing certificate this key produces, with the physical
    #: captures it rests on.  Two that agree bit-for-bit on DISJOINT
    #: captures corroborate each other; two that differ are a
    #: contradiction and the key is refused (RULING 2026-09-04, leg 4).
    claims: list[combine_mod.CertificateClaim] = []
    for rule in config.rules:
        combined = combine_mod.combine(chosen, rule, sibling_state=state_seq)
        summary = combine_mod.combine_detail(combined)
        if config.keep_vectors:
            summary["llr_sequential"] = np.asarray(combined.llr_sequential)
        out["combined"][rule] = summary
        rule_knobs = _derived_knobs(
            knobs, combined, state_seq,
            refit_mod.bind(inputs, certs, key, halo, knobs_by_lane,
                           lanes_by_id, tuple(chosen), rule, state_seq,
                           budget, refit_limit))
        results = ladder_mod.run_ladder(
            combined, inputs.row, key, rungs=rungs, knobs=rule_knobs,
            exposure=exposure, metadata_bit=metadata_bit)
        out["rungs"][rule] = results
        claims.extend(_claims_of(results, rule, summary))
        # RULING 2026-09-03 (W4 review D1): a list rung's certificate passed
        # syndrome AND CRC like any other; it mints, cascades and reaches the
        # close.  The quarantine of DESIGN §0 is on the zero-wrong CLAIM — the
        # row keeps the verdict `certified_list` and the run states its
        # exposure beside every count.
        hit = next((item for item in results
                    if item.verdict in (VERDICT_CERTIFIED,
                                        VERDICT_CERTIFIED_LIST)), None)
        if hit is not None and certified is None:
            certified = (rule, hit.rung, np.asarray(hit.user_bits, np.uint8))
            out["certified_verdict"] = hit.verdict
            out["certifying_arm"] = "|".join(
                sorted({item.arm for item in chosen}))
            if not config.all_rules:
                break

    # THE RE-ROLL (`analyzer/GAPS-2026-09-03.md` §7).  The selected arm's
    # ladder has failed and the battery's other arms are already computed —
    # the selection paid for them and used one.  On the C tiles production
    # had to work hardest for, every factor that recovers one moves the
    # soft-information rate by a hundredth across the BP waterfall, so what
    # the parity control lacks against production is ATTEMPTS, not a
    # mechanism.  Each remaining arm's evidence therefore gets its own
    # combination and its own L0/L1, gated by syndrome + CRC like anything
    # else and charged to the same exposure.  Blind throughout: no ground
    # truth reaches this, and the select fold is not consulted again — this
    # is not a second arm choice, it is more rolls of the same dice.
    if certified is None and bool(getattr(config, "reroll", False)):
        reroll_rungs = expand_rungs(
            getattr(config, "reroll_rungs", ("L0", "L1")))
        # W8 B8: the arms PLACED in the re-roll (`reroll_only_arms`) are
        # computed HERE and nowhere else — the selection never saw them,
        # so a key the battery closed never paid for them.  Same knobs,
        # same halo, same lanes as the battery's own arms.
        deferred = config.reroll_battery_for(str(stream_id))
        for arm in deferred:
            for lane in lanes:
                if lane.lane_id not in usable_by_lane:
                    continue
                evidence = arms_mod.evidence_for(
                    inputs, certs, key, lane, arm, halo_cells=halo,
                    knobs=knobs_by_lane[lane.lane_id],
                    crop_memo=crop_memo.for_lane(lane.lane_id))
                out["evidence"][(lane.lane_id, arm)] = dict(evidence.blind)
                if (evidence.blind.get("refusal") is None
                        and bool(np.any(evidence.observed))):
                    usable_by_lane[lane.lane_id].append(evidence)
        sets = combine_mod.reroll_sets(usable_by_lane, chosen)
        out["reroll"] = {"n_sets": len(sets),
                         "arms": [arm for arm, _evidence in sets],
                         "deferred": list(deferred),
                         "rungs": list(reroll_rungs)}
        for arm, evidence_set in sets:
            for rule in config.rules:
                combined = combine_mod.combine(evidence_set, rule,
                                               sibling_state=state_seq)
                label = f"{rule}|reroll:{arm}"
                reroll_summary = combine_mod.combine_detail(combined)
                out["combined"][label] = reroll_summary
                # bound here too, on the SAME budget; `L3f` is not in any
                # default `reroll_rungs`, so this fires only when asked
                rule_knobs = _derived_knobs(
                    knobs, combined, state_seq,
                    refit_mod.bind(inputs, certs, key, halo, knobs_by_lane,
                                   lanes_by_id, tuple(evidence_set), rule,
                                   state_seq, budget, refit_limit))
                results = ladder_mod.run_ladder(
                    combined, inputs.row, key, rungs=reroll_rungs,
                    knobs=rule_knobs, exposure=exposure,
                    metadata_bit=metadata_bit)
                out["rungs"][label] = results
                claims.extend(_claims_of(results, label, reroll_summary))
                hit = next((item for item in results
                            if item.verdict in (VERDICT_CERTIFIED,
                                                VERDICT_CERTIFIED_LIST)),
                           None)
                if hit is not None:
                    certified = (label, hit.rung,
                                 np.asarray(hit.user_bits, np.uint8))
                    out["certified_verdict"] = hit.verdict
                    out["certifying_arm"] = f"reroll:{arm}"
                    break
            if certified is not None:
                break

    certified, agreement = adjudicate(certified, claims)
    out["agreement"] = agreement
    if agreement["contradiction"]:
        out.pop("certified_verdict", None)
        out.pop("certifying_arm", None)
        out["refusal"] = CONTRADICTION_REFUSAL
    if certified is not None:
        out["certifying_rule"], out["certifying_rung"], out["user_bits"] = \
            certified
    out["seconds"] = time.perf_counter() - started
    return out


#: What a row says when two gate-passing certificates disagreed.
CONTRADICTION_REFUSAL = "independent_certificates_disagree"


def adjudicate(certified: tuple[str, str, np.ndarray] | None,
               claims: Sequence[combine_mod.CertificateClaim],
               ) -> tuple[tuple[str, str, np.ndarray] | None, dict]:
    """Leg 4 (RULING 2026-09-04): corroborate, or refuse the key.

    Two gate-passing certificates for one key with different bits both
    passed syndrome and CRC, so at least one is a FALSE ACCEPT and
    nothing blind can say which.  There is no majority to take and no
    tie-break that is not a guess, so the key is refused: no mint, no
    cascade, and the contradiction on the row for the record.  A key
    whose certificates all agree keeps its certificate and carries the
    count of how many of them rest on disjoint captures.
    """
    agreement = combine_mod.independent_agreement(claims)
    return (None if agreement["contradiction"] else certified), agreement


def _claims_of(results: Sequence[Any], label: str,
               summary: Mapping[str, Any]
               ) -> list[combine_mod.CertificateClaim]:
    """The gate-passing certificates one (rule, combination) produced.

    The ladder stops at its first certificate, so this is normally zero
    or one item; it is written over the whole batch anyway, because a
    ladder that ever returns two is exactly the case the contradiction
    check exists for.
    """
    captures = combine_mod.contributing_captures(summary)
    return [combine_mod.CertificateClaim(
        label=str(label), rung=str(item.rung), verdict=str(item.verdict),
        captures=captures,
        user_bits=np.asarray(item.user_bits, np.uint8))
        for item in results
        if item.verdict in (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST)
        and item.user_bits is not None]


# ------------------------------------------------------------- the pass

def _row_for(census_by_key: Mapping[Key, LedgerRow], key: Key) -> LedgerRow:
    row = census_by_key.get(key)
    if row is not None:
        return dc_replace(row)
    page, ty, tx, stream_id = key
    return LedgerRow(page=page, ty=ty, tx=tx, stream_id=stream_id, esi=-1,
                     covered=True, certified_by_production=False,
                     source=None, band="unclassified",
                     band_any="unclassified", neighbours_certified=0,
                     siblings_certified=(), known_cells_in_halo=0,
                     n_discriminating_labels=0, production_attempts={},
                     metadata_known=False)


def _retarget(inputs: Any, key: Key, certified: set[Key],
              attempted: set[Key], known: Mapping[Key, Any] | None = None
              ) -> list[Key]:
    """DESIGN §6b: the 8-neighbourhood plus the tile's other streams.

    `known` is the WORKING certificate mapping, not `inputs.certificates`:
    under `--withhold` (DESIGN §8) a withheld key is not a certificate of
    this pass, and skipping it here would make the cascade unable to
    re-target the very keys the positive control is trying to win back.

    `attempted` is the caller's exclusion set.  `run` passes it EMPTY (the
    W3 cascade ruling: a key attempted in an earlier generation is
    re-attacked, because its frame at attempt time did not hold the
    certificate that triggered this re-target); it stays a parameter so a
    caller that wants one-shot behaviour can still ask for it.
    """
    known = inputs.certificates if known is None else known
    page, ty, tx, stream_id = key
    tiles_y, tiles_x = inputs.tiles_yx
    out: list[Key] = []
    for fact in inputs.row.streams:
        if fact.stream_id != stream_id:
            out.append((page, ty, tx, fact.stream_id))
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = ty + dy, tx + dx
            if 0 <= ny < tiles_y and 0 <= nx < tiles_x:
                out.append((page, ny, nx, stream_id))
    return [item for item in out
            if item not in certified and item not in attempted
            and item not in known]


#: The row verdict's order (2026-09-04).  There is nothing worse than
#: `certified` for a run to say any more: `wrong` and `false_accept` were
#: GT adjudications and left with truth, so a row is `open` without a
#: certificate, `certified` when a direct rung's gate passed, and
#: `certified_list` when only a list rung's did.
VERDICT_PRECEDENCE: tuple[str, ...] = (
    VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST, VERDICT_OPEN)


def row_verdict(rung_verdicts: Sequence[str], *, has_certificate: bool
                ) -> str:
    """The row-level verdict of a tile-stream (DESIGN §0, as amended).

    `rung_verdicts` is every rung verdict the row produced, over every
    rule; `has_certificate` says whether the blind path handed back user
    bits.  A direct-rung certificate outranks a list-rung one, because
    the count that quarantines list rungs from the zero-wrong claim reads
    this column.
    """
    seen = set(str(name) for name in rung_verdicts)
    if not has_certificate:
        return VERDICT_OPEN
    if VERDICT_CERTIFIED in seen:
        return VERDICT_CERTIFIED
    return VERDICT_CERTIFIED_LIST if VERDICT_CERTIFIED_LIST in seen \
        else VERDICT_CERTIFIED


def work_rung_verdicts(work: Mapping[str, Any]) -> list[str]:
    """Every rung verdict a key produced, off the LIVE results.

    The fold reads the same list off the row's rung dicts; this is the
    spelling for a caller that still holds `blind_key`'s output, which
    is what the mint needs a generation earlier.
    """
    return [str(getattr(item, "verdict", ""))
            for batch in (work.get("rungs") or {}).values()
            for item in batch]


def _header(inputs: Any, config: AnalyzerConfig,
            exposure: Exposure, n_targets: int,
            fixed_point: bool = False) -> dict:
    return {
        "seed": int(config.seed),
        "workers": int(config.workers),
        "arms": list(config.arms),
        "refused_arms": list(config.refused_arms),
        "rules": list(config.rules),
        "rungs": list(expand_rungs(config.rungs)),
        "ctx_mode": config.ctx_mode,
        "cover_fraction": float(config.cover_fraction),
        "halo_cells": (None if config.halo_cells is None
                       else dict(config.halo_cells)),
        # WHERE THE HALO CAME FROM (2026-09-07): `knobs_from` used to
        # read `profile:patch+cli` when the only CLI word was
        # `--halo-cells`, and a reader diffing that one field would call
        # it a knob-pinned run.  The halo is an operator axis, not a
        # knob, and it says so on its own line now.
        "halo_from": config.halo_from,
        # R1 (2026-09-06): the CAP and the CONVERGENCE REQUEST are two
        # values, not one.  `max_generations` is the cap the pass ran
        # under whatever asked for it; `fixed_point` says the operator
        # spelled `--fixed-point`.  `stop_reason` (written at the end)
        # says which of them, if either, ended the pass.
        "max_generations": int(config.max_generations),
        "fixed_point": bool(fixed_point),
        "all_rules": bool(config.all_rules),
        "targets_from": config.targets_from,
        "knobs_from": config.knobs_from,
        # W8 B1: the knob VALUES, the re-roll switch and its rungs — two
        # passes that differ only in a knob were indistinguishable on disk.
        "knobs": _jsonable_knobs(config.knobs),
        "reroll": bool(getattr(config, "reroll", False)),
        "reroll_rungs": list(getattr(config, "reroll_rungs", ())),
        # W8 B8: the arms PLACED in the re-roll — a pass that carries the
        # pure path behind the patch battery must say so on disk
        "reroll_only_arms": list(getattr(config, "reroll_only_arms", ())),
        "non_blind": bool(config.non_blind),
        "n_targets": int(n_targets),
        "format_ref": inputs.format_ref,
        "run_dir": str(inputs.run_dir),
        "captures": [{"capture": capture.capture_id, "dpi": capture.dpi,
                      "shape_px": list(capture.shape_px)}
                     for capture in inputs.captures],
        "provenance": dict(inputs.provenance),
        # No `truth` block: a run opens no payload (2026-09-04 ruling).
        # `analyzer score` records which payload IT was scored against, in
        # its own report, where that fact belongs.
        "exposure_bound_expected_false": exposure.bound_expected_false,
    }


def run(inputs: Any, targets: Sequence[Any],
        config: AnalyzerConfig | None = None, *,
        census_rows: Sequence[LedgerRow] | None = None,
        exposure: Exposure | None = None,
        certs: Mapping[Key, Any] | None = None,
        progress: Callable[[str], None] | None = None,
        progress_every: int = PROGRESS_EVERY,
        writer: Any | None = None,
        checkpoint: Any | None = None,
        fixed_point: bool = False) -> Ledger:
    """Drive `targets` to a fixed point and return the ledger (PLAN §1.2).

    `targets` are census `LedgerRow`s or bare keys.  `certs` overrides the
    working certificate mapping (the positive control hands one with the
    withheld keys removed); it is COPIED, and the pass's own certificates
    are folded into the copy, never into `inputs`.  `progress`, when
    given, receives the operator lines of :class:`Progress` and arms its
    status signals for the duration of the pass — and its STOP DOOR
    (`stopdoor`, 2026-09-07): a SIGINT or SIGTERM then ends the pass in
    order at the next consistent point (the keys in flight finish, the
    unstarted ones stay open and unattempted) and the ledger is written
    from here as always, `stop_reason = interrupted` with the two counts
    `keys_done`/`keys_skipped`.  A pass without a sink arms nothing, so a
    library caller's run is untouched.

    The cascade runs at most `config.max_generations` generations and
    stops the moment a generation re-attacks nothing, whatever that cap
    is (R1, 2026-09-06): the cap and the convergence request are
    orthogonal, so nothing here reads `fixed_point` as behaviour — it is
    recorded in the header beside the cap and the `stop_reason`, so a
    ledger says whether the pass CONVERGED or was cut short.

    There is no `truth` argument and no `allow_wrong` escape hatch: the
    2026-09-04 ruling took ground truth out of the run entirely, so the
    only verdicts this can produce are `open`, `certified` and
    `certified_list`.

    `writer` is a `ledger.LedgerWriter`, and it is what a PASS should
    hand in (the memory wave of 2026-09-13): each row goes to disk as
    its generation folds it and NOTHING is kept — `Ledger.rows` comes
    back empty, and the 15-32 GB of rows a 2,700-target pass used to
    hold are one dict of three small values per key.  Every certificate
    also lands in `mints.jsonl` the moment its key returns, which is a
    whole generation earlier than its row and is what a killed pass is
    recovered from.  Without a writer this returns its rows in memory,
    exactly as it always did, which is what the controls and the small
    tests read.

    `checkpoint` is a `stopdoor.Checkpointer`: it writes what the pass
    has done at the first key or generation boundary after each half
    hour, and once more if the operator stops it.
    There is no `--resume` — see `stopdoor.RECOVERY_RECIPE`.
    """
    config = AnalyzerConfig() if config is None else config
    exposure = shared_exposure() if exposure is None else exposure
    census_by_key: dict[Key, LedgerRow] = {}
    for row in (census_rows or ()):
        census_by_key[row.key] = row
    for item in targets:
        if isinstance(item, LedgerRow):
            census_by_key.setdefault(item.key, item)

    keys: list[Key] = [item.key if isinstance(item, LedgerRow)
                       else tuple(item) for item in targets]
    working: dict[Key, Any] = dict(inputs.certificates if certs is None
                                   else certs)
    metadata: dict[Key, int | None] = {}
    ledger = Ledger(exposure=exposure)
    # THIS PASS's identity (M2): minted here, carried to every key's knob
    # bag, and published in the header so a product written beside the
    # ledger can say which of the process memo's fields are this pass's.
    pass_token = next(_PASS_TOKENS)
    ledger.header = _header(inputs, config, exposure, len(keys),
                            fixed_point)
    ledger.header["pass_token"] = pass_token
    if writer is not None:
        # BEFORE generation 0, not after the pass: the header on disk is
        # what makes a killed pass's ledger readable at all.
        writer.start(ledger.header)

    certified: set[Key] = set()
    predecessors: dict[Key, tuple[Key, ...]] = {key: () for key in keys}
    generation_of: dict[Key, int] = {key: 0 for key in keys}
    pending = list(keys)
    started = time.perf_counter()
    row_index: dict[Key, int] = {}
    attempts: dict[Key, int] = {}
    cap = int(config.max_generations)
    #: WHAT THE PASS KEEPS PER KEY once the row is written (2026-09-13):
    #: the generation it was folded in, whether it was corroborated, and
    #: whether it contradicted — the three things the header counts.
    #: Everything else the fixed point re-reads is already here as a set
    #: (`certified`), a small mapping (`predecessors`, `generation_of`,
    #: `attempts`) or the certificate itself (`working`, `ledger.mints`).
    summary: dict[Key, tuple[int, bool, bool]] = {}

    watch = (None if progress is None else
             Progress(progress, n_targets=len(keys), exposure=exposure,
                      every=progress_every))

    def checkpoint_state() -> dict:
        """What a checkpoint says about a pass that is still running."""
        return {
            "generation": generation,
            "generations_cap": cap,
            "fixed_point": bool(fixed_point),
            "stop_requested": bool(getattr(stop, "requested", False)),
            "keys": {
                "targets": len(keys),
                "pending": len(pending),
                "attempted": len(attempts),
                # RETIRED and CERTIFIED are what the pass has FOLDED, and
                # a fold happens at the END of a generation — so inside
                # one they lag `mints_written`, which is the gap the mint
                # file exists to close.  Said in the FILE too: a recovery
                # report is read by whoever finds it.
                "retired_folded": len(summary),
                "certified_folded": len(certified),
                "rows_written": (len(ledger.rows) if writer is None
                                 else int(writer.n_rows)),
                "mints_written": (len(ledger.mints) if writer is None
                                  else int(writer.n_mints)),
                "note": "retired_folded/certified_folded count the keys "
                        "whose GENERATION has folded; a certificate won "
                        "inside the running generation is in "
                        "mints_written and in neither of them yet"},

            # The BLIND CRC-consult ledger (DESIGN §0): a recovery report
            # that does not carry it is claiming an exposure it cannot
            # state, and the bound is what every certificate rests on.
            "exposure": {
                "distinct": int(exposure.distinct),
                "expected_false": float(exposure.expected_false),
                "bound_expected_false": float(exposure.bound_expected_false)},
            "config": {
                "seed": int(config.seed), "workers": int(config.workers),
                "arms": list(config.arms), "rules": list(config.rules),
                "rungs": list(expand_rungs(config.rungs)),
                "halo_cells": (None if config.halo_cells is None
                               else dict(config.halo_cells)),
                "halo_from": config.halo_from,
                "knobs": _jsonable_knobs(config.knobs),
                "knobs_from": config.knobs_from},
            "elapsed": _hms(time.perf_counter() - started),
            "elapsed_seconds": time.perf_counter() - started,
            "run_dir": str(inputs.run_dir),
            "format_ref": inputs.format_ref,
            "ledger": None if writer is None else str(writer.path),
            "mints": None if writer is None else str(writer.mints_path),
            "status": None if watch is None else watch.status(),
        }

    def work_one(key: Key) -> dict | None:
        # The stop door, BEFORE any work: a key the operator's signal
        # beat here is left open and un-attempted, and `None` is the
        # only way to say so — a half-attempted key must never be a row.
        if not stop.begin():
            return None
        bit = metadata.get(key)
        work = blind_key(inputs, snapshot_certs, key, config, exposure,
                         metadata_bit=bit, pass_token=pass_token)
        minted = work.get("user_bits") is not None
        if minted and writer is not None:
            # THE MINT LANDS HERE, a generation before its row: rows fold
            # when the generation's last key returns, and the pass this
            # was written for died inside generation 0 (2026-09-10).  The
            # verdict is decided HERE, by the call the fold makes too, so
            # the mint and the row can never disagree about a key.
            writer.mint(mint_record(
                key, work, generation=generation_of.get(key, 0),
                verdict=row_verdict(work_rung_verdicts(work),
                                    has_certificate=True)))
        if watch is not None:
            watch.key_done(key, minted)
        if checkpoint is not None:
            checkpoint.maybe(checkpoint_state)
        return work

    # Optimistic: every `break` below is a generation that re-attacked
    # nothing, which IS the fixed point.  Only spending the cap with work
    # still pending overwrites this (the `else` arm of the loop).
    stop_reason = STOP_FIXED_POINT
    with _status_doors(watch), stop_door(progress) as stop:
        for generation in range(cap):
            # W3 cascade ruling (2026-09-03, Q2 measurement): a key attempted in
            # an EARLIER generation is re-attacked when a neighbour certifies —
            # its frame at attempt time did not hold that certificate.  Only
            # certified keys and duplicates are dropped; termination comes from
            # `fresh` (every re-target is triggered by a new certificate) and
            # from `max_generations`.
            seen_pending: set[Key] = set()
            pending = [key for key in pending
                       if key not in certified
                       and not (key in seen_pending or seen_pending.add(key))]
            if not pending:
                break
            if watch is not None:
                watch.generation_started(
                    generation, len(pending),
                    sum(1 for key in pending if attempts.get(key, 0)))
            for key in pending:
                attempts[key] = attempts.get(key, 0) + 1
            for key in pending:
                metadata.setdefault(key, inputs_mod.metadata_bit(inputs, key))
            snapshot_certs = dict(working)
            results: dict[Key, dict] = {}
            if int(config.workers) <= 1:
                for key in pending:
                    results[key] = work_one(key)
            else:
                with ThreadPoolExecutor(max_workers=int(config.workers)) as pool:
                    futures = [(key, pool.submit(work_one, key))
                               for key in pending]
                    # DRAINED INTO THE SLOT, not just read out of it: a
                    # `Future` holds its `_result` for as long as anything
                    # holds the future, so this list kept every work dict
                    # of the generation alive through the fold and
                    # `results.pop` freed nothing at workers > 1 (measured
                    # with weakrefs 2026-09-13: 6 of 6 alive where the
                    # serial path had 1).  Emptying the slot drops the
                    # future, and with it the work dict, as it drains.
                    for index, (key, future) in enumerate(futures):
                        results[key] = future.result()
                        futures[index] = None
                    futures = future = None

            fresh: list[Key] = []
            refused = 0
            for key in pending:                     # PINNED order, not completion
                # POPPED, not read: the generation's work dicts are the
                # other half of the pass's memory, and a key's is dead
                # the moment its row is built (memory wave item 5).
                work = results.pop(key, None)
                if work is None:           # the stop door skipped it: no
                    continue               # row, so the key stays OPEN
                if work.get("refusal"):
                    refused += 1
                row = _row_for(census_by_key, key)
                row.generation = generation_of.get(key, generation)
                row.predecessors = predecessors.get(key, ())
                row.evidence = {
                    f"{lane[0][:12]}/l{lane[1]}|{arm}": blind
                    for (lane, arm), blind in work.get("evidence", {}).items()}
                row.evidence["_selected"] = {
                    f"{lane[0][:12]}/l{lane[1]}": detail
                    for lane, detail in work.get("selected", {}).items()}
                row.combined = work.get("combined", {})
                row.rungs = {rule: [_rung_dict(item) for item in batch]
                             for rule, batch in work.get("rungs", {}).items()}
                agreement = work.get("agreement") or {}
                diag = {"seconds": float(work.get("seconds", 0.0)),
                        "n_lanes": int(work.get("n_lanes", 0)),
                        # Leg 4 of the correctness argument, per row: how many
                        # certificates resting on DISJOINT captures agree, and
                        # whether any two contradicted (which refused the key).
                        "independent_agreement": int(
                            agreement.get("independent_agreement", 0)),
                        "n_certificate_claims": int(
                            agreement.get("n_claims", 0)),
                        "contradiction": bool(agreement.get("contradiction",
                                                            False))}
                if work.get("refusal") == CONTRADICTION_REFUSAL:
                    diag["refused_certificate"] = True
                if agreement.get("contradiction"):
                    diag["contradicting"] = agreement.get("contradicting")
                elif agreement.get("independent_claims"):
                    diag["independent_claims"] = agreement["independent_claims"]
                if work.get("refusal"):
                    diag["refusal"] = work["refusal"]
                # The collapsed-field economy, said out loud: how many
                # (lane, arm) rows took an already-computed twin instead
                # of a second evaluation.  Each such row names its twin
                # under `reused_from_arm`.
                if work.get("reused_arms"):
                    diag["reused_arm_evaluations"] = int(work["reused_arms"])
                # W8 B2: the sibling-state COUNTS of the tile, never the
                # 3,976-entry vector (which would ride the row 13 x 12 times)
                diag.update(work.get("diag_state") or {})
                row.diag = diag

                rung_verdicts = [str(item["verdict"])
                                 for batch in row.rungs.values()
                                 if isinstance(batch, list) for item in batch]
                if work.get("user_bits") is not None:
                    row.certifying_rule = work["certifying_rule"]
                    row.certifying_rung = work["certifying_rung"]
                    row.certifying_arm = work.get("certifying_arm")
                    bits = np.asarray(work["user_bits"], np.uint8)
                    row.rungs["user_bits"] = bits
                    working[key] = bits
                    ledger.mints[key] = bits
                    certified.add(key)
                    fresh.append(key)
                # A re-attack REPLACES the key's row.  Nothing needs carrying
                # over the replacement any more: the two STICKY verdicts were
                # `wrong` and `false_accept`, both GT adjudications, and both
                # left with truth (2026-09-04).  `certified`/`open` describe
                # the attempt whose evidence the row now holds, which is
                # exactly what a replacement should say.
                row.verdict = row_verdict(
                    rung_verdicts,
                    has_certificate=work.get("user_bits") is not None)
                row.diag["attempts"] = int(attempts.get(key, 1))
                summary[key] = (
                    int(row.generation or 0),
                    int(row.diag.get("independent_agreement", 0) or 0) >= 2,
                    bool(row.diag.get("contradiction")))
                if writer is not None:
                    # STREAMED: the row is on disk and the driver keeps
                    # none of it.  A re-attacked key APPENDS a second row
                    # rather than replacing the first — a flushed line
                    # cannot be rewritten — and every reader of this file
                    # takes the last row per key (`iter_rows_latest`).
                    writer.append(row)
                elif key in row_index:          # a re-attack replaces its row
                    ledger.rows[row_index[key]] = row
                else:
                    row_index[key] = len(ledger.rows)
                    ledger.rows.append(row)

            if watch is not None:
                watch.generation_finished(generation, len(fresh), refused)
            if checkpoint is not None:
                checkpoint.maybe(checkpoint_state, reason="generation")
            # The drain is over and every finished row is folded, which is
            # where an orderly stop ends: no re-targeting, no next
            # generation, and the ledger written below as always.
            if stop.requested or not fresh:
                break
            nxt: list[Key] = []
            for key in fresh:
                for follow in _retarget(inputs, key, certified, set(),
                                        working):
                    if follow not in nxt:
                        nxt.append(follow)
                    predecessors[follow] = predecessors.get(follow, ()) + (key,)
                    generation_of[follow] = generation + 1
            pending = nxt
        else:
            # The cap was spent.  It BOUND the pass only if the last
            # generation left a re-attack behind; otherwise the pass
            # converged on its last allowed generation and says so.
            if [key for key in pending if key not in certified]:
                stop_reason = STOP_CAP_REACHED

        if stop.requested:
            stop_reason = STOP_INTERRUPTED
        # The header's counts are over KEYS, and they come from the small
        # per-key summary rather than the rows: a streamed pass has no
        # rows left, and a re-attacked key must count once either way.
        ledger.header.update({
            "n_rows": len(summary),
            "n_certified": len(certified),
            "n_corroborated": sum(1 for _gen, corroborated, _contra
                                  in summary.values() if corroborated),
            "n_contradictions": sum(1 for _gen, _corr, contradiction
                                    in summary.values() if contradiction),
            "generations_run": max(
                (gen for gen, _corr, _contra in summary.values()),
                default=0) + 1,
            "stop_reason": stop_reason,
            # Only an interrupted pass carries these: an ordinary ledger
            # header is byte-identical to the one before the door.
            **(stop.counts if stop.requested else {}),
            "seconds": time.perf_counter() - started,
            "exposure_distinct": int(exposure.distinct),
            "exposure_expected_false": float(exposure.expected_false),
        })
        if checkpoint is not None and stop.requested:
            # An orderly stop writes one last checkpoint, so the file
            # beside the ledger describes the pass that was stopped and
            # not the half hour before it.
            checkpoint.write(checkpoint_state(), reason="stop")
        if watch is not None:
            watch.finished(int(ledger.header["generations_run"]))
    return ledger


def targets_from_census(rows: Sequence[LedgerRow], spec: str
                        ) -> list[LedgerRow]:
    """`residue.target_rows`, re-exported so the CLI has one door."""
    return residue_mod.target_rows(rows, spec)
