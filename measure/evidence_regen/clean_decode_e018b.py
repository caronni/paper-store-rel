"""Clean-domain decode of one e018b PostScript page back to its payload bytes.

The e018b payload (a third-party image, withheld from the archive under the
2026-10-09 D1 ruling) is what the page carries; the page is its own carrier.
This reads the published job with no scan and no receiver:

    PS -> K imagemask bits (util/ps_gt) -> cells (cell_dots blocks, uniformity
    checked) -> compose.extract_payload -> per-tile r0550 LDPC decode (exact
    +/-20 LLRs, syndrome + CRC-32 gate) -> fountain.tiles_to_symbols ->
    fountain.volume_decode.

The volume descriptor (data_len_bytes) comes from the manifest, as fountain-v1
does not carry it in-band; k_total, n_symbols_total and symbol_bits are
asserted against the manifest.  A second volume_decode over the repair symbols
alone proves the rank by elimination, not only the systematic shortcut.

    PYTHONPATH=src:. env/bin/python measure/evidence_regen/clean_decode_e018b.py \
        c2 <job>.ps <job>_manifest.json build/lena_std-192.heic

Measured 2026-10-22 on the published pair (docs/evidence-archive/
REGENERATION-2026-10-22.md): c2 1,734/1,734 interior tiles, rank 737/737,
192,160 B, sha == manifest, 28 s; c3 782/782, rank 338/338, 88,157 B, 7 s.
Keep the recovered file out of git (build/ is ignored); `gen_e018b.py emit
<profile> <file>` with the recovered bytes named as the manifest's input_name
re-emits the published job and manifest byte-identically at main.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

TOOL = Path(__file__).resolve().parents[2]
for p in (TOOL / "src", TOOL / "util", TOOL / "experiments" / "018b-payload-sheet"):
    sys.path.insert(0, str(p))

import gen_e018b  # noqa: E402
import ps_gt  # noqa: E402
from paperholo import fountain, ldpc  # noqa: E402
from paperholo.compose import extract_payload, payload_capacity  # noqa: E402

LLR_EXACT: float = 20.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("profile", choices=("c2", "c3"))
    ap.add_argument("ps", type=Path)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("out", type=Path, help="recovered payload bytes (keep out of git)")
    a = ap.parse_args(argv)
    t0 = time.time()
    mf = json.loads(a.manifest.read_text())
    patch = mf["patches"][0]
    spec = gen_e018b.make_spec(a.profile)
    seed = gen_e018b.get_profile(a.profile).seed
    assert mf["format"]["seed"] == seed.decode("ascii")
    cell_dots = spec.cell_dots
    assert cell_dots == patch["params"]["cell_dots"]

    text = a.ps.read_bytes()
    bms = ps_gt.parse_bitmaps(text)
    assert len(bms) == 1 and ps_gt.count_paint_operators(text) == 1
    bm = bms[0]
    assert bm.kind == "mask" and bm.polarity is True, (bm.kind, bm.polarity)
    assert (bm.x_dots, bm.y_dots, bm.w_dots, bm.h_dots) == (
        patch["x_dots"], patch["y_dots"], patch["w_dots"], patch["h_dots"]), bm
    dots = bm.bits().astype(np.uint8)
    h_c, w_c = spec.page_cells_yx
    assert dots.shape == (h_c * cell_dots, w_c * cell_dots), dots.shape
    blocks = dots.reshape(h_c, cell_dots, w_c, cell_dots)
    cells = blocks[:, 0, :, 0]
    nonuniform = int((blocks != cells[:, None, :, None]).any(axis=(1, 3)).sum())
    t_bitmap = time.time() - t0

    t1 = time.time()
    payload_bits = extract_payload(cells, spec, seed, page=0)
    assert payload_bits.size == payload_capacity(spec)
    llr = np.where(payload_bits == 1, LLR_EXACT, -LLR_EXACT).astype(np.float64)
    pci = np.arange(payload_bits.size, dtype=np.int64)
    lspec = ldpc.LDPC_LADDER[gen_e018b.LDPC_RATE_ID]
    results = ldpc.decode_page_tiles(llr, pci, spec, seed, lspec)
    interior = set(fountain.interior_tiles(spec))
    n_int_ok = sum(r.ok for r in results if tuple(r.tile_yx) in interior)
    t_ldpc = time.time() - t1

    t2 = time.time()
    vspec = fountain.VolumeSpec(
        n_pages=1, data_len_bytes=int(mf["volume"]["data_len_bytes"]),
        seed=seed, ldpc_rate_id=gen_e018b.LDPC_RATE_ID, compose_spec=spec)
    assert vspec.k_total == mf["volume"]["k_total"]
    assert vspec.n_symbols_total == mf["volume"]["n_symbols_total"]
    assert vspec.symbol_bits == mf["volume"]["symbol_bits"]
    symbols = fountain.tiles_to_symbols([(0, r) for r in results], vspec)
    data, diag = fountain.volume_decode(symbols, vspec)
    t_fountain = time.time() - t2
    out = {
        "profile": a.profile,
        "bitmap_shape_hw": list(dots.shape),
        "bitmap_unpacked_uint8_sha256": hashlib.sha256(np.ascontiguousarray(dots).tobytes()).hexdigest(),
        "ink_dots": int(dots.sum()),
        "nonuniform_cells": nonuniform,
        "tiles_total": len(results), "tiles_certified_total": sum(r.ok for r in results),
        "interior_tiles": len(interior), "interior_certified": n_int_ok,
        "symbols": len(symbols), "k_total": vspec.k_total,
        "blocks_rank_needed_received_systematic": [
            (d["rank"], d["needed"], d["received"], d["systematic"]) for d in diag["blocks"]],
        "solved_all": diag["solved_all"],
        "times_s": {"bitmap": round(t_bitmap, 2), "ldpc": round(t_ldpc, 2),
                    "fountain": round(t_fountain, 2)},
    }
    if data is not None:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_bytes(data)
        out["recovered_len"] = len(data)
        out["recovered_sha256"] = hashlib.sha256(data).hexdigest()
        out["equals_manifest_data_sha256"] = out["recovered_sha256"] == mf["payload"]["data_sha256"]
    kpb = vspec.k_per_block
    repair = {k: v for k, v in symbols.items() if k[1] >= kpb[k[0]]}
    data_r, diag_r = fountain.volume_decode(repair, vspec)
    out["repair_only_check"] = {"symbols": len(repair), "solved_all": diag_r["solved_all"],
                                "equals_systematic_data": data_r == data}
    print(json.dumps(out, indent=1))
    return 0 if data is not None and out.get("equals_manifest_data_sha256") else 1


if __name__ == "__main__":
    raise SystemExit(main())
