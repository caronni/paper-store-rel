"""Refine-chain machinery tests (segment.rotate_transform + samplers +
supervised refinement + recal; 016.6). The rotate_transform equivalence
test is LOAD-BEARING: sample_cells_at/refine_on_sites define their
de-rotated frame through it, and a scipy convention change would
silently skew every angle in the piece pipeline."""
import numpy as np
import pytest
from scipy import ndimage

from paperholo import segment


def test_rotate_transform_matches_ndimage_rotate():
    rng = np.random.default_rng(7)          # test-only rng
    a = ndimage.gaussian_filter(rng.normal(size=(160, 130)), 3.0)
    for ang in (17.3, -8.6, 44.0):
        ref = ndimage.rotate(a, ang, reshape=True, order=1, cval=0.0,
                             mode="constant")
        M, off, out_shape = segment.rotate_transform(a.shape, ang)
        assert out_shape == ref.shape
        oy, ox = np.meshgrid(np.arange(30, out_shape[0] - 30),
                             np.arange(30, out_shape[1] - 30),
                             indexing="ij")
        coords = (M @ np.array([oy.ravel(), ox.ravel()], np.float64)
                  + off[:, None])
        got = ndimage.map_coordinates(a, coords, order=1, cval=0.0)
        assert np.abs(got - ref[30:-30, 30:-30].ravel()).max() < 1e-6


def _lattice(n_cells: int, pitch: int, seed: int, blur: float = 2.0,
             noise: float = 3.0) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic c2-ish piece through the fixture's optical channel:
    random binary cells at `pitch` px (ink 45 / paper 205), Gaussian PSF
    + sensor noise (gen_confetti_synth's constants). A NOISELESS binary
    lattice is degenerate here twice over: the masked median lands ON a
    class value, and site-center sampling cannot see sub-half-pitch
    angle errors at all (no graded edges) — both measured while writing
    these tests."""
    rng = np.random.default_rng(seed)
    cells = (rng.random((n_cells, n_cells)) < 0.5).astype(np.uint8)
    img = np.where(np.kron(cells, np.ones((pitch, pitch))) > 0,
                   45.0, 205.0).astype(np.float32)
    img = ndimage.gaussian_filter(img, blur)
    img = img + rng.normal(0.0, noise, img.shape).astype(np.float32)
    return img, cells


def test_sample_cells_at_recovers_axis_aligned_lattice():
    img, cells = _lattice(40, 8, seed=3)
    gmask = np.ones_like(img, bool)
    got = segment.sample_cells_at(img, gmask, 250.0, 0.0, 8.0, 0.0, 0.0)
    assert got is not None
    means, kmask, mid = got
    bits = (means < mid).astype(np.uint8)
    assert (bits[:40, :40] == cells).mean() > 0.995


def test_refine_on_sites_recovers_known_angle():
    img, cells = _lattice(142, 8, seed=5)    # ~12 mm c2 piece
    true_ang = 0.35                          # inside the search span
    rot = ndimage.rotate(img, -true_ang, reshape=True, order=3,
                         cval=250.0, mode="constant")
    gmask = np.ones_like(rot, bool)
    # sites: every 3rd cell as a labeled reference, values = ground truth
    sij = np.array([(i, j) for i in range(0, 142, 3)
                    for j in range(0, 142, 3)])
    sv = cells[sij[:, 0], sij[:, 1]]
    # production-faithful: the phase is locked at the ESTIMATE (here 0.0,
    # i.e. the estimator missed the 0.35 entirely); refinement must find
    # the angle from there with the phase staying meaningful (anchored
    # frames)
    M, off, oshape = segment.rotate_transform(rot.shape, 0.0)
    mid = float(np.median(rot))
    ph = segment.phase_scan_glass(rot, gmask.astype(np.float32), mid,
                                  250.0, M, off, oshape, 8.0)
    assert ph is not None
    _, dy0, dx0 = ph
    ang, dyf, dxf, meta = segment.refine_on_sites(
        rot, gmask, 250.0, 0.0, 8.0, dy0, dx0, sij, sv,
        ang_span=0.6, ang_step=0.05)
    assert abs(ang - true_ang) <= 0.1        # within two search steps
    assert meta["heldout_post"] <= meta["heldout_pre"] + 1e-9


def test_recal_llrs_from_labels_sign_and_guards():
    rng = np.random.default_rng(11)
    means = np.concatenate([rng.normal(60, 8, 200),
                            rng.normal(200, 8, 200)]).reshape(20, 20)
    sel = np.zeros((20, 20), bool)
    sel.ravel()[::3] = True
    vals = (means[sel] < 128).astype(np.uint8)   # ink = dark
    llr = segment.recal_llrs_from_labels(means, sel, vals)
    assert llr is not None
    assert ((llr > 0) == (means < 128)).mean() > 0.99   # positive = ink
    # degenerate fit (labels inverted -> "ink" brighter) must refuse
    assert segment.recal_llrs_from_labels(means, sel, 1 - vals) is None
    # too few labels must refuse
    tiny = np.zeros((20, 20), bool)
    tiny[0, :5] = True
    assert segment.recal_llrs_from_labels(
        means, tiny, (means[tiny] < 128).astype(np.uint8)) is None


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
