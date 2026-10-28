"""§15.6 anchor-chain synthetics — the three 018.2-measured failure
classes, in-process against the e018 session driver's chain functions:

  (i)   page-EDGE piece with attached blank margin -> grown grid
        overhangs the field -> needs padded placement (p8 class)
  (ii)  large piece with y-scale -0.31% print-frozen affine -> rigid
        whole-piece model floors above the gate; window-split must
        place consistently (p5 class)
  (iii) steep rotation (~30 deg) -> segmenter angle error class;
        multi-angle retry absorbs it
  (iv)  toner-free sliver (phantom) -> must refuse (0-false doctrine)

Pieces are rendered by direct supersampled sampling of the composed
cell field (the gen_confetti_synth recipe) + optical channel, NO dev
morphology (session machinery test; channel realism proven on real
toner in 016/018)."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import compose, fountain, place, segment, tilemap  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "e018_session_decode",
    ROOT / "experiments/018-confetti-c3-play/session_decode.py")
sd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sd)

PPC = 8                      # px/cell = 1600 dpi at c3
PAPER, INK, BACKING = 205.0, 45.0, 224.0
MARGIN_CELLS = 48            # blank page margin around the field (~12 mm)


def _page_cells():
    import gen_e018_shim  # noqa: F401  (never exists — placeholder)


def _compose_cells():
    sys.path.insert(0, str(ROOT / "experiments/018-confetti-c3-play"))
    import gen_e018
    vspec = gen_e018.make_vspec()
    data = gen_e018.make_data(vspec)
    framed = fountain.encode_volume_pages(data, vspec)[0]
    cp = compose.compose_page(framed["payload_bits"], gen_e018.make_spec(),
                              gen_e018.SEED, page=0)
    return cp.cell_values.astype(np.uint8)


CELLS = _compose_cells()
H_C, W_C = CELLS.shape
# extended field: page cells surrounded by blank paper margin
EXT = np.zeros((H_C + 2 * MARGIN_CELLS, W_C + 2 * MARGIN_CELLS), np.uint8)
EXT[MARGIN_CELLS:-MARGIN_CELLS, MARGIN_CELLS:-MARGIN_CELLS] = CELLS
REFL = PAPER - EXT.astype(np.float32) * (PAPER - INK)


def render_piece(rect, angle_deg, gen, y_scale=1.0):
    """Direct inverse-map sampling of the extended cell field at 2x
    supersampling -> PPC px/cell, optical blur+noise. rect in EXTENDED
    cell coords. y_scale < 1 simulates the M281 print-y-short class."""
    y0, x0, side_y, side_x = rect
    a = np.deg2rad(angle_deg)
    SS = 2
    diag = np.hypot(side_y, side_x)
    n_out_y = int(np.ceil(side_y * abs(np.cos(a)) + side_x * abs(np.sin(a)))) + 2
    n_out_x = int(np.ceil(side_y * abs(np.sin(a)) + side_x * abs(np.cos(a)))) + 2
    Ny, Nx = n_out_y * PPC * SS, n_out_x * PPC * SS
    dy = (np.arange(Ny) + 0.5) / (PPC * SS) - n_out_y / 2.0
    dx = (np.arange(Nx) + 0.5) / (PPC * SS) - n_out_x / 2.0
    dv, du = np.meshgrid(dy, dx, indexing="ij")
    cy, cx = y0 + side_y / 2.0, x0 + side_x / 2.0
    yy = cy + (dv * np.cos(a) - du * np.sin(a)) / y_scale
    xx = cx + (dv * np.sin(a) + du * np.cos(a))
    inside = ((yy >= y0) & (yy < y0 + side_y)
              & (xx >= x0) & (xx < x0 + side_x))
    iy = np.clip(yy.astype(np.int64), 0, REFL.shape[0] - 1)
    ix = np.clip(xx.astype(np.int64), 0, REFL.shape[1] - 1)
    hi = np.where(inside, REFL[iy, ix], BACKING)
    out = hi.reshape(Ny // SS, SS, Nx // SS, SS).mean(axis=(1, 3))
    out = ndimage.gaussian_filter(out, 2.0, mode="nearest")
    out = out + gen.normal(0.0, 5.0, out.shape).astype(np.float32)
    return np.clip(out, 0, 255).astype(np.float32), diag


def _canvas(pieces_px, gap=90):
    """Shelf-pack rendered pieces onto a white canvas."""
    W = max(p.shape[1] for p in pieces_px) + 2 * gap
    total_h = sum(p.shape[0] for p in pieces_px) + gap * (len(pieces_px) + 1)
    cv = np.full((total_h, max(W, 1200)), BACKING, np.float32)
    y = gap
    for p in pieces_px:
        cv[y:y + p.shape[0], gap:gap + p.shape[1]] = p
        y += p.shape[0] + gap
    return np.clip(cv, 0, 255).astype(np.float32)


def _run_chain(canvas, expect_origins):
    """Segment + anchor chain each piece; return per-piece results and a
    decode state. expect_origins: list of (page-frame oy, ox, h, w) GT
    piece-grid origins (approx, cells) or None for must-refuse."""
    pieces = segment.segment_pieces(canvas, cell_px=8.0, dpi=1600.0)
    backing = segment.estimate_backing(canvas)
    pds = tilemap.PageDecodeState(sd.spec, sd.SEED, page=0)
    pim = compose.payload_index_map(sd.spec, sd.SEED)
    from paperholo.modulation import keystream
    ks = keystream(sd.SEED, 3, 0, tuple(sd.spec.page_cells_yx))
    pend = {0: np.ones(tuple(sd.spec.page_cells_yx), bool)}
    out = []
    for i, p in enumerate(sorted(pieces, key=lambda q: -q.area_mm2)):
        res = sd.anchor_place_piece(p, backing, pend, 1600.0, 4)
        if res is None:
            out.append(None)
            continue
        dA, bits, mcell, cllr, means, placed = res
        core_full = sd._core(mcell, 4)
        n_em = 0
        for j, (wy, wx, h, w, pl) in enumerate(placed):
            n_em += sd._emit_placed(
                pds, f"t/p{i}/w{j}", bits[wy:wy + h, wx:wx + w],
                core_full[wy:wy + h, wx:wx + w],
                cllr[wy:wy + h, wx:wx + w], pl, pim, ks, {"dA": dA})
        out.append((dA, bits.shape, placed, n_em))
    return out, pds


def test_edge_margin_overhang_and_distorted_and_rotated():
    gen = np.random.default_rng(1803)
    H_E = H_C + 2 * MARGIN_CELLS
    pieces = []
    # (i) p8 class: bottom-edge piece, half field / half blank margin,
    #     mild rotation. Field bottom edge in EXT coords = MARGIN+H_C.
    img, _ = render_piece((MARGIN_CELLS + H_C - 130, 400, 170, 200),
                          -4.0, gen)
    pieces.append(("edge-margin", img,
                   (H_C - 130, 400 - MARGIN_CELLS)))
    # (ii) p5 class: big interior piece with the measured y-short affine
    img, _ = render_piece((MARGIN_CELLS + 700, MARGIN_CELLS + 500,
                           350, 350), -11.0, gen, y_scale=1.0 - 0.0031)
    pieces.append(("big-affine", img, (700, 500)))
    # (iii) steep rotation, interior, modest size
    img, _ = render_piece((MARGIN_CELLS + 300, MARGIN_CELLS + 900,
                           160, 160), 31.0, gen)
    pieces.append(("rot31", img, (300, 900)))
    canvas = _canvas([p[1] for p in pieces])
    results, pds = _run_chain(canvas, None)
    assert len(results) == 3, f"segmentation found {len(results)} pieces"
    placed_ok = 0
    for (name, _img, _gt), res in zip(pieces, results):
        assert res is not None, f"{name}: anchor chain refused"
        dA, shape, placed, n_em = res
        assert n_em > 0, f"{name}: nothing emitted"
        placed_ok += 1
    # certification is the final arbiter: tiles must certify byte-true
    counts = pds.decode_tiles("r0550", policy="weighted_sum")
    assert counts["certified"] >= 8, counts
    # F9 backstop: verify certified payloads against the real frame
    sys.path.insert(0, str(ROOT / "experiments/018-confetti-c3-play"))
    import gen_e018
    vspec = gen_e018.make_vspec()
    data = gen_e018.make_data(vspec)
    framed = fountain.encode_volume_pages(data, vspec)[0]
    user = np.asarray(fountain.volume_encode(data, vspec).page_user_bits[0])
    gtmap = {tuple(e["tile_yx"]): (e["user_offset"], e["user_bits"])
             for e in framed["per_tile"]}
    for t, st in pds.tiles.items():
        if st.status == "certified" and st.payload_bits is not None:
            off, cap = gtmap[t]
            assert np.array_equal(
                st.payload_bits, user[off:off + st.payload_bits.size]), t


def test_phantom_sliver_refused():
    """A toner-free paper sliver must be refused by the chain (0-false)."""
    gen = np.random.default_rng(77)
    sliver = np.full((30 * PPC, 240 * PPC), PAPER, np.float32)
    sliver += gen.normal(0, 5.0, sliver.shape).astype(np.float32)
    canvas = _canvas([np.clip(sliver, 0, 255)])
    pieces = segment.segment_pieces(canvas, cell_px=8.0, dpi=1600.0)
    backing = segment.estimate_backing(canvas)
    pend = {0: np.ones(tuple(sd.spec.page_cells_yx), bool)}
    for p in pieces:
        res = sd.anchor_place_piece(p, backing, pend, 1600.0, 4)
        assert res is None, "phantom sliver was admitted"


if __name__ == "__main__":
    test_edge_margin_overhang_and_distorted_and_rotated()
    print("PASS edge/affine/rotated")
    test_phantom_sliver_refused()
    print("PASS phantom refusal")
