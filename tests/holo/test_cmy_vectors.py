"""Spec vectors for the cmy family, typed from docs/CMY-DESIGN.md v0.3
before the build (docs/CMY-GENERATOR-PLAN.md W0; design §11, G11).

Every expected value is a LITERAL, computed once from the design text over
the frozen reference machinery — the BCH word and its domain-2 scramble as
``pilots.word_values`` renders them for cmy8, domain 9 through
``core.keystream_spec``'s stdlib ``block``/``bit``, the column-group law of
``core.column_groups`` — never with a cmy helper of the W1 diff.  Each test
skips, naming the W1 symbols it is missing, until W1 lands them; a
mismatch after that is a defect in W1 or in a premise below, never a
re-pin.

Four families:

* the LABEL TABLE (§2.2, R2) and the two streams' auxes (§2.3, R1, R6);
* the IDENTITY of the vector rows (§2.4, R1, R12): canonical id, seed,
  codec and bank ids;
* the FURNITURE of four tiles — word sites by R10, dust by R3 as amended
  (§2.5): counters 12, 28, 30 of c2-cmy-r0700@10x10 (W 19 at the tie, so
  M takes all twenty; W 15; Y 15) and counter 0 of the p300 row, whose
  word keys start at u = 200;
* the PAIR TABLE (§3.2) at p120, and at p300 for the rows the plan's
  10x10 goldens name, through the existing law.

Premises the design leaves to the builder, frozen here: a p300 row's
display spelling is cmy8's (``c2-cmy-r0700-p300@10x10``); the codec id is
``cmy-{token}-p{p}-v1`` (plan §1); ``cmy_state_labels`` refuses with
ValueError; word and dust states are presence ids.
"""
from __future__ import annotations

import hashlib
import importlib
from collections import Counter
from fractions import Fraction

import numpy as np
import pytest

from holo.core import capacity, channel
from holo.core import keystream_spec as spec_ks
from holo.format import pilots
from holo.format.lattice import parse_format_id

from _cmy_vectors import STATE_ID, TILES, ids, letters


def _missing(symbols: tuple[str, ...]) -> list[str]:
    out = []
    for symbol in symbols:
        module, _, path = symbol.partition(":")
        obj = importlib.import_module(module)
        for name in path.split("."):
            obj = getattr(obj, name, None)
            if obj is None:
                out.append(symbol)
                break
    return out


def needs_w1(*symbols: str) -> pytest.MarkDecorator:
    missing = _missing(symbols)
    return pytest.mark.skipif(
        bool(missing), reason="cmy W1 not built: " + ", ".join(missing))


LABEL_SYMBOLS = (
    "holo.core.channel:CMY_STATE_IDS",
    "holo.core.channel:CMY_LABEL_TO_STATE",
    "holo.core.channel:cmy_label_states",
    "holo.core.channel:cmy_state_labels",
)
ROW_SYMBOLS = (
    "holo.format.profiles:Family.CMY",
    "holo.format.families:cmy_codec",
)
KEY_SYMBOLS = ("holo.core.keystream:color_word_zero_mask",)


# ---------------------------------------------------------- label table

# design §2.2 table (R2): (state, hi, lo, presence id, C/M/Y inks)
LABEL_TABLE = (
    ("W", 0, 0, 0, (0, 0, 0)),
    ("Y", 0, 1, 4, (0, 0, 1)),
    ("M", 1, 0, 2, (0, 1, 0)),
    ("C", 1, 1, 1, (1, 0, 0)),
)
CMY_STATE_IDS = (0, 1, 2, 4)                 # §2.1
CMY_LABEL_TO_STATE = (0, 4, 2, 1)            # plan §1, index (hi << 1) | lo
DITHER_AUX = (("hi", 1), ("lo", 2))          # §2.3 D9, R6; fountain aux None


@needs_w1(*LABEL_SYMBOLS)
def test_the_label_table_is_the_cyan_antipode():
    assert channel.CMY_STATE_IDS == CMY_STATE_IDS
    assert channel.CMY_LABEL_TO_STATE == CMY_LABEL_TO_STATE
    assert type(channel.CMY_STATE_IDS) is tuple
    assert type(channel.CMY_LABEL_TO_STATE) is tuple
    hi = np.array([row[1] for row in LABEL_TABLE], dtype=np.uint8)
    lo = np.array([row[2] for row in LABEL_TABLE], dtype=np.uint8)
    ids = channel.cmy_label_states(hi, lo)
    assert ids.dtype == np.uint8
    assert ids.tolist() == [row[3] for row in LABEL_TABLE]
    assert [CMY_LABEL_TO_STATE[(h << 1) | b] for _, h, b, _, _
            in LABEL_TABLE] == [row[3] for row in LABEL_TABLE]
    back_hi, back_lo = channel.cmy_state_labels(ids)
    assert back_hi.tolist() == hi.tolist()
    assert back_lo.tolist() == lo.tolist()
    assert channel.states_to_planes(ids).tolist() == [
        list(row[4]) for row in LABEL_TABLE]
    assert {row[0]: row[3] for row in LABEL_TABLE} == STATE_ID


@needs_w1(*LABEL_SYMBOLS)
@pytest.mark.parametrize("state", [3, 5, 6, 7])
def test_state_labels_refuse_every_overlap_state(state):
    with pytest.raises(ValueError):
        channel.cmy_state_labels(np.array([0, state, 1], dtype=np.uint8))


@needs_w1(*ROW_SYMBOLS)
def test_the_streams_are_hi_then_lo_with_integer_dither_auxes():
    from holo.format.families import cmy_codec
    codec = cmy_codec(("r0700", "r0700"))
    assert codec.stream_ids == tuple(s for s, _ in DITHER_AUX)
    assert tuple(codec.stream_ids.index(s) + 1 for s in codec.stream_ids) \
        == tuple(aux for _, aux in DITHER_AUX)
    assert [stream.fountain_aux for stream in codec.streams] == [None, None]


# -------------------------------------------------------------- identity

# §2.4 table, R1 (rungs in stream order, the uniform pair contracted),
# R12 (p always spelled); seed = b"holo/v2/" + canonical (FORMAT-SPACE §6,
# descriptor.FormatSpec.seed); banks §2.2 D3
ROWS = {
    "c2-cmy-r0700@10x10": dict(
        canonical="1i300-cmy-r0700-p120-v1@10x10",
        seed=b"holo/v2/1i300-cmy-r0700-p120-v1@10x10",
        codec_id="cmy-r0700-p120-v1",
        banks=("cmy-hi-r0700-p120-v1", "cmy-lo-r0700-p120-v1"),
        n_dust=20,
        family_seed=b"holo/v1/sites/p120",
    ),
    "c2-cmy-r0700-p300@10x10": dict(
        canonical="1i300-cmy-r0700-p300-v1@10x10",
        seed=b"holo/v2/1i300-cmy-r0700-p300-v1@10x10",
        codec_id="cmy-r0700-p300-v1",
        banks=("cmy-hi-r0700-p300-v1", "cmy-lo-r0700-p300-v1"),
        n_dust=200,
        family_seed=b"holo/v1/sites/p300",
    ),
}


@needs_w1(*ROW_SYMBOLS)
@pytest.mark.parametrize("display", sorted(ROWS))
def test_the_vector_rows_spell_their_identity(display):
    row = ROWS[display]
    spec = parse_format_id(display)
    assert (spec.spec_id, spec.display_id, spec.seed) == (
        row["canonical"], display, row["seed"])
    assert parse_format_id(row["canonical"]).seed == row["seed"]
    codec = spec.codec
    assert codec.codec_id == row["codec_id"]
    assert tuple(s.fec.profile_id for s in codec.streams) == row["banks"]
    assert (codec.n_dust, spec.family_seed) == (
        row["n_dust"], row["family_seed"])
    assert codec.state_names == ("W", "C", "M", "Y")
    assert codec.state_ids == CMY_STATE_IDS
    assert codec.word_states == (STATE_ID["W"], STATE_ID["C"])
    assert codec.dust_base_cycle == ()
    assert spec.pooled_fountain


# ------------------------------------------------------------- furniture

# The four tiles' literals live in _cmy_vectors.py (TILES), beside the
# state-id spelling test_cmy_emission reads them through.


@needs_w1(*ROW_SYMBOLS)
@pytest.mark.parametrize("key", sorted(TILES))
def test_word_sites_print_cyan_for_one_and_the_keyed_w_or_y_for_zero(key):
    display, counter = key
    tile = TILES[key]
    spec = parse_format_id(display)
    states = pilots.color_word_states(spec.seed, [counter], spec.codec)[0]
    assert states.dtype == np.uint8 and states.shape == (100,)
    assert states.tolist() == ids(tile["words"])
    assert hashlib.sha256(states.tobytes()).hexdigest() \
        == tile["words_sha256"]
    assert dict(Counter(letters(tile["words"]))) == tile["supply"]
    assert pilots.decode_color_word(states, spec.seed, spec.codec) == counter


@needs_w1(*ROW_SYMBOLS, *KEY_SYMBOLS)
@pytest.mark.parametrize("key", sorted(TILES))
def test_the_word_zero_mask_is_domain_9_past_the_dust(key):
    from holo.core import keystream
    display, counter = key
    spec = parse_format_id(display)
    mask = keystream.color_word_zero_mask(spec.seed, counter, spec.n_dust)
    assert mask.dtype == np.bool_ and mask.shape == (100,)
    assert "".join("1" if b else "0" for b in mask) \
        == letters(TILES[key]["zero_mask"])


@needs_w1(*ROW_SYMBOLS)
@pytest.mark.parametrize("key", sorted(TILES))
def test_the_dust_balances_the_tiles_own_word_supply(key):
    display, counter = key
    tile = TILES[key]
    spec = parse_format_id(display)
    dust = pilots.dust_state_values(spec.seed, [counter], spec.codec)[0]
    assert dust.tolist() == ids(tile["dust"])
    assert dict(Counter(letters(tile["dust"]))) == tile["dust_counts"]


@needs_w1(*ROW_SYMBOLS)
@pytest.mark.parametrize("key", sorted(TILES))
def test_the_literals_are_the_design_rule_over_the_frozen_reference(key):
    display, counter = key
    tile = TILES[key]
    seed, n_dust = ROWS[display]["seed"], ROWS[display]["n_dust"]
    values = pilots.word_values(seed, [counter], pilots.PLANE_K)[0]
    zero_y = [spec_ks.bit(seed, spec_ks.DOMAIN_COLOR_DUST_ORDER, 0, counter,
                          n_dust + site, 0) for site in range(100)]
    words = ["C" if v else "WY"[y] for v, y in zip(values, zero_y)]
    assert "".join(words) == letters(tile["words"])
    assert "".join(map(str, zero_y)) == letters(tile["zero_mask"])
    totals = Counter(words)
    fill = []
    for _ in range(n_dust):
        state = min("MYWC", key=lambda s: totals[s])
        fill.append(state)
        totals[state] += 1
    keys = [spec_ks.color_dust_order_key(seed, counter, i)
            for i in range(n_dust)]
    order = sorted(range(n_dust), key=lambda i: (keys[i], i))
    assert "".join(fill[i] for i in order) == letters(tile["dust"])


# ------------------------------------------------------------ pair table

# §3.2 (p120) and its p300 replica; widths S = k - p - 33 per stream
# (§2.3, §3.1); the reserve at one block, 16 + bit_length(Z - 1) (§2.6).
# (display, widths, Z, carried, spare b/site, (hi-dead, lo-dead) ceilings,
#  fountain bits/site, reserve)
PAIRS = (
    ("c2-cmy-r0700@10x10", (2727, 2727), 1, (1, 1), Fraction(0),
     (Fraction(1, 2), Fraction(1, 2)), Fraction(5454), 16),
    ("c2-cmy-r0775@10x10", (3047, 3047), 1, (1, 1), Fraction(0),
     (Fraction(1, 2), Fraction(1, 2)), Fraction(6094), 16),
    ("c2-cmy-r0850@10x10", (3367, 3367), 1, (1, 1), Fraction(0),
     (Fraction(1, 2), Fraction(1, 2)), Fraction(6734), 16),
    ("c2-cmy-r0775x0700@10x10", (3047, 2727), 19, (19, 17), Fraction(14, 19),
     (Fraction(17, 36), Fraction(19, 36)), Fraction(109692, 19), 21),
    ("c2-cmy-r0850x0775@10x10", (3367, 3047), 21, (21, 19), Fraction(2, 3),
     (Fraction(19, 40), Fraction(21, 40)), Fraction(19240, 3), 21),
    ("c2-cmy-r0850x0700@10x10", (3367, 2727), 21, (21, 17), Fraction(4, 3),
     (Fraction(17, 38), Fraction(21, 38)), Fraction(18278, 3), 21),
    ("c2-cmy-r0700x0547@10x10", (2727, 2087), 17, (17, 13), Fraction(28, 17),
     (Fraction(13, 30), Fraction(17, 30)), Fraction(81810, 17), 21),
    ("c2-cmy-r0700x0625@10x10", (2727, 2407), 17, (17, 15), Fraction(14, 17),
     (Fraction(15, 32), Fraction(17, 32)), Fraction(87264, 17), 21),
    ("c2-cmy-r0700-p300@10x10", (2547, 2547), 1, (1, 1), Fraction(0),
     (Fraction(1, 2), Fraction(1, 2)), Fraction(5094), 16),
    ("c2-cmy-r0775x0700-p300@10x10", (2867, 2547), 26, (26, 23),
     Fraction(281, 26), (Fraction(23, 49), Fraction(26, 49)),
     Fraction(140483, 26), 21),
    ("c2-cmy-r0700x0625-p300@10x10", (2547, 2227), 31, (31, 27),
     Fraction(268, 31), (Fraction(27, 58), Fraction(31, 58)),
     Fraction(147726, 31), 21),
    ("c2-cmy-r0850x0700-p300@10x10", (3187, 2547), 29, (29, 23),
     Fraction(562, 29), (Fraction(23, 52), Fraction(29, 52)),
     Fraction(165724, 29), 21),
)


@needs_w1(*ROW_SYMBOLS)
@pytest.mark.parametrize(
    "display,widths,z,carried,spare,ceilings,site_bits,reserve", PAIRS)
def test_the_pair_table_pools_two_streams_by_the_column_group_law(
        display, widths, z, carried, spare, ceilings, site_bits, reserve):
    spec = parse_format_id(display)
    assert spec.stream_symbol_bits == widths
    assert spec.pooled_fountain
    g = spec.column_groups
    assert (g.n_groups, g.carried, g.spare_bits_per_site) == (
        z, carried, spare)
    assert (g.plane_tier_ceiling(0), g.plane_tier_ceiling(1)) == ceilings
    assert g.any_plane_ceiling == min(ceilings)
    assert Fraction(g.chunks_per_site * g.symbol_bits, g.n_groups) \
        == site_bits
    assert capacity.rank_reserve_for(1, solves_per_block=z) == reserve
