"""Family constructors (FORMAT-SPACE §5): k_codec / cmy7_codec / cmy8_codec
/ cmy_codec.

Legacy frozen numerics are accessed ONLY via the public catalog
(``holo.format.descriptor.CODINGS``) — never via underscore-private
profiles-module singletons.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from holo.core import keystream
from holo.core.ldpc.construct import LADDER
from holo.format.descriptor import CODINGS
from holo.format.families import (
    cmy7_codec,
    cmy8_codec,
    cmy_codec,
    k_codec,
    rung_token,
)
from holo.format.profiles import Family


def test_k_codec_same_object_as_catalog_and_bank_naming() -> None:
    codec = k_codec("r0700", 100)
    assert codec is CODINGS["c2-r0700"].codec
    assert codec.family is Family.K
    assert codec.streams[0].fec.profile_id == "k-r0700-p100-v1"


def test_cmy8_codec_matches_legacy_numerics_except_ids() -> None:
    """Everything but the id strings is the frozen -p120-v0 legacy."""
    legacy = CODINGS["c2-cmy8-p120-v1"].codec
    fresh = cmy8_codec(("r0550", "r0550", "r0547"))

    assert fresh.stream_ids == ("C", "M", "Y")
    assert fresh.stream_ids == legacy.stream_ids
    assert tuple(s.fountain_aux for s in fresh.streams) == (
        keystream.COLOR_STREAM_C, keystream.COLOR_STREAM_M,
        keystream.COLOR_STREAM_Y)
    assert tuple(s.fountain_aux for s in fresh.streams) == \
        tuple(s.fountain_aux for s in legacy.streams)

    assert fresh.n_sites == legacy.n_sites == 120
    assert fresh.n_dust == legacy.n_dust == 20
    assert fresh.state_names == legacy.state_names
    assert fresh.word_states == legacy.word_states
    assert fresh.dust_base_cycle == legacy.dust_base_cycle
    assert fresh.family is legacy.family is Family.CMY8


# What (rungs, sites) must produce, one row per construction the four
# separate tests used to make (folded 2026-09-20).  The id strings are
# v2-minted grammar names, not the frozen -p120-v0 legacy ones; the bank
# id rule is per-plane rung (cmy8_codec zips channel.PLANE_ORDER with the
# rungs tuple), and the uneven row is where that becomes visible.  The
# widths: user_bits = 4096 - sites - 32 - repair, symbol_bits one below
# it (the metadata bit), transmitted_bits = 4096 - sites = payload_cells.
CMY8_ROWS = (
    ("legacy-r0550x0550x0547", ("r0550", "r0550", "r0547"), 120,
     "cmy8-r0550x0550x0547-p120-v1",
     ("cmy8-C-r0550-p120-v1", "cmy8-M-r0550-p120-v1",
      "cmy8-Y-r0547-p120-v1"),
     (2088, 2088, 2088), (2087, 2087, 2087), 2087, 20, 3976),
    ("uniform-r0700", ("r0700",) * 3, 120,
     "cmy8-r0700-p120-v1",
     ("cmy8-C-r0700-p120-v1", "cmy8-M-r0700-p120-v1",
      "cmy8-Y-r0700-p120-v1"),
     (2728, 2728, 2728), (2727, 2727, 2727), 2727, 20, 3976),
    ("uniform-r0700-p140", ("r0700",) * 3, 140,
     "cmy8-r0700-p140-v1",
     ("cmy8-C-r0700-p140-v1", "cmy8-M-r0700-p140-v1",
      "cmy8-Y-r0700-p140-v1"),
     (2708, 2708, 2708), (2707, 2707, 2707), 2707, 40, 3956),
    ("uneven-r0700x0700x0547", ("r0700", "r0700", "r0547"), 120,
     "cmy8-r0700x0700x0547-p120-v1",
     ("cmy8-C-r0700-p120-v1", "cmy8-M-r0700-p120-v1",
      "cmy8-Y-r0547-p120-v1"),
     (2728, 2728, 2088), (2727, 2727, 2087), 2727, 20, 3976),
)


@pytest.mark.parametrize(
    ("rungs", "sites", "codec_id", "bank_ids", "user_bits", "symbol_bits",
     "widest", "n_dust", "payload_cells"),
    [row[1:] for row in CMY8_ROWS],
    ids=[row[0] for row in CMY8_ROWS],
)
def test_cmy8_codec_names_its_banks_and_prices_its_streams(
    rungs, sites, codec_id, bank_ids, user_bits, symbol_bits, widest,
    n_dust, payload_cells,
) -> None:
    codec = cmy8_codec(rungs, sites)

    assert codec.codec_id == codec_id
    assert tuple(s.fec.profile_id for s in codec.streams) == bank_ids
    assert tuple(s.user_bits for s in codec.streams) == user_bits
    assert tuple(s.symbol_bits for s in codec.streams) == symbol_bits
    assert codec.symbol_bits == widest            # the pool's symbol
    assert tuple(s.fec.transmitted_bits for s in codec.streams) == \
        (payload_cells,) * 3
    assert codec.n_sites == sites
    assert codec.n_dust == n_dust
    assert codec.payload_cells == payload_cells


def test_cmy8_uneven_triplet_refuses_one_common_symbol_width() -> None:
    codec = cmy8_codec(("r0700", "r0700", "r0547"))
    with pytest.raises(ValueError, match="widths differ"):
        codec.common_symbol_bits          # the v1 receiver's property


def test_cmy7_codec() -> None:
    codec = cmy7_codec()
    assert codec.codec_id == "cmy7-p120-v1"
    assert codec.family is Family.CMY7
    stream = codec.streams[0]
    assert stream.user_bits == 5974
    assert stream.symbol_bits == 5973
    children = stream.fec.children
    assert tuple(c.active_information_bits for c in children) == \
        (2240, 1883, 1883)

    with pytest.raises(ValueError):
        cmy7_codec(p=140)
    with pytest.raises(ValueError):
        cmy7_codec(gen=2)


def test_site_bounds() -> None:
    with pytest.raises(ValueError):
        k_codec("r0550", 99)

    codec = k_codec("r0550", 2200)
    assert codec.streams[0].user_bits == 2240 - 2200 - 32 == 8

    with pytest.raises(ValueError):
        k_codec("r0550", 2210)


def test_dust_law() -> None:
    codec = cmy8_codec(("r0550", "r0550", "r0547"))
    assert len(codec.dust_base_cycle) == 6
    assert k_codec("r0550").dust_base_cycle == ()


def test_rung_token() -> None:
    assert rung_token(("r0700", "r0700", "r0700")) == "r0700"
    assert rung_token(("r0550", "r0550", "r0547")) == "r0550x0550x0547"


def test_cmy8_requires_dust_sites() -> None:
    """p100 parses arithmetically but colour furniture includes dust —
    the constructor refuses (P6 review finding, FORMAT-SPACE §11.4)."""
    with pytest.raises(ValueError, match="dust"):
        cmy8_codec(("r0700", "r0700", "r0700"), 100)


def test_cmy8_bank_override_arity_is_validated() -> None:
    """The fossil-only _bank_ids override cannot truncate the pool."""
    with pytest.raises(ValueError, match="three distinct banks"):
        cmy8_codec(("r0700",) * 3, 120, _codec_id="x",
                   _bank_ids=("a", "b"))


# The cmy rows (docs/CMY-DESIGN.md §2.3, §3.1): two label-bit streams in
# (hi, lo) order, one bank per stream named by its own rung, S = k - p - 33
# fountain bits per stream (k - 153 at p120), transmitted = 4096 - p.
CMY_ROWS = (
    ("c3-first-r0850", ("r0850", "r0850"), 120, "cmy-r0850-p120-v1",
     ("cmy-hi-r0850-p120-v1", "cmy-lo-r0850-p120-v1"), (3367, 3367)),
    ("uniform-r0700", ("r0700", "r0700"), 120, "cmy-r0700-p120-v1",
     ("cmy-hi-r0700-p120-v1", "cmy-lo-r0700-p120-v1"), (2727, 2727)),
    ("probe-r0775x0700", ("r0775", "r0700"), 120, "cmy-r0775x0700-p120-v1",
     ("cmy-hi-r0775-p120-v1", "cmy-lo-r0700-p120-v1"), (3047, 2727)),
    ("minimum-r0700x0625", ("r0700", "r0625"), 120,
     "cmy-r0700x0625-p120-v1",
     ("cmy-hi-r0700-p120-v1", "cmy-lo-r0625-p120-v1"), (2727, 2407)),
    ("floor-r0550x0547", ("r0550", "r0547"), 120, "cmy-r0550x0547-p120-v1",
     ("cmy-hi-r0550-p120-v1", "cmy-lo-r0547-p120-v1"), (2087, 2087)),
    ("p101-r0700", ("r0700", "r0700"), 101, "cmy-r0700-p101-v1",
     ("cmy-hi-r0700-p101-v1", "cmy-lo-r0700-p101-v1"), (2746, 2746)),
    ("p300-r0700", ("r0700", "r0700"), 300, "cmy-r0700-p300-v1",
     ("cmy-hi-r0700-p300-v1", "cmy-lo-r0700-p300-v1"), (2547, 2547)),
)


@pytest.mark.parametrize(
    ("rungs", "sites", "codec_id", "bank_ids", "symbol_bits"),
    [row[1:] for row in CMY_ROWS],
    ids=[row[0] for row in CMY_ROWS],
)
def test_cmy_codec_names_its_label_streams_and_prices_them(
    rungs, sites, codec_id, bank_ids, symbol_bits,
) -> None:
    codec = cmy_codec(rungs, sites)

    assert codec.family is Family.CMY
    assert codec.codec_id == codec_id
    assert codec.stream_ids == ("hi", "lo")
    assert tuple(s.fec.profile_id for s in codec.streams) == bank_ids
    assert tuple(s.symbol_bits for s in codec.streams) == symbol_bits
    assert symbol_bits == tuple(LADDER[r].k_bits - sites - 33 for r in rungs)
    assert tuple(s.fountain_aux for s in codec.streams) == (None, None)
    assert tuple(s.fec.transmitted_bits for s in codec.streams) == \
        (4096 - sites,) * 2 == (codec.payload_cells,) * 2
    assert codec.symbol_bits == max(symbol_bits)
    assert (codec.n_sites, codec.n_dust) == (sites, sites - 100)
    assert codec.state_names == ("W", "C", "M", "Y")
    assert codec.state_ids == (0, 1, 2, 4)
    assert codec.word_states == (0, 1)
    assert codec.dust_base_cycle == ()
    assert (codec.evidence_values_per_cell, codec.bits_per_mapper_unit,
            codec.cells_per_mapper_unit) == (3, 2, 1)


@pytest.mark.parametrize(("rungs", "sites", "fragment"), [
    (("r0700", "r0700"), 100, "no anchor"),
    (("r0700", "r0700"), 99, "word floor"),
    (("r0700", "r0700", "r0700"), 120, "rung pair"),
    (("r0700",), 120, "rung pair"),
    (("r0700", "r0300"), 120, "unknown LDPC rung"),
])
def test_cmy_codec_refuses_p100_triplets_and_unknown_rungs(
        rungs, sites, fragment) -> None:
    with pytest.raises(ValueError, match=fragment):
        cmy_codec(rungs, sites)


def test_the_alphabet_law_derives_state_ids_per_family() -> None:
    assert k_codec("r0700").state_ids == (0, 1)
    assert cmy7_codec().state_ids == tuple(range(7))
    assert cmy8_codec(("r0700",) * 3).state_ids == tuple(range(8))
    assert cmy_codec(("r0700", "r0700")).state_ids == (0, 1, 2, 4)


@pytest.mark.parametrize(("change", "fragment"), [
    ({"state_names": ("W", "Y", "C", "M")}, "non-canonical"),
    ({"state_names": ("W", "C", "C", "Y")}, "non-canonical"),
    ({"state_names": ("W", "C", "M", "K")}, "non-canonical"),
    ({"word_states": (0, 3)}, "word states outside"),
    ({"dust_base_cycle": (2, 3)}, "dust states outside"),
])
def test_a_colour_alphabet_is_a_subsequence_checked_by_membership(
        change, fragment) -> None:
    with pytest.raises(ValueError, match=fragment):
        replace(cmy_codec(("r0700", "r0700")), **change)
