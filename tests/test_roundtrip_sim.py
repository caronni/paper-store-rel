"""M0 sanity: encode -> simulate print/scan -> naive decode, plus determinism checks.

Runs under pytest, or standalone:  python tests/test_roundtrip_sim.py
Sync is bypassed (warp disabled, known geometry) — this tests the simulator plumbing
and modulation round-trip, not Layer 2. M1 adds the sync-in-the-loop version.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from paperholo.channel import ChannelParams, print_plane, print_scan, rescreen_plane, scan_plane
from paperholo.metrics import ber
from paperholo.modulation import cells_to_dots, dots_to_cells_hard, keystream, scramble
from paperholo.pilots import pilot_sites
from paperholo.sync import estimate_lattice

SEED = b"paper-holo-test"
CELL = 3


def test_keystream_deterministic_and_involution():
    a = keystream(SEED, plane=1, page=7, shape=(64, 64))
    b = keystream(SEED, plane=1, page=7, shape=(64, 64))
    c = keystream(SEED, plane=2, page=7, shape=(64, 64))
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    assert 0.4 < a.mean() < 0.6
    data = keystream(b"other", 0, 0, (64, 64))
    assert np.array_equal(scramble(scramble(data, a), a), data)


def test_pilot_sites_periodic_and_sparse():
    m = pilot_sites((256, 256), SEED)
    assert 0.02 < m.mean() < 0.04
    assert np.array_equal(m[:128, :128], m[128:, 128:])  # PERIOD=64 tiling


def test_sim_roundtrip_no_warp():
    rng = np.random.default_rng(42)
    cells = rng.integers(0, 2, size=(96, 96), dtype=np.uint8)
    dots = cells_to_dots(cells, CELL)
    p = ChannelParams(seed=1, geometry=False)  # sync bypassed at M0
    scan = print_scan(dots, p)
    cell_px = CELL * p.scan_oversample
    rx = dots_to_cells_hard(scan, cell_px)
    e = ber(cells, rx)
    # Naive hard decision under 2-D ISI, measured channel: hardware anchor is
    # 3.74% (CAL-1 c3 K matrix, conservative within-page number); the v4-class
    # context/soft detector and the inner LDPC (M2) live above this. Guard the
    # envelope, don't celebrate the mean.
    print(f"  raw hard-decision BER = {e:.4f}")
    assert e < 0.06, f"raw BER outside measured envelope: {e:.4f}"


def test_lattice_pitch_estimate():
    rng = np.random.default_rng(3)
    cells = rng.integers(0, 2, size=(128, 128), dtype=np.uint8)
    p = ChannelParams(seed=2, geometry=False)
    scan = print_scan(cells_to_dots(cells, CELL), p)
    true_pitch = CELL * p.scan_oversample
    est = estimate_lattice(scan, pitch_px_nominal=true_pitch)
    assert 0.75 * true_pitch < est["pitch_px"] < 1.33 * true_pitch, est


def test_printer_scanner_split():
    """002.0b contract: printer randomness is print-frozen (rescans reproduce
    it), scanner randomness is fresh per scan (steps do not reproduce)."""
    rng = np.random.default_rng(7)
    dots = cells_to_dots(rng.integers(0, 2, size=(64, 64), dtype=np.uint8), CELL)
    p = ChannelParams(seed=5)
    printed_a = print_plane(dots, p)
    printed_b = print_plane(dots, p)
    assert np.array_equal(printed_a.refl_dots, printed_b.refl_dots)
    assert np.array_equal(printed_a.wander_dy_of_y, printed_b.wander_dy_of_y)

    scan1 = scan_plane(printed_a, ChannelParams(seed=5, scan_seed=101))
    scan1b = scan_plane(printed_a, ChannelParams(seed=5, scan_seed=101))
    scan2 = scan_plane(printed_a, ChannelParams(seed=5, scan_seed=102))
    assert np.array_equal(scan1, scan1b)  # a scan is deterministic in its seed
    assert not np.array_equal(scan1, scan2)  # fresh steps/noise per scan


def test_rescreen_composite_path():
    """Screened-composite emission: coverage is preserved to first order and
    the output carries screen structure the clean path does not."""
    rng = np.random.default_rng(11)
    dots = cells_to_dots(rng.integers(0, 2, size=(128, 128), dtype=np.uint8), CELL)
    screened = rescreen_plane(dots, dpi=600, lpi=165.0, angle_deg=14.0)
    assert abs(screened.mean() - dots.mean()) < 0.08
    assert not np.array_equal(screened, dots)
    # Screen fundamental (~600/165 = 3.6-dot period, rotated 14 deg) must be
    # off the 3-dot cell lattice: spectra differ at the screen frequency.
    f = np.fft.fftfreq(dots.shape[0])
    fs, a = 165.0 / 600.0, np.deg2rad(14.0)
    fy, fx = fs * np.sin(a), fs * np.cos(a)
    iy, ix = np.argmin(np.abs(f - fy)), np.argmin(np.abs(f - fx))
    mag_screened = np.abs(np.fft.fft2(screened - screened.mean()))
    mag_clean = np.abs(np.fft.fft2(dots - dots.mean()))
    assert mag_screened[iy, ix] > 3 * mag_clean[iy, ix]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
