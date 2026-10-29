#!/usr/bin/env python3
"""Illustrate the same 263 raw bytes in an LDPC tile and a standard QR-H."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
from types import ModuleType

from common import CELL_MM, PAYLOAD_BYTES, TILE_MM
from generate import generate
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from holo.gen.ps import PSDoc

def _load_qrcode() -> ModuleType:
    """Load the optional illustration dependency only when generating a QR."""
    dependency_path = str(Path(__file__).parent / "build/python-deps")
    if dependency_path not in sys.path:
        sys.path.insert(0, dependency_path)
    try:
        import qrcode
    except ModuleNotFoundError as exc:
        if exc.name != "qrcode":
            raise
        raise ValueError(
            "QR illustration requires qrcode; install it with "
            "env/bin/python -m pip install --target qr-toy/build/python-deps "
            "-r qr-toy/requirements-illustration.txt"
        ) from exc
    return qrcode


def compare(payload: bytes, out: Path) -> dict[str, object]:
    """Emit equal-pitch LDPC/QR artwork for identical raw bytes."""
    if len(payload) != PAYLOAD_BYTES:
        raise ValueError(f"expected exactly {PAYLOAD_BYTES} bytes")
    if out.exists():
        raise ValueError(f"output directory already exists: {out}")
    qrcode = _load_qrcode()
    from qrcode.util import MODE_8BIT_BYTE, QRData

    out.mkdir(parents=True, exist_ok=False)
    manifest = generate(payload, out / "ldpc")
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=15,
        border=4,
    )
    # Force one raw byte segment: no text, base64, ECI or numeric optimization.
    qr.add_data(QRData(payload, mode=MODE_8BIT_BYTE), optimize=0)
    qr.make(fit=True)
    modules = np.array(qr.get_matrix(), np.uint8)
    dots = np.repeat(np.repeat(modules, 15, axis=0), 15, axis=1)
    qr_image = Image.fromarray(255 * (1 - dots))
    qr_image.save(out / "qr.png", dpi=(600, 600))
    canvas = Image.new("L", (3500, 2300), 255)
    draw = ImageDraw.Draw(canvas)

    def label(x: int, y: int, text: str, size: int = 42) -> None:
        draw.text((x, y), text, fill=0, font=ImageFont.load_default(size=size))

    label(160, 100, "263 bytes, two printed codes", 82)
    label(160, 220, "Identical raw payload  |  equal cell/module pitch: 0.635 mm", 46)
    label(220, 380, "Our LDPC tile", 62)
    label(1900, 380, f"QR version {qr.version}, level H", 62)
    # Align active top edges; retain four modules of white space around QR.
    with Image.open(out / "ldpc/patch.png") as patch:
        canvas.paste(patch, (160, 510))
    canvas.paste(qr_image, (1840, 510))
    label(220, 1640, "64 x 64 cells")
    label(220, 1710, f"Active: {TILE_MM:.2f} x {TILE_MM:.2f} mm")
    label(220, 1780, "LDPC r0547, p103; no fountain")
    label(1900, 1970, f"{qr.modules_count} x {qr.modules_count} modules")
    label(
        1900, 2040,
        f"Active: {qr.modules_count * CELL_MM:.2f} x {qr.modules_count * CELL_MM:.2f} mm",
    )
    label(1900, 2110, f"With quiet zone: {len(modules) * CELL_MM:.2f} mm square")
    label(
        160, 2220,
        "Print at actual size / 100%. Dimensions compare geometry, not equal error tolerance.",
        34,
    )
    # Both outputs use precisely the same one-bit ink raster.
    ink = (np.asarray(canvas) < 128).astype(np.uint8)
    Image.fromarray(255 * (1 - ink)).save(out / "comparison.png", dpi=(600, 600))
    doc = PSDoc(
        page_dots_xy=(4960, 7016),
        jobid=str(manifest["payload_sha256"])[:8],
        title="263-byte LDPC and QR-H comparison",
        engine_dpi=600,
    )
    doc.begin_page()
    doc.put_bitmap(ink, x_dots=(4960 - 3500) // 2, y_dots=(7016 - 2300) // 2)
    doc.end_page()
    (out / "comparison.ps").write_text(doc.render(), encoding="ascii")
    try:
        qr_version = importlib.metadata.version("qrcode")
    except importlib.metadata.PackageNotFoundError:
        qr_version = "unknown (distribution metadata unavailable)"
    details = {
        "payload_bytes": len(payload),
        "payload_sha256": manifest["payload_sha256"],
        "qr_library": f"qrcode {qr_version}",
        "qr_version": qr.version,
        "qr_error_correction": "H",
        "qr_mode": "single raw byte segment",
        "qr_modules": qr.modules_count,
        "quiet_zone_modules": 4,
        "cell_mm": CELL_MM,
        "ldpc_active_mm": TILE_MM,
        "qr_active_mm": qr.modules_count * CELL_MM,
        "qr_with_quiet_zone_mm": len(modules) * CELL_MM,
    }
    (out / "comparison.json").write_text(
        json.dumps(details, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(details, indent=2))
    print(f"Wrote {out}/comparison.png and comparison.ps")
    return details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--payload", type=Path, help="263 bytes; default: counting 00..ff,00..06"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = (
            args.payload.read_bytes()
            if args.payload
            else bytes(i % 256 for i in range(PAYLOAD_BYTES))
        )
        compare(payload, args.out)
        return 0
    except (ValueError, OSError) as exc:
        parser.exit(2, f"compare: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
