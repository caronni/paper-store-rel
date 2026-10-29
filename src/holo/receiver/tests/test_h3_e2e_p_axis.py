"""Two volumes at a furniture density that is not the printed one.

`p` is the number of cells a tile spends on furniture: 100 indexed word
sites plus `p - 100` known-content cells.  Every colour identity the
record has ever printed is p120, and both derivations of that furniture
— the receiver's `words._site_cells` and the writer's `_color_geometry`
— hardcoded the 20 dust that follows from it, beside an
`identity.build_site_geometry` that had always taken the count from the
row.  The unit pins for that repair live in
test_h3_plugins_placement.py (the receiver's mask),
tests/holo/test_color_compose.py (the writer's partition) and
tests/holo/test_lattice_gen.py (capacity and generate agreeing).  This
module is the whole-volume statement the unit pins cannot make: emit at
p300, render, decode blind, close.

The K volume is here for a different reason.  K reached lawful `p` on
its own — its filler count always came from the row — but no K row off
p100 had ever been DECODED, in sim or on paper, and K is the axis's
only print candidate.  It is the control as much as the coverage: if
the colour volume ever fails at p300 in a way K does not, the fault is
in the colour furniture and not in `p`.

ZERO WRONG CERTIFICATES, here, means what it means for the column-group
e2e beside it: the close is VERIFIED — the recovered envelope's sha256
is the one the emitter wrote — and the recovered bytes are the emitted
bytes.  A wrong certificate reaches the fountain as a corrupt symbol and
takes the envelope sha with it.

Both stimuli are sized off their one-page cliff.  That sizing is a claim
about the src/holo planner, so it is pinned where the planner lives, in
tests/holo/test_lattice_gen.py: this module imports nothing outside the
receiver tree (the import firewall, test_h3_hygiene.py).
"""
from __future__ import annotations

from holo.receiver.format import identity
from holo.receiver.tests import _h3_sims_p_axis, _h3_support


def _per_stream(record) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in record.certificates:
        counts[key[3]] = counts.get(key[3], 0) + 1
    return counts


# The frozen-render check this module opened with retired 2026-09-20:
# `_h3_fixture_build._materialise` verifies the same digests on both the
# cache-hit and the rebuild path.  Its two payload lengths moved into the
# site-count test below, where the volumes' sizing belongs.


def test_the_p300_rows_spend_their_tiles_on_three_hundred_sites(sim_p_axis,
                                                                sim_p_axis_k):
    """The stimuli really are off the p120 lineage, and by how much.

    Without this the decodes below could pass on rows that quietly
    resolved to the printed density — the exact failure mode the
    repaired derivations had, which is that a `p` is declared and a
    different one is used.
    """
    assert len(sim_p_axis.payload_data) == 12000
    assert len(sim_p_axis_k.payload_data) == 4000
    for capture, n_dust in ((sim_p_axis, 200), (sim_p_axis_k, 0)):
        row = identity.resolve_format_ref(capture.format_ref)
        geometry = identity.build_site_geometry(row)
        assert row.n_sites == 300 and row.n_dust == n_dust
        assert geometry.word_cells_yx.shape == (100, 2)
        assert geometry.extra_cells_yx.shape == (200, 2)
        assert row.payload_cells == geometry.payload_flat.size == 3796
        assert row.n_sites + row.payload_cells == 64 * 64


def test_the_p300_colour_volume_decodes_verified_and_byte_exact(
        decode_p_axis_w8, sim_p_axis):
    record = decode_p_axis_w8
    assert record.exit_code == 0
    assert record.status == "verified"
    assert record.payload == sim_p_axis.payload_data
    _h3_support.assert_golden("p300 recovered payload sha256",
                              record.payload_sha256,
                              _h3_sims_p_axis.P_AXIS_PAYLOAD_SHA256)
    counts = _per_stream(record)
    assert counts["C"] > 0 and counts["M"] > 0 and counts["Y"] > 0


def test_the_p300_k_volume_decodes_verified_and_byte_exact(decode_p_axis_k_w8,
                                                           sim_p_axis_k):
    record = decode_p_axis_k_w8
    assert record.exit_code == 0
    assert record.status == "verified"
    assert record.payload == sim_p_axis_k.payload_data
    _h3_support.assert_golden("p300 K recovered payload sha256",
                              record.payload_sha256,
                              _h3_sims_p_axis.P_AXIS_K_PAYLOAD_SHA256)
    assert set(_per_stream(record)) == {"main"}
