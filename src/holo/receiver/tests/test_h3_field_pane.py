"""The FIELD band and its producer: what the `fields` row publishes to
diag, and what the viewer makes of it.

Synthetic throughout — the events are built by the real producer
(`plugins.fields.solved_event`) from real `lib.plane_field.Solution`
records, so nothing here is a hand-written event that could drift from
the shape the decode actually emits.  The end-to-end rendering gate on a
real sim capture went with that module's three decodes on 2026-09-20
(`docs/WIDENED-MATRIX-RETIREMENT-2026-09-20.md`); the page-field frame
decodes are what exercise the producer on real pixels now.

W2 (2026-09-07) re-pinned this module on the PAGE field: one solve per
page instead of one fit per lane-page, no publish verdict and no
refusal — every plane of a solved page has a field, and a plane no
observation reached reads zero with zero support.  W4 (2026-09-08)
re-pinned the readers on it.  W8 (2026-09-08) re-pinned them again, off
a run, on the shape the new solve publishes: ONE `Solution` over all
three planes rather than three of them; the per-tile UNCERTAINTY beside
the value and a plane that reads UNKNOWN rather than zero (I13); the
residual energies per (capture, PLANE), never summed across planes
first (R-F, review F11); and the page's evidence REVISION where the
trigger ratio used to be, the trigger being retired in all three of its
forms (design §2.7).
"""

from __future__ import annotations

import io
import json

import numpy as np
import pytest
from PIL import Image

from holo.receiver import data
from holo.receiver.diag import fields_pane
from holo.receiver.diag import model as diag_model
from holo.receiver.diag import readout as diag_readout
from holo.receiver.diag import report as diag_report
from holo.receiver.diag import panes, server
from holo.receiver.lib import plane_field
from holo.receiver.plugins import fields

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

CAP_A = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
CAP_B = "b1b2c3d4e5f60718293a4b5c6d7e8f90"
FORMAT_ID = "src/holo/receiver/v2/c2-cmy8-r0700@6x10"

TILES_YX = (10, 6)


def _run(streams: tuple[str, ...] = ("C", "M", "Y"),
         tiles_yx: tuple[int, int] = TILES_YX,
         pages: int = 1) -> data.RunOpen:
    return data.RunOpen(format_id=FORMAT_ID, pages=pages, tiles_yx=tiles_yx,
                        stream_ids=streams, n_captures=1, workers=1,
                        family="cmy8", pitch_in=1 / 300)


def _capture(capture: str = CAP_A, ordinal: int = 0) -> data.CaptureOpen:
    return data.CaptureOpen(capture=capture, dpi=2400.0, shape_yx=(600, 400),
                            channels=3, duplicate=False, ordinal=ordinal)


def _certified(page: int, ty: int, tx: int) -> tuple:
    return tuple(
        data.TileOutcome(page=page, ty=ty, tx=tx, stream_id=stream,
                         source="scan", result="certified", bp_iters=3)
        for stream in ("C", "M", "Y"))


#: the error bar a fixture tile carries where evidence reached it, and
#: where the prior faded the field back to the pose.  Two numbers, so
#: that "measured < faded" is visible in anything this module renders;
#: what the real solve publishes is `test_h3_field_estimator`'s.
UNCERTAINTY_MEASURED_DOTS = 0.02
UNCERTAINTY_FADED_DOTS = 0.30


def _residuals(captures: tuple[str, ...], count: int,
               energies: tuple[float, ...] | None = None,
               ) -> dict[tuple[int, int], plane_field.Residual]:
    """One `Residual` per (capture, PLANE) — R-F's shape.

    The weight is the observation count, so `Residual.expected` is one
    noise scale per measured component and a ratio reads in the units
    the band prints.
    """
    return {
        (index, plane): plane_field.Residual(
            energy=(0.5 if energies is None else float(energies[index])),
            weight=float(count), count=int(count))
        for index in range(len(captures)) for plane in range(3)}


#: The page's evidence revision at solve time (I12).  Any number does:
#: the row prints it, nothing computes with it, and the trigger ratio it
#: replaces was the thing that pretended to decide something.
REVISION: int = 4


def _plane(delta_dots_xy: np.ndarray, support: np.ndarray,
           n_observations: int = 4096) -> tuple:
    """One plane's three columns, before they are stacked into a
    `Solution`: the solve publishes all three at once."""
    return (np.asarray(delta_dots_xy, np.float64),
            np.asarray(support, np.float64), int(n_observations))


def _solution(planes: tuple, captures: tuple[str, ...] = (CAP_A,),
              energies: tuple[float, ...] | None = None,
              revision: int = REVISION) -> plane_field.Solution:
    delta = np.stack([entry[0] for entry in planes])
    support = np.stack([entry[1] for entry in planes])
    live = support > 0.0
    per_tile = np.stack([
        np.where(live[plane],
                 max(1, planes[plane][2] // max(1, int(live[plane].sum()))),
                 0).astype(np.int64)
        for plane in range(len(planes))])
    return plane_field.Solution(
        delta_dots_xy=delta,
        uncertainty_dots=np.where(live, UNCERTAINTY_MEASURED_DOTS,
                                  UNCERTAINTY_FADED_DOTS),
        support=support,
        n_observations=per_tile,
        n_captures=np.where(live, len(captures), 0).astype(np.int64),
        plane_known=np.array([bool(live[plane].any())
                              for plane in range(len(planes))]),
        nuisance_dots_xy=np.zeros((len(captures), 2), np.float64),
        residual_by_capture_plane=_residuals(
            captures, int(per_tile[0].sum()), energies),
        revision=int(revision), passes=1, converged=True,
        max_gradient=0.0)


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


def _solutions(tiles_yx: tuple[int, int] = TILES_YX,
               blind: tuple[slice, slice] | None = None,
               y_dx: float = 0.9,
               captures: tuple[str, ...] = (CAP_A,),
               energies: tuple[float, ...] | None = None,
               revision: int = REVISION) -> plane_field.Solution:
    """C small, M with no evidence at all, Y large."""
    support = _support(tiles_yx, blind)
    return _solution(
        (_plane(_uniform(tiles_yx, 0.05), support, 4096),
         _plane(_uniform(tiles_yx, 0.0), np.zeros(tiles_yx, np.float64), 0),
         _plane(_uniform(tiles_yx, y_dx), support, 5000)),
        captures, energies, revision)


def _event(tiles_yx: tuple[int, int] = TILES_YX,
           captures: tuple[str, ...] = (CAP_A,), page: int = 0,
           revision: int = REVISION, **kwargs) -> data.FieldSolved:
    return fields.solved_event(
        page, _solutions(tiles_yx, captures=captures, revision=revision,
                         **kwargs), captures)


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


def test_a_plane_no_observation_reached_reads_unknown_not_zero():
    """I6 and I13 together: the field always exists for a colour family
    and an unseen tile reads exactly zero, but the ROW says that zero is
    unknown and not measured.  `has_data` carries it per tile and
    `known` carries it per plane — the honesty that used to be spelled
    as a None, and that a starved Y depends on (W8 R-C)."""
    row = _event().planes[1]
    assert row.plane_name == "M"
    assert not row.known
    assert row.median_delta_dots == 0.0
    assert row.support_tiles == 0
    assert row.n_observations == 0
    assert row.n_captures == 0
    assert not np.any(row.has_data)
    assert not np.any(row.delta_grid_dots_xy)


def test_a_small_field_is_reported_as_the_measurement_it_is():
    """I8: no publish floor.  A 0.05-dot field is a small field, not a
    refused one, and the row carries the number either way."""
    row = _event().planes[0]
    assert row.plane_name == "C"
    assert row.known
    assert row.median_delta_dots == pytest.approx(0.05)
    assert row.median_uncertainty_dots == pytest.approx(
        UNCERTAINTY_MEASURED_DOTS)
    assert row.support_tiles == TILES_YX[0] * TILES_YX[1]
    assert row.n_captures == 1


@pytest.mark.parametrize("tiles_yx", [(10, 6), (53, 37), (200, 140)])
def test_the_event_grid_is_capped_on_both_axes(tiles_yx):
    event = _event(tiles_yx)
    grid = event.planes[2].delta_grid_dots_xy
    assert grid.shape[0] <= fields.DIAG_GRID_MAX
    assert grid.shape[1] <= fields.DIAG_GRID_MAX
    assert grid.dtype == np.float32
    cost = sum(row.delta_grid_dots_xy.nbytes + row.has_data.nbytes
               for row in event.planes)
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


def test_the_event_names_every_capture_and_plane_that_fed_the_solve():
    """R-F: the residual table is per (capture, PLANE) and never summed
    across planes first (review F11), so the sheet-H question — which
    FOOTING disagrees with the page — is now also answerable about which
    plane it disagrees on."""
    event = _event(captures=(CAP_A, CAP_B))
    rows = event.residual_by_capture_plane
    assert {(capture, plane) for capture, plane, *_rest in rows} == {
        (capture, plane) for capture in (CAP_A, CAP_B)
        for plane in range(3)}
    for _capture, _plane, energy, expected, count in rows:
        assert expected > 0.0 and count > 0 and energy > 0.0


def test_the_event_carries_the_revision_the_page_was_solved_at():
    """I12, and what replaced the trigger: the page solves because its
    evidence revision moved, so the number the event owes is that
    revision and not a statistic that pretended to decide."""
    assert _event(revision=11).revision == 11


# -- the fold --------------------------------------------------------


def test_the_latest_solve_wins_and_there_is_only_ever_one_per_page():
    """I1: one field per page.  A re-solve supersedes its predecessor;
    nothing accumulates beside it, which is exactly what the retired
    lane-page key could not say."""
    first = _event(y_dx=0.4)
    second = _event(y_dx=0.9)
    model = _fold((_run(), _capture(), first, second))
    assert len(model.field_solves) == 1
    assert model.field_solves[0] is second
    assert diag_readout.page_field(model, 0) is second


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
                                n_captures=1, workers=1, family="k"),
                   _capture()))
    assert diag_readout.field_rows(model) == ()
    assert diag_readout.all_rows(model) == diag_readout.six_row_status(model)


def test_a_colour_run_names_the_wait_before_the_first_solve():
    model = _fold((_run(), _capture()))
    assert diag_readout.field_rows(model) == (
        "fields   unavailable before the first solve",)


def test_the_field_row_carries_the_page_its_medians_and_its_support():
    """The row's exact spelling, which is this module's to freeze: each
    plane's median with the solve's own error bar beside it, the plane
    with no template spelled UNKNOWN rather than 0.00 (I13), the
    evidence revision, and the loudest (capture, plane) disagreement."""
    model = _fold((_run(), _capture(), _event()))
    row, = diag_readout.field_rows(model)
    assert row == ("fields   page 0 — C 0.05±0.02 M unknown Y 0.90±0.02"
                   " dots, support 67% · rev 4 · passes 1"
                   " · worst C 0.00x"), row
    # two planes of three carry evidence on every tile, the third none
    assert diag_readout.field_support(_event()) == pytest.approx(2 / 3)


def test_every_page_a_solve_landed_on_gets_its_own_row_in_page_order():
    """W4: per page, because the field is per (page, plane) — a duplex
    sheet's two faces carry different fields (design §2.2), and a single
    latest-solve row could name only one of them."""
    model = _fold((_run(pages=2), _capture(),
                   _event(page=1, y_dx=0.9), _event(page=0, y_dx=0.3)))
    rows = diag_readout.field_rows(model)
    assert [row.split(" — ")[0] for row in rows] == [
        "fields   page 0", "fields   page 1"]
    assert "Y 0.30±" in rows[0] and "Y 0.90±" in rows[1]
    assert diag_readout.all_rows(model)[6:] == rows


def test_the_row_says_which_plane_disagrees_with_its_field_and_how_loudly():
    """R-F on the status block: the loudest (capture, PLANE) ratio, so a
    Y plane whose evidence fights its field is visible behind two
    healthy word planes (review F11).  The two-capture stimulus makes
    the ordering do work — the louder footing's plane wins.
    """
    model = _fold((_run(), _capture(), _capture(CAP_B, 1),
                   _event(captures=(CAP_A, CAP_B),
                          energies=(600.0, 3000.0))))
    row, = diag_readout.field_rows(model)
    loudest = max(
        energy / expected for _capture, _plane, energy, expected, _count
        in diag_readout.page_field(model, 0).residual_by_capture_plane)
    assert row.endswith(f"· worst C {loudest:.2f}x"), row


#: One name per subject, 2026-09-05: the seam, the per-plane verdicts and
#: the JSON round-trip used to share one name.  Same one-line fold in each,
#: same seven assertions, three failure names.
def test_the_rows_ride_the_status_dict_and_the_report():
    model = _fold((_run(), _capture(), _event()))
    status = diag_readout.status(model)
    assert status["rows"] == list(diag_readout.all_rows(model))
    report = diag_report.build_report(model)
    assert len(report["plane_fields"]) == 1


def test_the_report_names_each_planes_measurement():
    model = _fold((_run(), _capture(), _event()))
    report = diag_report.build_report(model)
    planes = {row["plane_name"]: row for row in
              report["plane_fields"][0]["planes"]}
    assert planes["Y"]["median_delta_dots"] == pytest.approx(0.9)
    assert planes["C"]["median_delta_dots"] == pytest.approx(0.05)
    assert planes["M"]["support_tiles"] == 0


def test_the_report_carries_the_residual_per_capture_and_plane_in_json():
    model = _fold((_run(), _capture(), _capture(CAP_B, 1),
                   _event(captures=(CAP_A, CAP_B))))
    report = diag_report.build_report(model)
    page = json.loads(json.dumps(
        diag_report._jsonable(report)))["plane_fields"][0]
    assert page["page"] == 0
    assert page["revision"] == REVISION
    rows = page["residual_by_capture_plane"]
    assert {(row["capture_label"], row["plane_name"]) for row in rows} == {
        (label, plane) for label in ("0", "1") for plane in "CMY"}


def test_the_report_carries_each_planes_uncertainty_and_whether_it_is_known():
    """The status row glances at the medians; the post-mortem carries
    the error bar beside every one of them and says which planes were
    measured at all (design §2.4, I13)."""
    model = _fold((_run(), _capture(), _event()))
    report = json.loads(json.dumps(diag_report._jsonable(
        diag_report.build_report(model))))
    planes = {row["plane_name"]: row
              for row in report["plane_fields"][0]["planes"]}
    assert planes["C"]["known"] and planes["Y"]["known"]
    assert not planes["M"]["known"]
    assert planes["C"]["median_uncertainty_dots"] == pytest.approx(
        UNCERTAINTY_MEASURED_DOTS)
    assert planes["M"]["median_uncertainty_dots"] == 0.0


# -- the band --------------------------------------------------------


def test_the_band_is_absent_until_a_solve_lands():
    bare = _fold((_run(), _capture()))
    assert panes.render_pane(bare, "field", 0) is None
    assert ("field", 0) not in panes.pin_panes(bare)
    fitted = _fold((_run(), _capture(), _event()))
    png = panes.render_pane(fitted, "field", 0)
    assert png[:8] == PNG_MAGIC
    assert ("field", 0) in panes.pin_panes(fitted)


def test_the_band_paints_each_plane_in_its_own_hue():
    body = _body(_fold((_run(), _capture(), _event())))
    assert _has_colour(body, fields_pane.PLANE_HUE["Y"])
    assert _has_colour(body, fields_pane.PLANE_HUE["C"])
    # M reached no tile, so it draws no arrow at all
    assert not _has_colour(body, fields_pane.PLANE_HUE["M"])


def test_the_shading_threshold_is_the_fields_own_noise_scale(monkeypatch):
    """W4: one number, named once.  Pinned by MOVING the constant, not
    by bracketing its value: a floor re-typed into the band — 0.25
    itself included — reads identically until the design's scale
    changes, which is exactly the drift the charter is guarding."""
    def shades(dots: float) -> bool:
        model = _fold((_run(), _capture(), _event(y_dx=dots)))
        return _has_colour(_body(model), fields_pane.SHADE)

    floor = plane_field.FIELD_NOISE_DOTS
    assert floor == 0.25
    assert not hasattr(fields_pane, "SHADE_DOTS")
    assert shades(floor + 0.01) and not shades(floor - 0.01)
    monkeypatch.setattr(plane_field, "FIELD_NOISE_DOTS", 0.6)
    assert shades(0.61) and not shades(0.59)


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


def _measured(event: data.FieldSolved) -> tuple:
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


def test_a_page_no_plane_has_evidence_on_still_renders():
    empty = _plane(_uniform(TILES_YX, 0.0),
                   np.zeros(TILES_YX, np.float64), 0)
    flat = fields.solved_event(0, _solution((empty, empty, empty)),
                               (CAP_A,))
    model = _fold((_run(), _capture(), flat))
    png = panes.render_pane(model, "field", 0)
    assert png[:8] == PNG_MAGIC
    row, = diag_readout.field_rows(model)
    assert "support 0%" in row


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
    event = fields.solved_event(
        0,
        _solution((_plane(_uniform(tiles, 0.6), full),
                   _plane(_uniform(tiles, 0.0),
                          np.zeros(tiles, np.float64), 0),
                   _plane(_uniform(tiles, 0.6), dead))),
        (CAP_A,))
    body = _body(_fold((_run(), _capture(), event)))
    assert _has_colour(body, _mix(fields_pane.PLANE_HUE["Y"],
                                  fields_pane.BLIND_MIX))
    # C measured everywhere, so C never tints a blind segment
    assert not _has_colour(body, _mix(fields_pane.PLANE_HUE["C"],
                                      fields_pane.BLIND_MIX))
    # and no block is a whole-band hole: C reached all of them
    assert not _has_colour(body, fields_pane.HOLE)


def test_opposing_deltas_in_one_block_still_shade_it():
    """The shading is on the pooled per-tile MAGNITUDE: a block
    straddling a sign change clears the threshold while its pooled
    vector reads zero."""
    tiles = (48, 48)
    delta = np.zeros(tiles + (2,), np.float64)
    delta[:, 0::2, 0] = 0.9
    delta[:, 1::2, 0] = -0.9
    blank = _plane(_uniform(tiles, 0.0), np.zeros(tiles, np.float64), 0)
    event = fields.solved_event(
        0, _solution((_plane(delta, _support(tiles)), blank, blank)),
        (CAP_A,))
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


def test_the_residual_table_puts_the_loudest_footing_and_plane_first():
    """The sheet-H question (design §7) as an ordering: which footing
    disagrees with the page, and — since W8 (R-F) — on which plane, one
    line per (capture, plane).  Captures are named by their ordinal:
    the field has no lane to name."""
    model = _fold((_run(), _capture(), _capture(CAP_B, 1),
                   _event(captures=(CAP_A, CAP_B),
                          energies=(600.0, 3000.0))))
    fit = diag_readout.page_field(model, 0)
    header, *table = fields_pane._residual_table(model, fit)
    assert header == "residual/noise by capture and plane, loudest first"
    assert [line.split()[0] for line in table] == ["1", "1", "1",
                                                   "0", "0", "0"]
    assert [line.split()[1] for line in table] == list("CMYCMY")
    ratios = [float(line.split()[2].removesuffix("x")) for line in table]
    assert ratios[0] > ratios[-1] > 0.0
    # and the table is what the band prints, one line per capture-plane
    printed = [line for line, _ink in
               fields_pane._text_lines(model, fit, 50.0, (10, 6))]
    assert printed[-7:] == [header] + table


def test_a_tie_falls_back_to_the_events_own_capture_order():
    """The labels are ordinals, so a text sort would put capture 10
    ahead of capture 2 whenever two footings disagree by the same
    amount."""
    model = _fold((_run(), _capture(CAP_A, 2), _capture(CAP_B, 10),
                   _event(captures=(CAP_A, CAP_B),
                          energies=(600.0, 600.0))))
    fit = diag_readout.page_field(model, 0)
    _header, *table = fields_pane._residual_table(model, fit)
    assert [line.split()[0] for line in table] == ["2", "2", "2",
                                                   "10", "10", "10"]


def test_the_bands_text_names_each_planes_measurement():
    n_tiles = TILES_YX[0] * TILES_YX[1]
    lines = [fields_pane._plane_line(row, n_tiles)
             for row in _event().planes]
    assert lines[0].startswith(
        f"C  median 0.050d ± {UNCERTAINTY_MEASURED_DOTS:.3f}d")
    assert f"support {n_tiles}/{n_tiles} tiles" in lines[0]
    assert lines[1] == "M  unknown — no template on any tile"
    assert lines[2].startswith("Y  median 0.900d")


# -- no diag failure touches the decode ------------------------------


class _Poison:
    """A field event whose planes explode when the pane touches them.

    It carries `FieldSolved`'s own fields and not the retired
    `FieldFitted`'s: what the fold dispatches on is the type, so the
    columns are here to make the stub readable rather than to be read.
    """

    page = 0
    tiles_yx = TILES_YX
    block_tiles_yx = (1, 1)
    residual_by_capture_plane = ()
    revision = 0

    @property
    def planes(self):
        raise ValueError("poisoned field event")


def test_a_poisoned_field_event_is_counted_never_raised():
    model = _fold((_run(), _capture(), _Poison()))
    # not a FieldSolved, so the fold ignores it outright: no crash
    assert model.fold_errors == 0
    assert diag_readout.field_pages(model) == ()


def _broken_events() -> tuple:
    """A field event the band cannot draw: its block shape is not a
    shape, which the certified-tile overlay walks into."""
    broken = _event()
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
        "RunOpen", "CaptureOpen", "FieldSolved"]


def test_the_engine_run_dir_products_survive_a_pane_that_raises(tmp_path):
    from holo.receiver import operator

    operator._diag_products(tmp_path, list(_broken_events()))
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


def test_status_says_unavailable_and_the_band_404s_before_a_solve(
        field_server):
    instance, _live = field_server
    code, body = _get(instance, "/status")
    assert code == 200
    status = json.loads(body)
    assert ("fields   unavailable before the first solve"
            in status["rows"])
    assert status["panes"]["field"] == []
    assert _get(instance, "/pane/field-0.png")[0] == 404


def test_the_band_appears_the_moment_a_solve_lands(field_server):
    instance, live = field_server
    live.append(_event())
    code, body = _get(instance, "/status")
    assert code == 200
    status = json.loads(body)
    assert status["panes"]["field"] == [0]
    assert any(row.startswith("fields   page 0")
               for row in status["rows"])
    code, png = _get(instance, "/pane/field-0.png")
    assert code == 200 and png[:8] == PNG_MAGIC
