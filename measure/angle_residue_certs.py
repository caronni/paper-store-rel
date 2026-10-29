#!/usr/bin/env python
"""Do the two receivers agree on what they certified?  Per arm.

    PYTHONPATH=src:. env/bin/python -m measure.angle_residue_certs \\
        --work build/angle-residue

Historical record (holo2 vs holo3 angle residue); reads the run dirs
``measure.angle_residue`` wrote into ``--work``.

holo3's certificates come from the run dir's ``facts.npz`` snapshot
(``holo.receiver.snapshot.read``), a recorded artifact; the receiver is not re-run.
Until 2026-09-05 this script also read holo2's ``--state-dir`` and
compared the two certificate sets bit for bit (zero disagreements ever
found); that half went with holo2 — the record is
docs/archive/holo2/measure-README.md and the angle-residue report.

A DISAGREEING BIT VECTOR ON A SHARED ADDRESS IS THE ONE ALARM.  Both
trees claim zero wrong certificates; a mismatch here would be a wrong
certificate in one of them, which outranks every scheduling question in
this report.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np



def holo3_bits(run_dir: Path) -> dict:
    from holo.receiver import data, snapshot

    facts = snapshot.read(run_dir / "facts.npz")
    out = {}
    for fact in facts:
        if isinstance(fact, data.Certificate):
            out[(int(fact.page), int(fact.ty), int(fact.tx),
                 str(fact.stream_id))] = np.asarray(
                     fact.user_bits, np.uint8).ravel()
    return out



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--angles", type=float, nargs="+",
                        default=[0.00, 0.80])
    parser.add_argument("--work", type=Path, required=True,
                        help="the directory measure.angle_residue wrote")
    args = parser.parse_args(argv)
    summary = {}
    for angle in args.angles:
        row: dict = {}
        h3_dir = args.work / f"holo3-a{angle:.2f}"
        if (h3_dir / "facts.npz").exists():
            h3 = holo3_bits(h3_dir)
            row["holo3_certificates"] = len(h3)
        else:
            h3 = {}
            row["holo3_certificates"] = None
        summary[f"a{angle:.2f}"] = row
    (args.work / "certs-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
