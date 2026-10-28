"""e017 ARCH-C preflight (sim-before-toner, CLAUDE.md ground rule) — the
COLOR coded gate (COLOR-DESIGN §2 "clean-channel CODED round-trip byte-exact,
fully blind").

Gates:
- byte-identical regeneration + frozen ps/data golden shas; the gen spec
  equals the formats registry row e017-v4-cmy8 (one format, two spellings);
- gs tiffsep per-plane pixel-exact vs the GT bitmaps (the e004 composite
  render gate: gs does not screen — the addressed dots ARE the page);
- THE GATE: clean-channel coded round-trip, FULLY BLIND, byte-exact:
  data -> level-stratified fountain -> per-level LDPC -> cmy8 compose ->
  clean RGB render (measured crosstalk compose, NO sim noise, ONE crop) ->
  blind formats.page_decode (luma identify -> dust-QDA -> per-level
  PAVA'd LLRs) -> decode_tiles at the frozen rungs -> certified ->
  fountain volume_decode -> data sha match. Run on an e017-CLASS page
  (300x300 cells; identical format constants: v4, dust 18/3, CM words,
  rungs r0550/r0550/r0547, K/N 0.80) — the full A4 through the blind
  page loop is an experiment-script workload, not a suite gate;
- the REAL e017 page: one interior 600-cell window, blind acquire_scan via
  the REGISTRY row -> per-level certification byte-exact vs the fountain
  frame (the e016 window-certify idiom);
- sim-noise leg through print_scan_cmy, SCOPE-DECLARED (the e016/M0
  idiom): the clean_mask (AltaLink-class overlap-preserving) emission is
  the certifiable sim regime — declared level-BER band, certify what
  certifies, byte-exact where certified, zero wrong certifications. The
  M281 screened path is DECLARED OUT OF SIM SCOPE at this footing: probe
  P2 measured the ~165 lpi re-screen attenuating the c3 luma cell line
  ~3x (blind pitch ID fails 75% of tiles at 2 px/dot) — M281 color decode
  is pre-registered on the Canon 8 px/dot footing (017 log, hardware
  queue); the screened path's genie-footing regime bands live in
  test_color_sim.py.

Runs under pytest, or standalone: env/bin/python tests/test_e017.py
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
EXP = Path(__file__).resolve().parent.parent / "experiments/017-color-channel"
sys.path.insert(0, str(EXP))

from paperholo import acquire, compose, formats, fountain, ldpc, \
    tilemap  # noqa: E402
from paperholo.channel import ChannelParams, planes_to_rgb_refl, \
    print_scan_cmy  # noqa: E402
from paperholo.dust import DustLayout  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
from paperholo.pilots import PilotLayout  # noqa: E402
import gen_e017  # noqa: E402

GOLD_PS_SHA = ("d99ea1c50d40fd81389fc356cf0157f7d03cac33ecb347014b32e9f33"
               "c6652b3")
GOLD_DATA_SHA = ("19a5cc15ba4f0b4bdd73cefcb7d1591e1154315417fca2a0abb2a53b"
                 "964ee13b")
GATE_SEED = b"paper-store/exp017-color/gate"

_cache: dict = {}


def _built() -> dict:
    if "mf" not in _cache:
        if not (EXP / "build/e017.ps").exists():
            r = subprocess.run([sys.executable, str(EXP / "gen_e017.py")],
                               capture_output=True, text=True, timeout=600,
                               cwd=str(EXP))
            assert r.returncode == 0, r.stdout + r.stderr
        _cache["mf"] = json.loads(
            (EXP / "build/e017_manifest.json").read_text())
    return _cache["mf"]


def _framed() -> tuple:
    """(vspec, data, framed-page-0 dict, per-level full user vectors)."""
    if "framed" not in _cache:
        vspec = gen_e017.make_vspec()
        data = gen_e017.make_data(vspec)
        framed = fountain.encode_volume_pages(data, vspec)[0]
        users = fountain.volume_encode(data, vspec).page_user_bits[0]
        _cache["framed"] = (vspec, data, framed, users)
    return _cache["framed"]


def _gt_planes() -> np.ndarray:
    """(3, Hd, Wd) uint8 plane bitmaps from the sha-gated build GT."""
    if "gt" not in _cache:
        mf = _built()
        planes = []
        for pl in "CMY":
            (e,) = [q for q in mf["patches"] if q["planes"] == [pl]]
            planes.append(np.load(EXP / "build" / e["gt"]))
        _cache["gt"] = np.stack(planes).astype(np.uint8)
    return _cache["gt"]


def _clean_rgb_u8(plane_bits: np.ndarray) -> np.ndarray:
    """CLEAN render: dot bitmaps -> (H, W, 3) uint8 RGB at 2 px/dot through
    the measured density-domain crosstalk compose. NO noise, NO geometry —
    the ideal-channel footing of the coded gate."""
    up = np.repeat(np.repeat(plane_bits.astype(np.float64), 2, 1), 2, 2)
    rgb = planes_to_rgb_refl({pl: up[lv] for lv, pl in enumerate("CMY")})
    return np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)


def _gate_volume() -> tuple:
    """The e017-CLASS gate volume: 300x300 cells (25 pilot tiles -> 450
    dust labels >= the 300-label PAVA bar; 16 interior LDPC tiles), same
    frozen format constants and rungs, K/N 0.80."""
    if "gate" not in _cache:
        spec = compose.ComposeSpec(
            layout_version=4, encoding_id="cmy8-c3", plane="CMY",
            pilot=PilotLayout(version=4), page_cells_yx=(300, 300),
            dust=DustLayout(sites_per_tile=18, pure_quota=3))
        fd = formats.FormatDescriptor(
            "e017-gate-v4-cmy8", GATE_SEED, 4, "cmy8-c3", (300, 300),
            plane="CMY", notes="test-local e017-class gate page",
            dust=DustLayout(sites_per_tile=18, pure_quota=3))
        probe = fountain.VolumeSpec(
            n_pages=1, data_len_bytes=1, seed=GATE_SEED, compose_spec=spec,
            n_levels=3, ldpc_rate_ids=gen_e017.RUNGS)
        cap = sum(probe.source_capacity_bits_level(lv) for lv in range(3))
        data_len = int(gen_e017.K_OVER_N * cap) // 8
        vspec = fountain.VolumeSpec(
            n_pages=1, data_len_bytes=data_len, seed=GATE_SEED,
            compose_spec=spec, n_levels=3, ldpc_rate_ids=gen_e017.RUNGS)
        data = rng(GATE_SEED, b"gate/data").integers(
            0, 256, data_len, dtype=np.uint8).tobytes()
        framed = fountain.encode_volume_pages(data, vspec)[0]
        cp = compose.compose_page(framed["payload_bits"], spec, GATE_SEED,
                                  page=0)
        _cache["gate"] = (spec, fd, vspec, data, cp)
    return _cache["gate"]


def _e017_fd() -> formats.FormatDescriptor:
    (fd,) = [f for f in formats.FORMAT_REGISTRY
             if f.format_id == "e017-v4-cmy8"]
    return fd


# ---------------------------------------------------------------------------


def test_determinism_and_golden_sha() -> None:
    mf = _built()
    ps_sha = hashlib.sha256((EXP / "build/e017.ps").read_bytes()).hexdigest()
    assert ps_sha == mf["ps_sha256"] == GOLD_PS_SHA, \
        "e017.ps does not match the frozen golden sha — layout bump needed"
    vspec = gen_e017.make_vspec()
    data = gen_e017.make_data(vspec)
    assert hashlib.sha256(data).hexdigest() == GOLD_DATA_SHA
    # volume accounting: 782 interior tiles, K/N 0.80 per level, S 2064
    assert vspec.n_symbols_total == 782
    assert gen_e017.RUNGS == ("r0550", "r0550", "r0547")
    for lv in range(3):
        assert vspec.symbol_bits_level(lv) == 2064, lv
        assert vspec.k_total_level(lv) == 626, lv
    assert mf["volume"]["data_len_bytes"] == vspec.data_len_bytes == 484214
    # r0547 = the ladder floor twin (k Z-quantized), own parity structure
    assert ldpc.LDPC_LADDER["r0547"].k_bits == ldpc.LDPC_LADDER[
        "r0550"].k_bits == 2240
    assert ldpc.LDPC_LADDER["r0547"].seed_label != ldpc.LDPC_LADDER[
        "r0550"].seed_label
    # the gen spec IS the registry row (one format, two spellings)
    fd = _e017_fd()
    assert fd.spec() == gen_e017.make_spec()
    assert fd.seed == gen_e017.SEED
    assert fd.dust == DustLayout(sites_per_tile=18, pure_quota=3)
    # P1-frozen word rendering is pinned by this golden
    assert compose.RENDER_DARK == "CM"
    print(f"  golden sha ok; volume {vspec.data_len_bytes} bytes = 3 x "
          f"{vspec.k_total_level(0)}/{vspec.n_symbols_total} symbols, "
          f"net {mf['volume']['net_bits_per_mm2']} b/mm2")


def test_gs_render_pixel_exact_per_plane() -> None:
    """gs tiffsep separations == the addressed plane bitmaps, exactly, and
    nothing else marks the page (composite emission, e004 gate)."""
    mf = _built()
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                    "-sDEVICE=tiffsep", "-r600",
                    "-o", str(EXP / "build/e017_sep_%d.tif"),
                    str(EXP / "build/e017.ps")], check=True, timeout=600)
    for pl, sep in (("C", "Cyan"), ("M", "Magenta"), ("Y", "Yellow"),
                    ("K", "Black")):
        img = np.asarray(
            Image.open(EXP / f"build/e017_sep_1({sep}).tif")) < 128
        if pl == "K":
            assert not img.any(), "K separation must be empty"
            continue
        (e,) = [q for q in mf["patches"] if q["planes"] == [pl]]
        x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
        gt = np.load(EXP / "build" / e["gt"]).astype(bool)
        crop = img[y:y + h, x:x + w]
        assert np.array_equal(crop, gt), \
            f"{pl}: {int((crop != gt).sum())}/{gt.size} px differ"
        outside = img.copy()
        outside[y:y + h, x:x + w] = False
        assert not outside.any(), f"{pl}: marks outside the field"
    print(f"  gs tiffsep pixel-exact, 3 planes ({gt.shape} dots), K empty")


def test_blind_coded_volume_byte_exact_clean() -> None:
    """THE GATE (see module docstring): fully blind, clean channel, ONE
    crop, byte-exact through the whole color stack."""
    spec, fd, vspec, data, cp = _gate_volume()
    rgb_u8 = _clean_rgb_u8(cp.plane_bits)
    ident, state = formats.page_decode(rgb_u8, scan_id="clean",
                                       candidates=[fd], calibrate=True)
    assert ident.ok, ident.tried
    assert ident.fmt.format_id == "e017-gate-v4-cmy8"
    assert ident.diagnostics["n_windows_ok"] == 1        # ONE crop
    counts = state.decode_tiles(gen_e017.RUNGS)
    # every fountain-bearing (interior) tile certifies on all 3 levels on
    # the clean channel; page-edge tiles may lose rows to the coverage trim
    interior = set(fountain.interior_tiles(spec))
    for t in interior:
        for lv in range(3):
            assert state.tiles[(t, lv)].status == "certified", \
                (t, lv, counts)
    syms = fountain.tiles_to_symbols(state.certified_results(), vspec)
    out, diag = fountain.volume_decode(syms, vspec)
    assert diag["solved_all"], diag
    assert out == data
    assert hashlib.sha256(out).hexdigest() == hashlib.sha256(
        data).hexdigest()
    # volume-level F6: nothing more to ask once the volume decodes
    assert tilemap.volume_scans_wanted({0: state}, vspec) == []
    print(f"  blind clean coded volume byte-exact: {len(syms)} symbols, "
          f"{counts['certified']} (tile,level) certified, "
          f"{len(data)} bytes")


def test_e017_window_certifies_byte_exact() -> None:
    """The REAL e017 page: one interior 600-cell window rendered clean,
    blind-acquired via the REGISTRY row, per-level LDPC certification
    byte-exact vs the fountain frame (e016 window idiom)."""
    gt = _gt_planes()
    vspec, data, framed, users = _framed()
    y0c, x0c, wc = 630, 450, 600                     # interior, cells
    cd = 3
    crop = gt[:, y0c * cd:(y0c + wc) * cd, x0c * cd:(x0c + wc) * cd]
    rgb_u8 = _clean_rgb_u8(crop)
    fd = _e017_fd()
    out = formats.acquire_scan(rgb_u8, candidates=[fd], calibrate=True)
    assert out.ok, out.tried
    assert out.fmt.format_id == "e017-v4-cmy8"
    assert out.geometry_confirmed
    res = out.result
    assert res.page == 0
    state = tilemap.PageDecodeState(vspec.compose_spec, gen_e017.SEED,
                                    page=0)
    state.add_acquire_result("clean-window", res)
    counts = state.decode_tiles(gen_e017.RUNGS, min_coverage=0.999)
    # tiles fully inside the window: ty 10..18 x tx 8..15 = 72, x 3 levels
    assert counts["certified"] >= 200, counts
    per_tile = {lv: {tuple(e["tile_yx"]): (e["user_offset"], e["user_bits"])
                     for e in framed["per_tile"][lv]} for lv in range(3)}
    n_bits = 0
    for (tyx, lv), st in state.tiles.items():
        if st.status == "certified" and st.payload_bits is not None:
            off, cap = per_tile[lv][tyx]
            assert np.array_equal(st.payload_bits,
                                  users[lv][off:off + cap]), (tyx, lv)
            n_bits += int(st.payload_bits.size)
    print(f"  e017 window: {counts['certified']} (tile,level) certified, "
          f"{n_bits} user bits byte-exact vs the fountain frame")


def test_e017_left_edge_window_pava_sign_safe() -> None:
    """Regression for the 017.5 selftest 'M/Y latch' (first e017 hardware
    decode failure): the REAL page's left-edge window (field cells
    540..1140 x -1..600, the driver selftest's win@(4829,509)) rendered
    clean at the 8 px/cell decode footing. Pre-fix, PAVA was FIT on
    cross-fitted HALF-model QDA scores but APPLIED to FULL-model payload
    scores; on a clean channel the two models' LLR scales differ by
    100-1000x (covariance-floor-dominated), the interpolated p=0.5
    crossing landed outside the payload score cloud, and M/Y latched to a
    constant bit = keystream = exactly 50% BER while C decoded 0.00%
    (deterministic, window-specific). The calibration map must be fit on
    the SAME model's scores it is applied to."""
    gt = _gt_planes()
    vspec, data, framed, users = _framed()
    # c3 cells are uniform 3x3 dot blocks: cell values by striding
    cv = gt[:, ::3, ::3].astype(np.float64)
    assert np.array_equal(gt[:, ::3, ::3], gt[:, 1::3, 1::3])
    h_c, w_c = cv.shape[1:]
    cell_px = 8                                     # the driver footing
    # window cells (rows 539..1141, cols -1..601 in field coords) + the
    # 5 px sub-cell crop offset == the selftest frame crop at (4829, 509)
    ry0, rx0, n = 539, -1, 602
    fy = np.arange(ry0, ry0 + n)
    fx = np.arange(rx0, rx0 + n)
    iny = (fy >= 0) & (fy < h_c)
    inx = (fx >= 0) & (fx < w_c)
    rgb_cells = np.full((n, n, 3), 0.92, np.float64)
    rgb_cells[np.ix_(iny, inx)] = planes_to_rgb_refl(
        {pl: cv[lv][np.ix_(fy[iny], fx[inx])]
         for lv, pl in enumerate("CMY")})
    u8 = np.clip(rgb_cells * 255.0 + 0.5, 0, 255).astype(np.uint8)
    scan = np.repeat(np.repeat(u8, cell_px, 0), cell_px, 1)
    crop = np.ascontiguousarray(scan[5:5 + 4800, 5:5 + 4800])
    rgb_f = crop.astype(np.float64) / 255.0
    res = acquire.acquire_and_decode(
        rgb_f.mean(axis=2), vspec.compose_spec, gen_e017.SEED,
        cell_px_nominal=float(cell_px), detector="global", calibrate=True,
        rgb=rgb_f, color_features="rgb")
    assert res.ok, res.diagnostics.get("failed_stage")
    assert res.cell_origin_abs_yx == (540, 0), res.cell_origin_abs_yx
    idx = res.payload_cell_index
    assert idx.size > 0
    bers = []
    for lv in range(3):
        llr = np.asarray(res.payload_llr[lv])
        m = llr != 0.0
        assert m.any(), f"level {lv}: all-zero LLRs"
        hard = (llr[m] > 0).astype(np.uint8)
        ber = float(np.mean(hard != framed["payload_bits"][lv][idx[m]]))
        bers.append(ber)
        assert ber < 0.05, \
            f"level {'CMY'[lv]} BER {ber:.4f} on the clean left-edge " \
            "window — PAVA calibration flipped/latched the payload signs"
    print(f"  left-edge window clean BER C/M/Y "
          f"{['%.3f%%' % (100 * b) for b in bers]} (PAVA sign-safe)")


def test_sim_noise_leg_clean_mask_regime() -> None:
    """Sim-noise leg, SCOPE-DECLARED (module docstring): the clean_mask
    (AltaLink-class) emission through the FULL measured pipeline (develop +
    PSF + mottle + crosstalk + per-channel sensor noise; geometry=False =
    the genie-footing convention of every e0NN sim leg — warp legality is
    the K-validated 011/012 machinery + IMPL-2's shared-warp tests).

    Declared regime: genie-footing clean_mask level BER < 8% (test_color_sim
    band); the blind path adds acquisition residuals — band [0.0005, 0.12]
    per level. Certification: whatever certifies must be byte-exact vs the
    fountain frame (F9: zero wrong certifications), and on this channel at
    the conservative rungs at least half the fully-covered tiles certify."""
    gt = _gt_planes()
    vspec, data, framed, users = _framed()
    spec = vspec.compose_spec
    y0c, x0c, wc = 630, 450, 300                     # interior, cells
    cd = 3
    bits = gt[:, y0c * cd:(y0c + wc) * cd, x0c * cd:(x0c + wc) * cd]
    p = ChannelParams(seed=1701, scan_seed=1702, geometry=False,
                      emission="clean_mask")
    rgb = print_scan_cmy(bits, p)                    # (1800, 1800, 3) float
    res = acquire.acquire_and_decode(rgb.mean(axis=2), spec, gen_e017.SEED,
                                     rgb=rgb, calibrate=True,
                                     cell_px_nominal=6.0)
    assert res.ok, res.diagnostics
    assert res.page == 0
    idx = res.payload_cell_index
    assert idx.size > 0.8 * wc * wc
    bers = []
    for lv in range(3):
        gt_bits = framed["payload_bits"][lv][idx]
        ber = float((res.payload_bits[lv] != gt_bits).mean())
        bers.append(ber)
        assert 0.0005 < ber < 0.12, f"level {lv} BER {ber:.4f} out of the " \
            "declared clean_mask band"
    state = tilemap.PageDecodeState(spec, gen_e017.SEED, page=0)
    state.add_acquire_result("sim", res)
    counts = state.decode_tiles(gen_e017.RUNGS, min_coverage=0.999)
    n_full = sum(1 for (tyx, lv), st in state.tiles.items()
                 if st.coverage >= 0.999)
    assert counts["certified"] >= max(3, n_full // 2), (counts, n_full)
    per_tile = {lv: {tuple(e["tile_yx"]): (e["user_offset"], e["user_bits"])
                     for e in framed["per_tile"][lv]} for lv in range(3)}
    for (tyx, lv), st in state.tiles.items():
        if st.status == "certified" and st.payload_bits is not None:
            off, cap = per_tile[lv][tyx]
            assert np.array_equal(st.payload_bits,
                                  users[lv][off:off + cap]), (tyx, lv)
    print(f"  sim clean_mask: level BER "
          f"{['%.2f%%' % (100 * b) for b in bers]}, "
          f"{counts['certified']}/{n_full} full (tile,level) certified, "
          f"all byte-exact")


if __name__ == "__main__":
    for fn in (test_determinism_and_golden_sha,
               test_gs_render_pixel_exact_per_plane,
               test_blind_coded_volume_byte_exact_clean,
               test_e017_window_certifies_byte_exact,
               test_sim_noise_leg_clean_mask_regime):
        t0 = time.time()
        fn()
        print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)")
