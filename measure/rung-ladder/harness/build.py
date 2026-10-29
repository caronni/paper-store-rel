# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/harness/build.py
"""Build candidate low-rate e-IRA codes with paperholo's FROZEN recipe
(paperholo.ldpc.build_code) and write them as holo-style json via
util/regen_holo_ldpc_data.code_document().  Variants (h14, f50) are NOT the
frozen recipe and are labelled as such.  Read-only on the repo; output in
<workdir>/data/ and <workdir>/build_log.json."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "util")); sys.path.insert(0, str(ROOT / "tests"))
from paperholo import ldpc
from regen_holo_ldpc_data import code_document  # reuses the writer

CANDIDATES = [("r0250", 1024), ("r0297", 1216), ("r0313", 1280),
              ("r0391", 1600), ("r0406", 1664), ("r0469", 1920)]
VARIANTS = [("r0313-h14", 1280, 14, 0.30), ("r0313-f50", 1280, 10, 0.50),
            ("r0391-h14", 1600, 14, 0.30), ("r0391-f50", 1600, 10, 0.50)]


def build_one(rid: str, k: int, heavy_deg: int, heavy_frac: float, out: Path, log: list) -> None:
    old = ldpc.HEAVY_FRAC
    ldpc.HEAVY_FRAC = heavy_frac          # monkeypatch (variants only)
    try:
        spec = ldpc.LdpcSpec(rid, k, heavy_deg=heavy_deg)
        t0 = time.perf_counter()
        try:
            code = ldpc.build_code(spec)
        except RuntimeError as e:
            log.append({"rate_id": rid, "k_bits": k, "heavy_deg": heavy_deg,
                        "heavy_frac": heavy_frac, "status": "FAILED", "error": str(e),
                        "seconds": time.perf_counter() - t0})
            print(rid, "FAILED", e); return
        dt = time.perf_counter() - t0
        doc = code_document(rid, code)
        doc["comment"] = (f"CANDIDATE built 2026-09-30 by scratch/rung-ladder-20260930/harness/build.py "
                          f"with paperholo.ldpc.build_code; heavy_frac={heavy_frac} "
                          f"({'FROZEN recipe' if heavy_frac == 0.30 and heavy_deg == 10 else 'VARIANT, not the frozen recipe'}); "
                          f"seed label {spec.seed_label!r}; NOT a format row")
        doc["heavy_frac"] = heavy_frac
        (out / f"{rid}.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        kb = k // 64; nh = round(heavy_frac * kb); mb = (4096 - k) // 64
        rec = {"rate_id": rid, "k_bits": k, "rate": k / 4096, "kb": kb, "mb": mb, "nh": nh,
               "heavy_deg": heavy_deg, "heavy_frac": heavy_frac, "restart": int(code.restart),
               "n_edges": int(code.n_edges), "seconds": round(dt, 2), "status": "OK",
               "seed_label": spec.seed_label.decode(),
               "deg_cap_rule_d": -(-(3 * (kb - nh) + heavy_deg * nh) // mb) + 1}
        log.append(rec); print(rec)
    finally:
        ldpc.HEAVY_FRAC = old


if __name__ == "__main__":
    out = WORK / "data"; log: list = []
    for rid, k in CANDIDATES:
        build_one(rid, k, 10, 0.30, out, log)
    for rid, k, hd, hf in VARIANTS:
        build_one(rid, k, hd, hf, out, log)
    (WORK / "build_log.json").write_text(json.dumps(log, indent=1) + "\n")
