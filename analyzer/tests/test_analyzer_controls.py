"""W2 — `analyzer.controls`: a run without these is not a result.

The synthetic half checks the bookkeeping (exact intervals, a
deterministic stratified draw, the empty-withhold refusal, the wall
clock kept out of the permutation comparison).  The sheet-I half runs
the controls themselves at reduced n, so the numbers here are a
regression pin rather than the campaign's own measurement.
"""

from __future__ import annotations

import json

import pytest

from analyzer import controls
from analyzer.types import AnalyzerConfig, LedgerRow

from ._analyzer_fixtures import i_census, i_inputs, needs_i_run


def _row(ty: int, tx: int, stream: str, band: str) -> LedgerRow:
    return LedgerRow(page=0, ty=ty, tx=tx, stream_id=stream, esi=0,
                     covered=True, certified_by_production=True,
                     source="tiles/scan", band=band, band_any=band,
                     neighbours_certified=8, siblings_certified=(),
                     known_cells_in_halo=0, n_discriminating_labels=0,
                     production_attempts={}, metadata_known=True)


# ------------------------------------------------------------- intervals

def test_clopper_pearson_ends_are_exact():
    assert controls.clopper_pearson(0, 10)[0] == 0.0
    assert controls.clopper_pearson(10, 10)[1] == 1.0
    low, high = controls.clopper_pearson(10, 10)
    assert low == pytest.approx(0.6915, abs=1e-3)
    low, high = controls.clopper_pearson(5, 10)
    assert low == pytest.approx(0.187, abs=1e-3)
    assert high == pytest.approx(0.813, abs=1e-3)


def test_clopper_pearson_on_no_trials_is_the_whole_interval():
    assert controls.clopper_pearson(0, 0) == (0.0, 1.0)


# ---------------------------------------------------------------- sample

def test_stratified_sample_is_deterministic_and_spreads_over_bands():
    rows = ([_row(index, 0, "Y", "dead") for index in range(50)]
            + [_row(index, 1, "Y", "live") for index in range(50)]
            + [_row(index, 2, "C", "live") for index in range(50)])
    first = controls.stratified_sample(rows, 10, seed=5)
    again = controls.stratified_sample(rows, 10, seed=5)
    other = controls.stratified_sample(rows, 10, seed=6)
    assert [row.key for row in first] == [row.key for row in again]
    assert [row.key for row in first] != [row.key for row in other]
    picked = [row for row in first if row.stream_id == "Y"]
    assert len(picked) == 10
    assert {row.band for row in picked} == {"dead", "live"}
    assert len([row for row in first if row.stream_id == "C"]) == 10


def test_stratified_sample_takes_what_there_is():
    rows = [_row(0, 0, "M", "live"), _row(1, 0, "M", "live")]
    assert len(controls.stratified_sample(rows, 10, seed=1)) == 2


def test_stratified_sample_can_be_limited_to_streams():
    rows = [_row(0, 0, "Y", "live"), _row(1, 0, "C", "live")]
    out = controls.stratified_sample(rows, 5, seed=1, streams=("C",))
    assert [row.stream_id for row in out] == ["C"]


# ----------------------------------------------------------- withholding

def test_withheld_keys_refuses_an_empty_set():
    class _Inputs:
        run_dir = "/nonexistent"
        certificates: dict = {}

    with pytest.raises(controls.ControlError, match="EMPTY"):
        controls.withheld_keys(_Inputs(), sources=("tiles/nothing",))


def test_withheld_keys_reads_a_key_file(tmp_path):
    class _Inputs:
        run_dir = "/nonexistent"
        certificates = {(0, 1, 2, "Y"): object(), (0, 3, 4, "C"): object()}

    path = tmp_path / "keys.txt"
    path.write_text("# a comment\n0,1,2,Y\n0,3,4,C\n", "utf-8")
    assert controls.withheld_keys(_Inputs(), keys_file=path) == (
        (0, 1, 2, "Y"), (0, 3, 4, "C"))
    path.write_text(json.dumps([[0, 1, 2, "Y"]]), "utf-8")
    assert controls.withheld_keys(_Inputs(), keys_file=path) == (
        (0, 1, 2, "Y"),)


def test_withheld_keys_refuses_a_key_that_is_not_a_certificate(tmp_path):
    class _Inputs:
        run_dir = "/nonexistent"
        certificates = {(0, 1, 2, "Y"): object()}

    path = tmp_path / "keys.txt"
    path.write_text("0,9,9,Y\n", "utf-8")
    with pytest.raises(controls.ControlError, match="not certificates"):
        controls.withheld_keys(_Inputs(), keys_file=path)


def test_field_arms_are_refused_under_withholding():
    config = AnalyzerConfig()
    for arm in controls.FIELD_ARMS:
        assert arm in config.battery_for("C")
    refused = AnalyzerConfig(refused_arms=controls.FIELD_ARMS)
    for arm in controls.FIELD_ARMS:
        assert arm not in refused.battery_for("C")


# -------------------------------------------- the stratified holdout (W3)

def test_parse_holdout_spec_reads_stream_source_counts():
    assert controls.parse_holdout_spec(
        "Y:tiles/planek150=60, C:tiles/local150=20") == {
            ("Y", "tiles/planek150"): 60, ("C", "tiles/local150"): 20}


@pytest.mark.parametrize("spec", ["Y=60", "Y:tiles/planek150", "",
                                  "Y:tiles/planek150=0",
                                  "Y:tiles/planek150=many"])
def test_parse_holdout_spec_refuses_a_malformed_spec(spec):
    with pytest.raises(controls.ControlError):
        controls.parse_holdout_spec(spec)


def test_holdout_selection_takes_what_there_is_and_says_so():
    rows = [_row(ty, 0, "Y", "dead") for ty in range(5)]
    for row in rows[:2]:
        row.source = "tiles/local150"
    for row in rows[2:]:
        row.source = "tiles/planek150"
    keys, plan = controls.holdout_selection(
        rows, {("Y", "tiles/planek150"): 2,
               ("Y", "tiles/local150"): 9}, seed=7)
    assert len(keys) == 2 + 2 and len(set(keys)) == len(keys)
    by_source = {item["source"]: item for item in plan}
    assert by_source["tiles/local150"]["short"] is True
    assert by_source["tiles/local150"]["available"] == 2
    assert by_source["tiles/planek150"]["short"] is False
    # deterministic: the same spec and seed pick the same certificates
    again, _plan = controls.holdout_selection(
        rows, {("Y", "tiles/planek150"): 2,
               ("Y", "tiles/local150"): 9}, seed=7)
    assert again == keys


def test_holdout_selection_ignores_uncertified_rows():
    rows = [_row(ty, 0, "C", "live") for ty in range(3)]
    rows[0].certified_by_production = False
    keys, _plan = controls.holdout_selection(
        rows, {("C", "tiles/scan"): 3}, seed=1)
    assert rows[0].key not in keys and len(keys) == 2


# ------------------------------------------------------- the wall clock

def test_the_oracle_permutation_control_is_gone():
    """2026-09-04: a run has no truth to permute.

    The control compared two runs of the battery, one against a truth
    table rotated across addresses, and asserted every non-oracle column
    was byte-identical.  With truth out of the run that claim is
    structural — there is nothing to permute — so the control and its
    helpers left, and what remains testable moved to the scorer.
    """
    for name in ("oracle_permutation", "permuted_truth", "_strip_oracle",
                 "_drop_wall_clock"):
        assert not hasattr(controls, name), name


# -------------------------------------------------------- sheet-I legs

@needs_i_run
def test_sheet_i_parity_sample_re_derives_with_the_default_arm():
    """Q1.3 (lite): the acceptance gate, at n=3 per stream."""
    run, rows = i_inputs(), i_census()
    out = controls.parity_sample(run, rows,
                                 AnalyzerConfig(workers=4), n_per_stream=3)
    print("\nQ1.3-lite parity:")
    for name, body in out["configurations"].items():
        rates = {stream: f"{cell['re_derived']}/{cell['n']}"
                 for stream, cell in body["by_stream"].items()}
        print(f"  {name:28s} arm={body['arm']:18s} "
              f"ctx={body['ctx_mode']:10s} {rates} "
              f"disagreeing={body['n_disagreeing_with_production']}")
    default = out["configurations"]["default"]
    assert default["n_disagreeing_with_production"] == 0
    for cell in default["by_stream"].values():
        assert cell["rate"] >= controls.PARITY_BAR
    assert out["passes"] is True


@needs_i_run
def test_sheet_i_null_arm_certifies_nothing():
    """Q1.4 (lite): the pixels of a tile 8 columns away, this address."""
    run, rows = i_inputs(), i_census()
    certified = [row for row in rows if row.certified_by_production]
    keys = [row.key for row in
            controls.stratified_sample(certified, 1, seed=20260903)][:2]
    out = controls.null_arm(run, keys, AnalyzerConfig(workers=4))
    print(f"\nQ1.4-lite null arm: {out['n_certificates']} certificate(s) in "
          f"{out['n_trials']} trials, power {out['power_denominator']}, "
          f"exposure {out['exposure_distinct']} distinct")
    for trial in out["trials"]:
        print(f"  {trial['key']} <- {trial['donor']} "
              f"certs={trial['null_certificates']} "
              f"min_unsat={trial['null_min_unsat']} "
              f"truthful={trial['truthful_certifies']}")
    assert out["n_certificates"] == 0
    assert out["power_denominator"] == len(keys)


@needs_i_run
def test_sheet_i_frame_null_certifies_nothing():
    run, rows = i_inputs(), i_census()
    certified = [row for row in rows if row.certified_by_production]
    keys = [row.key for row in
            controls.stratified_sample(certified, 1, seed=7)][:1]
    out = controls.frame_null(run, keys, AnalyzerConfig(workers=4))
    print(f"\nQ1.4-lite frame null: {out['n_certificates']} certificate(s) "
          f"in {out['n_trials']} trials, power {out['power_denominator']}")
    assert out["n_certificates"] == 0
    assert out["power_denominator"] == len(keys)


@needs_i_run
def test_sheet_i_positive_control_on_the_run_mints():
    """Q1.5: the 14 keys this run minted, withheld and won back."""
    run, rows = i_inputs(), i_census()
    withheld = controls.withheld_keys(run, run_mints=True)
    assert len(withheld) == 14
    out = controls.positive_control(run, withheld,
                                    AnalyzerConfig(workers=4),
                                    census_rows=rows)
    print(f"\nQ1.5 positive control: {out['n_recovered']}/"
          f"{out['n_withheld']} recovered ({out['fraction']:.3f}), "
          f"bar {out['bar']}")
    for entry in out["per_key"]:
        if entry["recovered"]:
            print(f"  {entry['key']} RECOVERED {entry['source']} "
                  f"{entry['certifying_rule']}/{entry['certifying_rung']}")
        else:
            print(f"  {entry['key']} MISSED    {entry['source']} "
                  f"closest={entry.get('closest_arm')} "
                  f"min_unsat={entry.get('min_unsat')}")
    for stratum in out["strata"]:
        print(f"  stratum {stratum['source']}/{stratum['band']}: "
              f"{stratum['recovered']}/{stratum['n']} "
              f"CP95={stratum['clopper_pearson_95']} "
              f"graded={stratum['graded']}")
    assert out["passes"] is True
    # Truth-free and stronger: every recovered key must agree with
    # PRODUCTION's own certificate for that key, bit for bit.
    assert out["n_disagreeing_with_production"] == 0
    assert out["refused_arms"] == list(controls.FIELD_ARMS)


# The oracle-permutation legs are RETIRED with the control they tested
# (2026-09-04): there is no truth in a run to permute.  What replaced
# them is `test_analyzer_score.py`'s permuted-payload leg, which checks
# that the SCORER's blind columns come straight off the ledger and only
# its oracle columns move.
