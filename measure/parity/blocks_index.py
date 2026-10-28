#!/usr/bin/env python
"""Index the evidence blocks of a holo1 receive.state.

Each durable block is one ``(source sha, lane, page, tile)`` evidence unit
(``src/holo/receive/evidence_blocks.py``).  The state inlines it as
base64(zlib(body+digest)) with its ``block_id`` in the manifest, so the
header can be parsed directly -- no ``load_session``, no numpy tensors, and
a memory footprint of one block at a time.

Emits, per block: block_id, lane_id, page, tile, kind, observed-cell count,
and the origin table (placement id, patch ordinal, held-out log-loss).
"""
from __future__ import annotations

import argparse
import base64
import json
import struct
import zlib
from pathlib import Path

import peek_sub
import state_slice as S

MAGICS = {
    b"holo/e023b/evidence-block/v4\x00": ("k", 1),
    b"holo/e023b/evidence-block/cmy7-v1\x00": ("cmy7", 6),
    b"holo/e023b/evidence-block/cmy8-v1\x00": ("cmy8", 3),
}
BITMAP_BYTES = 512


def parse_header(body: bytes) -> dict:
    kind = arity = None
    for magic, (name, width) in MAGICS.items():
        if body.startswith(magic):
            kind, arity, off = name, width, len(magic)
            break
    if kind is None:
        raise ValueError("unknown evidence-block magic")
    source = body[off:off + 32].hex()
    off += 32
    (n,) = struct.unpack_from("<Q", body, off)
    off += 8
    lane = body[off:off + n].decode("ascii")
    off += n
    page, ty, tx = struct.unpack_from("<QQQ", body, off)
    off += 24
    bitmap = body[off:off + BITMAP_BYTES]
    off += BITMAP_BYTES
    n_observed = sum(byte.bit_count() for byte in bitmap)
    (n_origins,) = struct.unpack_from("<H", body, off)
    off += 2
    origins = []
    for _ in range(n_origins):
        (m,) = struct.unpack_from("<Q", body, off)
        off += 8
        placement = body[off:off + m].decode("utf-8")
        off += m
        (size,) = struct.unpack_from("<Q", body, off)
        off += 8
        patch = int.from_bytes(body[off:off + size], "little")
        off += size
        (loss,) = struct.unpack_from("<d", body, off)
        off += 8
        (n_deps,) = struct.unpack_from("<Q", body, off)
        off += 8
        deps = [body[off + 32 * i:off + 32 * (i + 1)].hex() for i in range(n_deps)]
        off += 32 * n_deps
        origins.append({"placement_id": placement, "patch_id": patch,
                        "heldout_logloss": loss, "deps": deps})
    return {"kind": kind, "arity": arity, "source_sha256": source,
            "lane_id": lane, "page": page, "tile_yx": [ty, tx],
            "n_observed": n_observed, "origins": origins}


def iter_blocks(state_path: str):
    handle, buf, lo, hi = peek_sub.state_obj(state_path)
    try:
        rows = peek_sub.sub_keys(buf, lo, hi)
        a, b = rows["blocks"]
        assert buf[a:a + 1] == b"["
        i = a + 1
        while i < b:
            if buf[i:i + 1] == b"]":
                break
            end = S.scan_value(buf, i)
            rec = json.loads(bytes(buf[i:end]).decode())
            body = zlib.decompress(base64.b64decode(rec["data"]))
            head = parse_header(body)
            head["block_id"] = rec["sha256"]
            head["size"] = rec["size"]
            yield head
            i = end
            if buf[i:i + 1] == b",":
                i += 1
    finally:
        buf.close()
        handle.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = list(iter_blocks(args.state))
    Path(args.out).write_text(json.dumps(rows))
    lanes: dict[str, int] = {}
    for row in rows:
        lanes[row["lane_id"]] = lanes.get(row["lane_id"], 0) + 1
    print(f"{len(rows)} blocks; lanes {dict(sorted(lanes.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
