# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/fast/test_fastdecode.py
"""Acceptance gate: decode_batch == production decode()/decode_soft(), bit for bit.

For every code (six frozen + candidate jsons), 300 LLR vectors across
channels; compare (ok, hard, n_iters) AND the extrinsic array (bytes, so
even signed zeros must agree) between production (one call per trial) and
decode_batch at B in {1, 8, 64}.  Any mismatch is printed with the trial
index and the first diverging field/position.

Run:  cd <repo> && PYTHONPATH=src:. env/bin/python \
      measure/rung-ladder/search/fast/test_fastdecode.py [--codes ...]
Exit status 0 iff every element of every comparison matches.
"""
from __future__ import annotations

import argparse
import json
import zlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(WORK / "harness"))

import codes as hcodes  # noqa: E402  (registers candidates as the harness does)
import channels as hch  # noqa: E402
from holo.core.ldpc import construct  # noqa: E402
from holo.core.ldpc.decode import decode, decode_soft, encode  # noqa: E402
from fastdecode import _seg_sum, decode_batch, decode_batch_simple  # noqa: E402

N = construct.N_BITS
DEFAULT_CODES = hcodes.EXISTING + ["r0406", "r0250", "r0391-h14"]
PER_CODE = 300
BATCHES = (1, 8, 64)


def make_llrs(rid: str, n_trials: int, seed: int = 7_000_000) -> tuple[np.ndarray, list[str]]:
    """300 vectors cycling over 12 channel settings (25 each)."""
    sp = construct.LADDER[rid]
    k = sp.k_bits
    R = k / N
    pcap = hch.bsc_capacity_p(R)
    es_sh = hch.biawgn_shannon_esn0_db(R)
    settings = ([("bsc", 1e-4), ("bsc", 0.35 * pcap)]
                + [("bsc", f * pcap) for f in (0.55, 0.75, 0.9)]
                + [("awgn", es_sh + d) for d in (1.6, 0.9, 0.3)]
                + [("eras", (0.5 * pcap, 0.4 * (1 - R))),
                   ("eras", (0.3 * pcap, 0.8 * (1 - R))),
                   ("inf", 0.7 * pcap), ("zero", 0.7 * pcap)])
    out, labels = [], []
    for t in range(n_trials):
        ch, prm = settings[t % len(settings)]
        g = np.random.default_rng(seed + 1000 * (zlib.crc32(rid.encode()) % 997) + t)
        info = g.integers(0, 2, k).astype(np.uint8)
        cw = encode(info, rid)
        if ch == "bsc":
            rx = cw ^ (g.random(N) < prm)
            llr = hch.hard_llr(rx, prm)
        elif ch == "awgn":
            s = np.sqrt(1 / (2 * 10 ** (prm / 10)))
            y = (1.0 - 2.0 * cw) + s * g.standard_normal(N)
            llr = -2.0 * y / (s * s)          # |llr| often > 20: exercises the clip
        elif ch == "eras":
            p, eps = prm
            rx = cw ^ (g.random(N) < p)
            llr = hch.hard_llr(rx, p)
            llr[g.random(N) < eps] = 0.0
        elif ch == "inf":                      # known bits as +-inf, some erasures
            rx = cw ^ (g.random(N) < prm)
            llr = hch.hard_llr(rx, prm)
            kn = g.random(N) < 0.05
            llr[kn] = np.where(cw[kn] == 1, np.inf, -np.inf)
            llr[g.random(N) < 0.03] = 0.0
            if t % 3 == 0:                     # a few confidently WRONG known bits
                j = g.integers(0, N, 2)
                llr[j] = np.where(cw[j] == 1, -np.inf, np.inf)
        else:                                  # exact zeros and -0.0, mixed magnitudes
            rx = cw ^ (g.random(N) < prm)
            llr = hch.hard_llr(rx, prm) * g.uniform(0.2, 3.0, N)
            z = g.random(N) < 0.08
            llr[z] = np.where(g.random(int(z.sum())) < 0.5, 0.0, -0.0)
        out.append(llr)
        labels.append(ch)
    return np.stack(out), labels


def check_code(rid: str) -> dict:
    code = construct.load_code(rid)
    X, labels = make_llrs(rid, PER_CODE)
    t0 = time.perf_counter()
    ref = [decode_soft(x, rid) for x in X]
    t_ref = time.perf_counter() - t0
    # decode() must agree with decode_soft()'s first three (it is the same _run)
    for i in range(0, PER_CODE, 25):
        a = decode(X[i], rid)
        assert a[0] == ref[i][0] and a[2] == ref[i][2] and np.array_equal(a[1], ref[i][1])
    mism = []
    for kern, B in [(decode_batch, b) for b in BATCHES] + [(decode_batch_simple, 64)]:
        for s in range(0, PER_CODE, B):
            ok, hard, nit, ext = kern(X[s:s + B], code, return_extrinsic=True)
            for j in range(ok.size):
                i = s + j
                r_ok, r_hard, r_n, r_ext = ref[i]
                where = None
                if bool(ok[j]) != bool(r_ok):
                    where = f"ok {bool(ok[j])} vs {r_ok}"
                elif int(nit[j]) != int(r_n):
                    where = f"n_iters {int(nit[j])} vs {r_n}"
                elif not np.array_equal(hard[j], r_hard):
                    where = f"hard first diff at bit {int(np.flatnonzero(hard[j] != r_hard)[0])}"
                elif ext[j].tobytes() != np.asarray(r_ext, np.float64).tobytes():
                    d = np.flatnonzero(ext[j].view(np.int64) != r_ext.view(np.int64))
                    where = f"extrinsic bytes differ at {d.size} bits, first {int(d[0])}"
                if where:
                    mism.append({"kernel": kern.__name__, "B": B, "trial": i, "channel": labels[i], "where": where})
    for mi in (0, 1, 5):                     # the break rule at tiny budgets
        sub = X[::5]
        r2 = [decode_soft(x, rid, max_iters=mi) for x in sub]
        ok, hard, nit, ext = decode_batch(sub, code, max_iters=mi, return_extrinsic=True)
        for j, (a, b, c, d) in enumerate(r2):
            if (bool(ok[j]) != a or int(nit[j]) != c or not np.array_equal(hard[j], b)
                    or ext[j].tobytes() != d.tobytes()):
                mism.append({"B": len(sub), "max_iters": mi, "trial": 5 * j,
                             "channel": labels[5 * j], "where": "max_iters edge case"})
    n_ok = sum(bool(r[0]) for r in ref)
    iters = [int(r[2]) for r in ref]
    return {"rid": rid, "k": code.spec.k_bits, "trials": PER_CODE, "ref_ok": n_ok,
            "iters_min": min(iters), "iters_max": max(iters),
            "n_zero_iter": sum(1 for v in iters if v == 0),
            "n_sp": sum(1 for v in iters if v > 60), "compared": PER_CODE * (len(BATCHES) + 1),
            "mismatches": mism, "ref_s": round(t_ref, 2)}


def check_seg_sum_model(trials: int = 400) -> int:
    """_seg_sum == np.add.reduceat per segment, bytes, degrees 1..40, with
    magnitudes spread over 1e-8..1e8 and signed zeros sprinkled in."""
    g = np.random.default_rng(11)
    bad = 0
    for d in range(1, 41):
        x = g.standard_normal((trials, d)) * 10.0 ** g.integers(-8, 9, (trials, d))
        z = g.random((trials, d)) < 0.15
        x[z] = np.where(g.random(int(z.sum())) < 0.5, 0.0, -0.0)
        ref = np.add.reduceat(x.ravel(), np.arange(0, trials * d, d))
        got = _seg_sum(np.ascontiguousarray(x.T)[:, None, :], d)[0]
        bad += int((ref.view(np.int64) != got.view(np.int64)).sum())
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", nargs="*", default=DEFAULT_CODES)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(check_code, a.codes))
    bad = check_seg_sum_model()
    print(f"reduceat float-add order model: {bad} byte mismatches over degrees 1..40")
    for r in res:
        bad += len(r["mismatches"])
        print(f"{r['rid']:>6} k={r['k']:4d} trials={r['trials']} ok={r['ref_ok']:3d} "
              f"iters {r['iters_min']}..{r['iters_max']} zero-iter={r['n_zero_iter']} "
              f"min-sum-failed(SP ran)={r['n_sp']} compared={r['compared']} "
              f"mismatches={len(r['mismatches'])}")
        for mm in r["mismatches"][:10]:
            print("   MISMATCH", mm)
    (HERE / "bitexact_result.json").write_text(json.dumps(res, indent=1))
    print("BIT-EXACT: PASS" if bad == 0 else f"BIT-EXACT: FAIL ({bad} mismatches)")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
