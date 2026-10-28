# Verify holo3/format/fountain.py + holo3/format/close.py against src/holo
# (the v1 oracle) in ONE process.
#
# Part 1: VolumeCode assignment parity (quotas / page_assignment /
#         block_row_of) for K, colour (main/C/M/Y), pooled n=3, and the
#         pooled n=1 bit-identity; packed generator-row parity (byte-
#         reversal bridge) per domain family.
# Part 2: end-to-end closes on synthetic volumes emitted with src/holo's
#         gen side: (a) K, (a2) cmy7-style colour single stream,
#         (b) cmy8 -v0 three-stream, (c) pooled cmy8, (d) pooled dead-Y;
#         negative variants: truncated -> open, metadata-starved -> open,
#         corrupted symbol -> integrity, conflicting duplicate ->
#         integrity, noncanonical K -> integrity, nonzero padding ->
#         integrity; close_count_ready on all of them.
#
# Run:
#   cd <checkout> && \
#   PYTHONPATH=.:src:holo2/src env314t/bin/python \
#     _distill/verify/verify_fountain_close.py

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import holo3.format.fountain as f3
import holo3.format.close as c3

import holo.core.fountain as f1
import holo.format.envelope as env1
import holo.format.metadata as md1
import holo.format.streamset as ss1

CHECKS = []


def check(name: str, ok: bool) -> None:
    CHECKS.append((name, ok))
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(f"FAILED: {name}")


# ---------------------------------------------------------------- part 1

SEED = b"holo3-verify/assignment"
T = 737
K_BIG = 40000  # 3 blocks
S = 64


def code_pair(**kw):
    return (f3.VolumeCode(K_BIG, S, SEED, T, **kw),
            f1.VolumeCode(K_BIG, S, SEED, T, **kw))


VARIANTS = {
    "K": {},
    "main-aux0": {"stream_id": "main", "fountain_aux": 0},
    "C": {"stream_id": "C", "fountain_aux": 1},
    "M": {"stream_id": "M", "fountain_aux": 2},
    "Y": {"stream_id": "Y", "fountain_aux": 3},
    "pooled-n3": {"n_streams": 3},
}

for label, kw in VARIANTS.items():
    a, b = code_pair(**kw)
    check(f"{label}: k_per_block", a.k_per_block == b.k_per_block)
    check(f"{label}: block_offsets", a.block_offsets == b.block_offsets)
    ok_q = all(
        np.array_equal(a.quotas(p, s), b.quotas(p, s))
        for p in range(4) for s in range(a.n_streams))
    check(f"{label}: quotas pages 0-3", ok_q)
    ok_pa = True
    for p in range(4):
        ba, ra = a.page_assignment(p)
        bb, rb = b.page_assignment(p)
        ok_pa &= np.array_equal(ba, bb) and np.array_equal(ra, rb)
        ok_pa &= ba.dtype == bb.dtype and ra.dtype == rb.dtype
    check(f"{label}: page_assignment pages 0-3 byte-identical", ok_pa)
    sample = np.arange(0, 4 * a.symbols_per_page, 7)
    ok_br = all(a.block_row_of(int(e)) == b.block_row_of(int(e))
                for e in sample)
    check(f"{label}: block_row_of sample", ok_br)

# the pooled n=1 bit-identity (the format-fork guard)
p1 = f3.VolumeCode(K_BIG, S, SEED, T, n_streams=1)
k3 = f3.VolumeCode(K_BIG, S, SEED, T)
k1 = f1.VolumeCode(K_BIG, S, SEED, T)
ok_id = True
for p in range(4):
    bp, rp = p1.page_assignment(p)
    bk, rk = k3.page_assignment(p)
    bo, ro = k1.page_assignment(p)
    ok_id &= np.array_equal(bp, bk) and np.array_equal(rp, rk)
    ok_id &= np.array_equal(bp, bo) and np.array_equal(rp, ro)
check("pooled n=1 == K (holo3 and v1)", ok_id)

# colour domains differ from K domains (routing is live, not decorative)
ck = f3.VolumeCode(K_BIG, S, SEED, T)
cm = f3.VolumeCode(K_BIG, S, SEED, T, stream_id="main", fountain_aux=0)
check("main-aux0 shuffle differs from K",
      not np.array_equal(ck.page_assignment(0)[0],
                         cm.page_assignment(0)[0]))

# generator-row parity: small single-block code, source + repair rows,
# tail mask exercised (kb=100, 100 & 7 == 4)
K_SMALL = 100
for label, kw in (("K", {}), ("main-aux0",
                              {"stream_id": "main", "fountain_aux": 0}),
                  ("C", {"stream_id": "C", "fountain_aux": 1}),
                  ("pooled-n3", {"n_streams": 3})):
    a = f3.VolumeCode(K_SMALL, S, SEED, T, **kw)
    b = f1.VolumeCode(K_SMALL, S, SEED, T, **kw)
    esis = list(range(0, 60)) + list(range(150, 190))  # rows <100 and >=100
    items = sorted((a.block_row_of(e)[1], e) for e in esis)
    dec = f3.Decoder(a)
    raw = dec._packed_generator_rows(items)
    got = f3._unpack_bits_2d(raw, K_SMALL)
    want = np.stack([b.generator_row(e) for _r, e in items])
    check(f"{label}: packed generator rows == v1 generator_row",
          np.array_equal(got, want))
    n_repair = sum(r >= K_SMALL for r, _e in items)
    check(f"{label}: repair rows present in generator sample", n_repair >= 10)


# ---------------------------------------------------------------- part 2

@dataclass(frozen=True)
class Cert:
    page: int
    ty: int
    tx: int
    stream_id: str
    user_bits: np.ndarray
    source: str


@dataclass(frozen=True)
class Stream:
    stream_id: str
    symbol_bits: int
    fountain_aux: int | None


@dataclass(frozen=True)
class Row:
    seed: bytes
    tiles_yx: tuple[int, int]
    streams: tuple[Stream, ...]
    pooled_fountain: bool


TILES_YX = (8, 8)
TT = 64
SB = 40  # symbol bits per stream in every synthetic volume


def mk_cert(counter: int, stream_id: str, md_bit: int,
            symbol: np.ndarray) -> Cert:
    page, local = divmod(int(counter), TT)
    ty, tx = divmod(local, TILES_YX[1])
    ub = np.concatenate(([md_bit], symbol)).astype(np.uint8)
    return Cert(page, ty, tx, stream_id, ub, "test")


rng = np.random.default_rng(7)

# ---- (a) K volume ------------------------------------------------------
payload_a = rng.integers(0, 256, 300, dtype=np.uint8).tobytes()
seed_a = b"verify/K"
env_a = env1.wrap(payload_a)
k_a = env1.source_symbol_count(len(payload_a), SB)
src_a = f1.pack_source(env_a, k_a, SB)
code_a = f1.VolumeCode(k_a, SB, seed_a, TT)
esis_a = np.arange(2 * TT, dtype=np.int64)
sym_a = code_a.encode_symbols(src_a, esis_a)
word_a = md1.encode_metadata(0, k_a)
bits_a = md1.tile_bits(word_a, esis_a)
certs_a = [mk_cert(c, "main", bits_a[i], sym_a[i])
           for i, c in enumerate(esis_a)]
row_a = Row(seed_a, TILES_YX, (Stream("main", SB, None),), False)

res = c3.close_volume(certs_a, row_a)
check("A: K close verified", res.status == "verified")
check("A: K payload byte-exact", res.payload == payload_a)
check("A: K k_total", res.k_total == k_a)
check("A: count_ready True", c3.close_count_ready(certs_a, row_a))
check("A: blocks solved, stream None",
      all(b.solved and b.stream_id is None for b in res.blocks))

# ---- (a2) cmy7-style single colour stream (domains 14/15, aux 0) -------
payload_a2 = rng.integers(0, 256, 280, dtype=np.uint8).tobytes()
seed_a2 = b"verify/cmy7"
env_a2 = env1.wrap(payload_a2)
k_a2 = env1.source_symbol_count(len(payload_a2), SB)
src_a2 = f1.pack_source(env_a2, k_a2, SB)
code_a2 = f1.VolumeCode(k_a2, SB, seed_a2, TT,
                        stream_id="main", fountain_aux=0)
esis_a2 = np.arange(2 * TT, dtype=np.int64)
sym_a2 = code_a2.encode_symbols(src_a2, esis_a2)
word_a2 = md1.encode_metadata(0, k_a2)
bits_a2 = md1.tile_bits(word_a2, esis_a2)
certs_a2 = [mk_cert(c, "main", bits_a2[i], sym_a2[i])
            for i, c in enumerate(esis_a2)]
row_a2 = Row(seed_a2, TILES_YX, (Stream("main", SB, 0),), False)

res = c3.close_volume(certs_a2, row_a2)
check("A2: cmy7-style close verified", res.status == "verified")
check("A2: payload byte-exact", res.payload == payload_a2)
check("A2: blocks carry stream_id 'main'",
      all(b.stream_id == "main" for b in res.blocks))

# ---- (b) cmy8 -v0 three independent streams ----------------------------
payload_b = rng.integers(0, 256, 310, dtype=np.uint8).tobytes()
seed_b = b"verify/cmy8-v0"
sset = ss1.StreamSet((("C", SB), ("M", SB), ("Y", SB)))
pset = ss1.pack_payload(payload_b, sset)
k_b = pset.k_total
word_b = md1.encode_metadata(0, k_b)
counters_b = np.arange(TT, dtype=np.int64)
bits_b = md1.tile_bits(word_b, counters_b)
certs_b = []
aux_of = {"C": 1, "M": 2, "Y": 3}
for ps in pset.streams:
    code = f1.VolumeCode(k_b, SB, seed_b, TT,
                         stream_id=ps.stream_id,
                         fountain_aux=aux_of[ps.stream_id])
    sym = code.encode_symbols(ps.rows, counters_b)
    certs_b += [mk_cert(c, ps.stream_id, bits_b[i], sym[i])
                for i, c in enumerate(counters_b)]
row_b = Row(seed_b, TILES_YX,
            (Stream("C", SB, 1), Stream("M", SB, 2), Stream("Y", SB, 3)),
            False)

res = c3.close_volume(certs_b, row_b)
check("B: -v0 cmy8 close verified", res.status == "verified")
check("B: payload byte-exact", res.payload == payload_b)
check("B: k_total is common K", res.k_total == k_b)
check("B: three labelled block spaces",
      sorted({b.stream_id for b in res.blocks}) == ["C", "M", "Y"])
check("B: count_ready True", c3.close_count_ready(certs_b, row_b))

# ---- (c) pooled cmy8 ---------------------------------------------------
payload_c = rng.integers(0, 256, 320, dtype=np.uint8).tobytes()
seed_c = b"verify/cmy8-pooled"
k_meta, rows_c = ss1.pooled_pack_payload(payload_c, sset)
k_total_c = 3 * k_meta
code_c = f1.VolumeCode(k_total_c, SB, seed_c, TT, n_streams=3)
esis_c = np.arange(TT * 3, dtype=np.int64)
sym_c = code_c.encode_symbols(rows_c, esis_c)
word_c = md1.encode_metadata(0, k_meta)
bits_c = md1.tile_bits(word_c, esis_c,
                       max_index=md1.max_equation_index(3))
stream_of = {0: "C", 1: "M", 2: "Y"}
certs_c = []
for i, e in enumerate(esis_c):
    counter, idx = divmod(int(e), 3)
    certs_c.append(mk_cert(counter, stream_of[idx], bits_c[i], sym_c[i]))
row_c = Row(seed_c, TILES_YX,
            (Stream("C", SB, 1), Stream("M", SB, 2), Stream("Y", SB, 3)),
            True)

res = c3.close_volume(certs_c, row_c)
check("C: pooled close verified", res.status == "verified")
check("C: payload byte-exact", res.payload == payload_c)
check("C: k_total = 3 * k_meta", res.k_total == k_total_c)
check("C: one unattributed block space",
      all(b.stream_id is None for b in res.blocks))
check("C: count_ready True", c3.close_count_ready(certs_c, row_c))

# ---- (d) pooled dead-Y -------------------------------------------------
certs_d = [c for c in certs_c if c.stream_id != "Y"]
res = c3.close_volume(certs_d, row_c)
check("D: dead-Y pooled close verified", res.status == "verified")
check("D: dead-Y payload byte-exact", res.payload == payload_c)
check("D: dead-Y count_ready True", c3.close_count_ready(certs_d, row_c))

# ---- negatives ---------------------------------------------------------

# truncated: metadata solvable (50 unique >= 48) but block short -> open
certs_tr = certs_a[:50]
res = c3.close_volume(certs_tr, row_a)
check("N1: truncated K -> open", res.status == "open")
check("N1: truncated reports block shortfall",
      res.blocks and not res.blocks[0].solved
      and res.blocks[0].have == 50 and res.blocks[0].needed == k_a)
check("N1: count_ready False", not c3.close_count_ready(certs_tr, row_a))

# metadata-starved: 30 unique < MIN_METADATA_EQUATIONS -> open (incomplete)
certs_md = certs_a[:30]
res = c3.close_volume(certs_md, row_a)
check("N2: metadata-starved -> open", res.status == "open")
check("N2: reason is metadata incomplete", res.reason == "metadata incomplete")
check("N2: count_ready False", not c3.close_count_ready(certs_md, row_a))

# corrupted symbol (systematic pivot): exactly k_a source certs, flip a bit
certs_cor = list(certs_a[:k_a])
ub = certs_cor[5].user_bits.copy()
ub[3] ^= 1
certs_cor[5] = Cert(certs_cor[5].page, certs_cor[5].ty, certs_cor[5].tx,
                    certs_cor[5].stream_id, ub, "test")
res = c3.close_volume(certs_cor, row_a)
check("N3: corrupted symbol -> integrity_failure",
      res.status == "integrity_failure")
check("N3: reason names envelope verification",
      "envelope verification failed" in (res.reason or ""))

# conflicting duplicate at one address -> integrity (never voted)
ub2 = certs_a[0].user_bits.copy()
ub2[7] ^= 1
dup = Cert(certs_a[0].page, certs_a[0].ty, certs_a[0].tx,
           "main", ub2, "test")
res = c3.close_volume(list(certs_a) + [dup], row_a)
check("N4: conflicting duplicate -> integrity_failure",
      res.status == "integrity_failure")
check("N4: reason names certified-symbol integrity",
      "certified-symbol integrity failure" in (res.reason or ""))

# identical duplicate is a no-op
res = c3.close_volume(list(certs_a) + [certs_a[0]], row_a)
check("N5: identical duplicate still verifies", res.status == "verified"
      and res.payload == payload_a and res.symbols_used == len(certs_a))

# noncanonical K: volume emitted at k_a + 1 -> gate b fires
k_nc = k_a + 1
src_nc = f1.pack_source(env_a, k_nc, SB)
code_nc = f1.VolumeCode(k_nc, SB, seed_a, TT)
esis_nc = np.arange(k_nc, dtype=np.int64)
sym_nc = code_nc.encode_symbols(src_nc, esis_nc)
word_nc = md1.encode_metadata(0, k_nc)
bits_nc = md1.tile_bits(word_nc, esis_nc)
certs_nc = [mk_cert(c, "main", bits_nc[i], sym_nc[i])
            for i, c in enumerate(esis_nc)]
res = c3.close_volume(certs_nc, row_a)
check("N6: noncanonical K -> integrity_failure",
      res.status == "integrity_failure")

# nonzero padding: set a padding bit in the emitted source -> gate c fires
src_pad = src_a.copy()
used_bits = (env1.OVERHEAD_BYTES + len(payload_a)) * 8
pad_bit = used_bits  # first padding bit, inside the last source row
r_pad, local_bit = divmod(pad_bit, SB)
byte_i, bit_i = divmod(local_bit, 8)
src_pad[r_pad, byte_i] |= np.uint8(0x80 >> bit_i)
sym_pad = code_a.encode_symbols(src_pad, np.arange(k_a, dtype=np.int64))
certs_pad = [mk_cert(c, "main", bits_a[c], sym_pad[i])
             for i, c in enumerate(range(k_a))]
res = c3.close_volume(certs_pad, row_a)
check("N7: nonzero padding -> integrity_failure",
      res.status == "integrity_failure")

# sanity that N7's construction is the only difference: clean re-emit closes
sym_clean = code_a.encode_symbols(src_a, np.arange(k_a, dtype=np.int64))
certs_clean = [mk_cert(c, "main", bits_a[c], sym_clean[i])
               for i, c in enumerate(range(k_a))]
res = c3.close_volume(certs_clean, row_a)
check("N7-control: same subset without padding bit verifies",
      res.status == "verified" and res.payload == payload_a)

print()
print(f"ALL {len(CHECKS)} CHECKS PASSED")
