"""COLOR CHANNEL decode axis (layout_version 4, IMPL-3) — receiver gates.

Covers, per the COLOR-DESIGN D4/D5 receiver contract:
- scannorm.normalize_to_canonical_rgb: SAME rational resample as the luma
  footing, per-channel honest reduction, frame-agreement guard.
- acquire.fit_qda / qda_level_llrs: full-covariance QDA with the documented
  shrinkage rule; degenerate-class and collapsed-pair guards (warn + clip,
  never crash); level-LLR signs.
- acquire._fit_offset_model: global + linear-in-y recovery, small-sample and
  small-span fallbacks (D5 v1 model shape).
- acquire_and_decode(rgb=...): fully blind end-to-end on SIM-FREE synthetic
  RGB (known planes + known per-plane offsets + gaussian noise): per-level
  payload aligns with compose GT; per-plane offsets recovered as PAIRWISE
  differences (the luma lock absorbs any common shift — differences are the
  invariant, COLOR-DESIGN P4's own report shape); guards (rgb on K spec,
  shape mismatch, grey color page -> pending); wrong-seed clean reject.
- tilemap level-aware map: (tile, level) keys, per-level rate rungs,
  per-level F9 overlays/known values, color extend/dedup, K guards.
- formats: blind identification + RGB threading (acquire_scan on a crop,
  page_decode whole-scan) -> per-level LDPC certify -> fountain
  volume_decode BYTE-EXACT — the receiver half of the D-plan's
  "clean-channel coded round-trip, fully blind" gate.

SIM-FREE by contract: RGB windows are constructed here from the composed
plane bitmaps with a subtractive crosstalk mix + gaussian noise + injected
per-plane offsets — no channel simulator in the loop (its known c2/closure
gaps must not gate the color receiver; the M0 color fold-in is IMPL-2's).

Runs under pytest, or standalone: env/bin/python tests/test_color_receiver.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from paperholo import acquire, compose, dust, formats, fountain, ldpc, \
    pilots, scannorm, tilemap  # noqa: E402
from paperholo.modulation import rng  # noqa: E402

# 2026-09-05: slow-lane gate (the tests/test_e025.py convention). A MARK,
# not an in-body skip: the module's standalone runner below calls every
# test_* directly, and a mark is inert on a direct call.
_SLOW = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the K-registry hypothesis sweep")

SEED = b"paper-store/test-color-receiver"
DUST = dust.DustLayout(sites_per_tile=24, pure_quota=3)
RATES = ("r0550", "r0700", "r0625")           # per-level rungs (C, M, Y)
# injected per-plane offsets, DOTS: (dy_global, dy_slope, dx_global, dx_slope)
# — slope terms are per unit page-y fraction (the D5 model shape). M is the
# zero reference; assertions are PAIRWISE differences vs M (the luma lock
# absorbs any common component; differences are invariant to it).
OFFSETS_DOTS = {
    0: (0.6, 0.0, -1.0, 0.0),                 # C: global dy + global dx
    1: (0.0, 0.0, 0.0, 0.0),                  # M: reference
    2: (-0.4, -0.8, 0.5, 0.0),                # Y: linear-in-y dy drift
}
# subtractive channel mix (rows R,G,B x cols C,M,Y ink): dominant own-plane
# absorption + mild crosstalk — CAL-1-shaped, numbers uncalibrated (SIM-FREE
# synthetic; only separability + coupling structure matter here)
MIX = np.array([[0.75, 0.12, 0.06],
                [0.10, 0.75, 0.08],
                [0.06, 0.10, 0.70]])
NOISE_SIGMA = 0.02

_cache: dict = {}


def _spec(cells: int) -> compose.ComposeSpec:
    return compose.ComposeSpec(
        layout_version=4, encoding_id="cmy8-c3", plane="CMY",
        pilot=pilots.PilotLayout(version=4), page_cells_yx=(cells, cells),
        dust=DUST)


def _render_rgb(plane_bits: np.ndarray, offsets: dict, noise_sigma: float,
                noise_label: bytes) -> np.ndarray:
    """(3, Hd, Wd) dot bitmaps -> (H, W, 3) float RGB at 2 px/dot with
    injected per-plane offsets (positive = content displaced +y/+x, the
    measure_pilot_anchors sign) + gaussian sensor noise."""
    h_px, w_px = plane_bits.shape[1] * 2, plane_bits.shape[2] * 2
    yy = np.arange(h_px, dtype=np.float64)[:, None]
    xx = np.arange(w_px, dtype=np.float64)[None, :]
    inks = []
    for lv in range(3):
        ink = np.kron(plane_bits[lv].astype(np.float64), np.ones((2, 2)))
        dy_a, dy_b, dx_a, dx_b = offsets[lv]
        yf = yy / h_px
        dy_px = (dy_a + dy_b * yf) * 2.0      # dots -> px at 2 px/dot
        dx_px = (dx_a + dx_b * yf) * 2.0
        if dy_a or dy_b or dx_a or dx_b:
            ink = ndimage.map_coordinates(
                ink, [np.broadcast_to(yy - dy_px, (h_px, w_px)),
                      np.broadcast_to(xx - dx_px, (h_px, w_px))],
                order=1, mode="nearest")
        inks.append(ink)
    g = rng(SEED, b"render-noise/" + noise_label)
    rgb = np.empty((h_px, w_px, 3))
    for c in range(3):
        clean = 1.0 - (MIX[c, 0] * inks[0] + MIX[c, 1] * inks[1]
                       + MIX[c, 2] * inks[2])
        rgb[..., c] = np.clip(
            clean + g.standard_normal((h_px, w_px)) * noise_sigma, 0.0, 1.0)
    return rgb


def _random_page(cells: int) -> tuple:
    """(spec, composed, rgb) for an unframed random-payload page."""
    key = f"page{cells}"
    if key not in _cache:
        spec = _spec(cells)
        cap = compose.payload_capacity(spec)
        g = rng(SEED, b"payload")
        payload = [g.integers(0, 2, cap, dtype=np.uint8) for _ in range(3)]
        cp = compose.compose_page(payload, spec, SEED, page=0)
        rgb = _render_rgb(cp.plane_bits, OFFSETS_DOTS, NOISE_SIGMA, b"e2e")
        _cache[key] = (spec, cp, rgb)
    return _cache[key]


def _e2e_result(cells: int = 240):
    """One full blind color acquire on the random page (cached)."""
    key = f"res{cells}"
    if key not in _cache:
        spec, cp, rgb = _random_page(cells)
        res = acquire.acquire_and_decode(rgb.mean(axis=2), spec, SEED,
                                         rgb=rgb, calibrate=True)
        _cache[key] = res
    return _cache[key]


# ---------------------------------------------------------------------------
# scannorm RGB companion
# ---------------------------------------------------------------------------

def test_normalize_to_canonical_rgb_same_resample() -> None:
    g = rng(SEED, b"rgbnorm")
    rgb = g.integers(0, 256, (240, 252, 3), dtype=np.uint8)
    luma = scannorm.reduce_plane(rgb, "CMY")           # -> luma fallback
    # pitch 12 px/cell -> 1/2 box resample onto the 6 px footing
    norm = scannorm.normalize_to_canonical(luma, 12.0, 3)
    assert (norm.scale_num, norm.scale_den) == (1, 2)
    out = scannorm.normalize_to_canonical_rgb(rgb, norm)
    assert out.shape == norm.img.shape + (3,)
    for lv, pl in enumerate("CMY"):
        ch = scannorm.reduce_plane(rgb, pl)
        expect = scannorm._box_resample(ch, 1, 2)
        assert np.allclose(out[..., lv], expect), pl
    # no-op footing keeps the frame
    norm1 = scannorm.normalize_to_canonical(luma, 6.0, 3)
    assert (norm1.scale_num, norm1.scale_den) == (1, 1)
    out1 = scannorm.normalize_to_canonical_rgb(rgb, norm1)
    assert out1.shape == (240, 252, 3)
    assert np.allclose(out1[..., 0], scannorm.reduce_plane(rgb, "C"))
    # guards: 2-D input refused; frame mismatch refused
    try:
        scannorm.normalize_to_canonical_rgb(luma, norm1)
        raise AssertionError("2-D input accepted")
    except ValueError:
        pass
    try:
        scannorm.normalize_to_canonical_rgb(rgb[:120], norm1)
        raise AssertionError("mismatched frame accepted")
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# QDA detector unit gates (pure feature space, no images)
# ---------------------------------------------------------------------------

def _clouds(n_per: int, sigma: float, drop: set[int] = frozenset(),
            merge: tuple[int, int] | None = None
            ) -> tuple[np.ndarray, np.ndarray]:
    mu = np.array([[(s >> lv) & 1 for lv in range(3)] for s in range(8)],
                  np.float64)
    if merge is not None:
        mu[merge[1]] = mu[merge[0]]           # collapse pair (starved plane)
    g = rng(SEED, b"clouds%d" % n_per)
    xs, ys = [], []
    for s in range(8):
        if s in drop:
            continue
        xs.append(mu[s] + g.standard_normal((n_per, 3)) * sigma)
        ys.append(np.full(n_per, s, np.int64))
    return np.concatenate(xs), np.concatenate(ys)


def test_qda_llr_signs_and_accuracy() -> None:
    x, y = _clouds(80, 0.08)
    model = acquire.fit_qda(x, y)
    assert not model["degenerate"] and not model["clip_levels"]
    llr = acquire.qda_level_llrs(model, x)
    truth = np.stack([(y >> lv) & 1 for lv in range(3)])
    assert ((llr > 0).astype(int) == truth).mean() > 0.999
    # confident cells carry large |LLR| (log-marginal ratio, not a floor)
    assert np.median(np.abs(llr)) > 10.0


def test_qda_shrinkage_small_class() -> None:
    # class 5 has 4 labels (< d+2 would be <5): full shrink to pooled, warn
    x, y = _clouds(60, 0.08)
    keep = np.ones(y.size, bool)
    keep[np.flatnonzero(y == 5)[4:]] = False
    model = acquire.fit_qda(x[keep], y[keep])
    assert any("class 5" in w and "shrunk" in w for w in model["warnings"])
    llr = acquire.qda_level_llrs(model, x)
    truth = np.stack([(y >> lv) & 1 for lv in range(3)])
    assert ((llr > 0).astype(int) == truth).mean() > 0.99


def test_qda_degenerate_and_collapsed_guards() -> None:
    # missing class: warn + degenerate + ALL levels clipped, no crash
    x, y = _clouds(60, 0.08, drop={6})
    model = acquire.fit_qda(x, y)
    assert model["degenerate"]
    assert any("class 6" in w for w in model["warnings"])
    llr = acquire.qda_level_llrs(model, x)
    assert float(np.abs(llr).max()) <= acquire.COLOR_LLR_FLOOR + 1e-9
    # collapsed pair 3/7 (differ in bit 2 = Y): level 2 clipped, 0/1 not
    x2, y2 = _clouds(60, 0.05, merge=(3, 7))
    m2 = acquire.fit_qda(x2, y2)
    assert 2 in m2["clip_levels"] and not {0, 1} & m2["clip_levels"]
    assert any("collapsed" in w for w in m2["warnings"])
    llr2 = acquire.qda_level_llrs(m2, x2)
    assert float(np.abs(llr2[2]).max()) <= acquire.COLOR_LLR_FLOOR + 1e-9
    assert float(np.abs(llr2[0]).max()) > acquire.COLOR_LLR_FLOOR


def test_offset_model_fit_and_fallbacks() -> None:
    g = rng(SEED, b"offsets")
    yf = g.random(64)
    vals = 0.7 - 1.2 * yf + g.standard_normal(64) * 0.05
    a, b, n = acquire._fit_offset_model(yf, vals, np.ones(64))
    assert n == 64 and abs(a - 0.7) < 0.1 and abs(b + 1.2) < 0.2
    # too few anchors -> zero model
    a0, b0, n0 = acquire._fit_offset_model(yf[:5], vals[:5], np.ones(5))
    assert (a0, b0) == (0.0, 0.0) and n0 == 5
    # tiny y-span -> slope dropped, global kept (weighted mean)
    yf_c = np.full(32, 0.5) + g.random(32) * 0.01
    vals_c = 0.3 + g.standard_normal(32) * 0.02
    a1, b1, _ = acquire._fit_offset_model(yf_c, vals_c, np.ones(32))
    assert b1 == 0.0 and abs(a1 - 0.3) < 0.05
    # NaN anchors (failed NCC sites) are ignored
    vals_nan = vals.copy()
    vals_nan[::3] = np.nan
    a2, b2, n2 = acquire._fit_offset_model(yf, vals_nan, np.ones(64))
    assert n2 == 64 - len(vals_nan[::3]) and abs(a2 - 0.7) < 0.15


# ---------------------------------------------------------------------------
# blind end-to-end on synthetic RGB (the D4/D5 receiver gate)
# ---------------------------------------------------------------------------

def test_color_acquire_end_to_end() -> None:
    spec, cp, rgb = _random_page(240)
    res = _e2e_result(240)
    assert res.ok, res.diagnostics
    assert res.page == 0 and res.orientation_k == 0
    assert isinstance(res.payload_bits, list) and len(res.payload_bits) == 3
    assert isinstance(res.payload_llr, list) and len(res.payload_llr) == 3
    idx = res.payload_cell_index
    assert idx.size > 0.9 * compose.payload_capacity(spec)
    for lv in range(3):
        gt = cp.payload_bits[lv][idx]
        ber = float((res.payload_bits[lv] != gt).mean())
        assert ber < 0.005, f"level {lv} BER {ber:.4f}"
        # house sign: bits == (llr > 0)
        assert np.array_equal(res.payload_bits[lv],
                              (res.payload_llr[lv] > 0).astype(np.uint8))
    cdiag = res.diagnostics["color"]
    assert cdiag["n_dust_labels"] >= 300          # 16 tiles x 24 sites, gated
    assert cdiag["calibrated_levels"] == [0, 1, 2]
    assert not cdiag["qda_degenerate"]


def test_color_offsets_recovered_pairwise() -> None:
    res = _e2e_result(240)
    fits = {f["plane"]: f for f in res.diagnostics["color"]
            ["plane_offsets_dots"]}
    for pl in "CMY":
        assert fits[pl]["n_anchors"] >= acquire.COLOR_ANCHOR_MIN, pl
    # pairwise vs the M reference (common-mode absorbed by the luma lock)
    for pl, lv in (("C", 0), ("Y", 2)):
        inj = OFFSETS_DOTS[lv]
        d_dy = fits[pl]["dy"][0] - fits["M"]["dy"][0]
        d_dx = fits[pl]["dx"][0] - fits["M"]["dx"][0]
        # the fitted global term at slope!=0 is the y=0 intercept
        assert abs(d_dy - inj[0]) < 0.35, (pl, "dy", d_dy)
        assert abs(d_dx - inj[2]) < 0.35, (pl, "dx", d_dx)
    d_slope = fits["Y"]["dy"][1] - fits["M"]["dy"][1]
    assert abs(d_slope - OFFSETS_DOTS[2][1]) < 0.5, d_slope


def test_color_acquire_guards() -> None:
    spec, cp, rgb = _random_page(240)
    luma = rgb.mean(axis=2)
    # rgb on a K spec refused
    k_spec = compose.ComposeSpec(layout_version=3,
                                 pilot=pilots.PilotLayout(version=3))
    try:
        acquire.acquire_and_decode(luma, k_spec, SEED, rgb=rgb)
        raise AssertionError("rgb accepted on a K spec")
    except ValueError:
        pass
    # frame mismatch refused
    try:
        acquire.acquire_and_decode(luma, spec, SEED, rgb=rgb[:100])
        raise AssertionError("mismatched rgb frame accepted")
    except ValueError:
        pass
    try:
        acquire.acquire_and_decode(luma, spec, SEED, rgb=rgb,
                                   color_features="hsv")
        raise AssertionError("unknown color_features accepted")
    except ValueError:
        pass
    # grey scan of a color page: addresses fine, payload pending
    # 2026-09-05: 600 px (100 cells), was 900 — every assertion here is a
    # boolean guard and all of them hold on the smaller crop (measured:
    # 2.3 + 12.2 s at 900 px, 1.3 + 2.5 s at 600). Do not go lower: blind
    # identification stops working below 600 px on this page, and this is
    # the default lane's only acquire-level wrong-seed reject.
    crop = np.ascontiguousarray(luma[300:900, 300:900])
    res = acquire.acquire_and_decode(crop, spec, SEED)
    assert res.ok
    assert res.diagnostics.get("color_payload_pending") is True
    assert res.payload_cell_index.size == 0
    # wrong seed: clean reject (sites + values re-key)
    res_bad = acquire.acquire_and_decode(crop, spec, b"not-the-seed")
    assert not res_bad.ok


# ---------------------------------------------------------------------------
# tilemap level-aware map (unit level, no acquisition)
# ---------------------------------------------------------------------------

def _framed_state() -> tuple:
    key = "framed120"
    if key not in _cache:
        spec = _spec(120)
        specs = [ldpc.LDPC_LADDER[r] for r in RATES]
        caps = [ldpc.page_user_capacity(spec, SEED, s) for s in specs]
        users = [rng(SEED, b"user%d" % lv).integers(0, 2, c, dtype=np.uint8)
                 for lv, c in enumerate(caps)]
        enc = ldpc.encode_page(users, spec, SEED, specs)
        _cache[key] = (spec, users, enc)
    return _cache[key]


def _fake_result(enc: dict):
    cap = enc["payload_bits"][0].size
    llrs = [np.where(pb == 1, 8.0, -8.0) for pb in enc["payload_bits"]]
    return acquire.AcquireResult(
        ok=True, orientation_k=0, mirrored=False, page=0, plane="K",
        payload_bits=[pb.copy() for pb in enc["payload_bits"]],
        payload_cell_index=np.arange(cap, dtype=np.int64),
        payload_llr=llrs,
        tile_words={(ty, tx): 0 for ty in range(2) for tx in range(2)})


def test_tilemap_color_decode_and_exports() -> None:
    spec, users, enc = _framed_state()
    state = tilemap.PageDecodeState(spec, SEED, page=0)
    assert state.n_levels == 3
    assert len(state.tiles) == 4 * 3            # 2x2 LDPC tiles x 3 levels
    state.add_acquire_result("A", _fake_result(enc))
    state.note_scan_added()
    counts = state.decode_tiles(RATES)
    assert counts["certified"] == 12, counts
    # per-level user bits reassemble exactly (tile raster order per level)
    for lv in range(3):
        got = np.concatenate(
            [state.tiles[(t, lv)].payload_bits
             for t in ldpc.tile_grid(spec.page_cells_yx)])
        assert np.array_equal(got, users[lv]), f"level {lv}"
        assert all(state.tiles[(t, lv)].rate_id == RATES[lv]
                   for t in ldpc.tile_grid(spec.page_cells_yx))
    # certified_results: (page, level, TileResult) triples
    trips = list(state.certified_results())
    assert len(trips) == 12
    assert {t[1] for t in trips} == {0, 1, 2}
    # F9 overlays are per level; known values match the printed cell grid
    cp = compose.compose_page(enc["payload_bits"], spec, SEED, page=0)
    for lv in range(3):
        ci, cl = state.certified_payload_llrs(level=lv)
        assert ci.size and np.all(np.isinf(cl))
        y, x, bits = state.known_cell_values(level=lv)
        assert np.array_equal(bits, cp.cell_values[lv][y, x]), f"level {lv}"
    try:
        state.certified_payload_llrs()
        raise AssertionError("color overlay served without a level")
    except ValueError:
        pass
    # placed fragments are K-only (F13 v1 scope)
    try:
        state.add_placed_fragment("A/frag", np.arange(4), np.zeros(4))
        raise AssertionError("color placed fragment accepted")
    except ValueError:
        pass
    # F6 loop runs on color states
    useful, reason = state.more_scans_useful()
    assert useful in (False, True) and isinstance(reason, str)


def test_tilemap_color_guards_and_extend() -> None:
    spec, users, enc = _framed_state()
    state = tilemap.PageDecodeState(spec, SEED, page=0)
    state.add_acquire_result("A", _fake_result(enc))
    # rate arity guards both ways
    try:
        state.decode_tiles("r0550")
        raise AssertionError("single rate accepted on a color page")
    except ValueError:
        pass
    k_state = tilemap.PageDecodeState(compose.ComposeSpec(
        layout_version=3, pilot=pilots.PilotLayout(version=3)), SEED)
    try:
        k_state.decode_tiles(RATES)
        raise AssertionError("rate list accepted on a K page")
    except ValueError:
        pass
    # color extend: overlap dedup keeps the higher mean-|LLR| observation
    obs = state.scans["A"]
    n0 = obs.payload_cell_index.size
    idx = obs.payload_cell_index[:10]
    strong = np.full((3, 10), 50.0)
    obs.extend(idx, strong, {})
    assert obs.payload_cell_index.size == n0     # no new cells
    order = np.searchsorted(obs.payload_cell_index, idx)
    assert np.allclose(obs.payload_llr[:, order], strong)
    # a color result into a K state refuses (shape contract)
    try:
        k_state.add_acquire_result("A", _fake_result(enc))
        raise AssertionError("color result accepted into a K map")
    except (ValueError, IndexError):
        pass


# ---------------------------------------------------------------------------
# formats threading + the fully blind coded round-trip (fountain byte-exact)
# ---------------------------------------------------------------------------

def _coded_volume() -> tuple:
    key = "coded240"
    if key not in _cache:
        spec = _spec(240)
        fd = formats.FormatDescriptor(
            "test-v4-cmy8", SEED, 4, "cmy8-c3", (240, 240), plane="CMY",
            notes="test-local color row", dust=DUST)
        probe = fountain.VolumeSpec(n_pages=1, data_len_bytes=1, seed=SEED,
                                    compose_spec=spec, n_levels=3,
                                    ldpc_rate_ids=RATES)
        cap_bits = sum(probe.source_capacity_bits_level(lv)
                       for lv in range(3))
        data_len = int(0.6 * cap_bits) // 8
        vspec = fountain.VolumeSpec(n_pages=1, data_len_bytes=data_len,
                                    seed=SEED, compose_spec=spec, n_levels=3,
                                    ldpc_rate_ids=RATES)
        data = rng(SEED, b"volume-data").integers(
            0, 256, data_len, dtype=np.uint8).tobytes()
        framed = fountain.encode_volume_pages(data, vspec)
        cp = compose.compose_page(framed[0]["payload_bits"], spec, SEED,
                                  page=0)
        rgb = _render_rgb(cp.plane_bits, OFFSETS_DOTS, NOISE_SIGMA, b"coded")
        rgb_u8 = np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
        _cache[key] = (spec, fd, vspec, data, rgb_u8, cp)
    return _cache[key]


def test_acquire_scan_color_crop() -> None:
    """Blind format identification + RGB threading on an interior crop
    (8-bit RGB in, luma identification, per-level payload out). The crop
    sees only ~6 pilot tiles' dust (< the 300-label PAVA bar): calibration
    correctly stays off — raw QDA LLRs must already carry the payload."""
    spec, fd, vspec, data, rgb_u8, cp = _coded_volume()
    crop = np.ascontiguousarray(rgb_u8[313:1213, 401:1301])
    out = formats.acquire_scan(crop, candidates=[fd], calibrate=True)
    assert out.ok, out.tried
    assert out.fmt.format_id == "test-v4-cmy8"
    res = out.result
    assert isinstance(res.payload_llr, list) and len(res.payload_llr) == 3
    idx = res.payload_cell_index
    assert idx.size > 10_000
    for lv in range(3):
        gt = cp.payload_bits[lv][idx]
        ber = float((res.payload_bits[lv] != gt).mean())
        assert ber < 0.01, f"level {lv} BER {ber:.4f}"


# 2026-09-05: 34 s — one blind acquire_scan pass per K hypothesis. Moved to
# the slow lane (the pin survives there; the default lane keeps
# test_acquire_scan_color_crop on the identical crop), and deduped on the
# way so even the slow lane pays 14 s.
@_SLOW
def test_acquire_scan_color_vs_k_registry_same_seed() -> None:
    """The reverse D7 direction at acquire level: a COLOR page offered the
    full K-format registry (reshaped, SAME seed) must reject every K-row
    hypothesis on the value scramble and win as the v4 row. (The forward
    direction — K pages vs the e017 color row — is exercised by
    test_scannorm_formats' registry-wide candidates.)"""
    spec, fd, vspec, data, rgb_u8, cp = _coded_volume()
    crop = np.ascontiguousarray(rgb_u8[313:1213, 401:1301])
    # 2026-09-05: one row per (layout_version, encoding_id). The reshape
    # below passes nothing else that distinguishes the rows (same SEED,
    # geometry, plane, dust=None), so rows sharing that pair are
    # byte-identical hypotheses; the registry's 7 dustless rows collapse to
    # 3 (measured 34.5 -> 14.4 s, same verdict, same out.tried ids). Read
    # from the registry, so a new K coding is still hypothesis-tested.
    seen: dict = {}
    for f in formats.FORMAT_REGISTRY:
        if f.dust is None:
            seen.setdefault((f.layout_version, f.encoding_id), f)
    k_rows = [formats.FormatDescriptor(f.format_id, SEED, f.layout_version,
                                       f.encoding_id, (240, 240), f.plane,
                                       dust=f.dust)
              for f in seen.values()]
    # K rows FIRST: their plane group is hypothesis-tested before the v4
    # row can win, so every reject is observable in out.tried
    out = formats.acquire_scan(crop, candidates=k_rows + [fd])
    assert out.ok, out.tried
    assert out.fmt.format_id == "test-v4-cmy8"
    tried_ids = {t[0] for t in out.tried}
    # the same-geometry c3 K rows (v3 AND v2 codes) were hypothesis-tested
    # and value-rejected; c2 rows may legitimately fall off the pitch
    # shortlist, so they are not asserted individually
    assert {"e012-v3-c3", "e011-v2-c3"} <= tried_ids, out.tried


def test_page_decode_coded_volume_byte_exact() -> None:
    """The receiver certification gate: blind page_decode (identify ->
    normalize luma+RGB -> window acquire with dust-QDA) -> per-level LDPC
    certify -> fountain volume_decode byte-exact."""
    spec, fd, vspec, data, rgb_u8, cp = _coded_volume()
    ident, state = formats.page_decode(rgb_u8, scan_id="A", candidates=[fd],
                                       calibrate=True)
    assert ident.ok, ident.tried
    assert ident.fmt.format_id == "test-v4-cmy8"
    assert ident.diagnostics["n_windows_ok"] >= 1
    state.decode_tiles(RATES)
    # every INTERIOR (fountain-bearing) tile must certify on all 3 levels;
    # page-edge tiles may lose boundary rows to the coverage trim
    interior = set(fountain.interior_tiles(spec))
    for t in interior:
        for lv in range(3):
            assert state.tiles[(t, lv)].status == "certified", (t, lv)
    syms = fountain.tiles_to_symbols(state.certified_results(), vspec)
    out, diag = fountain.volume_decode(syms, vspec)
    assert diag["solved_all"], diag
    assert out == data
    # volume-level F6: nothing more to ask once the volume decodes
    assert tilemap.volume_scans_wanted({0: state}, vspec) == []


if __name__ == "__main__":
    for fn in sorted(k for k in list(globals()) if k.startswith("test_")):
        globals()[fn]()
        print(f"PASS {fn}")
