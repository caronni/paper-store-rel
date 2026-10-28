"""Family constructors (FORMAT-SPACE §5): k_codec / cmy7_codec / cmy8_codec.

Legacy frozen numerics are accessed ONLY via the public catalog
(``holo.format.descriptor.CODINGS``) — never via underscore-private
profiles-module singletons.
"""
from __future__ import annotations

import pytest

from holo.core import keystream
from holo.format.descriptor import CODINGS
from holo.format.families import cmy7_codec, cmy8_codec, k_codec, rung_token
from holo.format.profiles import Family


def test_k_codec_same_object_as_catalog_and_bank_naming() -> None:
    codec = k_codec("r0700", 100)
    assert codec is CODINGS["c2-r0700"].codec
    assert codec.family is Family.K
    assert codec.streams[0].fec.profile_id == "k-r0700-p100-v1"


def test_cmy8_codec_matches_legacy_numerics_except_ids() -> None:
    legacy = CODINGS["c2-cmy8-p120-v1"].codec
    fresh = cmy8_codec(("r0550", "r0550", "r0547"))

    assert fresh.stream_ids == ("C", "M", "Y")
    assert fresh.stream_ids == legacy.stream_ids
    for stream in fresh.streams:
        assert stream.user_bits == 2088
        assert stream.symbol_bits == 2087
        assert stream.fec.transmitted_bits == 3976
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

    # Id strings differ: v2-minted grammar names, not the frozen -p120-v0
    # legacy names.  The bank id rule is per-plane rung (verified against
    # the code: cmy8_codec zips channel.PLANE_ORDER with the rungs tuple
    # to build each bank id) — pinning what it actually produces.
    assert fresh.codec_id == "cmy8-r0550x0550x0547-p120-v1"
    bank_ids = tuple(stream.fec.profile_id for stream in fresh.streams)
    assert bank_ids == (
        "cmy8-C-r0550-p120-v1",
        "cmy8-M-r0550-p120-v1",
        "cmy8-Y-r0547-p120-v1",
    )


def test_cmy8_codec_uniform_rung_contraction() -> None:
    codec = cmy8_codec(("r0700",) * 3)
    assert codec.codec_id == "cmy8-r0700-p120-v1"
    for stream in codec.streams:
        assert stream.user_bits == 2880 - 120 - 32 == 2728
        assert stream.symbol_bits == 2727
        assert stream.fec.transmitted_bits == 3976


def test_cmy8_codec_nondefault_sites() -> None:
    codec = cmy8_codec(("r0700",) * 3, 140)
    assert codec.n_sites == 140
    assert codec.n_dust == 40
    for stream in codec.streams:
        assert stream.fec.transmitted_bits == 4096 - 140 == 3956
    assert codec.payload_cells == 3956


def test_cmy8_codec_uneven_triplet_names_its_banks_and_widest_symbol() -> None:
    codec = cmy8_codec(("r0700", "r0700", "r0547"))
    assert codec.codec_id == "cmy8-r0700x0700x0547-p120-v1"
    assert tuple(s.fec.profile_id for s in codec.streams) == (
        "cmy8-C-r0700-p120-v1", "cmy8-M-r0700-p120-v1",
        "cmy8-Y-r0547-p120-v1")
    assert tuple(s.symbol_bits for s in codec.streams) == (2727, 2727, 2087)
    assert codec.symbol_bits == 2727
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
