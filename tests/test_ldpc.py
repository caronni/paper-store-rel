"""Layer-3 mother-code battery (paperholo.ldpc): construction goldens,
girth, encode validity, hybrid-decoder BSC/erasure gates, graceful failure.

GOLDEN ANCHORS (bump-don't-edit): the H sha256 per rate and the fixed
codeword sha pin the FORMAT-AXIS construction (seed labels, Fisher-Yates
interleaver, greedy rules a-d, per-rate heavy_deg). If one of these fails
you changed the printed format's inner code: mint new ldpc-v2 labels and
new anchors, never edit these.

Contract deviations, declared (measured basis in paperholo.ldpc docstring):
- construction is e-IRA with an INTERLEAVED bit-serial accumulator and
  mixed {heavy, 3} info degrees, not the contract's literal weight-3 QC-IRA
  block-accumulator (that variant was built and measured: weight-8..10
  codewords, undetected syndrome passes, and a waterfall far below the
  contract gate);
- the contract's erasure point 20% erased + 2% flipped at r0700 is beyond
  the mixed-channel capacity (0.8 * (1 - H2(0.02)) = 0.687 < R = 0.703):
  no code can decode it. The frontier is measured instead (see
  test_erasure_frontier): r0700 carries 20%+0.5% and r0550 carries 20%+2%.

Runs under pytest, or standalone: env/bin/python tests/test_ldpc.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paperholo import ldpc  # noqa: E402
from paperholo.modulation import rng  # noqa: E402

# --- frozen golden anchors (layer-3 v1) ------------------------------------
# r0547 = the COLOR-DESIGN P5 Y rung (k=2240 floor twin of r0550, own seed
# label — anchors added 2026-07-10 with the rung; the original five UNCHANGED)
H_SHA = {
    "r0547": "4cf6774a8fd3ed6d16878880f89778de172a6e3ed749e6f444537e726f4c9371",
    "r0550": "54c72b395776dd1aba2c65dfa49b1e3b9f7e4010266c477a6079b1d214ef477e",
    "r0625": "e98e65155f4e625f185fc202060d2bba4b6f23b70ad3786990ff77c0f059fb71",
    "r0700": "b1ef32ed91a17b6d74a20c3f0a415889aa1b0bae767b6c484bfee35b5c3e5913",
    "r0775": "8b0ec36d6bcad660056020e25bc196aac749c7374ccbd576919369407eff0712",
    "r0850": "4be74ca98de10596d556d756914eaa45538fd22a78b5fee8d128dbcb22da33c7",
}
CW_SHA = {
    "r0547": "5a075723735de934e9d9ee6df0565a04d7b405a7289730215c0f3024c0cf20b6",
    "r0550": "378d7b9b27e5119bf06250ef599684845fe68a9d5631d1d47caebd13ae03bbf8",
    "r0625": "af66fdaee2d5023d4437ad14c0c00899a82773a716d3fdc6173d77589495ebfd",
    "r0700": "8cc67cc0e83dac2878e37808044a6b9240f0ace38394332c3224d8e549b4d882",
    "r0775": "256a5c865430dbff1395c8e5ab10c6d114c661da04e99f4bf8d22aa07110e938",
    "r0850": "d033c60ebde4b96f0fc7bde633f3b4523d844ac3550585e45641b181acee8589",
}
# r0700 golden codeword, first 32 bits (info prefix of the golden-info draw)
CW_R0700_FIRST32 = [0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 1, 1,
                    0, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0]
N_EDGES = {"r0547": 14911, "r0550": 14911, "r0625": 16127, "r0700": 17343,
           "r0775": 16191, "r0850": 14783}


def _golden_info(spec: ldpc.LdpcSpec) -> np.ndarray:
    return rng(spec.seed_label, b"golden-info").integers(
        0, 2, spec.k_bits).astype(np.uint8)


def _hard_llr(bits: np.ndarray, mag: float = 4.0) -> np.ndarray:
    return mag * (2.0 * bits.astype(np.float64) - 1.0)


def test_ladder_build_structure() -> None:
    """All rates build; geometry, column-weight profile, girth > 4 (via
    sparse column-overlap), min check degree, draw determinism."""
    from scipy import sparse
    for rid, spec in ldpc.LDPC_LADDER.items():
        code = ldpc.build_code(spec)
        assert spec.k_bits % spec.z == 0 and spec.n_bits == 4096
        assert code.n_edges == N_EDGES[rid]
        H = code.h_sparse()
        col_w = np.asarray(H.sum(axis=0)).ravel()
        nh = ldpc._n_heavy(spec)
        k = spec.k_bits
        assert (col_w[:nh * spec.z] == spec.heavy_deg).all()
        assert (col_w[nh * spec.z:k] == 3).all()
        assert (col_w[k:-1] == 2).all() and col_w[-1] == 1
        row_w = np.asarray(H.sum(axis=1)).ravel()
        assert row_w.min() >= 2
        G = (H.T @ H).tocoo()
        off = G.data[G.row != G.col]
        assert off.max() <= 1, f"{rid}: 4-cycle in H"
        # determinism: re-run the normative draw at the winning restart
        redrawn = ldpc._draw_h_blocks(spec, code.restart)
        assert redrawn is not None
        assert np.array_equal(redrawn[0], code.pi)
        assert np.array_equal(redrawn[1], code.heavy_rows)
        assert np.array_equal(redrawn[2], code.heavy_shifts)
        assert np.array_equal(redrawn[3], code.light_rows)
        assert np.array_equal(redrawn[4], code.light_shifts)
        print(f"  {rid}: E={code.n_edges} girth>4 restart={code.restart} "
              f"check deg {row_w.min()}-{row_w.max()}")


def test_golden_anchors_and_encode_validity() -> None:
    """sha256 of the edge arrays + one fixed codeword per rate; H @ c == 0
    for golden and random codewords."""
    for rid, spec in ldpc.LDPC_LADDER.items():
        code = ldpc.build_code(spec)
        h_sha = hashlib.sha256(
            code.edge_chk.astype("<i4").tobytes()
            + code.edge_var.astype("<i4").tobytes()).hexdigest()
        assert h_sha == H_SHA[rid], f"{rid}: H changed — format bump needed"
        cw = ldpc.encode(_golden_info(spec), spec)
        cw_sha = hashlib.sha256(np.packbits(cw).tobytes()).hexdigest()
        assert cw_sha == CW_SHA[rid], f"{rid}: codeword changed"
        H = code.h_sparse()
        assert not (np.asarray(H @ cw).ravel() % 2).any()
        for t in range(3):
            info = rng(spec.seed_label, b"enc%d" % t).integers(
                0, 2, spec.k_bits).astype(np.uint8)
            c = ldpc.encode(info, spec)
            assert not (np.asarray(H @ c).ravel() % 2).any()
            assert np.array_equal(c[:spec.k_bits], info)   # systematic
    assert ldpc.encode(_golden_info(
        ldpc.LDPC_LADDER["r0700"]), ldpc.LDPC_LADDER["r0700"])[
        :32].tolist() == CW_R0700_FIRST32
    print("  golden anchors OK (H sha + codeword sha, 5 rates)")


def test_decode_identity_and_conventions() -> None:
    """Clean llr decodes in 0 iterations at every rate; house sign
    convention (positive = bit 1); +-inf accepted; all-erased input
    converges to the all-zero codeword (a valid word — CRC catches it at
    the framing layer)."""
    for rid, spec in ldpc.LDPC_LADDER.items():
        cw = ldpc.encode(_golden_info(spec), spec)
        hard, ok, n_it = ldpc.decode(_hard_llr(cw, 8.0), spec)
        assert ok and n_it == 0 and np.array_equal(hard, cw)
    spec = ldpc.LDPC_LADDER["r0700"]
    cw = ldpc.encode(_golden_info(spec), spec)
    llr = _hard_llr(cw)
    llr[:64] = np.where(cw[:64] == 1, np.inf, -np.inf)   # known bits
    llr[64:128] = 0.0                                    # erasures
    hard, ok, _ = ldpc.decode(llr, spec)
    assert ok and np.array_equal(hard, cw)
    hard, ok, n_it = ldpc.decode(np.zeros(spec.n_bits), spec)
    assert ok and n_it == 0 and not hard.any()
    print("  identity 0-iter all rates; inf/erasure conventions OK")


def test_bsc_gates_r0700() -> None:
    """Contract gates: 200 fixed-seed tiles, BLER < 2% at p = 0.035 and
    0/200 at p = 0.015 (hard-LLR input). Statistical context (500 trials,
    measured): 1.8% at p = 0.035, 0 undetected."""
    spec = ldpc.LDPC_LADDER["r0700"]
    for p, max_fail in ((0.015, 0), (0.035, 3)):
        fails = 0
        for t in range(200):
            g = np.random.default_rng(50_000 + t)
            info = g.integers(0, 2, spec.k_bits).astype(np.uint8)
            cw = ldpc.encode(info, spec)
            rx = cw ^ (g.random(spec.n_bits) < p)
            hard, ok, _ = ldpc.decode(_hard_llr(rx), spec)
            bad = not ok or not np.array_equal(hard, cw)
            fails += int(bad)
            # certification hazard gate: a syndrome pass must be correct
            # OR be caught by CRC at the framing layer — at codec level we
            # require this battery to have no wrong syndrome passes at all
            assert not (ok and not np.array_equal(hard, cw)), \
                f"undetected decode at p={p} trial {t}"
        assert fails <= max_fail, f"p={p}: BLER {fails}/200 > {max_fail}"
        print(f"  r0700 BSC p={p}: BLER {fails}/200 (gate <= {max_fail})")


def test_bsc_ladder_points() -> None:
    """One measured-clean point per remaining rate (fixed seeds; regression
    anchors on the measured frontier, not statistical claims)."""
    pts = {"r0550": (0.055, 1), "r0625": (0.045, 2),
           "r0775": (0.020, 2), "r0850": (0.005, 1)}
    for rid, (p, max_fail) in pts.items():
        spec = ldpc.LDPC_LADDER[rid]
        fails = 0
        for t in range(100):
            g = np.random.default_rng(60_000 + t)
            info = g.integers(0, 2, spec.k_bits).astype(np.uint8)
            cw = ldpc.encode(info, spec)
            rx = cw ^ (g.random(spec.n_bits) < p)
            hard, ok, _ = ldpc.decode(_hard_llr(rx), spec)
            fails += int(not ok or not np.array_equal(hard, cw))
        assert fails <= max_fail, f"{rid} p={p}: {fails}/100"
        print(f"  {rid} BSC p={p}: BLER {fails}/100 (gate <= {max_fail})")


def test_erasure_frontier() -> None:
    """Erasures are first-class (llr == 0). Measured mixed-channel points
    (fixed seeds). The contract's r0700 20%+2% point is beyond capacity
    (C = 0.687 < R = 0.703) — the ladder answer is r0550, which carries it."""
    pts = [("r0700", 0.20, 0.000, 0),
           ("r0700", 0.15, 0.010, 2),
           ("r0700", 0.20, 0.005, 4),
           ("r0550", 0.20, 0.020, 1),
           ("r0625", 0.20, 0.010, 1)]
    for rid, e, p, max_fail in pts:
        spec = ldpc.LDPC_LADDER[rid]
        fails = 0
        for t in range(50):
            g = np.random.default_rng(70_000 + t)
            info = g.integers(0, 2, spec.k_bits).astype(np.uint8)
            cw = ldpc.encode(info, spec)
            u = g.random(spec.n_bits)
            erased = u < e
            flip = (u >= e) & (g.random(spec.n_bits) < p)
            llr = _hard_llr(cw ^ flip)
            llr[erased] = 0.0
            hard, ok, _ = ldpc.decode(llr, spec)
            fails += int(not ok or not np.array_equal(hard, cw))
        assert fails <= max_fail, f"{rid} e={e} p={p}: {fails}/50"
        print(f"  {rid} erasure {e:.0%} + flips {p:.1%}: {fails}/50 "
              f"(gate <= {max_fail})")


def _interior_mask() -> np.ndarray:
    """A realistic pilots-only shorten mask (interior e012 tile)."""
    from paperholo import compose
    from paperholo.pilots import PilotLayout
    spec = compose.ComposeSpec(layout_version=3, pilot=PilotLayout(version=3),
                               page_cells_yx=(2220, 1500))
    return ldpc.tile_shorten_mask((10, 10), spec, b"paper-store/exp012-pilot1")


def test_graceful_failure_and_crc_false_pass() -> None:
    """decode_tile must NEVER certify garbage: 500 random-LLR tiles -> 0
    ok; and mid-waterfall r0625 tiles (where the code's one measured
    weight-6 word lives) -> no ok result with a wrong payload (F9)."""
    mask = _interior_mask()
    lspec = ldpc.LDPC_LADDER["r0700"]
    n_ok = n_syn = 0
    for t in range(500):
        g = np.random.default_rng(80_000 + t)
        llr = g.normal(0.0, 4.0, 4096)
        res = ldpc.decode_tile(llr, mask, lspec)
        n_ok += int(res.ok)
        n_syn += int(res.syndrome_ok)
    assert n_ok == 0, f"{n_ok}/500 garbage tiles certified"
    print(f"  garbage battery: 0/500 certified ({n_syn} stray syndrome "
          f"passes, all CRC-rejected)")

    spec = ldpc.LDPC_LADDER["r0625"]
    cap = ldpc.tile_user_capacity(mask, spec)
    n_bad_certified = n_ok2 = n_und = 0
    for t in range(150):
        g = np.random.default_rng(81_000 + t)
        user = g.integers(0, 2, cap).astype(np.uint8)
        cw, tx_bits = ldpc.encode_tile(user, mask, spec)
        rx = tx_bits ^ (g.random(tx_bits.size) < 0.05)
        llr = np.zeros(4096)
        llr[~mask] = _hard_llr(rx)
        res = ldpc.decode_tile(llr, mask, spec)
        if res.syndrome_ok and not res.crc_ok:
            n_und += 1                       # wrong codeword, CRC caught it
        if res.ok:
            n_ok2 += 1
            if not np.array_equal(res.payload_bits, user):
                n_bad_certified += 1
    assert n_bad_certified == 0, "certified tile with wrong payload (F9)"
    print(f"  r0625 mid-waterfall battery: {n_ok2}/150 ok, 0 wrong-payload "
          f"certifications, {n_und} wrong codewords caught by CRC")


def test_shortened_handling_exact() -> None:
    """Shortening is exact and decoder-side-derivable: interior tile, a
    2899-short corner tile (n_s > k at r0700: degenerate all-zero), and
    garbage LLRs injected at shortened slots must not matter."""
    from paperholo import compose
    from paperholo.pilots import PilotLayout
    SEED = b"paper-store/exp012-pilot1"
    cspec = compose.ComposeSpec(layout_version=3,
                                pilot=PilotLayout(version=3),
                                page_cells_yx=(2220, 1500))
    lspec = ldpc.LDPC_LADDER["r0700"]
    g = np.random.default_rng(5)
    for tile, expect_degenerate in (((10, 10), False), ((5, 23), False),
                                    ((34, 23), True)):
        mask = ldpc.tile_shorten_mask(tile, cspec, SEED)
        n_s = int(mask.sum())
        cap = ldpc.tile_user_capacity(mask, lspec)
        assert cap == max(max(lspec.k_bits - n_s, 0) - 32, 0)
        assert (cap == 0) == expect_degenerate or not expect_degenerate
        user = g.integers(0, 2, cap).astype(np.uint8)
        cw, tx_bits = ldpc.encode_tile(user, mask, lspec)
        assert tx_bits.size == 4096 - n_s
        if expect_degenerate:
            assert n_s > lspec.k_bits and not cw.any() and not tx_bits.any()
        llr = np.zeros(4096)
        llr[~mask] = _hard_llr(tx_bits)
        llr[mask] = g.normal(0.0, 8.0, n_s)   # garbage at shortened slots
        res = ldpc.decode_tile(llr, mask, lspec, tile_yx=tile)
        assert res.ok and res.syndrome_ok and res.crc_ok
        assert np.array_equal(res.payload_bits, user)
        assert res.n_measured == tx_bits.size and res.n_erased == 0
        print(f"  tile {tile}: n_short={n_s} cap={cap} exact "
              f"({'degenerate' if expect_degenerate else 'payload'})")


def test_decode_speed() -> None:
    """Report tiles/s (vectorized min-sum + SP retry), clean and at 3% BSC."""
    spec = ldpc.LDPC_LADDER["r0700"]
    g = np.random.default_rng(9)
    cws = [ldpc.encode(g.integers(0, 2, spec.k_bits).astype(np.uint8), spec)
           for _ in range(20)]
    for tag, p in (("clean", 0.0), ("3% BSC", 0.03)):
        llrs = [_hard_llr(cw ^ (g.random(spec.n_bits) < p)) for cw in cws]
        t0 = time.perf_counter()
        n_ok = 0
        for cw, llr in zip(cws, llrs):
            hard, ok, _ = ldpc.decode(llr, spec)
            n_ok += int(ok and np.array_equal(hard, cw))
        dt = time.perf_counter() - t0
        assert n_ok == len(cws)
        rate = len(cws) / dt
        assert rate > 20.0, f"decode too slow: {rate:.0f} tiles/s"
        print(f"  r0700 decode {tag}: {rate:.0f} tiles/s")


if __name__ == "__main__":
    for fn in [test_ladder_build_structure,
               test_golden_anchors_and_encode_validity,
               test_decode_identity_and_conventions,
               test_bsc_gates_r0700,
               test_bsc_ladder_points,
               test_erasure_frontier,
               test_graceful_failure_and_crc_false_pass,
               test_shortened_handling_exact,
               test_decode_speed]:
        print(fn.__name__)
        fn()
    print("all ldpc codec tests passed")
