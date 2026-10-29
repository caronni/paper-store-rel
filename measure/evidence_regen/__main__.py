"""Command line: tags | regen | gt | side.

    PYTHONPATH=src:. <python> -m measure.evidence_regen regen --work DIR [--family ID ...] [--hashes TSV]
    PYTHONPATH=src:. <python> -m measure.evidence_regen gt
    PYTHONPATH=src:. <python> -m measure.evidence_regen side [--only decimated|x2]
    PYTHONPATH=src:. <python> -m measure.evidence_regen tags

Verdicts land in ``build/evidence-regen/`` of this checkout (``--report``).
``--root`` is where the archived files are (default: the main checkout,
which holds scratch/, scans/ and the experiments' build/ dirs).
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
import time
from pathlib import Path

from . import gt_check, side_checks
from .families import BY_ID, FAMILIES
from .runner import Runner, load_hashes, make_tags, write_verdicts

TOOL = Path(__file__).resolve().parents[2]


def main_checkout() -> Path:
    common = subprocess.run(["git", "-C", str(TOOL), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            check=True, capture_output=True, text=True).stdout.strip()
    return Path(common).parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m measure.evidence_regen", description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("tags", "regen", "gt", "side"))
    ap.add_argument("--root", type=Path, default=None, help="archive root (default: the main checkout)")
    ap.add_argument("--report", type=Path, default=TOOL / "build" / "evidence-regen")
    ap.add_argument("--work", type=Path, default=None, help="regen: worktrees + fresh outputs (required)")
    ap.add_argument("--family", action="append", default=[],
                    help="regen: run only these ids (repeatable; shell-style globs, e.g. 'paperholo-*')")
    ap.add_argument("--hashes", type=Path, default=None, help="regen: sha TSV (sha256, bytes, mtime, path)")
    ap.add_argument("--python", type=Path, default=None, help="default: <main checkout>/env/bin/python")
    ap.add_argument("--keep-worktrees", action="store_true")
    ap.add_argument("--only", choices=("decimated", "x2"), default=None, help="side: one of the two")
    a = ap.parse_args(argv)
    repo = main_checkout()
    root = a.root or repo
    t0 = time.monotonic()
    if a.command == "tags":
        for name, sha, what in make_tags(repo):
            print(f"{name}\t{sha}\t{what}")
    elif a.command == "regen":
        if a.work is None:
            ap.error("regen needs --work DIR (worktrees and fresh outputs go there)")
        unknown = [g for g in a.family if not fnmatch.filter(BY_ID, g)]
        if unknown:
            ap.error(f"unknown family {unknown}; known: {', '.join(BY_ID)}")
        fams = tuple(f for f in FAMILIES if not a.family or any(fnmatch.fnmatch(f.id, g) for g in a.family))
        runner = Runner(repo, TOOL, root, a.work.resolve(), a.python or repo / "env/bin/python",
                        load_hashes(a.hashes), a.keep_worktrees)
        verdicts = runner.run(fams)
        tag = "-".join(g.replace("*", "") for g in a.family).strip("-")
        out = a.report / ("verdicts.tsv" if not a.family else f"verdicts-{tag}.tsv")
        write_verdicts(out, verdicts)
        counts: dict[str, int] = {}
        for v in verdicts:
            counts[v.verdict] = counts.get(v.verdict, 0) + 1
        print(f"{out}: {counts} (log {runner.log})")
    elif a.command == "gt":
        verdicts = gt_check.run(root)
        gt_check.write(a.report / "gt.tsv", verdicts)
        counts = {}
        for v in verdicts:
            counts[v.verdict] = counts.get(v.verdict, 0) + 1
        print(f"{a.report / 'gt.tsv'}: {counts}")
    else:
        rows = []
        if a.only in (None, "x2"):
            rows += side_checks.check_x2(root)
        if a.only in (None, "decimated"):
            rows += side_checks.check_decimated(root)
        name = "side.tsv" if a.only is None else f"side-{a.only}.tsv"
        side_checks.write(a.report / name, rows)
        for r in rows:
            print("\t".join(r))
    print(f"wall {time.monotonic() - t0:.0f} s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
