"""W2 — `analyzer.ledger`: the JSON lines, the attribution, the maps.

All synthetic: the ledger's job is bookkeeping, and bookkeeping is
testable without a run dir.  The attribution test is the one that
matters — DESIGN §9 asks for BOTH first-success marginals and
leave-one-out values, and the two disagree exactly when one rule or rung
is doing work another would also have done.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from analyzer import ledger, ledgerio
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


def test_certifying_arm_round_trips_through_the_ledger(tmp_path):
    """W8 B1: the driver set it since GAPS-2026-09-03 and README §4
    claimed it; `row_to_dict` never wrote it."""
    row = make_row(2, 3, "C", rules=("sum",), verdict=VERDICT_CERTIFIED,
                   rungs_by_rule={"sum": [("L0", VERDICT_CERTIFIED)]},
                   certifying=("sum|reroll:head+offset", "L0"))
    row.certifying_arm = "reroll:head+offset"
    plain = make_row(2, 4, "C")
    path = ledger.write_rows(tmp_path / "l.jsonl", [row, plain], {})
    _header, back = ledger.read_rows(path)
    assert back[0]["certifying_arm"] == "reroll:head+offset"
    assert back[1]["certifying_arm"] is None
    assert ledger.certifying_arms("reroll:head+offset") == (
        ("head+offset",), True)
    assert ledger.certifying_arms("head+offset|subtract+offset") == (
        ("head+offset", "subtract+offset"), False)
    assert ledger.certifying_arms(None) == ((ledger.UNRECORDED_ARM,), False)


def test_attribution_by_arm_counts_rerolls_under_their_arm():
    def certified(ty, arm):
        row = make_row(ty, 0, "C", rules=("sum",), verdict=VERDICT_CERTIFIED,
                       rungs_by_rule={"sum": [("L0", VERDICT_CERTIFIED)]},
                       certifying=("sum", "L0"))
        row.certifying_arm = arm
        return row

    rows = [certified(0, "subtract+offset"),
            certified(1, "reroll:patch+offset"),
            certified(2, "patch+offset|subtract+offset"),
            certified(3, "reroll:patch+offset"),
            certified(4, None),
            make_row(5, 0, "C", rules=("sum",),
                     rungs_by_rule={"sum": [("L0", VERDICT_OPEN)]})]
    out = ledger.attribution(rows, rule_order=("sum",), rung_order=("L0",),
                             arm_order=("subtract+offset", "patch+offset"))
    assert out["union"] == 5
    assert out["arm_order"] == ["subtract+offset", "patch+offset",
                                ledger.UNRECORDED_ARM]
    assert out["first_success_by_arm"] == {"subtract+offset": 2,
                                           "patch+offset": 3,
                                           ledger.UNRECORDED_ARM: 1}
    assert out["only_by_arm"] == {"subtract+offset": 1, "patch+offset": 2,
                                  ledger.UNRECORDED_ARM: 1}
    assert out["reroll_by_arm"] == {"subtract+offset": 0, "patch+offset": 2,
                                    ledger.UNRECORDED_ARM: 0}
    text = ledger.summarize(rows, header={"rules": ["sum"], "rungs": ["L0"],
                                          "arms": ["subtract+offset",
                                                   "patch+offset"]})
    assert "| arm | first-success | only this arm | via re-roll |" in text
    assert "| patch+offset | 3 | 2 | 2 |" in text
    assert "FIRST-SUCCESS marginal" in text


def test_the_header_records_knobs_reroll_and_reroll_rungs():
    from types import SimpleNamespace
    from analyzer import fixedpoint as fp
    from analyzer.types import AnalyzerConfig, Exposure
    inputs = SimpleNamespace(format_ref="L:x@1x1", run_dir="/tmp/run",
                             captures=(), provenance={"a": 1})
    config = AnalyzerConfig(knobs={"branches": "state",
                                   "patch_samples_per_cell": 16,
                                   "weights": np.arange(3)},
                            reroll=False, reroll_rungs=("L0",))
    header = fp._header(inputs, config, Exposure(), 7)
    assert header["knobs"] == {"branches": "state",
                               "patch_samples_per_cell": 16,
                               "weights": [0, 1, 2]}
    assert header["reroll"] is False and header["reroll_rungs"] == ["L0"]
    json.dumps(ledger.jsonable(header))
    default = fp._header(inputs, AnalyzerConfig(), Exposure(), 0)
    assert default["knobs"] == {} and default["reroll"] is True
    assert default["reroll_rungs"] == ["L0", "L1", "L2"]


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


def _on_page(page: int, *args, **kwargs):
    row = make_row(*args, **kwargs)
    row.page = page
    return row


def test_render_maps_draws_each_duplex_FACE_and_not_their_blend(tmp_path):
    """Review F14: the two faces of sheet J are both 53x37, so a map
    that groups by stream alone drew one picture of two pages — and
    which verdict survived a tile was the FOLD ORDER of the rows."""
    rows = [_on_page(0, 0, 0, "C", verdict=VERDICT_CERTIFIED),
            _on_page(1, 0, 0, "C")]
    written = ledger.render_maps(rows, tmp_path, tiles_yx=(1, 1), scale=1)
    assert sorted(path.name for path in written) == ["verdict-p0-C.png",
                                                     "verdict-p1-C.png"]
    from PIL import Image
    pixels = {}
    for path in written:
        with Image.open(path) as image:
            pixels[path.name] = image.convert("RGB").getpixel((0, 0))
    assert pixels["verdict-p0-C.png"] == ledger._VERDICT_RGB["certified"]
    assert pixels["verdict-p1-C.png"] == ledger._VERDICT_RGB["open"]

    # and the pictures do not depend on the order the rows arrive in
    reversed_dir = tmp_path / "reversed"
    for path in ledger.render_maps(list(reversed(rows)), reversed_dir,
                                   tiles_yx=(1, 1), scale=1):
        with Image.open(path) as image:
            assert image.convert("RGB").getpixel((0, 0)) == pixels[path.name]


def test_render_maps_keeps_the_bare_name_for_a_single_page_pass(tmp_path):
    """Every sheet-H and sheet-I artefact the record names is
    `verdict-{stream}.png`; a one-page pass keeps it."""
    written = ledger.render_maps(
        [_on_page(0, 0, 0, "C"), _on_page(0, 1, 1, "Y")],
        tmp_path, tiles_yx=(4, 4), scale=2)
    assert sorted(path.name for path in written) == ["verdict-C.png",
                                                     "verdict-Y.png"]


def test_a_duplex_pass_spells_the_face_even_when_only_one_survives(tmp_path):
    """A pass whose rows are all on page 1 is still a duplex pass.

    The rows alone said "one page" and the maps took page 0's names; the
    RUN knows better, and `live_pages` is how it says so.  Without it, a
    page above 0 among the rows is the fallback that says the same.
    """
    rows = [_on_page(1, 0, 0, "C")]
    told = ledger.render_maps(rows, tmp_path / "told", tiles_yx=(1, 1),
                              scale=1, live_pages=(0, 1))
    assert [path.name for path in told] == ["verdict-p1-C.png"]
    guessed = ledger.render_maps(rows, tmp_path / "guessed", tiles_yx=(1, 1),
                                 scale=1)
    assert [path.name for path in guessed] == ["verdict-p1-C.png"]
    # and a run that really has one page keeps the bare name
    alone = ledger.render_maps([_on_page(0, 0, 0, "C")], tmp_path / "alone",
                               tiles_yx=(1, 1), scale=1, live_pages=(0,))
    assert [path.name for path in alone] == ["verdict-C.png"]


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


# --------------------------------------- the live ledger (2026-09-13)

def _writer_row(ty: int, tx: int, stream: str = "Y", **kw):
    return make_row(ty, tx, stream, **kw)


def test_the_header_is_on_disk_before_the_first_row(tmp_path):
    """Item 1: a pass killed at hour three must leave a readable file."""
    path = tmp_path / "ledger.jsonl"
    writer = ledger.LedgerWriter(path, {"seed": 7, "rules": ["sum"]})
    assert path.read_text("utf-8").count("\n") == 1
    assert writer.mints_path == tmp_path / ledger.MINTS_NAME
    assert json.loads(path.read_text("utf-8"))["partial"] is True
    writer.append(_writer_row(1, 2))
    assert path.read_text("utf-8").count("\n") == 2      # flushed per line
    writer.append(_writer_row(3, 4))
    header, rows = ledger.read_rows(path)
    assert header["seed"] == 7 and len(rows) == 2
    assert [row["row_seq"] for row in rows] == [0, 1]
    writer.finish({"seed": 7, "n_rows": 2, "stop_reason": "fixed_point"})
    merged = ledger.read_header(path)
    assert merged["stop_reason"] == "fixed_point" and merged["n_rows"] == 2
    assert merged["partial"] is False and merged["type"] == "header"


def test_a_partial_ledger_says_so_and_a_finished_one_does_not(tmp_path):
    partial = ledger.LedgerWriter(tmp_path / "a.jsonl", {"seed": 1})
    partial.append(_writer_row(0, 0))
    assert ledger.read_header(tmp_path / "a.jsonl")["partial"] is True
    partial.close()                       # killed: no footer, ever
    stats = ledger.ReadStats()
    assert len(list(ledger.iter_rows(tmp_path / "a.jsonl", stats=stats))) == 1
    assert stats.partial is True and stats.footer == {}


def test_a_re_attacked_key_appends_and_every_reader_takes_the_last(tmp_path):
    """Item 1: a flushed line cannot be rewritten, so the LAST row wins."""
    path = tmp_path / "ledger.jsonl"
    writer = ledger.LedgerWriter(path, {"seed": 1})
    first = _writer_row(2, 3, "C")
    first.diag = {"attempts": 1}
    second = _writer_row(2, 3, "C", verdict=VERDICT_CERTIFIED,
                         rules=("sum",),
                         rungs_by_rule={"sum": [("L0", VERDICT_CERTIFIED)]},
                         certifying=("sum", "L0"))
    second.diag = {"attempts": 2}
    other = _writer_row(4, 4, "M")
    other.diag = {"attempts": 1}
    for row in (first, other, second):

        writer.append(row)
    writer.finish({"n_rows": 2})

    assert len(list(ledger.iter_rows(path))) == 3
    stats = ledger.ReadStats()
    latest = list(ledger.iter_rows_latest(path, stats=stats))
    assert stats.rows == 3 and stats.superseded == 1
    assert [(row["ty"], row["tx"], row["diag"]["attempts"]) for row in latest] \
        == [(4, 4, 1), (2, 3, 2)]
    assert latest[-1]["verdict"] == VERDICT_CERTIFIED
    # the summary counts KEYS, not attempts
    assert "Order-free union: 1 tile-stream(s)" in ledger.summarize(
        ledger.iter_rows_latest(path), header={})


def test_a_truncated_last_line_is_skipped_and_counted(tmp_path):
    """What a `kill -9` leaves: the row it was writing, cut in half."""
    path = tmp_path / "ledger.jsonl"
    writer = ledger.LedgerWriter(path, {"seed": 1})
    writer.append(_writer_row(0, 0, "C"))
    writer.append(_writer_row(0, 1, "C"))
    writer.close()
    whole = path.read_text("utf-8")
    path.write_text(whole[:-40], "utf-8")            # mid-row, no newline

    stats = ledger.ReadStats()
    rows = list(ledger.iter_rows_latest(path, stats=stats))
    assert [row["tx"] for row in rows] == [0]
    assert stats.truncated_lines == 1 and stats.rows == 1
    header_stats = ledger.ReadStats()
    header, back = ledger.read_rows(path, stats=header_stats)
    assert header["seed"] == 1 and len(back) == 1
    assert header_stats.truncated_lines == 1
    assert ledger.read_header(path)["partial"] is True


def test_the_mint_file_is_a_ledger_in_miniature(tmp_path):
    """Item 2: one line per certificate, readable by every ledger reader."""
    writer = ledger.LedgerWriter(tmp_path / "ledger.jsonl", {"seed": 3})
    writer.mint({"page": 0, "ty": 1, "tx": 2, "stream_id": "C",
                 "verdict": VERDICT_CERTIFIED, "certifying_rung": "L0",
                 "rungs": {"user_bits": np.zeros(4, np.uint8)}})
    writer.finish({"n_rows": 0})
    rows = list(ledger.iter_rows(writer.mints_path))
    assert len(rows) == 1 and rows[0]["mint"] is True
    assert rows[0]["rungs"]["user_bits"] == [0, 0, 0, 0]
    assert ledger.read_header(writer.mints_path)["seed"] == 3
    assert ledger.read_header(writer.mints_path)["n_mints"] == 1


def test_slim_row_keeps_the_report_and_drops_the_megabyte(tmp_path):
    row = make_row(1, 1, "C", rules=("sum",), verdict=VERDICT_CERTIFIED,
                   rungs_by_rule={"sum": [("L0", VERDICT_CERTIFIED)]},
                   certifying=("sum", "L0"))
    row.evidence = {"cap/l0|subtract": {"n_labels": 120}}
    row.combined = {"sum": {"mean_abs": 3.0}}
    row.rungs["sum"][0]["detail"] = {"hard_packed_b64": "A" * 683}
    slim = ledger.slim_row(row)
    assert "evidence" not in slim and "combined" not in slim
    assert set(slim["rungs"]["sum"][0]) == {"rung", "verdict",
                                            "unsat_at_exit"}
    assert "user_bits" not in slim["rungs"]

    assert slim["verdict"] == VERDICT_CERTIFIED
    assert slim["rungs"]["sum"][0]["unsat_at_exit"] == 0
    assert ledger.attribution([slim])["union"] == 1


def test_opening_a_writer_keeps_the_previous_pass_aside(tmp_path):
    """A streamed writer opens BEFORE the pass runs, so it may not
    truncate: a second pass into one out dir would otherwise destroy the
    first's ledger and mints before doing any work (the batch writer it
    replaced only overwrote at the end)."""
    path = tmp_path / "ledger.jsonl"
    first = ledger.LedgerWriter(path, {"seed": 1})
    first.append(_writer_row(0, 0, "C"))
    first.mint({"page": 0, "ty": 0, "tx": 0, "stream_id": "C",
                "verdict": VERDICT_CERTIFIED,
                "rungs": {"user_bits": np.zeros(4, np.uint8)}})
    first.finish({"n_rows": 1})

    second = ledger.LedgerWriter(path, {"seed": 2})
    assert set(second.kept_aside) == {
        tmp_path / "ledger.jsonl.bak", tmp_path / "mints.jsonl.bak"}
    second.finish({"n_rows": 0})
    # the first pass's record survives, whole, under .bak
    header, rows = ledger.read_rows(tmp_path / "ledger.jsonl.bak")
    assert header["seed"] == 1 and len(rows) == 1
    assert len(list(ledger.iter_rows(tmp_path / "mints.jsonl.bak"))) == 1
    assert ledger.read_header(path)["seed"] == 2
    assert list(ledger.iter_rows(path)) == []


def test_the_mint_file_is_named_after_its_ledger(tmp_path):
    """`read` and `ladder` write into the SAME out dir by default, so one
    fixed mint name would have had the two passes share a file."""
    assert ledger.mints_beside("x/ledger.jsonl") == Path("x/mints.jsonl")
    assert ledger.mints_beside("x/ledger-read.jsonl") == \
        Path("x/mints-read.jsonl")
    assert ledger.mints_beside("x/census.jsonl") == Path("x/census-mints.jsonl")
    ladder = ledger.LedgerWriter(tmp_path / "ledger.jsonl", {"seed": 1})
    read = ledger.LedgerWriter(tmp_path / "ledger-read.jsonl", {"seed": 1})
    assert ladder.mints_path != read.mints_path
    assert read.kept_aside == ()                 # it took nothing of the other's
    ladder.finish({}), read.finish({})


def test_a_truncated_last_line_that_ends_in_a_brace_is_still_truncated(
        tmp_path):
    """The cheap key scan reads line HEADS, so a cut that lands just
    after a nested `}` looks complete to it — and the key's earlier,
    COMPLETE row would then be suppressed as superseded and lost.  The
    last line is parsed for exactly that reason."""
    path = tmp_path / "ledger.jsonl"
    writer = ledger.LedgerWriter(path, {"seed": 1})
    writer.append(_writer_row(0, 0, "C"))            # the complete one
    writer.append(_writer_row(0, 0, "C"))            # the re-attack, cut
    writer.close()
    lines = path.read_text("utf-8").splitlines()
    cut = lines[-1]
    cut = cut[:cut.index('"diag"')] + '"diag": {"seconds": 1.0}'
    assert cut.endswith("}") and not cut.endswith("}}")
    path.write_text("\n".join(lines[:-1] + [cut]) + "\n", "utf-8")

    stats = ledger.ReadStats()
    rows = list(ledger.iter_rows_latest(path, stats=stats))
    assert len(rows) == 1 and rows[0]["row_seq"] == 0
    assert stats.truncated_lines == 1 and stats.superseded == 0


def test_a_torn_INTERIOR_line_does_not_take_the_complete_row_with_it(
        tmp_path):
    """Review §6, 2026-09-13: a tear anywhere, not only at the end.

    The key scan used to count any line that ended in `}`, and repair
    only the LAST one — so a torn line in the MIDDLE counted as a second
    row for its key, the complete row before it was dropped as
    superseded, and the torn one did not parse either.  The key
    vanished.  Both passes agree on whole rows now: a row line ends in
    `"row_seq": <n>}` or it is decoded to find out.
    """
    path = tmp_path / "ledger.jsonl"
    writer = ledger.LedgerWriter(path, {"seed": 1})
    writer.append(_writer_row(0, 0, "C"))            # the complete one
    writer.append(_writer_row(0, 0, "C"))            # the re-attack, cut
    writer.append(_writer_row(0, 1, "C"))            # and a later key
    writer.finish({"n_rows": 3})
    lines = path.read_text("utf-8").splitlines()
    torn = lines[2]
    torn = torn[:torn.index('"diag"')] + '"diag": {"seconds": 1.0}'
    assert torn.endswith("}") and not torn.endswith("}}")
    path.write_text("\n".join(lines[:2] + [torn] + lines[3:]) + "\n", "utf-8")

    stats = ledger.ReadStats()
    rows = list(ledger.iter_rows_latest(path, stats=stats))
    assert [(row["tx"], row["row_seq"]) for row in rows] == [(0, 0), (1, 2)]
    assert stats.truncated_lines == 1 and stats.superseded == 0


def test_the_one_tear_the_scan_does_not_catch_is_the_one_it_cannot_be_dealt(
        tmp_path):
    """M5: a head CONCATENATED with the next row's tail, and the writer.

    Both patterns match such a line, so it counts as the first key's and
    then fails to parse — the first key's complete row goes with it.
    The docstring says so rather than paying 384 us a line to close it,
    and what makes that safe is the writer: `"w"`, one process, no
    resume, so no concatenation can be written.  Both halves are pinned
    here, the behaviour and the reason it is out of reach.
    """
    path = tmp_path / "ledger.jsonl"
    writer = ledger.LedgerWriter(path, {"seed": 1})
    writer.append(_writer_row(0, 0, "C"))            # the complete one
    writer.append(_writer_row(0, 0, "C"))            # the re-attack
    writer.append(_writer_row(0, 1, "C"))
    writer.finish({"n_rows": 3})
    lines = path.read_text("utf-8").splitlines()
    glued = lines[2][:lines[2].index('"diag"')] + lines[3]
    assert ledgerio._ROW_HEAD.match(glued) is not None
    assert ledgerio._ROW_TAIL.search(glued[-ledgerio._ROW_TAIL_WINDOW:])
    assert glued.count('{"type": "row"') == 2       # what would catch it

    path.write_text("\n".join(lines[:2] + [glued]) + "\n", "utf-8")
    rows = list(ledger.iter_rows_latest(path))
    assert [(row["tx"], row["row_seq"]) for row in rows] == []

    source = inspect.getsource(ledgerio.LedgerWriter)
    assert 'open(self.path, "w"' in source
