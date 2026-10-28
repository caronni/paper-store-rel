"""Rendered synthetic pages for the verdicts (``holo2/measure/verdicts/``).

CARVED 2026-08-16 from the former ``_real_fixtures.py`` (the measure
cleanup, user-ruled: delete the eleven batteries outright, rename
``wall/`` to ``verdicts/`` — git history is the archive, resurrection on
need). This file is the used subset only — every function and constant
``conftest.py``'s three decodes actually call, moved verbatim with
docstrings intact. What the deleted batteries alone exercised
(``BEYOND_FIXED_SWEEP``/``BEYOND_FIXED_SHRINK``, ``COVERAGE_RAMP`` +
``COVERAGE_RAMP_TILES_YX``, ``REFUSAL_TILES_YX``, ``foreign_dots``) did
not come with it; resurrect from history if a future battery needs them.
The ramp arm was the first to be needed and came back at W3, re-measured
for its new question (:data:`SUBDIVISION_RAMP`); the render knob it
drives (``ink_ramp``) never left.

Imports BOTH packages: the page is emitted by the REAL ``src/holo``
generator and then RENDERED to a raster that holo2 ingests as an ordinary
capture. holo2 is told nothing about it beyond what an operator can type:
ONE FORMAT REFERENCE, the page count, and the capture's true DPI.

THE PAGES ARE v2 IDENTITIES SINCE 2026-08-22 (package C4, RULINGS G5:
"migrate these to the new syntax and regenerate the fixtures").  A
synthetic page is named by a v2 format id — ``c3-k-r0550@8x8`` — and a
PRINTED sheet by its ``L:`` fossil line; both sides resolve THE SAME
STRING, ``src/holo`` through ``holo.format.resolve.resolve_format_ref``
and holo2 through ``holo2.format.resolve.format_row_for``, which is what
makes the byte-identity canary in :func:`build_page` an assertion about
one identity rather than about two hand-built descriptions of it.  What
went with the migration is the last media->tiles inversion: geometry IS
the tile matrix (FORMAT-SPACE §7), so a fixture no longer searches for
the millimetres whose derived field happens to be the grid it wanted.

Every number this tree measured before that date was measured on the
v1-identity pages (``c3-r0550@512x512`` and friends).  A different
identity is a different row seed, hence a different address keystream,
slot permutation, pilot field, metadata LFSR and fountain — a different
dot field.  ``holo2/docs/MEASUREMENTS.md`` carries the dated note and
the re-measured pins.

RENDERS ARE CACHED ON DISK (suite economy, H4 W1b). A render is a pure
function of its parameters and the dot field, so it is content-addressed
into a gitignored cache directory and copied out on a hit; nothing about
a DECODE is ever cached.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from holo.core import fountain as h_fountain
from holo.format import metadata as h_metadata
from holo.format.descriptor import FormatSpec
from holo.format.resolve import resolve_format_ref as h_resolve_format_ref
from holo.gen.compose import cells_to_dots, compose_page_cells
from holo.gen.emit import source_packed_for
from holo.gen.plan import max_payload_bytes, plan_volume

from holo2.format import FormatRowSpec
from holo2.format.lattice import is_fossil_ref
from holo2.format.resolve import format_row_for
from holo2.solve.geometry import TILE_CELLS

#: The ENGINE grid these synthetic sheets are EMITTED on — a fixture
#: parameter, named as one (C3, RULINGS G4, 2026-08-22; it was
#: ``PRINT_DPI``).  Dots per cell is an emission fact and needs its
#: engine to mean anything; holo2's receive path carries the physical
#: PITCH instead and never names a printer.  This is emission code, so
#: it names one, once, out loud.
ENGINE_DPI = 600.0
PAPER = 238
INK = 26

# THE MEASURED CHANNEL (e032, Canon 4800 scan of an AltaLink c2-r0700
# sheet, diagnosed against v1's committed poses): the printed cell pitch
# read 16.184 px on y and 16.095 px on x against a declared-DPI nominal of
# 16.000 — +1.15% / +0.6%, anisotropic. The synthetic warp arm used +0.2%
# isotropic, which is BELOW the real channel; that is exactly why the
# synthetic gate passed while the real sheet refused every window. These
# two constants are the regression: the sweep must reach them.
CHANNEL_SCALE_YX = (1.0115, 1.0060)
CHANNEL_ROTATION_DEG = -0.13

# THE COVERAGE RAMP, resurrected from history (W3). The deleted
# differential kit carried a ``ramp`` arm — the e032 root cause, ink
# density falling across the sheet, which thins the survey's support on
# the light side while leaving the supported EXTENT — at
# ``COVERAGE_RAMP = 0.70`` on a 10x10 field, where it isolated the
# bbox-midpoint anchor. W3 needs the same MECHANISM at a stronger
# setting for a different question, so only the parameters come back and
# they come back measured for this arm rather than for that one.
#
# WHAT 0.85 ON AN 11x11 FIELD BUYS, and it is the whole point of the
# subdivision run: one window in the faded band whose 200-cell ladder
# runs out (its wide consult refuses) while three of its four 100-cell
# corners place — a page whose edge window cannot place whole but whose
# corners can. Two of those corners place by a wide consult and one by
# its own word centre, so the arm exercises both halves of the ladder
# BELOW the parent's failure.
#
# THE INCIDENCE IS GEOMETRY-SENSITIVE and the fixture does not pretend
# otherwise: at 0.85 on the v1-identity pages it reproduced over
# 10x10/12x12/14x14 while 9x12, 10x13 and 13x10 placed every window
# whole. That is why the subdivision verdict asserts NON-VACUITY first —
# a change that stops this page subdividing must fail the run, not pass
# it silently.
#
# AND IT FIRED, exactly as designed, on the identity migration
# (2026-08-22, RULINGS G5): the v2 page at 12x12 subdivides NOTHING
# (0 parents, 0 children, close verified at 98-100 certificates over
# ramps 0.83/0.85/0.88), so all four subdivision verdicts failed rather
# than passing on an empty subject. RE-MEASURED over the square field
# sizes at the UNCHANGED ramp, with everything else — coding, warp,
# noise, reading set — held fixed:
#
#   10x10  1 parent, 2 children, both by the wide consult
#   11x11  1 parent, 3 children, TWO by the wide consult and ONE by its
#          own word centre                       <- the arm's whole story
#   12x12  nothing subdivides
#   13x13  nothing subdivides
#   14x14  2 parents, 7 children (6 chain, 1 word), and the parents
#          INTERLEAVE with the children, which breaks the ordering claim
#          "every pass a corner made comes after its parent's cold
#          refusal" — a second parent is not the same arm
#
# So the field moves 12x12 -> 11x11 and NOTHING ELSE DOES: the ramp, the
# phenomenon, both halves of the ladder, and all three counts the verdict
# pins (1 parent, 3 children, 1 parent cold pass) are the numbers this arm
# always had. The geometry was never the claim; the incidence is, and it
# is a property of the dot field a page's identity produces.
SUBDIVISION_RAMP = 0.85
#: The subdivision arm's whole page, as ONE identity (C4, RULINGS G5):
#: the channel's coding on the 11x11 grid the paragraph above measured.
#: Naming the identity rather than a (coding, tiles) pair is the point of
#: the migration — a page is a format id, and the id is the row seed.
SUBDIVISION_FORMAT = "c2-k-r0700@11x11"

# The ARCHITECTURE SPINE's page (H4 W1b). 8x8 = 64 tiles clears the L9
# metadata floor (48 distinct certified counters) with 16 to spare, which
# is exactly the headroom ``damage_ring_tiles=1`` spends: the outer ring
# of an 8x8 grid is 28 tiles, so a ringed run certifies at most 36 and the
# session ends OPEN with real refusals on the ring's windows. c3 keeps the
# raster small (3 dots a cell).
SPINE_FORMAT = "c3-k-r0550@8x8"

#: Where cached renders live. Gitignored; ``HOLO2_E2E_FIXTURE_CACHE``
#: moves it, and setting it EMPTY turns caching off (which is how a run
#: proves the renders still reproduce from their parameters alone).
_CACHE_SETTING = os.environ.get("HOLO2_E2E_FIXTURE_CACHE")
_CACHE_DIR: Path | None = (
    Path(__file__).resolve().parent.parent.parent / ".fixture-cache"
    if _CACHE_SETTING is None
    else (Path(_CACHE_SETTING) if _CACHE_SETTING else None))

#: Bumped by hand when the RENDERING changes but the parameters do not —
#: the cache key cannot see into ``_warp``, so the one thing it cannot
#: content-address is this module's own arithmetic.
RENDER_CACHE_VERSION = "h4w1b-1"


def dots_per_cell(pitch_in: Fraction, engine_dpi: float) -> int:
    """One printed cell, in the dots of a NAMED engine grid.

    The inverse of ``format.native_cell_pitch_px``, and the ONLY shape
    in which dots survive C3 (RULINGS G4, 2026-08-22): a caller that
    wants dots must say whose dots they are.  Refuses a pitch that is
    not a whole number of them, because a renderer cannot lay half a
    dot — the refusal an emission path legitimately has and a receive
    path never did.
    """
    dots = Fraction(pitch_in) * Fraction(str(float(engine_dpi)))
    if dots.denominator != 1:
        raise ValueError(
            f"pitch {pitch_in} in is not a whole number of dots at "
            f"{engine_dpi:g} dpi ({dots}) — nothing can render it")
    return int(dots)


def one_sheet(format_ref: str,
              pages: int = 1) -> tuple[FormatSpec, FormatRowSpec, int]:
    """One format reference -> both trees' description of that sheet.

    THE BYTE-IDENTITY CANARY, and the reason the fixtures moved to v2
    identities (C4, RULINGS G5, 2026-08-22).  Each tree resolves THE SAME
    STRING through its own total resolver — ``src/holo``'s
    ``resolve_format_ref`` to a ``FormatSpec``, holo2's ``format_row_for``
    to a ``FormatRowSpec`` — and the two answers are then compared where
    it matters: the SEED, which is the AES-CTR keystream every address,
    pilot, slot permutation and metadata row hangs off.  Before the
    migration this compared a media-derived v1 spec against a row minted
    through a private legacy bridge; now it compares two readings of one
    identity, which is a strictly stronger statement about the same fact.

    ``row_id`` differs from ``spec_id`` by exactly the ``L:`` marker on
    the legacy route (C2, RULINGS G1) — a NAME, never a keystream — so
    the two spellings are compared with the marker made explicit rather
    than papered over.

    The third element is the EMISSION cell size, in the dots of this
    module's named engine (:data:`ENGINE_DPI`).  It is derived from
    holo2's physical pitch and then checked against ``src/holo``'s own
    ``cell_dots``: the two trees state one printed cell in different
    units (C3, RULINGS G4), and the renderer needs the dots.
    """
    spec = h_resolve_format_ref(format_ref)
    row = format_row_for(format_ref, pages)
    expected_id = ("L:" + spec.spec_id if is_fossil_ref(format_ref)
                   else spec.spec_id)
    assert row.row_id == expected_id, (row.row_id, expected_id)
    assert row.seed == spec.seed, (row.seed, spec.seed)
    cell_dots = dots_per_cell(row.pitch_in, ENGINE_DPI)
    assert cell_dots == spec.cell_dots, (cell_dots, spec.cell_dots)
    return spec, row, cell_dots


@dataclass(frozen=True)
class PageFixture:
    """One emitted volume, its truth, and the row holo2 is given."""

    format_ref: str
    spec: FormatSpec
    row: FormatRowSpec
    payload: bytes
    k_total: int
    symbols: np.ndarray
    metadata_bits: np.ndarray
    dots: np.ndarray

    @property
    def tiles_yx(self) -> tuple[int, int]:
        return self.spec.layout.tiles_yx

    @property
    def cell_dots(self) -> int:
        """How wide one cell is in ENGINE dots, for the renderer.

        Derived from the row's physical pitch and this fixture's own
        ``ENGINE_DPI`` rather than read off ``spec`` (C3, RULINGS G4):
        the arithmetic that turns a pitch into dots belongs to whoever
        is about to lay ink, and saying so here keeps the dots out of
        every consumer that only wanted a cell size.
        """
        return dots_per_cell(self.row.pitch_in, ENGINE_DPI)

    @property
    def tiles_per_page(self) -> int:
        return self.spec.tiles_per_page

    def truth_bits(self, ty: int, tx: int) -> np.ndarray:
        return self.symbols[ty * self.tiles_yx[1] + tx]

    def truth_metadata_bit(self, ty: int, tx: int) -> int:
        return int(self.metadata_bits[ty * self.tiles_yx[1] + tx])


def build_page(format_ref: str, *, payload_blocks: int = 40,
               source_fraction: float = 0.5) -> PageFixture:
    """Emit one K volume on the printed field ``format_ref`` names.

    The tile matrix comes from the IDENTITY (FORMAT-SPACE §7: geometry
    is the tile matrix), so there is nothing left for a caller to state
    twice and nothing left to invert media for.
    """
    spec, row, cell_dots = one_sheet(format_ref, 1)
    payload = hashlib.sha256(
        f"holo2-h3bis-{format_ref}".encode()).digest() * payload_blocks
    plan = plan_volume(spec, len(payload), source_fraction)
    assert plan.n_pages == 1, "the H3bis fixtures are one-page volumes"
    source = source_packed_for(payload, plan)
    counters = np.arange(spec.tiles_per_page, dtype=np.int64)
    code = h_fountain.VolumeCode(plan.k_total, plan.symbol_bits, spec.seed,
                                 tiles_per_page=spec.tiles_per_page)
    symbols = code.encode_symbols(source, counters)
    metadata_bits = h_metadata.tile_bits(
        h_metadata.encode_metadata(0, plan.k_total), counters)
    cells = compose_page_cells(spec, 0, symbols, plan.k_total)
    return PageFixture(
        format_ref=format_ref, spec=spec, row=row, payload=payload,
        k_total=plan.k_total, symbols=symbols, metadata_bits=metadata_bits,
        dots=cells_to_dots(cells, cell_dots))


@dataclass(frozen=True)
class VolumeFixture:
    """A MULTI-SHEET volume: the architecture spine's partial session (W1b).

    The retired toy spine staged "a page half solved" by handing the toys a
    truth table with tiles marked undecided. There is no such knob on a
    real family, and inventing one would be the toy back under another
    name. What a real receiver actually has half of is a VOLUME: sheet 0
    on the platen, sheet 1 still in the folder.

    So the partial state is produced by physics, not by staging. Every
    window of sheet 0 places, every tile of it certifies, the metadata
    rank recovers and K is read — and the close stays OPEN because K
    source symbols do not fit on one sheet. That gives, for free and
    honestly, everything the toy staging was for: a durable OPEN session,
    live open work keys, a frontier with real evidence on it, and windows
    whose supported extent IS wholly spent by certificates (the §6 gate
    needs one, and a one-sheet volume that closes never leaves one behind
    in an inspectable state, because a terminal session ingests nothing).
    Attaching sheet 1 is then the ordinary resume that finishes it.
    """

    format_ref: str
    spec: FormatSpec
    row: FormatRowSpec
    payload: bytes
    k_total: int
    n_pages: int
    symbols: tuple[np.ndarray, ...]         # per page
    metadata_bits: tuple[np.ndarray, ...]   # per page
    dots: tuple[np.ndarray, ...]            # per page

    @property
    def tiles_yx(self) -> tuple[int, int]:
        return self.spec.layout.tiles_yx

    @property
    def cell_dots(self) -> int:
        """How wide one cell is in ENGINE dots, for the renderer.

        Derived from the row's physical pitch and this fixture's own
        ``ENGINE_DPI`` rather than read off ``spec`` (C3, RULINGS G4):
        the arithmetic that turns a pitch into dots belongs to whoever
        is about to lay ink, and saying so here keeps the dots out of
        every consumer that only wanted a cell size.
        """
        return dots_per_cell(self.row.pitch_in, ENGINE_DPI)

    @property
    def tiles_per_page(self) -> int:
        return self.spec.tiles_per_page

    def truth_bits(self, page: int, ty: int, tx: int) -> np.ndarray:
        return self.symbols[page][ty * self.tiles_yx[1] + tx]

    def truth_metadata_bit(self, page: int, ty: int, tx: int) -> int:
        return int(self.metadata_bits[page][ty * self.tiles_yx[1] + tx])


def build_volume(format_ref: str, n_pages: int, *,
                 source_fraction: float = 0.8) -> VolumeFixture:
    """Emit an ``n_pages``-sheet K volume on the field ``format_ref`` names.

    ``source_fraction`` is deliberately high: at K/T = 0.8 the source
    symbol count exceeds one sheet's tiles, so no single sheet can ever
    close the volume however well it decodes. A fixture whose first
    sheet could close by luck would stage nothing at all.
    """
    spec, row, cell_dots = one_sheet(format_ref, n_pages)
    per_page = spec.tiles_per_page
    # Sized by the PLANNER's own promise for this page count, not by an
    # arithmetic of my own: ``max_payload_bytes`` is the largest payload
    # ``n_pages`` sheets carry at this source fraction, so asking for it
    # lands on exactly ``n_pages`` and on the largest K they admit.
    seed_block = hashlib.sha256(f"holo2-h4w1b-{format_ref}".encode()).digest()
    want = max_payload_bytes(spec, source_fraction, n_pages)
    payload = (seed_block * (want // len(seed_block) + 1))[:want]
    plan = plan_volume(spec, len(payload), source_fraction)
    assert plan.n_pages == n_pages, (
        f"{len(payload)} bytes planned {plan.n_pages} pages, not {n_pages}")
    assert plan.k_total > per_page, (
        "a single sheet could close this volume; the staging is vacuous")
    source = source_packed_for(payload, plan)
    code = h_fountain.VolumeCode(plan.k_total, plan.symbol_bits, spec.seed,
                                 tiles_per_page=per_page)
    symbols, metadata, dots = [], [], []
    for page in range(n_pages):
        counters = np.arange(page * per_page, (page + 1) * per_page,
                             dtype=np.int64)
        page_symbols = code.encode_symbols(source, counters)
        symbols.append(page_symbols)
        # ``encode_metadata(version, k)`` — the first argument is the
        # FORMAT VERSION, which is 0 for every page of every v1 volume;
        # what varies per page is only the tile COUNTERS the word is
        # spread over. (Passing the page number here instead produced a
        # fixture whose page-1 truth disagreed with the real receiver by
        # one bit per tile — caught by the pixel-free B9 gate.)
        metadata.append(h_metadata.tile_bits(
            h_metadata.encode_metadata(0, plan.k_total), counters))
        dots.append(cells_to_dots(
            compose_page_cells(spec, page, page_symbols, plan.k_total),
            cell_dots))
    return VolumeFixture(
        format_ref=format_ref, spec=spec, row=row, payload=payload,
        k_total=plan.k_total, n_pages=n_pages, symbols=tuple(symbols),
        metadata_bits=tuple(metadata), dots=tuple(dots))


@dataclass(frozen=True)
class Render:
    """One rendered capture plus the truth pose it was rendered under."""

    path: Path
    dpi: float
    native_affine: tuple[float, ...]      # page cells -> native px

    def predicted_native(self, cell_y: float,
                         cell_x: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.native_affine
        return (a * cell_y + b * cell_x + c, d * cell_y + e * cell_x + f)


def _warp(ideal: np.ndarray, out_shape: tuple[int, int], ideal_pitch: float,
          affine: tuple[float, ...]) -> np.ndarray:
    """Resample the ideal field so page cells land where ``affine`` says.

    Index coordinates are pixel CENTRES; holo2's affines are continuous
    EDGE coordinates (pixel i covers [i, i+1)), hence the half-pixel
    terms.
    """
    a, b, c, d, e, f = affine
    linear = np.array([[a, b], [d, e]], np.float64)
    inverse = np.linalg.inv(linear)
    matrix = ideal_pitch * inverse
    translation = np.array([c, f], np.float64)
    offset = matrix @ (np.full(2, 0.5) - translation) - 0.5
    return ndimage.affine_transform(
        ideal.astype(np.float64), matrix, offset=offset,
        output_shape=out_shape, order=1, mode="constant", cval=float(PAPER))


def render(dots: np.ndarray, path: Path, *, px_per_dot: int, cell_dots: int,
           origin_px: tuple[float, float] = (37.0, 53.0),
           margin_px: int = 40, rotation_deg: float = 0.0,
           pitch_scale: float | tuple[float, float] = 1.0,
           noise_sigma: float = 0.0, cell_error_rate: float = 0.0,
           cell_error_band: tuple[float, float] | None = None,
           damage_ring_tiles: int = 0, damage_rate: float = 0.5,
           ink_ramp: float = 0.0, noise_seed: int = 20260809,
           print_seed: int | None = None) -> Render:
    """Render a dot field to a capture at ``ENGINE_DPI * px_per_dot``.

    Cached on disk (module docstring): the returned ``Render`` is the same
    value either way, and on a hit the PNG is copied out of the cache
    rather than recomputed.

    ``pitch_scale`` is one number, or ``(scale_y, scale_x)`` for the
    ANISOTROPIC case the real channel produces. The scale is applied
    along the PAGE's own axes and then rotated, which is what both
    scanner transport (Canon +0.3-0.6%) and paper hygroexpansion
    (+-0.3%/day) do to a printed field.

    ``cell_error_rate`` flips whole CELLS before rendering — the hard-
    decision channel error the ladders measure (c2 reads 2-5% at 8
    px/dot on both engines). It is not decoration: geometric drift alone
    rarely exhausts a t = 13 word code, and it is drift PLUS the channel's
    own errors that refuses a sheet. A fixture without it cannot
    reproduce what the real e032 capture did.

    ``cell_error_band`` restricts those flips to a fractional COLUMN band
    ``(x0, x1)`` of the page — a toner void band or a fold, both of which
    the M281's known horizontal banding produces on a real sheet.

    ``damage_ring_tiles`` flips cells at ``damage_rate`` in the outermost
    N TILE rings, which is the architecture spine's staging (H4 W1b): the
    ring's cells still print, so the survey's support and the window
    lattice are untouched and every window still fits a lattice — what
    dies is the ADDRESS WORD and the payload under the ring. A run on such
    a page places its interior, certifies below the L9 floor, and ends
    OPEN with a per-window refusal vocabulary. That is the same shape the
    retired toy spine staged with a truth-table bbox, produced by pixels.

    ``ink_ramp`` fades ink contrast across x — the counting page's
    monotone density gradient. It moves the support mask's MASS CENTRE
    while leaving its EXTENT, which is the one thing a symmetric fixture
    can never exercise.

    ``print_seed`` separates WHAT IS ON THE PAPER from WHAT THE SENSOR
    DID (H4-LANES stage 2). The cell flips and the damage ring are
    PRINT facts — they are ink, and two scans of one sheet see the same
    ink — while ``noise_sigma`` is the sensor's own draw and differs
    between scans. One generator drove both until a fixture needed two
    captures of ONE sheet, which is unrepresentable while a second scan
    means a second set of printed errors: that would be two sheets, and
    the multi-scan law's whole subject is that errors are PRINT-
    CORRELATED (CLAUDE.md, F1∘F6). First built for run union (retired
    2026-08-17, merged into run streaming's sheet-0 rescan — the split
    itself outlived the fixture that needed it first). Defaults to
    ``noise_seed``, so every existing render is byte-identical and its
    cache entry stands.
    """
    # The GEOMETRY first: it is a pure function of the parameters, carries
    # no randomness and costs nothing, so a cache hit can return the same
    # ``Render`` value without touching a pixel.
    pitch = float(cell_dots * px_per_dot)
    angle = np.radians(rotation_deg)
    scale_y, scale_x = ((float(pitch_scale), float(pitch_scale))
                        if isinstance(pitch_scale, (int, float))
                        else (float(pitch_scale[0]), float(pitch_scale[1])))
    linear = pitch * np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    ) @ np.diag([scale_y, scale_x])
    cells_yx = (dots.shape[0] // cell_dots, dots.shape[1] // cell_dots)
    corners = np.array([[0, 0], [0, cells_yx[1]],
                        [cells_yx[0], 0], [cells_yx[0], cells_yx[1]]],
                       np.float64) @ linear.T
    translation = (np.array(origin_px, np.float64) - corners.min(axis=0))
    affine = (linear[0, 0], linear[0, 1], translation[0],
              linear[1, 0], linear[1, 1], translation[1])
    rendered = Render(path=path, dpi=ENGINE_DPI * px_per_dot,
                      native_affine=affine)

    cached = _cached_render_path(
        dots, px_per_dot=px_per_dot, cell_dots=cell_dots,
        origin_px=origin_px, margin_px=margin_px, rotation_deg=rotation_deg,
        pitch_scale=(scale_y, scale_x), noise_sigma=noise_sigma,
        cell_error_rate=cell_error_rate, cell_error_band=cell_error_band,
        damage_ring_tiles=damage_ring_tiles, damage_rate=damage_rate,
        ink_ramp=ink_ramp, noise_seed=noise_seed,
        print_seed=noise_seed if print_seed is None else print_seed)
    if cached is not None and cached.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, path)
        return rendered

    # TWO DRAWS, TWO SUBJECTS (see ``print_seed`` above): the ink first,
    # from the print's own seed, and the sensor afterwards from its own.
    # They are the SAME generator when the seeds agree, which is what
    # keeps every render that predates the split byte-identical.
    printing = np.random.default_rng(noise_seed if print_seed is None
                                     else print_seed)
    flips = np.zeros(cells_yx, bool)
    if cell_error_rate > 0.0:
        flips |= printing.random(cells_yx) < cell_error_rate
        if cell_error_band is not None:
            band = np.zeros(cells_yx, bool)
            x0 = int(round(cell_error_band[0] * cells_yx[1]))
            x1 = int(round(cell_error_band[1] * cells_yx[1]))
            band[:, x0:x1] = True
            flips &= band
    if damage_ring_tiles > 0:
        inner = np.zeros(cells_yx, bool)
        edge = damage_ring_tiles * TILE_CELLS
        inner[edge:cells_yx[0] - edge, edge:cells_yx[1] - edge] = True
        flips |= (printing.random(cells_yx) < damage_rate) & ~inner
    generator = (printing if print_seed is None
                 else np.random.default_rng(noise_seed))
    if flips.any():
        dots = dots ^ np.repeat(np.repeat(flips.astype(dots.dtype),
                                          cell_dots, 0), cell_dots, 1)
    printed = np.repeat(np.repeat(dots.astype(bool), px_per_dot, 0),
                        px_per_dot, 1)
    # A monotone ink-DENSITY gradient across x, as the e032 counting page
    # carries. Modelled as falling CONTRAST, not as blanked cells: on the
    # real sheet every cell is still a valid printed cell, and only the
    # structure-tensor ACTIVITY the survey measures falls off. Blanking
    # cells instead would destroy the payload and prove nothing about the
    # anchor (measured: at a 0.5 blanking ramp the volume was already
    # unrecoverable). Falling contrast thins the survey's support on the
    # light side while leaving the supported EXTENT — which is precisely
    # the geometry that separates a bbox midpoint from a mass centroid.
    level = INK + float(ink_ramp) * (PAPER - INK) * np.linspace(
        0.0, 1.0, printed.shape[1])[None, :]
    ideal = np.where(printed, level, float(PAPER))
    # The sheet ends one margin past the page's far corner. Sizing it from
    # the TRANSLATION instead would double it under a 180-degree pose,
    # where the translation already carries the whole extent.
    far = translation + corners.max(axis=0)
    shape = (int(np.ceil(far[0])) + margin_px,
             int(np.ceil(far[1])) + margin_px)
    sheet = _warp(ideal, shape, pitch, affine)
    if noise_sigma > 0.0:
        sheet = sheet + generator.normal(0.0, noise_sigma, sheet.shape)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(np.rint(sheet), 0, 255).astype(np.uint8)).save(path)
    _store_cached_render(cached, path)
    return rendered


# ------------------------------------------------------- the render cache

def _cached_render_path(dots: np.ndarray, **parameters: object) -> Path | None:
    """The content address of one render, or ``None`` if caching is off.

    The key covers the DOT FIELD by content and every parameter by value,
    plus :data:`RENDER_CACHE_VERSION` for the arithmetic the key cannot
    see. Setting ``HOLO2_E2E_FIXTURE_CACHE=`` (empty) turns it off, which
    is what a run that wants to prove the renders still reproduce does.
    """
    if _CACHE_DIR is None:
        return None
    digest = hashlib.sha256()
    digest.update(RENDER_CACHE_VERSION.encode())
    digest.update(f"{dots.dtype}|{dots.shape}".encode())
    digest.update(np.ascontiguousarray(dots).tobytes())
    for name in sorted(parameters):
        digest.update(f"|{name}={parameters[name]!r}".encode())
    return _CACHE_DIR / f"render-{digest.hexdigest()}.png"


def _store_cached_render(cached: Path | None, path: Path) -> None:
    """Publish a fresh render into the cache, atomically and best-effort.

    Two xdist workers may render the same fixture at the same moment, so
    the write goes to a private temporary name and is renamed into place;
    a cache that cannot be written is a slower suite, never a failure.
    """
    if cached is None:
        return
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        pending = cached.with_suffix(f".{os.getpid()}.partial")
        shutil.copyfile(path, pending)
        os.replace(pending, cached)
    except OSError:
        pass


def record_window_passes(monkeypatch) -> list[dict]:
    """A READ-ONLY census of the pull job's PASSES, not just its poses.

    :func:`record_placement_routes` answers "which half of the ladder
    placed this pose"; this answers "what did this window TRY, and what
    came of it". The two facts it adds are the job's own
    (``WindowJob.stage``/``stage_spent``: a stage is SPENT exactly when
    the word decode ran on that pass) and the route that pass reached an
    address by — which together distinguish *the chain placed it because
    the word died* from *the chain placed it because the chain is
    cheaper*. Same discipline as its sibling: the wrapper calls the real
    ``run``, changes no argument and no result, and composes with it
    (whichever is installed first is the one this one calls).
    """
    from holo2.solve.place_job import WindowJob
    from holo2.solve.view import as_plane

    passes: list[dict] = []
    original = WindowJob.run

    def wrapped(self, view, identity, progress, _run=original):
        result = _run(self, view, identity, progress)
        passes.append({
            "window": self.plan.window_id,
            "wide": self.wide,
            "stage_offered": self.stage,
            "stage_spent": self.stage_spent,
            "route": self.route_taken,
            "outcome": result.outcome,
            # W4: which cold flavour this pass was CLAIMED as, and which
            # it actually SPENT. The two differ when the flavour's pages
            # were all already swept by this window, which is the one
            # cold pass that does no correlation.
            "cold": self.cold,
            "cold_spent": self.cold_spent,
            "cold_pages": len(self._cold_pages(as_plane(view)))
            if self.cold else 0,
        })
        return result

    monkeypatch.setattr(WindowJob, "run", wrapped)
    return passes


def record_placement_routes(monkeypatch) -> dict[object, str]:
    """A READ-ONLY observer over the pull job's two ways to an address.

    Which half of the ladder placed a given window is not a durable fact,
    and since H4 W2's pull model it is not even a descriptor: one job
    consults the poses around it and falls through to the word slots when
    that consult is empty, so "the route" is a property of the PASS. The
    job records it for exactly this purpose (``WindowJob.route_taken``)
    and nothing schedules on it.

    Attribution is observed as it happens, exactly as the harness
    observes v1's first-fit-wins seed: the wrapper calls the real
    ``run``, changes no argument and no result, and notes the POSE KEY
    each accepted pass proposed. Keying on the POSE rather than on the
    window is what makes it exact under the pool — a proposal discarded
    as stale never becomes a committed pose, so it can never be counted —
    and it is what lets a caller attribute the poses a finished state
    holds rather than the fires a run made.
    """
    from holo2.solve.place_job import WindowJob

    routes: dict[object, str] = {}
    original = WindowJob.run

    def wrapped(self, view, identity, progress, _run=original):
        result = _run(self, view, identity, progress)
        if result.outcome == "accepted":
            for write in result.writes:
                if write.key.kind == "pose":
                    routes[write.key] = self.route_taken or "unknown"
        return result

    monkeypatch.setattr(WindowJob, "run", wrapped)
    return routes
