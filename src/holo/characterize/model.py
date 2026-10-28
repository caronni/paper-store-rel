"""Current schemas, candidate registry, and compact printed page identity."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

STIMULUS_SCHEMA = "holo/characterize/stimulus/v2"
REPORT_SCHEMA = "holo/characterize/report/v4"
SUMMARY_SCHEMA = "holo/characterize/summary/v4"
LAYOUT_VERSION = 2
BASE_DPI = 600
PAGE_MM = (210.0, 297.0)
PUBLIC_SEED = b"holo/characterize/v2"

REQUEST_CODES = {
    "default": 0,
    "300": 1,
    "600": 2,
    "1200": 3,
    "2400": 4,
    "1200x2400": 5,
}
REQUEST_NAMES = {value: key for key, value in REQUEST_CODES.items()}
REQUEST_DPI = {
    0: None,
    1: (300, 300),
    2: (600, 600),
    3: (1200, 1200),
    4: (2400, 2400),
    5: (1200, 2400),
}
STAGE_CODES = {"discovery": 1, "calibration": 2}
STAGE_NAMES = {value: key for key, value in STAGE_CODES.items()}
KIND_CODES = {"bw": 1, "color": 2}
KIND_NAMES = {value: key for key, value in KIND_CODES.items()}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def semantic_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class Candidate:
    code: int
    candidate_id: str
    page_kind: str
    grid_dpi: tuple[int, int]
    cell_dots: tuple[int, int]
    alphabet: str
    states: tuple[str, ...]
    state_planes: tuple[tuple[str, ...], ...]
    bit_names: tuple[str, ...]
    emission_path: str
    symbol_shape: str = "solid"
    role: str = "channel"

    def __post_init__(self) -> None:
        if not 1 <= self.code <= 255:
            raise ValueError("candidate code must fit one report byte")
        if self.page_kind not in KIND_CODES:
            raise ValueError(f"invalid page kind {self.page_kind!r}")
        if len(self.states) != len(self.state_planes):
            raise ValueError("state labels and plane memberships differ")
        if min(*self.grid_dpi, *self.cell_dots) <= 0:
            raise ValueError("grid and cell dimensions must be positive")

    @property
    def n_states(self) -> int:
        return len(self.states)

    @property
    def planes(self) -> tuple[str, ...]:
        return tuple(
            plane for plane in "CMYK"
            if any(plane in row for row in self.state_planes)
        )

    @property
    def pitch_mm(self) -> tuple[float, float]:
        return (
            25.4 * self.cell_dots[0] / self.grid_dpi[0],
            25.4 * self.cell_dots[1] / self.grid_dpi[1],
        )

    @property
    def cells_per_mm2(self) -> float:
        px, py = self.pitch_mm
        return 1.0 / (px * py)

    @property
    def alphabet_bits(self) -> float:
        return (
            float(len(self.bit_names))
            if self.bit_names
            else math.log2(self.n_states)
        )

    def identity_tuple(self, request_code: int) -> tuple[Any, ...]:
        return (
            self.page_kind,
            self.grid_dpi,
            self.cell_dots,
            self.alphabet,
            self.states,
            self.planes,
            self.symbol_shape,
            self.emission_path,
            int(request_code),
        )

    def to_dict(self, *, request_code: int = 0) -> dict[str, Any]:
        return {
            "code": self.code,
            "candidate_id": self.candidate_id,
            "page_kind": self.page_kind,
            "grid_dpi": list(self.grid_dpi),
            "cell_dots": list(self.cell_dots),
            "cell_pitch_mm": list(self.pitch_mm),
            "cells_per_mm2": self.cells_per_mm2,
            "alphabet": self.alphabet,
            "alphabet_bits": self.alphabet_bits,
            "states": list(self.states),
            "state_planes": [list(row) for row in self.state_planes],
            "bit_names": list(self.bit_names),
            "planes": list(self.planes),
            "emission_path": self.emission_path,
            "symbol_shape": self.symbol_shape,
            "role": self.role,
            "request_code": int(request_code),
            "request": REQUEST_NAMES[int(request_code)],
        }


_candidates: list[Candidate] = []


def _add(*, page_kind: str, grid: tuple[int, int],
         cell: tuple[int, int], alphabet: str = "K2",
         states: tuple[str, ...] = ("W", "K"),
         state_planes: tuple[tuple[str, ...], ...] = ((), ("K",)),
         bit_names: tuple[str, ...] = ("K",),
         emission_path: str = "single-plane-imagemask",
         symbol_shape: str = "solid", role: str = "channel",
         name: str | None = None) -> None:
    code = len(_candidates) + 1
    grid_text = (
        f"{grid[0]}" if grid[0] == grid[1] else f"{grid[0]}x{grid[1]}"
    )
    cell_text = (
        f"{cell[0]}" if cell[0] == cell[1] else f"{cell[0]}x{cell[1]}"
    )
    candidate_id = name or (
        f"{page_kind}-{alphabet.lower()}-g{grid_text}-c{cell_text}-"
        f"{emission_path}"
    )
    _candidates.append(Candidate(
        code, candidate_id, page_kind, grid, cell, alphabet,
        states, state_planes, bit_names, emission_path, symbol_shape, role,
    ))


_GRID_RUNGS = (
    ((300, 300), ((1, 1), (2, 2), (3, 3))),
    ((600, 600), ((2, 2), (3, 3), (4, 4))),
    ((1200, 1200), ((4, 4), (6, 6), (8, 8))),
    ((2400, 2400), ((8, 8), (12, 12), (16, 16))),
    ((1200, 2400), ((4, 8), (6, 12), (8, 16))),
)

# B/W: matched physical rungs, then compact frontier additions.
for _grid, _cells in _GRID_RUNGS:
    for _cell in _cells:
        _add(page_kind="bw", grid=_grid, cell=_cell)
for _grid, _cell in (
    ((300, 300), (4, 4)), ((300, 300), (6, 6)),
    ((600, 600), (1, 1)), ((600, 600), (5, 5)), ((600, 600), (6, 6)),
    ((1200, 1200), (2, 2)), ((1200, 1200), (3, 3)),
    ((1200, 1200), (12, 12)),
    ((2400, 2400), (2, 2)), ((2400, 2400), (4, 4)),
    ((2400, 2400), (24, 24)),
    ((1200, 2400), (2, 4)),
):
    _add(page_kind="bw", grid=_grid, cell=_cell, role="frontier")
_add(
    page_kind="bw", grid=(600, 600), cell=(3, 3),
    alphabet="K3", states=("W", "K1/3", "K"),
    state_planes=((), ("K",), ("K",)), bit_names=(),
    symbol_shape="nested-3", role="multilevel",
)
_add(
    page_kind="bw", grid=(600, 600), cell=(4, 4),
    alphabet="K4", states=("W", "K1/4", "K1/2", "K"),
    state_planes=((), ("K",), ("K",), ("K",)), bit_names=(),
    symbol_shape="nested-4", role="multilevel",
)
for _cell, _shape, _name in (
    ((2, 2), "diagonal", "bw-k2-g600-c2-diagonal"),
    ((2, 2), "horizontal-half", "bw-k2-g600-c2-horizontal"),
    ((2, 2), "vertical-half", "bw-k2-g600-c2-vertical"),
    ((2, 3), "solid", "bw-k2-g600-c2x3"),
    ((3, 2), "solid", "bw-k2-g600-c3x2"),
):
    _add(
        page_kind="bw", grid=(600, 600), cell=_cell,
        symbol_shape=_shape, role="shape-control", name=_name,
    )

# Color: pure-plane c3-class across grids.
for _grid, _cells in _GRID_RUNGS:
    _robust = _cells[1]
    for _plane in "CMY":
        _add(
            page_kind="color", grid=_grid, cell=_robust,
            alphabet=f"{_plane}2", states=("W", _plane),
            state_planes=((), (_plane,)), bit_names=(_plane,),
            name=(
                f"color-pure-{_plane.lower()}-g{_grid[0]}x{_grid[1]}"
                f"-c{_robust[0]}x{_robust[1]}"
            ),
        )

# Same-page 600-grid stress controls.
for _plane in "KCMY":
    _add(
        page_kind="color", grid=(600, 600), cell=(2, 2),
        alphabet=f"{_plane}2", states=("W", _plane),
        state_planes=((), (_plane,)), bit_names=(_plane,),
        role="stress",
        name=f"color-stress-{_plane.lower()}-g600-c2",
    )

_CMY7_STATES = ("W", "C", "M", "Y", "CM", "CY", "MY")
_CMY7_PLANES = ((), ("C",), ("M",), ("Y",), ("C", "M"),
                ("C", "Y"), ("M", "Y"))
_CMY8_STATES = ("W", "C", "M", "CM", "Y", "CY", "MY", "CMY")
_CMY8_PLANES = ((), ("C",), ("M",), ("C", "M"), ("Y",),
                ("C", "Y"), ("M", "Y"), ("C", "M", "Y"))
_CM4_STATES = ("W", "C", "M", "CM")
_CM4_PLANES = ((), ("C",), ("M",), ("C", "M"))

for _grid, _cells in _GRID_RUNGS:
    for _cell_index, _cell in enumerate(_cells[:2]):
        _role = "stress" if _cell_index == 0 else "channel"
        for _alphabet, _states, _planes, _bits in (
            ("CM4", _CM4_STATES, _CM4_PLANES, ("C", "M")),
            ("CMY7", _CMY7_STATES, _CMY7_PLANES, ()),
            ("CMY8", _CMY8_STATES, _CMY8_PLANES, ("C", "M", "Y")),
        ):
            _add(
                page_kind="color", grid=_grid, cell=_cell,
                alphabet=_alphabet, states=_states,
                state_planes=_planes, bit_names=_bits,
                emission_path="DeviceCMYK-image", role=_role,
                name=(
                    f"color-{_alphabet.lower()}-"
                    f"g{_grid[0]}x{_grid[1]}-"
                    f"c{_cell[0]}x{_cell[1]}"
                ),
            )

_add(
    page_kind="color", grid=(600, 600), cell=(3, 3),
    alphabet="KCMY4", states=("K", "C", "M", "Y"),
    state_planes=(("K",), ("C",), ("M",), ("Y",)),
    bit_names=("b0", "b1"), emission_path="DeviceCMYK-image",
    role="constellation",
)
_add(
    page_kind="color", grid=(600, 600), cell=(3, 3),
    alphabet="CMY7", states=_CMY7_STATES, state_planes=_CMY7_PLANES,
    bit_names=(), emission_path="sequential-overprint-opm1",
    role="emission-path", name="color-cmy7-g600-c3-opm1",
)
_add(
    page_kind="color", grid=(600, 600), cell=(3, 3),
    alphabet="CMY8", states=_CMY8_STATES, state_planes=_CMY8_PLANES,
    bit_names=("C", "M", "Y"),
    emission_path="sequential-overprint-opm1",
    role="emission-path", name="color-cmy8-g600-c3-opm1",
)

CANDIDATES_BY_CODE = {item.code: item for item in _candidates}
CANDIDATES_BY_ID = {item.candidate_id: item for item in _candidates}
if len(CANDIDATES_BY_CODE) != len(_candidates) or len(_candidates) > 255:
    raise RuntimeError("candidate registry codes are not unique uint8 values")


def discovery_candidate_codes(kind: str) -> tuple[int, ...]:
    if kind not in KIND_CODES:
        raise ValueError(f"invalid page kind {kind!r}")
    return tuple(
        item.code for item in _candidates if item.page_kind == kind
    )


def validate_shortlist(kind: str, codes) -> tuple[int, ...]:
    """The calibration-shortlist rule set, stated once.

    Previously enforced at seven sites with four different rule subsets;
    Identity.__post_init__ keeps its own stricter printed-identity
    invariants (already-sorted input) on top of these.
    """
    result = tuple(int(code) for code in codes)
    if len(set(result)) != len(result):
        raise ValueError("candidate list contains duplicates")
    unknown = [
        code for code in sorted(set(result))
        if code not in CANDIDATES_BY_CODE
    ]
    if unknown:
        raise ValueError(f"unknown candidate codes {unknown}")
    if not 1 <= len(result) <= 8:
        raise ValueError(
            "calibration carries between one and eight candidates"
        )
    if any(CANDIDATES_BY_CODE[code].page_kind != kind for code in result):
        raise ValueError("candidate list crosses page kind")
    return tuple(sorted(result))


@dataclass(frozen=True)
class Identity:
    stage: str
    kind: str
    copy_index: int
    request_code: int
    candidate_codes: tuple[int, ...]
    layout_digest: str

    @classmethod
    def from_page(cls, page: "Mapping[str, Any]") -> "Identity":
        """The page plan's identity record as a typed Identity."""
        value = page["identity"]
        return cls(
            stage=str(value["stage"]),
            kind=str(value["kind"]),
            copy_index=int(value["copy_index"]),
            request_code=int(value["request_code"]),
            candidate_codes=tuple(
                int(code) for code in value["candidate_codes"]
            ),
            layout_digest=str(value["layout_digest"]),
        )

    def __post_init__(self) -> None:
        if self.stage not in STAGE_CODES or self.kind not in KIND_CODES:
            raise ValueError("unknown identity stage or kind")
        if not 0 <= self.copy_index <= 0xFFFF:
            raise ValueError("copy index must fit uint16")
        if self.request_code not in REQUEST_NAMES:
            raise ValueError("unsupported request code")
        codes = tuple(int(code) for code in self.candidate_codes)
        if codes != tuple(sorted(set(codes))):
            raise ValueError("identity candidate codes must be sorted and unique")
        if any(
            code not in CANDIDATES_BY_CODE
            or CANDIDATES_BY_CODE[code].page_kind != self.kind
            for code in codes
        ):
            raise ValueError("identity candidate codes cross page kind")
        if self.stage == "discovery":
            if codes != discovery_candidate_codes(self.kind):
                raise ValueError(
                    "current discovery identity must carry the complete "
                    "page-kind registry"
                )
        elif not 1 <= len(codes) <= 8:
            raise ValueError(
                "current calibration identity must carry one to eight "
                "candidates"
            )
        if (
            len(self.layout_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.layout_digest
            )
        ):
            raise ValueError("layout digest must be lowercase SHA-256 hex")

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "kind": self.kind,
            "copy_index": self.copy_index,
            "request_code": self.request_code,
            "request": REQUEST_NAMES[self.request_code],
            "request_dpi": (
                None if REQUEST_DPI[self.request_code] is None
                else list(REQUEST_DPI[self.request_code])
            ),
            "candidate_codes": list(self.candidate_codes),
            "layout_digest": self.layout_digest,
        }
