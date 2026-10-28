"""The shared compact roundtrip fixture (one genuine 7x7-tile c3 volume).

Extracted from the retired ``_qualify_production_roundtrip`` battery
(Phase 7, PAYLOAD-REWORK-PLAN 7.2): the 4-case pathological battery is
replaced by the bounded phased end-to-end
(``test_phased_roundtrip_e2e.py``), while this fixture builder remains
the common footing for the placement null batteries, the multicapture /
small-scrap / frontier / phased-schedule pins, and the benches.

It builds a genuine format-v1 volume with the active generator, renders
the composed dot field into its format-derived page raster, and leaves
payload bytes, the generated page number, and generator intermediates on
the test side.  The small page geometry keeps tests practical without
changing any format or receiver algorithm: 49 ordinary 64x64-cell tiles,
the measured c3-r0550/q=0.50 profile class, metadata trust-48 cleared.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from holo.core import fountain
from holo.format.descriptor import FormatSpec, get_coding
from holo.gen.compose import cells_to_dots, compose_page_cells
from holo.gen.emit import METADATA_VERSION, source_packed_for
from holo.gen.plan import VolumePlan, plan_volume


_DPI = 600.0
_Q = 0.50
_PAPER = np.uint8(245)
_INK = np.uint8(35)


@dataclass(frozen=True, slots=True)
class _Fixture:
    spec: FormatSpec
    plan: VolumePlan
    payload: bytes
    raster: np.ndarray


def _spec() -> FormatSpec:
    """A genuine, compact 7x7-tile c3 row clearing metadata trust-48."""
    spec = FormatSpec(
        get_coding("c3-r0550"), "qualification-60x60",
        (60.0, 60.0), 0.0,
    )
    if spec.layout.tiles_yx != (7, 7):
        raise AssertionError(
            f"qualification geometry drifted to {spec.layout.tiles_yx}")
    return spec


def _payload() -> bytes:
    # Fixed non-repeating bytes make accidental truncation/repetition visible.
    return hashlib.sha256(b"holo-track3-production-roundtrip-v1").digest()


def _build_fixture() -> _Fixture:
    spec = _spec()
    payload = _payload()
    plan = plan_volume(spec, len(payload), _Q)
    if plan.n_pages != 1:
        raise AssertionError(
            f"qualification fixture is no longer one page: {plan.n_pages}")
    source = source_packed_for(payload, plan)
    code = fountain.VolumeCode(
        plan.k_total, plan.symbol_bits, spec.seed,
        tiles_per_page=spec.tiles_per_page,
    )
    esis = np.arange(spec.tiles_per_page, dtype=np.int64)
    symbols = code.encode_symbols(source, esis)
    cells = compose_page_cells(
        spec, 0, symbols, plan.k_total, version=METADATA_VERSION)
    dots = cells_to_dots(cells, spec.cell_dots)

    page_x, page_y = spec.layout.page_dots_xy
    raster = np.full((page_y, page_x), _PAPER, np.uint8)
    origin_y, origin_x = spec.layout.origin_dots_yx
    height, width = dots.shape
    raster[origin_y:origin_y + height, origin_x:origin_x + width] = np.where(
        dots != 0, _INK, _PAPER)
    # These tests qualify the scan receiver, not a direct GT-array decoder.
    # A sub-pixel Gaussian is the fixture's explicit optical point-spread
    # model; it changes no geometry and is never used by production code.
    raster = np.ascontiguousarray(ndimage.gaussian_filter(
        raster.astype(np.float32), 0.5
    ))
    raster.setflags(write=False)
    return _Fixture(spec, plan, payload, raster)


__all__ = [
    "_DPI", "_Q", "_PAPER", "_INK", "_Fixture",
    "_build_fixture", "_payload", "_spec",
]
