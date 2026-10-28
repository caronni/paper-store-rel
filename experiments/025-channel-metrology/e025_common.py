"""Frozen stimulus primitives for E025 channel metrology.

E025 is a measurement instrument, not a payload format.  Its public seed is
fixed here and never depends on a payload, a file hash, or print-time state.
The manifest records every physical rectangle and enough typed parameters to
regenerate its exact ground truth.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from paperholo import ldpc
from paperholo.metrology import CandidateSpec, GridSpec
from paperholo.modulation import rng

SCHEMA = "paper-store/e025/stimulus/v2"
LAYOUT_VERSION = 2
BASE_DPI = 600
SEED = b"paper-store/e025/channel-metrology-v2"
SEED_TEXT = SEED.decode("ascii")
PAGE_MM = (210.0, 297.0)

# The physical and payload-safe edge questions are sampled separately.
EDGE_GAPS_MM = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0,
                5.0, 6.0, 8.0, 10.0)
EDGE_CANARY_GAPS_MM = (0.5, 1.5, 2.5, 3.5, 5.0, 7.0, 10.0)


@dataclass(frozen=True)
class ChannelDefinition:
    """One exact printable alphabet and emission path."""

    definition_id: str
    label: str
    states: tuple[str, ...]
    state_planes: tuple[tuple[str, ...], ...]
    bit_levels: tuple[str, ...]
    emission_path: str
    symbol_shape: str = "solid-cell"
    data_bearing: bool = True
    notes: str = ""

    @property
    def planes(self) -> tuple[str, ...]:
        return tuple(
            plane for plane in "CMYK"
            if any(plane in membership for membership in self.state_planes)
        )

    @property
    def payload_bits_per_cell(self) -> float:
        return (
            float(len(self.bit_levels))
            if self.bit_levels
            else math.log2(len(self.states))
        )

    def candidate(self, grid: GridSpec) -> CandidateSpec:
        return CandidateSpec(
            candidate_id=f"{self.definition_id}-{grid.key}",
            grid=grid,
            constellation="/".join(self.states),
            payload_bits_per_cell=self.payload_bits_per_cell,
            planes=self.planes,
            emission_path=self.emission_path,
            symbol_shape=self.symbol_shape,
            bit_levels=self.bit_levels,
            data_bearing=self.data_bearing,
            notes=self.notes,
        )


def _binary_plane(plane: str) -> ChannelDefinition:
    return ChannelDefinition(
        definition_id=f"{plane.lower()}1-mask",
        label=f"{plane} binary",
        states=("W", plane),
        state_planes=((), (plane,)),
        bit_levels=(plane,),
        emission_path="single-plane-imagemask",
        notes=f"Pure {plane} bilevel path.",
    )


def _binary_k_motif(definition_id: str, label: str,
                    symbol_shape: str) -> ChannelDefinition:
    return ChannelDefinition(
        definition_id=definition_id,
        label=label,
        states=("W", "K"),
        state_planes=((), ("K",)),
        bit_levels=("K",),
        emission_path="single-plane-imagemask",
        symbol_shape=symbol_shape,
        notes=("Matched binary K field whose marked cells use the declared "
               "authored-dot motif."),
    )


CHANNELS: dict[str, ChannelDefinition] = {
    definition.definition_id: definition
    for definition in (_binary_plane("K"), _binary_plane("C"),
                       _binary_plane("M"), _binary_plane("Y"))
}
CHANNELS.update({
    "k1-diagonal-mask": _binary_k_motif(
        "k1-diagonal-mask", "K main diagonal", "main-diagonal"
    ),
    "k1-horizontal-mask": _binary_k_motif(
        "k1-horizontal-mask", "K horizontal half", "horizontal-half"
    ),
    "k1-vertical-mask": _binary_k_motif(
        "k1-vertical-mask", "K vertical half", "vertical-half"
    ),
    "cm4-image": ChannelDefinition(
        definition_id="cm4-image",
        label="CM4 image",
        states=("W", "C", "M", "CM"),
        state_planes=((), ("C",), ("M",), ("C", "M")),
        bit_levels=("C", "M"),
        emission_path="DeviceCMYK-image",
        notes="Exact two-bit CM alphabet through one composite image.",
    ),
    "cmy8-image": ChannelDefinition(
        definition_id="cmy8-image",
        label="CMY8 image",
        states=("W", "C", "M", "CM", "Y", "CY", "MY", "CMY"),
        state_planes=((), ("C",), ("M",), ("C", "M"), ("Y",),
                      ("C", "Y"), ("M", "Y"), ("C", "M", "Y")),
        bit_levels=("C", "M", "Y"),
        emission_path="DeviceCMYK-image",
        notes="Exact three-bit CMY alphabet, including the CMY triple.",
    ),
    "cmy8-opm": ChannelDefinition(
        definition_id="cmy8-opm",
        label="CMY8 OPM",
        states=("W", "C", "M", "CM", "Y", "CY", "MY", "CMY"),
        state_planes=((), ("C",), ("M",), ("C", "M"), ("Y",),
                      ("C", "Y"), ("M", "Y"), ("C", "M", "Y")),
        bit_levels=("C", "M", "Y"),
        emission_path="sequential-imagemask-overprint-opm1",
        notes="Same CMY8 alphabet through sequential overprint/OPM-1.",
    ),
    "kcmy4-image": ChannelDefinition(
        definition_id="kcmy4-image",
        label="KCMY4 one-hot image",
        states=("K", "C", "M", "Y"),
        state_planes=(("K",), ("C",), ("M",), ("Y",)),
        bit_levels=("b0", "b1"),
        emission_path="DeviceCMYK-image",
        notes=("Two-bit one-hot K/C/M/Y alphabet; no multi-toner state and no "
               "paper-white state."),
    ),
})


def parse_pair(text: str) -> tuple[int, int]:
    token = text.strip().lower()
    if "x" in token:
        left, right = token.split("x", 1)
        pair = int(left), int(right)
    else:
        pair = int(token), int(token)
    if min(pair) <= 0:
        raise ValueError(f"invalid positive pair {text!r}")
    return pair


def mm_to_dots(value_mm: float, dpi: int = BASE_DPI) -> int:
    return round(value_mm / 25.4 * dpi)


def dots_to_mm(value: float, dpi: int = BASE_DPI) -> float:
    return value / dpi * 25.4


def candidate_manifest(definition: ChannelDefinition,
                       grid: GridSpec) -> dict[str, Any]:
    out = definition.candidate(grid).to_dict()
    out.update({
        "definition_id": definition.definition_id,
        "label": definition.label,
        "states": list(definition.states),
        "state_planes": [list(item) for item in definition.state_planes],
    })
    return out


def balanced_states(n: int, n_states: int, label: str) -> np.ndarray:
    """Return a deterministic nearly exact state balance in random order."""
    if n <= 0 or n_states <= 0:
        raise ValueError("state population and alphabet must be positive")
    values = np.arange(n, dtype=np.int64) % n_states
    rng(SEED, label.encode("ascii") + b"/shuffle").shuffle(values)
    return values.astype(np.uint8)


def random_field_states(field: dict[str, Any],
                        definition: ChannelDefinition) -> np.ndarray:
    n = int(field["nx"]) * int(field["ny"])
    return balanced_states(n, len(definition.states), field["seed_label"]).reshape(
        int(field["ny"]), int(field["nx"])
    )


def fec_field_states(field: dict[str, Any],
                     definition: ChannelDefinition) -> np.ndarray:
    """Independent calibration prefix followed by real house LDPC words."""
    nx, ny = int(field["nx"]), int(field["ny"])
    n_cal = int(field["calibration_cells"])
    n_words = int(field["n_codewords"])
    rate_id = str(field["rate_id"])
    if n_cal + n_words * ldpc.N_BITS != nx * ny:
        raise ValueError(f"{field['field_id']}: invalid FEC partition")
    definition_bits = len(definition.bit_levels)
    if not definition_bits:
        raise ValueError("FEC coupon requires a binary-level alphabet")
    prefix = balanced_states(
        n_cal, len(definition.states), field["seed_label"] + "/calibration"
    )
    spec = ldpc.LDPC_LADDER[rate_id]
    suffix = np.zeros(n_words * ldpc.N_BITS, np.uint8)
    for level in range(definition_bits):
        for word in range(n_words):
            label = (
                field["seed_label"]
                + f"/{rate_id}/level{level}/word{word}"
            )
            info = rng(SEED, label.encode("ascii")).integers(
                0, 2, size=spec.k_bits, dtype=np.uint8
            )
            start = word * ldpc.N_BITS
            suffix[start:start + ldpc.N_BITS] |= (
                ldpc.encode(info, spec).astype(np.uint8) << level
            )
    return np.concatenate([prefix, suffix]).reshape(ny, nx)


def field_states(field: dict[str, Any],
                 definition: ChannelDefinition) -> np.ndarray:
    if field["family"] == "fec_coupon":
        states = fec_field_states(field, definition)
    else:
        states = random_field_states(field, definition)
    expected = field.get("state_sha256")
    if expected is not None and state_sha256(states) != expected:
        raise ValueError(f"{field['field_id']}: regenerated state digest mismatch")
    return states


def state_planes(states: np.ndarray,
                 definition: ChannelDefinition) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for plane in definition.planes:
        membership = np.array([
            int(plane in item) for item in definition.state_planes
        ], np.uint8)
        out[plane] = membership[states]
    return out


def _symbol_mask(grid: GridSpec, symbol_shape: str) -> np.ndarray:
    """Return one authored-cell motif in ``(c_y, c_x)`` order."""
    if symbol_shape == "solid-cell":
        return np.ones((grid.c_y, grid.c_x), np.uint8)
    if symbol_shape == "main-diagonal":
        out = np.zeros((grid.c_y, grid.c_x), np.uint8)
        for y in range(grid.c_y):
            x = min(grid.c_x - 1, int((y + 0.5) * grid.c_x / grid.c_y))
            out[y, x] = 1
        return out
    if symbol_shape == "horizontal-half":
        out = np.zeros((grid.c_y, grid.c_x), np.uint8)
        thickness = max(1, grid.c_y // 2)
        start = (grid.c_y - thickness) // 2
        out[start:start + thickness, :] = 1
        return out
    if symbol_shape == "vertical-half":
        out = np.zeros((grid.c_y, grid.c_x), np.uint8)
        thickness = max(1, grid.c_x // 2)
        start = (grid.c_x - thickness) // 2
        out[:, start:start + thickness] = 1
        return out
    raise ValueError(f"unsupported symbol shape {symbol_shape!r}")


def expand_cells(cell_bits: np.ndarray, grid: GridSpec,
                 symbol_shape: str = "solid-cell") -> np.ndarray:
    expanded = np.repeat(
        np.repeat(cell_bits.astype(np.uint8), grid.c_y, axis=0),
        grid.c_x,
        axis=1,
    )
    motif = np.tile(_symbol_mask(grid, symbol_shape), cell_bits.shape)
    return np.ascontiguousarray(expanded * motif)


def state_sha256(states: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(states).tobytes()).hexdigest()


def pattern_bits(probe: dict[str, Any]) -> np.ndarray:
    """Regenerate one typed physical probe on its declared source grid."""
    h, w = int(probe["h_source_dots"]), int(probe["w_source_dots"])
    kind = probe["kind"]
    params = probe.get("params", {})
    if kind in {"solid", "edge_tick"}:
        return np.ones((h, w), np.uint8)
    if kind == "paper":
        return np.zeros((h, w), np.uint8)
    if kind == "tone":
        p = float(params["coverage"])
        return (rng(SEED, probe["seed_label"].encode("ascii")).random((h, w))
                < p).astype(np.uint8)
    if kind == "profile_tone":
        p = float(params["coverage"])
        axis = str(params["axis"])
        random = rng(SEED, probe["seed_label"].encode("ascii"))
        out = np.zeros((h, w), np.uint8)
        if axis == "x":
            cumulative = np.floor(np.arange(w + 1) * p * h).astype(int)
            counts = np.diff(cumulative)
            keys = random.random((h, w))
            for x, count in enumerate(counts):
                if count:
                    out[np.argpartition(keys[:, x], count - 1)[:count], x] = 1
        elif axis == "y":
            cumulative = np.floor(np.arange(h + 1) * p * w).astype(int)
            counts = np.diff(cumulative)
            keys = random.random((h, w))
            for y, count in enumerate(counts):
                if count:
                    out[y, np.argpartition(keys[y], count - 1)[:count]] = 1
        else:
            raise ValueError(f"invalid profile-tone axis {axis!r}")
        return out
    if kind in {"grating", "phase_rail"}:
        on = int(params["on_dots"])
        off = int(params.get("off_dots", on))
        period = on + off
        horizontal = params["orientation"] == "horizontal_lines"
        axis = np.arange(h if horizontal else w) % period
        values = axis < on
        base = values[:, None] if horizontal else values[None, :]
        return np.ascontiguousarray(
            np.broadcast_to(base, (h, w)).astype(np.uint8)
        )
    if kind == "line_width":
        width = int(params["width_dots"])
        period = int(params.get("period_dots", 4 * width))
        horizontal = params["orientation"] == "horizontal_lines"
        axis = np.arange(h if horizontal else w) % period
        values = axis < width
        base = values[:, None] if horizontal else values[None, :]
        return np.ascontiguousarray(
            np.broadcast_to(base, (h, w)).astype(np.uint8)
        )
    if kind == "checker":
        n = int(params["n_dots"])
        yy, xx = np.indices((h, w))
        return (((yy // n) + (xx // n)) & 1).astype(np.uint8)
    if kind == "isolated_dots":
        pitch = int(params["pitch_dots"])
        dot = int(params.get("dot_dots", 1))
        out = np.zeros((h, w), np.uint8)
        y0 = max(0, (pitch - dot) // 2)
        x0 = max(0, (pitch - dot) // 2)
        for y in range(y0, h, pitch):
            for x in range(x0, w, pitch):
                out[y:y + dot, x:x + dot] = 1
        return out
    if kind == "white_holes":
        pitch = int(params["pitch_dots"])
        hole = int(params["hole_dots"])
        out = np.ones((h, w), np.uint8)
        y0 = max(0, (pitch - hole) // 2)
        x0 = max(0, (pitch - hole) // 2)
        for y in range(y0, h, pitch):
            for x in range(x0, w, pitch):
                out[y:y + hole, x:x + hole] = 0
        return out
    if kind == "slanted_edge":
        angle = math.radians(float(params["angle_deg"]))
        yy, xx = np.indices((h, w), dtype=np.float64)
        value = ((xx - (w - 1) / 2.0) * math.cos(angle)
                 + (yy - (h - 1) / 2.0) * math.sin(angle))
        return (value >= 0.0).astype(np.uint8)
    if kind == "microtext":
        return microtext_bits(
            w, h, int(params["stroke_dots"]), str(params["text"]),
            bool(params.get("vertical", False)),
        )
    if kind == "registration_cross":
        stroke = max(1, int(params.get("stroke_dots", 2)))
        out = np.zeros((h, w), np.uint8)
        cy, cx = h // 2, w // 2
        y0, x0 = max(0, cy - stroke // 2), max(0, cx - stroke // 2)
        out[y0:min(h, y0 + stroke), :] = 1
        out[:, x0:min(w, x0 + stroke)] = 1
        return out
    raise ValueError(f"unsupported probe kind {kind!r}")


_FONT_5X7 = {
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F),
    "5": (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F),
    "M": (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11),
    "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "R": (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    "Y": (0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04),
    " ": (0, 0, 0, 0, 0, 0, 0),
}


def microtext_bits(width: int, height: int, stroke: int, text: str,
                   vertical: bool = False) -> np.ndarray:
    """Raster microprint; the stroke width is exactly ``stroke`` dots."""
    glyphs = []
    for char in text.upper():
        rows = _FONT_5X7.get(char, _FONT_5X7[" "])
        glyph = np.array([
            [(row >> (4 - x)) & 1 for x in range(5)] for row in rows
        ], np.uint8)
        glyphs.append(glyph)
    if not glyphs:
        return np.zeros((height, width), np.uint8)
    spacer = np.zeros((7, 1), np.uint8)
    line = np.concatenate([
        item for pair in zip(glyphs, [spacer] * len(glyphs), strict=True)
        for item in pair
    ], axis=1)[:, :-1]
    line = np.repeat(np.repeat(line, stroke, axis=0), stroke, axis=1)
    if vertical:
        line = np.rot90(line)
    out = np.zeros((height, width), np.uint8)
    for y in range(0, height, line.shape[0] + stroke):
        for x in range(0, width, line.shape[1] + stroke):
            h = min(line.shape[0], height - y)
            w = min(line.shape[1], width - x)
            out[y:y + h, x:x + w] = line[:h, :w]
    return out
