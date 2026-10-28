"""Segmentation + alignment front end (paperholo.segment, §15.2) and the
mask-aware placer extension. Correctness bar: a piece cut from the
composed e014 page, rendered at 8 px/cell, rotated by an arbitrary angle
and pasted on a glass canvas must segment, de-rotate, and PLACE at its
true origin — placement is the aligner's ground truth. Backing invariance
(dark sheet vs white lid) is a test, not a claim."""
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "experiments/014-c2-print"))

from paperholo import compose, place, segment
from paperholo.modulation import rng
import gen_e014

SEED = gen_e014.SEED
SPEC = gen_e014.make_spec()
CELL_PX = 8            # 2400 dpi footing at c2
DPI = 2400.0
PAPER, INK = 210, 35


def _page_bits() -> np.ndarray:
    payload = rng(SEED, b"e014/payload").integers(
        0, 2, compose.payload_capacity(SPEC), dtype=np.uint8)
    return compose.compose_page(payload, SPEC, SEED, page=0).cell_values


_PAGE = _page_bits()


def _render(cells: np.ndarray) -> np.ndarray:
    return np.where(np.kron(cells, np.ones((CELL_PX, CELL_PX),
                                           np.uint8)) > 0, INK, PAPER
                    ).astype(np.float32)


def _canvas(pieces: list[tuple[np.ndarray, float]], backing: float
            ) -> np.ndarray:
    """Rotate each rendered piece, shelf them on one canvas."""
    rots = [ndimage.rotate(p, a, reshape=True, order=1, cval=backing,
                           mode="constant") for p, a in pieces]
    gap = 8 * CELL_PX
    W = max(r.shape[1] for r in rots) + 2 * gap
    H = sum(r.shape[0] + gap for r in rots) + gap
    canvas = np.full((H, W), backing, np.float32)
    y = gap
    for r in rots:
        canvas[y:y + r.shape[0], gap:gap + r.shape[1]] = r
        y += r.shape[0] + gap
    return canvas


def _gt_agree(pl: place.Placement, bits: np.ndarray, km: np.ndarray
              ) -> float:
    """Masked-cell agreement vs the composed page at the PLACED origin —
    the content-true verdict (the grid corner may legitimately sit
    grow-out + rotation-reshape margins before the piece content)."""
    oy, ox = pl.origin_yx
    bk, mk = np.rot90(bits, pl.rot_k), np.rot90(km, pl.rot_k)
    g = _PAGE[oy:oy + bk.shape[0], ox:ox + bk.shape[1]]
    if g.shape != bk.shape:
        return 0.0, 0.0
    core = ndimage.binary_erosion(mk, iterations=4)
    return (float(np.mean(bk[mk] == g[mk])),
            float(np.mean(bk[core] == g[core])) if core.any() else 0.0)


def _bits_from_piece(p: segment.Piece) -> tuple[np.ndarray, np.ndarray]:
    """Cell-grid hard bits + cell mask from a de-rotated piece (block-mean
    threshold — the sim path; real scans go through scannorm/lock)."""
    mid = (PAPER + INK) / 2
    best = None
    for dy in range(CELL_PX):        # integer phase lock (the real front
        for dx in range(CELL_PX):    # end does this sub-pixel in lock_grid)
            h = ((p.img.shape[0] - dy) // CELL_PX) * CELL_PX
            w = ((p.img.shape[1] - dx) // CELL_PX) * CELL_PX
            if h < CELL_PX or w < CELL_PX:
                continue
            m = p.img[dy:dy + h, dx:dx + w].reshape(
                h // CELL_PX, CELL_PX, w // CELL_PX, CELL_PX
            ).mean(axis=(1, 3))
            km = p.mask[dy:dy + h, dx:dx + w].reshape(
                h // CELL_PX, CELL_PX, w // CELL_PX, CELL_PX
            ).mean(axis=(1, 3)) > 0.85
            conf = float(np.abs(m[km] - mid).mean()) if km.any() else 0.0
            if best is None or conf > best[0]:
                best = (conf, m, km)
    _, m, km = best
    return (m < mid).astype(np.uint8), km


CROPS = [((317, 511), 118, 11.7), ((1201, 88), 94, 37.0),
         ((2660, 1990), 142, 78.4)]   # (origin, side cells, angle deg)


def _run_session(backing: float) -> list[dict]:
    pieces_in = [(_render(_PAGE[oy:oy + s, ox:ox + s]), a)
                 for (oy, ox), s, a in CROPS]
    canvas = _canvas(pieces_in, backing)
    found = segment.segment_pieces(canvas, cell_px=CELL_PX, dpi=DPI,
                                   backing=None)
    assert len(found) == len(CROPS), f"found {len(found)} pieces"
    out = []
    for p in found:
        bits, km = _bits_from_piece(p)
        pl = place.place_fragment(bits, SPEC, SEED, mask=km)
        out.append({"angle": p.angle_deg, "area": p.area_mm2, "pl": pl,
                    "agree": _gt_agree(pl, bits, km)})
    return out


def test_segment_align_place_dark_and_white_invariant() -> None:
    dark = _run_session(40.0)
    white = _run_session(250.0)
    truth = {(oy, ox) for (oy, ox), _, _ in CROPS}
    for sess, name in ((dark, "dark"), (white, "white")):
        origins = set()
        for r in sess:
            pl = r["pl"]
            assert pl.ok, (name, r)
            assert pl.mismatch < 0.10, (name, pl.mismatch)
            grown, core = r["agree"]
            # grown mask deliberately over-includes a background rim
            # (§15.2b); the fidelity bar sits on the eroded core
            assert core > 0.97 and grown > 0.88, (name, r["agree"])
            hit = min(truth, key=lambda t: abs(t[0] - pl.origin_yx[0])
                      + abs(t[1] - pl.origin_yx[1]))
            s = max(sd for _, sd, _ in CROPS)
            assert abs(hit[0] - pl.origin_yx[0]) <= s // 2
            assert abs(hit[1] - pl.origin_yx[1]) <= s // 2
            origins.add(hit)
        assert origins == truth, name
    # backing invariance: same pieces, angles agree to 0.3 deg
    for rd, rw in zip(sorted(dark, key=lambda r: r["area"]),
                      sorted(white, key=lambda r: r["area"])):
        assert abs(rd["angle"] - rw["angle"]) < 0.3


def test_lattice_angle_sweep() -> None:
    """Aligner alone: recovered angle (mod 90) within 0.4 deg across the
    quadrant, including near the 45-deg fold."""
    crop = _render(_PAGE[600:600 + 130, 600:600 + 130])
    for true in (0.0, 7.3, 22.0, 44.0, 46.0, 63.5, 88.0):
        rot = ndimage.rotate(crop, true, reshape=True, order=1,
                             cval=250.0, mode="constant")
        m = np.ones(rot.shape, bool)
        got = segment.lattice_angle(rot, m, CELL_PX)
        d = abs((got - (-true)) % 90.0)
        d = min(d, 90.0 - d)
        assert d < 0.4, (true, got)


def test_torn_piece_masked_placement() -> None:
    """Irregular blob piece: without the mask the gate would drown in
    background; with it, placement is exact-class and gated."""
    (oy, ox), s = (901, 301), 150
    crop = _render(_PAGE[oy:oy + s, ox:ox + s])
    yy, xx = np.mgrid[0:s * CELL_PX, 0:s * CELL_PX]
    c = s * CELL_PX / 2
    blob = ((yy - c) ** 2 / (0.95 * c) ** 2
            + (xx - c) ** 2 / (0.65 * c) ** 2) < 1.0   # torn-ish ellipse
    torn = np.where(blob, crop, 250.0)
    canvas = _canvas([(torn, 28.0)], 250.0)
    found = segment.segment_pieces(canvas, cell_px=CELL_PX, dpi=DPI)
    assert len(found) == 1
    bits, km = _bits_from_piece(found[0])
    assert 0.3 < km.mean() < 0.95          # genuinely partial coverage
    pl = place.place_fragment(bits, SPEC, SEED, mask=km)
    assert pl.ok and pl.mismatch < 0.10
    grown, core = _gt_agree(pl, bits, km)
    assert core > 0.97 and grown > 0.88, (grown, core)
    assert abs(pl.origin_yx[0] - oy) <= s and abs(pl.origin_yx[1] - ox) <= s
