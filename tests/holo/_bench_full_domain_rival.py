"""Full-domain cold-search gate rerun + rival diagnosis (bench, not pytest).

Reruns the complete-domain C3 cold-search measurement recorded in
docs/RECEIVE-DESIGN.md section 12.1 item 2 (the pre-final-hoist 312-page run
whose exact clean winner was refused by the inherited rival bar at mismatch
0.176) on CURRENT code, and diagnoses the selected rival.

MEASUREMENT ONLY: no gate, bar, floor, or budget is changed here.

Two modes:

  --mode historical   Exact reconstruction of the excised qualification
                      harness src/holo/receive/qualification/
                      full_cold_profile.py (present at commits 2079676 and
                      e3026f1^; removed by the kiss cleanup).  Fixture: the
                      c3-r0550@2240x1536 row, target page = domain//2,
                      a 200x200-cell patch of V1ReferenceField values at
                      cell origin (640, 512), all-ones mask, the synthetic
                      deterministic amplitude field of the excised
                      _e022_cold_hoist._patch, correlate_patch under the
                      PROVISIONAL_V1_PLACEMENT_POLICY cold budget.

  --mode survey       The production-path variant: an ideal 600-dpi render
                      of the target page (real compose_page_cells pilot
                      field; deterministic stand-in fountain symbols), a
                      128-cell fragment cut at cell (640, 512) pasted on a
                      16-cell paper margin canvas exactly as
                      tests/holo/test_placement_null_battery.py builds one
                      (support covers the printed fragment ONLY - the paper
                      margin is not claimed as search support), placed via
                      place_survey with word_budget=None (forcing cold)
                      over the complete page domain.

Usage:
  PYTHONPATH=src env/bin/python bench_full_domain_rival.py \
      --mode historical --pages 312 --top 12
"""
from __future__ import annotations

import argparse
import resource
import sys
import time

import numpy as np
from scipy import ndimage

from holo.devices.profiles import make_spec
from holo.format.descriptor import FormatSpec
from holo.gen.compose import cells_to_dots, compose_page_cells
from holo.gen.emit import METADATA_VERSION
from holo.receive.place import place_survey
from holo.receive.placement.defaults import PROVISIONAL_V1_PLACEMENT_POLICY
from holo.receive.placement.geometry import (
    SegmentSample,
    make_address_patch,
)
from holo.receive.placement.model import (
    AffinePose,
    CandidateScore,
    PlacementConfig,
    PoseSegment,
    PoseWindow,
)
from holo.receive.placement.reference import V1ReferenceField, overlap_slices
from holo.receive.placement.search import (
    ScoreMemo,
    correlate_patch,
    parity_mask,
)
from holo.receive.scan import open_capture
from holo.receive.survey import (
    PayloadSurvey,
    SupportMask,
    SurveyDiagnostics,
    SurveyRegion,
)

_DPI = 600.0
_PAPER = np.uint8(245)
_INK = np.uint8(35)
_TRUTH_ORIGIN = (640, 512)      # the excised harness' fixed cell origin
_HISTORICAL_SHAPE = (200, 200)  # the excised harness' patch span
_SURVEY_SPAN_CELLS = 128        # the null-battery fragment span
_SURVEY_MARGIN_CELLS = 16       # the null-battery paper margin


def _rss_mib() -> float:
    rss = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return rss / (1024.0 * 1024.0) if sys.platform == "darwin" else rss / 1024.0


def _patch(bits: np.ndarray, mask: np.ndarray):
    """Verbatim from the excised _e022_cold_hoist._patch (e3026f1^)."""
    bits = np.asarray(bits, np.uint8)
    mask = np.asarray(mask, bool)
    yy, xx = np.indices(bits.shape)
    amplitude = (
        0.55 + ((17 * yy + 31 * xx) % 29) / 37.0
    ).astype(np.float32)
    evidence = (1.0 - 2.0 * bits.astype(np.float32)) * amplitude
    pose = AffinePose(
        (0.0, 0.0), ((1.0, 0.0), (0.0, 1.0)),
        (0.5, 0.5), 1.0, 0.0,
    )
    segment = PoseSegment(
        PoseWindow(0, 0, (0, 0), bits.shape),
        pose,
        int(mask.sum()),
        1.0,
        (1.0, 1.0),
        0.0,
    )
    means = np.where(bits > 0, 25.0, 235.0).astype(np.float32)
    return make_address_patch(SegmentSample(
        segment, means, mask, bits, evidence, 130.0,
    ))


def _fmt_candidate(row: CandidateScore) -> str:
    return (
        f"page={row.page:3d} origin=({row.origin_yx[0]:5d},"
        f"{row.origin_yx[1]:5d}) rot={row.rot_k} "
        f"search={row.search_mismatch:.4f} valid={row.validation_mismatch:.4f} "
        f"errs={row.search_errors}/{row.validation_errors} "
        f"support={row.search_support}/{row.validation_support} "
        f"z={row.soft_z:8.3f} passes={row.passes} route={row.route}"
    )


def _diagnose(
    label: str,
    row: CandidateScore,
    truth_page: int,
    truth_origin: tuple[int, int],
    fragment_shape: tuple[int, int],
    provider: V1ReferenceField,
    bits: np.ndarray,
    mask: np.ndarray,
) -> None:
    """Print the identity/overlap/alignment story for one candidate."""
    spec = provider.spec
    page_shape = tuple(spec.layout.cells_yx)
    reference = provider.page(row.page)
    rot_shape = (
        fragment_shape if row.rot_k % 2 == 0 else fragment_shape[::-1]
    )
    print(f"  -- {label}: {_fmt_candidate(row)}")
    same_page = row.page == truth_page
    same_rot = row.rot_k == 0
    delta = (
        row.origin_yx[0] - truth_origin[0],
        row.origin_yx[1] - truth_origin[1],
    )
    tile_alias = same_page and same_rot and all(d % 64 == 0 for d in delta)
    print(
        f"     same_page={same_page} same_rot={same_rot} "
        f"delta_cells={delta} delta_mod64=({delta[0] % 64},{delta[1] % 64}) "
        f"pure_64cell_tile_alias={tile_alias}"
    )
    slices = overlap_slices(row.origin_yx, rot_shape, page_shape)
    if slices is None:
        print("     no page overlap at all")
        return
    page_y, page_x, frag_y, frag_x = slices
    overlap_shape = (page_y.stop - page_y.start, page_x.stop - page_x.start)
    full_area = rot_shape[0] * rot_shape[1]
    overlap_area = overlap_shape[0] * overlap_shape[1]
    keep = np.rot90(np.asarray(mask, bool), row.rot_k)
    selected = reference.sites[page_y, page_x] & keep[frag_y, frag_x]
    n_sites = int(selected.sum())
    search_par = parity_mask(
        selected.shape, (page_y.start, page_x.start), 0)
    n_search = int((selected & search_par).sum())
    n_valid = n_sites - n_search
    print(
        f"     overlap={overlap_shape[0]}x{overlap_shape[1]} cells "
        f"({overlap_area}/{full_area} = {overlap_area / full_area:.3f} of the "
        f"footprint; overhang clipped {1 - overlap_area / full_area:.3f}) "
        f"sites={n_sites} (search={n_search} validation={n_valid})"
    )
    # Hard mismatch on the overlapped sites (both parities).
    hard = np.rot90(np.asarray(bits, np.uint8), row.rot_k)
    expected = reference.values[page_y, page_x][selected]
    observed = hard[frag_y, frag_x][selected]
    errors = int(np.count_nonzero(observed != expected))
    print(
        f"     hard mismatch over all overlapped sites: {errors}/{n_sites}"
        f" = {errors / n_sites:.4f}" if n_sites else "     no sites"
    )
    if n_sites:
        expected_search = errors * n_search / n_sites
        search_errors = int(np.count_nonzero(
            (observed != expected) & (selected & search_par)[selected]))
        print(
            f"     parity split of those errors: search {search_errors}"
            f"/{n_search} = {search_errors / max(n_search, 1):.4f} "
            f"(uniform split would predict {expected_search:.1f}), "
            f"validation {errors - search_errors}/{n_valid} = "
            f"{(errors - search_errors) / max(n_valid, 1):.4f}"
        )
        # Per-tile-pair hard distances over the overlapped sites: the d=27
        # code-distance argument binds each FULL 100-site word pair; partial
        # fringe tiles and the parity subset are outside its reach.
        tile_rows: list[str] = []
        wrong = observed != expected
        site_yy, site_xx = np.nonzero(selected)
        abs_y = site_yy + page_y.start
        abs_x = site_xx + page_x.start
        tile_ids = (abs_y // 64) * 1000 + (abs_x // 64)
        for tile_id in np.unique(tile_ids):
            in_tile = tile_ids == tile_id
            tile_rows.append(
                f"t({tile_id // 1000},{tile_id % 1000}):"
                f"{int(wrong[in_tile].sum())}/{int(in_tile.sum())}"
            )
        print("     per-tile-pair distances (errors/sites, page tiles): "
              + " ".join(tile_rows))
    # Site-pattern alignment: fraction of the rival's selected sites which
    # land on cells that are THEMSELVES pilot sites of the fragment (the v1
    # site pattern is page-invariant and 64-periodic).  Non-aligned sites
    # read payload/zero cells of the fragment, not pilot bits.
    truth_sites = provider.page(truth_page).sites[
        truth_origin[0]:truth_origin[0] + fragment_shape[0],
        truth_origin[1]:truth_origin[1] + fragment_shape[1],
    ]
    frag_sites_rot = np.rot90(truth_sites, row.rot_k)
    aligned = int(
        (selected & frag_sites_rot[frag_y, frag_x]).sum())
    if n_sites:
        print(
            f"     site-pattern alignment: {aligned}/{n_sites} = "
            f"{aligned / n_sites:.3f} of selected sites read fragment "
            f"pilot cells (rest read payload-region cells)"
        )
    # Spatial overlap with the true placement footprint on the page.
    if same_page:
        ty0, tx0 = truth_origin
        ty1, tx1 = ty0 + fragment_shape[0], tx0 + fragment_shape[1]
        oy0 = max(page_y.start, ty0)
        ox0 = max(page_x.start, tx0)
        oy1 = min(page_y.stop, ty1)
        ox1 = min(page_x.stop, tx1)
        shared = max(0, oy1 - oy0) * max(0, ox1 - ox0)
        print(
            f"     footprint shared with the true placement: "
            f"{shared}/{full_area} = {shared / full_area:.3f}"
        )


def run_historical(n_pages: int, top: int) -> int:
    spec = make_spec("c3-r0550", "default")
    if n_pages > spec.max_pages:
        raise SystemExit(f"row caps the domain at {spec.max_pages} pages")
    pages = tuple(range(n_pages))
    target_page = n_pages // 2
    origin = _TRUTH_ORIGIN
    shape = _HISTORICAL_SHAPE
    provider = V1ReferenceField(spec)
    reference = provider.page(target_page)
    bits = reference.values[
        origin[0]:origin[0] + shape[0],
        origin[1]:origin[1] + shape[1],
    ]
    if bits.shape != shape:
        raise SystemExit("profile window does not fit the selected format")
    mask = np.ones(shape, bool)
    patch = _patch(bits, mask)
    config = PlacementConfig()
    budgets, _word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        spec, pages, 0, config
    )
    print(
        f"historical mode: {spec.spec_id} pages={len(pages)} "
        f"target_page={target_page} origin={origin} shape={shape}"
    )
    print(
        f"cold budget: max_hypotheses={budgets.cold.max_hypotheses} "
        f"min_support={budgets.cold.min_support}/parity "
        f"gate(search<{budgets.cold.gate.search_true}, "
        f"rival>{budgets.cold.gate.rival_decoy}, "
        f"gap>={budgets.cold.gate.minimum_gap}, "
        f"validation<{budgets.cold.gate.validation_true})"
    )
    memo = ScoreMemo(provider)
    started = time.perf_counter()
    result = correlate_patch(
        patch, provider, pages, budgets.cold, memo,
        sample_key=0, config=config,
    )
    wall = time.perf_counter() - started
    exact = (
        result.best is not None
        and result.best.page == target_page
        and result.best.origin_yx == origin
        and result.best.rot_k == 0
    )
    rival = result.rival
    status = (
        "PASS" if result.accepted and exact
        else "BLOCKED" if exact and not result.accepted
        else "FAIL"
    )
    print(
        f"{status} full-domain-cold: pages={len(pages)} "
        f"H={result.hypotheses} accepted={result.accepted} "
        f"reason={result.reason} exact_winner={exact} "
        f"wall={wall:.3f}s max_rss={_rss_mib():.1f}MiB"
    )
    if result.best is not None:
        print(f"  winner : {_fmt_candidate(result.best)}")
    if rival is not None:
        print(f"  rival  : {_fmt_candidate(rival)}")
        gap = rival.search_mismatch - (
            result.best.search_mismatch if result.best else 0.0)
        print(
            f"  rival bar: mismatch {rival.search_mismatch:.4f} "
            f"{'>' if rival.search_mismatch > budgets.cold.gate.rival_decoy else '<='}"
            f" {budgets.cold.gate.rival_decoy} (decoy bar), "
            f"gap {gap:.4f} "
            f"{'>=' if gap >= budgets.cold.gate.minimum_gap else '<'}"
            f" {budgets.cold.gate.minimum_gap}"
        )
    ranked = sorted(
        result.runner_ups, key=lambda row: -row.soft_z)[:top]
    print(f"  top {len(ranked)} runner-ups by soft z "
          f"(of {len(result.runner_ups)} retained):")
    for index, row in enumerate(ranked):
        print(f"   {index:2d}. {_fmt_candidate(row)}")
    if rival is not None:
        _diagnose(
            "selected rival", rival, target_page, origin, shape,
            provider, patch.bits, patch.mask,
        )
    for index, row in enumerate(ranked[:3]):
        if rival is not None and (
                row.page, row.origin_yx, row.rot_k
        ) == (rival.page, rival.origin_yx, rival.rot_k):
            continue
        _diagnose(
            f"runner-up #{index}", row, target_page, origin, shape,
            provider, patch.bits, patch.mask,
        )
    print(f"final max_rss={_rss_mib():.1f}MiB wall={wall:.3f}s "
          f"memo_requests={memo.requests} memo_hits={memo.hits}")
    return 0 if (result.accepted and exact) else 2 if exact else 1


def _render_page(spec: FormatSpec, page: int) -> np.ndarray:
    """Ideal 600-dpi render of one production page.

    The pilot/address field is the exact page-`page` format field.  The
    payload region carries deterministic stand-in symbols (seeded RNG, test
    side only): placement scores only pilot sites, and the payload texture
    merely feeds pose fitting.
    """
    rng = np.random.default_rng(20260731)
    symbols = rng.integers(
        0, 2, size=(spec.tiles_per_page, spec.symbol_bits), dtype=np.uint8)
    cells = compose_page_cells(
        spec, page, symbols, k_total=1024, version=METADATA_VERSION)
    dots = cells_to_dots(cells, spec.cell_dots)
    page_x, page_y = spec.layout.page_dots_xy
    raster = np.full((page_y, page_x), _PAPER, np.uint8)
    origin_y, origin_x = spec.layout.origin_dots_yx
    height, width = dots.shape
    raster[origin_y:origin_y + height, origin_x:origin_x + width] = np.where(
        dots != 0, _INK, _PAPER)
    # The null-battery fixture's explicit optical point-spread model.
    return np.ascontiguousarray(ndimage.gaussian_filter(
        raster.astype(np.float32), 0.5
    ))


def run_survey(n_pages: int, top: int) -> int:
    spec = make_spec("c3-r0550", "default")
    if n_pages > spec.max_pages:
        raise SystemExit(f"row caps the domain at {spec.max_pages} pages")
    pages = tuple(range(n_pages))
    target_page = n_pages // 2
    ppc = int(round(_DPI / 600.0)) * spec.cell_dots
    span = _SURVEY_SPAN_CELLS * ppc
    margin = _SURVEY_MARGIN_CELLS * ppc
    origin_cells = _TRUTH_ORIGIN
    print(
        f"survey mode: {spec.spec_id} pages={len(pages)} "
        f"target_page={target_page} fragment={_SURVEY_SPAN_CELLS}c at "
        f"cell {origin_cells} margin={_SURVEY_MARGIN_CELLS}c ppc={ppc}"
    )
    render_started = time.perf_counter()
    page_raster = _render_page(spec, target_page)
    origin_y, origin_x = spec.layout.origin_dots_yx
    y0 = origin_y + origin_cells[0] * ppc
    x0 = origin_x + origin_cells[1] * ppc
    piece = np.array(page_raster[y0:y0 + span, x0:x0 + span], copy=True)
    canvas = np.full(
        (span + 2 * margin, span + 2 * margin),
        float(page_raster.max()), page_raster.dtype)
    canvas[margin:margin + span, margin:margin + span] = piece
    canvas.setflags(write=False)
    print(f"render+cut: {time.perf_counter() - render_started:.3f}s "
          f"canvas={canvas.shape}")
    # Support covers the printed fragment only - the paper margin is not
    # search support, exactly as E021 segmentation would report it
    # (tests/holo/test_placement_null_battery.py).
    support = SupportMask(
        (margin, margin), span, np.ones((1, 1), bool), (span, span))
    raster = open_capture(canvas, _DPI)
    px_per_mm = raster.dpi / 25.4
    survey = PayloadSurvey(
        regions=(SurveyRegion(
            support, support.area_px / (px_per_mm * px_per_mm), 1.0),),
        c_dots=spec.cell_dots,
        cell_pitch_px=raster.dpi * spec.cell_dots / 600.0,
        pitch_votes=(),
        diagnostics=SurveyDiagnostics(None, 1, 1.0, 1, 0, 0, 0),
    )
    config = PlacementConfig()
    budgets, _word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        spec, pages, 0, config
    )
    print(
        f"cold budget: max_hypotheses={budgets.cold.max_hypotheses} "
        f"min_support={budgets.cold.min_support}/parity"
    )
    started = time.perf_counter()
    result = place_survey(
        raster, survey, spec,
        pages=pages, budgets=budgets, word_budget=None,
        config=config, scan_id="bench-full-domain",
    )
    wall = time.perf_counter() - started
    print(
        f"place_survey: wall={wall:.3f}s max_rss={_rss_mib():.1f}MiB "
        f"hypotheses={result.hypotheses_evaluated} "
        f"placements={len(result.placements)} "
        f"unresolved={len(result.unresolved)} "
        f"attempts={len(result.attempts)}"
    )
    provider = V1ReferenceField(spec)
    exit_code = 1
    for attempt in result.attempts:
        print(
            f"  attempt window={attempt.window.window_id} "
            f"depth={attempt.window.depth} outcome={attempt.outcome} "
            f"routes={attempt.attempted_routes} reason={attempt.reason!r}"
        )
        if attempt.candidate is not None:
            print(f"    best  : {_fmt_candidate(attempt.candidate)}")
        if attempt.rival is not None:
            print(f"    rival : {_fmt_candidate(attempt.rival)}")
    accepted = [row for row in result.placements if not row.redundant]
    for placed in accepted:
        row = placed.candidate
        exact = (
            row.page == target_page and row.rot_k == 0
        )
        print(
            f"  ACCEPTED patch={placed.patch_id} route={placed.route} "
            f"{_fmt_candidate(row)} page_origin={placed.segment.page_origin_yx}"
            f" (target page hit={exact})"
        )
        if exact:
            exit_code = 0
    # Diagnose every cold rival that sat under the decoy bar.  The truth
    # anchor is the attempt's own best candidate (its sampled-window origin,
    # not the nominal fragment cell), and the fragment is approximated by
    # the cell-domain truth under that window; the mismatch numbers of
    # record are the ones the receiver printed above.
    for attempt in result.attempts:
        if attempt.rival is None or attempt.candidate is None:
            continue
        best = attempt.candidate
        if best.page != target_page:
            continue
        window_shape = tuple(attempt.window.shape_yx_cells)
        truth_bits = provider.page(best.page).values[
            best.origin_yx[0]:best.origin_yx[0] + window_shape[0],
            best.origin_yx[1]:best.origin_yx[1] + window_shape[1],
        ]
        _diagnose(
            f"window {attempt.window.window_id} rival",
            attempt.rival, best.page, best.origin_yx,
            truth_bits.shape,
            provider,
            truth_bits,
            np.ones(truth_bits.shape, bool),
        )
    print(f"final max_rss={_rss_mib():.1f}MiB wall={wall:.3f}s")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("historical", "survey"), default="historical")
    parser.add_argument("--pages", type=int, default=312)
    parser.add_argument("--top", type=int, default=12)
    arguments = parser.parse_args()
    if arguments.mode == "historical":
        return run_historical(arguments.pages, arguments.top)
    return run_survey(arguments.pages, arguments.top)


if __name__ == "__main__":
    raise SystemExit(main())
