"""R11 smoke test on a painted synthetic page: the whole pipeline end to end, with assertions.

What: (1) the pins — the stratified PAVA equals fit_component_pava bit for bit on class-balanced strata (and on
one-state-per-class strata), the fold identities hold to 1e-9; (2) a small cmy4 page in the S14 contract
(measure.e041_scale_synth with SYNTH_BANDS = a c2 'detail' band and a c3 'smooth' band, no layout bands; painted
at 2400 dpi with blur 3 px, noise sd 8, shift (1.2, -0.7) mm, rotation 0.2 deg, scale 1.003 and the Y plane
displaced by (dy, dx) = (+4, +2) scan px), read back through extract.extract_capture (the readout's own
read_window): truth alignment (band-pooled nearest-mean state error < 0.5 % on both bands) and the Y offset
recovered (median Y - C pose within 1 px of (+4, +2)); (3) the calibration pipeline on the c2 band with seeded
feature noise added (sd --noise, so the states overlap as on paper; the page itself is too clean to
calibrate; --quick decodes at r0700 only): R-P page with LDPC, R-C cold start, the region gates and dead Y run,
and on the page the four
chains' information agrees within --tol bits on hi, lo, hi|lo and lo|hi (P-a), and their page-final LDPC
any-stage successes have no Wilson-disjoint pair.  The synthetic is plumbing only: iid noise, no screen, no dot
gain; no calibration conclusion is drawn from it.
Why: the builder's smoke gate.  How: --quick sizes run in under a minute once the painted TIFF is cached under
<art>/smoke/ (the first paint takes ~20 s); any failed assertion exits 1.

    cd <repo> && PYTHONPATH=src:. \\
        env/bin/python -m measure.cmy_calibration.smoke --quick
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import tifffile

from measure.cmy_calibration import controls, regimes
from measure.cmy_calibration.config import ARTEFACTS, RUNGS, Params
from measure.cmy_calibration.estimators import wilson
from measure.cmy_calibration.extract import band_pooled_errors, extract_capture
from measure.cmy_calibration.fit import build_band

PAINT = {"rot180": False, "shift_mm": (1.2, -0.7), "scale": 1.003, "rot_deg": 0.2, "pad_mm": 8.0, "blur_px": 3.0,
         "noise_sd": 8.0, "white": 255.0, "seed": 7}
Y_OFFSET_PX = (4.0, 2.0)


def synth_page(out: Path) -> tuple[Path, Path, dict[str, float]]:
    """(tiff, manifest, timings): the small cmy4 c2 + c3 page, painted once and cached by a parameter digest."""
    import measure.e041_scale_synth as ss
    from measure.e041_mixture_synth import M_SOLID, TONER_RGB
    saved = (ss.SYNTH_BANDS, ss.SYNTH_LAYOUT_BANDS)
    ss.SYNTH_BANDS = [("C2", "B", "off", ss.CMY4, M_SOLID, 2, "detail", "process", 368, 1),
                      ("C3", "B", "off", ss.CMY4, M_SOLID, 3, "smooth", "process", 372, 1)]
    ss.SYNTH_LAYOUT_BANDS = []
    try:
        man, npz = ss.build()
    finally:
        ss.SYNTH_BANDS, ss.SYNTH_LAYOUT_BANDS = saved
    out.mkdir(parents=True, exist_ok=True)
    mpath = out / "S14-synth.manifest.json"
    mpath.write_text(json.dumps(man, indent=1))
    np.savez_compressed(out / "S14-synth-bands.npz", **npz)
    digest = hashlib.sha256(json.dumps([PAINT, Y_OFFSET_PX, man["bands"]], sort_keys=True,
                                       default=str).encode()).hexdigest()[:12]
    tiff = out / f"cmy4-2400-{digest}.tiff"
    t = {"paint_s": 0.0}
    if not tiff.exists():
        t0 = time.time()
        img = ss.paint_scan(*ss.page_planes(man, npz), dict(TONER_RGB), {"Y": Y_OFFSET_PX}, scan_dpi=2400.0,
                            **PAINT)
        tifffile.imwrite(tiff, img, photometric="rgb", resolution=(2400.0, 2400.0), resolutionunit="INCH")
        t["paint_s"] = time.time() - t0
    return tiff, mpath, t


def check(name: str, ok: bool, detail: Any, results: list[dict[str, Any]]) -> None:
    results.append({"check": name, "pass": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def chains_equal(page: dict[str, Any], tol: float) -> tuple[bool, dict[str, Any]]:
    rows = [r for r in page["page"] if r["population"] == "P-a" and r["replicate"] == 0
            and r["chain"] in ("fallback", "lo-first", "hi-first", "six-maps") and r["weighting"] in ("w", "-")
            and r["form"] in ("hi", "lo", "hi|lo", "lo|hi")]
    spread = {}
    for form in ("hi", "lo", "hi|lo", "lo|hi"):
        v = {r["chain"]: r["I"]["est"] for r in rows if r["form"] == form}
        spread[form] = {"I": v, "spread": max(v.values()) - min(v.values())}
    return all(s["spread"] <= tol for s in spread.values()), spread


def ldpc_equal(page: dict[str, Any]) -> tuple[bool, list[str]]:
    by: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in page["ldpc"]:
        if r["population"] == "final" and r["mode"] == "any" and r["chain"] in ("fallback", "lo-first", "hi-first",
                                                                                 "six-maps") \
                and r["weighting"] in ("w", "-"):
            by.setdefault((r["stream"], r["rung"]), []).append(r)
    bad = []
    for key, rs in by.items():
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a = wilson(rs[i]["successes"], rs[i]["T"])
                b = wilson(rs[j]["successes"], rs[j]["T"])
                if a[1] < b[0] or b[1] < a[0]:
                    bad.append(f"{key}: {rs[i]['chain']} {rs[i]['successes']}/{rs[i]['T']} vs {rs[j]['chain']} "
                               f"{rs[j]['successes']}/{rs[j]['T']}")
    return not bad, bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="the < 60 s sizes")
    ap.add_argument("--art", default=str(ARTEFACTS))
    ap.add_argument("--noise", type=float, default=40.0,
                    help="feature-space noise sd added for the chain checks (every state pair must overlap)")
    ap.add_argument("--tol", type=float, default=0.02, help="bits: max spread of the chains' page information")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    t0 = time.time()
    art = Path(args.art)
    res: list[dict[str, Any]] = []
    c3 = controls.c3_pava(n_random=100 if args.quick else 300)
    check("weighted PAVA == fit_component_pava (class-balanced strata, bit for bit)",
          c3["class_balanced_exact"] and c3["class_balanced_max_abs"] == 0.0 and c3["conditional_identical"],
          {k: c3[k] for k in ("class_balanced_exact", "class_balanced_max_abs", "conditional_identical",
                              "n_random")}, res)
    check("state-balanced PAVA recovers the payload-prior map", c3["pass"],
          {k: c3[k] for k in ("payload_prior_mean_dp_weighted", "payload_prior_mean_dp_class_balanced")}, res)
    c2 = controls.c2_selfcheck(n_numeric=100_000 if args.quick else 1_000_000, n_decimal=20 if args.quick else 200)
    check("fold identities (numeric 1e-9, 60-digit decimal 1e-40)", c2["pass"],
          {k: {kk: v[kk] for kk in ("numeric_max_err", "decimal_max_err")} for k, v in c2.items() if k != "pass"}, res)
    tiff, mpath, tim = synth_page(art / "smoke")
    t1 = time.time()
    arrays, meta = extract_capture(tiff, mpath, 2400.0, ("C2", "C3"), False, lambda s: None,
                                   workers=args.workers)
    tim["extract_s"] = time.time() - t1
    for bi, name in enumerate(meta["band_names"]):
        sel = arrays["band"] == bi
        errs = band_pooled_errors(arrays["x_pp"][sel], arrays["y"][sel], arrays["win"][sel])
        mean_err = float(np.mean(list(errs.values())))
        check(f"truth alignment {name}: band-pooled state error < 0.5 %", mean_err < 0.005,
              {"mean_window_err": mean_err, "windows": len(errs), "skipped": meta["skipped"],
               "read_mode": meta["read_mode"]}, res)
    dy = float(np.nanmedian(arrays["w_Y_dy_vs_C_px"]))
    dx = float(np.nanmedian(arrays["w_Y_dx_vs_C_px"]))
    check("Y plane offset recovered (+4, +2) px", abs(dy - Y_OFFSET_PX[0]) <= 1.0 and abs(dx - Y_OFFSET_PX[1]) <= 1.0,
          {"dy_vs_C_px": dy, "dx_vs_C_px": dx}, res)
    band = build_band(arrays, meta, "C2", 20)
    rng = np.random.default_rng([20261010, 99, 20])
    band.X["F"] = band.X["F"] + rng.normal(0.0, args.noise, band.X["F"].shape)
    band.X["F1"] = band.X["F1"] + rng.normal(0.0, args.noise, band.X["F1"].shape)
    p = Params(T_page=12 if args.quick else 100, D_info=16 if args.quick else 100, D_ldpc=4 if args.quick else 40,
               B=100, B_slope=10, R=1, workers=args.workers, retry150=not args.quick)
    t2 = time.time()
    rungs = ("r0700",) if args.quick else RUNGS
    page = regimes.run_page(band, "F", p, rungs=rungs, log=lambda s: None)
    ok, spread = chains_equal(page, args.tol)
    check(f"chains equal on the synthetic page (P-a information spread <= {args.tol} bits)", ok, spread, res)
    ok, bad = ldpc_equal(page)
    lo_rates = {f"{r['chain']} {r['rung']}": f"{r['successes']}/{r['T']}" for r in page["ldpc"]
                if r["population"] == "final" and r["mode"] == "any" and r["stream"] == "lo"
                and r["weighting"] in ("w", "-") and r["chain"] != "oracle"}
    check("chains equal in page-final LDPC (no Wilson-disjoint pair)", ok, bad or lo_rates, res)
    fa = sum(r["false_accepts"] for r in page["ldpc"])
    check("no false accepts", fa == 0, fa, res)
    cold = regimes.run_cold(band, "F", 1, p, rungs=rungs, log=lambda s: None)
    check("cold start n=1 runs (draws, maps, gates, LDPC)", bool(cold["coldstart"]) and bool(cold["gates"])
          and bool(cold["ldpc"]), {"rows": len(cold["coldstart"]), "gates": len(cold["gates"]),
                                   "ldpc": len(cold["ldpc"]), "refusal": cold["coldstart"][0]["region_refusal_frac"]},
          res)
    dead = regimes.run_deady(band, "F", replace(p, R=1), sizes=(1,), T=8, D_info=8, D_ldpc=4, rungs=rungs,
                             log=lambda s: None)
    det = [r["detect_rate"] for r in dead["deadY"] if r["regime"] == "cold"]
    check("dead Y runs and the label-space collapse test fires", bool(det) and det[0] >= 0.75,
          {"detect_rate_n1": det[0] if det else None,
           "page_detect": [r["detect"] for r in dead["deadY"] if r["regime"] == "page"]}, res)
    tim["pipeline_s"] = time.time() - t2
    tim["total_s"] = time.time() - t0
    out = {"checks": res, "timings": tim, "params": {"noise": args.noise, "tol": args.tol, "quick": args.quick},
           "pass": all(r["pass"] for r in res)}
    (art / "smoke").mkdir(parents=True, exist_ok=True)
    (art / "smoke" / "smoke-quick.json").write_text(json.dumps(out, indent=1, default=str))
    print(f"smoke {'PASS' if out['pass'] else 'FAIL'} in {tim['total_s']:.1f} s ({json.dumps(tim)})")
    sys.exit(0 if out["pass"] else 1)


if __name__ == "__main__":
    main()
