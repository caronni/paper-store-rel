#!/usr/bin/env python
"""Extract the certified tile set from a holo1 receive.state, cheaply.

A holo1 state is ONE canonical-JSON file (state_codec.py): sorted keys, no
whitespace, evidence blocks inlined as base64(zlib(...)).  A full
``load_session`` therefore decompresses every evidence block -- for the
3.5 GB sheet-I state that is tens of GB of RAM, which this machine does not
have while anything else runs.

We only need the ADDRESSES of the certificates, so we mmap the file, find
the top-level ``"certificates":[`` array, bracket-scan its extent (string
aware) and json.loads that slice alone.  Neither hex bytes nor base64 blobs
can contain the marker (no quote/colon in either alphabet), so the marker is
unambiguous; we additionally require the array's elements to carry
``certificate_id``.

Cross-validated against a real ``load_session`` on the small e029 state --
see ``--crosscheck``.
"""
from __future__ import annotations

import argparse
import json
import mmap
import sys
from pathlib import Path

MARKER = b'"certificates":['


def _scan_array(buf, start: int) -> tuple[int, int]:
    """(start, end) byte offsets of the JSON array opening at ``start``."""
    assert buf[start:start + 1] == b"["
    return _scan_container(buf, start)


def _scan_container(buf, start: int) -> tuple[int, int]:
    """Return (start, end) byte offsets of the JSON value at ``start``.

    ``buf[start]`` must be ``[`` or ``{``.  Scans string-aware so brackets
    inside string values cannot end the container early.
    """
    depth = 0
    i = start
    n = len(buf)
    in_string = False
    escape = False
    # Chunked read so we never materialise the whole (multi-GB) file.
    CHUNK = 1 << 22
    while i < n:
        chunk = buf[i:i + CHUNK]
        for offset, byte in enumerate(chunk):
            if in_string:
                if escape:
                    escape = False
                elif byte == 0x5C:      # backslash
                    escape = True
                elif byte == 0x22:      # quote
                    in_string = False
                continue
            if byte == 0x22:
                in_string = True
            elif byte in (0x5B, 0x7B):  # [ {
                depth += 1
            elif byte in (0x5D, 0x7D):  # ] }
                depth -= 1
                if depth == 0:
                    return start, i + offset + 1
        i += len(chunk)
    raise ValueError("unterminated JSON array")


def _scan_array_or_object(buf, start: int) -> tuple[int, int]:
    """Same bracket scan, for a value opening with either ``[`` or ``{``."""
    opener = buf[start:start + 1]
    if opener not in (b"[", b"{"):
        raise ValueError("value does not open a JSON container")
    if opener == b"{":
        # _scan_array's loop is bracket-generic; only its assert is not.
        return _scan_container(buf, start)
    return _scan_array(buf, start)


def _find_scalar(buf, key: str) -> object | None:
    """Value of a top-level-ish scalar key, first occurrence."""
    marker = f'"{key}":'.encode()
    at = buf.find(marker)
    if at < 0:
        return None
    start = at + len(marker)
    tail = bytes(buf[start:start + 512])
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(tail.decode("utf-8", "replace"))
    except ValueError:
        return None
    return value


def extract(path: Path) -> dict:
    with open(path, "rb") as handle:
        buf = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            best: list | None = None
            occurrences = 0
            at = buf.find(MARKER)
            while at >= 0:
                occurrences += 1
                array_start = at + len(MARKER) - 1
                lo, hi = _scan_array(buf, array_start)
                text = bytes(buf[lo:hi]).decode("utf-8")
                rows = json.loads(text)
                if isinstance(rows, list) and (
                        not rows or (isinstance(rows[0], dict)
                                     and "certificate_id" in rows[0])):
                    if best is None or len(rows) > len(best):
                        best = rows
                at = buf.find(MARKER, hi)
            format_row = _find_scalar(buf, "format_row_id")
            policy = _find_scalar(buf, "receiver_policy_id")
            schema = _find_scalar(buf, "schema_version")
            # Canonical JSON sorts keys, so the state's own "close" record
            # sits immediately after "certificates" -- take the first one
            # at or past the array we accepted.
            close = None
            at_close = buf.find(b'"close":{')
            if at_close >= 0:
                lo2, hi2 = _scan_array_or_object(buf, at_close + len('"close":'))
                try:
                    close = json.loads(bytes(buf[lo2:hi2]).decode("utf-8"))
                except ValueError:
                    close = None
        finally:
            buf.close()

    if best is None:
        raise ValueError(f"no certificates array found in {path}")

    certs = []
    by_stream: dict[str, int] = {}
    seen: set[tuple[int, int, int, str]] = set()
    dupes = 0
    for row in best:
        page = int(row["page"])
        ty, tx = (int(v) for v in row["tile_yx"])
        stream = str(row.get("stream_id", "main"))
        key = (page, ty, tx, stream)
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        certs.append([page, ty, tx, stream])
        by_stream[stream] = by_stream.get(stream, 0) + 1
    certs.sort()
    return {
        "source": str(path),
        "format_row_id": format_row,
        "receiver_policy_id": policy,
        "schema_version": schema,
        "n_certs": len(certs),
        "n_raw_rows": len(best),
        "n_duplicate_work_keys": dupes,
        "marker_occurrences": occurrences,
        "close": close,
        "by_stream": dict(sorted(by_stream.items())),
        "certs": certs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--volume", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--crosscheck", action="store_true",
                    help="also load_session() the state and compare (SMALL "
                         "states only -- blows memory on the big ones)")
    args = ap.parse_args()

    result = extract(Path(args.state))
    result["volume"] = args.volume

    if args.crosscheck:
        sys.path.insert(0, "src")
        from holo.receive.session import load_session
        state = load_session(args.state, defer_fountain_validation=True)
        ref = sorted(
            [c.page, c.tile_yx[0], c.tile_yx[1], c.stream_id]
            for c in state.certificates)
        result["crosscheck"] = {
            "load_session_certs": len(ref),
            "identical": ref == result["certs"],
            "format_row_id": state.format_row_id,
        }
        print(f"crosscheck: load_session={len(ref)} slice={len(result['certs'])} "
              f"identical={ref == result['certs']}")

    Path(args.out).write_text(json.dumps(result))
    print(f"{args.volume}: {result['n_certs']} certs  "
          f"streams={result['by_stream']}  "
          f"format={result['format_row_id']}  schema={result['schema_version']}  "
          f"markers={result['marker_occurrences']}  dupes={result['n_duplicate_work_keys']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
