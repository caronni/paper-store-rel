"""Frozen value types of the analyzer (PLAN.md §1.1).

Values only: scalars, tuples, small ndarrays. No live objects, no truth.

ONE EXCEPTION, named here so the rule above stays readable as a rule:
:class:`Exposure` is a live ledger and carries the `threading.Lock` its
`reserve` holds.  It is the only mutable-and-shared type in the module,
and what makes copying one safe is that the lock rides in the init
beside the set it guards (M7, 2026-09-13).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace as dc_replace
from fractions import Fraction
from typing import Any, Mapping, Sequence

import numpy as np

Key = tuple[int, int, int, str]
LaneId = tuple[str, int]

STREAMS: tuple[str, ...] = ("C", "M", "Y")
PLANE_OF: dict[str, int] = {"C": 0, "M": 1, "Y": 2}

VERDICT_CERTIFIED = "certified"
VERDICT_CERTIFIED_LIST = "certified_list"
VERDICT_FALSE_ACCEPT = "false_accept"
VERDICT_WRONG = "wrong"
VERDICT_UNSCOREABLE = "unscoreable"
VERDICT_OPEN = "open"
VERDICT_UNCOVERED = "uncovered"
# W1c additions: blind rung outcomes that are neither a certificate nor a
# plain miss.  `below_floor` reproduces tiles.OUTCOME_BELOW_FLOOR (observed
# support under the bank's active bits); `refused` is a rung that declined to
# run (no labels, exposure bound, missing knob).
VERDICT_BELOW_FLOOR = "below_floor"
VERDICT_REFUSED = "refused"

DIRECT_RUNGS: tuple[str, ...] = ("L0", "L1", "L2", "L3", "L7")
LIST_RUNGS: tuple[str, ...] = ("L4", "L5", "L6")

#: Every rung name a `--rungs` list may SPELL (W8 B5).  Dispatch lives in
#: `ladder._run_rungs`, which raises on an unknown name — inside a worker,
#: per key, which is how a misspelled rung used to cost a whole pass
#: before anyone saw it.  This is the one place the spellable set is
#: written down: the CLI refuses anything else before a run dir is opened,
#: and the documentation test checks the README's commands against it.
#: `L7` is the alias `fixedpoint.RUNG_ALIASES` expands to L7a+L7b; `L5`
#: and `L6` are spellable because they exist as `DeferredRung` stubs and
#: refusing the name would be a lie about the ladder.
KNOWN_RUNGS: tuple[str, ...] = (
    "L0", "L1", "L2", "L3", "L3f", "L4", "L5", "L6",
    "L7", "L7a", "L7b", "L7c")

#: The calibration BRANCH names of DESIGN §4.7 (blocker B12).  They live
#: here rather than in `calibrate` because `statecal` needs `BRANCH_OTHER`
#: to name its own residual population while `calibrate` dispatches INTO
#: `statecal` — keeping them in `calibrate` would be an import cycle (W8
#: B2's import-direction ruling).  `calibrate` re-exports all three under
#: their old names, so every existing caller is unchanged.
BRANCH_CLEANABLE: str = "cleanable"
BRANCH_OTHER: str = "other"
BRANCH_ALL: str = "all"

EXPOSURE_PER_CONSULT = 2.0 ** -32
EXPOSURE_BOUND_EXPECTED_FALSE = 0.01

#: Knob names the DRIVER derives inside `blind_key` and assigns
#: unconditionally (W8 ruling 8): a value for one of these arriving through
#: `AnalyzerConfig.knobs` would be a lie about where it came from, so the
#: CLI refuses them at parse time and `blind_key` refuses the key.
RESERVED_KNOBS: tuple[str, ...] = (
    "pseudo_labels", "refit", "sibling_state", "disagree", "ctx_offsets",
    "ctx_state_adopted", "state_weighted")

#: The only sources a `PseudoLabels` may name.  P2's self-training labels
#: are built INSIDE `patch.patch_score` and never leave it, so the door
#: (`arms.evidence_for`, knob `pseudo_labels`) accepts the decoder's alone.
PSEUDO_SOURCES: tuple[str, ...] = ("decoder",)


@dataclass(frozen=True)
class PseudoLabels:
    """The decoder's confident bits as labels, TYPED (W8 ruling 8).

    `cells_yx` are PAGE cells (m, 2) int64; `bits` (m,) uint8 are
    PRINTED-domain bits — the convention of `KnownFrame.bits` — and
    `weights` (m,) float64 are the replication weights the fits give
    them.  This is the ONLY value the `pseudo_labels` knob accepts;
    anything else is refused at the door as `pseudo_labels:not_typed`.
    Built by `refit.confident_pseudo_labels` and nowhere else.
    """
    source: str
    cells_yx: np.ndarray
    bits: np.ndarray
    weights: np.ndarray

    def __post_init__(self) -> None:
        if self.source not in PSEUDO_SOURCES:
            raise ValueError(
                f"PseudoLabels: source {self.source!r} is not one of "
                f"{PSEUDO_SOURCES}")
        cells = np.asarray(self.cells_yx, np.int64).reshape(-1, 2)
        bits = np.asarray(self.bits, np.uint8).reshape(-1)
        weights = np.asarray(self.weights, np.float64).reshape(-1)
        if bits.size != cells.shape[0] or weights.size != cells.shape[0]:
            raise ValueError(
                f"PseudoLabels: {cells.shape[0]} cells, {bits.size} bits, "
                f"{weights.size} weights")
        if bits.size and (int(bits.max()) > 1 or bool(np.any(weights < 0.0))):
            raise ValueError("PseudoLabels: bits must be 0/1 and weights "
                             "non-negative")
        for array in (cells, bits, weights):
            array.setflags(write=False)
        object.__setattr__(self, "cells_yx", cells)
        object.__setattr__(self, "bits", bits)
        object.__setattr__(self, "weights", weights)

    @property
    def size(self) -> int:
        return int(self.bits.size)


#: The footprint-row form `patch.pseudo_rows` returns: ``(rows, bits,
#: weights)``, rows indexing the footprint the labels were mapped onto.
PseudoLabelsRows = tuple[np.ndarray, np.ndarray, np.ndarray]


@dataclass(frozen=True)
class Lane:
    capture_id: str
    ordinal: int
    level_index: int
    dpi: float
    ppc: Fraction
    frame: Fraction
    pitch_px_native: float
    pitch_px_level: float
    rasters: tuple[np.ndarray, ...]
    placements: tuple[Any, ...]

    @property
    def lane_id(self) -> LaneId:
        return (self.capture_id, self.level_index)


@dataclass(frozen=True)
class TileFootprint:
    page: int
    ty: int
    tx: int
    halo_cells: int
    page_cells_yx: np.ndarray
    in_tile: np.ndarray
    cargo: np.ndarray
    # W1b addition: `sample.lane_footprint` clips window page cells with
    # `calibrate.window_page_cells`, which needs the PAGE shape in cells;
    # carrying it here keeps the footprint self-contained (no `row`).
    page_shape_cells_yx: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class LaneFootprint:
    lane: LaneId
    tile: TileFootprint
    observed: np.ndarray
    owner_index: np.ndarray
    points_yx: np.ndarray


@dataclass(frozen=True)
class KnownFrame:
    bits: np.ndarray
    known: np.ndarray
    furniture: np.ndarray
    metadata_cell: int | None
    regressors: np.ndarray
    labels: np.ndarray
    siblings: np.ndarray
    n_discriminating: int
    # W1b additions.  `furniture` is the boolean mask a caller wants as a
    # mask; `color_model.reference_states` also hands back WHICH kind
    # (0 word, 1 dust, -1 neither), which the word arm (DESIGN §4.6) needs
    # to find its 100 sites, so it is kept rather than thrown away.
    furniture_kind: np.ndarray | None = None
    #: The key excluded from the certified projections (DESIGN §4.5).
    target: Key | None = None
    #: Blind bookkeeping: counts and the refusals the frame hit.
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Crops:
    """Per-channel pixels opened ONCE per (lane, footprint) — DESIGN §4.4.

    `filtered_rgb` is the aperture-filtered (h, w, 3) float32 crop in the
    LEVEL frame of `lane`, `y0`/`x0` its origin in that frame.  A read
    whose points fall outside it is REFUSED, never filled: `fill_rgb` is
    the crop median and exists only so a fill can never be silent.
    """

    lane: Any
    footprint: TileFootprint
    y0: int
    x0: int
    filtered_rgb: np.ndarray
    fill_rgb: tuple[float, float, float]
    pitch_px_level: float
    cell_dots: int
    bound_dots: float
    halo_px: int
    divisor: float
    #: W8 addition (B1, ruling 13): the UNFILTERED (h, w, 3) uint8 crop
    #: the aperture filter was computed from, kept ONLY when the caller
    #: asked (`open_crops(keep_raw=True)` — the patch modes and the
    #: aperture path).  Divide by `divisor` lazily; never stored as float.
    raw_rgb: np.ndarray | None = None
    #: W8 addition (B3, A7): the aperture `filtered_rgb` was computed
    #: through.  The defaults are production's
    #: (`color_region_anchor.APERTURE_CELLS` = 0.7, a uniform box) and
    #: `sample.open_crops` takes production's own code path for them, so
    #: a crop opened without asking is the crop every arm always read.
    aperture_cells: float = 0.7
    aperture_kind: str = "box"

    @property
    def shape_yx(self) -> tuple[int, int]:
        return (int(self.filtered_rgb.shape[0]),
                int(self.filtered_rgb.shape[1]))


@dataclass(frozen=True)
class Read:
    lane: LaneId
    arm: str
    values_rgb: np.ndarray
    offset_dots_xy: tuple[float, float]
    affine_terms: tuple[float, ...] | None
    scope: str
    refusal: str | None
    #: W8 additions (B1).  `affine_terms` carries the FIRST owner's terms
    #: only, so a footprint spanning several placements cannot recover its
    #: per-cell pose from a `Read`; the patch family needs exactly that.
    #: `points_yx` is the (n, 2) LEVEL-pixel position of every cell centre
    #: AT THE READ'S POSE (offset and override applied), NaN where
    #: unobserved; `linear_by_owner` maps an owner index to
    #: `anchor.pose_linear(terms)`, the 2x2 cell -> level-pixel map in
    #: (y, x) for that owner.  Both `None` on a refused read.
    points_yx: np.ndarray | None = None
    linear_by_owner: Mapping[int, np.ndarray] | None = None


@dataclass(frozen=True)
class Evidence:
    key: Key
    lane: LaneId
    arm: str
    llr_sequential: np.ndarray
    observed: np.ndarray
    blind: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Combined:
    key: Key
    rule: str
    lanes: tuple[LaneId, ...]
    coefficients: tuple[float, ...]
    llr_sequential: np.ndarray
    observed: np.ndarray
    clipped_fraction: float
    #: W3 addition (DESIGN §6 L3): the 9 production-context offsets this
    #: combination carries, pooled across the contributing lanes by the
    #: rule's own coefficients.  `None` when no lane adopted a context
    #: correction, which is L3's `no_ctx_offsets` refusal.
    ctx_offsets: tuple[float, ...] | None = None
    #: W4 additions (DESIGN §6 L7a): per-cell lane agreement.  `agreement`
    #: is the fraction of VOTING lanes (observed, non-zero LLR) whose sign
    #: matches the combined sign, one entry per sequential position;
    #: `disagree` are the positions below the agreement threshold.  Both are
    #: `None` for a single-lane combination, which is why L7a refuses on
    #: one-lane rules exactly as it did before.
    agreement: np.ndarray | None = None
    disagree: np.ndarray | None = None
    #: W8 additions (B2, D1 `platt-state`).  `coefficients` stays the
    #: POOLED per-lane weight vector — `combine.pooled_ctx_offsets` and
    #: every reader of the rule's scale keep their contract — and the
    #: per-sibling-state weights ride beside it, one entry per state
    #: (`None` where that state fell back to the pooled vector).  ALWAYS
    #: `None` for every rule but `platt-state`.
    coefficients_by_state: tuple[tuple[float, ...] | None, ...] | None = None
    #: W8 (B2, ruling 10): did any CONTRIBUTING lane adopt a per-state
    #: context correction?  L3's APPLY mode shifts ONE pooled 9-vector
    #: between bin assignments and is exact only for a pooled correction,
    #: so it refuses `state_context_adopted` on such a row.
    ctx_state_adopted: bool = False


@dataclass(frozen=True)
class Mother:
    key: Key
    rate_id: str
    llr: np.ndarray
    active: int
    k_bits: int
    transmitted: np.ndarray
    dither: np.ndarray
    metadata_bit: int | None


@dataclass(frozen=True)
class BpOut:
    hard: np.ndarray
    syndrome: np.ndarray
    unsat: int
    posterior: np.ndarray
    n_iters: int
    syndrome_ok: bool
    # W1c addition: how many _bp_loop passes produced n_iters, so the
    # "minsum-then-sp" 2x accounting is explicit rather than inferred.
    passes: int = 1
    mode: str = "minsum-then-sp"


@dataclass(frozen=True)
class RungResult:
    rung: str
    verdict: str
    user_bits: np.ndarray | None
    n_iters: int
    unsat_at_exit: int
    syndrome_ok: bool
    posterior_summary: Mapping[str, float]
    crc_consults_distinct: int
    seconds: float
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class Exposure:
    consulted: set = field(default_factory=set)
    # W1c addition: the bound is a value, not a module constant, so a control
    # run (and a test) can state a different one in the ledger header.
    bound_expected_false: float = EXPOSURE_BOUND_EXPECTED_FALSE
    # The lock `reserve` holds.  Every exposure carries one, shared or not:
    # a bare `Exposure()` is built in serial callers too, and one object
    # that is sometimes safe is not a bound.
    #
    # IT IS AN INIT FIELD, and that is the whole guard (M7, 2026-09-13).
    # `consulted` is copied BY REFERENCE, so a copy of an exposure shares
    # the set; under `init=False` it did not share the lock, and two
    # locks over one set is the race `reserve` exists to close.
    # `dataclasses.replace` carries init fields and re-defaults the rest
    # — and it does NOT dispatch to `__replace__`, measured on 3.14.7 —
    # so the lock has to ride in the init to come across.  `None` is the
    # bare construction, which mints one below; nobody passes it by hand.
    _lock: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._lock is None:
            self._lock = threading.Lock()

    @property
    def distinct(self) -> int:
        return len(self.consulted)

    @property
    def expected_false(self) -> float:
        return self.distinct * EXPOSURE_PER_CONSULT

    def exceeded(self) -> bool:
        return self.expected_false > self.bound_expected_false

    def would_exceed(self, n_new: int) -> bool:
        return ((self.distinct + n_new) * EXPOSURE_PER_CONSULT
                > self.bound_expected_false)

    def reserve(self, digest: bytes) -> tuple[bool, int]:
        """Pay for one CRC consultation: `(allowed, n_new)`.

        ONE operation, not three (review F13, 2026-09-13).  `mother.gate`
        used to ask "is this digest new?", "would the bound break?" and
        "add it" separately, and two workers could both pass the bound
        check before either added — measured on the free-threaded build
        at 8 workers, the run ends over a bound DESIGN §0 calls a
        correctness bound.  Membership, the check and the insertion are
        one critical section here; the CRC the caller then computes is
        not, which is the point of returning rather than holding.

        `n_new` is what THIS call paid: 1 for the first proposal of a
        digest, 0 for a repeat — including a repeat proposed at the same
        moment by another worker, which is the rung's honest charge.
        """
        with self._lock:
            if digest in self.consulted:
                return True, 0
            if self.would_exceed(1):
                return False, 0
            self.consulted.add(digest)
            return True, 1


@dataclass
class LedgerRow:
    page: int
    ty: int
    tx: int
    stream_id: str
    esi: int
    covered: bool
    certified_by_production: bool
    source: str | None
    band: str
    band_any: str
    neighbours_certified: int
    siblings_certified: tuple[str, ...]
    known_cells_in_halo: int
    n_discriminating_labels: int
    production_attempts: Mapping[str, Any]
    metadata_known: bool
    evidence: dict = field(default_factory=dict)
    combined: dict = field(default_factory=dict)
    rungs: dict = field(default_factory=dict)
    verdict: str = VERDICT_OPEN
    certifying_rung: str | None = None
    certifying_rule: str | None = None
    #: GAPS-2026-09-03 addition: WHICH ARM's evidence certified.  The
    #: selected arm is the usual answer (`selected`); a re-roll names the
    #: arm whose already-computed evidence won after the selected one's
    #: ladder failed, which is the only way to read the attempt-count gap
    #: off the ledger instead of re-measuring it.
    certifying_arm: str | None = None
    generation: int | None = None
    predecessors: tuple[Key, ...] = ()
    #: Blind per-row bookkeeping (seconds, lanes, refusal, attempts).
    #: It was called `oracle` and held the GT side table until the
    #: 2026-09-04 ruling took truth out of the run; the name went with
    #: the scores, and what is left is honestly a diagnostic column.
    diag: dict = field(default_factory=dict)
    # W1a additions: DESIGN §3 lists both on the census row.  Volume-level
    # quantities repeated per row; `residue.rank_check` computes them once.
    rank_report: int | None = None
    rank_recomputed: int | None = None

    @property
    def key(self) -> Key:
        return (self.page, self.ty, self.tx, self.stream_id)


# --- W1a additions (inputs / truth / census); see PLAN.md §1.2 -------------
# Added, never renamed: the contract in PLAN §1.2 names RunInputs and Truth
# without spelling their fields, and inputs.py / truth.py / residue.py all
# need them.  Live objects (mmaps, FormatRow, SiteGeometry) already live in
# `Lane`; RunInputs is the same kind of handle.


@dataclass(frozen=True)
class CaptureFact:
    """One capture as report.json declares it."""

    capture_id: str
    ordinal: int
    dpi: float
    channels: int
    levels_ppc: tuple[str, ...]
    shape_px: tuple[int, int]

    @property
    def sha12(self) -> str:
        return self.capture_id[:12]


@dataclass(frozen=True)
class RunInputs:
    """A finished holo3 run dir, typed (DESIGN §2).

    `row`/`geometry` are holo3's `FormatRow`/`SiteGeometry`; `certificates`
    maps a Key to a `holo.receiver.data.Certificate`; `plane_fields` is keyed by
    (page, plane) — the receiver's own key, and nothing else belongs in it
    (docs/PAGE-FIELD-DESIGN.md §2.2) — and `pooled_ctx` by (page, rung).
    `lattice_seeds`, `windows` and `surveys` are kept OPAQUE on purpose —
    W1a reads none of them, and a later wave may.
    """

    run_dir: Any
    format_ref: str
    row: Any
    geometry: Any
    pitch_in: Fraction
    tiles_yx: tuple[int, int]
    cells_yx: tuple[int, int]
    live_pages: tuple[int, ...]
    declared_pages: tuple[int, ...]
    captures: tuple[CaptureFact, ...]
    lanes: tuple[Lane, ...]
    lane_policy: str
    rung_ppc: Fraction | None
    certificates: Mapping[Key, Any]
    plane_fields: Mapping[tuple[int, int], Any]
    pooled_ctx: Mapping[tuple[int, str], Any]
    lattice_seeds: tuple[Any, ...]
    windows: Mapping[Any, Any]
    surveys: Mapping[str, Any]
    metadata_word: int | None
    metadata_version: int | None
    metadata_state: str
    k_total: int | None
    rank_report: int | None
    close_report: Mapping[str, Any]
    provenance: Mapping[str, Any]
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    def lane(self, lane_id: LaneId) -> Lane:
        for item in self.lanes:
            if item.lane_id == lane_id:
                return item
        raise KeyError(lane_id)

    @property
    def n_streams(self) -> int:
        return len(self.row.streams)

    def stream_index(self, stream_id: str) -> int:
        for index, fact in enumerate(self.row.streams):
            if fact.stream_id == stream_id:
                return index
        raise KeyError(stream_id)

    def esi(self, key: Key) -> int:
        page, ty, tx, stream_id = key
        counter = self.row.tile_counter(page, ty, tx)
        if not self.row.pooled_fountain:
            return counter
        return counter * self.n_streams + self.stream_index(stream_id)


@dataclass(frozen=True)
class Truth:
    """Ground truth: user bits per key, the emitted field per page.

    A SCORE COLUMN (DESIGN §0) — never reachable from unmix/register/
    calibrate/combine/ladder/osd/mother.
    """

    format_ref: str
    gen_dir: Any
    field_dir: Any
    payload_path: Any
    payload_sha256: str
    payload_bytes: int
    n_pages: int
    tiles_yx: tuple[int, int]
    streams: tuple[str, ...]
    user_bits: Mapping[Key, np.ndarray]
    fields: Mapping[int, Any]
    manifest: Mapping[str, Any]


BAND_DEAD = "dead"
BAND_MARGINAL = "marginal"
BAND_LIVE = "live"
BAND_UNCLASSIFIED = "unclassified"


# --- W1d additions (arms / calibrate / combine); see PLAN.md §1.2 ---------
# Added, never renamed.  PLAN §1.2 names `Folds` in `split_folds`'s return
# without spelling it, and arms/calibrate/combine all pass it around.


@dataclass(frozen=True)
class Folds:
    """The three-way label split of DESIGN §4.8, over FOOTPRINT rows.

    `fit` trains the PAVA map, `search` scores an offset/affine search and
    `select` chooses among arms — three disjoint masks over the same cell
    order, assigned by an independent hash of ``(seed, y, x)`` so a cell's
    fold is the same in every footprint, lane, arm and pass it appears in.
    """

    seed: int
    fit: np.ndarray
    search: np.ndarray
    select: np.ndarray

    def mask(self, name: str) -> np.ndarray:
        if name not in ("fit", "search", "select"):
            raise KeyError(f"unknown fold {name!r}")
        return getattr(self, name)

    @property
    def sizes(self) -> tuple[int, int, int]:
        return (int(np.count_nonzero(self.fit)),
                int(np.count_nonzero(self.search)),
                int(np.count_nonzero(self.select)))


# --- W2 additions (fixedpoint / ledger / cli); see PLAN.md §1.2 -----------
# Added, never renamed.  PLAN §1.2 names `config` and `Ledger` in
# `fixedpoint.run(inputs, truth, targets, config) -> Ledger` without
# spelling either; both are values, so both belong here.

#: DESIGN §4.6's battery, in the order the driver builds it.  The FIRST
#: entry is the pinned default arm (RULED 2026-09-03); `subtract+word` is
#: C/M-only (the word field renders state 0 or 3, so Y is 0 at every word
#: site and has no word pose to fit) — `battery_for` applies that.
DEFAULT_ARMS: tuple[str, ...] = (
    "subtract+offset",
    "raw+committed",
    "project+committed",
    "subtract+committed",
    "subtract+field",
    "subtract+field+offset",
    "global+offset",
    "head+offset",
    "conditional+offset",
    "subtract+affine",
    "subtract+word",
)

STREAM_ONLY_ARMS: dict[str, tuple[str, ...]] = {
    "subtract+word": ("C", "M"),
    # the word arm reads the 100-site colour word, which is C/M only —
    # the restriction is the ARM's, not the unmix mode's (W8 B3).
    "patch+word": ("C", "M"),
}

DEFAULT_RULES: tuple[str, ...] = ("sum", "best", "platt", "corr")
#: L4 sits after L2 (it enters at the best posterior L2 produced) and
#: before L3; it is BLINDLY gated on the unsatisfied-check count, so a tile
#: outside the few-error regime pays one comparison for it.
DEFAULT_LADDER_RUNGS: tuple[str, ...] = ("L0", "L1", "L2", "L4", "L3", "L7")


@dataclass(frozen=True)
class AnalyzerConfig:
    """Every knob one analyzer pass reads (DESIGN §4-§6, PLAN §5)."""

    arms: tuple[str, ...] = DEFAULT_ARMS
    rules: tuple[str, ...] = DEFAULT_RULES
    rungs: tuple[str, ...] = DEFAULT_LADDER_RUNGS
    workers: int = 4
    seed: int = 20260903
    halo_cells: Mapping[str, int] | None = None
    #: where that halo came from; `knobs_from` is for KNOBS (2026-09-07)
    halo_from: str = "defaults"
    cover_fraction: float = 0.9
    max_generations: int = 8
    #: Run EVERY rule's ladder even after one certifies, so the ledger's
    #: leave-one-out attribution over RULES is exact (DESIGN §9).
    all_rules: bool = True
    #: Keep the combined LLR vectors on the row (memory; DESIGN §10).
    keep_vectors: bool = False
    metadata_known: bool = True
    ctx_mode: str = "production"
    mix_scope_ladder: tuple[str, ...] = ("footprint", "lane")
    lane_mix_tiles: int = 12
    #: Extra `ladder` knobs, merged last.
    knobs: Mapping[str, Any] = field(default_factory=dict)
    #: Provenance for the ledger header, not behaviour.
    targets_from: str = "residue"
    knobs_from: str = "defaults"
    non_blind: bool = False
    #: Arms the run refuses (the positive control refuses `field`).
    refused_arms: tuple[str, ...] = ()
    #: GAPS-2026-09-03: after the SELECTED arm's ladder fails, run the
    #: remaining arms' already-computed evidence through `reroll_rungs`.
    #: The measurement's diagnosis is that the C gap on sheet H is an
    #: attempt-count gap — production won those tiles with six tools and
    #: hundreds of attempts each, the parity control fires one arm once —
    #: so the re-roll is a yield tool, ON for a decoding pass.  It is OFF
    #: for `controls.parity_sample`, where the whole point of the number
    #: is what ONE configuration re-derives.
    reroll: bool = True
    #: 2026-09-03 measurement (GAPS-2026-09-03.md §10): re-roll at L0+L1
    #: bought +0; at L0+L1+L2 it bought +1 of 8 on the C parity misses.
    reroll_rungs: tuple[str, ...] = ("L0", "L1", "L2")
    #: W8 B8: arms placed in the RE-ROLL ONLY — see `reroll_battery_for`.
    #: Added at the end, never renamed; empty is every profile that
    #: existed before this wave, so nothing changes for them.
    reroll_only_arms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # R1 (2026-09-06) at the LIBRARY boundary, not only the CLI's
        # (follow-up review): a cap below one runs ZERO generations, and
        # the loop's `else` arm would then write a header claiming one
        # generation ran with every target untouched.  Refused where the
        # value lives, so `fixedpoint.run` can never be handed it.
        if int(self.max_generations) < 1:
            raise ValueError(f"max_generations must be >= 1, got "
                             f"{self.max_generations!r}")

    def battery_for(self, stream_id: str) -> tuple[str, ...]:
        """The arms this stream actually runs."""
        return self._filter(self.arms, stream_id)

    def reroll_battery_for(self, stream_id: str) -> tuple[str, ...]:
        """The arms this stream runs ONLY if the battery leaves the key open.

        W8 B8, from the user's ruling of 2026-09-06 ("only run it after
        the other pass has done its job -- in case it does show
        incremental gains").  An arm named here is NOT in the battery, so
        it is not computed for the selection, it cannot be the arm the
        select fold picks, and it costs nothing on a key the battery
        closes.  `fixedpoint.blind_key` computes its evidence inside the
        re-roll, where the ladder has already failed on every rule; the
        ledger then attributes it exactly, as `certifying_arm =
        "reroll:<arm>"` and under `reroll.deferred`.  An arm that is
        already in `arms` is dropped here — a name means one placement.
        """
        return tuple(arm for arm in self._filter(self.reroll_only_arms,
                                                 stream_id)
                     if arm not in self.arms)

    def _filter(self, arms: Sequence[str], stream_id: str) -> tuple[str, ...]:
        out = []
        for arm in arms:
            if arm in self.refused_arms:
                continue
            only = STREAM_ONLY_ARMS.get(arm)
            if only is not None and str(stream_id) not in only:
                continue
            out.append(arm)
        return tuple(out)


@dataclass
class Ledger:
    """The pass's rows plus the header DESIGN §9 requires.

    `rows` is EMPTY on a streamed pass (the memory wave of 2026-09-13):
    a pass given a `ledger.LedgerWriter` puts each row on disk as its
    generation folds it and keeps none of them — 1.6 MB a row on the
    four-capture sheet-J pass, 15-32 GB over a 2,700-target one.  A
    library caller that hands no writer still gets its rows here, which
    is what `controls` and the small tests read; the CLI reads the file.

    `mints` is what the driver keeps either way: the certificates this
    pass produced, which the close needs and which are a few hundred
    bytes each.
    """

    header: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)
    exposure: Exposure | None = None
    close_row: dict | None = None
    controls: dict = field(default_factory=dict)
    mints: dict = field(default_factory=dict)

    @property
    def certified(self) -> dict:
        """New certificates this pass produced, Key -> user bits."""
        return dict(self.mints)


# --- page-scope context addition (2026-09-03); see DESIGN §4.7 -----------
# Added, never renamed.  DESIGN §4.7 asks for production's context variable
# "at lane-page scope over all footprints of a pass, behind
# `apply_region_context`'s adoption gate"; W1d recorded the per-footprint
# form as a deviation because one footprint cannot see the lane-page.  This
# is the value that closes it: ONE fit per (lane, page, stream), carried to
# every footprint that asks for it.


@dataclass(frozen=True)
class PageContext:
    """The lane-page 9-bin context correction, fitted once.

    `offsets` is production's own vector (one per neighbour-ink bin) and is
    applied by `calibrate.apply_context_offsets` exactly as a region's is;
    `adopted` is `context_decision`'s verdict on the pooled validation
    labels, and an unadopted context leaves every LLR alone.  The tiles the
    fit read are carried so the ledger can say what the fit saw.
    """

    lane: LaneId
    page: int
    stream_id: str
    offsets: tuple[float, ...]
    adopted: bool
    reason: str
    baseline_logloss: float | None
    candidate_logloss: float | None
    tiles: tuple[tuple[int, int], ...]
    n_tiles_read: int
    n_fit_labels: int
    n_validation_labels: int


# --- GAPS-2026-09-03 additions (the neighbourhood context) --------------
# Added, never renamed.  RULING 2026-09-03 (Germano): pose, page field and
# toner intensity are LOCAL phenomena, so a fitted model takes a
# NEIGHBOURHOOD, not the sheet.  `GAPS-2026-09-03.md` §5 measured the
# page-scope fit as 1.6% WORSE than the analyzer's per-footprint one, so
# this is not a replacement for the footprint fit — it is what a
# label-starved footprint borrows from, shrunk toward its own fit by label
# count and gated on its own held-out labels.


@dataclass(frozen=True)
class LocalContext:
    """A 9-bin context correction fitted over a 5x5 tile neighbourhood.

    `offsets` is production's own vector and is applied by
    `calibrate.apply_context_offsets`; `bin_labels` is how many fit-fold
    labels backed each bin, which is what the shrinkage weight is computed
    from.  `adopted` is `context_decision`'s verdict on the pooled
    validation labels of the neighbourhood — an unadopted neighbourhood
    context is not blended at all, and the footprint keeps its own fit.
    """

    lane: LaneId
    page: int
    stream_id: str
    target_tile_yx: tuple[int, int]
    radius_tiles: int
    offsets: tuple[float, ...]
    bin_labels: tuple[int, ...]
    adopted: bool
    reason: str
    baseline_logloss: float | None
    candidate_logloss: float | None
    tiles: tuple[tuple[int, int], ...]
    n_tiles_read: int
    n_fit_labels: int
    n_validation_labels: int


# --- GAPS-2026-09-03: the configurations that did NOT become defaults ----
# `halo 48` for C and M gains three certificates on sheet H's 60-tile C
# sample and LOSES one — (0, 2, 5, C) — so it fails the no-regression gate
# a default has to clear (`analyzer/GAPS-2026-09-03.md` §8) even though it
# is the highest-yield configuration measured.  It is therefore a NAMED
# PROFILE: reachable in one call, never fired by accident, and carrying the
# regression in its own docstring so nobody re-adopts it by remembering
# only the gain.

PROFILES: dict[str, dict[str, Any]] = {
    # +3 / -1 on sheet H's C sample, neutral on sheet I and on H's M/Y.
    "wide-halo": {"halo_cells": {"C": 48, "M": 48, "Y": 32}},
    # what the 2026-09-03 measurement's `battery_all` row ran: 7 of the 11
    # missed keys, at four times the cost of the default.
    "battery": {"rules": DEFAULT_RULES, "rungs": DEFAULT_LADDER_RUNGS,
                "reroll": True},
    # the pre-amendment calibration, for a control run that wants it
    "split-branches": {"knobs": {"branches": "subtract",
                                 "starved_fallback": False}},
    # RULING 2026-09-03 (Germano: "why not all of the above?"): on a
    # residue pass nothing an arm, halo, rule or rung does can mint a wrong
    # certificate — the gate decides — so the yield configuration is the
    # UNION: every arm on every lane, every rule, every rung, the wide
    # halo, and re-roll across the unselected arms at L0–L2.  Costs about
    # four times the default; exposure stays a stated number.
    # The field2 arms are IN, since the 2026-09-03 late ruling: the field
    # they read is now the POOLED FURNITURE field — one fit per (page,
    # plane) over every lane, with no certificate in it, so it does not
    # refit per lane or per generation and the cost finding that kept
    # them out (a refit per lane per generation) no longer applies.
    "everything": {"rules": DEFAULT_RULES,
                   "arms": tuple(DEFAULT_ARMS) + ("subtract+field2+offset",
                                                  "head+field2+offset"),
                   "rungs": ("L0", "L1", "L2", "L4", "L3", "L7"),
                   "reroll": True, "reroll_rungs": ("L0", "L1", "L2"),
                   "halo_cells": {"C": 48, "M": 48, "Y": 32}},
    # `everything+field2` stood here until 2026-09-12 (A2): it was
    # `everything` plus the two CERTIFICATE-anchored per-lane `field2c`
    # arms, and it retired with them.  Every composition built on it —
    # `everything+patch`, and `everything+patch+pure` through it — is
    # rebased on `everything` below.  The rebase alone removes those two
    # arms (0 first-success on sheet J, `J-CONFETTI-2026-09-10.md`);
    # counting A3's `subtract+smooth`, which left `DEFAULT_ARMS` in the
    # same wave and which every one of these profiles inherits, the two
    # rosters the sheet-J record was minted under lose THREE arms.
}

# ------------------------------------------------- W8's compositions (§2)
#
# X1-X5 of APPROACHES-2026-09-06 §2.  They are assigned AFTER the literal
# because each one is the previous one plus a little, and a dict literal
# cannot read itself.  `subtract+offset` stays FIRST in every arm list —
# it is `calibrate.DEFAULT_ARM`, the pinned default `select_arm` falls back
# to — and neither W8 rung (`L7c`, `L3f`) joins the `L7` alias or any
# existing profile, so no profile that existed before this wave changes
# behaviour.  `L3f` is in `patch-refit`'s MAIN ladder only, never in a
# `reroll_rungs` (its cost is a re-run of every chosen lane's evidence).
_PATCH_ARMS: tuple[str, ...] = ("patch+offset", "patch+committed")
# W8 B7 — the user's SELF-DISCOVERY ruling of 2026-09-06 ("even the
# existing pins / defaults are not well grounded.  if a run can discover
# its own truth for the paper-print-scanner-scan object at hand, it
# should!"): every knob of the patch family a run can decide from the
# sheet itself is `"auto"` here.  The module constants that used to be
# these values stay in `analyzer.patch` as the INHERITED FALLBACK — what
# a run uses where its own select fold cannot tell the candidates apart —
# and NOTHING is re-pinned from a sheet-H sweep.  The choice is made per
# (lane, plane, sibling state, tile) on the select fold and recorded in
# the ledger under `auto_choices` / `auto_losses`; an explicit value in a
# knob bag still wins, so every isolation run of APPROACHES §3 (and the
# `patch_min_labels_*=1000000` tier isolations) keeps working unchanged.
_AUTO_PATCH_KNOBS: dict[str, Any] = {
    "patch_samples_per_cell": "auto", "patch_window_cells": "auto",
    "patch_channels": "auto", "patch_features": "auto",
    "patch_shrinkage": "auto", "patch_min_labels_per_state": "auto",
    "patch_min_labels_agnostic": "auto", "aperture_cells": "auto"}
_STATE_KNOBS: dict[str, Any] = {"branches": "state", "ctx_state": True,
                                **_AUTO_PATCH_KNOBS}
_PATCH_RUNGS: tuple[str, ...] = ("L0", "L1", "L2", "L4", "L3", "L7", "L7c")
#: The halo the patch family runs with.  B1 inherited `wide-halo`'s 48
#: unmeasured; the H48 isolation dropped it (APPROACHES §6.9 — dead-band
#: three-ink 0.1518 -> 0.1640, 5 of 7 lanes past 2 SE), and the halo x
#: channel matrix CONFIRMED that at CERTIFICATE level at a fixed channel
#: set (109 -> 104, 128 -> 127 for 4.3x the CPU; HALO-CHANNEL §3(d)).
#: An OPERATOR axis (`--halo-cells 48`, or `C=48,M=48,Y=32`): two halo
#: candidates share no evaluation population, so none is walkable.
_PATCH_HALO: dict[str, int] = {"C": 16, "M": 16, "Y": 32}

PROFILES["patch"] = {                                          # X1
    "arms": ("subtract+offset",) + _PATCH_ARMS,
    "rules": DEFAULT_RULES + ("platt-state",),
    "rungs": _PATCH_RUNGS,
    "reroll": True, "reroll_rungs": ("L0", "L1", "L2"),
    "halo_cells": dict(_PATCH_HALO),
    "knobs": dict(_STATE_KNOBS)}
PROFILES["patch-self"] = {                                     # X2
    **PROFILES["patch"],
    "knobs": {**_STATE_KNOBS, "patch_selftrain_rounds": 4}}
PROFILES["patch-refit"] = {                                    # X3
    **PROFILES["patch-self"],
    "rungs": ("L0", "L1", "L2", "L4", "L3", "L3f", "L7", "L7c"),
    "reroll_rungs": ("L0", "L1", "L2"),
    "knobs": {**_STATE_KNOBS, "patch_selftrain_rounds": 4,
              "refit_rounds": 2, "refit_max_evidence": 26}}
PROFILES["patch-affine"] = {                                   # X4
    **PROFILES["patch-refit"],
    "arms": ("subtract+offset",) + _PATCH_ARMS + ("patch+affine",
                                                  "subtract+affine")}
PROFILES["everything+patch"] = {                               # X5
    "rules": DEFAULT_RULES + ("platt-state",),
    "arms": PROFILES["everything"]["arms"] + _PATCH_ARMS
            + ("patch+field2+offset", "patch+affine", "rings+offset",
               "mixture+offset"),
    "rungs": _PATCH_RUNGS,
    "reroll": True, "reroll_rungs": ("L0", "L1", "L2"),
    "halo_cells": dict(_PATCH_HALO),
    "knobs": {**_STATE_KNOBS, "patch_selftrain_rounds": 4}}

# ------------------------------------------------------- W8's pure path
#
# P0 of the user's ruling of 2026-09-06: "we already have every tile
# addressed, the correct page field and mostly correct poses per plane —
# there is no justification for pushing that through PAVA, ctx, Platt;
# just try it out either way."  So: the page-field pose with NO search
# (`patch+field2`, which collapses to the committed placement by itself
# where no field covers the tile — `patch+committed` is the same pose
# named explicitly), the B1 filter trained over the 5x5 neighbourhood's
# certified cells, and `pure.pure_llr` in place of the whole calibration
# stage.  `subtract+offset` is deliberately ABSENT: the pinned default is
# measured by every other profile, and the point here is the pure path
# alone, so `select_arm` falls back to the first arm named.  One rule
# (`sum`), no re-roll, and `ctx_mode` is a CONFIG field rather than a
# knob so the ledger header says `none` in its own column.
#
# W8 B7: the auto knobs are here too, with ONE exception spelled out.
# `patch_train_scope="local5"` means the 5x5 neighbourhood's rows are
# extracted by the loader before any per-population choice exists.  Since
# the review of 2026-09-06 that extraction is made at the WALK'S WIDEST
# geometry, so a chosen window, channel set or feature kind is a column
# SLICE of it and no choice can drop the rows — but a coarser SAMPLING
# moves every sample position and is a different grid, not a slice.
# `patch_samples_per_cell` is therefore the one axis left NAMED at B6's
# 16 in this family, so the neighbourhood's labels always survive; every
# other axis is the run's to choose.  README §2.4 says the same thing and
# a drift guard keeps the two together.
_PURE_ARMS: tuple[str, ...] = ("patch+field2", "patch+committed")
_PURE_KNOBS: dict[str, Any] = {"calibration": "pure",
                               "patch_train_scope": "local5",
                               **_AUTO_PATCH_KNOBS,
                               "patch_samples_per_cell": 16}

PROFILES["pure"] = {                                           # P0
    "arms": _PURE_ARMS, "rules": ("sum",),
    "rungs": ("L0", "L1", "L2"), "reroll": False, "ctx_mode": "none",
    "halo_cells": dict(_PATCH_HALO), "knobs": dict(_PURE_KNOBS)}
PROFILES["pure-self"] = {                                      # P0 + P2
    **PROFILES["pure"],
    "knobs": {**_PURE_KNOBS, "patch_selftrain_rounds": 4}}
PROFILES["pure-refit"] = {                                     # P0 + P2 + P3
    **PROFILES["pure-self"],
    "rungs": ("L0", "L1", "L2", "L3f")}

# ------------------------------------- W8 B8: the pure path, PLACED LAST
#
# THE RULING (Germano, 2026-09-06): "nothing prevents us from a) numpy
# optimizing and parallelizing the pure pass (which is probably a thing),
# and b) only run it after the other pass has done its job -- in case it
# does show incremental gains."  (a) is `analyzer.patchcache`; this is
# (b).  `pure+committed` and `pure+field2` compute EXACTLY the score
# `patch+committed` and `patch+field2` compute — same filter, same
# knobs, same halo, same neighbourhood — and differ from them in one
# thing only, the calibration (`pure.pure_llr` instead of the PAVA map,
# the context stage and Platt).  They are `reroll_only_arms`, so on a key
# the patch battery closes they are never computed, and on a key it
# leaves open they are one more roll of the same dice, gated by syndrome
# and CRC like anything else.  It is visible in the ledger as
# `certifying_arm = "reroll:pure+…"`.
#
# WHAT THE PLACEMENT DOES NOT ISOLATE (review 2026-09-06): the placed
# arms are re-rolled under the PROFILE's full rule list, which for
# `patch-then-pure` is `sum, best, platt, corr, platt-state` — and
# `platt`, `platt-state` and `best` are fitted stages of exactly the kind
# the pure path exists to remove.  A gain here is the pure calibration AS
# COMBINED BY THOSE RULES.  `PROFILES["pure"]` (`rules: ("sum",)`) and
# the two-pass form below are the isolations.
#
# THE TWO-PASS FORM is the other way to spend the same idea, and it is
# what an operator should reach for when the pure path wants knobs of its
# own (`patch_train_scope="local5"`, a coarser or finer sampling): run
# the patch profile, then
#
#     analyzer ladder --run-dir … --profile pure \
#         --targets "open-after <the patch pass's ledger.jsonl>"
#
# which puts the pure family on exactly the keys the first pass left
# open.  The single-profile placement below is the cheaper form: one
# pass, one exposure ledger, one row per key.
_PURE_REROLL_ARMS: tuple[str, ...] = ("pure+committed", "pure+field2")

PROFILES["patch-then-pure"] = {                                # X7
    **PROFILES["patch-refit"],
    "reroll_only_arms": _PURE_REROLL_ARMS}
PROFILES["everything+patch+pure"] = {                          # X8
    **PROFILES["everything+patch"],
    "reroll_only_arms": _PURE_REROLL_ARMS}


def with_profile(config: AnalyzerConfig, name: str) -> AnalyzerConfig:
    """`config` with a named profile's overrides applied.

    A profile is a measured configuration that is NOT the default — it
    either failed the no-regression gate or costs more than the yield it
    buys — so it is applied deliberately, by name, and the name is what
    the ledger header records.
    """
    if name not in PROFILES:
        raise KeyError(f"unknown profile {name!r}; known: "
                       f"{sorted(PROFILES)}")
    overrides = dict(PROFILES[name])
    knobs = overrides.pop("knobs", None)
    if knobs is not None:
        overrides["knobs"] = {**dict(config.knobs), **dict(knobs)}
    return dc_replace(config, knobs_from=f"profile:{name}", **overrides)
