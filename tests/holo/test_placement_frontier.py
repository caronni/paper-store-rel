"""v0.23 frontier scheduler: deferred cold + wave-front + nearest anchors.

The synthetic case is the measured motivation for deferral: a two-window
fragment where one window's word slots are surgically corrupted (15 flipped
word-site cells per interior tile — beyond t=13, so Stage A refuses, but
only ~15% site mismatch, well inside the chain gate).  The sequential
ladder would spend a full cold search on that window before its neighbour's
cheap word decode existed; the frontier defers it and chains it for 49
memoized scores.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo.format import pilots
from holo.receive.place import place_survey
from holo.receive.placement.defaults import PROVISIONAL_V1_PLACEMENT_POLICY
from holo.receive.placement.model import PlacementConfig
from holo.receive.scan import open_capture
from holo.receive.survey import (
    PayloadSurvey,
    SupportMask,
    SurveyDiagnostics,
    SurveyRegion,
)

import _roundtrip_fixture as roundtrip

SPAN_Y_CELLS = 128
SPAN_X_CELLS = 288
FLIPS_PER_TILE = 15


@pytest.fixture(scope="module")
def fixture():
    return roundtrip._build_fixture()


def _fragment(fixture, *, damage: bool):
    """A 128x288-cell fragment; optionally word-kill its left 200 cells."""
    spec = fixture.spec
    ppc = int(round(roundtrip._DPI / 600.0)) * spec.cell_dots
    cells_yx = np.asarray(spec.layout.cells_yx)
    assert cells_yx[0] >= 32 + SPAN_Y_CELLS
    assert cells_yx[1] >= 32 + SPAN_X_CELLS
    origin_dots = spec.layout.origin_dots_yx
    y0 = int(origin_dots[0] + 32 * ppc)
    x0 = int(origin_dots[1] + 32 * ppc)
    piece = np.array(
        fixture.raster[
            y0:y0 + SPAN_Y_CELLS * ppc, x0:x0 + SPAN_X_CELLS * ppc],
        copy=True)

    if damage:
        # Whiten (erase to paper) a 3x3-cell neighbourhood around the first
        # FLIPS_PER_TILE canonical word sites whose PRINTED bit is dark, for
        # every tile INTERSECTING the left window's page span (x < 32+200).
        # Erased-dark sites read light under any aperture and add no decoy
        # texture, so exactly FLIPS_PER_TILE deterministic word errors per
        # interior tile: beyond t=13 (no slot decodes) while the ~15%
        # word-site mismatch stays inside the chain gate (<0.20).
        word_cells = pilots.word_site_cells_yx(spec.family_seed)
        tiles_y = range(0, (32 + SPAN_Y_CELLS + 63) // 64)
        tiles_x = range(0, (32 + 200 + 63) // 64)
        peak = float(fixture.raster.max())
        for ty in tiles_y:
            for tx in tiles_x:
                counter = spec.tile_counter(0, ty, tx)
                values = pilots.word_values(spec.seed, (counter,))[0]
                dark = [
                    cell for cell, bit in zip(word_cells, values) if bit
                ][:FLIPS_PER_TILE]
                for site_y, site_x in dark:
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            fy = ty * 64 + int(site_y) + dy - 32
                            fx = tx * 64 + int(site_x) + dx - 32
                            if not (0 <= fy < SPAN_Y_CELLS
                                    and 0 <= fx < SPAN_X_CELLS):
                                continue
                            piece[
                                fy * ppc:(fy + 1) * ppc,
                                fx * ppc:(fx + 1) * ppc] = peak

    margin = 16 * ppc
    canvas = np.full(
        (SPAN_Y_CELLS * ppc + 2 * margin, SPAN_X_CELLS * ppc + 2 * margin),
        float(fixture.raster.max()), fixture.raster.dtype)
    canvas[margin:margin + SPAN_Y_CELLS * ppc,
           margin:margin + SPAN_X_CELLS * ppc] = piece
    canvas.setflags(write=False)
    raster = open_capture(canvas, roundtrip._DPI)
    support = SupportMask(
        (margin, margin), max(SPAN_Y_CELLS, SPAN_X_CELLS) * ppc,
        np.ones((1, 1), bool),
        (SPAN_Y_CELLS * ppc, SPAN_X_CELLS * ppc))
    return raster, support


def _place(fixture, fragment, pages=(0,), progress=None):
    raster, support = fragment
    spec = fixture.spec
    px_per_mm = raster.dpi / 25.4
    survey = PayloadSurvey(
        regions=(SurveyRegion(
            support, support.area_px / (px_per_mm * px_per_mm), 1.0),),
        c_dots=spec.cell_dots,
        cell_pitch_px=raster.dpi * spec.cell_dots / 600.0,
        pitch_votes=(),
        diagnostics=SurveyDiagnostics(None, 1, 1.0, 1, 0, 0, 0),
    )
    budgets, word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        spec, pages, 0, PlacementConfig())
    return place_survey(
        raster, survey, spec, pages=pages, budgets=budgets, word_budget=word,
        progress=progress)


def _cold_calls(result) -> int:
    return sum(
        "correlation" in row.attempted_routes for row in result.attempts)


def test_clean_fragment_never_defers_or_colds(fixture) -> None:
    result = _place(fixture, _fragment(fixture, damage=False))
    accepted = [row for row in result.placements if not row.redundant]
    assert accepted
    assert _cold_calls(result) == 0
    assert all(
        row.route in ("word", "chain") for row in result.placements)


def test_word_killed_window_chains_instead_of_cold(fixture) -> None:
    """The deferral save: 1 sequential-ladder cold becomes 0.

    v0.33: the rest-first regime binds only above the §3.5 price
    threshold, so this pin runs at a two-page domain (a one-page domain
    deliberately inverts — see the companion test below).
    """
    result = _place(fixture, _fragment(fixture, damage=True), pages=(0, 1))
    accepted = [row for row in result.placements if not row.redundant]
    assert len(accepted) >= 2, [row.reason for row in result.unresolved]
    routes = sorted(row.route for row in accepted)
    assert "word" in routes, routes
    assert "chain" in routes, routes
    assert _cold_calls(result) == 0, [
        (row.outcome, row.attempted_routes) for row in result.attempts]
    # The chained placement really is the damaged-slot window: its route
    # record shows word was attempted and failed before deferral.
    chained = [row for row in accepted if row.route == "chain"]
    chained_attempts = [
        row for row in result.attempts
        if row.patch_id in {p.patch_id for p in chained}]
    assert any("word" in row.attempted_routes for row in chained_attempts)
    assert all(row.candidate.page == 0 for row in accepted)


def test_cold_sweep_emits_count_bounded_heartbeats(fixture) -> None:
    """v0.33 D14c: a running cold labels its silent span with at most 64
    ``address.cold_progress`` heartbeats per sweep, each carrying the page
    total and ordinal; a headless run constructs no callback at all."""
    events: list[tuple[str, dict[str, object]]] = []

    def progress(name, details):
        events.append((name, {row.name: row.value for row in details}))

    result = _place(
        fixture, _fragment(fixture, damage=True), pages=(0,),
        progress=progress)
    assert _cold_calls(result) >= 1
    opens = [row for name, row in events if name == "address.cold_open"]
    beats = [row for name, row in events if name == "address.cold_progress"]
    assert opens and beats
    assert len(beats) <= 64 * len(opens)
    # One declared page: ceil(1/64) stride puts exactly one heartbeat at
    # the sweep's first page.
    assert all(row == {"address.pages": 1, "address.page_ordinal": 1}
               for row in beats)


def test_single_page_domain_prices_cold_before_rest_sweep(fixture) -> None:
    """PLACEMENT-IMPROVEMENTS §3.5 (v0.33): at one declared page the cold
    is cheaper than a remaining-slot sweep, so the deferred window colds
    first — and still accepts everything the rest-first regime would."""
    result = _place(fixture, _fragment(fixture, damage=True), pages=(0,))
    accepted = [row for row in result.placements if not row.redundant]
    assert len(accepted) >= 2, [row.reason for row in result.unresolved]
    routes = sorted(row.route for row in accepted)
    assert "correlation" in routes, routes
    assert _cold_calls(result) >= 1
    assert all(row.candidate.page == 0 for row in accepted)
