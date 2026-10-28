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

ROW = resolve_format_ref("L:c2-r0700@3392x2368")
WORD = h3_pilots.word_site_cells_yx(ROW.sites_seed)
FILLER = h3_pilots.filler_site_cells_yx(
    ROW.sites_seed, ROW.n_sites - h3_pilots.N_WORD_SITES, WORD)
EMPTY = np.zeros(0, np.int64)
GEOMETRY = SiteGeometry(WORD, FILLER, EMPTY, EMPTY, EMPTY, EMPTY)
LOOKUP = cal.build_site_lookup(GEOMETRY)


def bench(fn, repeat: int = 9) -> float:
    best = float("inf")
    for _ in range(repeat):
        started = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - started)
    return best


def build(pitch_px: float, side: int):
    origin = (37.0, 23.0)
    cell_y0, cell_x0 = 128, 192
    page_cells = np.stack(np.meshgrid(
        np.arange(cell_y0, cell_y0 + side, dtype=np.int64),
        np.arange(cell_x0, cell_x0 + side, dtype=np.int64),
        indexing="ij"), axis=-1).reshape(-1, 2)
    reference = cal.format_reference_values(ROW, LOOKUP, 0, page_cells)
    truth = RNG.integers(0, 2, size=page_cells.shape[0]).astype(np.int8)
    truth = np.where(reference >= 0, reference, truth).astype(np.int8)
    grid = np.zeros((side, side), np.uint8)
    grid[page_cells[:, 0] - cell_y0, page_cells[:, 1] - cell_x0] = truth
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
        window_id=("cap", 0, 0, (0, 0, side, side)), capture_id="cap",
        level_index=0, region_index=0, patch_ordinal=0, page=0, rot_k=0,
        page_origin_yx=(cell_y0, cell_x0), native_affine=affine,
        pitch_px=pitch_px, route="payload",
        local_cells_yx=(page_cells
                        - np.asarray((cell_y0, cell_x0), np.int64)))
    return image, placement, page_cells


for pitch_px in (5.0, 8.0):
    image, placement, page_cells = build(pitch_px, WINDOW_CELLS)
    planes = [image]
    frame = Fraction(1)
    raster_shape = (int(image.shape[0]), int(image.shape[1]))

    points = cal.scan_points_yx(placement.native_affine, frame,
                                page_cells, None)
    crop = cal.window_crop(planes, points, raster_shape, pitch_px)
    raw_means = cal.sample_points(crop, points)
    scores = cal.window_scores(raw_means)
    labels = cal.format_reference_values(ROW, LOOKUP, placement.page,
                                         page_cells)

    t_points = bench(lambda: cal.scan_points_yx(
        placement.native_affine, frame, page_cells, None))
    t_inside = bench(lambda: cal.points_inside_raster(points, raster_shape))
    t_crop = bench(lambda: cal.window_crop(planes, points, raster_shape,
                                           pitch_px))
    t_sample = bench(lambda: cal.sample_points(crop, points))
    t_fused = bench(lambda: cal.sampled_window_means(
        planes, points, raster_shape, pitch_px))
    t_scores = bench(lambda: cal.window_scores(raw_means))
    t_labels = bench(lambda: cal.format_reference_values(
        ROW, LOOKUP, placement.page, page_cells))
    pava._pava_nodes = OLD_PAVA
    t_fit_old = bench(lambda: cal.fit_window_calibration(
        scores, labels, page_cells))
    pava._pava_nodes = NEW_PAVA
    t_fit_new = bench(lambda: cal.fit_window_calibration(
        scores, labels, page_cells))

    cells = np.asarray(page_cells, np.int64)
    known = labels >= 0
    parity = cal.site_parity(cells[:, 0], cells[:, 1]).astype(bool)
    search = known & ~parity
    n_search = int(np.count_nonzero(search))
    t_pava_old = bench(lambda: OLD_PAVA(scores[search], labels[search]))
    t_pava_new = bench(lambda: NEW_PAVA(scores[search], labels[search]))

    stages = (("scan_points_yx", t_points), ("points_inside_raster", t_inside),
              ("window_crop (filter)", t_crop), ("sample_points", t_sample),
              ("window_scores", t_scores),
              ("format_reference_values", t_labels),
              ("fit_window_calibration", t_fit_old))
    total_old = sum(v for _, v in stages)
    print(f"\n=== pitch_px={pitch_px}  raster={raster_shape}  "
          f"cells={page_cells.shape[0]}  known={int(known.sum())}  "
          f"n_search={n_search} ===")
    for name, value in stages:
        print(f"  {name:<26} {value*1e3:8.3f} ms  {value/total_old*100:5.1f}%")
    print(f"  {'TOTAL (old pava)':<26} {total_old*1e3:8.3f} ms")
    print(f"    of which _pava_nodes     {t_pava_old*1e3:8.3f} ms  "
          f"{t_pava_old/total_old*100:5.2f}%")
    print(f"    _pava_nodes new          {t_pava_new*1e3:8.3f} ms  "
          f"({t_pava_old/t_pava_new:.2f}x)")
    print(f"    fit stage old/new        {t_fit_old*1e3:.3f} / "
          f"{t_fit_new*1e3:.3f} ms  ({t_fit_old/t_fit_new:.2f}x)")
    saved = t_pava_old - t_pava_new
    print(f"    window saving            {saved*1e3:8.3f} ms  "
          f"{saved/total_old*100:5.2f}% of window")
    total_fused = total_old - t_crop - t_sample + t_fused
    print(f"    crop+sample fused        {t_fused*1e3:8.3f} ms  "
          f"({(t_crop + t_sample)/t_fused:.2f}x vs dense crop+sample)")
    print(f"    TOTAL (fused path)       {total_fused*1e3:8.3f} ms  "
          f"({total_old/total_fused:.2f}x vs dense-stage total)")

pava._pava_nodes = NEW_PAVA
print("\nSTAGE PROFILE DONE")
