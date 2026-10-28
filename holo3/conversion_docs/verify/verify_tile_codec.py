# Verify holo3/format/tile_codec.py bit-exactly against the src/holo oracle
# (holo.core.ldpc.tile / .frame, holo.core.color_tile, holo.core.channel),
# in ONE process. Run:
#   cd <checkout> && \
#   PYTHONPATH=.:src:holo2/src env314t/bin/python _distill/verify/verify_tile_codec.py
from __future__ import annotations

import numpy as np

import holo.core.channel as o_channel
import holo.core.color_tile as o_ct
import holo.core.keystream as o_ks
import holo.core.ldpc.frame as o_frame
import holo.core.ldpc.tile as o_tile
import holo.format.pilots as o_pilots

import holo3.format.tile_codec as tc

SEED = b"holo3-verify-tile-codec-seed"
FAMILY_SEED = b"holo3-verify-fam"
RNG = np.random.default_rng(20260828)

CMY7_BANK = (("r0550", 0), ("r0625", 677), ("r0625", 677))
CMY8_BANKS = {"C": ("r0550", 120), "M": ("r0550", 120), "Y": ("r0547", 120)}

o_cmy7_bank = o_frame.FecBankProfile(
    "cmy7-p120-v0",
    tuple(o_frame.FecChildProfile(cid, s) for cid, s in CMY7_BANK))
o_cmy8_banks = {
    sid: o_frame.FecBankProfile(
        f"cmy8-{sid}-p120-v0", (o_frame.FecChildProfile(cid, s),))
    for sid, (cid, s) in CMY8_BANKS.items()}

checks = 0


def ok(cond: bool, what: str) -> None:
    global checks
    checks += 1
    if not cond:
        raise SystemExit(f"FAIL: {what}")


def outcome_tuple(o: o_frame.FrameDecodeOutcome):
    return (bool(o.ok),
            tuple((c.n_iters, c.syndrome_ok) for c in o.children),
            bool(o.crc_invoked), o.crc_ok)


def same_frame_outcome(mine, oracle, what: str, check_extrinsic: bool) -> None:
    m_ok, m_children, m_inv, m_crc, m_user, m_soft = mine
    ok((m_ok, m_children, m_inv, m_crc) == outcome_tuple(oracle),
       f"{what}: outcome fields differ "
       f"({(m_ok, m_children, m_inv, m_crc)} vs {outcome_tuple(oracle)})")
    if oracle.certified_user_bits is None:
        ok(m_user is None, f"{what}: user bits should be None")
    else:
        ok(m_user is not None
           and np.array_equal(m_user, oracle.certified_user_bits),
           f"{what}: user bits differ")
    if check_extrinsic:
        if oracle.extrinsic_llrs is None:
            ok(m_soft is None, f"{what}: extrinsic should be None")
        else:
            ok(m_soft is not None
               and m_soft.dtype == oracle.extrinsic_llrs.dtype
               and np.array_equal(m_soft, oracle.extrinsic_llrs),
               f"{what}: extrinsic differs")


# ---- width arithmetic (spec 02 table 2.10) ---------------------------------
ok(tc.tile_capacity("r0550", 100) == 2108, "K r0550 p100 capacity")
ok(tc.tile_capacity("r0700", 100) == 2748, "K r0700 p100 capacity")
ok(tc.bank_transmitted_bits(CMY7_BANK) == 10934, "cmy7 T")
ok(tc.bank_active_bits(CMY7_BANK) == 2240 + 1883 + 1883, "cmy7 active")
ok(tc.bank_user_bits(CMY7_BANK) == 5974, "cmy7 user bits")
for sid in ("C", "M", "Y"):
    b = (CMY8_BANKS[sid],)
    ok(tc.bank_transmitted_bits(b) == 3976, f"cmy8 {sid} T")
    ok(tc.bank_user_bits(b) == 2088, f"cmy8 {sid} user bits")
ok(tc.bank_transmitted_bits((("r0700", 120),)) == 3976, "fossil r0700 T")
ok(tc.bank_active_bits((("r0700", 120),)) == 2760, "fossil r0700 active")
ok(tc.bank_user_bits((("r0700", 120),)) == 2728, "fossil r0700 user")
for cid, s in [("r0550", 0), ("r0625", 677), ("r0550", 120),
               ("r0547", 120), ("r0700", 120), ("r0700", 100)]:
    o_pos = o_frame.transmitted_positions(o_frame.FecChildProfile(cid, s))
    ok(np.array_equal(tc.transmitted_positions(cid, s), o_pos),
       f"transmitted_positions {cid}/{s}")

# ---- crc32_bits ------------------------------------------------------------
for n in (1, 7, 8, 33, 2108, 5974):
    bits = RNG.integers(0, 2, n, dtype=np.uint8)
    ok(np.array_equal(tc.crc32_bits(bits), o_tile.crc32_bits(bits)),
       f"crc32_bits n={n}")

# ---- K framing: encode/decode round-trips vs oracle, r0550/r0700 @ p100 ----
site_flat = o_pilots.site_cell_indices(FAMILY_SEED, 0)
ok(site_flat.size == 100, "p100 site count")
n_slots = 4096 - site_flat.size
k_stats = {"ok": 0, "fail": 0, "erased": 0}
for rate_id in ("r0550", "r0700"):
    cap = tc.tile_capacity(rate_id, 100)
    ok(cap == o_tile.tile_capacity(rate_id, 100), f"{rate_id} capacity")
    ok(np.array_equal(tc.cell_map(site_flat, 7, 11),
                      o_tile.cell_map(site_flat, 7, 11)),
       f"{rate_id} cell_map")
    for trial in range(12):
        counter = trial + (0 if rate_id == "r0550" else 500)
        a_arr, b_arr = o_ks.slot_perm_params(SEED, counter, n_slots)
        a_t, b_t = int(a_arr[0]), int(b_arr[0])
        user = RNG.integers(0, 2, cap, dtype=np.uint8)
        cells_mine = tc.encode_tile(user, rate_id, site_flat, a_t, b_t)
        cells_o = o_tile.encode_tile(user, rate_id, site_flat, a_t, b_t)
        ok(cells_mine.dtype == np.uint8
           and np.array_equal(cells_mine, cells_o),
           f"{rate_id} encode_tile trial {trial}")
        p_flip = (0.0, 0.02, 0.05, 0.09)[trial % 4]
        llr = (2.0 * cells_o.astype(np.float64) - 1.0) * \
            RNG.uniform(0.8, 6.0, 4096)
        flip = RNG.random(4096) < p_flip
        llr[flip] = -llr[flip]
        erase = RNG.random(4096) < 0.03
        llr[erase] = 0.0
        llr[site_flat] = 0.0
        k_stats["erased"] += int(erase.sum())
        for max_iters in (60, 150):
            mine = tc.decode_tile(llr, rate_id, site_flat, a_t, b_t,
                                  max_iters, 0.8)
            oo = o_tile.decode_tile(llr, rate_id, site_flat, a_t, b_t,
                                    max_iters=max_iters, alpha=0.8)
            ok(mine[0] == oo.ok and mine[2] == oo.n_iters
               and mine[3] == oo.syndrome_ok and mine[4] == oo.crc_ok,
               f"{rate_id} decode_tile flags trial {trial} mi={max_iters}")
            if oo.ok:
                ok(mine[1] is not None
                   and np.array_equal(mine[1], oo.user_bits)
                   and np.array_equal(mine[1], user),
                   f"{rate_id} decode_tile user trial {trial}")
                k_stats["ok"] += 1
            else:
                ok(mine[1] is None, f"{rate_id} user must be None on fail")
                k_stats["fail"] += 1
print(f"K framing: {k_stats}")

# ---- decode_frame parity: cmy7 baked bank + cmy8 per-plane banks ----------
frame_stats = {"ok": 0, "fail": 0}
for label, bank_mine, bank_o in (
        [("cmy7", CMY7_BANK, o_cmy7_bank)]
        + [(f"cmy8-{sid}", (CMY8_BANKS[sid],), o_cmy8_banks[sid])
           for sid in ("C", "M", "Y")]):
    n_code = tc.bank_transmitted_bits(bank_mine)
    ok(n_code == bank_o.transmitted_bits, f"{label} transmitted_bits")
    ok(tc.bank_user_bits(bank_mine) == bank_o.user_bits, f"{label} user_bits")
    for trial in range(8):
        user = RNG.integers(0, 2, bank_o.user_bits, dtype=np.uint8)
        code_bits = o_frame.encode_frame(user, bank_o)
        ok(np.array_equal(tc.encode_frame(user, bank_mine), code_bits),
           f"{label} encode_frame trial {trial}")
        p_flip = (0.0, 0.03, 0.06, 0.10)[trial % 4]
        llr = (2.0 * code_bits.astype(np.float64) - 1.0) * \
            RNG.uniform(0.8, 6.0, n_code)
        flip = RNG.random(n_code) < p_flip
        llr[flip] = -llr[flip]
        llr[RNG.random(n_code) < 0.02] = 0.0
        for want in (False, True):
            mine = tc.decode_frame(llr, bank_mine, 60, 0.8,
                                   want_extrinsic=want)
            oo = o_frame.decode_frame(llr, bank_o, max_iters=60, alpha=0.8,
                                      want_extrinsic=want)
            same_frame_outcome(mine, oo, f"{label} decode_frame t{trial}",
                               check_extrinsic=True)
        frame_stats["ok" if oo.ok else "fail"] += 1
print(f"decode_frame: {frame_stats}")

# ---- cmy7_soft_demap exact parity (incl. prior + underflow fallback) ------
for trial in range(30):
    n_packs = int(RNG.integers(1, 40))
    scale = (3.0, 40.0, 800.0)[trial % 3]  # 800 forces the log-domain fallback
    rel = RNG.uniform(-scale, scale, (n_packs, 4, 6))
    prior = (None if trial % 2 == 0
             else RNG.uniform(-20.0, 20.0, (n_packs, 11)))
    mine = tc.cmy7_soft_demap(rel, prior)
    oo = o_channel.cmy7_soft_demap(rel, prior)
    ok(np.array_equal(mine, oo), f"cmy7_soft_demap trial {trial}")
huge = np.full((2, 4, 6), 0.0)
huge[0, :, 0] = -750.0  # partition underflow row
ok(np.array_equal(tc.cmy7_soft_demap(huge), o_channel.cmy7_soft_demap(huge)),
   "cmy7_soft_demap underflow row")

# codebook / bit tables / cmy7_map parity
ok(np.array_equal(tc.CMY7_CODEBOOK, o_channel.CMY7_CODEBOOK), "codebook")
bits11 = RNG.integers(0, 2, (17, 11), dtype=np.uint8)
ok(np.array_equal(tc.cmy7_map(bits11), o_channel.cmy7_map(bits11)),
   "cmy7_map")
states_r = RNG.integers(0, 8, (23, 3), dtype=np.uint8)
ok(np.array_equal(tc.planes_to_states(tc.states_to_planes(states_r[..., 0])),
                  states_r[..., 0]), "states/planes round-trip")
ok(np.array_equal(tc.states_to_planes(states_r[..., 0]),
                  o_channel.states_to_planes(states_r[..., 0])),
   "states_to_planes parity")

# ---- cmy7 payload demap + iterated decode, >=100 noisy tiles --------------
n_code = 10934
n_cells = 3976
stats = {"pass1": 0, "iter_ok": 0, "fail": 0, "incomplete_packs": 0}
demap_prior_checked = 0
for counter in range(104):
    interleave = o_ks.cmy7_interleave_permutation(SEED, counter, n_code)
    dither = o_ks.cmy7_dither_bits(SEED, counter, n_code)
    user = RNG.integers(0, 2, 5974, dtype=np.uint8)
    states = o_ct.cmy7_encode_payload(user, o_cmy7_bank, interleave, dither)
    ok(np.array_equal(
        tc.cmy7_encode_payload(user, CMY7_BANK, interleave, dither), states),
       f"cmy7_encode_payload c{counter}")
    # W-relative synthesis: rel_s = mag*(onehot(true)_s - is_W) + noise, so
    # the true state (W included) leads its rivals by mag before noise.
    mag = 7.0
    sigma = (2.5, 2.75, 3.1)[counter % 3]
    scores = RNG.normal(0.0, sigma, (n_cells, 6))
    inked = states > 0
    scores[np.flatnonzero(inked), states[inked].astype(np.int64) - 1] += mag
    scores[~inked] -= mag
    observed = np.ones(n_cells, dtype=bool)
    if counter % 4 == 1:
        observed[RNG.integers(0, n_cells, 30)] = False
        stats["incomplete_packs"] += 1
    llr_mine = tc.cmy7_demap_payload(scores, observed, CMY7_BANK,
                                     interleave, dither)
    llr_o = o_ct.cmy7_demap_payload(scores, observed, o_cmy7_bank,
                                    interleave, dither)
    ok(np.array_equal(llr_mine, llr_o), f"cmy7_demap_payload c{counter}")
    mine = tc.cmy7_iterated_decode(llr_mine, scores, observed, CMY7_BANK,
                                   interleave, dither, 60, 0.8, 3)
    oo = o_ct.cmy7_iterated_decode(llr_o, scores, observed, o_cmy7_bank,
                                   interleave, dither, max_iters=60,
                                   alpha=0.8, demap_iterations=3)
    same_frame_outcome(mine, oo, f"cmy7_iterated_decode c{counter}",
                       check_extrinsic=False)
    ok(mine[5] is None, "iterated outcome must carry no soft output")
    single = tc.cmy7_iterated_decode(llr_mine, scores, observed, CMY7_BANK,
                                     interleave, dither, 60, 0.8, 1)
    same_frame_outcome(
        single,
        o_frame.decode_frame(llr_o, o_cmy7_bank, max_iters=60, alpha=0.8),
        f"cmy7 demap_iterations=1 c{counter}", check_extrinsic=True)
    if oo.ok:
        ok(np.array_equal(oo.certified_user_bits, user),
           f"cmy7 certified bits wrong c{counter}")
        first = o_frame.decode_frame(llr_o, o_cmy7_bank, max_iters=60,
                                     alpha=0.8)
        if first.ok:
            stats["pass1"] += 1
        else:
            stats["iter_ok"] += 1
    else:
        stats["fail"] += 1
    if demap_prior_checked < 12 and not oo.ok:
        soft_o = o_frame.decode_frame(llr_o, o_cmy7_bank, max_iters=60,
                                      alpha=0.8, want_extrinsic=True)
        prior = np.clip(soft_o.extrinsic_llrs, -20.0, 20.0)
        re_mine = tc.cmy7_demap_payload(scores, observed, CMY7_BANK,
                                        interleave, dither, prior)
        re_o = o_ct.cmy7_demap_payload(scores, observed, o_cmy7_bank,
                                       interleave, dither, prior)
        ok(np.array_equal(re_mine, re_o),
           f"cmy7_demap_payload w/ prior c{counter}")
        # Pack structure lives in INTERLEAVED order: mapped = code[order].
        incomplete = ~observed.reshape(-1, 4).all(axis=1)
        ok((re_mine[interleave].reshape(-1, 11)[incomplete] == 0.0).all()
           if incomplete.any() else True,
           f"erased packs must stay exactly 0.0 c{counter}")
        demap_prior_checked += 1
ok(stats["pass1"] + stats["iter_ok"] + stats["fail"] == 104, "cmy7 count")
ok(stats["iter_ok"] > 0, "no tile exercised the iterated demap win path")
ok(stats["fail"] > 0, "no tile exercised the failure path")
print(f"cmy7 tiles: {stats}, prior-demap parity checks: {demap_prior_checked}")

# ---- cmy8: encode + per-stream decode, >=100 noisy tiles ------------------
stats8 = {"ok": 0, "fail": 0}
for counter in range(35):
    users = {sid: RNG.integers(0, 2, 2088, dtype=np.uint8)
             for sid in ("C", "M", "Y")}
    dithers = {sid: o_ks.cmy8_dither_bits(SEED, sid, counter, 3976)
               for sid in ("C", "M", "Y")}
    states_o = o_ct.cmy8_encode_payload(users, o_cmy8_banks, dithers)
    states_m = tc.cmy8_encode_payload(
        tuple(users[sid] for sid in ("C", "M", "Y")),
        tuple((CMY8_BANKS[sid],) for sid in ("C", "M", "Y")),
        tuple(dithers[sid] for sid in ("C", "M", "Y")))
    ok(np.array_equal(states_m, states_o), f"cmy8_encode_payload c{counter}")
    for sid in ("C", "M", "Y"):
        wire = o_frame.encode_frame(users[sid], o_cmy8_banks[sid]) \
            ^ dithers[sid]
        p_flip = (0.0, 0.04, 0.08)[counter % 3]
        llr = (2.0 * wire.astype(np.float64) - 1.0) * \
            RNG.uniform(0.8, 6.0, 3976)
        flip = RNG.random(3976) < p_flip
        llr[flip] = -llr[flip]
        llr[RNG.random(3976) < 0.02] = 0.0
        mine = tc.cmy8_decode_stream(llr, (CMY8_BANKS[sid],), dithers[sid],
                                     60, 0.8)
        oo = o_ct.cmy8_decode_stream(llr, o_cmy8_banks[sid], dithers[sid],
                                     max_iters=60, alpha=0.8)
        same_frame_outcome(mine, oo, f"cmy8_decode_stream {sid} c{counter}",
                           check_extrinsic=True)
        if oo.ok:
            ok(np.array_equal(oo.certified_user_bits, users[sid]),
               f"cmy8 {sid} certified bits wrong c{counter}")
            stats8["ok"] += 1
        else:
            stats8["fail"] += 1
ok(stats8["ok"] + stats8["fail"] == 105, "cmy8 stream count")
ok(stats8["ok"] > 0 and stats8["fail"] > 0, "cmy8 mix of outcomes")
print(f"cmy8 streams: {stats8}")

print(f"ALL GREEN: {checks} checks passed "
      f"(verify_tile_codec vs src/holo oracle, one process)")
