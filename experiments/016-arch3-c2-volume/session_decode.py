#!/usr/bin/env python
"""Fragment-session decoder (PILOTS-DESIGN §15, end to end): feed glass
images — PNG or TIFF, whole pages or confetti canvases, ANY order — and
the session accumulates until the fountain closes.

Per image: segment (backing-agnostic, §15.2) -> per piece, biggest first:
  1. word path: big pieces = tiny pages. Pieces longer than one safe c2
     window (~26 mm; 014.1: warp accumulation vetoes a 40 mm window at
     29% BER where 25 mm reads 8%) go through formats.page_decode —
     25.4 mm windows tiled over the mask-cropped piece; smaller word-rich
     pieces through a single formats.acquire_scan (ctx+PAVA, unchanged);
  2. fallback for sub-grain / word-less pieces: own pitch + own lattice
     lock + ctx bits -> mask-aware F13 placer against the PENDING set ->
     add_placed_fragment (correlation provenance, F9 backstop).
After each image: LDPC r0550 certify -> fountain rank; at rank >= K the
volume decodes and the data sha must equal the golden 412b9256... .

State: build/session_state.pkl accumulates across invocations (--fresh
resets). Certified tiles are never demoted.

Usage:
  env/bin/python session_decode.py <img> [<img> ...]
      [--dpi 2400] [--fresh] [--state PATH] [--policy P]
      [--emit-erode-cells N]
"""
from __future__ import annotations

import argparse
import hashlib
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.joinpath("experiments/016-arch3-c2-volume")))

from PIL import Image                                    # noqa: E402
import tifffile                                          # noqa: E402

from paperholo import (acquire, compose, formats, fountain, place,  # noqa
                       scannorm, segment, tilemap)
from paperholo.modulation import keystream               # noqa: E402
import gen_e016                                          # noqa: E402

Image.MAX_IMAGE_PIXELS = None
SEED = gen_e016.SEED
FMT = next(f for f in formats.FORMAT_REGISTRY if f.format_id == "e016-v3-c2")
spec = FMT.spec()
# ^ decode-identical to gen_e016.make_spec() — only the emit-side page
# margins (x_dots/y_dots) differ, and payload_index_map + composed cell
# fields verify byte-equal under both; page_decode's state check compares
# against FMT.spec(), so the session state must live in that family.
CD = int(spec.cell_dots)
GOLDEN_SHA = "412b9256829ece06243f16ab0456e4a817b1459d64625f28dd09eae26059bb90"
STATE = ROOT / "experiments/016-arch3-c2-volume/build/session_state.pkl"
WORD_PATH_MIN_MM2 = 140.0     # >= ~12 mm square: try self-addressing first
TILE_PATH_MIN_MM = 26.0       # longer than one safe c2 window: tile windows
WINDOW_CELLS = 300            # 25.4 mm at c2 (014.1 measured-safe size)
OVERLAP_CELLS = 60
# id crop is RAW pixels in page_decode — derive from the runtime dpi in
# main() (a hardcoded 8 px/cell would make the crop 50.8 mm at --dpi 1200,
# past the 014.1 c2 warp-veto regime; review finding)


def load_img(path: Path) -> np.ndarray:
    if path.suffix.lower() in (".tif", ".tiff"):
        return tifffile.TiffFile(str(path)).pages[0].asarray(out="memmap")
    return np.asarray(Image.open(path).convert("L"))


def refine_piece(p: segment.Piece, backing: float, pl_e, spec_, pend,
                 dpi: float, erode_cells: int):
    """The measured P2 chain (2026-07-11 detector A/B, white fixture):
    core-mask placement gives the admission (+47% vs grown mask), then
    pilot-supervised (angle, continuous-phase) refinement + per-piece
    Gaussian recal give the quality (core BER 0.128 -> 0.109 median).
    Anchored on a fresh rot-free lock of the UNROTATED glass crop; every
    step re-validates through the placer gate — any failure falls back
    to the initial observation (returns None)."""
    if p.img_glass is None or p.mask_glass is None:
        return None
    glass, gm = p.img_glass, p.mask_glass
    try:
        pitch = float(scannorm.measure_cell_pitch(p.img).pitch_px)
    except Exception:
        pitch = dpi / 600.0 * CD
    im = np.where(gm, glass, np.float32(backing))
    mid = float(np.median(im[gm])) if gm.any() else 128.0
    M, off, oshape = segment.rotate_transform(im.shape, p.angle_deg)
    ph = segment.phase_scan_glass(im, gm.astype(np.float32), mid, backing,
                                  M, off, oshape, pitch)
    if ph is None:
        return None
    _, dy0, dx0 = ph
    got = segment.sample_cells_at(glass, gm, backing, p.angle_deg, pitch,
                                  dy0, dx0)
    if got is None:
        return None
    means, kmask, mid_f = got
    bits_f = (means < mid_f).astype(np.uint8)
    core_f = _core(kmask, erode_cells)
    pl_f = place.place_fragment(bits_f, spec_, SEED, mask=core_f,
                                pending_cell_mask=pend,
                                gate_true=0.20, gate_decoy=0.20)
    if not (pl_f.ok and (pl_f.rival_mismatch - pl_f.mismatch) >= 0.08
            and pl_f.page == pl_e.page):
        return None
    sij, sv = place.fragment_pilot_sites(pl_f, bits_f.shape, core_f,
                                         spec_, SEED)
    if sij.shape[0] < 60:
        return None
    ang, dyf, dxf, meta = segment.refine_on_sites(
        glass, gm, backing, p.angle_deg, pitch, dy0, dx0, sij, sv)
    got_r = segment.sample_cells_at(glass, gm, backing, ang, pitch,
                                    dyf, dxf, ref_angle_deg=p.angle_deg)
    if got_r is None:
        return None
    means_r, kmask_r, mid_r = got_r
    bits_r = (means_r < mid_r).astype(np.uint8)
    core_r = _core(kmask_r, erode_cells)
    pl_r = place.place_fragment(bits_r, spec_, SEED, mask=core_r,
                                pending_cell_mask=pend,
                                gate_true=0.20, gate_decoy=0.20)
    if not (pl_r.ok and (pl_r.rival_mismatch - pl_r.mismatch) >= 0.08):
        return None
    sij_r, sv_r = place.fragment_pilot_sites(pl_r, bits_r.shape, core_r,
                                             spec_, SEED)
    sel = np.zeros(bits_r.shape, bool)
    sel[sij_r[:, 0], sij_r[:, 1]] = True
    llr_r = segment.recal_llrs_from_labels(means_r, sel, sv_r)
    if llr_r is None:       # too few labels: spread LLRs on refined means
        spread = float(np.abs(means_r[kmask_r] - mid_r).mean()) or 1.0
        llr_r = np.clip((mid_r - means_r) / max(spread, 1e-6),
                        -8.0, 8.0) * 2.0
    return bits_r, kmask_r, llr_r, pl_r, meta


def _core(mask: np.ndarray, erode_cells: int) -> np.ndarray:
    if erode_cells <= 0:
        return mask
    e = ndimage.binary_erosion(mask, iterations=erode_cells)
    return e if e.any() else mask


def piece_bits(piece: segment.Piece, dpi: float
               ) -> tuple[np.ndarray, np.ndarray] | None:
    """Sub-grain path: own pitch + own lock + ctx bits + cell mask."""
    try:
        pit = scannorm.measure_cell_pitch(piece.img)
        norm = scannorm.normalize_to_canonical(piece.img, pit.pitch_px, CD)
        mscaled = piece.mask
        if norm.img.shape != piece.mask.shape:  # canonical resample moved px
            zy = norm.img.shape[0] / piece.mask.shape[0]
            zx = norm.img.shape[1] / piece.mask.shape[1]
            yy = (np.arange(norm.img.shape[0]) / zy).astype(int)
            xx = (np.arange(norm.img.shape[1]) / zx).astype(int)
            mscaled = piece.mask[np.clip(yy, 0, piece.mask.shape[0] - 1)][
                :, np.clip(xx, 0, piece.mask.shape[1] - 1)]
        # phase-searched block lock (segment.piece_cell_bits): lock_grid's
        # windowed profiles mislock on backing-embedded sub-grain pieces
        # (measured 2026-07-10; the session-yield diagnosis)
        hard, mcell, llr = segment.piece_cell_bits(
            norm.img, mscaled, int(round(norm.cell_px_est)))
        if hard.size == 0:
            return None
        return hard, mcell, llr
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--dpi", type=float, default=2400.0)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--state", type=Path, default=STATE)
    ap.add_argument("--policy", default="weighted_sum",
                    choices=tilemap.PageDecodeState._POLICIES,
                    help="tile merge policy. Default weighted_sum (union): "
                         "pieces are spatially disjoint (each cell scanned "
                         "once), so the measured multi-scan sum-negative "
                         "(012.3/013/014.2, same cells re-observed) does "
                         "not apply, and the 2026-07-11 review's carve-sim "
                         "measured best_per_tile geometrically unable to "
                         "close a confetti session (single-piece >=0.70-"
                         "coverage ceiling 1027 tiles < K=1387 on the "
                         "stress fixture; union ceiling 1477); measured "
                         "A/B same fixture: union 693 vs best 653 symbols. "
                         "best_per_tile remains the right choice for "
                         "whole-page multi-SCAN states.")
    ap.add_argument("--piece-chain", default="refine",
                    choices=["median", "refine"],
                    help="placer-path detector: 'median' = the 016.4 "
                         "baseline (piece_cell_bits, spread LLRs); "
                         "'refine' adds the measured P2 chain after a "
                         "gate-passing placement — pilot-supervised "
                         "(angle, sub-cell phase) refinement + per-piece "
                         "Gaussian recal (core BER 0.128->0.109, "
                         "held-out mismatch 0.091->0.073, white fixture "
                         "2026-07-11)")
    ap.add_argument("--emit-erode-cells", type=int, default=4,
                    help="erode the piece mask by N cells for LLR EMISSION "
                         "only (placement keeps the full grown mask). The "
                         "grow-out ring samples backing — on a white lid "
                         "it reads as confidently-paper garbage, and since "
                         "carved pieces are page-adjacent, a piece's ring "
                         "lands INSIDE its neighbors' cells: union-poison "
                         "for exactly the boundary tiles that need the "
                         "union. Grow-out is a segmentation/placement "
                         "doctrine (never under-include), not an emission "
                         "one.")
    args = ap.parse_args()

    args.state.parent.mkdir(parents=True, exist_ok=True)
    if args.state.exists() and not args.fresh:
        pds, done = pickle.loads(args.state.read_bytes())
        if pds.spec != spec and tuple(pds.spec.page_cells_yx) == tuple(
                spec.page_cells_yx) and pds.seed == SEED:
            # pre-2026-07-11 states carry gen_e016.make_spec() (emit
            # margins 260/208 vs the registry's 230/178 — measured decode-
            # identical); migrate so page_decode's state gate passes
            # instead of aborting mid-image on the first tiled piece
            pds.spec = spec
    else:
        pds, done = tilemap.PageDecodeState(spec, SEED, page=0), set()
    pim = compose.payload_index_map(spec, SEED)
    ks = keystream(SEED, "CMYK".index(spec.plane), 0,
                   tuple(spec.page_cells_yx))
    cell_px = args.dpi / 600.0 * CD
    id_window_px = int(round(WINDOW_CELLS * cell_px))   # 25.4 mm at any dpi

    for img_path in args.images:
        if img_path.name in done:
            print(f"{img_path.name}: already folded — skip", flush=True)
            continue
        img = load_img(img_path)
        imgf = np.asarray(img, np.float32)
        pieces = segment.segment_pieces(imgf, cell_px=cell_px, dpi=args.dpi)
        backing = segment.estimate_backing(imgf)
        print(f"{img_path.name}: {len(pieces)} pieces", flush=True)
        n_word = n_tiled = n_placed = n_refined = n_fail = 0
        pend = None
        for i, p in enumerate(pieces):
            sid = f"{img_path.name}/p{i}"
            if p.area_mm2 >= WORD_PATH_MIN_MM2:
                yy = np.flatnonzero(p.mask.any(axis=1))
                xx = np.flatnonzero(p.mask.any(axis=0))
                long_mm = max(yy[-1] - yy[0], xx[-1] - xx[0]) / (
                    args.dpi / 25.4)
                if long_mm >= TILE_PATH_MIN_MM:
                    # window-tiled word path: the mask-cropped piece IS the
                    # field, so plain image-anchored tiling covers it
                    # (backing-agnostic; align_to_field's darkness bbox
                    # assumes a white margin). A failed tiled piece falls
                    # to the placer, never to a >26 mm single window.
                    crop = np.ascontiguousarray(
                        p.img[yy[0]:yy[-1] + 1, xx[0]:xx[-1] + 1])
                    ident, _ = formats.page_decode(
                        crop, scan_id=sid, state=pds, candidates=[FMT],
                        scan_dpi=args.dpi, window_cells=WINDOW_CELLS,
                        overlap_cells=OVERLAP_CELLS,
                        id_window_px=id_window_px,
                        detector="ctx", calibrate=True)
                    if ident.ok and sid in pds.scans:
                        n_tiled += 1
                        continue
                else:
                    r = formats.acquire_scan(p.img, scan_dpi=args.dpi,
                                             detector="ctx", calibrate=True)
                    if r.ok:
                        pds.add_acquire_result(sid, r.result)
                        n_word += 1
                        continue
            got = piece_bits(p, args.dpi)
            if got is None:
                n_fail += 1
                continue
            bits, mcell, cllr = got
            if pend is None:      # pending prune, refreshed per image
                pm = np.zeros(tuple(spec.page_cells_yx), bool)
                for (ty, tx) in pds.pending_tiles():
                    pm[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64] = True
                if not pm.any():
                    pm[:] = True     # nothing decoded yet: whole page
                pend = {0: pm}
            # gap-based gate for the real-toner piece regime (validated
            # 2026-07-10: rotated real pieces run ~13-14% BER — the frozen
            # clean-regime constants 0.15/0.20 reject them, while the
            # 014.4 decoy floor (>=0.257 measured; ~0.33 at this BER)
            # leaves a >=0.08 gap; A/B: 12/42 admitted, 0 false).
            # Placement mask = CORE (grown mask minus the backing rim):
            # measured +47% admissions at 0 false on the white fixture
            # (2026-07-11 detector A/B, arm E).
            pl = place.place_fragment(bits, spec, SEED,
                                      mask=_core(mcell,
                                                 args.emit_erode_cells),
                                      pending_cell_mask=pend,
                                      gate_true=0.20, gate_decoy=0.20)
            if not pl.ok or (pl.rival_mismatch - pl.mismatch) < 0.08:
                n_fail += 1
                continue
            if args.piece_chain == "refine":
                ref = refine_piece(p, backing, pl, spec, pend, args.dpi,
                                   args.emit_erode_cells)
                if ref is not None:
                    bits, mcell, cllr, pl, _rmeta = ref
                    n_refined += 1
            oy, ox = pl.origin_yx
            bk = np.rot90(bits, pl.rot_k)
            mk = np.rot90(mcell, pl.rot_k)
            if args.emit_erode_cells > 0:
                mk_e = ndimage.binary_erosion(
                    mk, iterations=args.emit_erode_cells)
                if mk_e.any():          # tiny piece: full mask beats nothing
                    mk = mk_e
            H, W = spec.page_cells_yx
            hh = min(bk.shape[0], H - oy)
            ww = min(bk.shape[1], W - ox)
            sel = np.zeros((hh, ww), bool)
            sel[mk[:hh, :ww]] = True
            idx = pim[oy:oy + hh, ox:ox + ww]
            sel &= idx >= 0
            kk = ks[oy:oy + hh, ox:ox + ww]
            lk = np.rot90(cllr, pl.rot_k)[:hh, :ww]
            llr = lk * (1.0 - 2.0 * kk)       # ctx LLRs, descrambled sign
            pds.add_placed_fragment(
                sid, idx[sel].astype(np.int64), llr[sel],
                placement_meta={"mismatch": pl.mismatch,
                                "z_gap": pl.z_gap,
                                "angle_deg": p.angle_deg})
            n_placed += 1
        done.add(img_path.name)
        counts = pds.decode_tiles("r0550", policy=args.policy)
        vspec = gen_e016.make_vspec()
        syms = fountain.tiles_to_symbols(pds.certified_results(), vspec)
        data_out, diag = fountain.volume_decode(syms, vspec)
        print(f"  word-path {n_word} (+{n_tiled} tiled), placed {n_placed} "
              f"({n_refined} refined), failed {n_fail} | decode_tiles "
              f"{counts} | fountain symbols "
              f"{diag['n_symbols_received']}", flush=True)
        args.state.write_bytes(pickle.dumps((pds, done)))
        if data_out is not None:
            sha = hashlib.sha256(data_out).hexdigest()
            print(f"  VOLUME DECODED: {len(data_out)} bytes, sha "
                  f"{sha[:16]}… "
                  f"{'== GOLDEN, BYTE-EXACT' if sha == GOLDEN_SHA else '*** MISMATCH ***'}",
                  flush=True)
            return 0
        wanted = tilemap.volume_scans_wanted({0: pds}, vspec)
        print(f"  volume_scans_wanted: {wanted}", flush=True)
    print("session open — feed more images (fountain rank not reached)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
