#!/usr/bin/env python
"""Before/after adjudication of the holo3 descriptor-engine change.

For each of the six parity volumes, compares the BASELINE harvest
(parity/run-<id>/, pre-change tree) with the POST harvest
(parity/post-<id>/, HEAD f4a18ea) and with holo1's certified set.

A note on row accounting: the two trees do not share a row vocabulary.
The baseline emitted five JobDone plugins (survey, place, calibrate, a
single merged `tiles`, refine); HEAD emits twelve, splitting tiles into
freeze/scan/union/retry and adding ctx, color, refine.color, revisit.
Row-for-row job deltas are therefore meaningless for the tiles family, so
`tiles.*` is aggregated for the before/after column and the split is
reported separately.

Certificates are minted ONLY by the tiles rows (TileOutcome.source is
always `tiles/<stage>`).  The new rows -- refine, refine.color, revisit --
do not mint: they adopt a revised placement, which re-fires the ordinary
tiles rows through the declared reads.  Their yield is therefore measured
as (fires, adoptions, certificates that followed), where an adoption is a
PoseCommitted carrying route=`refine`.  Reporting a "certificate count"
directly against those source tags would be a category error, so this
script reports what the events actually attribute.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

PARITY = Path("<checkout>/_distill/verify/parity")

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

# Pre-registered, recorded BEFORE the post runs were scored.
EXPECTATION = {
    "2": "stays 1940 exact",
    "3": "recovers some of its 4 misses",
    "4": "gains from unstarved retries + colour refinement, toward its 36",
    "5": "misses shrink from 8 toward ~3 (widened refine + revisit target "
         "the never-refined rescue rows)",
    "6": "toward its 22 misses",
    "7": "toward its 104 misses",
}

NEW_ROWS = ("refine", "refine.color", "revisit")


def scan_events(path: Path) -> dict:
    """One pass over an events.jsonl -> everything the report needs."""
    if not path.is_file():
        return {"error": f"missing {path}"}
    certs: set[tuple] = set()
    jobs = Counter()
    job_certs = Counter()
    attempts = Counter()          # source -> TileOutcome rows
    attempts_certified = Counter()  # source -> certified rows
    results = Counter()
    routes = Counter()
    routes_accepted = Counter()
    calib = Counter()
    run_done = None
    for line in path.open():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "TileOutcome":
            source = event.get("source", "?")
            attempts[source] += 1
            results[event.get("result")] += 1
            if event.get("result") == "certified":
                attempts_certified[source] += 1
                certs.add((int(event["page"]), int(event["ty"]),
                           int(event["tx"]), str(event.get("stream_id", "main"))))
        elif kind == "JobDone":
            jobs[event["plugin"]] += 1
            job_certs[event["plugin"]] += int(event.get("n_certificates", 0))
        elif kind == "PoseCommitted":
            routes[event.get("route")] += 1
            if event.get("accepted"):
                routes_accepted[event.get("route")] += 1
        elif kind == "CalibrateAdopted":
            calib["adopted" if event.get("adopted") else "refused"] += 1
        elif kind == "RunDone":
            run_done = event
    return {
        "certs": certs,
        "jobs": dict(sorted(jobs.items())),
        "job_certificates": dict(sorted(job_certs.items())),
        "attempts_by_source": dict(sorted(attempts.items())),
        "certified_by_source": dict(sorted(attempts_certified.items())),
        "results": dict(sorted(results.items())),
        "pose_routes": dict(sorted(routes.items())),
        "pose_routes_accepted": dict(sorted(routes_accepted.items())),
        "calibrate": dict(calib),
        "run_done": run_done,
    }


def tiles_family(jobs: dict) -> int:
    return sum(n for name, n in jobs.items()
               if name == "tiles" or name.startswith("tiles."))


def cluster_note(missing: list[tuple], matrix: tuple[int, int]) -> str:
    if not missing:
        return ""
    n_ty, n_tx = matrix
    rows, cols = Counter(m[1] for m in missing), Counter(m[2] for m in missing)
    edge = sum(1 for m in missing
               if m[1] in (0, n_ty - 1) or m[2] in (0, n_tx - 1))
    bits = []
    top_rows = [f"ty={t}:{n}" for t, n in rows.most_common(4) if n > 1]
    top_cols = [f"tx={t}:{n}" for t, n in cols.most_common(4) if n > 1]
    if top_rows:
        bits.append("rows " + " ".join(top_rows))
    if top_cols:
        bits.append("cols " + " ".join(top_cols))
    bits.append(f"{edge}/{len(missing)} on the outer ring of {n_ty}x{n_tx}")
    bits.append(f"{len({(m[0], m[1], m[2]) for m in missing})} distinct tiles")
    return "; ".join(bits)


def build() -> dict:
    report: dict[str, dict] = {}
    for step, label, basename in VOLUMES:
        entry: dict = {"step": step, "label": label,
                       "expectation": EXPECTATION[step]}
        h1 = json.loads((PARITY / basename).read_text())
        set1 = {tuple(c) for c in h1["certs"]}
        entry["holo1"] = {"n": len(set1), "by_stream": h1["by_stream"]}

        pre = scan_events(PARITY / f"run-{step}" / "events.jsonl")
        post_dir = PARITY / f"post-{step}"
        if not (post_dir / "events.jsonl").is_file():
            alt = PARITY / f"post-{step}-w6"
            if (alt / "events.jsonl").is_file():
                post_dir = alt
        post = scan_events(post_dir / "events.jsonl")
        entry["post_run_dir"] = str(post_dir)

        for name, side in (("pre", pre), ("post", post)):
            if "error" in side:
                entry[name] = {"error": side["error"]}
                continue
            certs = side["certs"]
            entry[name] = {
                "n": len(certs),
                "by_stream": dict(sorted(Counter(c[3] for c in certs).items())),
                "jobs": side["jobs"],
                "jobs_tiles_family": tiles_family(side["jobs"]),
                "job_certificates": side["job_certificates"],
                "attempts_by_source": side["attempts_by_source"],
                "certified_by_source": side["certified_by_source"],
                "results": side["results"],
                "pose_routes": side["pose_routes"],
                "pose_routes_accepted": side["pose_routes_accepted"],
                "calibrate": side["calibrate"],
            }
            v = post_dir / "harvest-verdict.json" if name == "post" else \
                PARITY / f"run-{step}" / "harvest-verdict.json"
            if v.is_file():
                entry[name]["verdict"] = json.loads(v.read_text())

        if "error" in pre or "error" in post:
            report[step] = entry
            continue

        set_pre, set_post = pre["certs"], post["certs"]
        for tag, other in (("vs_holo1", set1), ("vs_baseline", set_pre)):
            missing = sorted(other - set_post)
            extra = sorted(set_post - other)
            entry[tag] = {
                "matched": len(set_post & other),
                "missing": len(missing),
                "extra": len(extra),
                "miss_fraction": (len(missing) / len(other)) if other else 0.0,
                "missing_by_stream": dict(sorted(
                    Counter(m[3] for m in missing).items())),
                "extra_by_stream": dict(sorted(
                    Counter(m[3] for m in extra).items())),
                "missing_sample": [list(m) for m in missing[:40]],
                "cluster": cluster_note(missing, TILE_MATRIX[step]),
            }
        entry["over_one_percent"] = entry["vs_holo1"]["miss_fraction"] > 0.01
        # The BEFORE column: how many of holo1's certificates the baseline
        # harvest missed, so the table reads pre-miss -> post-miss.
        entry["pre_miss"] = len(set1 - set_pre)
        entry["pre_miss_fraction"] = len(set1 - set_pre) / len(set1)
        entry["recovered_from_baseline_misses"] = sorted(
            [list(m) for m in ((set1 - set_pre) & set_post)])
        entry["lost_vs_baseline"] = sorted(
            [list(m) for m in (set_pre - set_post)])

        # New-row accounting.  These rows never mint a certificate; they
        # adopt a revised placement (PoseCommitted route='refine') which
        # re-fires the tiles rows.  Report fires vs adoptions.
        adoptions = post["pose_routes"].get("refine", 0)
        pre_adoptions = pre["pose_routes"].get("refine", 0)
        entry["new_rows"] = {
            row: {"fires_post": post["jobs"].get(row, 0),
                  "fires_pre": pre["jobs"].get(row, 0),
                  "certificates_credited_post":
                      post["job_certificates"].get(row, 0),
                  "certificates_credited_pre":
                      pre["job_certificates"].get(row, 0)}
            for row in NEW_ROWS
        }
        entry["refine_adoptions"] = {"post": adoptions, "pre": pre_adoptions}
        colour_fires = post["jobs"].get("refine.color", 0)
        entry["colour_lane_churn"] = {
            "refine_color_fires": colour_fires,
            "refine_route_adoptions": adoptions,
            "fires_per_adoption": (round(colour_fires / adoptions, 1)
                                   if adoptions else None),
            "pathological": bool(colour_fires >= 200 and adoptions == 0),
        }
        report[step] = entry
    return report


SCORE = {
    "2": ("FAILED", "pre-registered 'stays 1940 exact' -- lost 2, gained 0; "
                    "both losses at ty=42, the documented HP weak-horizontal "
                    "band"),
    "3": ("EXCEEDED", "pre-registered 'recovers some of its 4' -- recovered "
                      "ALL 4, reaching exact parity with holo1"),
    "4": ("NO MEASUREMENT", "killed at the 58 GiB ceiling at BOTH workers 8 "
                            "(60.51 GiB) and workers 6 (60.24 GiB)"),
    "5": ("PARTIAL", "pre-registered 'from 8 toward ~3' -- reached 5 "
                     "(recovered 3, lost 0), including two of the tx=0 "
                     "rescue-column tiles the widened refine targeted"),
    "6": ("FAILED", "pre-registered 'toward its 22' -- regressed to 26 "
                    "(recovered 8, lost 39)"),
    "7": ("MET", "pre-registered 'toward its 104' -- reached 34, dropping "
                 "below the 1% flag line; Y 1470 -> 1559"),
}


def _row_table(e: dict) -> list[str]:
    """Per-row job counts and per-source attempt counts, before vs after."""
    lines = ["", "| row | jobs pre | jobs post | | source | attempts pre "
             "| attempts post |", "|---|---:|---:|---|---|---:|---:|"]
    rows = sorted(set(e["pre"]["jobs"]) | set(e["post"]["jobs"]))
    srcs = sorted(set(e["pre"]["attempts_by_source"])
                  | set(e["post"]["attempts_by_source"]))
    for i in range(max(len(rows), len(srcs))):
        if i < len(rows):
            r = rows[i]
            left = (f"| `{r}` | {e['pre']['jobs'].get(r, 0)} "
                    f"| {e['post']['jobs'].get(r, 0)} |")
        else:
            left = "| | | |"
        if i < len(srcs):
            s = srcs[i]
            right = (f" | `{s}` | {e['pre']['attempts_by_source'].get(s, 0)} "
                     f"| {e['post']['attempts_by_source'].get(s, 0)} |")
        else:
            right = " | | | |"
        lines.append(left + right)
    return lines


def write_report(report: dict) -> None:
    """Append the post columns + verdict section to PARITY.md."""
    md = PARITY / "PARITY.md"
    base = md.read_text()
    marker = "\n## Post-change adjudication"
    if marker in base:
        base = base[:base.index(marker)]

    out = [base.rstrip(), "",
           "## Post-change adjudication (holo3 HEAD f4a18ea)", ""]
    out.append(
        "Re-harvest of all six volumes on the descriptor engine: retries "
        "never close-gated, a widened `refine` re-arm, the new `revisit` "
        "row, and the new `refine.color` lane carrying v1's numerics "
        "verbatim. Same rules as the baseline batch -- strictly serial, "
        "`--complete`, `--workers 8`, one decode at a time -- run from a "
        "single daemonized driver so the harness could not reap it "
        "mid-batch, with 5 s RSS sampling against a 58 GiB kill line.\n")
    out.append("| volume | holo1 | pre | post | miss pre | miss post "
               "| recovered | lost | wall x | peak rss GiB | peak fp GiB "
               "| sha | verdict |")
    out.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")
    for step, label, _b in VOLUMES:
        e = report[step]
        score, _why = SCORE[step]
        if "vs_holo1" not in e:
            out.append(f"| {label} | {e['holo1']['n']} | - | **none** "
                       f"| - | - | - | - | - | >60.5 killed | - | - "
                       f"| {score} |")
            continue
        v = e["post"].get("verdict", {})
        out.append(
            f"| {label} | {e['holo1']['n']} | {e['pre']['n']} | "
            f"{e['post']['n']} | {e['pre_miss']} | {e['vs_holo1']['missing']} "
            f"| {len(e['recovered_from_baseline_misses'])} | "
            f"{len(e['lost_vs_baseline'])} | {v.get('wall_ratio', '-')} | "
            f"{v.get('peak_rss_gib', '-')} | "
            f"{v.get('peak_footprint_gib', '-')} | "
            f"{'OK' if v.get('sha_ok') else 'FAIL'} | {score} |")
    out.append("")
    out.append("### Verdict against the pre-registered expectations\n")
    for step, label, _b in VOLUMES:
        score, why = SCORE[step]
        out.append(f"- **{label} — {score}**: {why}.")
    out.append("")
    out.append(
        "**Every close that ran stayed byte-exact.** Five of five completed "
        "volumes recovered their payload sha exactly. The changes moved "
        "WHICH tiles certify; they never broke payload reconstruction.\n")

    fires_refine = sum(report[s]["new_rows"]["refine"]["fires_post"]
                       for s, _l, _b in VOLUMES if "new_rows" in report[s])
    fires_colour = sum(report[s]["new_rows"]["refine.color"]["fires_post"]
                       for s, _l, _b in VOLUMES if "new_rows" in report[s])
    fires_revisit = sum(report[s]["new_rows"]["revisit"]["fires_post"]
                        for s, _l, _b in VOLUMES if "new_rows" in report[s])
    adoptions = sum(report[s]["refine_adoptions"]["post"]
                    for s, _l, _b in VOLUMES if "refine_adoptions" in report[s])
    out.append(
        f"**The refinement rows adopted nothing, on any volume.** Across the "
        f"five completed volumes `refine` fired {fires_refine} times, "
        f"`refine.color` {fires_colour} times and `revisit` "
        f"{fires_revisit} times, producing {adoptions} `route=refine` poses "
        f"-- zero, everywhere. Certificates are minted only by the tiles "
        f"rows, and the refinement rows' whole contribution is supposed to "
        f"arrive as an adopted revised placement, so a zero adoption count "
        f"means they contributed no certificate anywhere in this batch. "
        f"On c2-cmy7 and sheet I that is 788 and 2,950 colour-lane fires "
        f"for no adoption -- the runaway signature this batch was told to "
        f"watch for.\n")
    out.append(
        "**Where the certificates actually came from.** Retry attempts rose "
        "steeply everywhere -- 4.7x on step 2 (1,500 -> 7,037), 0 -> 2,694 "
        "on step 3, 3.7x on step 5, 23x on step 6 (1,028 -> 23,881), 1.9x "
        "on step 7 -- but the per-source certified counts show the retry "
        "row minting only 50 / 0 / 21 / 13 / 99 certificates on steps "
        "2/3/5/6/7. Notably it minted NONE on step 3, the volume that "
        "reached exact parity: there the whole gain sits in `tiles/scan` "
        "(786 -> 815) on a larger attempt count (3,399 -> 3,840). So the "
        "retry un-gating is real and does mint certificates on four "
        "volumes, but it does not by itself explain step 3, and with zero "
        "refinement adoptions the events in hand do not isolate what "
        "re-fired those extra scans. Attributing step 3's gain would need "
        "instrumentation this batch does not carry -- stated as an open "
        "question rather than guessed.\n")
    out.append(
        "**Memory is the batch's hard limit.** Post peaks ran well above "
        "baseline (step 3 15.8 -> 39.4 GiB; step 6 56.3 -> 57.96, within "
        "0.04 GiB of the kill line). Step 4 breached at BOTH workers 8 "
        "(60.51) and workers 6 (60.24) -- 0.27 GiB apart, so worker count "
        "is not the driver and the prescribed reduced-worker fallback "
        "cannot rescue that volume on this machine.\n")
    out.append(
        "**Wall cost.** Step 6 crossed the 2.5x tripwire (3.1x, 8,487 s) "
        "and was logged rather than killed -- a killed volume measures "
        "nothing, and it is the flagged volume. Step 7 ran 2.03x "
        "(13,580 s). Steps 2/3 ran 1.16x/1.39x and step 5 came in FASTER "
        "than baseline at 0.68x.\n")

    for step, label, _b in VOLUMES:
        e = report[step]
        out.append(f"### post step {step} -- {label}\n")
        score, why = SCORE[step]
        out.append(f"- verdict: **{score}** -- {why}")
        out.append(f"- expectation as pre-registered: {e['expectation']}")
        if "vs_holo1" not in e:
            out.append("- no post events: the volume never completed.\n")
            continue
        v = e["post"].get("verdict", {})
        out.append(
            f"- harvest: wall {v.get('wall_s')} s ({v.get('wall_ratio')}x "
            f"baseline), peak rss {v.get('peak_rss_gib')} GiB, "
            f"peak footprint {v.get('peak_footprint_gib', '-')} GiB "
            f"({v.get('memory_source', 'rss-only batch')}), "
            f"{v.get('bytes')} B, sha_ok={v.get('sha_ok')}")
        out.append(f"- certificates: pre {e['pre']['n']} -> post "
                   f"{e['post']['n']} (holo1 {e['holo1']['n']})")
        out.append(f"- by stream: pre {e['pre']['by_stream']} -> post "
                   f"{e['post']['by_stream']}")
        out.append(
            f"- vs holo1: matched {e['vs_holo1']['matched']}, missing "
            f"{e['vs_holo1']['missing']} "
            f"({100 * e['vs_holo1']['miss_fraction']:.2f}%), extra "
            f"{e['vs_holo1']['extra']}; miss by stream "
            f"{e['vs_holo1']['missing_by_stream']}")
        out.append(
            f"- vs baseline: recovered "
            f"{len(e['recovered_from_baseline_misses'])} of the baseline's "
            f"misses, lost {len(e['lost_vs_baseline'])} it had held")
        if e["vs_holo1"]["cluster"]:
            out.append(f"- miss geometry: {e['vs_holo1']['cluster']}")
        out.append(f"- new rows: {e['new_rows']}")
        out.append(f"- colour lane: {e['colour_lane_churn']}")
        out.append(f"- pose routes: pre {e['pre']['pose_routes']} -> post "
                   f"{e['post']['pose_routes']}")
        out.extend(_row_table(e))
        if e["lost_vs_baseline"]:
            out.append("\n- lost vs baseline (page, ty, tx, stream), up to 40:")
            out.append("```")
            for m in e["lost_vs_baseline"][:40]:
                out.append(f"  {m[0]} {m[1]:>3} {m[2]:>3} {m[3]}")
            out.append("```")
        out.append("")
    md.write_text("\n".join(out) + "\n")


def main() -> int:
    report = build()
    (PARITY / "post-analysis.json").write_text(json.dumps(
        report, indent=2, default=str))
    write_report(report)

    # Merge the post findings into the machine-readable parity.json so one
    # file carries both halves of the before/after.
    parity_path = PARITY / "parity.json"
    if parity_path.is_file():
        parity = json.loads(parity_path.read_text())
        for step, _label, _b in VOLUMES:
            e = report[step]
            block = {
                "head": "f4a18eac26b9d04e16fad69b4f3d321eca0a6725",
                "expectation": e["expectation"],
                "verdict": SCORE[step][0],
                "verdict_note": SCORE[step][1],
                "run_dir": e.get("post_run_dir"),
            }
            if "vs_holo1" in e:
                block.update({
                    "n": e["post"]["n"],
                    "by_stream": e["post"]["by_stream"],
                    "vs_holo1": e["vs_holo1"],
                    "vs_baseline_run": e["vs_baseline"],
                    "recovered_from_baseline_misses":
                        e["recovered_from_baseline_misses"],
                    "lost_vs_baseline": e["lost_vs_baseline"],
                    "jobs": e["post"]["jobs"],
                    "attempts_by_source": e["post"]["attempts_by_source"],
                    "certified_by_source": e["post"]["certified_by_source"],
                    "pose_routes": e["post"]["pose_routes"],
                    "new_rows": e["new_rows"],
                    "colour_lane_churn": e["colour_lane_churn"],
                    "harvest": e["post"].get("verdict"),
                })
            else:
                block["error"] = ("no post measurement: killed at the 58 GiB "
                                  "ceiling at workers 8 and workers 6")
            parity.setdefault(step, {})["post"] = block
        parity_path.write_text(json.dumps(parity, indent=2, default=str))
    for step, label, _b in VOLUMES:
        e = report[step]
        if "vs_holo1" not in e:
            print(f"step {step} {label}: POST NOT AVAILABLE "
                  f"({e.get('post', {}).get('error', 'pending')})")
            continue
        print(f"step {step} {label}: holo1 {e['holo1']['n']} | "
              f"pre {e['pre']['n']} -> post {e['post']['n']} | "
              f"miss {e['vs_holo1']['missing']} "
              f"({100 * e['vs_holo1']['miss_fraction']:.2f}%) | "
              f"recovered {len(e['recovered_from_baseline_misses'])} "
              f"lost {len(e['lost_vs_baseline'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
