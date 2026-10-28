"""Synthetic page/segment fixtures extracted from the retired
receive.qualification.e023c_refine module (holo-v1-kiss excision).
Used by test_receive_bch_quarantine and test_receive_refined_reuse."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

import numpy as np


from holo.format import metadata
from holo.format.descriptor import CODINGS, FormatSpec
from holo.gen.compose import compose_page_cells
from holo.receive.evidence import TileCertificateRecord
from holo.receive.records import certificate_record_from_user_bits
from holo.receive import certified_refine as refine
from holo.receive import detect, tiles
from holo.receive._payload_sampling import _scores
from holo.receive.payload import format_reference_values
from holo.receive.payload_model import (
    CONTEXT_PROFILE,
    ContextDecision,
    EvidenceSource,
    WindowEvidence,
)
from holo.receive.placement.model import (
    AffinePose,
    PlacedSegment,
    PoseSegment,
    PoseWindow,
)


@dataclass(frozen=True, slots=True)
class _ArrayRaster:
    image: np.ndarray
    dpi: float

    @property
    def shape(self) -> tuple[int, int]:
        return tuple(int(value) for value in self.image.shape)

    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        return self.image[r0:r1, c0:c1]


@dataclass(frozen=True, slots=True)
class _PageFixture:
    spec: FormatSpec
    symbols: np.ndarray
    field: np.ndarray
    raster: _ArrayRaster
    certificates: tuple[TileCertificateRecord, ...]


@dataclass(frozen=True, slots=True)
class _SegmentFixture:
    request: refine.SegmentRefinementRequest
    image: refine.RefinementRegionImage
    true_pose: AffinePose


def _page_fixture() -> _PageFixture:
    spec = FormatSpec(CODINGS["c3-r0550"], "e023c-refine-q", (35.0, 35.0), 1.0)
    rng = np.random.default_rng(23031)
    symbols = rng.integers(
        0, 2, (spec.tiles_per_page, spec.symbol_bits), dtype=np.uint8
    )
    version, k_total, page = 0, 197, 0
    field = compose_page_cells(spec, page, symbols, k_total, version)
    meta = metadata.encode_metadata(version, k_total)
    certificates: list[TileCertificateRecord] = []
    tiles_x = spec.layout.tiles_yx[1]
    for index, symbol in enumerate(symbols):
        ty, tx = divmod(index, tiles_x)
        counter = spec.tile_counter(page, ty, tx)
        user = np.concatenate((
            np.asarray([metadata.tile_bit(meta, counter)], np.uint8),
            symbol)).astype(np.uint8)
        certificates.append(certificate_record_from_user_bits(
            spec, page=page, tile_yx=(ty, tx), stream_id="main",
            user_bits=user,
            origin_attempt_id=f"fixture-attempt-{index}"))
    ppc = 8
    levels = np.where(field > 0, 24.0, 232.0).astype(np.float32)
    image = np.kron(levels, np.ones((ppc, ppc), np.float32))
    return _PageFixture(
        spec, symbols, field, _ArrayRaster(image, 1200.0), tuple(certificates)
    )


def _segment_fixture(
    page: _PageFixture,
    *,
    window_id: int,
    region_index: int,
    page_origin_yx: tuple[int, int] = (64, 64),
    shift_yx_cells: tuple[float, float] = (0.125, -0.125),
) -> _SegmentFixture:
    shape = (128, 128)
    ppc = 8.0
    center = (ppc - 1.0) * 0.5
    true_origin = (
        page_origin_yx[0] * ppc + center,
        page_origin_yx[1] * ppc + center,
    )
    true_pose = AffinePose(
        true_origin, ((ppc, 0.0), (0.0, ppc)), (0.5, 0.5), ppc, 0.0
    )
    shifted_origin = tuple(
        float(value) for value in (
            np.asarray(true_origin)
            + true_pose.matrix() @ np.asarray(shift_yx_cells, np.float64)
        )
    )
    initial_pose = AffinePose(
        shifted_origin, true_pose.jacobian_yx, (0.5, 0.5), ppc, 0.0
    )
    window = PoseWindow(
        window_id, region_index, (0, 0), shape,
        support_estimate=shape[0] * shape[1],
    )
    segment = PoseSegment(
        window, initial_pose, shape[0] * shape[1],
        1.0, (ppc, ppc), 0.0,
    )
    gy, gx = np.indices(shape)
    local = np.stack((gy.ravel(), gx.ravel()), axis=1).astype(np.int32)
    placed = PlacedSegment(segment, page_origin_yx, 0, local)
    image = refine.prepare_region_image(page.raster, region_index, (segment,))
    raw = refine._sample(image, initial_pose, local)
    page_cells = local.astype(np.int64) + np.asarray(page_origin_yx, np.int64)
    reference = format_reference_values(page.spec, 0, page_cells)
    # v0.39 (ruling 10.2): gen-0 fixture evidence rides the ONE production
    # float32-native score transform instead of a local replica.
    scores = _scores(raw)
    known = reference >= 0
    heldout = ((131 * page_cells[:, 0] + 17 * page_cells[:, 1]) & 1).astype(bool)
    search = known & ~heldout
    validation = known & heldout
    identity = f"qualification/window-{window_id}"
    page_width = page.spec.layout.cells_yx[1]
    site_ids = page_cells[:, 0] * page_width + page_cells[:, 1]
    fit = detect.fit_calibration(
        detect.CalibrationObservations(
            identity, scores[search], reference[search], site_ids[search]
        ),
        detect.CalibrationObservations(
            identity, scores[validation], reference[validation],
            site_ids[validation],
        ),
    )
    if not fit.accepted or fit.calibration is None:
        raise AssertionError(f"qualification detector refused: {fit.reason}")
    llr = np.asarray(fit.calibration.llr(scores), np.float32)
    generation0 = WindowEvidence(
        source=EvidenceSource(
            hashlib.sha256(b"capture-q").hexdigest(), "lane-q"),
        placement_id=identity,
        patch_id=window_id,
        region_id=f"qualification/region-{region_index}",
        page=0,
        redundant=False,
        segment_id=window_id,
        segment_local_cells_yx=local,
        page_cells_yx=page_cells,
        scan_points_yx=initial_pose.points(local),
        raw_means=raw,
        scores=scores,
        reference_values=reference,
        calibration_score_nodes=fit.calibration.knots,
        calibration_probability_nodes=fit.calibration.probabilities,
        baseline_printed_llr=llr,
        printed_llr=llr,
        accepted=True,
        refusal_reason="",
        n_search_0=fit.n_search_0,
        n_search_1=fit.n_search_1,
        n_heldout=fit.n_heldout,
        heldout_logloss=fit.heldout_logloss,
    )
    return _SegmentFixture(
        refine.SegmentRefinementRequest(placed, generation0), image, true_pose
    )


def _certificates_for_segment(
    page: _PageFixture, origin: tuple[int, int] = (64, 64)
) -> tuple[TileCertificateRecord, ...]:
    ty0, tx0 = origin[0] // 64, origin[1] // 64
    selected = []
    for certificate in page.certificates:
        ty, tx = certificate.tile_yx
        if ty0 <= ty < ty0 + 2 and tx0 <= tx < tx0 + 2:
            selected.append(certificate)
    return tuple(selected)
