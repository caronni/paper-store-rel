"""e041 S7 — sheet F with the job asking for a heavier media profile.

The band on F/S1/S6 (denser M and Y on the dots, cleaner whites, same
gloss, same grain, all planes at one x, plus a density gradient across
the width) reads as a transfer-nip effect, not fusing. The engine's media
profiles change transfer voltage and nip behaviour page-wide, and the
PostScript page device accepts `/MediaType` (query 5: every string reads
back, so the NAME must be one the firmware maps — HP's PPD names
"Heavy" (111–130 g) and "Cardstock" (176–220 g) are used here). One
variable: the media profile. Image data unchanged (same fossil id). The
printer may stop and ask for that stock in the tray; confirm at the panel.

    env/bin/python experiments/041-m281-screen-routes/make_media_variants.py \
        --src <F gen dir>/page000.ps \
        --out experiments/041-m281-screen-routes/build
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

OLD = (b"{ << /PageSize [595.20 841.92] /HWResolution [600 600] "
       b"/Duplex false >> setpagedevice } stopped { } if\n")
VARIANTS = {"S7a-media-heavy": "Heavy", "S7b-media-cardstock": "Cardstock"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ps = Path(args.src).read_bytes()
    if ps.count(OLD) != 1:
        raise SystemExit("not sheet F's PostScript shape; refusing")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    for tag, media in VARIANTS.items():
        new = (b"{ << /PageSize [595.20 841.92] /HWResolution [600 600] /Duplex false "
               b"/MediaType (" + media.encode() + b") >> setpagedevice } stopped { } if\n")
        data = ps.replace(OLD, new)
        (out / f"{tag}.ps").write_bytes(data)
        manifest = {"tag": tag, "media_type": media, "source_sha256": hashlib.sha256(ps).hexdigest(),
                    "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                    "format_ref": "L:c3-cmy8-p120-v1@2240x1536", "image_data_changed": False}
        (out / f"{tag}.manifest.json").write_text(json.dumps(manifest, indent=1))
        print(f"{tag}: {len(data)} B sha {manifest['sha256'][:16]}…  /MediaType ({media})")


if __name__ == "__main__":
    main()
