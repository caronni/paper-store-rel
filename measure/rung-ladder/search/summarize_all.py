# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/summarize_all.py
"""ONE ranked summary over every tier (added by the 2026-09-30 prep review).

Merges the runs' results.jsonl (common.merge_runs: identical rids are identical codes under common
random numbers, so the union is safe) into <out>/results.jsonl and writes <out>/TABLES-search.md:

  1. the CONFIRMED ranking (confirm.py's stage-3 table), when the confirm dir exists — the headline;
  2. common.summarize over the union: per k, every walked finalist of Tier A, B1, B2 and the frozen
     recipe in ONE table ranked by BIAWGN Es/N0 @ 1 % (the `tier` column says where each came from),
     the screen-1 ranking, screen-0 verdicts and factor marginals, and the SEED-VARIANCE table;
  3. Tier B1's density-evolution section (GA/MC thresholds vs measurement);
  4. Tier B2's paired section (variant − plain on the same config and seed).

  cd <repo>; S=measure/rung-ladder/search
  PYTHONPATH=src:. env/bin/python $S/summarize_all.py                      # overnight dirs -> overnight-ALL
  PYTHONPATH=src:. env/bin/python $S/summarize_all.py --runs trial-A2 trial-B1 trial-B2 --out trial-ALL --conf none
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import confirm  # noqa: E402
import de_profile  # noqa: E402
import variants_search as VS  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", default=["overnight-A", "overnight-AF", "overnight-B1", "overnight-B2"])
    ap.add_argument("--conf", default="overnight-CONF", help="confirm.py output dir, or 'none'")
    ap.add_argument("--out", default="overnight-ALL")
    a = ap.parse_args(argv)
    sp = lambda x: Path(x) if Path(x).is_absolute() else common.SEARCH / x  # noqa: E731
    runs = [sp(r) for r in a.runs if (sp(r) / "results.jsonl").exists()]
    missing = [r for r in a.runs if not (sp(r) / "results.jsonl").exists()]
    if missing:
        print(f"[summarize_all] no results.jsonl in {missing} (skipped)", file=sys.stderr)
    if not runs:
        sys.exit("nothing to summarize")
    out = sp(a.out)
    common.merge_runs(runs, out)
    p = common.summarize(out)
    body = p.read_text()
    head = []
    if a.conf != "none":
        done = confirm.union(runs)
        head = confirm.table(sp(a.conf), done)
        if head:
            (sp(a.conf) / "TABLES-confirm.md").write_text("\n".join(head) + "\n")
            head += ["---", ""]
    tail = ["", "---", ""] + de_profile.de_section(out, [r for r in runs if (r / "de-candidates.json").exists()])
    tail += VS.b2_section(out)
    p.write_text("\n".join(head) + "\n" + body + "\n".join(tail) + "\n")
    print(p)


if __name__ == "__main__":
    main()
