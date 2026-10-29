"""The decoder ladder: rungs L0-L3 and L7, the gate, verdicts (DESIGN §6).

One combined as-printed sequential LLR vector goes in; a list of
`RungResult` comes out, in the pinned rung order, stopping at the first
certificate.  Every rung proposes a hard vector; only `mother.gate` (syndrome
then the priced CRC) ever certifies one.

Blindness (DESIGN §0, and the 2026-09-04 ruling): this module must not
import `analyzer.truth` or `analyzer.oracle`, and NOTHING here reads a
GT vector any more — the verdict a rung returns is the gate's own.

Rungs built here:

  L0  `prod60`   `tile_codec.cmy8_decode_stream` at 60 - the bit-exact
                 production baseline.  Fed the AS-PRINTED sequential vector:
                 it owns its own un-dither.
  L1  `prod150`  the same at 150 (production's heavy retry).
  L2  `bp`       the analyzer's BP variants over `mother.bp`.
  L3  `ctx`      the turbo context-iterate of DESIGN §6, as RULED after W2:
                 the FOOTPRINT's production-context offsets (fitted by
                 `calibrate` on halo labels), re-applied to the tile's own
                 cells at bins derived from the decoder's EXTRINSIC.  No
                 refit inside the tile — there are no labels there.
  L7a `erase`    down-weight / erase the lanes' disagreeing cells.
  L7b `runs`     blind contiguous-run erasure of low-|posterior| positions.
  L7c `state`    BUILT W8 (2026-09-06): erase the least confident cells of
                 one SIBLING STATE — the format's own statement about
                 which cells are hard, not a decoder's.  Its own rung
                 name: NOT in `DEFAULT_RUNGS` and NOT under the `L7`
                 alias, so no existing profile changes behaviour.
  L3f `feedback` BUILT W8 B4 (2026-09-06), in `refit.py`: the decoder's
                 confident extrinsic bits become typed pseudo labels, the
                 rule's lanes are RECOMPUTED with them behind the `refit`
                 closure the driver binds, recombined under the round-0
                 label view, and BP runs again.  Dispatched from here,
                 never in `DEFAULT_RUNGS` or an alias.  L2 variants may
                 also carry a `temperature` (T1): the channel is scaled
                 before BP and the label says so (`L2:damped@300@t0.8`).
  L4  `flip`     BUILT W4 (2026-09-03): bit-flip hypotheses on the variables
                 incident to the unsatisfied checks, singles then pairs,
                 each followed by a short BP and the gate.  Sheet H's unsat
                 histogram is NOT bimodal (222 rung exits at 5-9 and 234 at
                 10-49 unsatisfied checks out of 7,369), which is what the
                 DESIGN §6 deferral rule asked for before building it; the
                 sheet-I bimodality that deferred it was a sheet fact.

L5 (`osd`) and L6 (`perturb`) stay DEFERRED behind the Q3.2 histograms
(DESIGN §6, review finding B7) and raise NotImplementedError.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import replace as dc_replace

import numpy as np

from holo.receiver.format import keystream, tile_codec
from holo.receiver.format.identity import build_site_geometry
from holo.receiver.lib.ldpc import CODES, LLR_CLIP
from holo.receiver.plugins.calibrate import N_CONTEXT_BINS, apply_context_offsets
from holo.receiver.plugins.color_region_ctx import context_neighbour_counts
from holo.receiver.plugins.tiles import stream_fact

from . import mother as mother_mod
from .types import (
    VERDICT_BELOW_FLOOR,
    VERDICT_CERTIFIED,
    VERDICT_CERTIFIED_LIST,
    VERDICT_OPEN,
    VERDICT_REFUSED,
    Exposure,
    Key,
    Mother,
    RungResult,
)

BP_ALPHA = mother_mod.BP_ALPHA
PROD_BASELINE_ITERS = 60
PROD_RETRY_ITERS = 150

DEFAULT_RUNGS: tuple[str, ...] = ("L0", "L1", "L2", "L4", "L3", "L7a",
                                  "L7b")

# Measured elsewhere as the only decoder changes with value at n = 4096 near
# threshold (DESIGN §6 L2).  Each entry becomes its own RungResult.
# Pinned 2026-09-03 from analyzer/sweeps/l2_variants.py (synthetic bi-AWGN,
# r0850 + r0700, 20 seeds/cell, 69 variants): the greedy union cascade over
# all cells is damped@300 lam=0.5 (71/200) then
# layered@300 lam=0.7 (72/200); production minsum-then-sp@150 alone is 69/200.
# Gains are at the waterfall edge only (r0850 3.5%: 5/20 vs 3/20; r0700 7%:
# 20/20 vs 19/20); everything else in the sweep ties or loses.
DEFAULT_L2_VARIANTS: tuple[dict, ...] = (
    {"mode": "damped", "iters": 300, "lam": 0.5},
    {"mode": "layered", "iters": 300, "lam": 0.7, "beta": 0.0},
)

L3_MAX_ROUNDS = 3
L7B_QUANTILE = 0.10

# L4 (DESIGN §6): the rung is BLINDLY gated on the unsatisfied-check count at
# the entry posterior, so a tile in the >=50 regime never pays for it.  12 is
# the sheet-H histogram's own shoulder: 222 exits sit at 5-9 and 234 at 10-49,
# and a few-bit hypothesis has no purchase above that.  m / m2 / iters are the
# cost dial; measured on synthetic r0850 near-codeword failures in
# `test_analyzer_ladder.py` (see PLAN §6).
L4_MAX_UNSAT = 12
L4_SINGLES = 24
L4_PAIRS = 8
L4_ITERS = 50

_GEOMETRY: dict[str, object] = {}


class DeferredRung(NotImplementedError):
    pass


def osd(*_args, **_kwargs):
    raise DeferredRung(
        "L5 (osd) is DEFERRED behind the same Q3.2 histogram; when built it "
        "lives in analyzer/osd.py per DESIGN §6 L5.")


def perturb(*_args, **_kwargs):
    raise DeferredRung(
        "L6 (perturb) is DEFERRED behind the same Q3.2 histogram "
        "(DESIGN §6).")


def _geometry(row):
    """Cached per FORMAT IDENTITY, never per object identity.

    `id(row)` is reused after a FormatRow is collected, which would hand a
    later row another format's payload cells; `row_id` is the canonical
    format id and determines the geometry exactly.
    """
    cached = _GEOMETRY.get(row.row_id)
    if cached is None:
        cached = build_site_geometry(row)
        _GEOMETRY[row.row_id] = cached
    return cached


def _sequential_llr(combined) -> np.ndarray:
    values = getattr(combined, "llr_sequential", combined)
    return np.asarray(values, np.float64).ravel()


def _support(llr: np.ndarray) -> int:
    return int(np.count_nonzero(llr != 0.0))


def _result(rung: str, verdict: str, *, user_bits=None, n_iters=0, unsat=-1,
            syndrome_ok=False, summary=None, consults=0, seconds=0.0,
            detail=None) -> RungResult:
    return RungResult(rung=rung, verdict=verdict, user_bits=user_bits,
                      n_iters=int(n_iters), unsat_at_exit=int(unsat),
                      syndrome_ok=bool(syndrome_ok),
                      posterior_summary=summary or {},
                      crc_consults_distinct=int(consults),
                      seconds=float(seconds), detail=detail or {})


def _decode_and_gate(mother: Mother, bank, exposure: Exposure, rung: str,
                     *, iters: int, mode: str, alpha: float = BP_ALPHA,
                     lam=None, beta=None, extra: dict | None = None,
                     keep_hard: bool = False,
                     ) -> tuple[RungResult, object]:
    """One BP run through the gate.  Returns (RungResult, BpOut).

    `keep_hard` (W2 addition, driven from `knobs["keep_hard"]`, ON by
    default in the driver since 2026-09-04) packs the exit hard vector
    into `detail["hard_packed"]`.  It is 512 bytes per rung and BLIND (a
    decoder output, not a truth column); the driver base64s it into the
    ledger row, and the OFFLINE scorer counts bits wrong against the GT
    mother codeword from it — DESIGN §6's deferral histogram, computed
    after the run rather than during it.
    """
    started = time.perf_counter()
    out = mother_mod.bp(mother, None, iters, mode=mode, alpha=alpha,
                        lam=lam, beta=beta)
    notes: dict = dict(extra or {})
    notes.update({"mode": mode, "iters": iters, "passes": out.passes})
    ok, user = mother_mod.gate(out.hard, mother, bank, exposure, notes=notes)
    if keep_hard:
        notes["hard_packed"] = np.packbits(
            np.asarray(out.hard, np.uint8)).tobytes()
    return (_result(rung, VERDICT_CERTIFIED if ok else VERDICT_OPEN,
                    user_bits=user, n_iters=out.n_iters, unsat=out.unsat,
                    syndrome_ok=out.syndrome_ok,
                    summary=mother_mod.posterior_summary(out, mother),
                    consults=int(notes.get("consulted_new", 0)),
                    seconds=time.perf_counter() - started, detail=notes),
            out)


def _rung_production(llr_seq: np.ndarray, row, key: Key, bank,
                     exposure: Exposure, *, rung: str, iters: int,
                     metadata_bit, diagnostics: bool,
                     keep_hard: bool = False,
                     ) -> tuple[RungResult, tuple]:
    """L0/L1: the bit-exact production path, plus blind diagnostics.

    `cmy8_decode_stream` returns neither a hard vector nor a posterior, so a
    second `mother.bp` at the same knobs supplies the unsat/posterior
    columns and — when the syndrome closed — the codeword whose CRC consult
    must be charged to the exposure bound.  The two agree bit-for-bit (test
    `test_l2_minsum_then_sp_matches_production`); a disagreement here is a
    convention bug and aborts the run.  Production gets NO metadata bit: L0
    and L1 are the parity baseline.
    """
    started = time.perf_counter()
    dither = mother_mod.dither_of(row, key)
    outcome = tile_codec.cmy8_decode_stream(llr_seq, bank, dither, iters,
                                            BP_ALPHA)
    ok, children, _crc_invoked, crc_ok, user, _soft = outcome
    n_iters = sum(int(n) for n, _s in children)
    syn_ok = all(bool(s) for _n, s in children)
    notes: dict = {"path": "production", "iters": iters,
                   "crc_ok": crc_ok, "n_observed": _support(llr_seq),
                   "metadata_bit_used": False}
    out = None
    mother = None
    if syn_ok or diagnostics:
        mother = mother_mod.to_mother(llr_seq, row, key, metadata_bit=None)
        out = mother_mod.bp(mother, None, iters, mode="minsum-then-sp",
                            alpha=BP_ALPHA)
        if out.syndrome_ok != syn_ok:
            raise AssertionError(
                f"ladder: {rung} mother reframing disagrees with production "
                f"on the syndrome for {key}")
        gate_ok, gate_user = mother_mod.gate(out.hard, mother, bank,
                                             exposure, notes=notes)
        if bool(gate_ok) != bool(ok):
            raise AssertionError(
                f"ladder: {rung} gate disagrees with production for {key}")
        if gate_ok and not np.array_equal(gate_user, user):
            raise AssertionError(
                f"ladder: {rung} user bits disagree with production "
                f"for {key}")
        notes["metadata_bit_available"] = metadata_bit is not None
        if keep_hard:
            notes["hard_packed"] = np.packbits(
                np.asarray(out.hard, np.uint8)).tobytes()
    result = _result(
        rung, VERDICT_CERTIFIED if ok else VERDICT_OPEN,
        user_bits=(None if user is None else np.asarray(user, np.uint8)),
        n_iters=n_iters, unsat=(-1 if out is None else out.unsat),
        syndrome_ok=syn_ok,
        summary=({} if out is None
                 else mother_mod.posterior_summary(out, mother)),
        consults=int(notes.get("consulted_new", 0)),
        seconds=time.perf_counter() - started, detail=notes)
    return result, (out, mother)


def _cell_grid(row, key: Key) -> np.ndarray:
    """Tile-local (y, x) of every SEQUENTIAL position, permuted cell space.

    `tiles._sequential_payload` sets `sequential[order] = physical`, so
    sequential index s lives at physical payload cell
    `payload_flat[argsort(order)[s]]`.
    """
    page, ty, tx, _stream = key
    counter = row.tile_counter(page, ty, tx)
    order = keystream.color_cell_permutation(row.seed, counter,
                                             row.payload_cells)
    inverse = np.empty_like(order)
    inverse[order] = np.arange(order.size, dtype=order.dtype)
    flat = np.asarray(_geometry(row).payload_flat, np.int64)[inverse]
    return np.stack((flat // 64, flat % 64), axis=1)


def _ctx_bins(cells_yx: np.ndarray, ink: np.ndarray) -> np.ndarray:
    """Production's 9-bin context variable: ink over the 8 neighbours.

    A cell whose eight neighbours are not all PRESENT in the domain gets
    bin -1 and no correction — the tile's own border cells, and the cells
    whose neighbours are word/dust furniture rather than payload.
    """
    counts, valid = context_neighbour_counts(cells_yx, np.asarray(ink, bool))
    return np.where(valid, counts.astype(np.int64), -1)


def _ctx_shift(llr: np.ndarray, cells_yx: np.ndarray, ink_from: np.ndarray,
               ink_to: np.ndarray, offsets: np.ndarray,
               ) -> tuple[np.ndarray, dict]:
    """Move the context correction from one bin assignment to another.

    The channel LLR that reaches L3 has ALREADY had the footprint's
    context offsets applied by `calibrate` at bins derived from the
    detector's own provisional ink.  Re-adding them here would double the
    correction, so the rung REMOVES the correction at the channel-derived
    bins and re-applies it at the extrinsic-derived bins:

        out = clamp(llr - offsets[bin_channel] + offsets[bin_extrinsic])

    which is production's `apply_context_offsets` (its clamp included)
    over a channel with the old correction taken off.  Where the two bin
    assignments agree the shift is exactly zero, so round 0 is a no-op
    and the rung can only move cells the decoder disagrees with the
    detector about.
    """
    from_bins = _ctx_bins(cells_yx, ink_from)
    to_bins = _ctx_bins(cells_yx, ink_to)
    removed = llr - np.where(from_bins >= 0, offsets[np.clip(from_bins, 0, 8)],
                             0.0)
    out = apply_context_offsets(removed, to_bins, offsets)
    moved = int(np.count_nonzero((from_bins != to_bins)
                                 & (from_bins >= 0) & (to_bins >= 0)))
    return out, {"n_bins_moved": moved,
                 "n_bins_eligible": int(np.count_nonzero(to_bins >= 0))}


def _rung_ctx_iterate(llr_seq: np.ndarray, row, key: Key, bank,
                      exposure: Exposure, knobs: dict, metadata_bit
                      ) -> list[RungResult]:
    """L3: the turbo contract of DESIGN §6, as RULED 2026-09-03.

    NO REFIT INSIDE THE TILE.  W2 measured the original spelling refusing
    on every real target, and the reason is structural: the target key's
    in-tile cargo carries no known bits by DESIGN §4.5's exclusion
    assertion, so there is nothing in the tile to fit 9 offsets on.  The
    rung therefore APPLIES the offsets the footprint already produced —
    `calibrate`'s production-context fit, made on HALO labels whose own
    neighbours are known — to the tile's cells, and the only thing that
    changes from round to round is which BIN a cell falls in:

      round 0   decode the channel as given (identical to L1);
      round r   provisional ink from the CLIPPED EXTRINSIC of round r-1
                (never the channel, never a hard decision — review
                finding B9), bins recomputed from it, the correction
                shifted from the channel's bins to those (`_ctx_shift`).

    The offsets never change across rounds; only the bins move.  Aborts
    when mean |LLR| grows without reducing the unsatisfied-check count.

    RULING 10 (W8 B2): the APPLY mode is exact for a POOLED correction
    only.  It removes ONE 9-vector at the channel's bins and re-applies
    the same vector at the extrinsic's bins; if a contributing lane
    adopted a per-state residual (C2, `statecal.apply_state_context`),
    the correction sitting in the combined LLR is not one vector any
    more and the shift would remove a correction the cell never had.
    The rung refuses such a row rather than shifting the wrong thing.

    RULING 10 REACHES D1 TOO (review 2026-09-06).  `platt-state` weights
    the LANES per sibling state — a state-s cell is ``w_s @ stack`` while
    `combine.pooled_ctx_offsets` pooled the offsets under the POOLED
    coefficients — so the vector this rung would remove is not the vector
    those cells carry either.  `state_weighted` is that case and it is
    refused with its own reason, so the ledger can tell the two apart.
    """
    if bool(knobs.get("ctx_state_adopted", False)):
        return [_result("L3", VERDICT_REFUSED,
                        detail={"reason": "state_context_adopted"})]
    if bool(knobs.get("state_weighted", False)):
        return [_result("L3", VERDICT_REFUSED,
                        detail={"reason": "state_weighted_combination"})]
    spec = knobs.get("ctx_offsets")
    if spec is None:
        return [_result("L3", VERDICT_REFUSED,
                        detail={"reason": "no_ctx_offsets"})]
    offsets = np.asarray(spec, np.float64).ravel()
    if offsets.size != N_CONTEXT_BINS or not np.all(np.isfinite(offsets)):
        return [_result("L3", VERDICT_REFUSED,
                        detail={"reason": "malformed_ctx_offsets",
                                "n_offsets": int(offsets.size)})]
    if float(np.ptp(offsets)) == 0.0:
        return [_result("L3", VERDICT_REFUSED,
                        detail={"reason": "flat_ctx_offsets"})]
    rounds = int(knobs.get("rounds", L3_MAX_ROUNDS))
    iters = int(knobs.get("iters", PROD_RETRY_ITERS))
    cells_yx = _cell_grid(row, key)
    base = np.asarray(llr_seq, np.float64)
    channel_ink = base > 0.0
    current = base
    shift_detail: dict = {}
    results: list[RungResult] = []
    previous: tuple[int, float] | None = None
    for round_index in range(rounds):
        mother = mother_mod.to_mother(current, row, key,
                                      metadata_bit=metadata_bit)
        result, out = _decode_and_gate(
            mother, bank, exposure, f"L3.r{round_index}", iters=iters,
            mode="minsum-then-sp",
            extra={"round": round_index,
                   "ctx_offsets": tuple(float(value) for value in offsets),
                   **shift_detail},
            keep_hard=bool(knobs.get("keep_hard", False)))
        results.append(result)
        if result.verdict == VERDICT_CERTIFIED:
            break
        if round_index + 1 == rounds:
            break
        mean_abs = float(np.mean(np.abs(current)))
        if previous is not None and (out.unsat >= previous[0]
                                     and mean_abs > previous[1]):
            results.append(_result(f"L3.r{round_index}", VERDICT_REFUSED,
                                   detail={"reason": "llr_growth_no_gain",
                                           "unsat": out.unsat}))
            break
        previous = (out.unsat, mean_abs)
        posterior_seq = mother_mod.to_sequential(out.posterior, mother)
        extrinsic = np.clip(posterior_seq - np.clip(current, -LLR_CLIP,
                                                    LLR_CLIP),
                            -LLR_CLIP, LLR_CLIP)
        current, shift_detail = _ctx_shift(base, cells_yx, channel_ink,
                                           extrinsic > 0.0, offsets)
    return results


def _erase(llr: np.ndarray, positions: np.ndarray, factor: float
           ) -> np.ndarray:
    out = llr.copy()
    out[positions] = out[positions] * factor
    return out


def _rung_erase_disagree(llr_seq: np.ndarray, row, key: Key, bank,
                         exposure: Exposure, knobs: dict, metadata_bit
                         ) -> RungResult:
    """L7a: down-weight the cells the lanes disagree on.

    `knobs['disagree']` is either the sequential indices, or a
    (indices, agreement) pair; the least-agreeing come first and the count is
    capped at n - k - margin so the frame cannot fall below the code's own
    slack.  Production's below-floor refusal (`tiles._attempt_stream`:
    supported < bank_active_bits) is reproduced as an explicit outcome.
    """
    spec = knobs.get("disagree")
    if spec is None:
        return _result("L7a", VERDICT_REFUSED,
                       detail={"reason": "no_disagree_set"})
    if isinstance(spec, tuple) and len(spec) == 2:
        index = np.asarray(spec[0], np.int64).ravel()
        agreement = np.asarray(spec[1], np.float64).ravel()
    else:
        index = np.asarray(spec, np.int64).ravel()
        agreement = np.abs(llr_seq[index])
    if index.size == 0:
        # The lanes agreed everywhere (or there was only one lane to
        # disagree with).  Erasing nothing would re-decode L1's channel and
        # charge its codeword again, so the rung says so instead.
        return _result("L7a", VERDICT_REFUSED,
                       detail={"reason": "no_disagreement",
                               "n_disagreeing": 0})
    active = tile_codec.bank_active_bits(bank)
    margin = int(knobs.get("margin", 0))
    cap = max(llr_seq.size - active - margin, 0)
    order = np.argsort(agreement, kind="stable")[:cap]
    chosen = index[order]
    factor = float(knobs.get("factor", 0.0))
    candidate = _erase(llr_seq, chosen, factor)
    support = _support(candidate)
    detail = {"n_disagreeing": int(index.size), "n_erased": int(chosen.size),
              "cap": int(cap), "factor": factor,
              "bank_active_bits": int(active), "n_observed": int(support)}
    if support < active:
        return _result("L7a", VERDICT_BELOW_FLOOR, detail=detail)
    mother = mother_mod.to_mother(candidate, row, key,
                                  metadata_bit=metadata_bit)
    result, _out = _decode_and_gate(
        mother, bank, exposure, "L7a",
        iters=int(knobs.get("iters", PROD_RETRY_ITERS)),
        mode="minsum-then-sp", extra=detail,
        keep_hard=bool(knobs.get("keep_hard", False)))
    return result


def _rung_erase_state(llr_seq: np.ndarray, row, key: Key, bank,
                      exposure: Exposure, knobs: dict, metadata_bit
                      ) -> RungResult:
    """L7c: erase the least confident cells of ONE sibling state (W8 C3).

    L7a erases where the LANES disagree and L7b where a RUN of positions
    is unreliable; this one erases where the FORMAT says the cell is hard
    — the cells whose two sibling planes are both inked, which on sheet H
    are read 2-4x worse than any other cell of the plane and whose LLRs
    the same measurement found OVER-confident (|L| 2-4 claims 5.8% error
    and measures 15.7%).  An over-confident wrong cell is exactly what BP
    cannot recover from, and an erasure is the one move that costs the
    code slack instead of trust.

    `knobs['sibling_state']` is the per-position state vector the driver
    built once for the key (`statecal.sequential_state`) — from the
    FRAME, never from a decoder output, so this rung reads no decision of
    its own.  Positions of `erase_state` (3 by default: both siblings
    inked) with |L| below `erase_tau` are erased least-confident first,
    capped at `n - k - margin` exactly as L7a, and production's
    below-floor refusal is reproduced.
    """
    spec = knobs.get("sibling_state")
    if spec is None:
        return _result("L7c", VERDICT_REFUSED,
                       detail={"reason": "no_sibling_state"})
    state = np.asarray(spec, np.int8).ravel()
    if state.size != llr_seq.size:
        return _result("L7c", VERDICT_REFUSED,
                       detail={"reason": "malformed_sibling_state",
                               "n_state": int(state.size),
                               "n_positions": int(llr_seq.size)})
    erase_state = int(knobs.get("erase_state", 3))
    tau = float(knobs.get("erase_tau", 2.0))
    in_state = state == erase_state
    magnitude = np.abs(np.asarray(llr_seq, np.float64))
    # A zero LLR is already the erasure spelling; erasing it again buys
    # nothing and would re-charge L1's own codeword.
    index = np.flatnonzero(in_state & (magnitude < tau)
                           & (np.asarray(llr_seq, np.float64) != 0.0))
    if index.size == 0:
        return _result("L7c", VERDICT_REFUSED,
                       detail={"reason": "no_state_cells",
                               "n_state_cells": int(np.count_nonzero(
                                   in_state)),
                               "erase_state": erase_state,
                               "erase_tau": tau})
    active = tile_codec.bank_active_bits(bank)
    margin = int(knobs.get("margin", 0))
    cap = max(llr_seq.size - active - margin, 0)
    order = np.argsort(magnitude[index], kind="stable")[:cap]
    chosen = index[order]
    if chosen.size == 0:
        # The margin ate the whole slack.  Decoding an unmodified channel
        # here would re-charge L1's own codeword for nothing.
        return _result("L7c", VERDICT_REFUSED,
                       detail={"reason": "cap_exhausted", "cap": int(cap),
                               "n_below_tau": int(index.size)})
    factor = float(knobs.get("erase_factor", 0.0))
    candidate = _erase(llr_seq, chosen, factor)
    support = _support(candidate)
    detail = {"n_state_cells": int(np.count_nonzero(in_state)),
              "n_below_tau": int(index.size), "n_erased": int(chosen.size),
              "cap": int(cap), "erase_state": erase_state,
              "erase_tau": tau, "erase_factor": factor,
              "bank_active_bits": int(active), "n_observed": int(support)}
    if support < active:
        return _result("L7c", VERDICT_BELOW_FLOOR, detail=detail)
    mother = mother_mod.to_mother(candidate, row, key,
                                  metadata_bit=metadata_bit)
    result, _out = _decode_and_gate(
        mother, bank, exposure, "L7c",
        iters=int(knobs.get("iters", PROD_RETRY_ITERS)),
        mode="minsum-then-sp", extra=detail,
        keep_hard=bool(knobs.get("keep_hard", False)))
    return result


def _runs_of(mask: np.ndarray) -> list[tuple[int, int]]:
    if not mask.any():
        return []
    padded = np.concatenate(([False], mask, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return list(zip(edges[0::2].tolist(), edges[1::2].tolist()))


def _rung_erase_runs(llr_seq: np.ndarray, row, key: Key, bank,
                     exposure: Exposure, knobs: dict, metadata_bit,
                     posterior_seq: np.ndarray | None) -> RungResult:
    """L7b: blind contiguous-run erasure of low-|posterior| positions.

    Errors cluster in sequential order when a band of cells is misread; the
    longest runs of unreliable positions are erased whole, capped at the same
    n - k - margin slack.  Reliability is |Ltot|, never |extrinsic|.
    """
    if posterior_seq is None:
        mother0 = mother_mod.to_mother(llr_seq, row, key,
                                       metadata_bit=metadata_bit)
        out0 = mother_mod.bp(mother0, None, PROD_BASELINE_ITERS,
                             mode="minsum-then-sp")
        posterior_seq = mother_mod.to_sequential(out0.posterior, mother0)
    reliability = np.abs(posterior_seq)
    quantile = float(knobs.get("threshold", L7B_QUANTILE))
    cut = float(np.quantile(reliability, quantile))
    runs = sorted(_runs_of(reliability <= cut),
                  key=lambda run: run[1] - run[0], reverse=True)
    active = tile_codec.bank_active_bits(bank)
    cap = max(llr_seq.size - active - int(knobs.get("margin", 0)), 0)
    chosen: list[int] = []
    n_runs = 0
    for start, stop in runs:
        if len(chosen) + (stop - start) > cap:
            continue
        chosen.extend(range(start, stop))
        n_runs += 1
    index = np.asarray(chosen, np.int64)
    candidate = _erase(llr_seq, index, 0.0)
    support = _support(candidate)
    detail = {"n_erased": int(index.size), "n_runs": n_runs, "cap": int(cap),
              "threshold_quantile": quantile, "reliability_cut": cut,
              "bank_active_bits": int(active), "n_observed": int(support)}
    if support < active:
        return _result("L7b", VERDICT_BELOW_FLOOR, detail=detail)
    mother = mother_mod.to_mother(candidate, row, key,
                                  metadata_bit=metadata_bit)
    result, _out = _decode_and_gate(
        mother, bank, exposure, "L7b",
        iters=int(knobs.get("iters", PROD_RETRY_ITERS)),
        mode="minsum-then-sp", extra=detail,
        keep_hard=bool(knobs.get("keep_hard", False)))
    return result


def _check_variables(code, syndrome_vector: np.ndarray) -> np.ndarray:
    """The variables incident to the UNSATISFIED checks, de-duplicated.

    `Code` carries the parity-check matrix as edge lists sorted by check, so
    check c owns the edge slice `[chk_starts[c], chk_starts[c+1])` and its
    variables are `edge_var` over that slice.  This is the check->variables
    map DESIGN §6 L4 asks for, built without materialising H.
    """
    rows = np.flatnonzero(np.asarray(syndrome_vector, np.uint8))
    if not rows.size:
        return np.zeros(0, np.int64)
    starts = np.asarray(code.chk_starts, np.int64)
    ends = np.concatenate((starts[1:], [code.edge_var.size]))
    return np.unique(np.concatenate(
        [np.asarray(code.edge_var[starts[c]:ends[c]], np.int64)
         for c in rows]))


def _forbidden_positions(mother: Mother) -> np.ndarray:
    """Positions a hypothesis may never touch (DESIGN §0, §6 L4).

    The shortened window `[active, k)` is format-known and the metadata bit
    at info index 0 is trusted evidence when it was injected; flipping either
    proposes a vector the printer could not have produced, and `mother.gate`
    would refuse it anyway (`shortening_violated`).  Every non-finite channel
    entry is forbidden for the same reason, which is the same set spelled
    from the frame rather than from the format.
    """
    mask = ~np.isfinite(mother.llr)
    if mother.active < mother.k_bits:
        mask[mother.active:mother.k_bits] = True
    return mask


def _flip_signs(posterior: np.ndarray, hard: np.ndarray,
                positions: np.ndarray) -> np.ndarray:
    """`-sign(Ltot)` at `positions`, as +-inf (= +-LLR_KNOWN downstream).

    `mother.clipped_external` maps +-inf to +-LLR_KNOWN, which is the ONE
    door a hypothesis enters by (DESIGN §0: the bounded-LLR invariant binds
    CHANNEL evidence, and a hypothesis is not channel evidence).  A posterior
    of exactly zero falls back to the hard bit, which the posterior identity
    says carries the same sign.
    """
    post = np.asarray(posterior, np.float64)[positions]
    sign = np.where(post != 0.0, np.sign(post),
                    2.0 * np.asarray(hard, np.float64)[positions] - 1.0)
    return np.where(sign > 0.0, -np.inf, np.inf)


def _flip_source(states):
    """L4's entry posterior: the best L2 variant, else L1's, else L0's.

    "Best" is BLIND — the fewest unsatisfied checks at exit — and the
    preference order is the ladder's own: L2's variants are the strongest
    decoders on the same channel, and L1/L0 are the production frames the
    rung falls back to when L2 did not run.
    """
    for prefix in ("L2", "L1", "L0"):
        pool = [item for item in states if item[0].startswith(prefix)]
        if pool:
            return min(pool, key=lambda item: int(item[1].unsat))
    return None


def _rung_flip(row, key: Key, bank, exposure: Exposure, knobs: dict,
               state) -> RungResult:
    """L4: bit-flip hypotheses on the unsatisfied checks' variables.

    Entry is the best posterior the earlier rungs of THIS rule produced
    (`state` = the L2 variant with the fewest unsatisfied checks, else L1's,
    else L0's), because that is the frame whose syndrome names the suspects.
    The rung is gated BLINDLY on that frame's `unsat_at_exit`: at or below
    `flip_max_unsat` a handful of bits can plausibly be wrong, above it the
    tile is in the >=50 regime and L4 buys nothing but exposure.

    Candidates are the variables incident to the unsatisfied checks, ranked
    by |Ltot| ASCENDING (least reliable first), with the format-known and
    metadata positions removed.  Singles over the first `flip_m`, then all
    pairs over the first `flip_m2`; each hypothesis is a channel LLR pinned
    at -sign(Ltot)*LLR_KNOWN, re-decoded by a short BP and put through
    `mother.gate` (syndrome THEN the priced CRC).  The first certificate
    stops the rung.

    Verdict `certified_list` (DESIGN §0): L4 is a list rung, so its
    certificates are quarantined from a zero-wrong claim until the run's
    exposure is stated beside them.  `n_iters` is the rung's TOTAL BP
    iterations (its cost), not one decode's.
    """
    started = time.perf_counter()
    if state is None:
        return _result("L4", VERDICT_REFUSED,
                       detail={"reason": "no_entry_posterior"},
                       seconds=time.perf_counter() - started)
    source, out, mother = state
    limit = int(knobs.get("flip_max_unsat", L4_MAX_UNSAT))
    detail: dict = {"source_rung": source, "unsat_at_entry": int(out.unsat),
                    "flip_max_unsat": limit,
                    "metadata_bit_used": mother.metadata_bit is not None}
    if out.unsat > limit or out.unsat == 0:
        detail["reason"] = ("unsat_above_gate" if out.unsat > limit
                            else "no_unsatisfied_checks")
        return _result("L4", VERDICT_REFUSED, unsat=out.unsat,
                       detail=detail, seconds=time.perf_counter() - started)

    code = mother_mod.code_of(mother)
    variables = _check_variables(code, out.syndrome)
    forbidden = _forbidden_positions(mother)
    detail["n_incident"] = int(variables.size)
    detail["n_forbidden_dropped"] = int(np.count_nonzero(
        forbidden[variables])) if variables.size else 0
    variables = variables[~forbidden[variables]] if variables.size else \
        variables
    ranked = variables[np.argsort(np.abs(out.posterior[variables]),
                                  kind="stable")] if variables.size else \
        variables
    m_singles = int(knobs.get("flip_m", L4_SINGLES))
    m_pairs = int(knobs.get("flip_m2", L4_PAIRS))
    iters = int(knobs.get("flip_iters", L4_ITERS))
    plan = [(int(v),) for v in ranked[:m_singles]]
    heads = [int(v) for v in ranked[:m_pairs]]
    plan.extend(itertools.combinations(heads, 2))

    n_candidates = 0
    n_syndrome_ok = 0
    n_iters_total = 0
    consults = 0
    best_unsat = int(out.unsat)
    certified: np.ndarray | None = None
    refusal: str | None = None
    for positions in plan:
        index = np.asarray(positions, np.int64)
        llr = mother.llr.copy()
        llr[index] = _flip_signs(out.posterior, out.hard, index)
        candidate = dc_replace(mother, llr=llr)
        trial = mother_mod.bp(candidate, code, iters, mode="minsum-then-sp")
        n_candidates += 1
        n_iters_total += int(trial.n_iters)
        best_unsat = min(best_unsat, int(trial.unsat))
        if trial.syndrome_ok:
            n_syndrome_ok += 1
        notes: dict = {}
        ok, user = mother_mod.gate(trial.hard, candidate, bank, exposure,
                                   notes=notes)
        consults += int(notes.get("consulted_new", 0))
        if notes.get("refusal") == "exposure_exceeded":
            refusal = "exposure_exceeded"
            break
        if ok:
            certified = np.asarray(user, np.uint8)
            detail["certifying_positions"] = tuple(int(v) for v in index)
            detail["certifying_iters"] = int(trial.n_iters)
            break
    detail.update({"n_candidates": n_candidates,
                   "n_syndrome_ok": n_syndrome_ok,
                   "n_singles": min(len(ranked), m_singles),
                   "n_pairs": max(len(plan) - min(len(ranked), m_singles), 0),
                   "best_unsat": best_unsat,
                   "iters": iters, "n_iters_total": n_iters_total})
    if refusal is not None:
        detail["reason"] = refusal
        return _result("L4", VERDICT_REFUSED, unsat=best_unsat,
                       consults=consults, detail=detail,
                       seconds=time.perf_counter() - started)
    if not plan:
        detail["reason"] = "no_candidate_variables"
        return _result("L4", VERDICT_REFUSED, unsat=best_unsat,
                       detail=detail, seconds=time.perf_counter() - started)
    return _result("L4",
                   VERDICT_CERTIFIED_LIST if certified is not None
                   else VERDICT_OPEN,
                   user_bits=certified, n_iters=n_iters_total,
                   unsat=best_unsat, syndrome_ok=certified is not None,
                   summary=mother_mod.posterior_summary(out, mother),
                   consults=consults, detail=detail,
                   seconds=time.perf_counter() - started)


def _run_rungs(llr_seq: np.ndarray, row, key: Key, *, rungs, knobs,
               exposure: Exposure, metadata_bit) -> list[RungResult]:
    """Blind: no ground truth reaches this function or anything it calls."""
    bank = stream_fact(row, key[3]).rung_children
    keep_hard = bool(knobs.get("keep_hard", False))
    results: list[RungResult] = []
    posterior_seq: np.ndarray | None = None
    #: (rung, BpOut, Mother) per decode, so L4 can enter at the best
    #: posterior this rule has produced so far (DESIGN §6 L4).
    states: list[tuple[str, object, Mother]] = []
    for name in rungs:
        if name in ("L5", "L6"):
            {"L5": osd, "L6": perturb}[name]()
        if name in ("L0", "L1"):
            iters = (PROD_BASELINE_ITERS if name == "L0"
                     else PROD_RETRY_ITERS)
            result, (out, mother) = _rung_production(
                llr_seq, row, key, bank, exposure, rung=name, iters=iters,
                metadata_bit=metadata_bit,
                diagnostics=bool(knobs.get("diagnostics", True)),
                keep_hard=keep_hard)
            if out is not None:
                posterior_seq = mother_mod.to_sequential(out.posterior,
                                                         mother)
                states.append((name, out, mother))
            batch = [result]
        elif name == "L2":
            shared = mother_mod.to_mother(llr_seq, row, key,
                                          metadata_bit=metadata_bit)
            batch = []
            for variant in knobs.get("L2", DEFAULT_L2_VARIANTS):
                spec = dict(variant)
                mode = spec.pop("mode", "minsum-then-sp")
                iters = int(spec.pop("iters", PROD_RETRY_ITERS))
                # T1 (W8 B4): a variant may scale the channel before BP —
                # multi-lane sums on a print-frozen channel are
                # over-confident.  At 1.0 the shared mother is used
                # verbatim and the variant's label and detail are exactly
                # what they were.
                temperature = float(spec.pop("temperature", 1.0))
                label = f"L2:{mode}@{iters}"
                mother = shared
                if temperature != 1.0:
                    label += f"@t{temperature:g}"
                    spec["temperature"] = temperature
                    mother = mother_mod.to_mother(
                        np.asarray(llr_seq, np.float64) * temperature, row,
                        key, metadata_bit=metadata_bit)
                result, out = _decode_and_gate(
                    mother, bank, exposure, label,
                    iters=iters, mode=mode, extra=spec,
                    lam=spec.get("lam"), beta=spec.get("beta"),
                    alpha=float(spec.get("alpha", BP_ALPHA)),
                    keep_hard=keep_hard)
                posterior_seq = mother_mod.to_sequential(out.posterior,
                                                         mother)
                states.append((label, out, mother))
                batch.append(result)
                if result.verdict == VERDICT_CERTIFIED:
                    break
        elif name == "L4":
            state = _flip_source(states)
            if state is None:
                mother = mother_mod.to_mother(llr_seq, row, key,
                                              metadata_bit=metadata_bit)
                out = mother_mod.bp(mother, None, PROD_RETRY_ITERS,
                                    mode="minsum-then-sp")
                state = ("L4.entry", out, mother)
            batch = [_rung_flip(row, key, bank, exposure, knobs, state)]
        elif name == "L3":
            batch = _rung_ctx_iterate(llr_seq, row, key, bank, exposure,
                                      knobs, metadata_bit)
        elif name == "L7a":
            batch = [_rung_erase_disagree(llr_seq, row, key, bank, exposure,
                                          knobs, metadata_bit)]
        elif name == "L7b":
            batch = [_rung_erase_runs(llr_seq, row, key, bank, exposure,
                                      knobs, metadata_bit, posterior_seq)]
        elif name == "L7c":
            batch = [_rung_erase_state(llr_seq, row, key, bank, exposure,
                                       knobs, metadata_bit)]
        elif name == "L3f":
            # W8 B4 (ruling 3): the decoder-feedback rung lives in
            # `refit.py`; the import is function-local because `refit`
            # imports this module's helpers the same way.  Its own name:
            # NOT in `DEFAULT_RUNGS`, NOT under any alias.
            from . import refit as refit_mod
            batch = refit_mod.rung_feedback(llr_seq, row, key, bank,
                                            exposure, knobs, metadata_bit,
                                            states)
        else:
            raise ValueError(f"ladder: unknown rung {name!r}")
        results.extend(batch)
        if any(item.verdict in (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST)
               for item in batch):
            break
    return results


def run_ladder(combined, row, key: Key, *, rungs=DEFAULT_RUNGS,
               knobs: dict | None = None, exposure: Exposure | None = None,
               metadata_bit: int | None = None) -> list[RungResult]:
    """Climb the ladder for one tile-stream; the first certificate stops it.

    `combined` is a `Combined` or a bare as-printed sequential LLR vector.

    RULING 2026-09-04: there is no `truth_bits` door any more.  This
    module used to end in a `score_rung` that turned a CRC match
    disagreeing with GT into `wrong`/`false_accept`; that adjudication
    is the OFFLINE scorer's (`analyzer.score.verdict_against_truth`),
    and a gate-passing certificate here is `certified` (direct rung) or
    `certified_list` (list rung), full stop.
    """
    llr_seq = _sequential_llr(combined)
    # PLAN §1.2 spells the second argument `inputs`; everything here needs
    # only its `row`, so a RunInputs and a bare FormatRow are both accepted.
    row = getattr(row, "row", row)
    exposure = Exposure() if exposure is None else exposure
    return _run_rungs(llr_seq, row, key, rungs=tuple(rungs),
                      knobs=dict(knobs or {}), exposure=exposure,
                      metadata_bit=metadata_bit)


def bits_wrong_denominators(row, stream_id: str) -> dict[str, int]:
    """The four denominators a bits-wrong column may quote (DESIGN §6)."""
    bank = stream_fact(row, stream_id).rung_children
    code_id, shorten = bank[0]
    code = CODES[code_id]
    return {"mother": code.n_bits,
            "transmitted": code.n_bits - shorten,
            "active": code.k_bits - shorten,
            "user": code.k_bits - shorten - tile_codec.CRC_BITS}
