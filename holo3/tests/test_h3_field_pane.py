"""The FIELD band and its producer: what the `fields` row publishes to
diag, and what the viewer makes of it.

Synthetic throughout — the events are built by the real producer
(`plugins.fields.diag_event`) from real `lib.plane_field.FieldFit`s, so
nothing here is a hand-written event that could drift from the shape the
decode actually emits.  The end-to-end rendering gate on a real sim
capture lives in `test_h3_color_field_yield.py`, beside the decodes it
needs.
"""

from __future__ import annotations

import io
import json

import numpy as np
import pytest
from PIL import Image

from holo3 import data
from holo3.diag import fields_pane
from holo3.diag import model as diag_model
from holo3.diag import readout as diag_readout
from holo3.diag import report as diag_report
from holo3.diag import panes, server
from holo3.lib import plane_field
from holo3.plugins import fields

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

CAP_A = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
CAP_B = "b1b2c3d4e5f60718293a4b5c6d7e8f90"
FORMAT_ID = "holo3/v2/c2-cmy8-r0700@6x10"

TILES_YX = (10, 6)


def _run(streams: tuple[str, ...] = ("C", "M", "Y"),
         plane_fields: bool = True,
         tiles_yx: tuple[int, int] = TILES_YX) -> data.RunOpen:
    return data.RunOpen(format_id=FORMAT_ID, pages=1, tiles_yx=tiles_yx,
                        stream_ids=streams, n_captures=1, workers=1,
                        pitch_in=1 / 300, plane_fields=plane_fields)


def _capture(capture: str = CAP_A, ordinal: int = 0) -> data.CaptureOpen:
    return data.CaptureOpen(capture=capture, dpi=2400.0, shape_yx=(600, 400),
                            channels=3, duplicate=False, ordinal=ordinal)


def _certified(page: int, ty: int, tx: int) -> tuple:
    return tuple(
        data.TileOutcome(page=page, ty=ty, tx=tx, stream_id=stream,
                         source="scan", result="certified", bp_iters=3)
        for stream in ("C", "M", "Y"))


def _fit(delta_dots_xy: np.ndarray, support: np.ndarray, n_sites: int,
         residual: float) -> plane_field.FieldFit:
    return plane_field.FieldFit(
        delta_dots_xy=delta_dots_xy, support=support, residual=residual,
        median_delta_dots=plane_field.median_magnitude_dots(delta_dots_xy,
                                                            support),
        n_sites=n_sites)


def _uniform(tiles_yx: tuple[int, int], dx: float,
             dy: float = 0.0) -> np.ndarray:
    delta = np.zeros(tiles_yx + (2,), np.float64)
    delta[..., 0] = dx
    delta[..., 1] = dy
    return delta


def _support(tiles_yx: tuple[int, int],
             blind: tuple[slice, slice] | None = None) -> np.ndarray:
    support = np.ones(tiles_yx, np.float64)
    if blind is not None:
        support[blind] = 0.0
    return support


def _fits(tiles_yx: tuple[int, int] = TILES_YX,
          blind: tuple[slice, slice] | None = None,
          y_dx: float = 0.9) -> tuple:
    """C small (refused), M dead (no fit), Y large (published)."""
    support = _support(tiles_yx, blind)
    return (_fit(_uniform(tiles_yx, 0.05), support, 4096, 0.97),
            None,
            _fit(_uniform(tiles_yx, y_dx), support, 5000, 0.90))


def _event(tiles_yx: tuple[int, int] = TILES_YX, capture: str = CAP_A,
           level_index: int = 0, page: int = 0, n_certificates: int = 260,
           **kwargs) -> data.FieldFitted:
    return fields.diag_event(tiles_yx, _fits(tiles_yx, **kwargs), capture,
                             level_index, page, n_certificates)


def _fold(events: tuple) -> diag_model.DiagModel:
    return diag_model.fold(diag_model.empty(), list(events))


def _image(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))


def _has_colour(image: np.ndarray, colour: tuple[int, int, int]) -> bool:
    return bool((image == np.asarray(colour, np.uint8)).all(axis=-1).any())


def _body(model: diag_model.DiagModel, page: int = 0) -> np.ndarray:
    """The band's plot area alone.  The text block under it is blitted
    through an antialiased glyph mask, so its blend greys would answer
    a colour question the plot is being asked."""
    width, body_h = fields_pane.band_geometry(model, page)
    image = _image(panes.render_pane(model, "field", page))
    assert image.shape[1] == width
    return image[fields_pane.TITLE_H:fields_pane.TITLE_H + body_h]


# -- the producer ----------------------------------------------------


def test_the_publish_verdict_is_the_writers_own_decision():
    good = _fit(_uniform(TILES_YX, 0.9), _support(TILES_YX), 5000, 0.90)
    nan = np.float64("nan")
    for fit in (good,
                _fit(_uniform(TILES_YX, 0.9), _support(TILES_YX), 4, 0.90),
                _fit(_uniform(TILES_YX, 0.01), _support(TILES_YX), 5000,
                     0.90),
                _fit(_uniform(TILES_YX, 0.9), _support(TILES_YX), 5000,
                     0.999),
                # a degenerate solve: neither floor can COMPARE, and a
                # value that fails the decision must fail the explanation
                _fit(_uniform(TILES_YX, nan), _support(TILES_YX), 5000,
                     0.90),
                _fit(_uniform(TILES_YX, 0.9), _support(TILES_YX), 5000,
                     float(nan))):
        assert fields.publishable(fit) is (fields.refusal(fit) == "")
    assert fields.refusal(good) == ""
    assert fields.publishable(good)


def test_a_refused_fit_names_every_floor_it_missed():
    starved = _fit(_uniform(TILES_YX, 0.01), _support(TILES_YX), 4, 0.999)
    why = fields.refusal(starved)
    assert "sites 4<256" in why
    assert "median 0.01d<0.25d" in why
    assert "residual 0.999>0.995" in why


def test_a_plane_that_never_fitted_reports_none_never_zero():
    row = _event().planes[1]
    assert row.plane_name == "M"
    assert not row.fitted
    assert row.published is False
    assert "no fit" in row.refusal
    for value in (row.median_delta_dots, row.n_sites, row.residual,
                  row.support_tiles, row.delta_grid_dots_xy, row.has_data):
        assert value is None


def test_a_refused_plane_still_carries_its_measurement():
    row = _event().planes[0]
    assert row.plane_name == "C" and row.fitted and not row.published
    assert row.median_delta_dots == pytest.approx(0.05)
    assert row.n_sites == 4096
    assert row.support_tiles == TILES_YX[0] * TILES_YX[1]
    assert "median" in row.refusal


@pytest.mark.parametrize("tiles_yx", [(10, 6), (53, 37), (200, 140)])
def test_the_event_grid_is_capped_on_both_axes(tiles_yx):
    event = _event(tiles_yx)
    grid = event.planes[2].delta_grid_dots_xy
    assert grid.shape[0] <= fields.DIAG_GRID_MAX
    assert grid.shape[1] <= fields.DIAG_GRID_MAX
    assert grid.dtype == np.float32
    cost = sum(row.delta_grid_dots_xy.nbytes + row.has_data.nbytes
               for row in event.planes if row.fitted)
    assert cost <= 3 * fields.DIAG_GRID_MAX ** 2 * (2 * 4 + 1), cost


def test_the_block_size_is_the_smallest_that_fits_the_cap():
    assert fields.block_size(10) == 1
    assert fields.block_size(24) == 1
    assert fields.block_size(25) == 2
    assert fields.block_size(53) == 3
    assert fields.block_size(0) == 1


def test_pooling_keeps_evidence_free_tiles_out_of_the_mean():
    delta = np.zeros((4, 4, 2), np.float64)
    delta[0, :, 0] = 1.0            # the only tiles with evidence
    support = np.zeros((4, 4), np.float64)
    support[0, :] = 1.0
    grid, magnitude, has_data = fields.pool_field(delta, support, (2, 2))
    assert grid.shape == (2, 2, 2) and has_data.shape == (2, 2)
    assert magnitude.shape == (2, 2)
    assert has_data.tolist() == [[True, True], [False, False]]
    # the mean over the block's LIVE tiles is 1.0, not 0.5
    assert grid[0, 0, 0] == pytest.approx(1.0)
    assert grid[1, 0, 0] == 0.0
    assert magnitude[0, 0] == pytest.approx(1.0)


def test_the_magnitude_is_pooled_in_its_own_right_never_from_the_vector():
    """A block whose deltas oppose: the vector cancels, the magnitude
    does not, and the writer's floor is on the magnitude."""
    delta = np.zeros((2, 2, 2), np.float64)
    delta[:, 0, 0] = 0.9
    delta[:, 1, 0] = -0.9
    grid, magnitude, has_data = fields.pool_field(
        delta, np.ones((2, 2), np.float64), (2, 2))
    assert bool(has_data.all())
    assert grid[0, 0, 0] == pytest.approx(0.0)
    assert magnitude[0, 0] == pytest.approx(0.9)


def test_the_event_carries_the_writers_own_publish_floor():
    assert _event().publish_floor_dots == fields.MIN_DELTA_DOTS


# -- the fold --------------------------------------------------------


def test_the_latest_fit_wins_per_lane_page():
    first = _event(n_certificates=100)
    second = _event(n_certificates=260)
    model = _fold((_run(), _capture(), first, second))
    assert len(model.field_fits) == 1
    assert model.field_fits[(CAP_A, 0, 0)].n_certificates == 260
    assert model.last_field.n_certificates == 260


def test_the_pane_draws_the_lane_that_fitted_the_page_most_recently():
    model = _fold((_run(), _capture(), _capture(CAP_B, 1),
                   _event(capture=CAP_A), _event(capture=CAP_B)))
    assert len(model.field_fits) == 2
    assert diag_readout.page_field(model, 0).capture == CAP_B
    assert diag_readout.page_field_lanes(model, 0) == ("1.0", "0.0")


def test_the_field_pane_indexes_only_pages_a_fit_landed_on():
    bare = _fold((_run(), _capture()))
    assert diag_readout.field_pages(bare) == ()
    assert diag_readout.status(bare)["panes"]["field"] == []
    assert diag_readout.page_field(bare, 0) is None
    fitted = _fold((_run(), _capture(), _event()))
    assert diag_readout.field_pages(fitted) == (0,)
    assert diag_readout.status(fitted)["panes"]["field"] == [0]


def test_a_field_event_bumps_only_the_field_pane():
    before = _fold((_run(), _capture()))
    after = _fold((_run(), _capture(), _event()))
    for pane in ("capture", "page", "payload", "pose"):
        assert after.pane_revs[pane] == before.pane_revs[pane], pane
    assert after.pane_revs["field"] == before.pane_revs["field"] + 1


# -- the status row --------------------------------------------------


def test_the_six_row_block_is_still_exactly_six():
    model = _fold((_run(), _capture(), _event()))
    assert len(diag_readout.six_row_status(model)) == 6
    assert len(diag_readout.all_rows(model)) == 7


def test_a_k_run_carries_no_field_row_at_all():
    model = _fold((data.RunOpen(format_id=FORMAT_ID, pages=1,
                                tiles_yx=TILES_YX, stream_ids=("main",),
                                n_captures=1, workers=1),
                   _capture()))
    assert diag_readout.field_rows(model) == ()
    assert diag_readout.all_rows(model) == diag_readout.six_row_status(model)


def test_a_colour_run_with_the_dial_off_says_off_never_zero():
    model = _fold((_run(plane_fields=False), _capture()))
    row, = diag_readout.field_rows(model)
    assert row.startswith("fields   off")
    assert "--plane-fields" in row
    assert "0" not in row


def test_a_colour_run_names_the_wait_before_the_first_fit():
    model = _fold((_run(), _capture()))
    assert diag_readout.field_rows(model) == (
        "fields   unavailable before the first fit",)


def test_the_field_row_carries_median_support_and_the_verdict():
    model = _fold((_run(), _capture(), _event()))
    row, = diag_readout.field_rows(model)
    assert row.startswith("fields   lane 0.0 page 0 · ")
    assert "C 0.05d 60t refused" in row
    assert "M no fit" in row
    assert "Y 0.90d 60t published" in row
    assert row.endswith("· 1 lane-page fitted")


def test_the_field_row_counts_every_lane_page_that_fitted():
    model = _fold((_run(), _capture(), _capture(CAP_B, 1),
                   _event(capture=CAP_A), _event(capture=CAP_B)))
    row, = diag_readout.field_rows(model)
    assert row.endswith("· 2 lane-pages fitted")


def test_the_rows_ride_the_status_dict_and_the_report():
    model = _fold((_run(), _capture(), _event()))
    status = diag_readout.status(model)
    assert status["rows"] == list(diag_readout.all_rows(model))
    report = diag_report.build_report(model)
    assert len(report["plane_fields"]) == 1
    planes = {row["plane_name"]: row for row in
              report["plane_fields"][0]["planes"]}
    assert planes["Y"]["published"] is True
    assert planes["C"]["published"] is False
    assert "median" in planes["C"]["refusal"]
    assert planes["M"]["median_delta_dots"] is None
    assert json.loads(json.dumps(
        diag_report._jsonable(report)))["plane_fields"][0]["lane"] == "0.0"


# -- the band --------------------------------------------------------


def test_the_band_is_absent_until_a_fit_lands():
    bare = _fold((_run(), _capture()))
    assert panes.render_pane(bare, "field", 0) is None
    assert ("field", 0) not in panes.pin_panes(bare)
    fitted = _fold((_run(), _capture(), _event()))
    png = panes.render_pane(fitted, "field", 0)
    assert png[:8] == PNG_MAGIC
    assert ("field", 0) in panes.pin_panes(fitted)


def test_a_run_without_the_arm_pins_exactly_the_panes_it_always_did():
    bare = _fold((_run(plane_fields=False), _capture()))
    assert set(panes.pin_panes(bare)) == {
        ("capture", 0), ("page", 0), ("payload", 0), ("pose", 0)}


def test_the_band_paints_each_plane_in_its_own_hue():
    body = _body(_fold((_run(), _capture(), _event())))
    # Y published: its own full hue
    assert _has_colour(body, fields_pane.PLANE_HUE["Y"])
    # M never fitted, so it draws nothing at all
    assert not _has_colour(body, fields_pane.PLANE_HUE["M"])
    assert not _has_colour(body, _mix(fields_pane.PLANE_HUE["M"],
                                      fields_pane.REFUSED_MIX))


def test_a_refused_planes_quiver_is_drawn_dimmed_never_full_strength():
    """C's fit is real and drawn — it is the point of carrying a refused
    fit — but it is not in effect, and the band says so by weight."""
    body = _body(_fold((_run(), _capture(), _event())))
    assert _has_colour(body, _mix(fields_pane.PLANE_HUE["C"],
                                  fields_pane.REFUSED_MIX))
    assert not _has_colour(body, fields_pane.PLANE_HUE["C"])


def test_the_shading_is_the_publish_floor_and_nothing_else():
    over = _fold((_run(), _capture(), _event(y_dx=0.9)))
    under = _fold((_run(), _capture(), _event(y_dx=0.05)))
    assert _has_colour(_body(over), fields_pane.SHADE)
    assert not _has_colour(_body(under), fields_pane.SHADE)


def test_an_uncovered_block_is_black_only_while_it_is_uncertified():
    blind = (slice(0, 3), slice(0, 3))
    blank = _body(_fold((_run(), _capture(), _event(blind=blind))))
    assert _has_colour(blank, fields_pane.HOLE)
    assert not _has_colour(blank, fields_pane.DONE)
    done = _body(_fold((_run(), _capture(), _event(blind=blind),
                        *(row for ty in range(3) for tx in range(3)
                          for row in _certified(0, ty, tx)))))
    assert _has_colour(done, fields_pane.DONE)
    assert not _has_colour(done, fields_pane.HOLE)


def _measured(event: data.FieldFitted) -> tuple:
    return tuple((row,) + fields_pane._live_blocks(row)
                 for row in event.planes)


def test_no_drawn_arrow_reaches_beyond_v1s_two_blocks_on_its_own_axis():
    measured = _measured(_event())
    block_w, block_h = 40.0, 12.0
    factor = fields_pane.exaggeration(measured, block_w, block_h)
    for _row, _blocks, deltas, _magnitudes in measured:
        if not deltas.size:
            continue
        assert (float(np.abs(deltas[:, 0]).max()) * factor
                <= fields_pane.ARROW_BLOCK_CAP * block_w)
        assert (float(np.abs(deltas[:, 1]).max()) * factor
                <= fields_pane.ARROW_BLOCK_CAP * block_h)


def test_the_clamp_is_v1s_own_two_blocks():
    """A fidelity port does not retune the constant it ports (user
    ruling 2026-08-30)."""
    assert fields_pane.ARROW_BLOCK_CAP == 2.0


def test_the_arrow_scale_is_v1s_fixed_factor_when_it_fits():
    """PARITY: the same delta draws the same length on every sheet, so
    two runs can be compared by eye.  A cap-only factor normalised that
    away — the longest arrow was two blocks long whatever it measured."""
    small = _measured(_event(y_dx=0.4))
    smaller = _measured(_event(y_dx=0.2))
    assert fields_pane.exaggeration(small, 400.0, 400.0) == (
        fields_pane.FIXED_EXAGGERATION)
    assert fields_pane.exaggeration(smaller, 400.0, 400.0) == (
        fields_pane.FIXED_EXAGGERATION)


def test_the_geometric_cap_only_ever_shortens_the_fixed_factor():
    measured = _measured(_event(y_dx=0.9))
    tight = fields_pane.exaggeration(measured, 10.0, 10.0)
    widest = max(float(np.abs(deltas[:, 0]).max())
                 for _row, _blocks, deltas, _mag in measured if deltas.size)
    assert tight < fields_pane.FIXED_EXAGGERATION
    assert widest * tight == pytest.approx(
        fields_pane.ARROW_BLOCK_CAP * 10.0)


def test_a_field_with_no_deltas_at_all_still_renders():
    flat = fields.diag_event(TILES_YX, (None, None, None), CAP_A, 0, 0, 8)
    model = _fold((_run(), _capture(), flat))
    png = panes.render_pane(model, "field", 0)
    assert png[:8] == PNG_MAGIC
    row, = diag_readout.field_rows(model)
    assert row.count("no fit") == 3


def test_a_degenerate_delta_is_a_blind_spot_not_a_measurement():
    row = _event().planes[2]
    grid = np.array(row.delta_grid_dots_xy)
    grid[0, 0] = np.nan
    object.__setattr__(row, "delta_grid_dots_xy", grid)
    blocks, deltas, magnitudes = fields_pane._live_blocks(row)
    assert len(blocks) == grid.shape[0] * grid.shape[1] - 1
    assert bool(np.isfinite(deltas).all())
    assert len(magnitudes) == len(blocks)


def _mix(colour: tuple, share: float) -> tuple:
    return fields_pane._mix(colour, share)


def test_a_plane_blind_where_another_measured_gets_its_own_tint():
    """The dead-plane sheets (e030, e033) are why this band exists: the
    all-planes-blind black square cannot say WHICH plane went blind."""
    tiles = (48, 48)
    full = _support(tiles)
    dead = _support(tiles, blind=(slice(0, 24), slice(0, 24)))
    event = fields.diag_event(
        tiles,
        (_fit(_uniform(tiles, 0.6), full, 4096, 0.9), None,
         _fit(_uniform(tiles, 0.6), dead, 4096, 0.9)),
        CAP_A, 0, 0, 260)
    body = _body(_fold((_run(), _capture(), event)))
    assert _has_colour(body, _mix(fields_pane.PLANE_HUE["Y"],
                                  fields_pane.BLIND_MIX))
    # C measured everywhere, so C never tints a blind segment
    assert not _has_colour(body, _mix(fields_pane.PLANE_HUE["C"],
                                      fields_pane.BLIND_MIX))
    # and no block is a whole-band hole: C reached all of them
    assert not _has_colour(body, fields_pane.HOLE)


def test_opposing_deltas_in_one_block_still_shade_it():
    """The shading mirrors the writer's floor, which is on the MEDIAN
    per-tile magnitude: a block straddling a sign change clears it while
    its pooled vector reads zero."""
    tiles = (48, 48)
    delta = np.zeros(tiles + (2,), np.float64)
    delta[:, 0::2, 0] = 0.9
    delta[:, 1::2, 0] = -0.9
    event = fields.diag_event(
        tiles, (_fit(delta, _support(tiles), 4096, 0.9), None, None),
        CAP_A, 0, 0, 260)
    plane = event.planes[0]
    assert abs(float(plane.delta_grid_dots_xy[0, 0, 0])) < 0.25
    assert float(plane.magnitude_grid_dots[0, 0]) == pytest.approx(0.9)
    assert _has_colour(_body(_fold((_run(), _capture(), event))),
                       fields_pane.SHADE)


def test_only_a_certified_outcome_moves_the_field_pane():
    """The band reads tile states for its done/blind split alone, so a
    failed tile leaves its map exactly where it was — and the busiest
    event in the system stops re-rendering the most expensive pane."""
    def outcome(result: str) -> data.TileOutcome:
        return data.TileOutcome(page=0, ty=0, tx=0, stream_id="C",
                                source="tiles/scan", result=result,
                                bp_iters=8)

    events = [_run(), _capture(), _event()]
    base = _fold(tuple(events))
    before = base.pane_revs.get("field", 0)
    events.append(outcome("attempted_failed"))
    failed = diag_model.fold(base, events)
    assert failed.pane_revs.get("field", 0) == before
    assert failed.pane_revs["payload"] > base.pane_revs["payload"]
    events.append(outcome("certified"))
    certified = diag_model.fold(failed, events)
    assert certified.pane_revs.get("field", 0) == before + 1


def test_the_bands_text_names_the_refusing_floor():
    n_tiles = TILES_YX[0] * TILES_YX[1]
    lines = [fields_pane._plane_line(row, n_tiles)
             for row in _event().planes]
    assert lines[0].startswith("C  median 0.050d · sites 4096")
    assert f"support {n_tiles}/{n_tiles} tiles" in lines[0]
    assert "refused: median 0.05d<0.25d" in lines[0]
    assert lines[1] == ("M  no fit — plane dead here, or no live states")
    assert lines[2].endswith("PUBLISHED")


# -- no diag failure touches the decode ------------------------------


class _Poison:
    """A field event whose planes explode when the pane touches them."""

    capture = CAP_A
    level_index = 0
    page = 0
    n_certificates = 4
    tiles_yx = TILES_YX
    block_tiles_yx = (1, 1)
    publish_floor_dots = 0.25

    @property
    def planes(self):
        raise ValueError("poisoned field event")


def test_a_poisoned_field_event_is_counted_never_raised():
    model = _fold((_run(), _capture(), _Poison()))
    # not a FieldFitted, so the fold ignores it outright: no fit, no crash
    assert model.fold_errors == 0
    assert diag_readout.field_pages(model) == ()


def _broken_events() -> tuple:
    """A field event the band cannot draw: its block shape is not a
    shape, which the certified-tile overlay walks into."""
    broken = fields.diag_event(TILES_YX, _fits(), CAP_A, 0, 0, 4)
    object.__setattr__(broken, "block_tiles_yx", "not a shape")
    return (_run(), _capture(), broken, *_certified(0, 0, 0))


def test_a_pane_that_raises_refuses_and_the_products_still_land(tmp_path):
    events = _broken_events()
    model = _fold(events)
    with pytest.raises(Exception):
        panes.render_pane(model, "field", 0)
    # every OTHER pane still pins, and the poisoned one is simply absent
    pinned = panes.pin_panes(model)
    assert ("field", 0) not in pinned
    assert {("capture", 0), ("page", 0), ("payload", 0),
            ("pose", 0)} <= set(pinned)
    diag_report.write_report(tmp_path / "report.json", model)
    diag_report.write_events_jsonl(tmp_path / "events.jsonl", events[:3])
    assert (tmp_path / "report.json").is_file()
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert [json.loads(line)["type"] for line in lines] == [
        "RunOpen", "CaptureOpen", "FieldFitted"]


def test_the_engine_run_dir_products_survive_a_pane_that_raises(tmp_path):
    from holo3 import engine

    engine._diag_products(tmp_path, list(_broken_events()))
    assert (tmp_path / "report.json").is_file()
    assert (tmp_path / "events.jsonl").is_file()
    assert not (tmp_path / "pane-field-0.png").exists()
    assert (tmp_path / "pane-page-0.png").is_file()


def test_the_live_band_answers_a_broken_event_with_a_refusal():
    live: list = list(_broken_events())
    instance = server.serve(0, live)
    assert instance is not None
    try:
        assert _get(instance, "/status")[0] == 200
        code, body = _get(instance, "/pane/field-0.png")
        assert code == 500
        assert b"pane failed" in body
        # the panes that CAN draw are untouched by the one that cannot
        assert _get(instance, "/pane/payload-0.png")[0] == 200
    finally:
        instance.stop()


# -- the live server -------------------------------------------------


FIELD_EVENTS: tuple = (_run(), _capture(), _event())


@pytest.fixture(scope="module")
def field_server():
    live: list = [_run(), _capture()]
    instance = server.serve(0, live)
    assert instance is not None
    try:
        yield instance, live
    finally:
        instance.stop()


def _get(instance, path: str) -> tuple[int, bytes]:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        f"http://127.0.0.1:{instance.port}{path}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_the_home_shell_names_the_field_img(field_server):
    instance, _live = field_server
    code, body = _get(instance, "/")
    assert code == 200
    assert b'id="img-field"' in body


def test_status_says_unavailable_and_the_band_404s_before_a_fit(
        field_server):
    instance, _live = field_server
    code, body = _get(instance, "/status")
    assert code == 200
    status = json.loads(body)
    assert "fields   unavailable before the first fit" in status["rows"]
    assert status["panes"]["field"] == []
    assert _get(instance, "/pane/field-0.png")[0] == 404


def test_the_band_appears_the_moment_a_fit_lands(field_server):
    instance, live = field_server
    live.append(_event())
    code, body = _get(instance, "/status")
    assert code == 200
    status = json.loads(body)
    assert status["panes"]["field"] == [0]
    assert any(row.startswith("fields   lane 0.0") for row in status["rows"])
    code, png = _get(instance, "/pane/field-0.png")
    assert code == 200 and png[:8] == PNG_MAGIC
