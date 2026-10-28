"""`analyzer score` — the offline scorer (RULED 2026-09-04).

The synthetic half builds a ledger by hand around a real format row, so
the certificate comparison, the per-rung bits-wrong columns (read out of
the packed hard vectors the ledger now carries) and the WRONG report can
be exercised with no run dir and no pixels.  The sheet-I half runs the
whole command against the real `I-resume3` ledger and the emitted
payload, and then against a payload with one byte flipped — which is
what replaced the oracle-permutation control: the blind columns come
straight off the ledger and do not move, the oracle columns do.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
import pytest

from analyzer import ladder as ladder_mod
from analyzer import ledger as ledger_mod
from analyzer import mother as mother_mod
from analyzer import oracle as oracle_mod
from analyzer import score as score_mod
from analyzer.types import (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST,
                            Exposure, Truth)

from . import _synthetic as syn
from ._analyzer_fixtures import I_GEN_DIR, I_PAYLOAD, REPO

I_LEDGER = REPO / "scratch/analyzer/I-resume3/ledger.jsonl"

needs_i_ledger = pytest.mark.skipif(
    not I_LEDGER.exists() or not I_PAYLOAD.exists(),
    reason=f"the sheet-I ledger {I_LEDGER} or its payload is absent")


def _truth_for(frame, *, bits=None) -> Truth:
    return Truth(format_ref=frame.ref, gen_dir=None, field_dir=None,
                 payload_path=None, payload_sha256="0" * 64, payload_bytes=0,
                 n_pages=1, tiles_yx=tuple(frame.row.tiles_yx),
                 streams=tuple(fact.stream_id for fact in frame.row.streams),
                 user_bits={frame.key: frame.user if bits is None else bits},
                 fields={}, manifest={})


def _ledger_row(frame, *, bits, rung="L0", rule="sum", verdict=None,
                hard=None) -> dict:
    """A ledger row the way `fixedpoint` writes one, by hand."""
    detail: dict = {"path": "production"}
    if hard is not None:
        detail["hard_packed_b64"] = base64.b64encode(
            np.packbits(np.asarray(hard, np.uint8)).tobytes()).decode()
    verdict = verdict or VERDICT_CERTIFIED
    page, ty, tx, stream_id = frame.key
    return {
        "type": "row", "page": page, "ty": ty, "tx": tx,
        "stream_id": stream_id, "band": "live", "verdict": verdict,
        "certifying_rule": rule, "certifying_rung": rung,
        "certifying_arm": "subtract+offset", "generation": 0,
        "rungs": {rule: [{"rung": rung, "verdict": verdict, "n_iters": 60,
                          "unsat_at_exit": 0, "syndrome_ok": True,
                          "posterior_summary": {}, "seconds": 0.1,
                          "crc_consults_distinct": 1, "detail": detail}],
                  "user_bits": [int(value) for value in bits]},
    }


# --------------------------------------------------------- the plumbing

def test_format_ref_comes_from_the_ledger_and_conflicts_refuse():
    left = ("a", {"format_ref": "L:x@1x1"})
    right = ("b", {"format_ref": "L:y@1x1"})
    assert score_mod.format_ref_of([left], None) == "L:x@1x1"
    assert score_mod.format_ref_of([left, right], "L:z@1x1") == "L:z@1x1"
    with pytest.raises(score_mod.ScoreError, match="different format refs"):
        score_mod.format_ref_of([left, right], None)
    with pytest.raises(score_mod.ScoreError, match="no ledger header"):
        score_mod.format_ref_of([("c", {})], None)


def test_a_missing_ledger_refuses_rather_than_scoring_nothing(tmp_path):
    with pytest.raises(score_mod.ScoreError, match="is absent"):
        score_mod.read_headers([tmp_path / "nope.jsonl"])
    with pytest.raises(score_mod.ScoreError, match="no --ledger"):
        score_mod.read_headers([])


def test_the_ledgers_are_streamed_not_materialised():
    """The 26 GB lesson: sheet H's five ledgers are 18 GB of JSON.

    `read_headers` reads one line per file and the row loop goes
    through `ledger.iter_rows`, so nothing ever holds a whole ledger.
    """
    import inspect
    source = inspect.getsource(score_mod)
    assert "ledger_mod.iter_rows" in source
    assert "ledger_mod.read_rows" not in source   # the 26 GB call


def test_a_row_beyond_the_reconstructed_pages_refuses(tmp_path):
    """Never mis-scored: page 1 against a one-page reconstruction stops."""
    frame = syn.build_frame()
    row = _ledger_row(frame, bits=frame.user)
    row["page"] = 1
    path = tmp_path / "l.jsonl"
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(json.dumps({"type": "header",
                                 "format_ref": frame.ref}) + "\n")
        stream.write(json.dumps(row) + "\n")
    with pytest.raises(score_mod.ScoreError, match="pass --pages 2"):
        score_mod.score([path], I_PAYLOAD, tmp_path / "out")


# ------------------------------------------------------ one row, scored

def test_a_matching_certificate_scores_certified():
    frame = syn.build_frame()
    row = _ledger_row(frame, bits=frame.user)
    scored = score_mod.score_row(row, _truth_for(frame), frame.row,
                                 mother_cache={})
    assert scored["verdict"] == VERDICT_CERTIFIED
    assert scored["certificate_matches_gt"] is True
    assert scored["certificate_bits_wrong"] == 0
    assert scored["scoreable"] is True


def test_a_mismatching_certificate_is_reported_wrong_on_a_direct_rung():
    frame = syn.build_frame()
    forged = frame.user.copy()
    forged[:5] ^= 1
    row = _ledger_row(frame, bits=forged)
    scored = score_mod.score_row(row, _truth_for(frame), frame.row,
                                 mother_cache={})
    assert scored["verdict"] == "wrong"
    assert scored["certificate_bits_wrong"] == 5
    assert score_mod.wrong_keys([scored])[0]["bits_wrong"] == 5
    assert score_mod.wrong_keys([scored])[0]["list_rung"] is False


def test_a_mismatching_list_rung_certificate_is_a_false_accept():
    frame = syn.build_frame()
    forged = frame.user.copy()
    forged[3] ^= 1
    row = _ledger_row(frame, bits=forged, rung="L4",
                      verdict=VERDICT_CERTIFIED_LIST)
    scored = score_mod.score_row(row, _truth_for(frame), frame.row,
                                 mother_cache={})
    assert scored["verdict"] == "false_accept"
    assert score_mod.wrong_keys([scored])[0]["list_rung"] is True


def test_an_address_outside_the_payload_is_unscoreable():
    frame = syn.build_frame()
    truth = _truth_for(frame)
    row = _ledger_row(frame, bits=frame.user)
    row["ty"] = row["ty"] + 1                      # an address truth lacks
    scored = score_mod.score_row(row, truth, frame.row, mother_cache={})
    assert scored["verdict"] == "unscoreable"
    assert scored["scoreable"] is False


def test_only_the_certifying_rung_is_credited_with_the_row_s_bits():
    """A rung that did not mint the certificate is not adjudicated by it."""
    frame = syn.build_frame()
    row = _ledger_row(frame, bits=frame.user, rung="L2:damped@300")
    row["rungs"]["sum"].insert(0, {"rung": "L0", "verdict": "open",
                                   "n_iters": 60, "unsat_at_exit": 12,
                                   "syndrome_ok": False,
                                   "posterior_summary": {}, "seconds": 0.1,
                                   "crc_consults_distinct": 0, "detail": {}})
    scored = score_mod.score_row(row, _truth_for(frame), frame.row,
                                 mother_cache={})
    rungs = {item["rung"]: item for item in scored["rungs"]["sum"]}
    assert rungs["L0"]["verdict"] == "open"
    assert rungs["L0"]["gt_bits_wrong_user"] is None
    assert rungs["L2:damped@300"]["verdict"] == VERDICT_CERTIFIED


# ------------------------------------------- the packed hard vector leg

def test_bits_wrong_comes_out_of_the_packed_hard_vector():
    """The column the run can no longer compute, computed offline.

    A rung that did NOT certify still carries its exit hard vector, and
    that is the whole of DESIGN §6's deferral histogram: here a codeword
    with four flipped mother bits is scored against the payload's own.
    """
    frame = syn.build_frame()
    hard = frame.codeword.copy()
    hard[:4] ^= 1
    row = _ledger_row(frame, bits=frame.user, hard=hard)
    scored = score_mod.score_row(row, _truth_for(frame), frame.row,
                                 mother_cache={})
    item = scored["rungs"]["sum"][0]
    assert item["bits_wrong_mother"] == 4
    assert item["denominators"] == {"mother": 4096, "transmitted": 3976,
                                    "active": frame.active,
                                    "user": frame.active - 32}
    hist = score_mod.bits_wrong_histogram([scored])
    assert hist["n_samples"] == 1
    assert sum(hist["bits_wrong_active"].values()) == 1
    assert list(hist["by_rung"]) == ["L0"]


def test_the_packed_vector_round_trips_from_a_live_rung():
    """`keep_hard` -> `_rung_dict` -> the ledger -> `oracle.packed_hard`."""
    from analyzer import fixedpoint as fp
    frame = syn.build_frame()
    llr = syn.channel_llr(frame.printed, 0.02, 11)
    results = ladder_mod.run_ladder(llr, frame.row, frame.key, rungs=("L0",),
                                    knobs={"keep_hard": True},
                                    exposure=Exposure())
    stored = fp._rung_dict(results[0])
    live = oracle_mod.packed_hard(results[0])
    assert live == oracle_mod.packed_hard(stored)
    mother = mother_mod.to_mother(llr, frame.row, frame.key,
                                  metadata_bit=None)
    scored = oracle_mod.score_rung(stored, _truth_for(frame), frame.key,
                                   mother)
    assert scored["bits_wrong_mother"] == 0        # a clean channel


def test_verdict_against_truth_only_ever_downgrades():
    assert oracle_mod.verdict_against_truth("L0", "open", None) == "open"
    assert oracle_mod.verdict_against_truth(
        "L0", VERDICT_CERTIFIED, 0) == VERDICT_CERTIFIED
    assert oracle_mod.verdict_against_truth("L0", VERDICT_CERTIFIED,
                                            3) == "wrong"
    assert oracle_mod.verdict_against_truth("L4", VERDICT_CERTIFIED_LIST,
                                            3) == "false_accept"
    assert oracle_mod.verdict_against_truth(
        "L7a", VERDICT_CERTIFIED, None) == "unscoreable"
    assert oracle_mod.is_direct("L2:damped@300") is True
    assert oracle_mod.is_direct("L4") is False


def test_the_waterfall_needs_r_and_says_so_without_it():
    frame = syn.build_frame()
    row = _ledger_row(frame, bits=frame.user)
    scored = score_mod.score_row(row, _truth_for(frame), frame.row,
                                 mother_cache={})
    assert score_mod.waterfall_rows([scored]) == []
    scored["evidence"] = {"cap/l0": {"R": 0.91}}
    flat = score_mod.waterfall_rows([scored])
    assert flat == [{"stream_id": "C", "rung": "L0", "R": 0.91,
                     "certified": True}]


def test_the_splits_pool_by_cell_count_not_by_lane():
    """DESIGN §7's splits, summarised: a big lane must outweigh a tiny one.

    Two lanes of one tile see the same sibling state; one read 4,000
    cells at 5 % error, the other 100 at 50 %.  The pooled error is
    (200 + 50) / 4100 = 6.1 %, not the 27.5 % a mean of rates would give.
    """
    rows = [{"stream_id": "Y", "evidence": {
        "capA/l2": {"scoreable": True,
                    "by_sibling_state": {"0/certified": {"n": 4000,
                                                         "cell_error": 0.05}},
                    "by_context_bin": {"3": {"n": 4000, "cell_error": 0.05}},
                    "capture_agreement_on_wrong": 0.8},
        "capB/l2": {"scoreable": True,
                    "by_sibling_state": {"0/certified": {"n": 100,
                                                         "cell_error": 0.5}},
                    "by_context_bin": {"3": {"n": 100, "cell_error": 0.5}},
                    "capture_agreement_on_wrong": 0.6}}}]
    split = score_mod.pooled_split(rows, "by_sibling_state")
    assert split["Y"]["0/certified"]["n"] == 4100
    assert split["Y"]["0/certified"]["cell_error"] == pytest.approx(
        250 / 4100)
    assert score_mod.pooled_split(rows, "by_context_bin")["Y"]["3"]["n"] \
        == 4100
    assert score_mod.pooled_agreement(rows) == {
        "Y": {"n": 2, "mean": pytest.approx(0.7)}}


def test_a_refused_lane_never_enters_a_split():
    """`scoreable` False is a refusal, not a zero-error observation."""
    rows = [{"stream_id": "C", "evidence": {
        "capA/l2": {"scoreable": False, "reason": "outside the GT domain",
                    "by_sibling_state": {"0/certified": {"n": 9,
                                                         "cell_error": 1.0}}},
        "capB/l2": {"refusal": "no_lane_sees_this_tile"}}}]
    assert score_mod.pooled_split(rows, "by_sibling_state") == {}
    assert score_mod.pooled_agreement(rows) == {}


def test_the_report_says_the_splits_need_the_emitted_field():
    frame = syn.build_frame()
    row = _ledger_row(frame, bits=frame.user)
    scored = score_mod.score_row(row, _truth_for(frame), frame.row,
                                 mother_cache={})
    text = score_mod.render({"format_ref": frame.ref}, [scored])
    assert "these splits need `--gt-dir`" in text
    assert "## Capture agreement on the wrong cells" in text


# ----------------------------------------------------- the sheet-I legs

@needs_i_ledger
def test_the_sheet_i_ledger_scores_clean_against_the_emitted_payload(
        tmp_path):
    """Q1: three certificates, checked bit for bit, none wrong."""
    header = score_mod.score([I_LEDGER], I_PAYLOAD, tmp_path,
                             gt_dir=I_GEN_DIR)
    print(f"\nscore(I-resume3): {header['n_certificates_checked']} "
          f"certificates checked, {header['n_wrong']} wrong, "
          f"{header['n_false_accept']} false accept(s)")
    assert header["n_certificates_checked"] == 3
    assert header["n_wrong"] == 0 and header["n_false_accept"] == 0
    assert header["verdicts"] == {"certified": 3}
    assert header["wrong_keys"] == []
    assert header["payload_source"].startswith("generation manifest")
    assert header["gates"] == {}                   # no run dir, no gates
    assert (tmp_path / "score.md").exists()
    lines = (tmp_path / "score.jsonl").read_text("utf-8").splitlines()
    assert json.loads(lines[0])["type"] == "header"
    assert len(lines) == 4


@needs_i_ledger
def test_a_payload_with_one_flipped_byte_is_reported_wrong(tmp_path):
    """What replaced the oracle-permutation control.

    The ledger is BLIND — the same file, unchanged — so every column
    that comes off it is identical between the two scorings; the only
    thing that moves is the payload comparison, which is exactly the
    claim the permutation control used to defend by running the battery
    twice.
    """
    corrupt = tmp_path / "payload-flipped.bin"
    data = bytearray(I_PAYLOAD.read_bytes())
    data[1000] ^= 0xFF
    corrupt.write_bytes(bytes(data))

    good = score_mod.score([I_LEDGER], I_PAYLOAD, tmp_path / "good",
                           gt_dir=I_GEN_DIR)
    bad = score_mod.score([I_LEDGER], corrupt, tmp_path / "bad")
    print(f"\nflipped-byte payload: {bad['n_wrong']} wrong, keys "
          f"{[item['key'] for item in bad['wrong_keys']]}")
    assert bad["n_wrong"] == 3 and good["n_wrong"] == 0
    assert all(item["bits_wrong"] > 0 for item in bad["wrong_keys"])
    # the BLIND columns are the ledger's own and do not move
    for left, right in zip(_rows(tmp_path / "good"), _rows(tmp_path / "bad")):
        assert left["blind_verdict"] == right["blind_verdict"]
        assert left["certifying_rung"] == right["certifying_rung"]
        assert [item["blind_verdict"] for item in left["rungs"]["sum"]] == \
            [item["blind_verdict"] for item in right["rungs"]["sum"]]
        assert [item["unsat_at_exit"] for item in left["rungs"]["sum"]] == \
            [item["unsat_at_exit"] for item in right["rungs"]["sum"]]
    assert bad["payload_source"].startswith("given bytes")


def _rows(out_dir: Path) -> list[dict]:
    _header, rows = ledger_mod.read_rows(out_dir / score_mod.SCORE_ROWS)
    return rows


@needs_i_ledger
def test_the_cli_score_exits_2_when_a_certificate_disagrees(tmp_path):
    from analyzer import cli
    corrupt = tmp_path / "payload-flipped.bin"
    data = bytearray(I_PAYLOAD.read_bytes())
    data[2048] ^= 0x0F
    corrupt.write_bytes(bytes(data))
    assert cli.main(["score", "--ledger", str(I_LEDGER),
                     "--payload", str(I_PAYLOAD), "--gt-dir", str(I_GEN_DIR),
                     "--out", str(tmp_path / "clean")]) == 0
    assert cli.main(["score", "--ledger", str(I_LEDGER),
                     "--payload", str(corrupt),
                     "--out", str(tmp_path / "dirty")]) == cli.EXIT_WRONG


@needs_i_ledger
def test_a_payload_the_manifest_disowns_refuses(tmp_path):
    """With `--gt-dir` the two must agree; without it, no gate exists."""
    from analyzer import truth as truth_mod
    corrupt = tmp_path / "payload-flipped.bin"
    data = bytearray(I_PAYLOAD.read_bytes())
    data[7] ^= 0x01
    corrupt.write_bytes(bytes(data))
    with pytest.raises(truth_mod.TruthError, match="the manifest declares"):
        score_mod.score([I_LEDGER], corrupt, tmp_path / "out",
                        gt_dir=I_GEN_DIR)


@needs_i_ledger
def test_the_bits_wrong_map_is_the_scorer_s_picture(tmp_path):
    score_mod.score([I_LEDGER], I_PAYLOAD, tmp_path, gt_dir=I_GEN_DIR)
    written = score_mod.render_maps(_rows(tmp_path), tmp_path,
                                    tiles_yx=(4, 4), scale=2)
    assert sorted(path.name for path in written) == ["bits-wrong-C.png",
                                                     "bits-wrong-Y.png"]
