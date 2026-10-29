"""Blind readings of a ledger that ran a patch arm (W8 B1: I1, I2).

No payload, no truth: this reads the ledger's own bookkeeping —
`certifying_arm` per row, the `_selected` paired select-fold comparisons
(patch-vs-default per lane), the per-(lane, state) `patch_states`, the
fallback / outside counts and the in-sample vs cross-fit fit-fold error
gap.  Rows are streamed (a sheet-H ledger is gigabytes).

    PYTHONPATH=src:. env/bin/python measure/c-third-layer-20260906/ledger_patch_readings.py \
        [--arm patch+offset] [--level 3] <pass>/ledger.jsonl
"""
import argparse
import collections
import json
import statistics as st

from analyzer import ledger as ledger_mod


def _level_of(key: str) -> int | None:
    if "/l" not in key:
        return None
    try:
        return int(key.split("|", 1)[0].rsplit("/l", 1)[1])
    except ValueError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger")
    parser.add_argument("--arm", default="patch+offset")
    parser.add_argument("--level", type=int, default=None)
    args = parser.parse_args()
    header = ledger_mod.read_header(args.ledger)
    print(f"arms={header.get('arms')} rules={header.get('rules')} "
          f"rungs={header.get('rungs')} halo={header.get('halo_cells')} "
          f"knobs={header.get('knobs')} reroll={header.get('reroll')} "
          f"{header.get('reroll_rungs')} n_rows={header.get('n_rows')} "
          f"n_certified={header.get('n_certified')} "
          f"seconds={header.get('seconds')} "
          f"exposure={header.get('exposure_distinct')}")
    rows = list(ledger_mod.iter_rows(args.ledger))
    attributed = ledger_mod.attribution(
        rows, rule_order=header.get("rules", ()),
        rung_order=header.get("rungs", ()), arm_order=header.get("arms", ()))
    print("attribution:", json.dumps({
        name: attributed[name] for name in (
            "union", "first_success_by_rule", "leave_one_out_by_rule",
            "first_success_by_rung", "first_success_by_arm", "only_by_arm",
            "reroll_by_arm")}))
    bands = ledger_mod.stream_band_table(rows)
    print("stream x band:", json.dumps(bands))
    certified = [(r["ty"], r["tx"], r["band"], r.get("certifying_arm"),
                  r.get("certifying_rule"), r.get("certifying_rung"))
                 for r in rows if r.get("verdict") in ("certified",
                                                        "certified_list")]
    print("certified rows:", certified)

    adopted = collections.Counter()
    compared = collections.Counter()
    refused = collections.Counter()
    fitted = collections.defaultdict(lambda: collections.Counter())
    fallback = collections.defaultdict(list)
    outside = collections.defaultdict(list)
    gap = collections.defaultdict(list)
    labels_per_feature = collections.defaultdict(list)
    for r in rows:
        band = r["band"]
        for lane, sel in (r.get("evidence") or {}).get("_selected", {}).items():
            if args.level is not None and _level_of(lane) != args.level:
                continue
            comparison = (sel.get("comparisons") or {}).get(args.arm)
            if sel.get("selection_refused"):
                refused[band] += 1
            if comparison is None:
                continue
            compared[band] += 1
            adopted[band] += bool(comparison.get("adopted"))
        for key, blind in (r.get("evidence") or {}).items():
            if key == "_selected" or not key.endswith(f"|{args.arm}"):
                continue
            if args.level is not None and _level_of(key) != args.level:
                continue
            if not isinstance(blind, dict) or blind.get("refusal"):
                fitted[band]["refused:" + str((blind or {}).get("refusal"))] += 1
                continue
            states = blind.get("patch_states") or {}
            for state, entry in states.items():
                fitted[band][f"s{state}:{'fit' if entry.get('fitted') else entry.get('reason')}"] += 1
                if entry.get("fitted"):
                    labels_per_feature[(band, state)].append(
                        entry.get("labels_per_feature"))
            n_obs = float(blind.get("n_observed") or 1)
            fallback[band].append(float(blind.get("patch_fallback_cells", 0))
                                  / n_obs)
            outside[band].append(float(blind.get("patch_outside_cells", 0))
                                 / n_obs)
            if blind.get("patch_fit_error_crossfit") is not None:
                gap[band].append((blind["patch_fit_error_insample"],
                                  blind["patch_fit_error_crossfit"]))
    for band in ("dead", "marginal", "live"):
        print(f"\n[{band}] select-fold paired test {args.arm} vs default: "
              f"adopted {adopted[band]} of {compared[band]} lanes "
              f"(selection refused on {refused[band]})")
        print(f"[{band}] per-(lane, state) tiers: "
              f"{dict(sorted(fitted[band].items()))}")
        if fallback[band]:
            print(f"[{band}] fallback fraction median "
                  f"{st.median(fallback[band]):.3f}, outside median "
                  f"{st.median(outside[band]):.4f} over {len(fallback[band])} "
                  f"(lane, row)")
        if gap[band]:
            print(f"[{band}] fit-fold error in-sample median "
                  f"{st.median(g[0] for g in gap[band]):.4f} vs cross-fit "
                  f"{st.median(g[1] for g in gap[band]):.4f}")
        for state in ("0", "1", "2", "3"):
            values = [v for v in labels_per_feature[(band, state)]
                      if v is not None]
            if values:
                print(f"[{band}] state {state} labels/feature median "
                      f"{st.median(values):.2f} (min {min(values):.2f})")


if __name__ == "__main__":
    main()
