"""Deterministic known-state fields and compact typed probe patterns."""

from __future__ import annotations

import hashlib
import math
from typing import Any

import numpy as np

from .model import Candidate, PUBLIC_SEED


def _rng(label: str) -> np.random.Generator:
    seed = hashlib.sha256(PUBLIC_SEED + b"/" + label.encode("utf-8")).digest()
    return np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(seed, dtype=">u4"))
    )


def field_states(field: dict[str, Any], candidate: Candidate) -> np.ndarray:
    nx, ny = int(field["nx"]), int(field["ny"])
    label = (
        f"{field.get('stage', 'discovery')}/{field.get('kind', candidate.page_kind)}/"
        f"copy-{int(field['copy_index'])}/{field['field_id']}"
    )
    values = np.arange(nx * ny, dtype=np.int64) % candidate.n_states
    _rng(label + "/states").shuffle(values)
    return values.astype(np.uint8).reshape(ny, nx)


def state_planes(states: np.ndarray,
                 candidate: Candidate) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for plane in candidate.planes:
        membership = np.array([
            int(plane in row) for row in candidate.state_planes
        ], np.uint8)
        out[plane] = membership[states]
    return out


def _nested_mask(cell: tuple[int, int], state: int,
                 n_states: int) -> np.ndarray:
    width, height = cell
    total = width * height
    count = round(state / (n_states - 1) * total)
    yy, xx = np.indices((height, width))
    # Deterministic dispersed order; each higher level is a strict superset.
    order = np.argsort(
        ((xx * 37 + yy * 61 + (xx ^ yy) * 17) % max(total * 2 + 1, 3)).ravel(),
        kind="stable",
    )
    mask = np.zeros(total, np.uint8)
    mask[order[:count]] = 1
    return mask.reshape(height, width)


def symbol_motif(cell_dots: tuple[int, int],
                 symbol_shape: str) -> np.ndarray:
    """The authored sub-cell ink motif for one non-solid symbol shape.

    Single source for both the emitter's rendered dots and the analyzer's
    sampling offsets — the two must agree bit-for-bit.
    """
    cell_x, cell_y = cell_dots
    motif = np.zeros((cell_y, cell_x), np.uint8)
    if symbol_shape == "diagonal":
        for y in range(cell_y):
            x = min(
                cell_x - 1,
                int(round(y * (cell_x - 1) / max(cell_y - 1, 1))),
            )
            motif[y, x] = 1
    elif symbol_shape == "horizontal-half":
        motif[:max(1, math.ceil(cell_y / 2)), :] = 1
    elif symbol_shape == "vertical-half":
        motif[:, :max(1, math.ceil(cell_x / 2))] = 1
    else:
        raise ValueError(f"unsupported symbol shape {symbol_shape!r}")
    return motif


def expand_state_planes(states: np.ndarray,
                        candidate: Candidate) -> dict[str, np.ndarray]:
    """Expand cells to authored dots, including pinned multilevel motifs."""
    cell_x, cell_y = candidate.cell_dots
    if candidate.symbol_shape.startswith("nested-"):
        if candidate.planes != ("K",):
            raise ValueError("nested levels are implemented only for K")
        height, width = states.shape
        out = np.zeros((height * cell_y, width * cell_x), np.uint8)
        for state in range(candidate.n_states):
            mask = _nested_mask(candidate.cell_dots, state, candidate.n_states)
            yy, xx = np.nonzero(states == state)
            for y, x in zip(yy, xx, strict=True):
                out[y * cell_y:(y + 1) * cell_y,
                    x * cell_x:(x + 1) * cell_x] = mask
        return {"K": out}
    planes = state_planes(states, candidate)
    if candidate.symbol_shape != "solid":
        motif = symbol_motif(candidate.cell_dots, candidate.symbol_shape)
        return {
            plane: np.kron(bits, motif).astype(np.uint8)
            for plane, bits in planes.items()
        }
    return {
        plane: np.repeat(
            np.repeat(bits, cell_y, axis=0), cell_x, axis=1
        ).astype(np.uint8)
        for plane, bits in planes.items()
    }


_FONT = {
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 2, 4, 8, 31),
    "3": (30, 1, 1, 14, 1, 1, 30),
    "4": (2, 6, 10, 18, 31, 2, 2),
    "5": (31, 16, 30, 1, 1, 17, 14),
    "6": (6, 8, 16, 30, 17, 17, 14),
    "7": (31, 1, 2, 4, 8, 8, 8),
    "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 2, 12),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (28, 18, 17, 17, 17, 18, 28),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "H": (17, 17, 17, 31, 17, 17, 17),
    "I": (14, 4, 4, 4, 4, 4, 14),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "V": (17, 17, 17, 17, 17, 10, 4),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    "-": (0, 0, 0, 31, 0, 0, 0),
    " ": (0, 0, 0, 0, 0, 0, 0),
}


def _microtext(width: int, height: int, stroke: int, text: str) -> np.ndarray:
    glyphs = []
    for char in text.upper():
        rows = _FONT.get(char, _FONT[" "])
        glyphs.append(np.array([
            [(row >> (4 - x)) & 1 for x in range(5)] for row in rows
        ], np.uint8))
    if not glyphs:
        return np.zeros((height, width), np.uint8)
    spacer = np.zeros((7, 1), np.uint8)
    line = spacer
    for glyph in glyphs:
        line = np.concatenate([line, glyph, spacer], axis=1)
    line = np.repeat(np.repeat(line, stroke, axis=0), stroke, axis=1)
    out = np.zeros((height, width), np.uint8)
    for y in range(0, height, line.shape[0] + stroke):
        for x in range(0, width, line.shape[1] + stroke):
            h = min(line.shape[0], height - y)
            w = min(line.shape[1], width - x)
            out[y:y + h, x:x + w] = line[:h, :w]
    return out


def pattern_bits(probe: dict[str, Any]) -> np.ndarray:
    width = int(probe["w_source_dots"])
    height = int(probe["h_source_dots"])
    kind = str(probe["kind"])
    params = dict(probe.get("params", {}))
    if kind in {"paper", "quiet_zone"}:
        return np.zeros((height, width), np.uint8)
    if kind in {"solid", "edge_tick", "end_sentinel"}:
        return np.ones((height, width), np.uint8)
    if kind in {"tone", "profile_tone", "entropy_field"}:
        coverage = float(params["coverage"])
        return (
            _rng(str(probe["seed_label"])).random((height, width)) < coverage
        ).astype(np.uint8)
    if kind == "cell_field":
        cell = int(params["cell_dots"])
        if cell <= 0:
            raise ValueError("cell_field cell_dots must be positive")
        ny = math.ceil(height / cell)
        nx = math.ceil(width / cell)
        cells = (
            _rng(str(probe["seed_label"]) + "/cells")
            .random((ny, nx))
            < float(params.get("coverage", 0.5))
        ).astype(np.uint8)
        return np.repeat(
            np.repeat(cells, cell, axis=0), cell, axis=1
        )[:height, :width]
    if kind in {"grating", "phase_rail", "grid_ruler", "line_width"}:
        on = int(params.get("on_dots", params.get("width_dots", 1)))
        off = int(params.get("off_dots", max(on, 1)))
        period = on + off
        horizontal = params.get("orientation") == "horizontal_lines"
        axis = np.arange(height if horizontal else width) % period
        base = (axis < on)[:, None] if horizontal else (axis < on)[None, :]
        return np.broadcast_to(base, (height, width)).astype(np.uint8).copy()
    if kind == "checker":
        size = int(params["n_dots"])
        yy, xx = np.indices((height, width))
        return (((yy // size) + (xx // size)) & 1).astype(np.uint8)
    if kind == "isolated_dots":
        dot, pitch = int(params["dot_dots"]), int(params["pitch_dots"])
        out = np.zeros((height, width), np.uint8)
        y0 = max(0, (pitch - dot) // 2)
        x0 = max(0, (pitch - dot) // 2)
        for y in range(y0, height, pitch):
            for x in range(x0, width, pitch):
                out[y:y + dot, x:x + dot] = 1
        return out
    if kind == "white_holes":
        hole, pitch = int(params["hole_dots"]), int(params["pitch_dots"])
        out = np.ones((height, width), np.uint8)
        y0 = max(0, (pitch - hole) // 2)
        x0 = max(0, (pitch - hole) // 2)
        for y in range(y0, height, pitch):
            for x in range(x0, width, pitch):
                out[y:y + hole, x:x + hole] = 0
        return out
    if kind == "slanted_edge":
        angle = math.radians(float(params.get("angle_deg", 5.0)))
        yy, xx = np.indices((height, width), dtype=np.float64)
        distance = (
            (xx - (width - 1) / 2.0) * math.cos(angle)
            + (yy - (height - 1) / 2.0) * math.sin(angle)
        )
        return (distance >= 0.0).astype(np.uint8)
    if kind == "microtext":
        return _microtext(
            width, height, int(params.get("stroke_dots", 2)),
            str(params.get("text", "HOLO CAL")),
        )
    if kind in {"registration_cross", "plus_mark"}:
        stroke = int(params.get("stroke_dots", 3))
        out = np.zeros((height, width), np.uint8)
        cy, cx = height // 2, width // 2
        out[max(0, cy - stroke // 2):cy + (stroke + 1) // 2, :] = 1
        out[:, max(0, cx - stroke // 2):cx + (stroke + 1) // 2] = 1
        return out
    if kind == "chiral_corner":
        out = pattern_bits({
            **probe, "kind": "plus_mark",
            "params": {"stroke_dots": int(params.get("stroke_dots", 3))},
        })
        count = int(params["satellites"])
        dy, dx = (int(value) for value in params["inward"])
        for index in range(count):
            distance = 18 + 12 * index
            cy = height // 2 + dy * distance
            cx = width // 2 + dx * distance
            out[cy - 4:cy + 4, cx - 4:cx + 4] = 1
        return out
    raise ValueError(f"unsupported pattern kind {kind!r}")
