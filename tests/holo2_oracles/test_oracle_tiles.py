"""Carry-equivalence oracle: holo2's tile decode chain == holo's, exactly.

WORKPLAN H3bis.  ``holo2/src/holo2/{bch,pilots,detect,tiles}.py`` and
``holo2/src/holo2/ldpc/{construct,decode,tile}.py`` are copy-and-adapt
carries of ``src/holo/{core,format,receive}``; the firewall forbids
importing the original, so equivalence is pinned HERE, outside the holo2
tree, where both packages may be imported.

Five things are compared, in the order a decode meets them:

(a) the C1 address word — BCH(127,50,t=13)->(100,23) over an 18-bit flat
    counter plus five known-zero pads: same codewords, same counter
    round-trip, same refusals (including the ones that make d=27 real);
(b) the per-tile site families and the affine slot permutation — the two
    format facts that say which cell carries which code bit;
(c) the detector — ``pava-v1`` and the nine-bin ``ctx-pava-v1`` arm,
    byte-equal on shared observations, refusals included;
(d) ``attempt_k_tile`` itself — identical certificates on real generator
    pages, and identical REFUSALS as the same cells are flipped until BP
    gives up (a chain that agreed only where it succeeds would be no
    evidence at all);
(e) the code, not just its outputs: every carried definition compared to
    its original by unparsed AST, with the adaptations declared.

The pages come from the REAL generator (``plan_volume`` ->
``source_packed_for`` -> ``VolumeCode.encode_symbols`` ->
``compose_page_cells``), so what the chain decodes is what a printed sheet
carries, not a hand-built approximation of it.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import inspect
from dataclasses import dataclass

import numpy as np
import pytest

from holo.core import bch as h_bch
from holo.format import lattice as v1_lattice
from holo.core import fountain as h_fountain
from holo.core import keystream as h_keystream
from holo.core.ldpc import construct as h_construct
from holo.core.ldpc import decode as h_ldpc_decode
from holo.core.ldpc import tile as h_ldpc_tile
from holo.format import metadata as h_metadata
from holo.format import pilots as h_pilots
from holo.format.descriptor import FormatSpec, get_coding
from holo.format.layout import MEDIA_MM
from holo.format.resolve import resolve_format_ref as h_resolve_format_ref
from holo.gen.compose import compose_page_cells
from holo.gen.emit import source_packed_for
from holo.gen.plan import plan_volume
from holo.receive import detect as h_detect
from holo.receive import tiles as h_tiles
from holo.receive.evidence import AttemptStage as HAttemptStage
from holo.receive.payload import attempt_k_tile as h_attempt_k_tile
from holo.receive.records import certificate_for_close

from holo2.format import bch as h2_bch
from holo2.solve import detect as h2_detect
from holo2.format import keystream as h2_keystream
from holo2.format import pilots as h2_pilots
from holo2.solve import tiles as h2_tiles
from holo2.format.ldpc import construct as h2_construct
from holo2.format.ldpc import decode as h2_ldpc_decode
from holo2.format.ldpc import tile as h2_ldpc_tile
from holo2.format.registry_rows import tile_format_for
from holo2.format.resolve import format_row_for

# The three K codings this phase carries, each on the tile matrix its
# page always had — whole real pages, small enough that every tile of
# them can be decoded twice inside a test run.
#
# v2 IDENTITIES since 2026-08-22 (package C4, RULINGS G5): the pages used
# to be minted from a 68x68 mm synthetic media that DERIVED 8x8 tiles at
# c3 and 12x12 at c2, and the tile matrices below are exactly the ones
# that inversion produced.  Naming them is the whole point — geometry is
# identity (FORMAT-SPACE §7) — and it is what lets BOTH trees resolve one
# string instead of hand-building two descriptions of one sheet.
FORMATS = ("c3-k-r0550@8x8", "c2-k-r0550@12x12", "c2-k-r0700@12x12")
IDEAL_LLR = 5.0


# ------------------------------------------------------------- fixtures

@dataclass(frozen=True)
class PageFixture:
    """One real generator page, on both sides' description of its format."""

    format_ref: str
    spec: FormatSpec                    # holo's
    fmt: object                         # holo2's TileFormat
    field: np.ndarray                   # composed page cells
    symbols: np.ndarray
    metadata_bits: np.ndarray
    k_total: int

    def tile(self, ty: int, tx: int) -> np.ndarray:
        return self.field[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]

    def index(self, ty: int, tx: int) -> int:
        return ty * self.spec.layout.tiles_yx[1] + tx


def _build_page(format_ref: str) -> PageFixture:
    spec = h_resolve_format_ref(format_ref)
    payload = hashlib.sha256(format_ref.encode()).digest() * 100
    plan = plan_volume(spec, len(payload), 0.5)
    assert plan.n_pages == 1
    source = source_packed_for(payload, plan)
    counters = np.arange(spec.tiles_per_page, dtype=np.int64)
    code = h_fountain.VolumeCode(plan.k_total, plan.symbol_bits, spec.seed,
                                 tiles_per_page=spec.tiles_per_page)
    symbols = code.encode_symbols(source, counters)
    field = compose_page_cells(spec, 0, symbols, plan.k_total)
    metadata_bits = h_metadata.tile_bits(
        h_metadata.encode_metadata(0, plan.k_total), counters)
    row = format_row_for(format_ref, plan.n_pages)
    return PageFixture(format_ref, spec, tile_format_for(row), field,
                       symbols, metadata_bits, plan.k_total)


@pytest.fixture(scope="module")
def pages() -> dict[str, PageFixture]:
    return {format_ref: _build_page(format_ref) for format_ref in FORMATS}


# --------------------------------------------------- the format identity

@pytest.mark.parametrize("format_ref", FORMATS)
def test_the_two_descriptions_are_one_printed_format(
        pages: dict[str, PageFixture], format_ref: str) -> None:
    """holo2's row and holo's FormatSpec name the same sheet.

    ON A v2 IDENTITY THE TWO SPELLINGS ARE THE SAME STRING (C4,
    2026-08-22, RULINGS G5).  These pages used to be v1 identities, where
    holo2 marked the legacy route with ``L:`` on every surface (C2,
    RULINGS G1) while ``src/holo`` kept the bare form its catalogue is
    keyed by; the marker was the only difference and it is gone with the
    namespace.  The printed sheet a page below still names the legacy way
    (``test_the_e029_e032_row_resolves_by_identity_never_by_a_catalog``)
    keeps that comparison alive.  A name is not a keystream either way —
    the SEED is the assertion that matters, and it is compared
    byte-for-byte.
    """
    page = pages[format_ref]
    spec, fmt = page.spec, page.fmt
    assert fmt.spec_id == spec.spec_id
    assert fmt.spec_id == v1_lattice.parse_format_id(format_ref).spec_id
    assert fmt.display_id == spec.display_id == format_ref
    assert fmt.seed == spec.seed
    assert fmt.family_seed == spec.family_seed
    assert fmt.codec_id == spec.codec_id
    # PITCH, not dots (C3, RULINGS G4, 2026-08-22): holo2's row carries
    # the physical pitch and ``src/holo``'s spec derives one from its
    # ``cell_dots``, so the pitches are the fact both trees hold.
    assert fmt.pitch_in == spec.pitch
    assert fmt.rate_id == spec.rate_id
    assert fmt.n_sites == spec.n_sites and fmt.n_filler == spec.n_filler
    assert fmt.n_transmitted_slots == spec.n_transmitted_slots
    assert fmt.tile_user_bits == spec.tile_user_bits
    assert fmt.symbol_bits == spec.symbol_bits
    assert fmt.tiles_per_page == spec.tiles_per_page
    assert fmt.max_pages == spec.max_pages
    assert fmt.stream_ids == spec.stream_ids
    assert fmt.fec_profile_id == spec.stream_profile("main").fec.profile_id
    assert fmt.cells_yx == spec.layout.cells_yx
    for counter in range(spec.tiles_per_page):
        assert fmt.tile_address(counter) == spec.tile_address(counter)
        assert fmt.tile_counter(*spec.tile_address(counter)) == counter


def test_the_e029_e032_row_resolves_by_identity_never_by_a_catalog() -> None:
    """``c2-r0700@3392x2368`` — two verified volumes, not in FORMAT_ROWS.

    Built here from the printer fact that produced it (the ``hp-m281-ink``
    4.5 mm probe geometry) so the two sides are compared on the row the
    hardware actually used, not on a registry row nothing was printed on.

    WP-1.2 (2026-08-22) inverted this test's premise without touching its
    REASON.  It used to end at "declared dimensions": holo2 could reach
    this sheet only because an operator retyped ``--coding`` plus a tile
    grid.  Now the sheet has a NAME — the same string, resolved through
    the legacy catalogue in both spellings — and the point is unchanged
    and sharper: a receiver that could only name registry rows could not
    read the sheets this project actually printed, so the identity is
    what resolves, and the catalog never gates lawfulness.
    """
    from holo.format.registry import FORMAT_ROWS

    from holo2.format.resolve import ROUTE_FOSSIL
    from holo2.format.resolve import format_row_for, resolve_format_ref

    #: THE PRINTED SHEET IS NAMED, NOT DERIVED (C4, 2026-08-22, RULINGS
    #: G5).  The synthetic pages above moved to v2 identities; this one
    #: does not and must not — it is keyed by the frozen v1 seed the
    #: hardware was printed under, and its v2 twin ``c2-k-r0700@53x37``
    #: seeds under ``holo/v2/``, a different keystream for one physical
    #: format.  So the identity is the source here, resolved by
    #: ``src/holo`` from the same ``L:`` string holo2 resolves.
    printed = h_resolve_format_ref("L:c2-r0700@3392x2368")
    assert printed.spec_id == "c2-r0700@3392x2368"
    assert printed.layout.tiles_yx == (53, 37)
    assert printed.spec_id not in FORMAT_ROWS       # the whole point
    # THE PRINTER FACT, kept as an INDEPENDENT WITNESS rather than as the
    # source: ``hp-m281-ink``'s 4.5 mm probe row on A4 derives exactly
    # these cells, which is WHY this identity exists at all and why the
    # two sides are compared on the row the hardware used rather than on
    # a registry row nothing was printed on.
    assert FormatSpec(coding=get_coding("c2-r0700"), media_id="a4",
                      media_mm=MEDIA_MM["a4"], margin_mm=4.5).seed \
        == printed.seed
    row = format_row_for("L:" + printed.spec_id, 1)
    assert row.row_id == "L:" + printed.spec_id
    assert row.seed == printed.seed
    assert row.streams[0].symbol_bits == printed.symbol_bits
    assert tile_format_for(row).n_transmitted_slots == \
        printed.n_transmitted_slots

    # The identity route: the same row, from the string alone — and
    # since C2 (RULINGS G1) there is exactly ONE spelling of it, the
    # ``L:`` line.  Never a catalog lookup, never the v2 grammar.
    assert resolve_format_ref(f"L:{printed.spec_id}").route == ROUTE_FOSSIL
    assert format_row_for(f"L:{printed.spec_id}", 1) == row


# --------------------------------------------- (a) the C1 address word

COUNTERS = (0, 1, 2, 3, 17, 100, 255, 256, 1023, 4096, 65535, 131072,
            (1 << 18) - 2, (1 << 18) - 1)


def test_bch_generator_and_tables_are_identical() -> None:
    assert h2_bch.GF_PRIM_POLY == h_bch.GF_PRIM_POLY == 0x89
    for name in ("N_FULL", "K_FULL", "T", "D_MIN", "SHORTEN_BY", "N_WORD",
                 "K_MSG", "N_PARITY"):
        assert getattr(h2_bch, name) == getattr(h_bch, name), name
    assert np.array_equal(h2_bch.generator_poly(), h_bch.generator_poly())
    left_exp, left_log = h_bch.gf_tables()
    right_exp, right_log = h2_bch.gf_tables()
    assert np.array_equal(left_exp, right_exp)
    assert np.array_equal(left_log, right_log)


@pytest.mark.parametrize("counter", COUNTERS)
def test_address_word_encode_and_counter_round_trip(counter: int) -> None:
    left = h_pilots.encode_word(counter)
    right = h2_pilots.encode_word(counter)
    assert np.array_equal(left, right)
    assert left.shape == (100,)
    seed = b"holo/v1/c2-r0700/3392x2368"
    values_left = h_pilots.word_values(seed, [counter])
    values_right = h2_pilots.word_values(seed, [counter])
    assert np.array_equal(values_left, values_right)
    assert h_pilots.decode_word(values_left[0], seed) == counter
    assert h2_pilots.decode_word(values_right[0], seed) == counter


def test_out_of_range_counters_are_refused_identically() -> None:
    for counter in (-1, 1 << 18):
        with pytest.raises(ValueError):
            h_pilots.encode_word(counter)
        with pytest.raises(ValueError):
            h2_pilots.encode_word(counter)


def test_value_scramble_is_site_local_and_identical() -> None:
    for seed in (b"holo/v1/c3-r0550/512x512", b"holo/v1/c2-r0550/768x768"):
        left = h_pilots.value_scramble_bits(seed)
        right = h2_pilots.value_scramble_bits(seed)
        assert np.array_equal(left, right) and left.shape == (100,)
    assert h2_pilots.PLANE_K == h_pilots.PLANE_K == 3


@pytest.mark.parametrize("n_errors", [0, 1, 6, 13, 14, 20, 33, 50])
def test_word_decode_agrees_on_every_error_count(n_errors: int) -> None:
    """Inside t=13 both correct; beyond it both refuse or both miscorrect
    the SAME way — a decoder that diverged only on bad input would be a
    silent false-accept difference."""
    seed = b"holo/v1/c2-r0550/768x768"
    for counter in (0, 7, 1234, 200000):
        clean = h_pilots.word_values(seed, [counter])[0]
        # deterministic, spread-out error positions (no RNG in any path)
        positions = (np.arange(n_errors, dtype=np.int64) * 37 + counter) % 100
        positions = np.unique(positions)
        corrupt = clean.copy()
        corrupt[positions] ^= 1
        left = h_pilots.decode_word(corrupt, seed)
        right = h2_pilots.decode_word(corrupt, seed)
        assert left == right
        if positions.size <= 13:
            assert left == counter


def test_pad_gate_refuses_identically() -> None:
    """A structurally valid codeword with a nonzero pad is not an address."""
    message = np.zeros(h_bch.K_MSG, np.uint8)
    message[h_pilots.COUNTER_BITS] = 1          # first of the five pads
    seed = b"holo/v1/c3-r0550/512x512"
    printed = h_bch.encode(message) ^ h_pilots.value_scramble_bits(seed)
    assert h_bch.decode(h_bch.encode(message)) is not None   # legal codeword
    assert h_pilots.decode_word(printed, seed) is None
    assert h2_pilots.decode_word(printed, seed) is None


def test_the_printed_word_set_really_has_distance_27() -> None:
    """d_min = 27 EXACT is a format anchor; both sides must realise it."""
    counters = np.arange(384, dtype=np.int64)
    left = np.array([h_pilots.encode_word(int(c)) for c in counters])
    right = np.array([h2_pilots.encode_word(int(c)) for c in counters])
    assert np.array_equal(left, right)
    distances = (left[:, None, :] != left[None, :, :]).sum(axis=2)
    off_diagonal = distances[~np.eye(counters.size, dtype=bool)]
    assert int(off_diagonal.min()) == 27


def test_erasure_decode_agrees(pages: dict[str, PageFixture]) -> None:
    seed = pages["c2-k-r0700@12x12"].fmt.seed
    clean = h_pilots.word_values(seed, [77])[0]
    erasures = np.arange(0, 24, dtype=np.int64)
    damaged = clean.copy()
    damaged[erasures] ^= 1
    assert h_pilots.decode_word(damaged, seed, erasure_idx=erasures) == 77
    assert h2_pilots.decode_word(damaged, seed, erasure_idx=erasures) == 77
    over_budget = np.arange(0, 40, dtype=np.int64)
    assert h_pilots.decode_word(clean, seed, erasure_idx=over_budget) \
        == h2_pilots.decode_word(clean, seed, erasure_idx=over_budget)


# ------------------------------ (b) site families + slot permutation

@pytest.mark.parametrize("format_ref", FORMATS)
def test_site_family_masks_are_byte_equal(pages: dict[str, PageFixture],
                                          format_ref: str) -> None:
    page = pages[format_ref]
    left = h_tiles._geometry(page.spec)
    right = h2_tiles._geometry(page.fmt)
    assert np.array_equal(left.site_flat, right.site_flat)
    assert np.array_equal(left.site_mask_yx, right.site_mask_yx)
    assert np.array_equal(left.word_cells_yx, right.word_cells_yx)
    assert np.array_equal(left.filler_cells_yx, right.filler_cells_yx)
    assert left.site_flat.size == page.spec.n_sites == 100
    # and the family seed is geometry-free, so all three codings share it
    assert page.fmt.family_seed == b"holo/v1/sites/p100"


def test_site_construction_agrees_on_unprinted_filler_rungs() -> None:
    """The filler dial is format-axis even though v1 rows launch at F=0."""
    family = b"holo/v1/sites/p128"
    for n_filler in (0, 1, 5, 28):
        left_word, left_filler = h_pilots.site_cells_yx(family, n_filler)
        right_word, right_filler = h2_pilots.site_cells_yx(family, n_filler)
        assert np.array_equal(left_word, right_word)
        assert np.array_equal(left_filler, right_filler)
        assert np.array_equal(h_pilots.site_cell_indices(family, n_filler),
                              h2_pilots.site_cell_indices(family, n_filler))


@pytest.mark.parametrize("format_ref", FORMATS)
def test_slot_permutation_is_byte_equal_over_the_page(
        pages: dict[str, PageFixture], format_ref: str) -> None:
    page = pages[format_ref]
    slots = page.spec.n_transmitted_slots
    site_flat = h_tiles._geometry(page.spec).site_flat
    for counter in range(page.spec.tiles_per_page):
        left = h_tiles._slot_permutation(page.spec.seed, counter, slots)
        right = h2_tiles._slot_permutation(page.fmt.seed, counter, slots)
        assert left == right
        assert np.gcd(left[0], slots) == 1          # bijectivity
    for counter in (0, 1, 4095, 65535, (1 << 18) - 1):
        a_left, b_left = h_keystream.slot_perm_params(
            page.spec.seed, counter, slots)
        a_right, b_right = h2_keystream.slot_perm_params(
            page.fmt.seed, counter, slots)
        assert np.array_equal(a_left, a_right)
        assert np.array_equal(b_left, b_right)
        assert np.array_equal(
            h_ldpc_tile.cell_map(site_flat, int(a_left[0]), int(b_left[0])),
            h2_ldpc_tile.cell_map(site_flat, int(a_right[0]),
                                  int(b_right[0])))


@pytest.mark.parametrize("format_ref", FORMATS)
def test_payload_scramble_is_byte_equal_per_tile(
        pages: dict[str, PageFixture], format_ref: str) -> None:
    page = pages[format_ref]
    tiles_y, tiles_x = page.spec.layout.tiles_yx
    for ty, tx in ((0, 0), (0, tiles_x - 1), (tiles_y - 1, 0),
                   (tiles_y // 2, tiles_x // 2)):
        assert np.array_equal(
            h_tiles._tile_scramble_bits(page.spec, 0, ty, tx),
            h2_tiles._tile_scramble_bits(page.fmt, 0, ty, tx))
        assert np.array_equal(
            h_tiles._tile_scramble_bits(page.spec, 1, ty, tx),
            h2_tiles._tile_scramble_bits(page.fmt, 1, ty, tx))


@pytest.mark.parametrize("format_ref", FORMATS)
def test_shortening_and_capacity_agree(pages: dict[str, PageFixture],
                                       format_ref: str) -> None:
    page = pages[format_ref]
    rate_id, n_sites = page.spec.rate_id, page.spec.n_sites
    assert h2_ldpc_tile.tile_capacity(rate_id, n_sites) \
        == h_ldpc_tile.tile_capacity(rate_id, n_sites) \
        == page.fmt.tile_user_bits
    assert np.array_equal(
        h_ldpc_tile.transmitted_positions(rate_id, n_sites),
        h2_ldpc_tile.transmitted_positions(rate_id, n_sites))
    assert h2_tiles.k_eff_bits(page.fmt) == h_tiles.k_eff_bits(page.spec)


def test_the_ldpc_mother_codes_are_the_same_codes() -> None:
    """Structure loaded from the copied JSON == structure loaded from v1's."""
    assert set(h2_construct.LADDER) == set(h_construct.LADDER)
    for rate_id, spec in h_construct.LADDER.items():
        mirror = h2_construct.LADDER[rate_id]
        assert (mirror.k_bits, mirror.n_bits, mirror.z, mirror.gap_min,
                mirror.heavy_deg) == (spec.k_bits, spec.n_bits, spec.z,
                                      spec.gap_min, spec.heavy_deg)
    for rate_id in ("r0550", "r0700"):          # the rungs the K rows use
        left = h_construct.load_code(rate_id)
        right = h2_construct.load_code(rate_id)
        assert np.array_equal(left.edge_chk, right.edge_chk)
        assert np.array_equal(left.edge_var, right.edge_var)
        assert np.array_equal(left.chk_starts, right.chk_starts)
        assert np.array_equal(left.var_order, right.var_order)
        assert np.array_equal(left.var_starts, right.var_starts)
        assert np.array_equal(left.enc_info_col, right.enc_info_col)
        assert np.array_equal(left.enc_rows, right.enc_rows)
        assert np.array_equal(left.enc_row_starts, right.enc_row_starts)


def test_crc_and_ldpc_encode_agree() -> None:
    bits = ((np.arange(4000, dtype=np.int64) * 2654435761) >> 5 & 1
            ).astype(np.uint8)
    assert np.array_equal(h_ldpc_tile.crc32_bits(bits),
                          h2_ldpc_tile.crc32_bits(bits))
    info = ((np.arange(2240, dtype=np.int64) * 48271) % 3 == 0
            ).astype(np.uint8)
    assert np.array_equal(h_ldpc_decode.encode(info, "r0550"),
                          h2_ldpc_decode.encode(info, "r0550"))


# ------------------------------------------------------ (c) the detector

def _calibration_population(cls, window_id: str, offset: int, size: int):
    """One deterministic labelled population (no RNG anywhere, L11)."""
    index = np.arange(offset, offset + 2 * size, 2, dtype=np.int64)
    labels = ((index * 7 + 3) % 5 < 2).astype(np.uint8)
    scores = (np.sin(index * 0.37) + labels * 0.8
              + np.cos(index * 0.11) * 0.3)
    return cls(window_id=window_id, scores=scores, labels=labels,
               site_ids=index)


def test_pava_calibration_is_byte_equal() -> None:
    left = h_detect.fit_calibration(
        _calibration_population(h_detect.CalibrationObservations,
                                "window-1", 0, 240),
        _calibration_population(h_detect.CalibrationObservations,
                                "window-1", 1, 120))
    right = h2_detect.fit_calibration(
        _calibration_population(h2_detect.CalibrationObservations,
                                "window-1", 0, 240),
        _calibration_population(h2_detect.CalibrationObservations,
                                "window-1", 1, 120))
    assert left.accepted and right.accepted
    assert left.reason == right.reason
    assert (left.n_search, left.n_search_0, left.n_search_1, left.n_heldout) \
        == (right.n_search, right.n_search_0, right.n_search_1,
            right.n_heldout)
    assert left.heldout_logloss == right.heldout_logloss
    assert np.array_equal(left.calibration.knots, right.calibration.knots)
    assert np.array_equal(left.calibration.probabilities,
                          right.calibration.probabilities)
    probe = np.linspace(-3.0, 3.0, 501)
    assert np.array_equal(left.calibration.llr(probe),
                          right.calibration.llr(probe))
    assert h2_detect.clamp_for(left.n_search) == h_detect.clamp_for(
        left.n_search)


def test_calibration_refusals_are_byte_equal() -> None:
    """A window either has the registered support or refuses (same reason)."""
    def one_sided(cls, size: int):
        index = np.arange(size, dtype=np.int64)
        return cls(window_id="w", scores=index * 0.01,
                   labels=np.zeros(size, np.uint8), site_ids=index)

    for size, expect in ((40, "search_class_starved"),):
        left = h_detect.fit_calibration(
            one_sided(h_detect.CalibrationObservations, size),
            _calibration_population(h_detect.CalibrationObservations,
                                    "w", 1001, 60))
        right = h2_detect.fit_calibration(
            one_sided(h2_detect.CalibrationObservations, size),
            _calibration_population(h2_detect.CalibrationObservations,
                                    "w", 1001, 60))
        assert left.reason == right.reason == expect
        assert not left.accepted and not right.accepted
    starved_heldout = (
        h_detect.fit_calibration(
            _calibration_population(h_detect.CalibrationObservations,
                                    "w", 0, 200),
            _calibration_population(h_detect.CalibrationObservations,
                                    "w", 1001, 4)),
        h2_detect.fit_calibration(
            _calibration_population(h2_detect.CalibrationObservations,
                                    "w", 0, 200),
            _calibration_population(h2_detect.CalibrationObservations,
                                    "w", 1001, 4)))
    assert starved_heldout[0].reason == starved_heldout[1].reason \
        == "heldout_starved"
    for name in ("CAL_MIN_PER_CLASS", "CAL_MIN_HELDOUT", "N_CONTEXT_BINS",
                 "CTX_OFFSET_LIMIT", "CTX_LLR_CLAMP", "CTX_BIN_PRIOR",
                 "CTX_MIN_SEARCH", "CTX_MIN_SEARCH_PER_CLASS",
                 "CTX_MIN_VALIDATION", "CTX_MIN_VALIDATION_PER_CLASS",
                 "CTX_ROOT_TOL"):
        assert getattr(h2_detect, name) == getattr(h_detect, name), name


def _context_population(cls, region_id: str, offset: int, size: int):
    site_ids = np.repeat(np.arange(offset, offset + size, dtype=np.int64), 2)
    labels = ((site_ids * 11 + 5) % 7 < 3).astype(np.uint8)
    counts = ((site_ids * 3 + np.arange(site_ids.size)) % 9).astype(np.int8)
    baseline = (np.sin(site_ids * 0.21) * 1.5
                + labels * 1.1 - 0.4 + counts * 0.05)
    return cls(region_id=region_id, baseline_llr=baseline,
               neighbour_count=counts, labels=labels, site_ids=site_ids)


def test_context_arm_is_byte_equal() -> None:
    left = h_detect.fit_context(
        _context_population(h_detect.ContextObservations, "r", 0, 300),
        _context_population(h_detect.ContextObservations, "r", 5000, 150))
    right = h2_detect.fit_context(
        _context_population(h2_detect.ContextObservations, "r", 0, 300),
        _context_population(h2_detect.ContextObservations, "r", 5000, 150))
    assert left.eligible and right.eligible
    assert left.adopted == right.adopted and left.reason == right.reason
    assert np.array_equal(left.offsets, right.offsets)
    assert left.baseline_validation_logloss == \
        right.baseline_validation_logloss
    assert left.candidate_validation_logloss == \
        right.candidate_validation_logloss
    for name in ("search_support_by_bin", "validation_support_by_bin",
                 "search_observations_by_bin",
                 "validation_observations_by_bin"):
        assert np.array_equal(getattr(left, name), getattr(right, name)), name
    assert (left.n_search, left.n_search_0, left.n_search_1) == \
        (right.n_search, right.n_search_0, right.n_search_1)
    # the offsets are ordered (monotone in ink neighbourhood) on both sides
    assert np.all(np.diff(left.offsets) <= 1e-10)


def test_context_starvation_refuses_identically() -> None:
    left = h_detect.fit_context(
        _context_population(h_detect.ContextObservations, "r", 0, 20),
        _context_population(h_detect.ContextObservations, "r", 5000, 150))
    right = h2_detect.fit_context(
        _context_population(h2_detect.ContextObservations, "r", 0, 20),
        _context_population(h2_detect.ContextObservations, "r", 5000, 150))
    assert not left.eligible and not right.eligible
    assert left.reason == right.reason == "insufficient_search_support"
    assert np.array_equal(left.offsets, right.offsets)


def test_context_neighbourhood_and_application_are_byte_equal() -> None:
    ys, xs = np.meshgrid(np.arange(12), np.arange(11), indexing="ij")
    cells = np.stack([ys.ravel(), xs.ravel()], axis=1).astype(np.int64)
    ink = ((cells[:, 0] * 5 + cells[:, 1] * 3) % 4 < 2).astype(np.uint8)
    left_counts, left_valid = h_detect.context_neighbour_counts(cells, ink)
    right_counts, right_valid = h2_detect.context_neighbour_counts(cells, ink)
    assert np.array_equal(left_counts, right_counts)
    assert np.array_equal(left_valid, right_valid)
    left_bins = h_detect.context_bins(left_counts, valid=left_valid)
    right_bins = h2_detect.context_bins(right_counts, valid=right_valid)
    assert np.array_equal(left_bins, right_bins)
    assert int((left_bins < 0).sum()) > 0        # the boundary really is -1
    offsets = np.linspace(2.0, -2.0, h_detect.N_CONTEXT_BINS)
    llr = np.sin(np.arange(cells.shape[0]) * 0.13) * 20.0
    assert np.array_equal(
        h_detect.apply_context_offsets(llr, left_bins, offsets),
        h2_detect.apply_context_offsets(llr, right_bins, offsets))


# -------------------------------------------- (d) attempt_k_tile parity

_ORACLE_SHA = hashlib.sha256(b"holo2-h3bis-oracle-source").hexdigest()


def _holo_attempt(page: PageFixture, llr: np.ndarray, ty: int, tx: int,
                  tag: str):
    record, certificate = h_attempt_k_tile(
        llr, page.spec, (0, ty, tx), HAttemptStage.SCAN,
        source_sha256=_ORACLE_SHA, lane_id="h3bis-oracle",
        component_block_ids=(hashlib.sha256(tag.encode()).hexdigest(),))
    return record, certificate


def _llr_from(tile: np.ndarray, flips: np.ndarray | None = None
              ) -> np.ndarray:
    out = (tile.astype(np.float64) * 2.0 - 1.0) * IDEAL_LLR
    if flips is not None and flips.size:
        flat = out.reshape(-1)
        flat[flips] = -flat[flips]
    return out


@pytest.mark.parametrize("format_ref", FORMATS)
def test_clean_certificates_are_identical(pages: dict[str, PageFixture],
                                          format_ref: str) -> None:
    """Every tile of a real page, decoded twice, must agree exactly."""
    page = pages[format_ref]
    tiles_y, tiles_x = page.spec.layout.tiles_yx
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            llr = _llr_from(page.tile(ty, tx))
            record, certificate = _holo_attempt(page, llr, ty, tx,
                                                f"{format_ref}-{ty}-{tx}")
            attempt = h2_tiles.attempt_k_tile(
                llr, page.fmt, (0, ty, tx), h2_tiles.AttemptStage.SCAN)
            assert record.state.value == attempt.state.value == "certified"
            assert record.n_informative == attempt.n_informative
            assert record.n_iters == attempt.n_iters
            assert record.syndrome_ok == attempt.syndrome_ok
            assert record.crc_ok == attempt.crc_ok
            close = certificate_for_close(certificate, page.spec)
            assert np.array_equal(close.symbol, attempt.symbol_bits)
            assert close.metadata_bit == attempt.metadata_bit
            # ... and it is the generator's own truth, not just agreement
            index = page.index(ty, tx)
            assert np.array_equal(attempt.symbol_bits, page.symbols[index])
            assert attempt.metadata_bit == int(page.metadata_bits[index])
            assert attempt.counter == index


@pytest.mark.parametrize("format_ref", FORMATS)
def test_printed_field_reencode_is_identical(pages: dict[str, PageFixture],
                                             format_ref: str) -> None:
    """The certified-field substrate, byte-for-byte, against gen.compose."""
    from holo.receive.records import printed_cells_from_record

    page = pages[format_ref]
    for ty, tx in ((0, 0), (1, 2), (2, 1)):
        llr = _llr_from(page.tile(ty, tx))
        _record, certificate = _holo_attempt(page, llr, ty, tx,
                                             f"reencode-{format_ref}-{ty}{tx}")
        attempt = h2_tiles.attempt_k_tile(
            llr, page.fmt, (0, ty, tx), h2_tiles.AttemptStage.SCAN)
        left = printed_cells_from_record(certificate, page.spec)
        right = h2_tiles.printed_cells(page.fmt, attempt)
        assert np.array_equal(left, right)
        assert np.array_equal(right, page.tile(ty, tx))


# Deterministic flip ladders: a rung count, then unique positions from a
# fixed stride.  Chosen to bracket the cliff — the last rungs must FAIL on
# both sides, which is the half of the parity a clean corpus cannot show.
FLIP_LADDER = (0, 30, 120, 300, 700, 1400, 2400)


@pytest.mark.parametrize("format_ref", FORMATS)
def test_degraded_attempts_refuse_identically(pages: dict[str, PageFixture],
                                              format_ref: str) -> None:
    page = pages[format_ref]
    ty, tx = 1, 1
    tile = page.tile(ty, tx)
    outcomes: list[str] = []
    for n_flips in FLIP_LADDER:
        flips = np.unique((np.arange(n_flips, dtype=np.int64) * 1637) % 4096)
        llr = _llr_from(tile, flips)
        record, certificate = _holo_attempt(
            page, llr, ty, tx, f"deg-{format_ref}-{n_flips}")
        attempt = h2_tiles.attempt_k_tile(
            llr, page.fmt, (0, ty, tx), h2_tiles.AttemptStage.SCAN)
        assert record.state.value == attempt.state.value, n_flips
        assert record.n_informative == attempt.n_informative, n_flips
        assert record.n_iters == attempt.n_iters, n_flips
        assert record.syndrome_ok == attempt.syndrome_ok, n_flips
        assert record.crc_ok == attempt.crc_ok, n_flips
        if attempt.certified:
            close = certificate_for_close(certificate, page.spec)
            assert np.array_equal(close.symbol, attempt.symbol_bits)
        else:
            assert certificate is None and attempt.user_bits is None
        outcomes.append(attempt.state.value)
    assert outcomes[0] == "certified"
    assert outcomes[-1] == "attempted_failed"       # the ladder really falls


@pytest.mark.parametrize("format_ref", FORMATS)
def test_retry150_rung_agrees(pages: dict[str, PageFixture],
                              format_ref: str) -> None:
    """The second ladder rung is a different decoder, and says so."""
    page = pages[format_ref]
    flips = np.unique((np.arange(600, dtype=np.int64) * 1637) % 4096)
    llr = _llr_from(page.tile(0, 1), flips)
    record, _certificate = h_attempt_k_tile(
        llr, page.spec, (0, 0, 1), HAttemptStage.RETRY150,
        source_sha256=_ORACLE_SHA, lane_id="h3bis-oracle",
        component_block_ids=(hashlib.sha256(b"retry").hexdigest(),))
    attempt = h2_tiles.attempt_k_tile(
        llr, page.fmt, (0, 0, 1), h2_tiles.AttemptStage.RETRY150)
    assert record.state.value == attempt.state.value
    assert record.n_iters == attempt.n_iters
    assert attempt.decoder_profile == h_tiles.decoder_profile(
        page.spec.rate_id, h_tiles.RETRY_BP_MAX_ITERS, h_tiles.BP_ALPHA)


def test_below_floor_agrees(pages: dict[str, PageFixture]) -> None:
    page = pages["c2-k-r0700@12x12"]
    tile = page.tile(0, 0)
    nonsite = np.flatnonzero(
        ~h_tiles._geometry(page.spec).site_mask_yx.reshape(-1))
    llr = _llr_from(tile)
    llr.reshape(-1)[nonsite[h_tiles.k_eff_bits(page.spec) - 1:]] = 0.0
    record, certificate = _holo_attempt(page, llr, 0, 0, "floor")
    attempt = h2_tiles.attempt_k_tile(
        llr, page.fmt, (0, 0, 0), h2_tiles.AttemptStage.SCAN)
    assert record.state.value == attempt.state.value == "below_attempt_floor"
    assert certificate is None and attempt.user_bits is None
    assert record.n_informative == attempt.n_informative


def test_shared_decoder_constants() -> None:
    for name in ("TILE_CELLS", "N_CELLS", "BASELINE_BP_MAX_ITERS",
                 "RETRY_BP_MAX_ITERS", "BP_ALPHA"):
        assert getattr(h2_tiles, name) == getattr(h_tiles, name), name
    for name in ("LLR_KNOWN", "LLR_CLIP"):
        assert getattr(h2_ldpc_decode, name) == getattr(h_ldpc_decode,
                                                        name), name
    for name in ("TILE_CELLS", "N_CELLS", "CRC_BITS"):
        assert getattr(h2_ldpc_tile, name) == getattr(h_ldpc_tile, name), name
    for name in ("N_QUOTA", "N_WORD_SITES", "COUNTER_BITS", "PAD_BITS",
                 "MESSAGE_BITS", "PLANE_K", "TILE_CELLS"):
        assert getattr(h2_pilots, name) == getattr(h_pilots, name), name
    assert np.array_equal(h2_pilots._QUOTA_EDGES, h_pilots._QUOTA_EDGES)
    assert np.array_equal(h2_pilots._QUOTA_SPANS, h_pilots._QUOTA_SPANS)
    for name in ("DOMAIN_PAYLOAD", "DOMAIN_PILOT_VALUES",
                 "DOMAIN_FILLER_VALUES", "DOMAIN_PILOT_SITES",
                 "DOMAIN_FILLER_SITES", "DOMAIN_SLOT_PERM", "PLANE_K"):
        assert getattr(h2_keystream, name) == getattr(h_keystream, name), name


def test_carried_keystream_domains_draw_the_same_bits() -> None:
    seed = b"holo/v1/c2-r0700/3392x2368"
    yy = np.repeat(np.arange(64, dtype=np.int64), 64)
    xx = np.tile(np.arange(64, dtype=np.int64), 64)
    for domain in (h_keystream.DOMAIN_PAYLOAD,
                   h_keystream.DOMAIN_FILLER_VALUES):
        assert np.array_equal(
            h_keystream.bits(seed, domain, 3, 0, yy, xx),
            h2_keystream.bits(seed, domain, 3, 0, yy, xx))
    for bound in (2, 6, 7, 100, 256):
        u = np.arange(200, dtype=np.int64)
        assert np.array_equal(
            h_keystream.bounded_draws(seed, h_keystream.DOMAIN_PILOT_SITES,
                                      u, bound),
            h2_keystream.bounded_draws(seed, h2_keystream.DOMAIN_PILOT_SITES,
                                       u, bound))


# ------------------------------------------------- (e) carry fidelity

CARRY_PAIRS = (
    ("holo.core.bch", "holo2.format.bch"),
    ("holo.format.pilots", "holo2.format.pilots"),
    ("holo.core.ldpc.construct", "holo2.format.ldpc.construct"),
    ("holo.core.ldpc.decode", "holo2.format.ldpc.decode"),
    ("holo.core.ldpc.tile", "holo2.format.ldpc.tile"),
    ("holo.receive.detect", "holo2.solve.detect"),
    ("holo.receive.tiles", "holo2.solve.tiles"),
)

# Deliberate, reviewed deviations (H3bis).  A NEW entry appearing in a
# failure is a decision to make, not a line to add reflexively: either the
# carry drifted (fix it) or the divergence is intended (record it here).
NOT_CARRIED = {
    # the COLOR surface: dust sites, color word states, dust schedules.
    # It needs the codec-profile registry and belongs with the color
    # leaves (H7); carrying it now would buy nothing for a K decode.
    "holo.format.pilots": {
        "color_payload_cell_indices", "color_site_cells_yx",
        "color_word_states", "decode_color_word", "dust_site_cells_yx",
        "dust_state_values"},
    # v1's DURABLE-IDENTITY machinery.  holo2 names an attempt by its
    # read-set (identity.py, DESIGN §7) and a certificate by its
    # (key, version) in the store, so carrying the E023b/E023c hash
    # family would install a second source of truth for the same fact.
    # ``CertifiedSymbolConflict`` is not here because it carries no code —
    # the class itself lives in holo2.fountain_close (H2b).
    "holo.receive.tiles": {
        "attempt_identity", "dependency_identity", "sha256_parts_be",
        "sha256_parts_le"},
}

HOLO2_ONLY = {
    # the adapted record boundary (see ADAPTED_ELSEWHERE) and the three
    # helpers that turn one transient attempt into DESIGN §5.2 content.
    # ``printed_cells_for`` (H5 P2) is the DURABLE-side door of
    # ``printed_cells``: a committed TileRecord keeps the metadata bit and
    # a blob ref, never the attempt, so the label harvest reassembles the
    # user bits and asks by ADDRESS.  v1's equivalent is
    # ``holo.receive.records.printed_cells_from_record`` — a different
    # module, and one whose durable-identity machinery is NOT_CARRIED
    # above — so this pair is holo2-only here and byte-compared against
    # v1 in ``test_oracle_certified_labels.py`` instead.
    "holo2.solve.tiles": {"attempt_k_tile", "certified_tile_record",
                    "printed_cells", "printed_cells_for"},
}
HOLO2_ONLY_PREFIXES = {"holo2.solve.tiles": ("TileAttempt.",)}
RENAMED_SYMBOLS = {
    # v1's FormatSpec restricted to the tile chain's surface (§5 of the
    # holo2 format module), exactly as the close restricted it to CloseSpec
    "holo.receive.tiles": {"FormatSpec": "TileFormat"},
}

# Carried from a DIFFERENT origin module and adapted at the record
# boundary only — the numerics are compared in test (d) above, tile by
# tile, on real generator pages and on the degraded ladder.
ADAPTED_ELSEWHERE = {
    ("holo.receive.payload", "attempt_k_tile"): ("holo2.solve.tiles",
                                                 "attempt_k_tile"),
}


def _function_sources(module_name: str) -> dict[str, str]:
    """Every def in a module, unparsed, with docstrings removed."""
    tree = ast.parse(inspect.getsource(importlib.import_module(module_name)))
    out: dict[str, str] = {}

    def strip_doc(node):
        node = copy.deepcopy(node)
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            node.body = node.body[1:] or [ast.Pass()]
        return node

    def walk(parent, prefix=""):
        for child in parent.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[prefix + child.name] = ast.unparse(strip_doc(child))
            elif isinstance(child, ast.ClassDef):
                walk(child, prefix + child.name + ".")

    walk(tree)
    return out


ORIGIN_MOVED: dict[str, str] = {}


@pytest.mark.parametrize("origin,carried", CARRY_PAIRS,
                         ids=[pair[1] for pair in CARRY_PAIRS])


def test_carried_code_is_the_original_code(origin: str, carried: str) -> None:
    """Every shared function is the ORIGINAL, character for character.

    The numerical tests above prove the two chains agree on the fixtures
    they run; this proves there is no third behaviour hiding on an
    untested branch.  Docstrings are stripped and the renamed types
    normalised; nothing else may differ.
    """
    left = _function_sources(origin)
    right = _function_sources(carried)
    renames = RENAMED_SYMBOLS.get(origin, {})

    missing = set(left) - set(right) - NOT_CARRIED.get(origin, set())

    prefixes = HOLO2_ONLY_PREFIXES.get(carried, ())
    extra = {
        name for name in set(right) - set(left)
        if not name.startswith(prefixes)
        and name not in HOLO2_ONLY.get(carried, set())
    }

    drifted = []
    for name in sorted(set(left) & set(right)):
        source = left[name]
        for old, new in renames.items():
            source = source.replace(old, new)
        if source != right[name]:
            drifted.append(name)

    # The tripwire gate reinterprets the SAME comparison — a declared-
    # moved origin must still show a divergence the oracle would flag,
    # otherwise the entry is stale and must retire loudly.  (Comparing
    # raw sources here would be wrong: a rename-bearing pair never goes
    # raw-equal, so a synced pair would skip forever.)
    if carried in ORIGIN_MOVED:
        assert missing or extra or drifted, (
            f"{origin} no longer diverges from {carried}: the sync has "
            "landed — delete this ORIGIN_MOVED entry and let the carry "
            "oracle re-arm")
        pytest.skip(f"origin moved ({ORIGIN_MOVED[carried]}); holo2 keeps "
                    "its carry until the declared sync lands")

    assert not missing, f"{carried} silently dropped {sorted(missing)}"
    assert not extra, f"{carried} grew unreviewed code {sorted(extra)}"
    assert not drifted, (
        f"{carried} diverged from {origin} in {drifted} — decide whether "
        "the carry drifted or the divergence is intended, then record it")


@pytest.mark.parametrize("key", sorted(ADAPTED_ELSEWHERE),
                         ids=lambda key: f"{key[0]}:{key[1]}")
def test_adapted_leaves_exist_on_both_sides(key) -> None:
    """An adapted carry is exempt from the AST compare, not from existing.

    Its numerics are pinned behaviourally instead (test (d)); this only
    stops the declaration from silently outliving the function.
    """
    origin_module, origin_name = key
    carried_module, carried_name = ADAPTED_ELSEWHERE[key]
    assert origin_name in _function_sources(origin_module)
    assert carried_name in _function_sources(carried_module)


def test_the_ldpc_data_is_byte_identical() -> None:
    """The frozen mother codes ARE the format; the copies must be copies.

    G3 (rung parity, 2026-08-22): the carried set is the WHOLE ladder now
    — r0547/r0625/r0775/r0850 joined r0550/r0700 so the six-row
    ``LADDER`` in ``format_v1``/``construct.py`` is no longer a promise
    holo2 only half keeps. Six names, not two: pinning the exact list
    (not just its length) catches a dropped or partial copy that a
    length-only check would miss.
    """
    from pathlib import Path

    holo_dir = Path(inspect.getfile(h_construct)).parent / "data"
    holo2_dir = Path(inspect.getfile(h2_construct)).parent / "data"
    carried = sorted(path.name for path in holo2_dir.glob("*.json"))
    assert carried == ["r0547.json", "r0550.json", "r0625.json",
                       "r0700.json", "r0775.json", "r0850.json"]
    for name in carried:
        left = (holo_dir / name).read_bytes()
        right = (holo2_dir / name).read_bytes()
        assert hashlib.sha256(left).hexdigest() == \
            hashlib.sha256(right).hexdigest(), name
        assert left == right


@pytest.mark.parametrize("carried", [pair[1] for pair in CARRY_PAIRS])
def test_carried_modules_import_nothing_from_holo(carried: str) -> None:
    tree = ast.parse(inspect.getsource(importlib.import_module(carried)))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    assert not (roots & {"holo", "paperholo", "experiments"}), carried
