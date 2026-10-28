"""Paper profiles and sheet placement — putting a v2 field on real paper.

FORMAT-SPACE §7/§9.  A v2 identity is ``coding x tile matrix``; media,
margins, engine grid and placement are EMISSION facts that never enter a
seed.  This module owns those facts:

- ``PAPER_PROFILES``: named (media, per-edge margin) bundles, the
  ``--paper`` argument of generation.  Printers exited the generation
  path with the second-round ruling; what generation needs from a device
  is the printable rectangle, and that is what a paper profile carries.
- ``sheet_layout``: places one spec's field on one paper profile at one
  engine grid, centered, with the slack split like the v1 derivation
  (odd dot to bottom/right).
- ``fit``: the largest tile matrix a (paper, pitch, engine grid) admits —
  the v1 ``derive_field`` arithmetic, demoted from identity-maker to
  convenience.

Emission gate (FORMAT-SPACE §4/§9, third-round ruling): ``dots_per_cell =
pitch x engine_dpi`` must be a positive integer, and that is the ONLY
gate.  There is no minimum-cell floor: 1 dot/cell is lawful format.  The
measured fact that both 600-dpi engines fail to develop isolated single
dots is characterization knowledge for the operator, never a refusal.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

from ..format.descriptor import FormatSpec
from ..format.lattice import parse_pitch
from ..format.layout import MEDIA_MM, MM_PER_INCH, TILE_CELLS, split_slack

DEFAULT_ENGINE_DPI = 600      # the only measured engine class
DEFAULT_PAPER = "A4-6mm"      # the locked conservative bundle


@dataclass(frozen=True)
class PaperProfile:
    """A named (media, per-edge payload-safe margin) bundle."""

    name: str
    media_id: str
    media_mm: tuple[float, float]
    margin_mm: float
    note: str


def _paper(name: str, media_id: str, margin_mm: float,
           note: str) -> PaperProfile:
    return PaperProfile(name=name, media_id=media_id,
                        media_mm=MEDIA_MM[media_id], margin_mm=margin_mm,
                        note=note)


#: The generation-side paper bundles.  Append-only in practice: a printed
#: sheet's manifest names one of these, and the name should keep meaning
#: what it meant.  (Keying-neutral: none of this ever enters a seed.)
PAPER_PROFILES: Mapping[str, PaperProfile] = MappingProxyType({
    profile.name: profile for profile in (
        _paper("A4-6mm", "a4", 6.0,
               "locked conservative (the pre-Phase-C margin policy)"),
        _paper("A4-4mm", "a4", 4.0,
               "measured-probe, e028/e031/e033 footing (ink reach "
               "3.5-4.3 mm on both engines)"),
        _paper("A3-6mm", "a3", 6.0,
               "unprinted — no A3 print day has happened"),
        _paper("A3-4mm", "a3", 4.0,
               "measured-probe margins on unprinted media — no A3 print "
               "day has happened"),
    )
})


def get_paper(paper: PaperProfile | str) -> PaperProfile:
    if isinstance(paper, PaperProfile):
        return paper
    try:
        return PAPER_PROFILES[paper]
    except KeyError:
        raise KeyError(f"unknown paper profile {paper!r}; known: "
                       f"{sorted(PAPER_PROFILES)}") from None


def page_dots_xy(media_mm: tuple[float, float],
                 engine_dpi: int = DEFAULT_ENGINE_DPI) -> tuple[int, int]:
    """Page raster in dots ``(x, y)`` on an engine's dot grid.

    Each axis is rounded to the nearest multiple of 8 dots (byte-aligned
    rows for the 1-bit PostScript imagemask, F15) — the generalization of
    ``format.layout.page_dots_xy`` over the engine grid.  At 600 dpi it
    reproduces that function bit-for-bit (pinned by
    tests/holo/test_lattice_gen.py); nothing here anchors on 600.
    """
    _require_engine_dpi(engine_dpi)
    w_mm, h_mm = media_mm
    if not (w_mm > 0 and h_mm > 0):
        raise ValueError(f"media_mm must be positive, got {media_mm}")

    def axis(mm: float) -> int:
        return 8 * int(math.floor(mm / MM_PER_INCH * engine_dpi / 8 + 0.5))

    return axis(w_mm), axis(h_mm)


def margin_dots(margin_mm: float, engine_dpi: int) -> int:
    """Per-edge margin in whole dots, rounded OUT (the v1 convention)."""
    _require_engine_dpi(engine_dpi)
    if not (margin_mm >= 0 and math.isfinite(margin_mm)):
        raise ValueError(f"margin_mm must be finite and >= 0, got {margin_mm}")
    return math.ceil(margin_mm / MM_PER_INCH * engine_dpi)


def dots_per_cell(pitch: Fraction | str, engine_dpi: int) -> int:
    """``pitch x engine_dpi``, which must be a positive whole number.

    The only emission gate (FORMAT-SPACE §4, third-round ruling): a cell
    has to land on a whole number of engine dots.  No floor beyond that —
    1 dot/cell emits.
    """
    _require_engine_dpi(engine_dpi)
    exact_pitch = _pitch_fraction(pitch)
    exact = exact_pitch * engine_dpi
    if exact <= 0 or exact.denominator != 1:
        raise ValueError(
            f"pitch {exact_pitch} in x {engine_dpi} dpi = {float(exact):g} "
            f"dots/cell — emission needs a whole positive number of dots "
            f"per cell; this pitch wants an engine grid that is a multiple "
            f"of {exact_pitch.denominator} dpi")
    return int(exact)


@dataclass(frozen=True)
class SheetLayout:
    """One field placed on one sheet: the emission-side page geometry.

    Sizes are in the engine's dots; borders are the measured consequence,
    in mm.  ``field_dots_yx`` is the placed field, ``origin_dots_yx`` its
    top-left corner on the page raster (y, x — raster order, matching the
    numpy page bitmap and the v1 ``FieldLayout``).
    """

    paper: PaperProfile
    engine_dpi: int
    dots_per_cell: int
    page_dots_xy: tuple[int, int]
    origin_dots_yx: tuple[int, int]
    field_dots_yx: tuple[int, int]
    border_top_mm: float
    border_bottom_mm: float
    border_left_mm: float
    border_right_mm: float

    @property
    def media_id(self) -> str:
        return self.paper.media_id

    @property
    def margin_mm(self) -> float:
        return self.paper.margin_mm

    @property
    def mm_per_dot(self) -> float:
        return MM_PER_INCH / self.engine_dpi


def sheet_layout(spec: FormatSpec,
                 paper: PaperProfile | str = DEFAULT_PAPER,
                 engine_dpi: int = DEFAULT_ENGINE_DPI) -> SheetLayout:
    """Center a v2 spec's field on a paper profile at an engine grid."""
    if spec.coding.namespace != "v2":
        raise ValueError(
            f"{spec.spec_id}: sheet placement is the v2 emission path; a "
            f"v1 row derives its page from media x margin (spec.layout)")
    profile = get_paper(paper)
    cell_dots = dots_per_cell(spec.pitch, engine_dpi)
    cells_y, cells_x = spec.cells_yx
    field_y, field_x = cells_y * cell_dots, cells_x * cell_dots
    page_x, page_y = page_dots_xy(profile.media_mm, engine_dpi)
    edge_dots = margin_dots(profile.margin_mm, engine_dpi)
    mm_per_dot = MM_PER_INCH / engine_dpi
    for axis_name, field, page in (("y", field_y, page_y),
                                   ("x", field_x, page_x)):
        if field + 2 * edge_dots > page:
            raise ValueError(
                f"{spec.spec_id} does not fit {profile.name} at "
                f"{engine_dpi} dpi: {axis_name} field {field} dots + 2 x "
                f"{edge_dots} dots margin = {field + 2 * edge_dots} > page "
                f"{page} dots ({field * mm_per_dot:.1f} mm field + "
                f"{2 * profile.margin_mm:.1f} mm margins on "
                f"{profile.media_mm[0 if axis_name == 'x' else 1]:.1f} mm "
                f"media)")
    top, bottom = split_slack(page_y - field_y)
    left, right = split_slack(page_x - field_x)
    return SheetLayout(
        paper=profile,
        engine_dpi=engine_dpi,
        dots_per_cell=cell_dots,
        page_dots_xy=(page_x, page_y),
        origin_dots_yx=(top, left),
        field_dots_yx=(field_y, field_x),
        border_top_mm=top * mm_per_dot,
        border_bottom_mm=bottom * mm_per_dot,
        border_left_mm=left * mm_per_dot,
        border_right_mm=right * mm_per_dot,
    )


def fit(paper: PaperProfile | str, pitch: Fraction | str,
        engine_dpi: int = DEFAULT_ENGINE_DPI) -> tuple[int, int]:
    """Largest ``(tiles_y, tiles_x)`` matrix inside media minus margins.

    The v1 ``derive_field`` arithmetic, per axis and in engine dots:
    ``usable = page - 2*ceil(margin)``, then ``usable // dots_per_cell //
    64`` whole tiles.  A convenience for choosing a matrix — the matrix
    it returns is identity, this computation is not (FORMAT-SPACE §7).
    """
    profile = get_paper(paper)
    cell_dots = dots_per_cell(pitch, engine_dpi)
    page_x, page_y = page_dots_xy(profile.media_mm, engine_dpi)
    edge_dots = margin_dots(profile.margin_mm, engine_dpi)

    def tiles(page_axis_dots: int, axis_name: str) -> int:
        usable = page_axis_dots - 2 * edge_dots
        n_tiles = max(0, usable) // cell_dots // TILE_CELLS
        if n_tiles < 1:
            raise ValueError(
                f"{profile.name} at {engine_dpi} dpi holds no whole "
                f"{TILE_CELLS}-cell tile on {axis_name}: usable {usable} "
                f"dots / {cell_dots} dots per cell < {TILE_CELLS} cells")
        return n_tiles

    return tiles(page_y, "y"), tiles(page_x, "x")


def usable_dots_xy(paper: PaperProfile | str,
                   engine_dpi: int = DEFAULT_ENGINE_DPI) -> tuple[int, int]:
    """Printable rectangle ``(x, y)`` in dots: page minus both margins."""
    profile = get_paper(paper)
    page_x, page_y = page_dots_xy(profile.media_mm, engine_dpi)
    edge_dots = margin_dots(profile.margin_mm, engine_dpi)
    return page_x - 2 * edge_dots, page_y - 2 * edge_dots


def _pitch_fraction(pitch: Fraction | str) -> Fraction:
    return parse_pitch(pitch) if isinstance(pitch, str) else pitch


def _require_engine_dpi(engine_dpi: int) -> None:
    if not isinstance(engine_dpi, int) or isinstance(engine_dpi, bool) \
            or engine_dpi <= 0:
        raise ValueError(f"engine_dpi must be a positive integer, got "
                         f"{engine_dpi!r}")


__all__ = [
    "DEFAULT_ENGINE_DPI",
    "DEFAULT_PAPER",
    "PAPER_PROFILES",
    "PaperProfile",
    "SheetLayout",
    "dots_per_cell",
    "fit",
    "get_paper",
    "margin_dots",
    "page_dots_xy",
    "sheet_layout",
    "usable_dots_xy",
]
