"""`analyzer.field2` — the page field, correctly done (DESIGN §13).

Pinned here: that a planted field comes back out of the fit (sinusoid +
local bump, and an unobserved tile that must NOT be pulled to zero), that
the delta frame is the PAGE frame on a rot_k-2 placement, that the draws
are deterministic across processes, and that the module is blind.

Then the 2026-09-03 LATE RULING's half — the field is a property of the
PRINTED PAGE, so it is fitted ONCE per (page, plane), pooled over every
lane, from FURNITURE anchors only: that the pooled fit recovers a planted
field across two lanes, that a furniture-only frame really is
word-and-dust-only and its target exclusion moot, that the memo carries
NO certificate token (so the field is byte-identical under two
certificate mappings and constant across cascade generations), and that
the profiles name arms that parse.  The certificate-anchored per-lane
fit and its `field2c` arms retired on 2026-09-12 (A2), and the pins that
were theirs went with them.
"""

from __future__ import annotations

import importlib
import inspect
import json
import pathlib
import subprocess
import sys
import time

import numpy as np
import pytest

from holo.receiver.format import identity
from holo.receiver.lib import page_map
from holo.receiver.plugins import color_region_anchor as anchor
from holo.receiver.plugins import pose as pose_plugin

from analyzer import arms, field2, field2_kernel
from analyzer import frame as frame_mod
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
    delta, support, surface, degree, rms, n_used, n_clamped = \
        field2.build_field(records(tiles, noise=0.05), TILES_YX)
    assert n_used == len(tiles) and degree == 3 and n_clamped == 0
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
    delta, support, _surface, _degree, _rms, _n, _c = field2.build_field(
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
    _delta, support, _surface, _degree, _rms, n_used, _c = \
        field2.build_field((flat, sharp), TILES_YX)
    assert n_used == 1 and float(support[4, 4]) > 0.0


def test_a_small_median_is_published_with_no_floor_to_report_against():
    """A2 (2026-09-12): the quarter-dot floor reporting is DELETED.

    This test used to assert that a 0.05-dot field was published anyway
    and annotated with `production_publishable` / `production_refusal` —
    production's writer refusing at `MIN_DELTA_DOTS` because it ADOPTED a
    published field blindly.  The receiver retired the floor with the gate
    it belonged to (`docs/PAGE-FIELD-DESIGN.md` I8), and a floor the
    receiver retired is nothing to report against.  What survives is the
    half that was always field2's own: honest units at any magnitude, and
    a field that evaluates.
    """
    tiles = [(ty, tx) for ty in range(0, TILES_YX[0], 2)
             for tx in range(0, TILES_YX[1], 2)]
    small = tuple(
        field2.TileOffset(ty=ty, tx=tx, offset_dots_xy=(0.05, 0.0),
                          n_labels=30, n_discriminating=20,
                          committed_logloss=0.3, search_logloss=0.29,
                          gain=0.01, curvature=0.05, weight=30.0)
        for ty, tx in tiles)
    delta, support, _s, _d, _r, _n, _c = field2.build_field(small, TILES_YX)
    field = field2.PageField(
        lane=("cap", 0), stream_id="Y", page=0, plane=2,
        delta_dots_xy=delta, support=support, poly_dots_xy=delta,
        degree=3, tiles=small,
        median_delta_dots=float(np.median(np.hypot(delta[..., 0],
                                                   delta[..., 1]))),
        residual_rms_dots=0.0)
    assert 0.0 < field.median_delta_dots < 0.25
    assert field.evaluate(np.array([[64 * 4 + 3, 64 * 4 + 3]])) is not None
    for gone in ("production_publishable", "production_refusal"):
        assert not hasattr(field, gone), gone
    assert not any(name.startswith("production_")
                   for name in field2.summary(field)), field2.summary(field)
    assert "fields_plugin" not in pathlib.Path(
        field2.__file__).read_text(encoding="utf-8")


def test_the_column_profile_reads_the_sinusoid_back():
    tiles = [(ty, tx) for ty in range(TILES_YX[0])
             for tx in range(TILES_YX[1])]
    delta, support, _s, _d, _r, _n, _c = field2.build_field(
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

    ours = page_map.raster_points(points, page_linear, delta_page, 1)
    # what production would have to hold, in ITS frame, for the same move
    theirs = np.linalg.solve(
        rotation, np.asarray(delta_page)[:, ::-1].T).T[:, ::-1]
    assert np.allclose(
        ours, page_map.raster_points(points, page_linear @ rotation, theirs, 1))
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
    runs over the same run dir.  Pinned on the POOLED fit since A2
    (2026-09-12) retired the per-lane one; the memo is the same memo."""
    calls: list[str] = []

    def fake_fit(inputs, certs, pool_lanes, stream_id, plane, page, anchors,
                 tiles, seed, halo, unmix_mode, bandwidth_tiles, pool,
                 workers):
        calls.append(str(inputs.run_dir))
        return _stub_field(str(inputs.run_dir))

    monkeypatch.setattr(field2, "_pooled_fit", fake_fit)
    monkeypatch.setattr(field2, "_MEMO", {})
    monkeypatch.setattr(field2, "_MEMO_ORDER", [])
    monkeypatch.setattr(field2, "_KEY_LOCKS", {})

    first = _pooled_inputs("/run/one")
    got = field2.fit_pooled_page_field(first, "Y", 0, tiles=8, seed=1)
    assert isinstance(got, field2.PageField) and got.detail["tag"] == "/run/one"
    again = field2.fit_pooled_page_field(first, "Y", 0, tiles=8, seed=1)
    assert again is got and calls == ["/run/one"]      # the memo hit

    # a DIFFERENT run over a different dir must not read the first field,
    # and the memo must be holding the first run dir so its id is not free
    second = _pooled_inputs("/run/two")
    other = field2.fit_pooled_page_field(second, "Y", 0, tiles=8, seed=1)
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


def test_concurrent_fits_share_one_bound_on_reads_in_flight(monkeypatch):
    """A2's worker wiring hands every fit the PASS's width, and up to one
    fit per (page, stream) can be in flight — six on a duplex colour
    sheet — so the reads have to share a bound or a run holds `6 x
    workers` crops on a machine sized for `workers`.  Two fits are run
    at once here with the pool at 2: the observed peak of concurrent
    per-lane reads never passes it.  The counterfactual is measured —
    the same two fits with the bound removed peak at 4 — so the upper
    bound has teeth; the lower one is 1 because whether two threads
    overlap at all is the machine's business, not the code's."""
    import threading as th

    tiles = [(ty, tx) for ty in range(0, TILES_YX[0], 6)
             for tx in range(0, TILES_YX[1], 6)]
    inputs = _pooled_inputs()
    _stub_reads(monkeypatch, tiles, bias={("capA", 2): 0.0, ("capB", 3): 0.0})
    monkeypatch.setattr(field2, "_READ_SLOTS", None)
    monkeypatch.setattr(field2, "_MEMO", {})
    monkeypatch.setattr(field2, "_MEMO_ORDER", [])
    monkeypatch.setattr(field2, "_KEY_LOCKS", {})

    live = 0
    peak = 0
    guard = th.Lock()
    inner = field2._lane_records

    def counted(*args, **kwargs):
        nonlocal live, peak
        with guard:
            live += 1
            peak = max(peak, live)
        try:
            time.sleep(0.01)              # long enough to overlap at all
            return inner(*args, **kwargs)
        finally:
            with guard:
                live -= 1

    monkeypatch.setattr(field2, "_lane_records", counted)
    assert field2.read_slots(2) is field2.read_slots(8)   # created once
    fits = [th.Thread(target=field2.fit_pooled_page_field,
                      args=(inputs, stream, 0),
                      kwargs={"tiles": None, "seed": 5, "workers": 2,
                              "memoise": False})
            for stream in ("C", "M")]
    for fit in fits:
        fit.start()
    for fit in fits:
        fit.join()
    assert peak >= 1 and peak <= 2, peak


def test_the_furniture_memo_has_no_certificate_token_at_all():
    """The ruling's key: furniture is certificate-INDEPENDENT, so the
    token would only force a refit per cascade generation.  The key has
    not taken a certificate mapping since A2 (2026-09-12) retired the
    one fit that read certificates, so the slot is None by construction
    and no mapping can reach it."""
    import inspect

    inputs = _pooled_inputs()
    lanes = [lane.lane_id for lane in inputs.lanes]
    key = field2._pooled_memo_key(inputs, "Y", 0, field2.ANCHORS_FURNITURE,
                                  lanes, 200, 5, "subtract", 32, 2.0,
                                  "wmedian")
    assert key.token is None and key[-1] is None      # the token slot
    assert "certs" not in inspect.signature(
        field2._pooled_memo_key).parameters
    # and the fit refuses any other anchor set by name
    with pytest.raises(ValueError, match="unknown anchor set"):
        field2.fit_pooled_page_field(inputs, "Y", 0, anchors="certified")


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
    """The family is the FURNITURE pair and nothing else (A2): the
    certificate-anchored `field2c` arms and the `everything+field2`
    profile that carried them retired on 2026-09-12."""
    from analyzer.types import PROFILES
    assert set(arms.FIELD2_ARMS) == {"field2", "field2+offset"}
    for name in arms.FIELD2_ARMS:
        assert name in arms.REGISTER_ARMS
        assert arms.FIELD2_ARMS[name] == field2.ANCHORS_FURNITURE
    assert not any("field2c" in name for name in arms.REGISTER_ARMS)
    with pytest.raises(arms.ArmError):
        arms.parse_arm("subtract+field2c+offset")
    assert "everything+field2" not in PROFILES
    everything = PROFILES["everything"]["arms"]
    assert "subtract+field2+offset" in everything
    assert "head+field2+offset" in everything
    for profile in ("everything", "everything+patch"):
        for arm in PROFILES[profile]["arms"]:
            arms.parse_arm(arm)                    # raises if it does not
            assert "field2c" not in arm


# ------------------------------- the rules that are field2's own (A2)

#: The per-tile scale the null is written against: the offset search's
#: own grid step, which is also the scale at which two lanes of one sheet
#: were measured to disagree (sd 0.28-0.38 dots on a winner).  A field
#: fitted from structureless noise of this size must publish nothing at
#: this size.  Bound to the search, not retyped.
NULL_SCALE_DOTS = float(arms.OFFSET_STEP_DOTS)
assert NULL_SCALE_DOTS == 0.25


def noise_records(tiles, scale=NULL_SCALE_DOTS, *, weight=30.0, seed=17):
    """The same records as `records`, with the PLANT taken out.

    Structureless: every tile's offset is an independent draw, so there
    is no surface to find and no residual to smooth — whatever comes out
    of the fit is what the fit invents.
    """
    rng = np.random.default_rng(seed)
    return tuple(
        field2.TileOffset(
            ty=int(ty), tx=int(tx),
            offset_dots_xy=(float(rng.normal(0.0, scale)),
                            float(rng.normal(0.0, scale))),
            n_labels=int(weight), n_discriminating=20,
            committed_logloss=0.30, search_logloss=0.25, gain=0.05,
            curvature=field2.CURVATURE_SCALE_NATS, weight=float(weight))
        for ty, tx in tiles)


def _pooled_from(records_in, page=0):
    """One `PageField` from one lane's records, the phase-C way."""
    return field2.field_from_pooled(
        field2.by_tile_from({("nullcap", 0): tuple(records_in)}),
        _Inputs(pathlib.Path("/run/null")), [("nullcap", 0)], "Y", 2,
        int(page), field2.ANCHORS_FURNITURE, 5, 32, "subtract")


def _null_statistics(field):
    """What a `phase-C.json` row says about a plane, in three numbers.

    The two `compare.py` scores a field on — the median magnitude over
    supported tiles and the amplitude of the best sinusoid on the column
    profile, fitted with the sweep's own `sinusoid_fit`, which is the
    definition the product reports — plus the bound's own count.
    """
    from analyzer.sweeps.field2_paper import MM_PER_TILE, sinusoid_fit
    live = np.asarray(field.support, np.float64) > 0.0
    magnitude = np.hypot(field.delta_dots_xy[..., 0],
                         field.delta_dots_xy[..., 1])
    # amplitude is in dots and the corpus is c2; only `period_mm` reads
    # the scale, and this predicate does not look at it
    fitted = sinusoid_fit(field2.column_profile(field, axis=0), MM_PER_TILE)
    return {"median_magnitude_dots": float(np.median(magnitude[live])),
            "sinusoid_amplitude_dots": float(fitted["amplitude_dots"] or 0.0),
            "clamped_tiles": int(field.detail["clamped_tiles"])}


def _publishes_nothing(stats, scale=NULL_SCALE_DOTS) -> bool:
    return (stats["median_magnitude_dots"] < scale
            and stats["sinusoid_amplitude_dots"] < scale
            and stats["clamped_tiles"] == 0)


def test_a_structureless_plane_publishes_nothing_above_the_noise_scale():
    """AB4, the null (PAGE-FIELD-PLAN §0).

    One synthetic world, run twice.  With a planted sinusoid the fit
    recovers it (the positive control, at the module's existing
    tolerance); with structureless noise OF THE SAME PER-TILE SCALE it
    must publish nothing at that scale — the surface has nothing to fit
    and the kernel averages i.i.d. draws down, so both the median
    magnitude and the fitted sinusoid stay under the input's own noise,
    and the bound never bites.

    The assertion is DISCRIMINATING by construction: `_publishes_nothing`
    is one predicate and the positive control must FAIL it, which is the
    difference between a null and a test that passes on anything.
    """
    tiles = [(ty, tx) for ty in range(TILES_YX[0])
             for tx in range(TILES_YX[1])]
    control = _pooled_from(records(tiles, noise=NULL_SCALE_DOTS))
    null = _pooled_from(noise_records(tiles))

    control_stats = _null_statistics(control)
    null_stats = _null_statistics(null)

    # the positive control: the plant comes back
    assert abs(control_stats["sinusoid_amplitude_dots"] - AMPLITUDE_DOTS) \
        < 0.12, control_stats
    assert not _publishes_nothing(control_stats), control_stats

    # the null: nothing at the input's own scale
    assert _publishes_nothing(null_stats), null_stats
    assert null_stats["median_magnitude_dots"] \
        < 0.5 * control_stats["median_magnitude_dots"], (null_stats,
                                                         control_stats)
    assert null.detail["clamped_tiles"] == 0
    assert float(field2.summary(null)["median_delta_dots"]) < NULL_SCALE_DOTS


class _SweepRun:
    """The four things the sweep's product header and units read.

    `pitch_in` is what `color_sites.cell_dots_of` reads off a format row
    (c2 = 2/600 in), and it is the whole of F11: a c3 tile is 1.5x as
    wide and `period_mm` has to say so.
    """

    def __init__(self, run_dir: str = "runs/H", cell_dots: int = 2,
                 format_ref: str = FORMAT_REF) -> None:
        self.run_dir = pathlib.Path(run_dir)
        self.format_ref = format_ref
        self.tiles_yx = TILES_YX

        class _Row:
            pitch_in = cell_dots / 600.0
        self.row = _Row()


def _write_phase_c(out_dir: pathlib.Path, fields: list, run) -> pathlib.Path:
    """A phase-C product with the header `phase_c` writes (F10)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "phase-C.json"
    path.write_text(json.dumps({"run_dir": str(run.run_dir),
                                "format_ref": run.format_ref,
                                "fields": fields}), "utf-8")
    return path


def test_the_period_in_mm_is_the_loaded_runs_rung(tmp_path):
    """F11: the sweep's mm/tile comes from the run it loaded.

    `--run-dir`/`--format` let this sweep run on any rung, and the
    module constant is c2's; a 12-tile period is 65.024 mm at c2 and
    97.536 at c3, and reporting the first for a c3 corpus moves a
    physical interpretation by 1.5x while the tile units look right.
    """
    from analyzer.sweeps import field2_paper as sweep

    c2, c3 = _SweepRun(cell_dots=2), _SweepRun(cell_dots=3)
    assert sweep.mm_per_tile_of(c2) == pytest.approx(sweep.MM_PER_TILE)
    assert sweep.mm_per_tile_of(c3) == pytest.approx(1.5 * sweep.MM_PER_TILE)

    profile = np.sin(2 * np.pi * np.arange(36, dtype=np.float64) / 12.0)
    at_c2 = sweep.sinusoid_fit(profile, sweep.mm_per_tile_of(c2))
    at_c3 = sweep.sinusoid_fit(profile, sweep.mm_per_tile_of(c3))
    assert at_c2["period_tiles"] == at_c3["period_tiles"] == 12.0
    assert at_c2["period_mm"] == pytest.approx(65.024)
    assert at_c3["period_mm"] == pytest.approx(97.536)

    # and it is the IN-RUN product's own helper, not a second copy
    from analyzer import passfiles
    assert sweep.mm_per_tile_of(c3) == passfiles._field2_mm_per_tile(c3)


def test_phase_d_reads_the_phase_c_it_was_pointed_at(tmp_path, monkeypatch):
    """F10: the selected product, and never another corpus's.

    Phase D used to call a zero-argument loader that always read the
    module-global `OUT`, so a `--run-dir`/`--out` run silently applied
    the 2026-09-03 sheet-H fields — both sheets of record are 53x37 and
    `evaluate` clamps rather than raises, so nothing downstream would
    have said a word.
    """
    from analyzer.sweeps import field2_paper as sweep

    good = field2.summary(_pooled_from(records(
        [(ty, tx) for ty in range(TILES_YX[0])
         for tx in range(TILES_YX[1])])))
    good["field_dots_xy"] = np.zeros(TILES_YX + (2,)).tolist()
    good["support"] = np.ones(TILES_YX).tolist()
    rows = [{**good, "page": 0, "stream": "C", "plane": 0}]

    mine = _SweepRun(run_dir=str(tmp_path / "H"))
    theirs = _SweepRun(run_dir=str(tmp_path / "J"),
                       format_ref="L:c2-cmy8-r0547@53x37")
    here = _write_phase_c(tmp_path / "out-H", rows, mine)
    there = _write_phase_c(tmp_path / "out-J", rows, theirs)

    assert set(sweep.pooled_fields_from_phase_c(here, mine)) == {(0, "C")}
    with pytest.raises(SystemExit, match="this run is"):
        sweep.pooled_fields_from_phase_c(there, mine)

    # the 2026-09-03 products carry no header at all: refused by default,
    # applied only on the operator's explicit word
    bare = tmp_path / "out-old" / "phase-C.json"
    bare.parent.mkdir()
    bare.write_text(json.dumps({"fields": rows}), "utf-8")
    with pytest.raises(SystemExit, match="allow-unlabelled-phase-c"):
        sweep.pooled_fields_from_phase_c(bare, mine)
    assert set(sweep.pooled_fields_from_phase_c(
        bare, mine, allow_unlabelled=True)) == {(0, "C")}

    # …and phase D itself consumes the path it is given, all the way to
    # the arms' knob table
    seen: dict = {}

    class _Ledger:
        rows: tuple = ()

    def ran(small, targets, config, **kw):
        seen["table"] = config.knobs["page_field2"]
        return _Ledger()

    monkeypatch.setattr(sweep, "chosen_lanes", lambda run, page=0: [])
    monkeypatch.setattr(sweep, "lanes_only", lambda run, lanes: run)
    monkeypatch.setattr(sweep, "residue_sample",
                        lambda rows, stream, n_total: [])
    monkeypatch.setattr(sweep.fp, "run", ran)
    digest = sweep.phase_d(mine, None, [], 1, 1, here)
    assert set(seen["table"]) == {(0, "C")}
    assert set(digest["by_arm"]) == set(sweep.ARMS_D)
    with pytest.raises(SystemExit, match="this run is"):
        sweep.phase_d(mine, None, [], 1, 1, there)
    # main hands D the product dir it was given, not the default — and
    # there is no default left for a library caller to fall into
    assert 'args.out / "phase-C.json"' in inspect.getsource(sweep.main)
    assert inspect.signature(sweep.phase_d).parameters["phase_c_path"] \
        .default is inspect.Parameter.empty


def test_the_phase_c_product_is_one_row_per_page_and_plane(tmp_path,
                                                          monkeypatch):
    """A2: `phase-C.json` covers every live page and every named stream.

    The phase itself needs a run dir and rasters, so what is pinned here
    is its PRODUCT: the schema `measure/page_field/compare.py --analyzer`
    reads (`page`, `stream`, `field_dots_xy`, `support`, `sinusoid_x`),
    the row a refused (page, plane) writes instead of raising or
    vanishing, and the table the D phase rebuilds from it — which must
    key on (page, stream) and must NOT rebuild a refusal as a zero grid,
    because an arm would read that as a measured "no displacement here".
    """
    from analyzer.sweeps import field2_paper as sweep

    refused = sweep._empty_entry(_SweepRun(), 1, "Y", "no_furniture_anchors")
    for name in ("page", "stream", "plane", "field_dots_xy", "support",
                 "sinusoid_x", "fit_refused"):
        assert name in refused, name
    assert np.asarray(refused["support"]).shape == TILES_YX
    assert np.asarray(refused["field_dots_xy"]).shape == TILES_YX + (2,)
    assert not np.any(np.asarray(refused["support"]) > 0.0)

    tiles = [(ty, tx) for ty in range(TILES_YX[0])
             for tx in range(TILES_YX[1])]
    good = field2.summary(_pooled_from(records(tiles)))
    good["field_dots_xy"] = np.zeros(TILES_YX + (2,)).tolist()
    good["support"] = np.ones(TILES_YX).tolist()
    fields = []
    for page in (0, 1):
        for stream in ("C", "M", "Y"):
            if (page, stream) == (1, "Y"):
                fields.append(sweep._empty_entry(_SweepRun(), page, stream,
                                                 "no_lane_on_page"))
                continue
            fields.append({**good, "page": page, "stream": stream,
                           "plane": {"C": 0, "M": 1, "Y": 2}[stream]})
    run = _SweepRun()
    path = _write_phase_c(tmp_path, fields, run)

    table = sweep.pooled_fields_from_phase_c(path, run)
    assert set(table) == {(0, "C"), (0, "M"), (0, "Y"),
                          (1, "C"), (1, "M")}          # the refusal is out
    for (page, stream), rebuilt in table.items():
        assert rebuilt.lane is None and rebuilt.pooled       # page-scope
        assert rebuilt.page == page and rebuilt.stream_id == stream
        assert rebuilt.plane == {"C": 0, "M": 1, "Y": 2}[stream]
        assert rebuilt.lanes == (("nullcap", 0),)


def test_the_bound_is_field2_s_own_and_the_fit_reports_where_it_bit():
    """A2: `BOUND_DOTS` is field2's rule, and it is never silent.

    Past the bound what the grid holds is the degree-<=3 surface
    extrapolating beyond the lanes' coverage, not a registration estimate
    — so the fit bounds it AND says how many tiles it moved, in the same
    report dict the phase-C row is built from.
    """
    assert field2.BOUND_DOTS == field2_kernel.BOUND_DOTS == 2.0
    tiles = [(ty, tx) for ty in range(TILES_YX[0])
             for tx in range(TILES_YX[1])]
    far = tuple(
        field2.TileOffset(
            ty=int(ty), tx=int(tx), offset_dots_xy=(4.0, 3.0),
            n_labels=30, n_discriminating=20, committed_logloss=0.3,
            search_logloss=0.25, gain=0.05,
            curvature=field2.CURVATURE_SCALE_NATS, weight=30.0)
        for ty, tx in tiles)
    delta, _support, _surface, _degree, _rms, _n, n_clamped = \
        field2.build_field(far, TILES_YX)
    assert n_clamped == TILES_YX[0] * TILES_YX[1]
    assert np.allclose(np.hypot(delta[..., 0], delta[..., 1]),
                       field2.BOUND_DOTS)

    field = _pooled_from(far)
    assert field.detail["clamped_tiles"] == n_clamped
    assert field.detail["bound_dots"] == field2.BOUND_DOTS
    row = field2.summary(field)            # the phase-C row's own shape
    assert row["clamped_tiles"] == n_clamped and row["bound_dots"] == 2.0
    # every tile of the grid is read, so every clip is under support
    assert row["clamped_supported_tiles"] == n_clamped

    inside = _pooled_from(records(tiles))
    assert inside.detail["clamped_tiles"] == 0

    # §5.3: the degree ladder counts, and a count is not identifiability.
    # Whole-page coverage identifies the cubic; ONE tile row clears the
    # six-term rule (53 >= 8 x 6) and identifies three of those six.
    assert (row["surface_degree"], row["n_terms"], row["design_rank"]) \
        == (3, 10, 10)
    one_row = field2.summary(_pooled_from(
        records([(4, tx) for tx in range(TILES_YX[1])])))
    assert (one_row["surface_degree"], one_row["n_terms"],
            one_row["design_rank"]) == (2, 6, 3)


def test_the_adopted_kernel_is_the_receiver_s_taps_bit_for_bit():
    """DELETE ME with the receiver's copy (PAGE-FIELD-PLAN A8).

    `field2_kernel` adopted `gaussian_kernel`, `smooth` and `clamp` from
    `holo.receiver.lib.plane_field` verbatim so that the receiver can
    delete names nothing in it reads.  While both exist this pins that
    the adoption really was a copy and not a re-derivation: the taps, the
    smoothing and the bound agree to the bit, at the default bandwidth
    and at another.  When the hand-back lands the import below fails and
    this test goes — it is the only thing here that reaches for the
    receiver's copy.
    """
    from holo.receiver.lib import plane_field as receiver_kernel

    for bandwidth in (field2_kernel.BANDWIDTH_TILES, 3.0):
        mine = field2_kernel.gaussian_kernel(bandwidth)
        theirs = receiver_kernel.gaussian_kernel(bandwidth)
        assert np.array_equal(mine, theirs), bandwidth

    assert field2_kernel.BANDWIDTH_TILES == receiver_kernel.BANDWIDTH_TILES
    assert field2_kernel.KERNEL_TRUNCATION == \
        receiver_kernel.KERNEL_TRUNCATION
    assert field2_kernel.TWICING_PASSES == receiver_kernel.TWICING_PASSES
    assert field2_kernel.BOUND_DOTS == receiver_kernel.MAX_DELTA_DOTS

    rng = np.random.default_rng(20260912)
    grid = rng.normal(0.0, 1.0, TILES_YX)
    kernel = field2_kernel.gaussian_kernel()
    assert np.array_equal(field2_kernel.smooth(grid, kernel),
                          receiver_kernel.smooth(grid, kernel))
    deltas = rng.normal(0.0, 2.0, TILES_YX + (2,))
    assert np.array_equal(field2_kernel.clamp(deltas),
                          receiver_kernel.clamp(deltas))


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


# -------------------------- the comparator's support and ranks (F6)
#
# `measure/page_field/compare.py --analyzer` is the ONE reader of the
# phase-C product above, and until the 2026-09-13 review nothing pinned
# what it does with it.  These are that reader's two corrected rules,
# pinned from this side because the product they score is this one.

def _comparison(tmp_path, mine_delta, mine_support, theirs_delta,
                theirs_support, plane="Y"):
    """One `against_analyzer` row over two grids handed in directly."""
    from measure.page_field import compare

    shape = np.asarray(mine_support).shape
    solved = {"pages": [{"page": 0, "tiles_yx": list(shape), "planes": [{
        "plane_name": plane,
        "delta_dots_xy": np.asarray(mine_delta).tolist(),
        "support": np.asarray(mine_support).tolist(),
        "uncertainty_dots": np.ones(shape).tolist()}]}]}
    path = tmp_path / "phase-C.json"
    path.write_text(json.dumps({"fields": [{
        "page": 0, "stream": plane,
        "field_dots_xy": np.asarray(theirs_delta).tolist(),
        "support": np.asarray(theirs_support).tolist(),
        "sinusoid_x": {"amplitude_dots": 0.3, "period_tiles": 6.7,
                       "r_squared": 1.0}}]}), "utf-8")
    return compare.against_analyzer(solved, path)[0]


def _interacting_field(shape=(8, 12)):
    """A field with a row x column INTERACTION in it.

    The review's stimulus, and the reason it is this and not an additive
    field: `products.column_profile` declares an additive row-plus-column
    model, and for a field that obeys it the profile really is support-
    invariant (measured: +1.0000 own-support under the two disjoint masks
    below).  It is interaction that makes two supports summarise two
    different pages — which sheet J's real fields evidently have.
    """
    ys, xs = np.indices(shape)
    delta = np.zeros(shape + (2,))
    delta[..., 0] = 0.2 * (ys - 3.5) * np.sin(2 * np.pi * xs / 6.7 + 0.137)
    return delta


def test_two_identical_grids_agree_however_their_supports_differ(tmp_path):
    """F6: the profiles are built on the COMMON live tiles.

    Two grids that are equal tile for tile, read under a top mask and a
    bottom mask that overlap on 24 tiles.  Every pointwise number
    already said they agree exactly; the profile correlation was built
    from each side's own support, summarised two different halves of the
    page, and reported −1 — perfect DISagreement between a field and
    itself.
    """
    delta = _interacting_field()
    mine, theirs = np.zeros((8, 12)), np.zeros((8, 12))
    mine[:5] = 1.0
    theirs[3:] = 1.0

    row = _comparison(tmp_path, delta, mine, delta, theirs)
    assert row["n_tiles"] == 24
    assert row["median_abs_dx_dots"] == 0.0
    assert row["median_abs_dy_dots"] == 0.0
    assert row["spearman_x_column_profile"] == pytest.approx(1.0)
    assert row["spearman_x_column_profile_columns"] == 12
    # …and the old number is kept, named for what it is
    assert row["spearman_x_column_profile_own_support"] == pytest.approx(-1.0)


def test_a_column_with_no_common_tile_is_dropped_and_counted(tmp_path):
    """The convention the fix has to NAME, not leave implicit.

    `column_profile` writes zero where a column has no evidence, which
    is honest about the field and wrong as a correlation input: a block
    of shared zeros in both profiles is agreement neither side measured.
    Those columns are dropped, and the count of the ones that survived
    rides in the row so a thin page cannot pass for a full one.
    """
    delta = _interacting_field()
    mine, theirs = np.ones((8, 12)), np.ones((8, 12))
    mine[:, 9:] = 0.0                  # the last three columns share
    theirs[:, :3] = 0.0                # nothing with the first three

    row = _comparison(tmp_path, delta, mine, delta, theirs)
    assert row["spearman_x_column_profile_columns"] == 6
    assert row["spearman_x_column_profile"] == pytest.approx(1.0)


def test_where_support_is_full_the_two_conventions_are_one_number(tmp_path):
    """Sheet H's case, and the cheapest evidence its record never moved.

    Both products carry support on all 1961 tiles there, so common
    support IS own support and the recorded C 0.873 / M 0.659 / Y 0.888
    are invariant to the correction.  A pair that is full on both sides
    must therefore read the same under both keys — here with two
    DIFFERENT fields, so the equality is not the trivial one.
    """
    delta = _interacting_field()
    other = delta + 0.05 * np.cos(np.indices((8, 12))[1])[..., None]
    full = np.ones((8, 12))

    row = _comparison(tmp_path, delta, full, other, full)
    assert row["spearman_x_column_profile_columns"] == 12
    assert row["spearman_x_column_profile"] == pytest.approx(
        row["spearman_x_column_profile_own_support"])
    assert not np.isnan(row["spearman_x_column_profile"])


@pytest.mark.parametrize("left,right,averaged,argsorted", (
    ([0, 0, 0, 1], [0, 1, 1, 1], 1.0 / 3.0, 1.0),
    ([0, 0, 1, 1], [0, 1, 0, 1], 0.0, 0.8),
))
def test_tied_profile_values_get_average_ranks(left, right, averaged,
                                               argsorted):
    """F6's other half: a double `argsort` breaks ties by POSITION.

    Equal values get distinct arbitrary ranks that way, and the answer
    can come out anywhere — 1.0 for a pair whose Spearman is 1/3.  Ties
    reach this comparator through `column_profile`'s zeroed columns, two
    to six per profile on sheet J.  `spearman` itself keeps the old
    definition on purpose: it produced the supervised and per-lane
    numbers of record and no row but this one reads the new function.
    """
    from measure.page_field import compare

    assert compare.spearman_average_ranks(left, right) == \
        pytest.approx(averaged, abs=1e-12)
    assert compare.spearman(left, right) == pytest.approx(argsorted)


def test_a_profile_with_no_variation_still_has_no_ranks(tmp_path):
    """The refusal `spearman` reasons about, kept in the new function."""
    from measure.page_field import compare

    assert np.isnan(compare.spearman_average_ranks(np.zeros(12),
                                                   np.arange(12.0)))
    assert np.isnan(compare.spearman_average_ranks([1.0], [2.0]))
    row = _comparison(tmp_path, np.zeros((8, 12, 2)), np.ones((8, 12)),
                      np.zeros((8, 12, 2)), np.ones((8, 12)))
    assert np.isnan(row["spearman_x_column_profile"])


@pytest.mark.parametrize("module", ("field2", "harmonic"))
def test_field2_names_no_truth_column(module):
    """DESIGN §0's rule below the import set, for the new module.

    That neither module can REACH `truth` or `oracle` is the package-wide
    closure in `test_analyzer_fixedpoint.py`; what is left here is the
    stronger local claim — the source does not so much as name a truth
    column.
    """
    loaded = importlib.import_module(f"analyzer.{module}")
    source = pathlib.Path(loaded.__file__).read_text(encoding="utf-8")
    for forbidden in ("user_bits", "gt_", "payload_sha"):
        assert forbidden not in source, forbidden
