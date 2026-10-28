#!/usr/bin/env python
"""Peek at nested values inside a holo1 state's ``state`` object."""
from __future__ import annotations
import argparse, json
import state_slice as S


def state_obj(path):
    handle, buf = S.open_buf(path)
    keys = {k: (a, b) for k, a, b in S.top_level_keys(buf)}
    lo, hi = keys["state"]
    return handle, buf, lo, hi


def sub_keys(buf, lo, hi):
    rows = {}
    i = lo + 1
    while i < hi:
        if buf[i:i + 1] == b"}":
            break
        ke = S.scan_value(buf, i)
        k = json.loads(bytes(buf[i:ke]).decode())
        vs = ke + 1
        ve = S.scan_value(buf, vs)
        rows[k] = (vs, ve)
        i = ve
        if buf[i:i + 1] == b",":
            i += 1
    return rows


def first_elem(buf, lo, hi):
    """First element of a JSON array in [lo,hi)."""
    assert buf[lo:lo + 1] == b"["
    end = S.scan_value(buf, lo + 1)
    return json.loads(bytes(buf[lo + 1:end]).decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--elem", action="store_true", help="decode first array element")
    ap.add_argument("--n", type=int, default=2000)
    args = ap.parse_args()
    handle, buf, lo, hi = state_obj(args.state)
    try:
        rows = sub_keys(buf, lo, hi)
        a, b = rows[args.key]
        if args.elem:
            obj = first_elem(buf, a, b)
            print(json.dumps(obj, indent=1)[:args.n])
        else:
            print(bytes(buf[a:a + args.n]).decode("utf-8", "replace"))
    finally:
        buf.close(); handle.close()


if __name__ == "__main__":
    main()
