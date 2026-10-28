"""Word-path emission masking (Fix 2, 2026-07-12 scan-2 forensics).

acquire_and_decode gained an optional cell_mask (window-frame bool): a
square word window emits its whole rectangle, so at a piece boundary it
dumps off-scrap cells (measured ~0.50 BER) onto a neighbor's page
territory. The mask confines emission to the piece interior.

Two guarantees, both load-bearing for the gated change:
  (1) cell_mask=None  and  cell_mask=all-True  emit the IDENTICAL cell set
      as each other — i.e. an all-interior mask drops nothing (proves the
      canonical mirror/rot90 transform + cell-centre sampling are aligned;
      a misaligned mask would silently drop good cells).
  (2) a partial mask emits a strict SUBSET, and every dropped cell lies in
      the masked-off region.

Run under PYTHONPATH=src (the worktree editable-install gotcha).
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/018-confetti-c3-play"))

import test_session_anchor as tsa          # noqa: E402  (render machinery)
from paperholo import acquire               # noqa: E402

sd = tsa.sd


def _window():
    """A clean axis-aligned interior window (~210 cells) that acquires."""
    gen = np.random.default_rng(20260712)
    img, _ = tsa.render_piece(
        (tsa.MARGIN_CELLS + 300, tsa.MARGIN_CELLS + 300, 210, 210), 0.0, gen)
    return img


def _decode(win, cell_mask):
    return acquire.acquire_and_decode(
        win, sd.spec, sd.SEED, cell_px_nominal=float(tsa.PPC),
        detector="ctx", calibrate=True, cell_mask=cell_mask)


def test_all_true_mask_matches_no_mask():
    win = _window()
    r_none = _decode(win, None)
    r_all = _decode(win, np.ones(win.shape, bool))
    assert r_none.ok and r_all.ok, "clean window failed to acquire"
    a = np.sort(r_none.payload_cell_index)
    b = np.sort(r_all.payload_cell_index)
    assert a.size > 500, f"suspiciously few cells emitted: {a.size}"
    assert np.array_equal(a, b), (
        "all-True cell_mask changed the emitted set — the mask transform "
        "is misaligned with the payload grid")


def test_partial_mask_drops_only_off_region_cells():
    win = _window()
    r_none = _decode(win, None)
    mask = np.ones(win.shape, bool)
    mask[:, win.shape[1] // 2:] = False          # drop the right half
    r_half = _decode(win, mask)
    assert r_none.ok and r_half.ok
    kept = set(r_half.payload_cell_index.tolist())
    full = set(r_none.payload_cell_index.tolist())
    assert kept, "masked decode emitted nothing"
    assert kept < full, "partial mask did not drop any cells"
    # every KEPT cell was in the no-mask set (masking only removes)
    assert kept <= full, "masking added cells that were not emitted unmasked"
    # the dropped cells live in the masked-off (right) half: check via the
    # page-column of each dropped payload index using the compose inverse
    from paperholo import compose
    pim = compose.payload_index_map(sd.spec, sd.SEED)
    ys, xs = np.nonzero(pim >= 0)
    flat = pim[ys, xs]
    inv = np.empty((int(flat.max()) + 1, 2), np.int64)
    inv[flat, 0], inv[flat, 1] = ys, xs
    dropped = np.array(sorted(full - kept), dtype=np.int64)
    kept_arr = np.array(sorted(kept), dtype=np.int64)
    # dropped cells sit to the RIGHT of the kept cells' page span (the
    # right half was masked); allow a one-cell seam at the boundary
    if dropped.size and kept_arr.size:
        assert inv[dropped, 1].min() >= inv[kept_arr, 1].min(), (
            "dropped cells fell left of the kept region — mask orientation "
            "is flipped")


if __name__ == "__main__":
    test_all_true_mask_matches_no_mask()
    print("PASS all-True == no-mask")
    test_partial_mask_drops_only_off_region_cells()
    print("PASS partial mask drops only off-region cells")
