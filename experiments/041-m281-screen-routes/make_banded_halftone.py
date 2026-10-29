"""e041 S2 — sheet F's page in three horizontal bands, one halftone each.

The halftone is graphics state, not job state, so the control and the
two candidate operators share ONE sheet, one engine pass and one
lateral position of the M281's rendering band:

  band 0  tile rows  0–11  (dots    0–2303)  default halftone — the control
  band 1  tile rows 12–23  (dots 2304–4607)  Type 3, 1x1 threshold 0x80
  band 2  tile rows 24–34  (dots 4608–6719)  Type 1, 600 lpi, angle 0, identity spot

The single DeviceCMYK 1-bit image of the original job is split by rows
into three `image` operators at the exact same dots (same translate /
scale arithmetic, 0.12 pt per dot); the hex data is copied verbatim.
Under ghostscript the three-band page renders to the byte-identical
bitmap of the original (the gate below), so the fossil id and the
stripe instrument apply per tile row.

    env/bin/python experiments/041-m281-screen-routes/make_banded_halftone.py \
        --src <F gen dir>/page000.ps \
        --out experiments/041-m281-screen-routes/build/S2-banded-halftone.ps
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

WIDTH, HEIGHT = 4608, 6720              # dots
HEX_PER_ROW = WIDTH * 4 // 8 * 2        # 4 components x 1 bit -> 2304 bytes -> 4608 hex
PT_PER_DOT = 72.0 / 600.0
X0_PT, Y0_PT = 21.12, 17.76             # the original translate (left, bottom)
BANDS = (                               # (first dot row, last dot row + 1, prologue)
    (0, 2304, b"% band 0: default halftone (control)\n"),
    (2304, 4608, b"% band 1: Type 3, one-cell 50% threshold\n"
                 b"<< /HalftoneType 3 /Width 1 /Height 1 /Thresholds <80> >> sethalftone\n"),
    (4608, 6720, b"% band 2: Type 1, 600 lpi, angle 0, identity spot\n"
                 b"<< /HalftoneType 1 /Frequency 600 /Angle 0 /SpotFunction { pop } >> "
                 b"sethalftone\n"),
)


def split_source(ps: bytes) -> tuple[bytes, str, bytes]:
    head, _, rest = ps.partition(b">> image\n")
    data, _, tail = rest.partition(b"\n>\n")
    hexdata = data.replace(b"\n", b"").decode("ascii")
    if len(hexdata) != HEX_PER_ROW * HEIGHT:
        raise SystemExit(f"unexpected hex length {len(hexdata)}")
    if b"/Width 4608 /Height 6720" not in head:
        raise SystemExit("not sheet F's image header")
    return head, hexdata, tail


def band_ps(r0: int, r1: int, hexrows: str, prologue: bytes) -> bytes:
    h = r1 - r0
    y_bottom = Y0_PT + (HEIGHT - r1) * PT_PER_DOT
    out = b"gsave\n" + prologue
    out += (f"{X0_PT:.6f} {y_bottom:.6f} translate\n"
            f"{WIDTH * PT_PER_DOT:.6f} {h * PT_PER_DOT:.6f} scale\n"
            f"<< /ImageType 1\n   /Width {WIDTH} /Height {h} /BitsPerComponent 1\n"
            f"   /Decode [0 1 0 1 0 1 0 1]\n   /ImageMatrix [{WIDTH} 0 0 -{h} 0 {h}]\n"
            f"   /DataSource currentfile /ASCIIHexDecode filter\n>> image\n").encode()
    wrapped = "\n".join(hexrows[i:i + 128] for i in range(0, len(hexrows), 128))
    out += wrapped.encode() + b"\n>\ngrestore\n"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ps = Path(args.src).read_bytes()
    head, hexdata, tail = split_source(ps)
    # keep everything up to and including "gsave /DeviceCMYK setcolorspace"
    prefix, marker, _ = head.partition(b"gsave /DeviceCMYK setcolorspace\n")
    out = prefix + marker
    for r0, r1, prologue in BANDS:
        out += band_ps(r0, r1, hexdata[r0 * HEX_PER_ROW:r1 * HEX_PER_ROW], prologue)
    out += tail  # "grestore\nshowpage\n%%Trailer\n%%EOF\n" of the original
    Path(args.out).write_bytes(out)
    manifest = {
        "tag": Path(args.out).stem, "source_ps": args.src,
        "source_sha256": hashlib.sha256(ps).hexdigest(),
        "bytes": len(out), "sha256": hashlib.sha256(out).hexdigest(),
        "bands": [{"dot_rows": [r0, r1], "tile_rows": [r0 // 192, (r1 - 1) // 192],
                   "halftone": p.decode().splitlines()[0][2:]} for r0, r1, p in BANDS],
        "format_ref": "L:c3-cmy8-p120-v1@2240x1536", "image_data_changed": False,
    }
    Path(args.out).with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"{Path(args.out).name}: {len(out)} B sha {manifest['sha256'][:16]}…")


if __name__ == "__main__":
    main()
