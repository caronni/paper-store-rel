"""§15.6 padded placement (allow_overhang) — the e018 018.2/018.3 fix for
page-edge pieces whose true origin is excluded by 'valid'-mode search.

Covers: exact placement at negative origins and far-edge overhang;
decoy refusal under the enlarged padded candidate set; legacy-mode
byte-compatibility; overlap_slices clipping; fragment_pilot_sites on an
overhanging placement."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from paperholo import place
from paperholo.compose import ComposeSpec
from paperholo.pilots import PilotLayout

SEED = b"paper-store/test-overhang"
SPEC = ComposeSpec(layout_version=3, pilot=PilotLayout(version=3))


def _gt_pilot_bits(h, w, oy, ox, rng):
    """Fragment bits = pilot-field values where on-page, random elsewhere
    (payload cells random too — the placer only reads pilot sites)."""
    vals, smask = place.pilot_field(SPEC, SEED, 0)
    b = rng.integers(0, 2, (h, w), dtype=np.uint8)
    sl = place.overlap_slices((oy, ox), (h, w), vals.shape)
    assert sl is not None
    pys, pxs, fys, fxs = sl
    sub_v = vals[pys, pxs]
    sub_m = smask[pys, pxs]
    region = b[fys, fxs]
    region[sub_m] = sub_v[sub_m]
    b[fys, fxs] = region
    return b


def test_overhang_places_negative_and_far_edge():
    rng = np.random.default_rng(3)
    H, W = SPEC.page_cells_yx
    for oy, ox in ((-40, -30), (H - 60, 500), (800, W - 55), (700, 900)):
        b = _gt_pilot_bits(150, 150, oy, ox, rng)
        m = np.ones((150, 150), bool)
        pl = place.place_fragment(b, SPEC, SEED, mask=m,
                                  allow_overhang=True)
        assert pl.ok, (oy, ox, pl.mismatch, pl.rival_mismatch)
        assert pl.origin_yx == (oy, ox), (pl.origin_yx, (oy, ox))
        assert pl.mismatch < 0.05
        assert pl.diagnostics["allow_overhang"] is True


def test_valid_mode_unchanged_and_refuses_overhang():
    rng = np.random.default_rng(4)
    H, _ = SPEC.page_cells_yx
    b = _gt_pilot_bits(150, 150, 800, 600, rng)
    m = np.ones((150, 150), bool)
    legacy = place.place_fragment(b, SPEC, SEED, mask=m)
    padded = place.place_fragment(b, SPEC, SEED, mask=m,
                                  allow_overhang=True)
    assert legacy.ok and legacy.origin_yx == (800, 600)
    assert padded.ok and padded.origin_yx == (800, 600)
    # float32 FFT jitter between the two plan sizes is ~5e-8; anything
    # beyond 1e-6 would indicate a real semantic difference
    assert abs(legacy.mismatch - padded.mismatch) < 1e-6
    # a true bottom-edge fragment cannot place in 'valid' mode
    b2 = _gt_pilot_bits(150, 150, H - 60, 500, rng)
    pl2 = place.place_fragment(b2, SPEC, SEED, mask=m)
    assert pl2.origin_yx != (H - 60, 500)


def test_padded_decoy_refusal():
    """Random bits must refuse under the ENLARGED padded candidate set —
    the §15.6 argument that padding moves the gate toward refusal."""
    rng = np.random.default_rng(5)
    for trial in range(5):
        b = rng.integers(0, 2, (150, 150), dtype=np.uint8)
        pl = place.place_fragment(b, SPEC, SEED,
                                  mask=np.ones((150, 150), bool),
                                  allow_overhang=True)
        assert not pl.ok, (trial, pl.mismatch, pl.rival_mismatch)


def test_overlap_slices():
    # fully inside
    sl = place.overlap_slices((5, 7), (10, 10), (100, 100))
    assert sl == (slice(5, 15), slice(7, 17), slice(0, 10), slice(0, 10))
    # negative origin clips the fragment's leading edge
    sl = place.overlap_slices((-3, -4), (10, 10), (100, 100))
    assert sl == (slice(0, 7), slice(0, 6), slice(3, 10), slice(4, 10))
    # far-edge overhang clips the trailing edge
    sl = place.overlap_slices((95, 96), (10, 10), (100, 100))
    assert sl == (slice(95, 100), slice(96, 100), slice(0, 5), slice(0, 4))
    # empty overlap
    assert place.overlap_slices((200, 0), (10, 10), (100, 100)) is None
    assert place.overlap_slices((-20, 0), (10, 10), (100, 100)) is None


def test_fragment_pilot_sites_overhanging():
    """Sites of an overhanging placement come only from the on-page part
    and agree with the pilot field."""
    rng = np.random.default_rng(6)
    H, _ = SPEC.page_cells_yx
    oy, ox = H - 60, 500
    b = _gt_pilot_bits(150, 150, oy, ox, rng)
    m = np.ones((150, 150), bool)
    pl = place.place_fragment(b, SPEC, SEED, mask=m, allow_overhang=True)
    assert pl.ok and pl.origin_yx == (oy, ox)
    sij, sv = place.fragment_pilot_sites(pl, b.shape, m, SPEC, SEED)
    assert sij.shape[0] > 50
    # every returned site must read the printed value in the fragment bits
    bk = np.rot90(b, pl.rot_k)          # rot_k is 0 here by construction
    got = b[sij[:, 0], sij[:, 1]]
    assert np.array_equal(got, sv)
    # and every site must map on-page
    fys = sij[:, 0]
    assert fys.max() < H - oy


if __name__ == "__main__":
    for fn in (test_overhang_places_negative_and_far_edge,
               test_valid_mode_unchanged_and_refuses_overhang,
               test_padded_decoy_refusal,
               test_overlap_slices,
               test_fragment_pilot_sites_overhanging):
        fn()
        print(f"PASS {fn.__name__}")
