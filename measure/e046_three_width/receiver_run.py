"""e046 — the receiver runs M1 and M2 on sheet c2-cmy8-r0775x0850x0700@53x37, read from their own records.
MEASUREMENT ONLY: reads events.jsonl, report.json and facts.npz of a run dir; mints nothing, runs no decode.

The clock is event order and cumulative JobDone cpu (no wall clocks).  Measured: certificates by row and plane at
cumulative-cpu checkpoints, jobs / cpu / cpu per certificate per row, WorkerSeated by plugin, the close replayed in
certificate order through the receiver's own CloseProgress (format.close) with the row's column groups — first
pooled symbol count >= K, first count-ready (every group >= K rows), first verified prefix — and, as a COUNT
ESTIMATE only, the same replay's counts against the q 0.9 row's K (the pooled Decoder of format.fountain built at
that K; the q 0.9 sheet would carry other symbols), the page field per FieldSolved event and in report.json, and
the resume run's replay and its certificates.

    cd <repo> && PYTHONPATH=src:. env/bin/python -m measure.e046_three_width.receiver_run \\
        --run M1=scratch/e046/runs/M1/rundir.40735 --run M2=scratch/e046/runs/M2/rundir.42487 \\
        --format c2-cmy8-r0775x0850x0700@53x37 --q09-payload-bytes 2006275 \\
        --out scratch/e046/analysis/receiver/receiver_run.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from holo.receiver import data, snapshot
from holo.receiver.format import close as fclose
from holo.receiver.format import fountain
from holo.receiver.format.identity import resolve_format_ref

Key = tuple[int, int, int, str]


def _plugin_of_source(source: str) -> str:
    head, _, tail = source.partition("/")
    return f"{head}.{tail.rstrip('0123456789')}"


def scan_events(path: Path, checkpoint_cpu_s: float) -> dict[str, Any]:
    cum_cpu_s = 0.0
    jobs: Counter[str] = Counter()
    cpu_s: defaultdict[str, float] = defaultdict(float)
    job_certs: Counter[str] = Counter()
    seated: Counter[str] = Counter()
    seated_stage: Counter[str] = Counter()
    seat_costs: defaultdict[str, list[float]] = defaultdict(list)
    seat_first_cpu_s: dict[str, float] = {}
    job_costs: defaultdict[str, list[float]] = defaultdict(list)
    first: dict[Key, dict[str, Any]] = {}
    recert: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    close_checks: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []
    other: dict[str, Any] = {}
    timeline: list[dict[str, Any]] = []
    next_cp = checkpoint_cpu_s
    n_event = 0

    def snap(label: str) -> None:
        by_row: Counter[str] = Counter()
        by_plane: Counter[str] = Counter()
        for rec in first.values():
            by_row[rec["row"]] += 1
            by_plane[rec["key"][3]] += 1
        timeline.append({"at": label, "cum_cpu_s": round(cum_cpu_s, 1), "event": n_event,
                         "certified": len(first), "by_row": dict(by_row), "by_plane": dict(by_plane),
                         "jobs": dict(jobs), "cpu_s": {k: round(v, 1) for k, v in cpu_s.items()},
                         "job_certs": dict(job_certs)})

    with open(path) as stream:
        for line in stream:
            n_event += 1
            ev = json.loads(line)
            kind = ev["type"]
            if kind == "JobDone":
                cum_cpu_s += float(ev["cpu_s"])
                jobs[ev["plugin"]] += 1
                cpu_s[ev["plugin"]] += float(ev["cpu_s"])
                job_certs[ev["plugin"]] += int(ev["n_certificates"])
                job_costs[ev["plugin"]].append(float(ev["cost"]))
                while cum_cpu_s >= next_cp:
                    snap(f"{int(next_cp)}")
                    next_cp += checkpoint_cpu_s
            elif kind == "TileOutcome":
                outcomes[f"{ev['source']}:{ev['result']}"] += 1
                if ev["result"] == "certified":
                    key: Key = (int(ev["page"]), int(ev["ty"]), int(ev["tx"]), str(ev["stream_id"]))
                    if key in first:
                        recert[ev["source"]] += 1
                    else:
                        first[key] = {"key": key, "source": ev["source"],
                                      "row": _plugin_of_source(ev["source"]),
                                      "cum_cpu_s": cum_cpu_s, "event": n_event, "ordinal": len(first)}
            elif kind == "WorkerSeated":
                seated[ev["plugin"]] += 1
                seated_stage[f"{ev['plugin']}:{ev.get('stage')}"] += 1
                seat_costs[ev["plugin"]].append(float(ev["cost"]))
                seat_first_cpu_s.setdefault(ev["plugin"], round(cum_cpu_s, 1))
            elif kind == "CloseCheck":
                b = ev["blocks"][0] if ev["blocks"] else {}
                close_checks.append({"event": n_event, "cum_cpu_s": cum_cpu_s, "certified": ev["certified"],
                                     "status": ev["status"], "have": b.get("have"),
                                     "min_group_rows": min(b["group_rows"]) if b else None,
                                     "group_rows": b.get("group_rows")})
            elif kind == "FieldSolved":
                fields.append({"event": n_event, "cum_cpu_s": round(cum_cpu_s, 1), "page": ev["page"],
                               "planes": [{k: p.get(k) for k in ("plane_name", "median_delta_dots",
                                                                 "median_uncertainty_dots", "support_tiles",
                                                                 "n_observations", "n_captures", "known",
                                                                 "held")}
                                          for p in ev["planes"]],
                               "extra": {k: v for k, v in ev.items() if k not in ("planes", "type")}})
            elif kind in ("RunOpen", "EngineStat", "RunDone", "SurveyDone", "SnapshotReplayed"):
                if kind == "SurveyDone":
                    ev = {k: v for k, v in ev.items() if k not in ("preview",)}
                other.setdefault(kind, []).append(ev)
    snap("end")

    def stats(values: dict[str, list[float]]) -> dict[str, dict[str, float]]:
        return {k: {"n": len(v), "min": min(v), "median": float(np.median(v)), "max": max(v)}
                for k, v in values.items() if v}

    return {"seat_cost": stats(seat_costs), "seat_first_cpu_s": seat_first_cpu_s, "job_cost": stats(job_costs),
            "first": first, "recert": dict(recert), "outcomes": dict(outcomes), "seated": dict(seated),
            "seated_stage": dict(seated_stage), "close_checks": close_checks, "fields": fields, "other": other,
            "timeline": timeline, "n_events": n_event, "total_cpu_s": cum_cpu_s}


def _first_index(flags: list[bool]) -> int | None:
    return next((i for i, f in enumerate(flags) if f), None)


def replay_close(row: Any, order: list[Key], certs: dict[Key, data.Certificate],
                 k_alt: int | None) -> dict[str, Any]:
    progress = fclose.CloseProgress(row)
    index_of = {s.stream_id: i for i, s in enumerate(row.streams)}
    alt = fountain.Decoder(fclose._pooled_volume_code(row, k_alt)) if k_alt else None
    have: list[int] = []
    min_rows: list[int] = []
    ready: list[bool] = []
    alt_have: list[int] = []
    alt_min: list[int] = []
    for key in order:
        progress.absorb({key: certs[key]})
        rows = progress.block_rows()
        have.append(sum(r.have for r in rows) if rows else 0)
        min_rows.append(min(min(r.group_rows) for r in rows) if rows else 0)
        ready.append(progress.count_ready)
        if alt is not None:
            cert = certs[key]
            alt.add_symbol(fclose._symbol_index(row, cert, index_of[cert.stream_id]),
                           np.asarray(cert.user_bits[1:], np.uint8))
            st = alt.block_status()
            alt_have.append(sum(s.have for s in st))
            alt_min.append(min(min(s.group_rows) for s in st))
    k_total = progress.k_total
    i_sym = _first_index([h >= k_total for h in have])
    i_ready = _first_index(ready)
    final_rows = progress.block_rows()

    def verified_at(n: int) -> bool:
        return fclose.close_volume([certs[k] for k in order[:n]], row).status == "verified"

    i_verified = None
    if i_ready is not None:
        lo, hi = i_ready + 1, len(order)
        if verified_at(lo):
            i_verified = lo - 1
        elif verified_at(hi):
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if verified_at(mid):
                    hi = mid
                else:
                    lo = mid
            i_verified = hi - 1
    out: dict[str, Any] = {
        "k_total": k_total, "n_groups": final_rows[0].n_groups if final_rows else None,
        "carried": list(fclose._pooled_volume_code(row, k_total).groups.carried),
        "group_widths": [fclose._pooled_volume_code(row, k_total).groups.width(g)
                         for g in range(final_rows[0].n_groups)] if final_rows else None,
        "final_have": have[-1], "final_group_rows": list(final_rows[0].group_rows) if final_rows else None,
        "first_symbols_ge_K": i_sym, "first_count_ready": i_ready, "first_verified": i_verified,
        "min_rows_at_symbols_ge_K": min_rows[i_sym] if i_sym is not None else None,
        "min_rows_curve": min_rows, "have_curve": have,
    }
    if alt is not None:
        out["alt"] = {"k_total": k_alt,
                      "first_symbols_ge_K": _first_index([h >= k_alt for h in alt_have]),
                      "first_count_ready": _first_index([m >= k_alt for m in alt_min]),
                      "final_have": alt_have[-1], "final_min_group_rows": alt_min[-1],
                      "final_group_rows": list(alt.block_status()[0].group_rows)}
    return out


def _cert_point(first_list: list[dict[str, Any]], i: int | None) -> dict[str, Any] | None:
    if i is None:
        return None
    rec = first_list[i]
    return {"certificates": i + 1, "cum_cpu_s": round(rec["cum_cpu_s"], 1), "event": rec["event"],
            "key": list(rec["key"]), "row": rec["row"]}


def analyse_run(label: str, run_dir: Path, row: Any, k_alt: int | None,
                checkpoint_cpu_s: float) -> dict[str, Any]:
    ev = scan_events(run_dir / "events.jsonl", checkpoint_cpu_s)
    report = json.loads((run_dir / "report.json").read_text())
    facts = snapshot.read(run_dir / "facts.npz")
    certs: dict[Key, data.Certificate] = {
        (c.page, c.ty, c.tx, c.stream_id): c for c in facts if isinstance(c, data.Certificate)}
    first_list = sorted(ev["first"].values(), key=lambda r: r["ordinal"])
    order = [tuple(r["key"]) for r in first_list]
    snapshot_sources = Counter(c.source for c in certs.values())
    event_keys = set(order)
    out: dict[str, Any] = {
        "label": label, "run_dir": str(run_dir), "n_events": ev["n_events"],
        "total_cpu_s": round(ev["total_cpu_s"], 1),
        "certified_events_first_seen": len(order), "certified_in_facts": len(certs),
        "facts_minus_events": len(set(certs) - event_keys), "events_minus_facts": len(event_keys - set(certs)),
        "facts_sources": dict(snapshot_sources),
        "facts_planes": dict(Counter(k[3] for k in certs)),
        "event_source_vs_facts_source_mismatch": sum(
            1 for r in first_list if r["key"] in certs and certs[r["key"]].source != r["source"]),
        "recertified_events_by_source": ev["recert"], "outcomes": ev["outcomes"],
        "worker_seated": ev["seated"], "worker_seated_stage": ev["seated_stage"],
        "seat_cost": ev["seat_cost"], "seat_first_cpu_s": ev["seat_first_cpu_s"], "job_cost": ev["job_cost"],
        "snapshot_replayed": ev["other"].get("SnapshotReplayed"),
        "timeline": ev["timeline"], "fields_events": ev["fields"],
        "report_plane_fields": report.get("plane_fields"), "report_close": report.get("close"),
        "report_plugins": report.get("scheduler", {}).get("plugins"), "report_replayed": report.get("replayed"),
        "engine_stat": ev["other"].get("EngineStat"), "run_done": ev["other"].get("RunDone"),
        "run_open": ev["other"].get("RunOpen"),
        "close_checks_n": len(ev["close_checks"]),
        "close_checks_status": dict(Counter(c["status"] for c in ev["close_checks"])),
        "close_check_last": ev["close_checks"][-1] if ev["close_checks"] else None,
    }
    cc_sym = next((c for c in ev["close_checks"] if c["have"] is not None and c["have"] >= 4236), None)
    cc_ready = next((c for c in ev["close_checks"]
                     if c["min_group_rows"] is not None and c["min_group_rows"] >= 4236), None)
    out["close_check_first_have_ge_K"] = {k: cc_sym[k] for k in ("event", "certified", "cum_cpu_s")} if cc_sym else None
    out["close_check_first_min_rows_ge_K"] = (
        {k: cc_ready[k] for k in ("event", "certified", "cum_cpu_s")} if cc_ready else None)
    if label == "M1":
        rc = replay_close(row, order, certs, k_alt)
        out["replay"] = {k: v for k, v in rc.items() if not k.endswith("_curve")}
        out["replay"]["matches_close_check_group_rows"] = (
            rc["final_group_rows"] == (ev["close_checks"][-1]["group_rows"] if ev["close_checks"] else None))
        for name in ("first_symbols_ge_K", "first_count_ready", "first_verified"):
            out["replay"][name + "_at"] = _cert_point(first_list, rc[name])
        if "alt" in rc:
            for name in ("first_symbols_ge_K", "first_count_ready"):
                rc["alt"][name + "_at"] = _cert_point(first_list, rc["alt"][name])
            out["replay"]["alt_ESTIMATE"] = rc["alt"]
            del out["replay"]["alt"]
        tail = [r for r in first_list if rc["first_count_ready"] is not None
                and r["ordinal"] > rc["first_count_ready"]]
        out["after_count_ready_by_row"] = dict(Counter(r["row"] for r in tail))
        out["after_count_ready_by_plane"] = dict(Counter(r["key"][3] for r in tail))
    span: dict[str, dict[str, float]] = {}
    for r in first_list:
        sp = span.setdefault(r["row"], {"first_cpu_s": round(r["cum_cpu_s"], 1), "first_ordinal": r["ordinal"]})
        sp["last_cpu_s"], sp["last_ordinal"] = round(r["cum_cpu_s"], 1), r["ordinal"]
    out["row_cert_span"] = span
    out["by_row_plane"] = {f"{row}:{pl}": n for (row, pl), n in
                           sorted(Counter((r["row"], r["key"][3]) for r in first_list).items())}
    out["facts_by_source_plane"] = {f"{src}:{pl}": n for (src, pl), n in
                                    sorted(Counter((c.source, c.stream_id) for c in certs.values()).items())}
    ty_n, tx_n = row.tiles_yx
    out["missing_keys"] = [[0, ty, tx, s.stream_id] for ty in range(ty_n) for tx in range(tx_n)
                           for s in row.streams if (0, ty, tx, s.stream_id) not in certs]
    out["missing_by_plane_tx"] = {s.stream_id: [sum(1 for k in out["missing_keys"] if k[3] == s.stream_id
                                                    and k[2] == tx) for tx in range(tx_n)] for s in row.streams}
    out["missing_by_plane_ty"] = {s.stream_id: [sum(1 for k in out["missing_keys"] if k[3] == s.stream_id
                                                    and k[1] == ty) for ty in range(ty_n)] for s in row.streams}
    out["new_certificates"] = [{"key": list(r["key"]), "row": r["row"], "source": r["source"],
                                "cum_cpu_s": round(r["cum_cpu_s"], 1), "event": r["event"]}
                               for r in first_list] if len(first_list) <= 50 else None
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", action="append", required=True, help="LABEL=RUN_DIR")
    ap.add_argument("--format", required=True)
    ap.add_argument("--q09-payload-bytes", type=int, required=True,
                    help="max payload bytes of the row at q 0.9 (confetti.py capacity)")
    ap.add_argument("--checkpoint-cpu-s", type=float, default=10000.0)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    row = resolve_format_ref(args.format)
    widths = tuple(s.symbol_bits for s in row.streams)
    n = len(widths)
    k_alt = n * fclose.source_symbol_count(args.q09_payload_bytes, n * max(widths))
    result: dict[str, Any] = {"format": args.format, "row_id": row.row_id, "stream_widths": list(widths),
                              "k_q09_ESTIMATE": k_alt, "runs": {}}
    for spec in args.run:
        label, _, path = spec.partition("=")
        result["runs"][label] = analyse_run(label, Path(path), row, k_alt, args.checkpoint_cpu_s)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, default=str))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
