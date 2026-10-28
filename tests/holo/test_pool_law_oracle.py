"""Phase-0.1 pool-law oracle fixture (docs/PAYLOAD-REWORK-PLAN.md Phase 0/1).

Phase 1's acceptance instrument for the ruled region pool law
(PAYLOAD-IMPROVEMENTS §1; rulings §13a):

- L1 wholly-terminal regions drop whole (pinned elsewhere:
  ``unresolved_region_patch_ids`` tests in test_receive_refined_reuse).
- L2 a certified-complete window in a mixed region does no payload work but
  contributes LABEL rows to the region context fit.
- L3 labels are never terminal-gated in ANY path (gen-0, refined-reuse,
  replay).
- L4 zero-payload (all-reference) windows are label-only always.
- L5 the pitch/filter-signature pool = placements ∪ labels, identical in
  every path.

One case family over one small synthetic page (`_e023c_fixtures`): every
case pins the LAW as shipped by Phase 1 (K paths).  The pre-law c7aa340
window-granular skip pin (old case (b)) was consciously REPLACED by its law
counterpart in the same pass that flipped the five ``xfail`` law cases —
the certified-complete window now contributes label rows instead of
vanishing.

Scoping (per the 0.1 assignment): the refined-reuse law cases (e)/(f) drive
``sample_refined_reusing_generation`` / ``collect_refined_region_delta``
(v0.42: the R-level delta seam, successor of the retired whole-capture
``collect_refined_capture_evidence``) directly rather than the full
production pipeline — the pool divergences live entirely in
``_payload_sampling.py``/``_payload_reuse.py`` (the v0.38 split of
``_payload_windows.py``) and ``payload.py``.
"""
from __future__ import annotations

import hashlib
import pickle
from dataclasses import dataclass

import numpy as np
import pytest

from _e023c_fixtures import _PageFixture, _page_fixture
from holo.core import channel
from holo.format import metadata, pilots
from holo.format.registry import get_format_row
from holo.gen.color_compose import compose_color_tile
from holo.receive import payload
from holo.receive.color_payload import (
    collect_color_evidence,
    color_blocks_from_frontier,
)
from holo.receive.records import certificate_record_from_user_bits
from holo.receive.scan import open_capture
from holo.receive._payload_context import apply_region_context
from holo.receive._payload_reuse import sample_refined_reusing_generation
from holo.receive._payload_sampling import sample_and_calibrate
from holo.receive.payload_model import (
    ContextDecision,
    EvidenceSource,
    WindowEvidence,
)
from holo.receive.placement.model import (
    AddressResult,
    AffinePose,
    CandidateScore,
    PlacedPatch,
    PlacedSegment,
    PoseSegment,
    PoseWindow,
)

_PPC = 8.0
_SHAPE_YX_CELLS = (128, 128)

# Patch 0's window at page origin (0, 0) covers exactly these 2x2 tiles.
_T_PATCH0 = frozenset({(0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1)})
# A tile no fixture window touches — "an unrelated certificate" for L4.
_T_UNRELATED = frozenset({(0, 3, 3)})

_COUNT_FIELDS = (
    "n_search", "n_search_0", "n_search_1", "n_search_observations",
    "n_validation", "n_validation_0", "n_validation_1",
    "n_validation_observations",
)

def _pose(page_origin_yx: tuple[int, int], *, pitch_px: float = _PPC,
          shift_yx_cells: tuple[float, float] = (0.0, 0.0)) -> AffinePose:
    """Grid-true pose for the 8 px/cell fixture raster.

    ``pitch_px`` is the pose's *declared* pitch only — it feeds the region
    pitch pool, while the jacobian keeps sampling on the true grid, letting
    one window shift the pooled median without mis-sampling anything.
    """
    center_px = (_PPC - 1.0) * 0.5
    origin_yx_px = (
        page_origin_yx[0] * _PPC + center_px + shift_yx_cells[0] * _PPC,
        page_origin_yx[1] * _PPC + center_px + shift_yx_cells[1] * _PPC,
    )
    return AffinePose(
        origin_yx_px, ((_PPC, 0.0), (0.0, _PPC)), (0.5, 0.5), pitch_px, 0.0)


def _patch(patch_id: int, region_index: int, page_origin_yx: tuple[int, int],
           *, local_cells_yx: np.ndarray | None = None,
           route: str = "pool-law", redundant: bool = False,
           pitch_px: float = _PPC,
           shift_yx_cells: tuple[float, float] = (0.0, 0.0)) -> PlacedPatch:
    window = PoseWindow(
        patch_id, region_index, (0, 0), _SHAPE_YX_CELLS,
        support_estimate=_SHAPE_YX_CELLS[0] * _SHAPE_YX_CELLS[1])
    pose = _pose(page_origin_yx, pitch_px=pitch_px,
                 shift_yx_cells=shift_yx_cells)
    segment = PoseSegment(
        window, pose, _SHAPE_YX_CELLS[0] * _SHAPE_YX_CELLS[1], 1.0,
        (_PPC, _PPC), 0.0)
    if local_cells_yx is None:
        grid_y, grid_x = np.indices(_SHAPE_YX_CELLS)
        local_cells_yx = np.stack(
            (grid_y.ravel(), grid_x.ravel()), axis=1).astype(np.int32)
    placed = PlacedSegment(segment, page_origin_yx, 0, local_cells_yx)
    page_cells_yx = (
        local_cells_yx.astype(np.int64)
        + np.asarray(page_origin_yx, np.int64)).astype(np.int32)
    candidate = CandidateScore(
        0, page_origin_yx, 0, 0.0, 0.0, 0, 0, 100, 100, 10.0, True, route)
    return PlacedPatch(
        patch_id, region_index, 0, route, candidate, (), placed, (),
        redundant, page_cells_yx)


def _site_only_local_cells_yx(page: _PageFixture) -> np.ndarray:
    """All format-known site cells of the window's 2x2 tiles — a window
    whose payload-cell set is empty (the L4 zero-payload shape)."""
    word_cells_yx, filler_cells_yx = pilots.site_cells_yx(
        page.spec.family_seed, page.spec.n_filler)
    tiles = [
        np.concatenate([word_cells_yx, filler_cells_yx])
        + np.asarray((64 * tile_y, 64 * tile_x), np.int64)
        for tile_y in (0, 1) for tile_x in (0, 1)
    ]
    return np.concatenate(tiles).astype(np.int32)


def _assert_decisions_equal(lhs: ContextDecision,
                            rhs: ContextDecision) -> None:
    assert lhs.decision_id == rhs.decision_id
    assert (lhs.eligible, lhs.adopted, lhs.reason) == (
        rhs.eligible, rhs.adopted, rhs.reason)
    assert np.array_equal(lhs.offsets, rhs.offsets)
    assert np.array_equal(
        lhs.search_support_by_bin, rhs.search_support_by_bin)
    assert np.array_equal(
        lhs.validation_support_by_bin, rhs.validation_support_by_bin)
    assert np.array_equal(
        lhs.search_observations_by_bin, rhs.search_observations_by_bin)
    assert np.array_equal(
        lhs.validation_observations_by_bin,
        rhs.validation_observations_by_bin)
    for name in _COUNT_FIELDS:
        assert getattr(lhs, name) == getattr(rhs, name)


def _counts(decision: ContextDecision) -> tuple[int, ...]:
    return tuple(int(getattr(decision, name)) for name in _COUNT_FIELDS)


@pytest.fixture(scope="module")
def page() -> _PageFixture:
    return _page_fixture()


@pytest.fixture(scope="module")
def source() -> EvidenceSource:
    return EvidenceSource(
        hashlib.sha256(b"pool-law-oracle").hexdigest(), "pool-lane")


@dataclass(frozen=True, slots=True)
class _TwoWindowRegion:
    """One mixed region: patch 0 on the 4 certified tiles, patch 1 not."""

    address: AddressResult
    rows_full: tuple[WindowEvidence, ...]

    @property
    def row0_full(self) -> WindowEvidence:
        return next(row for row in self.rows_full if row.patch_id == 0)

    @property
    def row1_full(self) -> WindowEvidence:
        return next(row for row in self.rows_full if row.patch_id == 1)


@pytest.fixture(scope="module")
def region_ab(page: _PageFixture,
              source: EvidenceSource) -> _TwoWindowRegion:
    address = AddressResult(
        (_patch(0, 0, (0, 0)), _patch(1, 0, (128, 0))),
        (), (), ((0, "accepted"),), 2)
    rows_full = sample_and_calibrate(page.raster, source, address, page.spec)
    assert [row.patch_id for row in rows_full] == [0, 1]
    assert all(row.accepted for row in rows_full)
    return _TwoWindowRegion(address, rows_full)


def test_split_fit_equals_pooled_oracle_with_labels_no_terminal(
    page: _PageFixture, source: EvidenceSource,
    region_ab: _TwoWindowRegion,
) -> None:
    """Case (a): D7 split-fit-vs-pooled equality at fixture scale.

    Sanity duplicate of test_phased_schedule.py's
    ``test_split_region_fit_equals_pooled_oracle`` on this file's small
    synthetic region: fitting (mop-up rows + label rows) reproduces the
    single-pass pooled fit exactly, with no terminal set involved.
    """
    pooled_rows, pooled_decisions = apply_region_context(
        region_ab.rows_full)
    split_rows, split_decisions = apply_region_context(
        (region_ab.row1_full,), (region_ab.row0_full,))
    assert len(pooled_decisions) == len(split_decisions) == 1
    _assert_decisions_equal(split_decisions[0], pooled_decisions[0])
    assert [row.patch_id for row in split_rows] == [1]
    twin = next(row for row in pooled_rows if row.patch_id == 1)
    assert np.array_equal(split_rows[0].printed_llr, twin.printed_llr)
    assert split_rows[0].detector_profile == twin.detector_profile


def test_gen0_certified_window_is_label_contribution_not_payload(
    page: _PageFixture, source: EvidenceSource,
    region_ab: _TwoWindowRegion,
) -> None:
    """Case (b), law counterpart of the retired c7aa340 skip pin.

    Under L2 the certified-complete window is a LABEL contribution: absent
    from the returned payload rows (no owner rows, no blocks, no attempts
    — the c7aa340 payload-side savings stand) yet present in the region
    fit.  Phase 1 samples such windows full-window through the D7 label
    channel, so the terminal run's region decision and surviving payload
    row are byte-equal to the full pooled run's.

    Pins: (1) the certified-complete window is absent from the returned
    payload evidence; (2) the surviving window's samples are byte-equal to
    the no-terminal run's (the pitch pool spans label-routed windows —
    aperture unchanged); (3) the terminal-run region decision equals the
    full pooled decision exactly, and the surviving row carries the pooled
    run's profiled LLRs; (4) non-vacuity: dropping the certified window
    from the fit would have shrunk the population.
    """
    evidence_terminal = payload.collect_capture_evidence(
        page.raster, source, region_ab.address, page.spec,
        terminal_addresses=_T_PATCH0)
    assert [row.patch_id for row in evidence_terminal.windows] == [1]

    row1_terminal = evidence_terminal.windows[0]
    assert np.array_equal(
        row1_terminal.raw_means, region_ab.row1_full.raw_means)
    assert np.array_equal(row1_terminal.scores, region_ab.row1_full.scores)

    pooled_rows, pooled_decisions = apply_region_context(
        region_ab.rows_full)
    assert len(evidence_terminal.context_decisions) == 1
    _assert_decisions_equal(
        evidence_terminal.context_decisions[0], pooled_decisions[0])
    twin = next(row for row in pooled_rows if row.patch_id == 1)
    assert np.array_equal(row1_terminal.printed_llr, twin.printed_llr)
    assert row1_terminal.detector_profile == twin.detector_profile

    _skip_rows, skip_decisions = apply_region_context(
        (region_ab.row1_full,))
    assert (skip_decisions[0].n_search
            < evidence_terminal.context_decisions[0].n_search)


def test_law_l2_certified_window_label_sites_join_region_fit(
    page: _PageFixture, source: EvidenceSource,
    region_ab: _TwoWindowRegion,
) -> None:
    """Case (c), L2: under a terminal set, the certified-complete window's
    format-known (word/filler) site observations still join the region
    context fit population.

    Acceptance form: the terminal-run region decision's fit-population
    counts equal the full pool's.  The count fields depend only on cell
    geometry, parity, format labels, and neighbourhood completeness — NOT
    on scores or calibration — so they are invariant to whether Phase 1
    routes the certified window through the D7 label channel at full-window
    sampling or samples label sites plus their neighbourhoods.  (A
    label-sites-only row with no sampled neighbourhoods would be erased by
    the context model's complete-neighbourhood validity mask and fail this
    case — deliberately: the law says the sites JOIN the fit.)
    Bin-shaped support/observation arrays and offsets are deliberately NOT
    compared: they depend on marginal calibration, which the label-row
    mechanism may legitimately move.
    """
    evidence_terminal = payload.collect_capture_evidence(
        page.raster, source, region_ab.address, page.spec,
        terminal_addresses=_T_PATCH0)
    _pooled_rows, pooled_decisions = apply_region_context(
        region_ab.rows_full)
    assert _counts(evidence_terminal.context_decisions[0]) == _counts(
        pooled_decisions[0])


def test_law_l3_gen0_label_on_certified_tiles_still_joins_fit(
    page: _PageFixture, source: EvidenceSource,
) -> None:
    """Case (d), L3 gen-0: a D7 label placement whose tiles are all
    certified still joins the region fit — labels are never
    terminal-gated.

    The terminal set covers ONLY the label's tiles, so under the law the
    run with the terminal set is indistinguishable from the run without
    it: byte-identical CaptureEvidence.  (Pre-law gen-0 terminal-gated the
    label out and the two runs' region fits diverged.)
    """
    label_patch = _patch(7, 0, (0, 0), route="label", redundant=True)
    address = AddressResult(
        (_patch(1, 0, (128, 0)),), (), (), ((0, "accepted"),), 1,
        label_placements=(label_patch,))
    evidence_no_terminal = payload.collect_capture_evidence(
        page.raster, source, address, page.spec)
    evidence_terminal = payload.collect_capture_evidence(
        page.raster, source, address, page.spec,
        terminal_addresses=_T_PATCH0)
    assert pickle.dumps(evidence_terminal, protocol=5) == pickle.dumps(
        evidence_no_terminal, protocol=5)


def test_law_l5_refined_reuse_pool_matches_gen0_under_terminal_set(
    page: _PageFixture, source: EvidenceSource,
) -> None:
    """Case (e), L5: the refined-reuse path's region pitch pool (and hence
    integer filter signature) equals the gen-0 pool under a nonempty
    terminal set.

    Construction: the certified-complete window declares pose pitch 12 px
    (jacobian stays grid-true, so sampling geometry is unchanged); the
    unresolved sibling declares 8 px.  Gen-0 pools BOTH (median 10 px,
    aperture 7); the pre-law refined path deleted the reconciled window
    from its pool first (median 8 px, aperture 6 — PAYLOAD-IMPROVEMENTS
    1.3), so the resampled window's raw means diverged from the gen-0 path
    run on the same refined address.  Under L5 the two paths sample
    identically.

    Scoped to sample_refined_reusing_generation + sample_and_calibrate per
    the 0.1 assignment (the divergence lives entirely in
    _payload_sampling.py/_payload_reuse.py pool preparation).
    """
    baseline_address = AddressResult(
        (_patch(0, 0, (0, 0), pitch_px=12.0), _patch(1, 0, (128, 0))),
        (), (), ((0, "accepted"),), 2)
    refined_address = AddressResult(
        (_patch(0, 0, (0, 0), pitch_px=12.0),
         _patch(1, 0, (128, 0), shift_yx_cells=(0.125, -0.125))),
        (), (), ((0, "accepted"),), 2)

    generation0_rows = sample_and_calibrate(
        page.raster, source, baseline_address, page.spec,
        terminal_addresses=_T_PATCH0)
    assert [row.patch_id for row in generation0_rows] == [1]

    sampled, affected_regions, resampled_patch_ids, _label_rows = (
        sample_refined_reusing_generation(
            page.raster, source, baseline_address, refined_address,
            generation0_rows, page.spec,
            changed_patch_ids=(1,), terminal_addresses=_T_PATCH0))
    assert resampled_patch_ids == frozenset((1,))
    assert len(affected_regions) == 1

    gen0_path_rows = sample_and_calibrate(
        page.raster, source, refined_address, page.spec,
        terminal_addresses=_T_PATCH0)
    row1_refined = next(row for row in sampled if row.patch_id == 1)
    row1_gen0_path = next(
        row for row in gen0_path_rows if row.patch_id == 1)
    assert np.array_equal(
        row1_refined.scan_points_yx, row1_gen0_path.scan_points_yx)
    assert np.array_equal(
        row1_refined.raw_means, row1_gen0_path.raw_means)


def test_law_l3_refined_and_gen0_fit_populations_agree(
    page: _PageFixture, source: EvidenceSource,
) -> None:
    """Case (f), L3 refined-vs-gen0 consistency: under a terminal set with
    an affected labeled region, the refined-reuse pass and gen-0 fit the
    SAME region population.

    Pre-law the two production passes disagreed (PAYLOAD-IMPROVEMENTS
    1.4): gen-0 terminal-gated the label out; the refined pass re-sampled
    every label of an affected region with no terminal check.  The pin compares
    fit-population COUNTS, which are pose-invariant (placement cell
    geometry is frozen across refinement), so the legitimate pose change
    that makes the region "affected" cannot mask or fake agreement.
    """
    label_patch = _patch(7, 0, (0, 0), route="label", redundant=True)
    baseline_address = AddressResult(
        (_patch(1, 0, (128, 0)),), (), (), ((0, "accepted"),), 1,
        label_placements=(label_patch,))
    refined_address = AddressResult(
        (_patch(1, 0, (128, 0), shift_yx_cells=(0.125, -0.125)),),
        (), (), ((0, "accepted"),), 1,
        label_placements=(label_patch,))

    generation0 = payload.collect_capture_evidence(
        page.raster, source, baseline_address, page.spec,
        terminal_addresses=_T_PATCH0)
    refined = payload.collect_refined_region_delta(
        page.raster, source, baseline_address, refined_address,
        generation0, page.spec,
        changed_patch_ids=(1,), terminal_addresses=_T_PATCH0)
    assert len(generation0.context_decisions) == 1
    assert len(refined.context_decisions) == 1
    assert _counts(generation0.context_decisions[0]) == _counts(
        refined.context_decisions[0])


def test_law_l4_zero_payload_window_is_label_only_and_certificate_invariant(
    page: _PageFixture, source: EvidenceSource,
) -> None:
    """Case (g), L4: an all-reference (zero-payload) window is label-only
    ALWAYS — never a returned payload row — and its handling does not flip
    on the existence of an unrelated certificate.

    The pre-law knife edge (PAYLOAD-IMPROVEMENTS 1.5): with an empty
    terminal set the zero-payload window was sampled and RETURNED as
    payload evidence; the moment ANY terminal address existed — here one
    tile no window touches — it was skipped entirely.  Under the law both
    runs are byte-identical and neither returns the window.

    (Note: this window's audited cells are scattered format sites, so its
    region-fit contribution is empty under the context model's
    complete-neighbourhood validity mask in every era; the durable L4
    surface pinned here is the returned-evidence set plus full run
    invariance.)
    """
    zero_payload_patch = _patch(
        0, 0, (0, 0), local_cells_yx=_site_only_local_cells_yx(page))
    address = AddressResult(
        (zero_payload_patch, _patch(1, 0, (128, 0))),
        (), (), ((0, "accepted"),), 2)

    evidence_without = payload.collect_capture_evidence(
        page.raster, source, address, page.spec)
    evidence_with = payload.collect_capture_evidence(
        page.raster, source, address, page.spec,
        terminal_addresses=_T_UNRELATED)
    assert 0 not in {row.patch_id for row in evidence_without.windows}
    assert 0 not in {row.patch_id for row in evidence_with.windows}
    assert pickle.dumps(evidence_with, protocol=5) == pickle.dumps(
        evidence_without, protocol=5)


def _color_tile_patch(patch_id: int, tile_x: int, *,
                      route: str = "pool-law-color",
                      redundant: bool = False) -> PlacedPatch:
    """One 64x64-cell window over tile (0, tile_x) of the 2 px/cell page."""
    yy, xx = np.meshgrid(np.arange(64), np.arange(64), indexing="ij")
    cells = np.stack((yy, xx), axis=-1).reshape(-1, 2).astype(np.int32)
    pose = AffinePose(
        (0.5, tile_x * 128 + 0.5), ((2.0, 0.0), (0.0, 2.0)),
        (0.5, 0.5), 2.0, 0.0)
    segment = PoseSegment(
        PoseWindow(patch_id, 0, (0, 0), (64, 64)),
        pose, cells.shape[0], 1.0, (2.0, 2.0), 0.0)
    placed = PlacedSegment(segment, (0, 64 * tile_x), 0, cells)
    page_cells_yx = (
        cells.astype(np.int64)
        + np.asarray((0, 64 * tile_x), np.int64)).astype(np.int32)
    candidate = CandidateScore(
        0, (0, 64 * tile_x), 0, 0.0, 0.0, 0, 0, 1000, 1000, 20.0, True,
        route)
    return PlacedPatch(
        patch_id, 0, 0, route, candidate, (), placed, (), redundant,
        page_cells_yx)


def test_law_l6_certified_color_window_is_label_contribution_not_payload(
) -> None:
    """Case (h), L6: the color half of the law on one CMY8 mixed region.

    Three tiles in one region: patch 0 wholly on tile (0,0), patch 1 on
    tile (0,1), and a D7 label placement on tile (0,2).  With every
    stream of tile (0,0) certified, patch 0 is certified-complete at
    work-key granularity, so under L2/L6 it does no payload work — absent
    from the returned windows, owned pages, and blocks — while its
    format-known word/dust sites still join the region QDA fit as a label
    row, and the D7 label's sites join un-gated (L3).

    Acceptance form mirrors cases (c)/(f): the QDA fit-population counts
    (``n_train + n_heldout`` on the mechanism-robust ColorRegionSummary)
    are certificate-invariant — the certified run fits the SAME population
    as the certificate-free run — and non-vacuously larger than a run
    without the label-routed contributions.  The region's dependency ids
    carry the routing certificates (the fit population exists only under
    their authority).
    """
    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    rng = np.random.default_rng(0xC0102)
    states = np.empty((64, 192), np.uint8)
    symbols_by_tile: dict[tuple[int, int], dict[str, np.ndarray]] = {}
    for tile_x in range(3):
        counter = spec.tile_counter(0, 0, tile_x)
        symbols = {
            stream.stream_id: rng.integers(
                0, 2, stream.symbol_bits, dtype=np.uint8)
            for stream in spec.stream_profiles
        }
        symbols_by_tile[(0, tile_x)] = symbols
        states[:, tile_x * 64:(tile_x + 1) * 64] = compose_color_tile(
            spec, counter, symbols, 1)
    planes = channel.states_to_planes(states)
    rgb = np.repeat(
        np.repeat((1 - planes) * np.uint8(255), 2, axis=0), 2, axis=1)
    raster = open_capture(rgb, 600.0)
    color_source = EvidenceSource(raster.source.sha256, "ppc-2")

    label_patch = _color_tile_patch(7, 2, route="label", redundant=True)
    address = AddressResult(
        (_color_tile_patch(0, 0), _color_tile_patch(1, 1)),
        (), (), ((0, "accepted"),), 2,
        label_placements=(label_patch,))
    lone_address = AddressResult(
        (_color_tile_patch(1, 1),), (), (), ((0, "accepted"),), 1)
    metadata_bit = metadata.tile_bit(
        metadata.encode_metadata(0, 1), spec.tile_counter(0, 0, 0))
    certificates = tuple(
        certificate_record_from_user_bits(
            spec,
            page=0,
            tile_yx=(0, 0),
            stream_id=profile.stream_id,
            user_bits=np.concatenate((
                np.asarray([metadata_bit], np.uint8),
                symbols_by_tile[(0, 0)][profile.stream_id],
            )),
            origin_attempt_id=f"prior-{profile.stream_id}",
        )
        for profile in spec.stream_profiles
    )

    full = collect_color_evidence(raster, color_source, address, spec)
    certified = collect_color_evidence(
        raster, color_source, address, spec, certificates=certificates)
    lone = collect_color_evidence(raster, color_source, lone_address, spec)

    # No payload work for the certified-complete window; labels never in
    # the return surface (windows, owned pages, blocks).
    assert [row.patch_id for row in full.windows] == [0, 1]
    assert [row.patch_id for row in certified.windows] == [1]
    assert all(
        np.all(page.cells_yx[:, 1] // 64 == 1)
        for page in certified.pages)
    assert {block.address[1:3]
            for block in color_blocks_from_frontier(certified)} == {(0, 1)}

    # The word/dust sites of BOTH the certified window and the D7 label
    # join the fit: the fit population is certificate-invariant and
    # strictly larger than the lone unresolved window's.
    def fit_population(evidence) -> int:
        (summary,) = evidence.regions
        assert summary.accepted
        return summary.n_train + summary.n_heldout

    assert fit_population(certified) == fit_population(full)
    assert fit_population(certified) == fit_population(lone) + 240
    (certified_summary,) = certified.regions
    (full_summary,) = full.regions
    assert certified_summary.class_counts == full_summary.class_counts
    assert certified_summary.dependency_certificate_ids == tuple(sorted(
        record.certificate_id for record in certificates))
    assert full_summary.dependency_certificate_ids == ()
