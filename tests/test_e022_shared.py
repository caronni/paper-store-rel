"""Parity locks for E022's shared combination and A/B/C view seams."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "experiments/022-pilot-tile-search"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from paperholo import pilotcombine, pilotdiag, pilotsearch  # noqa: E402
from paperholo.platen import PayloadRegion, PayloadSurvey  # noqa: E402
import run_e022  # noqa: E402
import session_e022  # noqa: E402


def _result(scan_id: str, region_index: int, bit: int, *, bch_ok=None):
    pose = pilotsearch.AffinePose(
        origin_yx=(10.0, 20.0),
        jacobian_yx=((8.0, 0.0), (0.0, 8.0)),
        angle_deg=0.0,
        pitch_px=8.0,
        phase_yx=(0.0, 0.0),
        footing_factor=3,
    )
    placement = pilotsearch.PlacedWindow(
        region_index=region_index,
        window=pilotsearch.Window(0, 0, 60, 60, 3600),
        page=0,
        origin_yx=(0, 0),
        rot_k=0,
        method="correlation",
        mismatch=0.05,
        validation_mismatch=0.04,
        rival_mismatch=0.30,
        support=100,
        pose=pose,
        elapsed_s=0.1,
        scan_id=scan_id,
        page_cells_yx=np.array([[0, 0], [1, 1]], np.int32),
    )
    observation = pilotsearch.PilotObservation(
        region_index=region_index,
        window_yx=(0, 0),
        scan_yx=(10.0, 20.0),
        bit=bit,
        expected=bit,
        weight=1.0,
        method="correlation",
        scan_id=scan_id,
    )
    tile = pilotsearch.PilotTileEvidence(
        page=0,
        tile_y=0,
        tile_x=0,
        expected_bits=np.zeros(100, np.uint8),
        observations={0: [observation]},
        bch_ok=bch_ok,
        bch_attempted=bch_ok is not None,
        bch_refused=bch_ok is False,
    )
    return pilotsearch.SearchResult(
        placements=[placement],
        tiles={(0, 0, 0): tile},
        region_states={region_index: "accepted"},
        timings={"total_s": 1.0},
        diagnostics={"scan_id": scan_id},
    )


def _combined_snapshot(result: pilotsearch.SearchResult) -> tuple:
    placements = tuple(
        (
            row.scan_id,
            row.region_index,
            row.diagnostics["scan_id"],
            row.diagnostics["source_region_index"],
        )
        for row in result.placements
    )
    tiles = tuple(
        (
            key,
            tile.bch_ok,
            tile.bch_attempted,
            tile.bch_refused,
            tile.expected_bits.tobytes(),
            tuple(
                (
                    site,
                    tuple(
                        (row.scan_id, row.region_index, row.bit)
                        for row in observations
                    ),
                )
                for site, observations in sorted(tile.observations.items())
            ),
        )
        for key, tile in sorted(result.tiles.items())
    )
    return (
        placements,
        tiles,
        tuple(sorted(result.region_states.items())),
        tuple(sorted(result.timings.items())),
        result.diagnostics,
    )


def test_shared_combiner_matches_session_wrapper_and_is_pure() -> None:
    descriptor = run_e022.E018
    first = _result("s000", 1, 0, bch_ok=False)
    second = _result("s001", 0, 1, bch_ok=True)
    scans = [
        SimpleNamespace(scan_id="s000", region_count=2, result=first),
    ]
    session = SimpleNamespace(scans=scans, pages=(0, 2))
    current = ("s001", 3, second)
    inputs_before = pickle.dumps((first, second))

    compatibility = session_e022.combine_results(
        session, descriptor, current=current, decode_words=False
    )
    shared = pilotcombine.combine_search_results(
        [
            pilotcombine.SearchResultPart("s000", 2, first),
            pilotcombine.SearchResultPart("s001", 3, second),
        ],
        descriptor,
        pages=(0, 2),
        decode_words=False,
    )

    assert _combined_snapshot(compatibility) == _combined_snapshot(shared)
    assert [row.region_index for row in shared.placements] == [1, 2]
    assert shared.region_states == {1: "accepted", 2: "accepted"}
    assert shared.tiles[(0, 0, 0)].bch_ok is True
    assert shared.tiles[(0, 0, 0)].bch_refused is True
    assert shared.diagnostics == {
        "session_scans": ["s000", "s001"],
        "scan_count": 2,
        "format_id": descriptor.format_id,
        "pages": [0, 2],
    }
    assert pickle.dumps((first, second)) == inputs_before


def test_e022_cli_exports_exact_shared_diagnostic_primitives() -> None:
    # Existing qualification scripts keep working, while new orchestrators
    # import these implementations from paperholo rather than a CLI module.
    assert run_e022.scan_panel is pilotdiag.scan_panel
    assert run_e022.placement_panel is pilotdiag.placement_panel
    assert run_e022.pilot_panel is pilotdiag.pilot_panel
    assert run_e022.compose_diagnostic is pilotdiag.compose_diagnostic
    assert run_e022.render_diagnostic is pilotdiag.render_diagnostic
    assert run_e022.diagnostic_png_bytes is pilotdiag.diagnostic_png_bytes
    assert run_e022.search_result_report is pilotdiag.search_result_report

    descriptor = run_e022.E018
    image = np.full((160, 220), 210.0, np.float32)
    region = PayloadRegion(
        (20, 30, 80, 100),
        np.ones((80, 100), bool),
        area_mm2=10.0,
        angle_hint_deg=None,
        score=5.0,
    )
    survey = PayloadSurvey((region,), c_dots=3, cell_pitch_px=8.0)
    result = _result("s000", 0, 0)

    via_cli = run_e022.diagnostic_png_bytes(
        image, survey, result, descriptor, active_region=0, panel_width=180
    )
    via_library = pilotdiag.diagnostic_png_bytes(
        image, survey, result, descriptor, active_region=0, panel_width=180
    )
    assert via_cli == via_library
    assert (
        run_e022.search_result_report(result, descriptor)
        == pilotdiag.search_result_report(result, descriptor)
    )
