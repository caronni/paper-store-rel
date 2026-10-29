#!/usr/bin/env python
"""E023 qualification on the real v2.2 six-scan states (both footings).

Two PRE-REGISTERED gates (README section 3):
  (a) ZERO wrong certifications — GT audit vs the e018 render truth
      (build/e018_gt, never regenerated: the 018.7 drift rule);
  (b) >= 95% certification of the NONDEGENERATE tiles with >= 95%
      GEOMETRIC coverage on the frozen DECIMATED state (the round-4
      denominator: 641 tiles).

Plus the self-contained instruments and GT-domain diagnostics:
coverage-vs-certification curve, held-out calibration honesty (log-loss +
predicted-vs-realized BER), staged-merge ablation (stage-1 union vs
+stage-2 sum vs sum-only vs best-single-scan), core-edge-distance BER,
context-conditioned error breakdown (ink-neighbor count), unresolved-
sliver census from the e022 audit, CRC attempt-budget ledger.

  env/bin/python experiments/023-payload-tiles/qualify_e023.py \
      --e018-gt <018's build>/e018_gt \\
      --decimated <022's build>/session_state.pkl \\
      --native <022's build>/session_native.pkl [--quick]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import compose, ldpc, payloaddec  # noqa: E402
from paperholo.formats import FORMAT_REGISTRY  # noqa: E402

E018_GT = Path()  # the frozen e018 render truth dir, set from --e018-gt
REPORT: dict = {}


def _gt_field(spec) -> np.ndarray:
    """Printed page CELL values (H, W) uint8 from the frozen e018 GT.

    The GT file is the DOT raster (cells x cell_dots per axis; kcell
    renders a cell as a uniform dot block) — decimate to the cell grid
    and verify the shape against the format."""
    dots = np.load(E018_GT / "K__e018_field.npy")
    cd = spec.cell_dots
    cells = dots[::cd, ::cd].astype(np.uint8)
    if cells.shape != tuple(spec.page_cells_yx):
        raise ValueError(f"GT dot field {dots.shape} does not decimate to "
                         f"page cells {spec.page_cells_yx}")
    return cells


def _geometric_coverage(session, spec, seed):
    """Per-tile geometric payload coverage from the e022 cores (pre-
    detector), the round-4 denominator definition."""
    pim = compose.payload_index_map(spec, seed)
    h, w = spec.page_cells_yx
    covered = np.zeros((h, w), bool)
    for scan in session.scans:
        for placed in scan.result.placements:
            c = placed.page_cells_yx
            covered[c[:, 0], c[:, 1]] = True
    rows = {}
    for tile in ldpc.tile_grid(spec.page_cells_yx):
        mask = ldpc.tile_shorten_mask(tile, spec, seed)
        cap = ldpc.tile_user_capacity(mask, ldpc.LDPC_LADDER["r0550"])
        ys = slice(tile[0] * 64, min(h, (tile[0] + 1) * 64))
        xs = slice(tile[1] * 64, min(w, (tile[1] + 1) * 64))
        nonshort = int((pim[ys, xs] >= 0).sum())
        got = int((covered[ys, xs] & (pim[ys, xs] >= 0)).sum())
        rows[tile] = {"degenerate": cap == 0,
                      "geom": got / nonshort if nonshort else 0.0}
    return rows, covered


def _gt_payload_bits(spec, seed, gt_field) -> np.ndarray:
    """(capacity,) payload-bit truth: printed values at payload cells,
    descrambled by the keystream."""
    pim = compose.payload_index_map(spec, seed)
    ks = compose.payload_keystream(spec, seed, 0)
    cells = np.argwhere(pim >= 0)
    order = np.argsort(pim[cells[:, 0], cells[:, 1]], kind="stable")
    cells = cells[order]
    vals = gt_field[cells[:, 0], cells[:, 1]]
    return (vals ^ ks[cells[:, 0], cells[:, 1]]).astype(np.uint8)


def gate_a_zero_wrong(state, gt_bits, spec, seed) -> dict:
    """Every certified tile's re-encoded payload bits vs GT."""
    wrong = []
    n_cert = 0
    for key, out in state.tiles.items():
        if out.state != "certified":
            continue
        n_cert += 1
        pidx, tx_bits = state.certified_payload_indices(out)
        if not np.array_equal(tx_bits, gt_bits[pidx]):
            wrong.append(list(key))
    ok = not wrong
    print(f"GATE (a) zero wrong certifications: "
          f"{'PASS' if ok else 'FAIL'} ({n_cert} certified, "
          f"{len(wrong)} wrong)")
    return {"ok": ok, "certified": n_cert, "wrong": wrong}


def gate_b_yield(state, geom_rows) -> dict:
    denom = [t for t, row in geom_rows.items()
             if not row["degenerate"] and row["geom"] >= 0.95]
    got = sum(1 for t in denom
              if state.tiles.get((0, *t)) is not None
              and state.tiles[(0, *t)].state == "certified")
    frac = got / len(denom) if denom else 0.0
    ok = frac >= 0.95
    print(f"GATE (b) yield: {'PASS' if ok else 'FAIL'} "
          f"({got}/{len(denom)} = {frac:.3f} of the >=95%-geometric "
          f"nondegenerate denominator)")
    return {"ok": ok, "denominator": len(denom), "certified": got,
            "fraction": frac}


def coverage_curve(state, geom_rows) -> list[dict]:
    bins = [(0.0, 0.3), (0.3, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8),
            (0.8, 0.9), (0.9, 0.95), (0.95, 1.0001)]
    curve = []
    for lo, hi in bins:
        tiles = [t for t, row in geom_rows.items()
                 if not row["degenerate"] and lo <= row["geom"] < hi]
        got = sum(1 for t in tiles
                  if (o := state.tiles.get((0, *t))) is not None
                  and o.state == "certified")
        curve.append({"coverage": [lo, min(hi, 1.0)], "tiles": len(tiles),
                      "certified": got})
    print("coverage/certification curve: "
          + "  ".join(f"[{c['coverage'][0]:.2f},{c['coverage'][1]:.2f})"
                      f"={c['certified']}/{c['tiles']}"
                      for c in curve if c["tiles"]))
    return curve


def calibration_honesty(state) -> dict:
    ll = [row["heldout_logloss"] for s in state.scans
          for row in s.window_rows if not row["refused"]]
    refused = sum(row["refused"] for s in state.scans
                  for row in s.window_rows)
    out = {"windows": len(ll), "refused": refused,
           "logloss_median": float(np.median(ll)),
           "logloss_p95": float(np.percentile(ll, 95)),
           "logloss_max": float(np.max(ll))}
    print(f"calibration honesty: {out['windows']} windows, "
          f"refused={refused}, held-out log-loss median "
          f"{out['logloss_median']:.4f} / p95 {out['logloss_p95']:.4f}")
    return out


def gt_cell_diagnostics(state, gt_bits, spec, seed) -> dict:
    """GT-domain instruments: per-cell emission BER overall, by core-edge
    distance, and by ink-neighbor context (the context-binned-PAVA
    decision instrument)."""
    inv = payloaddec._payload_inverse(spec, seed)
    gt_field = REPORT["_gt_field"]
    h, w = spec.page_cells_yx
    edge = {}
    ctx = {}
    total = wrong = 0
    # neighbor-ink count from GT (context of the PRINTED page)
    from scipy import ndimage as ndi
    nbr = ndi.convolve(gt_field.astype(np.int16),
                       np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]]),
                       mode="constant")
    for emission in state.scans:
        vec = emission.pages.get(0)
        if vec is None:
            continue
        idx, llr = vec["index"], vec["llr"]
        hard = (llr > 0).astype(np.uint8)
        bad = hard != gt_bits[idx]
        total += idx.size
        wrong += int(bad.sum())
        cells = inv[idx]
        # core-edge distance: approximate per scan from its own union
        cov = np.zeros((h, w), bool)
        cov[cells[:, 0], cells[:, 1]] = True
        dist = ndi.distance_transform_cdt(cov, metric="taxicab")
        d = np.minimum(dist[cells[:, 0], cells[:, 1]], 6)
        for k in range(1, 7):
            sel = d == k
            if sel.any():
                row = edge.setdefault(int(k), [0, 0])
                row[0] += int(sel.sum())
                row[1] += int(bad[sel].sum())
        c = nbr[cells[:, 0], cells[:, 1]]
        for k in range(9):
            sel = c == k
            if sel.any():
                row = ctx.setdefault(int(k), [0, 0])
                row[0] += int(sel.sum())
                row[1] += int(bad[sel].sum())
    out = {
        "emitted_cell_ber": wrong / total if total else None,
        "by_core_edge_distance": {
            k: {"cells": n, "ber": b / n} for k, (n, b) in sorted(
                edge.items())},
        "by_ink_neighbors": {
            k: {"cells": n, "ber": b / n} for k, (n, b) in sorted(
                ctx.items())},
    }
    print(f"emitted-cell BER vs GT: {out['emitted_cell_ber']:.5f}")
    print("  by core-edge distance: " + "  ".join(
        f"d{k}={v['ber']:.4f}" for k, v in
        out["by_core_edge_distance"].items()))
    print("  by ink-neighbors: " + "  ".join(
        f"n{k}={v['ber']:.4f}" for k, v in
        out["by_ink_neighbors"].items()))
    return out


def staged_ablation(session, descriptor, state_full) -> dict:
    """stage1-union (certified after per-scan passes, before stage 2) vs
    full staged vs sum-only vs best-single-scan."""
    full = sum(o.state == "certified" for o in state_full.tiles.values())
    stage2 = sum(o.state == "certified" and o.certified_by == "union"
                 for o in state_full.tiles.values())

    # best single scan: replay each scan alone from the stored emissions
    best_single = 0
    per_scan = []
    for emission in state_full.scans:
        st = payloaddec.DecodeState(descriptor, state_full.rate_id,
                                    state_full.pages, ())
        st.ingest_scan(emission)
        n = sum(o.state == "certified" for o in st.tiles.values())
        per_scan.append({"scan_id": emission.scan_id, "certified": n})
        best_single = max(best_single, n)

    # sum-only: skip stage 1 entirely, decode every tile from the union
    st = payloaddec.DecodeState(descriptor, state_full.rate_id,
                                state_full.pages, ())
    st.scans = list(state_full.scans)
    sum_only = st.decode_union()["certified"]

    out = {"staged_total": full, "stage2_gain": stage2,
           "stage1_union": full - stage2, "sum_only": sum_only,
           "best_single_scan": best_single, "per_scan": per_scan}
    print(f"staged ablation: staged={full} (stage2 +{stage2})  "
          f"sum-only={sum_only}  best-single={best_single}")
    return out


def sliver_census(session) -> dict:
    unresolved = 0
    with_candidate = 0
    for scan in session.scans:
        for rows in scan.result.diagnostics.get("window_audit", {}).values():
            for row in rows:
                if row.get("outcome") == "unresolved":
                    unresolved += 1
                    with_candidate += int("best_candidate" in row)
    out = {"unresolved_windows": unresolved,
           "with_retry_candidate": with_candidate}
    print(f"sliver census: {unresolved} unresolved windows "
          f"({with_candidate} carry a retry-ledger candidate)")
    return out


def run_footing(name: str, state_path: Path, gate_b_applies: bool,
                quick: bool) -> dict:
    print(f"\n=== {name}: {state_path} ===")
    session = payloaddec.load_e022_session(state_path)
    descriptor = next(f for f in FORMAT_REGISTRY
                      if f.format_id == session.format_id)
    spec, seed = descriptor.spec(), descriptor.seed
    t0 = perf_counter()
    state = payloaddec.run_session(
        session, descriptor,
        on_scan=lambda st, sid, counts, dt: print(
            f"  {sid}: +{counts['certified']} certified "
            f"({counts['attempted']} attempted) [{dt:.0f}s]", flush=True))
    elapsed = perf_counter() - t0
    payloaddec.save_state(HERE / "build" / f"e023_{name}.pkl", state)

    gt_field = _gt_field(spec)
    REPORT["_gt_field"] = gt_field
    gt_bits = _gt_payload_bits(spec, seed, gt_field)
    geom_rows, _cov = _geometric_coverage(session, spec, seed)

    row: dict = {"state": str(state_path), "elapsed_s": elapsed,
                 "summary": state.summary()}
    row["gate_a"] = gate_a_zero_wrong(state, gt_bits, spec, seed)
    gate_b = gate_b_yield(state, geom_rows)
    row["gate_b"] = {**gate_b, "applies": gate_b_applies}
    row["coverage_curve"] = coverage_curve(state, geom_rows)
    row["calibration"] = calibration_honesty(state)
    if not quick:
        row["gt_diagnostics"] = gt_cell_diagnostics(state, gt_bits, spec,
                                                    seed)
        row["ablation"] = staged_ablation(session, descriptor, state)
    row["sliver_census"] = sliver_census(session)
    summary = state.summary()
    print(f"summary: {summary['tiles']}  attempts={summary['n_attempts']} "
          f"(CRC budget {summary['crc_false_accept_budget']:.2e})  "
          f"divergence mean={summary['divergence_mean']:.5f} "
          f"max={summary['divergence_max']:.5f}  [{elapsed:.0f}s]")
    del REPORT["_gt_field"]
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--e018-gt", type=Path, required=True)
    parser.add_argument("--decimated", type=Path, required=True)
    parser.add_argument("--native", type=Path,
                        help="required unless --skip-native")
    parser.add_argument("--quick", action="store_true",
                        help="skip GT cell diagnostics + ablation")
    parser.add_argument("--skip-native", action="store_true")
    args = parser.parse_args()
    if not args.skip_native and args.native is None:
        parser.error("--native is required unless --skip-native")
    global E018_GT
    E018_GT = args.e018_gt

    REPORT["decimated"] = run_footing("decimated", args.decimated,
                                      gate_b_applies=True, quick=args.quick)
    if not args.skip_native:
        REPORT["native"] = run_footing("native", args.native,
                                       gate_b_applies=False,
                                       quick=args.quick)
    gates_ok = (REPORT["decimated"]["gate_a"]["ok"]
                and REPORT["decimated"]["gate_b"]["ok"]
                and REPORT.get("native", {}).get("gate_a", {}).get("ok",
                                                                   True))
    REPORT["gates_ok"] = gates_ok
    out = HERE / "build" / "qualify_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        REPORT, indent=2, sort_keys=True,
        default=lambda v: v.item() if isinstance(v, np.generic)
        else v.tolist() if isinstance(v, np.ndarray) else str(v)) + "\n")
    print(f"\nQUALIFICATION {'PASS' if gates_ok else 'FAIL'} -> {out}")
    return 0 if gates_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
