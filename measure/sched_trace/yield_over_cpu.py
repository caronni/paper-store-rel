"""Yield over CPU per row, from a holo3 run dir's events.jsonl (no decode).

    PYTHONPATH=src env/bin/python measure/sched_trace/yield_over_cpu.py <run_dir>/events.jsonl ...

For each run: the RunOpen (family, format, captures), then the JobDone
sequence in file order (seat-sequence merge order; events.jsonl carries
no timestamps, so cumulative job cpu_s is the clock). Per row: fires,
cpu, certificates, cpu per certificate; certificates by the SUBJECT's
fire ordinal (1, 2, 3-5, 6+) with the cpu spent in each bin; and the
certificate yield per row in deciles of the run's cumulative cpu.
Reading only. Record: YIELD-OVER-CPU-2026-10-18.md beside this file.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

BINS = ("1", "2", "3-5", "6+")


def _bin(n: int) -> str:
    return "1" if n == 1 else "2" if n == 2 else "3-5" if n <= 5 else "6+"


def reduce(path: str) -> None:
    rows_fires: Counter = Counter()
    rows_cpu: Counter = Counter()
    rows_certs: Counter = Counter()
    ordinal: Counter = Counter()                 # (plugin, subject) -> fires so far
    certs_by_ordinal: dict = defaultdict(Counter)   # plugin -> bin -> certs
    cpu_by_ordinal: dict = defaultdict(Counter)     # plugin -> bin -> cpu
    jobs: list[tuple[str, float, int]] = []
    run_open: dict = {}
    total_certs = 0
    with open(path) as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            t = o.get("type")
            if t == "RunOpen":
                run_open = o
            elif t == "JobDone":
                p = o["plugin"]
                cpu = float(o.get("cpu_s", 0.0))
                nc = int(o.get("n_certificates", 0))
                key = (p, repr(o.get("subject")))
                ordinal[key] += 1
                b = _bin(ordinal[key])
                certs_by_ordinal[p][b] += nc
                cpu_by_ordinal[p][b] += cpu
                rows_fires[p] += 1
                rows_cpu[p] += cpu
                rows_certs[p] += nc
                total_certs += nc
                jobs.append((p, cpu, nc))
    total_cpu = sum(c for _, c, _ in jobs)
    print(f"\n### {path}")
    print(f"family {run_open.get('family')}  format "
          f"{run_open.get('display_id') or run_open.get('format_id')}  "
          f"captures {run_open.get('n_captures')}  workers "
          f"{run_open.get('workers')}  jobs {len(jobs)}  job cpu "
          f"{total_cpu:,.0f} s  certs {total_certs:,}")
    print(f"{'row':<18}{'fires':>8}{'cpu-s':>10}{'certs':>7}{'cpu/cert':>10}"
          f"  certs by subject fire ordinal 1 | 2 | 3-5 | 6+   (cpu-s in each)")
    for p in sorted(rows_fires, key=lambda q: -rows_cpu[q]):
        c = rows_certs[p]
        per = f"{rows_cpu[p] / c:,.1f}" if c else "—"
        bins = " | ".join(f"{certs_by_ordinal[p][b]}" for b in BINS)
        cpus = " | ".join(f"{cpu_by_ordinal[p][b]:,.0f}" for b in BINS)
        print(f"{p:<18}{rows_fires[p]:>8}{rows_cpu[p]:>10,.0f}{c:>7}{per:>10}"
              f"  {bins:<28} ({cpus})")
    if total_cpu > 0:
        print("certs per decile of cumulative job cpu (rows with any certificate):")
        dec: dict = defaultdict(lambda: [0] * 10)
        acc = 0.0
        for p, cpu, nc in jobs:
            acc += cpu
            dec[p][min(9, int(10 * acc / total_cpu))] += nc
        for p in sorted(dec, key=lambda q: -rows_certs[q]):
            if rows_certs[p]:
                print(f"  {p:<16} " + " ".join(f"{v:>5}" for v in dec[p]))


if __name__ == "__main__":
    for path in sys.argv[1:]:
        reduce(path)
