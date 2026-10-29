"""The c2 cmy page through the receiver (CMY-RECEIVER-PLAN A9): the print-
edge row read at 2400 dpi with M and Y a dot out of register, closed with
one toner dead (CMY-DESIGN §11 G8), and read cold off a 2x3-tile scrap
(G12).

The stimuli are `_h3_sims_cmy`'s: `c2-cmy-r0775x0700@10x10`, e043c sheet
3's bars, M and Y +1.0 dot in x (B1's +1.23 / +1.06 at the nearest half
dot), a 3-px dot gain; the same emission rendered with Y, M or C
`dropped`; and seeded scraps of whole tiles cut from it, each with its
own plane offsets (Z, A, B, C) and an M/Y drift across it or its
same-blur control.

What this module states.  The page closes VERIFIED byte-exact and every
certificate is the generator's.  G8, through the whole engine at q =
0.35, under the pair's any-one-stream ceiling 17/36: a dead Y closes with
no lo certificate, a dead M with no hi certificate, a dead C ends OPEN
with nothing certified and the run done; and the colour lane's fit at the
render's own pose erases exactly the dead toner's stream
(`color_model.cmy_unsupported_streams`): none on the live page, lo under a
dead Y, hi under a dead M.  G12 on 2x3 scraps (Z and A drifting, A's
same-blur control, C constant): every scrap is placed at its true
counters and certifies nothing that is not the generator's, no scrap
closes (twelve metadata equations are below rank 24), and what each
certifies and where its field reads the plant is a measured pin -- C,
2.5 dots out, is the expected RECOVERY R17 makes a finding when refused,
and the pin says what happened.

LEDGER 2026-10-12 (A9), a record, not a test; four lane runs on fresh
caches (machine 1, `-n 0`, 181, 151, 173 and 178 s cold for the module,
renders included), every crop record identical wherever it was decoded
(Z, A drifting and C in all four, A's control in the last two and in the
record).  The page
(`decode_cmy_c2_w8`, eight workers, `--max-pages 1`): VERIFIED byte-exact,
52 / 54 / 52 / 56 certificates (hi 23-28, lo 26-29), `tiles.scan` 44-53
and `tiles.cond` 1-8, the close's 44 source symbols, 13.0-17.5 s and 52-67
cpu-s; the field never solved before the close (a scratch `--complete`
decode: 200 tile-streams, M +0.99 and Y +1.08 dots against the plant's
+1.0, 48.5 s).  The render's supervised context-free W row is 5.88 %
against paper's 13.9-14.9 % (measure/cmy_coldstart, RESULTS-2026-10-12):
the stimulus is easier than paper.  G8: dead Y VERIFIED on hi alone, 48
each run (scan 25-47, local 0-22, retry 0-1), 33-51 s; dead M VERIFIED
on lo alone, 52-55 (scan 30-42, local 12-24, retry 0-1), 28-40 s; both
solved the field twice (dead Y: M +0.90-0.94, Y no data; dead M: Y +1.01,
M no data); dead C OPEN, RunDone "open", 0 certificates, nothing
attempted, metadata rank 0, survey 1 and `place` 1,008 jobs (106-112
cpu-s, 22-23 s) -- the placement ladder exhausting a page with no dark word
site, then done.  The erasure trigger fired on every lane fit of the dead
pages in a scratch decode with `color_model.cmy_unsupported_streams`
logged at run time: dead Y erased lo in all 242 fits, dead M hi in all
54, the live page nothing in 3 (pinned at the render's pose below).  G12
(one worker, deterministic): 2x3-Z-drift 6/6 by scan, all before the
field's one solve, 12 LDPC attempts (CRC exposure <= 2.8e-9), field M
+0.00, Y +0.01; 2x3-A-drift 6/6 (scan 10, cond 2; 9 before the first of
two solves), 53 attempts (1.2e-8), M +0.46, Y -0.40 against +0.5 / -0.5;
its control 6/6 by scan, 48 attempts (1.1e-8), M +0.45, Y -0.13 -- Y's
reading leans ~35 % toward M's offset where they differ, M's ink in Y's
B channel (the record's `lean`: the raw read before any solve leans the
same, with or without the dot gain; no interpolation reads -0.14), so at
the half-dot quantum the control's Y misses its plant by 0.5 while the
drift's does not; 2x3-C-none 0/0, M no field data (2.5 dots past the 2.24-dot reach),
Y -1.74 on 2 tiles, scan, retry and swim attempted and failed, 18
attempts (4.2e-9) -- R17's expected recovery refused, a FINDING.  Across
a two-tile scrap the field's per-tile range is 0.08-0.11 dot against the
drift's +-0.25 tile-row means: it reads the scrap's mean.  The 1x2/2x2
shapes, B and the other controls are the record's.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from holo.receiver import data
from holo.receiver.format import identity, keystream, tile_codec
from holo.receiver.plugins import (color_model, color_region,
                                   color_region_head, color_sites, tiles)
from holo.receiver.tests import (_h3_fixture_geometry, _h3_sims,
                                 _h3_sims_cmy, _h3_support)

BORDER_PX = _h3_sims.COLOR_BORDER_DOTS * _h3_sims_cmy.CMY_C2_PX_PER_DOT
TILE_CELLS = 64


def _row() -> identity.FormatRow:
    return identity.resolve_format_ref(_h3_sims_cmy.CMY_C2_FORMAT_REF)


def _pitch_px(row: identity.FormatRow) -> int:
    return int(row.pitch_in * _h3_sims_cmy.CMY_C2_DPI)


def _gt_states(capture: _h3_sims.SimCapture,
               row: identity.FormatRow) -> np.ndarray:
    """The emitter's GT page as presence ids, one per cell."""
    planes = np.unpackbits(_h3_sims.load_emit_gt(capture), axis=-1)
    cells_y, cells_x = row.cells_yx
    step = planes.shape[1] // cells_y
    cells = planes[:, step // 2::step, step // 2::step][:, :cells_y,
                                                         :cells_x]
    return tile_codec.planes_to_states(np.moveaxis(cells, 0, -1))


def _wrong_label_bits(record: object,
                      capture: _h3_sims.SimCapture) -> dict[tuple, int]:
    """Per certificate, its label bits that differ from the GT's: the
    user bits re-encoded and dithered as the generator sent them, read
    through the tile's cell permutation."""
    row = _row()
    flat = np.asarray(identity.build_site_geometry(row).payload_flat,
                      np.int64)
    gt = _gt_states(capture, row)
    wrong = {}
    for key, certificate in sorted(record.certificates.items()):
        page, ty, tx, stream_id = key
        fact = tiles.stream_fact(row, stream_id)
        counter = row.tile_counter(page, ty, tx)
        sent = (tile_codec.encode_frame(
                    np.asarray(certificate.user_bits, np.uint8),
                    fact.rung_children)
                ^ keystream.cmy8_dither_bits(
                    row.seed, fact.dither_aux, counter,
                    tile_codec.bank_transmitted_bits(fact.rung_children)))
        label = sent[keystream.color_cell_permutation(row.seed, counter,
                                                      row.payload_cells)]
        tile = gt[ty * TILE_CELLS:(ty + 1) * TILE_CELLS,
                  tx * TILE_CELLS:(tx + 1) * TILE_CELLS].ravel()
        truth = color_model.CMY_COLUMN_LABEL_BITS[
            color_region_head.state_columns(row.state_ids, tile[flat])
        ][:, fact.label_index]
        wrong[key] = int(np.count_nonzero(label != truth))
    return wrong


def _streams(record: object) -> set[str]:
    return {key[3] for key in record.certificates}


def _assert_verified_byte_exact(record: object,
                                capture: _h3_sims.SimCapture) -> None:
    assert record.exit_code == 0
    assert record.status == "verified"
    assert record.payload == capture.payload_data
    _h3_support.assert_golden("recovered c2 cmy payload sha256",
                              record.payload_sha256,
                              _h3_sims_cmy.CMY_C2_PAYLOAD_SHA256)
    final = [event for event in record.events
             if isinstance(event, data.CloseCheck)][-1]
    assert final.status == "verified"
    assert final.certified == record.certified


def test_the_c2_sim_decode_is_verified_and_byte_exact(decode_cmy_c2_w8,
                                                      sim_cmy_c2):
    _assert_verified_byte_exact(decode_cmy_c2_w8, sim_cmy_c2)


def test_every_c2_certificate_is_the_generators(decode_cmy_c2_w8,
                                                sim_cmy_c2):
    assert _streams(decode_cmy_c2_w8) == {"hi", "lo"}
    wrong = _wrong_label_bits(decode_cmy_c2_w8, sim_cmy_c2)
    assert wrong and not any(wrong.values()), wrong


#: Design §2.2's death map through the engine: the stream each dead
#: toner leaves certifiable, None where none is (C carries the words'
#: '1' and both labels' C state).
SURVIVING_STREAM = {"Y": "hi", "M": "lo", "C": None}


@pytest.mark.parametrize("toner", sorted(SURVIVING_STREAM))
def test_a_dead_toner_closes_on_its_surviving_stream_or_stays_open(
        decode_cmy_c2_dead, sim_cmy_c2_dead, toner):
    """G8 at q = 0.35, under the pair's any-one-stream ceiling (17/36):
    the stream tier closes a dead Y on hi alone and a dead M on lo alone;
    a dead C certifies nothing, the close stays OPEN, and the run ends --
    a RunDone, the frontier drained."""
    record = decode_cmy_c2_dead(toner)
    capture = sim_cmy_c2_dead(toner)
    survivor = SURVIVING_STREAM[toner]
    if survivor is None:
        assert record.certified == 0
        assert record.exit_code != 0 and record.payload is None
        (done,) = [event for event in record.events
                   if isinstance(event, data.RunDone)]
        assert done.status == "open"
        final = [event for event in record.events
                 if isinstance(event, data.CloseCheck)][-1]
        assert (final.status, final.metadata_rank) == ("open", 0)
        return
    _assert_verified_byte_exact(record, capture)
    assert _streams(record) == {survivor}
    wrong = _wrong_label_bits(record, capture)
    assert not any(wrong.values()), wrong


def _page_window(row: identity.FormatRow) -> color_region.RegionWindow:
    """The whole page as one window at the render's own pose (cell c
    starts at BORDER_PX + pitch * c, pixel-edge frame)."""
    cells_y, cells_x = row.cells_yx
    placement = _h3_fixture_geometry.window_placement(
        ("sim-cmy-c2", 0, 0, (0, 0, cells_y, cells_x)),
        _h3_fixture_geometry.page_native_affine(_pitch_px(row),
                                                BORDER_PX - 0.5),
        _h3_fixture_geometry.grid_cells((0, 0), (cells_y, cells_x)))
    return _h3_fixture_geometry.window_pose(row, placement)


@pytest.mark.parametrize("toner, erased", [
    (None, ()), ("Y", (1,)), ("M", (0,))], ids=["live", "dead-Y", "dead-M"])
def test_the_lane_fit_erases_the_dead_toners_stream(
        sim_cmy_c2, sim_cmy_c2_dead, toner, erased):
    """The erasure trigger (`color_model.cmy_unsupported_streams`, A3)
    over the whole page at the render's own pose: it erases nothing on
    the live page, lo (stream 1) under a dead Y, hi (stream 0) under a
    dead M -- what the dead decodes' every lane fit did (the ledger)."""
    import tifffile

    row = _row()
    capture = sim_cmy_c2 if toner is None else sim_cmy_c2_dead(toner)
    image = tifffile.imread(capture.tiff)
    planes = tuple(SimpleNamespace(
        open=lambda channel=channel: image[..., channel])
        for channel in range(3))
    inputs = color_region.build_region_inputs(
        row, identity.build_site_geometry(row), (_page_window(row),), (),
        planes, {}, "sim-cmy-c2", 0)
    stack = color_region_head.fit_region_stack(
        row, inputs.selection, inputs.row_tuple, inputs.base_tuple,
        inputs.corrected, inputs.emission_by_row,
        color_region_head.StackConfig())
    assert stack.selected is not None, stack.refusal_reason
    assert stack.selected.erased_streams == erased


def _crop_tiles(shape: tuple[int, int]) -> set[tuple[int, int, int]]:
    ty0, tx0 = _h3_sims_cmy.cmy_c2_crop_origin(shape)
    return {(0, ty0 + dy, tx0 + dx)
            for dy in range(shape[0]) for dx in range(shape[1])}


def _crop_offset_px(event: data.PoseCommitted, shape: tuple[int, int],
                    pitch_px: int) -> float:
    """Placed minus printed pixel of the window's centre cell: the scrap
    prints page cell c at BORDER_PX + pitch * (c - its first cell) in the
    pixel-edge frame, half a pixel later than the native affine's."""
    first = np.asarray(_h3_sims_cmy.cmy_c2_crop_origin(shape),
                       np.float64) * TILE_CELLS
    centre = (np.asarray(event.page_origin_yx, np.float64)
              + np.asarray(event.shape_yx, np.float64) / 2.0)
    affine = np.asarray(event.native_affine, np.float64).reshape(2, 3)
    placed = affine[:, :2] @ centre + affine[:, 2]
    printed = BORDER_PX - 0.5 + pitch_px * (centre - first)
    return float(np.abs(placed - printed).max())


CROPS = _h3_sims_cmy.CMY_C2_TESTED_CROPS
CROP_IDS = [_h3_sims_cmy.cmy_c2_crop_name(*crop) for crop in CROPS]


@pytest.mark.parametrize("shape, plant, drift", CROPS, ids=CROP_IDS)
def test_a_cold_scrap_is_placed_at_its_true_counters(
        decode_cmy_c2_crop, shape, plant, drift):
    record = decode_cmy_c2_crop(shape, plant, drift)
    pitch_px = _pitch_px(_row())
    covered = {(event.page, ty, tx) for event in record.events
               if isinstance(event, data.AddressCoverage)
               for ty, tx, _sites in event.tiles}
    assert covered == _crop_tiles(shape)
    poses = [event for event in record.events
             if isinstance(event, data.PoseCommitted)]
    assert poses
    for event in poses:
        assert (event.page, event.rot_k) == (0, 0)
        assert _crop_offset_px(event, shape, pitch_px) < pitch_px / 2


@pytest.mark.parametrize("shape, plant, drift", CROPS, ids=CROP_IDS)
def test_a_cold_scrap_certifies_only_the_generators_tiles_and_never_closes(
        decode_cmy_c2_crop, sim_cmy_c2_crop, shape, plant, drift):
    record = decode_cmy_c2_crop(shape, plant, drift)
    wrong = _wrong_label_bits(record, sim_cmy_c2_crop(shape, plant, drift))
    assert not any(wrong.values()), wrong
    assert {key[:3] for key in record.certificates} <= _crop_tiles(shape)
    assert record.exit_code != 0 and record.payload is None
    (done,) = [event for event in record.events
               if isinstance(event, data.RunDone)]
    assert done.status == "open"


def _field_reading(record: object, shape: tuple[int, int],
                   plant: str) -> tuple[tuple[int, int], tuple[object, ...]]:
    """The last solve on the scrap's tiles, per plane M, Y: how many tiles
    carry data, and the mean (F_p - F_C) minus the plant, x and y in dots
    at the plant's own half-dot quantum -- where the plant is within one
    printed cell of the pose (G12's promise); past it, and on a plane
    with no data, None (the ledger carries the value)."""
    solved = [event for event in record.events
              if isinstance(event, data.FieldSolved)]
    planes = {row.plane: row for row in solved[-1].planes}
    ty0, tx0 = _h3_sims_cmy.cmy_c2_crop_origin(shape)
    scrap = (slice(ty0, ty0 + shape[0]), slice(tx0, tx0 + shape[1]))
    zero = np.asarray(planes[0].delta_grid_dots_xy, np.float64)[scrap]
    cell_dots = color_sites.cell_dots_of(_row())
    counts: list[int] = []
    errors: list[object] = []
    for plane, planted in zip((1, 2),
                              _h3_sims_cmy.CMY_C2_CROP_PLANTS_DOTS[plant]):
        has = np.asarray(planes[plane].has_data, bool)[scrap]
        counts.append(int(has.sum()))
        if not has.any() or abs(planted) > cell_dots:
            errors.append(None)
            continue
        grid = np.asarray(planes[plane].delta_grid_dots_xy,
                          np.float64)[scrap]
        error = (grid - zero)[has].mean(axis=0) - (planted, 0.0)
        errors.append(tuple(float(value) + 0.0
                            for value in np.round(2.0 * error) / 2.0))
    return (counts[0], counts[1]), tuple(errors)


#: Per tested scrap: (hi, lo) certified, the field's (M, Y) tiles with
#: data, and its (M, Y) error against the plant at the half-dot quantum
#: (the ledger, A9).
CROP_OUTCOMES = {
    "cmy-c2-crop-2x3-Z-drift": ((6, 6), (6, 6), ((0.0, 0.0), (0.0, 0.0))),
    "cmy-c2-crop-2x3-A-drift": ((6, 6), (6, 6), ((0.0, 0.0), (0.0, 0.0))),
    "cmy-c2-crop-2x3-A-control": ((6, 6), (6, 6), ((0.0, 0.0), (0.5, 0.0))),
    "cmy-c2-crop-2x3-C-none": ((0, 0), (0, 2), (None, None)),
}


@pytest.mark.parametrize("shape, plant, drift", CROPS, ids=CROP_IDS)
def test_what_a_cold_scrap_certifies_and_where_its_field_reads_the_plant(
        decode_cmy_c2_crop, shape, plant, drift):
    record = decode_cmy_c2_crop(shape, plant, drift)
    counts = tuple(sum(1 for key in record.certificates if key[3] == stream)
                   for stream in ("hi", "lo"))
    name = _h3_sims_cmy.cmy_c2_crop_name(shape, plant, drift)
    _h3_support.assert_measured(
        f"{name}: (hi, lo) certified, field (M, Y) tiles and - plant",
        (counts, *_field_reading(record, shape, plant)),
        CROP_OUTCOMES[name])
