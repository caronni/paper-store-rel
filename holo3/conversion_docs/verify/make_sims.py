# Emit the two acceptance-step-1 sim captures at 1200 dpi (2 px/dot),
# using MAIN-worktree src/holo as the data producer (format authority).
# Run: cd <repo> && PYTHONPATH=src env/bin/python \
#        <checkout>/_distill/verify/sim/make_sims.py
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage

OUT = "<checkout>/_distill/verify/sim"


def det_bytes(tag: bytes, n: int) -> bytes:
    out = b""
    c = tag
    while len(out) < n:
        c = hashlib.sha256(c).digest()
        out += c
    return out[:n]


def make_k() -> dict:
    from holo.format.resolve import resolve_format_ref
    from holo.gen.plan import plan_volume
    from holo.gen.emit import METADATA_VERSION, source_packed_for
    from holo.gen.compose import compose_page_cells, cells_to_dots
    from holo.core import fountain

    spec = resolve_format_ref("c3-k-r0550@7x7")
    payload = det_bytes(b"holo3-sim-k", 6000)
    plan = plan_volume(spec, len(payload), 0.5)
    source = source_packed_for(payload, plan)
    code = fountain.VolumeCode(plan.k_total, plan.symbol_bits, spec.seed,
                               tiles_per_page=spec.tiles_per_page)
    esis = np.arange(spec.tiles_per_page, dtype=np.int64)
    cells = compose_page_cells(spec, 0, code.encode_symbols(source, esis),
                               plan.k_total, version=METADATA_VERSION)
    dots = cells_to_dots(cells, spec.cell_dots)
    b = 96
    h, w = dots.shape
    canvas = np.full((h + 2 * b, w + 2 * b), 245, np.uint8)
    canvas[b:b + h, b:b + w] = np.where(dots != 0, 35, 245)
    up = np.repeat(np.repeat(canvas, 2, axis=0), 2, axis=1)
    blurred = ndimage.gaussian_filter(up.astype(np.float32), 1.0)
    img = np.round(np.clip(blurred, 0, 255)).astype(np.uint8)
    tifffile.imwrite(f"{OUT}/sim-k-1200dpi.tiff", img)
    open(f"{OUT}/sim-k-payload.bin", "wb").write(payload)
    return {
        "format": "c3-k-r0550@7x7", "dpi": 1200,
        "tiff": "sim-k-1200dpi.tiff",
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }


def make_color() -> dict:
    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import emit_volume
    from holo.qualification.color_synthetic import render_color_scan

    spec = resolve_format_ref("c3-cmy8-r0550x0550x0547@10x10")
    payload = det_bytes(b"holo3-sim-color", 20000)
    outdir = f"{OUT}/color-emit"
    if os.path.isdir(outdir):
        import shutil
        shutil.rmtree(outdir)
    emit_volume(spec, payload, 0.35, Path(outdir))
    gt = np.load(f"{outdir}/page000_gt.npy")
    planes = np.unpackbits(gt, axis=-1)
    field_h = planes.shape[1]
    field_w_bits = planes.shape[2]
    dots_h = spec.layout.cells_yx[0] * spec.cell_dots
    dots_w = spec.layout.cells_yx[1] * spec.cell_dots
    coverage = planes[:, :dots_h, :dots_w].astype(np.float64)
    b = 60
    padded = np.zeros((3, dots_h + 2 * b, dots_w + 2 * b), np.float64)
    padded[:, b:b + dots_h, b:b + dots_w] = coverage
    up = np.repeat(np.repeat(padded, 2, axis=1), 2, axis=2)
    rgb = render_color_scan(np.ascontiguousarray(up.transpose(1, 2, 0))).rgb
    img = np.round(np.clip(rgb * 255.0, 0, 255)).astype(np.uint8)
    tifffile.imwrite(f"{OUT}/sim-color-1200dpi.tiff", img)
    open(f"{OUT}/sim-color-payload.bin", "wb").write(payload)
    return {
        "format": "c3-cmy8-r0550x0550x0547@10x10", "dpi": 1200,
        "tiff": "sim-color-1200dpi.tiff",
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "field_shape": [int(field_h), int(field_w_bits)],
    }


def main() -> None:
    manifest = {"k": make_k(), "color": make_color()}
    with open(f"{OUT}/sims.json", "w") as f:
        json.dump(manifest, f, indent=1)
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
