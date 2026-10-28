"""Oracle: holo2.scale_space == holo.receive.scale_space (footings).

Compares the carried leaf against its source on the footing ladder
(``auto_ppc_levels`` as exact Fractions), the affine/point transforms,
and the exact-area decimation itself — byte-exact, for integer AND
non-integer ratios, over grey/RGB and uint8/uint16/float32, including
the chunk-geometry invariance the module promises.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

import holo2.capture.scale_space as h2
from holo.receive import scale_space as h1
from _oracle_fixtures import (  # noqa: F401  (pytest fixtures; rgb_page
    grey_page, holo_sequential, rgb_page,  # and small_rgb derive from the
    small_grey, small_rgb)                 # grey ones, so both come along)

# (native_dpi, cell_factor) -> the ladders DESIGN §5.1 derives per capture.
# 1000 dpi @ c3 is the NON-INTEGER case: ppc 5 -> levels (2, 5/2, 5), whose
# first transform is 5/2 = 2.5 source pixels per output pixel.
#
# ``src/holo`` takes the CELL FACTOR (dots) and divides by its hard-coded
# 600; holo2 takes the printed PITCH and multiplies (C3, RULINGS G4,
# 2026-08-22).  The pairs stay in dots here — they are what the SOURCE
# reads — and :func:`_pitch` converts at the holo2 call, so this file
# proves the two forms agree rather than assuming they do.
LADDERS = [
    (1200, 2), (1200, 3), (4800, 3), (4800, 2), (1000, 3), (600, 2),
    (1200.0, 1), ("2400", 3), (Fraction(4800, 1), 4),
]

#: The engine grid ``src/holo``'s ladder is written against.  It lives
#: HERE, in the oracle, because it is a fact about the SOURCE — holo2's
#: own ladder no longer names it.
SOURCE_ENGINE_DPI = 600


def _pitch(cell_factor) -> Fraction:
    """The printed pitch ``src/holo``'s cell factor means, in inches."""
    return Fraction(int(cell_factor), SOURCE_ENGINE_DPI)

RATIOS = [
    Fraction(1), Fraction(2), Fraction(3), Fraction(4), Fraction(6),
    Fraction(5, 2), Fraction(7, 3), Fraction(3, 2), Fraction(12, 5),
]


@pytest.mark.parametrize("dpi,c", LADDERS, ids=lambda v: str(v))
def test_auto_ppc_levels(dpi, c) -> None:
    levels_one = h1.auto_ppc_levels(dpi, c)
    levels_two = h2.auto_ppc_levels(dpi, _pitch(c))
    assert levels_two == levels_one
    assert all(isinstance(level, Fraction) for level in levels_two)
    assert (h2.native_pixels_per_cell(dpi, _pitch(c))
            == h1.native_pixels_per_cell(dpi, c))
    assert not hasattr(h2, "_PRINT_DPI"), (
        "the engine grid left holo2's footing ladder at C3 (RULINGS G4); "
        "this oracle is what keeps the pitch form equal to the dot form")


@pytest.mark.parametrize("dpi,c", LADDERS, ids=lambda v: str(v))
def test_schedule_levels_and_labels(dpi, c) -> None:
    one = h1.ScaleSchedule.auto(dpi, c)
    two = h2.ScaleSchedule.auto(dpi, _pitch(c))
    assert len(two.levels) == len(one.levels)
    for a, b in zip(one.levels, two.levels, strict=True):
        assert (b.index, b.ppc, b.dpi) == (a.index, a.ppc, a.dpi)
        assert b.label == a.label
        assert b.is_native == a.is_native
        assert b.transform.source_per_output == a.transform.source_per_output


@pytest.mark.parametrize("ratio", RATIOS, ids=lambda r: f"{r.numerator}_{r.denominator}")
def test_transform_geometry(ratio: Fraction) -> None:
    one, two = h1.AreaPixelTransform(ratio), h2.AreaPixelTransform(ratio)
    assert two.is_identity == one.is_identity
    assert two.is_integer_box == one.is_integer_box
    for length in (0, 1, 7, 599, 1024, 4801):
        assert two.output_length(length) == one.output_length(length)
    for shape in ((600, 1000), (1024, 1024, 3)):
        assert two.output_shape(shape) == one.output_shape(shape)

    points = np.array([[0.0, 0.0], [1.5, 2.5], [599.0, 1023.0]])
    affine = np.array([[3.0, 0.25, 11.5], [-0.125, 3.5, -7.25]])
    for name in ("source_to_view_points", "view_to_source_points"):
        assert (getattr(two, name)(points).tobytes()
                == getattr(one, name)(points).tobytes())
    for name in ("source_to_view_affine", "view_to_source_affine"):
        assert (getattr(two, name)(affine).tobytes()
                == getattr(one, name)(affine).tobytes())


def _sources(grey: np.ndarray, rgb: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "uint8_grey": grey,
        "uint8_rgb": rgb,
        "uint16_grey": (grey.astype(np.uint16) * 257),
        "uint16_rgb": (rgb.astype(np.uint16) * 257),
        "float32_grey": grey.astype(np.float32) / np.float32(255.0),
        "float32_rgb": rgb.astype(np.float32) / np.float32(255.0),
        "int16_grey": (grey.astype(np.int16) - 128),
    }


@pytest.mark.parametrize("ratio", RATIOS, ids=lambda r: f"{r.numerator}_{r.denominator}")
@pytest.mark.parametrize(
    "kind",
    ["uint8_grey", "uint8_rgb", "uint16_grey", "uint16_rgb",
     "float32_grey", "float32_rgb", "int16_grey"],
)
def test_area_decimate_bytes(
    small_grey: np.ndarray, small_rgb: np.ndarray, ratio: Fraction, kind: str
) -> None:
    source = _sources(small_grey, small_rgb)[kind]
    one = h1.area_decimate(source, h1.AreaPixelTransform(ratio))
    two = h2.area_decimate(source, h2.AreaPixelTransform(ratio))
    assert two.dtype == one.dtype == source.dtype
    assert two.shape == one.shape
    assert two.tobytes() == one.tobytes()


@pytest.mark.parametrize("ratio", [Fraction(2), Fraction(5, 2)],
                         ids=["integer", "rational"])
def test_area_decimate_rgb_bytes(rgb_page: np.ndarray, ratio: Fraction) -> None:
    one = h1.area_decimate_rgb(rgb_page, h1.AreaPixelTransform(ratio))
    two = h2.area_decimate_rgb(rgb_page, h2.AreaPixelTransform(ratio))
    assert two.shape == one.shape == one.shape[:2] + (3,)
    assert two.tobytes() == one.tobytes()


@pytest.mark.parametrize("ratio", [Fraction(3), Fraction(7, 3)],
                         ids=["integer", "rational"])
@pytest.mark.parametrize("chunk", [(1, 1), (7, 13), (128, 2048), (4096, 4096)])
def test_chunk_geometry_cannot_change_values(
    small_grey: np.ndarray, ratio: Fraction, chunk: tuple[int, int]
) -> None:
    """Chunking is a work-set control; the leaf owes identical bytes."""
    rows, cols = chunk
    # A crop, because the 1x1 chunk case is one tile per OUTPUT pixel.
    source = small_grey[:120, :150]
    one = h1.area_decimate(
        source, h1.AreaPixelTransform(ratio), chunk_rows=rows, chunk_cols=cols)
    two = h2.area_decimate(
        source, h2.AreaPixelTransform(ratio), chunk_rows=rows, chunk_cols=cols)
    reference = h2.area_decimate(source, h2.AreaPixelTransform(ratio))
    assert two.tobytes() == one.tobytes() == reference.tobytes()


@pytest.mark.parametrize("ratio", [Fraction(4), Fraction(12, 5)],
                         ids=["integer", "rational"])
def test_chunk_slices_and_patches(small_grey: np.ndarray, ratio: Fraction) -> None:
    chunks_one = list(h1.iter_area_decimation_chunks(
        small_grey, h1.AreaPixelTransform(ratio), chunk_rows=13, chunk_cols=29))
    chunks_two = list(h2.iter_area_decimation_chunks(
        small_grey, h2.AreaPixelTransform(ratio), chunk_rows=13, chunk_cols=29))
    assert len(chunks_two) == len(chunks_one)
    for (slice_one, patch_one), (slice_two, patch_two) in zip(
            chunks_one, chunks_two, strict=True):
        assert slice_two == slice_one
        assert patch_two.tobytes() == patch_one.tobytes()


def test_derive_scale_levels_whole_schedule(small_grey: np.ndarray) -> None:
    """The full per-capture footing derivation, level by level."""
    levels_one = list(h1.derive_scale_levels(
        small_grey, h1.ScaleSchedule.auto(1000, 3)))
    levels_two = list(h2.derive_scale_levels(
        small_grey, h2.ScaleSchedule.auto(1000, _pitch(3))))
    assert [level.label for level, _ in levels_two] == [
        level.label for level, _ in levels_one]
    assert len(levels_two) == 3  # (2, 5/2, 5) ppc: the non-integer ladder
    for (level_one, view_one), (level_two, view_two) in zip(
            levels_one, levels_two, strict=True):
        assert level_two.ppc == level_one.ppc
        assert view_two.tobytes() == view_one.tobytes()


def test_arbitrary_precision_fallbacks_match(small_grey: np.ndarray) -> None:
    """Both python fallbacks: integer-accumulator and coordinate overflow.

    The ratios are ~4 either way, so the values are ordinary; what the
    huge numerator/denominator select is the exact-arithmetic branch.
    """
    crop = small_grey[:64, :64]

    # Integer dtype, accumulator overflow -> _integer_area_tile_python.
    integer_ratio = Fraction(4 * 10**8 + 1, 10**8)
    assert not h1._integer_accumulator_fits(crop, integer_ratio)
    one = h1.area_decimate(crop, h1.AreaPixelTransform(integer_ratio))
    two = h2.area_decimate(crop, h2.AreaPixelTransform(integer_ratio))
    assert two.tobytes() == one.tobytes()

    # Float dtype, coordinate overflow -> _float_area_tile_python.
    float_ratio = Fraction(4 * 10**18 + 1, 10**18)
    floats = crop.astype(np.float32)
    assert not h1._coordinates_fit_int64(floats.shape, 16, 16, float_ratio)
    one = h1.area_decimate(floats, h1.AreaPixelTransform(float_ratio))
    two = h2.area_decimate(floats, h2.AreaPixelTransform(float_ratio))
    assert two.tobytes() == one.tobytes()


@pytest.mark.parametrize(
    "case", ["upsample", "zero", "negative", "nan", "bad_chunk", "shape_3d"])
def test_refusals_match(case: str, small_grey: np.ndarray) -> None:
    if case == "shape_3d":
        with pytest.raises(ValueError) as excinfo_one:
            h1.AreaPixelTransform(Fraction(2)).output_shape((1,))
        with pytest.raises(ValueError) as excinfo_two:
            h2.AreaPixelTransform(Fraction(2)).output_shape((1,))
    elif case == "bad_chunk":
        with pytest.raises(ValueError) as excinfo_one:
            h1.area_decimate(small_grey, h1.AreaPixelTransform(2), chunk_rows=0)
        with pytest.raises(ValueError) as excinfo_two:
            h2.area_decimate(small_grey, h2.AreaPixelTransform(2), chunk_rows=0)
    else:
        value = {"upsample": Fraction(1, 2), "zero": 0,
                 "negative": -2, "nan": float("nan")}[case]
        with pytest.raises(ValueError) as excinfo_one:
            h1.AreaPixelTransform(value)
        with pytest.raises(ValueError) as excinfo_two:
            h2.AreaPixelTransform(value)
    assert str(excinfo_two.value) == str(excinfo_one.value)
