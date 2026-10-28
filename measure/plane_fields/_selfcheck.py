#!/usr/bin/env python
"""Synthetic checks for the REFIT SEAM — no state, no scan, no pixels.

`measure/` is outside `testpaths` and nothing here is pytest-collected,
but the 2026-08-22 review found two defects that a five-line synthetic
check would have caught the day they were written:

* the refit override reached only the A1 arm, so on a capture whose
  stack selected A0 the refit silently evaluated at the zero; and
* ``null_proof`` short-circuited to ``True`` on exactly those captures.

Both are seam arithmetic, and seam arithmetic needs no scan.  This module
builds a synthetic window — a made-up crop, a made-up pose, made-up
points — and asserts what the seam must do:

1. ``base_features`` with no override IS ``color_sampling.crop_features``,
   bit for bit (the A0 arm is untouched on an ordinary fit);
2. an all-zero override is the identity, bit for bit (so a nonzero
   difference is the correction and nothing else);
3. a per-plane CONSTANT delta moves that plane's A0 samples and no
   other plane's; and
4. a per-cell AFFINE (``gt_affine.affine_override_builder``) reaches the
   A0 arm too, and its displacement VARIES across the tile — which a
   constant delta cannot express;
5. ``_refit_probe`` RAISES when the selected arm's features equal that
   arm's zero (the no-op it exists to make impossible); and
6. every P2 SUMMARY REDUCTION survives the rows it will actually be
   handed — the first full run computed all twenty-four E1
   measurements and then died in a reduction, with nothing on disk.

    PYTHONPATH=src:measure env/bin/python -m plane_fields._selfcheck
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from holo.receive.color_sampling import crop_features

from . import _swim_region
from ._affine_fit import Affine
from ._swim_region import (
    RefitDidNotReach,
    base_features,
    constant_override,
    override_offsets,
)

TILE_CELLS = 64


# --------------------------------------------------------------------------
# the synthetic window
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _Pose:
    scale: float

    def matrix(self) -> np.ndarray:
        """Local cell (dy, dx) -> scan px (dy, dx); a plain scaling."""
        return np.asarray(((self.scale, 0.0), (0.0, self.scale)))


@dataclass(frozen=True)
class _Segment:
    rot_k: int
    segment: object


@dataclass(frozen=True)
class _Patch:
    patch_id: int
    segment: _Segment


@dataclass(frozen=True)
class _Layout:
    cells_yx: tuple[int, int]


@dataclass(frozen=True)
class _Spec:
    cell_dots: int
    layout: _Layout


@dataclass
class _Row:
    patch: _Patch
    page_cells_yx: np.ndarray
    scan_points_yx: np.ndarray


@dataclass
class _Stack:
    adopted: bool
    selected_features: tuple = field(default_factory=tuple)


def synthetic(pitch_px: float = 8.0, cell_dots: int = 2, tile_y: int = 3,
              tile_x: int = 2, side: int = 16):
    """One window covering a ``side x side`` corner of one tile."""
    inner = type("_Inner", (), {"pose": _Pose(pitch_px)})()
    patch = _Patch(7, _Segment(0, inner))
    spec = _Spec(cell_dots, _Layout((TILE_CELLS * 8, TILE_CELLS * 8)))
    cy, cx = np.meshgrid(np.arange(side), np.arange(side), indexing="ij")
    page_cells = np.stack(
        (tile_y * TILE_CELLS + cy.ravel(), tile_x * TILE_CELLS + cx.ravel()),
        axis=1).astype(np.int64)
    # Scan points: the window's own local grid, offset into the crop.
    points = (np.stack((cy.ravel(), cx.ravel()), axis=1).astype(np.float64)
              * pitch_px + 40.0)
    row = _Row(patch, page_cells, points)
    rng = np.random.default_rng(20260822)
    span = int(side * pitch_px) + 80
    raw = rng.integers(0, 256, size=(span, span, 3), dtype=np.uint8)
    return spec, row, (0, 0, raw), pitch_px, 255.0


# --------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------
def check_base_arm_seam() -> list[str]:
    spec, row, crop, pitch_px, divisor = synthetic()
    findings: list[str] = []

    production = crop_features(crop, row.scan_points_yx, pitch_px, divisor)
    mine = base_features(crop, row, spec, pitch_px, divisor)
    if not np.array_equal(production, mine):
        findings.append(
            "base_features(None) is not crop_features bit for bit: "
            f"max |diff| {np.abs(production - mine).max():.3e}")

    zero = base_features(
        crop, row, spec, pitch_px, divisor,
        offsets_override=override_offsets(
            row, None, spec, np.zeros((3, 2)), False))
    if not np.array_equal(production, zero):
        findings.append(
            "an all-zero A0 override is not the identity: "
            f"max |diff| {np.abs(production - zero).max():.3e}")

    delta = np.zeros((3, 2))
    delta[2] = (0.6, 0.0)                      # move Y in page x, 0.6 dots
    moved = base_features(
        crop, row, spec, pitch_px, divisor,
        offsets_override=constant_override(delta)(row, None, spec, False))
    if not np.abs(moved[:, 2] - zero[:, 2]).max() > 0.0:
        findings.append(
            "a 0.6-dot Y delta did not move the A0 arm's Y samples — the "
            "REFIT NO-OP the review found")
    for plane in (0, 1):
        if not np.array_equal(moved[:, plane], zero[:, plane]):
            findings.append(
                f"a Y-only delta moved plane {plane}'s A0 samples")
    return findings


def check_affine_seam() -> list[str]:
    """The per-cell affine reaches A0, and it is not a constant."""
    from .gt_affine import affine_override_builder

    spec, row, crop, pitch_px, divisor = synthetic()
    findings: list[str] = []
    address = (0, int(row.page_cells_yx[0, 0]) // TILE_CELLS,
               int(row.page_cells_yx[0, 1]) // TILE_CELLS)
    # Translation + a scale error: the displacement must vary with the
    # in-tile coordinate, which is the whole point of the 6-dof seam.
    affines = (None, None, Affine(0.4, 0.0, ((0.02, 0.0), (0.0, 0.0))))
    builder = affine_override_builder(address, affines)
    override = builder(row, None, spec, False)
    displacement = np.asarray(override[2], np.float64)[:, 0]
    if not np.ptp(displacement) > 1e-6:
        findings.append(
            "the per-cell affine override is constant across the tile — "
            "the 6-dof seam degenerated to a translation")
    zero = base_features(crop, row, spec, pitch_px, divisor)
    moved = base_features(crop, row, spec, pitch_px, divisor,
                          offsets_override=override)
    if not np.abs(moved[:, 2] - zero[:, 2]).max() > 0.0:
        findings.append("the per-cell affine did not reach the A0 arm")
    for plane in (0, 1):
        if not np.array_equal(moved[:, plane], zero[:, plane]):
            findings.append(
                f"a Y-only affine moved plane {plane}'s A0 samples")
    return findings


def check_probe_raises() -> list[str]:
    """A refit whose selected features equal the zero must FAIL LOUDLY."""
    findings: list[str] = []
    address = (0, 3, 2)
    features = np.arange(24, dtype=np.float64).reshape(8, 3)
    for adopted in (False, True):
        stack = _Stack(adopted=adopted,
                       selected_features=(np.array(features),))
        try:
            _swim_region._refit_probe(
                stack, {address: object()}, {address: [0]},
                {0: np.array(features)}, "region", "0" * 64)
        except RefitDidNotReach:
            pass
        else:
            findings.append(
                f"_refit_probe accepted a no-op refit on the "
                f"{'A1' if adopted else 'A0'} arm")
        stack = _Stack(adopted=adopted,
                       selected_features=(features + 0.5,))
        try:
            probe = _swim_region._refit_probe(
                stack, {address: object()}, {address: [0]},
                {0: np.array(features)}, "region", "0" * 64)
        except RefitDidNotReach as exc:
            findings.append(f"_refit_probe rejected a real refit: {exc}")
        else:
            if abs(probe["max_abs_feature_delta"] - 0.5) > 1e-12:
                findings.append(
                    "the refit probe mis-measures the feature delta: "
                    f"{probe['max_abs_feature_delta']}")
    return findings


def check_reductions() -> list[str]:
    """Every P2 summary reduction, over synthetic rows.  No state, no scan.

    The first full P2 run computed all twenty-four E1 measurements and
    then died in the E3 ratio reduction on a ``mean`` over a column that
    holds a stratum NAME and a list of names beside its numbers.  These
    rows reproduce that shape in a second.
    """
    import json

    from . import _residue_run as run
    from . import _residue_strata as strata

    findings: list[str] = []
    rng = np.random.default_rng(20260822)

    class _Target:
        def __init__(self, tile_y, tile_x, band, role) -> None:
            self.tile_y, self.tile_x = tile_y, tile_x
            self.stream, self.plane = "Y", 2
            self.band, self.role = band, role

    measured = [_Target(14, 9, "dead", "target"),
                _Target(15, 7, "clear", "reproduction-control")]

    def rows():
        truth = np.stack([rng.integers(0, 2, 2000).astype(float)
                          for _ in range(3)])
        values = 0.4 - 0.15 * truth[2] + rng.normal(0, 0.05, 2000)
        return strata.stratum_rows(values, truth[2], truth[0], truth[1])

    def directional():
        table = rows()
        contrast = strata._contrast(table)
        return {"direction": {"axis": "x", "sign": 1, "dominant_dots": 0.6,
                              "translation_dots_xy": [0.6, 0.1],
                              "dominance_ratio": 6.0},
                "n_samples": 2000,
                "downstream": {"strata": table, "contrast": contrast,
                               "n_valid": 2000},
                "upstream": {"strata": table, "contrast": contrast,
                             "n_valid": 2000},
                "same_cell": {"strata": table, "contrast": contrast},
                "downstream_minus_upstream_gap": 0.001}

    per_capture = {}
    for sha in ("a" * 64, "b" * 64, "c" * 64):
        capture = {"capture": sha, "e1": {}, "e2": {}, "e3": {}}
        for key in [f"{row.tile_y},{row.tile_x}/Y" for row in measured] + [
                "ref 0,3/Y", "ref 5,26/Y"]:
            table = rows()
            capture["e2"][key] = directional()
            capture["e3"][key] = {"strata": table,
                                  "contrast": strata._contrast(table)}
        per_capture[sha] = capture

    for name, summary in (("E2", lambda: run._e2_summary(
                               per_capture, measured)),
                          ("E3", lambda: run._e3_summary(
                               per_capture, measured))):
        try:
            json.dumps(summary(), default=str)
        except Exception as exc:                           # noqa: BLE001
            findings.append(f"the {name} summary raised: {exc!r}")

    e1 = [{"tile_y": 14, "tile_x": 9, "band": "dead", "role": "target",
           "frozen": {"union_ber": 0.11, "certified": False},
           "refit": {"union_ber": 0.10, "certified": False},
           "refit_minus_frozen_ber": -0.01,
           "reproduction_gap_vs_gt_affine": 0.0},
          {"tile_y": 15, "tile_x": 7, "band": "clear",
           "role": "reproduction-control",
           "frozen": {"union_ber": 0.08, "certified": True},
           "refit": {"error": "the region refused"}}]
    try:
        json.dumps(run._e1_summary(e1), default=str)
    except Exception as exc:                               # noqa: BLE001
        findings.append(f"the E1 summary raised on a refused arm: {exc!r}")
    return findings


def main() -> int:
    checks = (("A0 base-arm seam", check_base_arm_seam),
              ("per-cell affine seam", check_affine_seam),
              ("refit no-op tripwire", check_probe_raises),
              ("P2 summary reductions", check_reductions))
    failed = 0
    for name, check in checks:
        findings = check()
        failed += len(findings)
        print(f"{'FAIL' if findings else 'ok  '}  {name}")
        for finding in findings:
            print(f"        {finding}")
    print("PASS" if not failed else f"FAILED ({failed} findings)")
    return 1 if failed else 0


__all__ = ["check_affine_seam", "check_base_arm_seam", "check_probe_raises",
           "check_reductions", "main", "synthetic"]


if __name__ == "__main__":
    raise SystemExit(main())
