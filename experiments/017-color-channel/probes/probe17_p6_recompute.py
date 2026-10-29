#!/usr/bin/env python
"""probe17_p6_recompute.py — P6 seven-vs-eight decision numbers, part A.

Recomputes (tonight, from the archived cross-validated confusion matrices of
the REAL scans) every MI/capacity/subset number the 7-vs-8-state decision
rests on, plus per-level (C/M/Y presence bit) BER and the CMY-triple
confusion structure, on both engines.

Data sources (all measured, hard-decision CV confusion counts; the build/
dirs are flags, --e002-build and --e004-build):
  - experiments/002-calibration-page/build/calpage_report.json        (home M281, CAL-1, 2026-07-04)
  - experiments/002-calibration-page/build/calpage_report_xerox.json  (AltaLink C8245 print, home flatbed scan)
  - experiments/002-calibration-page/build/overlap2_report.json       (home M281, 002.2 printed 7-state fields)
  - experiments/004-finalists-checkerboard/build/e004_report{,_xerox}.json (A3 7st-c3 cross-tile)

Machinery reused verbatim: analyze_overlap2.blahut_arimoto /
best_uniform_subsets / _row_normalize (the 002.0c port).

Run: env/bin/python experiments/017-color-channel/probes/probe17_p6_recompute.py \\
         --e002-build <002's build> --e004-build <004's build>
Writes experiments/017-color-channel/build/probe17_p6_recompute.json (the
record is the copy beside this file).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "experiments" / "002-calibration-page"))

import analyze_overlap2 as ao2  # noqa: E402
import cal_color as ccol  # noqa: E402

B002 = Path()  # set from --e002-build
B004 = Path()  # set from --e004-build

# state index -> name for the raw 3-bit CMY field (bit0=C, bit1=M, bit2=Y)
NAMES8 = ["W", "C", "M", "CM", "Y", "CY", "MY", "CMY"]
BITS8 = np.array([[s >> i & 1 for i in range(3)] for s in range(8)])  # (8,3) C,M,Y
NAMES16 = [("".join(p for i, p in enumerate("CMYK") if s >> i & 1) or "W")
           for s in range(16)]
# 002.2/e004 printed 7-state order:
NAMES7 = ["W", "C", "M", "Y", "CM", "CY", "MY"]
BITS7 = np.array([[int(p in n) for p in "CMY"] for n in NAMES7])  # (7,3)


def mi_uniform(conf: np.ndarray) -> float:
    return ccol._mi_bits_from_counts(conf.astype(np.float64))


def per_level_ber(conf: np.ndarray, bits: np.ndarray) -> dict:
    """Per-level presence-bit BER implied by the confusion counts."""
    total = conf.sum()
    out = {}
    for li, name in enumerate("CMY"):
        diff = bits[:, li][:, None] != bits[:, li][None, :bits.shape[0]]
        # conf may be square (n,n) with same in/out alphabet
        out[name] = float((conf * diff[: conf.shape[0], : conf.shape[1]]).sum() / total)
    out["mean"] = float(np.mean([out[p] for p in "CMY"]))
    return out


def per_level_ber_restricted(conf: np.ndarray, bits: np.ndarray,
                             rows: list[int]) -> dict:
    """Per-level bit BER over a subset of TRUE states (rows), full output."""
    sub = conf[rows, :]
    total = sub.sum()
    out = {}
    for li, name in enumerate("CMY"):
        diff = bits[rows, li][:, None] != bits[None, : conf.shape[1], li][0][None, :]
        out[name] = float((sub * diff).sum() / total)
    out["mean"] = float(np.mean([out[p] for p in "CMY"]))
    return out


def triple_structure(conf: np.ndarray, names: list[str], tri: int) -> dict:
    """Row (what true-CMY decodes as) + column (what steals CMY's identity)."""
    row = conf[tri].astype(float)
    col = conf[:, tri].astype(float)
    n = conf.sum(axis=1)
    return {
        "true_CMY_decoded_as": {names[j]: round(float(row[j] / max(row.sum(), 1)), 4)
                                for j in np.argsort(-row) if row[j] > 0},
        "CMY_row_accuracy": round(float(row[tri] / max(row.sum(), 1)), 4),
        "decoded_CMY_true_was": {names[j]: round(float(col[j] / max(col.sum(), 1)), 4)
                                 for j in np.argsort(-col) if col[j] > 0},
        "false_CMY_rate_nontriple": round(float(
            (col.sum() - col[tri]) / max(n.sum() - n[tri], 1)), 4),
    }


def analyze8(conf: np.ndarray, label: str) -> dict:
    ba = ao2.blahut_arimoto(ao2._row_normalize(conf))
    subs = ao2.best_uniform_subsets(conf, NAMES8)
    acc = float(np.trace(conf) / conf.sum())
    nontri = [s for s in range(8) if s != 7]
    res = {
        "label": label,
        "n_cells": int(conf.sum()),
        "accuracy": round(acc, 4),
        "mi_uniform8": round(mi_uniform(conf), 4),
        "ba_capacity": round(ba["capacity_bits"], 4),
        "ba_input_dist": {NAMES8[i]: round(p, 4) for i, p in enumerate(ba["input_dist"])},
        "best7_subset": {"states": subs["7"]["states"],
                         "mi": round(subs["7"]["mi_bits"], 4)},
        "best6_subset": {"states": subs["6"]["states"],
                         "mi": round(subs["6"]["mi_bits"], 4)},
        "per_level_bit_ber_all_cells": per_level_ber(conf, BITS8),
        "per_level_bit_ber_true_nontriple": per_level_ber_restricted(conf, BITS8, nontri),
        "per_level_bit_ber_true_triple": per_level_ber_restricted(conf, BITS8, [7]),
        "triple_confusion": triple_structure(conf, NAMES8, 7),
        "per_state_accuracy": {NAMES8[i]: round(float(conf[i, i] / max(conf[i].sum(), 1)), 4)
                               for i in range(8)},
    }
    return res


def analyze7(conf: np.ndarray, label: str, names: list[str]) -> dict:
    bits = np.array([[int(p in n) for p in "CMY"] for n in names])
    ba = ao2.blahut_arimoto(ao2._row_normalize(conf))
    acc = float(np.trace(conf) / conf.sum())
    return {
        "label": label,
        "n_cells": int(conf.sum()),
        "accuracy": round(acc, 4),
        "mi_uniform": round(mi_uniform(conf), 4),
        "ba_capacity": round(ba["capacity_bits"], 4),
        "per_level_bit_ber": per_level_ber(conf, bits),
        "per_state_accuracy": {names[i]: round(float(conf[i, i] / max(conf[i].sum(), 1)), 4)
                               for i in range(len(names))},
    }


def main() -> None:
    out: dict = {"provenance": {}}

    # --- CAL-1 state8 fields, both engines -------------------------------
    for eng, rep in (("home_m281", "calpage_report.json"),
                     ("xerox_altalink", "calpage_report_xerox.json")):
        r = json.load(open(B002 / rep))
        out["provenance"][eng] = {"report": rep, "scan": r["scan"].get("path", "?"),
                                  "scan_sha256": r["scan"].get("sha256", "?")}
        ca = r["families"]["density_color"]["color_alphabet"]
        s8 = ca["state8"]
        conf8 = np.array(s8["confusion"], np.int64)
        a = analyze8(conf8, f"{eng} CAL-1 state8_c3 (printed 8-state, cell=3)")
        a["stored_mi_check"] = round(float(s8["mi_bits"]), 4)
        a["stored_bit_ber_check"] = s8["classifier_bit_ber"]
        out[f"{eng}_state8_c3"] = a

        # 16-state: best-8 subset (the {7+K} = 1.801 home anchor)
        s16 = ca["state16"]
        conf16 = np.array(s16["confusion"], np.int64)
        subs16 = ao2.best_uniform_subsets(conf16, NAMES16)
        ba16 = ao2.blahut_arimoto(ao2._row_normalize(conf16))
        out[f"{eng}_state16_c3"] = {
            "mi_uniform16": round(mi_uniform(conf16), 4),
            "stored_mi_check": round(float(s16["mi_bits"]), 4),
            "ba_capacity": round(ba16["capacity_bits"], 4),
            "best8_subset": {"states": subs16["8"]["states"],
                             "mi": round(subs16["8"]["mi_bits"], 4)},
            "best7_subset": {"states": subs16["7"]["states"],
                             "mi": round(subs16["7"]["mi_bits"], 4)},
        }

    # --- 002.2 overlap2 printed 7-state fields (home M281) ---------------
    r = json.load(open(B002 / "overlap2_report.json"))
    out["provenance"]["overlap2"] = {"scan": r["scan"], "sha_note": "see report"}
    af = r["blockA"]["alphabet_fields"]
    for fld in ("A1/state7_c3", "A1/state7_c4", "A1/state7_c6"):
        f = af[fld]
        conf = np.array(f["confusion"], np.int64)
        a = analyze7(conf, f"home_m281 002.2 printed {fld}", f["state_names"])
        a["stored_mi_check"] = round(float(f["mi_bits_uniform"]), 4)
        out["home_overlap2_" + fld.split("/")[1]] = a
    f8k = af["A2/state8k_c4"]
    conf8k = np.array(f8k["confusion"], np.int64)
    subs8k = ao2.best_uniform_subsets(conf8k, f8k["state_names"])
    out["home_overlap2_state8k_c4"] = {
        "mi_uniform8": round(mi_uniform(conf8k), 4),
        "stored_mi_check": round(float(f8k["mi_bits_uniform"]), 4),
        "best7_subset": {"states": subs8k["7"]["states"],
                         "mi": round(subs8k["7"]["mi_bits"], 4)},
        "note": "8th state here is K (no CMY triple printed on this field)",
    }

    # --- e004 A3 7-state cross-tile, both engines -------------------------
    for eng, rep in (("home_m281", "e004_report.json"),
                     ("xerox_altalink", "e004_report_xerox.json")):
        r = json.load(open(B004 / rep))
        ct = r["classes"]["A3"]["cross_tile"]
        conf = np.array(ct["confusion"], np.int64)
        a = analyze7(conf, f"{eng} e004 A3 7st-c3 cross-tile (16 tiles page-balanced)",
                     NAMES7)
        a["stored_mi_check"] = round(float(ct["mi_bits"]), 4)
        a["scan"] = r["scan"]
        out[f"{eng}_e004_A3_crosstile"] = a

    outp = REPO / "experiments/017-color-channel/build/probe17_p6_recompute.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(outp, "w"), indent=1)
    print(json.dumps(out, indent=1))
    print(f"\nwritten: {outp}")


if __name__ == "__main__":
    _ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    _ap.add_argument("--e002-build", type=Path, required=True)
    _ap.add_argument("--e004-build", type=Path, required=True)
    _args = _ap.parse_args()
    B002, B004 = _args.e002_build, _args.e004_build
    main()
