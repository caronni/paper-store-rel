# B3 verify: holo3/format/keystream.py + holo3/format/metadata.py vs the
# src/holo oracles (holo.core.keystream, holo.core.keystream_spec,
# holo.format.metadata) in ONE process. Bit-exactness = byte-equal arrays /
# exact ints everywhere. Run:
#   cd <checkout> && \
#   PYTHONPATH=.:src:holo2/src env314t/bin/python \
#     _distill/verify/verify_keystream_metadata.py
import hashlib
import math
import sys

import numpy as np

from holo3.format import keystream as ks3
from holo3.format import metadata as md3
from holo.core import keystream as prod
from holo.core import keystream_spec as ref
from holo.format import metadata as mdo

FAILURES: list[str] = []
N_CHECKS = 0


def check(name: str, cond: bool) -> None:
    global N_CHECKS
    N_CHECKS += 1
    if not cond:
        FAILURES.append(name)
        print(f"FAIL {name}")


def eq_arrays(name: str, a: np.ndarray, b: np.ndarray) -> None:
    check(name + ":dtype", a.dtype == b.dtype)
    check(name + ":shape", a.shape == b.shape)
    check(name + ":bytes", np.array_equal(a, b))


SEEDS = [
    b"holo/v1/c2-r0550/3328x2304",          # golden-vector row seed
    b"holo/v1/c2-r0700/3392x2368",          # e029 row seed
    b"holo/v2/c2-cmy8-r0700@53x37",         # v2-style seed
    b"holo/v1/sites/p100",                  # K family seed
    b"holo/v1/sites/p120",                  # colour family seed
]
GOLD_SEED = SEEDS[0]

rng = np.random.default_rng(0)

# ---------------------------------------------------------------- kdf
for seed in SEEDS:
    check(f"kdf:{seed!r}", ks3.kdf(seed) == prod.kdf(seed) == ref.kdf(seed))

# ---------------------------------------------------------------- counters
maj = rng.integers(0, 1 << 24, size=7)
uu = rng.integers(0, 1 << 32, size=7)
vv = rng.integers(0, 1 << 32, size=7)
eq_arrays("counters:random", ks3.counters(9, 2, maj, uu, vv),
          prod.counters(9, 2, maj, uu, vv))
eq_arrays("counters:broadcast", ks3.counters(1, 3, 2, np.arange(5), 0),
          prod.counters(1, 3, 2, np.arange(5), 0))
for i, bad in enumerate([
        (1, 0, 1 << 24, 0, 0), (1, 0, 0, -1, 0), (1, 0, 0, 0, 1 << 32),
        (300, 0, 0, 0, 0), (1, 256, 0, 0, 0), (-1, 0, 0, 0, 0)]):
    for mod, tag in ((ks3, "holo3"), (prod, "oracle")):
        try:
            mod.counters(*bad)
            check(f"counters:refuse{i}:{tag}", False)
        except ValueError:
            check(f"counters:refuse{i}:{tag}", True)

# ------------------------------------------- blocks + bits, all 15 domains
AUX_BY_DOMAIN = {1: (0, 3), 2: (0, 3), 3: (1, 3), 4: (0,), 5: (0,),
                 6: (0,), 7: (0,), 8: (0,), 9: (0,), 10: (0,), 11: (0,),
                 12: (0,), 13: (1, 2, 3), 14: (0, 1, 2, 3),
                 15: (0, 1, 2, 3)}
for seed in (GOLD_SEED, SEEDS[2], SEEDS[4]):
    for dom, auxes in AUX_BY_DOMAIN.items():
        for aux in auxes:
            m = rng.integers(0, 1 << 24, size=4)
            u = rng.integers(0, 1 << 32, size=4)
            v = rng.integers(0, 1 << 32, size=4)
            b3 = ks3.blocks(seed, dom, aux, m, u, v)
            eq_arrays(f"blocks:d{dom}a{aux}", b3, prod.blocks(seed, dom, aux, m, u, v))
            eq_arrays(f"bits:d{dom}a{aux}", ks3.bits(seed, dom, aux, m, u, v),
                      prod.bits(seed, dom, aux, m, u, v))
            # spec spot check (scalar reference, pure stdlib AES)
            check(f"blocks:d{dom}a{aux}:ref",
                  b3[0].tobytes() == ref.block(seed, dom, aux, int(m[0]),
                                               int(u[0]), int(v[0])))
            check(f"bits:d{dom}a{aux}:ref",
                  int(ks3.bits(seed, dom, aux, int(m[1]), int(u[1]),
                               int(v[1]))[0])
                  == ref.bit(seed, dom, aux, int(m[1]), int(u[1]), int(v[1])))

# ---------------------------------------------------------------- keys64
lt = np.array([0, 1, 17, 839, 1871], dtype=np.int64)
for seed in (GOLD_SEED, SEEDS[1]):
    for page in (0, 139):
        got = ks3.keys64(seed, ks3.DOMAIN_BLOCK_ASSIGN, 0, page, lt, 0)
        eq_arrays(f"keys64:p{page}", got,
                  prod.keys64(seed, prod.DOMAIN_BLOCK_ASSIGN, 0, page, lt, 0))
        want = np.array([ref.block_assign_key(seed, page, int(t))
                         for t in lt], dtype=np.uint64)
        check(f"keys64:p{page}:ref", np.array_equal(got, want))

# ------------------------------------------------------------ payload_bits
for seed, plane, page, shape in [
        (GOLD_SEED, 3, 0, (64, 128)), (GOLD_SEED, 0, 1, (7, 1)),
        (SEEDS[1], 3, 139, (3, 333)), (SEEDS[2], 2, 0, (33, 65))]:
    eq_arrays(f"payload_bits:{plane}/{page}/{shape}",
              ks3.payload_bits(seed, plane, page, shape),
              prod.payload_bits(seed, plane, page, shape))

# ------------------------------------------------------- fountain rows (7)
for n_cols in (1, 127, 128, 129, 4001):
    rows = np.array([0, 3, 4095], dtype=np.int64)
    got = ks3.fountain_rows_bits(GOLD_SEED, 63, rows, n_cols)
    eq_arrays(f"fountain_rows:{n_cols}", got,
              prod.fountain_rows_bits(GOLD_SEED, 63, rows, n_cols))
    for ri, row in enumerate(rows):
        for col in {0, n_cols - 1, min(130, n_cols - 1)}:
            check(f"fountain_rows:{n_cols}:ref:{ri}:{col}",
                  int(got[ri, col]) == ref.fountain_coeff_bit(
                      GOLD_SEED, 63, int(row), col))

# ------------------------------------------------- colour fountain rows (14)
for stream in ("main", "C", "M", "Y", 0, 1, 2, 3):
    rows = np.array([0, 7], dtype=np.int64)
    got = ks3.color_fountain_rows_bits(SEEDS[2], stream, 5, rows, 300)
    eq_arrays(f"color_fountain:{stream}", got,
              prod.color_fountain_rows_bits(SEEDS[2], stream, 5, rows, 300))
    aux = stream if isinstance(stream, int) else \
        {"main": 0, "C": 1, "M": 2, "Y": 3}[stream]
    check(f"color_fountain:{stream}:ref",
          int(got[1, 299]) == ref.color_fountain_coeff_bit(
              SEEDS[2], aux, 5, 7, 299))

# --------------------------------------------- colour block assign keys (15)
for stream in ("main", "C", "M", "Y"):
    got = ks3.color_block_assign_keys(SEEDS[2], stream, 3, lt)
    eq_arrays(f"color_block_assign:{stream}", got,
              prod.color_block_assign_keys(SEEDS[2], stream, 3, lt))
    aux = {"main": 0, "C": 1, "M": 2, "Y": 3}[stream]
    want = np.array([ref.color_block_assign_key(SEEDS[2], aux, 3, int(t))
                     for t in lt], dtype=np.uint64)
    check(f"color_block_assign:{stream}:ref", np.array_equal(got, want))

# ------------------------------------------- item permutations (9, 10, 12)
for name, f3, fo, refkey, sizes in [
        ("dust", ks3.color_dust_permutation, prod.color_dust_permutation,
         ref.color_dust_order_key, (20, 5, 1, 0)),
        ("interleave", ks3.cmy7_interleave_permutation,
         prod.cmy7_interleave_permutation, ref.cmy7_interleave_key,
         (10934, 33)),
        ("cells", ks3.color_cell_permutation, prod.color_cell_permutation,
         ref.color_cell_order_key, (3976, 11))]:
    for size in sizes:
        for tc in (0, 261143):
            got = f3(SEEDS[2], tc, size)
            eq_arrays(f"perm:{name}:{size}:{tc}", got, fo(SEEDS[2], tc, size))
            check(f"perm:{name}:{size}:{tc}:bijection",
                  np.array_equal(np.sort(got), np.arange(size)))
            if size and size <= 40:
                keys = [refkey(SEEDS[2], tc, i) for i in range(size)]
                want = sorted(range(size), key=lambda i: (keys[i], i))
                check(f"perm:{name}:{size}:{tc}:ref",
                      list(got) == want)

# --------------------------------------------------- dither bits (11, 13)
for size in (10934, 17):
    for tc in (0, 1871):
        got = ks3.cmy7_dither_bits(SEEDS[2], tc, size)
        eq_arrays(f"cmy7_dither:{size}:{tc}", got,
                  prod.cmy7_dither_bits(SEEDS[2], tc, size))
        check(f"cmy7_dither:{size}:{tc}:ref",
              int(got[size - 1]) == ref.cmy7_dither_bit(SEEDS[2], tc, size - 1))
for stream in ("C", "M", "Y", 1, 2, 3):
    got = ks3.cmy8_dither_bits(SEEDS[2], stream, 7, 3976)
    eq_arrays(f"cmy8_dither:{stream}", got,
              prod.cmy8_dither_bits(SEEDS[2], stream, 7, 3976))
    aux = stream if isinstance(stream, int) else {"C": 1, "M": 2, "Y": 3}[stream]
    check(f"cmy8_dither:{stream}:ref",
          int(got[3975]) == ref.cmy8_dither_bit(SEEDS[2], aux, 7, 3975))

# --------------------------------------------------- bounded draws (4, 5)
for bound in (2, 6, 7, 49, 64, 100, 256):
    us = np.array([0, 1, 42, 99, 100000], dtype=np.int64)
    for dom in (ks3.DOMAIN_PILOT_SITES, ks3.DOMAIN_FILLER_SITES):
        got = ks3.bounded_draws(GOLD_SEED, dom, us, bound)
        eq_arrays(f"bounded:{dom}:{bound}", got,
                  prod.bounded_draws(GOLD_SEED, dom, us, bound))
        for i, u in enumerate(us):
            check(f"bounded:{dom}:{bound}:ref:{i}",
                  int(got[i]) == ref.bounded_draw(GOLD_SEED, dom, int(u),
                                                  bound))

# ------------------------------------------------------ slot perms (6)
for n_slots in (3996, 3976, 10, 2):
    tcs = np.array([0, 1, 7, 1871, 261143], dtype=np.int64)
    a3, b3 = ks3.slot_perm_params(GOLD_SEED, tcs, n_slots)
    ao, bo = prod.slot_perm_params(GOLD_SEED, tcs, n_slots)
    eq_arrays(f"slot_perm:{n_slots}:a", a3, ao)
    eq_arrays(f"slot_perm:{n_slots}:b", b3, bo)
    for i, tc in enumerate(tcs):
        check(f"slot_perm:{n_slots}:ref:{i}",
              ref.slot_perm_param(GOLD_SEED, int(tc), n_slots)
              == (int(a3[i]), int(b3[i])))
        check(f"slot_perm:{n_slots}:gcd:{i}",
              math.gcd(int(a3[i]), n_slots) == 1)

# ------------------------------ frozen golden vectors (test_keystream.py)
GOLDEN = {
    "payload-256": "cf3943f45be5b668fb87799bafa71df2"
                   "bf858eb2fb06fb6df03498501069b78f",
    "pilot-values-100": "cfa8f309811d523137b3ff9805ae5d75"
                        "5b1ebf55017d67d0429de870f792cb4e",
    "slot-perm-16": "025219fdc0b082e73e389d8640b9b30c"
                    "79eff8bf48bc3963f92490cbe57a4b18",
    "block-assign-1872": "5f5da9ce386c164d2f106e4a2f02ecf"
                         "b8b521435e95962c46217498c6d3a62ec",
}
b = ks3.bits(GOLD_SEED, ks3.DOMAIN_PAYLOAD, 3, 0, 0, np.arange(256))
check("golden:payload-256",
      hashlib.sha256(np.packbits(b).tobytes()).hexdigest()
      == GOLDEN["payload-256"])
b = ks3.bits(GOLD_SEED, ks3.DOMAIN_PILOT_VALUES, 3, 0, np.arange(100), 0)
check("golden:pilot-values-100",
      hashlib.sha256(np.packbits(b).tobytes()).hexdigest()
      == GOLDEN["pilot-values-100"])
a, bb = ks3.slot_perm_params(GOLD_SEED, np.arange(16), 4096 - 100)
check("golden:slot-perm-16",
      hashlib.sha256(a.tobytes() + bb.tobytes()).hexdigest()
      == GOLDEN["slot-perm-16"])
keys = ks3.keys64(GOLD_SEED, ks3.DOMAIN_BLOCK_ASSIGN, 0, 139,
                  np.arange(1872), 0)
check("golden:block-assign-1872",
      hashlib.sha256(keys.astype(">u8", copy=False).tobytes()).hexdigest()
      == GOLDEN["block-assign-1872"])

# ------------------------------------------------------------- metadata
# coefficient tables (single-stream + pooled 3-stream) vs the oracle's
t3 = md3.coefficient_table(md3.MAX_COUNTER)
to = mdo._coefficient_table(mdo.MAX_COUNTER)
eq_arrays("md:table:single", t3, to)
t3p = md3.coefficient_table(3 * md3.MAX_COUNTER)
top = mdo._coefficient_table(3 * mdo.MAX_COUNTER)
eq_arrays("md:table:pooled", t3p, top)
check("md:table:readonly", not t3.flags.writeable)

# constants
for name in ("METADATA_BITS", "K_BITS", "MAX_K", "VALID_VERSIONS",
             "COUNTER_BITS", "MAX_COUNTER", "MIN_METADATA_EQUATIONS",
             "LFSR_POLYNOMIAL", "LFSR_FEEDBACK", "LFSR_INITIAL_STATE"):
    check(f"md:const:{name}", getattr(md3, name) == getattr(mdo, name))

# equation_index / max_equation_index
for n in (1, 2, 3, 63):
    check(f"md:max_index:{n}",
          md3.max_equation_index(n) == mdo.max_equation_index(n))
for mod, tag in ((md3, "holo3"), (mdo, "oracle")):
    try:
        mod.max_equation_index(64)
        check(f"md:max_index:64:{tag}", False)
    except ValueError:
        check(f"md:max_index:64:{tag}", True)
for n in (1, 2, 3):
    for c in (0, 1, 7, 262143):
        for s in range(n):
            check(f"md:eqidx:{c}/{s}/{n}",
                  md3.equation_index(c, s, n) == mdo.equation_index(c, s, n))


def compare_decode(name: str, observations: list[tuple[int, int]],
                   max_index: int, expect_ok: bool,
                   expect_inconsistent: bool = False,
                   expect_rank: int | None = None) -> None:
    """Feed the oracle the observation list and holo3 the dedup'd dict;
    verdicts must match field-for-field (holo3 folds the receiver's
    version-in-{0} gate into ok). The expect_* arguments pin the intended
    scenario so a case cannot pass vacuously."""
    o = mdo.decode_metadata(observations, max_index=max_index)
    equations = dict(observations)
    r = md3.decode_metadata(equations, max_index)
    check(f"md:{name}:version", r.version == o.version)
    check(f"md:{name}:k", r.k == o.k)
    check(f"md:{name}:rank", r.rank == o.rank)
    check(f"md:{name}:n_unique", r.n_unique == o.n_unique_counters)
    check(f"md:{name}:inconsistent", r.inconsistent == o.inconsistent)
    check(f"md:{name}:ok",
          r.ok == (o.ok and o.version in md3.SUPPORTED_METADATA_VERSIONS))
    check(f"md:{name}:scenario_ok", r.ok == expect_ok)
    check(f"md:{name}:scenario_inconsistent",
          r.inconsistent == expect_inconsistent)
    if expect_rank is not None:
        check(f"md:{name}:scenario_rank", r.rank == expect_rank)


def obs_for(word: np.ndarray, indices: list[int],
            max_index: int) -> list[tuple[int, int]]:
    bits_ = mdo.tile_bits(word, np.array(indices, dtype=np.int64),
                          max_index=max_index)
    return [(idx, int(bit)) for idx, bit in zip(indices, bits_)]


MAXC = mdo.MAX_COUNTER
word_ok = mdo.encode_metadata(0, 1961)

# a. full-rank, >=48 consecutive counters, version 0 -> VERIFIED-ready
compare_decode("full60", obs_for(word_ok, list(range(60)), MAXC), MAXC,
               expect_ok=True, expect_rank=24)
# b. scattered counters
compare_decode("scatter", obs_for(word_ok, [7 * i + 3 for i in range(100)],
                                  MAXC), MAXC, expect_ok=True)
# c. sub-48 (rank 24 but below the trust floor)
compare_decode("sub48", obs_for(word_ok, list(range(30)), MAXC), MAXC,
               expect_ok=False, expect_rank=24)
# d. rank < 24
compare_decode("rank20", obs_for(word_ok, list(range(20)), MAXC), MAXC,
               expect_ok=False, expect_rank=20)
# e. algebraic inconsistency (flip the bit of a dependent equation)
bad = obs_for(word_ok, list(range(60)), MAXC)
bad[-1] = (bad[-1][0], bad[-1][1] ^ 1)
compare_decode("inconsistent", bad, MAXC, expect_ok=False,
               expect_inconsistent=True)
# f. all-zero word -> K = 0 refusal
word_k0 = np.zeros(mdo.METADATA_BITS, dtype=np.uint8)
compare_decode("k0", obs_for(word_k0, list(range(60)), MAXC), MAXC,
               expect_ok=False, expect_rank=24)
# g. reserved bit set
word_res = mdo.encode_metadata(0, 1234).copy()
word_res[20] = 1
compare_decode("reserved", obs_for(word_res, list(range(60)), MAXC), MAXC,
               expect_ok=False, expect_rank=24)
# h. version 1: oracle decodes ok, the receiver gate refuses
word_v1 = mdo.encode_metadata(1, 5000)
compare_decode("version1", obs_for(word_v1, list(range(60)), MAXC), MAXC,
               expect_ok=False, expect_rank=24)
o = mdo.decode_metadata(obs_for(word_v1, list(range(60)), MAXC),
                        max_index=MAXC)
r = md3.decode_metadata(dict(obs_for(word_v1, list(range(60)), MAXC)), MAXC)
check("md:version1:oracle_ok", o.ok and o.version == 1)
check("md:version1:holo3_refuses", not r.ok and r.version == 1 and r.k == 5000)
# i. pooled 3-stream row (k field = k_meta), healthy + dead-Y punctured
max_p = mdo.max_equation_index(3)
word_meta = mdo.encode_metadata(0, 600)
healthy = [mdo.equation_index(c, s, 3) for c in range(20) for s in range(3)]
compare_decode("pooled_healthy", obs_for(word_meta, healthy, max_p), max_p,
               expect_ok=True, expect_rank=24)
dead_y = [mdo.equation_index(c, s, 3) for c in range(40) for s in (0, 1)]
compare_decode("pooled_deadY", obs_for(word_meta, dead_y, max_p), max_p,
               expect_ok=True)
r = md3.decode_metadata(dict(obs_for(word_meta, healthy, max_p)), max_p)
check("md:pooled:k_is_k_meta", r.ok and r.k == 600)
# j. -v0 replication: duplicate consistent observations dedup to one index
rep = obs_for(word_ok, list(range(60)), MAXC) * 3
compare_decode("v0_replicated", rep, MAXC, expect_ok=True)
# k. empty
compare_decode("empty", [], MAXC, expect_ok=False, expect_rank=0)

print(f"checks run: {N_CHECKS}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} checks")
    sys.exit(1)
print("verify_keystream_metadata: ALL GREEN")
