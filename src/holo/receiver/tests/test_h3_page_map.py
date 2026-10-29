"""The one mapping: page cells, printed dots, and the window's frames.

Everything here is synthetic and takes milliseconds.  What it pins is
that a displacement written in PAGE dots means the same page
displacement whatever rotation the window was placed at (I2), that the
two frame conversions are exact inverses, that one dot of field moves
the sampler by exactly one printed dot's worth of pixels, and that the
window carries the two matrices the mapping runs on rather than letting
a consumer re-compose one.

The rot 0-3 frame pins used to live in `test_h3_plane_field_lib`
against `plane_field.to_page_axes`; the algebra moved here whole with
the function, so there is ONE set of them.
"""

from __future__ import annotations

import ast
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo.receiver import data
from holo.receiver.format import identity
from holo.receiver.lib import geometry, page_map
from holo.receiver.plugins import color_region_anchor as anchor
from holo.receiver.plugins import pose
from holo.receiver.tests import _h3_fixture_geometry

FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"
ROW = identity.resolve_format_ref(FORMAT_REF)
WINDOW_CELLS = 8
WID = ("cap", 0, 0, (0, 0, WINDOW_CELLS, WINDOW_CELLS))
#: A page cell-index -> pixel map with rotation and shear in it, so
#: nothing here can pass by being axis-aligned.  Spelling a
#: `native_affine` is the convention that carries no half cell (the pose
#: is production's to compose, `_h3_fixture_geometry`).
SHEARED_NATIVE = (6.0, 0.35, 40.0, -0.2, 6.12, 25.0)
LEVEL_SCALE = Fraction(2)

RECEIVER_ROOT = Path(__file__).resolve().parents[1]


def _window(rot_k: int, native: tuple[float, ...] = SHEARED_NATIVE,
            scale: Fraction = LEVEL_SCALE):
    """A placed window and the page map its pose is composed from.

    The pose comes from the production composer through the fixtures'
    one door; `level_terms` is the same page cell -> pixel map that
    composer starts from, so the two are independent statements of the
    geometry rather than one restated.
    """
    placement = _h3_fixture_geometry.window_placement(
        WID, native,
        _h3_fixture_geometry.grid_cells((0, 0),
                                        (WINDOW_CELLS, WINDOW_CELLS)),
        rot_k=rot_k)
    window = _h3_fixture_geometry.window_pose(ROW, placement, scale=scale)
    level_terms = np.asarray(geometry.compose_from_native(native, scale),
                             np.float64).reshape(2, 3)
    rotation, _translation = pose.rotation_affine(rot_k,
                                                  window.shape_yx_cells)
    return window, level_terms[:, :2], rotation


# ------------------------------------------------- what the window carries

@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
def test_the_window_carries_the_page_map_its_pose_was_composed_from(rot_k):
    """The two matrices are the composer's own, not a consumer's guess.

    `color_region.region_window` builds the window's LOCAL cell->pixel
    2x2 as `level_terms[:, :2] @ rotation`, so `page_linear` is that
    pose with the rotation solved away and `rotation` is the placement's
    own quarter-turn.  A consumer that re-derived either would be
    re-deciding the frame.
    """
    window, page_to_pixels, rotation = _window(rot_k)
    assert np.allclose(window.page_linear, page_to_pixels)
    assert np.allclose(window.rotation, rotation)
    assert np.allclose(anchor.pose_linear(window.affine),
                       window.page_linear @ window.rotation)


# --------------------------------------------------------- the frame

@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
def test_one_page_vector_is_the_same_vector_at_every_rotation(rot_k):
    """Invariant I2, the library half of bar B1.

    A displacement of the printer's is a fact about the PAGE.  Written
    along a placed window's local cell axes it wears that window's
    rotation; the two conversions are exact inverses, which is what lets
    a confetti page whose scraps mix all four rotations pool into one
    field.
    """
    page_dots_xy = np.asarray((0.7, -0.35))
    _window_at, _page_to_pixels, rotation = _window(rot_k)
    local_dots_xy = page_map.local_axes(page_dots_xy, rotation)
    if rot_k:
        assert not np.allclose(local_dots_xy, page_dots_xy), local_dots_xy
    recovered = page_map.page_axes(local_dots_xy, rotation)
    assert np.allclose(recovered, page_dots_xy), recovered


@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
def test_the_frame_conversions_are_the_declared_quarter_turns(rot_k):
    """The quarter-turn spelled out, so the sign convention is pinned.

    A page +x displacement at rot 1 is a local +y one, at rot 2 a local
    -x one and at rot 3 a local -y one: the placement rotates the cells,
    so it rotates the axes a delta is read along the other way.
    """
    _window_at, _page_to_pixels, rotation = _window(rot_k)
    want = {0: (1.0, 0.0), 1: (0.0, 1.0),
            2: (-1.0, 0.0), 3: (0.0, -1.0)}[rot_k]
    got = page_map.local_axes(np.asarray((1.0, 0.0)), rotation)
    assert np.allclose(got, want), got


def test_the_conversions_take_a_whole_table_at_once():
    """Row for row, and 1-D in gives 1-D out."""
    _window_at, _page_to_pixels, rotation = _window(1)
    table = np.asarray([[0.7, -0.35], [0.0, 0.0], [-1.25, 2.0]])
    down = page_map.local_axes(table, rotation)
    assert down.shape == table.shape
    for index in range(table.shape[0]):
        assert np.allclose(down[index],
                           page_map.local_axes(table[index], rotation))
    assert np.allclose(page_map.page_axes(down, rotation), table)


# ---------------------------------------------------- dots into pixels

@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
@pytest.mark.parametrize("cell_dots", [2, 3])
def test_a_page_delta_moves_a_point_the_same_way_at_every_rotation(
        rot_k, cell_dots):
    """One dot is one dot: the frame cannot drift out from under it.

    The SAME page-axis delta, applied to the same window placed at four
    rotations, moves each window's sample points by the same page
    displacement — measured as the local-frame vector the pose would
    have to be handed to land there.  This is the receiver half of bar
    B1 at the unit level, and it is what a consumer applying a page
    field through a LOCAL 2x2 gets wrong at rot 1, 2 and 3.
    """
    window, page_to_pixels, rotation = _window(rot_k)
    points = window.scan_points_yx
    page_dots_xy = np.asarray((0.7, -0.35))
    moved = page_map.raster_points(
        points, window.page_linear,
        np.tile(page_dots_xy, (points.shape[0], 1)), cell_dots)
    through_the_page = points + (page_dots_xy[::-1] / cell_dots
                                 @ page_to_pixels.T)
    assert np.allclose(moved, through_the_page), moved - through_the_page
    local_dots_xy = page_map.local_axes(page_dots_xy, rotation)
    through_the_pose = points + (
        np.tile(local_dots_xy[::-1] / cell_dots, (points.shape[0], 1))
        @ anchor.pose_linear(window.affine).T)
    assert np.allclose(moved, through_the_pose)


def test_the_grid_form_is_the_per_cell_form_broadcast():
    """`(S, 2)` uniform offsets, `(S, N, 2)` out, same arithmetic."""
    window, _page_to_pixels, _rotation = _window(2)
    points = window.scan_points_yx
    offsets = np.asarray([[0.0, 0.0], [0.75, -0.25], [-1.5, 2.0]])
    grid = page_map.raster_point_grid(points, window.page_linear, offsets, 3)
    assert grid.shape == (3, points.shape[0], 2)
    for index, offset in enumerate(offsets):
        one = page_map.raster_points(
            points, window.page_linear,
            np.tile(offset, (points.shape[0], 1)), 3)
        assert np.allclose(grid[index], one)
    assert np.allclose(grid[0], points)


@pytest.mark.parametrize("pitch_px,cell_dots", [(4.0, 2), (6.0, 3),
                                                (12.0, 4)])
def test_one_dot_is_one_dot_at_every_pitch(pitch_px, cell_dots):
    """The units doctrine, measured rather than read off the names.

    On an axis-aligned pose a one-dot page delta moves the sample point
    by exactly the pixels one dot occupies — `pitch_px / cell_dots` —
    whatever the cell size and whatever the sampling rate.
    """
    native = _h3_fixture_geometry.page_native_affine(pitch_px, 12.0)
    window, page_to_pixels, _rotation = _window(
        0, native=native, scale=Fraction(1))
    points = window.scan_points_yx
    moved = page_map.raster_points(
        points, window.page_linear,
        np.tile((1.0, 0.0), (points.shape[0], 1)), cell_dots)
    step = moved - points
    assert np.allclose(step[:, 1], pitch_px / cell_dots)
    assert np.allclose(step[:, 0], 0.0)
    assert np.allclose(page_to_pixels, np.eye(2) * pitch_px)


def test_a_field_is_evaluated_per_cell_on_the_tile_grid():
    """I11 through the mapping's own door, and I6's zero.

    A field solved on the tile grid is read at each cell's own page
    coordinate, so two cells a tile apart in a ramp read different
    numbers; a tile the solve never saw reads exactly zero, which is the
    pose.
    """
    tiles_yx = (3, 4)
    delta = np.zeros(tiles_yx + (2,), np.float64)
    delta[1, :, 0] = np.asarray([0.0, 0.5, 1.0, 1.5])
    #: THE REAL FACT, not a stand-in (2026-09-08).  `plane_delta_dots`
    #: reads `.delta_dots_xy` and nothing else, and `lib/` may not import
    #: `data` to say so in a type; a test that only ever fed it a
    #: duck-type would never have checked that claim against the bird.
    field = data.PlaneField(
        page=0, plane=2, delta_dots_xy=delta,
        support=np.ones(tiles_yx, np.float64),
        uncertainty_dots=np.zeros(tiles_yx, np.float64), n_observations=8,
        n_captures=1, ordinal=1)
    cells = np.asarray([[geometry.TILE_CELLS + geometry.TILE_CELLS // 2,
                         geometry.TILE_CELLS // 2],
                        [geometry.TILE_CELLS + geometry.TILE_CELLS // 2,
                         geometry.TILE_CELLS + geometry.TILE_CELLS // 2],
                        [geometry.TILE_CELLS // 2,
                         geometry.TILE_CELLS // 2]], np.int64)
    read = page_map.plane_delta_dots(field, cells)
    assert read.shape == (3, 2)
    assert read[0, 0] == pytest.approx(0.0)
    assert read[1, 0] == pytest.approx(0.5)
    assert read[2, 0] == pytest.approx(0.0)
    assert np.allclose(read[:, 1], 0.0)


# -------------------------------------------------- I7, by source

#: Every production module that may turn a standing field into per-cell
#: dots.  `lib/page_map` is the mapping; `plugins/fields` is the SOLVE
#: row, which writes the grid and hands it to the diag event; nothing
#: else may read a `PlaneField`'s array — a consumer that did would be
#: choosing its own frame, which is exactly what I7 forbids.
EVALUATE_MODULES: tuple[str, ...] = ("lib/page_map.py",)
FIELD_GRID_MODULES: tuple[str, ...] = ("lib/page_map.py",
                                       "plugins/fields.py")


def _production_files() -> tuple[Path, ...]:
    return tuple(sorted(
        path for path in RECEIVER_ROOT.rglob("*.py")
        if "tests" not in path.parts and "docs" not in path.parts))


def _relative(path: Path) -> str:
    return str(path.relative_to(RECEIVER_ROOT))


def _modules_importing(module_tail: str, name: str) -> tuple[str, ...]:
    """Modules that bind `name` off `...module_tail` as a BARE name.

    The hole this closes, found 2026-09-08: `_modules_calling` matches
    `x.evaluate(...)` only, so a `from ..lib.plane_field import evaluate`
    followed by a plain `evaluate(...)` passed the pin untouched — the
    pin said "nobody writes `x.evaluate(`" where the invariant says
    "nobody evaluates a field".  Widening the CALL sweep to bare names
    was tried first and is wrong: it matches any local function of the
    same name (`plugins/pose.py` has its own `evaluate` closure).  The
    binding is the thing to forbid, and it is unambiguous.
    """
    found: list[str] = []
    for path in _production_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.ImportFrom)
                    and (node.module or "").split(".")[-1] == module_tail
                    and any(alias.name == name for alias in node.names)):
                found.append(_relative(path))
                break
    return tuple(sorted(set(found)))


def _modules_calling(attribute: str) -> tuple[str, ...]:
    found: list[str] = []
    for path in _production_files():
        source = path.read_text()
        if attribute not in source:
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == attribute):
                found.append(_relative(path))
                break
    return tuple(sorted(set(found)))


def test_only_the_mapping_turns_a_standing_field_into_dots():
    """Invariant I7, read off the source.

    `plane_field.evaluate` is the one function that turns a solved grid
    into per-cell dots, and `lib/page_map` is the one module that calls
    it.  A consumer that evaluated a field itself would then have to
    choose a frame to apply it in, and choosing wrong is silent — it is
    the frame regression the whole phase exists to close.
    """
    assert _modules_calling("evaluate") == EVALUATE_MODULES
    assert _modules_importing("plane_field", "evaluate") == (), (
        "a module that binds plane_field.evaluate to a bare name "
        "evaluates a field without the attribute call this pin reads")


def test_only_the_mapping_and_the_solve_row_name_a_fields_own_grid():
    grid: list[str] = []
    for path in _production_files():
        if "delta_dots_xy" not in path.read_text():
            continue
        grid.append(_relative(path))
    named = tuple(sorted(set(grid)))
    # the observation table and the estimator carry a column of the same
    # name; the pin is over the modules that read a SOLVED field
    excused = {
        "data.py": "the fact types' own column",
        "lib/evidence.py": "the evidence table's own column (W8)",
        "lib/plane_field.py": "the estimator, which produces the grid",
        "plugins/field_tiers.py": "the measurement tiers' column",
        "plugins/fields_collect.py": "the observation table's column",
        # NAMED SEPARATELY 2026-09-08: plane_k used to read a solved
        # field's array directly and no longer does — every one of its
        # six hits is a PARAMETER name on the delta the mapping already
        # produced (`field_delta_dots` calls `page_map`, and the sweep
        # is handed the result).  The exclusion is the one place the pin
        # is blind at a module that once did the thing it forbids.
        "plugins/plane_k.py": "parameter names on an already-mapped delta",
    }
    field_readers = tuple(name for name in named if name not in excused)
    assert field_readers == FIELD_GRID_MODULES
