from __future__ import annotations

from holo.receiver.tests import _h3_sims, _h3_support


def _per_stream(record) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in record.certificates:
        counts[key[3]] = counts.get(key[3], 0) + 1
    return counts


# The frozen-render checks these two modules used to open with retired
# 2026-09-20: `_h3_fixture_build._materialise` verifies the same digests
# on both the cache-hit and the rebuild path, so the renders cannot be
# stale without the fixture itself raising, and the payload length the
# check also read is entailed by the payload sha below.


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


#: One name per subject, 2026-09-05: the three-page lever's recovery and
#: its per-(block, group) close ledger used to share one name.  Same
#: session decode, same assertions, two failure names.


def test_the_three_page_lever_decodes_with_source_chunks_in_its_narrow_plane(
        decode_color_groups_pages_w8, sim_color_groups_pages):
    record = decode_color_groups_pages_w8
    assert record.exit_code == 0
    assert record.status == "verified"
    assert record.payload == sim_color_groups_pages[0].payload_data
    counts = _per_stream(record)
    assert counts["C"] > 0 and counts["M"] > 0 and counts["Y"] > 0


def test_the_three_page_lever_closes_every_column_group_of_its_block(
        decode_color_groups_pages_w8):
    from holo.receiver import data

    checks = [event for event in decode_color_groups_pages_w8.events
              if isinstance(event, data.CloseCheck)]
    (block,) = checks[-1].blocks
    assert block.solved and block.short == 0 and block.groups_open == 0
    assert block.n_groups == 17 and block.needed == 237
