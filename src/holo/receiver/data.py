from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import numpy as np

WindowId = tuple[str, int, int, tuple[int, int, int, int]]
RegionKey = tuple[str, int, int]
LaneKey = tuple[str, int]
TileKey = tuple[int, int, int]
CertKey = tuple[int, int, int, str]
RefineBasis = tuple[tuple, ...]
StoodPoses = tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class Level:
    index: int
    ppc: Fraction
    scale: Fraction
    shape_px: tuple[int, int]
    label: str


@dataclass(frozen=True)
class Capture:
    capture_id: str
    path: Path
    dpi: float
    shape_px: tuple[int, int]
    channels: int
    platen_backing: float
    levels: tuple[Level, ...]
    plane_dir: Path
    #: Declared with `--dpi-force`: the survey takes the declared pitch
    #: and votes none (2026-10-02, the c2-at-4800 harmonic).  Re-declared
    #: every run like the rest of Capture, never a snapshot fact.
    dpi_forced: bool = False


@dataclass(frozen=True)
class PlaneRaster:
    capture_id: str
    level_index: int
    plane: str
    path: Path
    shape_px: tuple[int, int]

    def open(self) -> np.ndarray:
        return np.load(self.path, mmap_mode="r")


@dataclass(frozen=True)
class Region:
    capture_id: str
    region_index: int
    origin_yx: tuple[int, int]
    step_px: int
    cells: np.ndarray
    extent_px: tuple[int, int]
    area_mm2: float
    median_tensor_score: float


@dataclass(frozen=True)
class CaptureSurvey:
    capture_id: str
    regions: tuple[Region, ...]
    pitch_class: Fraction | None
    pitch_px: float | None


@dataclass(frozen=True)
class Window:
    window_id: tuple[str, int, int, tuple[int, int, int, int]]
    capture_id: str
    level_index: int
    region_index: int
    extent_cells: tuple[int, int, int, int]
    supported_cells: int
    depth: int
    lane_depth: int
    ordinal: int
    #: The window this one is a QUARTER of, and the whole parent/child
    #: relation (2026-09-21): a subdivision mints four of these, the
    #: window fold links them both ways, and a resume rebuilds the
    #: relation from the snapshot instead of losing it.  A planned
    #: window has none.  Defaulted, so a snapshot written before the
    #: field existed reads back unchanged.
    parent: tuple[str, int, int, tuple[int, int, int, int]] | None = None


@dataclass(frozen=True)
class LatticeSeed:
    capture_id: str
    level_index: int
    region_index: int
    rows: np.ndarray
    support_cells: int
    window_ordinal: int = 0


#: A commutative CELL MERGE POLICY, not a staleness mechanism: max by
#: support, tie-broken on the producing window ordinal.  It replaced a
#: `rows.tobytes()` tie-break -- determinism without a byte-compare
#: (D6 addendum 8c).
def lattice_seed_ordinal(seed: LatticeSeed) -> tuple[int, int]:
    return (int(seed.support_cells), -int(seed.window_ordinal))


@dataclass(frozen=True)
class Placement:
    window_id: tuple[str, int, int, tuple[int, int, int, int]]
    capture_id: str
    level_index: int
    region_index: int
    patch_ordinal: int
    page: int
    rot_k: int
    page_origin_yx: tuple[int, int]
    native_affine: tuple[float, float, float, float, float, float]
    pitch_px: float
    route: str
    #: The addressed cells, WINDOW-LOCAL and int16: non-negative, never
    #: past the window extent (200 cells is the largest this record has
    #: seen).  The width is named because this one array is 94-98% of a
    #: fact snapshot's bytes (measured 2026-09-13).  `place.local_cells_of`
    #: is the only producer and refuses a coordinate int16 cannot hold;
    #: every reader coerces before arithmetic, because a page origin
    #: added to these does NOT fit int16.  Snapshots written before that
    #: measurement carry int64 and still read back as int64 -- the width
    #: is a storage choice, not format law, and every archive resumes.
    local_cells_yx: np.ndarray
    quality: float = 0.0
    refine_basis: RefineBasis = ()
    #: Every geometry this window has already stood at, canonical
    #: (`refine.pose_key`), oldest first, the standing one excluded.
    #: Written only by `refine.revised_placement`; read only by the
    #: refinement guard (RULINGS.md D4).  Not in `placement_ordinal`.
    stood_affines: StoodPoses = ()


ROUTE_REFINE: str = "refine"

#: The basis entry naming the page field a refinement was fitted through.
#: A certificate key is `(page, ty, tx, stream_id)` and its first element
#: is an int, so the string here is what tells the two apart inside one
#: basis tuple.  The SCHEMA owns it because the ordinal below reads it.
FIELD_BASIS_KEY: str = "field"


#: The page field revision a standing basis was fitted through.  Zero
#: where the basis names no field, which is what a pose refined before
#: the page had one carries -- and the same number
#: `color_region.field_revision_of` gives that page.
def basis_field_revision(basis: RefineBasis) -> int:
    for key in basis:
        if key[0] == FIELD_BASIS_KEY:
            return int(key[1])
    return 0


#: The placement cell's ordinal, lexicographic: an adopted revision
#: outranks its parent, then the page field its basis was fitted through,
#: then the certificates it read (marker excluded), then held-out quality.
#: FIELD-MAJOR OVER THE COUNT (R6): two fields are two sampling
#: geometries, so neither depth nor loss compares across them and the
#: held-out gate is the proof; K carries no marker and reads 0.  Argument
#: in docs/API.md's cell-class law 14, which `store_folds._adopts` gates.
def placement_ordinal(placement: Placement) -> tuple[int, int, int, float]:
    basis = placement.refine_basis
    return (int(placement.route == ROUTE_REFINE),
            basis_field_revision(basis),
            sum(1 for key in basis if key[0] != FIELD_BASIS_KEY),
            -float(placement.quality))


@dataclass(frozen=True)
class WindowEvidence:
    window_id: tuple[str, int, int, tuple[int, int, int, int]]
    capture_id: str
    level_index: int
    region_index: int
    patch_ordinal: int
    page: int
    page_cells_yx: np.ndarray
    scores: np.ndarray
    reference_values: np.ndarray
    knots: np.ndarray
    probs: np.ndarray
    n_search: int
    marginal_llr: np.ndarray
    printed_llr: np.ndarray
    accepted: bool
    refusal_reason: str
    heldout_logloss: float | None
    ctx_adopted: bool


@dataclass(frozen=True)
class RegionCtx:
    capture_id: str
    level_index: int
    region_index: int
    offsets: np.ndarray
    adopted: bool
    reason: str
    validation_logloss: float | None = None


def region_ctx_ordinal(ctx: RegionCtx) -> tuple[int, float]:
    if not ctx.adopted:
        return (0, -float("inf"))
    if ctx.validation_logloss is None:
        return (1, -float("inf"))
    return (1, -float(ctx.validation_logloss))


@dataclass(frozen=True)
class OwnedPageEvidence:
    capture_id: str
    level_index: int
    page: int
    cells_yx: np.ndarray
    printed_llr: np.ndarray
    owner_window: np.ndarray


@dataclass(frozen=True)
class WindowRows:
    patch_ordinal: int
    window_id: tuple[str, int, int, tuple[int, int, int, int]]
    page: int
    #: The same window-local cells as `Placement.local_cells_yx`, but
    #: int64: this bundle is built per job from a `RegionWindow` and
    #: never stored, so it carries the width its readers do arithmetic
    #: in rather than the width the snapshot pays for.
    local_cells_yx: np.ndarray
    page_cells_yx: np.ndarray
    scan_points_yx: np.ndarray
    states: np.ndarray
    furniture_kind: np.ndarray
    known_component_bits: np.ndarray
    known_component_mask: np.ndarray
    heldout_logloss: float | None


@dataclass(frozen=True)
class PlaneField:
    """One printed face's registration field for one ink plane.

    Keyed by (page, plane) and by nothing else: the displacement is the
    printer's, frozen at print time, so the capture, the decimation
    level, the lane and the scrap are axes the evidence POOLS over
    (docs/PAGE-FIELD-DESIGN.md §2.2).  `delta_dots_xy` is (ty, tx, 2) in
    printed dots along the PAGE axes, `support` the pooled weight per
    tile and `uncertainty_dots` how much of the prior's ignorance the
    evidence has NOT removed at that tile, carried on the prior's own
    scale in dots (design §2.4 — it is not a posterior deviation, and
    it is 18.1x one on the behaviour suite's stimulus).  Nothing gates
    on either: a reader samples where the field says and the
    uncertainty is what a sparse page says out loud about what it does
    not know.

    `ordinal` is the page's EVIDENCE REVISION at solve time (I12): the
    number the store advances on every placement birth, change or
    removal and every certificate, summed over the collections this
    solve read.  It orders two solves of one page — a later one saw
    everything the standing one did — and it is what a consumer records
    to know whether it owes a refit.
    """

    page: int
    plane: int
    delta_dots_xy: np.ndarray
    support: np.ndarray
    uncertainty_dots: np.ndarray
    n_observations: int
    n_captures: int
    ordinal: int


@dataclass(frozen=True)
class FieldObservations:
    """One capture's measurements of one page's field, as parallel arrays.

    A row is RAW (design §2.5, W8 R-C): one measurement of one plane on
    one tile, the displacement against the pose it was taken through, in
    printed dots along the PAGE axes.  Nothing is subtracted from it —
    the gauge is a constraint on the page's FIELDS and each window's own
    pose error is a parameter of the solve, so neither belongs in the
    evidence.  `measured_xy` is a flag per AXIS: an axis nobody measured
    is marked unmeasured and enters no sum, which is not the statement a
    measured zero makes (I13).

    `window` indexes this fact's own window table — `window_ids` and
    `window_generation` — which is the memo key: a row is copied into
    the next collection while its (tile, plane) is still measured
    through THAT window at THAT pose generation from the same template
    source.  Derived, never durable: a resume re-declares the
    placements, which re-arm the collection.

    `revision` is the store's evidence revision for this (capture, page)
    when the collection was made (I12).  It is the fact's ordinal, so a
    collection whose inputs really changed is never mistaken for one
    already done, and a page whose last window left publishes an EMPTY
    table under a higher revision rather than leaving its rows standing.
    """

    capture_id: str
    page: int
    tile_code: np.ndarray
    plane: np.ndarray
    delta_dots_xy: np.ndarray
    measured_xy: np.ndarray
    weight: np.ndarray
    source: np.ndarray
    window: np.ndarray
    window_ids: tuple[WindowId, ...]
    window_generation: np.ndarray
    revision: int


@dataclass(frozen=True)
class EvidenceRevision:
    """One (capture, page)'s evidence revision, carried across a resume.

    The revision counts EVENTS and events do not survive the facts they
    left behind: a placement refined five times is snapshotted once, and
    a placement that has left page 0 leaves page 0 no trace at all.  A
    resumed run that recounted would come back LOWER than the run it
    resumed, and the collection it restores beside it carries the higher
    number — so every fresh collection would be outranked by a restored
    one.  This fact is the number itself, written at RunDone and folded
    back at the front of the resume (design §2.7, I12).
    """

    capture_id: str
    page: int
    revision: int


def plane_field_ordinal(field: PlaneField) -> tuple[int]:
    """The page's evidence revision at solve time.

    A later solve read everything the standing one did and more, so the
    revision alone orders them; an identical revision is the same
    evidence and the fold is a no-op.
    """
    return (int(field.ordinal),)


def field_observations_ordinal(
        observations: FieldObservations) -> tuple[int]:
    """The store's evidence revision this collection was made at.

    Monotone by construction (I12), so a re-collection that reads a page
    one window SMALLER is still strictly newer and is adopted, where a
    count of what the table contains would have refused it and left rows
    measured through a window that has gone (the review's F5).
    """
    return (int(observations.revision),)


@dataclass(frozen=True)
class ColorEvidenceRow:
    capture_id: str
    level_index: int
    patch_ordinal: int
    page: int
    page_cells_yx: np.ndarray
    values: np.ndarray
    heldout_logloss: float


@dataclass(frozen=True)
class ColorCtxPopulation:
    """One lane's context-fit population, published so the captures that
    observe the same printed page at the same rung can be pooled.  Labels
    are format truth plus this run's certificates — never ground truth."""
    capture_id: str
    level_index: int
    page: int
    rung: str
    keys_pyx: np.ndarray
    scores: np.ndarray
    states: np.ndarray
    kinds: np.ndarray
    bins: np.ndarray
    search: np.ndarray


@dataclass(frozen=True)
class PooledColorCtx:
    page: int
    rung: str
    offsets: np.ndarray
    applied: np.ndarray
    adopted: bool
    reason: str
    n_lanes: int
    n_rows: int
    validation_logloss: float | None = None


def pooled_ctx_ordinal(cell: PooledColorCtx) -> tuple[int, int, int, float]:
    """Quality first (a usable head beats a refusal), then the evidence
    it was fitted on, then the pooled validation loss."""
    evidence = (int(cell.n_lanes), int(cell.n_rows))
    if not cell.adopted or cell.validation_logloss is None:
        return (int(cell.adopted), *evidence, -float("inf"))
    return (1, *evidence, -float(cell.validation_logloss))


@dataclass(frozen=True)
class Certificate:
    page: int
    ty: int
    tx: int
    stream_id: str
    user_bits: np.ndarray
    source: str


@dataclass(frozen=True)
class AttemptFact:
    page: int
    ty: int
    tx: int
    stream_id: str
    stage: str
    outcome: str
    n_informative: int
    n_iters: int
    syndrome_ok: bool | None
    crc_ok: bool | None
    components: tuple[tuple[str, int], ...] = ()
    #: The tile-lane GENERATION this attempt's evidence was read at --
    #: the store's counter, read by `prepare` and reported back by the
    #: job (the cell-class law: the store stamps, the plugin reports
    #: what it read).  A verdict whose generation is behind the lane's
    #: is stale: the assembled cut has moved since it was decoded.
    #: Defaulted so every hand-built fact and every archived call site
    #: stays valid; AttemptFact is not snapshotted, so no state schema
    #: moves with it.
    generation: int = 0


class IntegrityError(Exception):
    pass


@dataclass(frozen=True)
class RegionMark:
    region_index: int
    origin_yx: tuple[int, int]
    shape_cells: tuple[int, int]
    pitch_px: float | None
    support_cells: int
    cells: np.ndarray | None = None
    step_px: int = 0


@dataclass(frozen=True)
class RunOpen:
    format_id: str
    pages: int
    tiles_yx: tuple[int, int]
    stream_ids: tuple[str, ...]
    n_captures: int
    workers: int
    #: The row's `Family` value ("k", "cmy7", "cmy8", "cmy"), recorded
    #: 2026-10-12 so the readout gates its field rows on the family
    #: and not on the stream count (cmy7 is colour with one stream).
    family: str
    pitch_in: float = 0.0
    display_id: str = ""
    #: The effective `HOLO3_COLOR_ROW_ADOPT` mode (store_folds; the
    #: shipped fold is "last").  Recorded because an environment
    #: variable changes the receiver and leaves no trace in argv.
    color_row_adopt: str = "last"


@dataclass(frozen=True)
class CaptureOpen:
    capture: str
    dpi: float
    shape_yx: tuple[int, int]
    channels: int
    duplicate: bool
    ordinal: int = 0
    levels_ppc: tuple[str, ...] = ()


@dataclass(frozen=True)
class SnapshotReplayed:
    """What a `--resume` fold brought in, once, at fold time.

    Pure accounting for diag: the engine appends it and never reads it.
    Without it a resumed run's status counts only this run's own tile
    outcomes and prints CERTIFIED 0 over a verified close.
    """
    facts: tuple[tuple[str, int], ...]
    certified: int


@dataclass(frozen=True)
class SurveyDone:
    capture: str
    n_regions: int
    regions: tuple[RegionMark, ...]
    pitch_class: str | None
    preview: np.ndarray | None
    preview_decim: int


@dataclass(frozen=True)
class SurveyPitchFallback:
    """A survey that voted no printed pitch, working at the declared one.

    Ruled 2026-09-04 (`retirement_docs-2026-09/RULINGS.md` D5): a tie
    or an unsnappable measurement used to leave the capture with no
    frames and no windows, silently, on exactly the fragment material
    that votes worst.  A CONTRADICTING vote still refuses the run.

    `cause` says which door led here: a tie or no snap (D5), a vote
    finer than the row with the declared lattice present on the page,
    or `--dpi-force` (both 2026-10-02, the c2-at-4800 harmonic).
    """
    capture: str
    declared_pitch_in: str
    pitch_px: float
    n_regions: int
    cause: str = "tie or no snap"


@dataclass(frozen=True)
class PoseCommitted:
    capture: str
    level_index: int
    region_index: int
    extent_cells: tuple[int, int, int, int]
    page: int
    route: str
    mismatch: float
    accepted: bool
    page_origin_yx: tuple[int, int] = (0, 0)
    rot_k: int = 0
    pitch_px: float = 0.0
    native_affine: tuple[float, float, float, float, float, float] = (
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    shape_yx: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class WindowSettled:
    capture: str
    level_index: int
    region_index: int
    extent_cells: tuple[int, int, int, int]
    state: str


@dataclass(frozen=True)
class CalibrateAdopted:
    capture: str
    pool_id: str
    adopted: bool
    reason: str


@dataclass(frozen=True)
class TileOutcome:
    page: int
    ty: int
    tx: int
    stream_id: str
    source: str
    result: str
    bp_iters: int


@dataclass(frozen=True)
class WorkerSeated:
    """A row taking a NEW seat at a (stage, cost) it was not last at.

    One event per row, not per push: a wake that re-seats at the same
    price is the common case and would drown the log.  Generic since
    2026-09-21 — it was `WindowScheduled`, place only, and every reader
    that wants windows filters `plugin == "place"`.
    """
    plugin: str
    subject: object
    stage: str
    cost: int


@dataclass(frozen=True)
class WorkerRetired:
    """A row leaving the frontier for good, and WHY.

    `cause` is whatever this row's `descriptor.retire` returned — its
    own vocabulary, which the engine tallies and never reads.  For place
    it is the clause of `place_sched.place_retire_cause`: `placed` (an
    accepted pose) or `exhausted` (the ladder ran out).  `done_covered`
    (done-geometry) was a third cause until 2026-10-03; the done gate
    suppresses through the row's stage since, because its projection
    can shrink under a pose revision, and records before that date
    carry it.  It has no default: a retirement with no reason is what
    the record already had.
    """
    plugin: str
    subject: object
    cause: str


@dataclass(frozen=True)
class EngineStat:
    queued: tuple[tuple[str, int], ...]
    inflight: int
    stale_skips: int
    retired: int
    attempts_hist: tuple[tuple[str, int], ...]
    wakes: int = 0
    inflight_jobs: tuple[tuple[str, object, str], ...] = ()
    consult_cpu_s: float = 0.0
    # `WorkerRetired.cause` tallied: the run's own answer to "did the
    # done gate bite?", so nobody has to walk the event file to find out
    retire_causes: tuple[tuple[str, int], ...] = ()


@dataclass
class StatBoard:
    value: EngineStat | None = None


@dataclass(frozen=True)
class WordOutcome:
    page: int
    ty: int
    tx: int
    errors: int
    sites: int


@dataclass(frozen=True)
class AddressCoverage:
    page: int
    tiles: tuple[tuple[int, int, bytes], ...]


@dataclass(frozen=True)
class Contradiction:
    """Two placements of one capture claim different printed addresses
    for the same paper cells — the disagreement v1 quarantined on.

    DIAGNOSTIC ONLY (ruling D1, 2026-09-04: keep the alarm, not the
    gate): nothing is excluded, refused, repriced or unplaced, and the
    certificate gate stays the only bar.  Each side's full pose rides
    its own `PoseCommitted`, which this event joins by window id.
    """
    capture: str
    window_id: tuple[str, int, int, tuple[int, int, int, int]]
    standing_window_id: tuple[str, int, int, tuple[int, int, int, int]]
    route: str
    standing_route: str
    page: int
    standing_page: int
    page_origin_yx: tuple[int, int]
    standing_page_origin_yx: tuple[int, int]
    rot_k: int
    standing_rot_k: int
    tile_yx: tuple[int, int]
    standing_tile_yx: tuple[int, int]
    overlap_cells: tuple[int, int, int, int]
    delta_cells_yx: tuple[float, float]


@dataclass(frozen=True)
class JobDone:
    plugin: str
    subject: object
    cost: int
    cpu_s: float
    n_certificates: int
    n_poses: int
    n_words: int


#: The `group_*` tuples are the decoder's per-column-group counts in
#: group order (`fountain.BlockStatus`): rows from the tiles carrying the
#: group, its rank, solved.  Every group needs `needed` rows.  Empty means
#: the producer gave none (a hand-built row), never zero rows.
@dataclass(frozen=True)
class CloseBlockRow:
    stream_id: str | None
    block: int
    have: int
    needed: int
    rank: int | None
    solved: bool
    short: int
    groups_open: int
    n_groups: int
    group_rows: tuple[int, ...] = ()
    group_rank: tuple[int | None, ...] = ()
    group_solved: tuple[bool, ...] = ()


@dataclass(frozen=True)
class CloseCheck:
    certified: int
    symbols_used: int
    k_total: int | None
    metadata_rank: int
    metadata_n_unique: int
    blocks: tuple[CloseBlockRow, ...]
    status: str
    blocks_counting: bool = False


@dataclass(frozen=True)
class RunDone:
    status: str
    payload_sha256: str | None
    n_bytes: int | None
    certified: int


@dataclass(frozen=True)
class FieldPlaneRow:
    """One plane's solved field as the diag viewer sees it.

    There is no publish verdict to carry: the solve produces what the
    readers sample through (I8), so every plane of a solved page has a
    field and the honest report is the measurement itself.  A plane no
    template could be built for reads `known` False — zero everywhere
    with zero support, which is unknown and not a measured zero (I13).

    `delta_grid_dots_xy` (gy, gx, 2), `magnitude_grid_dots` (gy, gx) and
    `has_data` (gy, gx) are the per-tile field BLOCK-POOLED to a bounded
    grid (see `plugins.fields.DIAG_GRID_MAX`).  The magnitude is pooled
    from the per-tile |delta| rather than taken from the pooled vector,
    because the two are different statistics: a block straddling a sign
    change averages its VECTORS toward zero while every tile in it
    carries a real displacement.

    `median_uncertainty_dots` is that per-tile uncertainty's median
    over the tiles that carry evidence — the number beside the value
    that says how much of this field is measured, on the prior's scale
    rather than the posterior's (design §2.4).

    `held` is a plane the gauge holds AT THE POSE (`lib/field_gauge`,
    coefficient 0: cmy's C, R7): its field is zero by name and not a
    measurement, and its rows inform only the window nuisances, so its
    support is no statement about its field (2026-10-12).
    """

    plane: int
    plane_name: str
    median_delta_dots: float
    median_uncertainty_dots: float
    support_tiles: int
    n_observations: int
    n_captures: int
    known: bool
    delta_grid_dots_xy: np.ndarray
    magnitude_grid_dots: np.ndarray
    has_data: np.ndarray
    held: bool = False


@dataclass(frozen=True)
class FieldSolved:
    """One page's field solve: every plane, and who disagrees with it.

    Diag-only — nothing reads it back into the decode.  Bounded by
    construction: three planes x a grid capped on both axes, so the
    event's arrays cost at most 22,464 bytes whatever the tile matrix
    (13,338 at sheet I's 53x37, 351 on a 3x3 page).

    `residual_by_capture_plane` is `(capture_id, plane, energy,
    expected, count)` PER CAPTURE AND PLANE, never summed across planes
    first (design §2.6, W8 R-F): 100 explained C rows, 100 explained M
    rows and one Y row a dot out give Y a ratio of 8 and the summed
    report 0.040, so healthy word-plane evidence hides exactly the
    poorly supported Y this diagnostic exists to expose (review F11).

    `revision` is the page's evidence revision this solve was fitted at,
    which replaces the residual-energy trigger the row used to report
    (I12): the page solves because its evidence moved, and this is the
    number that moved.

    `passes` is how many reweighted solves the robust loss took to reach
    its fixed point — the worse of the two axes — and `converged` says
    whether it reached one inside `plane_field.IRLS_MAX_PASSES`.  A
    capped fit IS published (the objective is convex, so its last
    iterate is its best one) and this pair is the only place that says
    so, which is why they travel with the solve and not with a log line.
    """

    page: int
    planes: tuple[FieldPlaneRow, ...]
    residual_by_capture_plane: tuple[
        tuple[str, int, float, float, int], ...]
    tiles_yx: tuple[int, int]
    block_tiles_yx: tuple[int, int]
    revision: int
    passes: int
    converged: bool


Event = (
    RunOpen
    | CaptureOpen
    | SnapshotReplayed
    | SurveyDone
    | SurveyPitchFallback
    | PoseCommitted
    | WindowSettled
    | WorkerSeated
    | WorkerRetired
    | EngineStat
    | WordOutcome
    | AddressCoverage
    | Contradiction
    | CalibrateAdopted
    | TileOutcome
    | JobDone
    | CloseCheck
    | RunDone
    | FieldSolved
)


@dataclass(frozen=True)
class PluginRow:
    plugin: str
    jobs: int = 0
    cpu_seconds: float = 0.0
    certificates: int = 0
    poses: int = 0
    words: int = 0


@dataclass(frozen=True)
class JobResult:
    facts: tuple[object, ...]
    events: tuple[object, ...]
    cpu_s: float


@dataclass(frozen=True)
class RunResult:
    status: str
    payload: bytes | None
    payload_sha256: str | None
    certified: int
    plugin_rows: tuple[PluginRow, ...] = field(default_factory=tuple)


#: Which detector the black-and-white refinement adoption gate scores.
#: `context` is v1's `_fixed_detector_logits` (RULINGS D3, 2026-09-04);
#: `marginal` is the holo2 ruling spec 08 carried and reproduces the
#: pre-D3 tree exactly.
REFINE_GATE_CONTEXT: str = "context"
REFINE_GATE_MARGINAL: str = "marginal"
REFINE_GATES: tuple[str, ...] = (REFINE_GATE_CONTEXT, REFINE_GATE_MARGINAL)


@dataclass(frozen=True)
class DecodeRequest:
    scans: tuple[Path, ...]
    dpis: tuple[float, ...]
    format_ref: str
    max_pages: int | None
    workers: int
    complete: bool
    no_close: bool
    diag_port: int | None
    run_dir: Path
    pooled_color_context: bool = True
    resume: Path | None = None
    snapshot_every_s: float | None = 1800.0
    refine_gate: str = REFINE_GATE_CONTEXT
    #: Per scan, True where it was declared with `--dpi-force`; empty
    #: means none was (the engine pads with False to one per scan).
    dpi_forced: tuple[bool, ...] = ()
