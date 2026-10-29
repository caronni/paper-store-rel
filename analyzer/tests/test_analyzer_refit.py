"""W8 B4 — `analyzer.refit`: the decoder-feedback rung `L3f`, the typed
pseudo-label door, the per-key refit budget, and T1 (temperature).

Synthetic throughout (`_synthetic.build_frame` / `near_codeword_llr` for
the ladder side, `test_analyzer_calibrate._synthetic_frame` for the map,
`_patch_world.World` for one end-to-end `evidence_for` on pixels).
The blind pins matter most: the door takes ONE type, a pseudo row is
never a select-fold label row, the rule's coefficients cannot move under
a refit, `frame.known` is never written, and every CRC consult is
charged once.
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import replace as dc_replace

import numpy as np
import pytest

from holo.receiver.format import tile_codec
from holo.receiver.lib import pava

from analyzer import arms as arms_mod
from analyzer import calibrate as cal
from analyzer import combine as comb
from analyzer import controls as ctl
from analyzer import fixedpoint as fp
from analyzer import frame as frame_mod
from analyzer import ladder as L
from analyzer import mother as M
from analyzer import refit
from analyzer.types import (RESERVED_KNOBS, VERDICT_CERTIFIED, VERDICT_OPEN,
                            VERDICT_REFUSED, AnalyzerConfig, BpOut, Combined,
                            Evidence, Exposure, PseudoLabels)

from ._synthetic import (R0850, build_frame, channel_llr, near_codeword_llr,
                         row_of, through_cells)
from .test_analyzer_calibrate import _synthetic_frame
from .test_analyzer_gaps_fix import _FakeInputs, _FakeLane, _reroll_world
from ._patch_world import HALO, World
from .test_analyzer_statecal import _two_lane_world

#: `L4_MISS` of the ladder tests: L1 exits at 6 unsatisfied checks, the
#: regime the rung was built for (see the module docstring's measurement).
NEAR = (2, 9)


# ----------------------------------------------------------- scaffolding

@pytest.fixture(scope="module")
def near():
    frame = build_frame(R0850)
    return frame, near_codeword_llr(frame, *NEAR)


def _seq_of(row, key) -> dict[tuple[int, int], int]:
    """PAGE cell -> sequential index, the inverse the rung's labels use."""
    grid = L._cell_grid(row, key)
    ty, tx = int(key[1]), int(key[2])
    return {(int(y) + ty * 64, int(x) + tx * 64): index
            for index, (y, x) in enumerate(grid)}


def _combined(key, llr: np.ndarray) -> Combined:
    return Combined(key=key, rule="sum", lanes=(("cap", 3),),
                    coefficients=(1.0,),
                    llr_sequential=np.asarray(llr, np.float64),
                    observed=np.ones(len(llr), bool), clipped_fraction=0.0)


class _Stub:
    """A refit closure with the `Refit` surface the rung reads.

    `reader(seq_index, pseudo_bit) -> llr` says what the "refit" reads
    at each pseudo cell; everything else keeps the base channel.  With
    `reader=None` the base is returned unchanged (no gain).
    """

    def __init__(self, base, key, seq_of, reader=None, *, limit: int = 26,
                 n_evidence: int = 1):
        self.base = np.asarray(base, np.float64)
        self.key = key
        self.seq_of = seq_of
        self.reader = reader
        self.budget = [int(limit)]
        self.limit = int(limit)
        self.n_evidence = int(n_evidence)
        self.calls: list[PseudoLabels] = []

    @property
    def remaining(self) -> int:
        return int(self.budget[0])

    @property
    def used(self) -> int:
        return self.limit - int(self.budget[0])

    def __call__(self, pseudo):
        assert isinstance(pseudo, PseudoLabels)
        self.calls.append(pseudo)
        if self.budget[0] < self.n_evidence:
            raise refit.RefitBudgetExhausted("stub: out of budget")
        self.budget[0] -= self.n_evidence
        out = self.base.copy()
        if self.reader is not None:
            for (y, x), bit in zip(pseudo.cells_yx, pseudo.bits):
                index = self.seq_of[(int(y), int(x))]
                out[index] = self.reader(index, int(bit))
        return _combined(self.key, out)


def _truth_reader(frame):
    printed = through_cells(frame)

    def read(index: int, _bit: int) -> float:
        return 8.0 if printed[index] else -8.0
    return read


# -------------------------------------------------------- the pseudo labels

def test_confident_bits_map_through_the_cell_grid_and_exclude_index_0(near):
    frame, _llr = near
    row, key = frame.row, frame.key
    n = row.payload_cells
    current = np.full(n, 3.0)
    current[5] = 0.0                              # unobserved position
    posterior = current.copy()
    plus = np.array([0, 1, 5, 40, 41, 2000])
    minus = np.array([7, 300, 3975])
    posterior[plus] += 10.0
    posterior[minus] -= 10.0
    grid = L._cell_grid(row, key)
    origin = np.array([key[1] * 64, key[2] * 64], np.int64)

    labels = refit.confident_pseudo_labels(current, posterior, row, key,
                                           tau=4.0, weight=3.0,
                                           metadata_bit=1)
    assert labels.source == "decoder"
    named = sorted((plus.tolist() + minus.tolist()))
    named = [index for index in named if index not in (0, 5)]
    assert np.array_equal(labels.cells_yx, grid[named] + origin)
    expected_bits = np.asarray([1 if index in plus else 0 for index in named],
                               np.uint8)
    assert np.array_equal(labels.bits, expected_bits)
    assert np.all(labels.weights == 3.0) and labels.size == len(named)
    assert not labels.bits.flags.writeable

    # without an injected metadata bit, index 0 is a cell like any other
    free = refit.confident_pseudo_labels(current, posterior, row, key,
                                         tau=4.0, weight=1.0,
                                         metadata_bit=None)
    assert free.size == len(named) + 1
    assert np.array_equal(free.cells_yx[0], grid[0] + origin)
    # a tau above every extrinsic names nothing
    assert refit.confident_pseudo_labels(current, posterior, row, key,
                                         tau=11.0, weight=1.0,
                                         metadata_bit=None).size == 0


def test_pseudo_bits_are_printed_domain_bits(near):
    """A posterior of +-20 at the printed bits -> pseudo bits == the
    cells' PRINTED bits (no dither re-applied: both sides are sequential)."""
    frame, _llr = near
    row, key = frame.row, frame.key
    printed = through_cells(frame)
    current = 0.5 * (2.0 * printed.astype(np.float64) - 1.0)
    posterior = 20.0 * (2.0 * printed.astype(np.float64) - 1.0)
    labels = refit.confident_pseudo_labels(current, posterior, row, key,
                                           tau=4.0, weight=3.0,
                                           metadata_bit=None)
    assert labels.size == printed.size
    seq_of = _seq_of(row, key)
    at = np.asarray([seq_of[(int(y), int(x))] for y, x in labels.cells_yx])
    assert np.array_equal(labels.bits, printed[at])
    assert np.array_equal(labels.bits, frame.printed[at])


def test_the_typed_value_refuses_a_foreign_source_and_ragged_arrays():
    cells = np.zeros((3, 2), np.int64)
    with pytest.raises(ValueError):
        PseudoLabels(source="self", cells_yx=cells, bits=np.zeros(3, np.uint8),
                     weights=np.ones(3))
    with pytest.raises(ValueError):
        PseudoLabels(source="decoder", cells_yx=cells,
                     bits=np.zeros(2, np.uint8), weights=np.ones(3))
    with pytest.raises(ValueError):
        PseudoLabels(source="decoder", cells_yx=cells,
                     bits=np.full(3, 2, np.uint8), weights=np.ones(3))
    ok = PseudoLabels(source="decoder", cells_yx=cells,
                      bits=np.zeros(3, np.uint8), weights=np.ones(3))
    assert ok.size == 3 and not ok.cells_yx.flags.writeable


# ---------------------------------------------------------------- the rung

def test_l3f_refuses_without_a_refit_closure(near, monkeypatch):
    frame, llr = near
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L1", "L3f"),
                           knobs={}, exposure=Exposure(), metadata_bit=None)
    assert [item.rung for item in results] == ["L1", "L3f"]
    assert results[0].verdict == VERDICT_OPEN
    assert results[1].verdict == VERDICT_REFUSED
    assert results[1].detail["reason"] == "no_refit"
    assert results[1].crc_consults_distinct == 0

    # the controls null arm hands the config's bare knob bag — no closure
    row = row_of(R0850)
    inputs = _FakeInputs(row, frame_mod.geometry_of(row))
    lane = _FakeLane()

    def fake_lanes(_inputs, _page, _ty, _tx, cover_fraction=0.9):
        return [lane]

    def fake_evidence(_inputs, _certs, key, lane_, arm, *, halo_cells=None,
                      knobs=None, crop_memo=None):
        assert "refit" not in (knobs or {})
        return Evidence(key=key, lane=lane_.lane_id, arm=arm,
                        llr_sequential=np.asarray(llr, np.float64),
                        observed=np.ones(llr.size, bool),
                        blind={"arm": arm})

    from analyzer import sample as sample_mod
    monkeypatch.setattr(sample_mod, "lanes_for_tile", fake_lanes)
    monkeypatch.setattr(ctl.arms_mod, "evidence_for", fake_evidence)
    config = AnalyzerConfig(arms=("subtract+offset",), rules=("sum",),
                            rungs=("L1", "L3f"))
    out = ctl._decode_at(inputs, {}, frame.key, frame.key, config,
                         Exposure(), metadata_bit=None)
    assert out["refusal"] is None
    l3f = [item for item in out["results"] if item.rung == "L3f"]
    assert l3f and l3f[0].verdict == VERDICT_REFUSED
    assert l3f[0].detail["reason"] == "no_refit"


def test_l3f_runs_bounded_rounds_and_stops_on_a_certificate(near):
    frame, llr = near
    row, key = frame.row, frame.key
    stub = _Stub(llr, key, _seq_of(row, key), _truth_reader(frame))
    exposure = Exposure()
    results = L.run_ladder(llr, row, key, rungs=("L1", "L3f"),
                           knobs={"refit": stub, "keep_hard": True},
                           exposure=exposure, metadata_bit=None)
    assert [item.rung for item in results] == ["L1", "L3f.r0"]
    assert results[0].verdict == VERDICT_OPEN           # L1 did not
    hit = results[1]
    assert hit.verdict == VERDICT_CERTIFIED             # round 0 did
    assert np.array_equal(hit.user_bits, frame.user)
    assert hit.unsat_at_exit == 0 and hit.syndrome_ok
    assert hit.crc_consults_distinct == 1 and exposure.distinct == 1
    assert hit.detail["round"] == 0
    assert hit.detail["source_rung"] == "L1"
    assert hit.detail["unsat_entry"] == 6
    assert hit.detail["n_pseudo"] == len(stub.calls[0].bits) > 3000
    assert hit.detail["n_observed"] == row.payload_cells
    assert hit.detail["refit_evidence_used"] == 1
    assert hit.detail["refit_budget_remaining"] == 25
    assert hit.detail["tau"] == 4.0 and hit.detail["weight"] == 3.0
    assert "hard_packed" in hit.detail
    assert hit.detail["extrinsic_q50"] > 4.0
    assert len(stub.calls) == 1                         # one round, one refit

    # the pseudo bits the stub was handed are the decoder's own, and in
    # this regime almost all of them are right
    printed = through_cells(frame)
    seq_of = _seq_of(row, key)
    pseudo = stub.calls[0]
    at = np.asarray([seq_of[(int(y), int(x))] for y, x in pseudo.cells_yx])
    assert np.count_nonzero(pseudo.bits != printed[at]) <= 8

    # bounded: `refit_rounds=1` on a closure that never helps is ONE row
    same = _Stub(llr, key, seq_of, None)
    results = L.run_ladder(llr, row, key, rungs=("L1", "L3f"),
                           knobs={"refit": same, "refit_rounds": 1},
                           exposure=Exposure(), metadata_bit=None)
    assert [item.rung for item in results] == ["L1", "L3f.r0"]
    assert results[1].verdict == VERDICT_OPEN
    assert len(same.calls) == 1


def test_l3f_aborts_without_unsat_gain(near):
    frame, llr = near
    row, key = frame.row, frame.key
    same = _Stub(llr, key, _seq_of(row, key), None)
    results = L.run_ladder(llr, row, key, rungs=("L1", "L3f"),
                           knobs={"refit": same, "refit_rounds": 3},
                           exposure=Exposure(), metadata_bit=None)
    assert [item.rung for item in results] == ["L1", "L3f.r0", "L3f.r0"]
    assert results[1].verdict == VERDICT_OPEN
    assert results[2].verdict == VERDICT_REFUSED
    assert results[2].detail["reason"] == "no_unsat_gain"
    assert results[2].detail["unsat_previous"] == 6
    assert results[2].unsat_at_exit == 6
    assert len(same.calls) == 1                     # no third round paid


def test_l3f_stops_at_the_evidence_budget_and_says_so(near):
    frame, llr = near
    row, key = frame.row, frame.key
    seq_of = _seq_of(row, key)
    empty = _Stub(llr, key, seq_of, _truth_reader(frame), limit=0)
    results = L.run_ladder(llr, row, key, rungs=("L1", "L3f"),
                           knobs={"refit": empty}, exposure=Exposure(),
                           metadata_bit=None)
    assert [item.rung for item in results] == ["L1", "L3f.r0"]
    refused = results[1]
    assert refused.verdict == VERDICT_REFUSED
    assert refused.detail["reason"] == "refit_budget_exhausted"
    assert refused.detail["budget_remaining"] == 0
    assert refused.detail["budget_needed"] == 1
    assert refused.detail["n_pseudo"] > 0          # the labels were built
    assert refused.crc_consults_distinct == 0      # ... but nothing decoded

    # a budget that cannot cover a FULL round refuses before spending
    short = _Stub(llr, key, seq_of, _truth_reader(frame), limit=1,
                  n_evidence=2)
    results = L.run_ladder(llr, row, key, rungs=("L1", "L3f"),
                           knobs={"refit": short}, exposure=Exposure(),
                           metadata_bit=None)
    assert results[-1].detail["reason"] == "refit_budget_exhausted"
    assert short.remaining == 1


def test_l3f_refuses_an_entry_whose_syndrome_already_closed(near):
    """An entry at unsat 0 that did not certify failed the CRC — its
    extrinsic is a full-confidence lie, and the rung will not learn it."""
    frame, llr = near
    row, key = frame.row, frame.key
    mother = M.to_mother(llr, row, key, metadata_bit=None)
    out = M.bp(mother, None, 150)
    closed = BpOut(hard=out.hard, syndrome=np.zeros_like(out.syndrome),
                   unsat=0, posterior=out.posterior, n_iters=out.n_iters,
                   syndrome_ok=True)
    stub = _Stub(llr, key, _seq_of(row, key), _truth_reader(frame))
    results = refit.rung_feedback(llr, row, key, frame.bank, Exposure(),
                                  {"refit": stub}, None,
                                  [("L1", closed, mother)])
    assert len(results) == 1
    assert results[0].verdict == VERDICT_REFUSED
    assert results[0].detail["reason"] == "entry_syndrome_closed"
    assert not stub.calls


def test_l3f_makes_its_own_entry_when_no_earlier_rung_decoded(near):
    frame, llr = near
    row, key = frame.row, frame.key
    stub = _Stub(llr, key, _seq_of(row, key), _truth_reader(frame))
    results = L.run_ladder(llr, row, key, rungs=("L3f",),
                           knobs={"refit": stub}, exposure=Exposure(),
                           metadata_bit=None)
    assert [item.rung for item in results] == ["L3f.r0"]
    assert results[0].verdict == VERDICT_CERTIFIED
    assert results[0].detail["source_rung"] == "L3f.entry"


def test_l3f_charges_every_distinct_codeword_once(near):
    frame, llr = near
    row, key = frame.row, frame.key
    seq_of = _seq_of(row, key)
    real = tile_codec.crc32_bits
    calls = {"n": 0}

    def spy(bits):
        calls["n"] += 1
        return real(bits)

    M.tile_codec.crc32_bits = spy
    try:
        exposure = Exposure()
        first = L.run_ladder(llr, row, key, rungs=("L1", "L3f"),
                             knobs={"refit": _Stub(llr, key, seq_of,
                                                   _truth_reader(frame))},
                             exposure=exposure, metadata_bit=None)
        assert calls["n"] == 1
        assert sum(item.crc_consults_distinct for item in first) == 1
        assert exposure.distinct == 1
        # the SAME codeword again, under the same exposure: consulted,
        # certified, and charged NOTHING new
        again = L.run_ladder(llr, row, key, rungs=("L1", "L3f"),
                             knobs={"refit": _Stub(llr, key, seq_of,
                                                   _truth_reader(frame))},
                             exposure=exposure, metadata_bit=None)
    finally:
        M.tile_codec.crc32_bits = real
    assert again[-1].verdict == VERDICT_CERTIFIED
    assert again[-1].crc_consults_distinct == 0
    assert exposure.distinct == 1
    assert calls["n"] == 2                          # consulted twice, paid once


def test_l3f_is_direct_for_both_classifiers():
    from analyzer import oracle, score
    for name in ("L3f", "L3f.r0", "L3f.r1", "L3f.entry"):
        assert oracle.is_direct(name), name
        assert not score._is_list_rung(name), name
    assert "L3f" not in L.DEFAULT_RUNGS
    assert all("L3f" not in expansion for expansion in
               fp.RUNG_ALIASES.values())
    assert fp.expand_rungs(("L3f",)) == ("L3f",)


def test_refit_is_blind_and_imports_ladder_only_inside_functions():
    tree = ast.parse(pathlib.Path(refit.__file__).read_text("utf-8"))
    top: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            top.add(node.module or "")
            top.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            top.update(alias.name for alias in node.names)
    everywhere: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            everywhere.add(node.module or "")
            everywhere.update(alias.name for alias in node.names)
    assert not any("truth" in name or "oracle" in name or name == "score"
                   for name in everywhere), sorted(everywhere)
    assert "ladder" not in top and "ladder" in everywhere
    assert {"arms", "combine", "mother"} <= top


# ------------------------------------------------------- the door (arms)

def test_the_door_refuses_an_untyped_pseudo_label():
    row = row_of(R0850)
    inputs = _FakeInputs(row, frame_mod.geometry_of(row))
    key = (0, 12, 7, "C")
    cells = np.array([[12 * 64 + 3, 7 * 64 + 4]], np.int64)
    for untyped in ({"cells_yx": cells, "bits": [1], "weights": [3.0]},
                    (cells, np.ones(1, np.uint8), np.ones(1)),
                    cells):
        evidence = arms_mod.evidence_for(
            inputs, {}, key, _FakeLane(), "subtract+offset",
            knobs={"pseudo_labels": untyped})
        assert evidence.blind["refusal"] == "pseudo_labels:not_typed"
        assert not np.any(evidence.observed)
    # the refit closure refuses the same thing before any evidence runs
    with pytest.raises(refit.RefitError):
        refit.refit_evidence(inputs, {}, key, 16, {}, {}, (), "sum", None,
                             (), [26], cells)


@pytest.fixture(scope="module")
def pixels() -> World:
    return World()


def _pixel_run(world: World, monkeypatch, arm: str, knobs: dict):
    """`evidence_for` end to end on the synthetic page.

    The real row's tile (0, 0) footprint at the page's halo is the
    world's own box, so only `known_frame` is swapped — for the world's
    frame, which is the one consistent with its pixels.
    """
    row = row_of(R0850)
    inputs = _FakeInputs(row, frame_mod.geometry_of(row))
    key = (0, 0, 0, "C")

    def fake_known_frame(_inputs, _certs, fp_, target, *, metadata_known,
                         metadata_bit=None):
        assert np.array_equal(fp_.page_cells_yx, world.fp.page_cells_yx)
        return dc_replace(world.frame, target=target)

    monkeypatch.setattr(arms_mod.frame_mod, "known_frame", fake_known_frame)
    return arms_mod.evidence_for(
        inputs, {}, key, world.lane, arm, halo_cells=HALO,
        knobs={"seed": 20260906, "ctx_mode": "none",
               "mix_scope_ladder": ("footprint",),
               "metadata_known": False, **knobs})


def _pixel_pseudo(world: World, *, n_known: int = 40, weight: float = 3.0
                  ) -> tuple[PseudoLabels, np.ndarray]:
    """Decoder-shaped labels: the truth at in-tile cargo cells, plus a few
    KNOWN halo cells that the door must drop.  Returns (labels, cargo rows)."""
    cells = world.fp.page_cells_yx
    known = np.asarray(world.frame.known[:, 0], bool)
    cargo = np.flatnonzero(world.fp.in_tile & ~known)[:900]
    halo_rows = np.flatnonzero(known & ~world.fp.in_tile)[:n_known]
    rows = np.concatenate((cargo, halo_rows))
    bits = world.page_bits[cells[rows, 0], cells[rows, 1], 0]
    labels = PseudoLabels(source="decoder", cells_yx=cells[rows],
                          bits=np.asarray(bits, np.uint8),
                          weights=np.full(rows.size, weight))
    return labels, cargo


def test_the_door_records_the_source_and_feeds_both_fits(pixels,
                                                         monkeypatch):
    labels, cargo = _pixel_pseudo(pixels)
    before = np.array(pixels.frame.known, copy=True)
    plain = _pixel_run(pixels, monkeypatch, "patch+committed", {})
    fed = _pixel_run(pixels, monkeypatch, "patch+committed",
                     {"pseudo_labels": labels})
    assert plain.blind.get("refusal") is None
    assert fed.blind.get("refusal") is None
    # a patch arm publishes `pseudo_source` itself (P2's "self", or None);
    # only the door can make it "decoder"
    assert plain.blind.get("pseudo_source") is None
    assert plain.blind["patch_labels_from"] == "halo"
    assert fed.blind["pseudo_source"] == "decoder"
    assert fed.blind["pseudo_weight"] == 3.0
    assert fed.blind["n_pseudo_offered"] == labels.size
    assert fed.blind["n_pseudo_labels"] == cargo.size      # the known dropped
    assert fed.blind["patch_labels_from"] == "halo+bp"
    assert fed.blind["patch_n_extra_labels"] == cargo.size
    # ... and the map: OFF by default on a patch arm (review 2026-09-06 —
    # the filter already absorbed those rows and cross-fits them, so the
    # map may not be fitted on its output at the cells that trained it)
    assert fed.blind["refit_calibration"] is False
    assert fed.blind["branches"]["all"]["n_pseudo_fit"] == 0
    assert plain.blind["branches"]["all"]["n_pseudo_fit"] == 0
    assert fed.blind["n_pseudo_offered"] == labels.size
    # ... and ON when the operator asks for it: every pseudo row sits in
    # the one pooled branch
    both = _pixel_run(pixels, monkeypatch, "patch+committed",
                      {"pseudo_labels": labels, "refit_calibration": True})
    assert both.blind["patch_labels_from"] == "halo+bp"
    assert both.blind["branches"]["all"]["n_pseudo_fit"] == cargo.size
    # with `refit_calibration` off the filter still sees them, the map not
    filter_only = _pixel_run(pixels, monkeypatch, "patch+committed",
                             {"pseudo_labels": labels,
                              "refit_calibration": False})
    assert filter_only.blind["patch_labels_from"] == "halo+bp"
    assert filter_only.blind["branches"]["all"]["n_pseudo_fit"] == 0
    # a box arm takes the map side only
    box = _pixel_run(pixels, monkeypatch, "subtract+committed",
                     {"pseudo_labels": labels})
    assert box.blind["pseudo_source"] == "decoder"
    assert box.blind["refit_calibration"] is True     # the box arm's default
    assert box.blind["branches"]["all"]["n_pseudo_fit"] == cargo.size
    assert np.array_equal(pixels.frame.known, before)


def test_pseudo_labels_never_touch_frame_known(pixels, monkeypatch):
    labels, _cargo = _pixel_pseudo(pixels)
    snapshot = np.array(pixels.frame.known, copy=True)
    fed = _pixel_run(pixels, monkeypatch, "patch+committed",
                     {"pseudo_labels": labels})
    assert fed.blind.get("refusal") is None
    assert np.array_equal(pixels.frame.known, snapshot)
    # the DESIGN §4.5 invariant the assertion in `known_frame` guards
    inside = pixels.fp.in_tile & pixels.fp.cargo
    assert not np.any(pixels.frame.known[inside, 0])
    # the frame's own labels never grew: n_labels is the halo's count
    plain = _pixel_run(pixels, monkeypatch, "patch+committed", {})
    for name in ("n_labels", "n_labels_fit", "n_labels_search",
                 "n_labels_select", "n_discriminating_select"):
        assert fed.blind[name] == plain.blind[name], name


def test_a_production_frame_is_read_only_so_no_fit_could_write_it():
    """`known_frame` hands out read-only arrays: a pseudo label that tried
    to become a known bit would raise, not leak (the world's synthetic
    frame above is writable, which is why this pin is on the real one)."""
    row = row_of(R0850)
    inputs = _FakeInputs(row, frame_mod.geometry_of(row))
    real = frame_mod.known_frame(
        inputs, {}, frame_mod.tile_footprint(row, 0, 12, 7, 0,
                                             geometry=inputs.geometry),
        (0, 12, 7, "C"), metadata_known=False)
    assert not real.known.flags.writeable and not real.bits.flags.writeable
    with pytest.raises(ValueError):
        real.known[0, 0] = True


def test_pseudo_labels_leave_the_select_fold_arrays_and_no_pseudo_cell_is_a_label_row(
        pixels, monkeypatch):
    labels, cargo = _pixel_pseudo(pixels)
    plain = _pixel_run(pixels, monkeypatch, "patch+committed", {})
    fed = _pixel_run(pixels, monkeypatch, "patch+committed",
                     {"pseudo_labels": labels})
    for name in ("label_rows", "label_values", "label_discriminating",
                 "label_state"):
        assert np.array_equal(plain.blind[name], fed.blind[name]), name
    rows = set(int(row) for row in fed.blind["label_rows"])
    assert not rows & set(int(row) for row in cargo)
    # the held-out VIEW of the refitted map is allowed to move
    assert fed.blind["label_llr"].shape == plain.blind["label_llr"].shape
    # ... on the footprint rows `pseudo_rows` maps the cells to, once the
    # door has dropped the KNOWN ones (the mapper maps everything it is
    # handed; the 40 halo cells in the offer are label rows by design)
    mapped, _bits, _weights = arms_mod.patch_mod.pseudo_rows(
        pixels.fp, labels)
    known = np.asarray(pixels.frame.known[:, 0], bool)
    kept = mapped[~known[mapped]]
    assert kept.size == cargo.size == fed.blind["n_pseudo_labels"]
    assert not rows & set(int(row) for row in kept)
    assert rows & set(int(row) for row in mapped[known[mapped]])


# ------------------------------------------------------------ calibrate

def _map_world(seed: int = 21):
    frame, lfp, cells = _synthetic_frame(4000, seed, plane=2)
    folds = cal.split_folds(cells, 4)
    rng = np.random.default_rng(seed + 100)
    truth = np.asarray(frame.bits[:, 2], np.float64)
    score = truth + rng.normal(0.0, 0.45, truth.size)
    unknown = np.flatnonzero(~frame.known[:, 2])
    return frame, lfp, folds, score, truth, unknown


def test_calibrate_pseudo_rows_join_the_fit_fold_by_integer_weight_and_leave_the_floors():
    frame, lfp, folds, score, truth, unknown = _map_world()
    rows = unknown[:600]
    known_rows = np.flatnonzero(frame.known[:, 2])[:25]
    pseudo = (np.concatenate((rows, known_rows)),
              np.concatenate((truth[rows], truth[known_rows])).astype(np.uint8),
              np.concatenate((np.full(rows.size, 3.0),
                              np.full(known_rows.size, 3.0))))
    base_llr, base = cal.calibrate(score, frame, 2, lfp, folds,
                                   branches="pooled", ctx_mode="none")
    fed_llr, fed = cal.calibrate(score, frame, 2, lfp, folds,
                                 branches="pooled", ctx_mode="none",
                                 pseudo=pseudo)
    # counted DISTINCT, the known rows dropped (a label beats a pseudo)
    assert fed["branches"]["all"]["n_pseudo_fit"] == rows.size
    assert fed["n_pseudo_rows"] == rows.size + known_rows.size
    assert base["branches"]["all"]["n_pseudo_fit"] == 0
    # every halo count and floor input is untouched
    for name in ("n_fit_0", "n_fit_1", "n_heldout", "accepted"):
        assert fed["branches"]["all"][name] == base["branches"]["all"][name]
    for name in ("n_labels", "n_labels_fit", "n_labels_search",
                 "n_labels_select", "n_discriminating"):
        assert fed[name] == base[name]
    for name in ("label_rows", "label_values", "label_discriminating",
                 "label_state"):
        assert np.array_equal(fed[name], base[name])
    assert not set(fed["label_rows"].tolist()) & set(rows.tolist())
    assert fed_llr.shape == base_llr.shape

    # the replication: round(weight) copies, zero for a weight under 0.5
    usable = np.ones(score.size, bool)
    labels_all = np.asarray(frame.known[:, 2], bool)
    p_rows, p_values, n_distinct = cal._pseudo_fit_rows(
        usable, labels_all, rows[:4], truth[rows[:4]],
        np.array([3.0, 2.6, 0.4, 1.0]))
    assert n_distinct == 4
    assert p_rows.tolist() == [rows[0]] * 3 + [rows[1]] * 3 + [rows[3]]
    assert p_values.tolist() == [truth[rows[0]]] * 3 + \
        [truth[rows[1]]] * 3 + [truth[rows[3]]]

    # THE FLOORS stay on the halo labels: a branch starved of one class
    # is not rescued by a thousand pseudo rows of it
    starved = np.array(frame.known, copy=True)
    ones = np.flatnonzero(starved[:, 2] & (frame.bits[:, 2] == 1))
    starved[ones[pava.CAL_MIN_PER_CLASS - 3:], 2] = False
    frame_starved = dc_replace(frame, known=starved, labels=starved[:, 2])
    rescue_rows = np.flatnonzero(~starved[:, 2])[:1000]
    rescue = (rescue_rows, np.ones(rescue_rows.size, np.uint8),
              np.full(rescue_rows.size, 3.0))
    _llr, detail = cal.calibrate(score, frame_starved, 2, lfp, folds,
                                 branches="pooled", ctx_mode="none",
                                 starved_fallback=False, pseudo=rescue)
    assert detail["branches"]["all"]["accepted"] is False
    assert detail["branches"]["all"]["reason"] == "search_class_starved"
    assert detail["n_calibrated"] == 0

    # a malformed pseudo is refused, never silently ignored
    with pytest.raises(cal.CalibrateError):
        cal.calibrate(score, frame, 2, lfp, folds, branches="pooled",
                      ctx_mode="none", pseudo=rows)


def test_shuffled_pseudo_bits_flatten_the_map_and_honest_ones_do_not():
    """The permutation control of a learned component (DESIGN §8): the
    refitted map read on the HELD-OUT halo labels.  Honest pseudo bits
    leave it where the halo put it; the same rows with their bits
    permuted (weight 3, outnumbering the halo's fit rows) pull the map
    toward flat, and the held-out loss says so."""
    frame, lfp, folds, score, truth, unknown = _map_world()
    rows = unknown[:1500]
    honest = (rows, truth[rows].astype(np.uint8), np.full(rows.size, 3.0))
    shuffled_bits = np.random.default_rng(5).permutation(
        truth[rows]).astype(np.uint8)
    shuffled = (rows, shuffled_bits, np.full(rows.size, 3.0))
    _l0, base = cal.calibrate(score, frame, 2, lfp, folds, branches="pooled",
                              ctx_mode="none")
    _l1, good = cal.calibrate(score, frame, 2, lfp, folds, branches="pooled",
                              ctx_mode="none", pseudo=honest)
    _l2, bad = cal.calibrate(score, frame, 2, lfp, folds, branches="pooled",
                             ctx_mode="none", pseudo=shuffled)
    loss = {name: detail["heldout_logloss_search"]
            for name, detail in (("base", base), ("good", good),
                                 ("bad", bad))}
    assert loss["good"] <= loss["base"] + 0.02, loss
    assert loss["bad"] > loss["base"] + 0.10, loss
    assert loss["bad"] > 1.5 * loss["good"], loss
    # and the shuffled map is FLATTER, not merely different: its held-out
    # LLRs carry less magnitude than the honest one's
    assert (np.mean(np.abs(bad["label_llr"]))
            < 0.75 * np.mean(np.abs(good["label_llr"])))


# ----------------------------------------------------------- the refit

def test_refit_recombines_under_the_round0_label_view_so_coefficients_do_not_move():
    lanes, seq_state = _two_lane_world()
    kept, _detail = comb.deduplicate(lanes)
    view = comb._label_view(kept)
    rng = np.random.default_rng(11)
    # "refitted" lanes: a new combined vector AND a moved label_llr view
    moved = tuple(
        dc_replace(item,
                   llr_sequential=item.llr_sequential + rng.normal(0, 2, 200),
                   blind={**dict(item.blind),
                          "label_llr": np.asarray(item.blind["label_llr"])
                          * rng.uniform(0.2, 3.0, 300)})
        for item in lanes)
    for rule in ("platt", "corr", "platt-state"):
        base = comb.combine(lanes, rule, sibling_state=seq_state)
        held = comb.combine(moved, rule, labels=view,
                            sibling_state=seq_state)
        free = comb.combine(moved, rule, sibling_state=seq_state)
        assert held.coefficients == base.coefficients, rule
        assert held.coefficients_by_state == base.coefficients_by_state, rule
        if rule != "corr":
            # a Platt fit on the MOVED view would have moved (`corr`'s
            # scale is (1, 1) whenever the errors are uncorrelated, so
            # it cannot show the difference)
            assert free.coefficients != base.coefficients, rule
        # the vector itself DID change — the refit is not a no-op
        assert not np.allclose(held.llr_sequential, base.llr_sequential)

    # the view restricted to the lanes that survived a refit
    sub = refit._label_view_for([kept[1]], view, kept)
    assert sub[1].shape == (1, view[1].shape[1])
    assert np.array_equal(sub[1][0], view[1][1])
    assert np.array_equal(sub[0], view[0]) and np.array_equal(sub[3], view[3])
    with pytest.raises(refit.RefitError):
        refit._label_view_for([kept[1]], view, kept[:1])


def test_blind_key_binds_a_refit_closure_per_rule_with_one_budget_per_key(
        monkeypatch):
    inputs, built = _reroll_world(monkeypatch, good_arm="head+offset")
    seen: list[dict] = []
    real_run = fp.ladder_mod.run_ladder

    def spy_run(combined, row, key, **kwargs):
        seen.append(dict(kwargs["knobs"]))
        return real_run(combined, row, key, **kwargs)

    monkeypatch.setattr(fp.ladder_mod, "run_ladder", spy_run)
    config = AnalyzerConfig(arms=("subtract+offset", "head+offset"),
                            rules=("sum", "best"), rungs=("L0",),
                            reroll=True, all_rules=True,
                            knobs={"refit_max_evidence": 5})
    out = fp.blind_key(inputs, {}, built.key, config, fp.shared_exposure())
    assert out.get("user_bits") is not None            # the re-roll won
    assert len(seen) >= 3                              # 2 rules + re-roll
    closures = [bag["refit"] for bag in seen]
    assert all(isinstance(item, refit.Refit) for item in closures)
    assert [item.rule for item in closures[:2]] == ["sum", "best"]
    assert all(item.budget is closures[0].budget for item in closures)
    assert all(item.limit == 5 for item in closures)
    assert closures[0].key == built.key
    # every derived knob is ASSIGNED, whether or not the rule derived it
    for bag in seen:
        assert bag["keep_hard"] is True
        assert "ctx_offsets" in bag and "sibling_state" in bag
        assert bag["ctx_state_adopted"] is False
        assert "refit_max_evidence" in bag
        state = bag["sibling_state"]
        assert state.dtype == np.int8 and state.size == built.row.payload_cells
    assert set(out["diag_state"]) == {"n_state3", "n_state_known"}

    # the closure re-runs the lane's evidence WITH the labels, on the
    # shared budget, and recombines under the round-0 view
    fake = fp.arms_mod.evidence_for
    handed: list = []

    def recording(_inputs, _certs, key, lane, arm, *, halo_cells=None,
                  knobs=None, crop_memo=None):
        handed.append(knobs["pseudo_labels"])
        return fake(_inputs, _certs, key, lane, arm, halo_cells=halo_cells,
                    knobs=knobs, crop_memo=crop_memo)

    monkeypatch.setattr(fp.arms_mod, "evidence_for", recording)
    pseudo = PseudoLabels(source="decoder",
                          cells_yx=np.zeros((0, 2), np.int64),
                          bits=np.zeros(0, np.uint8), weights=np.zeros(0))
    combined = closures[0](pseudo)
    assert isinstance(combined, Combined)
    assert handed == [pseudo]
    assert closures[0].remaining == 4 and closures[1].remaining == 4
    assert closures[0].used == 1
    with pytest.raises(refit.RefitError):
        closures[0]({"cells_yx": []})
    # four more and the budget is out: the closure refuses BEFORE spending
    for _ in range(4):
        closures[1](pseudo)
    assert closures[0].remaining == 0
    with pytest.raises(refit.RefitBudgetExhausted):
        closures[0](pseudo)
    assert closures[0].remaining == 0 and len(handed) == 5


def test_blind_key_refuses_a_config_that_names_a_reserved_knob(monkeypatch):
    inputs, built = _reroll_world(monkeypatch, good_arm="head+offset")
    for name in RESERVED_KNOBS:
        config = AnalyzerConfig(arms=("subtract+offset", "head+offset"),
                                rules=("sum",), rungs=("L0",),
                                knobs={name: 1})
        out = fp.blind_key(inputs, {}, built.key, config,
                           fp.shared_exposure())
        assert out["refusal"] == f"reserved_knob:{name}"
        assert "user_bits" not in out and out["evidence"] == {}


# ---------------------------------------------------------------- T1

def test_temperature_scales_the_channel_and_labels_the_variant(monkeypatch):
    frame = build_frame(R0850)
    llr = channel_llr(frame.printed, 0.08, seed=202)      # L2 fails on it
    handed: list[np.ndarray] = []
    real = L.mother_mod.to_mother

    def spy(vector, row, key, *, metadata_bit=None):
        handed.append(np.array(vector, np.float64))
        return real(vector, row, key, metadata_bit=metadata_bit)

    monkeypatch.setattr(L.mother_mod, "to_mother", spy)
    variants = ({"mode": "minsum-then-sp", "iters": 40},
                {"mode": "minsum-then-sp", "iters": 40, "temperature": 0.5},
                {"mode": "damped", "iters": 40, "lam": 0.7,
                 "temperature": 1.25})
    results = L.run_ladder(llr, frame.row, frame.key, rungs=("L2",),
                           knobs={"L2": variants}, exposure=Exposure(),
                           metadata_bit=None)
    assert [item.rung for item in results] == [
        "L2:minsum-then-sp@40", "L2:minsum-then-sp@40@t0.5",
        "L2:damped@40@t1.25"]
    assert all(item.verdict == VERDICT_OPEN for item in results)
    assert "temperature" not in results[0].detail       # byte-identical
    assert results[1].detail["temperature"] == 0.5
    assert results[2].detail["temperature"] == 1.25
    # one shared mother at t=1, one per scaled variant, the channel scaled
    assert len(handed) == 3
    assert np.array_equal(handed[0], llr)
    assert np.allclose(handed[1], 0.5 * llr)
    assert np.allclose(handed[2], 1.25 * llr)
    # the default variants carry no temperature at all
    assert all("temperature" not in spec for spec in L.DEFAULT_L2_VARIANTS)
