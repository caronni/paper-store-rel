"""W1c tests for analyzer/ladder.py (rungs, verdicts, exposure, blindness).

Synthetic frames only; the ladder's own knobs are cut small so the suite
stays seconds, not minutes.  The deferral of L4/L5/L6 is asserted here as a
property of the code, not left to prose.
"""

from __future__ import annotations

import ast
import pathlib

import numpy as np
import pytest

from holo3.format import tile_codec
from holo3.lib.ldpc import LLR_CLIP, LLR_KNOWN

from analyzer import ladder as L
from analyzer import mother as M
from analyzer.types import (
    VERDICT_BELOW_FLOOR,
    VERDICT_CERTIFIED,
    VERDICT_CERTIFIED_LIST,
    VERDICT_OPEN,
    VERDICT_REFUSED,
    VERDICT_WRONG,
    Exposure,
)

from ._synthetic import (R0700, R0850, build_frame, channel_llr,
                         near_codeword_llr)

FAST_L2 = ({"mode": "minsum-then-sp", "iters": 60},
           {"mode": "damped", "iters": 60, "lam": 0.7},
           {"mode": "layered", "iters": 20})


def clean(ref=R0850, hard=0.03, seed=101):
    frame = build_frame(ref)
    return frame, channel_llr(frame.printed, hard, seed=seed)


def broken(ref=R0850, hard=0.08, seed=202):
    frame = build_frame(ref)
    return frame, channel_llr(frame.printed, hard, seed=seed)


@pytest.mark.parametrize("ref,hard", [(R0850, 0.03), (R0700, 0.06)])
def test_l0_certifies_and_stops_the_ladder(ref, hard):
    frame, llr = clean(ref, hard)
    exposure = Exposure()
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L0", "L1"),
                           knobs={}, exposure=exposure,
                           metadata_bit=int(frame.user[0]))
    assert [item.rung for item in results] == ["L0"]
    assert results[0].verdict == VERDICT_CERTIFIED
    assert np.array_equal(results[0].user_bits, frame.user)
    assert results[0].unsat_at_exit == 0 and results[0].syndrome_ok
    assert results[0].crc_consults_distinct == 1
    assert exposure.distinct == 1
    assert results[0].detail["metadata_bit_used"] is False
    # No `gt_bits_wrong`: the rung's detail is BLIND (2026-09-04).  That
    # the bits are right is asserted above, against the synthetic
    # frame's own user vector, which is the test's fixture and not a
    # column the ladder produced.
    assert "gt_bits_wrong" not in results[0].detail


def test_a_failing_frame_walks_every_rung_and_records_refusals():
    frame, llr = broken()
    exposure = Exposure()
    results = L.run_ladder(
        llr, frame.row, frame.key,
        rungs=("L0", "L1", "L2", "L3", "L7a", "L7b"),
        knobs={"L2": FAST_L2, "iters": 60}, exposure=exposure,
        metadata_bit=None)
    rungs = [item.rung for item in results]
    assert rungs[:2] == ["L0", "L1"]
    assert any(item.startswith("L2:") for item in rungs)
    assert "L3" in rungs and "L7a" in rungs and "L7b" in rungs
    by_rung = {item.rung: item for item in results}
    assert by_rung["L3"].verdict == VERDICT_REFUSED
    assert by_rung["L3"].detail["reason"] == "no_ctx_offsets"
    assert by_rung["L7a"].verdict == VERDICT_REFUSED
    assert by_rung["L7a"].detail["reason"] == "no_disagree_set"
    assert by_rung["L7b"].verdict in (VERDICT_OPEN, VERDICT_BELOW_FLOOR)
    # Blind columns are populated on every attempted rung.
    for item in results:
        if item.verdict in (VERDICT_OPEN, VERDICT_CERTIFIED):
            assert item.unsat_at_exit >= 0
            assert item.posterior_summary["n_transmitted"] == 3976
            assert item.seconds >= 0.0
    assert all(item.verdict != VERDICT_WRONG for item in results)


def test_l0_diagnostics_report_the_unsat_histogram_input():
    frame, llr = broken()
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L0",),
                           knobs={}, exposure=Exposure(), metadata_bit=None)
    assert results[0].verdict == VERDICT_OPEN
    assert results[0].unsat_at_exit > 0
    assert results[0].n_iters == 120  # 60 min-sum + 60 sum-product
    assert results[0].detail["n_observed"] == 3976


def test_l0_without_diagnostics_leaves_unsat_unmeasured():
    frame, llr = broken()
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L0",),
                           knobs={"diagnostics": False},
                           exposure=Exposure(), metadata_bit=None)
    assert results[0].unsat_at_exit == -1
    assert results[0].posterior_summary == {}


def test_l2_variants_each_get_their_own_row():
    frame, llr = broken()
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L2",),
                           knobs={"L2": FAST_L2}, exposure=Exposure(),
                           metadata_bit=None)
    assert [item.rung for item in results] == [
        "L2:minsum-then-sp@60", "L2:damped@60", "L2:layered@20"]
    assert results[0].detail["mode"] == "minsum-then-sp"
    assert results[0].detail["passes"] == 2
    assert results[1].detail["lam"] == 0.7


def test_l2_minsum_then_sp_reproduces_l0_on_a_failing_frame():
    """The classic bug guard: a missing shortening or a double dither."""
    frame, llr = broken()
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    out = M.bp(mother, None, 60, mode="minsum-then-sp")
    undithered = llr * (1.0 - 2.0 * frame.dither)
    _ok, children, _inv, _crc, _user, soft = tile_codec.decode_frame(
        undithered, frame.bank, 60, 0.8, want_extrinsic=True)
    assert out.n_iters == sum(n for n, _s in children)
    extrinsic = out.posterior - M.clipped_external(mother.llr)
    assert np.array_equal(extrinsic[mother.transmitted], soft)


def test_l3_refuses_without_ctx_offsets():
    frame, llr = broken()
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L3",),
                           knobs={}, exposure=Exposure(), metadata_bit=None)
    assert results[0].verdict == VERDICT_REFUSED
    assert results[0].detail["reason"] == "no_ctx_offsets"


def test_l3_refuses_flat_or_malformed_ctx_offsets():
    frame, llr = broken()
    flat = L.run_ladder(llr, frame.row, frame.key, rungs=("L3",),
                        knobs={"ctx_offsets": [0.0] * 9},
                        exposure=Exposure(), metadata_bit=None)
    assert flat[0].verdict == VERDICT_REFUSED
    assert flat[0].detail["reason"] == "flat_ctx_offsets"
    short = L.run_ladder(llr, frame.row, frame.key, rungs=("L3",),
                         knobs={"ctx_offsets": [0.1, -0.1]},
                         exposure=Exposure(), metadata_bit=None)
    assert short[0].verdict == VERDICT_REFUSED
    assert short[0].detail["reason"] == "malformed_ctx_offsets"


def test_l3_applies_footprint_offsets_over_rounds_without_a_refit():
    frame, llr = broken(hard=0.06, seed=303)
    offsets = [0.4, 0.3, 0.2, 0.1, 0.0, -0.1, -0.2, -0.3, -0.4]
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L3",),
                           knobs={"ctx_offsets": offsets, "rounds": 3,
                                  "iters": 60},
                           exposure=Exposure(), metadata_bit=None)
    assert results, "L3 produced no rows"
    assert all(item.rung.startswith("L3.r") for item in results)
    assert tuple(results[0].detail["ctx_offsets"]) == tuple(offsets)
    assert all(item.verdict != VERDICT_WRONG for item in results)


def test_l3_round_zero_is_the_channel_and_the_offsets_never_move():
    """The apply-only contract: the bins move, the offsets do not."""
    frame, llr = broken(hard=0.06, seed=303)
    offsets = [0.4, 0.3, 0.2, 0.1, 0.0, -0.1, -0.2, -0.3, -0.4]
    knobs = {"ctx_offsets": offsets, "rounds": 3, "iters": 60}
    l3 = L.run_ladder(llr, frame.row, frame.key, rungs=("L3",),
                      knobs=knobs, exposure=Exposure(), metadata_bit=None)
    l1 = L.run_ladder(llr, frame.row, frame.key, rungs=("L1",),
                      knobs={}, exposure=Exposure(), metadata_bit=None)
    # round 0 decodes the channel as given, so it IS L1 at these iterations
    assert l3[0].rung == "L3.r0"
    assert l3[0].unsat_at_exit == l1[0].unsat_at_exit
    assert "n_bins_moved" not in l3[0].detail   # nothing shifted yet
    for item in l3:
        if item.verdict == VERDICT_REFUSED:
            continue
        assert tuple(item.detail["ctx_offsets"]) == tuple(offsets)
    later = [item for item in l3 if "n_bins_moved" in item.detail]
    assert later, "no round applied the shift"
    for item in later:
        assert 0 <= item.detail["n_bins_moved"] <= \
            item.detail["n_bins_eligible"]


def test_l7a_erases_the_disagreeing_cells_within_the_cap():
    frame, llr = broken(hard=0.06, seed=404)
    rng = np.random.default_rng(6)
    disagree = rng.choice(frame.printed.size, 100, replace=False)
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L7a",),
                           knobs={"disagree": disagree, "factor": 0.0,
                                  "iters": 60},
                           exposure=Exposure(), metadata_bit=None)
    detail = results[0].detail
    assert detail["n_disagreeing"] == 100
    assert detail["n_erased"] == 100
    assert detail["cap"] == 3976 - 3400
    assert detail["n_observed"] == 3976 - 100
    assert results[0].verdict in (VERDICT_OPEN, VERDICT_CERTIFIED)


def test_l7a_reproduces_the_below_floor_refusal():
    frame, llr = broken()
    llr = llr.copy()
    llr[:500] = 0.0                       # already unobserved
    disagree = np.arange(500, 700)        # 200 more erasures
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L7a",),
                           knobs={"disagree": disagree, "factor": 0.0},
                           exposure=Exposure(), metadata_bit=None)
    assert results[0].verdict == VERDICT_BELOW_FLOOR
    assert results[0].detail["n_observed"] == 3976 - 700
    assert results[0].detail["bank_active_bits"] == 3400
    assert results[0].crc_consults_distinct == 0


def test_l7a_caps_the_erasures_at_the_codes_slack():
    frame, llr = broken()
    disagree = np.arange(1500)            # far more than n - k
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L7a",),
                           knobs={"disagree": disagree, "factor": 0.0,
                                  "margin": 20, "iters": 30},
                           exposure=Exposure(), metadata_bit=None)
    assert results[0].detail["n_erased"] == 3976 - 3400 - 20
    assert results[0].verdict != VERDICT_BELOW_FLOOR


def test_l7b_erases_contiguous_runs_of_unreliable_positions():
    frame, llr = broken(hard=0.06, seed=505)
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L7b",),
                           knobs={"threshold": 0.05, "iters": 60},
                           exposure=Exposure(), metadata_bit=None)
    detail = results[0].detail
    assert detail["n_runs"] >= 1
    assert 0 < detail["n_erased"] <= detail["cap"]
    assert detail["n_observed"] == 3976 - detail["n_erased"]


def test_runs_of_finds_maximal_runs():
    mask = np.array([0, 1, 1, 0, 0, 1, 0, 1, 1, 1], bool)
    assert L._runs_of(mask) == [(1, 3), (5, 6), (7, 10)]
    assert L._runs_of(np.zeros(5, bool)) == []


# `score_rung` is GONE from this module (2026-09-04): the verdict a
# certificate gets against a payload is the offline scorer's, and its
# tests moved with it to `test_analyzer_score.py`.  What stays here is
# the pin that nothing in the ladder can read a GT vector at all
# (`test_ladder_is_blind` below).


@pytest.mark.parametrize("name", ["L5", "L6"])
def test_deferred_rungs_are_named_stubs_that_refuse(name):
    frame, llr = broken()
    with pytest.raises(NotImplementedError) as excinfo:
        L.run_ladder(llr, frame.row, frame.key, rungs=(name,), knobs={},
                     exposure=Exposure(), metadata_bit=None)
    assert "DEFERRED" in str(excinfo.value)


def test_unknown_rung_is_refused():
    frame, llr = broken()
    with pytest.raises(ValueError):
        L.run_ladder(llr, frame.row, frame.key, rungs=("L9",), knobs={},
                     exposure=Exposure(), metadata_bit=None)


def test_exposure_accumulates_across_rungs_and_de_duplicates():
    frame, llr = clean()
    exposure = Exposure()
    L.run_ladder(llr, frame.row, frame.key, rungs=("L0",), knobs={},
                 exposure=exposure, metadata_bit=None)
    L.run_ladder(llr, frame.row, frame.key, rungs=("L0",), knobs={},
                 exposure=exposure, metadata_bit=None)
    assert exposure.distinct == 1            # same codeword, one consult
    assert exposure.expected_false == 2.0 ** -32
    assert not exposure.exceeded()


def test_a_wrong_metadata_bit_kills_the_frame():
    """Measured (20 seeds, r0850 at 3.3-3.7% hard error): the right bit buys
    nothing at 60 iterations (12/20 vs 12/20 at 3.3%), the wrong bit costs
    everything (0/20).  The bar here is only the second half.
    """
    frame, llr = clean(hard=0.03)
    right = L.run_ladder(llr, frame.row, frame.key, rungs=("L2",),
                         knobs={"L2": ({"mode": "minsum-then-sp",
                                        "iters": 60},)},
                         exposure=Exposure(),
                         metadata_bit=int(frame.user[0]))
    assert right[0].verdict == VERDICT_CERTIFIED
    wrong = L.run_ladder(llr, frame.row, frame.key, rungs=("L2",),
                         knobs={"L2": ({"mode": "minsum-then-sp",
                                        "iters": 60},)},
                         exposure=Exposure(),
                         metadata_bit=1 - int(frame.user[0]))
    assert wrong[0].verdict == VERDICT_OPEN
    assert wrong[0].user_bits is None


def test_cell_grid_is_the_permuted_payload_cells():
    frame, _llr = clean()
    grid = L._cell_grid(frame.row, frame.key)
    assert grid.shape == (frame.row.payload_cells, 2)
    assert grid.min() >= 0 and grid.max() < 64
    flat = grid[:, 0] * 64 + grid[:, 1]
    assert np.unique(flat).size == frame.row.payload_cells


def test_bits_wrong_denominators_are_the_four_named_ones():
    frame, _llr = clean()
    assert L.bits_wrong_denominators(frame.row, "C") == {
        "mother": 4096, "transmitted": 3976, "active": 3400, "user": 3368}


def test_ladder_is_blind():
    """DESIGN §0: no truth or oracle import, and no truth in the core."""
    tree = ast.parse(pathlib.Path(L.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add("." * node.level + (node.module or ""))
    assert not any("truth" in name or "oracle" in name
                   for name in imported), sorted(imported)
    core = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "_run_rungs")
    names = {arg.arg for arg in core.args.args + core.args.kwonlyargs}
    assert "truth_bits" not in names and "truth" not in names
    stripped = ast.Module(body=list(core.body), type_ignores=[])
    if (stripped.body and isinstance(stripped.body[0], ast.Expr)
            and isinstance(stripped.body[0].value, ast.Constant)):
        stripped.body = stripped.body[1:]
    assert "truth" not in ast.dump(stripped)

# ------------------------------------------------------------------ L4

#: MEASURED (2026-09-03, r0850, `near_codeword_llr`): of 180 constructions
#: over n_bad in {1,2,3} x 60 seeds, 59 exit BP at 1 <= unsat <= 12 and NONE
#: of them is reachable by L0/L1/L2 (0/59).  L4 certifies 11 of the 59.
#: These three are the fast single-bit cases; `L4_MISS` is a two-bit one the
#: rung does not reach, kept so the test says what L4 does NOT do.
L4_HITS = ((1, 1), (1, 15), (1, 14))
L4_MISS = (2, 9)


def near_codeword(n_bad: int, seed: int, ref=R0850):
    frame = build_frame(ref)
    return frame, near_codeword_llr(frame, n_bad, seed)


@pytest.mark.parametrize("n_bad,seed", L4_HITS)
def test_l4_certifies_what_l0_l1_l2_cannot(n_bad, seed):
    """The rung's reason to exist: a few-bit exit the earlier rungs miss."""
    frame, llr = near_codeword(n_bad, seed)
    exposure = Exposure()
    without = L.run_ladder(llr, frame.row, frame.key,
                           rungs=("L0", "L1", "L2"), knobs={"L2": FAST_L2},
                           exposure=exposure, metadata_bit=None)
    assert all(item.verdict == VERDICT_OPEN for item in without), \
        [(item.rung, item.verdict) for item in without]
    entry = min(item.unsat_at_exit for item in without)
    assert 0 < entry <= L.L4_MAX_UNSAT   # the few-error regime, blindly

    results = L.run_ladder(llr, frame.row, frame.key,
                           rungs=("L0", "L1", "L2", "L4"),
                           knobs={"L2": FAST_L2}, exposure=exposure,
                           metadata_bit=None)
    l4 = results[-1]
    assert l4.rung == "L4"
    assert l4.verdict == VERDICT_CERTIFIED_LIST          # a LIST rung
    assert np.array_equal(l4.user_bits, frame.user)      # and it is right
    assert "gt_bits_wrong" not in l4.detail              # BLIND detail
    assert l4.detail["n_candidates"] >= 1
    assert l4.detail["n_syndrome_ok"] >= 1
    assert l4.detail["best_unsat"] == 0
    assert l4.detail["source_rung"].startswith("L2")
    assert l4.detail["unsat_at_entry"] <= L.L4_MAX_UNSAT
    assert l4.crc_consults_distinct >= 1


def test_l4_reaches_the_single_bit_regime_and_not_the_two_bit_one():
    """Measured, not assumed: the pair sweep over 8 heads does not reach a
    two-bit exit, so the rung reports an honest miss rather than a hit."""
    frame, llr = near_codeword(*L4_MISS)
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L4"),
                           knobs={}, exposure=Exposure(), metadata_bit=None)
    l4 = results[-1]
    assert l4.verdict == VERDICT_OPEN
    assert l4.detail["n_candidates"] == 52       # 24 singles + C(8,2) pairs
    assert l4.detail["n_singles"] == 24 and l4.detail["n_pairs"] == 28


def test_l4_refuses_above_the_blind_unsat_gate():
    frame, llr = broken()                        # the >=50 regime
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L4"),
                           knobs={}, exposure=Exposure(), metadata_bit=None)
    l4 = results[-1]
    assert l4.verdict == VERDICT_REFUSED
    assert l4.detail["reason"] == "unsat_above_gate"
    assert l4.detail["unsat_at_entry"] > L.L4_MAX_UNSAT
    assert l4.crc_consults_distinct == 0
    assert "n_candidates" not in l4.detail       # nothing was decoded


def test_l4_gate_is_a_knob_and_bites_at_the_stated_value():
    frame, llr = near_codeword(*L4_HITS[0])
    tight = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L4"),
                         knobs={"flip_max_unsat": 2}, exposure=Exposure(),
                         metadata_bit=None)[-1]
    assert tight.verdict == VERDICT_REFUSED
    assert tight.detail["reason"] == "unsat_above_gate"
    loose = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L4"),
                         knobs={"flip_max_unsat": 12}, exposure=Exposure(),
                         metadata_bit=None)[-1]
    assert loose.verdict == VERDICT_CERTIFIED_LIST


def test_l4_exposure_counts_distinct_codewords():
    """DESIGN §0: the charge is per DISTINCT codeword, not per candidate."""
    frame, llr = near_codeword(*L4_HITS[2])      # 11 candidates, one hit
    exposure = Exposure()
    first = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L4"),
                         knobs={}, exposure=exposure, metadata_bit=None)[-1]
    assert first.verdict == VERDICT_CERTIFIED_LIST
    charged = exposure.distinct
    assert 0 < first.crc_consults_distinct <= first.detail["n_candidates"]
    assert first.crc_consults_distinct <= charged
    again = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L4"),
                         knobs={}, exposure=exposure, metadata_bit=None)[-1]
    assert again.verdict == VERDICT_CERTIFIED_LIST
    assert exposure.distinct == charged          # same codewords, no charge
    assert again.crc_consults_distinct == 0
    assert exposure.expected_false == charged * 2.0 ** -32


def test_l4_never_flips_a_format_known_or_metadata_position():
    """The hypothesis set excludes the shortened window and the metadata
    bit; both would propose a vector the printer could not have made."""
    frame, llr = near_codeword(*L4_HITS[1])
    seen: list[np.ndarray] = []
    real_bp = M.bp

    def spy(mother, code=None, iters=60, **kwargs):
        seen.append(np.asarray(mother.llr).copy())
        return real_bp(mother, code, iters, **kwargs)

    L.mother_mod.bp = spy
    try:
        results = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L4"),
                               knobs={"flip_m": 12, "flip_m2": 4},
                               exposure=Exposure(),
                               metadata_bit=int(frame.user[0]))
    finally:
        L.mother_mod.bp = real_bp
    l4 = results[-1]
    assert l4.detail["metadata_bit_used"] is False   # entry is L1's frame
    assert seen, "no candidate was decoded"
    entry = seen[0]
    forbidden = ~np.isfinite(entry)
    assert forbidden.sum() == 4096 - 3976
    for candidate in seen[1:]:
        assert np.array_equal(candidate[forbidden], entry[forbidden])
        moved = np.flatnonzero(candidate != entry)
        assert moved.size and not forbidden[moved].any()
        assert np.all(np.isinf(candidate[moved]))     # +-LLR_KNOWN, exactly


def test_l4_forbids_the_metadata_position_when_it_is_trusted():
    frame, llr = near_codeword(*L4_HITS[0])
    mother = M.to_mother(llr, frame.row, frame.key,
                         metadata_bit=int(frame.user[0]))
    forbidden = L._forbidden_positions(mother)
    assert forbidden[0]                                  # info index 0
    assert forbidden[mother.active:mother.k_bits].all()
    assert int(forbidden.sum()) == 4096 - 3976 + 1
    plain = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    assert not L._forbidden_positions(plain)[0]


def test_l4_candidates_are_the_unsatisfied_checks_variables_by_reliability():
    frame, llr = near_codeword(*L4_HITS[0])
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    out = M.bp(mother, None, 150, mode="minsum-then-sp")
    code = M.code_of(mother)
    variables = L._check_variables(code, out.syndrome)
    assert variables.size and np.array_equal(variables, np.unique(variables))
    # every named variable really is incident to an unsatisfied check
    rows = np.flatnonzero(out.syndrome)
    starts = np.asarray(code.chk_starts, np.int64)
    ends = np.concatenate((starts[1:], [code.edge_var.size]))
    expected = set()
    for c in rows:
        expected.update(int(v) for v in code.edge_var[starts[c]:ends[c]])
    assert set(int(v) for v in variables) == expected
    # and the ranking is |Ltot| ascending
    ranked = variables[np.argsort(np.abs(out.posterior[variables]),
                                  kind="stable")]
    reliability = np.abs(out.posterior[ranked])
    assert np.all(np.diff(reliability) >= 0.0)
    assert L._check_variables(code, np.zeros_like(out.syndrome)).size == 0


def test_l4_refuses_when_the_entry_frame_has_no_unsatisfied_checks():
    """A CRC-failing codeword: syndrome clean, so there is nothing to flip."""
    frame, llr = clean()
    exposure = Exposure()
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L4"),
                           knobs={}, exposure=exposure, metadata_bit=None)
    assert results[0].verdict == VERDICT_CERTIFIED
    assert [item.rung for item in results] == ["L1"]     # L1 stopped it
    mother = M.to_mother(llr, frame.row, frame.key)
    state = ("L1", M.bp(mother, None, 60), mother)
    l4 = L._rung_flip(frame.row, frame.key,
                      L.stream_fact(frame.row, "C").rung_children, exposure,
                      {}, state)
    assert l4.verdict == VERDICT_REFUSED
    assert l4.detail["reason"] == "no_unsatisfied_checks"


def test_l4_refuses_without_an_entry_posterior():
    frame, _llr = clean()
    result = L._rung_flip(frame.row, frame.key,
                          L.stream_fact(frame.row, "C").rung_children,
                          Exposure(), {}, None)
    assert result.verdict == VERDICT_REFUSED
    assert result.detail["reason"] == "no_entry_posterior"


class _FakeOut:
    """Only `unsat` is consulted by the entry-state choice."""

    def __init__(self, unsat):
        self.unsat = unsat


def test_l4_enters_at_the_l2_variant_with_the_fewest_unsatisfied_checks():
    states = [("L0", _FakeOut(80), None), ("L1", _FakeOut(60), None),
              ("L2:damped@300", _FakeOut(9), None),
              ("L2:layered@300", _FakeOut(31), None)]
    assert L._flip_source(states)[0] == "L2:damped@300"
    assert L._flip_source(states[:2])[0] == "L1"
    assert L._flip_source(states[:1])[0] == "L0"
    assert L._flip_source([]) is None


def test_l4_is_in_the_default_ladder_after_l2_and_before_l3():
    assert "L4" in L.DEFAULT_RUNGS
    assert L.DEFAULT_RUNGS.index("L4") > L.DEFAULT_RUNGS.index("L2")
    assert L.DEFAULT_RUNGS.index("L4") < L.DEFAULT_RUNGS.index("L3")


def test_l7a_refuses_an_empty_disagreement_set():
    frame, llr = broken()
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L7a",),
                           knobs={"disagree": (np.zeros(0, np.int64),
                                               np.zeros(0))},
                           exposure=Exposure(), metadata_bit=None)
    assert results[0].verdict == VERDICT_REFUSED
    assert results[0].detail["reason"] == "no_disagreement"


def test_l4_never_consults_the_crc_on_a_syndrome_failing_candidate():
    """DESIGN §0's ordering, measured rather than read: over a full 52-
    candidate sweep that closes no syndrome, `tile_codec.crc32_bits` is
    never called and the exposure is untouched."""
    frame, llr = near_codeword(*L4_MISS)
    real = tile_codec.crc32_bits
    calls = {"n": 0}

    def spy(bits):
        calls["n"] += 1
        return real(bits)

    M.tile_codec.crc32_bits = spy
    try:
        exposure = Exposure()
        l4 = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L4"),
                          knobs={}, exposure=exposure,
                          metadata_bit=None)[-1]
    finally:
        M.tile_codec.crc32_bits = real
    assert l4.verdict == VERDICT_OPEN
    assert l4.detail["n_candidates"] == 52
    assert l4.detail["n_syndrome_ok"] == 0
    assert calls["n"] == 0                       # no codeword, no CRC
    assert exposure.distinct == 0 and l4.crc_consults_distinct == 0


def test_l4_stops_at_the_exposure_bound_without_charging_it():
    frame, llr = near_codeword(*L4_HITS[0])
    exhausted = Exposure(bound_expected_false=0.0)
    l4 = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L4"),
                      knobs={}, exposure=exhausted, metadata_bit=None)[-1]
    assert l4.verdict == VERDICT_REFUSED
    assert l4.detail["reason"] == "exposure_exceeded"
    assert exhausted.distinct == 0 and not exhausted.exceeded()
    room = Exposure(bound_expected_false=2.0 * 2.0 ** -32)
    hit = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L4"),
                       knobs={}, exposure=room, metadata_bit=None)[-1]
    assert hit.verdict == VERDICT_CERTIFIED_LIST
    assert room.distinct <= 2 and not room.exceeded()


def test_l4_hypotheses_enter_at_llr_known_against_the_entry_decision():
    """The hypothesis door (DESIGN §0): +-LLR_KNOWN, never the channel clip,
    and always the OPPOSITE of what the entry posterior decided."""
    frame, llr = near_codeword(*L4_HITS[0])
    mother = M.to_mother(llr, frame.row, frame.key, metadata_bit=None)
    out = M.bp(mother, None, 150, mode="minsum-then-sp")
    code = M.code_of(mother)
    variables = L._check_variables(code, out.syndrome)
    variables = variables[~L._forbidden_positions(mother)[variables]]
    ranked = variables[np.argsort(np.abs(out.posterior[variables]),
                                  kind="stable")][:8]
    signs = L._flip_signs(out.posterior, out.hard, ranked)
    external = M.clipped_external(signs)
    assert set(np.unique(np.abs(external)).tolist()) == {LLR_KNOWN}
    assert LLR_CLIP not in set(np.unique(np.abs(external)).tolist())
    assert np.array_equal((external > 0).astype(np.uint8),
                          1 - out.hard[ranked])
