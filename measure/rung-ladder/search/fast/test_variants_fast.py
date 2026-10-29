# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/fast/test_variants_fast.py
"""variants.run_chan_v_fast == variants.run_chan_v, dict for dict (und_w included), on every channel,
for an ARA-precoded and an IRAA mother graph (n > 4096, punctured LLRs 0.0), batch 7 and 64
(overnight prep 2026-09-30).  Also fastdecode.selfcheck on both registered variant rids.

  cd <repo> && PYTHONPATH=src:. env/bin/python \
      measure/rung-ladder/search/fast/test_variants_fast.py
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import common  # noqa: E402
import variants as V  # noqa: E402

N_T = 48
VCFGS = [dict(variant="ara", pre_frac=0.25, pre_sel="heavy"), dict(variant="iraa", iraa_frac=0.25, iraa_links="one"),
         dict(variant="ara", pre_frac=0.5, pre_sel="light")]
CHANS = [("bsc", {"p": 0.112}), ("awgn", {"esn0_db": -3.2, "sigma": common.sigma_of(-3.2)}),
         ("eras", {"p": 0.03, "eps": 0.3}), ("robust", {"esn0_db": -2.9, "sigma": common.sigma_of(-2.9), "f": 0.005}),
         ("bsc", {"p": 0.125})]


def one(case):
    i, (chn, prm) = case
    o = common.recipe_cfg(1664, 8, 0.5, 3, "balanced", 0)
    v = V.VCfg(outer=o, **VCFGS[i])
    rid = V.register_v(v)
    a = V.run_chan_v(rid, chn, prm, 5, N_T)
    bad = []
    for b in (7, 64):
        f = V.run_chan_v_fast(rid, chn, prm, 5, N_T, batch=b)
        if a != f:
            bad.append((b, a, f))
    import fastdecode
    return rid, chn, prm, a, bad, fastdecode.selfcheck(rid)


def main() -> int:
    cases = [(i, c) for i in range(len(VCFGS)) for c in CHANS]
    nbad = 0
    with ProcessPoolExecutor(8) as ex:
        for rid, chn, prm, a, bad, sc in ex.map(one, cases):
            print("OK " if not bad else "MISMATCH", rid, chn, {k: v for k, v in prm.items() if k != "sigma"},
                  {k: a[k] for k in ("fails", "undetected", "iters", "n_ok")}, f"und_w={len(a['und_w'])}", f"selfcheck={sc}")
            nbad += len(bad) + (not sc)
            for b, x, y in bad:
                print("   batch", b, "\n   prod:", x, "\n   fast:", y)
    print("VARIANTS: PASS" if nbad == 0 else f"VARIANTS: FAIL ({nbad})")
    return 1 if nbad else 0


if __name__ == "__main__":
    sys.exit(main())
