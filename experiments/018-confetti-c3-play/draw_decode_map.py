#!/usr/bin/env python
"""Four-panel e018 decode map from a session state (post-hoc summary):

 A  glass (scan space): pieces outlined in their tilted frame, colored
    by decode outcome (green=contributed / red=failed / grey=phantom)
 B  page reassembly: each decoded piece's payload footprint at its
    absolute pilot-addressed page position (per-piece tints)
 C  LDPC data tiles (64-cell): certified / failed / low-cov / degenerate
 D  pilot tiles (60-cell): decoded BCH word or no coverage

Panels B/C/D come entirely from the state (no scan needed); panel A
re-segments the fed scan at --dpi (pass the SAME dpi you fed
session_decode.py, so piece indices match the state's scan ids). If the
scan is omitted or re-segmentation mismatches, A is skipped and the map
still renders. Renderers are importable (the --diag live viewer reuses
them). PIL/numpy only — no matplotlib in env.

  env/bin/python draw_decode_map.py --state build/session.pkl \
      --scan scan_1600.tiff --dpi 1600 --out build/e018_map.png
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import compose, segment  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
# TAB20 (was TAB10): more physical pieces than 10 per session collided on
# the mod-10 wheel — the 2-scan e018 map painted piece 16 in piece 4's
# purple, on top of it (2026-07-12 forensics, a pane-B misread trigger).
TAB20 = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
         (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127),
         (188, 189, 34), (23, 190, 207), (174, 199, 232), (255, 187, 120),
         (152, 223, 138), (255, 152, 150), (197, 176, 213), (196, 156, 148),
         (247, 182, 210), (199, 199, 199), (219, 219, 141), (158, 218, 229)]
GREEN, RED, GREY = (44, 160, 44), (214, 39, 40), (176, 176, 176)
LDPC_COL = {"certified": (44, 160, 44), "failed": (255, 127, 14),
            # low_coverage was background-grey = invisible in panel C
            # (2026-07-12 forensics); yellow makes "seen but not enough
            # evidence yet" legible, distinct from unobserved (grey).
            "low_coverage": (245, 210, 40), "degenerate": (138, 138, 138),
            "unobserved": (236, 236, 236)}
PALE, PILOT = (240, 240, 240), (31, 119, 180)
PILOT_PLACED = (255, 187, 120)   # pale orange: pilot tile covered only by a
#                                  correlation-placed fragment (no BCH word)


def _font(sz):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", sz)
    except Exception:
        return ImageFont.load_default()


def piece_index(sid: str, basename: str) -> int | None:
    """'basename/p7' or 'basename/p7/w2' -> 7."""
    pre = basename + "/p"
    if not sid.startswith(pre):
        return None
    tail = sid[len(pre):].split("/")[0]
    return int(tail) if tail.isdigit() else None


def _upscale(arr: np.ndarray, target_w: int) -> Image.Image:
    im = Image.fromarray(arr)
    z = max(1, target_w // arr.shape[1])
    return im.resize((arr.shape[1] * z, arr.shape[0] * z), Image.NEAREST)


_REASM_INV_CACHE: dict[tuple, np.ndarray] = {}


def reassembly_inv(pds) -> np.ndarray:
    """payload-bit index -> (y, x) absolute cell, cached per (seed, page
    geometry). Building it re-derives payload_index_map (~24 ms) + a 3.2 M
    scatter, so cache it: the --diag live viewer redraws panel B once PER
    PIECE, and this map is a pure function of (spec, seed)."""
    key = (pds.seed, tuple(pds.spec.page_cells_yx))
    inv = _REASM_INV_CACHE.get(key)
    if inv is None:
        pim = compose.payload_index_map(pds.spec, pds.seed)
        ys, xs = np.nonzero(pim >= 0)
        idx = pim[ys, xs]
        inv = np.empty((int(idx.max()) + 1, 2), np.int32)
        inv[idx, 0] = ys
        inv[idx, 1] = xs
        _REASM_INV_CACHE[key] = inv
    return inv


def _parse_sid(sid: str) -> tuple[str, int] | None:
    """'name/p7' or 'name/p7/w2' -> ('name', 7); None if not piece-shaped."""
    if "/p" not in sid:
        return None
    base, rest = sid.rsplit("/p", 1)
    pn = rest.split("/")[0]
    return (base, int(pn)) if pn.isdigit() else None


MERGE_CELLS = 60   # same PHYSICAL piece across scans lands within this
#                    (measured on the 2-scan e018 session: same piece
#                    centroid distance 1-35 cells; a different region 152)


def panel_reassembly(pds, target_w: int, bin_cells: int = 6,
                     basename: str | None = None) -> Image.Image:
    """Per-piece payload footprints at absolute page position. Multi-scan
    aware: observations are grouped per (scan, piece), then groups from
    DIFFERENT scans whose page centroids sit within MERGE_CELLS are the
    same PHYSICAL piece and merge — one color + one number per physical
    piece (labeled with the EARLIEST scan's piece index, matching that
    scan's panel A). Without the merge, a re-placed second scan painted
    every piece twice in clashing colors (user report, 2-scan session)."""
    H, W = pds.spec.page_cells_yx
    inv = reassembly_inv(pds)
    covH, covW = H // bin_cells + 1, W // bin_cells + 1
    cover = np.full((covH, covW, 3), 245, np.uint8)

    # 1. per-(scan, piece) groups, in observation (chronological) order
    groups: dict = {}
    base_order: list[str] = []
    for sid, obs in pds.scans.items():
        parsed = _parse_sid(sid)
        key = parsed if parsed is not None else (sid, -1)
        if parsed is not None and parsed[0] not in base_order:
            base_order.append(parsed[0])
        groups.setdefault(key, []).append(obs)

    # 2. centroid per group
    ginfo = []
    for (base, pn), obss in groups.items():
        allyx = np.concatenate([inv[o.payload_cell_index] for o in obss])
        ginfo.append({"base": base, "pn": pn, "obss": obss,
                      "cen": (float(allyx[:, 0].mean()),
                              float(allyx[:, 1].mean())),
                      "n": int(allyx.shape[0])})

    # 3. merge across scans by page-footprint centroid (greedy, earliest
    #    scan's group is the anchor and provides the label)
    def brank(b):
        return base_order.index(b) if b in base_order else len(base_order)
    ginfo.sort(key=lambda g: (brank(g["base"]), g["pn"]))
    merged: list[dict] = []
    for g in ginfo:
        home = None
        for m in merged:
            if m["base"] != g["base"]:
                d = np.hypot(m["cen"][0] - g["cen"][0],
                             m["cen"][1] - g["cen"][1])
                if d <= MERGE_CELLS:
                    home = m
                    break
        if home is None:
            merged.append(dict(g))
        else:
            home["obss"] = home["obss"] + g["obss"]
            home["n"] += g["n"]

    # 4. paint + label (biggest physical piece first). Labels are
    #    'S.P' — S = the anchor (earliest) scan's index in feed order,
    #    P = that scan's piece index (matching its panel A) — so a
    #    footprint can be traced back to the exact scan+piece it came from
    #    (user request 2026-07-12). Every DISJOINT component of a group's
    #    footprint is labeled, not just the merged centroid: the
    #    ride-along triangle sat far from its piece's centroid and read as
    #    orphan/foreign (the pane-B misread).
    merged.sort(key=lambda m: -m["n"])
    dr_pts = []
    for k, m in enumerate(merged):
        occ = np.zeros((covH, covW), bool)
        for obs in m["obss"]:
            yx = inv[obs.payload_cell_index]
            by, bx = yx[:, 0] // bin_cells, yx[:, 1] // bin_cells
            cover[by, bx] = TAB20[k % 20]
            occ[by, bx] = True
        if m["pn"] >= 0:
            tag = f"{brank(m['base'])}.{m['pn']}"
            lab_c, n_c = ndimage.label(occ)
            for ci in range(1, n_c + 1):
                cy, cx = np.argwhere(lab_c == ci).mean(axis=0)
                dr_pts.append((tag, cy, cx))
    img = _upscale(cover, target_w).resize(
        (target_w, int(target_w * covH / covW)), Image.NEAREST)
    if dr_pts:
        dr = ImageDraw.Draw(img)
        f = _font(16)
        sy = img.height / covH
        sx = img.width / covW
        for (tag, cy, cx) in dr_pts:
            dr.text((cx * sx - 6, cy * sy - 9), tag,
                    fill=(255, 255, 255), font=f,
                    stroke_width=2, stroke_fill=(40, 40, 40))
    return img


def panel_ldpc(pds, target_w: int) -> tuple[Image.Image, dict]:
    tks = list(pds.tiles.keys())
    tH = max(t[0] for t in tks) + 1
    tW = max(t[1] for t in tks) + 1
    grid = np.full((tH, tW, 3), 236, np.uint8)
    nstat: dict[str, int] = {}
    for t, st in pds.tiles.items():
        grid[t] = LDPC_COL.get(st.status, PALE)
        nstat[st.status] = nstat.get(st.status, 0) + 1
    img = _upscale(grid, target_w).resize(
        (target_w, int(target_w * tH / tW)), Image.NEAREST)
    return img, nstat


def panel_pilot(pds, target_w: int, period: int = 60
                ) -> tuple[Image.Image, int, int]:
    """Pilot-tile map. BLUE = a BCH word decoded there (word path). PALE
    ORANGE = the tile is covered only by a correlation-PLACED fragment
    (no word; add_placed_fragment carries tile_words={} by design, so
    panel D used to show nothing for placed pieces — a coverage-vs-word
    confusion, 2026-07-12 forensics). Returns (img, n_words, n_placed)."""
    H, W = pds.spec.page_cells_yx
    pH, pW = H // period, W // period
    grid = np.full((pH, pW, 3), 240, np.uint8)
    n_words = 0
    for obs in pds.scans.values():
        for (ty, tx) in getattr(obs, "tile_words", {}) or {}:
            if 0 <= ty < pH and 0 <= tx < pW and tuple(grid[ty, tx]) != PILOT:
                grid[ty, tx] = PILOT
                n_words += 1
    # second pass: correlation-placed coverage in the still-background tiles
    inv = reassembly_inv(pds)
    placed = set()
    for obs in pds.scans.values():
        if getattr(obs, "tile_words", None):
            continue                              # word-path obs already drawn
        yx = inv[obs.payload_cell_index]
        for (ty, tx) in set(zip((yx[:, 0] // period).tolist(),
                                (yx[:, 1] // period).tolist())):
            if (0 <= ty < pH and 0 <= tx < pW
                    and tuple(grid[ty, tx]) == (240, 240, 240)):
                grid[ty, tx] = PILOT_PLACED
                placed.add((ty, tx))
    img = _upscale(grid, target_w).resize(
        (target_w, int(target_w * pH / pW)), Image.NEAREST)
    return img, n_words, len(placed)


def panel_glass(scan_gray: np.ndarray, dpi: float, decoded: set[int],
                target_w: int, preview_down: int = 8) -> Image.Image | None:
    cell_px = dpi / 600.0 * 3
    try:
        pieces = segment.segment_pieces(np.asarray(scan_gray, np.float32),
                                        cell_px=cell_px, dpi=dpi)
    except Exception:
        return None
    d = preview_down
    pv = scan_gray[::d, ::d]
    pv = np.clip((pv - pv.min()) / (np.ptp(pv) + 1e-6) * 255,
                 0, 255).astype(np.uint8)
    img = Image.fromarray(pv).convert("RGB")
    scale = target_w / img.width
    img = img.resize((target_w, int(img.height * scale)))
    dr = ImageDraw.Draw(img)
    f = _font(13)
    MASK_COL = (150, 200, 235)          # pale blue: the considered lattice
    for i, p in enumerate(sorted(pieces, key=lambda q: -q.area_mm2)):
        y0, x0, h, w = p.bbox_glass
        s = scale / d
        col = GREEN if i in decoded else (
            RED if p.area_mm2 >= 200 else GREY)
        # pale outline of the segmenter mask = the region actually
        # considered (grow-out included) — user-requested from the
        # original hand overview
        mg = p.mask_glass
        if mg is not None and mg.any():
            st = max(1, int(round(1.0 / (scale / d) / 2)))
            ms = mg[::st, ::st]
            edge = (ms ^ np.roll(ms, 1, 0)) | (ms ^ np.roll(ms, 1, 1))
            ys2, xs2 = np.nonzero(edge)
            gs = st * scale / d
            pts = [((x0 * s) + xx * gs, (y0 * s) + yy * gs)
                   for yy, xx in zip(ys2, xs2)]
            if pts:
                dr.point(pts, fill=MASK_COL)
        dr.rectangle([x0 * s, y0 * s, (x0 + w) * s, (y0 + h) * s],
                     outline=col, width=2)
        if p.area_mm2 >= 200:
            dr.text((x0 * s + 2, y0 * s - 15),
                    f"{i} {p.angle_deg:+.0f}°", fill=col, font=f,
                    stroke_width=2, stroke_fill=(255, 255, 255))
    return img


def render_decode_map(pds, out_path: Path, scan_gray=None, dpi=1600.0,
                      basename: str | None = None,
                      title: str = "e018 decode map") -> Path:
    PANEL_W, pad, top, th = 760, 30, 92, 34
    f13, f16, f22 = _font(15), _font(18), _font(24)
    decoded: set[int] = set()
    if basename is not None:
        for sid in pds.scans:
            pi = piece_index(sid, basename)
            if pi is not None:
                decoded.add(pi)
    glass = (panel_glass(scan_gray, dpi, decoded, PANEL_W)
             if scan_gray is not None else None)
    reasm = panel_reassembly(pds, PANEL_W, basename=basename)
    ldpc, nstat = panel_ldpc(pds, PANEL_W)
    pilot, n_pilot, n_placed_tiles = panel_pilot(pds, PANEL_W)

    col_h = max(glass.height if glass else 0, reasm.height)
    row2_h = max(ldpc.height, pilot.height)
    W = pad * 3 + PANEL_W * 2
    Ht = top + th + col_h + 40 + th + row2_h + 60
    canvas = Image.new("RGB", (W, Ht), (255, 255, 255))
    dr = ImageDraw.Draw(canvas)
    cert = nstat.get("certified", 0)
    dr.text((pad, 22), title, fill=(0, 0, 0), font=f22)
    dr.text((pad, 56), f"{cert} certified LDPC tiles · {n_pilot} pilot "
            f"words · {len(decoded)} pieces on this scan",
            fill=(90, 90, 90), font=f16)
    x1, x2 = pad, pad * 2 + PANEL_W

    def _title(x, y, t):
        dr.text((x, y), t, fill=(0, 0, 0), font=f13)

    yT = top
    if glass:
        _title(x1, yT, "A · glass  (green=decoded  red=failed  grey=phantom)")
        canvas.paste(glass, (x1, yT + th))
    else:
        _title(x1, yT, "A · glass  (scan not supplied)")
    _title(x2, yT, "B · page reassembly  (per-piece tint at page position)")
    canvas.paste(reasm, (x2, yT + th))
    yT2 = yT + th + col_h + 40
    _title(x1, yT2, f"C · LDPC tiles  cert {cert} / fail "
           f"{nstat.get('failed',0)} / low-cov {nstat.get('low_coverage',0)}")
    canvas.paste(ldpc, (x1, yT2 + th))
    _title(x2, yT2, f"D · pilot tiles  {n_pilot} words + "
           f"{n_placed_tiles} placed")
    canvas.paste(pilot, (x2, yT2 + th))
    canvas.save(out_path)
    return out_path


def _load_scan(path: Path) -> np.ndarray:
    import tifffile
    if path.suffix.lower() in (".tif", ".tiff"):
        return tifffile.TiffFile(str(path)).pages[0].asarray(out="memmap")
    return np.asarray(Image.open(path).convert("L"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", type=Path, required=True)
    ap.add_argument("--scan", type=Path, default=None,
                    help="the SAME image you fed session_decode.py "
                         "(for panel A; re-segmented at --dpi)")
    ap.add_argument("--dpi", type=float, default=1600.0)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "experiments/018-confetti-c3-play/build/e018_decode_map.png")
    ap.add_argument("--title", default="e018 decode map")
    args = ap.parse_args()
    pds, done = pickle.loads(args.state.read_bytes())
    scan_gray = _load_scan(args.scan) if args.scan else None
    basename = args.scan.name if args.scan else None
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out = render_decode_map(pds, args.out, scan_gray=scan_gray, dpi=args.dpi,
                            basename=basename, title=args.title)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
