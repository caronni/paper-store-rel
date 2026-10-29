# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/compare_runs.py
"""Decoder identity check (overnight prep 2026-09-30): the per-point OUTCOMES of two runs agree on every
(code, screen, channel, x, t0) both measured — fails, undetected, n, mean iterations and the und_w list
of every syndrome-valid wrong decode.  Used for --decoder prod vs --decoder fast.

  PYTHONPATH=src:. env/bin/python $S/compare_runs.py RUN_A RUN_B
"""
import json
import sys
from pathlib import Path


def points(d):
    out = {}
    for line in (Path(d) / "results.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["rid"] == "__meta__":
            continue
        if r["screen"] == "s0":
            # edge_sha only exists on lines written since the 2026-09-30 review: compared where both have it
            out[(r["rid"], "s0")] = (r["status"], tuple(r["reasons"]), r.get("build", {}).get("restart"),
                                     json.dumps(r.get("struct"), sort_keys=True))
            if r.get("build", {}).get("edge_sha"):
                out[(r["rid"], "s0-sha")] = r["build"]["edge_sha"]
            continue
        for p in r.get("points", []):
            x = p["params"].get("p", p["params"].get("esn0_db"))
            key = (r["rid"], r["screen"], p["channel"], round(x, 6), p["params"].get("f"), p.get("t0", 0))
            out[key] = (p["n"], p["fails"], p["und"], round(p["mean_iters"] or 0, 9), json.dumps(sorted(p.get("und_w", []))))   # chunk arrival order is scheduling
    return out


if __name__ == "__main__":
    a, b = points(sys.argv[1]), points(sys.argv[2])
    common = sorted(set(a) & set(b), key=str)
    diff = [k for k in common if a[k] != b[k]]
    pk = [k for k in common if not k[1].startswith("s0")]
    npts = len(pk)
    ndec = sum(a[k][0] for k in pk)
    nund = sum(a[k][2] for k in pk)
    print(f"common keys {len(common)} (s0 {len(common) - npts}, points {npts}, decodes {ndec}, undetected {nund}); "
          f"only in A {len(set(a) - set(b))}, only in B {len(set(b) - set(a))}; MISMATCHES {len(diff)}")
    for k in diff[:20]:
        print("  ", k, "\n     A", a[k], "\n     B", b[k])
    sys.exit(1 if diff else 0)
