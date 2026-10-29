#!/usr/bin/env python3
"""Emit one direct-data LDPC tile; never operate a physical printer."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from common import FORMAT, PAYLOAD_BYTES, TILE_MM, format_parts
import numpy as np
from PIL import Image
from holo.gen.compose import cells_to_dots, compose_page_cells
from holo.gen.ps import PSDoc
from holo.gen.sheet import sheet_layout


def generate(payload: bytes, out: Path) -> dict[str, object]:
    """Emit deterministic rasters and provenance into a new directory."""
    if len(payload) != PAYLOAD_BYTES:
        raise ValueError(
            f"expected exactly {PAYLOAD_BYTES} arbitrary bytes, got {len(payload)}"
        )
    if out.exists():
        raise ValueError(f"output directory already exists: {out}")
    spec, _, _, _, _ = format_parts()
    symbols = np.unpackbits(np.frombuffer(payload, np.uint8))[None, :]
    # The existing frame keeps its one metadata bit. This is not a volume:
    # K=1 only supplies that bit; no fountain or file envelope is constructed.
    cells = compose_page_cells(spec, 0, symbols, k_total=1, version=0)
    dots = cells_to_dots(cells, 15)
    placement = sheet_layout(spec, "A4-6mm", 600)
    digest = hashlib.sha256(payload).hexdigest()
    doc = PSDoc(
        page_dots_xy=placement.page_dots_xy,
        jobid=digest[:8],
        title=f"qr-toy direct-data {FORMAT}",
        engine_dpi=600,
    )
    y, x = placement.origin_dots_yx
    doc.begin_page()
    doc.put_bitmap(dots, x_dots=x, y_dots=y)
    doc.end_page()
    ps = doc.render().encode("ascii")
    page = Image.new("L", placement.page_dots_xy, 255)
    tile = Image.fromarray((255 * (1 - dots)).astype(np.uint8))
    page.paste(tile, (x, y))
    # Useful for screen experiments: same physical scale, four blank cells
    # all around. This blank border is emission space, not a format change.
    patch = Image.new("L", (1080, 1080), 255)
    patch.paste(tile, (60, 60))
    manifest = {
        "kind": "qr-toy-direct-data-v1",
        "format": spec.spec_id,
        "payload_bytes": len(payload),
        "payload_sha256": digest,
        "tile_mm": TILE_MM,
        "cell_mm": TILE_MM / 64,
        "engine_dpi": 600,
        "dots_per_cell": 15,
        "metadata_bit": "existing compose_page_cells(version=0, k_total=1); ignored by toy",
        "fountain": False,
        "envelope": False,
        "page_origin_dots_yx": [int(y), int(x)],
        "ps_sha256": hashlib.sha256(ps).hexdigest(),
        "decoder_contract": "known format, page=0, tile=(0,0), 263 fixed-length bytes",
    }
    out.mkdir(parents=True)
    (out / "tile.ps").write_bytes(ps)
    page.save(out / "tile.png", dpi=(600, 600))
    patch.save(out / "patch.png", dpi=(600, 600))
    (out / "payload.bin").write_bytes(payload)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path, nargs="?", help="exactly 263 bytes")
    parser.add_argument("--counting", action="store_true", help="demo input: 00..ff,00..06")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if (args.payload is not None) == args.counting:
        parser.error("choose a payload file OR --counting")
    try:
        payload = (
            bytes(i % 256 for i in range(PAYLOAD_BYTES))
            if args.counting
            else args.payload.read_bytes()
        )
        print(
            f"[1 input] {len(payload)} bytes; no compression or counting-specific encoding",
            flush=True,
        )
        manifest = generate(payload, args.out)
        print(
            f"[2 frame] {FORMAT}; 103 known cells; 2104 payload bits + metadata + CRC",
            flush=True,
        )
        print(
            f"[3 emit] 960 x 960 printer dots; {TILE_MM:.2f} mm square; centered on A4",
            flush=True,
        )
        print(
            f"[4 output] {args.out}/tile.ps, tile.png, patch.png, payload.bin, manifest.json",
            flush=True,
        )
        print(f"[5 digest] payload sha256={manifest['payload_sha256']}", flush=True)
        return 0
    except (ValueError, OSError) as exc:
        parser.exit(2, f"generate: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
