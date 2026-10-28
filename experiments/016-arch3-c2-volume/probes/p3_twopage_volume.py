#!/usr/bin/env python
"""p3_twopage_volume — pre-registered zero-print probe (P3 item 3): the F13
placer's PAGE-HYPOTHESIS axis, measured on a synthetic 2-page volume.

Every fixture to date is single-page: place_fragment's page axis has never
carried a measurement. Semantics confirmed in place.py before this run:
the search set is the `pages` tuple intersected with the pages present in
`pending_cell_mask` (a page listed in `pages` but absent from the dict is
fully pruned); the winning page is encoded in Placement.page; the rival of
the global best pools ACROSS pages and rotations (every other hypothesis's
top peak + the best hypothesis's own out-of-shoulder 2nd peak) — so the
wrong-page mismatch floor feeds the decoy gate directly.

Construction:
  volume : 2-page VolumeSpec analogous to gen_e016.make_vspec (same e014
           page geometry, same r0550 rung, same K/N = 0.80; volume seed =
           gen_e016.SEED, so page 0 is pilot-identical to the printed e016
           sheet and page 1 is the fresh discrimination target — page
           identity lives ONLY in the pilot-word values, the site pattern
           is page-independent). Data = the make_data recipe (integers
           0..255, dtype=np.uint8) under the FRESH probe label, sized for
           2 pages.
  pieces : per page, N at 8 mm + N at 12 mm; seeded-uniform positions and
           angles (0-360); rendered by gen_confetti_synth.render_piece
           (the calibrated optical-only channel), white backing.
  detect : the session path verbatim — segment.segment_pieces on a padded
           per-piece canvas, then session_decode.piece_bits (scannorm
           pitch + canonical footing + segment.piece_cell_bits phase
           lock). No reimplementation.
  legs   : (A) two-page placement: pending {0: all-True, 1: all-True},
               session gap gate (gate_true=0.20, gate_decoy=0.20,
               rival-best >= 0.08); admission, correct-PAGE and correct-
               POSITION vs GT (center distance <= POS_TOL_CELLS), wall
               time per call;
           (B) wrong-page rejection: page-0 pieces offered pending
               {1: all-True} ONLY (truth absent) — ANY admission is a
               false placement;
           (C) timing: same pieces, single-page pending {0} vs the
               two-page call — the wall-cost ratio of the page axis.
               (For page-1 pieces the single-page {0} run doubles as a
               BONUS wrong-page rejection set, reported separately.)

RNG discipline: everything flows from ONE generator
rng(gen_e016.SEED, b"e016/p3-twopage/v1"), draws in this frozen order:
(1) data bytes; (2) per piece in (page, side_mm, index) lexicographic
order: y0 (integers), x0 (integers), angle (uniform), then render_piece's
internal noise normals.

Declared deviations (pre-registered axes honored, mechanics differ):
  * pieces are rendered one-per-padded-canvas at seeded-uniform field
    positions — no carve/shelf-pack (nothing is consumed; rects may
    overlap each other; placements are independent, so carving adds
    nothing to the page-axis question);
  * leg B passes pages=(1,) — semantically identical to pages=(0,1) with
    pending={1: ...} (absent page = fully pruned) but does not bill
    page-0 FFT work to the wrong-page timing.

Usage (from experiments/016-arch3-c2-volume/):
  ../../env/bin/python probes/p3_twopage_volume.py
      [--n 10] [--quick] [--out build/p3_twopage_volume.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

EXPDIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXPDIR))

from paperholo import compose, fountain, place, segment  # noqa: E402
from paperholo.modulation import rng                      # noqa: E402
import gen_confetti_session as gcs                        # noqa: E402
import gen_confetti_synth as gsyn                         # noqa: E402
import gen_e016                                           # noqa: E402
import session_decode as sd                               # noqa: E402

LABEL = b"e016/p3-twopage/v1"
SEED = gen_e016.SEED
OUT_DPI = gsyn.OUT_DPI            # 2400 dpi = 8 px/cell at c2
PAD_PX = 96                       # backing margin around each piece canvas
POS_TOL_CELLS = 5.0               # GT center-distance bar for correct-pos
GATE_TRUE = 0.20                  # session gap gate (016.4 frozen constants)
GATE_DECOY = 0.20
GATE_GAP = 0.08


def make_vspec2() -> fountain.VolumeSpec:
    """2-page volume analogous to gen_e016.make_vspec (same spec, same
    r0550, same K/N = 0.80; data sized for 2 pages)."""
    spec = gen_e016.make_spec()
    probe = fountain.VolumeSpec(n_pages=2, data_len_bytes=1, seed=SEED,
                                ldpc_rate_id="r0550", compose_spec=spec)
    k = int(gen_e016.K_OVER_N * probe.n_symbols_total)
    data_len = (k * probe.symbol_bits) // 8
    return fountain.VolumeSpec(n_pages=2, data_len_bytes=data_len,
                               seed=SEED, ldpc_rate_id="r0550",
                               compose_spec=spec)


def detect_piece(piece_img: np.ndarray, backing: int
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Session detection path, verbatim reuse: pad onto backing, segment,
    then session_decode.piece_bits (pitch + footing + phase lock)."""
    h, w = piece_img.shape
    canvas = np.full((h + 2 * PAD_PX, w + 2 * PAD_PX), backing, np.uint8)
    canvas[PAD_PX:PAD_PX + h, PAD_PX:PAD_PX + w] = piece_img
    cell_px = OUT_DPI / 600.0 * sd.CD
    pieces = segment.segment_pieces(canvas.astype(np.float32),
                                    cell_px=cell_px, dpi=OUT_DPI)
    if not pieces:
        return None
    return sd.piece_bits(pieces[0], OUT_DPI)   # biggest piece (sorted)


def timed_place(bits, mcell, spec, pages, pend) -> tuple[place.Placement,
                                                         float, bool]:
    t = time.perf_counter()
    pl = place.place_fragment(bits, spec, SEED, mask=mcell, pages=pages,
                              pending_cell_mask=pend,
                              gate_true=GATE_TRUE, gate_decoy=GATE_DECOY)
    dt = time.perf_counter() - t
    admitted = bool(pl.ok and (pl.rival_mismatch - pl.mismatch) >= GATE_GAP)
    return pl, dt, admitted


def gt_score(pl: place.Placement, gt_page: int, rect: tuple[int, int, int],
             bits: np.ndarray, mcell: np.ndarray,
             cells: dict[int, np.ndarray], H: int, W: int) -> dict:
    """Correctness of an (admitted or not) placement vs ground truth."""
    y0, x0, side = rect
    if pl.page is None or pl.origin_yx is None:
        return {"correct_page": False, "center_dist_cells": None,
                "correct_pos": False, "gt_agreement": None}
    bk = np.rot90(bits, pl.rot_k)
    mk = np.rot90(mcell, pl.rot_k)
    oy, ox = pl.origin_yx
    cy = oy + bk.shape[0] / 2.0
    cx = ox + bk.shape[1] / 2.0
    dist = float(np.hypot(cy - (y0 + side / 2.0), cx - (x0 + side / 2.0)))
    correct_page = pl.page == gt_page
    correct_pos = bool(correct_page and dist <= POS_TOL_CELLS)
    hh = min(bk.shape[0], H - oy)
    ww = min(bk.shape[1], W - ox)
    m = mk[:hh, :ww]
    agree = None
    if m.any():
        gt_win = cells[pl.page][oy:oy + hh, ox:ox + ww]
        agree = float((bk[:hh, :ww][m] == gt_win[m]).mean())
    return {"correct_page": bool(correct_page),
            "center_dist_cells": round(dist, 2),
            "correct_pos": correct_pos,
            "gt_agreement": None if agree is None else round(agree, 4)}


def pl_row(pl: place.Placement, dt: float, admitted: bool) -> dict:
    return {"ok": bool(pl.ok), "admitted": admitted,
            "page": None if pl.page is None else int(pl.page),
            "origin_yx": (None if pl.origin_yx is None
                          else [int(pl.origin_yx[0]), int(pl.origin_yx[1])]),
            "rot_k": None if pl.rot_k is None else int(pl.rot_k),
            "mismatch": round(float(pl.mismatch), 4),
            "rival_mismatch": round(float(pl.rival_mismatch), 4),
            "support": int(pl.support), "z": round(float(pl.z), 2),
            "z_gap": (None if not np.isfinite(pl.z_gap)
                      else round(float(pl.z_gap), 2)),
            "wall_s": round(dt, 3)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10,
                    help="pieces per (page, size) cell")
    ap.add_argument("--quick", action="store_true",
                    help="smoke run: --n 2")
    ap.add_argument("--out", type=Path,
                    default=EXPDIR / "build/p3_twopage_volume.json")
    args = ap.parse_args()
    n_per_cell = 2 if args.quick else args.n

    t_start = time.time()
    vspec = make_vspec2()
    spec = vspec.compose_spec
    H, W = spec.page_cells_yx
    gen = rng(SEED, LABEL)
    # draw 1 (frozen order): data bytes, the make_data recipe, fresh label
    data = gen.integers(0, 256, vspec.data_len_bytes,
                        dtype=np.uint8).tobytes()
    print(f"volume: {vspec.n_pages} pages, {vspec.data_len_bytes} data "
          f"bytes = {vspec.k_total} source / {vspec.n_symbols_total} "
          f"symbols x {vspec.symbol_bits} bits (K/N "
          f"{vspec.k_total / vspec.n_symbols_total:.3f}), r0550", flush=True)
    t0 = time.time()
    framed = fountain.encode_volume_pages(data, vspec)
    cells = {p: compose.compose_page(framed[p]["payload_bits"], spec, SEED,
                                     page=p).cell_values for p in (0, 1)}
    print(f"encode+compose 2 pages: {time.time() - t0:.1f} s", flush=True)
    refl = {p: np.where(cells[p] > 0, gsyn.INK, gsyn.PAPER
                        ).astype(np.float32) for p in (0, 1)}
    backing = gcs.BACKINGS["white"]
    cpmm = 600 / 25.4 / 2                       # cells per mm (11.81)

    # draw 2..: per piece in (page, side_mm, index) lexicographic order
    trials: list[dict] = []
    for page in (0, 1):
        for side_mm in (8, 12):
            side = int(side_mm * cpmm)
            for i in range(n_per_cell):
                y0 = int(gen.integers(0, H - side))
                x0 = int(gen.integers(0, W - side))
                ang = float(gen.uniform(0.0, 360.0))
                img = gsyn.render_piece(refl[page], (y0, x0, side), ang,
                                        backing, gen, gsyn.BLUR_SIGMA,
                                        gsyn.NOISE_SIGMA)
                trials.append({"id": f"pg{page}-{side_mm}mm-{i:02d}",
                               "gt_page": page, "side_mm": side_mm,
                               "rect_cells": [y0, x0, side],
                               "angle_deg": round(ang, 2), "_img": img})
    print(f"rendered {len(trials)} pieces "
          f"({n_per_cell}/page/size)", flush=True)

    pend_two = {0: np.ones((H, W), bool), 1: np.ones((H, W), bool)}
    pend_p0 = {0: pend_two[0]}
    pend_p1 = {1: pend_two[1]}

    for k, tr in enumerate(trials):
        img = tr.pop("_img")
        got = detect_piece(img, backing)
        tr["detect_ok"] = got is not None
        if got is None:
            print(f"[{k + 1}/{len(trials)}] {tr['id']}: DETECT FAIL",
                  flush=True)
            continue
        bits, mcell, _llr = got
        tr["grid_cells"] = [int(bits.shape[0]), int(bits.shape[1])]
        # leg A: two-page search
        pl, dt, adm = timed_place(bits, mcell, spec, (0, 1), pend_two)
        tr["legA_two_page"] = {**pl_row(pl, dt, adm),
                               **gt_score(pl, tr["gt_page"],
                                          tr["rect_cells"], bits, mcell,
                                          cells, H, W)}
        # leg C: single-page {0} (timing; for page-1 pieces also a bonus
        # wrong-page rejection set)
        pl_c, dt_c, adm_c = timed_place(bits, mcell, spec, (0,), pend_p0)
        tr["legC_single_page0"] = {**pl_row(pl_c, dt_c, adm_c),
                                   **gt_score(pl_c, tr["gt_page"],
                                              tr["rect_cells"], bits, mcell,
                                              cells, H, W)}
        # leg B: wrong-page offering (page-0 pieces vs pending {1} only)
        if tr["gt_page"] == 0:
            pl_b, dt_b, adm_b = timed_place(bits, mcell, spec, (1,), pend_p1)
            tr["legB_wrong_page"] = pl_row(pl_b, dt_b, adm_b)
        a = tr["legA_two_page"]
        print(f"[{k + 1}/{len(trials)}] {tr['id']}: A "
              f"{'ADMIT' if a['admitted'] else 'refuse'} "
              f"page={a['page']} mism={a['mismatch']:.3f} "
              f"rival={a['rival_mismatch']:.3f} "
              f"pos={'OK' if a['correct_pos'] else 'no'} "
              f"({dt:.2f}s two-page / {dt_c:.2f}s single)", flush=True)

    # ---- aggregates -------------------------------------------------------
    def agg_leg(rows: list[dict], leg: str) -> dict:
        sub = [r[leg] for r in rows if leg in r]
        adm = [s for s in sub if s["admitted"]]
        return {
            "n": len(sub),
            "admitted": len(adm),
            "admit_rate": round(len(adm) / len(sub), 3) if sub else None,
            "correct_page": sum(1 for s in adm if s.get("correct_page")),
            "correct_page_rate_of_admitted":
                (round(sum(1 for s in adm if s.get("correct_page"))
                       / len(adm), 3) if adm else None),
            "correct_pos": sum(1 for s in adm if s.get("correct_pos")),
            "correct_pos_rate_of_admitted":
                (round(sum(1 for s in adm if s.get("correct_pos"))
                       / len(adm), 3) if adm else None),
            "false_placements": sum(
                1 for s in adm if not s.get("correct_pos")),
            "gt_agreement_admitted": [s["gt_agreement"] for s in adm],
            "mean_wall_s": (round(float(np.mean([s["wall_s"] for s in sub])),
                                  3) if sub else None),
        }

    detected = [t for t in trials if t.get("detect_ok")]
    aggregates: dict = {"n_trials": len(trials),
                        "n_detect_ok": len(detected)}
    for side_mm in (8, 12):
        rows = [t for t in detected if t["side_mm"] == side_mm]
        aggregates[f"legA_{side_mm}mm"] = agg_leg(rows, "legA_two_page")
    aggregates["legA_all"] = agg_leg(detected, "legA_two_page")
    for page in (0, 1):
        rows = [t for t in detected if t["gt_page"] == page]
        aggregates[f"legA_page{page}"] = agg_leg(rows, "legA_two_page")

    # leg B: must-be-zero admissions
    b_rows = [t["legB_wrong_page"] for t in detected
              if "legB_wrong_page" in t]
    b_admitted = [s for s in b_rows if s["admitted"]]
    aggregates["legB_wrong_page"] = {
        "offered": len(b_rows),
        "admitted_FALSE_PLACEMENTS": len(b_admitted),
        "must_be_zero_pass": len(b_admitted) == 0,
        "min_best_mismatch": (round(min(s["mismatch"] for s in b_rows), 4)
                              if b_rows else None),
        "n_gate_ok_bar_gap": sum(1 for s in b_rows if s["ok"]),
    }
    # bonus wrong-page set: page-1 pieces through the single-page {0} search
    c1_rows = [t["legC_single_page0"] for t in detected if t["gt_page"] == 1
               and "legC_single_page0" in t]
    c1_admitted = [s for s in c1_rows if s["admitted"]]
    aggregates["legC_bonus_wrong_page_page1_vs_p0"] = {
        "offered": len(c1_rows),
        "admitted_FALSE_PLACEMENTS": len(c1_admitted),
        "min_best_mismatch": (round(min(s["mismatch"] for s in c1_rows), 4)
                              if c1_rows else None),
    }
    # leg C timing: cost ratio of the page axis (all detected pieces ran both)
    both = [t for t in detected
            if "legA_two_page" in t and "legC_single_page0" in t]
    tA = [t["legA_two_page"]["wall_s"] for t in both]
    tC = [t["legC_single_page0"]["wall_s"] for t in both]
    aggregates["timing"] = {
        "n": len(both),
        "two_page_mean_s": round(float(np.mean(tA)), 3) if tA else None,
        "single_page_mean_s": round(float(np.mean(tC)), 3) if tC else None,
        "two_over_single_ratio": (round(float(np.mean(tA) / np.mean(tC)), 2)
                                  if tA and tC else None),
        "two_page_range_s": ([round(min(tA), 3), round(max(tA), 3)]
                             if tA else None),
        "single_page_range_s": ([round(min(tC), 3), round(max(tC), 3)]
                                if tC else None),
    }

    report = {
        "probe": "p3_twopage_volume (P3 item 3: placer page-hypothesis axis)",
        "date": time.strftime("%Y-%m-%d"),
        "rng_label": LABEL.decode(),
        "rng_draw_order": "data bytes; then per piece (page, side_mm, "
                          "index): y0, x0, angle, render noise",
        "volume": {
            "n_pages": vspec.n_pages,
            "data_len_bytes": vspec.data_len_bytes,
            "data_sha256": hashlib.sha256(data).hexdigest(),
            "ldpc_rate_id": "r0550",
            "k_total": vspec.k_total,
            "n_symbols_total": vspec.n_symbols_total,
            "symbol_bits": vspec.symbol_bits,
            "k_over_n": round(vspec.k_total / vspec.n_symbols_total, 4),
            "seed": SEED.decode(),
            "note": "volume seed = gen_e016.SEED: page 0 pilot-identical "
                    "to the printed e016 sheet; page identity lives in the "
                    "pilot-word values only (site pattern page-independent)",
        },
        "channel": {"renderer": "gen_confetti_synth.render_piece",
                    "blur_sigma": gsyn.BLUR_SIGMA,
                    "noise_sigma": gsyn.NOISE_SIGMA,
                    "paper_ink": [gsyn.PAPER, gsyn.INK],
                    "backing_grey": backing, "out_dpi": OUT_DPI},
        "gate": {"gate_true": GATE_TRUE, "gate_decoy": GATE_DECOY,
                 "gap_min": GATE_GAP,
                 "pos_tol_cells": POS_TOL_CELLS},
        "n_per_page_per_size": n_per_cell,
        "placement_page_encoding":
            "Placement.page (int|None) = page of the winning (page, rot90, "
            "offset) hypothesis; pages searched = `pages` tuple INTERSECT "
            "pending_cell_mask keys (absent page = fully pruned); rival "
            "pools across pages and rotations",
        "deviations": [
            "pieces rendered one-per-padded-canvas at seeded-uniform "
            "positions (no carve/shelf-pack; rects may mutually overlap — "
            "placements independent, nothing consumed)",
            "leg B passes pages=(1,) — semantically identical to "
            "pages=(0,1) with pending={1:...}, without billing page-0 "
            "FFTs to the timing",
            f"quick run: n={n_per_cell} per cell" if args.quick else
            f"full pre-registered n={n_per_cell} per cell",
        ],
        "aggregates": aggregates,
        "trials": trials,
        "total_wall_s": round(time.time() - t_start, 1),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1))
    print(f"\nreport -> {args.out}", flush=True)
    la = aggregates["legA_all"]
    lb = aggregates["legB_wrong_page"]
    tm = aggregates["timing"]
    print(f"legA: {la['admitted']}/{la['n']} admitted, correct-page "
          f"{la['correct_page']}/{la['admitted']}, correct-pos "
          f"{la['correct_pos']}/{la['admitted']}", flush=True)
    print(f"legB wrong-page: {lb['admitted_FALSE_PLACEMENTS']}/"
          f"{lb['offered']} admitted (must be 0: "
          f"{'PASS' if lb['must_be_zero_pass'] else '*** FAIL ***'})",
          flush=True)
    print(f"timing: two-page {tm['two_page_mean_s']}s vs single "
          f"{tm['single_page_mean_s']}s (ratio "
          f"{tm['two_over_single_ratio']})", flush=True)
    print(f"total {report['total_wall_s']} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
