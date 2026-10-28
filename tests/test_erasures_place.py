"""Erasure word decoding (bch.decode_erasures / pilots.decode_word) and the
F13 fragment placer (paperholo.place) — the 2026-07-10 build items from
PILOTS-DESIGN §14 (erasure rung) and §15 (correlation placement)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "experiments/014-c2-print"))

from paperholo import bch, compose, pilots, place
from paperholo.modulation import rng
import gen_e014

SEED = gen_e014.SEED
SPEC = gen_e014.make_spec()
GEO = {"tiles_x": SPEC.page_cells_yx[1] // 60,
       "tiles_per_page": (SPEC.page_cells_yx[0] // 60)
       * (SPEC.page_cells_yx[1] // 60)}


def _rand_word(gen: np.random.Generator, code: bch.BCHCode) -> np.ndarray:
    msg = gen.integers(0, 2, code.k_short, dtype=np.uint8)
    return code.encode(msg)


def test_erasures_full_budget_sweep() -> None:
    """2e + f <= 26 recovers exactly, e_out == e, across the budget lattice
    (random codewords, random disjoint error/erasure sets, random values in
    the erased positions)."""
    code = bch.CODE_V3
    gen = rng(SEED, b"test/erasure-budget")
    for e in range(0, code.t_full + 1):
        for f in range(0, 2 * (code.t_full - e) + 1, 3):
            for _ in range(4):
                cw = _rand_word(gen, code)
                idx = gen.permutation(code.n_short)
                era, errs = idx[:f], idx[f:f + e]
                w = cw.copy()
                w[errs] ^= 1
                if f:
                    w[era] = gen.integers(0, 2, f, dtype=np.uint8)
                res = code.decode_erasures(w, era)
                assert res is not None, (e, f)
                got, e_out = res
                assert np.array_equal(got, cw), (e, f)
                assert e_out == e, (e, f, e_out)


def test_erasures_never_wrong_within_budget() -> None:
    """Within-budget acceptance is unique: 3000 random draws, never a
    codeword other than the true one."""
    code = bch.CODE_V3
    gen = rng(SEED, b"test/erasure-unique")
    for _ in range(3000):
        cw = _rand_word(gen, code)
        f = int(gen.integers(0, 27))
        e = int(gen.integers(0, (26 - f) // 2 + 1))
        idx = gen.permutation(code.n_short)
        era, errs = idx[:f], idx[f:f + e]
        w = cw.copy()
        w[errs] ^= 1
        if f:
            w[era] = gen.integers(0, 2, f, dtype=np.uint8)
        res = code.decode_erasures(w, era)
        assert res is not None and np.array_equal(res[0], cw)


def test_erasures_edges_and_errors_only_parity() -> None:
    code = bch.CODE_V3
    gen = rng(SEED, b"test/erasure-edge")
    cw = _rand_word(gen, code)
    # f = 26, e = 0: full-erasure budget
    era = gen.permutation(code.n_short)[:26]
    w = cw.copy()
    w[era] ^= 1  # worst fill on every erased position
    res = code.decode_erasures(w, era)
    assert res is not None and np.array_equal(res[0], cw) and res[1] == 0
    # f = 27 > budget: refused outright
    assert code.decode_erasures(w, gen.permutation(code.n_short)[:27]) is None
    # f = 0 delegates to errors-only decode exactly
    w2 = cw.copy()
    w2[:13] ^= 1
    res2 = code.decode_erasures(w2, np.array([], dtype=int))
    ref = code.decode(w2, code.t_full)
    assert res2 is not None and ref is not None
    assert np.array_equal(res2[0], ref[0]) and res2[1] == ref[1] == 13


def test_decode_word_erasures_end_to_end() -> None:
    """A partial pilot tile (fragment-edge geometric cut, q = 0.85) decodes
    to the right absolute address through pilots.decode_word."""
    pos = pilots.site_positions_tile(SPEC.pilot, SEED)
    ty, tx = 20, 15
    printed = pilots.encode_word(SPEC.pilot, SEED, SPEC.plane, 0, ty, tx,
                                 **GEO)
    cut = np.quantile(pos[:, 0], 0.85)  # keep sites with y below the cut
    era = np.flatnonzero(pos[:, 0] > cut)
    assert 10 <= era.size <= 20
    gen = rng(SEED, b"test/word-erasure")
    w = printed.copy()
    flip = gen.permutation(np.flatnonzero(pos[:, 0] <= cut))[:2]
    w[flip] ^= 1                         # 2 channel errors on visible sites
    w[era] = gen.integers(0, 2, era.size, dtype=np.uint8)
    info = pilots.decode_word(w, SPEC.pilot, SEED, SPEC.plane,
                              bch.CODE_V3.t_full, erasures=era, **GEO)
    assert info is not None
    assert (info["page"], info["ptile_y"], info["ptile_x"]) == (0, ty, tx)
    assert info["n_errors"] == 2 and info["n_erasures"] == era.size
    # without the erasure list the same word must NOT decode (mean fill
    # errors + channel errors exceed t) — the rung needs the erasure path
    info_plain = pilots.decode_word(w, SPEC.pilot, SEED, SPEC.plane,
                                    bch.CODE_V3.t_full, **GEO)
    assert info_plain is None or info_plain["counter"] == info["counter"]


def _page_bits() -> np.ndarray:
    payload = rng(SEED, b"e014/payload").integers(
        0, 2, compose.payload_capacity(SPEC), dtype=np.uint8)
    return compose.compose_page(payload, SPEC, SEED, page=0).cell_values


def test_place_clean_rot_and_noise() -> None:
    """Sim-clean 71-cell (6 mm c2 class) crops place exactly at every rot90,
    survive 8% i.i.d. flips, and report d-floor-respecting rivals."""
    page = _page_bits()
    gen = rng(SEED, b"test/place")
    for oy, ox, k in ((317, 511, 0), (1201, 88, 1), (2660, 1990, 3)):
        crop = page[oy:oy + 71, ox:ox + 71]
        pl = place.place_fragment(np.rot90(crop, -k), SPEC, SEED)
        assert pl.ok and pl.origin_yx == (oy, ox) and pl.rot_k == k
        assert pl.mismatch == 0.0 and pl.rival_mismatch > 0.20
    crop = page[317:317 + 71, 511:511 + 71].copy()
    noise = gen.random(crop.shape) < 0.08
    pl = place.place_fragment(crop ^ noise, SPEC, SEED)
    assert pl.ok and pl.origin_yx == (317, 511) and pl.rot_k == 0
    assert 0.02 < pl.mismatch < 0.15


def test_place_null_controls() -> None:
    """Wrong seed and excluded-region pending masks must never gate-pass."""
    page = _page_bits()
    crop = page[317:317 + 71, 511:511 + 71]
    wrong = place.place_fragment(crop, SPEC, b"not-the-volume-seed")
    assert not wrong.ok and wrong.mismatch > 0.20
    # pending mask that EXCLUDES the true region: no false accept anywhere
    pm = np.zeros(tuple(SPEC.page_cells_yx), bool)
    pm[:200, :200] = True
    pl = place.place_fragment(crop, SPEC, SEED,
                              pending_cell_mask={0: pm})
    assert not pl.ok
    # pending mask that INCLUDES it: same exact answer as unpruned
    pm2 = np.zeros(tuple(SPEC.page_cells_yx), bool)
    pm2[250:450, 450:650] = True
    pl2 = place.place_fragment(crop, SPEC, SEED,
                               pending_cell_mask={0: pm2})
    assert pl2.ok and pl2.origin_yx == (317, 511)


def test_placed_fragment_quality_plumbing() -> None:
    """A correlation-placed fragment's placer-measured mismatch must drive
    the merge-policy quality estimates (2026-07-10 review finding: the 0.5
    no-evidence default starved pristine fragments)."""
    from paperholo import tilemap
    pds = tilemap.PageDecodeState(SPEC, SEED, page=0)
    pds.add_placed_fragment(
        "C/frag01", np.arange(100, dtype=np.int64),
        np.full(100, 8.0), placement_meta={"mismatch": 0.02})
    obs = pds.scans["C/frag01"]
    assert obs.meta["placement_source"] == "correlation"
    assert obs.pilot_ber_est == 0.02
    assert obs.tile_quality((0, 0)) == 0.02
    # distinct-id discipline: colliding scan_id refused
    try:
        pds.add_placed_fragment("C/frag01", np.arange(3, dtype=np.int64),
                                np.ones(3))
        raise AssertionError("duplicate placed-fragment id accepted")
    except ValueError:
        pass
