"""cmy's residue rows and readout (CMY-RECEIVER-PLAN A7): the cmy8 rows
translated through the label mapping (R25), not new rows.

`tiles.swim`'s level table and objective floor are the ROW'S alphabet's:
cmy's four presence ids (0, 1, 2, 4) give a four-row table and a floor
of 4 x 8 = 32 cells, cmy8's eight stay 64 (`test_h3_plugins_swim`).
`tiles.planek` reads a label stream as the SUM of its toners' isolated
presences, hi = C + M and lo = C + Y (`tile_codec.stream_toners`, exact
because a cmy cell carries at most one toner), and is born for cmy where
it is born for cmy8; a synthetic two-by-two page read through
`plane_label` certifies the target tile's hi and lo with the generator's
bits.  `tiles.local` runs cmy as it stands (R11): its colour arm is the
region head.  The readout gates the field rows on the run's FAMILY, says
`hi,lo` and PROVISIONAL, and spells cmy's C, held at the pose by the
gauge (R7), as `0 (gauge)` outside the support count.

LEDGER 2026-10-12 (A7), a record: the planek attempt below, on its
seeded two-by-two page (the e043c bars, a 2 px blur, pixel noise sd 90),
certifies hi in 1 and lo in 3 BP iterations with the generator's user
bits.  Scratch probes on the same page, not pinned: at sd 60 / 90 / 120
over three seeds hi certified 9 of 9 and lo 7 of 9, read on the PROJECT
readout or the subtract one alike; on a page whose noise is one level
per CELL (sd 20) the subtract readout's offset sweep ran to -1.25 dots
and hi failed where the project readout certified it -- the label-
correlated bias `plugins/plane_label` derives.  On those clean pages the
sweep's held-out loss (cmy8's `choose_offset`, unchanged) has no
resolution once every read is separable: with the neighbours' dense
labels it chose -1.0 dots for C at sd 120 where d' peaks at 0.0 (10.6
against 5.0), and lo failed there; with furniture labels only it chose
0.0.  The slow-lane residue decode is `test_h3_e2e_cmy`'s.
"""
from __future__ import annotations

from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import ndimage

from holo.receiver import data
from holo.receiver.data import AttemptFact
from holo.receiver.diag import model as diag_model
from holo.receiver.diag import readout as diag_readout
from holo.receiver.format import identity, tile_codec
from holo.receiver.plugins import (color_region, color_sites, local_ctx,
                                   plane_k, plane_label, swim, tiles)
from holo.receiver.tests import _h3_fixture_geometry, _h3_sims_cmy

CMY_REF = "c3-cmy-r0850@10x10"
CMY_ROW = identity.resolve_format_ref(CMY_REF)
CMY8_ROW = identity.resolve_format_ref("c3-cmy8-r0550@10x10")
K_ROW = identity.resolve_format_ref("c3-k-r0550@8x8")
CMY7_ROW = identity.resolve_format_ref("L:c3-cmy7-p120-v0@2240x1536")
PPC = Fraction(6)

#: The label table of CMY-DESIGN §2.2, written out: state -> (hi, lo).
LABELS_BY_STATE = {0: (0, 0), 1: (1, 1), 2: (1, 0), 4: (0, 1)}


# --- swim: the level table and the floor over the row's alphabet -------


def test_swims_level_table_over_cmys_ids_is_the_hand_written_one():
    """Four rows, in the alphabet's order (W, C, M, Y = 0, 1, 2, 4), each
    the per-channel median of its own cells; a state short of
    MIN_STATE_CELLS is not live."""
    rng = np.random.default_rng(20261012)
    levels_by_state = {0: (230.0, 231.0, 234.0), 1: (51.0, 155.0, 207.0),
                       2: (217.0, 71.0, 125.0), 4: (230.0, 222.0, 93.0)}
    counts = {0: 12, 1: 9, 2: 8, 4: 7}
    states = np.concatenate([np.full(count, state)
                             for state, count in counts.items()])
    values = np.stack([levels_by_state[int(state)] for state in states])
    values = values + rng.integers(-2, 3, values.shape)
    levels, live = swim.state_levels(states, values, CMY_ROW.state_ids)
    expected = np.stack([np.median(values[states == state], axis=0)
                         for state in (0, 1, 2, 4)])
    assert levels.shape == (4, 3)
    assert np.array_equal(live, (True, True, True, False))
    assert np.array_equal(levels[:3], expected[:3])
    assert not levels[3].any()
    assert np.array_equal(
        swim.alphabet_index(CMY_ROW.state_ids, np.array([0, 4, 2, 1])),
        (0, 3, 2, 1))


def test_swims_floor_for_four_states_is_four_times_the_per_state_floor():
    """The objective wants the whole alphabet's worth of a live table:
    4 states x MIN_STATE_CELLS 8 = 32 cells for cmy, 8 x 8 = 64 for
    cmy8 (unchanged)."""
    assert swim.MIN_STATE_CELLS == 8
    assert swim.min_objective_cells(CMY_ROW) == 4 * 8 == 32
    assert swim.min_objective_cells(CMY8_ROW) == 64


# --- planek: the presence-to-label map --------------------------------


def test_the_map_reads_each_label_bit_as_its_toners_presence_summed():
    """hi = C + M, lo = C + Y over W, C, M, Y: the table, not a guess."""
    hi, lo = (plane_k.stream_toners(CMY_ROW, stream_id)
              for stream_id in ("hi", "lo"))
    assert (hi, lo) == ((0, 1), (0, 2))
    for state, bits in LABELS_BY_STATE.items():
        planes = tile_codec.states_to_planes(np.array([state]))[0]
        assert (int(planes[list(hi)].sum()), int(planes[list(lo)].sum())) \
            == bits, state


def test_a_toner_stream_reads_its_own_plane_and_k_and_cmy7_none():
    assert tuple(plane_k.stream_toners(CMY8_ROW, plane)
                 for plane in ("C", "M", "Y")) == ((0,), (1,), (2,))
    assert plane_k.stream_toners(K_ROW, "main") == ()
    assert plane_k.stream_toners(CMY7_ROW, "main") == ()
    assert plane_k.readable(CMY_ROW) and plane_k.readable(CMY8_ROW)
    assert not plane_k.readable(K_ROW) and not plane_k.readable(CMY7_ROW)


def _store(row: identity.FormatRow, certified: frozenset) -> SimpleNamespace:
    return SimpleNamespace(
        row=row,
        geometry=_h3_fixture_geometry.memoised_site_geometry(row),
        level=lambda capture_id, level_index: SimpleNamespace(ppc=PPC),
        cover_lanes=lambda page, ty, tx, ppc: (("cap", 0),),
        tile_cover=lambda key: ((), (("cap", 0, 0, 0),)),
        evidence_reach=lambda wid: None,
        color_row_cover_tiles=lambda key: ((0, 3, 5, "cap", 0),),
        window_by_ordinal=lambda capture_id, level_index, ordinal: (
            capture_id, level_index, 0, (0, 0, 64, 64)),
        attempt_verdict=lambda *key: None,
        tile_lane_generation=lambda key: 0,
        union_generation=lambda page, ty, tx, ppc: 0,
        has_certificate=lambda key: key in certified,
        union_rung_ordinal=lambda ppc: 0)


@pytest.mark.parametrize("stream_id, planes", (("hi", (0, 1)),
                                               ("lo", (0, 2))))
def test_planek_is_born_for_a_cmy_label_stream_and_reads_both_toner_fields(
        stream_id, planes):
    store = _store(CMY_ROW, frozenset({(0, 3, 5, "hi"), (0, 3, 5, "lo")}))
    fact = AttemptFact(page=0, ty=3, tx=4, stream_id=stream_id,
                       stage=tiles.STAGE_SCAN, outcome=tiles.OUTCOME_FAILED,
                       n_informative=100, n_iters=60, syndrome_ok=False,
                       crc_ok=None, components=(("cap", 0),))
    subject = (0, 3, 4, stream_id, PPC)
    assert plane_k._planek_subjects(store, fact) == (subject,)
    assert plane_k._planek_eligible(store, subject)
    fields = {key for key in plane_k._planek_reads(store, subject)
              if key[0] == "plane_field"}
    assert fields == {("plane_field", 0, plane) for plane in planes}


# --- planek: a label attempt on real (synthetic) pixels ----------------

LABEL_REF = "c3-cmy-r0850@2x2"
LABEL_PPC = 12
LABEL_MARGIN_PX = 24
LABEL_BLUR_PX = 2.0
LABEL_NOISE_SD = 90.0
LABEL_SEED = 20261012
TARGET = (0, 1, 1)


def _label_page(row, geometry):
    """Every tile certified in both streams (seeded user bits), so the
    page's planes are the projection's; then the page as e043c's bars,
    blurred, with noise per pixel."""
    rng = np.random.default_rng(LABEL_SEED)
    certificates = {
        (0, ty, tx, fact.stream_id): data.Certificate(
            0, ty, tx, fact.stream_id,
            rng.integers(0, 2, fact.user_bits, dtype=np.uint8), "t")
        for ty in range(row.tiles_yx[0]) for tx in range(row.tiles_yx[1])
        for fact in row.streams}
    height, width = row.cells_yx
    planes = np.zeros((height, width, 3), np.uint8)
    for ty in range(row.tiles_yx[0]):
        for tx in range(row.tiles_yx[1]):
            bits, known = color_sites.certified_projection(
                row, geometry, 0, ty, tx, certificates)
            assert known.all()
            planes[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64] = bits
    bars = _h3_sims_cmy.e043c_sheet3_bars()
    colours = np.asarray((bars.paper_rgb,) + bars.toner_rgb, np.float64)
    state_rows = planes @ np.asarray((1, 2, 3), np.uint8)
    rgb = np.kron(colours[state_rows],
                  np.ones((LABEL_PPC, LABEL_PPC, 1)))
    side = (height * LABEL_PPC + 2 * LABEL_MARGIN_PX,
            width * LABEL_PPC + 2 * LABEL_MARGIN_PX)
    raster = np.empty(side + (3,), np.float64)
    raster[...] = colours[0]
    raster[LABEL_MARGIN_PX:LABEL_MARGIN_PX + height * LABEL_PPC,
           LABEL_MARGIN_PX:LABEL_MARGIN_PX + width * LABEL_PPC] = rgb
    raster = ndimage.gaussian_filter(raster,
                                     (LABEL_BLUR_PX, LABEL_BLUR_PX, 0))
    raster = raster + rng.normal(0.0, LABEL_NOISE_SD, raster.shape)
    raster = np.clip(np.round(raster), 0, 255).astype(np.uint8)
    return certificates, tuple(raster[..., channel] for channel in range(3))


@pytest.mark.parametrize("stream_id", ("hi", "lo"))
def test_a_planek_label_attempt_certifies_the_stream_as_the_generator_wrote_it(
        stream_id):
    """The target tile's two streams withheld, its neighbours certified:
    each toner read at its own (zero) field, the presences summed,
    priced on proven cells, written in product form — and the codec
    certifies the label stream with the generator's user bits."""
    row = identity.resolve_format_ref(LABEL_REF)
    geometry = identity.build_site_geometry(row)
    certificates, planes = _label_page(row, geometry)
    known = {key: certificate for key, certificate in certificates.items()
             if key[:3] != TARGET}
    height, width = row.cells_yx
    placement = _h3_fixture_geometry.window_placement(
        ("cap", 0, 0, (0, 0, height, width)),
        _h3_fixture_geometry.page_native_affine(LABEL_PPC, LABEL_MARGIN_PX),
        _h3_fixture_geometry.grid_cells((0, 0), (height, width)))
    window = _h3_fixture_geometry.window_pose(row, placement)
    rasters = tuple(SimpleNamespace(open=lambda raster=raster: raster)
                    for raster in planes)
    toners = plane_k.stream_toners(row, stream_id)
    lane = tuple(plane_k.LanePlan(
        lane=("cap", 0), windows=(window,), placements=(placement,),
        region_indices=(0,), planes=rasters, field=None) for _ in toners)
    rows = plane_label.label_rows(row, geometry, lane, known, toners)
    assert rows, "the label read refused the window"
    _wid, _region, transient = rows[0]
    others = [column for column in range(3) if column not in toners]
    assert not np.any(transient.values[:, others])
    assert np.array_equal(transient.values[:, toners[0]],
                          transient.values[:, toners[1]])
    cut = plane_k.rows_cut(("cap", 0), rows, row, geometry, *TARGET)
    facts, _events = plane_k.attempt_components(row, geometry, (cut,),
                                                stream_id)
    minted = [fact for fact in facts if isinstance(fact, data.Certificate)]
    assert len(minted) == 1
    assert np.array_equal(minted[0].user_bits,
                          certificates[(*TARGET, stream_id)].user_bits)


# --- local: cmy's colour arm is the region head (R11) -------------------


def test_cmys_local_row_takes_the_colour_arm_and_runs_the_region_head(
        monkeypatch):
    """No change for cmy (R11): `prepare_local` sends a non-K row to the
    colour arm, whose read is `color_region.region_job` over the
    covering windows, handed the cmy row itself."""
    calls: list[identity.FormatRow] = []

    def region_job(row, *args, **kwargs):
        calls.append(row)
        return SimpleNamespace(facts=())

    plan = local_ctx.ColorLanePlan(("cap", 0), (), (), (None,) * 3,
                                   (None,) * 3)
    monkeypatch.setattr(color_region, "region_job", region_job)
    monkeypatch.setattr(local_ctx, "armed_streams",
                        lambda *args, **kwargs: ("hi", "lo"))
    monkeypatch.setattr(local_ctx, "certified_neighbours",
                        lambda *args, **kwargs: ((3, 5),))
    monkeypatch.setattr(local_ctx, "neighbourhood_tiles",
                        lambda *args, **kwargs: ((3, 5),))
    monkeypatch.setattr(local_ctx, "lane_generations",
                        lambda *args, **kwargs: None)
    monkeypatch.setattr(local_ctx, "_color_lane_plans",
                        lambda *args, **kwargs: (plan,))
    monkeypatch.setattr(local_ctx, "_prepare_k", None)
    store = SimpleNamespace(row=CMY_ROW, geometry=None,
                            certificates=lambda: {})
    job = local_ctx.prepare_local(store, (0, 3, 4, PPC),
                                  local_ctx.STAGE_LOCAL)
    assert job is not None
    assert job().facts == ()
    assert calls == [CMY_ROW]


# --- readout: the family gate, hi/lo, PROVISIONAL, C at the gauge -------


def _run_open(family: str, streams: tuple[str, ...]) -> data.RunOpen:
    return data.RunOpen(format_id=CMY_ROW.row_id, display_id=CMY_REF,
                        pages=1, tiles_yx=(10, 10), stream_ids=streams,
                        n_captures=1, workers=8, family=family)


def _plane_row(plane: int, name: str, median: float, support: int,
               held: bool = False) -> data.FieldPlaneRow:
    return data.FieldPlaneRow(
        plane=plane, plane_name=name, median_delta_dots=median,
        median_uncertainty_dots=0.0 if held else 0.25,
        support_tiles=support, n_observations=10 * support, n_captures=1,
        known=True, delta_grid_dots_xy=np.zeros((1, 1, 2), np.float32),
        magnitude_grid_dots=np.zeros((1, 1), np.float32),
        has_data=np.ones((1, 1), bool), held=held)


def _solved() -> data.FieldSolved:
    return data.FieldSolved(
        page=0, planes=(_plane_row(0, "C", 0.0, 100, held=True),
                        _plane_row(1, "M", 1.12, 80),
                        _plane_row(2, "Y", 1.30, 60)),
        residual_by_capture_plane=(), tiles_yx=(10, 10),
        block_tiles_yx=(1, 1), revision=7, passes=3, converged=True)


def _certified(stream_id: str, ty: int) -> data.TileOutcome:
    return data.TileOutcome(page=0, ty=ty, tx=0, stream_id=stream_id,
                            source="tiles/scan", result="certified",
                            bp_iters=3)


def test_a_cmy_run_reads_hi_lo_provisional_and_c_held_at_the_gauge():
    events = (_run_open("cmy", ("hi", "lo")), _certified("hi", 0),
              _certified("hi", 1), _certified("lo", 0), _solved())
    model = diag_model.fold(diag_model.empty(), events)
    rows = diag_readout.all_rows(model)
    assert rows[0] == (f"format   {CMY_REF} · 10x10 tiles · 1 possible"
                       " · streams hi,lo · PROVISIONAL")
    assert rows[4].endswith("· CERTIFIED 3 [hi 2 · lo 1]"), rows[4]
    assert diag_readout.plane_cert_counts(model) == (("hi", 2), ("lo", 1))
    assert rows[6] == ("fields   page 0 — C 0 (gauge) M 1.12±0.25"
                       " Y 1.30±0.25 dots, support 70% · rev 7 · passes 3"
                       " · no evidence"), rows[6]


@pytest.mark.parametrize("family, streams, has_field_row", (
    ("k", ("main",), False), ("cmy7", ("main",), True),
    ("cmy8", ("C", "M", "Y"), True), ("cmy", ("hi", "lo"), True)))
def test_the_field_rows_are_gated_on_the_family_not_the_stream_count(
        family, streams, has_field_row):
    model = diag_model.fold(diag_model.empty(), (_run_open(family, streams),))
    assert bool(diag_readout.field_rows(model)) is has_field_row
