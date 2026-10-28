"""Synthetic confetti generator (gen_confetti_synth): render exactness,
channel calibration into the measured real-scan band, and a rotated piece
surviving the real front end (segment -> lock -> ctx -> mask-aware place)."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/016-arch3-c2-volume"))

from paperholo import acquire, compose, fountain, place, scannorm, segment
from paperholo.modulation import rng
import gen_confetti_synth as syn
import gen_e016

SPEC = gen_e016.make_spec()
VSPEC = gen_e016.make_vspec()
FRAMED = fountain.encode_volume_pages(gen_e016.make_data(VSPEC), VSPEC)[0]
CELLS = compose.compose_page(FRAMED["payload_bits"], SPEC, gen_e016.SEED,
                             page=0).cell_values
REFL = np.where(CELLS > 0, syn.INK, syn.PAPER).astype(np.float32)
MID = (syn.PAPER + syn.INK) / 2


def _bits(img: np.ndarray, y0: int, x0: int, n_cells: int) -> np.ndarray:
    b = img[y0:y0 + n_cells * syn.PPC, x0:x0 + n_cells * syn.PPC]
    m = b.reshape(n_cells, syn.PPC, n_cells, syn.PPC).mean(axis=(1, 3))
    return (m < MID).astype(np.uint8)


def test_render_exact_at_angle_zero() -> None:
    """blur=0/noise=0 at angle 0 must reproduce the cell field exactly
    (the one resample is area-exact for axis-aligned pieces)."""
    gen = rng(gen_e016.SEED, b"test/synth-exact")
    rect = (600, 900, 60)
    img = syn.render_piece(REFL, rect, 0.0, 250.0, gen, blur=0.0,
                           noise=0.0)
    got = _bits(img.astype(np.float32), syn.PPC, syn.PPC, 60)
    want = CELLS[600:660, 900:960]
    assert np.mean(got == want) > 0.999


def test_channel_calibration_in_measured_band() -> None:
    """Default blur+noise land raw detection in the measured real-scan
    band (global-detector cell BER ~2-14% at 8 px/cell; real e016 scans:
    global med 8.6-10%). The mimic must be neither clean nor sim-c2-dead."""
    gen = rng(gen_e016.SEED, b"test/synth-cal")
    rect = (1200, 300, 300)                     # 25.4 mm upright
    img = syn.render_piece(REFL, rect, 0.0, 250.0, gen,
                           blur=syn.BLUR_SIGMA, noise=syn.NOISE_SIGMA)
    f = img.astype(np.float32)
    pit = scannorm.measure_cell_pitch(f)
    norm = scannorm.normalize_to_canonical(f, pit.pitch_px, 2)
    grid = acquire.lock_grid(norm.img, cell_px_nominal=norm.cell_px_est,
                             cell_dots=2)
    means = acquire.sample_cell_means(acquire._normalize_refl(norm.img),
                                      grid, cell_dots=2)
    hard, _ = acquire.cell_bits_ctx(means)
    # align by placement (mask-free, big support) then score vs GT
    pl = place.place_fragment(hard, SPEC, gen_e016.SEED)
    assert pl.ok, "calibration window must self-place"
    oy, ox = pl.origin_yx
    bk = np.rot90(hard, pl.rot_k)
    g = CELLS[oy:oy + bk.shape[0], ox:ox + bk.shape[1]]
    ber = float(np.mean(bk[: g.shape[0], : g.shape[1]] != g))
    # target = the ctx band real e016 scans measure (2-5%); the global
    # 8-10% gap is dev morphology, deliberately excluded (see generator)
    assert 0.005 < ber < 0.06, ber


def test_rotated_piece_through_real_front_end() -> None:
    """A 12 mm piece at 33.7 deg on a white canvas: segment -> own lock ->
    ctx -> mask-aware place must gate-PASS at its true location."""
    gen = rng(gen_e016.SEED, b"test/synth-rot")
    rect = (2000, 1500, 142)                    # ~12 mm
    img = syn.render_piece(REFL, rect, 33.7, 250.0, gen,
                           blur=syn.BLUR_SIGMA, noise=syn.NOISE_SIGMA)
    pad = 20 * syn.PPC
    canvas = np.full((img.shape[0] + 2 * pad, img.shape[1] + 2 * pad),
                     250.0, np.float32)
    canvas[pad:pad + img.shape[0], pad:pad + img.shape[1]] = img
    found = segment.segment_pieces(canvas, cell_px=syn.PPC, dpi=2400.0)
    assert len(found) == 1
    p = found[0]
    pit = scannorm.measure_cell_pitch(p.img)
    norm = scannorm.normalize_to_canonical(p.img, pit.pitch_px, 2)
    hard, mcell, _ = segment.piece_cell_bits(norm.img, p.mask,
                                             int(round(norm.cell_px_est)))
    pl = place.place_fragment(hard, SPEC, gen_e016.SEED, mask=mcell)
    assert pl.ok and pl.mismatch < 0.12, (pl.ok, pl.mismatch)
    oy, ox = pl.origin_yx
    assert abs(oy - 2000) < 142 and abs(ox - 1500) < 142
    bk, mk = np.rot90(hard, pl.rot_k), np.rot90(mcell, pl.rot_k)
    g = CELLS[oy:oy + bk.shape[0], ox:ox + bk.shape[1]]
    if g.shape == bk.shape:
        assert float(np.mean(bk[mk] == g[mk])) > 0.85
