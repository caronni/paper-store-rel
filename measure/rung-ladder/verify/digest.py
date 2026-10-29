# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/verify/digest.py
"""Did the harness measure the code it says it measured?  (1) reload every
candidate json through holo's construct.load_code(data_dir=...), (2) rebuild
with paperholo.ldpc.build_code from the same seed label (HEAVY_FRAC
monkeypatched for the f50 variants), (3) compare sha256 over the '<i4'
lexsorted edge arrays (the golden-digest convention of
tests/holo/test_holo_ldpc.py), (4) also compare against what harness/codes.py
registers into construct._CODE_CACHE (the object the workers decode with),
and (5) cross-check a few structural claims of structure.json."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[3]; WORK = ROOT / "measure" / "rung-ladder"
sys.path.insert(0, str(ROOT / "src"))
from holo.core.ldpc import construct
from paperholo import ldpc as pl


def dig(code) -> str:
    return hashlib.sha256(code.edge_chk.astype("<i4").tobytes() + code.edge_var.astype("<i4").tobytes()).hexdigest()


SPECS = {"r0250": (1024, 10, 0.30), "r0297": (1216, 10, 0.30), "r0313": (1280, 10, 0.30), "r0391": (1600, 10, 0.30),
         "r0406": (1664, 10, 0.30), "r0469": (1920, 10, 0.30), "r0313-h14": (1280, 14, 0.30), "r0313-f50": (1280, 10, 0.50),
         "r0391-h14": (1600, 14, 0.30), "r0391-f50": (1600, 10, 0.50)}

res = {}
# holo reload of the candidate json (fresh LADDER entries, explicit data_dir)
for rid, (k, hd, hf) in SPECS.items():
    construct.LADDER[rid] = construct.LdpcSpec(rid, k, heavy_deg=hd)
    c = construct.load_code(rid, data_dir=WORK / "data")
    d = json.loads((WORK / "data" / f"{rid}.json").read_text())
    old = pl.HEAVY_FRAC; pl.HEAVY_FRAC = hf
    try:
        pc = pl.build_code(pl.LdpcSpec(rid, k, heavy_deg=hd))
    finally:
        pl.HEAVY_FRAC = old
    res[rid] = {"holo_reload": dig(c), "paperholo_build": dig(pc), "match": dig(c) == dig(pc),
                "json_restart": d["restart"], "build_restart": int(pc.restart), "json_heavy_frac": d.get("heavy_frac"),
                "nh_json": len(d["heavy_rows"]), "n_edges": c.n_edges}
# existing six: package data vs paperholo build (frozen recipe)
for rid, spec in pl.LDPC_LADDER.items():
    c = construct.load_code(rid); pc = pl.build_code(spec)
    res[rid] = {"holo_pkg": dig(c), "paperholo_build": dig(pc), "match": dig(c) == dig(pc), "n_edges": c.n_edges}
# what the harness workers actually decode with
sys.path.insert(0, str(WORK / "harness"))
construct._CODE_CACHE.clear()
import codes  # noqa: E402  (registers)
for rid in codes.ALL:
    hc = codes.code(rid)
    res[rid]["harness_cache"] = dig(hc)
    res[rid]["harness_matches_paperholo"] = dig(hc) == res[rid]["paperholo_build"]
    res[rid]["harness_spec"] = (codes.spec(rid).k_bits, codes.spec(rid).heavy_deg)
for rid, r in res.items():
    print(rid, "match" if r["match"] else "MISMATCH", "harness", "match" if r.get("harness_matches_paperholo") else "MISMATCH", r.get("harness_spec"), r["n_edges"])

# structural cross-checks
from holo.core.ldpc.decode import encode  # noqa: E402
st = json.loads((WORK / "structure.json").read_text())
chk = {}
for rid in ["r0313", "r0550", "r0547", "r0250"]:
    c = codes.code(rid); k = c.spec.k_bits; m = c.spec.m_bits
    info_edges = np.bincount(c.edge_chk[c.edge_var < k], minlength=m)
    chk[rid] = {"n_chk_no_info_edge_mine": int((info_edges == 0).sum()), "harness": st[rid]["n_chk_no_info_edge"],
                "chk_deg_mean_mine": float(np.bincount(c.edge_chk, minlength=m).mean()), "harness_mean": st[rid]["chk_deg_mean"]}
    if st[rid]["argmin_w2"]:
        i, j = st[rid]["argmin_w2"]
        e = np.zeros(k, np.uint8); e[i] = 1; e[j] = 1
        chk[rid]["w2_at_argmin_mine"] = int(encode(e, rid).sum()); chk[rid]["harness_min_w2"] = st[rid]["min_w2"]
    # single-bit min weight: brute force
    w1 = [int(encode(np.eye(1, k, i, dtype=np.uint8)[0], rid).sum()) for i in range(k)]
    chk[rid]["min_w1_mine"] = min(w1); chk[rid]["harness_min_w1"] = st[rid]["min_w1"]
print(json.dumps(chk, indent=1))
(Path(__file__).resolve().parent / "digest_results.json").write_text(json.dumps({"digests": res, "structure": chk}, indent=1) + "\n")
