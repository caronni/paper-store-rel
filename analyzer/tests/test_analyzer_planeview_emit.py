"""The emission: does the unmixed grey page carry the plane and nothing else.

The claim under test is `spectral`'s and the module docstring's: the
projection functional annihilates the two sibling planes IN THE MEAN, so
a pixel with the target plane's ink comes out dark whatever M and Y are
doing there, and a pixel without it comes out at paper.  These tests
plant exactly that raster — all eight printed states, in blocks — and
read the emitted u8 page back.
"""

from __future__ import annotations

import numpy as np
import pytest

from holo.receiver.lib import spectral

from analyzer.planeview import emit as emit_mod

#: A plausible CMY-on-paper mixing model in `raw/255` units: cyan
#: darkens red most, magenta green, yellow blue, and every ink darkens
#: its neighbours a little (which is why the raw channel is not the
#: plane — `spectral`'s own measured point).
#: Paper sits well below white on purpose: a platen scan's lid and bare
#: glass are BRIGHTER than the sheet, and `score_span` has to be able to
#: tell them apart.  Every one of the eight printed states still lands
#: inside [0, 1] under COEF below.
PAPER = np.array([0.70, 0.68, 0.66])
COEF = np.array([[-0.42, -0.06, -0.02],      # red   from C, M, Y
                 [-0.08, -0.36, -0.05],      # green
                 [-0.03, -0.21, -0.34]])     # blue


def _states(n: int, rng) -> np.ndarray:
    return rng.integers(0, 2, (n, 3)).astype(np.uint8)


def _values(bits: np.ndarray, rng, noise: float = 0.004) -> np.ndarray:
    return (PAPER[None, :] + bits.astype(np.float64) @ COEF.T
            + rng.normal(0.0, noise, (bits.shape[0], 3)))


@pytest.fixture(scope="module")
def fitted():
    rng = np.random.default_rng(4242)
    bits = _states(2000, rng)
    mix = spectral.fit_plane_mix(_values(bits, rng), bits,
                                 np.ones(bits.shape, bool))
    assert mix.accepted, mix.reason
    return mix


def test_the_functional_annihilates_the_siblings_in_the_mean(fitted):
    """`w · m_sibling = 0`, `w · m_plane = 1` — the definition, measured."""
    for plane in range(3):
        w = np.asarray(fitted.projections)[:, plane]
        gains = np.asarray(fitted.coef).T @ w
        assert gains[plane] == pytest.approx(1.0, abs=1e-6)
        for sibling in spectral.siblings_of(plane):
            assert gains[sibling] == pytest.approx(0.0, abs=1e-6)


#: The planted tests give themselves headroom so the assertion is about
#: the annihilation, not about the 5-count margin the real span map uses.
TEST_BRIGHT_U8 = 200.0
TEST_DARK_U8 = 60.0


def _affine(fitted, plane_index, bright=0.0, dark=1.0):
    return emit_mod.pixel_affine(fitted, plane_index, bright, dark,
                                 bright_u8=TEST_BRIGHT_U8,
                                 dark_u8=TEST_DARK_U8)


def test_the_pixel_map_sends_paper_bright_and_ink_dark(fitted):
    coefficients, constant, _w, _offset = _affine(fitted, 0)
    paper_rgb = PAPER * 255.0
    ink_rgb = (PAPER + COEF[:, 0]) * 255.0
    assert (paper_rgb @ coefficients + constant) == pytest.approx(
        TEST_BRIGHT_U8, abs=0.5)
    assert (ink_rgb @ coefficients + constant) == pytest.approx(
        TEST_DARK_U8, abs=0.5)
    assert emit_mod.DARK_U8 < emit_mod.BRIGHT_U8    # ink is DARK


def test_the_pixel_map_refuses_a_collapsed_anchor_pair(fitted):
    with pytest.raises(emit_mod.EmitError):
        emit_mod.pixel_affine(fitted, 0, 0.4, 0.4)
    with pytest.raises(emit_mod.EmitError):
        emit_mod.pixel_affine(fitted, 0, 0.9, 0.4)


def _planted_raster(rng, block: int = 12):
    """A raster of 8x8 blocks, each one of the eight printed states."""
    states = np.arange(8, dtype=np.uint8)
    bits = ((states[:, None] >> np.arange(3, dtype=np.uint8)) & 1)
    grid = rng.permutation(np.tile(states, 8)).reshape(8, 8)
    plane_bits = bits[grid]                                # (8, 8, 3)
    values = (PAPER[None, None, :]
              + plane_bits.astype(np.float64) @ COEF.T
              + rng.normal(0.0, 0.004, plane_bits.shape))
    raster = np.clip(np.rint(values * 255.0), 0, 255).astype(np.uint8)
    big = np.repeat(np.repeat(raster, block, axis=0), block, axis=1)
    truth = np.repeat(np.repeat(grid, block, axis=0), block, axis=1)
    return big, truth, bits


@pytest.mark.parametrize("plane_index", [0, 1, 2])
def test_a_planted_page_comes_back_as_that_plane_alone(fitted, plane_index):
    rng = np.random.default_rng(97 + plane_index)
    raster, truth, bits = _planted_raster(rng)
    coefficients, constant, _w, _offset = _affine(fitted, plane_index)
    page, low, high, histogram = emit_mod._write_plane_raster(
        (raster[..., 0], raster[..., 1], raster[..., 2]),
        coefficients, constant)
    assert page.dtype == np.uint8
    assert page.shape == raster.shape[:2]
    has_ink = bits[truth][..., plane_index] == 1
    inked = page[has_ink].astype(np.float64)
    clean = page[~has_ink].astype(np.float64)
    assert clean.mean() == pytest.approx(TEST_BRIGHT_U8, abs=3.0)
    assert inked.mean() == pytest.approx(TEST_DARK_U8, abs=3.0)
    # the separation is what the receiver reads; nothing may straddle it
    assert clean.min() > inked.max()
    assert low == 0.0 and high == 0.0
    assert histogram.sum() == page.size
    p1, _p50, p99 = emit_mod.level_percentiles(histogram)
    assert abs(p1 - TEST_DARK_U8) <= 8, p1
    assert abs(p99 - TEST_BRIGHT_U8) <= 8, p99


def test_the_siblings_do_not_move_the_emitted_level(fitted):
    """The whole point: C reads the same under every M, Y combination."""
    rng = np.random.default_rng(5)
    raster, truth, bits = _planted_raster(rng)
    coefficients, constant, _w, _offset = _affine(fitted, 0)
    page, _low, _high, _hist = emit_mod._write_plane_raster(
        (raster[..., 0], raster[..., 1], raster[..., 2]),
        coefficients, constant)
    for target in (0, 1):
        levels = [page[truth == state].mean()
                  for state in range(8)
                  if bits[state, 0] == target and np.any(truth == state)]
        assert max(levels) - min(levels) < 4.0, levels


def test_the_row_block_pass_is_block_size_independent(fitted, monkeypatch):
    rng = np.random.default_rng(11)
    raster, _truth, _bits = _planted_raster(rng, block=7)
    coefficients, constant, _w, _offset = _affine(fitted, 2)
    planes = (raster[..., 0], raster[..., 1], raster[..., 2])
    whole, _l, _h, hist_whole = emit_mod._write_plane_raster(
        planes, coefficients, constant)
    monkeypatch.setattr(emit_mod, "BLOCK_BYTES", 1)
    blocked, _l, _h, hist_blocked = emit_mod._write_plane_raster(
        planes, coefficients, constant)
    assert np.array_equal(whole, blocked)
    assert np.array_equal(hist_whole, hist_blocked)


def test_clipping_is_counted_when_the_anchors_are_squeezed(fitted):
    rng = np.random.default_rng(13)
    raster, _truth, _bits = _planted_raster(rng)
    # an ink anchor a tenth of a layer wide blows the scale up 10x, so
    # every inked pixel lands far below zero and must be COUNTED
    coefficients, constant, _w, _offset = _affine(fitted, 0, dark=0.1)
    _page, low, high, _hist = emit_mod._write_plane_raster(
        (raster[..., 0], raster[..., 1], raster[..., 2]),
        coefficients, constant)
    assert low > 0.3
    assert 0.0 <= high <= 1.0


def test_the_span_pass_finds_the_sheet_and_ignores_the_platen(fitted):
    """The measured defect of 2026-09-03: the anchors are not the gain.

    A raster of sheet plus a bright lid; the span must be the SHEET's
    per-pixel range, not the lid's, or the printed field is compressed
    into a handful of levels.
    """
    rng = np.random.default_rng(21)
    raster, truth, bits = _planted_raster(rng, block=6)
    lid = np.full((raster.shape[0], raster.shape[1] * 3, 3), 255, np.uint8)
    wide = np.concatenate((raster, lid), axis=1)
    functional, offset = emit_mod.plane_functional(fitted, 0)
    low, high, counted = emit_mod.score_span(
        (wide[..., 0], wide[..., 1], wide[..., 2]), functional, offset,
        paper_anchor=0.0, row_stride=1)
    assert 0 < counted < wide.shape[0] * wide.shape[1] * 0.5
    assert low > -emit_mod.SHEET_MARGIN - 0.05
    assert high == pytest.approx(1.0, abs=0.25)
    inked = bits[truth][..., 0] == 1
    coefficients, constant, _w, _o = emit_mod.pixel_affine(fitted, 0, low,
                                                           high)
    page, clipped_low, _high, _hist = emit_mod._write_plane_raster(
        (wide[..., 0], wide[..., 1], wide[..., 2]), coefficients, constant)
    assert clipped_low < 1e-3
    sheet = page[:, :raster.shape[1]]
    assert sheet[inked].mean() < sheet[~inked].mean() - 100.0


def test_the_span_pass_refuses_a_raster_with_no_sheet(fitted):
    lid = np.full((64, 64, 3), 255, np.uint8)
    functional, offset = emit_mod.plane_functional(fitted, 0)
    with pytest.raises(emit_mod.EmitError):
        emit_mod.score_span((lid[..., 0], lid[..., 1], lid[..., 2]),
                            functional, offset, paper_anchor=0.0,
                            row_stride=1)
