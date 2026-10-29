"""``tiles.planek`` — read one printing plane as a black-and-white page.

THE COMPOSITION.  cmy8 is per-plane independent LDPC — format law, not a
convenience — so one plane's stream is a codeword in its own right and
can be decoded alone.  This row builds that stand-alone decoder input:
it isolates the target plane out of the RGB channel means (cancelling
the two sibling planes in the mean, and subtracting them exactly wherever
a certificate or the format proves their bits), hands the result to the
BLACK-AND-WHITE machinery — `calibrate.window_scores`, the PAVA
score-to-probability map, the nine-bin neighbour-count context detector —
and pushes the calibrated LLRs through the UNCHANGED codec at the heavy
BP budget.  Nothing about the format changes; the certificate is minted
by `tiles.attempt_tile` like any other, and zero-wrong is inherited from
that gate.

WHY IT IS A ROW AND NOT A DEFAULT.  The measured record is
`measure/yask` (sheet H, `L:c2-cmy8-r0850-p120-x1@3392x2368`, one to
seven Canon captures, 2026-08-30).  Against a seven-capture production
harvest of the same sheet it recovered **32 yellow tiles the harvest did
not have, zero wrong**, on tiles where the ordinary colour path had
already certified C and M.  The ladder that got there is the shape of
this row:

    raw blue channel                                  0 adds
    + cyan and magenta cancelled in the mean          1
    + per-cell certified-sibling subtraction          5
    + blind per-window sampling offset (dust)        15
    + the ordinary multi-capture union               32

The first line is why the naive reading is not built: magenta darkens
blue by 60% of what yellow does, so the blue channel is a
yellow-plus-magenta readout and reading it raw certifies NOTHING.
`lib/spectral` carries that argument in full.

The same record says the arm is a RESIDUE arm by construction, not a
detector improvement: with the certified neighbours' labels removed it
certifies zero on every crop, even though the isolated signal is
measurably no worse (d' 2.480 against 2.459).  A PAVA map fitted on 120
format sites per tile cannot price 3,976 payload cells.  So eligibility
is `tiles.local`'s shape — uncertified, covered by evidence and a
committed pose, with certified material in the neighbourhood — and the
row prices itself above every other residue row.

PLANE-GENERAL, and every per-cell stream.  Yellow off blue is the
measured case; cyan off red and magenta off green are the same
arithmetic with a different column, so the row takes its target plane
from the subject's stream and one code path serves all three.  cmy7 is
refused at birth: its base-7 packing is a JOINT symbol over the three
planes and does not decompose, so there is no per-plane codeword to
decode; K has no sibling to cancel.

cmy's LABEL STREAMS, TRANSLATED (R25, 2026-10-12): a label bit is a
sum of toner presences (`tile_codec.stream_toners`), read as the sum of
the toners' isolated reads — the composition is `plugins/plane_label`,
whose docstring carries the derivation; this module's per-plane
machinery is what it sums.

TRANSIENT.  Every fit here — the mixing model, the sampling offset, the
PAVA map, the context correction — is built inside the job, used for one
decoder input and dropped.  The row writes no standing evidence row, no
region context cell and no pose; it emits `AttemptFact` and
`Certificate` and nothing else, so the ordinary colour head, the other
tile rows and the close are untouched whatever it decides.

WHAT THIS ROW REUSES, AND WHAT IT OWNS.  The truth at a window's cells is
`color_region.build_window_rows` verbatim (the colour lane's own
furniture-plus-certified-projection evidence).  The sampler is
`calibrate.window_crop` + `calibrate.sample_points`, the two primitives
`calibrate.sampled_window_means` fuses — unfused here because the offset
search reads ONE filtered crop at many point sets.  The calibration is
`calibrate.window_evidence` and `calibrate.apply_region_context`,
unchanged.  The cut is `tiles.color_candidates` + `tiles.assemble_cut`
over transient `ColorEvidenceRow`s.  What this module owns is the
composition and one thing nothing else in holo3 does: choosing a
window's sampling offset BLIND, on the format's own dust sites.
"""

from __future__ import annotations

import functools
import time
from dataclasses import dataclass, replace
from typing import Sequence

import numpy as np

from ..data import (
    AttemptFact,
    Certificate,
    ColorEvidenceRow,
    JobResult,
    LaneKey,
    PlaneField,
    PlaneRaster,
    Placement,
    WindowEvidence,
    WindowRows,
)
from ..descriptor import (
    FactKey,
    Job,
    KEY_ATTEMPT,
    KEY_PLANE_FIELD,
    KEY_POSE_AFFINE,
    KEY_TILE,
    PluginDescriptor,
    RETIRE_CERTIFIED,
    Subject,
)
from ..format import tile_codec
from ..format.identity import FormatRow, SiteGeometry
from ..lib import page_map
from ..lib import spectral
from . import calibrate, color_region, local_ctx, tiles

PLUGIN: str = "tiles.planek"
STAGE_PLANEK: str = "planek"

# LATE RESIDUE WORK, priced above every row that does strictly less.  One fire
# re-reads every covering window on three channels, searches that
# window's sampling offset over a grid (one filtered crop, many point
# sets, one PAVA fit apiece) and then spends the heavy 150-iteration
# payload attempt — strictly more per tile than `tiles.local` at 220,
# which pays one context fit or one head re-fit plus the same attempt,
# and than `tiles.uplift` at 210/220, which amortises one region
# derivation over a whole lane-page.  It also only ever exists for a
# tile those rows have already failed.  So it queues behind all of them.
# Only `tiles.swim` (240) sits above it: a full local colour head
# (`tiles.local`, 220) with a per-plane raster search in front of it.
PLANEK_COST: int = 230
RUNG_COST: int = 2
PRICES: tuple[tuple[str, int], ...] = ((STAGE_PLANEK, PLANEK_COST),)

# A failed ordinary or retried attempt is what gives this row a subject —
# `tiles.local`'s arming set exactly.  Its own facts never arm it again;
# it re-fires when the covering evidence or a neighbouring certificate
# moves, which is what its declared reads subscribe to.
ARMING_STAGES: tuple[str, ...] = (
    tiles.STAGE_SCAN, tiles.STAGE_UNION, tiles.STAGE_RETRY150)

# The blind sampling-offset grid, in printed DOTS along page +x.  Both
# ends and the step are the measured harness's (`measure/yask`,
# `--shift-min/--shift-max/--shift-step`); the object being searched is
# e033's measured per-plane x-registration sinusoid, 0.83 dot peak and
# ~100 mm period, which +-2 dots covers with room to spare.  The search
# is x-only because that is the axis the sinusoid lives on and the axis
# the yask battery measured; a y arm is unmeasured and unbuilt.
SHIFT_MIN_DOTS: float = -2.0
SHIFT_MAX_DOTS: float = 2.0
SHIFT_STEP_DOTS: float = 0.25

REASON_NO_LANE: str = "no_covering_lane"
REASON_NO_MIX: str = "mix_refused"

# THE OBJECTIVE'S RESOLUTION, and not a bar (RULED 2026-09-08).  The
# held-out log loss is read through a 0.7-cell box aperture, so on a
# noise-free page it has a flat basin about half a dot wide and the
# argmin inside that basin is arithmetic rather than measurement: the
# W3a build moved a field standing exactly at the truth by half a dot on
# a 1.6e-9 difference.  A candidate displaces the value the sweep was
# centred on only when it beats it by more than this, which is a
# statement about what the objective can tell apart — searchers search
# AROUND the field (design §2.8), and a search that cannot separate two
# points has nothing to say about them.
LOSS_TOLERANCE: float = 1e-6

#: What a window's read was offset by, for the instruments' ledger.
#: The two search spellings are the same sweep and differ only in what
#: it was centred on: `field+search` means the page had solved this
#: plane here and the scalar is measured FROM that, `search` means the
#: field read zero and the scalar is the whole correction.  The
#: spellings `read_window` STARTS at — `nominal`, `field`, `pose-only`,
#: `field+shift` — survive for the read whose labels never scored:
#: every candidate skipped leaves `best_loss` unset and the source is
#: whatever `read_window` gave it.  (A window whose MIX refused never
#: reaches the sweep at all — `lane_read` returns before it.)
SOURCE_NOMINAL: str = "nominal"
SOURCE_FIELD: str = "field"
SOURCE_SEARCH: str = "search"
SOURCE_FIELD_SEARCH: str = "field+search"
#: The fifth: a field stood here and this window's own labels PREFERRED
#: the pose (RULED 2026-09-08).  The sweep is x-only and centred on the
#: field, so without this candidate a field wrong in y — or wrong by
#: more than the sweep reaches in x — takes the pose out of the
#: candidate set altogether, and the window is read through an error it
#: could have measured its way out of.  Scored last, so a tie keeps the
#: field.
SOURCE_POSE: str = "pose"
#: The sixth, and it is a different event: the read is at the pose
#: because the field's own points left the RASTER, so no field candidate
#: was ever scored (W8 R-E, `start_candidates`).  A preference and a
#: rescue count the same in a ledger that spells them alike, and they
#: say opposite things about the field — one that it is wrong here, one
#: that this window sits at the edge of the scan.
SOURCE_POSE_ONLY: str = "pose-only"
#: The seventh: the field AND the pose both left the raster and the read
#: starts at one of the field's own declared shifts (R7, RULED
#: 2026-09-09).  That scalar was picked by RASTER MARGIN and not by the
#: objective — it is an admission, not a measurement — so it is spelled
#: apart from `field+search`, which is what the sweep answers with.
SOURCE_FIELD_SHIFT: str = "field+shift"

TileAddress = tuple[int, int]


def shift_grid() -> tuple[float, ...]:
    """The declared offset candidates, nominal first so a tie keeps it."""
    steps = int(round((SHIFT_MAX_DOTS - SHIFT_MIN_DOTS) / SHIFT_STEP_DOTS))
    grid = [round(SHIFT_MIN_DOTS + index * SHIFT_STEP_DOTS, 6)
            for index in range(steps + 1)]
    return (0.0,) + tuple(value for value in grid if value != 0.0)


@dataclass(frozen=True)
class LanePlan:
    """One capture-level's covering windows, read from the store once."""

    lane: LaneKey
    windows: tuple[color_region.RegionWindow, ...]
    placements: tuple[Placement, ...]
    region_indices: tuple[int, ...]
    planes: tuple[PlaneRaster, PlaneRaster, PlaneRaster]
    #: the standing per-plane registration field for the TARGET plane on
    #: this lane-page, or None when none is published
    field: PlaneField | None


@dataclass
class WindowRead:
    """One window's plane-isolated read at the offset it chose."""

    window: color_region.RegionWindow
    placement: Placement
    region_index: int
    rows: WindowRows
    labels: np.ndarray
    values: np.ndarray
    offset_source: str
    shift_dots: float
    evidence: WindowEvidence | None = None


def plane_labels(rows: WindowRows, plane: int) -> np.ndarray:
    """int8 labels for the black-and-white calibration; -1 = unproven.

    On a K page the 100 word sites of a tile are a BCH codeword under a
    keystream scramble, so labels are about half ones.  On a single
    colour plane they are not: the colour address word renders states
    {0, 3}, whose YELLOW bit is zero at every word site, so a yellow
    read's only furniture marks are the 20 dust sites per tile.  That
    asymmetry is format law and it is why this row needs certified
    neighbours to be useful at all — measured in `measure/yask` §4.3,
    where furniture-only labels certify nothing on any crop.
    """
    bits = np.asarray(rows.known_component_bits, np.uint8)
    known = np.asarray(rows.known_component_mask, bool)
    labels = np.full(bits.shape[0], -1, np.int8)
    proven = known[:, plane]
    labels[proven] = bits[proven, plane]
    return labels


def stream_labels(rows: WindowRows, toners: Sequence[int]) -> np.ndarray:
    """A LABEL stream's int8 labels: its toners' presence summed where
    every plane is proven, -1 elsewhere (`plugins/plane_label`)."""
    bits = np.asarray(rows.known_component_bits, np.uint8)
    proven = np.asarray(rows.known_component_mask, bool).all(axis=1)
    labels = np.full(bits.shape[0], -1, np.int8)
    labels[proven] = bits[proven][:, list(toners)].sum(axis=1)
    return labels


def field_delta_dots(field: PlaneField | None,
                     page_cells_yx: np.ndarray) -> np.ndarray:
    """The standing field's per-cell delta at these cells, always.

    THE FIELD IS WHERE THE SEARCH STARTS, not what replaces it.  The
    solve publishes a complete grid with no floor and no support gate
    (design §2.8, I6/I8), so a tile no evidence ever reached reads
    exactly zero — the pose — and a tile the page has measured reads
    what it measured.  `choose_offset` then sweeps around that value on
    this window's own held-out labels, because a page-scale field and a
    per-window scalar are different measurements of different things
    and the window's own labels are what adjudicate them.

    The evaluation is the colour lane's own (`lib/page_map`), so this
    row samples where the standing colour head samples.
    """
    cells = np.asarray(page_cells_yx, np.int64)
    if field is None:
        return np.zeros((cells.shape[0], 2), np.float64)
    return page_map.plane_delta_dots(field, cells)


def offset_points(window: color_region.RegionWindow, cell_dots: int,
                  delta_dots_xy: np.ndarray,
                  shift_dots: float) -> np.ndarray:
    """The window's scan points moved by a field delta and an x shift.

    Both are PAGE-axis dots and both go through the one mapping, so the
    sweep runs along the printer's x whatever rotation this scrap was
    placed at.
    """
    delta = np.asarray(delta_dots_xy, np.float64)
    if shift_dots:
        delta = delta + np.asarray((shift_dots, 0.0), np.float64)
    if not np.any(delta):
        return np.asarray(window.scan_points_yx, np.float64)
    return page_map.raster_points(
        np.asarray(window.scan_points_yx, np.float64),
        window.page_linear, delta, cell_dots)


def channel_crops(planes: Sequence[np.ndarray],
                  bound_points: Sequence[np.ndarray],
                  pitch_px: float) -> tuple[calibrate.WindowCrop, ...]:
    """One aperture-filtered crop per channel, covering every point set.

    `calibrate.sampled_window_means` fuses the crop and the read because
    the ordinary path reads one point set.  This row reads many (the
    offset grid), and the crop is the expensive half, so the two
    primitives are used unfused.  The bounds come from the EXTREME point
    sets: the offset enters the scan points affinely, so the bounding box
    of the extremes contains every intermediate candidate.
    """
    shape = (int(planes[0].shape[0]), int(planes[0].shape[1]))
    spanning = np.concatenate([np.asarray(points, np.float64)
                               for points in bound_points])
    return tuple(calibrate.window_crop((planes[channel],), spanning, shape,
                                       pitch_px)
                 for channel in range(spectral.N_PLANES))


def sample_channels(crops: Sequence[calibrate.WindowCrop],
                    points_yx: np.ndarray) -> np.ndarray:
    """(N, 3) aperture-filtered channel means at one point set."""
    return np.stack([calibrate.sample_points(crop, points_yx)
                     for crop in crops], axis=1).astype(np.float64)


def isolated_scores(mix: spectral.PlaneMix, read: WindowRead,
                    values: np.ndarray, plane: int,
                    mode: str = spectral.MODE_SUBTRACT) -> np.ndarray:
    """The synthetic black-on-white luma, in `window_scores` units.

    Ink is DARK, so the synthetic luma is the NEGATED plane presence;
    `window_scores` then removes level and scale exactly as it does for
    a real grey window.  `mode` is the readout (`lib/spectral`): a cmy
    label's toners read PROJECT (`plugins/plane_label`).
    """
    score = spectral.plane_score(
        mix, values, read.rows.known_component_bits,
        read.rows.known_component_mask, plane, mode)
    return calibrate.window_scores(np.asarray(-score, np.float32))


def heldout_loss_at(mix: spectral.PlaneMix, read: WindowRead,
                    values: np.ndarray, plane: int,
                    mode: str = spectral.MODE_SUBTRACT) -> float | None:
    """holo3's own model-selection number for one candidate offset.

    `fit_window_calibration` splits the window's PROVEN labels by site
    parity and reports the log loss of the PAVA map on the half it did
    not see.  Comparing that across offsets compares models on one fixed
    held-out label set — the ordinary use of a held-out score, and blind:
    in a band with no certificate at all the labels are the format's own
    dust states and nothing else.
    """
    fit = calibrate.fit_window_calibration(
        isolated_scores(mix, read, values, plane, mode), read.labels,
        read.rows.page_cells_yx)
    return fit.heldout_logloss if fit.accepted else None


def choose_offset(mix: spectral.PlaneMix, read: WindowRead,
                  planes: Sequence[np.ndarray], cell_dots: int,
                  delta_dots_xy: np.ndarray, plane: int,
                  mode: str = spectral.MODE_SUBTRACT) -> WindowRead:
    """Pick this window's sampling offset on its own held-out labels.

    The sweep is CENTRED ON THE FIELD: every candidate is the field's
    own per-cell delta plus one scalar x shift, and the nominal shift
    leads the grid so a tie keeps the field's answer whole.  A tie here
    is `LOSS_TOLERANCE` wide, because that is the resolution the
    objective has.  The POSE is a candidate of its own (`SOURCE_POSE`),
    last, so the field's answer is never displaced by a tie with it —
    and when it wins because no field candidate reached the raster at
    all, the ledger says `SOURCE_POSE_ONLY` instead.
    """
    delta = np.asarray(delta_dots_xy, np.float64)
    standing = bool(np.any(delta))
    zero = np.zeros_like(delta)
    candidates = [(delta, shift,
                   SOURCE_FIELD_SEARCH if standing else SOURCE_SEARCH)
                  for shift in shift_grid()]
    if standing:
        candidates.append((zero, 0.0, SOURCE_POSE))
    extremes = [offset_points(read.window, cell_dots, at, shift)
                for at, shift in ((delta, SHIFT_MIN_DOTS),
                                  (delta, SHIFT_MAX_DOTS), (delta, 0.0),
                                  (zero, 0.0))]
    shape = (int(planes[0].shape[0]), int(planes[0].shape[1]))
    crops = channel_crops(planes, extremes, read.window.pitch_px)
    best_loss: float | None = None
    field_scored = False
    for at, shift, source in candidates:
        points = offset_points(read.window, cell_dots, at, shift)
        if not calibrate.points_inside_raster(points, shape):
            continue
        values = sample_channels(crops, points)
        loss = heldout_loss_at(mix, read, values, plane, mode)
        if loss is None:
            continue
        field_scored = field_scored or source != SOURCE_POSE
        if best_loss is None or loss < best_loss - LOSS_TOLERANCE:
            best_loss = loss
            read.values = values
            read.shift_dots = float(shift)
            read.offset_source = (source if field_scored
                                  else SOURCE_POSE_ONLY)
    return read


def raster_margin_px(points_yx: np.ndarray,
                     raster_shape_yx: tuple[int, int]) -> float:
    """How far inside the raster the tightest of these points sits.

    The ADMISSION ORDERING KEY, in pixels and signed the obvious way:
    negative is exactly `calibrate.points_inside_raster`'s refusal, and
    that call stays the gate.  What this ranks is how much scan a
    candidate still has around it, which is the only thing separating
    two declared shifts before either has been sampled.
    """
    points = np.asarray(points_yx, np.float64)
    return float(min(points[:, 0].min(), points[:, 1].min(),
                     raster_shape_yx[0] - 1 - points[:, 0].max(),
                     raster_shape_yx[1] - 1 - points[:, 1].max()))


def shifted_starts(window: color_region.RegionWindow, cell_dots: int,
                   delta_dots_xy: np.ndarray,
                   raster_shape_yx: tuple[int, int]
                   ) -> tuple[tuple[np.ndarray, float, str], ...]:
    """The field's declared shifts as starts, deepest in the scan first.

    `raster_point_grid` is `offset_points` broadcast, so the whole grid
    costs one point map.  The sort is stable, so shifts that sit equally
    deep keep `shift_grid`'s own order and the choice is deterministic.
    """
    delta = np.asarray(delta_dots_xy, np.float64)
    shifts = tuple(shift for shift in shift_grid() if shift != 0.0)
    offsets = np.zeros((len(shifts), 2), np.float64)
    offsets[:, 0] = shifts
    grid = page_map.raster_point_grid(
        offset_points(window, cell_dots, delta, 0.0), window.page_linear,
        offsets, cell_dots)
    margins = [raster_margin_px(points, raster_shape_yx) for points in grid]
    order = sorted(range(len(shifts)), key=margins.__getitem__, reverse=True)
    return tuple((delta, shifts[index], SOURCE_FIELD_SHIFT)
                 for index in order)


def start_candidates(window: color_region.RegionWindow, cell_dots: int,
                     delta_dots_xy: np.ndarray,
                     raster_shape_yx: tuple[int, int]
                     ) -> tuple[tuple[np.ndarray, float, str], ...]:
    """Where the nominal read may start, best first.

    The field, then the pose, then the field's own declared shifts (R7,
    RULED 2026-09-09).  A field value is never an ADMISSION condition
    (design §2.8, W8 R-E): the read is initialised from the first viable
    candidate and candidates are rejected one at a time, so a field that
    takes this window off the raster costs its own candidate and not the
    window.  The shifts are what W8 R-E left on the table — a page-edge
    window whose field and pose BOTH point off the scan is read at the
    shift that reaches furthest in, rather than refused in front of a
    candidate set the sweep would have scored anyway.

    Only while a field stands.  With none there is nothing to shift: the
    pose is the whole declared set, and a pose off the raster is the
    same refusal it has always been.
    """
    delta = np.asarray(delta_dots_xy, np.float64)
    if not np.any(delta):
        return ((delta, 0.0, SOURCE_NOMINAL),)
    return ((delta, 0.0, SOURCE_FIELD),
            (np.zeros_like(delta), 0.0, SOURCE_POSE_ONLY),
            *shifted_starts(window, cell_dots, delta, raster_shape_yx))


def read_window(row: FormatRow, geometry: SiteGeometry,
                window: color_region.RegionWindow, placement: Placement,
                region_index: int, planes: Sequence[np.ndarray],
                cell_dots: int, certificates: dict, memo: dict,
                field: PlaneField | None,
                plane: int) -> tuple[WindowRead, np.ndarray | None] | None:
    """Nominal read of one window: truth, labels, channel means.

    The window is refused only when NO candidate reaches the raster —
    review F9, where a page-edge window whose field pointed off the
    scan lost the pose that would have read it, and R7, where it lost
    the declared shifts as well (`start_candidates`).  The start is
    recorded as it was taken, and it is NOT a starting value for the
    sweep: `choose_offset` rebuilds its candidates from the field
    (design §2.8) and scores them from scratch.  These values reach
    `fit_lane_mix`, which is fitted before the sweep runs, in every case
    — and they are the evidence itself when the sweep scores nothing at
    all.
    """
    rows = color_region.build_window_rows(row, geometry, window,
                                          certificates, memo)
    if not np.asarray(rows.page_cells_yx).shape[0]:
        return None
    delta = field_delta_dots(field, rows.page_cells_yx)
    shape = (int(planes[0].shape[0]), int(planes[0].shape[1]))
    for at, shift, source in start_candidates(window, cell_dots, delta,
                                              shape):
        points = offset_points(window, cell_dots, at, shift)
        if calibrate.points_inside_raster(points, shape):
            break
    else:
        return None
    crops = channel_crops(planes, (points,), window.pitch_px)
    values = sample_channels(crops, points)
    return (WindowRead(window=window, placement=placement,
                       region_index=region_index, rows=rows,
                       labels=plane_labels(rows, plane), values=values,
                       offset_source=source, shift_dots=float(shift)), delta)


def fit_lane_mix(reads: Sequence[WindowRead]) -> spectral.PlaneMix:
    """The mixing model over every covering window of this lane.

    Lane scope, not window scope: the fit needs cells proven in all three
    planes, and pooling the covering windows is what keeps a window whose
    own certified reach is thin from refusing on class starvation.  It is
    also the measured harness's scope.
    """
    return spectral.fit_plane_mix(
        np.concatenate([read.values for read in reads]),
        np.concatenate([read.rows.known_component_bits for read in reads]),
        np.concatenate([read.rows.known_component_mask for read in reads]))


def calibrated_rows(reads: Sequence[WindowRead], mix: spectral.PlaneMix,
                    plane: int) -> tuple[WindowEvidence, ...]:
    """The PAVA fit per window, then the region context over them all."""
    built = []
    for read in reads:
        scores = isolated_scores(mix, read, read.values, plane)
        built.append(calibrate.window_evidence(
            read.placement, read.rows.page_cells_yx, scores, read.labels))
    corrected, _ctx = calibrate.apply_region_context(tuple(built))
    return corrected


def transient_row(read: WindowRead, evidence: WindowEvidence,
                  toners: Sequence[int],
                  arity: int) -> ColorEvidenceRow | None:
    """The calibrated stream as a colour evidence row, never emitted.

    The toner columns carry the calibrated LLRs and the rest 0.0 — the
    erasure spelling — so `tiles._attempt_stream` reads exactly the one
    stream this row is arming: a cmy8 plane's own column, a cmy label's
    product form (module docstring), and nothing at all about what the
    row did not read.
    """
    if not evidence.accepted or evidence.heldout_logloss is None:
        return None
    values = np.zeros((int(evidence.page_cells_yx.shape[0]), arity),
                      np.float32)
    values[:, list(toners)] = np.asarray(evidence.printed_llr,
                                         np.float32)[:, None]
    return ColorEvidenceRow(
        capture_id=evidence.capture_id, level_index=evidence.level_index,
        patch_ordinal=read.window.patch_ordinal, page=evidence.page,
        page_cells_yx=np.asarray(evidence.page_cells_yx, np.int64),
        values=values, heldout_logloss=float(evidence.heldout_logloss))


@dataclass(frozen=True)
class LaneRead:
    """One lane's finished plane-isolated evidence, before any address.

    The split is where the cost is.  Everything above — three-channel
    sampling, the mixing fit, the offset search, the PAVA maps and the
    context correction — depends on the LANE and not on which tile is
    being attempted; only the cut below does.  Keeping the two apart
    makes that structure visible, keeps `lane_cut` honest about what it
    re-does per tile, and lets an instrument replay the identical
    arithmetic over many tiles without pretending the row is cheaper
    than it is.
    """

    lane: LaneKey
    mix: spectral.PlaneMix
    rows: tuple[tuple[object, int, ColorEvidenceRow], ...]
    offsets: tuple[tuple[int, str, float], ...]


def plane_reads(row: FormatRow, geometry: SiteGeometry, plan: LanePlan,
                certificates: dict, plane: int,
                planes: Sequence[np.ndarray], cell_dots: int, memo: dict,
                label_toner: bool = False,
                ) -> tuple[spectral.PlaneMix, list[WindowRead]] | None:
    """One plane's windows read, the lane's mix fitted, offsets chosen.

    `label_toner` is a cmy label stream's toner (`plugins/plane_label`):
    its labels are the plane's bit on proven cells only
    (`stream_labels`) and its offset is chosen on the PROJECT readout.
    """
    reads: list[WindowRead] = []
    deltas: list[np.ndarray] = []
    for window, placement, region_index in zip(
            plan.windows, plan.placements, plan.region_indices, strict=True):
        found = read_window(row, geometry, window, placement, region_index,
                            planes, cell_dots, certificates, memo,
                            plan.field, plane)
        if found is None:
            continue
        read, delta = found
        if label_toner:
            read.labels = stream_labels(read.rows, (plane,))
        reads.append(read)
        deltas.append(delta)
    if not reads:
        return None
    mix = fit_lane_mix(reads)
    if not mix.accepted:
        return None
    mode = spectral.MODE_PROJECT if label_toner else spectral.MODE_SUBTRACT
    for read, delta in zip(reads, deltas, strict=True):
        choose_offset(mix, read, planes, cell_dots, delta, plane, mode)
    return mix, reads


def lane_read(row: FormatRow, geometry: SiteGeometry, plan: LanePlan,
              certificates: dict, plane: int) -> LaneRead | None:
    """Read one capture-level's windows as a black-and-white page."""
    planes = tuple(raster.open() for raster in plan.planes)
    found = plane_reads(row, geometry, plan, certificates, plane, planes,
                        color_region.cell_dots_of(row), {})
    if found is None:
        return None
    mix, reads = found
    arity = tiles.evidence_arity(row)
    candidate_rows = []
    for read, evidence in zip(reads, calibrated_rows(reads, mix, plane),
                              strict=True):
        transient = transient_row(read, evidence, (plane,), arity)
        if transient is not None:
            candidate_rows.append(
                (read.window.window_id, read.region_index, transient))
    if not candidate_rows:
        return None
    return LaneRead(
        lane=plan.lane, mix=mix, rows=tuple(candidate_rows),
        offsets=tuple((int(read.window.patch_ordinal), read.offset_source,
                       float(read.shift_dots)) for read in reads))


def cut_of(read: LaneRead, row: FormatRow, geometry: SiteGeometry,
           page: int, ty: int, tx: int) -> tiles.TileCut | None:
    """One tile's cut out of a finished lane read."""
    return rows_cut(read.lane, read.rows, row, geometry, page, ty, tx)


def rows_cut(lane: LaneKey, rows: Sequence[tuple[object, int,
                                                 ColorEvidenceRow]],
             row: FormatRow, geometry: SiteGeometry, page: int, ty: int,
             tx: int) -> tiles.TileCut | None:
    candidates, order_keys = tiles.color_candidates(
        geometry, tiles.evidence_arity(row), page, ty, tx, rows)
    return tiles.assemble_cut(candidates, order_keys, row.cells_yx,
                              lane[0], lane[1], page, ty, tx)


def lane_cut(row: FormatRow, geometry: SiteGeometry, plan: LanePlan,
             certificates: dict, page: int, ty: int, tx: int,
             plane: int) -> tiles.TileCut | None:
    """One capture-level's plane-isolated cut of one tile."""
    read = lane_read(row, geometry, plan, certificates, plane)
    if read is None:
        return None
    return cut_of(read, row, geometry, page, ty, tx)


def attempt_components(row: FormatRow, geometry: SiteGeometry,
                       components: Sequence[tiles.TileCut], stream_id: str,
                       generation: int = 0,
                       ) -> tuple[tuple[object, ...], tuple[object, ...]]:
    """The one attempt, or nothing when no lane produced a cut.

    Several components are the ordinary MULTI-CAPTURE UNION: one cut per
    capture-level, summed by `tiles._combine` exactly as
    `tiles.prepare_union` sums them.  No new arithmetic — the same
    equal-weight LLR addition the receiver already performs, over
    per-capture context that has already been de-correlated (the F1 o F6
    law).  It is worth the largest single step in the measured ladder:
    15 adds on one capture, 32 over seven.
    """
    if not components:
        return (), ()
    result = tiles.attempt_tile(row, geometry, tuple(components), stream_id,
                                tiles.STAGE_PLANEK150, generation)
    facts: tuple[object, ...] = (
        (result.fact,) if result.certificate is None
        else (result.fact, result.certificate))
    return facts, (result.event,)


def planek_job(row: FormatRow, geometry: SiteGeometry,
               plans: Sequence[LanePlan], certificates: dict, page: int,
               ty: int, tx: int, stream_id: str, plane: int,
               generations: local_ctx.Generations | None = None,
               ) -> JobResult:
    """One plane-isolated attempt over every lane that produced a cut.

    The verdict is stamped through `local_ctx.Generations` (2026-10-03,
    S9): a summed attempt carries the footing's generation, but when
    only ONE lane produced a cut the attempt is keyed by that lane
    (`tiles.attempt_lane`), whose own counter is the tile-lane
    generation -- the footing's would make it stale-by-construction at
    its own key.
    """
    started = time.thread_time()
    components: list[tiles.TileCut] = []
    for plan in plans:
        cut = lane_cut(row, geometry, plan, certificates, page, ty, tx,
                       plane)
        if cut is not None:
            components.append(cut)
    stamps = generations or local_ctx.Generations()
    facts, events = attempt_components(row, geometry, components, stream_id,
                                       stamps.of(components))
    return JobResult(facts, events, time.thread_time() - started)


@functools.cache
def stream_toners(row: FormatRow, stream_id: str) -> tuple[int, ...]:
    """The planes this stream's bit sums; () = planek cannot read it.
    Cached: the birth gate asks on every verdict (20 us uncached)."""
    fact = tiles.stream_fact(row, stream_id)
    return tile_codec.stream_toners(row, row.streams.index(fact))


def readable(row: FormatRow) -> bool:
    """The birth gate: the row has streams planek can read (cmy8, cmy)."""
    return any(stream_toners(row, fact.stream_id) for fact in row.streams)


def lane_plans(store: object, page: int, ty: int, tx: int, ppc: object,
               plane: int) -> tuple[LanePlan, ...]:
    plans: list[LanePlan] = []
    for lane in store.cover_lanes(page, ty, tx, ppc):
        windows: list[color_region.RegionWindow] = []
        placements: list[Placement] = []
        region_indices: list[int] = []
        for row_key in local_ctx.covering_color_rows(store, page, ty, tx,
                                                     lane):
            wid = store.window_by_ordinal(lane[0], lane[1], int(row_key[3]))
            window = store.window(wid)
            placement = store.placement(wid)
            if window is None or placement is None:
                continue
            windows.append(color_region.region_window(store, wid))
            placements.append(placement)
            region_indices.append(int(window.region_index))
        if windows:
            plans.append(LanePlan(
                lane=lane, windows=tuple(windows),
                placements=tuple(placements),
                region_indices=tuple(region_indices),
                planes=store.rgb_planes(lane),
                field=store.page_plane_fields(page)[plane]))
    return tuple(plans)


def prepare_planek(store: object, subject: Subject,
                   stage: str) -> Job | None:
    """A toner stream reads its plane; a LABEL stream reads every toner
    its bit sums, each lane once per toner at that toner's field, and
    the sum is `plugins/plane_label`'s (imported here: it imports this
    module's per-plane machinery)."""
    page, ty, tx, stream_id, ppc = subject
    toners = stream_toners(store.row, stream_id)
    if not toners:
        return None
    if store.has_certificate((page, ty, tx, stream_id)):
        return None
    donors = local_ctx.certified_neighbours(
        store, page, local_ctx.neighbourhood_tiles(store, page, ty, tx, ppc),
        (ty, tx))
    if not donors:
        return None
    plane = toners[0]
    plans = lane_plans(store, page, ty, tx, ppc, plane)
    if not plans:
        return None
    row = store.row
    geometry = store.geometry
    certificates = store.certificates()
    # The GENERATIONS this fire reads, keyed as its verdict's wake is:
    # reported on every verdict it emits, so a later rung can tell a
    # live verdict from one decoded off evidence that has since moved.
    generations = local_ctx.lane_generations(store, page, ty, tx, ppc)
    if tiles.stream_fact(row, stream_id).label_index is not None:
        from . import plane_label

        fields = store.page_plane_fields(page)
        lanes = tuple(tuple(replace(plan, field=fields[toner])
                            for toner in toners) for plan in plans)

        def label_job() -> JobResult:
            return plane_label.label_job(row, geometry, lanes, certificates,
                                         page, ty, tx, stream_id, toners,
                                         generations)

        return label_job

    def job() -> JobResult:
        return planek_job(row, geometry, plans, certificates, page, ty, tx,
                          stream_id, plane, generations)

    return job


def _planek_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    """A readable row only (cmy8, cmy), and only from a failed ordinary
    attempt.

    The gate lives at BIRTH so the row has no subjects at all on a K or
    cmy7 page: nothing to schedule, nothing to consult, nothing to
    report.  cmy7's joint base-7 packing has no per-plane codeword, so
    there is no composition to attempt there — not a policy, an algebra.

    A colour row or an evidence row is the reach repair's re-birth
    (`local_ctx.COVER_BIRTH_FACTS`): one subject per stream this row's
    stages already ARMED in its cover, extending a standing bookmark and
    never creating one.
    """
    if not readable(store.row):
        return ()
    if isinstance(fact, local_ctx.COVER_BIRTH_FACTS):
        return tuple(
            (page, ty, tx, stream_id, ppc)
            for (page, ty, tx, ppc), armed
            in local_ctx.armed_cover_subjects(store, fact, ARMING_STAGES)
            for stream_id in armed)
    if fact.outcome != tiles.OUTCOME_FAILED:
        return ()
    if fact.stage not in ARMING_STAGES or not fact.components:
        return ()
    ppc = store.level(*fact.components[0]).ppc
    return ((fact.page, fact.ty, fact.tx, fact.stream_id, ppc),)


#: THE FOUR REAL INPUTS: this stream's own chain-head verdicts (scan
#: and union, `local_ctx.READ_STAGES`: a retry's failure arms but
#: carries nothing this row reads, 2026-10-03), the poses
#: the raster is sampled through, the field of every plane the stream
#: reads (cmy8's one, a cmy label's two toners), and the
#: neighbourhood's certificates.  The colour ROWS of every covering
#: window are gone: those are `tiles.scan`'s reads, and subscribing to
#: them was this row routing around its own predecessor's verdict.  The
#: chain head is re-armed by every generation bump (INV-G1) and its new
#: verdict is one of the keys below, so no wake is lost.
def _planek_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    page, ty, tx, stream_id, ppc = subject
    keys: list[FactKey] = [(KEY_PLANE_FIELD, page, plane) for plane
                           in stream_toners(store.row, stream_id)]
    for stage, lane in local_ctx.arming_lanes(store, page, ty, tx, ppc,
                                              local_ctx.READ_STAGES):
        keys.append((KEY_ATTEMPT, page, ty, tx, stream_id, stage, lane))
    for wid in local_ctx.covering_window_ids(store, page, ty, tx, ppc):
        keys.append((KEY_POSE_AFFINE, wid))
    for nty, ntx in local_ctx.neighbourhood_tiles(store, page, ty, tx, ppc):
        for stream in store.row.streams:
            keys.append((KEY_TILE, page, nty, ntx, stream.stream_id))
    return tuple(keys)


def _planek_eligible(store: object, subject: Subject) -> bool:
    page, ty, tx, stream_id, ppc = subject
    if not stream_toners(store.row, stream_id):
        return False
    if store.has_certificate((page, ty, tx, stream_id)):
        return False
    reach = local_ctx.neighbourhood_tiles(store, page, ty, tx, ppc)
    if not local_ctx.certified_neighbours(store, page, reach, (ty, tx)):
        return False
    return any(local_ctx.covering_color_rows(store, page, ty, tx, lane)
               for lane in store.cover_lanes(page, ty, tx, ppc))


def _planek_retire(store: object, subject: Subject) -> str | None:
    page, ty, tx, stream_id, _ppc = subject
    return (RETIRE_CERTIFIED
            if store.has_certificate((page, ty, tx, stream_id)) else None)


def _planek_stage(store: object, subject: Subject) -> str | None:
    return STAGE_PLANEK


def _planek_cost(store: object, subject: Subject, stage: str, attempts: int,
                 last_cost: int) -> int:
    """The escalation door, opened for the same reason `tiles.uplift`
    opened it: a growing certified frontier can wake this row again and
    again on the same tile, and one fire is the most expensive thing the
    receiver does.  Nothing is capped — the row may fire as often as new
    evidence justifies — it just drifts behind cheaper work each time.

    230 on the first fire, plus 230 for every earlier fire (2026-10-18:
    the one convention for every residue row, base + base x earlier
    fires; until then the first TWO fires both cost the base, so a row
    paid its base twice before escalating)."""
    base = PLANEK_COST + PLANEK_COST * attempts
    return base + RUNG_COST * store.union_rung_ordinal(subject[4])


PLANEK_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="tile",
    born_by=(AttemptFact,) + local_ctx.COVER_BIRTH_FACTS,
    subjects_of=_planek_subjects,
    reads=_planek_reads,
    eligible=_planek_eligible,
    stage=_planek_stage,
    cost=_planek_cost,
    retire=_planek_retire,
    prepare=prepare_planek,
    produces=(AttemptFact, Certificate),
    prices=PRICES,
)
