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
                    CloseCheck, Contradiction, EngineStat, FieldSolved,
                    JobDone, PluginRow, PoseCommitted, RunDone, RunOpen,
                    SnapshotReplayed, SurveyDone, SurveyPitchFallback,
                    TileOutcome, WindowSettled, WordOutcome,
                    WorkerRetired, WorkerSeated)
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

#: the one row whose seats and retirements the CAPTURE pane draws.
#: The seat and retire events are generic; the window view is not.
PLACE_PLUGIN = "place"

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


@dataclass
class DiagModel:
    cursor: int = 0
    run: RunOpen | None = None
    captures: dict[str, CaptureOpen] = field(default_factory=dict)
    ordinals: dict[int, str] = field(default_factory=dict)
    surveys: dict[str, SurveyDone] = field(default_factory=dict)
    pitch_fallbacks: dict[str, SurveyPitchFallback] = field(
        default_factory=dict)
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
    contradictions: int = 0
    #: page -> the tiles either side of a contradiction named, so the
    #: PAGE pane can paint the reserved deep red (DIAG-DESIGN §1, §8).
    contradicted_tiles: dict[int, set[tuple[int, int]]] = field(
        default_factory=dict)
    last_contradiction: Contradiction | None = None
    plugin_rows: dict[str, PluginRow] = field(default_factory=dict)
    plugin_subjects: dict[str, set] = field(default_factory=dict)
    plugin_price_sum: dict[str, int] = field(default_factory=dict)
    #: page -> its latest solve.  One field per page is the whole
    #: point (I1): a re-solve supersedes its own predecessor, it does
    #: not accumulate beside it.
    field_solves: dict[int, FieldSolved] = field(default_factory=dict)
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


def _apply_contradiction(working: DiagModel, event: Contradiction) -> None:
    working.contradictions += 1
    working.last_contradiction = event
    for page, tile in ((event.page, event.tile_yx),
                       (event.standing_page, event.standing_tile_yx)):
        working.contradicted_tiles.setdefault(int(page), set()).add(
            (int(tile[0]), int(tile[1])))


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
    door and arrives as a `WorkerRetired` carrying `cause`, which the
    `WorkerRetired` arm below removes without a cause tally.
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
    elif isinstance(event, SurveyPitchFallback):
        working.pitch_fallbacks[event.capture] = event
    elif isinstance(event, WorkerSeated):
        if event.plugin == PLACE_PLUGIN:
            wid = event.subject
            key = wkey(wid[0], wid[2], wid[3])
            rec = working.windows.get(key, WindowRec("", 0))
            working.windows[key] = WindowRec(event.stage, int(event.cost),
                                             rec.cause)
    elif isinstance(event, WorkerRetired):
        if event.plugin == PLACE_PLUGIN:
            wid = event.subject
            working.windows.pop(wkey(wid[0], wid[2], wid[3]), None)
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
    elif isinstance(event, Contradiction):
        _apply_contradiction(working, event)
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
    elif isinstance(event, FieldSolved):
        working.field_solves[int(event.page)] = event
    elif isinstance(event, SnapshotReplayed):
        working.replayed = event
    for pane in _EVENT_PANES.get(type(event), ()):
        if not _pane_moved(pane, event):
            continue
        working.pane_revs[pane] = working.pane_revs.get(pane, 0) + 1


def _pane_moved(pane: str, event: object) -> bool:
    """Does this event change what `pane` draws?

    Two rows.  The FIELD band reads tile states for its blind-spot/done
    split alone, so only a CERTIFIED tile moves it; a failed or
    below-floor outcome leaves the split exactly where it was.  The
    CAPTURE pane draws WINDOWS, so only the place row's seats and
    retirements move it — the seventeen other rows are seated and
    retired through the same two generic events and would otherwise bump
    it tens of thousands of times for a pane that never changed.
    Everything else mapped to a pane moves it by construction.
    """
    if pane == "field" and isinstance(event, TileOutcome):
        return event.result == CERTIFIED_RESULT
    if isinstance(event, (WorkerSeated, WorkerRetired)):
        return event.plugin == PLACE_PLUGIN
    return True


_EVENT_PANES: dict[type, tuple[str, ...]] = {
    RunOpen: PANE_NAMES,
    CaptureOpen: ("capture",),
    SnapshotReplayed: ("capture", "payload"),
    SurveyDone: ("capture",),
    SurveyPitchFallback: ("capture",),
    WorkerSeated: ("capture",),
    WorkerRetired: ("capture",),
    WindowSettled: ("capture",),
    CalibrateAdopted: ("capture",),
    PoseCommitted: POSE_PANES,
    # a CERTIFIED tile changes the field band's blind-spot/done split;
    # the other outcomes reach the band's map not at all (_field_pane_moved)
    TileOutcome: ("capture", "payload", "field"),
    FieldSolved: ("field",),
    AddressCoverage: ("page",),
    WordOutcome: ("page",),
    Contradiction: ("page",),
}


# The fold never mutates its input: the frame a caller already holds
# stays coherent while the next one is built (DIAG-DESIGN §0).
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
        pitch_fallbacks=dict(model.pitch_fallbacks),
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
        contradictions=model.contradictions,
        contradicted_tiles={page: set(tiles) for page, tiles
                            in model.contradicted_tiles.items()},
        last_contradiction=model.last_contradiction,
        plugin_rows=dict(model.plugin_rows),
        plugin_subjects={plugin: set(subjects) for plugin, subjects
                         in model.plugin_subjects.items()},
        plugin_price_sum=dict(model.plugin_price_sum),
        field_solves=dict(model.field_solves),
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
