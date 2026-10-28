"""COLOR CHANNEL simulator (IMPL-2) — measured-channel gates for cmy8 pages.

Covers, per the COLOR-DESIGN certification plan ("sim-regime sanity through
the measured color channel (rescreen + crosstalk + warp)"):

- determinism: print_scan_cmy is a pure function of (bits, seed, scan_seed);
  fresh scan_seed = fresh scanner realization on the same printed page;
- K-path regression: rescreen_plane's default blur is byte-identical to the
  frozen 0.5*period behavior (the new kwarg only OFFERS the calibrated CMY
  value — existing K screened-path consumers, e.g. the msel1 M0 gate, are
  untouched);
- shared warp: all three planes ride ONE scanner realization and ONE
  print-frozen wander/scale draw — with per-plane registration zeroed the
  three scanned ink fields are IDENTICAL under full geometry (planes fuse
  together, COLOR-DESIGN D5);
- per-plane registration: print_cmy's drift fields reproduce the frozen
  CAL-1 models (M281_PLANES reg_* constants: Y -2.17 center / -1.91 per
  100 mm, etc.) and displace the scanned ink by the modeled amount;
- REGIME SANITY at genie footing (geometry off, known grid), 120x120-cell
  cmy8 page, cross-half-trained 8-class full-covariance QDA on full-cell
  mean RGB:
    screened path (M281 model): soft-MI asserted in [1.5, 2.05] b/cell.
      Why this band: it is centered on the calibration point — this
      construction reads 1.760-1.766 across 4 seeds against CAL-1
      002.0's measured 1.76 (CMY_RESCREEN_SIGMA_FRAC provenance) — sits
      inside/above the measured hardware span 1.48-1.90 b/cell (002.2
      sheet-low 1.48 ... CAL-1 1.76 ... 004.0 A3 top 1.90; the 1.48
      sheet-low is deliberately below the band: the gate pins the
      CALIBRATED sim, not the worst sheet), and excludes both known
      failure modes: the uncalibrated 0.5*period screen reads 1.23 and
      an accidentally-clean channel reads ~2.47 — both FAIL, so the gate
      catches regressions in either direction.
    clean path (AltaLink-class overlap-preserving model): soft-MI in
      [2.2, 2.85] b/cell — engine-2 measured 8-state 2.208 (007.6, on
      JPEG-taxed scans the sim does not model) is the floor anchor;
      sim reads 2.466.
  KNOWN RESIDUAL (documented at CMY_RESCREEN_SIGMA_FRAC): the sim's
  per-LEVEL reliability order is inverted vs hardware (sim Y strongest);
  per-level assertions here are ceilings only, never orderings.

Runs under pytest, or standalone: env/bin/python tests/test_color_sim.py
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from paperholo import compose, dust, pilots  # noqa: E402
from paperholo.channel import (  # noqa: E402
    CMY_PLANE_ORDER,
    ChannelParams,
    PrinterParams,
    ScannerParams,
    print_cmy,
    print_scan_cmy,
    rescreen_plane,
    scan_cmy,
)
from paperholo.channel.simulator import (  # noqa: E402
    M281_PLANES,
    _scan_cmy_inks,
)
from paperholo.modulation import rng  # noqa: E402

SEED = b"paper-store/test-color-sim"
# 24/tile = the IMPL-2 calibration-era dust layout, KEPT deliberately so
# the regime/calibration numbers in this file's docstring stay regenerable
# (the P3-frozen FORMAT density is 18/tile = 0.5%, formats.py registry row;
# dust density is irrelevant to the whole-grid MI statistic here — the
# regime gate scores ALL cells via cell_values, not just dust)
DUST = dust.DustLayout(sites_per_tile=24, pure_quota=3)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

_PAGE_CACHE: dict = {}


def _page():
    """One composed 120x120-cell cmy8 page (2x2 pilot tiles), cached."""
    if "page" not in _PAGE_CACHE:
        spec = compose.ComposeSpec(
            layout_version=4, encoding_id="cmy8-c3", plane="CMY",
            pilot=pilots.PilotLayout(version=4), page_cells_yx=(120, 120),
            dust=DUST)
        cap = compose.payload_capacity(spec)
        g = rng(SEED, b"payload")
        payload = [g.integers(0, 2, cap, dtype=np.uint8) for _ in range(3)]
        _PAGE_CACHE["page"] = (
            compose.compose_page(payload, spec, SEED, page=0), spec)
    return _PAGE_CACHE["page"]


def _bits_block_y_only(h: int = 120, w: int = 120) -> np.ndarray:
    """(3, h, w) with one 30x30 ink block in the Y plane only."""
    bits = np.zeros((3, h, w), dtype=np.uint8)
    bits[2, 40:70, 40:70] = 1
    return bits


# quiet instruments: every stochastic/deterministic SCANNER displacement and
# the printer wander off, so only per-plane registration moves ink
_QUIET_PRINTER = PrinterParams(wander_components=(), y_scale_error=0.0)
_QUIET_SCANNER = ScannerParams(
    y_step_rate_per_mm=0.0, comb_step_dots=0.0,
    y_scale_error=0.0, y_scale_sigma=0.0, noise_sigma_refl=0.0)


def _centroid_yx(field: np.ndarray) -> tuple[float, float]:
    m = field / max(field.sum(), 1e-12)
    ys = np.arange(field.shape[0], dtype=np.float64)
    xs = np.arange(field.shape[1], dtype=np.float64)
    return float((m.sum(axis=1) * ys).sum()), float((m.sum(axis=0) * xs).sum())


# ---------------------------------------------------------------------------
# QDA + MI helpers (test-local; the receiver's detector lives in acquire)
# ---------------------------------------------------------------------------

def _cell_mean_rgb(rgb: np.ndarray, spec, os_px: int) -> np.ndarray:
    cd = spec.cell_dots
    h, w = spec.page_cells_yx
    px = cd * os_px
    r = rgb[: h * px, : w * px].reshape(h, px, w, px, 3)
    return r.mean(axis=(1, 3)).reshape(h * w, 3)


def _qda_loglik(X_tr: np.ndarray, y_tr: np.ndarray,
                X_te: np.ndarray, n_classes: int = 8) -> np.ndarray:
    ll = np.empty((len(X_te), n_classes))
    for c in range(n_classes):
        Xc = X_tr[y_tr == c]
        mu = Xc.mean(axis=0)
        cov = np.cov(Xc.T) + 1e-8 * np.eye(X_tr.shape[1])
        icov = np.linalg.inv(cov)
        d = X_te - mu
        ll[:, c] = (-0.5 * (np.einsum("ij,jk,ik->i", d, icov, d)
                            + np.linalg.slogdet(cov)[1])
                    + np.log(len(Xc) / len(X_tr)))
    return ll


def _soft_mi_bits(ll: np.ndarray, y_true: np.ndarray, n: int = 8) -> float:
    """Plug-in soft MI (the experiments' b/cell statistic)."""
    post = np.exp(ll - ll.max(axis=1, keepdims=True))
    post /= post.sum(axis=1, keepdims=True)
    h_cond = -np.mean(np.sum(post * np.log2(post + 1e-300), axis=1))
    pr = np.bincount(y_true, minlength=n) / len(y_true)
    h_s = -np.sum(pr[pr > 0] * np.log2(pr[pr > 0]))
    return float(h_s - h_cond)


def _genie_qda_read(rgb: np.ndarray, page, spec) -> dict:
    """Cross-half (train left / test right) 8-class QDA at genie footing."""
    feats = _cell_mean_rgb(rgb, spec, os_px=2)
    cv = page.cell_values
    states = (cv[0] + 2 * cv[1] + 4 * cv[2]).reshape(-1).astype(np.int64)
    h, w = spec.page_cells_yx
    col = np.tile(np.arange(w), h)
    tr = col < w // 2
    ll = _qda_loglik(feats[tr], states[tr], feats[~tr])
    pred = ll.argmax(axis=1)
    yt = states[~tr]
    return {
        "acc": float((pred == yt).mean()),
        "soft_mi": _soft_mi_bits(ll, yt),
        "level_ber": [float((((pred >> lv) & 1) != ((yt >> lv) & 1)).mean())
                      for lv in range(3)],
    }


# ---------------------------------------------------------------------------
# determinism + K-path regression
# ---------------------------------------------------------------------------

def test_print_scan_cmy_deterministic_and_seed_sensitive() -> None:
    bits = _bits_block_y_only()
    p = ChannelParams(seed=5, emission="screened_composite")
    a = print_scan_cmy(bits, p)
    b = print_scan_cmy(bits, ChannelParams(seed=5, emission="screened_composite"))
    assert a.shape == (240, 240, 3)
    assert np.array_equal(a, b), "same (seed, scan_seed) must be bit-identical"
    # fresh scan of the SAME printed page: new scanner realization
    c = print_scan_cmy(bits, ChannelParams(
        seed=5, scan_seed=99, emission="screened_composite"))
    assert not np.array_equal(a, c)
    # different print: different page
    d = print_scan_cmy(bits, ChannelParams(seed=6, emission="screened_composite"))
    assert not np.array_equal(a, d)


def test_print_scan_cmy_rejects_bad_shape() -> None:
    for bad in (np.zeros((120, 120)), np.zeros((2, 60, 60))):
        try:
            print_scan_cmy(bad, ChannelParams())
            raise AssertionError(f"accepted shape {bad.shape}")
        except ValueError:
            pass


def test_rescreen_default_is_frozen_k_behavior() -> None:
    """The new contone_sigma_dots kwarg must not move the default output:
    None == explicit 0.5*period (the K screened path is frozen)."""
    g = rng(SEED, b"rescreen")
    bits = g.integers(0, 2, (90, 90), dtype=np.uint8)
    base = rescreen_plane(bits, 600, 165.0, 14.0)
    explicit = rescreen_plane(bits, 600, 165.0, 14.0,
                              contone_sigma_dots=0.5 * 600 / 165.0)
    assert np.array_equal(base, explicit)
    # and the calibrated value is a genuinely different screen
    cal = rescreen_plane(bits, 600, 165.0, 14.0,
                         contone_sigma_dots=0.30 * 600 / 165.0)
    assert not np.array_equal(base, cal)


# ---------------------------------------------------------------------------
# shared warp + per-plane registration (COLOR-DESIGN D5)
# ---------------------------------------------------------------------------

def test_planes_share_one_scanner_and_wander_realization() -> None:
    """Identical ink in all planes + registration zeroed => the three
    scanned ink fields are IDENTICAL under FULL geometry (steps, comb,
    scales, wander are one shared realization — planes fuse together)."""
    bits = np.zeros((3, 120, 120), dtype=np.uint8)
    bits[:, 30:90:6, :] = 1     # same lattice in every plane
    p = ChannelParams(seed=11, geometry=True)
    printed = print_cmy(bits, p)
    printed.ink_dots[:] = printed.ink_dots[0]      # same ink (mottle differs)
    printed.reg_dy_of_y[:] = 0.0
    printed.reg_dx_of_x[:] = 0.0
    inks = _scan_cmy_inks(printed, p, rotate90=False)
    assert np.array_equal(inks[0], inks[1])
    assert np.array_equal(inks[0], inks[2])


def test_reg_fields_reproduce_cal1_drift_models() -> None:
    """print_cmy's registration fields are the frozen CAL-1 linear models:
    center value = reg_*_center_dots, slope = reg_*_slope_dots_per_100mm."""
    bits = np.zeros((3, 2220, 120), dtype=np.uint8)   # tall field: 94 mm
    p = ChannelParams(seed=3, geometry=True)
    printed = print_cmy(bits, p)
    dots_per_mm = 600 / 25.4
    for li, plane in enumerate(CMY_PLANE_ORDER):
        pl = M281_PLANES[plane]
        dy = printed.reg_dy_of_y[li]
        mid = 0.5 * (dy[0] + dy[-1])
        assert abs(mid - pl.reg_dy_center_dots) < 1e-9
        span_100mm = (len(dy) - 1) / dots_per_mm / 100.0
        slope = (dy[-1] - dy[0]) / span_100mm
        assert abs(slope - pl.reg_dy_slope_dots_per_100mm) < 1e-6, plane
    # geometry=False zeroes them (K-path convention)
    printed0 = print_cmy(bits, ChannelParams(seed=3, geometry=False))
    assert not printed0.reg_dy_of_y.any() and not printed0.reg_dx_of_x.any()
    assert printed0.y_scale_error == 0.0 and not printed0.wander_dy_of_y.any()


def test_y_plane_registration_displaces_scanned_ink() -> None:
    """Functional check on quiet instruments (all scanner/wander terms off):
    the Y plane's scanned ink moves by its modeled registration. Sign
    convention: scan_plane ADDS reg to the source coordinates, so content
    appears displaced by -reg (Y: reg_dy -2.17 dots => +2.17 dots down,
    reg_dx +0.50 dots => 0.50 dots left)."""
    bits = _bits_block_y_only()
    os_px = _QUIET_SCANNER.oversample
    p_on = ChannelParams(seed=7, geometry=True,
                         printer=_QUIET_PRINTER, scanner=_QUIET_SCANNER)
    p_off = replace(p_on, geometry=False)
    ink_on = _scan_cmy_inks(print_cmy(bits, p_on), p_on, rotate90=False)[2]
    ink_off = _scan_cmy_inks(print_cmy(bits, p_off), p_off, rotate90=False)[2]
    cy_on, cx_on = _centroid_yx(ink_on)
    cy_off, cx_off = _centroid_yx(ink_off)
    pl = M281_PLANES["Y"]
    # field is 5 mm tall: the linear term is < 0.05 dots — center term rules
    assert abs((cy_on - cy_off) - (-pl.reg_dy_center_dots) * os_px) < 0.4
    assert abs((cx_on - cx_off) - (-pl.reg_dx_center_dots) * os_px) < 0.4


# ---------------------------------------------------------------------------
# regime sanity (the headline gate; bands justified in the module docstring)
# ---------------------------------------------------------------------------

def test_regime_screened_m281_band() -> None:
    page, spec = _page()
    p = ChannelParams(seed=17, geometry=False, emission="screened_composite")
    stats = _genie_qda_read(print_scan_cmy(page.plane_bits, p), page, spec)
    print(f"  screened: acc {stats['acc']:.3f} soft-MI {stats['soft_mi']:.3f}"
          f" b/cell, level BER {[f'{b:.3f}' for b in stats['level_ber']]}")
    assert 1.5 <= stats["soft_mi"] <= 2.05, stats
    assert 0.50 <= stats["acc"] <= 0.72, stats
    # per-level ceiling only (order is a known sim residual, see docstring)
    assert all(b < 0.25 for b in stats["level_ber"]), stats


def test_regime_clean_altalink_class_band() -> None:
    page, spec = _page()
    p = ChannelParams(seed=17, geometry=False, emission="clean_mask")
    stats = _genie_qda_read(print_scan_cmy(page.plane_bits, p), page, spec)
    print(f"  clean: acc {stats['acc']:.3f} soft-MI {stats['soft_mi']:.3f}"
          f" b/cell, level BER {[f'{b:.3f}' for b in stats['level_ber']]}")
    assert 2.2 <= stats["soft_mi"] <= 2.85, stats
    assert all(b < 0.08 for b in stats["level_ber"]), stats


def main() -> int:
    tests = [
        test_print_scan_cmy_deterministic_and_seed_sensitive,
        test_print_scan_cmy_rejects_bad_shape,
        test_rescreen_default_is_frozen_k_behavior,
        test_planes_share_one_scanner_and_wander_realization,
        test_reg_fields_reproduce_cal1_drift_models,
        test_y_plane_registration_displaces_scanned_ink,
        test_regime_screened_m281_band,
        test_regime_clean_altalink_class_band,
    ]
    for t in tests:
        print(f"{t.__name__} ...")
        t()
        print("  ok")
    print(f"{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
