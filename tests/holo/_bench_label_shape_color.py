"""A3 label-shape instrument: real-corpus color runner + arm comparator.

Provenance: PAYLOAD-REWORK-PLAN addendum A3 (chip task_45921656) — the
K-vs-color label sampling shape re-evaluation; measured record in
docs/LABEL-SAMPLING-SHAPE-ANALYSIS.md. Standalone, never pytest-collected.

Run one arm (ordinary ladder + M-levels: run_mopup=True, run_refine=False
— the v0.42 flag analog of the PAYLOAD-MEASUREMENTS §6 "no-refine" arm),
recording EVERY ``payload.region`` event's registration facts (adopted,
per-plane anchors/intercepts, held-out losses, fit population) tagged
with barrier ordinal and lane, plus CPU seconds (``time.process_time`` +
rusage) so arms stay comparable under concurrent load:

    PYTHONPATH=src:tests/holo env/bin/python \
        tests/holo/_bench_label_shape_color.py run <corpus_dir> <arm> <out.json>

Compare two arm JSONs region by region (adoption flips, anchor support,
held-out loss deltas, fit population, per-lane table):

    PYTHONPATH=src:tests/holo env/bin/python \
        tests/holo/_bench_label_shape_color.py compare <a.json> <b.json>

The wall-anchored event-delta decomposition buckets are indicative only
under load; compare arms on CPU seconds and the per-stage
``timing.processor_seconds`` aggregates.

CACHE CAVEAT (color-uplift P8): ``color.registration.*`` now always
reports what registration MEASURED.  Runs recorded before that fix zeroed
those keys on every non-adopted region, so an anchor/intercept delta
against a pre-P8 JSON is a reporting change, not a channel change —
re-record both arms before reading those columns.
"""
from __future__ import annotations

import json
import resource
import statistics
import subprocess
import sys
import time
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory

_REGION_DETAIL_KEYS = (
    "color.region", "color.page", "color.accepted", "color.reason",
    "color.patches", "color.train_sites", "color.heldout_sites",
    "color.calibration_labels", "color.registration_adopted",
    "color.dependency_certificates",
    "color.baseline_heldout_logloss", "color.selected_heldout_logloss",
    "color.registration.c.anchors", "color.registration.m.anchors",
    "color.registration.y.anchors",
    "color.registration.c.intercept_x_dots",
    "color.registration.c.intercept_y_dots",
    "color.registration.m.intercept_x_dots",
    "color.registration.m.intercept_y_dots",
    "color.registration.y.intercept_x_dots",
    "color.registration.y.intercept_y_dots",
)


def run(corpus: Path, arm: str, out_path: Path) -> None:
    from holo.format.registry import get_format_row
    from holo.receive.observer import ProvisionalReceiverWarning
    from holo.receive.production import production_pipeline
    from holo.receive.runtime import ReceiveRequest, run_receive
    from holo.receive.types import CaptureInput

    from _bench_payload_decomp import _Decomposer, _totals

    prior = json.load(open(corpus / "receive.json"))["state"]
    spec = get_format_row(prior["format_row_id"])
    pages = prior.get("page_hypotheses")
    pages = None if pages is None else tuple(pages)
    truth = (corpus / "payload.bin").read_bytes()
    captures = tuple(
        CaptureInput(str(corpus / name), 4800.0)
        for name in ("scraps-r4800-001.tif", "scraps-r4800-002.tif"))

    counters = {"barriers": 0, "close_checks": 0}
    stage_seconds: dict[str, float] = {}
    regions: list[dict[str, object]] = []
    plans: list[dict[str, object]] = []
    decomp = _Decomposer()

    def observe(event) -> None:
        decomp.observe(event)
        name = event.name
        if name == "barrier.committed":
            counters["barriers"] += 1
            return
        if name == "close.check":
            counters["close_checks"] += 1
            return
        if name in ("stage.complete", "stage.refused"):
            details = {row.name: row.value for row in event.details}
            seconds = details.get("timing.processor_seconds")
            lane = str(details.get("lane.id", "?"))
            if isinstance(seconds, (int, float)):
                kind = ("mopup" if lane.startswith("m")
                        else "refine" if lane.startswith("r")
                        else "base")
                key = f"{kind}.{event.stage.value}"
                stage_seconds[key] = (
                    stage_seconds.get(key, 0.0) + float(seconds))
            return
        if name == "payload.plan":
            details = {row.name: row.value for row in event.details}
            plans.append({
                "barrier_index": counters["barriers"],
                "capture": (event.capture_id or "?")[:8],
                "lane": str(event.context.lane_id or "?"),
                "placements": details.get("color.placements"),
                "prior_certificates": details.get(
                    "color.prior_certificates"),
            })
            return
        if name == "payload.region":
            details = {row.name: row.value for row in event.details}
            row = {
                "barrier_index": counters["barriers"],
                "capture": (event.capture_id or "?")[:8],
                "lane": str(event.context.lane_id or "?"),
            }
            for key in _REGION_DETAIL_KEYS:
                if key in details:
                    row[key.replace("color.", "")] = details[key]
            regions.append(row)

    with TemporaryDirectory() as scratch:
        request = ReceiveRequest(
            spec, captures,
            state_path=Path(scratch) / "ab.json",
            page_hypotheses=pages,
            run_mopup=True,
            run_refine=False)
        start = time.perf_counter()
        cpu_start = time.process_time()
        ru_start = resource.getrusage(resource.RUSAGE_SELF)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ProvisionalReceiverWarning)
            result = run_receive(
                request, pipeline=production_pipeline(request),
                observer=observe)
        wall = time.perf_counter() - start
        cpu = time.process_time() - cpu_start
        ru_end = resource.getrusage(resource.RUSAGE_SELF)
        rusage_cpu = ((ru_end.ru_utime - ru_start.ru_utime)
                      + (ru_end.ru_stime - ru_start.ru_stime))
        state = result.state
    payload = result.payload
    head_sha = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, check=True).stdout.strip()
    report = {
        "arm": arm,
        "worktree_head": head_sha,
        # Other jobs may run concurrently: compare arms on CPU seconds,
        # and treat the wall-anchored event-delta decomposition buckets
        # as indicative only under load.
        "cpu_s": round(cpu, 1),
        "rusage_cpu_s": round(rusage_cpu, 1),
        "decomposition_is_wall_based_indicative_only": True,
        "wall_s": round(wall, 1),
        "verified": result.verified,
        "payload_matches_gt": payload == truth if payload else False,
        "certificates": len(state.certificates),
        "close_status": state.close.status.value,
        "peak_rss_mib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20),
        "stage_seconds": {
            key: round(value, 1)
            for key, value in sorted(stage_seconds.items())},
        **counters,
        "payload_decomposition": _totals(decomp, wall),
        "plans": plans,
        "regions": regions,
    }
    out_path.write_text(json.dumps(report, indent=1))
    print(json.dumps({key: report[key] for key in (
        "arm", "worktree_head", "cpu_s", "rusage_cpu_s", "wall_s",
        "verified", "certificates", "close_status", "barriers",
        "stage_seconds")}))


def _region_key(row: dict) -> tuple:
    return (row["lane"], row.get("region"), row.get("page"))


def _anchors_max(row: dict) -> int:
    return max(
        row.get("registration.c.anchors", 0),
        row.get("registration.m.anchors", 0),
        row.get("registration.y.anchors", 0))


def compare(base_path: str, full_path: str) -> None:
    base = json.load(open(base_path))
    full = json.load(open(full_path))

    print("=== headline (compare on CPU seconds; wall + event-delta "
          "decomposition are indicative only under concurrent load) ===")
    for name, d in (("baseline", base), ("candidate", full)):
        pd = d["payload_decomposition"]
        print(f"{name}: head={d.get('worktree_head', '?')[:9]} "
              f"cpu={d.get('cpu_s')}s rusage_cpu={d.get('rusage_cpu_s')}s "
              f"wall={d['wall_s']}s certs={d['certificates']} "
              f"barriers={d['barriers']} rss={d['peak_rss_mib']}MiB")
        print(f"  stage_seconds(CPU)={d['stage_seconds']}")
        print(f"  payload_total={pd['payload_total_s']}s "
              f"sampling_ctx="
              f"{pd['payload_bucket_seconds'].get('sampling_calibration_ctx_s')}s")

    b_regions = {_region_key(r): r for r in base["regions"]}
    f_regions = {_region_key(r): r for r in full["regions"]}
    common = sorted(set(b_regions) & set(f_regions))
    print(f"\n=== regions: base={len(b_regions)} cand={len(f_regions)} "
          f"common={len(common)} ===")

    b_adopt = sum(1 for r in base["regions"] if r.get("registration_adopted"))
    f_adopt = sum(1 for r in full["regions"] if r.get("registration_adopted"))
    print(f"adoption: base={b_adopt}/{len(b_regions)} "
          f"cand={f_adopt}/{len(f_regions)}")

    flips_on = [k for k in common
                if not b_regions[k].get("registration_adopted")
                and f_regions[k].get("registration_adopted")]
    flips_off = [k for k in common
                 if b_regions[k].get("registration_adopted")
                 and not f_regions[k].get("registration_adopted")]
    print(f"adoption flips on={len(flips_on)} off={len(flips_off)}")

    b_anch = [_anchors_max(b_regions[k]) for k in common]
    f_anch = [_anchors_max(f_regions[k]) for k in common]
    print(f"anchors(max/plane) over common regions: "
          f"base median={statistics.median(b_anch)} "
          f"cand median={statistics.median(f_anch)}")
    b_supported = sum(1 for a in b_anch if a >= 8)
    f_supported = sum(1 for a in f_anch if a >= 8)
    print(f"supported-anchor regions: base={b_supported} "
          f"cand={f_supported}")

    deltas = []
    for k in common:
        lb = b_regions[k].get("selected_heldout_logloss")
        lf = f_regions[k].get("selected_heldout_logloss")
        if lb is not None and lf is not None:
            deltas.append(lf - lb)
    if deltas:
        print(f"selected heldout logloss delta (cand - base) over "
              f"{len(deltas)} co-fit regions: "
              f"median={statistics.median(deltas):+.5f} "
              f"mean={statistics.mean(deltas):+.5f} "
              f"min={min(deltas):+.5f} max={max(deltas):+.5f}")

    b_pop = sum(r.get("train_sites", 0) + r.get("heldout_sites", 0)
                for r in base["regions"])
    f_pop = sum(r.get("train_sites", 0) + r.get("heldout_sites", 0)
                for r in full["regions"])
    print(f"total fit population: base={b_pop} cand={f_pop} "
          f"({f_pop / max(1, b_pop):.1f}x)")

    print("\n=== adoption by lane (base -> cand) ===")
    lanes = sorted({r["lane"] for r in base["regions"]}
                   | {r["lane"] for r in full["regions"]})
    for lane in lanes:
        br = [r for r in base["regions"] if r["lane"] == lane]
        fr = [r for r in full["regions"] if r["lane"] == lane]
        ba = sum(1 for r in br if r.get("registration_adopted"))
        fa = sum(1 for r in fr if r.get("registration_adopted"))
        bs = sum(1 for r in br if _anchors_max(r) >= 8)
        fs = sum(1 for r in fr if _anchors_max(r) >= 8)
        print(f"{lane}: regions {len(br)}->{len(fr)}, "
              f"adopted {ba}->{fa}, supported {bs}->{fs}")


def main() -> None:
    mode = sys.argv[1]
    if mode == "run":
        run(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
    elif mode == "compare":
        compare(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(f"unknown mode {mode!r} (use: run | compare)")


if __name__ == "__main__":
    main()
