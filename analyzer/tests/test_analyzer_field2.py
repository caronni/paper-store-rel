"""`analyzer.field2` — the page field, correctly done (DESIGN §13).

Pinned here: that a planted field comes back out of the fit (sinusoid +
local bump, and an unobserved tile that must NOT be pulled to zero), that
the delta frame is the PAGE frame on a rot_k-2 placement, that the draws
are deterministic across processes, and that the module is blind.

Then the 2026-09-03 LATE RULING's half — the field is a property of the
PRINTED PAGE, so it is fitted ONCE per (page, plane), pooled over every
lane, from FURNITURE anchors only: that the pooled fit recovers a planted
field across two lanes, that a furniture-only frame really is
word-and-dust-only and its target exclusion moot, that the furniture
memo carries NO certificate token (so the field is byte-identical under
two certificate mappings and constant across cascade generations) while
`field2c` keeps it, and that the profiles name arms that parse.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import subprocess
import sys

import numpy as np
import pytest

from holo3.format import identity
from holo3.plugins import color_region_anchor as anchor
from holo3.plugins import pose as pose_plugin

from analyzer import arms, field2, frame as frame_mod
from analyzer.types import LaneFootprint, RunInputs, TileFootprint

REPO = pathlib.Path(__file__).resolve().parents[2]
FORMAT_REF = "L:c2-cmy8-r0700-p120-x1@3392x2368"

TILES_YX = (37, 53)
PERIOD_TILES = 16.0          # ~ the AltaLink's 100 mm at c2/600 dpi
AMPLITUDE_DOTS = 0.8


def planted(ty: int, tx: int) -> tuple[float, float]:
    """A page-x sinusoid in the x delta, plus one local bump."""
    x = AMPLITUDE_DOTS * np.sin(2.0 * np.pi * tx / PERIOD_TILES)
    bump = 0.5 * float(np.exp(-(((ty - 8) ** 2 + (tx - 40) ** 2) / 8.0)))
    return (float(x + bump), 0.1)


def records(tiles, *, weight: float = 30.0, noise: float = 0.0, seed=3):
    rng = np.random.default_rng(seed)
    out = []
    for ty, tx in tiles:
        dx, dy = planted(ty, tx)
        if noise:
            dx += float(rng.normal(0.0, noise))
            dy += float(rng.normal(0.0, noise))
        out.append(field2.TileOffset(
            ty=int(ty), tx=int(tx), offset_dots_xy=(dx, dy),
            n_labels=int(weight), n_discriminating=20,
            committed_logloss=0.30, search_logloss=0.25, gain=0.05,
            curvature=field2.CURVATURE_SCALE_NATS, weight=float(weight)))
    return tuple(out)


# ------------------------------------------------- synthetic recovery

def test_the_fit_recovers_a_planted_sinusoid_and_its_local_bump():
    """The surface takes the tilt, the smoothed residual takes the rest.

    A degree-3 polynomial cannot represent three periods across a page;
    that is the whole reason the field is a surface PLUS a short-
    bandwidth residual, and this is the test that says the pair does what
    neither half can.
    """
    tiles = [(ty, tx) for ty in range(TILES_YX[0])
             for tx in range(TILES_YX[1]) if (ty + tx) % 2 == 0]
    delta, support, surface, degree, rms, n_used = field2.build_field(
        records(tiles, noise=0.05), TILES_YX)
    assert n_used == len(tiles) and degree == 3
    want = np.asarray([planted(ty, tx) for ty, tx in tiles], np.float64)
    got = np.asarray([delta[ty, tx] for ty, tx in tiles], np.float64)
    error = np.abs(got - want)
    assert float(np.median(error[:, 0])) < 0.07, float(np.median(error[:, 0]))
    assert float(np.max(np.abs(got[:, 1] - 0.1))) < 0.10
    # production's twicing pass, called: the amplitude survives the kernel
    amplitude = 0.5 * float(got[:, 0].max() - got[:, 0].min())
    assert abs(amplitude - AMPLITUDE_DOTS) < 0.12, amplitude
    # the bump is a LOCAL deviation and must survive the surface
    peak = float(delta[8, 40][0] - delta[8, 40 - int(PERIOD_TILES)][0])
    assert peak > 0.25, peak
    assert rms < 0.10 and np.all(support[np.asarray(tiles).T[0],
                                         np.asarray(tiles).T[1]] > 0.0)
    # and the surface alone must NOT already contain the sinusoid
    surface_error = np.abs(
        np.asarray([surface[ty, tx] for ty, tx in tiles])[:, 0] - want[:, 0])
    assert float(np.median(surface_error)) > 0.2, float(
        np.median(surface_error))


def test_an_unobserved_tile_is_not_pulled_toward_zero():
    """`smooth` is zero-padded; the support normalisation is what saves a
    hole and a band edge from being dragged to 0 (DESIGN §4.6)."""
    hole = {(ty, tx) for ty in range(6, 11) for tx in range(20, 27)}
    tiles = [(ty, tx) for ty in range(TILES_YX[0])
             for tx in range(TILES_YX[1]) if (ty, tx) not in hole]
    delta, support, _surface, _degree, _rms, _n = field2.build_field(
        records(tiles), TILES_YX)
    middle = delta[8, 23]
    want = planted(8, 23)
    assert abs(float(middle[0]) - want[0]) < 0.25, float(middle[0])
    assert abs(float(middle[1]) - want[1]) < 0.10, float(middle[1])
    assert float(support[8, 23]) > 0.0        # neighbours reach into it

    # a tile beyond every neighbour's reach keeps the SURFACE and is
    # honestly marked unsupported, rather than reading a fabricated zero
    far = field2.build_field(records([(2, 2), (2, 3), (3, 2)]), TILES_YX)
    assert float(far[1][30, 45]) == 0.0
    assert np.allclose(far[0][30, 45], far[2][30, 45])


def test_a_flat_objective_gets_no_weight_and_a_sharp_zero_keeps_it():
    """The curvature weight, not the gain (module docstring).

    Two tiles win the same offset; the one whose search profile was flat
    must not vote, and a tile whose winner is 0.0 with a sharp profile
    must (a genuine zero is evidence, not an absence).
    """
    tile = dict(ty=4, tx=4, offset_dots_xy=(1.5, 0.0), n_labels=40,
                n_discriminating=20, committed_logloss=0.3,
                search_logloss=0.3, gain=0.0)
    flat = field2.TileOffset(**tile, curvature=0.0, weight=0.0)
    sharp = field2.TileOffset(**{**tile, "offset_dots_xy": (0.0, 0.0)},
                              curvature=0.05, weight=40.0)
    _delta, support, _surface, _degree, _rms, n_used = field2.build_field(
        (flat, sharp), TILES_YX)
    assert n_used == 1 and float(support[4, 4]) > 0.0


def test_the_median_is_published_under_production_s_floor():
    """DESIGN §13: publish in honest units even below 0.25 dots, and say
    what production's writer would have done."""
    tiles = [(ty, tx) for ty in range(0, TILES_YX[0], 2)
             for tx in range(0, TILES_YX[1], 2)]
    small = tuple(
        field2.TileOffset(ty=ty, tx=tx, offset_dots_xy=(0.05, 0.0),
                          n_labels=30, n_discriminating=20,
                          committed_logloss=0.3, search_logloss=0.29,
                          gain=0.01, curvature=0.05, weight=30.0)
        for ty, tx in tiles)
    delta, support, _s, _d, _r, _n = field2.build_field(small, TILES_YX)
    field = field2.PageField(
        lane=("cap", 0), stream_id="Y", page=0, plane=2,
        delta_dots_xy=delta, support=support, poly_dots_xy=delta,
        degree=3, tiles=small,
        median_delta_dots=float(np.median(np.hypot(delta[..., 0],
                                                   delta[..., 1]))),
        residual_rms_dots=0.0)
    assert 0.0 < field.median_delta_dots < 0.25
    assert not field.production_publishable
    assert "0.25d" in field.production_refusal
    assert field.evaluate(np.array([[64 * 4 + 3, 64 * 4 + 3]])) is not None


def test_the_column_profile_reads_the_sinusoid_back():
    tiles = [(ty, tx) for ty in range(TILES_YX[0])
             for tx in range(TILES_YX[1])]
    delta, support, _s, _d, _r, _n = field2.build_field(
        records(tiles), TILES_YX)
    field = field2.PageField(
        lane=("cap", 0), stream_id="Y", page=0, plane=2,
        delta_dots_xy=delta, support=support, poly_dots_xy=delta, degree=3,
        tiles=(), median_delta_dots=0.0, residual_rms_dots=0.0)
    profile = field2.column_profile(field, axis=0)
    assert profile.shape == (TILES_YX[1],)
    spectrum = np.abs(np.fft.rfft(profile - profile.mean()))
    peak = int(np.argmax(spectrum))
    assert abs(TILES_YX[1] / max(peak, 1) - PERIOD_TILES) < 2.0, peak


# ----------------------------------------------------- the delta frame

@pytest.mark.parametrize("rot_k", (0, 1, 2, 3))
def test_a_field2_delta_is_page_frame_and_is_never_rotated(rot_k):
    """DESIGN §4.4's frame, for the analyzer's OWN field.

    `field2`'s per-tile offsets come from `sample.read_rgb`, which shifts
    through ``level_terms[:, :2]`` — the page frame — so the field is
    page-frame by construction and applying `to_page_frame` to it would
    be a second rotation.  The discriminating statement: production
    reaching the SAME displacement on this placement needs
    ``to_page_frame(d, rot_k)``'s inverse, which at rot_k 2 is −d.
    """
    rng = np.random.default_rng(rot_k + 11)
    level_terms = rng.normal(0.0, 4.0, 6)
    page_linear = anchor.pose_linear(tuple(level_terms))
    rotation, _t = pose_plugin.rotation_affine(rot_k, (128, 96))
    points = rng.normal(0.0, 50.0, (13, 2))
    delta_page = rng.normal(0.0, 1.0, (13, 2))

    ours = anchor.shifted_points(points, page_linear, delta_page)
    # what production would have to hold, in ITS frame, for the same move
    theirs = np.linalg.solve(
        rotation, np.asarray(delta_page)[:, ::-1].T).T[:, ::-1]
    assert np.allclose(
        ours, anchor.shifted_points(points, page_linear @ rotation, theirs))
    assert np.allclose(arms.to_page_frame(theirs, rot_k), delta_page)
    if rot_k == 2:
        assert np.allclose(theirs, -delta_page)


def _footprint(page_cells, in_tile, ty=4, tx=6):
    return TileFootprint(page=0, ty=ty, tx=tx, halo_cells=0,
                         page_cells_yx=np.asarray(page_cells, np.int64),
                         in_tile=np.asarray(in_tile, bool),
                         cargo=np.asarray(in_tile, bool),
                         page_shape_cells_yx=(64 * TILES_YX[0],
                                              64 * TILES_YX[1]))


def _lane_footprint(fp, owner_index):
    return LaneFootprint(lane=("cap", 0), tile=fp,
                         observed=np.ones(fp.page_cells_yx.shape[0], bool),
                         owner_index=np.asarray(owner_index, np.int64),
                         points_yx=np.zeros(
                             (fp.page_cells_yx.shape[0], 2), np.float64))


def test_the_field2_arm_reads_the_field_unrotated_on_a_rot_k_2_owner():
    """The arm-level half of the frame ruling: `_field2_delta` returns
    the field's own value, whatever the owning placement's rot_k."""
    delta = np.zeros(TILES_YX + (2,), np.float64)
    delta[..., 0] = 0.7
    delta[..., 1] = -0.3
    field = field2.PageField(
        lane=("cap", 0), stream_id="Y", page=0, plane=2,
        delta_dots_xy=delta, support=np.ones(TILES_YX, np.float64),
        poly_dots_xy=delta, degree=1, tiles=(), median_delta_dots=0.76,
        residual_rms_dots=0.0)
    cells = np.array([[4 * 64 + 10, 6 * 64 + 12],
                      [4 * 64 + 11, 6 * 64 + 13]], np.int64)
    lfp = _lane_footprint(_footprint(cells, [True, True]), [7, 7])
    got, detail = arms._field2_delta(field, lfp)
    assert detail["field2_applied"] is True
    assert np.allclose(got, np.array([[0.7, -0.3], [0.7, -0.3]]))
    assert not np.allclose(got, arms.to_page_frame(got, 2))


def test_the_field2_arm_collapses_explicitly_without_support():
    delta = np.zeros(TILES_YX + (2,), np.float64)
    support = np.ones(TILES_YX, np.float64)
    support[4, 6] = 0.0
    field = field2.PageField(
        lane=("cap", 0), stream_id="Y", page=0, plane=2,
        delta_dots_xy=delta, support=support, poly_dots_xy=delta, degree=1,
        tiles=(), median_delta_dots=0.0, residual_rms_dots=0.0)
    cells = np.array([[4 * 64 + 1, 6 * 64 + 1]], np.int64)
    lfp = _lane_footprint(_footprint(cells, [True]), [0])
    got, detail = arms._field2_delta(field, lfp)
    assert got is None and detail["field2_reason"] == "no_support"

    other, detail = arms._field2_delta(None, lfp)
    assert other is None and detail["field2_reason"] == "no_field"

    wrong = field2.PageField(
        lane=("other", 1), stream_id="Y", page=0, plane=2,
        delta_dots_xy=delta, support=np.ones(TILES_YX, np.float64),
        poly_dots_xy=delta, degree=1, tiles=(), median_delta_dots=0.0,
        residual_rms_dots=0.0)
    got, detail = arms._field2_delta(wrong, lfp)
    assert got is None and "field2_is_for_" in detail["field2_reason"]


def test_the_narrow_grid_is_one_dot_and_the_wide_arm_is_untouched():
    """`field2+offset` searches ±1 dot; `offset` keeps its measured ±2."""
    assert (arms.NARROW_X_MIN, arms.NARROW_X_MAX) == (-1.0, 1.0)
    assert (arms.OFFSET_X_MIN, arms.OFFSET_X_MAX) == (-2.0, 2.0)
    wide = arms._offset_grid(arms.OFFSET_X_MIN, arms.OFFSET_X_MAX,
                             arms.OFFSET_STEP_DOTS)
    narrow = arms._offset_grid(arms.NARROW_X_MIN, arms.NARROW_X_MAX,
                               arms.OFFSET_STEP_DOTS)
    assert len(wide) == 17 and len(narrow) == 9
    assert set(narrow) <= set(wide) and narrow[0] == 0.0


def test_profile_and_x_range_are_no_ops_on_the_existing_offset_arm(
        monkeypatch):
    """The record's claim, pinned: `_search_offset` with both keywords at
    their defaults evaluates the SAME candidates in the SAME order and
    emits the SAME row it did before `field2` touched it.

    The collaborators are stubbed so the pin is on the search itself —
    the grid, its order, the winner and the detail dict — and not on a
    raster.  The narrow range is checked against the same recording, so
    a future edit that widened or reordered the wide grid fails here.
    """
    seen: list[tuple[float, float]] = []

    def fake_read(crops, lfp, *, offset_dots_xy=(0.0, 0.0),
                  affine_override=None, arm="read"):
        seen.append((float(offset_dots_xy[0]), float(offset_dots_xy[1])))
        return offset_dots_xy

    def fake_loss(read, mix, frame, plane, mode, folds, lfp):
        # a sharp minimum at x = +0.5, y = -0.25, and one refusing point
        if read == (0.75, 0.0):
            return None
        return float((read[0] - 0.5) ** 2 + (read[1] + 0.25) ** 2)

    monkeypatch.setattr(arms.sample_mod, "read_rgb", fake_read)
    monkeypatch.setattr(arms, "_loss_of", fake_loss)

    def run(**keywords):
        seen.clear()
        best, detail = arms._search_offset(
            None, None, None, None, 2, "subtract", None, (0.0, 0.0),
            None, **keywords)
        return best, detail, tuple(seen)

    before, detail_before, grid_before = run()
    profiled, detail_profiled, grid_profiled = run(profile=True)
    explicit, detail_explicit, grid_explicit = run(
        x_range=(arms.OFFSET_X_MIN, arms.OFFSET_X_MAX),
        y_range=(arms.OFFSET_Y_MIN, arms.OFFSET_Y_MAX))

    assert grid_profiled == grid_before and grid_explicit == grid_before
    assert profiled == before and explicit == before
    assert detail_explicit == detail_before
    assert detail_before == {"offset_evaluations": 17 + 9,
                             "offset_search_logloss": 0.0}
    # the ONLY difference profile=True makes is the added key
    assert set(detail_profiled) - set(detail_before) == {"offset_profile"}
    assert {name: value for name, value in detail_profiled.items()
            if name != "offset_profile"} == detail_before
    losses = detail_profiled["offset_profile"]
    assert len(losses["x"]) == 17 and len(losses["y"]) == 9
    assert losses["x"][grid_before.index((0.75, 0.0))] is None
    assert before == (0.5, -0.25)

    _narrow, detail_narrow, grid_narrow = run(
        x_range=(arms.NARROW_X_MIN, arms.NARROW_X_MAX))
    assert len(grid_narrow) == 9 + 9
    assert set(x for x, _y in grid_narrow) <= set(x for x, _y in grid_before)
    assert detail_narrow["offset_evaluations"] == 18


def test_both_new_arms_parse_and_the_head_composes():
    assert "field2" in arms.REGISTER_ARMS
    assert "field2+offset" in arms.REGISTER_ARMS
    assert arms.parse_arm("subtract+field2") == ("subtract", "field2")
    assert arms.parse_arm("subtract+field2+offset") == ("subtract",
                                                        "field2+offset")
    assert arms.parse_arm("head+field2+offset") == ("head", "field2+offset")


# -------------------------------------------------------- determinism

def test_the_tile_sample_is_the_same_in_every_process():
    """DESIGN §0: every draw is a hash of (seed, key), never `hash`."""
    candidates = [(ty, tx) for ty in range(20) for tx in range(20)]
    first = field2.sample_tiles(candidates, 40, 20260903)
    assert first == field2.sample_tiles(candidates, 40, 20260903)
    assert first != field2.sample_tiles(candidates, 40, 20260904)
    assert len(first) == 40 and set(first) <= set(candidates)
    code = (
        "from analyzer import field2;"
        "c=[(y,x) for y in range(20) for x in range(20)];"
        "print(field2.sample_tiles(c, 40, 20260903))")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO,
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == repr(first)


class _Placement:
    page = 0


class _Lane:
    lane_id = ("cap", 0)
    placements = (_Placement(),)


class _Inputs:
    format_ref = "holo/v2/test"
    tiles_yx = TILES_YX

    def __init__(self, run_dir):
        self.run_dir = run_dir
        self._cache: dict = {}


def _stub_field(tag):
    return field2.PageField(
        lane=("cap", 0), stream_id="Y", page=0, plane=2,
        delta_dots_xy=np.zeros(TILES_YX + (2,), np.float64),
        support=np.ones(TILES_YX, np.float64),
        poly_dots_xy=np.zeros(TILES_YX + (2,), np.float64), degree=1,
        tiles=(), median_delta_dots=0.0, residual_rms_dots=0.0,
        detail={"tag": tag})


def test_the_memo_returns_a_field_and_never_two_runs_the_same_one(
        monkeypatch):
    """A memo that keys on `id(x)` must hold `x` — `frame._certs_token`
    hardened the identical hazard, and for the identical reason: a dead
    object's id is reused, and the certificate token restarts at 0 for a
    fresh `RunInputs`, so `id(run_dir)` is the only thing separating two
    runs over the same run dir."""
    calls: list[str] = []

    def fake_fit(inputs, certs, lane, stream_id, plane, page, tiles, seed,
                 halo, unmix_mode, bandwidth_tiles):
        calls.append(str(inputs.run_dir))
        return _stub_field(str(inputs.run_dir))

    monkeypatch.setattr(field2, "_fit", fake_fit)
    monkeypatch.setattr(field2, "_MEMO", {})
    monkeypatch.setattr(field2, "_MEMO_ORDER", [])
    monkeypatch.setattr(field2, "_KEY_LOCKS", {})

    certs: dict = {}          # ONE mapping: the token is per identity
    first = _Inputs(pathlib.Path("/run/one"))
    got = field2.fit_page_field(first, certs, _Lane(), "Y", tiles=8, seed=1)
    assert isinstance(got, field2.PageField) and got.detail["tag"] == "/run/one"
    again = field2.fit_page_field(first, certs, _Lane(), "Y", tiles=8, seed=1)
    assert again is got and calls == ["/run/one"]      # the memo hit

    # a DIFFERENT run over a different dir must not read the first field,
    # and the memo must be holding the first run dir so its id is not free
    second = _Inputs(pathlib.Path("/run/two"))
    other = field2.fit_page_field(second, certs, _Lane(), "Y", tiles=8, seed=1)
    assert other.detail["tag"] == "/run/two" and len(calls) == 2
    held = {id(value[1]) for value in field2._MEMO.values()}
    assert id(first.run_dir) in held and id(second.run_dir) in held


def test_build_field_is_a_pure_function_of_its_records():
    tiles = [(ty, tx) for ty in range(0, TILES_YX[0], 3)
             for tx in range(0, TILES_YX[1], 3)]
    one = field2.build_field(records(tiles, noise=0.03), TILES_YX)
    two = field2.build_field(records(tiles, noise=0.03), TILES_YX)
    for left, right in zip(one, two):
        assert np.all(np.asarray(left) == np.asarray(right))


# ------------------------------------------------------------ blindness

# ------------------------------------------ the POOLED furniture field

class _PooledLane:
    """A lane with nothing but an id and a page — the pooled fit's reads
    are stubbed, so nothing else of a lane is touched."""

    def __init__(self, capture: str, level: int) -> None:
        self.capture_id = capture
        self.level_index = level
        self.placements = (_Placement(),)

    @property
    def lane_id(self):
        return (self.capture_id, self.level_index)


def _pooled_inputs(run_dir="/run/pooled"):
    inputs = _Inputs(pathlib.Path(run_dir))
    inputs.lanes = (_PooledLane("capA", 2), _PooledLane("capB", 3))
    return inputs


def _stub_reads(monkeypatch, tiles, *, bias, seen=None, noise=0.0):
    """`_one_tile` replaced by the planted field plus a per-lane bias.

    The bias is the thing pooling has to remove: one lane reads the page
    a quarter dot to the right of the other, which is what two captures
    of one sheet actually do.  `seen` collects the certificate mapping
    each call was handed, so the test can pin that it was `NO_CERTS`.
    """
    monkeypatch.setattr(field2, "covered_tiles",
                        lambda inputs, lane, page: tuple(tiles))
    monkeypatch.setattr(field2.arms_mod, "lane_mix",
                        lambda *a, **k: (object(), {}))

    def fake_one_tile(inputs, certs, lane, stream_id, ty, tx, page, **kw):
        if seen is not None:
            seen.append(certs)
        # DESIGN §0: a seeded draw, never `hash` — the determinism test
        # compares a threaded fit against a serial one.
        rng = np.random.default_rng(
            (int(ty) * 1000003 + int(tx) * 10007
             + int(lane.level_index) * 97) % (1 << 31))
        dx, dy = planted(ty, tx)
        shift = bias[lane.lane_id]
        return field2.TileOffset(
            ty=int(ty), tx=int(tx),
            offset_dots_xy=(dx + shift + noise * float(rng.normal()),
                            dy + noise * float(rng.normal())),
            n_labels=400, n_discriminating=20, committed_logloss=0.30,
            search_logloss=0.25, gain=0.05,
            curvature=field2.CURVATURE_SCALE_NATS, weight=400.0)

    monkeypatch.setattr(field2, "_one_tile", fake_one_tile)


def test_the_pooled_fit_recovers_a_planted_field_from_two_lanes(monkeypatch):
    """The ruling's fit: one field per (page, plane) over every lane.

    Two lanes read the same planted page with opposite quarter-dot
    biases — the pooled field must land on the plant, not on either
    lane, and every tile must record that two lanes stood behind it.
    """
    tiles = [(ty, tx) for ty in range(TILES_YX[0])
             for tx in range(TILES_YX[1]) if (ty + tx) % 2 == 0]
    inputs = _pooled_inputs()
    seen: list = []
    _stub_reads(monkeypatch, tiles, seen=seen, noise=0.05,
                bias={("capA", 2): +0.25, ("capB", 3): -0.25})

    field = field2.fit_pooled_page_field(
        inputs, "Y", 0, tiles=None, seed=5, workers=1, memoise=False)

    assert field.pooled and field.lane is None
    assert field.anchors == field2.ANCHORS_FURNITURE
    assert field.lanes == (("capA", 2), ("capB", 3))
    assert all(certs is field2.NO_CERTS for certs in seen) and seen
    assert field.detail["certificate_free"] is True
    assert field.detail["n_lane_tile_reads"] == 2 * len(tiles)
    assert set(int(item.n_lanes) for item in field.tiles) == {2}
    assert np.all(field.n_lanes[np.asarray(tiles).T[0],
                                np.asarray(tiles).T[1]] == 2)

    want = np.asarray([planted(ty, tx) for ty, tx in tiles], np.float64)
    got = np.asarray([field.delta_at_tile(ty, tx) for ty, tx in tiles],
                     np.float64)
    assert float(np.median(np.abs(got[:, 0] - want[:, 0]))) < 0.07
    assert float(np.max(np.abs(got[:, 1] - 0.1))) < 0.12
    # and the two lanes' biases really were opposite and material
    assert float(np.median(np.abs(got[:, 0] - (want[:, 0] + 0.25)))) > 0.15


def test_the_pooled_fit_is_deterministic_and_thread_count_free(monkeypatch):
    """DESIGN §0: a threaded fit and a serial one are the same object."""
    tiles = [(ty, tx) for ty in range(0, TILES_YX[0], 2)
             for tx in range(0, TILES_YX[1], 2)]
    inputs = _pooled_inputs()
    _stub_reads(monkeypatch, tiles, noise=0.05,
                bias={("capA", 2): +0.2, ("capB", 3): -0.2})
    serial = field2.fit_pooled_page_field(inputs, "C", 0, tiles=None, seed=5,
                                          workers=1, memoise=False)
    again = field2.fit_pooled_page_field(inputs, "C", 0, tiles=None, seed=5,
                                         workers=1, memoise=False)
    threaded = field2.fit_pooled_page_field(inputs, "C", 0, tiles=None,
                                            seed=5, workers=4, memoise=False)
    for other in (again, threaded):
        assert np.array_equal(serial.delta_dots_xy, other.delta_dots_xy)
        assert np.array_equal(serial.support, other.support)
        assert np.array_equal(serial.n_lanes, other.n_lanes)


def test_the_furniture_memo_has_no_certificate_token_and_field2c_does():
    """The ruling's key: furniture is certificate-INDEPENDENT, so the
    token would only force a refit per cascade generation; `field2c`
    reads certificates, so two mappings must never share an entry."""
    inputs = _pooled_inputs()
    lanes = [lane.lane_id for lane in inputs.lanes]
    first: dict = {(0, 1, 1, "Y"): "a"}
    second: dict = {(0, 2, 2, "Y"): "b"}

    def key(certs, anchors):
        return field2._pooled_memo_key(inputs, certs, "Y", 0, anchors, lanes,
                                       200, 5, "subtract", 32, 2.0, "wmedian")

    furniture = key(first, field2.ANCHORS_FURNITURE)
    assert furniture == key(second, field2.ANCHORS_FURNITURE)
    assert furniture[-1] is None                      # the token slot
    certified = key(first, field2.ANCHORS_CERTIFIED)
    assert certified[-1] is not None
    assert certified != key(second, field2.ANCHORS_CERTIFIED)

    # the per-lane fit's own key keeps the token too (it always did)
    lane = inputs.lanes[0]
    assert field2._memo_key(inputs, first, lane, "Y", 0, 200, 5,
                            "subtract", 32, 2.0) \
        != field2._memo_key(inputs, second, lane, "Y", 0, 200, 5,
                            "subtract", 32, 2.0)


def test_the_furniture_field_is_identical_under_two_certificate_sets(
        monkeypatch):
    """The invariance the ruling rests on, end to end: the cascade's
    certificate set moves and the field does not — the same object comes
    back from the memo, and an unmemoised refit is byte-identical."""
    tiles = [(ty, tx) for ty in range(0, TILES_YX[0], 3)
             for tx in range(0, TILES_YX[1], 3)]
    inputs = _pooled_inputs()
    _stub_reads(monkeypatch, tiles, bias={("capA", 2): 0.1, ("capB", 3): 0.0})
    monkeypatch.setattr(field2, "_MEMO", {})
    monkeypatch.setattr(field2, "_MEMO_ORDER", [])
    monkeypatch.setattr(field2, "_KEY_LOCKS", {})

    generation_1: dict = {(0, 1, 1, "Y"): "cert"}
    generation_2: dict = {(0, 1, 1, "Y"): "cert", (0, 2, 2, "Y"): "another"}
    one = field2.fit_pooled_page_field(inputs, "Y", 0, certs=generation_1,
                                       tiles=None, seed=5)
    two = field2.fit_pooled_page_field(inputs, "Y", 0, certs=generation_2,
                                       tiles=None, seed=5)
    assert two is one                                   # ONE fit, not two
    fresh = field2.fit_pooled_page_field(inputs, "Y", 0, certs=generation_2,
                                         tiles=None, seed=5, memoise=False)
    assert np.array_equal(fresh.delta_dots_xy, one.delta_dots_xy)


def test_the_weighted_median_pooling_survives_an_outlier_lane():
    """Why the default is `wmedian` (the module docstring): one lane
    whose search latched onto the wrong minimum must not move the tile,
    and the mean shows what it would have cost."""
    def record(dx, weight=100.0):
        return field2.TileOffset(
            ty=3, tx=4, offset_dots_xy=(dx, 0.0), n_labels=int(weight),
            n_discriminating=20, committed_logloss=0.3, search_logloss=0.25,
            gain=0.05, curvature=0.05, weight=weight)

    good = [record(0.25), record(0.25), record(0.5), record(0.25)]
    with_outlier = good + [record(-2.0)]
    median = field2.pool_tile(with_outlier, field2.POOL_WMEDIAN)
    mean = field2.pool_tile(with_outlier, field2.POOL_WMEAN)
    assert median.offset_dots_xy[0] == 0.25
    assert mean.offset_dots_xy[0] < -0.1
    assert median.n_lanes == 5 and median.weight == 500.0
    assert field2.pool_tile((), field2.POOL_WMEDIAN) is None
    zero = field2.TileOffset(
        ty=3, tx=4, offset_dots_xy=(9.0, 9.0), n_labels=0,
        n_discriminating=0, committed_logloss=None, search_logloss=None,
        gain=None, curvature=0.0, weight=0.0, refusal="search_refused")
    assert field2.pool_tile((zero,), field2.POOL_WMEDIAN) is None
    with pytest.raises(ValueError):
        field2.pool_tile(good, "mode-that-does-not-exist")


def test_a_pooled_field_is_page_scope_and_a_per_lane_one_is_not():
    """The arm-level half of the ruling: a pooled field carries no lane,
    so every lane of its page reads it; a per-lane field still refuses
    on a lane that is not its own, and both refuse another PAGE."""
    delta = np.zeros(TILES_YX + (2,), np.float64)
    delta[..., 0] = 0.4
    common = dict(stream_id="Y", page=0, plane=2, delta_dots_xy=delta,
                  support=np.ones(TILES_YX, np.float64), poly_dots_xy=delta,
                  degree=1, tiles=(), median_delta_dots=0.4,
                  residual_rms_dots=0.0)
    pooled = field2.PageField(lane=None, lanes=(("capA", 2), ("capB", 3)),
                              anchors=field2.ANCHORS_FURNITURE, **common)
    per_lane = field2.PageField(lane=("capA", 2), **common)
    cells = np.array([[4 * 64 + 10, 6 * 64 + 12]], np.int64)
    lfp = _lane_footprint(_footprint(cells, [True]), [7])   # lane ("cap", 0)

    got, detail = arms._field2_delta(pooled, lfp)
    assert got is not None and detail["field2_applied"] is True
    assert detail["field2_pooled"] is True
    assert detail["field2_n_lanes_pooled"] == 2

    refused, detail = arms._field2_delta(per_lane, lfp)
    assert refused is None and "field2_is_for_" in detail["field2_reason"]

    other_page = field2.PageField(
        lane=None, lanes=(("capA", 2),),
        anchors=field2.ANCHORS_FURNITURE,
        **{**common, "page": 1})
    refused, detail = arms._field2_delta(other_page, lfp)
    assert refused is None and detail["field2_reason"] == "field2_is_for_1_not_0"


def test_the_field2_family_parses_and_the_profiles_name_real_arms():
    from analyzer.types import PROFILES
    for name in ("field2", "field2+offset", "field2c", "field2c+offset"):
        assert name in arms.REGISTER_ARMS and name in arms.FIELD2_ARMS
    assert arms.FIELD2_ARMS["field2+offset"] == field2.ANCHORS_FURNITURE
    assert arms.FIELD2_ARMS["field2c+offset"] == field2.ANCHORS_CERTIFIED
    assert arms.parse_arm("subtract+field2c+offset") == ("subtract",
                                                         "field2c+offset")
    everything = PROFILES["everything"]["arms"]
    assert "subtract+field2+offset" in everything
    assert "head+field2+offset" in everything
    assert not any("field2c" in arm for arm in everything)
    targeted = PROFILES["everything+field2"]["arms"]
    assert "subtract+field2c+offset" in targeted
    assert set(everything) <= set(targeted)
    for profile in ("everything", "everything+field2"):
        for arm in PROFILES[profile]["arms"]:
            arms.parse_arm(arm)                    # raises if it does not


# ---------------------------- the furniture frame the pooled fit reads

def _offline_inputs():
    """A `RunInputs` carrying only what `frame.known_frame` reads."""
    row = identity.resolve_format_ref(FORMAT_REF)
    return RunInputs(
        run_dir=pathlib.Path("."), format_ref=row.row_id, row=row,
        geometry=frame_mod.geometry_of(row), pitch_in=row.pitch_in,
        tiles_yx=tuple(row.tiles_yx), cells_yx=tuple(row.cells_yx),
        live_pages=(0,), declared_pages=(0,), captures=(), lanes=(),
        lane_policy="all", rung_ppc=None, certificates={},
        plane_fields={}, pooled_ctx={}, lattice_seeds=(), windows={},
        surveys={}, metadata_word=None, metadata_version=None,
        metadata_state="absent", k_total=None, rank_report=None,
        close_report={}, provenance={})


def test_an_empty_certificate_mapping_gives_word_and_dust_only():
    """The ruling's verification, made a pin.

    With `NO_CERTS` the frame projects NO tile, its known mask is exactly
    the furniture mask on all three planes, and the target exclusion is
    MOOT — two different targets in the same tile get byte-identical
    frames, because there is no certificate to exclude.
    """
    inputs = _offline_inputs()
    fp = frame_mod.tile_footprint(inputs.row, 0, 10, 10, 16,
                                  geometry=inputs.geometry)
    got = frame_mod.known_frame(inputs, field2.NO_CERTS, fp, (0, 10, 10, "Y"),
                                metadata_known=False)
    assert got.detail["n_tiles_projected"] == 0
    assert np.array_equal(
        got.known, np.repeat(np.asarray(got.furniture, bool)[:, None], 3, 1))
    assert got.detail["n_known_target_plane"] == int(got.furniture.sum()) > 0
    other = frame_mod.known_frame(inputs, field2.NO_CERTS, fp,
                                  (0, 10, 10, "C"), metadata_known=False)
    assert np.array_equal(got.known, other.known)
    assert np.array_equal(got.bits, other.bits)
    # ... and it is exactly the `--labels furniture` ablation, not less:
    # every furniture cell of every tile the footprint touches is known.
    assert int(got.furniture.sum()) > int(fp.in_tile.sum() * 0.01)


@pytest.mark.parametrize("module", ("field2",))
def test_field2_never_imports_truth_or_oracle(module):
    """DESIGN §0's import-set rule, for the new module."""
    loaded = importlib.import_module(f"analyzer.{module}")
    tree = ast.parse(pathlib.Path(loaded.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add("." * node.level + (node.module or ""))
    assert not any("truth" in name or "oracle" in name
                   for name in imported), sorted(imported)
    source = pathlib.Path(loaded.__file__).read_text(encoding="utf-8")
    for forbidden in ("user_bits", "gt_", "payload_sha"):
        assert forbidden not in source, forbidden
