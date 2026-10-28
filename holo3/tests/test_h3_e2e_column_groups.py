from __future__ import annotations

from holo3.tests import _h3_sims, _h3_support


def _per_stream(record) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in record.certificates:
        counts[key[3]] = counts.get(key[3], 0) + 1
    return counts


def test_column_group_sim_artefacts_reproduce_their_frozen_shas(
        sim_color_groups, sim_color_groups_dead_y):
    _h3_support.assert_golden(
        "sim-color-groups tiff sha256",
        _h3_sims.sha256_file(sim_color_groups.tiff),
        _h3_sims.GROUPS_TIFF_SHA256)
    _h3_support.assert_golden(
        "sim-color-groups dead-Y tiff sha256",
        _h3_sims.sha256_file(sim_color_groups_dead_y.tiff),
        _h3_sims.GROUPS_DEAD_Y_TIFF_SHA256)
    _h3_support.assert_golden(
        "sim-color-groups payload sha256",
        _h3_sims.sha256_file(sim_color_groups.payload),
        _h3_sims.GROUPS_PAYLOAD_SHA256)
    _h3_support.assert_golden(
        "sim-color-groups emit ground truth sha256",
        _h3_sims.sha256_file(sim_color_groups.emit_dir / "page000_gt.npy"),
        _h3_sims.GROUPS_GT_SHA256)
    assert len(sim_color_groups.payload_data) == 20000


def test_the_uneven_row_decodes_verified_and_byte_exact(
        decode_color_groups_w8, sim_color_groups):
    record = decode_color_groups_w8
    assert record.exit_code == 0
    assert record.status == "verified"
    assert record.payload == sim_color_groups.payload_data
    _h3_support.assert_golden("column-group recovered payload sha256",
                              record.payload_sha256,
                              _h3_sims.GROUPS_PAYLOAD_SHA256)
    counts = _per_stream(record)
    assert counts["C"] > 0 and counts["M"] > 0 and counts["Y"] > 0


def test_the_uneven_row_closes_with_its_narrow_plane_dead(
        decode_color_groups_dead_y_w8, sim_color_groups_dead_y):
    record = decode_color_groups_dead_y_w8
    assert record.exit_code == 0
    assert record.status == "verified"
    assert record.payload == sim_color_groups_dead_y.payload_data
    counts = _per_stream(record)
    assert counts.get("Y", 0) == 0
    assert counts["C"] > 0 and counts["M"] > 0


def test_three_page_sim_artefacts_reproduce_their_frozen_shas(
        sim_color_groups_pages):
    for capture, expected in zip(sim_color_groups_pages,
                                 _h3_sims.PAGES_TIFF_SHA256):
        _h3_support.assert_golden(f"{capture.name} tiff sha256",
                                  _h3_sims.sha256_file(capture.tiff),
                                  expected)
    _h3_support.assert_golden(
        "sim-color-groups-pages payload sha256",
        _h3_sims.sha256_file(sim_color_groups_pages[0].payload),
        _h3_sims.PAGES_PAYLOAD_SHA256)


def test_the_three_page_lever_decodes_with_source_chunks_in_its_narrow_plane(
        decode_color_groups_pages_w8, sim_color_groups_pages):
    from holo3 import data

    record = decode_color_groups_pages_w8
    assert record.exit_code == 0
    assert record.status == "verified"
    assert record.payload == sim_color_groups_pages[0].payload_data
    counts = _per_stream(record)
    assert counts["C"] > 0 and counts["M"] > 0 and counts["Y"] > 0
    checks = [event for event in record.events
              if isinstance(event, data.CloseCheck)]
    (block,) = checks[-1].blocks
    assert block.solved and block.short == 0 and block.groups_open == 0
    assert block.n_groups == 17 and block.needed == 237
