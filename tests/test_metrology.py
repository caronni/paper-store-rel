from __future__ import annotations

import math

from paperholo.metrology import (
    CandidateObservation,
    CandidateSpec,
    CaptureFooting,
    GridSpec,
    LdpcYield,
    observations_from_report,
    report_document,
    wilson_lower,
)


def _candidate() -> CandidateSpec:
    return CandidateSpec(
        candidate_id="k-g1200x2400-c4x8",
        grid=GridSpec(1200, 2400, 4, 8),
        constellation="k-binary",
        payload_bits_per_cell=1.0,
        planes=("K",),
        emission_path="single-plane-imagemask",
        symbol_shape="solid-cell",
        bit_levels=("K",),
    )


def test_grid_density_is_physical_and_anisotropic() -> None:
    grid = GridSpec(1200, 2400, 4, 8)
    # This is physically the same square cell pitch as 300 dpi, c1.
    control = GridSpec(300, 300, 1, 1)
    assert math.isclose(grid.cell_pitch_mm_x, control.cell_pitch_mm_x)
    assert math.isclose(grid.cell_pitch_mm_y, control.cell_pitch_mm_y)
    assert math.isclose(grid.cells_per_mm2, control.cells_per_mm2)
    assert grid.nominal_scan_samples(1200, 1200) == (4.0, 4.0)


def test_requested_and_readback_grids_remain_separate() -> None:
    footing = CaptureFooting(
        sheet_id="sheet-1",
        printer_id="printer",
        scanner_id="scanner",
        print_path="raw-ps",
        scan_mode="rgb48",
        scan_dpi_x=4800,
        scan_dpi_y=4800,
        requested_dpi=(1200, 2400),
        readback_dpi=(600, 600),
    )
    assert footing.to_dict()["requested_dpi"] == [1200, 2400]
    assert footing.to_dict()["readback_dpi"] == [600, 600]


def test_report_roundtrip_and_digest() -> None:
    candidate = _candidate()
    result = LdpcYield(
        "r0550", 2240 / 4096, 100, 100, level_id="K"
    )
    obs = CandidateObservation(
        candidate=candidate,
        stratum_id="sheet1/top",
        hard_error_rate=0.01,
        mutual_information_bpc=0.91,
        n_validation_cells=4096,
        scan_adequate=True,
        nominal_scan_samples_x=4.0,
        nominal_scan_samples_y=4.0,
        measured_scan_samples_x=4.0,
        measured_scan_samples_y=4.0,
        ldpc=(result,),
    )
    footing = CaptureFooting(
        sheet_id="sheet-1", printer_id="p", scanner_id="s",
        print_path="raw", scan_mode="grey", scan_dpi_x=1200, scan_dpi_y=1200,
    )
    document = report_document(footing=footing, observations=[obs])
    assert len(document["semantic_sha256"]) == 64
    restored = observations_from_report(document)
    assert restored == [obs]


def test_wilson_lower_is_conservative() -> None:
    assert 0.95 < wilson_lower(1000, 1000) < 1.0
    assert wilson_lower(0, 10) == 0.0
