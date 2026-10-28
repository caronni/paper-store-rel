"""W2 — `analyzer.ledger`: the JSON lines, the attribution, the maps.

All synthetic: the ledger's job is bookkeeping, and bookkeeping is
testable without a run dir.  The attribution test is the one that
matters — DESIGN §9 asks for BOTH first-success marginals and
leave-one-out values, and the two disagree exactly when one rule or rung
is doing work another would also have done.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from analyzer import ledger
from analyzer.types import (VERDICT_CERTIFIED, VERDICT_OPEN, LedgerRow)


def make_row(ty: int, tx: int, stream: str = "Y", *, band: str = "live",
             verdict: str = VERDICT_OPEN, rules=(), rungs_by_rule=None,
             certifying=None, diag=None,
             production: bool = False) -> LedgerRow:
    row = LedgerRow(page=0, ty=ty, tx=tx, stream_id=stream, esi=ty * 100 + tx,
                    covered=True, certified_by_production=production,
                    source="tiles/scan" if production else None,
                    band=band, band_any=band, neighbours_certified=3,
                    siblings_certified=("C",), known_cells_in_halo=1200,
                    n_discriminating_labels=13, production_attempts={"n": 1},
                    metadata_known=True)
    row.verdict = verdict
    rungs: dict = {}
    for rule in rules:
        entries = (rungs_by_rule or {}).get(rule, [("L0", verdict)])
        rungs[rule] = [
            {"rung": name, "verdict": value, "n_iters": 60,
             "unsat_at_exit": 0 if value == VERDICT_CERTIFIED else 17,
             "syndrome_ok": value == VERDICT_CERTIFIED,
             "posterior_summary": {"mean_abs_posterior": 4.5},
             "crc_consults_distinct": 1, "seconds": 0.1, "detail": {}}
            for name, value in entries]
    row.rungs = rungs
    if certifying is not None:
        row.certifying_rule, row.certifying_rung = certifying
        row.rungs["user_bits"] = np.zeros(8, np.uint8)
    row.diag = diag or {}
    row.generation = 0
    return row


# ------------------------------------------------------------ round trip

def test_write_and_read_round_trips_the_header_and_the_rows(tmp_path):
    rows = [make_row(1, 2), make_row(3, 4, "C", production=True)]
    rows[0].evidence = {"cap/l0|subtract+offset": {
        "n_labels": np.int64(120), "offset_dots_xy": (0.25, -0.5),
        "label_rows": np.arange(4)}}
    rows[0].rungs["sum"] = [{"rung": "L0", "verdict": "open",
                             "unsat_at_exit": 51, "detail":
                             {"hard_packed_b64": "AAEC"}}]
    rows[0].diag = {"seconds": 1.5, "n_lanes": 3}
    path = ledger.write_rows(tmp_path / "l.jsonl", rows,
                             {"seed": 7, "rules": ["sum"]})
    header, back = ledger.read_rows(path)
    assert header["seed"] == 7 and header["type"] == "header"
    assert len(back) == 2
    assert back[0]["ty"] == 1 and back[0]["tx"] == 2
    assert back[0]["evidence"]["cap/l0|subtract+offset"]["n_labels"] == 120
    assert back[0]["evidence"]["cap/l0|subtract+offset"][
        "offset_dots_xy"] == [0.25, -0.5]
    assert back[1]["certified_by_production"] is True
    # The packed exit hard vector SURVIVES the round trip: it is what
    # the offline scorer counts bits wrong from (2026-09-04).
    assert back[0]["rungs"]["sum"][0]["detail"]["hard_packed_b64"] == "AAEC"
    assert back[0]["diag"] == {"seconds": 1.5, "n_lanes": 3}
    assert "oracle" not in back[0]
    # every line is real JSON, not a repr
    for line in path.read_text("utf-8").splitlines():
        json.loads(line)


def test_jsonable_survives_numpy_and_non_finite():
    out = ledger.jsonable({"a": np.float64("nan"), "b": np.arange(3),
                           "c": (np.True_, np.int32(4)), "d": b"\x01\x02"})
    assert out == {"a": None, "b": [0, 1, 2], "c": [True, 4], "d": "0102"}
    json.dumps(out)


def test_row_to_dict_drops_nothing_the_census_put_there():
    row = make_row(5, 6, "M", production=True)
    record = ledger.row_to_dict(row)
    for name in ("band", "band_any", "neighbours_certified",
                 "siblings_certified", "known_cells_in_halo",
                 "n_discriminating_labels", "metadata_known", "esi"):
        assert name in record


# ----------------------------------------------------------- attribution

def test_attribution_union_marginals_and_leave_one_out():
    #: key A certifies under sum only; key B under sum and best; key C
    #: under best only; key D not at all.
    rows = [
        make_row(0, 0, rules=("sum", "best"), verdict=VERDICT_CERTIFIED,
                 rungs_by_rule={"sum": [("L0", VERDICT_CERTIFIED)],
                                "best": [("L0", VERDICT_OPEN)]},
                 certifying=("sum", "L0")),
        make_row(0, 1, rules=("sum", "best"), verdict=VERDICT_CERTIFIED,
                 rungs_by_rule={"sum": [("L0", VERDICT_CERTIFIED)],
                                "best": [("L1", VERDICT_CERTIFIED)]},
                 certifying=("sum", "L0")),
        make_row(0, 2, rules=("sum", "best"), verdict=VERDICT_CERTIFIED,
                 rungs_by_rule={"sum": [("L0", VERDICT_OPEN)],
                                "best": [("L1", VERDICT_CERTIFIED)]},
                 certifying=("best", "L1")),
        make_row(0, 3, rules=("sum", "best"),
                 rungs_by_rule={"sum": [("L0", VERDICT_OPEN)],
                                "best": [("L0", VERDICT_OPEN)]}),
    ]
    out = ledger.attribution(rows, rule_order=("sum", "best"),
                             rung_order=("L0", "L1"))
    assert out["union"] == 3
    assert out["first_success_by_rule"] == {"sum": 2, "best": 1}
    # dropping `sum` still leaves B (best certifies it) and C
    assert out["leave_one_out_by_rule"] == {"sum": 2, "best": 2}
    assert out["only_by_rule"] == {"sum": 1, "best": 1}
    assert out["first_success_by_rung"] == {"L0": 2, "L1": 1}


def test_attribution_ignores_the_user_bits_slot():
    row = make_row(1, 1, rules=("sum",), verdict=VERDICT_CERTIFIED,
                   rungs_by_rule={"sum": [("L0", VERDICT_CERTIFIED)]},
                   certifying=("sum", "L0"))
    assert "user_bits" in row.rungs
    assert ledger.attribution([row])["union"] == 1


# ------------------------------------------------------------ histograms

def test_histograms_are_blind_only():
    """2026-09-04: a ledger carries the unsat histogram and nothing else.

    The bits-wrong half needs a payload, so it moved to
    `analyzer.score.bits_wrong_histogram`, which reads the same rungs
    through the packed hard vectors this file writes.
    """
    rows = [
        make_row(0, 0, rules=("sum",),
                 rungs_by_rule={"sum": [("L0", VERDICT_OPEN)]}),
        make_row(0, 1, rules=("sum",),
                 rungs_by_rule={"sum": [("L0", VERDICT_CERTIFIED)]},
                 verdict=VERDICT_CERTIFIED, certifying=("sum", "L0")),
    ]
    out = ledger.histograms(rows)
    assert out["n_unsat_samples"] == 2
    assert out["unsat_at_exit"]["0"] == 1
    assert out["unsat_at_exit"]["10-49"] == 1
    assert "bits_wrong_active" not in out
    assert not hasattr(ledger, "waterfall_rows")


def test_stream_band_table_counts_by_verdict():
    rows = [make_row(0, 0, "Y", band="dead"),
            make_row(0, 1, "Y", band="dead", verdict=VERDICT_CERTIFIED),
            make_row(0, 2, "C", band="live")]
    table = ledger.stream_band_table(rows)
    assert table["Y"]["dead"] == {"n": 2, "certified": 1, "false_accept": 0,
                                  "uncovered": 0, "corroborated": 0,
                                  "contradicted": 0}
    assert table["C"]["live"]["n"] == 1


def test_summarize_points_at_the_offline_scorer_for_the_rest():
    """The report says where the missing columns went, by name."""
    text = ledger.summarize([make_row(0, 0)], header={})
    assert "analyzer score" in text
    assert "hard vectors" in text


# -------------------------------------------------------------- markdown

def test_summarize_names_the_union_and_labels_what_is_approximate():
    rows = [make_row(0, 0, rules=("sum",), verdict=VERDICT_CERTIFIED,
                     rungs_by_rule={"sum": [("L0", VERDICT_CERTIFIED)]},
                     certifying=("sum", "L0")),
            make_row(0, 1, rules=("sum",),
                     rungs_by_rule={"sum": [("L0", VERDICT_OPEN)]})]
    text = ledger.summarize(
        rows, header={"run_dir": "/tmp/I", "rules": ["sum"],
                      "rungs": ["L0"], "seed": 3},
        close_row={"status": "verified", "verified": True})
    assert "Order-free union: 1 tile-stream(s)" in text
    assert "LOWER BOUND" in text
    assert "NOT RUN" in text            # controls were not handed in
    assert "verified" in text


def test_summarize_refuses_to_pretend_controls_ran():
    text = ledger.summarize([make_row(0, 0)], header={})
    assert "a run without its controls is not a result" in text


# ------------------------------------------------------------- the maps

def test_render_maps_writes_the_verdict_png_per_plane(tmp_path):
    """One map per plane, not two: the bits-wrong twin is an oracle
    picture and lives in `analyzer.score.render_maps`."""
    rows = [make_row(0, 0, "C", verdict=VERDICT_CERTIFIED),
            make_row(1, 1, "Y")]
    written = ledger.render_maps(rows, tmp_path, tiles_yx=(4, 4), scale=2)
    names = sorted(path.name for path in written)
    assert names == ["verdict-C.png", "verdict-Y.png"]
    from PIL import Image
    with Image.open(written[0]) as image:
        assert image.size == (8, 8)


def test_render_maps_on_no_rows_writes_nothing(tmp_path):
    assert ledger.render_maps([], tmp_path) == []


def test_read_rows_tolerates_blank_lines(tmp_path):
    path = tmp_path / "l.jsonl"
    path.write_text('{"type": "header", "seed": 1}\n\n'
                    '{"type": "row", "ty": 0, "tx": 0, "stream_id": "Y"}\n',
                    "utf-8")
    header, rows = ledger.read_rows(path)
    assert header["seed"] == 1 and len(rows) == 1


def test_attribution_on_an_empty_ledger():
    out = ledger.attribution([])
    assert out["union"] == 0 and out["rule_order"] == []
    assert ledger.summarize([], header={}).startswith("# analyzer ledger")


def test_histogram_buckets_are_named_by_their_range():
    out = ledger._histogram([0, 1, 2, 4, 9, 60, 900], [0, 1, 2, 3, 5, 10, 50,
                                                       100, 500])
    assert out["0"] == 1 and out["1"] == 1 and out["2"] == 1
    assert out["3-4"] == 1 and out["5-9"] == 1 and out["50-99"] == 1
    assert out[">=500"] == 1
    assert sum(out.values()) == 7


def test_summarize_takes_no_waterfall_any_more():
    """The waterfall needs R, R needs a payload — `analyzer score`'s."""
    import inspect
    assert "waterfall" not in inspect.signature(ledger.summarize).parameters


@pytest.mark.parametrize("value", [np.float32(1.5), np.int8(-2), None, "x"])
def test_jsonable_is_total(value):
    json.dumps(ledger.jsonable(value))


def test_list_rungs_stay_out_of_the_blind_unsat_histogram():
    """W4 review: L4's `unsat_at_exit` is a minimum over its candidate
    decodes, so counting it would pull DESIGN §6's deferral histogram
    toward zero and break comparison with the L0-L3+L7 pass."""
    rows = [{"rungs": {"sum": [
        {"rung": "L1", "unsat_at_exit": 7},
        {"rung": "L2:damped@300", "unsat_at_exit": 6},
        {"rung": "L4", "unsat_at_exit": 0, "verdict": "certified_list"},
    ]}}]
    hist = ledger.histograms(rows)
    assert hist["n_unsat_samples"] == 2
    assert hist["unsat_at_exit"]["0"] == 0


# ------------------------ independent agreement in the summary (W7, 2026-09-04)


def _agreeing(ty: int, n_independent: int, *, contradiction: bool = False,
              verdict: str = VERDICT_CERTIFIED, stream: str = "Y"):
    diag = {"seconds": 1.0, "n_lanes": 3,
            "independent_agreement": n_independent,
            "n_certificate_claims": max(1, n_independent),
            "contradiction": contradiction}
    if contradiction:
        diag["contradicting"] = [{"label": "best", "rung": "L0",
                                  "sha256": "aa", "n_bits_differing": 3}]
    return make_row(ty, 0, stream, verdict=verdict, diag=diag)


def test_agreement_table_counts_corroboration_over_certified_rows_only():
    rows = [_agreeing(0, 1), _agreeing(1, 2), _agreeing(2, 3),
            _agreeing(3, 0, verdict=VERDICT_OPEN)]
    table = ledger.agreement_table(rows)
    assert table["n_certified"] == 3
    assert table["by_independent_agreement"] == {1: 1, 2: 1, 3: 1}
    assert table["n_corroborated"] == 2
    assert table["n_contradictions"] == 0


def test_agreement_table_lists_the_contradictions_that_refused_a_key():
    """A refused key is OPEN, so it is not a certified row — but it IS
    listed, because a contradiction is the loudest thing a pass can say."""
    rows = [_agreeing(0, 2),
            _agreeing(1, 0, contradiction=True, verdict=VERDICT_OPEN)]
    table = ledger.agreement_table(rows)
    assert table["n_certified"] == 1
    assert table["n_contradictions"] == 1
    assert table["contradictions"][0]["key"] == [0, 1, 0, "Y"]
    assert table["contradictions"][0]["claims"][0]["label"] == "best"


def test_the_stream_band_table_gains_the_corroborated_column():
    table = ledger.stream_band_table([_agreeing(0, 2), _agreeing(1, 1),
                                      _agreeing(2, 0, contradiction=True,
                                                verdict=VERDICT_OPEN)])
    cell = table["Y"]["live"]
    assert cell["n"] == 3
    assert cell["certified"] == 2
    assert cell["corroborated"] == 1
    assert cell["contradicted"] == 1


def test_the_summary_carries_the_independent_agreement_section():
    text = ledger.summarize(
        [_agreeing(0, 2), _agreeing(1, 1),
         _agreeing(2, 0, contradiction=True, verdict=VERDICT_OPEN)],
        header={})
    assert "## Independent agreement" in text
    assert "| independent certificates | certified rows |" in text
    assert "corroborated (>=2 independent): 1 of 2 certified row(s)" in text
    assert "contradictions refused: 1" in text
    assert "| stream | band | rows | certified | corroborated |" in text[
        text.index("## Stream x band"):]
