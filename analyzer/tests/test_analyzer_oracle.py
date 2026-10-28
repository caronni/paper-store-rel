"""W2 — `analyzer.oracle`, the score column (DESIGN §7).

Synthetic first: the information rate, d', AUC and the waterfall are
arithmetic and are pinned against vectors whose answer is known by
construction.  The sheet-I legs then check the truth vector itself —
that `true_sequential` is the same as what the format writes onto the
cells — and score one real certified tile.
"""

from __future__ import annotations

import numpy as np
import pytest

from analyzer import oracle
from analyzer.types import Truth

from . import _synthetic as syn
from ._analyzer_fixtures import i_inputs, i_truth, needs_i_run


def _truth_for(frame) -> Truth:
    return Truth(format_ref=frame.ref, gen_dir=None, field_dir=None,
                 payload_path=None, payload_sha256="0" * 64,
                 payload_bytes=0, n_pages=1,
                 tiles_yx=tuple(frame.row.tiles_yx),
                 streams=tuple(fact.stream_id
                               for fact in frame.row.streams),
                 user_bits={frame.key: frame.user}, fields={}, manifest={})


# ------------------------------------------------------------ the vectors

def test_true_sequential_is_the_printed_vector():
    frame = syn.build_frame()
    truth = _truth_for(frame)
    printed = oracle.true_sequential(truth, frame.row, frame.key)
    assert np.array_equal(printed, frame.printed)
    # and the same thing read back through the cells it is printed on
    assert np.array_equal(printed, syn.through_cells(frame))


def test_true_sequential_refuses_an_unknown_address():
    frame = syn.build_frame()
    truth = _truth_for(frame)
    assert oracle.true_sequential(truth, frame.row, (0, 0, 0, "C")) is None


def test_true_codeword_matches_the_synthetic_encoder():
    from analyzer import mother as mother_mod
    frame = syn.build_frame()
    truth = _truth_for(frame)
    mother = mother_mod.to_mother(np.zeros(frame.row.payload_cells),
                                  frame.row, frame.key, metadata_bit=None)
    assert np.array_equal(oracle.true_codeword(truth, frame.key, mother),
                          frame.codeword)


# -------------------------------------------------- the information rate

def test_information_rate_is_zero_on_a_zero_llr():
    bits = np.array([0, 1, 0, 1] * 64, np.uint8)
    out = oracle.soft_information_rate(np.zeros(bits.size), bits, 256,
                                       seed=1, draws=50)
    assert out["information_bits_per_cell"] == pytest.approx(0.0, abs=1e-12)
    assert out["R"] == pytest.approx(0.0, abs=1e-12)


def test_information_rate_is_one_bit_per_cell_when_the_llr_is_certain():
    rng = np.random.default_rng(3)
    bits = rng.integers(0, 2, 512).astype(np.uint8)
    llr = np.where(bits > 0, 40.0, -40.0)
    out = oracle.soft_information_rate(llr, bits, 512, seed=2, draws=100)
    assert out["information_bits_per_cell"] == pytest.approx(1.0, abs=1e-9)
    assert out["R"] == pytest.approx(1.0, abs=1e-9)
    assert out["R_upper"] >= out["R"] - 1e-9


def test_information_rate_goes_negative_when_the_llr_is_confidently_wrong():
    rng = np.random.default_rng(4)
    bits = rng.integers(0, 2, 256).astype(np.uint8)
    llr = np.where(bits > 0, -20.0, 20.0)
    out = oracle.soft_information_rate(llr, bits, 256, seed=3, draws=50)
    assert out["information_bits_per_cell"] < -20.0


def test_information_rate_scales_with_the_observed_count():
    rng = np.random.default_rng(5)
    bits = rng.integers(0, 2, 1000).astype(np.uint8)
    llr = np.where(bits > 0, 40.0, -40.0)
    full = oracle.soft_information_rate(llr, bits, 2000, seed=6, draws=50)
    half = oracle.soft_information_rate(llr[:500], bits[:500], 2000, seed=6,
                                        draws=50)
    assert full["R"] == pytest.approx(0.5, abs=1e-9)
    assert half["R"] == pytest.approx(0.25, abs=1e-9)


def test_information_rate_is_deterministic_in_the_seed():
    rng = np.random.default_rng(7)
    bits = rng.integers(0, 2, 400).astype(np.uint8)
    llr = syn.channel_llr(bits, 0.05, 11)
    a = oracle.soft_information_rate(llr, bits, 400, seed=99, draws=200)
    b = oracle.soft_information_rate(llr, bits, 400, seed=99, draws=200)
    c = oracle.soft_information_rate(llr, bits, 400, seed=100, draws=200)
    assert a["R_upper"] == b["R_upper"]
    assert a["R_upper"] != c["R_upper"]


# ------------------------------------------------------ d', AUC, clusters

def test_d_prime_and_auc_on_a_separated_pair():
    rng = np.random.default_rng(8)
    labels = np.array([0] * 500 + [1] * 500, np.uint8)
    values = np.where(labels > 0, 4.0, -4.0) + rng.normal(0, 1.0, 1000)
    assert oracle._d_prime(values, labels) == pytest.approx(8.0, rel=0.15)
    assert oracle._auc(values, labels) > 0.999


def test_auc_is_a_half_on_noise():
    rng = np.random.default_rng(9)
    labels = rng.integers(0, 2, 2000).astype(np.uint8)
    assert oracle._auc(rng.normal(0, 1, 2000), labels) == pytest.approx(
        0.5, abs=0.05)


def test_clustering_ratio_is_about_one_for_uniform_points():
    rng = np.random.default_rng(10)
    points = rng.integers(0, 64, (200, 2))
    out = oracle._clustering(points, 64 * 64)
    assert out["clustering_ratio"] == pytest.approx(1.0, abs=0.35)


def test_clustering_ratio_drops_when_the_wrong_cells_bunch():
    points = np.stack(np.meshgrid(np.arange(10), np.arange(10)),
                      axis=-1).reshape(-1, 2)
    out = oracle._clustering(points, 64 * 64)
    assert out["clustering_ratio"] < 0.5


# --------------------------------------------------------- the waterfall

def test_waterfall_finds_the_crossings():
    rows = []
    for index in range(400):
        rate = index / 200.0                       # 0 .. 2
        rows.append({"stream_id": "Y", "rung": "L0", "R": rate,
                     "certified": rate > 1.0})
    out = oracle.waterfall(rows)
    entry = out["Y/L0"]
    assert entry["n"] == 400
    assert entry["n_certified"] == 199
    assert 0.9 < entry["R50"] < 1.1
    assert entry["R05"] is not None and entry["R05"] <= entry["R50"]


def test_waterfall_skips_rows_without_a_rate():
    out = oracle.waterfall([{"stream_id": "C", "rung": "L0", "R": None,
                             "certified": True}])
    assert out == {}


# ------------------------------------------------------- score_evidence

def test_score_evidence_without_a_field_still_reports_the_rate():
    from analyzer.types import Evidence
    frame = syn.build_frame()
    truth = _truth_for(frame)
    llr = syn.channel_llr(frame.printed, 0.03, 21)
    observed = np.ones(llr.size, bool)
    evidence = Evidence(key=frame.key, lane=("abcdef012345", 0),
                        arm="subtract+offset", llr_sequential=llr,
                        observed=observed)
    out = oracle.score_evidence(evidence, truth, None, None, frame.row,
                                frame.key, seed=5, bootstrap_draws=50)
    assert out["scoreable"] is True
    assert out["cell_error_map"] == pytest.approx(0.03, abs=0.01)
    assert out["auc"] > 0.9
    assert out["R"] is not None and out["R"] > 0.0
    assert out["by_sibling_state"] == {}
    assert out["clustering"]["n_wrong"] > 0
    assert out["capture_agreement_on_wrong"] is None


def test_score_evidence_agreement_uses_the_peer_lanes():
    from analyzer.types import Evidence
    frame = syn.build_frame()
    truth = _truth_for(frame)
    llr = syn.channel_llr(frame.printed, 0.05, 31)
    observed = np.ones(llr.size, bool)
    mine = Evidence(key=frame.key, lane=("aaaaaaaaaaaa", 0), arm="a",
                    llr_sequential=llr, observed=observed)
    twin = Evidence(key=frame.key, lane=("bbbbbbbbbbbb", 0), arm="a",
                    llr_sequential=llr, observed=observed)
    out = oracle.score_evidence(mine, truth, None, None, frame.row,
                                frame.key, others=[mine, twin], seed=5,
                                bootstrap_draws=20)
    # an identical twin is wrong wherever this lane is wrong.
    assert out["n_peer_lanes"] == 1
    assert out["capture_agreement_on_wrong"] == pytest.approx(1.0)


def test_score_evidence_refuses_an_address_outside_the_gt_domain():
    from analyzer.types import Evidence
    frame = syn.build_frame()
    truth = _truth_for(frame)
    other = (0, 0, 0, "Y")
    evidence = Evidence(key=other, lane=("aaaaaaaaaaaa", 0), arm="a",
                        llr_sequential=np.zeros(frame.row.payload_cells),
                        observed=np.ones(frame.row.payload_cells, bool))
    out = oracle.score_evidence(evidence, truth, None, None, frame.row,
                                other)
    assert out["scoreable"] is False


# ----------------------------------------------------------- score_rung

def test_score_rung_counts_bits_wrong_with_every_denominator():
    from analyzer import ladder as ladder_mod
    from analyzer.types import Exposure
    frame = syn.build_frame()
    truth = _truth_for(frame)
    llr = syn.channel_llr(frame.printed, 0.02, 41)
    exposure = Exposure()
    results = ladder_mod.run_ladder(llr, frame.row, frame.key,
                                    rungs=("L0",), knobs={"keep_hard": True},
                                    exposure=exposure)
    from analyzer import mother as mother_mod
    mother = mother_mod.to_mother(llr, frame.row, frame.key,
                                  metadata_bit=None)
    scored = oracle.score_rung(results[0], truth, frame.key, mother)
    assert scored["rung"] == "L0"
    assert "bits_wrong_mother" in scored
    denominators = scored["denominators"]
    assert denominators["mother"] == 4096
    assert denominators["transmitted"] == frame.row.payload_cells
    assert denominators["active"] == frame.active
    assert denominators["user"] == frame.active - 32
    if scored["verdict"] == "certified":
        assert scored["bits_wrong_mother"] == 0


def test_score_rung_without_a_hard_vector_still_reports_the_verdict():
    from analyzer import ladder as ladder_mod
    from analyzer.types import Exposure
    frame = syn.build_frame()
    truth = _truth_for(frame)
    llr = syn.channel_llr(frame.printed, 0.02, 42)
    results = ladder_mod.run_ladder(llr, frame.row, frame.key,
                                    rungs=("L0",), exposure=Exposure())
    scored = oracle.score_rung(results[0], truth, frame.key, None)
    assert "bits_wrong_mother" not in scored
    assert scored["verdict"] in ("certified", "open")


# --------------------------------------------------------- sheet I legs

@needs_i_run
def test_sheet_i_true_sequential_matches_the_emitted_field():
    run = i_inputs()
    truth = i_truth()
    from holo3.plugins import color_sites
    key = sorted(run.certificates)[0]
    page, ty, tx, stream_id = key
    printed = oracle.true_sequential(truth, run.row, key)
    field = truth.fields[page]
    grid = oracle.sequential_cells(run.row, key)
    plane = {"C": 0, "M": 1, "Y": 2}[stream_id]
    cells = np.stack((grid[:, 0] + ty * 64, grid[:, 1] + tx * 64), axis=1)
    emitted = field.plane_bits[plane][cells[:, 0], cells[:, 1]]
    assert np.array_equal(np.asarray(printed, np.uint8),
                          np.asarray(emitted, np.uint8))
    del color_sites
