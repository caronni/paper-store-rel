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


@dataclass(frozen=True)
class LatticeSeed:
    capture_id: str
    level_index: int
    region_index: int
    rows: np.ndarray
    support_cells: int
    window_ordinal: int = 0


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
    local_cells_yx: np.ndarray
    quality: float = 0.0
    refine_basis: RefineBasis = ()


ROUTE_REFINE: str = "refine"


def placement_ordinal(placement: Placement) -> tuple[int, int, float]:
    return (int(placement.route == ROUTE_REFINE),
            len(placement.refine_basis), -float(placement.quality))


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
    local_cells_yx: np.ndarray
    page_cells_yx: np.ndarray
    scan_points_yx: np.ndarray
    states: np.ndarray
    furniture_kind: np.ndarray
    known_component_bits: np.ndarray
    known_component_mask: np.ndarray
    heldout_logloss: float | None


@dataclass(frozen=True)
class PlaneResidual:
    intercept_xy: tuple[float, float]
    slope_xy: tuple[float, float]
    n_anchors: int


@dataclass(frozen=True)
class PlaneField:
    capture_id: str
    level_index: int
    page: int
    plane: int
    delta_dots_xy: np.ndarray
    support: np.ndarray
    n_certificates: int
    n_sites: int
    residual: float
    median_delta_dots: float


@dataclass(frozen=True)
class PlaneFieldTiers:
    """What each evidence tier contributed to one plane's field.

    An EVENT, not a durable fact: the accounting is for a reader — the
    diag pane, a measurement harness, a report — and the state has no
    business carrying a nested dictionary it would have to version.
    ``tiers`` maps a tier name to its sites, weight mass and measured
    effect (the fit with that tier left out, differenced against the
    joint fit); ``gain_check`` says whether a tier declined and why.
    """

    capture_id: str
    level_index: int
    page: int
    plane: int
    tiers: dict
    gain_check: dict
    n_sites: int
    median_delta_dots: float


def plane_field_ordinal(field: PlaneField) -> tuple[int, float]:
    return (int(field.n_certificates), -float(field.residual))


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
    pitch_in: float = 0.0
    plane_fields: bool = False
    display_id: str = ""


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
class WindowScheduled:
    capture: str
    level_index: int
    region_index: int
    extent_cells: tuple[int, int, int, int]
    stage: str
    cost: int


@dataclass(frozen=True)
class WindowRetired:
    """A place row leaving the frontier for good, and WHY.

    `cause` is the clause of `place_sched.place_retire_cause` that fired:
    `placed` (an accepted pose), `exhausted` (the ladder ran out) or
    `done_covered` (done-geometry — every supported cell of the extent
    already carries a certified tile); `unknown` is the bug name, never
    a clause.  Without it the three are indistinguishable in the record,
    and the done gate — whose only door is this event — cannot be
    counted at all.  It has no default: a retirement with no reason is
    what the record already had.
    """
    capture: str
    level_index: int
    region_index: int
    extent_cells: tuple[int, int, int, int]
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
    # `WindowRetired.cause` tallied: the run's own answer to "did the
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
class JobDone:
    plugin: str
    subject: object
    cost: int
    cpu_s: float
    n_certificates: int
    n_poses: int
    n_words: int


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
class FieldPlaneFit:
    """One plane's registration field as the diag viewer sees it.

    Carries the FITTED measurement whether or not it was published: the
    writer's floors (`plugins.fields.publishable`) refuse a field that is
    real but too small to be worth the standing residual's place, and an
    operator watching a long decode needs to see the refused fit — that
    is how you tell "no registration error here" from "the row never
    ran".  `refusal` names every failing leg with its numbers and is ""
    exactly when `published`.

    `delta_grid_dots_xy` (gy, gx, 2), `magnitude_grid_dots` (gy, gx) and
    `has_data` (gy, gx) are the per-tile field BLOCK-POOLED to a bounded
    grid (see `plugins.fields.DIAG_GRID_MAX`); `has_data` is where the
    block held at least one tile with evidence in reach, so the pane can
    tell a measured zero from an unmeasured one.

    The magnitude grid is pooled from the per-tile |delta| rather than
    derived from the pooled vector, because the two are different
    statistics and only the first mirrors the writer's own decision: a
    block straddling a sign change averages its VECTORS toward zero
    while every tile in it clears the publish floor.  The band shades on
    this one, so the shading and `publishable` answer the same question.

    A plane that produced no fit at all (dead ink, no live states) sets
    EVERY measurement to None rather than to zero: the honesty rule is a
    schema here, not a rendering convention, so no consumer can print a
    zero the fit never measured.
    """

    plane: int
    plane_name: str
    published: bool
    refusal: str
    median_delta_dots: float | None
    n_sites: int | None
    residual: float | None
    support_tiles: int | None
    delta_grid_dots_xy: np.ndarray | None
    magnitude_grid_dots: np.ndarray | None
    has_data: np.ndarray | None

    @property
    def fitted(self) -> bool:
        return self.delta_grid_dots_xy is not None


@dataclass(frozen=True)
class FieldFitted:
    """One `fields` fit over one lane-page: every plane, published or not.

    Diag-only — nothing reads it back into the decode.  Bounded by
    construction: three planes x a grid capped on both axes, so the event
    costs the same on a 3x3 page and on sheet I's 53x37.
    """

    capture: str
    level_index: int
    page: int
    n_certificates: int
    tiles_yx: tuple[int, int]
    block_tiles_yx: tuple[int, int]
    #: the writer's own publish floor in dots, carried rather than
    #: re-typed downstream: the pane shades exactly the blocks the
    #: writer would call worth publishing.
    publish_floor_dots: float
    planes: tuple[FieldPlaneFit, ...]


Event = (
    RunOpen
    | CaptureOpen
    | SnapshotReplayed
    | SurveyDone
    | PoseCommitted
    | WindowSettled
    | WindowScheduled
    | WindowRetired
    | EngineStat
    | WordOutcome
    | AddressCoverage
    | CalibrateAdopted
    | TileOutcome
    | JobDone
    | CloseCheck
    | RunDone
    | FieldFitted
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
    plane_fields: bool = False
    resume: Path | None = None
    snapshot_every_s: float | None = 1800.0
