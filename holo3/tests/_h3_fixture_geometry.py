"""THE ONLY DOOR to a window pose in fixtures, tests and instruments.

WHY THIS MODULE EXISTS.  ``anchor.Affine`` is one bare
``tuple[float, ...]`` alias serving TWO conventions that differ by half a
cell:

* ``Placement.native_affine`` maps the PAGE's cell INDEX to pixels and
  must NOT carry the half cell, because every consumer adds it
  (``color_region.region_window`` composes ``M @ (page_cell + 0.5) + t``;
  ``calibrate.scan_points_yx`` does the same);
* the affine a ``RegionWindow`` carries, and that ``anchor.pose_points``
  is handed, maps a WINDOW-LOCAL cell index straight to the pixel it
  samples, so it MUST already carry the half cell — ``pose_points`` is a
  plain ``M @ local + t`` and adds nothing.

Nothing in the name or the type separates them.  An author copying
either one had even odds of being wrong, and the wrong half is SILENT: a
plane-common offset hides from every plane-relative comparison, and the
sampler's box aperture turns it into a clean loss of contrast rather
than into anything that looks like a bug.  THREE fixtures were carrying
the corner form on 2026-08-31 — ``measure/uplift_fixture.py``,
``measure/planek_fixture.py`` and
``holo3/tests/test_h3_plugins_color.py`` — and each read every plane at
a QUARTER of its true contrast (measured: 31.5% cell error and fitted
contrast 0.073, against 0.002% and 0.292 on centres).

THE FIX IS UNREPRESENTABILITY, not a fourth guard.  No fixture composes
a window pose by hand any more.  A fixture states its geometry as a
``Placement`` — the same object the receiver's placement rows carry —
and ``window_pose`` runs the PRODUCTION composer over it.  The half cell
is then not a thing a fixture can get wrong, because a fixture never
spells it.

``holo3/tests/test_h3_hygiene.py`` fails the build on any new
hand-rolled pose in ``measure/`` or ``holo3/tests``, naming this module
and ``color_region.region_window`` as the two sanctioned doors.

This module lives under ``holo3/tests`` rather than ``measure/`` for two
reasons: the ``_h3_`` prefix is what keeps the basename globally unique
under pytest's prepend import mode (``test_h3_conventions``), and
``measure`` already imports ``holo3.tests`` freely (``_h3_sims``,
``_h3_facts``) while nothing in ``holo3/tests`` may depend on the
instrument tree.
"""
from __future__ import annotations

import dataclasses
from fractions import Fraction
from types import SimpleNamespace

import numpy as np

from holo3 import data
from holo3.plugins import color_region

Extent = tuple[int, int, int, int]
WindowId = tuple[str, int, int, Extent]


def page_native_affine(pitch_px: float,
                       margin_px: float) -> tuple[float, ...]:
    """The PAGE's cell-index -> pixel map, for ``native_affine``.

    NO HALF CELL, and no per-window origin: both belong to the composer.
    A page laid down as ``margin_px + cell * pitch_px`` blocks has its
    cell (0, 0) block STARTING here, and ``window_pose`` is what aims at
    the centre of it.
    """
    return (float(pitch_px), 0.0, float(margin_px),
            0.0, float(pitch_px), float(margin_px))


def window_placement(window_id: WindowId, native_affine: tuple[float, ...],
                     local_cells_yx: np.ndarray, *,
                     page_origin_yx: tuple[int, int] | None = None,
                     patch_ordinal: int = 0, page: int = 0,
                     region_index: int = 0, rot_k: int = 0,
                     pitch_px: float | None = None,
                     route: str = "fixture") -> data.Placement:
    """One window's geometry, stated the way the receiver states it.

    ``page_origin_yx`` defaults to the window id's own extent origin,
    which is the production invariant: a window's local cell (0, 0) is
    the page cell its extent starts at.  ``pitch_px`` defaults to the
    native affine's own y scale.
    """
    capture_id, level_index, _ordinal, extent = window_id
    origin = (int(extent[0]), int(extent[1])) if page_origin_yx is None \
        else (int(page_origin_yx[0]), int(page_origin_yx[1]))
    return data.Placement(
        window_id=window_id, capture_id=str(capture_id),
        level_index=int(level_index), region_index=int(region_index),
        patch_ordinal=int(patch_ordinal), page=int(page), rot_k=int(rot_k),
        page_origin_yx=origin,
        native_affine=tuple(float(term) for term in native_affine),
        pitch_px=(float(native_affine[0]) if pitch_px is None
                  else float(pitch_px)),
        route=route,
        local_cells_yx=np.asarray(local_cells_yx, np.int64))


def window_pose(row: object, placement: data.Placement, *,
                scale: Fraction = Fraction(1),
                declared_window_id: WindowId | None = None,
                ) -> color_region.RegionWindow:
    """Compose one window's pose THROUGH THE PRODUCTION COMPOSER.

    ``color_region.region_window`` reads a store; the store it reads is
    exactly three things — the format row, the placement, and the
    level's scale — so a fixture can hand it the real function rather
    than a re-implementation of it.  Everything the fixture would
    otherwise have spelled by hand (the half cell, the per-window
    origin, the rotation, the level rescale, the page clip) is
    production's answer, byte for byte.

    ``declared_window_id`` replaces ONLY the returned window's identity,
    never its geometry, for a fixture whose windows deliberately carry
    an id that is not their own extent.  The pose is composed from the
    placement's extent either way, so this cannot reintroduce a
    half-cell error; it is an identity hatch, not a geometry one.
    """
    store = SimpleNamespace(
        row=row,
        placement=lambda wid: placement,
        level=lambda capture_id, level_index: SimpleNamespace(scale=scale))
    window = color_region.region_window(store, placement.window_id)
    if declared_window_id is None:
        return window
    return dataclasses.replace(window, window_id=declared_window_id)


def grid_cells(start_yx: tuple[int, int],
               shape_yx: tuple[int, int]) -> np.ndarray:
    """The page cells of a rectangular window, row-major."""
    ys = np.arange(start_yx[0], start_yx[0] + shape_yx[0], dtype=np.int64)
    xs = np.arange(start_yx[1], start_yx[1] + shape_yx[1], dtype=np.int64)
    grid = np.stack(np.meshgrid(ys, xs, indexing="ij"), axis=-1)
    return grid.reshape(-1, 2)
