"""The rectified NCC's correlation search, against its sliding oracle.

``_xcorr_offset_ncc`` used to materialize every candidate patch with a
sliding-window view and contract three ``einsum``s over them.  That cost
is O(shifts x template) and the shipped probe density's template is a
whole 64-cell tile, so the pass spent 12.12 ms per probe there
(INDEPENDENT-PLANES §2.9b).  It now runs as three FFT correlations
(§2.9c), and this module is the oracle that says the answer did not
change.

THE ORACLE IS THE OLD IMPLEMENTATION, copied verbatim from
``color_anchoring`` at 65c12e5 -- the commit before the FFT landed.  It
is deliberately kept nowhere else: there is no runtime switch, because
two implementations that agree are not a choice anyone should be asked
to make.

What is pinned, in the order it matters:

1. **The integer peak is identical.**  Sub-pixel refinement and every
   downstream gate hang off ``argmax``; a peak that moved would be a
   different measurement however close the surrounding numbers were.
2. **The surface agrees to 1e-9**, which the measured worst case beats by
   three orders of magnitude (3.4e-15 on every case with real contrast;
   3.1e-13 on a window with literally no variation, where the
   correlation is 0/0 and both forms return dust below q = 2e-3).
3. **The correlation primitive is a true VALID correlation** -- the
   transform is taken at the window's own length, not the full linear
   length, and the pin is against ``scipy.signal.correlate``'s direct
   method rather than against the FFT reasoning that justifies it.
4. **Low contrast survives.**  The FFT form recovers the patch variance
   from raw moments, which cancels catastrophically on a nearly-constant
   patch; the window is centred first so it does not.  At 1e-9 contrast
   the uncentred form is wrong by 3.7e4 and this is what catches it.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy import signal

from holo.receive.color_anchoring import (
    _valid_correlations,
    _weighted_ncc_surface,
    _xcorr_offset_ncc,
)

#: Every case agrees far inside this; the bar is set where a real
#: regression would have to land to pass, not at the measured noise.
TOLERANCE = 1e-9


# --------------------------------------------------------------- oracle
def _sliding_ncc_surface(
    window: np.ndarray, template: np.ndarray, weight: np.ndarray,
) -> np.ndarray:
    """The pre-FFT sliding weighted NCC surface, verbatim (65c12e5)."""
    wgt = np.asarray(weight, np.float64)
    wsum = float(wgt.sum()) + 1e-9
    centered_template = np.asarray(template, np.float64)
    centered_template = (
        centered_template
        - float((centered_template * wgt).sum()) / wsum
    )
    weighted_template = centered_template * wgt
    th, tw = template.shape
    template_norm = np.sqrt(
        (centered_template * weighted_template).sum()) + 1e-9
    patches = np.lib.stride_tricks.sliding_window_view(
        np.asarray(window, np.float64), (th, tw))
    means = np.einsum(
        "ijab,ab->ij", patches, wgt, optimize=True) / wsum
    centered = patches - means[..., None, None]
    numerator = np.einsum(
        "ijab,ab->ij", centered, weighted_template, optimize=True)
    norm = np.sqrt(np.einsum(
        "ijab,ijab,ab->ij", centered, centered, wgt, optimize=True))
    return numerator / (norm * template_norm + 1e-9)


def _sliding_offset_ncc(
    window: np.ndarray, template: np.ndarray, weight: np.ndarray,
) -> tuple[float, float, float]:
    """The pre-FFT peak + parabola, verbatim (65c12e5)."""
    corr = _sliding_ncc_surface(window, template, weight)
    th, tw = template.shape
    n_y = window.shape[0] - th + 1
    n_x = window.shape[1] - tw + 1
    iy, ix = np.unravel_index(int(np.argmax(corr)), corr.shape)

    def parabola(values: np.ndarray, index: int) -> float:
        if 0 < index < values.size - 1:
            left, center, right = values[index - 1:index + 2]
            denominator = left - 2.0 * center + right
            if abs(float(denominator)) > 1e-12:
                return float(np.clip(
                    (left - right) / (2.0 * denominator), -0.5, 0.5))
        return 0.0

    return (
        iy + parabola(corr[:, ix], iy) - (n_y - 1) / 2.0,
        ix + parabola(corr[iy, :], ix) - (n_x - 1) / 2.0,
        float(corr[iy, ix]),
    )


# ------------------------------------------------------------- fixtures
KINDS = ("dense", "masked", "anchor", "inverted", "noise", "flat")


def _case(rng: np.random.Generator, kind: str):
    """One randomized (window, template, weights) triple in probe shape.

    The template is a ``np.kron`` of cell bits exactly the way
    ``_rectified_ncc`` builds one, at a random RECTANGULAR extent from a
    3-cell anchor neighbourhood to a whole 64-cell tile, at each of the
    three rectified cell pitches the codings use.
    """
    cells_h = int(rng.integers(3, 66))
    cells_w = int(rng.integers(3, 66))
    cell_px = int(rng.choice((2, 4, 6)))
    max_shift = max(2, round(5 * cell_px / 6.0))
    bits = rng.integers(0, 2, (cells_h, cells_w)).astype(np.float64)
    if kind == "inverted":
        bits = 1.0 - bits
    template = np.kron(1.0 - bits, np.ones((cell_px, cell_px)))
    if kind == "masked":
        # A TILE_FRAGMENT's 0/1 mask: cells outside the covered tile.
        cell_weight = (rng.random((cells_h, cells_w)) > 0.3).astype(np.float64)
    elif kind == "anchor":
        # ``_measure_anchor``'s soft weights: unconfident cells at 0.05.
        cell_weight = np.where(
            rng.random((cells_h, cells_w)) > 0.5, 1.0, 0.05)
    else:
        cell_weight = np.ones((cells_h, cells_w))
    weight = np.kron(cell_weight, np.ones((cell_px, cell_px)))
    shape = (cells_h * cell_px + 2 * max_shift,
             cells_w * cell_px + 2 * max_shift)
    if kind == "flat":
        window = np.full(shape, 0.5)
    elif kind == "noise":
        window = rng.random(shape)
    else:
        window = 0.15 * rng.random(shape)
        offset_y = int(rng.integers(0, 2 * max_shift + 1))
        offset_x = int(rng.integers(0, 2 * max_shift + 1))
        window[offset_y:offset_y + template.shape[0],
               offset_x:offset_x + template.shape[1]] += 0.7 * template
    return window, template, weight


# ------------------------------------------------------------ the claims
@pytest.mark.parametrize("kind", KINDS)
def test_the_fft_surface_matches_the_sliding_oracle(kind: str) -> None:
    """Claims 1 and 2, over randomized templates of every shape."""
    rng = np.random.default_rng(0x5C0FF + KINDS.index(kind))
    worst = 0.0
    for _ in range(24):
        window, template, weight = _case(rng, kind)
        oracle = _sliding_ncc_surface(window, template, weight)
        measured = _weighted_ncc_surface(window, template, weight)
        assert measured.shape == oracle.shape
        assert int(np.argmax(measured)) == int(np.argmax(oracle)), kind
        worst = max(worst, float(np.abs(measured - oracle).max()))
    assert worst < TOLERANCE, f"{kind}: {worst:.3e}"


@pytest.mark.parametrize("kind", KINDS)
def test_the_offset_and_quality_match_the_sliding_oracle(kind: str) -> None:
    """The same claim at the seam every caller actually reads."""
    rng = np.random.default_rng(0xDE17A + KINDS.index(kind))
    for _ in range(16):
        window, template, weight = _case(rng, kind)
        oracle = _sliding_offset_ncc(window, template, weight)
        measured = _xcorr_offset_ncc(window, template, weight)
        for got, want in zip(measured, oracle, strict=True):
            assert got == pytest.approx(want, abs=TOLERANCE), kind


def test_the_valid_correlation_is_a_correlation() -> None:
    """Claim 3: the transform length is short, and it is still exact.

    The FFT is taken at the WINDOW's own ``next_fast_len``, not the full
    linear length, on the argument that circular wrap lands strictly
    before the valid region's first index.  That argument is checked here
    against a direct-method correlation, at deliberately awkward shapes
    where a padding mistake would show.
    """
    rng = np.random.default_rng(0xC0121)
    for shape, kernel_shape in (
        ((18, 18), (12, 12)), ((262, 166), (256, 160)),
        ((40, 40), (30, 30)), ((126, 262), (120, 256)), ((13, 29), (7, 23)),
    ):
        image = rng.random(shape)
        kernel = rng.random(kernel_shape)
        valid = (shape[0] - kernel_shape[0] + 1,
                 shape[1] - kernel_shape[1] + 1)
        measured = _valid_correlations(
            image[None], kernel[None], ((0, 0),), valid)[0]
        expected = signal.correlate(
            image, kernel, mode="valid", method="direct")
        assert measured.shape == expected.shape == valid
        assert np.abs(measured - expected).max() < 1e-9

    # ...and one batched call is the same as several single ones.
    images = rng.random((2, 40, 40))
    kernels = rng.random((2, 30, 30))
    batched = _valid_correlations(
        images, kernels, ((0, 0), (0, 1), (1, 1)), (11, 11))
    for row, (image, kernel) in enumerate(((0, 0), (0, 1), (1, 1))):
        single = _valid_correlations(
            images[image][None], kernels[kernel][None], ((0, 0),), (11, 11))
        assert np.array_equal(batched[row], single[0])


@pytest.mark.parametrize("contrast", (1e-3, 1e-6, 1e-9))
def test_a_low_contrast_patch_survives_the_raw_moment_cancellation(
    contrast: float,
) -> None:
    """Claim 4: the window is centred before the moments are taken.

    A weighted NCC is invariant to a constant added to the patch, so a
    correct implementation reads the same correlation off a template
    whose contrast is 1e-9 of the mean level as off one at 1e-1.  The
    RAW second moment is not invariant: it differences quantities of
    size ``mu^2 * W`` to recover ``contrast^2 * W``.  Uncentred, this
    case is wrong by 3.7e4 at 1e-9 contrast; centred it is exact.
    """
    rng = np.random.default_rng(0x10C0)
    cells, cell_px, max_shift = 64, 6, 5
    bits = rng.integers(0, 2, (cells, cells)).astype(np.float64)
    template = np.kron(1.0 - bits, np.ones((cell_px, cell_px)))
    weight = np.ones_like(template)
    window = np.full(
        (cells * cell_px + 2 * max_shift,) * 2, 0.5)
    window[max_shift:max_shift + template.shape[0],
           max_shift:max_shift + template.shape[1]] += contrast * template

    oracle = _sliding_ncc_surface(window, template, weight)
    measured = _weighted_ncc_surface(window, template, weight)
    # The signal is real at every contrast: the oracle locks on to it.
    # (Its own centring loses digits down here too -- 1.0 to 3e-5 at
    # 1e-9 contrast -- which is exactly why the bar below is agreement
    # WITH the oracle and not agreement with the ideal.)
    assert oracle.max() == pytest.approx(1.0, abs=1e-3)
    assert int(np.argmax(measured)) == int(np.argmax(oracle))
    assert np.abs(measured - oracle).max() < TOLERANCE


def test_a_window_with_no_variation_is_dust_in_both_forms() -> None:
    """The 0/0 case, and the reason it is nobody's problem.

    A perfectly constant patch has no correlation with anything; both
    forms return numerical dust, and every caller's quality floor
    (``_ANCHOR_MIN_Q`` 0.10, ``probe_min_quality`` 0.30) is orders above
    it.  Pinned so a future change that starts returning a CONFIDENT
    number here is caught.
    """
    rng = np.random.default_rng(0xF1A7)
    bits = rng.integers(0, 2, (32, 32)).astype(np.float64)
    template = np.kron(1.0 - bits, np.ones((4, 4)))
    weight = np.ones_like(template)
    window = np.full((template.shape[0] + 8, template.shape[1] + 8), 0.5)

    oracle = _sliding_offset_ncc(window, template, weight)
    measured = _xcorr_offset_ncc(window, template, weight)
    assert abs(oracle[2]) < 2e-3 and abs(measured[2]) < 2e-3
    assert measured[2] == pytest.approx(oracle[2], abs=TOLERANCE)
