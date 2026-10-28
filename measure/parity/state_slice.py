#!/usr/bin/env python
"""Stream/slice a holo1 receive.state (one canonical-JSON object) without
loading it whole.  Canonical JSON => sorted keys, no whitespace.

Usage:
  state_slice.py --state S --keys              # top-level key map + byte sizes
  state_slice.py --state S --dump KEY --out F  # dump one top-level value as JSON
  state_slice.py --state S --peek KEY [--n N]  # print first N bytes of a value
"""
from __future__ import annotations

import argparse
import json
import mmap
from pathlib import Path

CHUNK = 1 << 22


def scan_value(buf, start: int) -> int:
    """End offset (exclusive) of the JSON value beginning at ``start``."""
    opener = buf[start:start + 1]
    if opener in (b"[", b"{"):
        depth = 0
        i = start
        n = len(buf)
        in_string = False
        escape = False
        while i < n:
            chunk = buf[i:i + CHUNK]
            for offset, byte in enumerate(chunk):
                if in_string:
                    if escape:
                        escape = False
                    elif byte == 0x5C:
                        escape = True
                    elif byte == 0x22:
                        in_string = False
                    continue
                if byte == 0x22:
                    in_string = True
                elif byte in (0x5B, 0x7B):
                    depth += 1
                elif byte in (0x5D, 0x7D):
                    depth -= 1
                    if depth == 0:
                        return i + offset + 1
            i += len(chunk)
        raise ValueError("unterminated container")
    if opener == b'"':
        i = start + 1
        escape = False
        n = len(buf)
        while i < n:
            byte = buf[i]
            if escape:
                escape = False
            elif byte == 0x5C:
                escape = True
            elif byte == 0x22:
                return i + 1
            i += 1
        raise ValueError("unterminated string")
    # scalar: run to the next , } ]
    i = start
    n = len(buf)
    while i < n and buf[i] not in b",}]":
        i += 1
    return i


def top_level_keys(buf) -> list[tuple[str, int, int]]:
    """[(key, value_start, value_end)] for the outermost object."""
    assert buf[0:1] == b"{"
    out = []
    i = 1
    n = len(buf)
    while i < n:
        if buf[i:i + 1] == b"}":
            break
        assert buf[i:i + 1] == b'"', (i, bytes(buf[i:i + 20]))
        key_end = scan_value(buf, i)
        key = json.loads(bytes(buf[i:key_end]).decode("utf-8"))
        assert buf[key_end:key_end + 1] == b":"
        vstart = key_end + 1
        vend = scan_value(buf, vstart)
        out.append((key, vstart, vend))
        i = vend
        if buf[i:i + 1] == b",":
            i += 1
    return out


def open_buf(path: str):
    handle = open(path, "rb")
    return handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--keys", action="store_true")
    ap.add_argument("--dump")
    ap.add_argument("--peek")
    ap.add_argument("--out")
    ap.add_argument("--n", type=int, default=1200)
    args = ap.parse_args()

    handle, buf = open_buf(args.state)
    try:
        keys = top_level_keys(buf)
        if args.keys:
            for key, lo, hi in keys:
                head = bytes(buf[lo:lo + 40]).decode("utf-8", "replace")
                print(f"{hi - lo:>14,}  {key:<28} {head!r}")
        table = {k: (lo, hi) for k, lo, hi in keys}
        if args.peek:
            lo, hi = table[args.peek]
            print(bytes(buf[lo:min(hi, lo + args.n)]).decode("utf-8", "replace"))
        if args.dump:
            lo, hi = table[args.dump]
            data = bytes(buf[lo:hi])
            if args.out:
                Path(args.out).write_bytes(data)
                print(f"wrote {len(data):,} bytes to {args.out}")
            else:
                print(data.decode("utf-8"))
    finally:
        buf.close()
        handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
