"""e041 — the PostScript-side rungs of the M281 screen-defeat ladder.

Same bits as sheet F (`L:c3-cmy8-p120-v1@2240x1536`), one variable each:

  S1  the original PostScript wrapped in PJL that asks the RIP for its
      1-bit render path: @PJL SET BITSPERPIXEL=1 (the M281's PJL INFO
      VARIABLES lists BITSPERPIXEL=8 [1,2,4,8]; 8 is the multi-level
      ImageREt pipeline that renders the composite contone and screens
      it) plus RET=OFF.
  S2  the original PostScript with one prologue line after setpagedevice:
      a Type 3 halftone whose threshold array is a single 50 % cell, so
      if the RIP screens the composite through the graphics-state
      halftone, 100 %/0 % cells come out solid/white.
  S2b the Type 1 form of the same idea (600 lpi, angle 0, identity spot
      function) — a candidate, printed only if S2 is ignored.

Nothing here changes the image data: every variant decodes under the
same fossil id and payload sha.  Deterministic; writes <out>/<tag>.ps and
<out>/<tag>.manifest.json.

    env/bin/python experiments/041-m281-screen-routes/make_ps_variants.py \
        --src <F gen dir>/page000.ps \
        --out experiments/041-m281-screen-routes/build
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

UEL = b"\x1b%-12345X"
SETPAGEDEVICE_LINE = (b"{ << /PageSize [595.20 841.92] /HWResolution [600 600] "
                      b"/Duplex false >> setpagedevice } stopped { } if\n")

HALFTONE_TYPE3 = (b"% e041 S2: one-cell 50% threshold halftone -> binary rendering\n"
                  b"<< /HalftoneType 3 /Width 1 /Height 1 /Thresholds <80> >> "
                  b"sethalftone\n")
HALFTONE_TYPE1 = (b"% e041 S2b: 600 lpi angle 0 identity spot -> one dot per cell\n"
                  b"<< /HalftoneType 1 /Frequency 600 /Angle 0 "
                  b"/SpotFunction { pop } >> sethalftone\n")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def pjl_wrapped(ps: bytes, job: str, settings: tuple[str, ...]) -> bytes:
    head = UEL + b"@PJL JOB NAME=\"" + job.encode() + b"\"\r\n"
    for s in settings:
        head += b"@PJL SET " + s.encode() + b"\r\n"
    head += b"@PJL ENTER LANGUAGE=POSTSCRIPT\r\n"
    return head + ps + b"\r\n" + UEL + b"@PJL EOJ\r\n" + UEL


def with_prologue(ps: bytes, line: bytes) -> bytes:
    if ps.count(SETPAGEDEVICE_LINE) != 1:
        raise SystemExit("setpagedevice line not found exactly once; refusing")
    return ps.replace(SETPAGEDEVICE_LINE, SETPAGEDEVICE_LINE + line)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    src = Path(args.src)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ps = src.read_bytes()
    variants = {
        "S1-pjl-bpp1": (pjl_wrapped(ps, "E041-S1-BPP1", ("BITSPERPIXEL=1", "RET=OFF")),
                        "PJL SET BITSPERPIXEL=1 + RET=OFF around the unchanged PostScript"),
        "S2-sethalftone-type3": (with_prologue(ps, HALFTONE_TYPE3),
                                 "Type 3 halftone, 1x1 threshold 0x80, after setpagedevice"),
        "S2b-sethalftone-type1": (with_prologue(ps, HALFTONE_TYPE1),
                                  "Type 1 halftone, 600 lpi, angle 0, identity spot function"),
    }
    for tag, (data, what) in variants.items():
        path = out / f"{tag}.ps"
        path.write_bytes(data)
        manifest = {
            "tag": tag, "what": what, "source_ps": str(src), "source_sha256": sha(ps),
            "bytes": len(data), "sha256": sha(data),
            "format_ref": "L:c3-cmy8-p120-v1@2240x1536",
            "image_data_changed": False,
        }
        (out / f"{tag}.manifest.json").write_text(json.dumps(manifest, indent=1))
        print(f"{tag}: {len(data)} B sha {manifest['sha256'][:16]}…  {what}")


if __name__ == "__main__":
    main()
