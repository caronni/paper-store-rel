#!/usr/bin/env python3
"""Mine a holo3 receiver events.jsonl log and print a markdown report.

Usage:
    python3 events_report.py <events.jsonl> [--label LABEL] > report.md

stdlib + numpy only. Streams the file line by line (one known log is
~200 MB) -- never loads the raw file whole. What IS kept in memory are
small derived aggregates: per-plugin counters/cpu lists, per-tile-stream
outcome lists, per-window stage lists, etc. Their sizes are bounded by
the number of distinct subjects/windows/tile-streams in the run, which
for every log here is orders of magnitude smaller than the file itself.

Events have NO timestamps. They are appended in engine merge order (the
single merge thread), so line sequence is a proxy for wall-clock order,
never a substitute for it -- every "when in the run" statement below is
phrased as a fraction of the JobDone sequence, not as time, and the
report says so again at first use.

Methodology notes (read before trusting a number):
  - "fires" for a (plugin, subject) pair = count of JobDone events with
    that plugin and subject. Subject lists (JSON arrays) are converted
    to nested tuples so they can be dict keys; the tuple is printed
    verbatim as its repr.
  - zero-yield job = JobDone with n_certificates == n_poses == n_words == 0.
  - "child window" = a distinct (capture, level_index, region_index,
    extent_cells) window whose extent_cells area is smaller than the
    modal (most common) area seen in this log. The modal area is
    reported explicitly so this inference is checkable.
  - "last place WorkerSeated stage for a window before a JobDone" is
    computed by walking the file in order: a place JobDone's subject is
    matched to a window key, and we read off whatever stage that
    window's seat list currently holds (i.e. every place WorkerSeated
    for that window seen so far, which -- because the
    file is engine-ordered -- is exactly "before this JobDone").
  - "wasted retry" on a tile-stream = a TileOutcome whose source
    contains "retry" on a tile-stream whose FIRST certified TileOutcome
    (if any) came from a source that does not contain "retry". This
    undercounts if a tile-stream was retried, abandoned, and never
    certified at all (counted separately as "never certified").
  - "scan re-attempts on eventually-certified tiles" = for tile-streams
    whose first certified TileOutcome has a source containing "scan",
    the count of TileOutcome events on that stream whose source also
    contains "scan" (any result). >1 means the scan worker fired more
    than once on a tile it eventually certified.
  - facts-ingested estimate (section 6) is explicitly a rough proxy, not
    a count read from the engine: JobDone.n_certificates + n_poses +
    n_words summed, plus one per TileOutcome/WordOutcome/WindowSettled/
    AddressCoverage/CalibrateAdopted/FieldFitted/PlaneFieldTiers/
    PoseCommitted/CloseCheck event. It is NOT the number of _touch()
    calls or subscriber wakes; it is an order-of-magnitude anchor for
    "wakes per ingested fact", stated as such wherever printed.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict

import numpy as np

FIRE_BUCKETS = [(1, 1, "1"), (2, 2, "2"), (3, 5, "3-5"), (6, 10, "6-10"),
                (11, None, ">10")]

#: The seat and retire events in BOTH spellings.  `WorkerSeated` /
#: `WorkerRetired` are generic over every row and carry the subject as a
#: JSON list (2026-09-21); `WindowScheduled` / `WindowRetired` were
#: place-only and carried the window's four fields flat.  This report IS
#: the base-vs-branch A/B instrument, and the base leg's journal is
#: written by base code -- matching one name would render "distinct
#: windows: 0" for it and read as a branch win.
SEATED_TYPES = ("WorkerSeated", "WindowScheduled")
RETIRED_TYPES = ("WorkerRetired", "WindowRetired")


def _is_place(d):
    """The old events were place's alone and carry no `plugin` field."""
    return d.get("plugin", "place") == "place"


def _place_window_key(d):
    """The window a seat/retire event names, in either spelling."""
    subject = d.get("subject")
    if subject is None:
        return (d["capture"], d["level_index"], d["region_index"],
                tuple(d["extent_cells"]))
    return (subject[0], subject[1], subject[2], tuple(subject[3]))


def to_hashable(x):
    if isinstance(x, list):
        return tuple(to_hashable(e) for e in x)
    return x


def bucket_of(n):
    for lo, hi, label in FIRE_BUCKETS:
        if hi is None:
            if n >= lo:
                return label
        elif lo <= n <= hi:
            return label
    return "?"


def pct(a, q):
    if len(a) == 0:
        return float("nan")
    return float(np.percentile(a, q))


class PluginAgg:
    __slots__ = ("count", "cpu_sum", "cpu_list", "zy_count", "zy_cpu_sum",
                 "subjects", "first_seq", "last_seq")

    def __init__(self):
        self.count = 0
        self.cpu_sum = 0.0
        self.cpu_list = []
        self.zy_count = 0
        self.zy_cpu_sum = 0.0
        self.subjects = {}  # subject_tuple -> [count, cpu_sum]
        self.first_seq = None
        self.last_seq = None


class TileStream:
    __slots__ = ("outcomes",)

    def __init__(self):
        self.outcomes = []  # list of (source, result, bp_iters)


class Window:
    __slots__ = ("stages", "costs", "extent_area")

    def __init__(self, area):
        self.stages = []
        self.costs = []
        self.extent_area = area


def is_retry_source(s):
    return "retry" in s


def is_scan_source(s):
    return "scan" in s


def process(path):
    run_open = None
    capture_opens = []
    type_counts = Counter()

    plugins = defaultdict(PluginAgg)
    timeline = []  # (plugin, cpu_s) in JobDone sequence order

    tile_streams = {}  # (page,ty,tx,stream_id) -> TileStream
    to_result_bp = defaultdict(lambda: [0, 0])  # (source,result) -> [count, bp_sum]

    windows = {}  # (capture, level_index, region_index, extent_tuple) -> Window
    window_extent_counts = Counter()  # area -> distinct-window count (set membership tracked separately)
    window_retired_causes = Counter()

    place_cpu_per_last_stage = defaultdict(lambda: [0, 0.0])  # stage -> [count, cpu_sum]

    close_check_count = 0
    close_certified_first = None
    close_certified_last = None
    close_checks_where_certified_grew = 0

    engine_stat_final = None

    run_done = None

    n_lines = 0
    with open(path, "r") as f:
        for line in f:
            n_lines += 1
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            t = d.get("type")
            type_counts[t] += 1

            if t == "RunOpen":
                if run_open is None:
                    run_open = d
            elif t == "CaptureOpen":
                capture_opens.append(d)
            elif t == "JobDone":
                plugin = d["plugin"]
                cpu_s = d["cpu_s"]
                subj = to_hashable(d["subject"])
                nc, np_, nw = d["n_certificates"], d["n_poses"], d["n_words"]
                agg = plugins[plugin]
                seq = len(timeline)
                timeline.append((plugin, cpu_s))
                agg.count += 1
                agg.cpu_sum += cpu_s
                agg.cpu_list.append(cpu_s)
                if agg.first_seq is None:
                    agg.first_seq = seq
                agg.last_seq = seq
                zero_yield = (nc == 0 and np_ == 0 and nw == 0)
                if zero_yield:
                    agg.zy_count += 1
                    agg.zy_cpu_sum += cpu_s
                se = agg.subjects.get(subj)
                if se is None:
                    agg.subjects[subj] = [1, cpu_s]
                else:
                    se[0] += 1
                    se[1] += cpu_s

                if plugin == "place":
                    wkey = tuple(subj)  # (capture, level_index, region_index, extent_tuple)
                    w = windows.get(wkey)
                    last_stage = w.stages[-1] if (w and w.stages) else "<none-scheduled-yet>"
                    ps = place_cpu_per_last_stage[last_stage]
                    ps[0] += 1
                    ps[1] += cpu_s

            elif t == "TileOutcome":
                key = (d["page"], d["ty"], d["tx"], d["stream_id"])
                ts = tile_streams.get(key)
                if ts is None:
                    ts = TileStream()
                    tile_streams[key] = ts
                ts.outcomes.append((d["source"], d["result"], d["bp_iters"]))
                rb = to_result_bp[(d["source"], d["result"])]
                rb[0] += 1
                rb[1] += d["bp_iters"]

            elif t in SEATED_TYPES and _is_place(d):
                wkey = _place_window_key(d)
                extent = wkey[3]
                area = (extent[2] - extent[0]) * (extent[3] - extent[1])
                w = windows.get(wkey)
                if w is None:
                    w = Window(area)
                    windows[wkey] = w
                    window_extent_counts[area] += 1
                w.stages.append(d["stage"])
                w.costs.append(d["cost"])

            elif t in RETIRED_TYPES and _is_place(d):
                # Older trees logged WindowRetired without a `cause` field
                # (added later; see data.py's WorkerRetired docstring).
                window_retired_causes[d.get("cause", "<no-cause-field-in-this-tree>")] += 1

            elif t == "CloseCheck":
                close_check_count += 1
                cert = d["certified"]
                if close_certified_first is None:
                    close_certified_first = cert
                if close_certified_last is not None and cert > close_certified_last:
                    close_checks_where_certified_grew += 1
                close_certified_last = cert

            elif t == "EngineStat":
                engine_stat_final = d

            elif t == "RunDone":
                run_done = d

    total_jobdone = len(timeline)

    return dict(
        path=path,
        n_lines=n_lines,
        type_counts=type_counts,
        run_open=run_open,
        capture_opens=capture_opens,
        plugins=plugins,
        timeline=timeline,
        total_jobdone=total_jobdone,
        tile_streams=tile_streams,
        to_result_bp=to_result_bp,
        windows=windows,
        window_extent_counts=window_extent_counts,
        window_retired_causes=window_retired_causes,
        place_cpu_per_last_stage=place_cpu_per_last_stage,
        close_check_count=close_check_count,
        close_certified_first=close_certified_first,
        close_certified_last=close_certified_last,
        close_checks_where_certified_grew=close_checks_where_certified_grew,
        engine_stat_final=engine_stat_final,
        run_done=run_done,
    )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_section1(R, out):
    out.append("## 1. Per-plugin job / cpu / fire-repeat breakdown\n")
    out.append(
        "Sequence-order note: `first_frac`/`last_frac` are this plugin's "
        "first and last JobDone position divided by the run's total "
        "JobDone count -- a position in the engine-merge SEQUENCE, not a "
        "time.\n")
    total_cpu = sum(a.cpu_sum for a in R["plugins"].values())
    out.append(
        "| plugin | jobs | cpu_s | cpu share | zero-yield jobs | zy cpu_s | "
        "zy cpu share | cpu/job mean | p50 | p90 | max | first_frac | last_frac |")
    out.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    rows = sorted(R["plugins"].items(), key=lambda kv: -kv[1].cpu_sum)
    for plugin, a in rows:
        arr = np.asarray(a.cpu_list, dtype=float)
        cpu_share = a.cpu_sum / total_cpu if total_cpu else float("nan")
        zy_share = a.zy_cpu_sum / a.cpu_sum if a.cpu_sum else float("nan")
        ff = a.first_seq / R["total_jobdone"] if R["total_jobdone"] else float("nan")
        lf = a.last_seq / R["total_jobdone"] if R["total_jobdone"] else float("nan")
        out.append(
            f"| {plugin} | {a.count} | {a.cpu_sum:.2f} | {cpu_share:.3f} | "
            f"{a.zy_count} | {a.zy_cpu_sum:.2f} | {zy_share:.3f} | "
            f"{arr.mean():.4f} | {pct(arr,50):.4f} | {pct(arr,90):.4f} | "
            f"{arr.max():.4f} | {ff:.3f} | {lf:.3f} |")
    out.append("")

    out.append("### Fires-per-subject histogram and top-5 most-fired subjects, per plugin\n")
    for plugin, a in rows:
        out.append(f"**{plugin}** -- {len(a.subjects)} distinct subjects over {a.count} fires")
        hist = Counter()
        for subj, (cnt, cpu) in a.subjects.items():
            hist[bucket_of(cnt)] += 1
        hist_str = ", ".join(
            f"{label}:{hist.get(label,0)}" for _, _, label in FIRE_BUCKETS)
        out.append(f"- fires/subject histogram (subjects per bucket): {hist_str}")
        top5 = sorted(a.subjects.items(), key=lambda kv: -kv[1][0])[:5]
        out.append("- top 5 most-fired subjects (fire count, total cpu_s, subject):")
        for subj, (cnt, cpu) in top5:
            out.append(f"  - {cnt} fires, {cpu:.3f} cpu_s: `{subj!r}`")
        out.append("")


def render_section2(R, out):
    out.append("## 2. tiles.* TileOutcome analysis\n")
    tile_streams = R["tile_streams"]
    to_result_bp = R["to_result_bp"]

    out.append("### result counts per source, and mean bp_iters per (source,result)\n")
    out.append("| source | result | count | bp_iters mean |")
    out.append("|---|---|---:|---:|")
    for (source, result), (cnt, bpsum) in sorted(to_result_bp.items()):
        out.append(f"| {source} | {result} | {cnt} | {bpsum/cnt:.3f} |")
    out.append("")

    attempts_before_cert = []
    never_certified_attempts = []
    n_never_certified_streams = 0
    n_certified_streams = 0
    wasted_retries = 0
    scan_reattempts_hist = Counter()
    scan_reattempts_gt1_streams = 0

    for key, ts in tile_streams.items():
        outcomes = ts.outcomes
        first_cert_idx = None
        first_cert_source = None
        for i, (source, result, bp) in enumerate(outcomes):
            if result == "certified":
                first_cert_idx = i
                first_cert_source = source
                break
        if first_cert_idx is None:
            n_never_certified_streams += 1
            never_certified_attempts.append(len(outcomes))
            continue
        n_certified_streams += 1
        attempts_before_cert.append(first_cert_idx)

        if not is_retry_source(first_cert_source):
            retry_hits = sum(1 for (s, r, b) in outcomes if is_retry_source(s))
            wasted_retries += retry_hits

        if is_scan_source(first_cert_source):
            scan_hits = sum(1 for (s, r, b) in outcomes if is_scan_source(s))
            scan_reattempts_hist[scan_hits] += 1
            if scan_hits > 1:
                scan_reattempts_gt1_streams += 1

    abc = np.asarray(attempts_before_cert, dtype=float)
    nca = np.asarray(never_certified_attempts, dtype=float)
    out.append(
        f"- tile-streams certified: {n_certified_streams}; "
        f"never certified (in this log's window): {n_never_certified_streams}")
    if len(abc):
        out.append(
            f"- attempts BEFORE certification (index of the certifying "
            f"outcome, 0 = certified on first try), over {len(abc)} certified "
            f"streams: mean {abc.mean():.3f}, p50 {pct(abc,50):.1f}, "
            f"p90 {pct(abc,90):.1f}, max {abc.max():.0f}")
    if len(nca):
        out.append(
            f"- attempts on tile-streams that NEVER certified, over "
            f"{len(nca)} streams: total {int(nca.sum())}, mean {nca.mean():.3f}, "
            f"p50 {pct(nca,50):.1f}, p90 {pct(nca,90):.1f}, max {nca.max():.0f}")
    out.append(
        f"- wasted retries (retry-sourced TileOutcome on a stream whose "
        f"first certified outcome came from a non-retry source): "
        f"{wasted_retries}")
    out.append(
        f"- scan re-attempts on eventually scan-certified streams: "
        f"{scan_reattempts_gt1_streams} of "
        f"{sum(scan_reattempts_hist.values())} scan-certified streams had "
        f">1 scan attempt; histogram (scan-attempt-count -> #streams): "
        + ", ".join(f"{k}:{v}" for k, v in sorted(scan_reattempts_hist.items())))
    out.append("")


def render_section3(R, out):
    out.append("## 3. place / window scheduling\n")
    windows = R["windows"]
    window_extent_counts = R["window_extent_counts"]

    n_scheduled_events = sum(len(w.stages) for w in windows.values())
    out.append(f"- distinct windows: {len(windows)}; total place WorkerSeated events: {n_scheduled_events}")

    hist = Counter()
    max_window = None
    max_count = 0
    for wkey, w in windows.items():
        n = len(w.stages)
        hist[bucket_of(n)] += 1
        if n > max_count:
            max_count = n
            max_window = wkey
    hist_str = ", ".join(f"{label}:{hist.get(label,0)}" for _, _, label in FIRE_BUCKETS)
    out.append(f"- place WorkerSeated-events-per-window histogram (windows per bucket): {hist_str}")
    out.append(f"- max place WorkerSeated count for one window: {max_count} (window {max_window!r})")

    if window_extent_counts:
        modal_area = window_extent_counts.most_common(1)[0][0]
        n_child = sum(cnt for area, cnt in window_extent_counts.items() if area < modal_area)
        n_total = sum(window_extent_counts.values())
        out.append(
            f"- modal window extent area: {modal_area} cells "
            f"(area histogram: {dict(sorted(window_extent_counts.items()))}); "
            f"windows smaller than modal ('child' windows): {n_child}/{n_total} "
            f"({n_child/n_total:.3f})" if n_total else "")

    seq_ctr = Counter()
    for w in windows.values():
        seq_ctr[tuple(w.stages)] += 1
    out.append("\n### Top 10 most common stage sequences (ordered stages per window)\n")
    out.append("| count | stage sequence |")
    out.append("|---:|---|")
    for seq, cnt in seq_ctr.most_common(10):
        out.append(f"| {cnt} | {list(seq)} |")
    out.append("")

    all_costs = [c for w in windows.values() for c in w.costs]
    if all_costs:
        ca = np.asarray(all_costs, dtype=float)
        out.append(
            f"- place WorkerSeated cost distribution (all events): mean "
            f"{ca.mean():.2f}, p50 {pct(ca,50):.1f}, p90 {pct(ca,90):.1f}, "
            f"max {ca.max():.0f}")

    causes = R["window_retired_causes"]
    out.append(f"- place WorkerRetired causes: {dict(causes)}" if causes else
               "- place WorkerRetired causes: (none in this log)")

    out.append("\n### place JobDone: cpu per last-known stage before the JobDone\n")
    out.append("| last stage seen for the window | place JobDones | cpu_s |")
    out.append("|---|---:|---:|")
    for stage, (cnt, cpu) in sorted(R["place_cpu_per_last_stage"].items(), key=lambda kv: -kv[1][1]):
        out.append(f"| {stage} | {cnt} | {cpu:.3f} |")
    out.append("")


#: `revisit` is kept for ARCHIVED journals: the row was dissolved
#: 2026-09-21 and no run since emits it, but an A/B's base leg does.
SECTION4_PREFIXES = ("color", "refine.color", "fields", "revisit",
                     "tiles.local", "tiles.planek", "tiles.swim",
                     "tiles.uplift", "tiles.union")


def render_section4(R, out):
    out.append("## 4. Heavy / supplemental rows -- when in the run they fire\n")
    out.append(
        "Sequence-order note again: first/last fire are a FRACTION OF "
        "TOTAL JOBDONE COUNT (a position in engine-merge order), not a "
        "wall-clock fraction -- there are no timestamps in this file.\n")
    out.append("| plugin | distinct subjects | fires | cpu_s | cpu/fire mean | first_frac | last_frac |")
    out.append("|---|---:|---:|---:|---:|---:|---:|")
    total = R["total_jobdone"]
    for plugin, a in sorted(R["plugins"].items()):
        if not plugin.startswith(SECTION4_PREFIXES):
            continue
        ff = a.first_seq / total if total else float("nan")
        lf = a.last_seq / total if total else float("nan")
        out.append(
            f"| {plugin} | {len(a.subjects)} | {a.count} | {a.cpu_sum:.2f} | "
            f"{a.cpu_sum/a.count:.4f} | {ff:.3f} | {lf:.3f} |")
    out.append("")


def render_section5(R, out):
    out.append("## 5. CloseCheck\n")
    n = R["close_check_count"]
    first = R["close_certified_first"]
    last = R["close_certified_last"]
    grown = R["close_checks_where_certified_grew"]
    out.append(f"- CloseCheck events: {n}")
    if n:
        out.append(f"- certified at first CloseCheck: {first}; at last: {last}")
        delta = (last - first) if (first is not None and last is not None) else None
        if delta:
            out.append(
                f"- consults per new certificate (n_checks / (last-first) "
                f"certified): {n/delta:.4f}  (delta={delta})")
        out.append(
            f"- CloseCheck events where certified strictly grew vs the "
            f"previous check: {grown} ({grown/n:.3f} of checks)")
    out.append("")


def render_section6(R, out):
    out.append("## 6. EngineStat (final event, verbatim) + derived\n")
    es = R["engine_stat_final"]
    if es is None:
        out.append("(no EngineStat event in this log)\n")
        return
    out.append("```json")
    out.append(json.dumps(es, indent=2, sort_keys=True))
    out.append("```\n")

    total_jobdone = R["total_jobdone"]
    wakes = es.get("wakes", 0)
    stale_skips = es.get("stale_skips", 0)

    # facts-ingested estimate -- see module docstring for basis.
    tc = R["type_counts"]
    facts_est = (
        tc.get("TileOutcome", 0) + tc.get("WordOutcome", 0) +
        tc.get("WindowSettled", 0) + tc.get("AddressCoverage", 0) +
        tc.get("CalibrateAdopted", 0) + tc.get("FieldFitted", 0) +
        tc.get("PlaneFieldTiers", 0) + tc.get("PoseCommitted", 0) +
        tc.get("CloseCheck", 0)
    )
    out.append(
        f"- wakes per JobDone: {wakes/total_jobdone:.3f}" if total_jobdone else "")
    out.append(
        f"- facts-ingested estimate (see module docstring for basis; "
        f"counts TileOutcome+WordOutcome+WindowSettled+AddressCoverage+"
        f"CalibrateAdopted+FieldFitted+PlaneFieldTiers+PoseCommitted+"
        f"CloseCheck events, i.e. one per store-publishing event OTHER "
        f"than JobDone itself, NOT a count of _touch() calls or "
        f"subscriber wakes): {facts_est}")
    if facts_est:
        out.append(f"- wakes per ingested-fact-estimate: {wakes/facts_est:.3f}")
    if total_jobdone:
        out.append(f"- stale_skips per fire (fire == JobDone): {stale_skips/total_jobdone:.4f}")
    out.append("")


def render_section7(R, out):
    out.append("## 7. CPU timeline proxy -- cumulative cpu_s per plugin over JobDone sequence deciles\n")
    out.append(
        "Deciles are of the JobDone SEQUENCE (engine-merge order), not "
        "wall-clock time -- no timestamps exist in this file.\n")
    timeline = R["timeline"]
    total = len(timeline)
    if total == 0:
        out.append("(no JobDone events)\n")
        return
    plugin_names = sorted(R["plugins"].keys())
    boundaries = [max(1, round(total * k / 10)) for k in range(1, 11)]
    boundaries[-1] = total
    rows = []
    running_by_plugin = defaultdict(float)
    idx = 0
    for k, boundary in enumerate(boundaries, start=1):
        while idx < boundary:
            plugin, cpu_s = timeline[idx]
            running_by_plugin[plugin] += cpu_s
            idx += 1
        rows.append((k, boundary, dict(running_by_plugin)))

    out.append("| decile | jobdone_seq_upto | " + " | ".join(plugin_names) + " |")
    out.append("|---:|---:|" + "---:|" * len(plugin_names))
    for k, boundary, snap in rows:
        vals = " | ".join(f"{snap.get(p,0.0):.1f}" for p in plugin_names)
        out.append(f"| {k} | {boundary} | {vals} |")
    out.append("")


def render_header(R, args, out):
    label = args.label or R["path"]
    out.append(f"# events.jsonl report -- {label}\n")
    out.append(f"- source file: `{R['path']}`")
    out.append(f"- lines read: {R['n_lines']}")
    out.append(f"- event type counts: {dict(sorted(R['type_counts'].items()))}")
    ro = R["run_open"]
    if ro:
        out.append(f"- RunOpen: {json.dumps(ro)}")
    for co in R["capture_opens"]:
        out.append(f"- CaptureOpen: {json.dumps(co)}")
    rd = R["run_done"]
    if rd:
        out.append(f"- RunDone: {json.dumps(rd)}")
    out.append(f"- total JobDone events (the sequence axis used below): {R['total_jobdone']}")
    out.append("")
    out.append(
        "**No timestamps exist in this file.** Every \"sequence\", "
        "\"first/last fire\", \"decile\" or \"when in the run\" statement "
        "below is a position in the engine-merge order of JobDone events, "
        "which is a PROXY for time (appended by the single merge thread) "
        "and not a measurement of it.\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    R = process(args.path)
    out = []
    render_header(R, args, out)
    render_section1(R, out)
    render_section2(R, out)
    render_section3(R, out)
    render_section4(R, out)
    render_section5(R, out)
    render_section6(R, out)
    render_section7(R, out)
    print("\n".join(out))


if __name__ == "__main__":
    main()
