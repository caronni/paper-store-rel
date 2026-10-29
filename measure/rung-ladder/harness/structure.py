# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/harness/structure.py
"""Structural statistics per code -> <workdir>/structure.json."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import numpy as np
from scipy import sparse
sys.path.insert(0, str(Path(__file__).resolve().parent))
import codes  # noqa: E402  (registers everything)
from holo.core.ldpc.decode import encode  # noqa: E402
WORK = codes.WORK


def stats(rid: str) -> dict:
    c = codes.code(rid); sp = c.spec
    n, k, m = sp.n_bits, sp.k_bits, sp.m_bits
    chk = c.edge_chk.astype(np.int64); var = c.edge_var.astype(np.int64)
    H = sparse.csr_matrix((np.ones(chk.size, np.int64), (chk, var)), shape=(m, n))
    chk_deg = np.bincount(chk, minlength=m); var_deg = np.bincount(var, minlength=n)
    info_edges_per_chk = np.bincount(chk[var < k], minlength=m)
    HHt = (H @ H.T).tocoo()
    off = HHt.data[HHt.row != HHt.col]
    girth_gt4 = bool(off.max() <= 1) if off.size else True
    # single- and two-info-bit codeword weights (linear code: c_i xor c_j)
    t0 = time.perf_counter()
    cws = np.zeros((k, n), np.uint8)
    for i in range(k):
        e = np.zeros(k, np.uint8); e[i] = 1
        cws[i] = encode(e, rid)
    packed = np.packbits(cws, axis=1).view(np.uint64)  # (k, 64) — bit order irrelevant for popcount
    w1 = np.bitwise_count(packed).sum(axis=1).astype(np.int64)
    min2 = None; n2_le8 = 0; argmin2 = None
    for i in range(k - 1):
        a = np.bitwise_count(packed[i][None, :] & packed[i + 1:]).sum(axis=1)
        w2 = w1[i] + w1[i + 1:] - 2 * a
        j = int(np.argmin(w2)); mw = int(w2[j])
        if min2 is None or mw < min2:
            min2, argmin2 = mw, (i, i + 1 + j)
        n2_le8 += int((w2 <= 8).sum())
    dt = time.perf_counter() - t0
    nh = int(c.enc_info_col.size and (var_deg[:k] > 3).sum() // 64) if sp.heavy_deg != 3 else 0
    return {
        "rate_id": rid, "k_bits": k, "rate": k / n, "kb": k // 64, "mb": m // 64,
        "heavy_deg": sp.heavy_deg, "nh": int((var_deg[:k] == sp.heavy_deg).sum() // 64),
        "n_edges": int(c.n_edges),
        "chk_deg_hist": {int(d): int(v) for d, v in zip(*np.unique(chk_deg, return_counts=True))},
        "chk_deg_mean": float(chk_deg.mean()), "chk_deg_min": int(chk_deg.min()), "chk_deg_max": int(chk_deg.max()),
        "frac_chk_no_info_edge": float((info_edges_per_chk == 0).mean()),
        "n_chk_no_info_edge": int((info_edges_per_chk == 0).sum()),
        "var_deg_hist": {int(d): int(v) for d, v in zip(*np.unique(var_deg, return_counts=True))},
        "girth_gt4": girth_gt4, "HHt_offdiag_max": int(off.max()) if off.size else 0,
        "min_w1": int(w1.min()), "argmin_w1": int(np.argmin(w1)), "w1_le8": int((w1 <= 8).sum()),
        "min_w2": min2, "argmin_w2": argmin2, "n_w2_le8": n2_le8, "pair_seconds": round(dt, 1),
        "user_bits_p100": k - 32 - 100, "user_bits_p120": k - 32 - 120, "S_p120": k - 120 - 33,
    }


if __name__ == "__main__":
    out = {}
    for rid in codes.ALL:
        s = stats(rid); out[rid] = s
        print(rid, {kk: s[kk] for kk in ("n_edges", "chk_deg_min", "chk_deg_max", "frac_chk_no_info_edge", "girth_gt4", "min_w1", "min_w2", "n_w2_le8", "pair_seconds")}, flush=True)
    (WORK / "structure.json").write_text(json.dumps(out, indent=1) + "\n")
