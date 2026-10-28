from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass

from . import data

KEY_POSE_AFFINE = "pose_affine"
KEY_POSE_ROUTE = "pose_route"
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
KEY_KINDS: tuple[str, ...] = (
    KEY_POSE_AFFINE, KEY_POSE_ROUTE, KEY_PLACE_STAGE, KEY_EVIDENCE_FIT,
    KEY_EVIDENCE_READ, KEY_COLOR_ROW, KEY_COLOR_POP, KEY_POOLED_CTX,
    KEY_REGION_PITCH, KEY_REGION_CTX,
    KEY_LATTICE_SEED, KEY_LANE_POSES, KEY_PAGE_CERTS, KEY_TILE,
    KEY_LIVE_PAGES, KEY_PLANE_FIELD)

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
    cost: Callable[[object, Subject, str, int, int], int]
    retire: Callable[[object, Subject], bool]
    prepare: Callable[[object, Subject, str], Job | None]
    produces: tuple[type, ...]
    prices: tuple[tuple[str, int], ...]


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
