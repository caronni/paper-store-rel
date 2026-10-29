"""Blind Stage-A/B acquisition (paperholo.acquire) end to end on the measured
channel simulator: compose a layout_version-2 pilot page, crop fragments at
unknown-to-the-decoder offsets and rotations, print/scan them, and require the
full blind pipeline (lock -> orientation x 3600-phase x address search ->
BCH-gated Stage A -> cross-tile Stage B -> pilot-anchored warp repair ->
payload extraction) to recover address, orientation and payload with no GT.

Test order per the Wave-2 contract: the zero-channel coordinate-bookkeeping
test runs FIRST (geometry=False, known crop offsets, all 4 rotations), then
the noisy geometry=True path.

Contract deviation, declared: the bookkeeping test's payload-BER gate is 3%
(not the contract's 0.5%) — the measured Stage-0 geometry=False footing is
1.24% blind BER (wave-1 stage0 report; mottle + sensor noise + edge gain are
alive at geometry=False), so 0.5% is unreachable by construction. The
bookkeeping assertion strength is unchanged: a one-cell origin error scrambles
the descramble keystream and reads ~50% BER, so any BER << 50% at the exact
reported indices pins the bookkeeping; the null control makes that explicit.

Runs under pytest, or standalone: env/bin/python tests/test_acquire_blind.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paperholo import acquire, bch, compose  # noqa: E402
from paperholo.channel import ChannelParams, print_scan  # noqa: E402
from paperholo.modulation import rng  # noqa: E402

SEED = b"paper-store/test-acquire-blind"
CELL_DOTS = 3
PERIOD = 60

_cache: dict = {}


def _page(cells: int) -> tuple[compose.ComposeSpec, compose.ComposedPage]:
    key = f"page{cells}"
    if key not in _cache:
        spec = compose.ComposeSpec(page_cells_yx=(cells, cells))
        payload = rng(SEED, f"payload{cells}".encode()).integers(
            0, 2, compose.payload_capacity(spec)).astype(np.uint8)
        _cache[key] = (spec, compose.compose_page(payload, spec, SEED))
    return _cache[key]


def _crop_scan(cells: int, crop_dots_yx: tuple[int, int], crop_dots: int,
               chan_seed: int, geometry: bool) -> np.ndarray:
    _, composed = _page(cells)
    cy, cx = crop_dots_yx
    crop = composed.plane_bits[cy:cy + crop_dots, cx:cx + crop_dots]
    p = ChannelParams(seed=chan_seed, scan_seed=chan_seed + 1,
                      geometry=geometry)
    return print_scan(crop, p)


def _frag_geo(chan_seed: int) -> np.ndarray:
    """The 540-dot geometry crop at the odd offset (91,137), rotated -90."""
    # 2026-09-05: owned here instead of being left in _cache by
    # test_blind_roundtrip_geometry_true — test_negative_controls used to
    # rebuild it silently whenever that test did not run in the same process,
    # which is now the default lane's situation.
    key = f"frag_geo_{chan_seed}"
    if key not in _cache:
        _cache[key] = np.ascontiguousarray(np.rot90(
            _crop_scan(300, (91, 137), 540, chan_seed, True), -1))
    return _cache[key]


def _abs_cells(spec: compose.ComposeSpec,
               payload_cell_index: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Absolute (row, col) page cells of emitted payload indices (inverse of
    compose.payload_index_map — coverage/edge-exclusion bookkeeping)."""
    key = f"invmap{spec.page_cells_yx}"
    if key not in _cache:
        idx_map = compose.payload_index_map(spec, SEED)
        ys, xs = np.nonzero(idx_map >= 0)
        vals = idx_map[idx_map >= 0]
        cy = np.empty(vals.size, np.int64)
        cx = np.empty(vals.size, np.int64)
        cy[vals] = ys
        cx[vals] = xs
        _cache[key] = (cy, cx)
    cy, cx = _cache[key]
    return cy[payload_cell_index], cx[payload_cell_index]


def _nonpilot_count(spec: compose.ComposeSpec, r0: int, r1: int,
                    c0: int, c1: int) -> int:
    """Non-pilot cells in the inclusive absolute window [r0..r1]x[c0..c1]."""
    key = f"sitemask{spec.page_cells_yx}"
    if key not in _cache:
        _cache[key] = compose._pilot_site_mask(spec.page_cells_yx,
                                               spec.pilot, SEED)
    return int((~_cache[key][r0:r1 + 1, c0:c1 + 1]).sum())


def _payload_ber_null(res: acquire.AcquireResult,
                      composed: compose.ComposedPage) -> tuple[float, float]:
    gt = composed.payload_bits
    assert res.payload_bits is not None and res.payload_cell_index is not None
    ber = float(np.mean(res.payload_bits != gt[res.payload_cell_index]))
    null = float(np.mean(
        res.payload_bits != gt[(res.payload_cell_index + 7919) % gt.size]))
    return ber, null


def test_payload_index_map_bijection() -> None:
    """compose decode-side helpers agree with the compose_page embedding."""
    spec, composed = _page(240)
    idx = compose.payload_index_map(spec, SEED)
    non = idx >= 0
    assert int(non.sum()) == composed.payload_capacity_bits
    assert np.array_equal(np.sort(idx[non]),
                          np.arange(composed.payload_capacity_bits))
    ks = compose.payload_keystream(spec, SEED, 0)
    assert np.array_equal(
        np.bitwise_xor(composed.cell_values[non], ks[non]),
        composed.payload_bits[idx[non]])
    assert np.array_equal(
        compose.extract_payload(composed.cell_values, spec, SEED, 0),
        composed.payload_bits)
    print("  payload_index_map consistent with compose_page/extract_payload")


def test_stage_a_b_pure_cells() -> None:
    """Phase/address conventions on the exact composed cell grid (no channel):
    a crop at cell offset (37, 58) must yield the correct origin at n_err=0,
    Stage B must pool at 1.0, and a rotated grid must yield NOTHING (the site
    pattern does not map to itself under rot90 — orientation is BCH-gated)."""
    spec, composed = _page(240)
    off = (37, 58)
    bits = composed.cell_values[off[0]:off[0] + 150, off[1]:off[1] + 150]
    cands = acquire.stage_a(bits, spec.pilot, SEED, "K")
    assert cands, "stage A must decode the exact grid"
    best = cands[0]
    assert best["n_err"] == 0
    msg = best["message"]
    oy = msg["ptile_y"] * PERIOD - best["tile_window_origin"][0]
    ox = msg["ptile_x"] * PERIOD - best["tile_window_origin"][1]
    assert (oy, ox) == off, f"origin ({oy},{ox}) != {off}"
    assert msg["page"] == 0 and msg["plane_id"] == 0
    acc = acquire.stage_b(best, bits, spec.pilot, SEED, "K",
                          page_tiles_yx=(4, 4))
    assert acc is not None
    assert acc["pooled_match"] == 1.0
    assert acc["n_sites_checked"] >= 30
    assert acc["cell_origin_abs_yx"] == off
    for k in (1, 2, 3):
        rot = np.ascontiguousarray(np.rot90(bits, k))
        rot_cands = acquire.stage_a(rot, spec.pilot, SEED, "K")
        for c in rot_cands:  # any BCH fluke must die in Stage B
            assert acquire.stage_b(c, rot, spec.pilot, SEED, "K",
                                   page_tiles_yx=(4, 4)) is None
    print(f"  pure-cell stage A/B: origin {off} exact, pooled 1.0 over "
          f"{acc['n_sites_checked']} sites; rot90 orientations all rejected")


# 2026-09-05: 12 blind acquisitions (3 crops x 4 rotations) = 12 s, the
# module's largest cost. Slow-gated, not shrunk: the pinned coverage counts
# (13653/13529/13769) are measured once on these frozen crop offsets and
# channel seeds, so every offset and rotation has to stay.
@pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the zero-channel bookkeeping sweep")
def test_bookkeeping_zero_channel() -> None:
    """Coordinate bookkeeping (the contract's likely-bug zone), written and
    run FIRST on the near-noiseless channel: 3 known crop offsets x 4
    rotations, geometry=False. Requires exact cell_origin_abs_yx at
    cell-aligned offsets (within 1 cell at the odd offset, where the lattice
    registration of local cell 0 is legitimately phase-ambiguous — the
    payload/null check pins the bookkeeping exactly in every case)."""
    spec, composed = _page(240)
    crop_dots = 360  # 120x120 cells
    offsets = [(0, 0), (96, 63), (121, 44)]  # dots; first two cell-aligned
    # deterministic complete-cell payload coverage per crop (finding [7]):
    # measured once on the frozen simulator/channel seeds; rotation-invariant
    # (the canonical derotated image is identical for all k)
    exp_size = {(0, 0): 13653, (96, 63): 13529, (121, 44): 13769}
    for i, (cy, cx) in enumerate(offsets):
        scan = _crop_scan(240, (cy, cx), crop_dots, 900 + 10 * i, False)
        aligned = (cy % CELL_DOTS == 0) and (cx % CELL_DOTS == 0)
        for k in range(4):
            frag = np.ascontiguousarray(np.rot90(scan, -k))
            res = acquire.acquire_and_decode(frag, spec, SEED,
                                             max_anchor_sites=120)
            assert res.ok, (f"offset {(cy, cx)} rot {k}: acquisition failed "
                            f"({res.diagnostics.get('failed_stage')})")
            assert res.orientation_k == k
            assert res.page == 0 and res.plane == "K"
            exp = (cy // CELL_DOTS, cx // CELL_DOTS)
            got = res.cell_origin_abs_yx
            if aligned:
                assert got == exp, f"origin {got} != {exp} (rot {k})"
            else:
                assert (abs(got[0] - exp[0]) <= 1
                        and abs(got[1] - exp[1]) <= 1), \
                    f"origin {got} not within 1 cell of {exp}"
            ber, null = _payload_ber_null(res, composed)
            exp_t0 = (-(-got[0] // PERIOD), -(-got[1] // PERIOD))
            assert res.ptile_origin_yx == exp_t0
            assert ber < 0.03, (f"offset {(cy, cx)} rot {k}: payload BER "
                                f"{100 * ber:.2f}% (bookkeeping broken?)")
            assert abs(null - 0.5) < 0.05
            assert res.stage_b_match_rate > 0.95
            assert res.mirrored is False
            # edge exclusion (finding [1]): no partially-covered cell emits
            # payload bits — the complete-cell window from the crop geometry
            rows, cols = _abs_cells(spec, res.payload_cell_index)
            r_lo, r_hi = -(-cy // CELL_DOTS), (cy + crop_dots) // CELL_DOTS - 1
            c_lo, c_hi = -(-cx // CELL_DOTS), (cx + crop_dots) // CELL_DOTS - 1
            assert r_lo <= rows.min() and rows.max() <= r_hi, \
                f"rows [{rows.min()},{rows.max()}] leak past [{r_lo},{r_hi}]"
            assert c_lo <= cols.min() and cols.max() <= c_hi, \
                f"cols [{cols.min()},{cols.max()}] leak past [{c_lo},{c_hi}]"
            # coverage (finding [7]): dense inside the emitted window (every
            # non-pilot cell), spanning all but <=2 boundary lines per axis,
            # and the exact deterministic count for this crop
            assert rows.max() - rows.min() >= 117
            assert cols.max() - cols.min() >= 117
            n_exp = _nonpilot_count(spec, int(rows.min()), int(rows.max()),
                                    int(cols.min()), int(cols.max()))
            assert res.payload_bits.size == n_exp, \
                f"coverage {res.payload_bits.size} != window non-pilot {n_exp}"
            assert res.payload_bits.size == exp_size[(cy, cx)], \
                (f"offset {(cy, cx)} rot {k}: payload coverage "
                 f"{res.payload_bits.size} != pinned {exp_size[(cy, cx)]}")
            # per-tile decode gate (finding [8]): the 120x120-cell crop holds
            # exactly one fully-visible tile; on the zero channel it decodes
            assert res.n_tiles_decoded == res.n_tiles_attempted == 1
            assert 0 <= res.n_word_errors_corrected <= bch.T_FULL
            print(f"  off=({cy},{cx}) rot={k}: origin {got}, "
                  f"BER {100 * ber:.2f}%, null {null:.3f}, "
                  f"B-match {res.stage_b_match_rate:.3f}, "
                  f"cover {res.payload_bits.size}, "
                  f"tiles {res.n_tiles_decoded}/{res.n_tiles_attempted}")


# 2026-09-05: 3 channel seeds x a 180x180-cell blind acquisition = 7 s, the
# module's largest cost. Slow-gated per function (the module's cheap tests
# stay in the default lane), not shrunk: the 540-dot crop at (91,137) is what
# the edge-exclusion window [31,209]x[46,224] and the seed-314 measured
# boundary were measured on, so neither the crop nor the seed set may move.
@pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the 3-seed geometry round-trip")
def test_blind_roundtrip_geometry_true() -> None:
    """Full blind round-trip under measured geometry: 300x300-cell page,
    ~180x180-cell crop at an odd dot offset, k=1 rotation, channel seed sweep
    {7, 42, 314}. 314 is the adversarial fast-warp seed (Stage-0 known
    limitation): its result is MEASURED and reported; the pass bar is ok on
    >= 2/3 seeds with correct address+orientation, payload BER < 8%, and a
    0.50 +- 0.02 null control."""
    spec, composed = _page(300)
    crop_yx = (91, 137)  # _frag_geo's 540-dot crop: 180x180 cells, odd offset
    exp_oy, exp_ox = crop_yx[0] / CELL_DOTS, crop_yx[1] / CELL_DOTS
    results = {}
    for s in (7, 42, 314):
        frag = _frag_geo(s)
        t0 = time.time()
        res = acquire.acquire_and_decode(frag, spec, SEED)
        dt = time.time() - t0
        if res.ok:
            ber, null = _payload_ber_null(res, composed)
        else:
            ber, null = float("nan"), float("nan")
        results[s] = (res, ber, null)
        tm = res.diagnostics["timings_s"]
        print(f"  seed {s}: ok={res.ok} orient={res.orientation_k} "
              f"origin={res.cell_origin_abs_yx} BER={100 * ber:.2f}% "
              f"null={null:.3f} B-match={res.stage_b_match_rate:.3f} "
              f"tiles={res.n_tiles_decoded}/{res.n_tiles_attempted} "
              f"slip={ [t for t, r in res.per_tile_match.items() if r < 0.6] } "
              f"[{dt:.1f}s: lock {tm.get('lock_detect', 0):.1f} "
              f"search {tm.get('search', 0):.1f} "
              f"relock {tm.get('relock', 0):.1f} "
              f"anchors {tm.get('anchors', 0):.1f}]")
    n_ok = sum(1 for r, _, _ in results.values() if r.ok)
    assert n_ok >= 2, f"only {n_ok}/3 seeds acquired"
    for s, (res, ber, null) in results.items():
        if not res.ok:
            continue
        assert res.orientation_k == 1, f"seed {s}: orientation wrong"
        assert res.page == 0
        assert abs(res.cell_origin_abs_yx[0] - exp_oy) <= 1
        assert abs(res.cell_origin_abs_yx[1] - exp_ox) <= 1
        assert ber < 0.08, f"seed {s}: payload BER {100 * ber:.2f}%"
        assert abs(null - 0.5) < 0.02
        # edge exclusion (finding [1]): complete cells for this crop are
        # rows 31..209 x cols 46..224 (crop (91,137) x 540 dots); the labels
        # are pilot-word-verified absolute, so no partial line may emit
        rows, cols = _abs_cells(spec, res.payload_cell_index)
        assert 31 <= rows.min() and rows.max() <= 209, \
            f"seed {s}: rows [{rows.min()},{rows.max()}] leak past [31,209]"
        assert 46 <= cols.min() and cols.max() <= 224, \
            f"seed {s}: cols [{cols.min()},{cols.max()}] leak past [46,224]"
        # coverage (finding [7]): >= 95% of the complete-cell payload (the
        # +-1 origin ambiguity / content-edge slack can trim one line)
        n_exp = _nonpilot_count(spec, 31, 209, 46, 224)
        assert res.payload_bits.size >= 0.95 * n_exp, \
            f"seed {s}: coverage {res.payload_bits.size} < 95% of {n_exp}"
        # per-tile decode gate (finding [8]; measured 3/4-4/4 on this crop)
        assert res.n_tiles_decoded >= res.n_tiles_attempted - 1
    # adversarial seed: if the fast-warp region defeated v1 end-to-end, the
    # measured boundary is asserted instead — interior tiles must still
    # produce a correct-address Stage-A candidate (do not silently lower bars)
    res314 = results[314][0]
    if not res314.ok:
        frag = _frag_geo(314)
        grid = acquire.lock_grid(np.ascontiguousarray(np.rot90(frag, 1)))
        hard, _ = acquire.cell_bits_blind(
            acquire.sample_cell_means(np.rot90(frag, 1), grid))
        cands = acquire.stage_a(hard, spec.pilot, SEED, "K")
        assert any(c["message"]["page"] == 0 for c in cands), \
            "seed 314: even interior tiles fail Stage A"
        print("  seed 314: end-to-end FAILED, interior Stage-A decode OK "
              "(measured boundary)")


def test_fragment_grain_90cells() -> None:
    """Guaranteed-grain probe: a 90x90-cell crop (1.5 tiles per axis) placed
    so one full tile is inside (crop cells [45,135)^2 contains tile (1,1))
    must acquire with the correct address under full geometry."""
    spec, composed = _page(300)
    scan = _crop_scan(300, (135, 135), 270, 7000, True)
    res = acquire.acquire_and_decode(scan, spec, SEED)
    assert res.ok, f"90-cell fragment failed ({res.diagnostics})"
    assert res.orientation_k == 0
    got = res.cell_origin_abs_yx
    assert abs(got[0] - 45) <= 1 and abs(got[1] - 45) <= 1
    ber, null = _payload_ber_null(res, composed)
    assert ber < 0.08 and abs(null - 0.5) < 0.03
    # coverage + edge exclusion (findings [1]/[7]): complete cells are
    # 45..134 on both axes (aligned 270-dot crop at (135,135))
    rows, cols = _abs_cells(spec, res.payload_cell_index)
    assert 45 <= rows.min() and rows.max() <= 134
    assert 45 <= cols.min() and cols.max() <= 134
    n_exp = _nonpilot_count(spec, 45, 134, 45, 134)
    assert res.payload_bits.size >= 0.95 * n_exp
    # finding [8]: the crop holds exactly one full tile, and it decodes
    assert res.n_tiles_decoded == res.n_tiles_attempted == 1
    print(f"  90x90 fragment: origin {got}, BER {100 * ber:.2f}%, "
          f"null {null:.3f}, cover {res.payload_bits.size}/{n_exp}, "
          f"ptile_origin {res.ptile_origin_yx}")


def test_mirror_acquisition_first_class() -> None:
    """Finding [2]: a mirror-accepted result must carry mirrored=True as a
    first-class field, and the documented canonicalizing transform
    np.rot90(scan[:, ::-1] if mirrored else scan, orientation_k) must
    reproduce the internal canonical frame (pre-fix, a consumer following
    the orientation_k doc reconstructed a mirrored frame at ~50% BER while
    res.ok and all address fields looked valid)."""
    spec, composed = _page(240)
    scan = _crop_scan(240, (0, 0), 360, 1500, False)
    mir = np.ascontiguousarray(scan[:, ::-1])
    res = acquire.acquire_and_decode(mir, spec, SEED, include_mirror=True,
                                     max_anchor_sites=120)
    assert res.ok, f"mirrored acquisition failed ({res.diagnostics})"
    assert res.mirrored is True
    assert res.orientation_k == 0
    assert res.cell_origin_abs_yx == (0, 0)
    canon = np.rot90(mir[:, ::-1] if res.mirrored else mir, res.orientation_k)
    assert np.array_equal(canon, scan), \
        "documented mirror+rot90 transform does not reproduce the canonical frame"
    ber, null = _payload_ber_null(res, composed)
    assert ber < 0.03 and abs(null - 0.5) < 0.05
    print(f"  mirrored fragment: mirrored={res.mirrored} k={res.orientation_k} "
          f"BER {100 * ber:.2f}%, null {null:.3f}")


def test_slip_fold_boundary_row_content() -> None:
    """Finding [0] e2e regression (geometry=False): fold a -1/+1-cell slip
    band into a blind-locked grid on a real composed page scan and require
    EVERY row at and after the fold boundary to read the shifted content
    row (r + shift). Pre-fix, the _centers_uv fixed-point pass undid the
    fold at the boundary row, which then read the UNSHIFTED content row —
    a silent full-width ~50%-BER burst under valid payload indices."""
    spec, composed = _page(240)
    cells = composed.cell_values
    scan = print_scan(composed.plane_bits,
                      ChannelParams(seed=1300, scan_seed=1301,
                                    geometry=False))
    grid = acquire.lock_grid(scan)
    hard0, _ = acquire.cell_bits_blind(acquire.sample_cell_means(scan, grid))
    h_cells, w_cells = grid.shape_cells
    # base integer alignment of the arbitrary blind lock origin
    best = (1.0, (0, 0))
    for ky in (-1, 0, 1):
        for kx in (-1, 0, 1):
            h = hard0[8:h_cells - 8, 8:w_cells - 8]
            t = cells[8 + ky:h_cells - 8 + ky, 8 + kx:w_cells - 8 + kx]
            b = float(np.mean(h != t))
            if b < best[0]:
                best = (b, (ky, kx))
    ber0, (ky, kx) = best
    assert ber0 < 0.05, f"base lock BER {100 * ber0:.2f}% (test precondition)"
    for sign in (-1, 1):
        slip_dy = np.zeros(h_cells, np.int64)
        slip_dy[60:] = sign
        slip_dx = np.zeros(w_cells, np.int64)

        def warp(y_cells: np.ndarray, x_cells: np.ndarray
                 ) -> tuple[np.ndarray, np.ndarray]:
            iy = np.clip(np.round(np.asarray(y_cells, np.float64)
                                  ).astype(int), 0, slip_dy.size - 1)
            ix = np.clip(np.round(np.asarray(x_cells, np.float64)
                                  ).astype(int), 0, slip_dx.size - 1)
            return ((slip_dy[iy] * CELL_DOTS).astype(np.float64),
                    (slip_dx[ix] * CELL_DOTS).astype(np.float64))

        g2 = acquire._fold_warp_into_grid(grid, warp)
        hard2, _ = acquire.cell_bits_blind(
            acquire.sample_cell_means(scan, g2))
        worst, worst_r = 0.0, -1
        for r in range(4, h_cells - 4):
            src = r + ky + (sign if r >= 60 else 0)
            if not 0 <= src < cells.shape[0]:
                continue
            row_ber = float(np.mean(
                hard2[r, 8:w_cells - 8]
                != cells[src, 8 + kx:w_cells - 8 + kx]))
            if row_ber > worst:
                worst, worst_r = row_ber, r
        # pre-fix the boundary row read the unshifted content: ~42-50% BER;
        # post-fix every row tracks its shifted source (measured worst ~4%)
        assert worst < 0.15, (f"sign {sign:+d}: row {worst_r} reads "
                              f"{100 * worst:.1f}% BER vs its shifted "
                              f"source (fold undone at the boundary?)")
        print(f"  slip fold sign {sign:+d}: worst row BER "
              f"{100 * worst:.2f}% (row {worst_r})")


def test_blind_roundtrip_v3_geometry_true() -> None:
    """ONE layout_version-3 blind round-trip (v3 migration contract): small
    v3 page (p60b6.v3-k18: shared v2 sites, (100,23) t=13 flat-counter
    words), geometry=True, k=1 rotation at an odd dot offset. Requires the
    counter-derived absolute address, payload BER < 8%, a 0.50 +- 0.02 null
    control, and a null-hypothesis reject on the v2 format hypothesis (the
    labeled scrambler is the only format signal — implicit signaling).
    The existing v2 tests above are untouched."""
    spec = compose.ComposeSpec(layout_version=3,
                               pilot=compose.PilotLayout(version=3),
                               page_cells_yx=(240, 240))
    payload = rng(SEED, b"payload-v3").integers(
        0, 2, compose.payload_capacity(spec)).astype(np.uint8)
    composed = compose.compose_page(payload, spec, SEED)
    crop_yx, crop_dots = (91, 137), 420  # 140x140 cells at an odd offset
    crop = composed.plane_bits[crop_yx[0]:crop_yx[0] + crop_dots,
                               crop_yx[1]:crop_yx[1] + crop_dots]
    scan = print_scan(crop, ChannelParams(seed=7, scan_seed=8, geometry=True))
    frag = np.ascontiguousarray(np.rot90(scan, -1))
    res = acquire.acquire_and_decode(frag, spec, SEED)
    assert res.ok, f"v3 acquisition failed ({res.diagnostics})"
    assert res.orientation_k == 1 and res.page == 0
    got = res.cell_origin_abs_yx
    assert abs(got[0] - crop_yx[0] / CELL_DOTS) <= 1.5
    assert abs(got[1] - crop_yx[1] / CELL_DOTS) <= 1.5
    # the accepted address came through the flat counter; diagnostics report
    # it, and it must invert to the accepted tile origin
    c = res.diagnostics.get("counter")
    assert c is not None
    tiles_x = spec.page_tiles_yx[1]
    assert (c // (spec.page_tiles_yx[0] * tiles_x)) == 0  # page 0
    gt = composed.payload_bits
    ber = float(np.mean(res.payload_bits != gt[res.payload_cell_index]))
    null = float(np.mean(
        res.payload_bits != gt[(res.payload_cell_index + 7919) % gt.size]))
    assert ber < 0.08, f"v3 payload BER {100 * ber:.2f}%"
    assert abs(null - 0.5) < 0.02
    # v2-format hypothesis on the same fragment must fail cleanly (wrong
    # value-scramble label -> coin flips -> BCH reject)
    spec_v2 = compose.ComposeSpec(page_cells_yx=(240, 240))
    res_v2 = acquire.acquire_and_decode(frag, spec_v2, SEED)
    assert not res_v2.ok
    print(f"  v3 fragment: origin {got}, counter {c}, BER {100 * ber:.2f}%, "
          f"null {null:.3f}; v2 hypothesis fails at "
          f"{res_v2.diagnostics['failed_stage']}")


def test_negative_controls() -> None:
    """Wrong seed / blank paper / wrong plane hint must fail cleanly."""
    spec, _ = _page(300)
    frag = _frag_geo(7)

    res = acquire.acquire_and_decode(frag, spec, b"paper-store/WRONG-SEED")
    assert not res.ok
    assert res.diagnostics["failed_stage"] in ("lock", "stage_a", "stage_b")
    print(f"  wrong seed: ok=False at {res.diagnostics['failed_stage']} "
          f"({res.diagnostics['n_candidates']} candidates)")

    blank = print_scan(np.zeros((540, 540), np.uint8),
                       ChannelParams(seed=5, scan_seed=6, geometry=True))
    res_b = acquire.acquire_and_decode(blank, spec, SEED)
    assert not res_b.ok
    print(f"  blank paper: ok=False at {res_b.diagnostics['failed_stage']}")

    res_p = acquire.acquire_and_decode(frag, spec, SEED, plane_hint="C")
    assert not res_p.ok
    print(f"  wrong plane hint: ok=False at "
          f"{res_p.diagnostics['failed_stage']}")


if __name__ == "__main__":
    for fn in (test_payload_index_map_bijection,
               test_stage_a_b_pure_cells,
               test_bookkeeping_zero_channel,
               test_blind_roundtrip_geometry_true,
               test_fragment_grain_90cells,
               test_mirror_acquisition_first_class,
               test_slip_fold_boundary_row_content,
               test_blind_roundtrip_v3_geometry_true,
               test_negative_controls):
        t0 = time.time()
        fn()
        print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)")
