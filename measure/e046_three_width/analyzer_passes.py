"""e046 analyzer passes A1-A4 and the hand-back: per-pass tables, attribution, cascade, residue.

Inputs (scratch/e046/runs/): M1/M2 rundir facts.npz (holo.receiver.snapshot.read),
A{1..4}/mints.jsonl, A{1..4}-ladder.log, A{1..4}/close.json, A{1,2,3}-export manifests.
Re-target sets follow analyzer.fixedpoint._retarget (8-neighbourhood + sibling streams);
the reconstruction is checked against each log's per-generation pending counts.

    cd <repo> && PYTHONPATH=src:. env/bin/python \
        measure/e046_three_width/analyzer_passes.py \
        --runs scratch/e046/runs --out scratch/e046/analysis/analyzer
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analyzer.export_facts import snapshot_certificates
from analyzer.fixedpoint import _retarget
from analyzer.ledger import certifying_arms
from analyzer.types import DEFAULT_ARMS
from holo.receiver import snapshot
from holo.receiver.format import identity

Key = tuple[int, int, int, str]
FORMAT_REF: str = "1i300-cmy8-r0775x0850x0700-p120-v1@53x37"
PASSES: tuple[str, ...] = ("A1", "A2", "A3", "A4")
STREAMS: tuple[str, ...] = ("C", "M", "Y")
PATCH_FAMILY: frozenset[str] = frozenset({
    "patch+offset", "patch+committed", "patch+field2+offset", "patch+affine",
    "rings+offset", "mixture+offset", "pure+committed", "pure+field2"})
FIELD2_NONPATCH: frozenset[str] = frozenset({"subtract+field2+offset", "head+field2+offset"})

GEN_START = re.compile(r"^generation (\d+): (\d+) pending \((\d+) re-attacks\)")
GEN_DONE = re.compile(r"^generation (\d+) done: \+(\d+) certificates \(total (\d+)\), (\d+) refused, "
                      r"(\d+):(\d\d):(\d\d), peak RSS ([\d.]+) GB")
PASS_DONE = re.compile(r"^pass done: (\d+) certificates over (\d+) generation\(s\) in (\d+):(\d\d):(\d\d)")


class _Inputs:
    def __init__(self, tiles_yx: tuple[int, int], streams: tuple[str, ...]) -> None:
        self.tiles_yx = tiles_yx
        self.row = type("Row", (), {"streams": tuple(type("S", (), {"stream_id": s})() for s in streams)})()
        self.certificates: dict[Key, Any] = {}


def read_certs(path: Path) -> dict[Key, str]:
    facts = snapshot.read(path)
    certs = {k: str(v.source) for k, v in snapshot_certificates(facts).items()}
    del facts
    return certs


def read_mints(path: Path) -> tuple[dict, list[dict]]:
    header: dict = {}
    rows: list[dict] = []
    with path.open() as handle:
        for line in handle:
            obj = json.loads(line)
            if obj.get("type") == "header":
                header = obj
            elif obj.get("type") == "row":
                obj.pop("rungs", None)
                rows.append(obj)
    return header, rows


def key_of(row: dict) -> Key:
    return (int(row["page"]), int(row["ty"]), int(row["tx"]), str(row["stream_id"]))


def parse_log(path: Path) -> dict:
    gens: dict[int, dict] = {}
    out: dict[str, Any] = {"generations": gens}
    for line in path.read_text().splitlines():
        if m := GEN_START.match(line):
            gens.setdefault(int(m[1]), {}).update(pending=int(m[2]), reattacks=int(m[3]))
        elif m := GEN_DONE.match(line):
            gens.setdefault(int(m[1]), {}).update(
                certified=int(m[2]), total=int(m[3]), refused=int(m[4]),
                wall_s=int(m[5]) * 3600 + int(m[6]) * 60 + int(m[7]), peak_rss_gb_log=float(m[8]))
        elif m := PASS_DONE.match(line):
            out.update(pass_certified=int(m[1]), pass_generations=int(m[2]),
                       pass_wall_s=int(m[3]) * 3600 + int(m[4]) * 60 + int(m[5]))
    return out


def family_of(names: tuple[str, ...]) -> str:
    kinds = {"patch" if n in PATCH_FAMILY else "field2" if n in FIELD2_NONPATCH
             else "classic" if n in DEFAULT_ARMS else "other" for n in names}
    return kinds.pop() if len(kinds) == 1 else "mixed:" + "+".join(sorted(kinds))


def reconstruct(base: set[Key], mints: list[dict], targets: list[Key], tiles_yx: tuple[int, int],
                streams: tuple[str, ...]) -> dict:
    """Replay the fixed point's pending sets from the mints, per analyzer.fixedpoint.run."""
    inputs = _Inputs(tiles_yx, streams)
    by_gen: dict[int, list[Key]] = defaultdict(list)
    for row in mints:
        by_gen[int(row["generation"])].append(key_of(row))
    certified = set(base)
    pending = list(dict.fromkeys(targets))
    pending_counts: list[int] = []
    pending_keys: list[list[Key]] = []
    gen = 0
    while pending:
        pending = [k for k in dict.fromkeys(pending) if k not in certified]
        if not pending:
            break
        pending_counts.append(len(pending))
        pending_keys.append(sorted(pending))
        fresh = by_gen.get(gen, [])
        assert set(fresh) <= set(pending), f"generation {gen}: a mint was not pending"
        certified |= set(fresh)
        nxt: list[Key] = []
        for key in fresh:
            nxt.extend(_retarget(inputs, key, certified, set(), {k: 1 for k in certified}))
        pending = nxt
        gen += 1
    return {"pending_counts": pending_counts, "pending_keys": pending_keys}


def triggers(mints: list[dict], key: Key, gen: int) -> list[Key]:
    page, ty, tx, s = key
    out = []
    for row in mints:
        if int(row["generation"]) != gen - 1:
            continue
        k = key_of(row)
        if (k[1], k[2]) == (ty, tx) and k[3] != s:
            out.append(k)
        elif k[3] == s and max(abs(k[1] - ty), abs(k[2] - tx)) == 1:
            out.append(k)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    runs: Path = args.runs
    args.out.mkdir(parents=True, exist_ok=True)

    m1 = read_certs(runs / "M1/rundir.40735/facts.npz")
    m2 = read_certs(runs / "M2/rundir.42487/facts.npz")
    row = identity.resolve_format_ref(FORMAT_REF)
    tiles_yx = (int(row.tiles_yx[0]), int(row.tiles_yx[1]))
    assert tuple(s.stream_id for s in row.streams) == STREAMS
    universe = {(0, ty, tx, s) for ty in range(tiles_yx[0]) for tx in range(tiles_yx[1]) for s in STREAMS}
    report: dict[str, Any] = {"tiles_yx": tiles_yx, "n_universe": len(universe)}

    mints: dict[str, list[dict]] = {}
    headers: dict[str, dict] = {}
    for p in PASSES:
        headers[p], mints[p] = read_mints(runs / p / "mints.jsonl")

    bases: dict[str, set[Key]] = {}
    bases["A1"] = set(m1)
    bases["A2"] = bases["A1"] | {key_of(r) for r in mints["A1"]}
    bases["A3"] = bases["A2"] | {key_of(r) for r in mints["A2"]}
    after_a3 = bases["A3"] | {key_of(r) for r in mints["A3"]}
    m2_new = sorted(set(m2) - after_a3)
    bases["A4"] = set(m2)
    final = bases["A4"] | {key_of(r) for r in mints["A4"]}
    report["m2_vs_a3_export"] = {"missing_from_m2": len(after_a3 - set(m2)), "m2_new": m2_new,
                                 "m2_new_source": [m2[k] for k in m2_new]}

    def per_plane(keys: set[Key]) -> dict[str, int]:
        c = Counter(k[3] for k in keys)
        return {s: c.get(s, 0) for s in STREAMS}

    cascade = [("M1", set(m1)), ("A1", bases["A2"]), ("A2", bases["A3"]), ("A3", after_a3),
               ("M2", set(m2)), ("A4", final)]
    report["cascade"] = [{"step": n, "total": len(k), **per_plane(k)} for n, k in cascade]
    residue = sorted(universe - final)
    report["final_residue"] = residue
    report["final_residue_tile_planes_certified"] = {
        f"{k[1]},{k[2]}": [s for s in STREAMS if (0, k[1], k[2], s) in final] for k in residue}
    open_m1 = universe - set(m1)
    report["m1_open_by_tile_column"] = {s: dict(sorted(Counter(k[2] for k in open_m1 if k[3] == s).items()))
                                        for s in STREAMS}
    report["m1_open_by_tile_row"] = {s: dict(sorted(Counter(k[1] for k in open_m1 if k[3] == s).items()))
                                     for s in STREAMS}

    passes: dict[str, Any] = {}
    for p in PASSES:
        rows = mints[p]
        log = parse_log(runs / f"{p}-ladder.log")
        close = json.loads((runs / p / "close.json").read_text())
        targets = sorted(universe - bases[p])
        rec = reconstruct(bases[p], rows, targets, tiles_yx, STREAMS)
        log_pending = [log["generations"][g]["pending"] for g in sorted(log["generations"])]
        gen_plane: dict[int, Counter] = defaultdict(Counter)
        for r in rows:
            gen_plane[int(r["generation"])][r["stream_id"]] += 1
        rung_plane: dict[str, Counter] = defaultdict(Counter)
        rule_plane: dict[str, Counter] = defaultdict(Counter)
        arm_plane: dict[str, Counter] = defaultdict(Counter)
        only_arm_plane: dict[str, Counter] = defaultdict(Counter)
        fam_plane: dict[str, Counter] = defaultdict(Counter)
        reroll_plane: Counter = Counter()
        col_plane: dict[str, Counter] = defaultdict(Counter)
        for r in rows:
            s = r["stream_id"]
            rung_plane[str(r["certifying_rung"])][s] += 1
            rule_plane[str(r["certifying_rule"]).split("|")[0]][s] += 1
            names, via = certifying_arms(r.get("certifying_arm"))
            for n in names:
                arm_plane[n][s] += 1
            if len(names) == 1:
                only_arm_plane[names[0]][s] += 1
            if via:
                reroll_plane[s] += 1
            fam_plane[family_of(names)][s] += 1
            col_plane[s][int(r["tx"])] += 1
        chains = []
        for r in rows:
            g = int(r["generation"])
            if g >= 1:
                k = key_of(r)
                trig = triggers(rows, k, g)
                four = [t for t in trig if t[3] == k[3] and abs(t[1] - k[1]) + abs(t[2] - k[2]) == 1]
                chains.append({"key": k, "generation": g, "triggers": trig, "four_neighbour_same_plane": four})
        cons = close.get("consistency", {})
        passes[p] = {
            "header": {k: headers[p].get(k) for k in ("n_targets", "targets_from", "knobs_from", "max_generations",
                                                     "fixed_point", "halo_cells", "cover_fraction", "run_dir")},
            "base_certificates": len(bases[p]), "base_by_plane": per_plane(bases[p]),
            "targets_all_open": len(targets), "targets_by_plane": per_plane(set(targets)),
            "targets_equal_header": len(targets) == int(headers[p]["n_targets"]),
            "log": log, "reconstructed_pending": rec["pending_counts"], "log_pending": log_pending,
            "reconstruction_matches_log": rec["pending_counts"][:len(log_pending)] == log_pending,
            "pending_left_at_stop": (rec["pending_counts"][len(log_pending)]
                                     if len(rec["pending_counts"]) > len(log_pending) else 0),
            "mints": len(rows), "mints_by_plane": per_plane({key_of(r) for r in rows}),
            "by_generation": {g: {s: gen_plane[g].get(s, 0) for s in STREAMS} for g in sorted(gen_plane)},
            "mint_seconds_sum": sum(float(r["seconds"]) for r in rows),
            "mint_seconds_median": sorted(float(r["seconds"]) for r in rows)[len(rows) // 2] if rows else None,
            "rung_by_plane": {k: dict(v) for k, v in rung_plane.items()},
            "rule_by_plane": {k: dict(v) for k, v in rule_plane.items()},
            "arm_first_success_by_plane": {k: dict(v) for k, v in arm_plane.items()},
            "arm_only_by_plane": {k: dict(v) for k, v in only_arm_plane.items()},
            "reroll_by_plane": dict(reroll_plane),
            "family_by_plane": {k: dict(v) for k, v in fam_plane.items()},
            "tile_column_by_plane": {s: dict(sorted(v.items())) for s, v in col_plane.items()},
            "chains": chains,
            "close": {"status": close.get("status"), "verified": close.get("verified"),
                      "n_symbols_used": close.get("n_symbols_used"), "n_certificates": close.get("n_certificates"),
                      "n_from_production": close.get("n_from_production"),
                      "n_from_analyzer": close.get("n_from_analyzer"), "sha": close.get("payload_sha256"),
                      "n_redundant": cons.get("n_redundant"), "n_consistent": cons.get("n_consistent"),
                      "n_inconsistent": cons.get("n_inconsistent"), "excluded": cons.get("n_excluded"),
                      "metadata": close.get("metadata")},
        }
        cap = len(log_pending)
        run_attempts = Counter(k for keys in rec["pending_keys"][:cap] for k in keys)
        passes[p]["residue_attempts"] = {",".join(map(str, k)): run_attempts.get(k, 0) for k in residue}
        passes[p]["attempts_total"] = sum(run_attempts.values())
        passes[p]["pending_keys_left_at_stop"] = rec["pending_keys"][cap] if len(rec["pending_keys"]) > cap else []
        mp = runs / f"{p}-export/facts.npz.manifest.json"
        if mp.exists():
            man = json.loads(mp.read_text())
            passes[p]["export"] = {"counts": man["counts"],
                                   "exposure": [lg.get("exposure") for lg in man["ledgers"]],
                                   "superseded": [lg.get("n_rows_superseded") for lg in man["ledgers"]],
                                   "consistency": man["consistency"]["groups"],
                                   "snapshot_facts_unchanged": man["verified"]["snapshot_facts_unchanged"]}
    report["passes"] = passes
    (args.out / "analyzer_passes.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({"cascade": report["cascade"], "final_residue": residue, "m2": report["m2_vs_a3_export"],
                      "recon": {p: (passes[p]["reconstruction_matches_log"], passes[p]["targets_equal_header"])
                                for p in PASSES}}, default=str))


if __name__ == "__main__":
    main()
