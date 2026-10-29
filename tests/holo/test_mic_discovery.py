"""measure/mic_discovery on a synthetic yellow-dot lattice: the image
path (blue deficit -> dots -> autocorrelation lattice) and the site path
(indexing -> repeat -> fold -> DocuColor parity search)."""
from __future__ import annotations

import numpy as np

from measure.mic_discovery import capture as cap
from measure.mic_discovery import docucolor, lattice

A_MM = np.array([1.016, 0.004])
B_MM = np.array([-0.003, 1.016])
CELL = 16


def _cell(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """A 16 x 16 cell: the DocuColor block in rows 0-7, columns 0-14,
    and sparse random sites in rows 8-15."""
    block = docucolor.encode(minute=37, hour=14, day=9, month=10, year2=26, serial8="21436587")
    cell = np.zeros((CELL, CELL), np.int8)
    cell[:8, :15] = block
    cell[8:] = (rng.random((8, CELL)) < 0.2).astype(np.int8)
    return cell, block


def test_docucolor_block_round_trips() -> None:
    block = docucolor.encode(minute=5, hour=23, day=31, month=12, year2=4, serial8="00991234")
    assert docucolor.parity_sense(block) == "odd"
    fields = docucolor.decode(block)
    assert (fields["minute"], fields["hour"], fields["day"], fields["month"]) == (5, 23, 31, 12)
    assert fields["year_two_digit"] == 4 and fields["serial"] == "00991234"
    assert fields["fields_plausible"]
    flipped = block.copy()
    flipped[3, 7] ^= 1
    assert docucolor.parity_sense(flipped) is None


def test_site_path_recovers_cell_and_decodes() -> None:
    rng = np.random.default_rng(20261009)
    cell, block = _cell(rng)
    n = 3 * CELL
    jj, ii = np.mgrid[0:n, 0:n]
    on = cell[jj % CELL, ii % CELL] == 1
    xy = (ii[on, None] * A_MM + jj[on, None] * B_MM).astype(float) + 5.0
    xy += rng.normal(0, 0.02, xy.shape)
    specks = rng.uniform(5.0, 5.0 + n, (60, 2))
    xy = np.concatenate([xy, specks])
    seed = lattice.best_seed(xy, A_MM, B_MM)
    fit = lattice.fit_sites(xy, A_MM, B_MM, seed)
    assert fit.rms_mm < 0.05
    occ = lattice.occupancy(fit, lambda x, y: np.ones(np.shape(x), bool))
    rep, _ = lattice.find_repeat(occ, A_MM, B_MM)
    assert rep is not None
    a, b, c = lattice.hermite_cell(rep.r1, rep.r2)
    assert (a, b, c) == (CELL, 0, CELL)
    folded = lattice.fold(occ, (a, b, c))
    assert folded.consistency > 0.98
    jj, ii = np.mgrid[0:c, 0:a]
    hits, trials = docucolor.search(folded.at, np.column_stack([ii.ravel(), jj.ravel()]),
                                    site_key=folded.key)
    assert trials > 0
    decoded = [docucolor.decode(h.block) for h in hits]
    assert any(d["serial"] == "21436587" and d["minute"] == 37 and d["fields_plausible"]
               for d in decoded)


def test_image_path_finds_the_lattice() -> None:
    rng = np.random.default_rng(7)
    dpi = 600.0
    size = int(20.0 / 25.4 * dpi)
    rgb = np.full((size, size, 3), 0.95, np.float32) + rng.normal(0, 0.004, (size, size, 3)).astype(np.float32)
    px_mm = dpi / 25.4
    yy, xx = np.mgrid[0:size, 0:size] / px_mm
    for j in range(20):
        for i in range(20):
            if rng.random() < 0.25:
                x, y = 0.5 + i * A_MM + j * B_MM
                rgb[..., 2] -= 0.25 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 0.06 ** 2))
    stats = cap.YellowStats(paper_white_rgb=(0.95, 0.95, 0.95), deficit_median=0.0,
                            deficit_sigma=0.004, threshold_high=0.06, threshold_low=0.03)
    d, rg = cap.blue_deficit(rgb, np.full_like(rgb, 0.95))
    blobs = cap.detect_blobs(d, stats, working_dpi=dpi)
    assert 50 < len(blobs) < 150
    sparse = np.where(d > stats.threshold_low, d - stats.threshold_low, 0.0)
    vec, z = lattice.autocorrelation_peaks(sparse, px_mm)
    basis = lattice.lattice_from_peaks(vec, z)
    assert basis is not None
    a, b = basis
    assert np.allclose(a, A_MM, atol=0.02) and np.allclose(b, B_MM, atol=0.02)


def test_peak_differences_reveal_the_site_pitch() -> None:
    """Sites 6 x 12 printer dots apart, no two occupied closer than 24:
    the pitch shows only in differences of peaks (the Canon's case)."""
    dot_mm = 25.4 / 600
    peaks = np.array([(24, 0), (24, 12), (30, 12), (36, 0), (36, 12), (48, 12), (0, 48), (-30, 48)],
                     float) * dot_mm
    peaks = np.concatenate([peaks, -peaks])
    basis = lattice.lattice_from_peaks(peaks, np.full(len(peaks), 100.0))
    assert basis is not None
    a, b = basis
    assert np.allclose(a, (6 * dot_mm, 0), atol=1e-6) and np.allclose(b, (0, 12 * dot_mm), atol=1e-6)
