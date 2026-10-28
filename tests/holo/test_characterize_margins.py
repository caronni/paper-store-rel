"""Margin/verdict campaign fixtures (workplan W1/W3/W4, 028.2).

The retired tick rule failed solidly printed ticks on 1-3 dot
displacement; this battery pins the registered scorer on displaced,
partially clipped, and absent ticks, the clip-line aggregation, the
data-only payload edge curves, and the capacity/rung/registration
summary products.
"""
from __future__ import annotations

import numpy as np

from holo.characterize.probes import measure_probe
from holo.characterize.raster import RasterSource
from holo.characterize.summarize import (
    summarize_capacity_by_margin,
    summarize_rung_planning,
)
from holo.characterize.summarize_physical import (
    summarize_payload_edges,
    summarize_physical_ticks,
)

AFFINE = np.asarray([[2.0, 0.0, 40.0], [0.0, 2.0, 40.0]])
DOT_MM = 25.4 / 600.0


def _tick_probe(gap_mm: float = 4.0, edge: str = "left") -> dict:
    return {
        "probe_id": f"edge-tick/{edge}/{gap_mm:g}",
        "kind": "edge_tick",
        "group": "physical-ink-extent",
        "plane": "K",
        "params": {"edge": edge, "gap_mm": gap_mm},
        "x_layout_dots": 60.0,
        "y_layout_dots": 60.0,
        "w_layout_dots": 28.0,
        "h_layout_dots": 28.0,
        "w_source_dots": 28,
        "h_source_dots": 28,
        "source_dpi": [600, 600],
        "seed_label": "synthetic/tick",
    }


def _raster_with_tick(
    *,
    dx_dots: float = 0.0,
    dy_dots: float = 0.0,
    clipped_from_dots: float | None = None,
    absent: bool = False,
) -> RasterSource:
    canvas = np.full((400, 400), 255, np.uint8)
    if not absent:
        x0 = 60.0 + dx_dots + (clipped_from_dots or 0.0)
        x1 = 60.0 + dx_dots + 28.0
        y0, y1 = 60.0 + dy_dots, 60.0 + dy_dots + 28.0
        sx0 = int(round(AFFINE[0, 0] * x0 + AFFINE[0, 2]))
        sx1 = int(round(AFFINE[0, 0] * x1 + AFFINE[0, 2]))
        sy0 = int(round(AFFINE[1, 1] * y0 + AFFINE[1, 2]))
        sy1 = int(round(AFFINE[1, 1] * y1 + AFFINE[1, 2]))
        canvas[sy0:sy1, sx0:sx1] = 0
    return RasterSource(canvas)


def _measure(source: RasterSource, probe: dict) -> dict:
    result = measure_probe(source, AFFINE, probe)
    assert result["status"] == "ok"
    assert result["tick"]["scorable"] is True
    return result["tick"]


def test_registered_tick_survives_displacement() -> None:
    for dx, dy in ((0.0, 0.0), (2.0, -1.0), (-3.0, 2.5)):
        tick = _measure(
            _raster_with_tick(dx_dots=dx, dy_dots=dy), _tick_probe()
        )
        assert tick["classification"] == "full"
        assert tick["ink_fraction_registered"] >= 0.95
        got_dx, got_dy = tick["displacement_layout_dots"]
        assert abs(got_dx - dx) <= 0.75 and abs(got_dy - dy) <= 0.75
    # The retired rule's failure mode: displaced-but-solid must stay full.
    displaced = _measure(
        _raster_with_tick(dx_dots=3.0), _tick_probe()
    )
    assert displaced["ink_fraction_nominal"] < displaced[
        "ink_fraction_registered"
    ]


def test_partial_tick_yields_clip_estimate() -> None:
    clip_from = 11.0  # dots unprinted on the page-edge side
    tick = _measure(
        _raster_with_tick(clipped_from_dots=clip_from, dx_dots=1.0),
        _tick_probe(gap_mm=4.0, edge="left"),
    )
    assert tick["classification"] == "partial"
    truth_mm = 4.0 + (clip_from + 1.0) * DOT_MM
    assert abs(tick["clip_mm_estimate"] - truth_mm) <= 0.15


def test_absent_tick_reads_zero_ink() -> None:
    tick = _measure(_raster_with_tick(absent=True), _tick_probe())
    assert tick["classification"] == "absent"
    assert tick["ink_fraction_registered"] == 0.0


def _ladder_row(
    edge: str,
    gap: float,
    classification: str,
    *,
    clip: float | None = None,
) -> dict:
    tick = {
        "scorable": True,
        "classification": classification,
        "size_mm": [28.0 * DOT_MM, 28.0 * DOT_MM],
        "ink_fraction_nominal": 0.9,
        "ink_fraction_registered": {
            "full": 0.98, "partial": 0.5, "absent": 0.0
        }[classification],
        "displacement_layout_dots": [0.5, -0.5],
    }
    if clip is not None:
        tick["clip_mm_estimate"] = clip
    return {
        "probe_id": f"edge-tick/{edge}/{gap:g}",
        "group": "physical-ink-extent",
        "status": "ok",
        "tick": tick,
    }


def test_ladder_and_clip_aggregation_from_classifications() -> None:
    gaps = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0,
            10.0)
    probes = []
    for edge in ("top", "right", "bottom", "left"):
        for gap in gaps:
            if gap <= 3.0:
                probes.append(_ladder_row(edge, gap, "absent"))
            elif gap <= 4.0:
                probes.append(_ladder_row(
                    edge, gap, "partial", clip=4.15
                ))
            else:
                probes.append(_ladder_row(edge, gap, "full"))
    summary = summarize_physical_ticks(probes)
    for edge, row in summary["edges"].items():
        assert row["complete"] is True
        assert row["safe_gap_mm"] == 5.0
        assert row["first_partial_gap_mm"] == 3.5
        assert row["printable_clip_mm"] == 4.15
        lower, upper = row["clip_bounds_mm"]
        assert lower <= 4.15 <= upper
    assert summary["printable_clip_mm"]["left"] == 4.15


def test_payload_edges_are_data_not_verdicts() -> None:
    candidates = [{
        "candidate_code": 4,
        "candidate_id": "stress",
        "worst_error_wilson_upper_95": 0.037,
    }]
    fields = []
    for gap, upper, status in (
        (0.5, None, "geometry_uncertified"),
        (1.5, None, "geometry_uncertified"),
        (2.5, None, "geometry_uncertified"),
        (3.5, None, "geometry_uncertified"),
        (5.0, 0.090, "ok"),
        (6.5, 0.045, "ok"),
        (8.0, 0.041, "ok"),
        (10.0, 0.040, "ok"),
    ):
        for arm in range(2):
            fields.append({
                "family": "edge-canary",
                "edge": "left",
                "gap_mm": gap,
                "field_id": f"edge/left/{arm}/{gap:g}",
                "candidate_id": "stress",
                "candidate_code": 4,
                "status": status,
                "error_rate": None if upper is None else upper - 0.005,
                "error_wilson_95": (
                    None if upper is None else [0.0, upper]
                ),
            })
    summary = summarize_payload_edges(fields, candidates)
    left = summary["edges"]["left"]
    assert left["complete"] is True
    for gap_row in left["gaps"]:
        assert "passed" not in gap_row
        assert "exact_references_ok" not in gap_row
    assert "safe_payload_rectangle_mm" not in summary
    five = next(row for row in left["gaps"] if row["gap_mm"] == 5.0)
    assert abs(five["arms"][0]["edge_penalty"] - 0.053) < 1e-9
    # 5.0mm is above interior+0.02, so the flat suffix starts at 6.5mm.
    assert left["arm_curves"]["4"]["edge_flat_gap_mm"] == 6.5


def _usable_candidate(**overrides) -> dict:
    row = {
        "candidate_code": 5,
        "candidate_id": "bw-k2-g600-c3-single-plane-imagemask",
        "provisional_usable": True,
        "minimum_empirical_information_bits_per_mm2": 62.0,
        "window_error_quantiles": {
            "n_windows": 12, "p50": 0.001, "p90": 0.003,
            "p95": 0.005, "max": 0.01,
        },
    }
    row.update(overrides)
    return row


def test_capacity_by_margin_includes_measured_clip_row() -> None:
    table = summarize_capacity_by_margin(
        [_usable_candidate()],
        {"left": 4.13, "top": 4.14, "right": 4.28, "bottom": 4.15},
    )
    sources = [row["source"] for row in table["margins"]]
    assert sources.count("measured-clip-worst-edge") == 1
    measured = next(
        row for row in table["margins"]
        if row["source"] == "measured-clip-worst-edge"
    )
    assert measured["margin_mm"] == 4.3
    assert measured["candidates"][0]["empirical_information_bits"] > 3e6
    incomplete = summarize_capacity_by_margin(
        [_usable_candidate()], {"left": 4.13, "top": None,
                                "right": 4.28, "bottom": 4.15},
    )
    assert all(
        row["source"] == "standard" for row in incomplete["margins"]
    )


def test_rung_planning_prices_tails_not_gates() -> None:
    table = summarize_rung_planning([
        _usable_candidate(window_error_quantiles={
            "n_windows": 16, "p50": 0.03, "p90": 0.06,
            "p95": 0.09, "max": 0.12,
        }),
    ])
    assert len(table["rows"]) == 1
    rungs = table["rows"][0]["rungs"]
    # 1-h2(0.03)=0.806 clears r0700 (0.703) at p50 but p95 (0.09,
    # 1-h2=0.564) does not; the tail prices fountain overhead instead of
    # vetoing the rung.
    assert rungs["r0700"]["supported_at"]["p50"] is True
    assert rungs["r0700"]["supported_at"]["p95"] is False
    assert rungs["r0550"]["supported_at"]["p95"] is True
    assert rungs["r0859"]["supported_at"]["p50"] is False
