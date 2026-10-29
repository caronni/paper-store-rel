"""e041 S6 — sheet F through every PostScript door the M281 answered to.

The zero-paper capability queries of 2026-10-04 (query/ps-capability-
response{,2,3}.txt) established, on the printer itself:
  - `setpagedevice` accepts `/ProcessColorModel /DeviceCMYK /PixelDepth 1`
    for the job and both read back (the default is DeviceRGB, 8 bit: the
    interpreter renders our composite into an RGB contone pipeline and the
    engine converts and screens it afterwards — the stage e038's screens
    come from);
  - the interpreter honours `sethalftone` (HalftoneMode is 0; a Type 3
    1x1 threshold reads back as type 3);
  - the HP driver operators exist and take: booleans for
    HP{Image,Graphics,Text}AdaptiveHalftoning and ColorSmartColorMatching,
    the string (Off) for HPColorTrapping, the string (NoAdj) for the three
    ColorSmart*Adjustment operators.

S6 asks for all of it at once — binary CMYK rendering, no adaptive
halftoning, no trapping, no colour matching, a one-cell threshold — in
front of F's unchanged image data (same fossil id, same payload).  If the
screens vanish, the ablation comes next; if they stay, the engine screens
below the interpreter and PostScript is closed.

Two WITNESS patches in the bottom border (outside the field, inside the
4.2 mm clip): 50 % cyan drawn before the threshold halftone (expected: the
device screen, dotted) and after it (expected: uniform — solid or empty).
They tell "halftone honoured" from "ignored" independently of the field.

Gate: the ghostscript render's field rows are byte-identical to F's.

    env/bin/python experiments/041-m281-screen-routes/make_maxescape.py \
        --src <F gen dir>/page000.ps \
        --out experiments/041-m281-screen-routes/build/S6-maxescape.ps
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SETPAGEDEVICE_OLD = (b"{ << /PageSize [595.20 841.92] /HWResolution [600 600] "
                     b"/Duplex false >> setpagedevice } stopped { } if\n")
SETPAGEDEVICE_NEW = (b"{ << /PageSize [595.20 841.92] /HWResolution [600 600] "
                     b"/Duplex false /ProcessColorModel /DeviceCMYK /PixelDepth 1 "
                     b">> setpagedevice } stopped { } if\n")
HP_OPERATORS = (b"% e041 S6: HP rendering operators off (each guarded; absent under ghostscript)\n"
                b"{ false HPImageAdaptiveHalftoning } stopped { } if\n"
                b"{ false HPGraphicsAdaptiveHalftoning } stopped { } if\n"
                b"{ false HPTextAdaptiveHalftoning } stopped { } if\n"
                b"{ (Off) HPColorTrapping } stopped { } if\n"
                b"{ false ColorSmartColorMatching } stopped { } if\n"
                b"{ (NoAdj) ColorSmartImageAdjustment } stopped { } if\n"
                b"{ (NoAdj) ColorSmartGraphicsAdjustment } stopped { } if\n"
                b"{ (NoAdj) ColorSmartTextAdjustment } stopped { } if\n")
# witness A: 50% cyan, 20-50 mm from the left, 4.6-5.9 mm from the bottom
WITNESS_A = (b"% witness A: 50% cyan under the default halftone\n"
             b"gsave 0.5 0 0 0 setcmykcolor 56.69 13.04 85.04 3.69 rectfill grestore\n")
HALFTONE = (b"% e041 S6: one-cell 50% threshold halftone\n"
            b"<< /HalftoneType 3 /Width 1 /Height 1 /Thresholds <80> >> sethalftone\n")
WITNESS_B = (b"% witness B: 60% cyan under the threshold halftone (above 0x80: uniform solid)\n"
             b"gsave 0.6 0 0 0 setcmykcolor 453.54 13.04 85.04 3.69 rectfill grestore\n")
MARKER = b"gsave /DeviceCMYK setcolorspace\n"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ps = Path(args.src).read_bytes()
    if ps.count(SETPAGEDEVICE_OLD) != 1 or ps.count(MARKER) != 1:
        raise SystemExit("not sheet F's PostScript shape; refusing")
    out = ps.replace(SETPAGEDEVICE_OLD, SETPAGEDEVICE_NEW + HP_OPERATORS)
    out = out.replace(MARKER, WITNESS_A + HALFTONE + WITNESS_B + MARKER)
    Path(args.out).write_bytes(out)
    manifest = {
        "tag": Path(args.out).stem, "source_ps": args.src, "source_sha256": sha(ps),
        "bytes": len(out), "sha256": sha(out), "format_ref": "L:c3-cmy8-p120-v1@2240x1536",
        "image_data_changed": False,
        "prologue": ["setpagedevice ProcessColorModel DeviceCMYK, PixelDepth 1",
                     "false HP{Image,Graphics,Text}AdaptiveHalftoning", "(Off) HPColorTrapping",
                     "false ColorSmartColorMatching", "(NoAdj) ColorSmart{Image,Graphics,Text}Adjustment",
                     "Type 3 1x1 threshold 0x80 sethalftone"],
        "witnesses": {"A": "50% cyan, x 20-50 mm, y 4.6-5.9 mm from the bottom edge, default halftone",
                      "B": "60% cyan, x 160-190 mm, same y, threshold halftone (expected uniform solid)"},
    }
    Path(args.out).with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"{Path(args.out).name}: {len(out)} B sha {manifest['sha256'][:16]}…")


if __name__ == "__main__":
    main()
