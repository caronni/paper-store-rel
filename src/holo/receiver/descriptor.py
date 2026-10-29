from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass

from . import data

KEY_POSE_AFFINE = "pose_affine"
KEY_POSE_ROUTE = "pose_route"
#: One window's place LADDER moving -- a rung spent, the tried set
#: grown, a subdivision, a parent re-armed by its last child.  Read by
#: that window and by nobody else: `place_settled`, the narrow key a
#: parent held on each of its CHILDREN, retired 2026-09-21 when the
#: store started routing a child's settle to the parent's own key
#: instead (a derived relation is the store's, and a worker's reads
#: are fixed at birth).
KEY_PLACE_STAGE = "place_stage"
KEY_EVIDENCE_FIT = "evidence_fit"
KEY_EVIDENCE_READ = "evidence_read"
KEY_COLOR_ROW = "color_row"
KEY_COLOR_POP = "color_pop"
KEY_POOLED_CTX = "pooled_ctx"
KEY_REGION_PITCH = "region_pitch"
KEY_REGION_CTX = "region_ctx"
KEY_LATTICE_SEED = "lattice_seed"
KEY_LANE_POSES = "lane_poses"
KEY_PAGE_CERTS = "page_certs"
KEY_TILE = "tile"
KEY_LIVE_PAGES = "live_pages"
KEY_PLANE_FIELD = "plane_field"
KEY_FIELD_OBS = "field_obs"
#: One tile-stream's VERDICT at one stage on one lane -- the narrow
#: key the residue ladder is built on.  `(page, ty, tx, stream_id,
#: stage, lane)`, where the lane is `(capture_id, level_index)` for a
#: single-lane attempt and the shared footing's ppc for a summed one
#: (`tiles.attempt_lane`).  A rung subscribes to the verdicts of the
#: stages that arm it and to nothing else, so "the ladder exists only
#: at birth" stops being true.
KEY_ATTEMPT = "attempt"
#: One UNPLACED window's done verdict going back from done to open --
#: `(KEY_WINDOW_DONE, wid)`.  The pose-free projection that judges an
#: unplaced window done runs through the LATEST adopted pose of every
#: placed window in its region, so a pose revision can shrink it; the
#: store remembers which windows it last judged done and emits this key
#: for the ones a changed affine reopened (2026-10-03).  The other
#: direction needs no key: a window found done at its next wake simply
#: has no stage.
KEY_WINDOW_DONE = "window_done"
KEY_KINDS: tuple[str, ...] = (
    KEY_POSE_AFFINE, KEY_POSE_ROUTE, KEY_PLACE_STAGE,
    KEY_EVIDENCE_FIT,
    KEY_EVIDENCE_READ, KEY_COLOR_ROW, KEY_COLOR_POP, KEY_POOLED_CTX,
    KEY_REGION_PITCH, KEY_REGION_CTX,
    KEY_LATTICE_SEED, KEY_LANE_POSES, KEY_PAGE_CERTS, KEY_TILE,
    KEY_LIVE_PAGES, KEY_PLANE_FIELD, KEY_FIELD_OBS,
    KEY_ATTEMPT, KEY_WINDOW_DONE)

#: Facts whose fold legitimately wakes NOBODY.  A fact type that is not
#: here and emits no key is a lost re-arm, and `test_h3_lifecycle`
#: fails the build for it: that is what `AttemptFact` was until
#: 2026-09-21, which is why the residue ladder existed only at birth.
#: Each entry carries the reason it is terminal, and the reason is
#: always the same shape -- the work the fact creates is BORN by it,
#: rather than waking a row that was already standing.
TERMINAL_FACTS: tuple[tuple[str, str], ...] = (
    ("Capture", "declares a capture; births `survey` by type"),
    ("CaptureSurvey", "mints the frames and the window plan; births "
                      "`place` through the Window facts it ingests"),
    ("Window", "births the `place` row; no standing row reads a window"),
    ("ColorLaneFit", "the colour row's own output -- the debt it clears "
                     "and the head it publishes belong to the job that "
                     "emitted it, and that job is `color` itself"),
    ("EvidenceRevision", "resume-only ordinal restore; the rows that "
                         "read it are born by the placements folded "
                         "beside it"),
)

#: Retire CAUSES.  The string is the ROW's vocabulary, not the
#: engine's -- the engine tallies it and stamps it on `WorkerRetired`
#: and never branches on it.  Spelled here are only the causes more
#: than one row shares, so a run's tallies line up across rows; a
#: cause of one row's own lives in that row's module.
RETIRE_CERTIFIED = "certified"
RETIRE_PAGE_DONE = "page_done"
RETIRE_REACH_EXHAUSTED = "reach_exhausted"

Subject = Hashable
FactKey = tuple
Job = Callable[[], data.JobResult]


@dataclass(frozen=True)
class PluginDescriptor:
    name: str
    subject_kind: str
    born_by: tuple[type, ...]
    subjects_of: Callable[[object, object], tuple[Subject, ...]]
    reads: Callable[[object, Subject], tuple[FactKey, ...]]
    eligible: Callable[[object, Subject], bool]
    stage: Callable[[object, Subject], str | None]
    #: The engine hands the last two -- this bookmark's fire ordinal and
    #: the price it was last pushed at -- in as DATA and interprets
    #: neither.  Engine-side rework aging was deleted 2026-08-29 ("cost is
    #: a scheduling function, nothing the engine determines"); rows escalate.
    cost: Callable[[object, Subject, str, int, int], int]
    #: The CAUSE this row stopped for good, or None while it lives.
    #: The engine tallies the string and stamps it on the retirement
    #: event; it never branches on its value.
    retire: Callable[[object, Subject], str | None]
    prepare: Callable[[object, Subject, str], Job | None]
    produces: tuple[type, ...]
    prices: tuple[tuple[str, int], ...]


#: A scheduling BOOKMARK: subject, subscribed keys, and the engine's
#: own accounting (versions, seat, fire ordinal).  No domain state on a
#: worker, ever -- every fire is pure over the store, which is what
#: keeps a wake one bit wide.
@dataclass
class WorkerBookmark:
    plugin: str
    subject: Subject
    reads: tuple[FactKey, ...]
    version: int = 0
    tried_version: int = -1
    attempts: int = 0
    last_cost: int = 0
    retired: bool = False
    inflight: bool = False
    pending: bool = False
    seat_seq: int = -1
    seat_cost: int = 0
