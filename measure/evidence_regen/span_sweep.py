"""Regenerate families at every candidate commit: one verdict row per (commit, archived file).

Runtime-composed over this package: each commit gets its own Runner and work
dir, the family table's ``commit`` swapped for the candidate sha, so a
family's regeneration span (the earliest and latest tree that remake its
archived files byte-identically) is read off one matrix instead of argued.

    PYTHONPATH=src:. env/bin/python measure/evidence_regen/span_sweep.py \
        --work DIR --commits FILE [--family GLOB ...] [--jobs 6] [--order-ref main]

``--commits`` lists one sha per line (anything after a space is ignored).
Default families: ``paperholo-*`` and ``e025``.  Every family runs in a
detached worktree of each commit (``git worktree add``, serialized; removed
after the run) with the main checkout's interpreter and compares against
docs/evidence-archive/hashes-retained.tsv exactly as ``regen`` does.  Output:
``DIR/matrix.tsv`` (commit, date, family, archived, verdict, note) and, on
stdout, one verdict string per family over the commits in the topological
order of ``--order-ref`` (I every compared file identical, D some differ,
x not runnable or not produced) with the first and last identical commit.

Candidate list of record (2026-10-22, docs/evidence-archive/
REGENERATION-2026-10-22.md): every commit touching src/paperholo or a
generator (68) plus every commit between verdict transitions (16).  A commit
that touches none of a family's inputs cannot change its output, so the
sweep covers the dependency closure, not every commit.
"""
from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(TOOL / "src"), str(TOOL)]

from measure.evidence_regen.__main__ import main_checkout  # noqa: E402
from measure.evidence_regen.families import FAMILIES  # noqa: E402
from measure.evidence_regen.runner import Runner, load_hashes, write_verdicts  # noqa: E402

VERDICT_SYMBOL = {"byte-identical": "I"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--commits", type=Path, required=True)
    ap.add_argument("--family", action="append", default=[], help="glob over family ids (repeatable)")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--order-ref", default="main", help="ref whose topological order sorts the summary")
    ap.add_argument("--hashes", type=Path, default=TOOL / "docs/evidence-archive/hashes-retained.tsv")
    ap.add_argument("--python", type=Path, default=None, help="default: <main checkout>/env/bin/python")
    a = ap.parse_args(argv)
    python = a.python or main_checkout() / "env/bin/python"   # a worktree has no env/
    globs = a.family or ["paperholo-*", "e025"]
    fams = tuple(f for f in FAMILIES if f.commit and any(fnmatch.fnmatch(f.id, g) for g in globs))
    commits = [line.split()[0] for line in a.commits.read_text().splitlines() if line.strip()]
    hashes = load_hashes(a.hashes)
    lock = threading.Lock()

    def run_one(sha: str) -> list:
        date = subprocess.run(["git", "-C", str(TOOL), "log", "-1", "--format=%cs", sha],
                              capture_output=True, text=True).stdout.strip()
        runner = Runner(TOOL, TOOL, TOOL, a.work / f"{date}-{sha[:8]}", python, hashes)
        plain = runner.worktree

        def serialized(s: str, patch: str | None) -> Path:
            with lock:
                return plain(s, patch)
        runner.worktree = serialized
        t0 = time.monotonic()
        verdicts = runner.run(tuple(dataclasses.replace(f, commit=sha) for f in fams))
        write_verdicts(runner.work / "verdicts.tsv", verdicts)
        counts: dict[str, int] = {}
        for v in verdicts:
            counts[v.verdict] = counts.get(v.verdict, 0) + 1
        print(f"{date} {sha[:8]} {time.monotonic() - t0:5.0f} s {counts}", flush=True)
        return [(sha[:8], date, v.family, v.archived, v.verdict, v.note.replace("\t", " ")) for v in verdicts]

    rows: list = []
    with ThreadPoolExecutor(a.jobs) as ex:
        for res in ex.map(run_one, commits):
            rows.extend(res)
    a.work.mkdir(parents=True, exist_ok=True)
    (a.work / "matrix.tsv").write_text(
        "commit\tdate\tfamily\tarchived\tverdict\tnote\n" + "".join("\t".join(r) + "\n" for r in rows))

    topo = subprocess.run(["git", "-C", str(TOOL), "rev-list", "--reverse", "--topo-order", a.order_ref],
                          capture_output=True, text=True).stdout.split()
    rank = {h[:8]: i for i, h in enumerate(topo)}
    order = sorted({r[0] for r in rows}, key=lambda c: rank.get(c, 10**9))
    for fam in fams:
        cells = {c: [r[4] for r in rows if r[0] == c and r[2] == fam.id] for c in order}
        def sym(vs: list[str]) -> str:
            if vs and all(v == "byte-identical" for v in vs):
                return "I"
            return "D" if any(v == "differs" for v in vs) else "x"
        s = "".join(sym(cells[c]) for c in order)
        good = [c for c in order if sym(cells[c]) == "I"]
        span = f"first {good[0]} last {good[-1]}" if good else "never identical"
        print(f"{fam.id:30s} {s}  {span}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
