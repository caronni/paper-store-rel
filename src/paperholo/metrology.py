"""Physical-channel metrology contracts used by experiment 025.

The central rule is that four different quantities must never be collapsed:

``authored grid``
    The x/y dot grid on which a stimulus bitmap was constructed.
``requested grid``
    The optional ``/HWResolution`` request sent to the printer.
``read-back grid``
    What ``currentpagedevice`` reports after that request.
``measured channel result``
    What survived the complete printer -> paper -> scanner -> analyzer path.

A printer can accept, echo, resample, or ignore a resolution request.  E025
therefore ranks modes by measured recoverability per physical area.  It does
not infer density from a device claim alone.

All dataclasses are deliberately JSON-shaped and experiment-neutral.  The
E025 emitter/analyzer own the detailed field manifest, measured printable
extent, and profile policy; this module owns only portable units and report
records.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

SCHEMA = "paper-store/channel-metrology/v1"
MM_PER_INCH = 25.4


def _positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")


def _optional_pair(value: tuple[int, int] | None) -> list[int] | None:
    return None if value is None else [int(value[0]), int(value[1])]


@dataclass(frozen=True)
class GridSpec:
    """One authored raster/cell grid.

    Axis order is explicit throughout: ``x`` first, then ``y``.  ``c_x`` and
    ``c_y`` are authored dots per modulation cell, not scan pixels per cell.
    """

    dpi_x: int
    dpi_y: int
    c_x: int
    c_y: int

    def __post_init__(self) -> None:
        for name in ("dpi_x", "dpi_y", "c_x", "c_y"):
            _positive(name, getattr(self, name))

    @property
    def key(self) -> str:
        return f"g{self.dpi_x}x{self.dpi_y}-c{self.c_x}x{self.c_y}"

    @property
    def cell_pitch_mm_x(self) -> float:
        return MM_PER_INCH * self.c_x / self.dpi_x

    @property
    def cell_pitch_mm_y(self) -> float:
        return MM_PER_INCH * self.c_y / self.dpi_y

    @property
    def cells_per_mm2(self) -> float:
        return (
            self.dpi_x
            * self.dpi_y
            / (MM_PER_INCH**2 * self.c_x * self.c_y)
        )

    def nominal_scan_samples(self, scan_dpi_x: float,
                             scan_dpi_y: float) -> tuple[float, float]:
        """Nominal scanner samples/cell if physical scaling was honored."""
        _positive("scan_dpi_x", scan_dpi_x)
        _positive("scan_dpi_y", scan_dpi_y)
        return (
            scan_dpi_x * self.c_x / self.dpi_x,
            scan_dpi_y * self.c_y / self.dpi_y,
        )

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GridSpec":
        return cls(**{
            key: int(value[key])
            for key in ("dpi_x", "dpi_y", "c_x", "c_y")
        })


@dataclass(frozen=True)
class CandidateSpec:
    """One exact modulation candidate, including its physical authored grid."""

    candidate_id: str
    grid: GridSpec
    constellation: str
    payload_bits_per_cell: float
    planes: tuple[str, ...]
    emission_path: str
    symbol_shape: str = "solid-cell"
    bit_levels: tuple[str, ...] = ()
    data_bearing: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id is required")
        _positive("payload_bits_per_cell", self.payload_bits_per_cell)
        if not self.planes:
            raise ValueError("at least one plane is required")
        if len(set(self.bit_levels)) != len(self.bit_levels):
            raise ValueError("bit_levels must be unique")
        if self.bit_levels and not math.isclose(
            self.payload_bits_per_cell,
            float(len(self.bit_levels)),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "binary bit_levels require one payload bit per declared level"
            )

    @property
    def raw_bits_per_mm2(self) -> float:
        return self.grid.cells_per_mm2 * self.payload_bits_per_cell

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["grid"] = self.grid.to_dict()
        out["planes"] = list(self.planes)
        out["bit_levels"] = list(self.bit_levels)
        out["raw_bits_per_mm2"] = self.raw_bits_per_mm2
        return out

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CandidateSpec":
        return cls(
            candidate_id=str(value["candidate_id"]),
            grid=GridSpec.from_dict(value["grid"]),
            constellation=str(value["constellation"]),
            payload_bits_per_cell=float(value["payload_bits_per_cell"]),
            planes=tuple(str(v) for v in value["planes"]),
            emission_path=str(value["emission_path"]),
            symbol_shape=str(value.get("symbol_shape", "solid-cell")),
            bit_levels=tuple(str(v) for v in value.get("bit_levels", [])),
            data_bearing=bool(value.get("data_bearing", True)),
            notes=str(value.get("notes", "")),
        )


@dataclass(frozen=True)
class CaptureFooting:
    """Provenance for one physical print/capture path.

    ``requested_dpi`` and ``readback_dpi`` are evidence, not truth.  The
    analyzer's measurements remain valid when either is absent or misleading.
    """

    sheet_id: str
    printer_id: str
    scanner_id: str
    print_path: str
    scan_mode: str
    scan_dpi_x: float
    scan_dpi_y: float
    requested_dpi: tuple[int, int] | None = None
    readback_dpi: tuple[int, int] | None = None
    media: str = ""
    consumable_state: str = ""
    capture_sha256: str = ""
    capture_id: str = ""

    def __post_init__(self) -> None:
        _positive("scan_dpi_x", self.scan_dpi_x)
        _positive("scan_dpi_y", self.scan_dpi_y)
        for name, pair in (
            ("requested_dpi", self.requested_dpi),
            ("readback_dpi", self.readback_dpi),
        ):
            if pair is not None:
                _positive(f"{name}[0]", pair[0])
                _positive(f"{name}[1]", pair[1])

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["requested_dpi"] = _optional_pair(self.requested_dpi)
        out["readback_dpi"] = _optional_pair(self.readback_dpi)
        return out

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CaptureFooting":
        kwargs = dict(value)
        for key in ("requested_dpi", "readback_dpi"):
            pair = kwargs.get(key)
            kwargs[key] = None if pair is None else (int(pair[0]), int(pair[1]))
        return cls(**kwargs)


@dataclass(frozen=True)
class LdpcYield:
    """Measured result for one exact house LDPC rung."""

    rate_id: str
    code_rate: float
    attempted: int
    certified: int
    wrong: int = 0
    mean_iterations: float = 0.0
    level_id: str = ""

    def __post_init__(self) -> None:
        if not self.rate_id:
            raise ValueError("rate_id is required")
        if not (0.0 < self.code_rate <= 1.0):
            raise ValueError("code_rate must be in (0,1]")
        if min(self.attempted, self.certified, self.wrong) < 0:
            raise ValueError("yield counts must be non-negative")
        if self.certified + self.wrong > self.attempted:
            raise ValueError("certified + wrong exceeds attempted")

    @property
    def certified_fraction(self) -> float:
        return self.certified / self.attempted if self.attempted else 0.0

    @property
    def wilson_lower_95(self) -> float:
        return wilson_lower(self.certified, self.attempted)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["certified_fraction"] = self.certified_fraction
        out["wilson_lower_95"] = self.wilson_lower_95
        return out

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LdpcYield":
        return cls(
            rate_id=str(value["rate_id"]),
            code_rate=float(value["code_rate"]),
            attempted=int(value["attempted"]),
            certified=int(value["certified"]),
            wrong=int(value.get("wrong", 0)),
            mean_iterations=float(value.get("mean_iterations", 0.0)),
            level_id=str(value.get("level_id", "")),
        )


@dataclass(frozen=True)
class CandidateObservation:
    """One position/sheet/capture observation of one candidate."""

    candidate: CandidateSpec
    stratum_id: str
    hard_error_rate: float
    mutual_information_bpc: float
    n_validation_cells: int
    scan_adequate: bool
    nominal_scan_samples_x: float
    nominal_scan_samples_y: float
    measured_scan_samples_x: float
    measured_scan_samples_y: float
    ldpc: tuple[LdpcYield, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.hard_error_rate <= 1.0):
            raise ValueError("hard_error_rate must be in [0,1]")
        if self.mutual_information_bpc < 0.0:
            raise ValueError("mutual_information_bpc must be non-negative")
        if self.n_validation_cells < 0:
            raise ValueError("n_validation_cells must be non-negative")
        _positive("nominal_scan_samples_x", self.nominal_scan_samples_x)
        _positive("nominal_scan_samples_y", self.nominal_scan_samples_y)
        _positive("measured_scan_samples_x", self.measured_scan_samples_x)
        _positive("measured_scan_samples_y", self.measured_scan_samples_y)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "stratum_id": self.stratum_id,
            "hard_error_rate": self.hard_error_rate,
            "mutual_information_bpc": self.mutual_information_bpc,
            "n_validation_cells": self.n_validation_cells,
            "scan_adequate": self.scan_adequate,
            "nominal_scan_samples_x": self.nominal_scan_samples_x,
            "nominal_scan_samples_y": self.nominal_scan_samples_y,
            "measured_scan_samples_x": self.measured_scan_samples_x,
            "measured_scan_samples_y": self.measured_scan_samples_y,
            "ldpc": [item.to_dict() for item in self.ldpc],
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CandidateObservation":
        return cls(
            candidate=CandidateSpec.from_dict(value["candidate"]),
            stratum_id=str(value["stratum_id"]),
            hard_error_rate=float(value["hard_error_rate"]),
            mutual_information_bpc=float(value["mutual_information_bpc"]),
            n_validation_cells=int(value["n_validation_cells"]),
            scan_adequate=bool(value["scan_adequate"]),
            nominal_scan_samples_x=float(value["nominal_scan_samples_x"]),
            nominal_scan_samples_y=float(value["nominal_scan_samples_y"]),
            measured_scan_samples_x=float(
                value.get(
                    "measured_scan_samples_x",
                    value["nominal_scan_samples_x"],
                )
            ),
            measured_scan_samples_y=float(
                value.get(
                    "measured_scan_samples_y",
                    value["nominal_scan_samples_y"],
                )
            ),
            ldpc=tuple(LdpcYield.from_dict(v) for v in value.get("ldpc", [])),
            diagnostics=dict(value.get("diagnostics", {})),
        )


def wilson_lower(successes: int, trials: int, z: float = 1.959963984540054
                 ) -> float:
    """Two-sided Wilson interval's lower endpoint (95% by default)."""
    if trials <= 0:
        return 0.0
    if not (0 <= successes <= trials):
        raise ValueError("need 0 <= successes <= trials")
    p = successes / trials
    z2 = z * z
    denom = 1.0 + z2 / trials
    center = p + z2 / (2.0 * trials)
    radius = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * trials)) / trials)
    return max(0.0, (center - radius) / denom)


def report_document(*, footing: CaptureFooting,
                    observations: Iterable[CandidateObservation],
                    metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a canonical JSON report and attach a semantic digest."""
    document = {
        "schema": SCHEMA,
        "footing": footing.to_dict(),
        "observations": [item.to_dict() for item in observations],
        "metadata": dict(metadata or {}),
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    document["semantic_sha256"] = hashlib.sha256(payload).hexdigest()
    return document


def observations_from_report(document: dict[str, Any]
                             ) -> list[CandidateObservation]:
    if document.get("schema") != SCHEMA:
        raise ValueError(f"unsupported metrology schema {document.get('schema')!r}")
    return [CandidateObservation.from_dict(v) for v in document["observations"]]
