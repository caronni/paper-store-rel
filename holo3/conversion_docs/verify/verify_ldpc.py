# verify_ldpc.py — B2 build-time verification (throwaway; comments allowed here).
#
# Proves, in ONE process:
#   1. holo3/lib/ldpc_data/*.json byte-identical to src/holo/core/ldpc/data/*.json.
#   2. The six golden edge digests (tests/holo/test_holo_ldpc.py:43-57) reproduce
#      from holo3's eager CODES, and every derived Code array equals the oracle's.
#   3. encode(info, code) == oracle encode(info, rate_id) on random info words.
#   4. decode(llr, code, max_iters, alpha) == oracle decode_soft(llr, rate_id, ...)
#      EXACTLY (syndrome_ok, hard bytes, n_iters, extrinsic bit-identical floats)
#      on >=200 vectors per rung: clean encodes, BSC noise at several flip rates,
#      erasure-punched vectors, +-inf known bits (incl. some wrong infs), pure
#      gaussian junk; max_iters in {0, 60, 150}, a few alpha=0.75 off-default.
#
# Run:  cd <checkout> && \
#       PYTHONPATH=.:src:holo2/src env314t/bin/python _distill/verify/verify_ldpc.py

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import numpy as np

from holo3.lib import ldpc as h3

from holo.core.ldpc import construct as o_construct
from holo.core.ldpc.decode import decode_soft as o_decode_soft
from holo.core.ldpc.decode import encode as o_encode

ROOT = Path("<checkout>")
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

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)
        print(f"FAIL: {msg}")


def exact_eq(a: np.ndarray, b: np.ndarray) -> bool:
    return (a.dtype == b.dtype and a.shape == b.shape
            and np.array_equal(a, b))


# ---- 1. data JSON byte identity --------------------------------------------
for rid in sorted(GOLDEN_EDGES):
    src = (ROOT / "src/holo/core/ldpc/data" / f"{rid}.json").read_bytes()
    dst = (ROOT / "holo3/lib/ldpc_data" / f"{rid}.json").read_bytes()
    check(src == dst, f"{rid}.json not byte-identical")
    sha = hashlib.sha256(dst).hexdigest()
    print(f"data {rid}.json sha256 {sha[:16]}… byte-identical={src == dst}")

# ---- 2. edge digests + structural parity vs oracle -------------------------
check(tuple(sorted(h3.CODES)) == tuple(sorted(GOLDEN_EDGES)),
      f"CODES keys {sorted(h3.CODES)}")
for rid in sorted(GOLDEN_EDGES):
    c3 = h3.CODES[rid]
    oc = o_construct.load_code(rid)
    digest = hashlib.sha256(
        c3.edge_chk.astype("<i4").tobytes()
        + c3.edge_var.astype("<i4").tobytes()).hexdigest()
    check(digest == GOLDEN_EDGES[rid], f"{rid}: edge digest {digest}")
    check(c3.k_bits == oc.spec.k_bits and c3.n_bits == oc.spec.n_bits,
          f"{rid}: k/n mismatch")
    for name in ("edge_chk", "edge_var", "chk_starts", "var_order",
                 "var_starts", "enc_info_col", "enc_rows", "enc_row_starts"):
        check(exact_eq(getattr(c3, name), getattr(oc, name)),
              f"{rid}: Code.{name} != oracle")
    check(not c3.edge_chk.flags.writeable, f"{rid}: arrays writable")
    print(f"code {rid}: E={c3.edge_chk.size} digest ok, "
          f"all 8 derived arrays == oracle")

# ---- 3+4. encode + decode parity -------------------------------------------
rng = np.random.default_rng(20260828)
t0 = time.time()
for rid in sorted(GOLDEN_EDGES):
    c3 = h3.CODES[rid]
    n, k = c3.n_bits, c3.k_bits
    n_enc = 0
    n_dec = 0
    outcomes = {True: 0, False: 0}
    cases: list[tuple[np.ndarray, int, float]] = []

    # clean encodes (early-exit n_iters=0 path) — also the encode parity set
    for _ in range(60):
        info = rng.integers(0, 2, k, dtype=np.uint8)
        cw3 = h3.encode(info, c3)
        cwo = o_encode(info, rid)
        check(exact_eq(cw3, cwo), f"{rid}: encode mismatch")
        n_enc += 1
        cases.append(((2.0 * cw3 - 1.0) * 8.0, 60, 0.8))

    # BSC noise at several flip rates, mixed magnitudes / iteration caps
    for i in range(80):
        info = rng.integers(0, 2, k, dtype=np.uint8)
        cw = o_encode(info, rid).astype(np.float64)
        p = (0.02, 0.035, 0.05, 0.08)[i % 4]
        flips = rng.random(n) < p
        y = np.where(flips, 1.0 - cw, cw)
        mag = (4.0, 8.0, 2.5)[i % 3]
        max_iters = 150 if i % 10 == 7 else (0 if i % 10 == 8 else 60)
        alpha = 0.75 if i % 20 == 13 else 0.8
        cases.append(((2.0 * y - 1.0) * mag, max_iters, alpha))

    # erasures (exact 0.0) on top of light BSC noise
    for i in range(40):
        info = rng.integers(0, 2, k, dtype=np.uint8)
        cw = o_encode(info, rid).astype(np.float64)
        flips = rng.random(n) < 0.02
        y = np.where(flips, 1.0 - cw, cw)
        llr = (2.0 * y - 1.0) * 6.0
        frac = 0.1 + 0.3 * rng.random()
        erased = rng.random(n) < frac
        llr[erased] = 0.0
        cases.append((llr, 150 if i % 8 == 5 else 60, 0.8))

    # +-inf known bits (mostly true, a few wrong) over BSC noise
    for i in range(10):
        info = rng.integers(0, 2, k, dtype=np.uint8)
        cw = o_encode(info, rid).astype(np.float64)
        flips = rng.random(n) < 0.05
        y = np.where(flips, 1.0 - cw, cw)
        llr = (2.0 * y - 1.0) * 4.0
        known = rng.choice(n, size=200, replace=False)
        llr[known] = np.where(cw[known] > 0.5, np.inf, -np.inf)
        if i % 2:
            wrong = rng.choice(known, size=3, replace=False)
            llr[wrong] = -llr[wrong]
        cases.append((llr, 60, 0.8))

    # pure gaussian junk — guaranteed failures, full hybrid 60+60 path
    for i in range(10):
        cases.append((rng.normal(0.0, 3.0, n), 60 if i % 2 else 150, 0.8))

    for llr, max_iters, alpha in cases:
        ok3, hard3, it3, ext3 = h3.decode(llr, c3, max_iters, alpha)
        oko, hardo, ito, exto = o_decode_soft(llr, rid, max_iters, alpha)
        check(ok3 == oko, f"{rid}: syndrome_ok {ok3} != {oko}")
        check(exact_eq(hard3, hardo), f"{rid}: hard bits mismatch")
        check(it3 == ito, f"{rid}: n_iters {it3} != {ito}")
        check(ext3.dtype == exto.dtype == np.float64
              and np.array_equal(ext3, exto),
              f"{rid}: extrinsic not bit-identical")
        outcomes[ok3] += 1
        n_dec += 1

    print(f"decode {rid}: {n_dec} vectors "
          f"(ok={outcomes[True]}, fail={outcomes[False]}), "
          f"encode parity on {n_enc} words — all exact")

print(f"decode parity wall time {time.time() - t0:.1f}s")
if failures:
    print(f"VERIFY FAILED: {len(failures)} failures")
    sys.exit(1)
print("VERIFY OK: ldpc data byte-identical, six edge digests reproduce, "
      "Code structures == oracle, encode parity, decode parity exact "
      "(syndrome_ok/hard/n_iters/extrinsic) on 200 vectors x 6 rungs")
