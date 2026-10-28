"""Deterministic discovery/calibration page plans with overlap refusal."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Iterable

from .model import (
    BASE_DPI,
    CANDIDATES_BY_CODE,
    LAYOUT_VERSION,
    PAGE_MM,
    REQUEST_NAMES,
    STIMULUS_SCHEMA,
    Identity,
    discovery_candidate_codes,
    semantic_digest,
    validate_shortlist,
)
from .patterns import field_states, pattern_bits


def mm_to_dots(value: float, dpi: int = BASE_DPI) -> int:
    return int(round(value / 25.4 * dpi))


def dots_to_mm(value: float, dpi: int = BASE_DPI) -> float:
    return float(value) / dpi * 25.4


@dataclass(frozen=True)
class Rectangle:
    element_id: str
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float

    @property
    def right(self) -> float:
        return self.x_mm + self.width_mm

    @property
    def bottom(self) -> float:
        return self.y_mm + self.height_mm

    def overlaps(self, other: "Rectangle", clearance: float = 0.12) -> bool:
        return not (
            self.right + clearance <= other.x_mm
            or other.right + clearance <= self.x_mm
            or self.bottom + clearance <= other.y_mm
            or other.bottom + clearance <= self.y_mm
        )


class PagePlan:
    def __init__(self, *, stage: str, kind: str, copy_index: int,
                 request_code: int, candidate_codes: tuple[int, ...]) -> None:
        self.stage = stage
        self.kind = kind
        self.copy_index = copy_index
        self.request_code = request_code
        self.candidate_codes = candidate_codes
        self.rectangles: list[Rectangle] = []
        self.page: dict[str, Any] = {
            "schema": STIMULUS_SCHEMA,
            "layout_version": LAYOUT_VERSION,
            "stage": stage,
            "kind": kind,
            "copy_index": copy_index,
            "request_code": request_code,
            "request": REQUEST_NAMES[request_code],
            "base_layout_dpi": BASE_DPI,
            "page_size_mm": list(PAGE_MM),
            "candidate_codes": list(candidate_codes),
            "candidates": {
                str(code): CANDIDATES_BY_CODE[code].to_dict(
                    request_code=request_code
                )
                for code in candidate_codes
            },
            "infrastructure": [],
            "fields": [],
            "probes": [],
            "annotations": [],
        }

    def reserve(self, element_id: str, x_mm: float, y_mm: float,
                width_mm: float, height_mm: float) -> Rectangle:
        rect = Rectangle(element_id, x_mm, y_mm, width_mm, height_mm)
        if (
            width_mm <= 0.0 or height_mm <= 0.0
            or x_mm < 0.0 or y_mm < 0.0
            or rect.right > PAGE_MM[0] + 1e-6
            or rect.bottom > PAGE_MM[1] + 1e-6
        ):
            raise ValueError(f"{element_id}: rectangle outside A4: {rect}")
        for previous in self.rectangles:
            if rect.overlaps(previous):
                raise ValueError(
                    f"layout overlap: {element_id} with "
                    f"{previous.element_id}"
                )
        self.rectangles.append(rect)
        return rect

    def annotation(self, text: str, x_mm: float, y_mm: float,
                   size_pt: float = 4.0) -> None:
        self.page["annotations"].append({
            "text": text, "x_mm": x_mm, "y_mm": y_mm, "size_pt": size_pt,
        })

    def add_infrastructure(self) -> None:
        corner_centers = {
            1: (15.0, 15.0, (1, 1)),
            2: (195.0, 15.0, (1, -1)),
            3: (195.0, 282.0, (-1, -1)),
            4: (15.0, 282.0, (-1, 1)),
        }
        corner_mm = dots_to_mm(123)
        for satellites, (cx, cy, inward) in corner_centers.items():
            x, y = cx - corner_mm / 2.0, cy - corner_mm / 2.0
            self.reserve(f"infra/corner-{satellites}", x, y,
                         corner_mm, corner_mm)
            self.page["infrastructure"].append({
                "kind": "corner_mark", "satellites": satellites,
                "inward": list(inward),
                "cx_layout_dots": mm_to_dots(cx),
                "cy_layout_dots": mm_to_dots(cy),
                "x_layout_dots": mm_to_dots(x),
                "y_layout_dots": mm_to_dots(y),
                "w_layout_dots": 123, "h_layout_dots": 123,
            })

        # Two separated compact strips carry the same current binary report:
        # the minimal canonical identity plus guarded live interpreter state.
        # Their clock/parity/row-XOR framing is transport redundancy, not
        # three adjacent copies of a verbose static identity panel.
        module = 6
        width_modules, height_modules = 380, 10
        width, height = width_modules * module, height_modules * module
        x0 = mm_to_dots(56.75)
        for index, y_mm in enumerate((14.0, 280.0)):
            y0 = mm_to_dots(y_mm)
            self.reserve(
                f"infra/report-{index}",
                dots_to_mm(x0), dots_to_mm(y0),
                dots_to_mm(width), dots_to_mm(height),
            )
            self.page["infrastructure"].append({
                "kind": "machine_report",
                "index": index,
                "format": "HCAL-R1",
                "x_layout_dots": x0,
                "y_layout_dots": y0,
                "module_layout_dots": module,
                "width_modules": width_modules,
                "height_modules": height_modules,
                "payload_bytes": 160,
                "data_rows": 4,
                "bytes_per_row": 40,
                "w_layout_dots": width,
                "h_layout_dots": height,
                "dynamic_excluded_from_static_ground_truth": True,
            })

        plus_mm = dots_to_mm(31)
        plus_positions = [
            (22.0, y) for y in (48.0, 101.0, 154.0, 207.0, 260.0)
        ] + [
            (188.0, y) for y in (48.0, 101.0, 154.0, 207.0, 260.0)
        ]
        for index, (cx, cy) in enumerate(plus_positions):
            x, y = cx - plus_mm / 2.0, cy - plus_mm / 2.0
            self.reserve(f"infra/plus-{index}", x, y, plus_mm, plus_mm)
            self.page["infrastructure"].append({
                "kind": "geometry_plus", "index": index,
                "cx_layout_dots": mm_to_dots(cx),
                "cy_layout_dots": mm_to_dots(cy),
                "x_layout_dots": mm_to_dots(x),
                "y_layout_dots": mm_to_dots(y),
                "w_layout_dots": 31, "h_layout_dots": 31,
            })

        self.reserve("infra/annotation-box", 132.0, 31.0, 51.0, 6.5)
        self.page["infrastructure"].append({
            "kind": "annotation_box",
            "x_mm": 132.0, "y_mm": 31.0,
            "width_mm": 51.0, "height_mm": 6.5,
        })
        self.annotation(
            f"HOLO CHARACTERIZE {self.stage.upper()} "
            f"{self.kind.upper()} COPY {self.copy_index} "
            f"REQUEST {REQUEST_NAMES[self.request_code]}",
            28.0, 35.0, 4.6,
        )
        self.annotation(
            "printer/path/media/session:", 134.0, 35.0, 3.6
        )

    def add_probe(self, *, probe_id: str, kind: str,
                  x_mm: float, y_mm: float, width_mm: float,
                  height_mm: float, dpi: tuple[int, int] = (600, 600),
                  plane: str = "K", group: str = "physical",
                  params: dict[str, Any] | None = None,
                  seed_label: str | None = None) -> dict[str, Any]:
        self.reserve(f"probe/{probe_id}", x_mm, y_mm,
                     width_mm, height_mm)
        dpi_x, dpi_y = dpi
        width = max(1, mm_to_dots(width_mm, dpi_x))
        height = max(1, mm_to_dots(height_mm, dpi_y))
        probe = {
            "probe_id": probe_id, "kind": kind, "group": group,
            "plane": plane, "source_dpi": [dpi_x, dpi_y],
            "x_source_dots": mm_to_dots(x_mm, dpi_x),
            "y_source_dots": mm_to_dots(y_mm, dpi_y),
            "w_source_dots": width, "h_source_dots": height,
            "x_layout_dots": x_mm / 25.4 * BASE_DPI,
            "y_layout_dots": y_mm / 25.4 * BASE_DPI,
            "w_layout_dots": width * BASE_DPI / dpi_x,
            "h_layout_dots": height * BASE_DPI / dpi_y,
            "params": dict(params or {}),
            "seed_label": seed_label or (
                f"{self.stage}/{self.kind}/copy-{self.copy_index}/"
                f"probe/{probe_id}"
            ),
        }
        bits = pattern_bits(probe)
        probe["ground_truth_sha256"] = hashlib.sha256(
            bits.tobytes()
        ).hexdigest()
        self.page["probes"].append(probe)
        return probe

    def add_field(self, *, field_id: str, candidate_code: int,
                  x_mm: float, y_mm: float, width_mm: float,
                  height_mm: float, role: str, position: str,
                  family: str = "channel",
                  edge: str | None = None, gap_mm: float | None = None,
                  gap_index: int | None = None) -> dict[str, Any]:
        if candidate_code not in self.candidate_codes:
            raise ValueError(f"{field_id}: candidate not carried by the page")
        candidate = CANDIDATES_BY_CODE[candidate_code]
        pitch_x, pitch_y = candidate.pitch_mm
        nx = max(8, int(math.floor(width_mm / pitch_x)))
        ny = max(8, int(math.floor(height_mm / pitch_y)))
        actual_w, actual_h = nx * pitch_x, ny * pitch_y
        self.reserve(f"field/{field_id}", x_mm, y_mm, actual_w, actual_h)
        field: dict[str, Any] = {
            "field_id": field_id, "candidate_code": candidate_code,
            "candidate_id": candidate.candidate_id,
            "stage": self.stage, "kind": self.kind,
            "copy_index": self.copy_index,
            "family": family, "role": role, "position": position,
            "x_source_dots": mm_to_dots(x_mm, candidate.grid_dpi[0]),
            "y_source_dots": mm_to_dots(y_mm, candidate.grid_dpi[1]),
            "x_layout_dots": x_mm / 25.4 * BASE_DPI,
            "y_layout_dots": y_mm / 25.4 * BASE_DPI,
            "nx": nx, "ny": ny,
            "w_layout_dots": actual_w / 25.4 * BASE_DPI,
            "h_layout_dots": actual_h / 25.4 * BASE_DPI,
        }
        if edge is not None:
            field.update({
                "edge": edge, "gap_mm": float(gap_mm),
                "gap_index": int(gap_index or 0),
            })
        states = field_states(field, candidate)
        field["state_sha256"] = hashlib.sha256(states.tobytes()).hexdigest()
        self.page["fields"].append(field)
        return field

    def add_common_probes(self) -> None:
        # Controlled white witnesses stay in the two side gutters.
        for index, (x, y) in enumerate((
            (19.0, 37.0), (189.0, 37.0),
            (19.0, 127.0), (189.0, 127.0),
            (19.0, 237.0), (189.0, 237.0),
        )):
            self.add_probe(
                probe_id=f"paper/{index}", kind="paper",
                x_mm=x, y_mm=y, width_mm=2.0, height_mm=2.0,
                group="background",
            )

        tick_gaps = (
            0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0,
            3.5, 4.0, 5.0, 6.0, 8.0, 10.0,
        )
        # Keep the solid physical-ink ladder in dedicated along-edge
        # stations.  Payload canaries snap to whole cells and a coarse
        # 300-dpi candidate's minimum eight-cell support can be thicker than
        # its nominal slot; sharing x/y stations would therefore make legal
        # candidates overlap even though the two diagnostics answer different
        # questions.
        top_x = (
            12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0,
            26.0, 180.0, 182.0, 184.0, 186.0, 188.0,
        )
        side_y = (
            12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0,
            26.0, 260.0, 262.0, 264.0, 266.0, 268.0,
        )
        for index, gap in enumerate(tick_gaps):
            placements = {
                "top": (top_x[index], gap),
                "bottom": (top_x[index], PAGE_MM[1] - gap - 1.2),
                "left": (gap, side_y[index]),
                "right": (PAGE_MM[0] - gap - 1.2, side_y[index]),
            }
            for edge, (x, y) in placements.items():
                self.add_probe(
                    probe_id=f"edge-tick/{edge}/{gap:g}", kind="edge_tick",
                    x_mm=x, y_mm=y, width_mm=1.2, height_mm=1.2,
                    group="physical-ink-extent",
                    params={"edge": edge, "gap_mm": gap},
                )

        # Same-sheet scanner transfer standard: known c3/c2 cells, H/V
        # 2-on/2-off sampling controls, high-entropy compression canary, and
        # the larger quiet patch below.
        for cell, x in ((3, 28.0), (2, 44.0)):
            self.add_probe(
                probe_id=f"scanner/c{cell}", kind="cell_field",
                x_mm=x, y_mm=19.0, width_mm=14.0, height_mm=10.0,
                group="scanner-adequacy",
                params={
                    "cell_dots": cell,
                    "coverage": 0.5,
                    "adequacy_role": (
                        "solid_class_c3"
                        if cell == 3
                        else "marginal_class_c2"
                    ),
                },
            )
        for orientation, x in (
            ("horizontal_lines", 60.0),
            ("vertical_lines", 69.0),
        ):
            self.add_probe(
                probe_id=f"scanner/g2/{orientation}",
                kind="grating", x_mm=x, y_mm=19.0,
                width_mm=7.0, height_mm=10.0,
                group="scanner-adequacy",
                params={
                    "on_dots": 2, "off_dots": 2,
                    "orientation": orientation,
                    "adequacy_role": (
                        "sampling_horizontal"
                        if orientation == "horizontal_lines"
                        else "sampling_vertical"
                    ),
                },
            )
        self.add_probe(
            probe_id="scanner/entropy", kind="entropy_field",
            x_mm=78.0, y_mm=19.0, width_mm=10.0, height_mm=10.0,
            group="scanner-adequacy",
            params={"coverage": 0.5, "adequacy_role": "entropy"},
        )

        self.add_probe(
            probe_id="quiet/main", kind="quiet_zone",
            x_mm=162.0,
            y_mm=238.0 if self.stage == "calibration" else 258.0,
            width_mm=20.0, height_mm=14.0,
            group="scanner-adequacy",
            params={"content_gate": self.kind, "adequacy_role": "quiet"},
        )
        self.add_probe(
            probe_id="geometry/phase-x", kind="phase_rail",
            x_mm=28.0,
            y_mm=258.5 if self.stage == "calibration" else 256.0,
            width_mm=126.0, height_mm=1.5,
            group="transport-geometry",
            params={
                "orientation": "vertical_lines",
                "on_dots": 3, "off_dots": 3, "axis": "x",
            },
        )
        self.add_probe(
            probe_id="geometry/phase-y", kind="phase_rail",
            x_mm=184.0, y_mm=40.0, width_mm=1.5, height_mm=210.0,
            group="transport-geometry",
            params={
                "orientation": "horizontal_lines",
                "on_dots": 3, "off_dots": 3, "axis": "y",
            },
        )
        self.add_probe(
            probe_id="end", kind="end_sentinel",
            x_mm=82.0, y_mm=275.5, width_mm=46.0, height_mm=0.8,
            group="integrity",
            params={"stage": self.stage, "kind": self.kind},
        )
        self.annotation(
            f"END HCAL-V{LAYOUT_VERSION} {self.stage} {self.kind} "
            f"copy={self.copy_index}",
            82.0, 274.8, 4.2,
        )

    def _canary_candidates(self) -> tuple[int, int]:
        if self.stage == "calibration":
            ordered = sorted(
                self.candidate_codes,
                key=lambda code: (
                    CANDIDATES_BY_CODE[code].pitch_mm[0]
                    * CANDIDATES_BY_CODE[code].pitch_mm[1],
                    code,
                ),
            )
            return ordered[0], ordered[-1]
        alphabet, path = (
            ("K2", None) if self.kind == "bw"
            else ("CMY7", "DeviceCMYK-image")
        )

        def pick(cell_dots: tuple[int, int]) -> int:
            return next(
                code for code in self.candidate_codes
                if (c := CANDIDATES_BY_CODE[code]).grid_dpi == (600, 600)
                and c.cell_dots == cell_dots
                and c.alphabet == alphabet
                and (path is None or c.emission_path == path)
            )

        return pick((2, 2)), pick((3, 3))

    def add_edge_canaries(self) -> None:
        stress, robust = self._canary_candidates()
        gaps = (0.5, 1.5, 2.5, 3.5, 5.0, 6.5, 8.0, 10.0)
        for index, gap in enumerate(gaps):
            for arm_index, (arm, code) in enumerate((
                ("stress", stress), ("robust", robust),
            )):
                slot = 2 * index + arm_index
                x = 28.0 + 9.5 * slot
                y = 28.0 + 14.0 * slot
                candidate = CANDIDATES_BY_CODE[code]
                pitch_x, pitch_y = candidate.pitch_mm
                horizontal_height = (
                    max(8, int(math.floor(2.2 / pitch_y))) * pitch_y
                )
                vertical_width = (
                    max(8, int(math.floor(2.2 / pitch_x))) * pitch_x
                )
                for edge, x0, y0, w, h in (
                    ("top", x, gap, 7.2, 2.2),
                    (
                        "bottom", x,
                        PAGE_MM[1] - gap - horizontal_height,
                        7.2, 2.2,
                    ),
                    ("left", gap, y, 2.2, 7.2),
                    (
                        "right",
                        PAGE_MM[0] - gap - vertical_width,
                        y, 2.2, 7.2,
                    ),
                ):
                    self.add_field(
                        field_id=f"edge/{edge}/{arm}/{gap:g}",
                        candidate_code=code, x_mm=x0, y_mm=y0,
                        width_mm=w, height_mm=h, role="edge-canary",
                        family="edge-canary", position=f"{edge}/{gap:g}",
                        edge=edge, gap_mm=gap, gap_index=index,
                    )

    def add_grid_rulers(
        self,
        *,
        y_mm: float,
        planes: tuple[str, ...],
    ) -> None:
        grids = (
            (300, 300), (600, 600), (1200, 1200),
            (2400, 2400), (1200, 2400),
        )
        gap = 0.7
        band_width = (28.0 - gap * (len(planes) - 1)) / len(planes)
        specs = tuple(
            (f"g{on}-{axis[0]}", "grid_ruler", {
                "on_dots": on, "off_dots": on,
                "orientation": f"{axis}_lines",
            })
            for on in (1, 2) for axis in ("vertical", "horizontal")
        ) + (
            ("dots", "isolated_dots", {
                "dot_dots": 1, "pitch_dots": 8,
            }),
            ("line-pair", "line_width", {
                "width_dots": 1, "on_dots": 1, "off_dots": 3,
                "orientation": "vertical_lines",
            }),
        )
        for index, grid in enumerate(grids):
            x0 = 28.0 + 31.0 * index
            for plane_index, plane in enumerate(planes):
                x = x0 + plane_index * (band_width + gap)
                for spec_index, (name, kind, params) in enumerate(specs):
                    self.add_probe(
                        probe_id=(
                            f"grid/{grid[0]}x{grid[1]}/"
                            f"{plane}/{name}"
                        ),
                        kind=kind, x_mm=x,
                        y_mm=y_mm + 2.0 * spec_index,
                        width_mm=band_width, height_mm=1.5, dpi=grid,
                        plane=plane, group="grid-discovery",
                        params={
                            **params,
                            "grid": list(grid),
                            "plane": plane,
                            "diagnostic": name,
                        },
                    )

    def add_bw_discovery(self) -> None:
        codes = list(discovery_candidate_codes("bw"))
        for index, code in enumerate(codes):
            row, col = divmod(index, 6)
            self.add_field(
                field_id=f"matrix/{code}/p0", candidate_code=code,
                x_mm=28.0 + 25.5 * col, y_mm=40.0 + 18.5 * row,
                width_mm=23.5, height_mm=16.5,
                role=CANDIDATES_BY_CODE[code].role,
                family=(
                    "frontier"
                    if CANDIDATES_BY_CODE[code].role == "frontier"
                    else "channel"
                ),
                position=f"matrix-r{row}c{col}",
            )
        # Three-position evidence for the likely 600-grid frontier.
        for row, y in enumerate((153.0, 173.0), start=1):
            for col, code in enumerate(codes[3:6]):
                self.add_field(
                    field_id=f"matrix/{code}/p{row}", candidate_code=code,
                    x_mm=28.0 + 52.0 * col, y_mm=y,
                    width_mm=48.0, height_mm=17.0,
                    role="channel", family="channel",
                    position=("middle" if row == 1 else "bottom"),
                )

        self.add_grid_rulers(y_mm=195.0, planes=("K",))

        morphology: list[tuple[str, dict[str, Any]]] = []
        for orientation in ("horizontal_lines", "vertical_lines"):
            for width in (1, 2, 3, 4):
                morphology.append(("line_width", {
                    "orientation": orientation, "width_dots": width,
                    "on_dots": width, "off_dots": 3 * width,
                }))
        for feature_dots in (1, 2, 3, 4):
            morphology.append(("isolated_dots", {
                "dot_dots": feature_dots, "pitch_dots": 4 * feature_dots + 4,
            }))
            morphology.append(("white_holes", {
                "hole_dots": feature_dots, "pitch_dots": 4 * feature_dots + 4,
            }))
        morphology.extend([
            ("checker", {"n_dots": 1}),
            ("checker", {"n_dots": 2}),
            ("slanted_edge", {"angle_deg": 5.0}),
            ("microtext", {"stroke_dots": 2, "text": "HCAL 012345"}),
        ])
        for index, (kind, params) in enumerate(morphology):
            row, col = divmod(index, 10)
            self.add_probe(
                probe_id=f"morph/{kind}/{index}", kind=kind,
                x_mm=28.0 + 15.2 * col, y_mm=209.0 + 10.2 * row,
                width_mm=13.5, height_mm=8.5, group="morphology",
                params=params,
            )

        levels = (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0)
        for index, level in enumerate(levels):
            kind = "paper" if level == 0 else "solid" if level == 1 else "tone"
            self.add_probe(
                probe_id=f"tone/K/{level:g}", kind=kind,
                x_mm=28.0 + 18.0 * index, y_mm=231.0,
                width_mm=16.0, height_mm=7.0, group="tone",
                params={"coverage": level, "sequence": index},
            )
        self.add_probe(
            probe_id="tone/K/profile", kind="profile_tone",
            x_mm=28.0, y_mm=240.0, width_mm=126.0, height_mm=6.0,
            group="tone",
            params={"coverage": 0.5, "axis": "x", "mode": "fixed-profile"},
        )

    def add_color_discovery(self) -> None:
        for index, code in enumerate(discovery_candidate_codes("color")):
            row, col = divmod(index, 8)
            self.add_field(
                field_id=f"color/{code}", candidate_code=code,
                x_mm=28.0 + 19.25 * col, y_mm=40.0 + 16.0 * row,
                width_mm=17.5, height_mm=13.5,
                role=CANDIDATES_BY_CODE[code].role,
                family="channel", position=f"matrix-r{row}c{col}",
            )

        for row, y in enumerate((165.0, 178.0, 191.0)):
            for col, x in enumerate((34.0, 94.0, 154.0)):
                target = f"r{row}c{col}"
                for plane_index, plane in enumerate("KCMY"):
                    self.add_probe(
                        probe_id=f"registration/{target}/{plane}",
                        kind="registration_cross",
                        x_mm=x + 4.0 * plane_index, y_mm=y,
                        width_mm=3.0, height_mm=6.0, plane=plane,
                        group="plane-registration",
                        params={"target": target, "stroke_dots": 2},
                    )

        levels = (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0)
        for row, plane in enumerate("KCMY"):
            order = levels[row:] + levels[:row]
            for col, level in enumerate(order):
                kind = (
                    "paper" if level == 0 else
                    "solid" if level == 1 else "tone"
                )
                self.add_probe(
                    probe_id=f"tone/{plane}/{level:g}", kind=kind,
                    x_mm=28.0 + 10.0 * col, y_mm=207.0 + 7.0 * row,
                    width_mm=8.0, height_mm=5.0, plane=plane,
                    group="tone",
                    params={"coverage": level, "sequence": col},
                )
        for index, plane in enumerate("KCMY"):
            self.add_probe(
                probe_id=f"tone/{plane}/feed", kind="profile_tone",
                x_mm=101.0 + 9.0 * index, y_mm=207.0,
                width_mm=7.0, height_mm=26.0, plane=plane,
                group="tone",
                params={"coverage": 0.5, "axis": "y",
                        "mode": "fixed-profile"},
            )

        screen_seed = (
            f"{self.stage}/{self.kind}/copy-{self.copy_index}/"
            "probe/screen/matched-prn-path"
        )
        for index, (name, path, planes) in enumerate((
            (
                "imagemask-C",
                "single-plane-imagemask",
                ["C"],
            ),
            (
                "devicecmyk-C",
                "DeviceCMYK-image",
                ["C"],
            ),
            (
                "devicecmyk-CM",
                "DeviceCMYK-image",
                ["C", "M"],
            ),
            (
                "opm1-CM",
                "sequential-overprint-opm1",
                ["C", "M"],
            ),
        )):
            self.add_probe(
                probe_id=f"screen/path/{name}", kind="entropy_field",
                x_mm=139.0 + 10.0 * index, y_mm=207.0,
                width_mm=9.0, height_mm=17.0,
                plane="K", group="screen",
                params={
                    "coverage": 0.5,
                    "planes": planes,
                    "path": path,
                    "matched_set": "prn-path-v1",
                    "control_role": name,
                    "measurement_feature": "luma-density",
                },
                seed_label=screen_seed,
            )
        for index, plane in enumerate("CMY"):
            self.add_probe(
                probe_id=f"selectivity/{plane}", kind="solid",
                x_mm=139.0 + 6.0 * index, y_mm=227.0,
                width_mm=5.0, height_mm=6.0, plane=plane,
                group="color-selectivity", params={"plane": plane},
            )
        self.add_grid_rulers(
            y_mm=238.0, planes=("K", "C", "M", "Y")
        )

    def add_calibration(self) -> None:
        validate_shortlist(self.kind, self.candidate_codes)
        n = len(self.candidate_codes)
        total = n * 6
        for slot in range(total):
            position = slot // n
            candidate_index = (slot + position) % n
            code = self.candidate_codes[candidate_index]
            row, col = divmod(slot, 4)
            self.add_field(
                field_id=f"cal/{code}/p{position}",
                candidate_code=code,
                x_mm=28.0 + 39.0 * col, y_mm=40.0 + 16.5 * row,
                width_mm=36.0, height_mm=14.0,
                role="calibration", family="calibration",
                position=f"p{position}",
            )
        if self.kind == "color":
            for index, plane in enumerate("KCMY"):
                self.add_probe(
                    probe_id=f"cal/tone-mid/{plane}",
                    kind="profile_tone",
                    x_mm=28.0 + 31.5 * index, y_mm=243.0,
                    width_mm=29.0, height_mm=6.0,
                    plane=plane, group="tone",
                    params={
                        "coverage": 0.5, "axis": "x",
                        "mode": "fixed-profile",
                    },
                )
            for index, plane in enumerate("KCMY"):
                self.add_probe(
                    probe_id=f"cal/registration/{plane}",
                    kind="registration_cross",
                    x_mm=28.0 + 12.0 * index, y_mm=250.0,
                    width_mm=8.0, height_mm=7.0, plane=plane,
                    group="plane-registration",
                    params={"target": "cal", "stroke_dots": 2},
                )
        else:
            self.add_probe(
                probe_id="cal/tone-mid/K", kind="profile_tone",
                x_mm=28.0, y_mm=243.0, width_mm=126.0, height_mm=6.0,
                group="tone", params={
                    "coverage": 0.5, "axis": "x",
                    "mode": "fixed-profile",
                },
            )
        self.add_grid_rulers(
            y_mm=262.0,
            planes=(
                ("K", "C", "M", "Y") if self.kind == "color"
                else ("K",)
            ),
        )

    def finish(self) -> dict[str, Any]:
        descriptor = {
            "schema": self.page["schema"],
            "layout_version": self.page["layout_version"],
            "stage": self.stage, "kind": self.kind,
            "copy_index": self.copy_index,
            "request_code": self.request_code,
            "candidate_codes": list(self.candidate_codes),
            "candidates": self.page["candidates"],
            "infrastructure": self.page["infrastructure"],
            "fields": self.page["fields"],
            "probes": self.page["probes"],
        }
        layout_digest = semantic_digest(descriptor)
        identity = Identity(
            self.stage, self.kind, self.copy_index, self.request_code,
            self.candidate_codes, layout_digest,
        )
        self.page["identity"] = identity.to_dict()
        self.page["layout_descriptor_sha256"] = layout_digest
        self.page["layout_rectangles"] = [
            {
                "element_id": rect.element_id,
                "x_mm": rect.x_mm, "y_mm": rect.y_mm,
                "width_mm": rect.width_mm, "height_mm": rect.height_mm,
            }
            for rect in self.rectangles
        ]
        payload = dict(self.page)
        self.page["semantic_sha256"] = semantic_digest(payload)
        return self.page


def build_page(*, stage: str, kind: str, copy_index: int,
               request_code: int, candidate_codes: Iterable[int] | None = None
               ) -> dict[str, Any]:
    if stage not in {"discovery", "calibration"}:
        raise ValueError(f"unknown stage {stage!r}")
    if kind not in {"bw", "color"}:
        raise ValueError(f"unknown page kind {kind!r}")
    if request_code not in REQUEST_NAMES:
        raise ValueError(f"unknown request code {request_code}")
    if candidate_codes is None:
        if stage != "discovery":
            raise ValueError("calibration requires explicit candidate codes")
        codes = discovery_candidate_codes(kind)
    elif stage == "calibration":
        codes = validate_shortlist(kind, candidate_codes)
    else:
        supplied = tuple(int(code) for code in candidate_codes)
        if len(set(supplied)) != len(supplied):
            raise ValueError("candidate list contains duplicates")
        codes = tuple(sorted(supplied))
        if codes != discovery_candidate_codes(kind):
            raise ValueError(
                "discovery uses the complete fixed current candidate registry"
            )
    plan = PagePlan(
        stage=stage, kind=kind, copy_index=copy_index,
        request_code=request_code, candidate_codes=codes,
    )
    plan.add_infrastructure()
    plan.add_common_probes()
    # Calibration edges use its carried candidates. Discovery has the exact
    # fixed stress/robust arms.
    if stage == "discovery":
        plan.add_edge_canaries()
        if kind == "bw":
            plan.add_bw_discovery()
        else:
            plan.add_color_discovery()
    elif stage == "calibration":
        plan.add_edge_canaries()
        plan.add_calibration()
    return plan.finish()


def verify_page(page: dict[str, Any]) -> None:
    expected = page.get("semantic_sha256")
    payload = dict(page)
    payload.pop("semantic_sha256", None)
    if expected != semantic_digest(payload):
        raise ValueError("page semantic digest mismatch")
    identity = Identity(
        stage=str(page["identity"]["stage"]),
        kind=str(page["identity"]["kind"]),
        copy_index=int(page["identity"]["copy_index"]),
        request_code=int(page["identity"]["request_code"]),
        candidate_codes=tuple(
            int(code) for code in page["identity"]["candidate_codes"]
        ),
        layout_digest=str(page["identity"]["layout_digest"]),
    )
    if identity.layout_digest != page.get("layout_descriptor_sha256"):
        raise ValueError("printed identity/layout descriptor digest mismatch")
    rebuilt = build_page(
        stage=identity.stage, kind=identity.kind,
        copy_index=identity.copy_index,
        request_code=identity.request_code,
        candidate_codes=identity.candidate_codes,
    )
    if rebuilt["semantic_sha256"] != expected:
        raise ValueError("page is not the canonical regenerated plan")
