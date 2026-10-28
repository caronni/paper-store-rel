"""PK-FINAL derivation tool (committed per review disposition 2026-08-10).

Per-lane certificates (by stream) from a FULL run.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.pkfinal_lanes --capture xerox-c3-cmy7

Historically a full run's JSON recorded certificates without a lane id
(``run_full`` passed an empty lane map), so the per-lane split had to come
from the produced state itself, read READ-ONLY with the same
``load_session(..., defer_fountain_validation=True)`` the harness's state
cache uses.  ``run_full`` now publishes the lane on every certificate row
from the same fact (``_lane_by_certificate``); this tool remains the
independent reader — it opens the state rather than trusting the JSON, and
it is how the archived column is produced.  The archived column comes from
the frozen provenance cache of the ARCHIVED state, so the two columns are
the same quantity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import corpus, state_cache


def lane_rows(state_path: Path) -> tuple[list[dict], dict]:
    from holo.receive.session import load_session

    state = load_session(state_path, defer_fountain_validation=True)
    record = state.captures[0]
    by_id = {row.certificate_id: row for row in state.certificates}
    rows = []
    for ordinal, level in enumerate(record.levels):
        payload = level.payload
        ids = () if payload is None else tuple(payload.certificate_ids)
        streams: dict[str, int] = {}
        for identity in ids:
            row = by_id.get(identity)
            if row is not None:
                streams[row.stream_id] = streams.get(row.stream_id, 0) + 1
        rows.append({
            "ordinal": ordinal,
            "lane_id": record.plan[ordinal].lane_id,
            "certificates": len(ids),
            "by_stream": dict(sorted(streams.items())),
            "blocks": 0 if payload is None else int(payload.n_blocks),
            "attempts": 0 if payload is None else int(payload.n_attempts),
            "poses": 0 if level.address is None
                     else len(level.address.pose_ids),
        })
    summary = {
        "levels": len(record.levels),
        "certificates": len(state.certificates),
        "close_status": state.close.status.value,
        "page_hypotheses": (None if state.page_hypotheses is None
                            else list(state.page_hypotheses)),
        "format_row_id": state.format_row_id,
    }
    return rows, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.pkfinal_lanes", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--arm", default="pkfinal")
    parser.add_argument("--state", default=None,
                        help="produced receive.state (default "
                             "<work>/full/<capture>-<arm>/receive.state)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    row = corpus.capture(args.capture)
    state_path = (
        Path(args.state) if args.state
        else corpus.work_dir("full", f"{args.capture}-{args.arm}")
        / "receive.state")
    rows, summary = lane_rows(state_path)

    cache = state_cache.load(row, verbose=False)
    archived = {level.lane_id: len(level.certificate_ids)
                for level in cache.levels}
    archived_stream: dict[str, int] = {}
    for record in cache.certificates_by_id.values():
        archived_stream[record.stream_id] = (
            archived_stream.get(record.stream_id, 0) + 1)

    print(f"# {args.capture} / {args.arm}: {summary}")
    print(f"# archived total {cache.n_state_certificates} "
          f"{dict(sorted(archived_stream.items()))} "
          f"close={cache.close_status}")
    print(f"{'lane':22s} {'certs':>6s} {'arch':>6s} {'blocks':>7s} "
          f"{'attempts':>9s} {'poses':>6s}  by stream")
    for item in rows:
        arch = archived.get(item["lane_id"])
        print(f"{item['lane_id']:22s} {item['certificates']:6d} "
              f"{('-' if arch is None else arch):>6} {item['blocks']:7d} "
              f"{item['attempts']:9d} {item['poses']:6d}  "
              f"{item['by_stream']}")
    document = {"capture": args.capture, "arm": args.arm,
                "state_path": str(state_path),
                "summary": summary, "lanes": rows,
                "archived_by_lane": archived,
                "archived_by_stream": dict(sorted(archived_stream.items())),
                "archived_total": cache.n_state_certificates}
    if args.out:
        Path(args.out).write_text(json.dumps(document, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
