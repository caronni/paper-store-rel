#!/usr/bin/env python
"""e018 fragment-session decoder (PILOTS-DESIGN §15) — the c3 sibling of
experiments/016-arch3-c2-volume/session_decode.py: feed glass images — PNG
or TIFF, whole pages or confetti canvases, ANY order — and the session
accumulates until the fountain closes on the e018 play volume.

SOURCE-INDEPENDENT by design (the 018 log's decode-handoff rule): the
volume spec is reconstructed from frozen constants below, never by
re-tarring the live source (gen_e018.make_vspec() would drift with any
CORE edit). When build/e018_manifest.json is present it is cross-checked.

Per image: segment (backing-agnostic, §15.2) -> per piece, biggest first:
  1. word path: big pieces = tiny pages. Pieces longer than one safe
     window (~26 mm) go through formats.page_decode — 25.4 mm windows
     (200 cells at c3) tiled over the mask-cropped piece; smaller
     word-rich pieces through a single formats.acquire_scan (ctx+PAVA).
     c3 word grain: 15.1 mm placement-guaranteed / 13 mm ~60% (011.0;
     "13 mm+ fragments acquire" on hardware, 012.3) — the routing
     threshold sits just above it; a failed word path falls to the
     placer, never errors out.
  2. fallback for sub-grain / word-less pieces: own pitch + own lattice
     lock + ctx bits -> mask-aware F13 placer against the PENDING set ->
     add_placed_fragment (correlation provenance, F9 backstop). Placer
     gates ride the v3 window code's distance-spectrum decoy floor
     (014.4: min 32/100 — code algebra, format-independent), so the
     e016-measured constants carry; c3 pilot sites are (3/2)^2 sparser
     per mm^2, so expect the placer grain ~9 mm (unmeasured), not c2's 6.
After each image: LDPC r0550 certify -> fountain rank; at rank >= K=396
the volume decodes, the data sha must equal 4c75fe59..., and the bytes
are written to build/recovered_e018.tar.gz (`tar xzf` -> paperholo/*.py).

State: build/session_state.pkl accumulates across invocations (--fresh
resets). Certified tiles are never demoted.

Footing: scan Canon 4800 grey (white lid), then decimate 3x -> 1600 dpi
= 8 px/cell, the measured-best c3 footing (012.3 / acquire-v2: the
8 px/cell canonical beat 6; 016.2-style declared-equivalent decimation).
--dpi is REQUIRED and must be the TRUE dpi of the image you feed.

Usage:
  env/bin/python session_decode.py <img> [<img> ...] --dpi 1600
      [--fresh] [--state PATH] [--policy P] [--piece-chain C]
      [--emit-erode-cells N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image                                    # noqa: E402
import tifffile                                          # noqa: E402

from paperholo import (compose, formats, fountain, place,  # noqa: E402
                       scannorm, segment, tilemap)
from paperholo.modulation import keystream               # noqa: E402

Image.MAX_IMAGE_PIXELS = None

# ---- frozen e018 constants (018 log "Decode handoff"; run 018.0) ----
SEED = b"paper-store/exp018-confetti-c3"
DATA_LEN_BYTES = 103195
GOLDEN_SHA = "4c75fe59241499a827293a1c6b9261a306a3936678d46ec78843feea1d17c44d"
LDPC_RATE = "r0550"
# local descriptor, NOT registered: same frozen e012 v3-c3 page geometry
# (verified spec-equal to gen_e018.make_spec() AND to the e012 registry
# row), e018 seed. Passed as candidates=[FMT] to every formats call.
FMT = formats.FormatDescriptor(
    "e018-v3-c3", SEED, 3, "kcell-c3", (2220, 1500),
    notes="CONFETTI-C3-PLAY coded volume (fountain-v1 K/N 0.506 + LDPC "
          "r0550; printed sheet, session-local descriptor)")
spec = FMT.spec()
CD = int(spec.cell_dots)                                 # == 3
VSPEC = fountain.VolumeSpec(n_pages=1, data_len_bytes=DATA_LEN_BYTES,
                            seed=SEED, ldpc_rate_id=LDPC_RATE,
                            compose_spec=spec)
assert (VSPEC.k_total, VSPEC.n_symbols_total) == (396, 782), (
    "vspec drifted from the 018.0 build "
    f"({VSPEC.k_total}/{VSPEC.n_symbols_total} != 396/782)")

STATE = ROOT / "experiments/018-confetti-c3-play/build/session_state.pkl"
RECOVERED = ROOT / "experiments/018-confetti-c3-play/build/recovered_e018.tar.gz"
MISMATCH_OUT = RECOVERED.with_name("recovered_e018.MISMATCH.bin")
WORD_PATH_MIN_MM2 = 230.0     # >= ~15.2 mm square: try self-addressing
#                               first. Sits AT the 011.0 15.1 mm
#                               placement-guaranteed grain, +17% linear
#                               over the 012.3 "13 mm+ acquires" hardware
#                               fact (the e016 margin ratio anchored to
#                               ITS guarantee grain would give ~320).
#                               Routing-only: a failed word path falls
#                               through to the placer.
# ---- §15.6 anchor-chain constants (018.2 forensics, measured) ----
SPLIT_CELLS = 260             # placer pieces longer than ~33 mm split
#                               into windows: the rigid one-(angle,phase)
#                               model floors above the gate past ~25 mm
#                               (p5: 47 mm rigid 0.248 vs quadrant
#                               0.043-0.101)
WIN_CELLS_PLACER = 200        # ~25 mm placement windows (~975 pilot
#                               sites each at the 2.44% density)
MIN_WIN_CORE_CELLS = 8000     # ~195 sites — below this a window is
#                               support-starved (016.7: decoy gate goes
#                               marginal near ~150 sites)
SPLIT_CORE_CELLS = 52000      # ...AND carrying enough toner to feed
#                               windows: a rotated piece inflates its
#                               bbox past SPLIT_CELLS while its core
#                               stays small (measured in-build: a 160-
#                               cell square at 31 deg = 308-cell bbox,
#                               25k core -> 4 starved windows, all
#                               skipped). p5's core was 88.6k.
ANGLE_SWEEP_DEG = (0.25, 0.5, 0.75)   # gate-passing bands measured
#                               0.5-0.75 deg wide on both forensic pieces
CONSISTENCY_CELLS = 2         # window-implied piece origins must agree
TILE_PATH_MIN_MM = 26.0       # longer than one safe window: tile windows
#                               (physical constant — window mm unchanged)
WINDOW_CELLS = 200            # 25.4 mm at c3 (the measured-safe physical
#                               window; c3 accumulates warp over 1.5x
#                               FEWER cells/mm than c2, so 25.4 mm is
#                               conservative here)
OVERLAP_CELLS = 40            # same 5.1 mm physical overlap as the c2 60


def _manifest_crosscheck() -> None:
    """Guard the frozen constants against the sha-recorded build manifest
    when it is present (a truly separate session may not have it)."""
    mf_path = ROOT / "experiments/018-confetti-c3-play/build/e018_manifest.json"
    if not mf_path.exists():
        return
    vol = json.loads(mf_path.read_text())["volume"]
    assert vol["data_sha256"] == GOLDEN_SHA, "manifest/GOLDEN_SHA mismatch"
    assert vol["data_len_bytes"] == DATA_LEN_BYTES, "manifest/data_len mismatch"
    assert vol["ldpc_rate_id"] == LDPC_RATE, "manifest/rate mismatch"
    assert (vol["k_total"], vol["n_symbols_total"]) == (396, 782)


def load_img(path: Path) -> np.ndarray:
    if path.suffix.lower() in (".tif", ".tiff"):
        return tifffile.TiffFile(str(path)).pages[0].asarray(out="memmap")
    return np.asarray(Image.open(path).convert("L"))


def refine_piece(p: segment.Piece, backing: float, pl_e, spec_, pend,
                 dpi: float, erode_cells: int,
                 allow_overhang: bool = False):
    """The measured P2 chain (016.6, c2 white fixture): core-mask placement
    gives the admission, then pilot-supervised (angle, continuous-phase)
    refinement + per-piece Gaussian recal give the quality. Cell-size
    agnostic machinery; constants carried from the c2 measurement (first
    c3 session = its measurement). Any failure falls back to the initial
    observation (returns None)."""
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
                                gate_true=0.20, gate_decoy=0.20,
                                allow_overhang=allow_overhang)
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
                                gate_true=0.20, gate_decoy=0.20,
                                allow_overhang=allow_overhang)
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


def _verdict(data_out: bytes) -> int:
    """Closure verdict: golden bytes -> the deliverable + tar hint, exit 0;
    anything else -> a clearly-labeled forensics file, exit 1 (never the
    deliverable path — a bad re-decode must not clobber a good archive)."""
    sha = hashlib.sha256(data_out).hexdigest()
    ok = sha == GOLDEN_SHA
    out = RECOVERED if ok else MISMATCH_OUT
    out.parent.mkdir(parents=True, exist_ok=True)   # fresh worktrees/
    #                             clones lack the git-ignored build/
    out.write_bytes(data_out)
    print(f"  VOLUME DECODED: {len(data_out)} bytes, sha {sha[:16]}… "
          f"{'== GOLDEN, BYTE-EXACT' if ok else '*** MISMATCH ***'}",
          flush=True)
    if ok:
        print(f"  wrote {RECOVERED.relative_to(ROOT)} — "
              "`tar xzf` it for paperholo/*.py", flush=True)
    else:
        print(f"  wrote {out.relative_to(ROOT)} (forensics only — "
              "NOT the archive)", flush=True)
    return 0 if ok else 1


def _save_state(path: Path, pds, done) -> None:
    """Atomic: a crash mid-write must not brick the accumulated session."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(pickle.dumps((pds, done)))
    os.replace(tmp, path)


def _payload_inv(pim: np.ndarray) -> np.ndarray:
    """payload-bijection index -> (y, x) absolute cell (the inverse of
    compose.payload_index_map). Twin of draw_decode_map.reassembly_inv —
    used to find which 64-cell LDPC tiles a piece's cells touch, for the
    per-piece incremental decode."""
    ys, xs = np.nonzero(pim >= 0)
    flat = pim[ys, xs]
    inv = np.empty((int(flat.max()) + 1, 2), np.int32)
    inv[flat, 0] = ys
    inv[flat, 1] = xs
    return inv


def _touched_tiles(pds, inv: np.ndarray, sids: list[str]) -> list:
    """The 64-cell LDPC tiles any of these scan observations touch."""
    tiles: set = set()
    for s in sids:
        idx = pds.scans[s].payload_cell_index
        if idx.size == 0:
            continue
        yx = inv[idx]
        tiles.update(zip((yx[:, 0] // 64).tolist(),
                         (yx[:, 1] // 64).tolist()))
    return sorted(tiles)


def _rotated_offset(k: int, wy: int, wx: int, h: int, w: int,
                    H: int, W: int) -> tuple[int, int]:
    """Where a [wy:wy+h, wx:wx+w] window of an (H, W) grid lands after
    np.rot90(grid, k) — the window-consistency algebra (§15.6 I3)."""
    if k == 0:
        return wy, wx
    if k == 1:
        return W - wx - w, wy
    if k == 2:
        return H - wy - h, W - wx - w
    return wx, H - wy - h


def _emit_placed(pds, sid: str, bits: np.ndarray, emit_mask: np.ndarray,
                 cllr: np.ndarray, pl, pim: np.ndarray, ks: np.ndarray,
                 meta: dict, exclude_idx: np.ndarray | None = None) -> int:
    """Overhang-safe placed-fragment emission (§15.6: origins may be
    negative under padded search; clip via overlap_slices). exclude_idx:
    payload indices this piece must never emit — the driver passes cells
    already folded by the piece's word path (ID-only fold); repass v1.1-a
    passes PROTECTED word-evidence cells (conditional trust)."""
    bk_shape = np.rot90(bits, pl.rot_k).shape
    sl = place.overlap_slices(pl.origin_yx, bk_shape,
                              tuple(spec.page_cells_yx))
    if sl is None:
        return 0
    pys, pxs, fys, fxs = sl
    mk = np.rot90(emit_mask, pl.rot_k)
    lk = np.rot90(cllr, pl.rot_k)
    sel = mk[fys, fxs].copy()
    idx = pim[pys, pxs]
    sel &= idx >= 0
    kk = ks[pys, pxs]
    llr = lk[fys, fxs] * (1.0 - 2.0 * kk)   # ctx LLRs, descrambled sign
    if not sel.any():
        return 0
    emit_idx = idx[sel].astype(np.int64)
    emit_llr = llr[sel]
    if exclude_idx is not None and exclude_idx.size:
        keep = ~np.isin(emit_idx, exclude_idx)
        emit_idx, emit_llr = emit_idx[keep], emit_llr[keep]
    if emit_idx.size == 0:
        return 0
    pds.add_placed_fragment(sid, emit_idx, emit_llr,
                            placement_meta=meta)
    return int(emit_idx.size)


def sample_at_angle(p: segment.Piece, backing: float, dpi: float,
                    ang_deg: float):
    """Glass resample at an arbitrary angle (the refine_piece recipe,
    §15.6 multi-angle retry): (bits, kmask, spread-LLRs, means) or None."""
    glass, gm = p.img_glass, p.mask_glass
    if glass is None or gm is None:
        return None
    try:
        pitch = float(scannorm.measure_cell_pitch(p.img).pitch_px)
    except Exception:
        pitch = dpi / 600.0 * CD
    im = np.where(gm, glass, np.float32(backing))
    mid = float(np.median(im[gm])) if gm.any() else 128.0
    M, off, oshape = segment.rotate_transform(im.shape, ang_deg)
    ph = segment.phase_scan_glass(im, gm.astype(np.float32), mid, backing,
                                  M, off, oshape, pitch)
    if ph is None:
        return None
    _, dy0, dx0 = ph
    got = segment.sample_cells_at(glass, gm, backing, ang_deg, pitch,
                                  dy0, dx0)
    if got is None:
        return None
    means, kmask, mid_f = got
    bits = (means < mid_f).astype(np.uint8)
    spread = float(np.abs(means[kmask] - mid_f).mean()) or 1.0
    llr = np.clip((mid_f - means) / max(spread, 1e-6), -8.0, 8.0) * 2.0
    return bits, kmask, llr, means


def place_windows(bits: np.ndarray, core_full: np.ndarray, pend):
    """§15.6 I3 window-split placement: disjoint ~200-cell windows, each
    placed with the frozen gates (+ padded search), then the free
    mutual-consistency check — all passing windows must share rot_k and
    imply the same piece origin within ±CONSISTENCY_CELLS. Returns a
    list of (wy, wx, h, w, Placement) or None."""
    H, W = bits.shape
    core_n = int(core_full.sum())
    if max(H, W) <= SPLIT_CELLS or core_n <= SPLIT_CORE_CELLS:
        wins = [(0, 0, H, W)]
    else:
        ny = max(1, int(np.ceil(H / WIN_CELLS_PLACER)))
        nx = max(1, int(np.ceil(W / WIN_CELLS_PLACER)))
        hs, ws = int(np.ceil(H / ny)), int(np.ceil(W / nx))
        wins = [(iy * hs, ix * ws,
                 min(hs, H - iy * hs), min(ws, W - ix * ws))
                for iy in range(ny) for ix in range(nx)]
    results = []
    for (wy, wx, h, w) in wins:
        if h < 8 or w < 8:
            continue
        wcore = core_full[wy:wy + h, wx:wx + w]
        if len(wins) > 1 and int(wcore.sum()) < MIN_WIN_CORE_CELLS:
            continue
        pl = place.place_fragment(bits[wy:wy + h, wx:wx + w], spec, SEED,
                                  mask=wcore, pending_cell_mask=pend,
                                  gate_true=0.20, gate_decoy=0.20,
                                  allow_overhang=True)
        if pl.ok and (pl.rival_mismatch - pl.mismatch) >= 0.08:
            results.append((wy, wx, h, w, pl))
    grp = []
    if results:
        # consistency reference = the highest-z window (quality-aware;
        # a decoupled 2-window median can match NEITHER window —
        # review finding). Same rot_k required.
        ref = max(results, key=lambda g: g[4].z)
        rk = ref[4].rot_k
        for (wy, wx, h, w, pl) in results:
            if pl.rot_k != rk:
                continue
            ry, rx = _rotated_offset(rk, wy, wx, h, w, H, W)
            grp.append((wy, wx, h, w, pl,
                        (pl.origin_yx[0] - ry, pl.origin_yx[1] - rx)))
        if len(grp) > 1:
            wy0, wx0, h0, w0, pl0 = ref
            ry0, rx0 = _rotated_offset(rk, wy0, wx0, h0, w0, H, W)
            my, mx = pl0.origin_yx[0] - ry0, pl0.origin_yx[1] - rx0
            grp = [g for g in grp
                   if abs(g[5][0] - my) <= CONSISTENCY_CELLS
                   and abs(g[5][1] - mx) <= CONSISTENCY_CELLS]
    if not grp and len(wins) > 1:
        # split starved every window OR the consistency filter wiped
        # the set — whole-piece retry before giving up (review finding:
        # the fallback must also cover the wipeout path)
        pl = place.place_fragment(bits, spec, SEED, mask=core_full,
                                  pending_cell_mask=pend,
                                  gate_true=0.20, gate_decoy=0.20,
                                  allow_overhang=True)
        if pl.ok and (pl.rival_mismatch - pl.mismatch) >= 0.08:
            return [(0, 0, H, W, pl)]
    return [g[:5] for g in grp] or None


def anchor_place_piece(p: segment.Piece, backing: float, pend,
                       dpi: float, erode_cells: int):
    """§15.6 placer: angle candidates (segmenter estimate first, then the
    scannorm angle_rad seed, then the ±sweep), window-split placement at
    each, first angle with a consistent gate-passing set wins. Returns
    (dA, bits, mcell, cllr, means|None, placed_windows) or None."""
    cands = [0.0]
    try:
        seed_deg = float(np.degrees(
            scannorm.measure_cell_pitch(p.img).angle_rad))
        if 0.05 < abs(seed_deg) <= 1.5:
            cands.append(seed_deg)
    except Exception:
        pass
    for a in ANGLE_SWEEP_DEG:
        cands.extend((a, -a))
    order: list[float] = []
    for a in cands:
        if all(abs(a - b) > 0.1 for b in order):
            order.append(a)
    for dA in order:
        if dA == 0.0:
            got = piece_bits(p, dpi)
            if got is None:
                continue
            bits, mcell, cllr = got
            means = None
        else:
            s = sample_at_angle(p, backing, dpi, p.angle_deg + dA)
            if s is None:
                continue
            bits, mcell, cllr, means = s
        core_full = _core(mcell, erode_cells)
        placed = place_windows(bits, core_full, pend)
        if placed:
            return dA, bits, mcell, cllr, means, placed
    return None


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
    ap.add_argument("--dpi", type=float, required=True,
                    help="TRUE dpi of the fed image (required — a wrong "
                         "value breaks segmentation and window sizing). "
                         "Recommended footing: Canon 4800 grey decimated "
                         "3x -> 1600 dpi = 8 px/cell at c3.")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--state", type=Path, default=STATE)
    ap.add_argument("--policy", default="weighted_sum",
                    choices=tilemap.PageDecodeState._POLICIES,
                    help="tile merge policy. Default weighted_sum (union): "
                         "pieces are spatially disjoint (each cell scanned "
                         "once), so the measured multi-scan sum-negative "
                         "(012.3/013/014.2, same cells re-observed) does "
                         "not apply, and best_per_tile was measured "
                         "geometrically unable to close a confetti session "
                         "(016.5 carve-sim). best_per_tile remains right "
                         "for whole-page multi-SCAN states.")
    ap.add_argument("--piece-chain", default="anchor",
                    choices=["median", "refine", "anchor"],
                    help="'median' = the 016.4 baseline (piece_cell_bits, "
                         "spread LLRs); 'refine' adds the measured P2 "
                         "chain after a gate-passing placement (016.6); "
                         "'anchor' (default, §15.6/018.3) additionally: "
                         "mask-aware word-path windows + ID retry + "
                         "ID-window folding, padded (page-edge capable) "
                         "placement, multi-angle retry seeded by the "
                         "in-pipeline scannorm angle, and window-split "
                         "placement above the ~33 mm rigid-model span "
                         "(018.2: rescues measured 12+ symbols on a "
                         "47 mm piece that contributed 0)")
    ap.add_argument("--emit-erode-cells", type=int, default=4,
                    help="erode the piece mask by N cells for LLR EMISSION "
                         "only (placement keeps the full grown mask). The "
                         "grow-out ring samples backing and lands INSIDE "
                         "neighboring pieces' cells: union-poison for "
                         "exactly the boundary tiles that need the union "
                         "(016.7). The rim is GROW_CELLS=3 CELLS thick at "
                         "any cell size (segment.py), so N=4 = grow+1 — "
                         "the 016.5-frozen doctrine in its native cell "
                         "units; it transfers to c3 exactly.")
    ap.add_argument("--diag", nargs="?", const=str(
                        ROOT / "experiments/018-confetti-c3-play/scratch/diag"),
                    default=None, metavar="DIR",
                    help="ADDITIVE live diagnostic viewer (experiments/018-"
                         "confetti-c3-play/diag.py). Serves an auto-refreshing "
                         "glass+reference web view at localhost:--diag-port and "
                         "writes numbered PNG frames to DIR (default scratch/"
                         "diag), refreshed PER PIECE. Absent = the decode path "
                         "is byte-identical to a plain run (verified in "
                         "tests/test_diag.py).")
    ap.add_argument("--diag-port", type=int, default=8018,
                    help="port for the --diag web view (default 8018).")
    args = ap.parse_args()

    _manifest_crosscheck()
    args.state.parent.mkdir(parents=True, exist_ok=True)
    if args.state.exists() and not args.fresh:
        pds, done = pickle.loads(args.state.read_bytes())
        if pds.spec != spec or pds.seed != SEED:
            print(f"state {args.state} is not an e018 session state "
                  "(spec/seed mismatch) — pass --fresh or --state",
                  file=sys.stderr)
            return 2
    else:
        pds, done = tilemap.PageDecodeState(spec, SEED, page=0), set()
    pim = compose.payload_index_map(spec, SEED)
    ks = keystream(SEED, "CMYK".index(spec.plane), 0,
                   tuple(spec.page_cells_yx))
    cell_px = args.dpi / 600.0 * CD
    id_window_px = int(round(WINDOW_CELLS * cell_px))   # 25.4 mm at any dpi

    diag = None
    if args.diag is not None:
        import diag as diag_mod              # experiment-local, lazy
        diag = diag_mod.DiagViewer(args.diag, args.diag_port, spec, SEED,
                                   args.dpi)
    try:
        return _run(args, pds, done, pim, ks, cell_px, id_window_px, diag)
    finally:
        if diag is not None:
            diag.close()


def _run(args, pds, done, pim, ks, cell_px, id_window_px, diag) -> int:
    inv = _payload_inv(pim)                # payload idx -> cell (per-page)
    for img_path in args.images:
        if img_path.name in done:
            print(f"{img_path.name}: already folded — skip", flush=True)
            continue
        img = load_img(img_path)
        imgf = np.asarray(img, np.float32)
        pieces = segment.segment_pieces(imgf, cell_px=cell_px, dpi=args.dpi)
        backing = segment.estimate_backing(imgf)
        print(f"{img_path.name}: {len(pieces)} pieces", flush=True)
        if diag is not None:
            diag.begin_scan(img_path, imgf, pieces, pds)
        n_word = n_tiled = n_placed = n_refined = n_fail = 0
        # pend = pending-tile mask at SCAN START, hoisted above the piece
        # loop. With the per-piece incremental decode below, a lazy mid-loop
        # computation would let mid-scan certifications shrink the placer's
        # search space — a behavior change. Frozen here reproduces the
        # pre-incremental-decode semantics exactly (measured equivalent:
        # decode_tiles ran only at scan end before, so pending was constant
        # through the loop).
        pm = np.zeros(tuple(spec.page_cells_yx), bool)
        for (ty, tx) in pds.pending_tiles():
            pm[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64] = True
        if not pm.any():
            pm[:] = True                 # nothing decoded yet: whole page
        pend = {0: pm}
        checkpoint_ids = set(pds.scans)
        for i, p in enumerate(pieces):
            # progressive certification for the live view (F6): decode the
            # tiles the PREVIOUS piece(s) added, so panel C advances DURING
            # the scan instead of only at end_scan. UNCONDITIONAL (not
            # diag-gated): decode_tiles mutates the state, and the plain vs
            # --diag byte-identity contract (tests/test_diag) requires both
            # paths to run identically. Certified-never-demoted + the
            # end-of-scan full sweep keep the final state complete; every
            # early cert is CRC-gated (F9) so always valid. Cost ~+15 s/scan
            # (measured); the only visible artifact is a one-piece lag (a
            # piece's tiles light in the NEXT piece's frame).
            new_ids = [s for s in pds.scans if s not in checkpoint_ids]
            if new_ids:
                touched = _touched_tiles(pds, inv, new_ids)
                if touched:
                    pds.decode_tiles(LDPC_RATE, policy=args.policy,
                                     tiles=touched)
                checkpoint_ids = set(pds.scans)
            sid = f"{img_path.name}/p{i}"
            if diag is not None:
                diag.on_piece(p, sid, "in_progress", p.angle_deg,
                              None, None, None, pds)
            word_idx = None       # ID-only fold: placer excludes these
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
                    word_kwargs: dict = {}
                    if args.piece_chain == "anchor":
                        # §15.6 I1: mask-aware grid + ID retry + fold
                        word_kwargs = {
                            "mask": np.ascontiguousarray(
                                p.mask[yy[0]:yy[-1] + 1,
                                       xx[0]:xx[-1] + 1]),
                            "mask_min_cov": 0.65,
                            "id_retry": 3,
                            "fold_id_window": True}
                    ident, _ = formats.page_decode(
                        crop, scan_id=sid, state=pds, candidates=[FMT],
                        scan_dpi=args.dpi, window_cells=WINDOW_CELLS,
                        overlap_cells=OVERLAP_CELLS,
                        id_window_px=id_window_px,
                        detector="ctx", calibrate=True, **word_kwargs)
                    if ident.ok and sid in pds.scans:
                        n_win_ok = int(
                            ident.diagnostics.get("n_windows_ok", 0))
                        if args.piece_chain != "anchor" or n_win_ok >= 2:
                            if diag is not None:
                                diag.on_piece(p, sid, "word", p.angle_deg,
                                              None, None, None, pds)
                            n_tiled += 1
                            continue
                        # ID-only fold (review finding): the single
                        # folded ID window is certified evidence — keep
                        # it — but it is NOT piece coverage: fall
                        # through to the placer, which excludes the
                        # already-folded cells from its emission
                        word_idx = pds.scans[sid].payload_cell_index
                else:
                    r = formats.acquire_scan(p.img, candidates=[FMT],
                                             scan_dpi=args.dpi,
                                             detector="ctx", calibrate=True)
                    if r.ok:
                        pds.add_acquire_result(sid, r.result)
                        if diag is not None:
                            diag.on_piece(p, sid, "word", p.angle_deg,
                                          None, None, None, pds)
                        n_word += 1
                        continue
            # gap-based gate: constants carried from the e016 real-toner
            # sessions (016.4: x4 admissions 0 false; 016.7: 0 false in
            # 355 gated calls). The decoy floor they lean on is the v3
            # window code's distance spectrum (014.4, min 32/100) — code
            # algebra shared by this format; c3's lower piece BER only
            # widens the true-side margin.
            # Placement mask = CORE (grown mask minus the backing rim):
            # measured +47% admissions at 0 false (016.6, c2 fixture).
            if args.piece_chain == "anchor":
                res = anchor_place_piece(p, backing, pend, args.dpi,
                                         args.emit_erode_cells)
                if res is None:
                    if diag is not None:
                        diag.on_piece(p, sid, "failed", p.angle_deg,
                                      None, None, None, pds)
                    n_fail += 1
                    continue
                dA, bits, mcell, cllr, means, placed = res
                ang_disp = p.angle_deg + dA        # diag display angle
                if (len(placed) == 1 and dA == 0.0
                        and placed[0][2:4] == bits.shape):
                    # whole-piece placement at the segmenter angle: run
                    # the measured P2 refine chain for quality (016.6);
                    # allow_overhang so page-edge pieces keep the chain
                    # (review finding)
                    ref = refine_piece(p, backing, placed[0][4], spec,
                                       pend, args.dpi,
                                       args.emit_erode_cells,
                                       allow_overhang=True)
                    if ref is not None:
                        bits, mcell, cllr, pl_r, _rmeta = ref
                        n_refined += 1
                        placed = [(0, 0, bits.shape[0], bits.shape[1],
                                   pl_r)]
                        means = None
                        # review fix: dots must draw at the REFINED angle
                        ang_disp = p.angle_deg + float(
                            _rmeta.get("angle_moved", 0.0))
                core_full = _core(mcell, args.emit_erode_cells)
                n_em = 0
                for j, (wy, wx, h, w, pl) in enumerate(placed):
                    wbits = bits[wy:wy + h, wx:wx + w]
                    wcore = core_full[wy:wy + h, wx:wx + w]
                    wl = cllr[wy:wy + h, wx:wx + w]
                    if means is not None:
                        # per-window pilot-label Gaussian recal (the P2
                        # recal at window scale — measured 3/4 -> 4/4
                        # quadrant passes on the p5 forensics)
                        sij, sv = place.fragment_pilot_sites(
                            pl, (h, w), wcore, spec, SEED)
                        if sij.shape[0] >= 60:
                            lsel = np.zeros((h, w), bool)
                            lsel[sij[:, 0], sij[:, 1]] = True
                            rl = segment.recal_llrs_from_labels(
                                means[wy:wy + h, wx:wx + w], lsel, sv)
                            if rl is not None:
                                wl = rl
                    n_em += _emit_placed(
                        pds, f"{sid}/w{j}", wbits, wcore, wl, pl, pim, ks,
                        {"mismatch": pl.mismatch, "z_gap": pl.z_gap,
                         "angle_deg": p.angle_deg + dA, "dA": dA,
                         "window_yx": (wy, wx)},
                        exclude_idx=word_idx)
                if n_em > 0:
                    n_placed += 1
                else:
                    n_fail += 1
                if diag is not None:
                    diag.on_piece(p, sid, "placed" if n_em > 0 else "failed",
                                  ang_disp, placed, bits, core_full,
                                  pds)
                continue
            got = piece_bits(p, args.dpi)
            if got is None:
                if diag is not None:
                    diag.on_piece(p, sid, "failed", p.angle_deg,
                                  None, None, None, pds)
                n_fail += 1
                continue
            bits, mcell, cllr = got
            pl = place.place_fragment(bits, spec, SEED,
                                      mask=_core(mcell,
                                                 args.emit_erode_cells),
                                      pending_cell_mask=pend,
                                      gate_true=0.20, gate_decoy=0.20)
            if not pl.ok or (pl.rival_mismatch - pl.mismatch) < 0.08:
                if diag is not None:     # review fix: terminal red box
                    diag.on_piece(p, sid, "failed", p.angle_deg,
                                  None, None, None, pds)
                n_fail += 1
                continue
            ang_disp = p.angle_deg
            if args.piece_chain == "refine":
                ref = refine_piece(p, backing, pl, spec, pend, args.dpi,
                                   args.emit_erode_cells)
                if ref is not None:
                    bits, mcell, cllr, pl, _rmeta = ref
                    n_refined += 1
                    ang_disp = p.angle_deg + float(
                        _rmeta.get("angle_moved", 0.0))
            emit_mask = (_core(mcell, args.emit_erode_cells)
                         if args.emit_erode_cells > 0 else mcell)
            n_em = _emit_placed(pds, sid, bits, emit_mask, cllr, pl, pim, ks,
                                {"mismatch": pl.mismatch, "z_gap": pl.z_gap,
                                 "angle_deg": p.angle_deg})
            if n_em > 0:
                n_placed += 1
            else:
                n_fail += 1
            if diag is not None:
                diag.on_piece(
                    p, sid, "placed" if n_em > 0 else "failed", ang_disp,
                    [(0, 0, bits.shape[0], bits.shape[1], pl)], bits,
                    emit_mask, pds)
        done.add(img_path.name)
        # final full sweep: catches tiles whose evidence only completes at a
        # multi-piece boundary. The per-piece decodes above already certified
        # most; this call reports mostly skipped_certified, so print the
        # CUMULATIVE tile status (pds.summary) not this call's per-call counts.
        pds.decode_tiles(LDPC_RATE, policy=args.policy)
        syms = fountain.tiles_to_symbols(pds.certified_results(), VSPEC)
        data_out, fdiag = fountain.volume_decode(syms, VSPEC)
        print(f"  word-path {n_word} (+{n_tiled} tiled), placed {n_placed} "
              f"({n_refined} refined), failed {n_fail} | tiles "
              f"{pds.summary()['tiles']} | fountain symbols "
              f"{fdiag['n_symbols_received']}/{VSPEC.k_total} needed",
              flush=True)
        _save_state(args.state, pds, done)
        if diag is not None:
            diag.end_scan(img_path, pds)
        if data_out is not None:
            return _verdict(data_out)
        wanted = tilemap.volume_scans_wanted({0: pds}, VSPEC)
        print(f"  volume_scans_wanted: {wanted}", flush=True)
    # re-evaluate the persisted state: an all-images-skipped re-run of a
    # CLOSED session must repeat the real verdict (review-confirmed: the
    # e016-inherited flow printed a false "session open" and returned 0
    # here, inverting a prior MISMATCH exit 1). Certified tiles are never
    # demoted, so this is one cheap GE solve over the pickled results.
    syms = fountain.tiles_to_symbols(pds.certified_results(), VSPEC)
    data_out, _ = fountain.volume_decode(syms, VSPEC)
    if data_out is not None:
        return _verdict(data_out)
    print("session open — feed more images (fountain rank not reached)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
