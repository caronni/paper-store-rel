"""The v2 identity grammar (FORMAT-SPACE §6): parse_format_id round-trips,
normalization, refusals, off-600 pitches, pitch tokens, and the
v2/fossil seed-namespace split.
"""
from __future__ import annotations

from fractions import Fraction
from types import MappingProxyType

import pytest

from holo.format import fossils, lattice
from holo.format.lattice import (
    PITCH_CLASSES,
    display_pitch_token,
    mint,
    parse_format_id,
    parse_pitch,
)
from holo.format.profiles import Family

# The battery of canonical v2 format ids: each must parse to a spec whose
# spec_id is exactly the input string (i.e. the input is already the
# canonical spelling) and whose seed is the v2-namespaced encoding of it.
# Canonical = the EXPLICIT spelling since FORMAT-SPACE §16 (2026-08-30):
# rational pitch, sites and generation always spelled.  The short forms
# these were written in are now display spellings; they appear as inputs
# in NORMALIZATION_CASES and DISPLAY_CASES below.
ROUND_TRIP_IDS = [
    "1i300-k-r0700-p100-v1@53x37",
    "1i200-k-r0550-p100-v1@10x10",
    "1i150-k-r0550-p100-v1@26x18",
    "1i300-cmy8-r0700-p120-v1@53x37",
    "1i300-cmy8-r0550x0550x0547-p120-v1@53x37",
    "1i300-cmy7-p120-v1@52x36",
    "1i300-k-r0550-p300-v1@10x10",
    "1i400-k-r0700-p100-v1@40x28",
]


@pytest.mark.parametrize("format_id", ROUND_TRIP_IDS)
def test_round_trip_battery(format_id: str) -> None:
    spec = parse_format_id(format_id)
    assert spec.spec_id == format_id
    assert spec.seed == b"holo/v2/" + format_id.encode()


def test_round_trip_battery_facts() -> None:
    spec = parse_format_id("c2-k-r0700@53x37")
    assert spec.tiles_per_page == 1961
    assert spec.cells_yx == (3392, 2368)
    assert spec.codec_id == "k-v1"
    assert spec.rate_id == "r0700"

    spec = parse_format_id("c2-cmy8-r0700@53x37")
    assert spec.n_streams == 3
    assert spec.pooled_fountain is True
    assert spec.codec_id == "cmy8-r0700-p120-v1"
    assert spec.n_dust == 20


NORMALIZATION_CASES = [
    ("c2-cmy8-r0700x0700x0700-p120-v1@53x37",
     "1i300-cmy8-r0700-p120-v1@53x37"),
    ("c2-cmy8-r0700@53x37", "1i300-cmy8-r0700-p120-v1@53x37"),
    ("2i600-k-r0700@53x37", "1i300-k-r0700-p100-v1@53x37"),
    ("c2-k-r0700-p100-v1@53x37", "1i300-k-r0700-p100-v1@53x37"),
    ("c2-cmy7-p120-v1@52x36", "1i300-cmy7-p120-v1@52x36"),
]

# The short spelling each canonical id shows a person (FORMAT-SPACE §6).
DISPLAY_CASES = [
    ("1i300-k-r0700-p100-v1@53x37", "c2-k-r0700@53x37"),
    ("1i300-cmy8-r0700-p120-v1@53x37", "c2-cmy8-r0700@53x37"),
    ("1i300-cmy7-p120-v1@52x36", "c2-cmy7@52x36"),
    ("1i300-k-r0550-p300-v1@10x10", "c2-k-r0550-p300@10x10"),
    ("1i400-k-r0700-p100-v1@40x28", "1i400-k-r0700@40x28"),
]


@pytest.mark.parametrize("canonical,display", DISPLAY_CASES)
def test_display_id_is_the_short_spelling_and_round_trips(
        canonical: str, display: str) -> None:
    spec = parse_format_id(canonical)
    assert spec.display_id == display
    assert parse_format_id(display).spec_id == canonical
    assert parse_format_id(display).seed == spec.seed


@pytest.fixture
def clean_coding_cache():
    # coding_for is lru_cached on the canonical id, and display_coding_id
    # is minted with it — so a row minted while the sugar tables are
    # patched must not survive into another test.
    lattice._coding_for_id.cache_clear()
    yield
    lattice._coding_for_id.cache_clear()


def test_canonical_ids_and_seeds_ignore_the_pitch_class_table(
        monkeypatch: pytest.MonkeyPatch, clean_coding_cache) -> None:
    # FORMAT-SPACE §6 law 4: registering a class name is a DISPLAY act.
    # c5 is the next 600-grid class: five dots = 1/120 inch = 1i120.
    refs = ROUND_TRIP_IDS + [spelling for spelling, _ in NORMALIZATION_CASES]
    refs = refs + ["1i120-k-r0550@7x7"]
    before = {ref: parse_format_id(ref) for ref in refs}
    monkeypatch.setattr(lattice, "PITCH_CLASSES", MappingProxyType(
        {**PITCH_CLASSES, "c5": Fraction(1, 120)}))
    monkeypatch.setattr(lattice, "_CLASS_BY_PITCH", MappingProxyType(
        {**lattice._CLASS_BY_PITCH, Fraction(1, 120): "c5"}))
    lattice._coding_for_id.cache_clear()
    for ref in refs:
        spec = parse_format_id(ref)
        assert spec.spec_id == before[ref].spec_id, ref
        assert spec.seed == before[ref].seed, ref
    assert parse_format_id("1i120-k-r0550@7x7").display_id == \
        "c5-k-r0550@7x7"


def test_a_canonical_id_survives_a_defaults_change(
        monkeypatch: pytest.MonkeyPatch, clean_coding_cache) -> None:
    spec = parse_format_id("c3-k-r0550@10x10")
    monkeypatch.setattr(lattice, "_DEFAULT_SITES",
                        {**lattice._DEFAULT_SITES, Family.K: 120})
    monkeypatch.setattr(lattice, "_DEFAULT_GEN", 2)
    lattice._coding_for_id.cache_clear()
    again = parse_format_id(spec.spec_id)
    assert again.spec_id == spec.spec_id
    assert again.seed == spec.seed
    assert again.n_sites == spec.n_sites


def test_the_coding_constructor_refuses_a_non_canonical_id(
        clean_coding_cache) -> None:
    # The coding id is the seed payload verbatim, so only the canonical
    # spelling may reach the constructor; a display spelling handed in
    # directly would mint a second seed for one format.
    with pytest.raises(ValueError, match="not a canonical coding id"):
        lattice._coding_for_id("c2-k-r0700")
    with pytest.raises(ValueError, match="not a canonical coding id"):
        lattice._coding_for_id("1i300-k-r0700-p100")
    assert lattice._coding_for_id("1i300-k-r0700-p100-v1").coding_id == \
        "1i300-k-r0700-p100-v1"


def test_mint_is_the_parameter_door_and_equals_parse() -> None:
    minted = mint(pitch=Fraction(1, 200), family=Family.K,
                  rungs=("r0550",), sites=100, gen=1, tiles_yx=(7, 7))
    parsed = parse_format_id("c3-k-r0550@7x7")
    assert minted.spec_id == parsed.spec_id == "1i200-k-r0550-p100-v1@7x7"
    assert minted.display_id == parsed.display_id == "c3-k-r0550@7x7"
    assert minted.seed == parsed.seed
    with pytest.raises(ValueError, match="rung arity must be"):
        mint(pitch=Fraction(1, 300), family=Family.CMY8,
             rungs=("r0550",), sites=120, gen=1, tiles_yx=(10, 10))


@pytest.mark.parametrize("spelling,canonical", NORMALIZATION_CASES)
def test_normalization(spelling: str, canonical: str) -> None:
    parsed = parse_format_id(spelling)
    reference = parse_format_id(canonical)
    assert parsed.spec_id == canonical
    assert parsed.seed == reference.seed
    assert parsed.seed == b"holo/v2/" + canonical.encode()


def test_refusal_legacy_id_form_mentions_fossil() -> None:
    with pytest.raises(ValueError) as exc:
        parse_format_id("c2-r0700@52x36")
    msg = str(exc.value)
    assert "fossil" in msg or "L:" in msg


def test_refusal_unknown_rung() -> None:
    with pytest.raises(ValueError):
        parse_format_id("c2-k-r0300@10x10")


def test_uneven_cmy8_triplet_is_a_lawful_column_group_pool() -> None:
    """Ruling 2026-09-04 (docs/CMY8-COLUMN-GROUPS.md, gen-v1): an uneven
    triplet parses; the pool's symbol is the widest plane's width and the
    narrower plane carries column groups of it."""
    spec = parse_format_id("c2-cmy8-r0700x0700x0547@53x37")
    assert spec.spec_id == "1i300-cmy8-r0700x0700x0547-p120-v1@53x37"
    assert spec.pooled_fountain
    assert spec.stream_symbol_bits == (2727, 2727, 2087)
    assert spec.symbol_bits == 2727
    assert spec.aggregate_symbol_bits == 3 * 2727


def test_refusal_cmy7_with_rung_token() -> None:
    with pytest.raises(ValueError):
        parse_format_id("c2-cmy7-r0550@52x36")


def test_refusal_k_without_rung() -> None:
    with pytest.raises(ValueError):
        parse_format_id("c2-k@10x10")


def test_refusal_sites_below_floor() -> None:
    with pytest.raises(ValueError):
        parse_format_id("c2-k-r0700-p99@10x10")


def test_refusal_misordered_tokens() -> None:
    with pytest.raises(ValueError):
        parse_format_id("c2-k-p100-r0700@10x10")


def test_refusal_zero_tile_axis() -> None:
    with pytest.raises(ValueError):
        parse_format_id("c2-k-r0700@0x10")


def test_refusal_counter_space_overflow() -> None:
    assert 512 * 513 > (1 << 18)
    with pytest.raises(ValueError):
        parse_format_id("c2-k-r0700@512x513")


def test_refusal_unregistered_pitch_class() -> None:
    with pytest.raises(ValueError):
        parse_format_id("c9-k-r0700@10x10")


def test_refusal_zero_rational_pitch() -> None:
    with pytest.raises(ValueError):
        parse_format_id("0i300-k-r0700@10x10")


def test_refusal_missing_at_sign() -> None:
    with pytest.raises(ValueError):
        parse_format_id("c2-k-r0700")


def test_refusal_bad_tiles_token() -> None:
    with pytest.raises(ValueError):
        parse_format_id("c2-k-r0700@axb")


def test_off_600_pitch() -> None:
    spec = parse_format_id("1i400-k-r0700@40x28")
    assert spec.spec_id == "1i400-k-r0700-p100-v1@40x28"
    assert spec.seed == b"holo/v2/1i400-k-r0700-p100-v1@40x28"
    assert spec.display_id == "1i400-k-r0700@40x28"
    assert spec.tiles_per_page == 40 * 28
    assert spec.n_streams == 1
    with pytest.raises(ValueError) as exc:
        _ = spec.layout
    msg = str(exc.value)
    assert "off the 600 grid" in msg or "pending" in msg
    with pytest.raises(ValueError):
        _ = spec.cell_dots
    assert spec.pitch == Fraction(1, 400)


def test_pitch_tokens() -> None:
    assert parse_pitch("c2") == Fraction(1, 300)
    assert parse_pitch("2i600") == Fraction(1, 300)
    assert display_pitch_token(Fraction(1, 300)) == "c2"
    assert display_pitch_token(Fraction(1, 400)) == "1i400"
    with pytest.raises(ValueError):
        parse_pitch("c7")
    assert dict(PITCH_CLASSES) == {
        "c1": Fraction(1, 600),
        "c2": Fraction(1, 300),
        "c3": Fraction(1, 200),
        "c4": Fraction(1, 150),
    }


def test_seed_namespace_disjoint_from_fossils() -> None:
    fossil_seeds = {fossil.seed for fossil in fossils.FOSSILS.values()}
    for format_id in ROUND_TRIP_IDS:
        seed = parse_format_id(format_id).seed
        assert seed.startswith(b"holo/v2/")
        assert seed not in fossil_seeds
    for fossil in fossils.FOSSILS.values():
        assert fossil.seed.startswith(b"holo/v1/")


def test_v2_synthetic_layout_on_600_grid() -> None:
    spec = parse_format_id("c3-k-r0550@10x10")
    layout = spec.layout
    assert layout.cells_yx == (640, 640)
    assert layout.tiles_yx == (10, 10)
    assert layout.origin_dots_yx == (0, 0)
    assert layout.cell_dots == 3
    assert layout.page_dots_xy == (1920, 1920)


def test_family_seed_carries_frozen_v1_template() -> None:
    assert parse_format_id("c2-cmy8-r0700@53x37").family_seed == \
        b"holo/v1/sites/p120"
    assert parse_format_id("c2-k-r0550-p300@10x10").family_seed == \
        b"holo/v1/sites/p300"
