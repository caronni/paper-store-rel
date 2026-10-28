"""Frozen value types of the analyzer (PLAN.md §1.1).

Values only: scalars, tuples, small ndarrays. No live objects, no truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace as dc_replace
from fractions import Fraction
from typing import Any, Mapping

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

EXPOSURE_PER_CONSULT = 2.0 ** -32
EXPOSURE_BOUND_EXPECTED_FALSE = 0.01


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
    maps a Key to a `holo3.data.Certificate`; `plane_fields` is keyed by
    (capture_id, level_index, page, plane) and `pooled_ctx` by (page, rung).
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
    plane_fields: Mapping[tuple[str, int, int, int], Any]
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
#: entry is the pinned default arm (RULED 2026-09-03); `subtract+smooth`
#: is Y-only and `subtract+word` is C/M-only (the word field renders
#: state 0 or 3, so Y is 0 at every word site and has no word pose to
#: fit) — `battery_for` applies that.
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
    "subtract+smooth",
    "subtract+word",
)

STREAM_ONLY_ARMS: dict[str, tuple[str, ...]] = {
    "subtract+smooth": ("Y",),
    "subtract+word": ("C", "M"),
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

    def battery_for(self, stream_id: str) -> tuple[str, ...]:
        """The arms this stream actually runs."""
        out = []
        for arm in self.arms:
            if arm in self.refused_arms:
                continue
            only = STREAM_ONLY_ARMS.get(arm)
            if only is not None and str(stream_id) not in only:
                continue
            out.append(arm)
        return tuple(out)


@dataclass
class Ledger:
    """The pass's rows plus the header DESIGN §9 requires."""

    header: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)
    exposure: Exposure | None = None
    close_row: dict | None = None
    controls: dict = field(default_factory=dict)

    @property
    def certified(self) -> dict:
        """New certificates this pass produced, Key -> user bits."""
        out = {}
        for row in self.rows:
            if row.verdict == VERDICT_CERTIFIED and row.rungs.get("user_bits") \
                    is not None:
                out[row.key] = row.rungs["user_bits"]
        return out


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
    # ... and `everything+field2` adds the CERTIFICATE-anchored per-lane
    # variant on top, which is the expensive one (a refit per lane per
    # generation) and is kept behind its own name for that reason.
    "everything+field2": {
        "rules": DEFAULT_RULES,
        "arms": tuple(DEFAULT_ARMS) + ("subtract+field2+offset",
                                       "head+field2+offset",
                                       "subtract+field2c+offset",
                                       "head+field2c+offset"),
        "rungs": ("L0", "L1", "L2", "L4", "L3", "L7"),
        "reroll": True, "reroll_rungs": ("L0", "L1", "L2"),
        "halo_cells": {"C": 48, "M": 48, "Y": 32}},
}


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
