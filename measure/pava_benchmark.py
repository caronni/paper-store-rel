from __future__ import annotations

import time
from fractions import Fraction

import numpy as np

from holo.receive import detect as oracle

from holo3.data import Placement
from holo3.format import pilots as h3_pilots
from holo3.format.identity import SiteGeometry, resolve_format_ref
from holo3.lib import pava
from holo3.lib.geometry import WINDOW_CELLS
from holo3.plugins import calibrate as cal

RNG = np.random.default_rng(20260829)

NEW_PAVA = pava._pava_nodes
OLD_PAVA = oracle._pava_nodes


def bench(fn, repeat: int = 7) -> float:
    best = float("inf")
    for _ in range(repeat):
        started = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - started)
    return best


def make_case(n: int, bias: float) -> tuple[np.ndarray, np.ndarray]:
    labels = (RNG.random(n) < 0.5).astype(np.int8)
    truth = np.where(labels > 0, 1.0, -1.0)
    scores = (RNG.normal(0.0, 1.0, size=n) + bias * truth).astype(np.float32)
    return scores, labels


print("== _pava_nodes, old vs new (ms, best of 7) ==")
print(f"{'n':>7} {'bias':>5} {'old':>9} {'new':>9} {'speedup':>8}")
totals: list[tuple[float, float]] = []
for n in (2000, 5000, 10000, 20000, 40000):
    for bias in (0.35, 0.9, 1.4, 2.2, 3.0):
        scores, labels = make_case(n, bias)
        old = bench(lambda: OLD_PAVA(scores, labels))
        new = bench(lambda: NEW_PAVA(scores, labels))
        totals.append((old, new))
        print(f"{n:>7} {bias:>5} {old*1e3:>9.3f} {new*1e3:>9.3f} "
              f"{old/new:>8.2f}x")
sum_old = sum(a for a, _ in totals)
sum_new = sum(b for _, b in totals)
print(f"{'grid mean':>13} {sum_old*1e3:>9.3f} {sum_new*1e3:>9.3f} "
      f"{sum_old/sum_new:>8.2f}x")


print("\n== realistic full window (calibrate_window) ==")
ROW = resolve_format_ref("L:c2-r0700@3392x2368")
WORD = h3_pilots.word_site_cells_yx(ROW.sites_seed)
FILLER = h3_pilots.filler_site_cells_yx(
    ROW.sites_seed, ROW.n_sites - h3_pilots.N_WORD_SITES, WORD)
EMPTY = np.zeros(0, np.int64)
GEOMETRY = SiteGeometry(WORD, FILLER, EMPTY, EMPTY, EMPTY, EMPTY)
LOOKUP = cal.build_site_lookup(GEOMETRY)

for pitch_px in (5.0, 8.0):
    origin = (37.0, 23.0)
    cell_y0, cell_x0 = 128, 192
    ny = nx = WINDOW_CELLS
    page_cells = np.stack(np.meshgrid(
        np.arange(cell_y0, cell_y0 + ny, dtype=np.int64),
        np.arange(cell_x0, cell_x0 + nx, dtype=np.int64),
        indexing="ij"), axis=-1).reshape(-1, 2)
    reference = cal.format_reference_values(ROW, LOOKUP, 0, page_cells)
    truth_bits = RNG.integers(0, 2, size=page_cells.shape[0]).astype(np.int8)
    truth_bits = np.where(reference >= 0, reference, truth_bits).astype(np.int8)
    grid = np.zeros((ny, nx), np.uint8)
    grid[page_cells[:, 0] - cell_y0, page_cells[:, 1] - cell_x0] = truth_bits
    step = int(pitch_px)
    sheet = np.kron(grid, np.ones((step, step), np.uint8))
    image = np.full((int(origin[0]) + sheet.shape[0] + 60,
                     int(origin[1]) + sheet.shape[1] + 60), 235, np.uint8)
    image[int(origin[0]):int(origin[0]) + sheet.shape[0],
          int(origin[1]):int(origin[1]) + sheet.shape[1]] = np.where(
              sheet > 0, 45, 235)
    image = np.clip(image.astype(np.float64)
                    + RNG.normal(0.0, 6.0, size=image.shape),
                    0, 255).astype(np.uint8)
    affine = (pitch_px, 0.0, origin[0] - 0.5 - cell_y0 * pitch_px,
              0.0, pitch_px, origin[1] - 0.5 - cell_x0 * pitch_px)
    placement = Placement(
        window_id=("cap", 0, 0, (0, 0, ny, nx)), capture_id="cap",
        level_index=0, region_index=0, patch_ordinal=0, page=0, rot_k=0,
        page_origin_yx=(cell_y0, cell_x0), native_affine=affine,
        pitch_px=pitch_px, route="payload",
        local_cells_yx=(page_cells
                        - np.asarray((cell_y0, cell_x0), np.int64)))

    def run() -> object:
        return cal.calibrate_window([image], placement, (ny, nx), ROW,
                                    LOOKUP, pitch_px, Fraction(1))

    evidence = run()
    known = int(np.count_nonzero(evidence.reference_values >= 0))
    fit_scores = evidence.scores
    fit_labels = evidence.reference_values
    cells = evidence.page_cells_yx.astype(np.int64)
    known_mask = fit_labels >= 0
    parity = cal.site_parity(cells[:, 0], cells[:, 1]).astype(bool)
    search = known_mask & ~parity
    n_search = int(np.count_nonzero(search))
    pava_old = bench(lambda: OLD_PAVA(fit_scores[search], fit_labels[search]))
    pava_new = bench(lambda: NEW_PAVA(fit_scores[search], fit_labels[search]))
    llr = bench(lambda: pava.calibration_llr(
        evidence.scores, evidence.knots, evidence.probs))
    print(f"\npitch_px={pitch_px}  raster={image.shape}  "
          f"cells={page_cells.shape[0]}  known={known}  n_search={n_search}")
    print(f"  _pava_nodes        old {pava_old*1e3:8.3f} ms   "
          f"new {pava_new*1e3:8.3f} ms   {pava_old/pava_new:5.2f}x")
    print(f"  calibration_llr over all {evidence.scores.size} scores "
          f"{llr*1e3:8.3f} ms")

pava._pava_nodes = NEW_PAVA
print("\nBENCHMARK DONE")
