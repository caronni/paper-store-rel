#!/usr/bin/env python
"""Do the two receivers agree on what they certified?  Per arm.

    PYTHONPATH=holo2/src:. env/bin/python -m measure.angle_residue_certs

holo3's certificates come from the run dir's ``facts.npz`` snapshot
(``holo3.snapshot.read``); holo2's from its ``--state-dir`` through the
reader the 2026-08-28 crop campaign already used
(``holo2.measure.tile_differential``).  Both are recorded artifacts;
neither receiver is re-run.

A DISAGREEING BIT VECTOR ON A SHARED ADDRESS IS THE ONE ALARM.  Both
trees claim zero wrong certificates; a mismatch here would be a wrong
certificate in one of them, which outranks every scheduling question in
this report.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "angle-residue"


def holo3_bits(run_dir: Path) -> dict:
    from holo3 import data, snapshot

    facts = snapshot.read(run_dir / "facts.npz")
    out = {}
    for fact in facts:
        if isinstance(fact, data.Certificate):
            out[(int(fact.page), int(fact.ty), int(fact.tx),
                 str(fact.stream_id))] = np.asarray(
                     fact.user_bits, np.uint8).ravel()
    return out


def holo2_bits(state_dir: Path) -> dict:
    sys.path.insert(0, str(ROOT / "holo2"))
    from measure import tile_differential
    from holo2.solve.keys import parse_tile_key

    out = {}
    with tile_differential.open_h2_store(state_dir) as store:
        index = tile_differential.build_h2_index(store)
        for key in index.store_index.certified_tiles:
            record = index.store_index.tiles[key]
            page, ty, tx, stream = parse_tile_key(key)
            symbol = np.asarray(store.read_array(record.bits_ref),
                                np.uint8).ravel()
            out[(page, ty, tx, stream)] = np.concatenate(
                ([np.uint8(record.metadata_bit)], symbol))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--angles", type=float, nargs="+",
                        default=[0.00, 0.80])
    args = parser.parse_args(argv)
    summary = {}
    for angle in args.angles:
        row: dict = {}
        h3_dir = OUT / f"holo3-a{angle:.2f}"
        if (h3_dir / "facts.npz").exists():
            h3 = holo3_bits(h3_dir)
            row["holo3_certificates"] = len(h3)
        else:
            h3 = {}
            row["holo3_certificates"] = None
        h2_dir = OUT / f"holo2-a{angle:.2f}" / "state"
        try:
            h2 = holo2_bits(h2_dir)
            row["holo2_certificates"] = len(h2)
        except Exception as exc:
            h2 = {}
            row["holo2_error"] = f"{type(exc).__name__}: {exc}"
        if h3 and h2:
            shared = set(h3) & set(h2)
            disagree = [k for k in shared
                        if not np.array_equal(h3[k], h2[k])]
            row.update(shared=len(shared), holo3_only=len(set(h3) - set(h2)),
                       holo2_only=len(set(h2) - set(h3)),
                       disagreeing_bits=len(disagree),
                       disagreeing=[list(k) for k in sorted(disagree)[:10]])
        summary[f"a{angle:.2f}"] = row
    (OUT / "certs-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
