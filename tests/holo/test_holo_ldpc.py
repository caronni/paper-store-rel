"""holo inner FEC: frozen ladder pins, mother-code + tile round trips,
CRC certification, slot-permutation cell map (HOLO-DESIGN §3 F5, §4.4)."""


import numpy as np
import pytest

from holo.core import keystream
from holo.core.ldpc import construct, tile
from holo.core.ldpc.decode import decode, encode

SEED = b"holo/v1/c2-r0550/3328x2304"
RATE = "r0550"
N_SITES = 100
T = tile.N_CELLS - N_SITES           # 3996


def _site_cells(rng: np.random.Generator, n: int = N_SITES) -> np.ndarray:
    return np.sort(rng.choice(tile.N_CELLS, size=n, replace=False))


def _perm_params(tile_counter: int) -> tuple[int, int]:
    a, b = keystream.slot_perm_params(SEED, [tile_counter], T)
    return int(a[0]), int(b[0])


def _clean_tile(seed_int: int = 7):
    rng = np.random.default_rng(seed_int)
    sc = _site_cells(rng)
    a_t, b_t = _perm_params(0)
    user = rng.integers(0, 2, tile.tile_capacity(RATE, N_SITES),
                        dtype=np.uint8)
    cells = tile.encode_tile(user, RATE, sc, a_t, b_t)
    llr = (2.0 * cells - 1.0) * 8.0
    return sc, a_t, b_t, user, cells, llr


# GOLDEN EDGE DIGESTS (bump-don't-edit): sha256 over the canonical
# little-endian ('<i4') lexsorted edge arrays, chk bytes then var bytes.
# These pin the six frozen mother codes EXTERNALLY (the npz-internal
# edge_sha field is ignored — a hash stored beside the data it protects
# guards nothing). Values equal the historical paperholo H anchors.
GOLDEN_EDGES = {
    "r0547": "4cf6774a8fd3ed6d16878880f89778de"
             "172a6e3ed749e6f444537e726f4c9371",
    "r0550": "54c72b395776dd1aba2c65dfa49b1e3b"
             "9f7e4010266c477a6079b1d214ef477e",
    "r0625": "e98e65155f4e625f185fc202060d2bba"
             "4b6f23b70ad3786990ff77c0f059fb71",
    "r0700": "b1ef32ed91a17b6d74a20c3f0a415889"
             "aa1b0bae767b6c484bfee35b5c3e5913",
    "r0775": "8b0ec36d6bcad660056020e25bc196aa"
             "c749c7374ccbd576919369407eff0712",
    "r0850": "4be74ca98de10596d556d756914eaa45"
             "538fd22a78b5fee8d128dbcb22da33c7",
}


def test_ladder_loads_all_six_rungs_verified():
    import hashlib
    for rid, spec in construct.LADDER.items():
        code = construct.load_code(rid)
        assert code.spec is spec
        assert code.n_edges > 0
        assert code.chk_starts.size == spec.m_bits
        assert code.var_starts.size == spec.n_bits
        # decode-order invariant: edges lexsorted by (chk, var)
        assert (np.diff(code.edge_chk) >= 0).all()
        digest = hashlib.sha256(
            code.edge_chk.astype("<i4").tobytes()
            + code.edge_var.astype("<i4").tobytes()).hexdigest()
        assert digest == GOLDEN_EDGES[rid], f"{rid}: format fork"
        # cached: second load is the same object
        assert construct.load_code(rid) is code


def test_malformed_data_fails_loudly(tmp_path):
    import json
    doc = json.loads(
        (construct._DATA_DIR / f"{RATE}.json").read_text())

    def write(mutate):
        bad = json.loads(json.dumps(doc))     # deep copy
        mutate(bad)
        (tmp_path / f"{RATE}.json").write_text(json.dumps(bad))

    # structural: a non-permutation interleaver is refused
    write(lambda d: d["pi"].__setitem__(0, d["pi"][1]))
    with pytest.raises(ValueError, match="not a permutation"):
        construct.load_code(RATE, data_dir=tmp_path)
    # structural: out-of-range block row
    write(lambda d: d["heavy_rows"][0].__setitem__(0, 999))
    with pytest.raises(ValueError, match="out of range"):
        construct.load_code(RATE, data_dir=tmp_path)
    # geometry pin: k_bits disagreement
    write(lambda d: d.__setitem__("k_bits", 2304))
    with pytest.raises(ValueError, match="k_bits"):
        construct.load_code(RATE, data_dir=tmp_path)


def test_mother_code_clean_roundtrip_all_rungs():
    rng = np.random.default_rng(1)
    for rid, spec in construct.LADDER.items():
        code = construct.load_code(rid)
        info = rng.integers(0, 2, spec.k_bits, dtype=np.uint8)
        cw = encode(info, rid)
        assert cw.shape == (spec.n_bits,)
        assert np.array_equal(cw[:spec.k_bits], info)
        # valid codeword by direct syndrome over the edge arrays
        syn = np.bitwise_xor.reduceat(cw[code.edge_var], code.chk_starts)
        assert not syn.any()
        ok, hard, n_iters = decode((2.0 * cw - 1.0) * 8.0, rid)
        assert ok and n_iters == 0
        assert np.array_equal(hard, cw)


def test_capacity_formula():
    assert tile.tile_capacity("r0550", 100) == 2108
    assert tile.tile_capacity("r0850", 100) == 3520 - 32 - 100
    with pytest.raises(ValueError, match="no capacity"):
        tile.tile_capacity("r0550", 2240 - 32)


def test_transmitted_positions_info_tail_shortening():
    pos = tile.transmitted_positions(RATE, N_SITES)
    k = construct.LADDER[RATE].k_bits
    assert pos.size == T
    assert np.array_equal(pos[:k - N_SITES], np.arange(k - N_SITES))
    assert np.array_equal(pos[k - N_SITES:], np.arange(k, tile.N_CELLS))


def test_cell_map_bijective_identity_and_keyed():
    rng = np.random.default_rng(2)
    sc = _site_cells(rng)
    nonsite = np.setdiff1d(np.arange(tile.N_CELLS), sc)
    # identity params: raster order of the non-site cells
    assert np.array_equal(tile.cell_map(sc, 1, 0), nonsite)
    # keystream-drawn params: a permutation of exactly the non-site cells
    a0, b0 = _perm_params(0)
    a1, b1 = _perm_params(1)
    m0 = tile.cell_map(sc, a0, b0)
    m1 = tile.cell_map(sc, a1, b1)
    assert np.array_equal(np.sort(m0), nonsite)
    assert np.array_equal(np.sort(m1), nonsite)
    assert (a0, b0) != (a1, b1) and not np.array_equal(m0, m1)


def test_cell_map_rejects_bad_params():
    rng = np.random.default_rng(3)
    sc = _site_cells(rng)
    with pytest.raises(ValueError, match="coprime"):
        tile.cell_map(sc, 2, 0)             # T = 3996 is even
    with pytest.raises(ValueError, match="out of range"):
        tile.cell_map(sc, 1, T)
    with pytest.raises(ValueError, match="strictly increasing"):
        tile.cell_map(sc[::-1], 1, 0)


def test_tile_clean_roundtrip():
    sc, a_t, b_t, user, cells, llr = _clean_tile()
    assert cells.dtype == np.uint8 and cells.shape == (tile.N_CELLS,)
    assert not cells[sc].any()              # site cells left 0
    res = tile.decode_tile(llr, RATE, sc, a_t, b_t)
    assert res.ok and res.syndrome_ok and res.crc_ok
    assert res.n_iters == 0
    assert np.array_equal(res.user_bits, user)


def test_tile_noisy_roundtrip():
    sc, a_t, b_t, user, _, llr = _clean_tile(11)
    rng = np.random.default_rng(12)
    cmap = tile.cell_map(sc, a_t, b_t)
    flips = rng.choice(cmap, size=int(round(0.015 * cmap.size)),
                       replace=False)
    llr[flips] *= -1.0
    res = tile.decode_tile(llr, RATE, sc, a_t, b_t)
    assert res.ok and res.n_iters > 0
    assert np.array_equal(res.user_bits, user)


def test_tile_erasure_roundtrip():
    sc, a_t, b_t, user, _, llr = _clean_tile(13)
    rng = np.random.default_rng(14)
    erased = rng.choice(tile.N_CELLS, size=int(0.30 * tile.N_CELLS),
                        replace=False)
    llr[erased] = 0.0
    res = tile.decode_tile(llr, RATE, sc, a_t, b_t)
    assert res.ok
    assert np.array_equal(res.user_bits, user)


def test_crc_catches_syndrome_valid_wrong_decode():
    # A valid LDPC codeword whose CRC field belongs to DIFFERENT user bits:
    # syndrome passes instantly, CRC must refuse certification.
    rng = np.random.default_rng(21)
    sc = _site_cells(rng)
    a_t, b_t = _perm_params(0)
    cap = tile.tile_capacity(RATE, N_SITES)
    user = rng.integers(0, 2, cap, dtype=np.uint8)
    wrong = user.copy()
    wrong[0] ^= 1
    k = construct.LADDER[RATE].k_bits
    info = np.zeros(k, np.uint8)
    info[:cap] = wrong
    info[cap:cap + tile.CRC_BITS] = tile.crc32_bits(user)   # stale CRC
    cw = encode(info, RATE)
    cells = np.zeros(tile.N_CELLS, np.uint8)
    cells[tile.cell_map(sc, a_t, b_t)] = \
        cw[tile.transmitted_positions(RATE, N_SITES)]
    res = tile.decode_tile((2.0 * cells - 1.0) * 8.0, RATE, sc, a_t, b_t)
    assert res.syndrome_ok and not res.crc_ok
    assert not res.ok and res.user_bits is None


def test_corrupt_beyond_correction_refuses():
    sc, a_t, b_t, _, _, llr = _clean_tile(31)
    rng = np.random.default_rng(32)
    cmap = tile.cell_map(sc, a_t, b_t)
    flips = rng.choice(cmap, size=int(0.25 * cmap.size), replace=False)
    llr[flips] *= -1.0
    res = tile.decode_tile(llr, RATE, sc, a_t, b_t)
    assert not res.ok and res.user_bits is None


def test_decode_soft_extrinsic_is_the_graph_contribution():
    """P3 needs the decoder's own soft output, and nothing else to change."""
    from holo.core.ldpc.decode import LLR_CLIP, decode_soft

    rng = np.random.default_rng(9091)
    info = rng.integers(0, 2, construct.LADDER[RATE].k_bits, dtype=np.uint8)
    codeword = encode(info, RATE)
    llr = np.where(codeword == 1, 3.0, -3.0)
    flip = rng.choice(llr.size, size=llr.size // 40, replace=False)
    llr[flip] *= -1.0

    ok, hard, iters = decode(llr, RATE, max_iters=60)
    soft_ok, soft_hard, soft_iters, extrinsic = decode_soft(
        llr, RATE, max_iters=60)
    assert (soft_ok, soft_iters) == (ok, iters)
    assert np.array_equal(soft_hard, hard)
    assert extrinsic.shape == llr.shape
    assert np.isfinite(extrinsic).all()

    posterior = np.clip(llr, -LLR_CLIP, LLR_CLIP) + extrinsic
    assert np.array_equal((posterior > 0).astype(np.uint8), hard)


def test_decode_soft_extrinsic_is_zero_when_bp_never_ran():
    from holo.core.ldpc.decode import decode_soft

    rng = np.random.default_rng(9092)
    info = rng.integers(0, 2, construct.LADDER[RATE].k_bits, dtype=np.uint8)
    llr = np.where(encode(info, RATE) == 1, 8.0, -8.0)
    ok, _hard, iters, extrinsic = decode_soft(llr, RATE, max_iters=60)
    assert ok and iters == 0
    assert not np.any(extrinsic)
