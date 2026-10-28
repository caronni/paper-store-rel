from __future__ import annotations

import json
from unittest import mock

import numpy as np
import pytest

from holo3 import data
from holo3.format import identity, metadata, pilots, tile_codec
from holo3.plugins import color_region, tiles
from holo3.tests import _h3_sims, _h3_support
from holo3.tests import conftest as h3_conftest

TILE = 64

K_SERIAL_CERTIFICATES = 48
K_TILE_DOMAIN = 49
K_METADATA_RANK = 24
K_METADATA_EQUATIONS = 48
K_SOURCE_SYMBOLS = 23
K_WORD_SITES_PER_PAGE = 4900

COLOR_SOURCE_SYMBOLS = 78
COLOR_SERIAL_CERTIFICATES = 81
COLOR_METADATA_RANK = 24
COLOR_WORD_SITES = 100
COLOR_DUST_SITES = 20
COLOR_PAYLOAD_CELLS = 3976
COLOR_PLANES = 3
COLOR_TILE_DOMAIN = 100

GT_BAND_LOW = 60.0
GT_BAND_HIGH = 220.0
GT_INK_BELOW = 140.0

RUN_DIR_PRODUCTS = ("argv", "events.jsonl", "pane-capture-0.png",
                    "pane-page-0.png", "pane-payload-0.png",
                    "pane-pose-0.png", "report.json", "tree")


def row_and_geometry(capture: _h3_sims.SimCapture):
    row = identity.resolve_format_ref(capture.format_ref)
    return row, identity.build_site_geometry(row)


def k_page_cells(capture: _h3_sims.SimCapture) -> np.ndarray:
    import tifffile

    row = identity.resolve_format_ref(capture.format_ref)
    image = np.asarray(tifffile.imread(capture.tiff), dtype=np.float32)
    cell_px = int(row.pitch_in * capture.dpi)
    border_px = _h3_sims.K_BORDER_DOTS * _h3_sims.UPSAMPLE
    cells_y = row.tiles_yx[0] * TILE
    cells_x = row.tiles_yx[1] * TILE
    crop = image[border_px:border_px + cells_y * cell_px,
                 border_px:border_px + cells_x * cell_px]
    blocks = crop.reshape(cells_y, cell_px, cells_x, cell_px)
    half = cell_px // 2
    centre = blocks[:, half - 1:half + 1, :, half - 1:half + 1]
    return centre.mean(axis=(1, 3))


def colour_page_bits(capture: _h3_sims.SimCapture) -> np.ndarray:
    row = identity.resolve_format_ref(capture.format_ref)
    planes = np.unpackbits(_h3_sims.load_emit_gt(capture), axis=-1)
    cells_y = row.tiles_yx[0] * TILE
    cells_x = row.tiles_yx[1] * TILE
    step = planes.shape[1] // cells_y
    off = step // 2
    cells = planes[:, off::step, off::step][:, :cells_y, :cells_x]
    return np.ascontiguousarray(np.moveaxis(cells, 0, -1))


def shifted_lookup(field: np.ndarray, ys: np.ndarray, xs: np.ndarray,
                   shift: int) -> tuple[np.ndarray, np.ndarray]:
    inside = ((ys + shift < field.shape[0]) & (xs + shift < field.shape[1]))
    return field[ys[inside] + shift, xs[inside] + shift], inside


def k_word_site_agreement(row, geometry, page_cells: np.ndarray,
                          shift: int) -> tuple[int, int]:
    total = 0
    agree = 0
    for ty in range(row.tiles_yx[0]):
        for tx in range(row.tiles_yx[1]):
            counter = row.tile_counter(0, ty, tx)
            word = pilots.word_values(row.seed, counter,
                                      row.streams[0].plane)[0]
            ys = geometry.word_cells_yx[:, 0] + ty * TILE
            xs = geometry.word_cells_yx[:, 1] + tx * TILE
            read, inside = shifted_lookup(page_cells, ys, xs, shift)
            total += int(read.size)
            agree += int(np.count_nonzero(read == word[inside]))
    return total, agree


def colour_furniture_agreement(row, geometry, page_bits: np.ndarray,
                               shift: int) -> tuple[int, int]:
    total = 0
    agree = 0
    for ty in range(row.tiles_yx[0]):
        for tx in range(row.tiles_yx[1]):
            counter = row.tile_counter(0, ty, tx)
            states = np.concatenate((
                pilots.color_word_states(row.seed, (counter,))[0],
                pilots.dust_state_values(row.seed, (counter,),
                                         row.dust_base_cycle, row.n_dust)[0]))
            cells = np.concatenate((geometry.word_cells_yx,
                                    geometry.extra_cells_yx))
            expected = tile_codec.states_to_planes(states)
            ys = cells[:, 0] + ty * TILE
            xs = cells[:, 1] + tx * TILE
            read, inside = shifted_lookup(page_bits, ys, xs, shift)
            total += int(read.shape[0])
            agree += int(np.count_nonzero(
                np.all(read == expected[inside], axis=-1)))
    return total, agree


def audit_k_certificates(record, capture,
                         page_cells: np.ndarray) -> _h3_support.Checks:
    row, geometry = row_and_geometry(capture)
    checks = _h3_support.Checks(
        f"{record.label}: certified K tiles re-projected onto the page")
    for key in sorted(record.certificates):
        page, ty, tx, _stream_id = key
        field = tiles.printed_cells_for(
            row, geometry, page, ty, tx, record.certificates[key].user_bits)
        printed = page_cells[ty * TILE:(ty + 1) * TILE,
                             tx * TILE:(tx + 1) * TILE]
        checks.check(f"tile {key}", bool(np.array_equal(field, printed)),
                     f"{int(np.count_nonzero(field != printed))} of "
                     f"{field.size} cells differ from the printed page")
    return checks


def audit_colour_certificates(record, capture, page_bits: np.ndarray
                              ) -> tuple[_h3_support.Checks, int, int]:
    row, geometry = row_and_geometry(capture)
    checks = _h3_support.Checks(
        f"{record.label}: certified colour tiles re-projected onto the page")
    addresses = sorted({key[:3] for key in record.certificates})
    known_total = 0
    for page, ty, tx in addresses:
        projection = color_region.certified_projection(
            row, geometry, page, ty, tx, record.certificates)
        assert projection is not None
        bits, known = projection
        printed = page_bits[ty * TILE:(ty + 1) * TILE,
                            tx * TILE:(tx + 1) * TILE]
        wrong = int(np.count_nonzero((bits != printed) & known))
        n_streams = sum(
            1 for stream in row.streams
            if (page, ty, tx, stream.stream_id) in record.certificates)
        expected_known = (
            COLOR_PLANES * (COLOR_WORD_SITES + COLOR_DUST_SITES)
            + row.payload_cells * n_streams)
        checks.check(f"tile ({page},{ty},{tx}) zero wrong", wrong == 0,
                     f"{wrong} known component bits disagree with the page")
        checks.equal(f"tile ({page},{ty},{tx}) known component bits",
                     int(np.count_nonzero(known)), expected_known)
        known_total += int(np.count_nonzero(known))
    return checks, known_total, len(addresses)


def close_checks(record) -> tuple[data.CloseCheck, ...]:
    return tuple(event for event in record.events
                 if isinstance(event, data.CloseCheck))


def test_k_sim_artefacts_reproduce_their_frozen_shas(sim_k):
    _h3_support.assert_golden("sim-k tiff sha256",
                              _h3_sims.sha256_file(sim_k.tiff),
                              _h3_sims.K_TIFF_SHA256)
    _h3_support.assert_golden("sim-k payload sha256",
                              _h3_sims.sha256_file(sim_k.payload),
                              _h3_sims.K_PAYLOAD_SHA256)
    assert len(sim_k.payload_data) == _h3_sims.K_PAYLOAD_BYTES == 6000


def test_colour_sim_artefacts_reproduce_their_frozen_shas(sim_color):
    _h3_support.assert_golden("sim-color tiff sha256",
                              _h3_sims.sha256_file(sim_color.tiff),
                              _h3_sims.COLOR_TIFF_SHA256)
    _h3_support.assert_golden("sim-color payload sha256",
                              _h3_sims.sha256_file(sim_color.payload),
                              _h3_sims.COLOR_PAYLOAD_SHA256)
    _h3_support.assert_golden(
        "sim-color emit ground truth sha256",
        _h3_sims.sha256_file(sim_color.emit_dir / "page000_gt.npy"),
        _h3_sims.COLOR_GT_SHA256)
    assert len(sim_color.payload_data) == _h3_sims.COLOR_PAYLOAD_BYTES == 20000


def test_k_sim_decode_is_verified_and_byte_exact(decode_k_w8, sim_k):
    assert decode_k_w8.exit_code == 0
    assert decode_k_w8.status == "verified"
    assert decode_k_w8.out_exists
    assert decode_k_w8.payload == sim_k.payload_data
    _h3_support.assert_golden("recovered K payload sha256",
                              decode_k_w8.payload_sha256,
                              _h3_sims.K_PAYLOAD_SHA256)
    assert len(decode_k_w8.payload) == 6000
    assert "VERIFIED 6000 bytes" in decode_k_w8.stdout


def test_k_sim_serial_close_pins_the_metadata_floor(decode_k_w1):
    final = close_checks(decode_k_w1)[-1]
    assert final.status == "verified"
    assert decode_k_w1.certified == K_SERIAL_CERTIFICATES
    assert final.certified == K_SERIAL_CERTIFICATES
    assert final.symbols_used == K_SERIAL_CERTIFICATES
    assert final.k_total == K_SOURCE_SYMBOLS
    assert final.metadata_rank == K_METADATA_RANK == metadata.METADATA_BITS
    assert (final.metadata_n_unique == K_METADATA_EQUATIONS
            == metadata.MIN_METADATA_EQUATIONS)
    assert K_SERIAL_CERTIFICATES < K_TILE_DOMAIN


def test_k_sim_serial_certificate_addresses_lie_in_the_page_domain(
        decode_k_w1, sim_k):
    row = identity.resolve_format_ref(sim_k.format_ref)
    assert row.tiles_yx == (7, 7)
    for page, ty, tx, stream_id in decode_k_w1.certificates:
        assert page == 0
        assert 0 <= ty < row.tiles_yx[0]
        assert 0 <= tx < row.tiles_yx[1]
        assert stream_id == "main"
    assert len(set(decode_k_w1.certificates)) == K_SERIAL_CERTIFICATES


@pytest.mark.parametrize("shift, agrees", [(0, True), (1, False)])
def test_k_page_cells_are_anchored_to_the_printed_word_sites(
        sim_k, shift, agrees):
    row, geometry = row_and_geometry(sim_k)
    centre = k_page_cells(sim_k)
    assert not np.any((centre > GT_BAND_LOW) & (centre < GT_BAND_HIGH))
    page_cells = (centre < GT_INK_BELOW).astype(np.uint8)
    total, agree = k_word_site_agreement(row, geometry, page_cells, shift)
    assert total > 0
    if agrees:
        assert total == K_WORD_SITES_PER_PAGE
        assert agree == total
    else:
        assert agree < total


def test_k_sim_mints_zero_wrong_certificates(decode_k_w1, sim_k):
    page_cells = (k_page_cells(sim_k) < GT_INK_BELOW).astype(np.uint8)
    checks = audit_k_certificates(decode_k_w1, sim_k, page_cells)
    assert checks.n_total == K_SERIAL_CERTIFICATES
    checks.assert_clean()


def test_colour_sim_decode_is_verified_and_byte_exact(decode_color_w8,
                                                      sim_color):
    assert decode_color_w8.exit_code == 0
    assert decode_color_w8.status == "verified"
    assert decode_color_w8.out_exists
    assert decode_color_w8.payload == sim_color.payload_data
    _h3_support.assert_golden("recovered colour payload sha256",
                              decode_color_w8.payload_sha256,
                              _h3_sims.COLOR_PAYLOAD_SHA256)
    assert len(decode_color_w8.payload) == 20000
    assert "VERIFIED 20000 bytes" in decode_color_w8.stdout


def test_colour_sim_close_pins_the_exact_source_symbol_count(
        decode_color_w8):
    final = close_checks(decode_color_w8)[-1]
    assert final.status == "verified"
    assert final.k_total == COLOR_SOURCE_SYMBOLS
    assert final.metadata_rank == COLOR_METADATA_RANK == metadata.METADATA_BITS
    assert final.certified == decode_color_w8.certified
    assert final.symbols_used == decode_color_w8.certified
    assert decode_color_w8.certified >= COLOR_SOURCE_SYMBOLS
    assert decode_color_w8.certified <= COLOR_TILE_DOMAIN * 3


def test_a_reused_decode_label_is_a_loud_harness_error(tmp_path):
    """The colour-lane 'regression' of 2026-08-31 was a silent label
    reuse: two decodes sharing one label hit the CLI overwrite guard
    100 seconds in.  The registry refuses the second claim before any
    decode starts."""
    h3_conftest._claim_decode_label("claimed-once", tmp_path)
    with pytest.raises(RuntimeError, match="duplicate decode label"):
        h3_conftest._claim_decode_label("claimed-once", tmp_path)
    h3_conftest._claim_decode_label("claimed-once", tmp_path / "elsewhere")


def test_colour_sim_serial_close_solves_at_the_source_symbol_rank(
        sim_color, decode_root):
    _h3_support.skip_unless_oracle_sweeps(
        "the colour serial decode (~33 s, the only order-free source of "
        "an exact colour certificate count)")
    # Its own label: the conftest fixture decodes the same sim under
    # "color-w1" WITH --complete in the same session decode_root, and
    # the CLI's overwrite guard refuses the second run of a shared name.
    record = h3_conftest._decode_once("color-w1-close", sim_color,
                                      decode_root, workers=1)
    assert record.exit_code == 0
    assert record.payload_sha256 == _h3_sims.COLOR_PAYLOAD_SHA256
    assert record.certified == COLOR_SERIAL_CERTIFICATES
    final = close_checks(record)[-1]
    assert final.k_total == COLOR_SOURCE_SYMBOLS
    assert final.symbols_used == record.certified
    assert final.blocks[0].rank == COLOR_SOURCE_SYMBOLS
    _h3_support.assert_golden("colour serial job counts (churn tripwire)",
                              _serial_jobs(record), COLOR_SERIAL_JOB_COUNTS)


def _serial_jobs(record: object) -> dict[str, int]:
    return {row["plugin"]: row["jobs"]
            for row in record.report["scheduler"]["plugins"]
            if row["jobs"]}


# calibrate 45 -> 29 (2026-08-30, the done-geometry gate): a window
# whose whole tile reach is certified in every stream no longer re-fits
# when the region pitch or its pose wakes it — same 49 certificates,
# same payload, every other row job for job.
#
# RE-PINNED 2026-09-03 for the b8471fc re-key: ctx 9 -> 10, place 61 ->
# 55, tiles.retry 18 -> 25, tiles.scan 88 -> 99; calibrate and survey
# unchanged.  A re-key, not churn — place.py, words.py and pilots.py
# differ only by the family_seed -> sites_seed rename across the merge
# and no scheduling file moved; this serial run still reaches
# K_SERIAL_CERTIFICATES (48), the exhaustive run in test_h3_e2e_modes
# still certifies 49/49 with zero wrong, and the payload is byte-exact.
# Nothing else in the suite pins churn in that window.
K_SERIAL_JOB_COUNTS = {"calibrate": 29, "ctx": 10, "place": 55,
                       "survey": 1, "tiles.retry": 25, "tiles.scan": 99}
# RE-PINNED 2026-09-03 with COLOR_SERIAL_CERTIFICATES 80 -> 81: one more
# certificate for strictly less work (color 6->4, place 34->27, retry
# 38->19, scan 69->50); the close still solves at rank 78, payload
# byte-exact.  Behind HOLO3_RUN_ORACLE_SWEEPS, so the fork's own check
# never reached it.
COLOR_SERIAL_JOB_COUNTS = {"color": 4, "place": 27, "survey": 1,
                           "tiles.retry": 19, "tiles.scan": 50}

# How far into PLACEMENT a run is when half its certificates have
# landed. Measured on this harness at workers 1 under --complete: the K
# sim reaches its median at 27.4% of its place jobs, climbing steadily
# (25% of certificates at 16.1%, everything by 53.2%). The colour sim
# reached its own at 95.2% before the 2026-08-30 assembly repricing,
# and the hard colour sim at 100.0% — every colour certificate waited
# for placement to be all but exhausted, because a newly placed
# window's FIRST colour evidence was priced as a head re-fit and queued
# behind cold placement. The bar is the K figure with headroom, not a
# threshold picked to pass: a colour lane in the same regime as the K
# lane clears it by a wide margin (10.6% measured after the fix), and a
# lane that starves again lands near 100.
CERTIFICATE_MEDIAN_PLACEMENT_BAR_PCT = 50.0


def certificate_median_placement_pct(events: tuple) -> float:
    jobs = [event for event in events if isinstance(event, data.JobDone)]
    n_place = sum(1 for job in jobs if job.plugin == "place")
    total = sum(job.n_certificates for job in jobs)
    assert total > 0 and n_place > 0
    seen_place = 0
    seen_certs = 0
    for job in jobs:
        if job.plugin == "place":
            seen_place += 1
        seen_certs += job.n_certificates
        if seen_certs * 2 >= total:
            return 100.0 * seen_place / n_place
    return 100.0


def test_colour_payload_work_does_not_wait_for_placement_to_be_exhausted(
        decode_color_w1):
    _h3_support.skip_unless_oracle_sweeps(
        "the colour serial full-domain decode (~2 min, the only "
        "order-free measurement of when colour certificates land)")
    record = decode_color_w1
    assert record.exit_code == 0
    assert record.payload_sha256 == _h3_sims.COLOR_PAYLOAD_SHA256
    median = certificate_median_placement_pct(record.events)
    assert median <= CERTIFICATE_MEDIAN_PLACEMENT_BAR_PCT, (
        f"half the colour certificates landed only after {median:.1f}% of "
        f"this run's placement: colour payload work is queued behind cold "
        f"placement again. A never-assembled window's first colour "
        f"evidence must price as assembly, not as a head re-fit")


def test_k_serial_job_counts_are_the_churn_tripwire(decode_k_w1):
    _h3_support.assert_golden("K serial job counts (churn tripwire)",
                              _serial_jobs(decode_k_w1),
                              K_SERIAL_JOB_COUNTS)


@pytest.mark.parametrize("shift, agrees", [(0, True), (1, False)])
def test_colour_page_bits_are_anchored_to_the_printed_furniture(
        sim_color, shift, agrees):
    row, geometry = row_and_geometry(sim_color)
    page_bits = colour_page_bits(sim_color)
    assert page_bits.shape == (row.tiles_yx[0] * TILE,
                               row.tiles_yx[1] * TILE, COLOR_PLANES)
    total, agree = colour_furniture_agreement(row, geometry, page_bits, shift)
    assert total > 0
    if agrees:
        assert total == COLOR_TILE_DOMAIN * (COLOR_WORD_SITES
                                             + COLOR_DUST_SITES)
        assert agree == total
    else:
        assert agree < total


def test_colour_sim_mints_zero_wrong_certificates(decode_color_w8,
                                                  sim_color):
    page_bits = colour_page_bits(sim_color)
    checks, known_total, n_addresses = audit_colour_certificates(
        decode_color_w8, sim_color, page_bits)
    checks.assert_clean()
    assert n_addresses > 0
    assert n_addresses * COLOR_PLANES >= decode_color_w8.certified
    assert known_total == (
        n_addresses * COLOR_PLANES * (COLOR_WORD_SITES + COLOR_DUST_SITES)
        + decode_color_w8.certified * COLOR_PAYLOAD_CELLS)


def test_colour_tile_cell_budget_partitions_the_tile(sim_color):
    row, geometry = row_and_geometry(sim_color)
    assert row.n_sites == COLOR_WORD_SITES + COLOR_DUST_SITES
    assert row.n_dust == COLOR_DUST_SITES
    assert geometry.word_cells_yx.shape == (COLOR_WORD_SITES, 2)
    assert geometry.extra_cells_yx.shape == (COLOR_DUST_SITES, 2)
    assert row.payload_cells == COLOR_PAYLOAD_CELLS
    assert (COLOR_WORD_SITES + COLOR_DUST_SITES + COLOR_PAYLOAD_CELLS
            == TILE * TILE)
    occupied = np.concatenate((
        geometry.word_cells_yx[:, 0] * TILE + geometry.word_cells_yx[:, 1],
        geometry.extra_cells_yx[:, 0] * TILE + geometry.extra_cells_yx[:, 1],
        np.asarray(geometry.payload_flat, np.int64)))
    assert np.array_equal(np.sort(occupied), np.arange(TILE * TILE))


def test_run_dir_carries_the_declared_products(decode_k_w8, sim_k):
    for name in RUN_DIR_PRODUCTS:
        assert (decode_k_w8.run_dir / name).is_file(), name
    argv = (decode_k_w8.run_dir / "argv").read_text()
    assert argv.endswith("\n")
    jsonl = (decode_k_w8.run_dir / "events.jsonl").read_text()
    lines = [json.loads(line) for line in jsonl.splitlines()]
    assert lines[0]["type"] == "RunOpen"
    assert lines[-1]["type"] == "RunDone"
    assert len(lines) == len(decode_k_w8.events)
    assert (decode_k_w8.run_dir / "pane-page-0.png").read_bytes()[:8] == (
        b"\x89PNG\r\n\x1a\n")


def test_report_json_is_the_structured_witness_of_the_cli_line(decode_k_w8,
                                                               sim_k):
    report = decode_k_w8.report
    assert report["run_done"]["status"] == "verified"
    assert report["run_done"]["n_bytes"] == 6000
    assert report["run_done"]["payload_sha256"] == _h3_sims.K_PAYLOAD_SHA256
    assert report["run_done"]["payload_sha256"] in decode_k_w8.stdout
    assert report["fold_errors"] == 0
    assert [capture["capture"] for capture in report["capture_facts"]] == [
        _h3_sims.K_TIFF_SHA256]
    assert report["capture_facts"][0]["dpi"] == 1200.0
    assert report["capture_facts"][0]["shape_yx"] == [3072, 3072]
    assert report["close"]["status"] == "verified"
    assert report["close"]["k_total"] == K_SOURCE_SYMBOLS


def test_diag_failure_cannot_change_the_run_outcome(sim_k, decode_root,
                                                    decode_k_w8):
    from holo3.diag import model

    def broken_fold(*args: object, **kwargs: object) -> object:
        raise RuntimeError("diag deliberately broken for C-11")

    with mock.patch.object(model, "fold", broken_fold):
        record = h3_conftest._decode_once("k-diag-broken", sim_k, decode_root,
                                          workers=8)
    assert record.report == {}
    assert not (record.run_dir / "report.json").is_file()
    assert not (record.run_dir / "events.jsonl").is_file()
    assert (record.run_dir / "argv").is_file()
    assert record.exit_code == decode_k_w8.exit_code == 0
    assert record.status == decode_k_w8.status == "verified"
    assert record.payload == decode_k_w8.payload
    assert record.payload_sha256 == _h3_sims.K_PAYLOAD_SHA256
    assert record.certified >= K_SERIAL_CERTIFICATES
