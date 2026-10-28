"""E022 null battery, extended v1 rungs (format-v1 port, 2026-07-31).

Completes the format-v1 port of the historical E022 adversarial battery
(experiments/022-pilot-tile-search/qualify_e022.py; README section 10;
docs/RECEIVE-DESIGN.md sections 5.2/5.3/12.1).  The first two rungs (cold
true-accept; same-seed wrong-page refusal) live in
``test_placement_null_battery.py``; this module ports the rest:

- WRONG-SEED SIBLING NULL (historical Q4): a true c2-r0550 fragment
  correlated against the c2-r0700 reference of IDENTICAL page geometry.
  The two rows share ``family_seed`` (same pilot-site lattice) and differ
  only in ``spec.seed``, so every word descrambles to coin flips.  The
  production c2 page (c2-r0550@3328x2304, 1,872 tiles) is too heavy to
  render and cold-search in-test, so BOTH siblings use the 40x40 mm
  qualification geometry (c2-r0550@448x448 / c2-r0700@448x448, 7x7
  tiles) — the null is about seeds, not size, and the substitution keeps
  the page geometry of the two hypotheses bit-identical.
- GT-AFFINE POSE BATTERY (historical Q3): known rotations {2, 10, 30,
  44 deg}, anisotropy {1.5%, 4%}, and shear {1, 2.5 deg} applied with
  ``scipy.ndimage.affine_transform``; each must ACQUIRE and reproduce the
  applied page->raster map within 0.2 cells RMS over the audited cells
  (the historical <= 0.199-cell bound, measured at 8-11.7 px/cell).  The
  battery therefore runs at the historical 8 px/cell (1600 dpi) footing
  with the historical 200-cell scrap.  Rotated inputs are legitimate
  (dihedral rule): the cold domain enumerates all four rot90 and the
  fitted pose absorbs the residual in-plane angle inside the 6% pitch /
  3 deg orthogonality gates.
- MIRROR REFUSAL: the other half of the dihedral rule.  ``AffinePose``
  requires det(J) > 0, so a mirrored interpretation is unrepresentable;
  a mirrored capture must refuse at the value gates with zero accepted
  placements while its unmirrored twin accepts.
- CROSS-SCRAP FILL (historical README section 10, row 10): four disjoint
  fragments of one page as four ``SupportMask`` regions in one
  ``PayloadSurvey`` place independently with per-region components,
  disjoint page-cell unions, and no first-coverage placement marked
  redundant.

Complete-domain discipline (RECEIVE-DESIGN 5.3) is asserted where the
route ledger makes it exactly reconstructible: every route freezes its
hypothesis count before pixels, ``result.hypotheses_evaluated`` must equal
the sum of the declared domains actually entered, and the per-parity
support floor is ``max(30, ceil(log2(H_r) / (1 - h2(0.08))) + 0)`` for the
provisional policy row.  Gates are observed, never tuned.

Support-mask hygiene (from the base battery): the paper margin is never
claimed as support — claiming it dilutes window coverage and refuses the
true placement.  The affine rungs build support conservatively (interior
erosion plus full-coverage grid quantization), exactly as E021
segmentation would report a printed fragment.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
import pytest
from scipy import ndimage

from holo.core import fountain
from holo.format.descriptor import FormatSpec, get_coding
from holo.gen.compose import cells_to_dots, compose_page_cells
from holo.gen.emit import METADATA_VERSION, source_packed_for
from holo.gen.plan import plan_volume
from holo.receive.place import place_survey
from holo.receive.placement.defaults import PROVISIONAL_V1_PLACEMENT_POLICY
from holo.receive.placement.model import (
    AddressResult,
    PlacementBudgets,
    PlacementConfig,
)
from holo.receive.placement.reference import rotate_points
from holo.receive.placement.search import hypothesis_count
from holo.receive.scan import Raster, open_capture
from holo.receive.survey import (
    PayloadSurvey,
    SupportMask,
    SurveyDiagnostics,
    SurveyRegion,
)
from holo.receive.words import stage_a_hypotheses

import _roundtrip_fixture as roundtrip


# Refusal vocabulary shared with the base battery: value-gate and support
# refusals only.  "straddle_audit_refused" is deliberately NOT allowed in
# the null rungs — a null that reaches the audit has already passed the
# cold gate, which would be the false accept these rungs exist to catch.
_NULL_REASONS = {
    "winner_failed_heldout_gate", "rival_gap_failed", "insufficient_support",
}

# Provisional-row stand-ins (RECEIVE-DESIGN 5.3): asserted, never tuned.
_P_MAX = 0.08
_SUPPORT_MARGIN = 0


@pytest.fixture(scope="module")
def c3_fixture():
    return roundtrip._build_fixture()


def _build_ideal_page(
    spec: FormatSpec, payload: bytes, *, upsample: int
) -> np.ndarray:
    """Render one genuine page the way the production round-trip does.

    ``upsample`` follows the backbone payload gates' qualified footings:
    c3 decodes clean at 1 px/dot; c2 gets 2 px/dot (its native 2 px/cell
    sits at Nyquist).
    """
    plan = plan_volume(spec, len(payload), roundtrip._Q)
    if plan.n_pages != 1:
        raise AssertionError(f"fixture is no longer one page: {plan.n_pages}")
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
    raster = np.full((page_y, page_x), roundtrip._PAPER, np.uint8)
    origin_y, origin_x = spec.layout.origin_dots_yx
    height, width = dots.shape
    raster[origin_y:origin_y + height, origin_x:origin_x + width] = np.where(
        dots != 0, roundtrip._INK, roundtrip._PAPER)
    if upsample > 1:
        raster = np.repeat(np.repeat(raster, upsample, 0), upsample, 1)
    raster = np.ascontiguousarray(ndimage.gaussian_filter(
        raster.astype(np.float32), 0.5))
    raster.setflags(write=False)
    return raster


def _box_fragment(
    page_raster: np.ndarray,
    origin_dots_yx: tuple[int, int],
    ppc: int,
    *,
    first_cell: int,
    span_cells: int,
    margin_cells: int,
    dpi: float,
) -> tuple[Raster, SupportMask]:
    """One axis-aligned fragment on a paper canvas, margin excluded.

    Support covers the printed fragment only — the paper margin is not
    search support, exactly as E021 segmentation would report it.
    """
    y0 = origin_dots_yx[0] + first_cell * ppc
    x0 = origin_dots_yx[1] + first_cell * ppc
    span = span_cells * ppc
    margin = margin_cells * ppc
    canvas = np.full(
        (span + 2 * margin,) * 2, float(page_raster.max()), np.float32)
    canvas[margin:margin + span, margin:margin + span] = (
        page_raster[y0:y0 + span, x0:x0 + span])
    canvas.setflags(write=False)
    support = SupportMask(
        (margin, margin), span, np.ones((1, 1), bool), (span, span))
    return open_capture(canvas, dpi), support


def _survey(
    raster: Raster, supports: tuple[SupportMask, ...], spec: FormatSpec
) -> PayloadSurvey:
    px_per_mm = raster.dpi / 25.4
    return PayloadSurvey(
        regions=tuple(
            SurveyRegion(mask, mask.area_px / (px_per_mm * px_per_mm), 1.0)
            for mask in supports
        ),
        c_dots=spec.cell_dots,
        cell_pitch_px=raster.dpi * spec.cell_dots / 600.0,
        pitch_votes=(),
        diagnostics=SurveyDiagnostics(None, 1, 1.0, 1, 0, 0, 0),
    )


def _place(
    raster: Raster,
    supports: tuple[SupportMask, ...],
    spec: FormatSpec,
    pages: tuple[int, ...],
    *,
    with_word: bool,
) -> tuple[AddressResult, PlacementBudgets]:
    budgets, word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        spec, pages, 0, PlacementConfig())
    result = place_survey(
        raster, _survey(raster, supports, spec), spec,
        pages=pages, budgets=budgets,
        word_budget=word if with_word else None,
    )
    return result, budgets


def _reconstructed_hypotheses(
    result: AddressResult, spec: FormatSpec, pages: tuple[int, ...]
) -> int | None:
    """Re-derive the declared domains actually entered from the ledger.

    Word and cold domains are pure functions of the sampled window shape
    and the frozen page geometry (RECEIVE-DESIGN 5.3), so a run whose
    ledger contains only those routes must account bit-exactly.  Chain and
    lower-hint domains depend on the anchor inventory actually tried,
    which the ledger does not carry — such runs return ``None`` and are
    bounded instead of equated.
    """
    total = 0
    for attempt in result.attempts:
        routes = set(attempt.attempted_routes)
        if routes & {"chain", "lower_hint"}:
            return None
        shape = attempt.window.shape_yx_cells
        if "word" in routes:
            total += stage_a_hypotheses(shape)
        if "correlation" in routes:
            total += hypothesis_count(
                shape, tuple(spec.layout.cells_yx), len(pages),
                allow_overhang=True,
            )
    return total


def _assert_exact_accounting(
    result: AddressResult, spec: FormatSpec, pages: tuple[int, ...]
) -> None:
    expected = _reconstructed_hypotheses(result, spec, pages)
    assert expected is not None, "ledger contains an anchor-dependent route"
    assert result.hypotheses_evaluated == expected


def _section_5_3_floor(hypotheses: int) -> int:
    """Independent max(30, ceil(log2(H)/(1-h2(0.08))) + margin) arithmetic."""
    entropy = -_P_MAX * math.log2(_P_MAX) - (1.0 - _P_MAX) * math.log2(
        1.0 - _P_MAX)
    return max(
        30,
        math.ceil(math.log2(hypotheses) / (1.0 - entropy)) + _SUPPORT_MARGIN,
    )


# --------------------------------------------------------------------------
# Rung 1: wrong-seed sibling null (historical Q4).
# --------------------------------------------------------------------------

_C2_MEDIA_MM = (40.0, 40.0)
_C2_UPSAMPLE = 2          # 2 px/dot = the backbone gates' qualified c2 footing
_C2_DPI = 600.0 * _C2_UPSAMPLE


@pytest.fixture(scope="module")
def c2_siblings():
    """A true c2-r0550 page plus its wrong-seed c2-r0700 sibling row.

    Qualification geometry for BOTH siblings (documented choice): the
    production 3328x2304 page would put 1,872 tiles and a multi-minute
    cold map into every run, while the null's premise needs only that the
    two hypotheses share page geometry and site lattice while their row
    seeds differ.  40x40 mm derives c2 7x7 tiles (448x448 cells) — the
    same tile count as the c3 qualification fixture.
    """
    spec_true = FormatSpec(
        get_coding("c2-r0550"), "qualification-40x40", _C2_MEDIA_MM, 0.0)
    spec_wrong = FormatSpec(
        get_coding("c2-r0700"), "qualification-40x40", _C2_MEDIA_MM, 0.0)
    if spec_true.layout.tiles_yx != (7, 7):
        raise AssertionError(
            f"c2 qualification geometry drifted: {spec_true.layout.tiles_yx}")
    # The null premise: identical page geometry and pilot-site lattice,
    # different row seeds (value descramble becomes coin flips).
    assert spec_true.layout.cells_yx == spec_wrong.layout.cells_yx
    assert spec_true.family_seed == spec_wrong.family_seed
    assert spec_true.seed != spec_wrong.seed
    payload = hashlib.sha256(b"holo-e022-null-battery-c2-sibling-v1").digest()
    raster = _build_ideal_page(spec_true, payload, upsample=_C2_UPSAMPLE)
    return spec_true, spec_wrong, raster


def _c2_fragment(spec: FormatSpec, raster: np.ndarray
                 ) -> tuple[Raster, SupportMask]:
    origin_y, origin_x = spec.layout.origin_dots_yx
    return _box_fragment(
        raster,
        (origin_y * _C2_UPSAMPLE, origin_x * _C2_UPSAMPLE),
        spec.cell_dots * _C2_UPSAMPLE,
        first_cell=32, span_cells=128, margin_cells=16, dpi=_C2_DPI,
    )


def test_c2_fragment_accepts_on_its_own_seed(c2_siblings) -> None:
    """Positive control: the same pixels place under the true row seed.

    The control runs the production default word lane.  A cold-only c2
    control at this fragment size sits exactly on the documented
    small-support rival-floor gap (an overhang decoy dips to mismatch
    0.177 under the 0.20 bar frozen at >=135-site support — the same
    boundary as the recorded 0.176 complete-domain refusal), so Lane C
    refuses honestly there; the word-seeded point check is the qualified
    acceptance route for this support regime.  Gates are observed, never
    tuned.
    """
    spec_true, _spec_wrong, raster = c2_siblings
    fragment, support = _c2_fragment(spec_true, raster)
    result, _budgets = _place(
        fragment, (support,), spec_true, (0,), with_word=True)
    accepted = [row for row in result.placements if not row.redundant]
    assert accepted, [row.reason for row in result.unresolved]
    assert all(row.candidate.page == 0 for row in accepted)
    assert any(row.route == "word" for row in accepted)
    assert not result.quarantined_patch_ids
    for row in accepted:
        cells = np.asarray(row.page_cells_yx)
        assert ((cells >= 32) & (cells < 160)).all()
    _assert_exact_accounting(result, spec_true, (0,))


def test_c2_sibling_wrong_seed_refuses(c2_siblings) -> None:
    """The wrong-seed sibling null: same geometry, coin-flip values.

    Stage A stays enabled: its BCH decodes run against the sibling row's
    scramble and must produce no acceptable seed.  Cold correlation must
    refuse at the value gates with zero placements, and the run must
    account for every declared domain it entered.
    """
    spec_true, spec_wrong, raster = c2_siblings
    fragment, support = _c2_fragment(spec_true, raster)
    result, budgets = _place(
        fragment, (support,), spec_wrong, (0,), with_word=True)
    assert result.placements == ()
    assert result.unresolved, "null produced no attempts at all"
    assert {row.reason for row in result.unresolved} <= _NULL_REASONS
    _assert_exact_accounting(result, spec_wrong, (0,))
    # Complete-domain discipline, asserted independently (5.3): the cold
    # domain is the frozen 200-cell-window count over one declared page,
    # and its per-parity floor follows the identifiability formula.
    cold_domain = hypothesis_count(
        (200, 200), tuple(spec_wrong.layout.cells_yx), 1,
        allow_overhang=True,
    )
    assert budgets.cold.max_hypotheses == cold_domain
    assert budgets.cold.min_support == _section_5_3_floor(cold_domain)
    assert budgets.local.min_support == 30


# --------------------------------------------------------------------------
# Rung 2: GT-affine pose battery (historical Q3).
# --------------------------------------------------------------------------

# Historical Q3 footing: 8 px/cell (the 1600 dpi decimated footing), the
# smallest footing at which the <= 0.199-cell bound was measured, with the
# historical 200-cell scrap.
_POSE_SCALE = 8.0 / 3.0
_POSE_DPI = roundtrip._DPI * _POSE_SCALE
_POSE_FIRST = 32
_POSE_SPAN = 200
_POSE_MARGIN_PX = 48
_POSE_RMS_CELLS = 0.2
_SUPPORT_STEP_PX = 8


def _rotation(theta_deg: float) -> np.ndarray:
    angle = np.deg2rad(theta_deg)
    return np.array([
        [np.cos(angle), -np.sin(angle)],
        [np.sin(angle), np.cos(angle)],
    ])


_POSE_CASES = {
    # rotations exercise rot90 x residual-angle resolution; 44 deg is the
    # hard mod-90 boundary and, at this historical scrap size, ACQUIRES.
    "rot-2deg": _rotation(2.0),
    "rot-10deg": _rotation(10.0),
    "rot-30deg": _rotation(30.0),
    "rot-44deg": _rotation(44.0),
    # anisotropy within the 6% pitch gate
    "aniso-y-1.5pct": np.diag([1.015, 1.0]),
    "aniso-x-4pct": np.diag([1.0, 1.04]),
    # shear within the 3 deg orthogonality gate
    "shear-1deg": np.array(
        [[1.0, math.tan(math.radians(1.0))], [0.0, 1.0]]),
    "shear-2.5deg": np.array(
        [[1.0, math.tan(math.radians(2.5))], [0.0, 1.0]]),
}


@pytest.fixture(scope="module")
def pose_canvas(c3_fixture):
    """The undistorted 200-cell c3 scrap on paper, at the render footing."""
    spec = c3_fixture.spec
    ppc = spec.cell_dots
    origin_y, origin_x = spec.layout.origin_dots_yx
    y0 = origin_y + _POSE_FIRST * ppc
    x0 = origin_x + _POSE_FIRST * ppc
    span = _POSE_SPAN * ppc
    canvas = np.full(
        (span + 2 * _POSE_MARGIN_PX,) * 2,
        float(c3_fixture.raster.max()), np.float32)
    canvas[_POSE_MARGIN_PX:_POSE_MARGIN_PX + span,
           _POSE_MARGIN_PX:_POSE_MARGIN_PX + span] = (
        c3_fixture.raster[y0:y0 + span, x0:x0 + span])
    return canvas, span, ppc


def _grid_support(native: np.ndarray) -> SupportMask:
    """Quantize a native support footprint onto a full-coverage grid.

    A grid cell is claimed only when EVERY native pixel under it is
    supported, so quantization can only under-claim — the paper margin is
    never claimed as support.
    """
    step = _SUPPORT_STEP_PX
    ys, xs = np.nonzero(native)
    y0 = int(ys.min()) // step * step
    x0 = int(xs.min()) // step * step
    y1 = int(ys.max()) + 1
    x1 = int(xs.max()) + 1
    crop = native[y0:y1, x0:x1]
    grid_h = -(-crop.shape[0] // step)
    grid_w = -(-crop.shape[1] // step)
    padded = np.zeros((grid_h * step, grid_w * step), bool)
    padded[:crop.shape[0], :crop.shape[1]] = crop
    cells = padded.reshape(grid_h, step, grid_w, step).all(axis=(1, 3))
    return SupportMask((y0, x0), step, cells, (y1 - y0, x1 - x0))


def _distort(
    canvas: np.ndarray,
    span_px: int,
    ppc: int,
    matrix: np.ndarray,
    *,
    margin_px: int = _POSE_MARGIN_PX,
    first_cell: int = _POSE_FIRST,
    scale: float = _POSE_SCALE,
) -> tuple[Raster, SupportMask, np.ndarray, np.ndarray]:
    """Apply one known affine about the canvas centre; return exact GT.

    Output pixel o samples input pixel ``i = Minv @ o + offset`` with
    ``Minv = inv(scale * matrix)`` (the ``affine_transform`` convention),
    so the forward ground truth for page cell p is
    ``o(p) = J @ p + t`` with ``J = scale * matrix * ppc``.
    """
    forward = np.asarray(matrix, np.float64) * scale
    paper = float(canvas.max())
    height, width = canvas.shape
    centre_in = np.array([(height - 1) / 2.0, (width - 1) / 2.0])
    corners = np.array(
        [[0, 0], [0, width - 1], [height - 1, 0], [height - 1, width - 1]],
        np.float64)
    mapped = (corners - centre_in) @ forward.T
    out_shape = (
        int(np.ceil(mapped[:, 0].max() - mapped[:, 0].min())) + 17,
        int(np.ceil(mapped[:, 1].max() - mapped[:, 1].min())) + 17,
    )
    centre_out = np.array(
        [(out_shape[0] - 1) / 2.0, (out_shape[1] - 1) / 2.0])
    inverse = np.linalg.inv(forward)
    offset = centre_in - inverse @ centre_out
    out = np.ascontiguousarray(ndimage.affine_transform(
        canvas, inverse, offset=offset, output_shape=out_shape,
        order=1, mode="constant", cval=paper).astype(np.float32))
    out.setflags(write=False)
    # Conservative support: erode the fragment interior on the input side,
    # warp it, keep only fully covered pixels, then full-coverage-quantize.
    interior = np.zeros(canvas.shape, np.float32)
    erode_px = 2
    interior[margin_px + erode_px:margin_px + span_px - erode_px,
             margin_px + erode_px:margin_px + span_px - erode_px] = 1.0
    warped = ndimage.affine_transform(
        interior, inverse, offset=offset, output_shape=out_shape,
        order=1, mode="constant", cval=0.0)
    support = _grid_support(warped > 0.999)
    # GT map: input px of page cell p is ppc*p + t_axis per axis (the cell
    # centre of the ppc-wide dot block), then through the forward affine.
    t_axis = margin_px + (ppc - 1) / 2.0 - first_cell * ppc
    jacobian = forward * ppc
    translation = forward @ (np.array([t_axis, t_axis]) - centre_in) + (
        centre_out)
    return open_capture(out, _POSE_DPI), support, jacobian, translation


def _pose_errors_cells(
    result: AddressResult,
    jacobian: np.ndarray,
    translation: np.ndarray,
    *,
    first_cell: int,
    span_cells: int,
) -> tuple[float, int]:
    """RMS composed page->raster error in cells over all audited cells.

    Also asserts every audited cell of every placement resolves inside
    the true fragment's page rectangle (exact addressing, the 12/12
    historical bar).
    """
    inverse = np.linalg.inv(jacobian)
    errors = []
    for placed in result.placements:
        shape = placed.segment.segment.window.shape_yx_cells
        local = placed.segment.audited_cells_yx
        absolute = rotate_points(
            local, shape, placed.segment.rot_k
        ) + np.asarray(placed.segment.page_origin_yx, np.int64)
        inside = (
            (absolute >= first_cell)
            & (absolute < first_cell + span_cells)
        ).all(axis=1)
        assert bool(inside.all()), (
            f"placement {placed.patch_id} audited cells escaped the true "
            f"fragment rectangle")
        recovered = placed.segment.segment.pose.points(
            local.astype(np.float64))
        expected = absolute.astype(np.float64) @ jacobian.T + translation
        errors.append((recovered - expected) @ inverse.T)
    stacked = np.concatenate(errors)
    rms = float(np.sqrt(np.mean(np.sum(stacked ** 2, axis=1))))
    return rms, int(stacked.shape[0])


def _assert_bounded_accounting(
    result: AddressResult, spec: FormatSpec, pages: tuple[int, ...]
) -> None:
    """Chain-inclusive bounds when exact reconstruction is unavailable."""
    cold_total = 0
    chain_attempts = 0
    for attempt in result.attempts:
        routes = set(attempt.attempted_routes)
        assert not routes & {"lower_hint", "word"}
        if "correlation" in routes:
            cold_total += hypothesis_count(
                attempt.window.shape_yx_cells,
                tuple(spec.layout.cells_yx), len(pages),
                allow_overhang=True,
            )
        if "chain" in routes:
            chain_attempts += 1
    neighborhood = (2 * PlacementConfig().neighbor_radius_cells + 1) ** 2
    anchors = sum(1 for row in result.placements if not row.redundant)
    low = cold_total + neighborhood * chain_attempts
    high = cold_total + neighborhood * chain_attempts * max(1, anchors)
    assert low <= result.hypotheses_evaluated <= high


@pytest.mark.parametrize("case", sorted(_POSE_CASES))
def test_gt_affine_pose_battery(pose_canvas, c3_fixture, case: str) -> None:
    """Each known distortion must acquire and reproduce its own map."""
    canvas, span_px, ppc = pose_canvas
    fragment, support, jacobian, translation = _distort(
        canvas, span_px, ppc, _POSE_CASES[case])
    result, _budgets = _place(
        fragment, (support,), c3_fixture.spec, (0,), with_word=False)
    accepted = [row for row in result.placements if not row.redundant]
    assert accepted, (
        case, [row.reason for row in result.unresolved])
    assert all(
        row.candidate.page == 0 for row in result.placements)
    assert not result.quarantined_patch_ids
    rms, audited = _pose_errors_cells(
        result, jacobian, translation,
        first_cell=_POSE_FIRST, span_cells=_POSE_SPAN)
    assert audited >= 10_000, (case, audited)
    assert rms <= _POSE_RMS_CELLS, (case, rms)
    _assert_bounded_accounting(result, c3_fixture.spec, (0,))


def test_rot44_small_scrap_recovers_under_wholeword_rival_gate(
    pose_canvas, c3_fixture
) -> None:
    """v0.30 RECOVERY pin: 44 deg on a 128-cell scrap now ACQUIRES.

    Under the parity-class rival bar this case was the documented honest
    refusal: the pose gate passed and the true winner scored ~zero, but
    overhang decoys dipped to search-class mismatch 0.147-0.177 under the
    0.20 bar at ~76-86 sites/parity — the same structural family as the
    0.176 complete-domain refusal (docs/FULL-DOMAIN-RIVAL-ANALYSIS.md).
    The v0.30 whole-word rival evaluation restores the d=27 argument: the
    decoys' whole-word mismatch clears the unchanged 0.20 bar, and the
    true map is accepted.  Measured at the flip: winner mismatch 0.0,
    pose RMS 0.081 cells over 6,689 audited cells.
    """
    canvas, _span_px, ppc = pose_canvas
    small_span = 128
    keep = _POSE_MARGIN_PX + small_span * ppc + _POSE_MARGIN_PX
    small = np.ascontiguousarray(canvas[:keep, :keep])
    paper = float(canvas.max())
    small[_POSE_MARGIN_PX + small_span * ppc:, :] = paper
    small[:, _POSE_MARGIN_PX + small_span * ppc:] = paper
    fragment, support, jacobian, translation = _distort(
        small, small_span * ppc, ppc, _POSE_CASES["rot-44deg"])
    result, _budgets = _place(
        fragment, (support,), c3_fixture.spec, (0,), with_word=False)
    accepted = [row for row in result.placements if not row.redundant]
    assert accepted, [row.reason for row in result.unresolved]
    assert all(row.candidate.page == 0 for row in accepted)
    assert not result.quarantined_patch_ids
    rms, audited = _pose_errors_cells(
        result, jacobian, translation,
        first_cell=_POSE_FIRST, span_cells=small_span)
    assert audited >= 5_000
    assert rms <= _POSE_RMS_CELLS
    _assert_bounded_accounting(result, c3_fixture.spec, (0,))
@pytest.fixture(scope="module")
def c3_fragment_canvas(c3_fixture):
    """The base battery's 128-cell fragment canvas, at the native footing."""
    spec = c3_fixture.spec
    ppc = spec.cell_dots
    origin_y, origin_x = spec.layout.origin_dots_yx
    y0 = origin_y + 32 * ppc
    x0 = origin_x + 32 * ppc
    span = 128 * ppc
    margin = 16 * ppc
    canvas = np.full(
        (span + 2 * margin,) * 2, float(c3_fixture.raster.max()), np.float32)
    canvas[margin:margin + span, margin:margin + span] = (
        c3_fixture.raster[y0:y0 + span, x0:x0 + span])
    support = SupportMask(
        (margin, margin), span, np.ones((1, 1), bool), (span, span))
    return canvas, support


def test_mirrored_capture_refuses(c3_fragment_canvas, c3_fixture) -> None:
    """Mirrored input must refuse; its unmirrored twin must accept.

    ``AffinePose`` requires det(J) > 0, so no mirrored interpretation is
    representable in the hypothesis space.  A mirrored square lattice is
    still a square lattice, so the pose FITS (det > 0) and the refusal
    must come from the value gates: no rot90 of the reference matches
    mirrored bits, and Stage A's BCH decodes see non-codewords.  Only
    mirroring refuses — rotations acquire (pose battery above) — which is
    exactly the dihedral rule split.
    """
    canvas, support = c3_fragment_canvas
    spec = c3_fixture.spec
    mirrored = np.ascontiguousarray(canvas[:, ::-1])
    mirrored.setflags(write=False)
    # The support square is centred, so the same mask covers the mirror.
    result, _budgets = _place(
        open_capture(mirrored, roundtrip._DPI), (support,), spec, (0,),
        with_word=True)
    assert result.placements == ()
    assert result.unresolved, "mirror produced no attempts at all"
    assert {row.reason for row in result.unresolved} <= _NULL_REASONS
    _assert_exact_accounting(result, spec, (0,))

    # The unmirrored twin accepts from the identical canvas and support.
    upright = np.ascontiguousarray(canvas)
    upright.setflags(write=False)
    control, _budgets = _place(
        open_capture(upright, roundtrip._DPI), (support,), spec, (0,),
        with_word=False)
    accepted = [row for row in control.placements if not row.redundant]
    assert accepted, [row.reason for row in control.unresolved]
    assert all(row.candidate.page == 0 for row in accepted)


# --------------------------------------------------------------------------
# Rung 4: cross-scrap fill (historical README section 10, row 10).
# --------------------------------------------------------------------------


def test_cross_scrap_four_disjoint_fragments(c3_fixture) -> None:
    """Four disjoint fragments of one page in one canvas, four regions.

    Each region places independently (anchors and components are
    region-local), page-cell unions are pairwise disjoint and stay inside
    each fragment's true rectangle, and the redundancy logic never marks
    a first-coverage placement redundant.
    """
    spec = c3_fixture.spec
    ppc = spec.cell_dots
    origin_y, origin_x = spec.layout.origin_dots_yx
    size_cells = 96
    span_px = size_cells * ppc
    page_rects = ((48, 48), (48, 304), (304, 48), (256, 256))
    canvas_px = ((48, 48), (48, 384), (384, 48), (384, 384))
    canvas = np.full((720, 720), float(c3_fixture.raster.max()), np.float32)
    supports: list[SupportMask] = []
    for (cell_y, cell_x), (px_y, px_x) in zip(page_rects, canvas_px):
        y0 = origin_y + cell_y * ppc
        x0 = origin_x + cell_x * ppc
        canvas[px_y:px_y + span_px, px_x:px_x + span_px] = (
            c3_fixture.raster[y0:y0 + span_px, x0:x0 + span_px])
        supports.append(SupportMask(
            (px_y, px_x), span_px, np.ones((1, 1), bool),
            (span_px, span_px)))
    canvas.setflags(write=False)
    result, _budgets = _place(
        open_capture(canvas, roundtrip._DPI), tuple(supports), spec, (0,),
        with_word=True)

    assert dict(result.region_states) == {
        0: "accepted", 1: "accepted", 2: "accepted", 3: "accepted"}
    by_region: dict[int, list] = {}
    for placed in result.placements:
        by_region.setdefault(placed.region_index, []).append(placed)
    assert sorted(by_region) == [0, 1, 2, 3]
    union_by_region: dict[int, set[tuple[int, int]]] = {}
    for region_index, rows in by_region.items():
        # One 96-cell fragment fits one 200-cell window: exactly one
        # placement, opening that region's component 0.
        assert len(rows) == 1
        placed = rows[0]
        assert placed.component == 0
        assert not placed.redundant, (
            "first-coverage placement was marked redundant")
        assert placed.candidate.page == 0
        cells = np.asarray(placed.page_cells_yx)
        rect_y, rect_x = page_rects[region_index]
        assert ((cells[:, 0] >= rect_y)
                & (cells[:, 0] < rect_y + size_cells)).all()
        assert ((cells[:, 1] >= rect_x)
                & (cells[:, 1] < rect_x + size_cells)).all()
        union_by_region[region_index] = set(map(tuple, cells))
    regions = sorted(union_by_region)
    for index, first in enumerate(regions):
        for second in regions[index + 1:]:
            assert not (union_by_region[first] & union_by_region[second]), (
                f"regions {first} and {second} claim overlapping page cells")
    assert not result.quarantined_patch_ids
    assert not any(word.conflict for word in result.words)
    _assert_exact_accounting(result, spec, (0,))
