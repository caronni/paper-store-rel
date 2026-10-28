"""Phase-3.5 K/color unification + vectorization exactness pins.

PAYLOAD-REWORK-PLAN 3.5 (findings lens-efficiency:04, payload-windows:05,
color-payload:04/06, color-upstream:07/10, evidence-core:04).  Every hoist
is exact; per the phase-0 governing rules each pin keeps the NAIVE
pre-change computation as a test-local oracle and asserts byte-identity —
and the owner-freeze pins hand-construct their expected winners rather
than recomputing them through the shared code (the audit's
differential-cancellation warning).
"""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import numpy as np
import pytest

from holo.devices.profiles import make_spec
from holo.format import pilots
from holo.receive import _payload_context, color_detect, color_payload
from holo.receive import color_anchoring, color_fitting, color_pool
from holo.receive import color_sampling
from holo.receive.color_detect import (
    CMY8Detector,
    cmy8_raw_llrs,
    fit_cmy8_detector,
    fit_equal_prior_qda,
    qualify_cmy8_calibration_support,
)
from holo.receive.color_payload import (
    ColorCaptureEvidence,
    ColorWindowEvidence,
    color_blocks_from_frontier,
)
from holo.receive.evidence_blocks import (
    _block_from_rows,
    _origin_for_window,
    block_from_rows,
    blocks_from_frontier,
)
from holo.receive.payload import freeze_capture_evidence, payload_cell_mask
from holo.receive.payload_model import (
    CaptureEvidence,
    EvidenceSource,
    OwnedPageEvidence,
    PlacementModelError,
    WindowEvidence,
)


_SOURCE = EvidenceSource(
    hashlib.sha256(b"payload-unification").hexdigest(), "lane-u")


def _payload_cells(spec, tile_yx: tuple[int, int], count: int) -> np.ndarray:
    """First ``count`` row-major cargo cells of one 64x64 tile."""
    grid_y, grid_x = np.indices((64, 64))
    cells = np.stack((grid_y.ravel(), grid_x.ravel()), axis=1)
    cargo = payload_cell_mask(spec, cells)
    selected = cells[cargo][:count]
    return (selected + np.asarray(
        (tile_yx[0] * 64, tile_yx[1] * 64))).astype(np.int32)


def _k_window(
    patch_id: int,
    cells: np.ndarray,
    llr_values: tuple[float, ...] = (),
    *,
    loss: float | None = None,
    accepted: bool = True,
    page: int = 0,
) -> WindowEvidence:
    n_rows = cells.shape[0]
    common = dict(
        source=_SOURCE,
        placement_id=f"placement-{patch_id}",
        patch_id=patch_id,
        region_id="region-0",
        page=page,
        redundant=False,
        segment_id=patch_id,
        segment_local_cells_yx=cells.astype(np.int32),
        page_cells_yx=cells.astype(np.int32),
        scan_points_yx=cells.astype(np.float64),
        raw_means=np.zeros(n_rows, np.float32),
        scores=np.zeros(n_rows, np.float32),
        reference_values=np.full(n_rows, -1, np.int8),
        n_search_0=8,
        n_search_1=8,
        n_heldout=4,
    )
    if not accepted:
        return WindowEvidence(
            calibration_score_nodes=np.zeros(0),
            calibration_probability_nodes=np.zeros(0),
            baseline_printed_llr=np.zeros(0, np.float32),
            printed_llr=np.zeros(0, np.float32),
            accepted=False, refusal_reason="refused",
            heldout_logloss=None, **common)
    llr = np.asarray(llr_values, np.float32)
    assert llr.size == n_rows
    return WindowEvidence(
        calibration_score_nodes=np.asarray((-1.0, 1.0)),
        calibration_probability_nodes=np.asarray((0.25, 0.75)),
        baseline_printed_llr=llr,
        printed_llr=llr,
        accepted=True, refusal_reason="",
        heldout_logloss=loss, **common)


@pytest.fixture(scope="module")
def k_spec():
    return make_spec("c3-r0550")


@pytest.fixture(scope="module")
def k_capture(k_spec) -> CaptureEvidence:
    """Three overlapping accepted windows + one refused, two tiles."""
    cells = _payload_cells(k_spec, (0, 0), 4)
    far = _payload_cells(k_spec, (0, 1), 2)
    w_late = _k_window(0, cells[:2], (0.10, 0.11), loss=2.0)
    w_tie = _k_window(2, cells[2:4], (0.30, 0.31), loss=1.0)
    w_best = _k_window(1, cells[1:3], (0.20, 0.21), loss=1.0)
    w_far = _k_window(4, far, (0.40, 0.41), loss=3.0)
    w_refused = _k_window(3, cells, accepted=False)
    return freeze_capture_evidence(
        _SOURCE, k_spec,
        (w_late, w_tie, w_best, w_far, w_refused))


def test_k_owner_freeze_matches_hand_constructed_winners(
    k_spec, k_capture,
) -> None:
    """Shared-core K competition vs hand-built (loss, patch_id) winners.

    Cell 0: only patch 0 sees it.  Cells 1-2: patch 1 (loss 1.0) beats
    patch 0 (2.0) and, on cell 2, the loss-tied patch 2 by lower ordinal.
    Cell 3: only patch 2.  The refused window covers everything and owns
    nothing.  Winners here are HAND-DERIVED, never recomputed.
    """
    cells = _payload_cells(k_spec, (0, 0), 4)
    far = _payload_cells(k_spec, (0, 1), 2)
    assert len(k_capture.pages) == 1
    page = k_capture.pages[0]
    assert np.array_equal(
        page.cells_yx, np.concatenate((cells, far)))
    assert np.array_equal(
        page.printed_llr,
        np.asarray((0.10, 0.20, 0.21, 0.31, 0.40, 0.41), np.float32))
    # windows tuple order: (w_late, w_tie, w_best, w_far, w_refused)
    assert np.array_equal(
        page.window_indices, np.asarray((0, 2, 2, 1, 3, 3), np.int32))
    assert np.array_equal(
        page.window_row_indices, np.asarray((0, 0, 1, 1, 0, 1), np.int32))


def test_color_owner_freeze_matches_hand_constructed_winners() -> None:
    """Same competition, color codec, shared core — hand-built winners."""
    spec = make_spec("c3-cmy7-p120-v0")
    source = EvidenceSource("0" * 64, "lane")
    flat = np.sort(
        pilots.color_payload_cell_indices(spec.family_seed))[:4]
    cells = np.column_stack((flat // 64, flat % 64)).astype(np.int32)

    def window(patch_id, loss, selected, values):
        return ColorWindowEvidence(
            source=source,
            placement_id=f"placement-{patch_id}",
            patch_id=patch_id,
            region_id="region",
            page=0,
            page_cells_yx=selected,
            evidence_values=np.repeat(
                np.asarray(values, np.float32)[:, None], 6, axis=1),
            heldout_logloss=loss,
            evidence_kind=color_payload.COLOR_CMY7_KIND,
        )

    windows = (
        window(0, 2.0, cells[:2], (0.10, 0.11)),
        window(2, 1.0, cells[2:], (0.30, 0.31)),
        window(1, 1.0, cells[1:3], (0.20, 0.21)),
    )
    pages = color_payload._freeze(source, spec, windows)
    assert len(pages) == 1
    page = pages[0]
    assert np.array_equal(page.cells_yx, cells)
    assert np.array_equal(
        page.evidence_values[:, 0],
        np.asarray((0.10, 0.20, 0.21, 0.31), np.float32))
    assert np.array_equal(
        page.window_indices, np.asarray((0, 2, 2, 1), np.int32))
    assert np.array_equal(
        page.window_row_indices, np.asarray((0, 0, 1, 1), np.int32))


def test_k_freeze_bounds_degenerate_out_of_page_candidate(k_spec) -> None:
    """Degenerate-input note: out-of-page owned cells now refuse cleanly."""
    outside = np.asarray(
        ((0, k_spec.layout.cells_yx[1]),), np.int32)
    # An out-of-page cell is never a cargo site of any tile the mask can
    # name, so route it through the shared core directly.
    from holo.receive.payload_model import freeze_page_owners
    with pytest.raises(
            PlacementModelError, match="lies outside the page"):
        freeze_page_owners(
            ((0, 0, outside, np.zeros(1, np.int32),
              np.zeros((1, 1), np.float32)),),
            k_spec.layout.cells_yx)


def _naive_owner_validation(windows, pages) -> str | None:
    """Test-local oracle: the pre-change per-cell K validation loop."""
    for page in pages:
        for cell, llr, window_index, row_index in zip(
                page.cells_yx, page.printed_llr, page.window_indices,
                page.window_row_indices, strict=True):
            if not 0 <= int(window_index) < len(windows):
                return "payload: owner points outside window ledger"
            window = windows[int(window_index)]
            if (not window.accepted or window.page != page.page
                    or not 0 <= int(row_index)
                    < window.page_cells_yx.shape[0]
                    or not np.array_equal(
                        cell, window.page_cells_yx[int(row_index)])
                    or float(llr) != float(
                        window.printed_llr[int(row_index)])):
                return "payload: owner/window evidence mismatch"
    return None


def test_vectorized_owner_validation_matches_naive_oracle(
    k_spec, k_capture,
) -> None:
    windows = k_capture.windows
    page = k_capture.pages[0]

    def corrupt(**overrides) -> OwnedPageEvidence:
        fields = dict(
            page=page.page,
            cells_yx=page.cells_yx,
            printed_llr=page.printed_llr,
            window_indices=page.window_indices,
            window_row_indices=page.window_row_indices,
        )
        fields.update(overrides)
        return OwnedPageEvidence(**fields)

    bad_llr = np.array(page.printed_llr)
    bad_llr[2] += np.float32(0.5)
    bad_rows = np.array(page.window_row_indices)
    bad_rows[1] = 99
    bad_windows = np.array(page.window_indices)
    bad_windows[3] = 7
    refused_owner = np.array(page.window_indices)
    refused_owner[0] = 4  # w_refused
    cases = (
        page,
        corrupt(printed_llr=bad_llr),
        corrupt(window_row_indices=bad_rows),
        corrupt(window_indices=bad_windows),
        corrupt(window_indices=refused_owner),
    )
    for candidate in cases:
        expected = _naive_owner_validation(windows, (candidate,))
        if expected is None:
            CaptureEvidence(
                _SOURCE, k_spec.spec_id, windows, (), (candidate,))
            continue
        with pytest.raises(ValueError) as caught:
            CaptureEvidence(
                _SOURCE, k_spec.spec_id, windows, (), (candidate,))
        assert str(caught.value) == expected


def _naive_k_blocks(frontier, dependencies):
    """Test-local oracle: the pre-change per-element K converter."""
    origins = tuple(
        _origin_for_window(window, dependencies)
        for window in frontier.windows)
    output = []
    for page in frontier.pages:
        if page.cells_yx.shape[0] == 0:
            continue
        tile_y = page.cells_yx[:, 0].astype(np.int64) // 64
        tile_x = page.cells_yx[:, 1].astype(np.int64) // 64
        page_tiles_x = int(tile_x.max()) + 1
        tile_codes = tile_y * page_tiles_x + tile_x
        order = np.argsort(tile_codes, kind="stable")
        ordered_codes = tile_codes[order]
        starts = np.flatnonzero(np.concatenate((
            np.asarray((True,)),
            ordered_codes[1:] != ordered_codes[:-1])))
        stops = np.concatenate(
            (starts[1:], np.asarray((order.size,))))
        for start, stop in zip(starts, stops, strict=True):
            positions = order[start:stop]
            output.append(_block_from_rows(
                frontier.source.source_sha256,
                frontier.lane_id,
                int(page.page),
                (int(tile_y[positions[0]]), int(tile_x[positions[0]])),
                (
                    (
                        int((int(page.cells_yx[position, 0]) % 64) * 64
                            + int(page.cells_yx[position, 1]) % 64),
                        np.asarray(
                            [page.printed_llr[position]],
                            dtype="<f4").tobytes(),
                        origins[int(page.window_indices[position])],
                    )
                    for position in positions
                ),
            ))
    return tuple(output)


def test_k_converter_is_byte_identical_to_naive_oracle(k_spec) -> None:
    cells = _payload_cells(k_spec, (0, 0), 4)
    far = _payload_cells(k_spec, (0, 1), 2)
    capture = freeze_capture_evidence(
        _SOURCE, k_spec,
        (
            _k_window(0, cells[:2], (0.10, 0.11), loss=2.0),
            _k_window(2, cells[2:4], (0.30, 0.31), loss=1.0),
            _k_window(1, cells[1:3], (0.20, 0.21), loss=1.0),
            _k_window(4, far, (0.40, 0.41), loss=3.0),
        ))
    dependencies = {"placement-1": ("b" * 64,)}
    blocks = blocks_from_frontier(capture, dependencies)
    expected = _naive_k_blocks(capture, dependencies)
    assert len(blocks) == len(expected) == 2
    for block, oracle in zip(blocks, expected, strict=True):
        assert block.to_bytes() == oracle.to_bytes()
        assert block.block_id == oracle.block_id


def test_k_converter_tolerates_retained_refused_window(k_spec) -> None:
    """A capture legally retains refused windows, which own nothing.

    The converter must mint origins for owning windows only.  Regression
    pin for the 2026-08-02 crash ("evidence block: owner window has no
    held-out loss") on the first real K capture that retained a
    starved-window refusal; blocks must be byte-identical to the same
    capture without the refused row.
    """
    cells = _payload_cells(k_spec, (0, 0), 4)
    far = _payload_cells(k_spec, (0, 1), 2)
    accepted = (
        _k_window(0, cells[:2], (0.10, 0.11), loss=2.0),
        _k_window(2, cells[2:4], (0.30, 0.31), loss=1.0),
        _k_window(1, cells[1:3], (0.20, 0.21), loss=1.0),
        _k_window(4, far, (0.40, 0.41), loss=3.0),
    )
    with_refused = freeze_capture_evidence(
        _SOURCE, k_spec,
        (*accepted, _k_window(3, cells, accepted=False)))
    without_refused = freeze_capture_evidence(_SOURCE, k_spec, accepted)
    dependencies = {"placement-1": ("b" * 64,)}
    blocks = blocks_from_frontier(with_refused, dependencies)
    expected = blocks_from_frontier(without_refused, dependencies)
    assert len(blocks) == len(expected) == 2
    for block, oracle in zip(blocks, expected, strict=True):
        assert block.to_bytes() == oracle.to_bytes()
        assert block.block_id == oracle.block_id


def _naive_color_blocks(frontier, dependencies):
    """Test-local oracle: the pre-change per-element color converter."""
    from holo.receive.evidence_blocks import EvidenceOrigin
    origins = tuple(
        EvidenceOrigin(
            window.placement_id, window.patch_id,
            window.heldout_logloss,
            tuple(sorted(set(dependencies.get(
                window.placement_id, ())))))
        for window in frontier.windows)
    output = []
    for page in frontier.pages:
        if page.cells_yx.shape[0] == 0:
            continue
        tile_y = page.cells_yx[:, 0].astype(np.int64) // 64
        tile_x = page.cells_yx[:, 1].astype(np.int64) // 64
        page_tiles_x = int(tile_x.max()) + 1 if tile_x.size else 0
        tile_codes = tile_y * max(page_tiles_x, 1) + tile_x
        order = np.argsort(tile_codes, kind="stable")
        ordered_codes = tile_codes[order]
        starts = np.flatnonzero(np.concatenate((
            np.asarray((True,)),
            ordered_codes[1:] != ordered_codes[:-1])))
        stops = np.concatenate(
            (starts[1:], np.asarray((order.size,))))
        for start, stop in zip(starts, stops, strict=True):
            positions = order[start:stop]
            output.append(block_from_rows(
                frontier.source.source_sha256,
                frontier.lane_id,
                int(page.page),
                (int(tile_y[positions[0]]), int(tile_x[positions[0]])),
                (
                    (
                        int((int(page.cells_yx[position, 0]) % 64) * 64
                            + int(page.cells_yx[position, 1]) % 64),
                        page.evidence_values[position],
                        origins[int(page.window_indices[position])],
                    )
                    for position in positions
                ),
                kind=frontier.evidence_kind,
            ))
    return tuple(output)


def test_color_converter_is_byte_identical_to_naive_oracle() -> None:
    spec = make_spec("c3-cmy7-p120-v0")
    source = EvidenceSource("1" * 64, "lane-c")
    flat = np.sort(
        pilots.color_payload_cell_indices(spec.family_seed))[:6]
    cells = np.column_stack((flat // 64, flat % 64)).astype(np.int32)
    shifted = cells + np.asarray((0, 64), np.int32)
    rng = np.random.default_rng(7)

    def window(patch_id, loss, selected):
        return ColorWindowEvidence(
            source=source,
            placement_id=f"placement-{patch_id}",
            patch_id=patch_id,
            region_id="region",
            page=0,
            page_cells_yx=selected,
            evidence_values=rng.normal(
                0.0, 1.0, (selected.shape[0], 6)).astype(np.float32),
            heldout_logloss=loss,
            evidence_kind=color_payload.COLOR_CMY7_KIND,
        )

    windows = (
        window(0, 0.5, cells),
        window(1, 0.25, np.concatenate((cells[3:], shifted))),
    )
    frontier = ColorCaptureEvidence(
        source, spec.spec_id, color_payload.COLOR_CMY7_KIND, windows,
        color_payload._freeze(source, spec, windows), ())
    blocks = color_blocks_from_frontier(frontier)
    expected = _naive_color_blocks(
        frontier,
        {window.placement_id: window.dependency_certificate_ids
         for window in frontier.windows})
    assert len(blocks) == len(expected) == 2
    for block, oracle in zip(blocks, expected, strict=True):
        assert block.to_bytes() == oracle.to_bytes()
        assert block.block_id == oracle.block_id


def _naive_physical_cell_ids(rows):
    """Test-local oracle: the pre-change tuple/dict id enumeration."""
    physical_keys = sorted({
        (row.page, int(cell[0]), int(cell[1]))
        for row in rows for cell in row.page_cells_yx
    })
    physical_ids = {key: value for value, key in enumerate(physical_keys)}
    return tuple(
        np.asarray([
            physical_ids[(row.page, int(cell[0]), int(cell[1]))]
            for cell in row.page_cells_yx
        ], np.int64)
        for row in rows
    )


def test_physical_cell_ids_match_naive_tuple_oracle(k_spec) -> None:
    cells_a = _payload_cells(k_spec, (0, 0), 5)
    cells_b = _payload_cells(k_spec, (0, 1), 4)
    rows = (
        _k_window(0, cells_a, (0.1,) * 5, loss=1.0),
        _k_window(1, np.concatenate((cells_a[2:], cells_b)),
                  (0.1,) * 7, loss=1.5),
        _k_window(2, cells_b, (0.1,) * 4, loss=2.0, page=3),
    )
    ids = _payload_context._physical_cell_ids(rows)
    expected = _naive_physical_cell_ids(rows)
    assert len(ids) == len(expected) == 3
    for got, oracle in zip(ids, expected, strict=True):
        assert got.dtype == oracle.dtype
        assert np.array_equal(got, oracle)


def test_region_context_is_identical_under_naive_id_oracle(
    k_spec, monkeypatch,
) -> None:
    """apply_region_context differential: fast ids vs the dict oracle."""
    cells = _payload_cells(k_spec, (0, 0), 6)
    labels = np.where(
        np.arange(6) % 2 == 0, 0, 1).astype(np.int8)

    def window(patch_id, offset):
        row = _k_window(
            patch_id, cells + np.asarray((0, offset), np.int32),
            tuple(0.1 * (index + 1) for index in range(6)),
            loss=1.0 + 0.1 * patch_id)
        return WindowEvidence(**{
            **{name: getattr(row, name)
               for name in row.__dataclass_fields__},
            "reference_values": labels,
        })

    rows = (window(0, 0), window(1, 2))
    label_rows = (window(2, 4),)
    fast_rows, fast_decisions = _payload_context.apply_region_context(
        rows, label_rows)
    monkeypatch.setattr(
        _payload_context, "_physical_cell_ids",
        _naive_physical_cell_ids)
    naive_rows, naive_decisions = _payload_context.apply_region_context(
        rows, label_rows)
    assert len(fast_decisions) == len(naive_decisions) == 1
    fast, naive = fast_decisions[0], naive_decisions[0]
    assert fast.decision_id == naive.decision_id
    for name in fast.__dataclass_fields__:
        left = getattr(fast, name)
        right = getattr(naive, name)
        if isinstance(left, np.ndarray):
            assert np.array_equal(left, right)
        else:
            assert left == right
    for left, right in zip(fast_rows, naive_rows, strict=True):
        assert np.array_equal(left.printed_llr, right.printed_llr)
        assert left.heldout_logloss == right.heldout_logloss
        assert left.detector_profile == right.detector_profile


def _naive_known_owners(rows, features):
    """Test-local oracle: the pre-change per-fit ownership + gather."""
    owned = {}
    for window, values in sorted(
        zip(rows, features, strict=True),
        key=lambda pair: int(pair[0].patch.patch_id),
    ):
        for index in np.flatnonzero(window.states >= 0):
            cell = window.page_cells_yx[index]
            key = (window.patch.candidate.page,
                   int(cell[0]), int(cell[1]))
            owned.setdefault(
                key,
                (values[index], int(window.states[index]),
                 int(window.furniture_kind[index])))
    ordered = [owned[key] for key in sorted(owned)]
    keys = np.asarray(sorted(owned), np.int64)
    return (
        np.asarray([row[0] for row in ordered], np.float64),
        np.asarray([row[1] for row in ordered], np.int64),
        np.asarray([row[2] for row in ordered], np.int8),
        keys,
    )


def _fitting_row(patch_id, page, cells, states, kinds):
    return SimpleNamespace(
        patch=SimpleNamespace(
            patch_id=patch_id,
            candidate=SimpleNamespace(page=page)),
        page_cells_yx=np.asarray(cells, np.int64),
        states=np.asarray(states, np.int64),
        furniture_kind=np.asarray(kinds, np.int8),
    )


def test_owner_selection_matches_naive_known_owners_oracle() -> None:
    rng = np.random.default_rng(11)
    cells_a = np.asarray(((0, 0), (0, 1), (1, 0), (2, 2)), np.int64)
    cells_b = np.asarray(((0, 1), (1, 0), (3, 3), (4, 4)), np.int64)
    rows = (
        _fitting_row(5, 0, cells_a, (0, 3, -1, 6), (0, 1, -1, 0)),
        _fitting_row(2, 0, cells_b, (1, 2, 4, -1), (1, 0, 1, -1)),
    )
    features = tuple(
        rng.normal(0.0, 1.0, (4, 3)) for _row in rows)
    selection = color_fitting._owner_selection(rows)
    gathered = selection.gather(features)
    naive_features, naive_states, naive_kinds, naive_keys = (
        _naive_known_owners(rows, features))
    assert gathered.tobytes() == naive_features.tobytes()
    assert np.array_equal(selection.states, naive_states)
    assert np.array_equal(selection.kinds, naive_kinds)
    assert np.array_equal(selection.keys, naive_keys)
    assert np.array_equal(
        selection.search,
        color_fitting._deterministic_fit_split(
            naive_states, naive_keys))
    # The second fit's gather reuses the SAME frozen selection.
    second = tuple(
        rng.normal(0.0, 1.0, (4, 3)) for _row in rows)
    assert selection.gather(second).tobytes() == (
        _naive_known_owners(rows, second)[0].tobytes())


def test_furniture_geometry_caches_are_exact_and_shared() -> None:
    spec = make_spec("c3-cmy7-p120-v0")
    lookup = color_anchoring._color_site_lookup(spec.family_seed)
    word, dust = pilots.color_site_cells_yx(spec.family_seed)
    naive = np.full((64, 64), -1, np.int16)
    naive[word[:, 0], word[:, 1]] = np.arange(100, dtype=np.int16)
    naive[dust[:, 0], dust[:, 1]] = 100 + np.arange(20, dtype=np.int16)
    assert np.array_equal(lookup, naive)
    assert color_anchoring._color_site_lookup(
        spec.family_seed) is lookup
    with pytest.raises(ValueError):
        lookup[0, 0] = 0

    mask = color_pool._payload_site_mask(spec.family_seed)
    naive_mask = np.zeros(4096, bool)
    naive_mask[pilots.color_payload_cell_indices(
        spec.family_seed)] = True
    assert np.array_equal(mask, naive_mask)
    assert color_pool._payload_site_mask(spec.family_seed) is mask
    with pytest.raises(ValueError):
        mask[0] = True


def _cmy8_fixture(collapse_pair: tuple[int, int] | None):
    """Training/calibration data with an optionally collapsed state pair."""
    rng = np.random.default_rng(29)
    means = np.asarray([
        [10.0 * ((state >> plane) & 1) for plane in range(3)]
        for state in range(8)
    ])
    if collapse_pair is not None:
        means[collapse_pair[1]] = means[collapse_pair[0]]
    states = np.repeat(np.arange(8), 12)
    features = means[states] + rng.normal(0.0, 0.3, (states.size, 3))
    calibration_states = np.repeat(np.arange(8), 4)
    calibration = means[calibration_states] + rng.normal(
        0.0, 0.3, (calibration_states.size, 3))
    return features, states, calibration, calibration_states


def test_pava_skip_for_qda_zeroed_planes_is_result_identical(
    monkeypatch,
) -> None:
    """color-upstream:10: no PAVA fit for planes the QDA guard erases."""
    features, states, calibration, calibration_states = _cmy8_fixture(
        (6, 7))  # states 6/7 differ only in plane 0 -> plane 0 clipped
    calls: list[int] = []
    actual_pava = color_detect._pava_map

    def counting_pava(scores, labels):
        calls.append(1)
        return actual_pava(scores, labels)

    monkeypatch.setattr(color_detect, "_pava_map", counting_pava)
    detector = fit_cmy8_detector(
        features, states, calibration, calibration_states)
    assert detector.qda.clipped_planes == (0,)
    assert not detector.qda.degenerate
    assert detector.supported_planes == (False, True, True)
    assert len(calls) == 2  # planes 1 and 2 only

    # Oracle: the pre-change detector fitted plane 0's map anyway.
    support = qualify_cmy8_calibration_support(
        np.asarray(calibration_states))
    assert support.supported_planes == (True, True, True)
    raw = cmy8_raw_llrs(detector.qda, np.asarray(calibration, np.float64))
    oracle_maps = tuple(
        actual_pava(
            raw[:, plane],
            (np.asarray(calibration_states) >> plane) & 1)
        for plane in range(3))
    oracle = CMY8Detector(
        qda=detector.qda,
        calibrations=oracle_maps,
        calibration_labels=int(np.asarray(calibration_states).size),
        calibration_support=support,
    )
    probe = np.asarray(
        np.random.default_rng(31).normal(5.0, 4.0, (64, 3)))
    assert detector.llrs(probe).tobytes() == oracle.llrs(probe).tobytes()


def test_pava_skip_on_degenerate_qda_fits_no_maps(monkeypatch) -> None:
    features, states, calibration, calibration_states = _cmy8_fixture(None)
    keep = states != 7  # state 7 absent from training -> degenerate QDA
    calls: list[int] = []
    actual_pava = color_detect._pava_map

    def counting_pava(scores, labels):
        calls.append(1)
        return actual_pava(scores, labels)

    monkeypatch.setattr(color_detect, "_pava_map", counting_pava)
    detector = fit_cmy8_detector(
        features[keep], states[keep], calibration, calibration_states)
    assert detector.qda.degenerate
    assert detector.supported_planes == (False, False, False)
    assert not calls
    probe = np.asarray(
        np.random.default_rng(37).normal(5.0, 4.0, (16, 3)))
    assert np.array_equal(detector.llrs(probe), np.zeros((16, 3)))


def test_window_raw_crops_equal_naive_probe_and_base_reads() -> None:
    """color-upstream:07: the shared crop equals both former reads."""
    rng = np.random.default_rng(41)
    image = rng.integers(0, 256, (180, 200, 3), dtype=np.uint8)

    from holo.receive.scan import open_capture
    raster = open_capture(image, 1200.0)

    from test_receive_bounded_sampling import _patch
    patch = _patch(0, (17, 23), (0, 0), shape_yx=(16, 18), pitch=4.0)
    crops = color_sampling.window_raw_crops(raster, (patch,), 4.0)
    assert set(crops) == {0}
    y0, x0, raw = crops[0]
    naive_y0, naive_x0, naive_raw = color_sampling.native_crop(
        raster, color_sampling.window_points(patch),
        color_sampling.window_halo(4.0))
    assert (y0, x0) == (naive_y0, naive_x0)
    assert np.array_equal(raw, naive_raw)
    # The divisor probe over the shared crop equals the former
    # _window_maximum(raster, patch, pitch) = max over the same footprint.
    assert float(np.max(raw)) == float(np.max(naive_raw))


def test_emission_mask_computed_once_per_promoted_window(
    monkeypatch,
) -> None:
    """color-payload:06: the open_flags mask is reused by the emit loop."""
    from test_receive_color_payload import _fixture
    spec, _field, raster, _patch_row, address, source = _fixture(
        "c2-cmy7-p120-v0@3328x2304", (1, 1))
    calls: list[int] = []
    actual = color_payload._emission_mask

    def counting(*args, **kwargs):
        calls.append(1)
        return actual(*args, **kwargs)

    monkeypatch.setattr(color_payload, "_emission_mask", counting)
    evidence = color_payload.collect_color_evidence(
        raster, source, address, spec)
    assert evidence.windows
    assert len(calls) == len(address.payload_placements)
