"""e041 S5 — the alphabet sheet: cmy8 rows above and below a band of cmy7 rows.

Sheet F (`L:c3-cmy8-p120-v1@2240x1536`, eight states, the CMY triple
included) and e030's c3-cmy7 page (`L:c3-cmy7-p120-v0@2240x1536`, seven
states, no triple) share the tile matrix (35x24) and the field placement
(origin 148/176 dots), so their rows can be spliced at tile-row boundaries
with every tile at its native address:

  band 0  tile rows  0–11  (dots    0–2303)  F, cmy8
  band 1  tile rows 12–23  (dots 2304–4607)  e030 c3-cmy7
  band 2  tile rows 24–34  (dots 4608–6719)  F, cmy8

One sheet, one engine pass, default halftone, the cmy8 control on both
sides of the cmy7 band. Each band decodes under its own fossil id on the
same capture; the optical instruments run per band with the spliced
ground truth this script also writes (a gen dir `<out>/S5-alphabet-gt/`
in the manifest shape the instruments read).

Gate: the ghostscript render of the spliced page must equal the splice
of the two sources' renders, row for row.

    env/bin/python experiments/041-m281-screen-routes/make_alphabet_sheet.py \
        --cmy8 <F gen dir> \
        --cmy7 <e030 c3-cmy7 gen dir> \
        --out experiments/041-m281-screen-routes/build
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from make_banded_halftone import HEX_PER_ROW, HEIGHT, WIDTH, band_ps, split_source

BANDS = ((0, 2304, "cmy8"), (2304, 4608, "cmy7"), (4608, 6720, "cmy8"))
FOSSIL = {"cmy8": "L:c3-cmy8-p120-v1@2240x1536", "cmy7": "L:c3-cmy7-p120-v0@2240x1536"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load(gen_dir: Path) -> tuple[bytes, str, bytes, np.ndarray, dict]:
    ps = (gen_dir / "page000.ps").read_bytes()
    head, hexdata, tail = split_source(ps)
    manifest = json.loads((gen_dir / "manifest.json").read_text())
    page = manifest["pages"][0]
    packed = np.load(gen_dir / page["gt"])
    if sha(packed.tobytes()) != page["gt_sha256"]:
        raise SystemExit(f"{gen_dir}: GT sha mismatch")
    if packed.shape != (3, HEIGHT, WIDTH // 8):
        raise SystemExit(f"{gen_dir}: unexpected GT shape {packed.shape}")
    return head, hexdata, tail, packed, manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmy8", required=True)
    ap.add_argument("--cmy7", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    src = {"cmy8": load(Path(args.cmy8)), "cmy7": load(Path(args.cmy7))}
    head8, _, tail8, _, _ = src["cmy8"]
    prefix, marker, _ = head8.partition(b"gsave /DeviceCMYK setcolorspace\n")
    ps = prefix + marker
    gt = np.zeros_like(src["cmy8"][3])
    for r0, r1, fam in BANDS:
        hexdata, packed = src[fam][1], src[fam][3]
        ps += band_ps(r0, r1, hexdata[r0 * HEX_PER_ROW:r1 * HEX_PER_ROW],
                      f"% band {fam}: tile rows {r0 // 192}-{(r1 - 1) // 192}, {FOSSIL[fam]}\n".encode())
        gt[:, r0:r1, :] = packed[:, r0:r1, :]
    ps += tail8
    (out / "S5-alphabet.ps").write_bytes(ps)
    gen = out / "S5-alphabet-gt"; gen.mkdir(exist_ok=True)
    np.save(gen / "page000_gt.npy", gt)
    m8 = src["cmy8"][4]
    gen_manifest = {
        "note": "spliced ground truth for e041 S5; NOT a format identity — decode each band under its own fossil id",
        "bands": [{"dot_rows": [r0, r1], "tile_rows": [r0 // 192, (r1 - 1) // 192], "family": fam, "format_ref": FOSSIL[fam]}
                  for r0, r1, fam in BANDS],
        "cell_dots": 3, "page_cells_yx": m8["page_cells_yx"], "tiles_yx": m8["tiles_yx"],
        "pages": [{"page": 0, "gt": "page000_gt.npy", "gt_sha256": sha(gt.tobytes()),
                   "gt_plane_sha256": [sha(np.ascontiguousarray(gt[p]).tobytes()) for p in range(3)],
                   "gt_packed_shape": list(gt.shape), "gt_bitorder": "big",
                   "gt_axis_order": ["plane", "y", "packed_x"], "gt_plane_order": ["C", "M", "Y"]}],
    }
    (gen / "manifest.json").write_text(json.dumps(gen_manifest, indent=1))
    manifest = {
        "tag": "S5-alphabet", "bytes": len(ps), "sha256": sha(ps),
        "sources": {fam: {"dir": d, "ps_sha256": sha((Path(d) / "page000.ps").read_bytes()),
                          "format_ref": FOSSIL[fam]} for fam, d in (("cmy8", args.cmy8), ("cmy7", args.cmy7))},
        "bands": gen_manifest["bands"], "halftone": "default (unchanged)",
        "spliced_gt": str(gen / "page000_gt.npy"), "spliced_gt_sha256": gen_manifest["pages"][0]["gt_sha256"],
    }
    (out / "S5-alphabet.manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"S5-alphabet.ps: {len(ps)} B sha {manifest['sha256'][:16]}…; spliced GT sha {manifest['spliced_gt_sha256'][:16]}…")


if __name__ == "__main__":
    main()
