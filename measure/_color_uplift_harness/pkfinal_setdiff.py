"""PK-FINAL derivation tool (committed per review disposition 2026-08-10).

Certificate-set difference: candidate FULL run vs ARCHIVED.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.pkfinal_setdiff --capture xerox-c3-cmy7

`gt_score run` reports `certificate_set_vs_archived` only for REPLAY runs
(a full run carries no archived block, by design — it never opened the
archived state).  This does the same comparison from the frozen state
cache, at BOTH granularities that matter: the certificate id, and the
(page, tile, stream) ADDRESS.  Certificate ids embed the minting attempt,
so a re-timed tile is a different id for the same address; the address
level is the one the yield ledger counts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import corpus, state_cache


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.pkfinal_setdiff", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--arm", default="pkfinal")
    parser.add_argument("--runs", default=None,
                        help="run JSON directory (default <work>/runs)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    row = corpus.capture(args.capture)
    runs = Path(args.runs) if args.runs else corpus.work_dir("runs")
    run = json.loads(
        (runs / f"{args.capture}-full-{args.arm}.json").read_text())
    cache = state_cache.load(row, verbose=False)

    archived_ids = set(cache.certificates_by_id)
    candidate_ids = {item["certificate_id"] for item in run["certificates"]}

    def address(record) -> tuple:
        return (int(record.page), int(record.tile_yx[0]),
                int(record.tile_yx[1]), record.stream_id)

    archived_addr = {address(record)
                     for record in cache.certificates_by_id.values()}
    candidate_addr = {(int(item["page"]), int(item["tile_yx"][0]),
                       int(item["tile_yx"][1]), item["stream_id"])
                      for item in run["certificates"]}

    gained = sorted(candidate_addr - archived_addr)
    lost = sorted(archived_addr - candidate_addr)
    document = {
        "capture": args.capture,
        "arm": args.arm,
        "archived_certificates": len(archived_ids),
        "candidate_certificates": len(candidate_ids),
        "id_identical": archived_ids == candidate_ids,
        "id_missing": len(archived_ids - candidate_ids),
        "id_extra": len(candidate_ids - archived_ids),
        "archived_addresses": len(archived_addr),
        "candidate_addresses": len(candidate_addr),
        "addresses_gained": len(gained),
        "addresses_lost": len(lost),
        "strict_superset": not lost,
        "lost_addresses": [list(item) for item in lost[:60]],
        "gained_examples": [list(item) for item in gained[:10]],
    }
    print(json.dumps(document, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(document, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
