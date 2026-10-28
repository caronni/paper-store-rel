"""E023 payload-tile decoding over e022 poses (decoder-axis, zero print).

The stage after e022 pilot-field placement: sample payload cells from the
ORIGINAL scans through the recorded per-window affine poses, calibrate
per-window scores on pilot labels, and LDPC-decode + CRC-certify each
64x64 LDPC tile. No fountain accounting, no feedback loop (the certified
substrate is recorded for the later loop).

Design (experiments/023-payload-tiles/README.md, converged after four
review rounds — the load-bearing rules):

- inputs = original scans + an e022 v2.2 session state ONLY; the recorded
  audited core (`PlacedWindow.page_cells_yx`) is AUTHORITATIVE (no mask
  policy of our own); redundant placements are consumed like accepted ones;
- sampling: ONE box prefilter per (scan, region-extent) crop (aperture
  ~0.7 cell — the measured decimate-first radiometrics) + one order-1 read
  per pose-mapped core cell; nothing is ever resampled or rotated;
- detector: score = (mid - mean) / spread per window (ink-positive) ->
  per-window PAVA on SEARCH-parity pilot labels -> held-out log-loss on
  the disjoint VALIDATION parity; calibrate-or-refuse (no uncalibrated
  emission mode); bounded LLRs by PAVA's 1/(n+2) clamp (LAYERS section 1);
- merge: ONE owner per (scan, payload cell) — the covering window with the
  best held-out log-loss (F1/F6 correlated-evidence rule); across scans
  STAGED: per-scan decode + certified tile union first (the 013-measured
  doctrine), cross-scan LLR sum only for tiles no scan certifies alone;
- decode gate: the conservative ATTEMPT FLOOR n_informative >= k_eff,
  computed pre-decode from the shorten mask + nonzero LLRs; tile states
  unobserved / below_attempt_floor / attempted_failed / certified /
  degenerate (tile_user_capacity == 0);
- honesty accounting: every decode attempt is ledgered (CRC false-accept
  budget = attempts x 2^-32); conflicting certifications of one tile and
  a contradictory BCH read in the input state are FATAL (fail-closed
  input-integrity preconditions);
- feedback substrate: per certified tile the USER PAYLOAD BITS + rate are
  stored; re-encoding regenerates the codeword/CRC deterministically, and
  raw samples regenerate from scans + poses (nothing else persisted).
"""
from __future__ import annotations

import copy
import hashlib
import os
import pickle
from dataclasses import dataclass, field, replace
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import ndimage
from scipy.special import expit

from . import compose, ldpc, place, pilotsearch
from .acquire import apply_calibration, pava_calibrate
from .formats import FormatDescriptor

STATE_MAGIC = "e023-state-v1"
STATE_VERSION = 1
E022_MAGIC = "e022-session-v1"
E022_STATE_VERSION = 3          # v2.2+: redundant placements recorded

APERTURE_CELLS = 0.7            # box prefilter, fraction of cell pitch
CAL_MIN_PER_CLASS = 10          # search-parity labels per class, else refuse
CAL_MIN_HELDOUT = 10            # validation-parity sites, else refuse
CRC_FALSE_ACCEPT = 2.0 ** -32   # per decode attempt (budget ledger)

DETECTOR_PAVA_V1 = "pava-v1"
DETECTOR_CTX_PAVA_V1 = "ctx-pava-v1"
DETECTOR_PROFILES = frozenset((DETECTOR_PAVA_V1, DETECTOR_CTX_PAVA_V1))

# Registered ctx-pava-v1 constants.  Keep these here, rather than in the
# E023b entry point, so replay and qualification use the same numerical arm.
CTX_OFFSET_MIN = -4.0
CTX_OFFSET_MAX = 4.0
CTX_LLR_CLIP = 12.0
CTX_MIN_SEARCH = 80
CTX_MIN_SEARCH_PER_CLASS = 20
CTX_MIN_VALIDATION = 40
CTX_MIN_VALIDATION_PER_CLASS = 10
CTX_ROOT_TOL = 1e-12


class FatalIntegrityError(RuntimeError):
    """Fail-closed input-integrity violation (contradictory BCH read in the
    e022 state, or two conflicting CRC certifications of one tile)."""


# ---------------------------------------------------------------------------
# e022 session state (read-only input)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class E022Scan:
    scan_id: str
    source_path: str
    source_sha256: str
    dpi: float
    result: "pilotsearch.SearchResult"


@dataclass(frozen=True)
class E022Session:
    format_id: str
    seed: bytes
    pages: tuple[int, ...]
    dpi: float
    scans: tuple[E022Scan, ...]

    @property
    def fingerprint(self) -> tuple[tuple[str, str], ...]:
        """Ordered upstream identity: ((scan_id, source_sha256), ...)."""
        return tuple((s.scan_id, s.source_sha256) for s in self.scans)


def load_e022_session(path: Path | str) -> E022Session:
    """Load an e022 v2.2 session state; refuse anything else.

    Pre-v2.2 states (STATE_VERSION < 3) are an INCOMPLETE e023 input —
    their redundant placements were never recorded — and refuse cleanly.
    A contradictory known-position BCH read anywhere in the state is a
    fail-closed integrity violation (round-4 R5 disposition)."""
    payload = pickle.loads(Path(path).read_bytes())
    if not isinstance(payload, dict) or payload.get("magic") != E022_MAGIC:
        raise ValueError(f"{path} is not an e022 session state")
    version = int(payload.get("version", -1))
    if version != E022_STATE_VERSION:
        raise ValueError(
            f"{path} has e022 STATE_VERSION {version}; e023 requires "
            f"{E022_STATE_VERSION} (v2.2 records redundant placements — "
            "re-run session_e022.py)")
    scans = tuple(
        E022Scan(scan_id=str(row["scan_id"]),
                 source_path=str(row["source_path"]),
                 source_sha256=str(row["source_sha256"]),
                 dpi=float(row["dpi"]),
                 result=row["result"])
        for row in payload["scans"]
    )
    for scan in scans:
        for key, tile in scan.result.tiles.items():
            if tile.bch_ok is False:
                raise FatalIntegrityError(
                    f"e022 state {path}: scan {scan.scan_id} tile {key} "
                    "carries a CONTRADICTORY known-position BCH read — "
                    "input integrity violated, refusing to emit")
    return E022Session(
        format_id=str(payload["format_id"]),
        seed=bytes(payload["seed"]),
        pages=tuple(int(p) for p in payload["pages"]),
        dpi=float(payload["dpi"]),
        scans=scans,
    )


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# geometry: recorded-core inversion (the page_cells_yx -> local-cells map)
# ---------------------------------------------------------------------------

def unrotate_points(rotated: np.ndarray, shape_local: tuple[int, int],
                    rot_k: int) -> np.ndarray:
    """Exact inverse of pilotsearch._rotated_points (pinned by test)."""
    h, w = shape_local
    ry, rx = rotated[:, 0], rotated[:, 1]
    k = rot_k % 4
    if k == 0:
        return np.stack([ry, rx], axis=1)
    if k == 1:
        return np.stack([rx, w - 1 - ry], axis=1)
    if k == 2:
        return np.stack([h - 1 - ry, w - 1 - rx], axis=1)
    return np.stack([h - 1 - rx, ry], axis=1)


def local_core_cells(placed: "pilotsearch.PlacedWindow") -> np.ndarray:
    """(N, 2) window-local cell coords of the audited core, row-aligned
    with placed.page_cells_yx (the recorded core is AUTHORITATIVE)."""
    page = np.asarray(placed.page_cells_yx, np.int64)
    rotated = page - np.asarray(placed.origin_yx, np.int64)
    return unrotate_points(
        rotated, (placed.window.h, placed.window.w), placed.rot_k)


# ---------------------------------------------------------------------------
# sampling: one prefilter per (scan, region extent), order-1 reads per cell
# ---------------------------------------------------------------------------

@dataclass
class RegionCrop:
    y0: int
    x0: int
    filt: np.ndarray          # box-prefiltered float32 crop
    fill: float               # cval for (never-expected) off-crop reads


def region_extent_crop(image: np.ndarray,
                       placements: list["pilotsearch.PlacedWindow"],
                       ) -> RegionCrop:
    """Raw bbox crop over the union of pose-mapped window extents + halo,
    prefiltered ONCE. No masks: the audited core is >= erode depth inside
    the region mask and the aperture (~0.7 cell) cannot reach backing
    (README round-1/R1 argument; the _core-fallback caveat is measured by
    the qualification core-edge diagnostic, not handled here)."""
    pts = []
    for placed in placements:
        h, w = placed.window.h, placed.window.w
        corners = np.array([[0, 0], [0, w], [h, 0], [h, w]], np.float64)
        pts.append(placed.pose.points(corners))
    allpts = np.concatenate(pts, axis=0)
    pitch = float(np.median([p.pose.pitch_px for p in placements]))
    halo = int(np.ceil(APERTURE_CELLS * pitch)) + 2
    y0 = max(0, int(np.floor(allpts[:, 0].min())) - halo)
    x0 = max(0, int(np.floor(allpts[:, 1].min())) - halo)
    y1 = min(image.shape[0], int(np.ceil(allpts[:, 0].max())) + halo)
    x1 = min(image.shape[1], int(np.ceil(allpts[:, 1].max())) + halo)
    crop = np.asarray(image[y0:y1, x0:x1], np.float32)
    aperture = max(1, int(round(APERTURE_CELLS * pitch)))
    filt = ndimage.uniform_filter(crop, size=aperture, mode="nearest")
    return RegionCrop(y0=y0, x0=x0, filt=filt, fill=float(np.median(crop)))


def sample_window_means(crop: RegionCrop,
                        placed: "pilotsearch.PlacedWindow",
                        local_cells: np.ndarray) -> np.ndarray:
    """One order-1 subpixel read per pose-mapped core cell centre."""
    pts = placed.pose.points(local_cells.astype(np.float64))
    pts -= np.array([crop.y0, crop.x0], np.float64)
    return ndimage.map_coordinates(
        crop.filt, pts.T, order=1, cval=crop.fill)


# ---------------------------------------------------------------------------
# per-window emission: score -> PAVA (calibrate-or-refuse) -> payload LLRs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContextFit:
    """One registered ``ctx-pava-v1`` fit/gate decision for a region.

    The fit is deliberately a sidecar to :class:`WindowEmission`: when the
    held-out gate fails, the returned baseline emissions remain exactly the
    original objects.  E023b can therefore persist failed/adopted decisions
    without perturbing the qualified baseline evidence.
    """

    region_index: int
    detector_profile: str
    eligible: bool
    adopted: bool
    reason: str
    tau: np.ndarray
    search_support_by_bin: np.ndarray
    validation_support_by_bin: np.ndarray
    search_observations_by_bin: np.ndarray
    validation_observations_by_bin: np.ndarray
    n_search: int
    n_search_0: int
    n_search_1: int
    n_search_observations: int
    n_validation: int
    n_validation_0: int
    n_validation_1: int
    n_validation_observations: int
    baseline_validation_logloss: float | None
    candidate_validation_logloss: float | None
    n_context_valid_cells: int
    n_context_cells: int
    n_windows: int
    n_refused_windows: int

    @property
    def context_valid_coverage(self) -> float:
        if self.n_context_cells == 0:
            return 0.0
        return self.n_context_valid_cells / self.n_context_cells


@dataclass(frozen=True)
class ContextRegionResult:
    """Context decision plus the evidence selected by its held-out gate."""

    emissions: tuple["WindowEmission", ...]
    fit: ContextFit


@dataclass(frozen=True)
class ReprofileResult:
    """Pure detector replay result over stored raw-mean window substrate."""

    emissions: tuple["WindowEmission", ...]
    context_fits: tuple[ContextFit, ...] = ()


@dataclass
class WindowEmission:
    """One placed window's calibrated payload evidence (value domain
    already descrambled to PAYLOAD-BIT domain; positive = payload bit 1)."""

    placement_ordinal: int    # index into the scan's result.placements
    page: int
    payload_index: np.ndarray     # (M,) int64
    payload_llr: np.ndarray       # (M,) float32, bounded (PAVA clamp)
    heldout_logloss: float
    n_train_labels: int
    n_heldout: int
    refused: bool = False
    refuse_reason: str = ""
    diagnostics: dict = field(default_factory=dict)
    # E023b replay substrate.  Raw means + the recorded authoritative core
    # (`page_cells_yx`) are authoritative; scores and PAVA nodes are retained
    # and replay-validated derivations.  E023's v1 persistence continues to
    # store only its historical reduced rows; E023b owns the richer record.
    region_index: int = -1
    page_cells_yx: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 2), np.int32))
    raw_means: np.ndarray = field(
        default_factory=lambda: np.zeros(0, np.float32))
    scores: np.ndarray = field(
        default_factory=lambda: np.zeros(0, np.float32))
    calibration_score_nodes: np.ndarray = field(
        default_factory=lambda: np.zeros(0, np.float64))
    calibration_probability_nodes: np.ndarray = field(
        default_factory=lambda: np.zeros(0, np.float64))
    detector_profile: str = DETECTOR_PAVA_V1
    # Set only for emissions from an adopted region.  Failed/ineligible
    # regions return the baseline objects byte-for-byte and carry their
    # attempted fit through ContextRegionResult instead.
    context_fit: ContextFit | None = None


def _upgrade_window_emission(row: WindowEmission) -> WindowEmission:
    """Shallow-upgrade a legacy rich-state row missing new dataclass attrs."""
    stored = vars(row)
    if "detector_profile" in stored and "context_fit" in stored:
        return row
    upgraded = copy.copy(row)
    if "detector_profile" not in stored:
        upgraded.detector_profile = DETECTOR_PAVA_V1
    if "context_fit" not in stored:
        upgraded.context_fit = None
    return upgraded


def _emit_window_from_means(
    placed: "pilotsearch.PlacedWindow",
    ordinal: int,
    means: np.ndarray,
    spec: "compose.ComposeSpec",
    seed: bytes,
    pim: np.ndarray,
    ks_pages: dict[int, np.ndarray],
) -> WindowEmission:
    """Qualified post-sampling body shared by live emission and replay."""
    local = local_core_cells(placed)
    page_yx = np.asarray(placed.page_cells_yx, np.int64)
    if local.size == 0:
        if np.asarray(means).size:
            raise ValueError("empty authoritative core carries sample means")
        return WindowEmission(ordinal, placed.page,
                              np.zeros(0, np.int64), np.zeros(0, np.float32),
                              1.0, 0, 0, refused=True,
                              refuse_reason="empty_core",
                              region_index=int(placed.region_index),
                              page_cells_yx=page_yx.astype(np.int32,
                                                           copy=True))
    means = np.asarray(means)
    if means.ndim != 1 or means.size != local.shape[0]:
        raise ValueError("raw means must align with authoritative core")
    mid = float(np.median(means))
    spread = max(float(np.abs(means - mid).mean()), 1e-6)
    scores = (mid - means) / spread          # ink-positive (value 1 = ink)

    # labels: pilot sites inside the core, printed values from the seed
    shape = (placed.window.h, placed.window.w)
    core_mask = np.zeros(shape, bool)
    core_mask[local[:, 0], local[:, 1]] = True
    pl = place.Placement(ok=True, page=placed.page,
                         origin_yx=placed.origin_yx, rot_k=placed.rot_k)
    sites_ij, expected = place.fragment_pilot_sites(pl, shape, core_mask,
                                                    spec, seed)
    cell_pos = np.full(shape, -1, np.int64)
    cell_pos[local[:, 0], local[:, 1]] = np.arange(local.shape[0])
    site_pos = cell_pos[sites_ij[:, 0], sites_ij[:, 1]]
    keep = site_pos >= 0
    site_pos, expected = site_pos[keep], expected[keep]
    site_page = page_yx[site_pos]
    parity = ((site_page[:, 0] * 131 + site_page[:, 1] * 17) & 1).astype(bool)
    train, heldout = ~parity, parity          # parity 0 = search set

    y_tr = expected[train].astype(np.float64)
    n1, n0 = int(y_tr.sum()), int((1.0 - y_tr).sum())
    if (n1 < CAL_MIN_PER_CLASS or n0 < CAL_MIN_PER_CLASS
            or int(heldout.sum()) < CAL_MIN_HELDOUT):
        return WindowEmission(
            ordinal, placed.page, np.zeros(0, np.int64),
            np.zeros(0, np.float32), 1.0, n1 + n0, int(heldout.sum()),
            refused=True, refuse_reason="calibrate_or_refuse",
            diagnostics={"n_class1": n1, "n_class0": n0},
            region_index=int(placed.region_index),
            page_cells_yx=page_yx.astype(np.int32, copy=True),
            raw_means=np.asarray(means, np.float32),
            scores=np.asarray(scores, np.float32))

    nodes_s, nodes_p = pava_calibrate(scores[site_pos[train]], y_tr)
    value_llr = apply_calibration(scores, nodes_s, nodes_p)

    p_ho = np.interp(scores[site_pos[heldout]], nodes_s, nodes_p)
    y_ho = expected[heldout].astype(np.float64)
    logloss = float(-np.mean(y_ho * np.log(p_ho)
                             + (1.0 - y_ho) * np.log(1.0 - p_ho)))

    # payload domain: keep payload cells, flip by the keystream
    pidx = pim[page_yx[:, 0], page_yx[:, 1]]
    sel = pidx >= 0
    ks = ks_pages[placed.page][page_yx[sel, 0], page_yx[sel, 1]]
    payload_llr = (value_llr[sel]
                   * (1.0 - 2.0 * ks.astype(np.float64))).astype(np.float32)
    return WindowEmission(
        ordinal, placed.page, pidx[sel].astype(np.int64), payload_llr,
        logloss, n1 + n0, int(heldout.sum()),
        diagnostics={"n_cal_nodes": int(nodes_s.size),
                     "mid": mid, "spread": spread},
        region_index=int(placed.region_index),
        page_cells_yx=page_yx.astype(np.int32, copy=True),
        raw_means=np.asarray(means, np.float32),
        scores=np.asarray(scores, np.float32),
        calibration_score_nodes=np.asarray(nodes_s, np.float64),
        calibration_probability_nodes=np.asarray(nodes_p, np.float64))


def emit_window(placed: "pilotsearch.PlacedWindow",
                ordinal: int,
                crop: RegionCrop,
                spec: "compose.ComposeSpec",
                seed: bytes,
                pim: np.ndarray,
                ks_pages: dict[int, np.ndarray]) -> WindowEmission:
    """Sample + calibrate + emit one window under the recorded core."""
    local = local_core_cells(placed)
    means = (np.zeros(0, np.float32) if local.size == 0
             else sample_window_means(crop, placed, local))
    return _emit_window_from_means(
        placed, ordinal, means, spec, seed, pim, ks_pages)


def context_neighbor_counts(
    page_cells_yx: np.ndarray,
    provisional_ink: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return one-shot 8-neighbor counts and complete-neighborhood mask.

    Coordinates are absolute page-grid coordinates for *one* authoritative
    window core.  A cell is valid only when every one of its eight immediate
    neighbors occurs in that same core.  Results remain row-aligned with
    ``page_cells_yx``.
    """
    page_yx = np.asarray(page_cells_yx, np.int64)
    ink = np.asarray(provisional_ink, bool).ravel()
    if page_yx.ndim != 2 or page_yx.shape[1:] != (2,):
        raise ValueError("page_cells_yx must have shape (N, 2)")
    if ink.size != page_yx.shape[0]:
        raise ValueError("provisional_ink must align with page_cells_yx")
    if page_yx.shape[0] == 0:
        return np.zeros(0, np.int8), np.zeros(0, bool)
    if np.unique(page_yx, axis=0).shape[0] != page_yx.shape[0]:
        raise ValueError("page_cells_yx contains duplicate coordinates")

    lo = page_yx.min(axis=0)
    local = page_yx - lo
    shape = tuple((local.max(axis=0) + 1).astype(int))
    present = np.zeros(shape, np.uint8)
    ink_grid = np.zeros(shape, np.uint8)
    present[local[:, 0], local[:, 1]] = 1
    ink_grid[local[:, 0], local[:, 1]] = ink.astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    kernel[1, 1] = 0
    n_present = ndimage.convolve(
        present, kernel, mode="constant", cval=0)
    n_ink = ndimage.convolve(
        ink_grid, kernel, mode="constant", cval=0)
    row_present = n_present[local[:, 0], local[:, 1]]
    valid = row_present == 8
    counts = n_ink[local[:, 0], local[:, 1]].astype(np.int8)
    return counts, valid


def _logistic_logloss(logits: np.ndarray, labels: np.ndarray,
                      sample_weight: np.ndarray | None = None) -> float:
    """Stable mean binary logistic loss for physical-value logits."""
    logits = np.asarray(logits, np.float64).ravel()
    labels = np.asarray(labels, np.float64).ravel()
    if logits.size == 0 or logits.size != labels.size:
        raise ValueError("logits and labels must be equally non-empty")
    losses = np.logaddexp(0.0, logits) - labels * logits
    if sample_weight is None:
        return float(np.mean(losses))
    weight = np.asarray(sample_weight, np.float64).ravel()
    if weight.size != logits.size or not np.isfinite(weight).all() or np.any(
            weight <= 0.0):
        raise ValueError("sample weights must be finite, positive and aligned")
    return float(np.sum(weight * losses) / np.sum(weight))


def _context_block_offset(logits: np.ndarray, labels: np.ndarray,
                          weights: np.ndarray) -> float:
    """Unique clipped additive-logit optimum for one generalized-PAVA block."""
    logits = np.asarray(logits, np.float64).ravel()
    labels = np.asarray(labels, np.float64).ravel()
    weights = np.asarray(weights, np.float64).ravel()
    target = float(np.sum(weights * labels))

    def derivative(offset: float) -> float:
        return float(np.sum(weights * expit(logits + offset)) - target)

    f_lo = derivative(CTX_OFFSET_MIN)
    if f_lo >= 0.0:
        return CTX_OFFSET_MIN
    f_hi = derivative(CTX_OFFSET_MAX)
    if f_hi <= 0.0:
        return CTX_OFFSET_MAX
    f_zero = derivative(0.0)
    if f_zero == 0.0:
        return 0.0

    lo, hi = CTX_OFFSET_MIN, CTX_OFFSET_MAX
    # The tolerance, rather than data-dependent optimizer termination, is
    # part of the registered arm and makes replay deterministic.
    while hi - lo > CTX_ROOT_TOL:
        mid = (lo + hi) * 0.5
        if derivative(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


def fit_ordered_context_offsets(
    baseline_logits: np.ndarray,
    neighbor_count: np.ndarray,
    labels: np.ndarray,
    sample_weight: np.ndarray | None = None,
) -> np.ndarray:
    """Fit the registered nine-bin ordered additive-logit correction.

    Every original bin receives the fixed symmetric two-observation prior
    ``(logit=0,label=0)`` and ``(logit=0,label=1)``.  Adjacent blocks whose
    optima violate ``tau[0] >= ... >= tau[8]`` are pooled and re-solved.
    """
    logits = np.asarray(baseline_logits, np.float64).ravel()
    raw_count = np.asarray(neighbor_count).ravel()
    y = np.asarray(labels, np.float64).ravel()
    if logits.size != raw_count.size or logits.size != y.size:
        raise ValueError("context fit arrays must have equal length")
    if not np.isfinite(logits).all():
        raise ValueError("baseline logits must be finite")
    if not np.all((y == 0.0) | (y == 1.0)):
        raise ValueError("context labels must be binary")
    if sample_weight is None:
        weight = np.ones(logits.size, np.float64)
    else:
        weight = np.asarray(sample_weight, np.float64).ravel()
        if (weight.size != logits.size or not np.isfinite(weight).all()
                or np.any(weight <= 0.0)):
            raise ValueError(
                "sample weights must be finite, positive and aligned")
    count = raw_count.astype(np.int64)
    if not np.array_equal(raw_count, count) or np.any((count < 0) | (count > 8)):
        raise ValueError("neighbor counts must be integers in [0, 8]")

    blocks: list[dict] = []
    for bin_index in range(9):
        sel = count == bin_index
        block_logits = np.concatenate(
            (logits[sel], np.array([0.0, 0.0], np.float64)))
        block_labels = np.concatenate(
            (y[sel], np.array([0.0, 1.0], np.float64)))
        block_weights = np.concatenate(
            (weight[sel], np.array([1.0, 1.0], np.float64)))
        blocks.append({
            "bins": [bin_index],
            "logits": block_logits,
            "labels": block_labels,
            "weights": block_weights,
            "offset": _context_block_offset(
                block_logits, block_labels, block_weights),
        })
        while (len(blocks) >= 2
               and blocks[-2]["offset"] < blocks[-1]["offset"]):
            right = blocks.pop()
            left = blocks.pop()
            merged_logits = np.concatenate(
                (left["logits"], right["logits"]))
            merged_labels = np.concatenate(
                (left["labels"], right["labels"]))
            merged_weights = np.concatenate(
                (left["weights"], right["weights"]))
            blocks.append({
                "bins": left["bins"] + right["bins"],
                "logits": merged_logits,
                "labels": merged_labels,
                "weights": merged_weights,
                "offset": _context_block_offset(
                    merged_logits, merged_labels, merged_weights),
            })

    tau = np.empty(9, np.float64)
    for block in blocks:
        tau[np.asarray(block["bins"], np.int64)] = block["offset"]
    return tau


def _window_pilot_observations(
    placed: "pilotsearch.PlacedWindow",
    spec: "compose.ComposeSpec",
    seed: bytes,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Core-row positions, labels and validation parity of pilot sites."""
    local = local_core_cells(placed)
    page_yx = np.asarray(placed.page_cells_yx, np.int64)
    shape = (placed.window.h, placed.window.w)
    core_mask = np.zeros(shape, bool)
    core_mask[local[:, 0], local[:, 1]] = True
    pl = place.Placement(ok=True, page=placed.page,
                         origin_yx=placed.origin_yx, rot_k=placed.rot_k)
    sites_ij, expected = place.fragment_pilot_sites(
        pl, shape, core_mask, spec, seed)
    cell_pos = np.full(shape, -1, np.int64)
    cell_pos[local[:, 0], local[:, 1]] = np.arange(local.shape[0])
    site_pos = cell_pos[sites_ij[:, 0], sites_ij[:, 1]]
    keep = site_pos >= 0
    site_pos = site_pos[keep]
    expected = expected[keep].astype(np.uint8, copy=False)
    site_page = page_yx[site_pos]
    validation = (
        (site_page[:, 0] * 131 + site_page[:, 1] * 17) & 1
    ).astype(bool)
    return site_pos, expected, validation


def _context_fit_record(
    *,
    region_index: int,
    eligible: bool,
    adopted: bool,
    reason: str,
    tau: np.ndarray,
    search_support: np.ndarray,
    validation_support: np.ndarray,
    search_observations: np.ndarray,
    validation_observations: np.ndarray,
    n_search_observations: int,
    n_validation_observations: int,
    n_search_0: int,
    n_search_1: int,
    n_validation_0: int,
    n_validation_1: int,
    baseline_loss: float | None,
    candidate_loss: float | None,
    n_context_valid_cells: int,
    n_context_cells: int,
    n_windows: int,
    n_refused_windows: int,
) -> ContextFit:
    return ContextFit(
        region_index=int(region_index),
        detector_profile=DETECTOR_CTX_PAVA_V1,
        eligible=bool(eligible), adopted=bool(adopted), reason=str(reason),
        tau=np.asarray(tau, np.float64).copy(),
        search_support_by_bin=np.asarray(search_support, np.float64).copy(),
        validation_support_by_bin=np.asarray(
            validation_support, np.float64).copy(),
        search_observations_by_bin=np.asarray(
            search_observations, np.int64).copy(),
        validation_observations_by_bin=np.asarray(
            validation_observations, np.int64).copy(),
        n_search=int(n_search_0 + n_search_1),
        n_search_0=int(n_search_0), n_search_1=int(n_search_1),
        n_search_observations=int(n_search_observations),
        n_validation=int(n_validation_0 + n_validation_1),
        n_validation_0=int(n_validation_0),
        n_validation_1=int(n_validation_1),
        n_validation_observations=int(n_validation_observations),
        baseline_validation_logloss=(None if baseline_loss is None
                                     else float(baseline_loss)),
        candidate_validation_logloss=(None if candidate_loss is None
                                      else float(candidate_loss)),
        n_context_valid_cells=int(n_context_valid_cells),
        n_context_cells=int(n_context_cells), n_windows=int(n_windows),
        n_refused_windows=int(n_refused_windows))


def apply_context_region(
    placements: list["pilotsearch.PlacedWindow"],
    emissions: list[WindowEmission] | tuple[WindowEmission, ...],
    spec: "compose.ComposeSpec",
    seed: bytes,
    *,
    payload_index_map: np.ndarray | None = None,
    keystream_pages: dict[int, np.ndarray] | None = None,
) -> ContextRegionResult:
    """Fit, gate, and (only on adoption) apply ``ctx-pava-v1``.

    ``placements`` and ``emissions`` must be aligned.  Failure and
    ineligibility return the exact baseline emission objects; callers persist
    the complete decision through the returned :class:`ContextFit` sidecar.
    """
    baseline = tuple(emissions)
    if len(placements) != len(baseline):
        raise ValueError("placements and emissions must be aligned")
    region_ids = {int(p.region_index) for p in placements}
    if len(region_ids) > 1:
        raise ValueError("ctx-pava-v1 must be fit one region at a time")
    region_index = next(iter(region_ids), -1)

    rows: list[dict] = []
    train_logits: list[np.ndarray] = []
    train_count: list[np.ndarray] = []
    train_labels: list[np.ndarray] = []
    train_keys: list[tuple[int, int, int]] = []
    validation_logits: list[np.ndarray] = []
    validation_count: list[np.ndarray] = []
    validation_labels: list[np.ndarray] = []
    validation_keys: list[tuple[int, int, int]] = []
    n_context_cells = 0
    n_context_valid_cells = 0
    n_refused = 0

    for placed, emission in zip(placements, baseline):
        page_yx = np.asarray(placed.page_cells_yx, np.int64)
        if (int(emission.page) != int(placed.page)
                or not np.array_equal(
                    np.asarray(emission.page_cells_yx, np.int64), page_yx)):
            raise ValueError("placement/emission authoritative core mismatch")
        if emission.refused:
            n_refused += 1
            rows.append({"emission": emission})
            continue
        if (emission.scores.size != page_yx.shape[0]
                or emission.calibration_score_nodes.size == 0
                or (emission.calibration_score_nodes.size
                    != emission.calibration_probability_nodes.size)):
            raise ValueError("accepted emission lacks derived PAVA fields")

        value_llr = apply_calibration(
            emission.scores, emission.calibration_score_nodes,
            emission.calibration_probability_nodes)
        count, valid = context_neighbor_counts(page_yx, value_llr > 0.0)
        site_pos, expected, validation = _window_pilot_observations(
            placed, spec, seed)
        valid_site = valid[site_pos]
        search_sel = (~validation) & valid_site
        validation_sel = validation & valid_site
        train_logits.append(value_llr[site_pos[search_sel]])
        train_count.append(count[site_pos[search_sel]])
        train_labels.append(expected[search_sel])
        train_keys.extend(
            (int(placed.page), int(y), int(x))
            for y, x in page_yx[site_pos[search_sel]])
        validation_logits.append(value_llr[site_pos[validation_sel]])
        validation_count.append(count[site_pos[validation_sel]])
        validation_labels.append(expected[validation_sel])
        validation_keys.extend(
            (int(placed.page), int(y), int(x))
            for y, x in page_yx[site_pos[validation_sel]])
        n_context_cells += int(valid.size)
        n_context_valid_cells += int(valid.sum())
        rows.append({
            "emission": emission,
            "placed": placed,
            "value_llr": value_llr,
            "count": count,
            "valid": valid,
            "site_pos": site_pos,
            "expected": expected,
            "validation": validation,
        })

    def pooled(parts: list[np.ndarray], dtype) -> np.ndarray:
        nonempty = [np.asarray(part, dtype).ravel() for part in parts
                    if np.asarray(part).size]
        return (np.concatenate(nonempty) if nonempty
                else np.zeros(0, dtype))

    tr_l0 = pooled(train_logits, np.float64)
    tr_n = pooled(train_count, np.int64)
    tr_y = pooled(train_labels, np.uint8)
    va_l0 = pooled(validation_logits, np.float64)
    va_n = pooled(validation_count, np.int64)
    va_y = pooled(validation_labels, np.uint8)

    def duplicate_weights_and_unique_counts(
        keys: list[tuple[int, int, int]], labels: np.ndarray,
    ) -> tuple[np.ndarray, int, int]:
        if len(keys) != labels.size:
            raise AssertionError("physical-key pool lost row alignment")
        multiplicity: dict[tuple[int, int, int], int] = {}
        known_label: dict[tuple[int, int, int], int] = {}
        for key, label in zip(keys, labels):
            value = int(label)
            if key in known_label and known_label[key] != value:
                raise ValueError("one physical pilot has conflicting labels")
            known_label[key] = value
            multiplicity[key] = multiplicity.get(key, 0) + 1
        weights = np.asarray(
            [1.0 / multiplicity[key] for key in keys], np.float64)
        n1 = sum(known_label.values())
        return weights, len(known_label) - n1, n1

    tr_w, n_tr0, n_tr1 = duplicate_weights_and_unique_counts(
        train_keys, tr_y)
    va_w, n_va0, n_va1 = duplicate_weights_and_unique_counts(
        validation_keys, va_y)
    # Fractional bin support is intentional: all observations of one physical
    # pilot have total weight one even if overlapping window calibrations put
    # them in different provisional-neighbor bins.
    search_support = np.bincount(
        tr_n, weights=tr_w, minlength=9)[:9]
    validation_support = np.bincount(
        va_n, weights=va_w, minlength=9)[:9]
    search_observations = np.bincount(tr_n, minlength=9)[:9]
    validation_observations = np.bincount(va_n, minlength=9)[:9]

    reason = ""
    if n_tr0 + n_tr1 < CTX_MIN_SEARCH:
        reason = "insufficient_search_support"
    elif min(n_tr0, n_tr1) < CTX_MIN_SEARCH_PER_CLASS:
        reason = "search_class_starved"
    elif n_va0 + n_va1 < CTX_MIN_VALIDATION:
        reason = "insufficient_validation_support"
    elif min(n_va0, n_va1) < CTX_MIN_VALIDATION_PER_CLASS:
        reason = "validation_class_starved"
    if reason:
        fit = _context_fit_record(
            region_index=region_index, eligible=False, adopted=False,
            reason=reason, tau=np.zeros(9),
            search_support=search_support,
            validation_support=validation_support,
            search_observations=search_observations,
            validation_observations=validation_observations,
            n_search_observations=tr_y.size,
            n_validation_observations=va_y.size,
            n_search_0=n_tr0, n_search_1=n_tr1,
            n_validation_0=n_va0, n_validation_1=n_va1,
            baseline_loss=None, candidate_loss=None,
            n_context_valid_cells=n_context_valid_cells,
            n_context_cells=n_context_cells, n_windows=len(baseline),
            n_refused_windows=n_refused)
        return ContextRegionResult(baseline, fit)

    tau = fit_ordered_context_offsets(tr_l0, tr_n, tr_y, tr_w)
    baseline_loss = _logistic_logloss(va_l0, va_y, va_w)
    candidate_loss = _logistic_logloss(
        va_l0 + tau[va_n], va_y, va_w)
    adopted = candidate_loss < baseline_loss
    fit = _context_fit_record(
        region_index=region_index, eligible=True, adopted=adopted,
        reason="adopted" if adopted else "validation_gate_failed",
        tau=tau, search_support=search_support,
        validation_support=validation_support,
        search_observations=search_observations,
        validation_observations=validation_observations,
        n_search_observations=tr_y.size,
        n_validation_observations=va_y.size,
        n_search_0=n_tr0, n_search_1=n_tr1,
        n_validation_0=n_va0, n_validation_1=n_va1,
        baseline_loss=baseline_loss, candidate_loss=candidate_loss,
        n_context_valid_cells=n_context_valid_cells,
        n_context_cells=n_context_cells, n_windows=len(baseline),
        n_refused_windows=n_refused)
    if not adopted:
        return ContextRegionResult(baseline, fit)

    pim = (compose.payload_index_map(spec, seed)
           if payload_index_map is None else payload_index_map)
    ks_pages = ({
        int(p.page): compose.payload_keystream(spec, seed, int(p.page))
        for p in placements
    } if keystream_pages is None else keystream_pages)
    corrected_rows: list[WindowEmission] = []
    for row in rows:
        emission = row["emission"]
        if emission.refused:
            corrected_rows.append(emission)
            continue
        value_llr = np.asarray(row["value_llr"], np.float64)
        count = np.asarray(row["count"], np.int64)
        valid = np.asarray(row["valid"], bool)
        corrected = value_llr.copy()
        corrected[valid] = np.clip(
            corrected[valid] + tau[count[valid]],
            -CTX_LLR_CLIP, CTX_LLR_CLIP)

        site_pos = np.asarray(row["site_pos"], np.int64)
        validation = np.asarray(row["validation"], bool)
        expected = np.asarray(row["expected"], np.uint8)
        heldout_loss = _logistic_logloss(
            corrected[site_pos[validation]], expected[validation])

        page_yx = np.asarray(emission.page_cells_yx, np.int64)
        pidx = pim[page_yx[:, 0], page_yx[:, 1]]
        sel = pidx >= 0
        if not np.array_equal(
                pidx[sel].astype(np.int64), emission.payload_index):
            raise ValueError("payload replay no longer matches baseline row")
        ks = ks_pages[int(emission.page)][
            page_yx[sel, 0], page_yx[sel, 1]]
        payload_llr = (
            corrected[sel] * (1.0 - 2.0 * ks.astype(np.float64))
        ).astype(np.float32)
        diagnostics = dict(emission.diagnostics)
        diagnostics.update({
            "detector_profile": DETECTOR_CTX_PAVA_V1,
            "context_region_adopted": True,
            "context_region_index": int(region_index),
            "context_tau": tuple(float(v) for v in tau),
            "context_n_search": fit.n_search,
            "context_n_search_observations": fit.n_search_observations,
            "context_n_validation": fit.n_validation,
            "context_n_validation_observations": (
                fit.n_validation_observations),
            "context_baseline_validation_logloss": baseline_loss,
            "context_candidate_validation_logloss": candidate_loss,
            "context_valid_coverage": fit.context_valid_coverage,
        })
        corrected_rows.append(replace(
            _upgrade_window_emission(emission), payload_llr=payload_llr,
            heldout_logloss=heldout_loss, diagnostics=diagnostics,
            detector_profile=DETECTOR_CTX_PAVA_V1, context_fit=fit))
    return ContextRegionResult(tuple(corrected_rows), fit)


def _replay_baseline_window(
    placed: "pilotsearch.PlacedWindow",
    emission: WindowEmission,
    spec: "compose.ComposeSpec",
    seed: bytes,
    pim: np.ndarray,
    ks_pages: dict[int, np.ndarray],
) -> WindowEmission:
    """Validate and recover pava-v1 from authoritative retained raw means."""
    try:
        raw_means = emission.raw_means
    except AttributeError as exc:
        raise ValueError(
            "window evidence lacks raw means required for replay") from exc
    replayed = _emit_window_from_means(
        placed, int(emission.placement_ordinal), raw_means,
        spec, seed, pim, ks_pages)

    def array_exact(left: np.ndarray, right: np.ndarray) -> bool:
        a, b = np.asarray(left), np.asarray(right)
        return (a.dtype == b.dtype and a.shape == b.shape
                and np.array_equal(a, b))

    scalar_fields = (
        "placement_ordinal", "page", "heldout_logloss", "n_train_labels",
        "n_heldout", "refused", "refuse_reason", "region_index",
    )
    raw_scalar_fields = tuple(
        field for field in scalar_fields if field != "heldout_logloss")
    raw_array_fields = (
        "payload_index", "page_cells_yx", "raw_means", "scores",
        "calibration_score_nodes", "calibration_probability_nodes",
    )
    for field_name in raw_scalar_fields:
        if getattr(emission, field_name) != getattr(replayed, field_name):
            raise ValueError(
                f"window evidence replay mismatch in {field_name}")
    for field_name in raw_array_fields:
        if not array_exact(
                getattr(emission, field_name), getattr(replayed, field_name)):
            raise ValueError(
                f"window evidence replay mismatch in {field_name}")

    baseline_diagnostics = {
        key: value for key, value in emission.diagnostics.items()
        if key != "detector_profile" and not key.startswith("context_")
    }
    if baseline_diagnostics != replayed.diagnostics:
        raise ValueError("window evidence replay mismatch in diagnostics")

    is_baseline = (
        getattr(emission, "detector_profile", DETECTOR_PAVA_V1)
        == DETECTOR_PAVA_V1
        and getattr(emission, "context_fit", None) is None)
    if is_baseline:
        if emission.heldout_logloss != replayed.heldout_logloss:
            raise ValueError(
                "window evidence replay mismatch in heldout_logloss")
        if not array_exact(emission.payload_llr, replayed.payload_llr):
            raise ValueError("window evidence replay mismatch in payload_llr")
        if emission.diagnostics != replayed.diagnostics:
            raise ValueError("window evidence replay mismatch in diagnostics")
        # The exact-object guarantee is earned only after replay validation.
        return emission
    return replayed


def reprofile_window_evidence(
    placements: list["pilotsearch.PlacedWindow"]
    | tuple["pilotsearch.PlacedWindow", ...],
    emissions: list[WindowEmission] | tuple[WindowEmission, ...],
    spec: "compose.ComposeSpec",
    seed: bytes,
    detector_profile: str,
) -> ReprofileResult:
    """Purely replay stored PAVA evidence under a registered detector arm.

    Baseline rows already carrying ``pava-v1`` are returned as the exact same
    objects and arrays, but only after the common post-sampling body re-derives
    and validates their scores, PAVA nodes, counts, held-out loss and payload
    LLRs from raw means.  Context rows replay that baseline first, then region
    fits are recomputed.  No image or pose resampling occurs.
    """
    if detector_profile not in DETECTOR_PROFILES:
        raise ValueError(f"unknown detector profile {detector_profile!r}")
    placement_seq = tuple(placements)
    evidence_seq = tuple(emissions)
    if len(placement_seq) != len(evidence_seq):
        raise ValueError("placements and emissions must have equal length")
    ordinals = [int(row.placement_ordinal) for row in evidence_seq]
    if (len(set(ordinals)) != len(ordinals)
            or any(index < 0 or index >= len(placement_seq)
                   for index in ordinals)):
        raise ValueError("window evidence has invalid placement ordinals")
    aligned = [placement_seq[index] for index in ordinals]
    pim = compose.payload_index_map(spec, seed)
    ks_pages = {
        int(placed.page): compose.payload_keystream(
            spec, seed, int(placed.page))
        for placed in aligned
    }
    baseline = tuple(
        _replay_baseline_window(placed, emission, spec, seed, pim, ks_pages)
        for placed, emission in zip(aligned, evidence_seq))
    if detector_profile == DETECTOR_PAVA_V1:
        return ReprofileResult(baseline)

    # Legacy E023b.0 rich-state rows predate the profile fields.  Preserve
    # their exact objects for pava-v1 qualification above, but ctx replay owns
    # a shallow schema-upgraded copy before any dataclasses.replace call.
    baseline = tuple(_upgrade_window_emission(row) for row in baseline)

    by_region: dict[int, list[int]] = {}
    for index, placed in enumerate(aligned):
        by_region.setdefault(int(placed.region_index), []).append(index)
    profiled = list(baseline)
    fits: list[ContextFit] = []
    for region_index in sorted(by_region):
        indices = by_region[region_index]
        result = apply_context_region(
            [aligned[index] for index in indices],
            [baseline[index] for index in indices], spec, seed,
            payload_index_map=pim, keystream_pages=ks_pages)
        for index, row in zip(indices, result.emissions):
            profiled[index] = row
        fits.append(result.fit)
    return ReprofileResult(tuple(profiled), tuple(fits))


@dataclass
class ScanEmission:
    """One scan's reduced evidence: ONE owner per (page, payload cell)."""

    scan_id: str
    source_sha256: str
    pages: dict[int, dict[str, np.ndarray]]   # page -> {index, llr, owner}
    window_rows: list[dict] = field(default_factory=list)


def collect_window_evidence(
    scan: E022Scan,
    image: np.ndarray,
    spec: "compose.ComposeSpec",
    seed: bytes,
    pages: tuple[int, ...],
    *,
    on_region=None,
    detector_profile: str = DETECTOR_PAVA_V1,
    on_context=None,
) -> list[WindowEmission]:
    """Sample/calibrate every placed window, retaining non-owner evidence.

    The qualified numerical path is unchanged from E023's original
    ``emit_scan``.  The split is an orchestration seam for E023b: callers may
    publish observer-only progress after a region, while ownership and LDPC
    remain behind the complete-scan barrier.
    """
    if detector_profile not in DETECTOR_PROFILES:
        raise ValueError(f"unknown detector profile {detector_profile!r}")
    pim = compose.payload_index_map(spec, seed)
    ks_pages = {p: compose.payload_keystream(spec, seed, p) for p in pages}
    by_region: dict[int, list[tuple[int, pilotsearch.PlacedWindow]]] = {}
    for ordinal, placed in enumerate(scan.result.placements):
        by_region.setdefault(placed.region_index, []).append((ordinal, placed))
    emissions: list[WindowEmission] = []
    for region_index in sorted(by_region):
        group = by_region[region_index]
        crop = region_extent_crop(image, [p for _, p in group])
        region_emissions: list[WindowEmission] = []
        for ordinal, placed in group:
            row = emit_window(placed, ordinal, crop, spec, seed,
                              pim, ks_pages)
            region_emissions.append(row)
        if detector_profile == DETECTOR_CTX_PAVA_V1:
            context = apply_context_region(
                [placed for _, placed in group], region_emissions,
                spec, seed, payload_index_map=pim,
                keystream_pages=ks_pages)
            region_emissions = list(context.emissions)
            if on_context is not None:
                on_context(int(region_index), context.fit)
        emissions.extend(region_emissions)
        if on_region is not None:
            on_region(int(region_index), tuple(region_emissions),
                      tuple(emissions))
    return emissions


def freeze_scan_emission(scan: E022Scan,
                         emissions: list[WindowEmission],
                         spec: "compose.ComposeSpec",
                         ) -> ScanEmission:
    """Reduce immutable window evidence to one owner per physical cell."""
    # deterministic ownership: best held-out log-loss first
    order = sorted(range(len(emissions)),
                   key=lambda i: (emissions[i].heldout_logloss,
                                  emissions[i].placement_ordinal))
    out = ScanEmission(scan_id=scan.scan_id,
                       source_sha256=scan.source_sha256, pages={})
    taken: dict[int, np.ndarray] = {}
    acc: dict[int, dict[str, list]] = {}
    capacity = compose.payload_capacity(spec)
    for i in order:
        em = emissions[i]
        row = {"placement": em.placement_ordinal,
               "refused": em.refused, "reason": em.refuse_reason,
               "heldout_logloss": (None if em.refused
                                   else em.heldout_logloss),
               "n_train_labels": em.n_train_labels,
               "n_heldout": em.n_heldout,
               "n_payload_cells": int(em.payload_index.size)}
        row.update(em.diagnostics)
        out.window_rows.append(row)
        if em.refused or em.payload_index.size == 0:
            continue
        seen = taken.setdefault(em.page, np.zeros(capacity, bool))
        fresh = ~seen[em.payload_index]
        if not fresh.any():
            continue
        idx = em.payload_index[fresh]
        seen[idx] = True
        bucket = acc.setdefault(em.page,
                                {"index": [], "llr": [], "owner": []})
        bucket["index"].append(idx)
        bucket["llr"].append(em.payload_llr[fresh])
        bucket["owner"].append(np.full(idx.size, em.placement_ordinal,
                                       np.int32))
    for page, bucket in acc.items():
        index = np.concatenate(bucket["index"])
        order2 = np.argsort(index, kind="stable")
        out.pages[page] = {
            "index": index[order2],
            "llr": np.concatenate(bucket["llr"])[order2],
            "owner": np.concatenate(bucket["owner"])[order2],
        }
    out.window_rows.sort(key=lambda r: r["placement"])
    return out


def emit_scan(scan: E022Scan, image: np.ndarray,
              spec: "compose.ComposeSpec", seed: bytes,
              pages: tuple[int, ...], *,
              detector_profile: str = DETECTOR_PAVA_V1,
              on_context=None) -> ScanEmission:
    """Qualified E023 convenience path: collect then freeze one scan."""
    evidence = collect_window_evidence(
        scan, image, spec, seed, pages,
        detector_profile=detector_profile, on_context=on_context)
    return freeze_scan_emission(scan, evidence, spec)


# ---------------------------------------------------------------------------
# tile outcomes + staged decoding
# ---------------------------------------------------------------------------

@dataclass
class TileOutcome:
    """Honest per-tile state (R4): unobserved / below_attempt_floor /
    attempted_failed / certified / degenerate."""

    page: int
    tile_yx: tuple[int, int]
    state: str = "unobserved"
    user_bits: np.ndarray | None = None     # certified USER PAYLOAD bits
    certified_by: str = ""                  # scan_id or "union"
    k_eff: int = 0
    n_informative_best: int = 0
    n_nonshort: int = 0
    n_iters: int = 0
    attempts: int = 0
    divergence: dict = field(default_factory=dict)   # scan_id -> rate


@dataclass(frozen=True)
class TileEvaluation:
    """Pure result of applying E023's qualified attempt policy to evidence.

    ``decoder_invoked`` distinguishes an honest scheduling decision
    (degenerate/below floor) from CRC exposure.  E023's mutable
    ``DecodeState`` and E023b's evidence-addressed ledger both consume this
    one primitive, preventing detector/decoder drift between entry points.
    """

    state: str
    decoder_invoked: bool
    k_eff: int
    n_nonshort: int
    n_informative: int
    coverage: float
    n_iters: int = 0
    syndrome_ok: bool | None = None
    crc_ok: bool | None = None
    n_erased: int = 0
    user_bits: np.ndarray | None = None


def evaluate_tile(
    llr: np.ndarray,
    idx: np.ndarray,
    spec: "compose.ComposeSpec",
    seed: bytes,
    tile_yx: tuple[int, int],
    ldpc_spec: "ldpc.LdpcSpec",
    *,
    max_iters: int = 60,
    alpha: float = 0.8,
) -> TileEvaluation:
    """Run the exact E023 attempt floor and LDPC+CRC path without mutation."""
    mask = ldpc.tile_shorten_mask(tile_yx, spec, seed)
    n_nonshort = int((~mask).sum())
    k_eff = max(ldpc_spec.k_bits - int(mask.sum()), 0)
    if ldpc.tile_user_capacity(mask, ldpc_spec) == 0:
        return TileEvaluation(
            state="degenerate", decoder_invoked=False, k_eff=k_eff,
            n_nonshort=n_nonshort, n_informative=0, coverage=0.0)
    llr4096, _mask, coverage = ldpc.gather_tile_llrs(
        llr, idx, spec, seed, tile_yx)
    n_informative = int((llr4096[~mask] != 0.0).sum())
    if n_informative < k_eff:
        return TileEvaluation(
            state="below_attempt_floor", decoder_invoked=False,
            k_eff=k_eff, n_nonshort=n_nonshort,
            n_informative=n_informative, coverage=float(coverage),
            n_erased=n_nonshort - n_informative)
    result = ldpc.decode_tile(
        llr4096, mask, ldpc_spec, tile_yx=tile_yx,
        max_iters=max_iters, alpha=alpha)
    return TileEvaluation(
        state="certified" if result.ok else "attempted_failed",
        decoder_invoked=True, k_eff=k_eff, n_nonshort=n_nonshort,
        n_informative=n_informative, coverage=float(coverage),
        n_iters=result.n_iters, syndrome_ok=result.syndrome_ok,
        crc_ok=result.crc_ok, n_erased=result.n_erased,
        user_bits=(None if result.payload_bits is None
                   else np.asarray(result.payload_bits, np.uint8).copy()))


class DecodeState:
    """The thin e023 aggregator: per-scan reduced emissions + tile
    outcomes + the honesty ledgers. Persistable via to_payload()."""

    def __init__(self, descriptor: FormatDescriptor, rate_id: str,
                 pages: tuple[int, ...],
                 fingerprint: tuple[tuple[str, str], ...]):
        self.format_id = descriptor.format_id
        self.seed = descriptor.seed
        self.rate_id = rate_id
        self.pages = tuple(int(p) for p in pages)
        self.upstream = tuple(fingerprint)
        self.spec = descriptor.spec()
        self.ldpc_spec = ldpc.LDPC_LADDER[rate_id]
        self.scans: list[ScanEmission] = []
        self.tiles: dict[tuple[int, int, int], TileOutcome] = {}
        self.n_attempts = 0
        self.fatal: list[str] = []
        self._masks: dict[tuple[int, int], np.ndarray] = {}

    def __getstate__(self) -> dict:
        """Persist semantic decoder state, never process-local caches."""
        state = dict(self.__dict__)
        state["_masks"] = {}
        return state

    # -- codec-facing helpers ------------------------------------------------
    def shorten_mask(self, tile_yx: tuple[int, int]) -> np.ndarray:
        if tile_yx not in self._masks:
            self._masks[tile_yx] = ldpc.tile_shorten_mask(
                tile_yx, self.spec, self.seed)
        return self._masks[tile_yx]

    def outcome(self, page: int, tile_yx: tuple[int, int]) -> TileOutcome:
        key = (page, tile_yx[0], tile_yx[1])
        if key not in self.tiles:
            self.tiles[key] = TileOutcome(page=page, tile_yx=tuple(tile_yx))
        return self.tiles[key]

    def _payload_tiles(self, page: int, index: np.ndarray
                       ) -> set[tuple[int, int]]:
        inv = _payload_inverse(self.spec, self.seed)
        cells = inv[index]
        return {(int(y) // ldpc.TILE_CELLS, int(x) // ldpc.TILE_CELLS)
                for y, x in cells}

    # -- decode --------------------------------------------------------------
    def _attempt(self, out: TileOutcome, llr: np.ndarray,
                 idx: np.ndarray, source: str) -> bool:
        """Gathered attempt on one tile; returns True when certified."""
        evaluation = evaluate_tile(
            llr, idx, self.spec, self.seed, out.tile_yx, self.ldpc_spec)
        if evaluation.state == "degenerate":
            # Preserve the qualified E023 v1 ledger exactly: the historical
            # path classified zero-capacity tiles before filling attempt
            # metadata.  E023b's richer ledger records these values itself.
            out.state = "degenerate"
            return False
        out.k_eff = evaluation.k_eff
        out.n_nonshort = evaluation.n_nonshort
        out.n_informative_best = max(
            out.n_informative_best, evaluation.n_informative)
        if evaluation.state == "below_attempt_floor":
            if out.state == "unobserved":
                out.state = "below_attempt_floor"
            return False
        assert evaluation.decoder_invoked
        out.attempts += 1
        self.n_attempts += 1
        if evaluation.state != "certified":
            if out.state != "certified":
                out.state = "attempted_failed"
            return False
        assert evaluation.user_bits is not None
        if out.state == "certified":
            if not np.array_equal(out.user_bits, evaluation.user_bits):
                message = (f"tile page={out.page} {out.tile_yx}: conflicting "
                           f"certifications ({out.certified_by} vs {source})")
                self.fatal.append(message)
                raise FatalIntegrityError(message)
            return True
        out.state = "certified"
        out.user_bits = evaluation.user_bits
        out.certified_by = source
        out.n_iters = evaluation.n_iters
        return True

    def ingest_scan(self, emission: ScanEmission) -> dict:
        """Stage 1 for one scan: reduce is already done; decode every
        touched, not-yet-certified tile from THIS scan's evidence alone."""
        self.scans.append(emission)
        counts = {"certified": 0, "attempted": 0}
        for page, vec in emission.pages.items():
            for tile_yx in sorted(self._payload_tiles(page, vec["index"])):
                out = self.outcome(page, tile_yx)
                if out.state in ("certified", "degenerate"):
                    continue
                counts["attempted"] += 1
                if self._attempt(out, vec["llr"], vec["index"],
                                 emission.scan_id):
                    counts["certified"] += 1
        return counts

    def decode_union(self) -> dict:
        """Stage 2: for tiles no scan certified alone, sum the calibrated
        per-scan LLRs (independent scans; within-scan correlation was
        removed by the one-owner reduce) and decode once more."""
        counts = {"certified": 0, "attempted": 0}
        capacity = compose.payload_capacity(self.spec)
        for page in self.pages:
            acc = np.zeros(capacity, np.float64)
            touched = np.zeros(capacity, bool)
            for emission in self.scans:
                vec = emission.pages.get(page)
                if vec is None:
                    continue
                acc[vec["index"]] += vec["llr"]
                touched[vec["index"]] = True
            idx = np.flatnonzero(touched)
            if idx.size == 0:
                continue
            llr = acc[idx]
            for tile_yx in sorted(self._payload_tiles(page, idx)):
                out = self.outcome(page, tile_yx)
                if out.state in ("certified", "degenerate"):
                    continue
                counts["attempted"] += 1
                if self._attempt(out, llr, idx, "union"):
                    counts["certified"] += 1
        return counts

    # -- post-certification instruments ---------------------------------------
    def certified_payload_indices(self, out: TileOutcome
                                  ) -> tuple[np.ndarray, np.ndarray]:
        """(payload indices, transmitted payload bits) of a certified tile —
        the re-encode primitive (F9 family): user bits + rate regenerate
        the codeword and CRC deterministically."""
        assert out.state == "certified" and out.user_bits is not None
        mask = self.shorten_mask(out.tile_yx)
        _cw, tx_bits = ldpc.encode_tile(out.user_bits, mask, self.ldpc_spec)
        pidx = ldpc._tile_payload_indices(out.tile_yx, self.spec, self.seed,
                                          mask)
        return pidx, tx_bits

    def divergence_pass(self) -> None:
        """Post-certification payload-vs-pilot instrument: per certified
        tile, each scan's hard-decision disagreement against the certified
        bits (the production divergence alarm — no GT involved)."""
        for out in self.tiles.values():
            if out.state != "certified":
                continue
            pidx, tx_bits = self.certified_payload_indices(out)
            order = np.argsort(pidx, kind="stable")
            sorted_idx, sorted_bits = pidx[order], tx_bits[order]
            for emission in self.scans:
                vec = emission.pages.get(out.page)
                if vec is None:
                    continue
                pos = np.searchsorted(sorted_idx, vec["index"])
                ok = (pos < sorted_idx.size)
                ok[ok] = sorted_idx[pos[ok]] == vec["index"][ok]
                if not ok.any():
                    continue
                hard = (vec["llr"][ok] > 0).astype(np.uint8)
                want = sorted_bits[pos[ok]]
                out.divergence[emission.scan_id] = float(
                    np.mean(hard != want))

    # -- persistence -----------------------------------------------------------
    def to_payload(self) -> dict:
        return {
            "magic": STATE_MAGIC,
            "version": STATE_VERSION,
            "format_id": self.format_id,
            "seed": self.seed,
            "rate_id": self.rate_id,
            "pages": self.pages,
            "upstream": self.upstream,
            "n_attempts": self.n_attempts,
            "fatal": list(self.fatal),
            "scans": [{
                "scan_id": s.scan_id,
                "source_sha256": s.source_sha256,
                "pages": {int(p): {k: np.asarray(v) for k, v in vec.items()}
                          for p, vec in s.pages.items()},
                "window_rows": s.window_rows,
            } for s in self.scans],
            "tiles": {key: {
                "state": out.state,
                "user_bits": (None if out.user_bits is None
                              else np.packbits(out.user_bits)),
                "n_user_bits": (0 if out.user_bits is None
                                else int(out.user_bits.size)),
                "certified_by": out.certified_by,
                "k_eff": out.k_eff,
                "n_informative_best": out.n_informative_best,
                "n_nonshort": out.n_nonshort,
                "n_iters": out.n_iters,
                "attempts": out.attempts,
                "divergence": dict(out.divergence),
            } for key, out in self.tiles.items()},
        }

    @classmethod
    def from_payload(cls, payload: dict, descriptor: FormatDescriptor
                     ) -> "DecodeState":
        if (not isinstance(payload, dict)
                or payload.get("magic") != STATE_MAGIC):
            raise ValueError("not an e023 state")
        if int(payload.get("version", -1)) != STATE_VERSION:
            raise ValueError(
                f"e023 state version {payload.get('version')} != "
                f"{STATE_VERSION}")
        if (payload["format_id"] != descriptor.format_id
                or bytes(payload["seed"]) != descriptor.seed):
            raise ValueError("e023 state format/seed mismatch")
        state = cls(descriptor, str(payload["rate_id"]),
                    tuple(payload["pages"]), tuple(payload["upstream"]))
        state.n_attempts = int(payload["n_attempts"])
        state.fatal = list(payload["fatal"])
        for row in payload["scans"]:
            state.scans.append(ScanEmission(
                scan_id=str(row["scan_id"]),
                source_sha256=str(row["source_sha256"]),
                pages={int(p): {k: np.asarray(v) for k, v in vec.items()}
                       for p, vec in row["pages"].items()},
                window_rows=list(row["window_rows"]),
            ))
        for key, row in payload["tiles"].items():
            n_user = int(row["n_user_bits"])
            bits = None
            if row["user_bits"] is not None:
                bits = np.unpackbits(np.asarray(row["user_bits"],
                                                np.uint8))[:n_user]
            out = TileOutcome(
                page=int(key[0]), tile_yx=(int(key[1]), int(key[2])),
                state=str(row["state"]), user_bits=bits,
                certified_by=str(row["certified_by"]),
                k_eff=int(row["k_eff"]),
                n_informative_best=int(row["n_informative_best"]),
                n_nonshort=int(row["n_nonshort"]),
                n_iters=int(row["n_iters"]), attempts=int(row["attempts"]),
                divergence=dict(row["divergence"]))
            state.tiles[(out.page, *out.tile_yx)] = out
        return state

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for out in self.tiles.values():
            counts[out.state] = counts.get(out.state, 0) + 1
        certified_user_bits = sum(
            int(out.user_bits.size) for out in self.tiles.values()
            if out.state == "certified" and out.user_bits is not None)
        divergences = [rate for out in self.tiles.values()
                       for rate in out.divergence.values()]
        return {
            "tiles": counts,
            "certified_user_bits": certified_user_bits,
            "n_attempts": self.n_attempts,
            "crc_false_accept_budget": self.n_attempts * CRC_FALSE_ACCEPT,
            "divergence_mean": (float(np.mean(divergences))
                                if divergences else None),
            "divergence_max": (float(np.max(divergences))
                               if divergences else None),
            "fatal": list(self.fatal),
            "scans": [s.scan_id for s in self.scans],
        }


def full_tile_states(state: DecodeState) -> dict[tuple[int, int, int], str]:
    """Every (page, ty, tx) of every legal page classified — untouched
    payload tiles read `unobserved`, capacity-0 tiles `degenerate` (the
    pane-D/report enumeration; outcomes dict only holds touched tiles)."""
    out: dict[tuple[int, int, int], str] = {}
    for page in state.pages:
        for tile_yx in ldpc.tile_grid(state.spec.page_cells_yx):
            key = (page, tile_yx[0], tile_yx[1])
            existing = state.tiles.get(key)
            if existing is not None and existing.state != "unobserved":
                out[key] = existing.state
            elif ldpc.tile_user_capacity(
                    ldpc.tile_shorten_mask(tile_yx, state.spec, state.seed),
                                         state.ldpc_spec) == 0:
                out[key] = "degenerate"
            else:
                out[key] = "unobserved"
    return out


_PAYLOAD_INV_CACHE: dict[tuple, np.ndarray] = {}


def _payload_inverse(spec: "compose.ComposeSpec", seed: bytes) -> np.ndarray:
    """(capacity, 2) int32: payload index -> absolute page cell."""
    key = (seed, spec.encoding_id, tuple(spec.page_cells_yx),
           spec.pilot.version)
    if key not in _PAYLOAD_INV_CACHE:
        pim = compose.payload_index_map(spec, seed)
        cells = np.argwhere(pim >= 0)
        order = np.argsort(pim[cells[:, 0], cells[:, 1]], kind="stable")
        _PAYLOAD_INV_CACHE[key] = cells[order].astype(np.int32)
    return _PAYLOAD_INV_CACHE[key]


# ---------------------------------------------------------------------------
# state file I/O (atomic; unchanged-prefix append-only resume)
# ---------------------------------------------------------------------------

def save_state(path: Path | str, state: DecodeState) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(pickle.dumps(state.to_payload(),
                                 protocol=pickle.HIGHEST_PROTOCOL))
    os.replace(tmp, path)


def load_state(path: Path | str, descriptor: FormatDescriptor
               ) -> DecodeState:
    return DecodeState.from_payload(
        pickle.loads(Path(path).read_bytes()), descriptor)


def resume_check(state: DecodeState, session: E022Session) -> int:
    """Unchanged-prefix + append-only: returns the number of upstream scans
    already ingested; raises on any mutation/reordering (use --fresh)."""
    done = tuple((s.scan_id, s.source_sha256) for s in state.scans)
    fingerprint = session.fingerprint
    if done != fingerprint[:len(done)]:
        raise ValueError(
            "e023 state does not prefix-match the e022 session "
            "(upstream mutated or reordered) — pass --fresh")
    return len(done)


# ---------------------------------------------------------------------------
# one-call pipeline (driver + tests)
# ---------------------------------------------------------------------------

def run_session(session: E022Session, descriptor: FormatDescriptor,
                *, rate_id: str | None = None,
                state: DecodeState | None = None,
                image_loader=None,
                on_scan=None) -> DecodeState:
    """Emit + stage-1 decode every not-yet-ingested scan, then the stage-2
    union pass and the divergence instrument. image_loader(path) -> 2-D
    grey array (defaults to tifffile/PIL via _load_image)."""
    rate = rate_id or descriptor.ldpc_rate
    if rate is None:
        raise ValueError(f"{descriptor.format_id} carries no ldpc_rate; "
                         "pass rate_id explicitly")
    if state is None:
        state = DecodeState(descriptor, rate, session.pages,
                            session.fingerprint)
    else:
        if state.rate_id != rate:
            raise ValueError("e023 state rate mismatch")
    start_at = resume_check(state, session)
    loader = image_loader or _load_image
    spec = state.spec
    for scan in session.scans[start_at:]:
        t0 = perf_counter()
        sha = file_sha256(scan.source_path)
        if sha != scan.source_sha256:
            raise ValueError(f"{scan.source_path}: sha256 mismatch vs the "
                             "e022 record — scans must be immutable")
        image = loader(scan.source_path)
        emission = emit_scan(scan, image, spec, state.seed, state.pages)
        counts = state.ingest_scan(emission)
        if on_scan is not None:
            on_scan(state, scan.scan_id, counts, perf_counter() - t0)
    union_counts = state.decode_union()
    state.divergence_pass()
    if on_scan is not None:
        on_scan(state, "union", union_counts, 0.0)
    return state


def _load_image(path: str) -> np.ndarray:
    import tifffile
    from PIL import Image
    p = Path(path)
    if p.suffix.lower() in (".tif", ".tiff"):
        arr = tifffile.TiffFile(str(p)).pages[0].asarray(out="memmap")
        if arr.ndim == 3:
            return arr[..., :3].mean(axis=2, dtype=np.float32)
        return arr
    Image.MAX_IMAGE_PIXELS = None
    return np.asarray(Image.open(p).convert("L"))
