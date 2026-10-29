"""e041 S8 — sheet F's page turned 180 degrees ON the page: same dots, content turned.

On every F print the M281's rendering band sits at one paper x, 108–113 mm
from the left edge = tile column 12 of 24. F's field (4608 x 6720 dots) is
centred on the 4960 x 7016-dot page to the dot (176 dots left and right,
148 bottom and top), so turning the page content about the page centre
lands the field on EXACTLY F's device pixels: the toner footprint is
unchanged, only the content is turned. One variable: content orientation.
If the band is the engine's it falls under tile column 11 of the turned
content; if the content drives it, it stays at column 12. Image data
unchanged (same fossil id); the receiver reads the turned page as any
rotated capture.

One line is spliced in after `gsave /DeviceCMYK setcolorspace`:
`595.200000 841.920000 translate 180 rotate` = (x, y) -> (W - x, H - y).
`--verify` renders F and S8 through ghostscript (bitcmyk, 600 dpi, whole
page) and requires K empty on both, each C/M/Y plane of S8 == F's turned
by 180 degrees to the dot, the same ink footprint, and per-plane ink
counts equal to F's ground truth.

    PYTHONPATH=src:. env/bin/python experiments/041-m281-screen-routes/make_rotated_sheet.py \
        --src <F gen dir>/page000.ps \
        --out experiments/041-m281-screen-routes/build --verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np

TAG = "S8-rot180"
DEVICE = (b"{ << /PageSize [595.20 841.92] /HWResolution [600 600] "
          b"/Duplex false >> setpagedevice } stopped { } if\n")
MARKER = b"gsave /DeviceCMYK setcolorspace\n"
TURN = b"595.200000 841.920000 translate 180 rotate\n"
PAGE_DOTS_XY = (4960, 7016)
GT_INK_CMY = (15_499_179, 15_490_098, 15_123_663)  # unpacked page000_gt.npy of sheet F
BAND_COLUMN = {"paper_fixed": 11, "content_fixed": 12}
GS = ["gs", "-q", "-dBATCH", "-dNOPAUSE", "-dSAFER", "-r600", "-sDEVICE=bitcmyk",
      f"-g{PAGE_DOTS_XY[0]}x{PAGE_DOTS_XY[1]}"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def turn(ps: bytes) -> bytes:
    if ps.count(DEVICE) != 1 or ps.count(MARKER) != 1:
        raise SystemExit("not sheet F's PostScript shape; refusing")
    return ps.replace(MARKER, MARKER + TURN)


def render(ps_path: Path, work_dir: Path) -> tuple[str, np.ndarray]:
    """gs bitcmyk render -> (raster sha256, planes [4, rows, cols] uint8 in C M Y K order)."""
    out = work_dir / (ps_path.stem + ".bitcmyk")
    subprocess.run(GS + [f"-sOutputFile={out}", str(ps_path)], check=True, capture_output=True)
    raw = out.read_bytes()
    w, h = PAGE_DOTS_XY
    if len(raw) != w * h // 2:
        raise SystemExit(f"{ps_path}: render is {len(raw)} B, not {w}x{h} at 4 bits/dot")
    bits = np.unpackbits(np.frombuffer(raw, np.uint8).reshape(h, w // 2), axis=1).reshape(h, w, 4)
    return sha(raw), np.moveaxis(bits, 2, 0)


def footprint(planes: np.ndarray) -> list[int]:
    """[first row, last row, first col, last col] with any ink, rows from the page top."""
    rows, cols = np.flatnonzero(planes.any(axis=(0, 2))), np.flatnonzero(planes.any(axis=(0, 1)))
    return [int(rows[0]), int(rows[-1]), int(cols[0]), int(cols[-1])]


def verify(src: Path, job: Path) -> dict:
    with tempfile.TemporaryDirectory(dir=job.parent) as t:
        f_sha, f = render(src, Path(t))
        s_sha, s = render(job, Path(t))
    names = "CMYK"
    diff = {names[i]: int((s[i] != np.rot90(f[i], 2)).sum()) for i in range(3)}
    ink_f = {names[i]: int(f[i].sum()) for i in range(4)}
    ink_s = {names[i]: int(s[i].sum()) for i in range(4)}
    fp_f, fp_s = footprint(f), footprint(s)
    checks = {
        "K_empty_both": ink_f["K"] == 0 and ink_s["K"] == 0,
        "planes_equal_rot180": all(v == 0 for v in diff.values()),
        "footprint_identical": fp_f == fp_s,
        "ink_F_equals_gt": tuple(ink_f[c] for c in "CMY") == GT_INK_CMY,
        "ink_S8_equals_gt": tuple(ink_s[c] for c in "CMY") == GT_INK_CMY,
    }
    return {"command": " ".join(GS), "F_render_sha256": f_sha, "S8_render_sha256": s_sha,
            "diff_dots_vs_rot180_F": diff, "ink_F": ink_f, "ink_S8": ink_s,
            "gt_ink_CMY": list(GT_INK_CMY), "footprint_rows_cols_F": fp_f,
            "footprint_rows_cols_S8": fp_s, "checks": checks, "passed": all(checks.values())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify", action="store_true", help="render F and S8 with gs and compare")
    args = ap.parse_args()
    src = Path(args.src)
    ps = src.read_bytes()
    data = turn(ps)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    job = out / f"{TAG}.ps"
    job.write_bytes(data)
    manifest: dict = {"tag": TAG, "source_ps": str(src), "source_sha256": sha(ps), "bytes": len(data),
                      "sha256": sha(data), "format_ref": "L:c3-cmy8-p120-v1@2240x1536",
                      "image_data_changed": False, "rotation_deg": 180,
                      "inserted_line": TURN.decode().rstrip("\n"),
                      "expected_band_tile_column": BAND_COLUMN}
    if args.verify:
        manifest["gs_check"] = verify(src, job)
    (out / f"{TAG}.manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"{TAG}: {len(data)} B sha {manifest['sha256'][:16]}…")
    if args.verify:
        print(json.dumps(manifest["gs_check"], indent=1))
        if not manifest["gs_check"]["passed"]:
            raise SystemExit("verify FAILED")


if __name__ == "__main__":
    main()
