"""Paired per-lane comparison of two `analyzer score` runs, by sibling state.

TRUTH-SIDE, OUTSIDE THE PACKAGE ON PURPOSE (W8 B1's acceptance reading,
APPROACHES §3 S1 vs S0): for every (lane, row) both runs scored, the cell
error of ONE sibling state (default 3 = both siblings inked) in run B
minus run A, paired over the rows of one band, with its standard error —
the fall must clear 2 SE per lane on the 4800 lanes for S1 to pass.

    PYTHONPATH=src:. env/bin/python measure/c-third-layer-20260906/paired_bystate.py \
        --level 3 --band dead --state 3 <A>/score.jsonl <B>/score.jsonl
"""
import argparse
import collections
import json
import math


def _level_of(key: str) -> int | None:
    if "/l" not in key:
        return None
    try:
        return int(key.rsplit("/l", 1)[1])
    except ValueError:
        return None


def load(path: str, stream: str, level: int | None) -> dict:
    """{(lane, key) -> {band, state -> (error, n), all -> error}}."""
    out: dict = {}
    with open(path) as handle:
        next(handle)
        for line in handle:
            d = json.loads(line)
            if d.get("type") != "row" or d["stream_id"] != stream:
                continue
            key = (d["page"], d["ty"], d["tx"])
            for k, v in (d.get("evidence") or {}).items():
                if ("/" not in k or not isinstance(v, dict)
                        or not v.get("scoreable")):
                    continue
                if level is not None and _level_of(k) != level:
                    continue
                states = {stt.split("/")[0]: (s["cell_error"], s["n"])
                          for stt, s in v.get("by_sibling_state", {}).items()}
                out[(k, key)] = {"band": d["band"], "states": states,
                                 "all": v["cell_error_map"],
                                 "R": v.get("R")}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a")
    parser.add_argument("b")
    parser.add_argument("--level", type=int, default=3)
    parser.add_argument("--band", default="dead")
    parser.add_argument("--state", default="3")
    parser.add_argument("--stream", default="C")
    args = parser.parse_args()
    a = load(args.a, args.stream, args.level)
    b = load(args.b, args.stream, args.level)
    shared = sorted(set(a) & set(b))
    print(f"A={args.a}\nB={args.b}\nlevel={args.level} band={args.band} "
          f"state={args.state} stream={args.stream}: {len(shared)} shared "
          f"(lane, row) pairs")
    by_lane = collections.defaultdict(list)
    by_lane_all = collections.defaultdict(list)
    for lane, key in shared:
        if a[(lane, key)]["band"] != args.band:
            continue
        sa = a[(lane, key)]["states"].get(args.state)
        sb = b[(lane, key)]["states"].get(args.state)
        if sa and sb and sa[1] >= 50 and sb[1] >= 50:
            by_lane[lane].append((sa[0], sb[0]))
        by_lane_all[lane].append((a[(lane, key)]["all"], b[(lane, key)]["all"],
                                  a[(lane, key)]["R"], b[(lane, key)]["R"]))
    print(f"\n{'lane':22s} {'rows':>4s} {'A err':>7s} {'B err':>7s} "
          f"{'delta':>8s} {'SE':>7s} {'z':>6s} | {'A all':>7s} {'B all':>7s} "
          f"{'A R':>6s} {'B R':>6s}")
    passes = 0
    for lane in sorted(by_lane):
        pairs = by_lane[lane]
        deltas = [pb - pa for pa, pb in pairs]
        n = len(deltas)
        mean = sum(deltas) / n
        se = (math.sqrt(sum((d - mean) ** 2 for d in deltas) / (n - 1) / n)
              if n > 1 else float("nan"))
        z = mean / se if se and se > 0 else float("nan")
        alls = by_lane_all[lane]
        a_all = sum(x[0] for x in alls) / len(alls)
        b_all = sum(x[1] for x in alls) / len(alls)
        a_r = sum((x[2] or 0.0) for x in alls) / len(alls)
        b_r = sum((x[3] or 0.0) for x in alls) / len(alls)
        verdict = "PASS" if z < -2.0 else "    "
        passes += z < -2.0
        print(f"{lane:22s} {n:4d} {sum(p[0] for p in pairs) / n:7.4f} "
              f"{sum(p[1] for p in pairs) / n:7.4f} {mean:+8.4f} {se:7.4f} "
              f"{z:6.1f} | {a_all:7.4f} {b_all:7.4f} {a_r:6.3f} {b_r:6.3f} "
              f"{verdict}")
    print(f"\n{passes} of {len(by_lane)} lanes fall by more than 2 SE")


if __name__ == "__main__":
    main()
