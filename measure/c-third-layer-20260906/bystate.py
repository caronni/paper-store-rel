"""Cell error by (band, sibling state) from `analyzer score` rows.

TRUTH-SIDE, OUTSIDE THE PACKAGE ON PURPOSE: reads the `by_sibling_state`
splits the offline scorer wrote (it holds the payload), pools the lanes
per (band, state) and, since W8 B1, prints one row per LANE beside the
pooled table and takes `--level N` to restrict the aggregation to lanes
at that level (3 = the 4800-dpi lanes, MEAS §4/§5b's population).

    PYTHONPATH=src:. env/bin/python measure/c-third-layer-20260906/bystate.py \
        [--level 3] [--stream C] <out>/score.jsonl [...]
"""
import argparse
import collections
import json
import statistics as st


def _level_of(evidence_key: str) -> int | None:
    """``'<capture12>/l<level>'`` -> the level, None for anything else."""
    if "/l" not in evidence_key:
        return None
    try:
        return int(evidence_key.rsplit("/l", 1)[1])
    except ValueError:
        return None


def _print_table(title: str, summ: dict, agg: dict, lanes_label: str) -> None:
    print(f"\n{title}")
    print(f"{'band':9s} {lanes_label:>5s} {'err_med':>8s} {'R_med':>6s} | "
          f"{'state0':>7s} {'M only':>7s} {'Y only':>7s} {'M+Y':>7s}")
    for band in ("dead", "marginal", "live"):
        if band not in summ:
            continue
        v = summ[band]
        row = [agg.get((band, str(i))) for i in range(4)]
        cells = " ".join(f"{r[0] / r[1]:7.4f}" if r and r[1] else "      -"
                         for r in row)
        print(f"{band:9s} {len(v):5d} {st.median(x[0] for x in v):8.4f} "
              f"{st.median(x[1] for x in v):6.3f} | {cells}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--level", type=int, default=None,
                        help="only lanes at this level index (3 = 4800 dpi)")
    parser.add_argument("--stream", default="C")
    args = parser.parse_args()
    for path in args.paths:
        agg = collections.defaultdict(lambda: [0.0, 0])
        summ = collections.defaultdict(list)
        per_lane_agg = collections.defaultdict(
            lambda: collections.defaultdict(lambda: [0.0, 0]))
        per_lane_summ = collections.defaultdict(
            lambda: collections.defaultdict(list))
        arm = None
        with open(path) as handle:
            next(handle)
            for line in handle:
                d = json.loads(line)
                if d.get("type") != "row" or d["stream_id"] != args.stream:
                    continue
                for k, v in (d.get("evidence") or {}).items():
                    if ("/" not in k or not isinstance(v, dict)
                            or not v.get("scoreable")):
                        continue
                    level = _level_of(k)
                    if args.level is not None and level != args.level:
                        continue
                    arm = v.get("arm")
                    item = (v["cell_error_map"], v.get("R") or float("nan"))
                    summ[d["band"]].append(item)
                    per_lane_summ[k][d["band"]].append(item)
                    for stt, s in v.get("by_sibling_state", {}).items():
                        state = stt.split("/")[0]
                        for table in (agg, per_lane_agg[k]):
                            a = table[(d["band"], state)]
                            a[0] += s["cell_error"] * s["n"]
                            a[1] += s["n"]
        level_note = "" if args.level is None else f"  level={args.level}"
        _print_table(f"== {path}  arm={arm}{level_note}  (pooled over lanes)",
                     summ, agg, "lanes")
        for lane_key in sorted(per_lane_summ):
            _print_table(f"-- lane {lane_key}", per_lane_summ[lane_key],
                         per_lane_agg[lane_key], "rows")


if __name__ == "__main__":
    main()
