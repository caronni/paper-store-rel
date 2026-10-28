# Verify holo3/lib/bch.py against the oracles (src/holo scalar law, holo2 batch).
# Run: cd <checkout> && \
#   PYTHONPATH=.:src:holo2/src env314t/bin/python _distill/verify/verify_bch.py
import hashlib
import sys
import time

import numpy as np

import holo3.lib.bch as h3

import holo.core.bch as oracle            # src/holo scalar (format law)
import holo2.format.bch_batch as o_batch  # holo2 batched arm (oracle twin)

GPOLY_SHA = "a0be5064cfef57b2a84aaadbd7bd13b9772b1259fa041c25af0d7bde4922b684"
GPOLY_INT = 0x2C9352AA6CC054468311

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    tag = "ok  " if ok else "FAIL"
    print(f"{tag} {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def same_result(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    wa, ea = a
    wb, eb = b
    return (int(ea) == int(eb) and wa.dtype == np.uint8
            and np.array_equal(wa, wb))


def main() -> None:
    rng = np.random.default_rng(20260828)

    # --- 1. generator poly: sha pin, int pin, oracle byte-equality -------
    g = h3.generator_poly()
    check("gpoly sha256",
          hashlib.sha256(g.tobytes()).hexdigest() == GPOLY_SHA)
    check("gpoly int form",
          sum(int(c) << i for i, c in enumerate(g)) == GPOLY_INT)
    check("gpoly == oracle",
          g.dtype == np.uint8 and np.array_equal(g, oracle.generator_poly()))
    check("gf tables == oracle",
          np.array_equal(h3._EXP, oracle.gf_tables()[0])
          and np.array_equal(h3._LOG, oracle.gf_tables()[1]))

    # --- 2. full 2^18 weight spectrum (exhaustive; affine => pairwise) ---
    t0 = time.time()
    counts: dict[int, int] = {}
    for m_int in range(1, 1 << 18):
        parity = h3._polymod2(m_int << h3.N_PARITY, h3._GPOLY_INT)
        w = parity.bit_count() + m_int.bit_count()
        counts[w] = counts.get(w, 0) + 1
    expected = {27: 3, 28: 8, 31: 119, 32: 247, 35: 1613, 36: 2668,
                39: 9551, 40: 13205}
    low = {w: n for w, n in counts.items() if w <= 40}
    check("weight spectrum (full 2^18 sweep)", low == expected,
          f"low={sorted(low.items())} [{time.time() - t0:.1f}s]")
    check("d_min == 27 exact", min(counts) == 27)

    # --- 3. encode == oracle on random messages --------------------------
    ok = True
    for _ in range(500):
        msg = rng.integers(0, 2, size=h3.K_MSG).astype(np.uint8)
        a = h3.encode(msg)
        b = oracle.encode(msg)
        if a.dtype != np.uint8 or not np.array_equal(a, b):
            ok = False
            break
    check("encode == oracle (500 random messages)", ok)
    msg0 = rng.integers(0, 2, size=h3.K_MSG).astype(np.uint8)
    check("message_from_word round-trip",
          np.array_equal(h3.message_from_word(h3.encode(msg0)), msg0))

    # --- 4. syndromes == oracle ------------------------------------------
    words = rng.integers(0, 2, size=(2000, h3.N_WORD)).astype(np.uint8)
    ok = all(np.array_equal(h3.syndromes(words[i]), oracle.syndromes(words[i]))
             for i in range(200))
    check("syndromes == oracle (200 rows)", ok)
    check("syndromes_many == oracle",
          np.array_equal(h3.syndromes_many(words),
                         oracle.syndromes_many(words)))
    z = np.zeros(h3.N_WORD, dtype=np.uint8)
    check("all-zero word syndrome",
          np.array_equal(h3.syndromes(z), np.zeros(26, dtype=np.uint8)))

    # --- 5. scalar decode == oracle, 0..15 errors ------------------------
    ok = True
    n_none = 0
    for trial in range(3000):
        msg = rng.integers(0, 2, size=h3.K_MSG).astype(np.uint8)
        word = oracle.encode(msg)
        e = int(rng.integers(0, 16))
        pos = rng.choice(h3.N_WORD, size=e, replace=False)
        corrupted = word.copy()
        corrupted[pos] ^= 1
        a = h3.decode(corrupted)
        b = oracle.decode(corrupted)
        if not same_result(a, b):
            ok = False
            print(f"  mismatch at trial {trial}, e={e}")
            break
        if a is None:
            n_none += 1
        elif e <= h3.T:
            if not (np.array_equal(a[0], word) and a[1] == e):
                ok = False
                print(f"  wrong correction at trial {trial}, e={e}")
                break
    check("decode == oracle (3000 corrupted words, e in 0..15)", ok,
          f"refusals={n_none}")

    # --- 6. decode_erasures == oracle incl. refusals ---------------------
    ok = True
    n_none = 0
    n_ok = 0
    for trial in range(3000):
        msg = rng.integers(0, 2, size=h3.K_MSG).astype(np.uint8)
        word = oracle.encode(msg)
        f = int(rng.integers(0, 31))          # 27..30 must refuse (f > 26)
        e = int(rng.integers(0, 16))
        era = rng.choice(h3.N_WORD, size=f, replace=False)
        non_era = np.setdiff1d(np.arange(h3.N_WORD), era)
        pos = rng.choice(non_era, size=min(e, non_era.size), replace=False)
        corrupted = word.copy()
        corrupted[pos] ^= 1
        corrupted[era] = rng.integers(0, 2, size=f).astype(np.uint8)
        a = h3.decode_erasures(corrupted, era)
        b = oracle.decode_erasures(corrupted, era)
        if not same_result(a, b):
            ok = False
            print(f"  erasure mismatch at trial {trial}, e={e}, f={f}")
            break
        if a is None:
            n_none += 1
        else:
            n_ok += 1
            if 2 * len(pos) + f <= 26 and not np.array_equal(a[0], word):
                ok = False
                print(f"  in-budget wrong word at trial {trial}")
                break
    check("decode_erasures == oracle (3000 trials, f in 0..30)", ok,
          f"accepted={n_ok} refused={n_none}")
    era27 = np.arange(27, dtype=np.int64)
    check("f=27 refuses (both)",
          h3.decode_erasures(z, era27) is None
          and oracle.decode_erasures(z, era27) is None)
    # budget edge: e=0 f=26 accepted, e=1 f=25 accepted (2e+f=27 <= 26 false -> refusal path exercised in the sweep)
    word = oracle.encode(np.ones(h3.K_MSG, dtype=np.uint8))
    trial26 = word.copy()
    trial26[:26] ^= 1
    r3 = h3.decode_erasures(trial26, np.arange(26, dtype=np.int64))
    ro = oracle.decode_erasures(trial26, np.arange(26, dtype=np.int64))
    check("f=26 e=0 accepted, e_out=0",
          same_result(r3, ro) and r3 is not None and r3[1] == 0
          and np.array_equal(r3[0], word))

    # --- 7. decode_many bit-identical to scalar over >=200k rows ---------
    n_random = 60_000
    n_near = 140_000
    batch = np.empty((n_random + n_near, h3.N_WORD), dtype=np.uint8)
    batch[:n_random] = rng.integers(0, 2, size=(n_random, h3.N_WORD))
    msgs = rng.integers(0, 2, size=(n_near, h3.K_MSG)).astype(np.uint8)
    errs = rng.integers(0, 16, size=n_near)
    for k in range(n_near):
        w = oracle.encode(msgs[k])
        pos = rng.choice(h3.N_WORD, size=int(errs[k]), replace=False)
        w[pos] ^= 1
        batch[n_random + k] = w
    batch[n_random] = 0                      # all-zero word: clean R1 path
    order = rng.permutation(batch.shape[0])
    batch = batch[order]

    t0 = time.time()
    mine = h3.decode_many(batch)
    t1 = time.time()
    theirs_batch = o_batch.decode_many(batch)
    t2 = time.time()
    theirs_scalar = oracle.decode_many(batch)
    t3 = time.time()

    ok = len(mine) == len(theirs_scalar) and all(
        same_result(mine[i], theirs_scalar[i]) for i in range(len(mine)))
    n_dec = sum(1 for r in mine if r is not None)
    check(f"decode_many == oracle scalar ({batch.shape[0]} rows)", ok,
          f"decoded={n_dec} holo3={t1 - t0:.1f}s scalar={t3 - t2:.1f}s")
    ok2 = all(same_result(mine[i], theirs_batch[i]) for i in range(len(mine)))
    check("decode_many == holo2 batched", ok2,
          f"holo2={t2 - t1:.1f}s")
    check("decode_many empty batch",
          h3.decode_many(np.zeros((0, h3.N_WORD), dtype=np.uint8)) == [])

    # --- 8. lockstep BM + chien internals vs holo2 on dirty rows ---------
    synd_rows = h3._syndromes_many_words(batch[:8192])
    dirty = synd_rows.any(axis=1)
    s3, t3_, l3 = h3.berlekamp_massey_many(synd_rows[dirty])
    so, to, lo = o_batch.berlekamp_massey_many(synd_rows[dirty])
    check("berlekamp_massey_many == holo2",
          np.array_equal(s3, so) and np.array_equal(t3_, to)
          and np.array_equal(l3, lo))
    kept = (l3 <= h3.T) & (t3_ - 1 == l3)
    if kept.any():
        m3 = h3.chien_root_mask(s3[kept, :h3._SIGMA_WIDTH])
        mo = o_batch.chien_root_mask(so[kept, :h3._SIGMA_WIDTH])
        check("chien_root_mask == holo2", np.array_equal(m3, mo),
              f"rows={int(kept.sum())}")

    print()
    if FAILURES:
        print(f"VERIFY FAILED: {FAILURES}")
        sys.exit(1)
    print("VERIFY PASSED: holo3/lib/bch.py bit-exact vs src/holo scalar "
          "oracle and holo2 batched oracle")


if __name__ == "__main__":
    main()
