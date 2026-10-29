"""P5-level-rates summary: net-density scenarios + confusion diagnostics
from probe17_level_rates_report.json (the record beside this file, or the
report given as the one argument). Pure post-processing, no scan access."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
from paperholo import ldpc  # noqa: E402

STATES7 = ("W", "C", "M", "Y", "CM", "CY", "MY")
CELLS_MM2_C3 = (600 / 25.4 / 3) ** 2
OVERHEAD = (1 - 0.0278) * (1 - 0.0075) * (1 - 0.026)  # pilots, dust(worst), edges


def rung_net(rung: str, yield_frac: float = 1.0) -> float:
    s = ldpc.LDPC_LADDER[rung]
    return s.rate * (1 - 32.0 / s.k_bits) * yield_frac


def scenario(name: str, per_level: dict[str, tuple[str, float]]) -> None:
    b_cell = sum(rung_net(r, y) for r, y in per_level.values())
    net = CELLS_MM2_C3 * OVERHEAD * b_cell
    parts = " ".join(f"{p}:{r}@{y:.3f}" for p, (r, y) in per_level.items())
    print(f"  {name}: {parts} -> {b_cell:.3f} b/cell -> {net:.1f} b/mm2")


def main() -> None:
    report = (Path(sys.argv[1]) if len(sys.argv) > 1 else
              Path(__file__).resolve().parent / "probe17_level_rates_report.json")
    rep = json.loads(report.read_text())
    for sc in rep["scans"]:
        print(f"\n== {sc['scan']} ==")
        conf = np.array(sc["state_confusion_7st"], np.float64)
        acc = np.trace(conf) / conf.sum()
        print(f"7-state cross-tile acc {acc:.4f}")
        # top confusions
        off = conf.copy()
        np.fill_diagonal(off, 0)
        idx = np.dstack(np.unravel_index(np.argsort(off, axis=None)[::-1],
                                         off.shape))[0][:8]
        row_n = conf.sum(axis=1)
        print("top confusions (true->pred, % of true state):")
        for a, b in idx:
            print(f"  {STATES7[a]:>3} -> {STATES7[b]:<3} "
                  f"{100 * off[a, b] / row_n[a]:5.2f}%")
        # W row: pilot luma relevance (W vs any-ink confusion)
        w_err = off[0].sum() / row_n[0]
        w_as_2ink = off[0, 4:].sum() / row_n[0]
        ink2_as_w = sum(off[s, 0] for s in (4, 5, 6)) / row_n[4:].sum()
        print(f"W misread as any ink {100 * w_err:.2f}% (as 2-ink states "
              f"{100 * w_as_2ink:.3f}%); 2-ink states misread as W "
              f"{100 * ink2_as_w:.3f}%")
        mi_sum = sum(sc["levels"][p]["mi_cal_splithalf_bits"] for p in "CMY")
        print(f"sum of per-level cal MI {mi_sum:.3f} b/cell "
              f"(x{CELLS_MM2_C3 * OVERHEAD:.2f} eff cells/mm2 = "
              f"{mi_sum * CELLS_MM2_C3 * OVERHEAD:.1f} b/mm2 soft ceiling, "
              f"parallel-decode footing)")

    print(f"\noverhead factor (2.78% pilots, 0.75% dust, 2.6% edges): "
          f"{OVERHEAD:.4f}; {CELLS_MM2_C3:.1f} cells/mm2 at c3")
    print("\n== net-density scenarios (rung, block yield from the overlay) ==")
    home = rep["scans"][0]["levels"]
    off_ = rep["scans"][1]["levels"]
    print("MEASURED anchors, 2 px/dot:")
    scenario("home M281 (conservative floor; Y leans on fountain headroom)",
             {"C": ("r0550", home["C"]["ldpc_measured"]["r0550"]["yield"]),
              "M": ("r0550", home["M"]["ldpc_measured"]["r0550"]["yield"]),
              "Y": ("r0550", home["Y"]["ldpc_measured"]["r0550"]["yield"])})
    scenario("home M281 rate-greedy (>=95% yield rungs)",
             {"C": ("r0625", home["C"]["ldpc_measured"]["r0625"]["yield"]),
              "M": ("r0625", home["M"]["ldpc_measured"]["r0625"]["yield"]),
              "Y": ("r0550", home["Y"]["ldpc_measured"]["r0550"]["yield"])})
    scenario("office AltaLink (healthy CMY)",
             {"C": ("r0625", off_["C"]["ldpc_measured"]["r0625"]["yield"]),
              "M": ("r0625", off_["M"]["ldpc_measured"]["r0625"]["yield"]),
              "Y": ("r0550", off_["Y"]["ldpc_measured"]["r0550"]["yield"])})
    print("ESTIMATE (Canon 8px/dot halves BER, 014.2-class expectation):")
    scenario("home + Canon-halved",
             {"C": ("r0625", home["C"]["ldpc_halved_ESTIMATE"]["r0625"]["yield"]),
              "M": ("r0700", home["M"]["ldpc_halved_ESTIMATE"]["r0700"]["yield"]),
              "Y": ("r0550", home["Y"]["ldpc_halved_ESTIMATE"]["r0550"]["yield"])})
    scenario("office + Canon-halved",
             {"C": ("r0700", off_["C"]["ldpc_halved_ESTIMATE"]["r0700"]["yield"]),
              "M": ("r0700", off_["M"]["ldpc_halved_ESTIMATE"]["r0700"]["yield"]),
              "Y": ("r0625", off_["Y"]["ldpc_halved_ESTIMATE"]["r0625"]["yield"])})


if __name__ == "__main__":
    main()
