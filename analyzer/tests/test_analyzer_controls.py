"""W2 — `analyzer.controls`: a run without these is not a result.

The synthetic half checks the bookkeeping (exact intervals, a
deterministic stratified draw, the empty-withhold refusal, the wall
clock kept out of the permutation comparison).  The other half runs
the controls themselves at reduced n on the receiver's colour sim
decoded into a run dir (TIER S), so the numbers here are a regression
pin rather than the campaign's own measurement; sheet I's are records
(PAGE-FIELD-PLAN A1b).
"""

from __future__ import annotations

import json
from dataclasses import replace as dc_replace

import pytest

from analyzer import controls
from analyzer import inputs as inputs_mod
from analyzer import residue as residue_mod
from analyzer.types import AnalyzerConfig, LedgerRow

from ._analyzer_fixtures import (RESIDUE_WITHHELD, needs_sim, noisy_run_dir,
                                 sim_census, sim_run)


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


def test_withheld_keys_selects_by_certificate_source():
    from types import SimpleNamespace

    class _Inputs:
        run_dir = "/nonexistent"
        certificates = {
            (0, 1, 2, "Y"): SimpleNamespace(source="tiles/swim150"),
            (0, 3, 4, "C"): SimpleNamespace(source="tiles/scan"),
            (0, 0, 5, "M"): SimpleNamespace(source="tiles/swim150"),
            (0, 7, 1, "M"): SimpleNamespace(source="tiles/scan")}

    assert controls.withheld_keys(_Inputs(), sources=("tiles/swim150",)) == (
        (0, 0, 5, "M"), (0, 1, 2, "Y"))
    assert controls.withheld_keys(_Inputs(), sources=("tiles/scan",)) == (
        (0, 3, 4, "C"), (0, 7, 1, "M"))


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


def test_the_field_source_table_is_total_over_the_register_arms(monkeypatch):
    """PAGE-FIELD-PLAN A6: the classification must FAIL CLOSED.

    A table that merely listed the field arms would admit in silence any
    arm nobody classified — the review added a register arm `prior` and
    the controls never noticed.  So the table is TOTAL over
    `REGISTER_ARMS`, checked at import by `arms._check_field_source`,
    and this walks it without leaning on any naming convention: every
    register arm has a class, the classes are the three there are, and
    the table names nothing that is not a register arm.
    """
    from analyzer import arms as arms_mod

    assert set(arms_mod.FIELD_SOURCE) == set(arms_mod.REGISTER_ARMS)
    assert set(arms_mod.FIELD_SOURCE.values()) <= {"certified", "furniture",
                                                   "none"}
    # an arm registered without a class is an ERROR, not an admission:
    # the import-time check is driven here both ways round
    unclassified = {name: source
                    for name, source in arms_mod.FIELD_SOURCE.items()
                    if name != "field2"}
    monkeypatch.setattr(arms_mod, "FIELD_SOURCE", unclassified)
    with pytest.raises(arms_mod.ArmError, match="unclassified"):
        arms_mod._check_field_source()
    monkeypatch.setattr(arms_mod, "FIELD_SOURCE",
                        {**unclassified, "field2": "furniture",
                         "prior": "none"})
    with pytest.raises(arms_mod.ArmError, match="not a register arm"):
        arms_mod._check_field_source()


def test_the_refused_set_asks_the_table_what_each_arm_reads():
    """The certificate-fed arms are refused and the furniture ones are
    not — decided by `FIELD_SOURCE`, never by the spelling of a name.

    The production `field` family is certificate-fed BY CONSTRUCTION
    (the receiver's blind tier is retired, so every page field is solved
    from certified templates plus furniture); `field2` is fitted from
    furniture alone and stays ADMITTED — it is the blind cross-check,
    and refusing it would withhold nothing.
    """
    from analyzer import arms as arms_mod

    refused_tails = {arms_mod.parse_arm(arm)[1] for arm in controls.FIELD_ARMS}
    for tail, source in arms_mod.FIELD_SOURCE.items():
        if source == "certified":
            assert tail in refused_tails, tail
        else:
            assert tail not in refused_tails, tail
    # the pooled `field2` arms a battery actually names are admitted
    from analyzer.types import PROFILES, with_profile
    config = with_profile(AnalyzerConfig(refused_arms=controls.FIELD_ARMS),
                          "everything")
    named = [arm for arm in PROFILES["everything"]["arms"] if "field2" in arm]
    assert named
    for arm in named:
        assert arm in config.battery_for("C")
    # and the spelling is the battery's own: mode + register arm
    assert controls.FIELD_ARMS == ("subtract+field", "subtract+field+offset")


def test_an_operator_battery_is_walked_too_not_only_the_known_rosters():
    """`analyzer controls --arms …` names a roster the code never saw.

    `FIELD_ARMS` covers `DEFAULT_ARMS` and the profiles; a run's own
    `--arms` is where a certificate-fed arm would actually run, so the
    control walks `config.arms` and `config.reroll_only_arms` at call
    time.  `head+field+offset` is in no roster in the code and must
    still be refused (the review ran it through and it survived).
    """
    config = AnalyzerConfig(arms=("head+field+offset", "subtract+offset"),
                            reroll_only_arms=("head+field",))
    refused = controls._refused_under_withholding(config)
    assert "head+field+offset" in refused and "head+field" in refused
    assert set(controls.FIELD_ARMS) <= set(refused)
    assert "subtract+offset" not in refused
    local = dc_replace(config, refused_arms=refused)
    assert local.battery_for("C") == ("subtract+offset",)
    # a furniture arm an operator names is still admitted
    admitted = controls._refused_under_withholding(
        AnalyzerConfig(arms=("head+field2+offset", "subtract+offset")))
    assert "head+field2+offset" not in admitted


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

# ------------------------------------------------ the legs, on the sim

@needs_sim
def test_the_parity_sample_re_derives_with_the_default_arm():
    """Q1.3 (lite): the acceptance gate, at n=12 per stream.

    Twelve, not three: three tiles cannot measure a 0.80 rate (sheet I
    read C 12/12, M 12/12, Y 11/12 at this n, the record).
    """
    run, rows = sim_run(), sim_census()
    out = controls.parity_sample(run, rows,
                                 AnalyzerConfig(workers=4), n_per_stream=12)
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


@needs_sim
def test_the_null_arm_certifies_nothing():
    """Q1.4 (lite): the pixels of a tile 8 columns away, this address.

    On a ten-tile page only columns 0, 1, 8 and 9 have a donor at the
    production shift, so the keys are drawn there."""
    run, rows = sim_run(), sim_census()
    certified = [row for row in rows if row.certified_by_production
                 and controls._donor(run, row.key,
                                     controls.NULL_SHIFT_TILES) is not None]
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


#: The frame null's keys on the NOISY derivative: one per plane, each
#: certified on `sum`/L0 when withheld with the true frame.
FRAME_NULL_KEYS: tuple[tuple[int, int, int, str], ...] = (
    (0, 5, 5, "C"), (0, 6, 2, "M"), (0, 7, 7, "Y"))


@needs_sim
def test_the_frame_null_certifies_nothing_where_the_true_frame_reads():
    """Right pixels, right address, another tile's certified frame.

    On the noiseless sim the pixels alone carry the bits and the frame
    null certifies through a corrupted frame (9 of `RESIDUE_WITHHELD`'s
    12, measured 2026-10-09), so the control has no power there.  On the
    NOISY derivative (`NOISE_SIGMA_GREY`, the curve in the fixtures) the
    certified frame is what the read stands on: the frame null mints 0
    while the positive control, same pixels, same keys, same battery,
    wins every key back.  Sheet I's frame null (0) is the record.
    """
    from holo.receiver.tests._h3_support import assert_measured
    run = inputs_mod.load_run(noisy_run_dir())
    config = AnalyzerConfig(workers=4, rules=("sum",), rungs=("L0",))
    out = controls.frame_null(run, FRAME_NULL_KEYS, config)
    print(f"\nframe null on the noisy sim: {out['n_certificates']} "
          f"certificate(s) in {out['n_trials']} trials, power "
          f"{out['power_denominator']}")
    assert out["n_certificates"] == 0, out["trials"]
    assert out["passes"] is True
    assert_measured("frame-null power on the noisy sim",
                    out["power_denominator"], len(FRAME_NULL_KEYS))
    positive = controls.positive_control(
        run, FRAME_NULL_KEYS, config,
        census_rows=residue_mod.census(run))
    assert positive["n_disagreeing_with_production"] == 0
    assert_measured("positive control on the noisy sim",
                    positive["n_recovered"], len(FRAME_NULL_KEYS))


@needs_sim
def test_the_positive_control_wins_back_a_withheld_handful(tmp_path):
    """Q1.5: certificates this run won, withheld and won back.

    The sim run is from scratch, so its mints are all 300 certificates
    and withholding them is a decode, not a test; the withhold set is
    `RESIDUE_WITHHELD` from a key file.  Sheet I's nine `tiles/swim150`
    keys are the record (PAGE-FIELD-PLAN A1b).
    """
    run, rows = sim_run(), sim_census()
    assert len(controls.withheld_keys(run, run_mints=True)) == len(
        run.certificates)
    keys_file = tmp_path / "withhold.json"
    keys_file.write_text(json.dumps([list(key) for key in RESIDUE_WITHHELD]),
                         "utf-8")
    withheld = controls.withheld_keys(run, keys_file=keys_file)
    assert withheld == tuple(sorted(RESIDUE_WITHHELD))
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
