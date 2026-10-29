"""The plane-view FormatRow: the geometry claim, re-checked here.

The whole experiment rests on one measured fact — that holo3's K site
construction at p120 lands on the same cells as its cmy8 construction —
so these tests state it as an assertion against holo3 itself rather than
against a frozen constant.  If holo3's site construction ever moves,
`build_plane_row` refuses and these fail loudly.
"""

from __future__ import annotations

import dataclasses
from fractions import Fraction

import numpy as np
import pytest

from holo.receiver.format import identity, keystream
from holo.receiver.format.identity import Family

from analyzer.planeview import row as row_mod

H_REF = "L:c2-cmy8-r0850-p120-x1@3392x2368"
SMALL_REF = "c3-cmy8-r0550@7x7"


def test_the_plane_view_ref_round_trips():
    ref = row_mod.plane_view_ref(H_REF, "C")
    assert ref == f"PV:{H_REF}/C"
    assert row_mod.parse_plane_view_ref(ref) == (H_REF, "C")


@pytest.mark.parametrize("bad", ["L:whatever", "PV:x/Q", "PV:/C", "PV:x"])
def test_a_malformed_plane_view_ref_is_refused(bad):
    with pytest.raises(row_mod.PlaneRowError):
        row_mod.parse_plane_view_ref(bad)


def test_the_plane_row_is_family_k_with_the_source_seed():
    plane, source, report = row_mod.build_plane_row(H_REF, "C")
    assert plane.family is Family.K
    assert plane.seed == source.seed
    assert plane.sites_seed == source.sites_seed
    assert plane.pitch_in == source.pitch_in
    assert plane.tiles_yx == source.tiles_yx
    assert plane.n_sites == source.n_sites == 120
    assert plane.pooled_fountain is False
    assert len(plane.streams) == 1
    assert plane.streams[0].stream_id == "C"
    # PLANE_K, not 0: `words.addressing_plane` reads this field for a K
    # row and the printed word values are word_values(seed, c, PLANE_K)
    # on both sides.  The tile attempt takes evidence column 0 instead.
    assert plane.streams[0].plane == keystream.PLANE_K
    assert report["seed"] == source.seed.decode()
    assert report["minted_k_row_id"] != plane.row_id


def test_a_minted_k_row_would_have_carried_the_wrong_seed():
    """Why `dataclasses.replace` is not optional: the id IS the seed."""
    source = identity.resolve_format_ref(H_REF)
    minted = identity.mint_format(
        pitch=source.pitch_in, family=Family.K, rungs=("r0850",),
        sites=120, gen=1, tiles_yx=source.tiles_yx)
    assert minted.seed != source.seed
    assert minted.seed.startswith(identity.SEED_NAMESPACE)


def test_the_bank_and_the_frame_are_the_cmy8_stream_s_own():
    plane, source, report = row_mod.build_plane_row(H_REF, "C")
    cmy8_c = row_mod.source_stream_fact(source, "C")
    assert plane.streams[0].rung_children == cmy8_c.rung_children
    assert plane.streams[0].user_bits == cmy8_c.user_bits == 3368
    assert plane.payload_cells == source.payload_cells == 3976
    assert report["rung"] == "r0850"


def test_the_k_attempt_floor_equals_the_cmy8_bank_floor():
    from holo.receiver.plugins import tiles

    plane, source, _ = row_mod.build_plane_row(H_REF, "C")
    bank = row_mod.source_stream_fact(source, "C").rung_children
    assert tiles.k_eff_bits(plane) == tiles._bank_active_bits(bank) == 3400


def test_the_two_geometries_agree_everywhere_but_the_dust_row_order():
    plane, source, report = row_mod.build_plane_row(H_REF, "C")
    mine = identity.build_site_geometry(plane)
    theirs = identity.build_site_geometry(source)
    for name in ("word_cells_yx", "shorten_flat", "payload_flat",
                 "slot_a", "slot_b"):
        assert np.array_equal(getattr(mine, name), getattr(theirs, name)), name
    assert report["extra_cells_same_set"] is True
    # The one difference, and the reason `patches` overrides
    # `build_site_geometry`: `calibrate.build_site_lookup`'s index has to
    # agree with `pilots.dust_state_values`' order.
    assert report["extra_cells_same_order"] is False
    assert (set(map(tuple, mine.extra_cells_yx.tolist()))
            == set(map(tuple, theirs.extra_cells_yx.tolist())))


@pytest.mark.parametrize("ref", [H_REF, SMALL_REF])
@pytest.mark.parametrize("stream_id", ["C", "M"])
def test_every_stream_of_every_cmy8_row_frames(ref, stream_id):
    plane, source, report = row_mod.build_plane_row(ref, stream_id)
    assert plane.streams[0].stream_id == stream_id
    assert report["plane_index"] == row_mod.PLANE_OF[stream_id]
    assert plane.seed == source.seed


@pytest.mark.parametrize("ref", [H_REF, SMALL_REF])
def test_the_y_plane_view_is_refused(ref):
    """Word states are 0 or 3: Y is blank at every word site."""
    with pytest.raises(row_mod.PlaneRowError, match="C and M only"):
        row_mod.build_plane_row(ref, "Y")


def test_a_k_source_is_refused():
    with pytest.raises(row_mod.PlaneRowError):
        row_mod.build_plane_row("c3-k-r0550@7x7", "C")


def test_an_unknown_stream_is_refused():
    with pytest.raises(row_mod.PlaneRowError):
        row_mod.build_plane_row(H_REF, "K")


def test_the_geometry_guard_fires_when_the_sites_disagree():
    """A hand-forged row with the wrong site seed must be refused."""
    plane, source, _ = row_mod.build_plane_row(H_REF, "C")
    other = identity.mint_format(
        pitch=Fraction(1, 300), family=Family.CMY8,
        rungs=("r0850", "r0850", "r0850"), sites=110, gen=1,
        tiles_yx=source.tiles_yx)
    with pytest.raises(row_mod.PlaneRowError):
        row_mod._assert_geometry_agrees(dataclasses.replace(plane), other)
