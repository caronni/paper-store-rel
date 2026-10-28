"""The diag model and the fold: events in, one state value out.

The readout half — rows, status, selectors, report — is `readout.py`,
which imports this module and is not imported back.  That direction is
what lets `panes` import both at module level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from ..data import (AddressCoverage, CalibrateAdopted, CaptureOpen,
                    CloseCheck, EngineStat, FieldFitted, JobDone, PluginRow,
                    PoseCommitted, RunDone, RunOpen, SnapshotReplayed,
                    SurveyDone, TileOutcome, WindowRetired, WindowScheduled,
                    WindowSettled, WordOutcome)
from ..format import pilots

WindowKey = tuple[str, int, tuple[int, int, int, int]]

WORD_MASK_BYTES = (pilots.N_WORD_SITES + 7) // 8

#: The tile-state alphabet: the ranks stored in `DiagModel.tile_states`,
#: ordered so a later outcome only ever raises a tile.  The state owns
#: its own vocabulary; `panes` maps these ranks to chip colours.
TILE_UNKNOWN = 0
TILE_ADDRESSED = 1
TILE_FLOOR = 2
TILE_ATTEMPTED = 3
TILE_CERTIFIED = 4

#: the one `TileOutcome.result` the FIELD band's done split reacts to.
CERTIFIED_RESULT = "certified"

TILE_RANKS = {
    CERTIFIED_RESULT: TILE_CERTIFIED,
    "below_attempt_floor": TILE_FLOOR,
    "attempted_failed": TILE_ATTEMPTED,
}


@dataclass(frozen=True)
class WindowRec:
    stage: str
    cost: int
    cause: str | None = None


PANE_NAMES = ("capture", "page", "payload", "pose", "field")
#: Panes a committed pose moves.  Spelled out rather than PANE_NAMES so
#: adding a pane does not silently make every pose bump refetch it.
POSE_PANES = ("capture", "page", "payload", "pose")
#: Lane-page key of one `fields` fit: (capture, level_index, page).
FieldKey = tuple[str, int, int]


@dataclass
class DiagModel:
    cursor: int = 0
    run: RunOpen | None = None
    captures: dict[str, CaptureOpen] = field(default_factory=dict)
    ordinals: dict[int, str] = field(default_factory=dict)
    surveys: dict[str, SurveyDone] = field(default_factory=dict)
    windows: dict[WindowKey, WindowRec] = field(default_factory=dict)
    settle_causes: dict[str, dict[str, int]] = field(default_factory=dict)
    calibrations: dict[tuple[str, str], CalibrateAdopted] = field(
        default_factory=dict)
    poses: dict[int, list[PoseCommitted]] = field(default_factory=dict)
    region_placements: dict[tuple[str, int], int] = field(
        default_factory=dict)
    tile_states: dict[int, np.ndarray] = field(default_factory=dict)
    tile_evidence: dict[int, np.ndarray] = field(default_factory=dict)
    address_bits: dict[int, np.ndarray] = field(default_factory=dict)
    words_solved: dict[int, np.ndarray] = field(default_factory=dict)
    plugin_rows: dict[str, PluginRow] = field(default_factory=dict)
    plugin_subjects: dict[str, set] = field(default_factory=dict)
    plugin_price_sum: dict[str, int] = field(default_factory=dict)
    field_fits: dict[FieldKey, FieldFitted] = field(default_factory=dict)
    #: page -> the lane-page whose fit landed most recently on it, so
    #: the FIELD pane draws one lane's field and names which.
    field_latest: dict[int, FieldKey] = field(default_factory=dict)
    last_field: FieldFitted | None = None
    engine_stat: EngineStat | None = None
    last_job: JobDone | None = None
    duplicates: int = 0
    pane_revs: dict[str, int] = field(default_factory=dict)
    last_close: CloseCheck | None = None
    run_done: RunDone | None = None
    replayed: SnapshotReplayed | None = None
    fold_errors: int = 0


def empty() -> DiagModel:
    return DiagModel()


def wkey(capture: str, region_index: int,
          extent: Sequence[int]) -> WindowKey:
    cy0, cx0, cy1, cx1 = (int(v) for v in extent)
    return (capture, int(region_index), (cy0, cx0, cy1, cx1))


def _tile_state_array(working: DiagModel, page: int) -> np.ndarray:
    arr = working.tile_states.get(page)
    if arr is None:
        run = working.run
        ty_total, tx_total = run.tiles_yx
        n_streams = max(1, len(run.stream_ids))
        arr = np.zeros((n_streams, ty_total, tx_total), np.int8)
        working.tile_states[page] = arr
    return arr


def _apply_pose(working: DiagModel, event: PoseCommitted) -> None:
    if not event.accepted:
        return
    working.windows.pop(
        wkey(event.capture, event.region_index, event.extent_cells), None)
    region_key = (event.capture, int(event.region_index))
    working.region_placements[region_key] = (
        working.region_placements.get(region_key, 0) + 1)
    working.poses.setdefault(int(event.page), []).append(event)
    run = working.run
    if run is None:
        return
    ty_total, tx_total = run.tiles_yx
    h, w = (int(v) for v in event.shape_yx)
    if event.rot_k % 2:
        h, w = w, h
    if h <= 0 or w <= 0:
        return
    oy, ox = (int(v) for v in event.page_origin_yx)
    ty0 = max(0, oy // pilots.TILE_CELLS)
    tx0 = max(0, ox // pilots.TILE_CELLS)
    ty1 = min(ty_total - 1, (oy + h - 1) // pilots.TILE_CELLS)
    tx1 = min(tx_total - 1, (ox + w - 1) // pilots.TILE_CELLS)
    if ty1 < ty0 or tx1 < tx0:
        return
    arr = _tile_state_array(working, int(event.page))
    region = arr[:, ty0:ty1 + 1, tx0:tx1 + 1]
    np.maximum(region, np.int8(TILE_ADDRESSED), out=region)


def _apply_tile_outcome(working: DiagModel, event: TileOutcome) -> None:
    run = working.run
    if run is None:
        return
    ty_total, tx_total = run.tiles_yx
    if not (0 <= event.ty < ty_total and 0 <= event.tx < tx_total):
        return
    stream_index = run.stream_ids.index(event.stream_id)
    arr = _tile_state_array(working, int(event.page))
    rank = TILE_RANKS.get(event.result)
    if rank is not None and rank > arr[stream_index, event.ty, event.tx]:
        arr[stream_index, event.ty, event.tx] = rank
    evidence = working.tile_evidence.get(int(event.page))
    if evidence is None:
        evidence = np.zeros((ty_total, tx_total), np.int32)
        working.tile_evidence[int(event.page)] = evidence
    evidence[event.ty, event.tx] += 1


def _apply_coverage(working: DiagModel, event: AddressCoverage) -> None:
    run = working.run
    if run is None:
        return
    ty_total, tx_total = run.tiles_yx
    arr = working.address_bits.get(int(event.page))
    if arr is None:
        arr = np.zeros((ty_total, tx_total, WORD_MASK_BYTES), np.uint8)
        working.address_bits[int(event.page)] = arr
    for ty, tx, packed in event.tiles:
        if not (0 <= ty < ty_total and 0 <= tx < tx_total):
            continue
        buf = np.frombuffer(packed, np.uint8)
        n = min(buf.size, WORD_MASK_BYTES)
        np.bitwise_or(arr[ty, tx, :n], buf[:n], out=arr[ty, tx, :n])


def _apply_word(working: DiagModel, event: WordOutcome) -> None:
    run = working.run
    if run is None:
        return
    ty_total, tx_total = run.tiles_yx
    if not (0 <= event.ty < ty_total and 0 <= event.tx < tx_total):
        return
    arr = working.words_solved.get(int(event.page))
    if arr is None:
        arr = np.zeros((ty_total, tx_total), bool)
        working.words_solved[int(event.page)] = arr
    arr[event.ty, event.tx] = True


def _apply_job_done(working: DiagModel, event: JobDone) -> None:
    row = working.plugin_rows.get(event.plugin, PluginRow(event.plugin))
    working.plugin_rows[event.plugin] = PluginRow(
        event.plugin, row.jobs + 1,
        row.cpu_seconds + float(event.cpu_s),
        row.certificates + int(event.n_certificates),
        row.poses + int(event.n_poses),
        row.words + int(event.n_words))
    working.plugin_subjects.setdefault(event.plugin, set()).add(event.subject)
    working.plugin_price_sum[event.plugin] = (
        working.plugin_price_sum.get(event.plugin, 0) + int(event.cost))
    working.last_job = event


def _apply_settled(working: DiagModel, event: WindowSettled) -> None:
    """Every settle is a refusal that leaves the window live.

    Suppression is not a settle: done-geometry retires at the scheduler
    door and arrives as a `WindowRetired` carrying `cause`, which the
    `WindowRetired` arm below removes without a cause tally.
    """
    key = wkey(event.capture, event.region_index, event.extent_cells)
    rec = working.windows.get(key, WindowRec("", 0))
    working.windows[key] = WindowRec(rec.stage, rec.cost, event.state)
    causes = working.settle_causes.setdefault(event.capture, {})
    causes[event.state] = causes.get(event.state, 0) + 1


def _apply(working: DiagModel, event: object) -> None:
    if isinstance(event, RunOpen):
        working.run = event
    elif isinstance(event, CaptureOpen):
        working.captures.setdefault(event.capture, event)
        if event.duplicate:
            working.duplicates += 1
        else:
            working.ordinals.setdefault(int(event.ordinal), event.capture)
    elif isinstance(event, SurveyDone):
        working.surveys[event.capture] = event
    elif isinstance(event, WindowScheduled):
        key = wkey(event.capture, event.region_index, event.extent_cells)
        rec = working.windows.get(key, WindowRec("", 0))
        working.windows[key] = WindowRec(event.stage, int(event.cost),
                                         rec.cause)
    elif isinstance(event, WindowRetired):
        working.windows.pop(
            wkey(event.capture, event.region_index, event.extent_cells),
            None)
    elif isinstance(event, WindowSettled):
        _apply_settled(working, event)
    elif isinstance(event, JobDone):
        _apply_job_done(working, event)
    elif isinstance(event, PoseCommitted):
        _apply_pose(working, event)
    elif isinstance(event, WordOutcome):
        _apply_word(working, event)
    elif isinstance(event, AddressCoverage):
        _apply_coverage(working, event)
    elif isinstance(event, CalibrateAdopted):
        working.calibrations[(event.capture, event.pool_id)] = event
    elif isinstance(event, TileOutcome):
        _apply_tile_outcome(working, event)
    elif isinstance(event, EngineStat):
        working.engine_stat = event
    elif isinstance(event, CloseCheck):
        working.last_close = event
    elif isinstance(event, RunDone):
        working.run_done = event
    elif isinstance(event, FieldFitted):
        # Latest fit wins per lane-page: a re-fit supersedes its own
        # predecessor, it does not accumulate beside it.
        key = (event.capture, int(event.level_index), int(event.page))
        working.field_fits[key] = event
        working.field_latest[int(event.page)] = key
        working.last_field = event
    elif isinstance(event, SnapshotReplayed):
        working.replayed = event
    for pane in _EVENT_PANES.get(type(event), ()):
        if pane == "field" and not _field_pane_moved(event):
            continue
        working.pane_revs[pane] = working.pane_revs.get(pane, 0) + 1


def _field_pane_moved(event: object) -> bool:
    """Does this event change what the FIELD band draws?

    Only a CERTIFIED tile can: the band reads tile states for its
    blind-spot/done split alone, and a failed or below-floor outcome
    leaves that split exactly where it was.  Every other event mapped to
    the band moves it by construction.
    """
    if isinstance(event, TileOutcome):
        return event.result == CERTIFIED_RESULT
    return True


_EVENT_PANES: dict[type, tuple[str, ...]] = {
    RunOpen: PANE_NAMES,
    CaptureOpen: ("capture",),
    SnapshotReplayed: ("capture", "payload"),
    SurveyDone: ("capture",),
    WindowScheduled: ("capture",),
    WindowRetired: ("capture",),
    WindowSettled: ("capture",),
    CalibrateAdopted: ("capture",),
    PoseCommitted: POSE_PANES,
    # a CERTIFIED tile changes the field band's blind-spot/done split;
    # the other outcomes reach the band's map not at all (_field_pane_moved)
    TileOutcome: ("capture", "payload", "field"),
    FieldFitted: ("field",),
    AddressCoverage: ("page",),
    WordOutcome: ("page",),
}


def fold(model: DiagModel, events: Sequence[object]) -> DiagModel:
    n = len(events)
    if n <= model.cursor:
        return model
    working = DiagModel(
        cursor=model.cursor,
        run=model.run,
        captures=dict(model.captures),
        ordinals=dict(model.ordinals),
        surveys=dict(model.surveys),
        windows=dict(model.windows),
        settle_causes={capture: dict(causes)
                       for capture, causes in model.settle_causes.items()},
        calibrations=dict(model.calibrations),
        poses={page: list(rows) for page, rows in model.poses.items()},
        region_placements=dict(model.region_placements),
        tile_states={page: arr.copy()
                     for page, arr in model.tile_states.items()},
        tile_evidence={page: arr.copy()
                       for page, arr in model.tile_evidence.items()},
        address_bits={page: arr.copy()
                      for page, arr in model.address_bits.items()},
        words_solved={page: arr.copy()
                      for page, arr in model.words_solved.items()},
        plugin_rows=dict(model.plugin_rows),
        plugin_subjects={plugin: set(subjects) for plugin, subjects
                         in model.plugin_subjects.items()},
        plugin_price_sum=dict(model.plugin_price_sum),
        field_fits=dict(model.field_fits),
        field_latest=dict(model.field_latest),
        last_field=model.last_field,
        engine_stat=model.engine_stat,
        last_job=model.last_job,
        duplicates=model.duplicates,
        pane_revs=dict(model.pane_revs),
        last_close=model.last_close,
        run_done=model.run_done,
        replayed=model.replayed,
        fold_errors=model.fold_errors,
    )
    for event in events[model.cursor:n]:
        try:
            _apply(working, event)
        except Exception:
            working.fold_errors += 1
    working.cursor = n
    return working
