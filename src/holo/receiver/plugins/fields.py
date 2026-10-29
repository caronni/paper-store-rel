"""The `fields` row: solve one printed face's per-plane registration
field from every observation any capture has made of it.

Subject is the PAGE.  The displacement is the printer's, put there
before the sheet was ever paper and frozen at print time, so it is a
function of page position and of nothing else — not of the capture, the
decimation level, the lane, the platen placement, the scrap or the
cascade generation (docs/PAGE-FIELD-DESIGN.md §2.2).  Those are the axes
the evidence POOLS over, and pooling is what recovers signal per-lane
fitting throws away: on sheet H the per-lane Y fits read 0.21-0.27 dots
and the 22-lane pooled fit reads 0.374 at r² 0.91.

The measuring is `plugins/fields_collect.py`'s and the estimator is
`lib/plane_field.py`'s; what lives here is the scheduling decision, and
W8 makes it one sentence (design §2.7, R-D): the page solves whenever
its EVIDENCE REVISION has moved, and publishes only if the field moved.
No statistic decides.  The measured cost is the whole argument, and W8
moved it by two orders of magnitude: the run's solving against the run's
collecting was 0.107 s against 1,921.6 on sheet H (1:18,000) and 0.035
against 97.7 on sheet J's one capture (1:2,800), and on THIS solve — the
joint fit over every plane and window — sheet J's load 1a reads 6.165 s
against 89.9 (1:14.6, measured three times over the wave at 1:12 to
1:16).  Six to eight per cent of a collection is still the cheap side,
so a rule that skips solves optimises the cheap half while risking the
expensive direction, which is not solving when the field should have
moved; a page an order of magnitude larger would put that back on the
table, and the dense factor is cubic in `2 * n_tiles + n_windows`.  RETIRED with that: the residual-energy trigger in
all three of its forms, on its own arithmetic (against a standing zero
field, 1, 10 or 1,000 exact observations at +0.4 dots all give the same
ratio, 1.28, under the margin that shipped — no amount of agreeing
evidence could cross it).

Duplicate publication is suppressed by comparing the solved field to
the standing one, which is a fact about the OUTPUT and needs no model of
the input; only a publication wakes a reader, so the colour head refits
once per REAL field change and never once per certificate (§2.7).

There is no publish floor, no precision gate, no clip and no adoption
granularity (I8): what the solve produces is what every reader samples
through.  Uncertainty, support and the per-(capture, plane) residuals
are REPORTED, in the one event this row emits, and gate nothing.
"""

from __future__ import annotations

import time

import numpy as np

from ..data import (FieldObservations, FieldPlaneRow, FieldSolved,
                    JobResult, PlaneField)
from ..descriptor import (
    FactKey,
    Job,
    KEY_FIELD_OBS,
    PluginDescriptor,
    Subject,
)
from ..format.identity import CMY_PLANE_ORDER, HW_DPI, MM_PER_INCH
from ..lib import evidence, field_gauge, plane_field
from .color_sites import cell_dots_of

PLUGIN: str = "fields"
STAGE_SOLVE: str = "solve"
#: Flat, and cheap.  The solve pools arrays the collection already paid
#: for; there is no ordinal because a second solve is not more expensive
#: than the first and nothing is served by making it queue later
#: (design §2.7).
SOLVE_COST: int = 40
PRICES: tuple[tuple[str, int], ...] = ((STAGE_SOLVE, SOLVE_COST),)

N_PLANES: int = 3

#: Printed dots per millimetre: the PRINTER's number, named where the
#: printer is named.  `lib/` names no printer, so design §2.4's two
#: physical lengths — the smoothing length and the fade length — reach
#: the solve as this scale and never by an import.
DOTS_PER_MM: float = HW_DPI / MM_PER_INCH

#: Retired as a publish floor with the gate it belonged to (I8) and kept
#: for one reader outside this tree: `analyzer/field2` reports its own
#: parametric fits against production's recorded quarter dot
#: (`field2.py:276`, `:283`, `:842`).  The analyzer's own page-field
#: phase deletes that reader and this constant with it.
MIN_DELTA_DOTS: float = 0.25

#: Diag only: the field is per TILE and a real sheet has thousands, and
#: the viewer draws one arrow per block, so the event carries the field
#: block-pooled to at most this many blocks per axis — 3 planes x 24 x
#: 24 x (2 float32 vector + 1 float32 magnitude + 1 bool) = 22,464 bytes.
DIAG_GRID_MAX: int = 24


def block_size(n_tiles: int, cap: int = DIAG_GRID_MAX) -> int:
    """Tiles per diag block: the smallest that keeps the grid within
    `cap` on this axis."""
    return max(1, -(-max(1, int(n_tiles)) // max(1, int(cap))))


def pool_field(delta_dots_xy: np.ndarray, support: np.ndarray,
               block_yx: tuple[int, int],
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Block-pool one plane's tile field for the diag event.

    Returns the pooled delta VECTOR (gy, gx, 2), the pooled |delta|
    MAGNITUDE (gy, gx), and the has-data flag.  Both poolings average
    over the block's tiles that CARRY EVIDENCE, and a block with none of
    those is flagged rather than averaged to zero — the pane paints
    those as blind spots, and a blind spot averaged into a delta would
    read as a measurement.

    The magnitude is pooled in its own right because `hypot` of the
    pooled vector is a different number: opposing deltas inside one
    block cancel toward zero there while every tile of it carries a real
    displacement.  The band shades on the magnitude, so its shading
    answers a question about the tiles and not about their average.
    """
    delta = np.asarray(delta_dots_xy, np.float64)
    live = np.asarray(support, np.float64) > 0.0
    tiles_y, tiles_x = live.shape
    block_y, block_x = (max(1, int(v)) for v in block_yx)
    rows = np.arange(tiles_y) // block_y
    columns = np.arange(tiles_x) // block_x
    grid_y, grid_x = int(rows[-1]) + 1, int(columns[-1]) + 1
    code = (rows[:, None] * grid_x + columns[None, :]).ravel()
    weight = np.bincount(code, weights=live.ravel().astype(np.float64),
                         minlength=grid_y * grid_x)
    grid = np.zeros((grid_y, grid_x, 2), np.float32)
    for axis in (0, 1):
        total = np.bincount(code,
                            weights=(delta[..., axis] * live).ravel(),
                            minlength=grid_y * grid_x)
        grid[..., axis] = (total
                           / np.maximum(weight, 1.0)).reshape(grid_y, grid_x)
    magnitude = np.bincount(
        code, weights=(np.hypot(delta[..., 0], delta[..., 1]) * live).ravel(),
        minlength=grid_y * grid_x)
    return (grid,
            (magnitude / np.maximum(weight, 1.0)
             ).reshape(grid_y, grid_x).astype(np.float32),
            (weight > 0.0).reshape(grid_y, grid_x))


def plane_row(plane: int, solution: object, block_yx: tuple[int, int],
              held: bool = False) -> FieldPlaneRow:
    delta = np.asarray(solution.delta_dots_xy)[plane]
    support = np.asarray(solution.support, np.float64)[plane]
    uncertainty = np.asarray(solution.uncertainty_dots, np.float64)[plane]
    live = support > 0.0
    grid, magnitude, has_data = pool_field(delta, support, block_yx)
    return FieldPlaneRow(
        plane=plane, plane_name=CMY_PLANE_ORDER[plane],
        median_delta_dots=float(plane_field.median_magnitude_dots(delta,
                                                                  support)),
        median_uncertainty_dots=float(np.median(uncertainty[live]))
        if live.any() else 0.0,
        support_tiles=int(np.count_nonzero(live)),
        n_observations=int(np.asarray(solution.n_observations)[plane].sum()),
        n_captures=int(np.asarray(solution.n_captures)[plane].max()),
        known=bool(np.asarray(solution.plane_known)[plane]),
        delta_grid_dots_xy=grid, magnitude_grid_dots=magnitude,
        has_data=has_data, held=held)


def residual_rows(solution: object, captures: tuple[str, ...],
                  ) -> tuple[tuple[str, int, float, float, int], ...]:
    """Per capture AND plane: energy, expectation, observations.

    Never summed across planes first (design §2.6, W8 R-F): healthy,
    abundant word-plane evidence hides exactly the poorly supported Y
    this diagnostic was introduced to expose — 100 explained C rows, 100
    explained M rows and one Y row a dot out give Y a ratio of 8 and the
    summed report 0.040 (review F11).  The table names a FOOTING
    disagreeing with the page rather than with itself, and now says on
    which plane.
    """
    return tuple(
        (captures[capture], int(plane), float(row.energy),
         float(row.expected), int(row.count))
        for (capture, plane), row
        in sorted(solution.residual_by_capture_plane.items()))


def solved_event(page: int, solution: object,
                 captures: tuple[str, ...],
                 word: tuple[int, ...] = field_gauge.CM_WORD_PLANES,
                 ) -> FieldSolved:
    """The one event a solve emits: every plane, every capture, the
    revision the page's evidence stood at, and what the fit cost to
    reach.

    Everything but the page and the capture names comes off the solution
    — the grid IS the fields' own shape, the revision is the label they
    were fitted under, and the passes are the ones the robust loss
    actually took — so the event cannot disagree with the fit it reports
    on.  A fit stopped at the pass ceiling is published like any other
    and carries `converged` False, which is the only place a reader can
    learn it (the field itself looks the same).  `word` is the solve's
    gauge, which names the plane it holds at the pose (`held`).
    """
    tiles_yx = solution.tiles_yx
    block_yx = (block_size(tiles_yx[0]), block_size(tiles_yx[1]))
    held = field_gauge.held_planes(word)
    return FieldSolved(
        page=int(page),
        planes=tuple(plane_row(plane, solution, block_yx, held[plane])
                     for plane in range(N_PLANES)),
        residual_by_capture_plane=residual_rows(solution, captures),
        tiles_yx=tiles_yx, block_tiles_yx=block_yx,
        revision=int(solution.revision), passes=int(solution.passes),
        converged=bool(solution.converged))


def page_observations(store: object,
                      page: int) -> tuple[evidence.Rows, tuple[str, ...]]:
    """Every capture's observations of one page, in one table.

    The capture column is the POSITION of the capture id in the sorted
    list beside it, and the window column is renumbered ACROSS the
    page's collections: the estimator needs only to tell captures and
    windows apart — to split the residual and to give each window its
    own nuisance — and two collections that both numbered their windows
    from zero would otherwise share one.  That the field is not keyed by
    capture is exactly why the id itself does not travel into the solve.

    EVERY standing observation, not the ones since the last solve: a
    collection carries a row forward until the pose or the template
    under it moves (`fields_collect.standing_row`), so "since the last
    solve" is not a set this store can name — the rows that did not move
    are the same rows.
    """
    facts = store.field_observations(page)
    parts: list[evidence.Rows] = []
    base = 0
    for index, fact in enumerate(facts):
        window = np.asarray(fact.window, np.int64)
        generation = np.asarray(fact.window_generation, np.int64)
        n = window.shape[0]
        parts.append(evidence.Rows(
            capture=np.full(n, index, np.int64),
            page=np.full(n, int(page), np.int64),
            tile_code=np.asarray(fact.tile_code, np.int64),
            plane=np.asarray(fact.plane, np.int64),
            delta_dots_xy=np.asarray(fact.delta_dots_xy, np.float64),
            measured_xy=np.asarray(fact.measured_xy, bool),
            weight=np.asarray(fact.weight, np.float64),
            source=np.asarray(fact.source, np.int64),
            window=window + base,
            pose_generation=(generation[window] if window.size
                             else np.zeros(0, np.int64))))
        base += len(fact.window_ids)
    return (evidence.Rows.concat(*parts),
            tuple(fact.capture_id for fact in facts))


def moved(standing: tuple[PlaneField | None, ...],
          delta_dots_xy: np.ndarray, support: np.ndarray,
          held: tuple[bool, ...] = (False,) * N_PLANES) -> bool:
    """Is this PAGE's field a different statement from the one standing?

    ONE decision for the page and never one per plane (R1).  The gauge
    ties the planes (`lib/field_gauge`: cmy8's makes M exactly -C, cmy's
    holds C at exactly zero), so the three fields are
    one joint statement: publishing the planes that moved and leaving
    the others standing mixes two solves in the durable set and breaks
    that identity — the external review's counterexample published C
    alone and left the durable pair reading C+M = 0.1999 dots where
    every solve reads exactly 0.  So the answer is the page's, and
    `solve_job` publishes all three facts or none of them.

    The page moved when (a) no field stands for it, a first solve
    having nothing to agree with; or (b) some plane's support PRESENCE
    mask changed, which is where I13's transitions live — a supported
    plane losing its last evidence publishes zero support and the
    prior's own uncertainty although its displacement never left zero,
    and an empty plane that gains evidence publishes too; or (c) the
    largest per-tile displacement change over ALL THREE planes is past
    `plane_field.FIELD_NOISE_DOTS`, the measurement's own resolution
    and the anchor tier's search step.

    (c) is a threshold and not exact array equality: the lead's ruling
    of 2026-09-12 overrides the external handoff's R1, which asked for
    equality here.  A publication is what wakes a reader — a PlaneField
    fold arms `(plane_field, page, plane)` and the colour head
    subscribes to all three planes of its page, per WINDOW — so
    publishing every solve re-arms the page's whole colour fleet over a
    move no reader could sample, which is the churn design §2.7
    forbids — measured on the sheet-J ten-capture run, 105 solves after
    120 collections with 83 % of the run's CPU in the rows a
    publication wakes (`PAGE-FIELD-PLAN.md` §5.2).

    What the threshold costs is a BOUNDED STALENESS: the standing field
    lags the latest solve by at most FIELD_NOISE_DOTS on every tile,
    and the review's own 0.1999-dot counterexample sits inside that
    bound (it publishes here anyway, on its support mask).

    Metadata alone never publishes — counts, uncertainty and support
    MAGNITUDES are reported beside the field and no reader samples
    through them (I8).  Nor does a plane the gauge holds at the pose
    (`held`, cmy's C, 2026-10-12): its field is zero by name and its
    support mask counts the nuisance-only rows that reach it, so a
    change there is no new statement about any field.
    """
    if any(field is None for field in standing):
        return True
    #: Three standing planes from two solves is the shape the per-plane
    #: rule left behind (a snapshot from before R1); one publication heals
    #: it, so a mixed set counts as no field standing.
    if len({int(field.ordinal) for field in standing}) > 1:
        return True
    delta = np.asarray(delta_dots_xy, np.float64)
    live = np.asarray(support, np.float64) > 0.0
    for plane, field in enumerate(standing):
        if held[plane]:
            continue
        if not np.array_equal(np.asarray(field.support, np.float64) > 0.0,
                              live[plane]):
            return True
    shift_dots = max(
        float(np.max(np.abs(np.asarray(field.delta_dots_xy, np.float64)
                            - delta[plane]), initial=0.0))
        for plane, field in enumerate(standing))
    return shift_dots > plane_field.FIELD_NOISE_DOTS


def solve_job(page: int, rows: evidence.Rows, captures: tuple[str, ...],
              tiles_yx: tuple[int, int], cell_dots: int, revision: int,
              standing: tuple[PlaneField | None, ...],
              word: tuple[int, ...]) -> JobResult:
    """One solve for the page, over every plane and every window at once,
    under the gauge of `word`, the planes the row's word prints.

    Every plane is solved; a plane no template could be built for reads
    unknown, zero everywhere with zero support, which is the honest
    answer and the one its readers should sample at (I6, I13).  The
    publication is the PAGE's, one decision for all three planes under
    the solve's own revision (`moved`, R1), so a solve over evidence
    that says the same thing as before wakes nobody (§2.7) and one that
    says something new never leaves a reader holding two solves' planes
    at once.  The window nuisances stay on the solution object, where
    the diagnostics read them in this same process: a nuisance that
    reached the fact stream would be a per-window field with another
    name (design §2.6).
    """
    started = time.thread_time()
    solution = plane_field.solve(
        rows, tiles_yx, cell_dots=cell_dots, revision=revision,
        prior=plane_field.default_prior(cell_dots,
                                        dots_per_mm=DOTS_PER_MM),
        word=word)
    delta = np.asarray(solution.delta_dots_xy, np.float64)
    support = np.asarray(solution.support, np.float64)
    uncertainty = np.asarray(solution.uncertainty_dots, np.float64)
    facts: tuple[PlaneField, ...] = ()
    if moved(standing, delta, support, field_gauge.held_planes(word)):
        facts = tuple(
            PlaneField(page=int(page), plane=plane,
                       delta_dots_xy=delta[plane], support=support[plane],
                       uncertainty_dots=uncertainty[plane],
                       n_observations=int(
                           np.asarray(solution.n_observations)[plane].sum()),
                       n_captures=int(
                           np.asarray(solution.n_captures)[plane].max()),
                       ordinal=int(solution.revision))
            for plane in range(N_PLANES))
    event = solved_event(page, solution, captures, word)
    return JobResult(facts, (event,), time.thread_time() - started)


def prepare_fields(store: object, subject: Subject,
                   stage: str) -> Job | None:
    page = int(subject)
    rows, captures = page_observations(store, page)
    if not captures:
        return None
    tiles_yx = store.row.tiles_yx
    cell_dots = cell_dots_of(store.row)
    revision = store.page_evidence_revision(page)
    standing = store.page_plane_fields(page)
    word = field_gauge.word_planes(store.row.word_states[1])

    def job() -> JobResult:
        return solve_job(page, rows, captures, tiles_yx, cell_dots,
                         revision, standing, word)

    return job


def _fields_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    return (int(fact.page),)


def _fields_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    return ((KEY_FIELD_OBS, int(subject)),)


def _fields_eligible(store: object, subject: Subject) -> bool:
    """The page's evidence has moved since the field was fitted (I12).

    One integer against another: the revision the standing collections
    were made at, against the revision the standing field carries.  No
    statistic, and no per-plane rule — the solve is one problem over
    every plane and every window, so the question is asked of the page.
    """
    page = int(subject)
    if not store.field_observations(page):
        return False
    return store.page_evidence_revision(page) != store.field_revision(page)


def _fields_stage(store: object, subject: Subject) -> str | None:
    return STAGE_SOLVE


def _fields_cost(store: object, subject: Subject, stage: str,
                 attempts: int, last_cost: int) -> int:
    return SOLVE_COST


def _fields_retire(store: object, subject: Subject) -> str | None:
    """Never — the solve is not gated on the payload's done geometry.

    It was, until 2026-09-08, and the gate silently ate the row: the
    engine asks `retire` FIRST, before the version floor and before
    eligibility, so a page whose last tile certified while its
    collection was in flight retired the solve at the very pop that
    collection's own fact had BORN it on.  Measured on the field-frame
    arms of the clean colour sim, where the collection is the run's last
    job and the page has been complete for 43 seconds when it lands:
    `fields.collect` 1, `fields` 0, no `FieldSolved`, `plane_fields`
    empty, and the 66-76 CPU-seconds the collection cost thrown away.

    The done grid is a statement about the PAYLOAD — no tile is left to
    certify — and for the collector that is the whole story, so
    `fields_collect` keeps the gate and stops measuring.  For the solve
    it is not: what a solve publishes is also this run's report of the
    page's registration (the pane, `plane_fields`, the per-capture
    residuals), and a collection already paid for has to be turned into
    one.  Nothing runs away: the row is born only by a collection,
    subscribes only to collections, and is eligible only while the
    page's evidence revision is ahead of its field's — and the
    collector, which retires on the done grid, is the only source of
    either.  So a finished page solves at most once more — 0.01 s on
    that sim, 0.107 s on sheet H (§2.7's own measurement) — and then
    goes quiet on the version floor.  `color` and `color.pooled_ctx` are
    the same shape and have never retired.
    """
    return None


FIELDS_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="page",
    born_by=(FieldObservations,),
    subjects_of=_fields_subjects,
    reads=_fields_reads,
    eligible=_fields_eligible,
    stage=_fields_stage,
    cost=_fields_cost,
    retire=_fields_retire,
    prepare=prepare_fields,
    produces=(PlaneField,),
    prices=PRICES,
)
