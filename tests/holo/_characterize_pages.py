"""Synthetic characterization pages and the two ways to read them.

Split out of test_characterize_analyze (2026-09-20) when that module —
one xdist group, and so the wall of both the slow and the sweeps lane —
became three: the ungated units and refusals stay there, the
calibration-report facets and the two slow-lane measurement arms are
test_characterize_reports, the whole-page instrument proofs are
test_characterize_sweeps.  All three paint pages the same way, so the
painter lives here.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from holo.characterize.fields import measure_all_fields
from holo.characterize.geometry import register_blind
from holo.characterize.model import (
    BASE_DPI,
    CANDIDATES_BY_CODE,
    Identity,
)
from holo.characterize.patterns import (
    expand_state_planes,
    field_states,
    pattern_bits,
)
from holo.characterize.summarize import summarize_candidates
from holo.characterize.raster import RasterSource
from holo.characterize.report import (
    DeviceSelfReport,
    encode_report_payload,
    payload_to_modules,
)


def _candidate(kind: str, grid: tuple[int, int],
               cell: tuple[int, int]) -> int:
    return next(
        code for code, candidate in CANDIDATES_BY_CODE.items()
        if candidate.page_kind == kind
        and candidate.grid_dpi == grid
        and candidate.cell_dots == cell
        and candidate.emission_path == "single-plane-imagemask"
    )


def _paint_page(page: dict, *, dpi: int = 300,
                color: bool = False) -> np.ndarray:
    height = round(297.0 / 25.4 * dpi)
    width = round(210.0 / 25.4 * dpi)
    canvas = np.full(
        (height, width, 3) if color else (height, width), 255, np.uint8
    )

    def paint(bits: np.ndarray, x: int, y: int,
              source_dpi: tuple[int, int],
              planes: tuple[str, ...] = ("K",)) -> None:
        target_width = max(1, round(bits.shape[1] * dpi / source_dpi[0]))
        target_height = max(1, round(bits.shape[0] * dpi / source_dpi[1]))
        scaled = np.asarray(
            Image.fromarray((bits * 255).astype(np.uint8)).resize(
                (target_width, target_height), Image.Resampling.NEAREST
            )
        )
        x0 = round(x * dpi / source_dpi[0])
        y0 = round(y * dpi / source_dpi[1])
        crop = canvas[y0:y0 + target_height, x0:x0 + target_width]
        selected = scaled != 0
        if not color:
            crop[selected] = 0
        else:
            for plane in planes:
                if plane == "K":
                    crop[selected, :] = 0
                else:
                    channel = {"C": 0, "M": 1, "Y": 2}[plane]
                    crop[..., channel][selected] = 0

    identity_record = page["identity"]
    identity = Identity(
        stage=identity_record["stage"],
        kind=identity_record["kind"],
        copy_index=identity_record["copy_index"],
        request_code=identity_record["request_code"],
        candidate_codes=tuple(identity_record["candidate_codes"]),
        layout_digest=identity_record["layout_digest"],
    )
    device = DeviceSelfReport(
        language_level=3,
        default_resolution=(600, 600),
        effective_resolution=(600, 600),
        page_size_points=(595, 842),
        imaging_bbox=(0, 0, 595, 842),
        duplex=False,
        tumble=False,
        process_color_model=("DeviceRGB" if color else "DeviceGray"),
        product="synthetic-printer",
        version="1",
        revision=1,
        serial="synthetic-001",
        print_nonce=identity.copy_index + 1,
    )
    report_modules = payload_to_modules(
        encode_report_payload(identity, device)
    )
    for record in page["infrastructure"]:
        if record["kind"] == "corner_mark":
            bits = pattern_bits({
                "kind": "chiral_corner",
                "w_source_dots": record["w_layout_dots"],
                "h_source_dots": record["h_layout_dots"],
                "params": {
                    "satellites": record["satellites"],
                    "inward": record["inward"],
                    "stroke_dots": 3,
                },
            })
            paint(
                bits, record["x_layout_dots"], record["y_layout_dots"],
                (BASE_DPI, BASE_DPI),
            )
        elif record["kind"] == "geometry_plus":
            bits = pattern_bits({
                "kind": "plus_mark",
                "w_source_dots": record["w_layout_dots"],
                "h_source_dots": record["h_layout_dots"],
                "params": {"stroke_dots": 3},
            })
            paint(
                bits, record["x_layout_dots"], record["y_layout_dots"],
                (BASE_DPI, BASE_DPI),
            )
        elif record["kind"] == "machine_report":
            module = record["module_layout_dots"]
            bits = np.repeat(
                np.repeat(report_modules, module, axis=0), module, axis=1
            )
            paint(
                bits,
                record["x_layout_dots"],
                record["y_layout_dots"],
                (BASE_DPI, BASE_DPI),
            )

    for probe in page["probes"]:
        params = probe.get("params", {})
        paint(
            pattern_bits(probe),
            probe["x_source_dots"],
            probe["y_source_dots"],
            tuple(probe["source_dpi"]),
            tuple(params.get("planes", (probe["plane"],))),
        )
    for field in page["fields"]:
        candidate = CANDIDATES_BY_CODE[field["candidate_code"]]
        planes = expand_state_planes(field_states(field, candidate), candidate)
        for plane, bits in planes.items():
            paint(
                bits,
                field["x_source_dots"],
                field["y_source_dots"],
                candidate.grid_dpi,
                (plane,),
            )
    return canvas


# analyze_scan's own composition, restricted to one candidate's calibration
# fields: a test that reads only summary rows for that candidate gets the same
# numbers without paying for the common probe pass or the other families' edge
# canaries, which summarize_candidates drops anyway (2026-09-05).
def _measure_calibration_candidate(
    page: dict, code: int, scan: np.ndarray,
) -> tuple[list[dict], list[dict], dict]:
    source = RasterSource(scan)
    affine, geometry = register_blind(
        source, 300, 300, corner_layout=page["infrastructure"],
    )
    rows = measure_all_fields(source, affine, [
        field for field in page["fields"]
        if field["candidate_code"] == code
        and field.get("family") == "calibration"
    ])
    return rows, summarize_candidates(rows), geometry

