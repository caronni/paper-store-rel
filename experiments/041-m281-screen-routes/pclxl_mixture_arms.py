"""e041 S11 — the mixture probe's alphabets, arms, palette and per-patch composition (dot level).

Imported by pclxl_mixture.py (the plan, emitter and --verify).  Everything a readout needs to interpret a
patch is recorded from here into the manifest (arms table, colour table, cell layouts) and the patterns npz;
nothing here is re-derived by the readout.

Colours (device RGB sent) and the toner planes each one is MEANT to lay (C, M, Y, K): a single-toner colour
sets one plane, an engine overlap sets several, K sets the K plane in a toner-black band; CMY = (0, 0, 0)
in a process-black band (the three-toner composite).  A cell state is a cell_dots x cell_dots grid of colour
names: solid states fill the cell with one colour; the dotmix overlap states are fixed single-toner dot
layouts (DOTMIX3, DOTMIX2).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RGB = tuple[int, int, int]
PLANES = ("C", "M", "Y", "K")
PATTERN_DOTS, SOLID_DOTS = 93, 24
PATCH_H_DOTS = PATTERN_DOTS + SOLID_DOTS
CELLS_BY_DOTS = {3: 31, 2: 46}  # c2: 46 x 46 cells = the top-left 92 x 92 dots; last row and column white
STATE_SEED_BASE = 41_000  # cell-state seed = base + patch id

# name -> (RGB sent, planes laid); the order is the global palette index (0 = white) in every band image.
COLOURS: dict[str, tuple[RGB, str]] = {
    "W": ((255, 255, 255), ""),
    "C": ((0, 255, 255), "C"),
    "M-solid": ((240, 0, 192), "M"),
    "M-solid2": ((240, 0, 208), "M"),
    "M-corner": ((255, 0, 255), "M"),
    "Y": ((255, 255, 0), "Y"),
    "K": ((0, 0, 0), "K"),
    "CM": ((0, 0, 255), "CM"),
    "CY": ((0, 255, 0), "CY"),
    "MY": ((255, 0, 0), "MY"),
    "CMY": ((0, 0, 0), "CMY"),
}
COLOUR_INDEX = {name: k for k, name in enumerate(COLOURS)}

# Dotmix overlap states, rows of the cell, top to bottom (c3: (r + c) even = the first ink, 5 dots; CMY by
# (r + c) mod 3; c2: the main diagonal = the first ink).
DOTMIX3 = {"CM": (("C", "M", "C"), ("M", "C", "M"), ("C", "M", "C")),
           "CY": (("C", "Y", "C"), ("Y", "C", "Y"), ("C", "Y", "C")),
           "MY": (("M", "Y", "M"), ("Y", "M", "Y"), ("M", "Y", "M")),
           "CMY": (("C", "M", "Y"), ("M", "Y", "C"), ("Y", "C", "M"))}
DOTMIX2 = {"CM": (("C", "M"), ("M", "C")), "CY": (("C", "Y"), ("Y", "C")), "MY": (("M", "Y"), ("Y", "M")),
           "CMY": (("C", "M"), ("Y", "C"))}
CMY8 = ("W", "C", "M", "Y", "CM", "CY", "MY", "CMY")


@dataclass(frozen=True)
class Arm:
    key: str
    family: str
    states: tuple[str, ...]
    m_colour: str | None  # the palette colour of the M state (None: no M state)
    cell_dots: int
    neutral: str  # "process" | "toner": the band kinds the arm is placed in
    overlaps: str  # "none" | "engine" (overlap states = engine overlap colours) | "dotmix" (dot layouts)
    note: str = ""


ARMS: tuple[Arm, ...] = (
    Arm("A01", "W+M", ("W", "M"), "M-solid", 3, "process", "none", "control: the probe's single"),
    Arm("A02", "W+M", ("W", "M"), "M-corner", 3, "process", "none", "control"),
    Arm("A03", "W+C", ("W", "C"), None, 3, "process", "none"),
    Arm("A04", "W+Y", ("W", "Y"), None, 3, "process", "none"),
    Arm("A05", "W+K", ("W", "K"), None, 3, "toner", "none", "toner-black bands only"),
    Arm("A06", "W+C+M", ("W", "C", "M"), "M-solid", 3, "process", "none"),
    Arm("A07", "W+M+Y", ("W", "M", "Y"), "M-solid", 3, "process", "none"),
    Arm("A08", "W+C+Y", ("W", "C", "Y"), None, 3, "process", "none"),
    Arm("A09", "cmy4", ("W", "C", "M", "Y"), "M-solid", 3, "process", "none"),
    Arm("A10", "cmy4", ("W", "C", "M", "Y"), "M-solid2", 3, "process", "none"),
    Arm("A11", "cmy4", ("W", "C", "M", "Y"), "M-corner", 3, "process", "none"),
    Arm("A12", "cmy4", ("W", "C", "M", "Y"), "M-solid", 2, "process", "none"),
    Arm("A13", "cmy4", ("W", "C", "M", "Y"), "M-solid2", 2, "process", "none"),
    Arm("A14", "cmyk5", ("W", "C", "M", "Y", "K"), "M-solid", 3, "toner", "none", "toner-black bands"),
    Arm("A15", "cmyk5", ("W", "C", "M", "Y", "K"), "M-solid", 2, "toner", "none", "toner-black bands"),
    Arm("A16", "C+M", ("C", "M"), "M-solid", 3, "process", "none", "no white at all"),
    Arm("A17", "cmy8-engine", CMY8, "M-corner", 3, "process", "engine", "= S9's palette"),
    Arm("A18", "cmy8-engine", CMY8, "M-solid", 3, "process", "engine"),
    Arm("A19", "cmy8-engine", CMY8, "M-corner", 2, "process", "engine"),
    Arm("A20", "cmy8-dotmix", CMY8, "M-solid", 3, "process", "dotmix"),
    Arm("A21", "cmy8-dotmix", CMY8, "M-solid", 2, "process", "dotmix"),
    Arm("A22", "cmy4", ("W", "C", "M", "Y"), "M-solid", 3, "toner", "none", "the eTonerBlack control"),
)
ARM_BY_KEY = {a.key: a for a in ARMS}


def fractions(arm: Arm) -> tuple[str, ...]:
    """'uniform' and 'whiteheavy' for an arm with white, 'uniform' alone for one without."""
    return ("uniform", "whiteheavy") if "W" in arm.states else ("uniform",)


def probabilities(arm: Arm, fraction: str) -> list[float]:
    """State probabilities in alphabet order: uniform 1/n each; whiteheavy P(W) = 0.5, the rest uniform."""
    n = len(arm.states)
    if fraction == "uniform":
        return [1.0 / n] * n
    rest = 0.5 / (n - 1)
    return [0.5 if s == "W" else rest for s in arm.states]


def colour_of(arm: Arm, single: str) -> str:
    """The palette colour of a single-ink name inside this arm (M -> the arm's M colour)."""
    if single == "M":
        if arm.m_colour is None:
            raise ValueError(f"{arm.key} has no M colour")
        return arm.m_colour
    return single


def cell_layouts(arm: Arm) -> dict[str, list[list[str]]]:
    """State -> cell_dots x cell_dots grid of colour names (rows top to bottom)."""
    d = arm.cell_dots
    out: dict[str, list[list[str]]] = {}
    for s in arm.states:
        if arm.overlaps == "dotmix" and len(s) > 1:
            grid = (DOTMIX3 if d == 3 else DOTMIX2)[s]
            out[s] = [[colour_of(arm, c) for c in row] for row in grid]
        else:
            out[s] = [[colour_of(arm, s)] * d for _ in range(d)]
    return out


def solid_palette(arm: Arm) -> dict[str, list[int]]:
    """State -> RGB for every state whose cell is one colour (all but the dotmix overlaps)."""
    lay = cell_layouts(arm)
    return {s: list(COLOURS[g[0][0]][0]) for s, g in lay.items() if len({c for r in g for c in r}) == 1}


def bar_colour(arm: Arm) -> str:
    """The solid bar's colour: the colour of the arm's first non-white state (its first dot for a mix)."""
    first = next(s for s in arm.states if s != "W")
    return cell_layouts(arm)[first][0][0]


def draw_states(arm: Arm, fraction: str, seed: int) -> np.ndarray:
    """(cells, cells) uint8 state indices into arm.states: default_rng(seed).choice over the alphabet with the
    fraction's probabilities, one draw per cell, row-major."""
    n = CELLS_BY_DOTS[arm.cell_dots]
    rng = np.random.default_rng(seed)
    flat = rng.choice(len(arm.states), size=n * n, p=probabilities(arm, fraction))
    return flat.reshape(n, n).astype(np.uint8)


def compose(arm: Arm, states: np.ndarray) -> np.ndarray:
    """(117, 93) uint8 global palette indices: the pattern square from the states and the cell layouts (c2:
    last row and column white), the 24-dot bar in bar_colour."""
    d = arm.cell_dots
    lay = cell_layouts(arm)
    tiles = np.array([[[COLOUR_INDEX[c] for c in row] for row in lay[s]] for s in arm.states], np.uint8)
    n = states.shape[0]
    square = tiles[states].transpose(0, 2, 1, 3).reshape(n * d, n * d)
    out = np.zeros((PATCH_H_DOTS, PATTERN_DOTS), np.uint8)
    out[:n * d, :n * d] = square
    out[PATTERN_DOTS:] = COLOUR_INDEX[bar_colour(arm)]
    return out


def plane_table(neutral: str) -> np.ndarray:
    """(n_colours, 4) uint8: the toner planes a palette index lays (K only in a toner-black band; a K dot in a
    process band would be the composite, which no arm places there)."""
    t = np.zeros((len(COLOURS), 4), np.uint8)
    for k, (_, planes) in enumerate(COLOURS.values()):
        for p in planes:
            t[k, PLANES.index(p)] = 1
    if neutral == "process":
        t[COLOUR_INDEX["K"]] = (1, 1, 1, 0)
    return t


def planes_of(dots_idx: np.ndarray, neutral: str) -> np.ndarray:
    """(4, 93, 93) uint8 C, M, Y, K ink of the pattern square."""
    return np.ascontiguousarray(plane_table(neutral)[dots_idx[:PATTERN_DOTS]].transpose(2, 0, 1))


def arms_table() -> list[dict]:
    return [{"arm": a.key, "family": a.family, "alphabet": list(a.states), "m_colour": a.m_colour,
             "cell_dots": a.cell_dots, "cells": CELLS_BY_DOTS[a.cell_dots], "neutral": a.neutral,
             "overlaps": a.overlaps, "fractions": list(fractions(a)),
             "probabilities": {f: probabilities(a, f) for f in fractions(a)}, "bar_colour": bar_colour(a),
             "palette": solid_palette(a), "cell_layouts": cell_layouts(a), "note": a.note} for a in ARMS]


def colour_table() -> list[dict]:
    return [{"index": COLOUR_INDEX[n], "name": n, "rgb": list(rgb), "planes": planes,
             "planes_in_process_band": "".join(p for p, v in zip(PLANES, plane_table("process")[k]) if v),
             "planes_in_toner_band": "".join(p for p, v in zip(PLANES, plane_table("toner")[k]) if v)}
            for k, (n, (rgb, planes)) in enumerate(COLOURS.items())]
