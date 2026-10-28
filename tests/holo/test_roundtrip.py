"""End-to-end integration: payload -> gen -> clean-channel decode -> payload.

The reference decode here works from the composed CELL field with known
geometry (no acquisition — that is track 3); it exercises every format
layer: words, addressed metadata equations, slot-permuted LDPC tiles, fountain,
envelope. Byte-exact or bust.
"""
import hashlib

import numpy as np


from holo.core import fountain, keystream
from holo.core.ldpc import tile as ldpc_tile
from holo.format import envelope, metadata, pilots
from holo.devices.profiles import make_spec
from holo.gen import compose, emit, plan

ROW = make_spec("c3-r0550")
PAYLOAD = hashlib.sha256(b"holo-roundtrip").digest() * 160  # 5,120 bytes
Q = 0.35

# GOLDEN (bump-don't-edit): sha256 of np.packbits(page-0 cell field) for
# the fixture above — pins the ENTIRE compose stack (sites, words,
# scrambles, slot perms, LDPC, fountain, metadata, envelope). A mismatch
# is a format fork, never a test to update without an explicit design
# amendment. Re-frozen 2026-07-21 by §13.16: metadata changed in place from
# counter-mod-24 copies to one-bit LFSR-addressed equations.
GOLDEN_PAGE0_CELLS = ("9513732c2f72ede3d7e60b40b0fb1a57"
                      "a931de5e1ff40fabb76cda86d7c630e1")
GOLDEN_C2_R0700_PAGE0 = ("9231bbe836d07062fd1d3a2a645f22aa"
                         "c1929e3c6cf04ebd21e57a0f0c5f5397")
GOLDEN_C2_R0550_PAGE0 = ("714f9dd6a8a6c50bf8b40e1304f8b067"
                         "3f6c95bb22bd6a9d6ec95b4e67092235")


def _compose_pages(row, payload, q, pages=(0,)):
    vplan = plan.plan_volume(row, len(payload), q)
    src = emit.source_packed_for(payload, vplan)
    vc = fountain.VolumeCode(vplan.k_total, vplan.symbol_bits, row.seed,
                             tiles_per_page=row.tiles_per_page)
    tpp = row.tiles_per_page
    out = {}
    for page in pages:
        esis = np.arange(page * tpp, (page + 1) * tpp, dtype=np.int64)
        symbols = vc.encode_symbols(src, esis)
        out[page] = compose.compose_page_cells(row, page, symbols,
                                               vplan.k_total)
    return vplan, out


def _compose_first_page():
    vplan, cells = _compose_pages(ROW, PAYLOAD, Q)
    return vplan, cells[0]


def reference_decode_page(cells: np.ndarray, row, page: int = 0,
                          observations: list[tuple[int, int]] | None = None
                          ) -> tuple:
    """Known-geometry clean-channel decode of one page's cell field.
    Returns (counters_ok, observations, dict esi->symbol_bits); pass the
    observations list to accumulate addressed metadata across pages."""
    tys, txs = row.layout.tiles_yx
    site_flat = pilots.site_cell_indices(row.family_seed, row.n_filler)
    word_cells = pilots.word_site_cells_yx(row.family_seed)
    t_slots = row.n_transmitted_slots
    scramble = keystream.payload_bits(row.seed, row.plane, page,
                                      row.layout.cells_yx)
    site_mask = np.zeros(4096, dtype=bool)
    site_mask[site_flat] = True

    if observations is None:
        observations = []
    symbols: dict[int, np.ndarray] = {}
    words_ok = 0
    for ty in range(tys):
        for tx in range(txs):
            tile = cells[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
            wv = tile[word_cells[:, 0], word_cells[:, 1]]
            counter = pilots.decode_word(wv, row.seed, row.plane)
            assert counter is not None
            assert row.tile_address(counter) == (page, ty, tx)
            words_ok += 1
            scr = scramble[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
            descr = (tile ^ (scr & ~site_mask.reshape(64, 64))).ravel()
            llr = np.where(site_mask, 0.0,
                           (descr.astype(np.float64) * 2 - 1) * 5.0)
            a, b = keystream.slot_perm_params(row.seed, counter, t_slots)
            fr = ldpc_tile.decode_tile(llr, row.rate_id, site_flat,
                                       int(a[0]), int(b[0]))
            assert fr.ok
            mbit = int(fr.user_bits[0])
            observations.append((counter, mbit))
            symbols[counter] = fr.user_bits[1:]
    return words_ok, observations, symbols


def test_compose_page_golden():
    _, cells = _compose_first_page()
    digest = hashlib.sha256(np.packbits(cells).tobytes()).hexdigest()
    assert digest == GOLDEN_PAGE0_CELLS, "format fork — see comment above"


def _fountain_close(symbols: dict, md, symbol_bits: int, row,
                    drop_frac: float, payload: bytes) -> None:
    dec = fountain.Decoder(
        fountain.VolumeCode(md.k, symbol_bits, row.seed,
                            tiles_per_page=row.tiles_per_page))
    rng = np.random.default_rng(11)
    esis = np.array(sorted(symbols))
    keep = rng.random(esis.size) > drop_frac
    for esi in esis[keep]:
        dec.add_symbol(int(esi), symbols[int(esi)])
    src = dec.try_solve()
    assert src is not None
    assert envelope.unwrap(np.packbits(src.ravel()).tobytes()) == payload


def test_roundtrip_byte_exact():
    vplan, cells = _compose_first_page()
    assert vplan.n_pages == 1 and vplan.k_total < ROW.tiles_per_page
    words_ok, observations, symbols = reference_decode_page(cells, ROW)
    assert words_ok == ROW.tiles_per_page
    md = metadata.decode_metadata(observations)
    assert md.ok and md.version == 0 and md.k == vplan.k_total
    # drop 30% of tiles at random to prove repair works
    _fountain_close(symbols, md, vplan.symbol_bits, ROW, 0.30, PAYLOAD)


def test_multipage_roundtrip_byte_exact():
    """Pages >= 1: page-keyed scramble, page-offset counters, metadata
    equations across pages, fountain spanning the page boundary."""
    payload = hashlib.sha256(b"holo-multipage").digest() * 7000  # 224,000 B
    vplan, pages = _compose_pages(ROW, payload, 0.55, pages=(0, 1))
    # source symbols SPAN the page boundary (K=851 > 840 tiles/page)
    assert vplan.n_pages == 2 and vplan.k_total > ROW.tiles_per_page
    observations = None
    symbols: dict[int, np.ndarray] = {}
    for page, cells in pages.items():
        n_ok, observations, syms = reference_decode_page(
            cells, ROW, page=page, observations=observations)
        assert n_ok == ROW.tiles_per_page
        symbols.update(syms)
    md = metadata.decode_metadata(observations)
    assert md.ok and md.version == 0 and md.k == vplan.k_total
    _fountain_close(symbols, md, vplan.symbol_bits, ROW, 0.15, payload)


def test_c2_r0700_roundtrip_byte_exact():
    """The c2 geometry (52x36 tiles) + the r0700 rung through the whole
    stack — the 'max' profile's row."""
    row = make_spec("c2-r0700")
    payload = hashlib.sha256(b"holo-c2").digest() * 320  # 10,240 bytes
    vplan, pages = _compose_pages(row, payload, 0.75, pages=(0,))
    digest = hashlib.sha256(np.packbits(pages[0]).tobytes()).hexdigest()
    assert digest == GOLDEN_C2_R0700_PAGE0, "format fork"
    n_ok, observations, symbols = reference_decode_page(pages[0], row)
    assert n_ok == row.tiles_per_page
    md = metadata.decode_metadata(observations)
    assert md.ok and md.k == vplan.k_total
    _fountain_close(symbols, md, vplan.symbol_bits, row, 0.20, payload)


def test_c2_r0550_compose_golden():
    row = make_spec("c2-r0550")
    payload = hashlib.sha256(b"holo-c2-r0550").digest() * 32
    _, pages = _compose_pages(row, payload, 0.70, pages=(0,))
    digest = hashlib.sha256(np.packbits(pages[0]).tobytes()).hexdigest()
    assert digest == GOLDEN_C2_R0550_PAGE0, "format fork"


def test_wrong_geometry_hypothesis_refuses_at_word_gate():
    _, cells = _compose_first_page()
    wrong = make_spec("c2-r0550")   # different geometry row
    word_cells = pilots.word_site_cells_yx(ROW.family_seed)
    refused = 0
    for ty, tx in ((0, 0), (3, 5), (17, 11), (34, 23)):
        tile = cells[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
        wv = tile[word_cells[:, 0], word_cells[:, 1]]
        if pilots.decode_word(wv, wrong.seed, wrong.plane) is None:
            refused += 1
    assert refused == 4


def test_metadata_bit_survives_in_every_tile():
    vplan, cells = _compose_first_page()
    _, observations, _ = reference_decode_page(cells, ROW)
    md = metadata.decode_metadata(observations)
    word = metadata.encode_metadata(0, vplan.k_total)
    assert md.ok and md.n_unique_counters == ROW.tiles_per_page
    assert all(bit == metadata.tile_bit(word, counter)
               for counter, bit in observations)
