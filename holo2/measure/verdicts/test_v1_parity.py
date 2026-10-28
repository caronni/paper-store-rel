"""VERDICT 2 (run channel): pose for pose against v1, on the same page.

The R4 BEHAVIORAL PIN, distilled from ``test_differential_placement``'s
end-to-end arm to the one sentence H4 W2 has to keep true:

    **The pull model may reach an address any way it likes; it may not
    move the answer.**

Route attribution is FREE TO DIFFER and does — that is the wave. Under
the push era every window of this page was decoded by its own address
word, and no window ever consumed a hint (measured: word 9, chain 0).
Under the pull model the first acceptance PINGS its ring, a pinged window
prices at the ring tier (cost 10) below the word tiers (20/30), so the
frontier grows along its most confident edges and most windows arrive by
a seeded search instead. Both are legal, neither is asserted here.

What IS asserted is that v1's ``place_survey``, run over the SAME survey
(holo2's own support mask and pitch vote, handed to v1 so a difference
cannot be the segmentation's), places the same windows at the same poses:

* the same WINDOW SET is placed on both sides;
* per window, the same PAGE;
* per window, an affine agreeing to within one canonicalisation quantum —
  the tightest claim a rounded record can support, so a v1 term further
  out than this could not have rounded to the term holo2 stored;
* per window, the same TILES observed, with the same per-tile cell counts.

R5, THE ONLY ADMISSIBLE DELTA, is reported before any pose is compared:
v1's first-fit-wins ``lattice_f`` (observed through a read-only wrapper —
without it v1's seed regime is not observable from outside) against
holo2's durable ``LatticeSeedRecord``. A pose delta would be admissible
only where those differ. If this file ever fails, read those three
comparisons FIRST: they are the warrant for calling a pose difference a
defect rather than a different seed.
"""
from __future__ import annotations

from fractions import Fraction

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np

from conftest import PageRun

# --- v1 --------------------------------------------------------------------
from holo.receive import place as v1_place
from holo.receive.placement.defaults import PROVISIONAL_V1_PLACEMENT_POLICY
from holo.receive.placement.model import PlacementConfig as V1Config
from holo.receive.scan import open_capture as v1_open
from holo.receive.survey import (PayloadSurvey, SupportMask as V1Support,
                                 SurveyDiagnostics, SurveyRegion)

# --- holo2 -----------------------------------------------------------------
from holo2.capture import KIND_REGION
from holo2.format import native_cell_pitch_px
from holo2.solve import (KIND_EVIDENCE, parse_evidence_key, parse_window_key,
                         unpack_observed_cells)
from holo2.solve.place_shared import page_affine_terms
from holo2.solve.records import canonical_affine_terms
from holo2.solve.tilemap import StoreIndex

Extent = tuple[int, int, int, int]
WindowKey = tuple[tuple[int, int], tuple[int, int]]
Tile = tuple[int, int, int]

# --------------------------------------------------------------- both sides

@dataclass(frozen=True)
class H2Facts:
    """What holo2's finished state says about geometry and evidence."""

    support: V1Support
    pitch_in_vote: Fraction
    pitch: float
    windows: set[Extent]
    poses: dict[Extent, Any]
    evidence: dict[Extent, dict[Tile, int]]
    #: (source window extent, the four reciprocal terms) per R5 seed.
    seeds: tuple[tuple[Extent, tuple[float, ...]], ...]


def h2_facts(run: PageRun) -> H2Facts:
    """Read the finished state: support, windows, poses, seed, evidence."""
    with run.open() as session:
        store = session.store
        regions = [store.get(key) for key in store.keys()
                   if key.kind == KIND_REGION]
        assert len(regions) == 1, f"{len(regions)} regions: {regions}"
        region = regions[0]
        assert region.pitch_in_vote is not None, "the survey voted no pitch"
        support = V1Support(
            (int(region.support_origin_px[0]),
             int(region.support_origin_px[1])),
            int(region.support_step_px),
            np.asarray(store.read_array(region.support_mask_ref), bool),
            (int(region.support_extent_px[0]),
             int(region.support_extent_px[1])))
        index = StoreIndex.build(store)
        poses: dict[Extent, Any] = {}
        for pose in index.poses.values():
            _f, _r, extent = parse_window_key(pose.window_id)
            # NOT a structural law since W3 (RULING I3, 2026-08-23): a
            # window MAY carry a second committed pose, and which one the
            # tree reads is ``index.live_pose``. What this asserts is a
            # MEASURED fact about run_channel — at COST_REFINE = 200 the
            # cheaper bands never drain while residue remains here, so
            # RF1 commits nothing on this arm and the extent-keyed
            # comparison below is exact. A revision appearing here should
            # fail loudly and be re-pinned against the live pose, never
            # be tolerated by relaxing the map.
            assert extent not in poses, f"two poses for window {extent}"
            poses[extent] = pose
        windows = {parse_window_key(key)[2] for key in store.keys()
                   if key.kind == "window"}
        evidence: dict[Extent, dict[Tile, int]] = {}
        for key in store.keys():
            if key.kind != KIND_EVIDENCE:
                continue
            _f, page, ty, tx, _s, pose_id = parse_evidence_key(key)
            seen = unpack_observed_cells(
                store.read_array(store.get(key).observed_ref), (64, 64))
            _ff, _rr, extent = parse_window_key(index.poses[pose_id].window_id)
            evidence.setdefault(extent, {})[(page, ty, tx)] = int(seen.sum())
        seeds = tuple(
            (parse_window_key(record.source_window_id)[2], tuple(record.rows))
            for record in (store.get(key) for key in store.keys()
                           if key.kind == "seed"))
    return H2Facts(
        support=support, pitch_in_vote=region.pitch_in_vote,
        pitch=float(native_cell_pitch_px(run.capture.dpi,
                                         region.pitch_in_vote)),
        windows=windows, poses=poses, evidence=evidence, seeds=seeds)


def v1_place_survey(run: PageRun, facts: H2Facts, monkeypatch):
    """v1's whole placement over the SAME survey, plus its seed history.

    The wrapper around ``fit_window_pose`` is a READ-ONLY observer: it
    calls the real function and records which window first established the
    region's mutable ``lattice_f`` (v1's first-fit-wins seed, the thing R5
    replaced with a durable per-(footing, region) record). It changes no
    argument and no result.
    """
    spec = run.page.spec
    raster = v1_open(run.capture.path, run.capture.dpi)
    px_per_mm = raster.dpi / 25.4
    support = facts.support
    survey = PayloadSurvey(
        regions=(SurveyRegion(support,
                              support.area_px / (px_per_mm * px_per_mm), 1.0),),
        # ``src/holo``'s OWN survey type, so its own unit: this is the
        # one side that still counts engine dots (C3, RULINGS G4).
        c_dots=spec.cell_dots, cell_pitch_px=facts.pitch, pitch_votes=(),
        diagnostics=SurveyDiagnostics(None, 1, 1.0, 1, 0, 0, 0))
    pages = tuple(run.page.row.page_domain)
    budgets, word_budget = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        spec, pages, 0, V1Config())
    fit = v1_place.fit_window_pose
    seeds: list[tuple[WindowKey, tuple[float, ...]]] = []

    def observed(context, window, *, config):
        before = context.lattice_f
        segment = fit(context, window, config=config)
        if before is None and context.lattice_f is not None:
            seeds.append((v1_window_key(window),
                          tuple(float(term)
                                for term in np.asarray(context.lattice_f
                                                       ).ravel())))
        return segment

    monkeypatch.setattr(v1_place, "fit_window_pose", observed)
    result = v1_place.place_survey(raster, survey, spec, pages=pages,
                                   budgets=budgets, word_budget=word_budget)
    return result, tuple(seeds)


def v1_window_key(window) -> WindowKey:
    """A v1 window in the prepared region's own pixel frame."""
    return ((int(window.origin_yx_px[0]), int(window.origin_yx_px[1])),
            (int(window.shape_yx_cells[0]), int(window.shape_yx_cells[1])))


def h2_window_key(extent: Extent, pitch: float) -> WindowKey:
    """A holo2 window plan in that same frame (``placement._window``)."""
    cy0, cx0, cy1, cx1 = extent
    return ((int(round(cy0 * pitch)), int(round(cx0 * pitch))),
            (cy1 - cy0, cx1 - cx0))


def v1_tile_cells(placed) -> dict[Tile, int]:
    """How many page cells this placement observed, per tile it touched."""
    counts: Counter = Counter()
    page = int(placed.candidate.page)
    for cell_y, cell_x in placed.page_cells_yx:
        counts[(page, int(cell_y) // 64, int(cell_x) // 64)] += 1
    return dict(counts)


# ------------------------------------------------------------- the verdict

def test_the_pull_model_places_exactly_what_v1_places(
        run_channel: PageRun, monkeypatch) -> None:
    """R4: the routes may move; the POSES may not.

    The per-term bar is the CANONICAL EQUALITY below and nothing looser:
    holo2 stores ``canonical_affine_terms`` of what it fitted, so an
    equality against v1's unrounded terms already says every term agrees
    to within half the pose family's quantum. This file used to follow it
    with a full-quantum bound on the same numbers, which no input could
    fail without failing the equality first.
    """
    facts = h2_facts(run_channel)
    result, v1_seeds = v1_place_survey(run_channel, facts, monkeypatch)
    pitch = facts.pitch

    # The survey both sides read is the same survey, by construction —
    # and since C3 (RULINGS G4, 2026-08-22) the two sides state it in
    # DIFFERENT units, which is exactly what makes this worth asserting:
    # holo2's blind survey voted a physical pitch, v1's emitted spec
    # knows a dot count, and they describe one printed cell.
    assert facts.pitch_in_vote == run_channel.page.spec.pitch

    # R5, REPORTED BEFORE ANY POSE IS COMPARED (see the module docstring).
    h2_seeds = facts.seeds
    assert len(v1_seeds) == len(h2_seeds) == 1, (
        f"seed regimes differ: v1 {len(v1_seeds)}, holo2 {len(h2_seeds)}")
    assert v1_seeds[0][0] == h2_window_key(h2_seeds[0][0], pitch), (
        "the two sides seeded the region's lattice from different windows; "
        "a pose delta below would be ADMISSIBLE rather than wrong")
    assert v1_seeds[0][1] == h2_seeds[0][1], "the seed's four terms differ"

    v1_windows = {v1_window_key(attempt.window): attempt
                  for attempt in result.attempts if not attempt.window.depth}
    h2_windows = {h2_window_key(extent, pitch): extent
                  for extent in facts.windows}
    assert set(v1_windows) == set(h2_windows), (
        "the two sides enumerated different windows, so no pose comparison "
        "below means anything")

    placements: dict[WindowKey, list] = {}
    for placed in result.placements:
        placements.setdefault(
            v1_window_key(placed.segment.segment.window), []).append(placed)

    compared = 0
    for key in sorted(v1_windows):
        extent = h2_windows[key]
        pose = facts.poses.get(extent)
        rows = placements.get(key, [])
        assert bool(rows) == (pose is not None), (
            f"window {key}: v1 placed {len(rows)}, holo2 placed "
            f"{pose is not None} — the PLACED SET differs")
        if pose is None:
            continue
        placed = rows[0]
        segment = placed.segment
        terms = page_affine_terms(
            segment.segment.pose,
            (int(segment.segment.window.shape_yx_cells[0]),
             int(segment.segment.window.shape_yx_cells[1])),
            int(segment.rot_k),
            (int(segment.page_origin_yx[0]), int(segment.page_origin_yx[1])))
        assert int(placed.candidate.page) == int(pose.page), f"window {key}"
        assert canonical_affine_terms(terms) == tuple(pose.native_affine), (
            f"window {key}: pose moved\n  v1   {canonical_affine_terms(terms)}"
            f"\n  holo2 {tuple(pose.native_affine)}")
        v1_tiles = v1_tile_cells(placed)
        h2_tiles = facts.evidence.get(extent, {})
        assert sorted(v1_tiles.items()) == sorted(h2_tiles.items()), (
            f"window {key}: the tiles observed (or the cell counts) differ")
        compared += 1

    assert compared == len(v1_windows), (
        f"only {compared} of {len(v1_windows)} windows were placed on both "
        "sides")


def test_the_routes_are_free_to_differ_and_every_pose_is_attributed(
        run_channel: PageRun) -> None:
    """The other half of R4: attribution is provenance, and it is TOTAL.

    MEASURED on this arm, and recorded rather than pinned: the split moved
    from **word 9 / chain 0** under the push model to **word 1 / chain 8**
    under the pull model — one window seeds the page from its own address
    word, its acceptance pings its ring, and every other window arrives
    through the ladder. The poses did not move by so much as a
    canonicalisation quantum (the verdict above). That is the wave's
    route-migration number on a page the word route could have read in
    full, and it is the reason this file asserts poses and not routes.

    Nothing here pins a split — the ruling frees it. What it pins is that
    the census is exhaustive: every committed pose was proposed by a fire
    this run watched, under one of the job's two named ways to an address.
    A route that stopped being recorded would otherwise vanish silently.
    """
    with run_channel.open() as session:
        poses = tuple(StoreIndex.build(session.store).poses.values())
    assert poses
    attributed = Counter(run_channel.routes[pose.resource_key()] for pose in poses)
    assert sum(attributed.values()) == len(poses)
    assert set(attributed) <= {"word", "chain"}, dict(attributed)
    assert "unknown" not in attributed
