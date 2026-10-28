#!/usr/bin/env python
"""Stream a big JSON array file and keep only small per-record fields.

The colour certificate dumps are ~500 MB because a single colour
certificate can name >1,500 dependency certificates; loading one whole
would cost gigabytes.  This walks the array element by element (peak: one
element) and writes a compact table.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import state_slice as S


def elements(path: str):
    import mmap
    handle = open(path, "rb")
    buf = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        assert buf[0:1] == b"["
        i = 1
        n = len(buf)
        space = (b" ", b"\n", b"\t", b"\r")

        def skip(j: int) -> int:
            while j < n and buf[j:j + 1] in space:
                j += 1
            return j

        # Unlike the state files, these dumps are NOT canonical JSON --
        # json.dumps writes ", " / ": " separators -- so whitespace between
        # elements must be skipped or the walker slices a bare space.
        while i < n:
            i = skip(i)
            if buf[i:i + 1] == b"]":
                break
            end = S.scan_value(buf, i)
            yield json.loads(bytes(buf[i:end]).decode())
            i = skip(end)
            if buf[i:i + 1] == b",":
                i += 1
    finally:
        buf.close()
        handle.close()


MODES = {
    "certs": lambda r: [r["page"], r["tile_yx"][0], r["tile_yx"][1],
                        r.get("stream_id", "main"),
                        len(r["dependency_certificate_ids"])],
    "blocks": lambda r: [r["page"], r["tile_yx"][0], r["tile_yx"][1],
                         r["lane_id"], r["n_observed"], len(r["origins"])],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--mode", required=True, choices=sorted(MODES))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    pick = MODES[args.mode]
    rows = [pick(item) for item in elements(args.input)]
    Path(args.out).write_text(json.dumps(rows))
    print(f"{args.mode}: {len(rows)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
