"""Aggregate probe17_out/*.json into the P2 comparison table."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "probe17_out"


def agg(case: str) -> None:
    r = json.load(open(OUT / f"{case}.json"))
    groups: dict[str, list[dict]] = {}
    for t in r["tiles"]:
        groups.setdefault(t.get("class", "?"), []).append(t)
    print(f"\n### {case}  ({r.get('scan')})")
    st = r.get("affine_stats", {})
    if st:
        print(f"    affine px/dot x={st.get('px_per_dot_x')} "
              f"y={st.get('px_per_dot_y')} rot={st.get('rotation_deg')}deg")
    for cls, ts in groups.items():
        n = len(ts)
        cell = ts[0].get("cell_dots")
        # mcp fundamental identification
        exp_v = np.array([t["expected_pitch_v_px"] for t in ts
                          if "expected_pitch_v_px" in t])
        pit = np.array([t["mcp"].get("pitch_px", np.nan) for t in ts])
        nominal = 2.0 * cell if exp_v.size else None
        ok_id = (np.abs(pit / (exp_v if exp_v.size else nominal) - 1) < 0.04
                 ).sum() if nominal else 0
        # lock errors vs affine GT
        ev = np.array([t["lock"].get("pitch_v_px", np.nan)
                       / t["expected_pitch_v_px"] - 1 for t in ts
                       if "pitch_v_px" in t.get("lock", {})]) * 100
        eu = np.array([t["lock"].get("pitch_u_px", np.nan)
                       / t["expected_pitch_u_px"] - 1 for t in ts
                       if "pitch_u_px" in t.get("lock", {})]) * 100
        q = np.array([t["lock"].get("quality_mean", np.nan) for t in ts])
        cv = np.array([max(t["coherence"]["v48"], t["coherence"]["v96"])
                       for t in ts if "coherence" in t])
        cu = np.array([max(t["coherence"]["u48"], t["coherence"]["u96"])
                       for t in ts if "coherence" in t])

        def line_med(name, field="contrast"):
            vals = [t["lines"][name].get(field) for t in ts
                    if name in t.get("lines", {})
                    and field in t["lines"][name]]
            return float(np.median(vals)) if vals else float("nan")

        print(f"  {cls} (c{cell}, n={n}):")
        print(f"    mcp fundamental == cell pitch: {ok_id}/{n}"
              f"   (chosen median {np.nanmedian(pit):.3f} px)")
        print(f"    line contrast (median): cell_tight "
              f"{line_med('cell_tight'):6.1f} | comb11 "
              f"{line_med('comb11'):6.1f} | 165lpi {line_med('165lpi'):5.1f}"
              f" (ang {line_med('165lpi', 'angle_deg'):.1f}) | 224lpi "
              f"{line_med('224lpi'):5.1f} | 306lpi {line_med('306lpi'):5.1f}")
        if ev.size:
            print(f"    lock pitch err %: v med {np.nanmedian(np.abs(ev)):.2f}"
                  f" max {np.nanmax(np.abs(ev)):.2f} "
                  f"(>2%: {(np.abs(ev) > 2).sum()}/{ev.size}) | "
                  f"u med {np.nanmedian(np.abs(eu)):.2f} "
                  f"max {np.nanmax(np.abs(eu)):.2f} "
                  f"(>2%: {(np.abs(eu) > 2).sum()}/{eu.size})")
        if cv.size:
            print(f"    coherence best-of-band: v med {np.nanmedian(cv):.2f} "
                  f"min {np.nanmin(cv):.2f} | u med {np.nanmedian(cu):.2f} "
                  f"min {np.nanmin(cu):.2f} | quality med "
                  f"{np.nanmedian(q):.3f}")


if __name__ == "__main__":
    cases = sys.argv[1:] or [p.stem for p in sorted(OUT.glob("*.json"))]
    for c in cases:
        agg(c)
