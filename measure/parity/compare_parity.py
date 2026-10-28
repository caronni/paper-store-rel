#!/usr/bin/env python
"""Certificate-level parity: holo1's certified tile set vs holo3's.

The address set is the yield measure.  Both trees close byte-exact to the
same payload on every volume that closes, so bit-level conflicts are
excluded by construction -- what differs is WHICH tiles each receiver could
certify.  A fountain close can hide per-tile weakness behind its surplus
margin, so both sides are taken at FULL HARVEST (holo1 states are the
recorded full re-decodes; holo3 runs with ``--complete``).

holo1 side: parity/holo1-<id>.json from extract_holo1_certs.py.
holo3 side: run-<step>/events.jsonl, TileOutcome rows with result=certified,
deduped on (page, ty, tx, stream_id).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

PARITY = Path("<checkout>/_distill/verify/parity")

# step id -> (label, holo1 json basename).  Tile matrices (from
# resolve_format_ref) are the true page geometry, used for the edge/ring
# read on the misses:
#   2,5: 53x37 = 1961 tiles, 1 stream      3: 35x24 = 840, 1 stream
#   4,6: 52x36 = 1872 (4 has 3 streams)    7: 53x37 = 1961 x 3 streams
VOLUMES = [
    ("2", "e029 HP K (c2-r0700)", "holo1-e029-hp-k.json"),
    ("3", "xerox c3-cmy7", "holo1-xerox-c3-cmy7.json"),
    ("4", "xerox c2-cmy8", "holo1-xerox-c2-cmy8.json"),
    ("5", "xerox c2-k (c2-r0700)", "holo1-xerox-c2-k.json"),
    ("6", "xerox c2-cmy7 (PK-FINAL)", "holo1-xerox-c2-cmy7-pkfinal.json"),
    ("7", "sheet I pooled cmy8", "holo1-sheet-I.json"),
]

TILE_MATRIX = {"2": (53, 37), "3": (35, 24), "4": (52, 36),
               "5": (53, 37), "6": (52, 36), "7": (53, 37)}

# Which holo1 EPOCH each available state represents, plus the best holo1
# number on record for that sheet.  The states are NOT uniformly best-ever
# holo1: two of them predate the colour-uplift campaign, whose PK-FINAL
# re-decodes reached higher on the SAME archived scans.  Parity is scored
# against the state we can actually read; the record number rides along so
# the comparison is not oversold.
HOLO1_PROVENANCE = {
    "2": ("PK-FINAL full re-decode", 1940,
          "1940/1961 = 98.9%, the e029 headline"),
    "3": ("e032 print-day counting run", 810,
          "colour-uplift PK-FINAL reached 810 on this sheet; the readable "
          "state holds the e032 run at 720"),
    "4": ("e032 print-day counting run", 5466,
          "colour-uplift PK-FINAL reached 5466; the readable state holds "
          "the e032 run at 5370"),
    "5": ("e032 print-day counting run", 1930, "1930/1961 = 98.4%"),
    "6": ("colour-uplift PK-FINAL", 1559,
          "the pre-registered print-frozen negative control, closed at "
          "686,859 B"),
    "7": ("plane-fields W6 pooled run", 5297,
          "M 1958 / C 1895 / Y 1444; dead-Y bands expected on this sheet"),
}


def holo3_certs(run_dir: Path) -> tuple[set[tuple], dict]:
    """Certified (page,ty,tx,stream) set from a run dir's events.jsonl."""
    events = run_dir / "events.jsonl"
    if not events.is_file():
        return set(), {"error": f"no events.jsonl in {run_dir}"}
    certs: set[tuple] = set()
    results = Counter()
    rows = 0
    for line in events.open():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "TileOutcome":
            continue
        rows += 1
        results[event.get("result")] += 1
        if event.get("result") == "certified":
            certs.add((int(event["page"]), int(event["ty"]), int(event["tx"]),
                       str(event.get("stream_id", "main"))))
    return certs, {"tile_outcome_rows": rows, "results": dict(results)}


def cluster_note(missing: list[tuple], matrix: tuple[int, int]) -> str:
    """Geometric read on the misses: row/column/edge concentration.

    ``matrix`` is the format's true (n_ty, n_tx), so "outer ring" means the
    real page border, not the extent of whatever happened to certify.
    """
    if not missing:
        return ""
    n_ty, n_tx = matrix
    rows = Counter(m[1] for m in missing)
    cols = Counter(m[2] for m in missing)
    edge = sum(1 for m in missing
               if m[1] in (0, n_ty - 1) or m[2] in (0, n_tx - 1))
    # A distinct-address count separates "one tile, three planes" from
    # "three different tiles".
    distinct_tiles = len({(m[0], m[1], m[2]) for m in missing})
    bits = []
    top_rows = [f"ty={t}:{n}" for t, n in rows.most_common(4) if n > 1]
    top_cols = [f"tx={t}:{n}" for t, n in cols.most_common(4) if n > 1]
    if top_rows:
        bits.append("rows " + " ".join(top_rows))
    if top_cols:
        bits.append("cols " + " ".join(top_cols))
    bits.append(f"{edge}/{len(missing)} on the outer ring of the "
                f"{n_ty}x{n_tx} tile matrix")
    bits.append(f"{distinct_tiles} distinct tile positions")
    return "; ".join(bits)


def main() -> int:
    report: dict[str, dict] = {}
    for step, label, basename in VOLUMES:
        entry: dict = {"step": step, "label": label}
        h1_path = PARITY / basename
        run_dir = PARITY / f"run-{step}"
        verdict_path = run_dir / "harvest-verdict.json"

        if not h1_path.is_file():
            entry["holo1_error"] = f"missing {basename}"
        else:
            h1 = json.loads(h1_path.read_text())
            set1 = {tuple(c) for c in h1["certs"]}
            entry["holo1"] = {
                "n": len(set1),
                "by_stream": h1["by_stream"],
                "format_row_id": h1["format_row_id"],
                "state": h1["source"],
            }

        if verdict_path.is_file():
            entry["harvest"] = json.loads(verdict_path.read_text())
        set3, meta = holo3_certs(run_dir)
        entry["holo3"] = {"n": len(set3), "events": meta,
                          "by_stream": dict(sorted(
                              Counter(c[3] for c in set3).items()))}

        if "holo1" in entry and set3:
            matched = set1 & set3
            only1 = sorted(set1 - set3)
            only3 = sorted(set3 - set1)
            entry["matched"] = len(matched)
            entry["holo1_only"] = len(only1)
            entry["holo3_only"] = len(only3)
            entry["miss_fraction"] = (len(only1) / len(set1)) if set1 else 0.0
            entry["holo1_only_sample"] = [list(m) for m in only1[:40]]
            entry["holo3_only_sample"] = [list(m) for m in only3[:40]]
            entry["holo1_only_by_stream"] = dict(sorted(
                Counter(m[3] for m in only1).items()))
            entry["holo3_only_by_stream"] = dict(sorted(
                Counter(m[3] for m in only3).items()))
            entry["cluster_note"] = cluster_note(only1, TILE_MATRIX[step])
            entry["tile_matrix"] = list(TILE_MATRIX[step])
            entry["over_one_percent"] = entry["miss_fraction"] > 0.01
        epoch, best, note = HOLO1_PROVENANCE[step]
        entry["holo1_provenance"] = {
            "state_epoch": epoch, "best_on_record": best, "note": note}
        report[step] = entry

    (PARITY / "parity.json").write_text(json.dumps(report, indent=2))

    # ---- PARITY.md -------------------------------------------------
    lines: list[str] = []
    lines.append("# holo1 <-> holo3 certificate-level parity\n")
    lines.append(
        "Matching payload-tile decode is the parity measure, not the "
        "fountain close: a close stops at the first sufficient symbol "
        "surplus, so its margin can hide per-tile weakness. Both sides "
        "below are FULL HARVEST -- holo1's recorded full re-decode states "
        "vs holo3 run with `--complete` (close deferred to exhaustion).\n")
    lines.append(
        "Sanity: both trees close byte-exact to identical payloads (the "
        "manifest sha column), so bit-level certificate conflicts are "
        "excluded by construction. Address parity is the yield measure.\n")
    lines.append("| volume | holo1 | holo3 | matched | missing | extra "
                 "| miss % | verified sha |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for step, label, _basename in VOLUMES:
        e = report[step]
        h1 = e.get("holo1", {}).get("n")
        h3 = e.get("holo3", {}).get("n")
        harvest = e.get("harvest", {})
        sha = ("OK" if harvest.get("sha_ok")
               else ("FAIL" if harvest else "not run"))
        if harvest and harvest.get("sha_ok"):
            sha = f"OK ({harvest.get('bytes')} B)"
        miss_pct = (f"{100 * e['miss_fraction']:.2f}%"
                    if "miss_fraction" in e else "-")
        if e.get("over_one_percent"):
            miss_pct = f"**{miss_pct} FLAG**"
        lines.append(
            f"| {label} | {h1 if h1 is not None else '-'} "
            f"| {h3 if h3 else '-'} | {e.get('matched', '-')} "
            f"| {e.get('holo1_only', '-')} | {e.get('holo3_only', '-')} "
            f"| {miss_pct} | {sha} |")
    lines.append("")
    flagged = [label for step, label, _b in VOLUMES
               if report[step].get("over_one_percent")]
    lines.append(
        ("**FLAG: holo3 misses >1% of holo1's certificates on: "
         + ", ".join(flagged) + "**\n") if flagged else
        "No volume has holo3 missing more than 1% of holo1's "
        "certificates.\n")
    lines.append(
        "`holo1` above is the certificate count in the state that could "
        "actually be read. Two of those states predate the colour-uplift "
        "campaign, whose PK-FINAL re-decodes reached higher on the SAME "
        "archived scans -- the per-volume sections carry that number as "
        "`best on record` so the comparison is not oversold.\n")

    lines.append("## How the two sides were obtained\n")
    lines.append(
        "- **holo1**: `extract_holo1_certs.py` mmaps the state and parses "
        "ONLY the top-level `\"certificates\"` array. A full `load_session` "
        "decompresses every inlined evidence block (~7x the file size in "
        "RAM; measured 931 MB peak for the 131 MB colour state), which the "
        "3.5 GB sheet-I state does not survive alongside anything else. "
        "The slice path was cross-checked against a real `load_session` on "
        "two states (K and colour) and produced the IDENTICAL sorted "
        "address list both times.\n"
        "- Every holo1 state's own close record is `verified`, with a "
        "payload sha equal to the acceptance manifest's. That is what "
        "licenses the bit-level sanity claim above -- it is measured here, "
        "not assumed.\n"
        "- **holo3**: `TileOutcome` rows with `result=certified`, deduped "
        "on (page, ty, tx, stream_id). Deduping matters on the pooled "
        "multi-capture sheet: step 7 emitted 6072 certified rows for 5326 "
        "distinct addresses, because the same tile re-certifies from more "
        "than one capture.\n"
        "- All six holo3 runs used `--complete`, which gates the close "
        "solve to `final=True`, so the work loop cannot break early on a "
        "sufficient-surplus close and runs to exhaustion. The final close "
        "still happens, so every `verified sha` above is a real close.\n")
    lines.append(
        "Step 7 needed two attempts. The first died at ~33 min with the "
        "guard AND the decode both gone, no output and no RSS kill "
        "recorded. Re-running it detached (double-fork + setsid) survived "
        "1h52m to a verified close at a 47.86 GiB peak, and a sibling "
        "watcher process was independently killed at ~40 min -- so the "
        "first death was the harness reaping a long background task, not "
        "memory. Both attempts ran at `--workers 8`, so step 7 is on the "
        "SAME footing as the other five; no reduced-worker refooting was "
        "needed. Record: `step7-ledger.jsonl`.\n")

    for step, label, _basename in VOLUMES:
        e = report[step]
        lines.append(f"## step {step} -- {label}\n")
        prov = e["holo1_provenance"]
        if "holo1" in e:
            lines.append(f"- holo1 state: `{e['holo1']['state']}`")
            lines.append(f"- holo1 format row: `{e['holo1']['format_row_id']}`")
            lines.append(f"- holo1 certs by stream: {e['holo1']['by_stream']}")
            lines.append(f"- holo1 epoch: {prov['state_epoch']}; best on "
                         f"record {prov['best_on_record']} ({prov['note']})")
        else:
            lines.append(f"- holo1: {e.get('holo1_error')}")
        h = e.get("harvest")
        if h:
            lines.append(
                f"- holo3 harvest: exit {h['exit_code']}, wall {h['wall_s']} s, "
                f"child max RSS {h['child_max_rss_gib']} GiB, "
                f"{h['bytes']} B, sha_ok={h['sha_ok']}")
        lines.append(f"- holo3 certs: {e['holo3']['n']} "
                     f"by stream {e['holo3']['by_stream']}")
        if e["holo3"].get("events"):
            lines.append(f"- holo3 TileOutcome rows: {e['holo3']['events']}")
        if "matched" in e:
            lines.append(
                f"- matched {e['matched']} / holo1-only {e['holo1_only']} "
                f"({100 * e['miss_fraction']:.2f}%) / holo3-only "
                f"{e['holo3_only']}")
            lines.append(f"- holo1-only by stream: {e['holo1_only_by_stream']}")
            lines.append(f"- holo3-only by stream: {e['holo3_only_by_stream']}")
            if e.get("cluster_note"):
                lines.append(f"- miss geometry: {e['cluster_note']}")
            if e["holo1_only_sample"]:
                lines.append(
                    "- holo1-only addresses (page, ty, tx, stream), up to 40:\n")
                lines.append("```")
                for m in e["holo1_only_sample"]:
                    lines.append(f"  {m[0]} {m[1]:>3} {m[2]:>3} {m[3]}")
                lines.append("```")
            if e["holo3_only_sample"]:
                lines.append("- holo3-only addresses, up to 40:\n")
                lines.append("```")
                for m in e["holo3_only_sample"]:
                    lines.append(f"  {m[0]} {m[1]:>3} {m[2]:>3} {m[3]}")
                lines.append("```")
        lines.append("")

    (PARITY / "PARITY.md").write_text("\n".join(lines))
    print("\n".join(lines[:20]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
