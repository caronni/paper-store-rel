#!/usr/bin/env python
"""The v1/holo2 certificate-set differential — BY PATH (RULINGS I6, W1).

    env/bin/python holo2/measure/tile_differential.py \\
        --v1-state PATH --h2-state DIR --format L:c2-r0700@3392x2368 \\
        --label e029 --out scratch/holo2-catchup/real/differential-e029.md

NOT A TEST and not collectable as one — same standing as
``v1_side_by_side.py`` and the other census drivers in this directory
(``holo2/measure/README.md``): it holds no `__main__`-free assertions, it
opens a v1 state and a holo2 state and it prints/writes what it finds.
Its ONE pinned behaviour (the fixture pair that differs by a known tile)
lives in ``tests/holo2_oracles/test_oracle_tile_differential.py`` — not
``holo2/tests/``, because it builds a v1 ``SessionState`` fixture and
``holo2/tests/test_firewall.py`` forbids importing ``holo`` anywhere
under ``holo2/tests``; ``tests/holo2_oracles/`` is one of the two
directories the firewall exempts — a genuine pytest test, because the
classification logic below IS testable in isolation from a real decode.

READ-ONLY IN EFFECT, not lock-free: v1's ``load_session`` only ever reads
a file; holo2's side opens the store directly with :meth:`Store.open`
(never ``cli.open_receiver`` — that composes a live session with
providers, a recipe and a work source, none of which this instrument
needs or may construct on somebody else's behalf) and never calls
anything that proposes a commit — no journal line, no cache byte
changes (verified sha256-stable across a run on both real states). But
``Store.open`` still takes the state directory's exclusive lock and
truncates a torn cache tail on open, so do not run this against a state
a decode currently has open. RULINGS I6/§F: "never commit."

WHAT THIS ANSWERS, and the shape of the answer (RULINGS I6): "the tile
differential (W1) attributes every tile v1 has and holo2 lacks (and the
reverse) BEFORE any lever is pulled." For every tile in the symmetric
difference of the two certificate sets it reports:

* **v1's side** — every lane whose committed pose's window footprint
  covers the tile (ordinary rung / mop-up / refinement, via
  ``holo.receive.cascade.lane_kind``) — coverage, NOT an attribution of
  which lane actually minted the certificate (limitation 1: that
  attempt-level fact is not durable), that lane's
  footing (target ppc), the covering pose's window/page/pose id, plus —
  for a tile v1 does NOT certify — any evidence blocks v1 still retains
  there (LLR magnitude summary, since blocks are pruned once a tile
  certifies, so a retained block IS "v1 tried and has not yet closed
  it").
* **holo2's side** — the tile's rank (``solve.tilemap.tile_state``:
  NEVER-ADDRESSED / ADDRESSED-NOT-ATTEMPTED / ATTEMPTED-FAILED /
  CERTIFIED), every payload spend recorded against its work key (route,
  footing/tag, outcome, attempts, exposures — the durable ``SpendRecord``
  ledger, which unlike v1's folds to counters never prunes a row), and
  every covering pose/window this instrument can reach via the evidence
  index.

TWO KNOWN LIMITATIONS, recorded rather than routed around (both
traceable to facts this wave's PARITY-MATRIX/RULINGS already established
— this instrument adds no new claim, it just has to live with them):

1. **v1's per-attempt STAGE is not durable for a certified tile.**
   ``session.py``'s own docstring: "Attempt and divergence ledgers are
   not persisted — they fold into counters." ``TileCertificateRecord.
   origin_attempt_id`` is a content hash of the attempt's (address,
   stage, decoder, block ids); none of those components survive as a
   separate durable field, so this instrument cannot say "SCAN" vs
   "RETRY150" for a v1-certified tile — only which LANE covers it (the
   window/pose that produced the evidence), which is the finest
   provenance a completed v1 state actually retains.
2. **holo2's window scheduling state (dormant / subdivided) is durable
   NOWHERE.** PARITY-MATRIX adjudication (a): a ladder-exhausted window
   "simply goes dormant (``place_sched._Slot.ready = False``), which
   already IS the deferred state, durable nowhere"; subdivision
   (``place_subdivide.subdivide``) "SPENDS NOTHING: no pass, no budget,
   no durable write." So for a NEVER-ADDRESSED tile this instrument can
   say only that no committed pose's evidence ever reached it — not
   whether some window's plan geometrically covers it and is dormant,
   was subdivided, or was never scheduled at all. Page-edge/straddle
   membership IS knowable (page geometry is durable format truth) and is
   reported; window dormancy is not.

Both limitations are read straight off the record shapes cited above,
not assumed — see the docstrings of ``holo.receive.session`` and
``holo2.solve.place_subdivide``/``place_sched`` for the primary sources.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

# Self-locating, like every other by-path driver in this directory
# (``v1_side_by_side.py``, ``index_equivalence.py``): neither package is
# pip-installed, so a driver the operator runs BY PATH should not also
# demand a ``PYTHONPATH=`` prefix to find the tree it lives in.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_ROOT / "src", _ROOT / "holo2" / "src"):
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)

from holo.format.resolve import resolve_format_ref               # noqa: E402
from holo.receive.cascade import lane_kind                       # noqa: E402
from holo.receive.evidence_blocks import EvidenceBlock            # noqa: E402
from holo.receive.session import load_session                    # noqa: E402
from holo.receive.session_model import SessionState               # noqa: E402
from holo.receive.types import LaneSpec                          # noqa: E402

from holo2.cli import record_registry                             # noqa: E402
from holo2.core import ResourceKey, SpendRecord, Store            # noqa: E402
from holo2.solve import (StoreIndex, TileState, parse_tile_key,   # noqa: E402
                         parse_window_key, tile_key, tile_state)
from holo2.solve.payload import FAMILY_PAYLOAD                    # noqa: E402

#: One v1 tile is 64x64 cells (the format constant ``diag/seed.py`` and
#: ``_diagnostic_snapshots.payload`` already assume for the same
#: reason — colocated v1/v2 tiles are 64 cells on a side everywhere).
_TILE_CELLS = 64

TileKey = tuple[int, int, int]     # (page, ty, tx)


# --------------------------------------------------------------------
# v1 side
# --------------------------------------------------------------------


@dataclass(frozen=True)
class V1PoseFacts:
    """What one committed v1 pose says about a tile it covers."""

    pose_id: str
    lane_id: str
    lane_kind: str                  # ordinary / mopup / refine / uplift:<arm>
    footing_ppc: str                # "num/den", the LANE's target ppc
    page: int
    window_id: int
    placement_outcome: str
    rot90: int


@dataclass(frozen=True)
class V1BlockFacts:
    """A retained (hence uncertified-as-of-close) v1 evidence block."""

    lane_id: str
    n_observed: int
    min_abs_llr: float
    mean_abs_llr: float


@dataclass
class V1Index:
    state: SessionState
    certified: dict[TileKey, str]                       # -> certificate_id
    coverage: dict[TileKey, list[V1PoseFacts]]
    blocks: dict[TileKey, list[V1BlockFacts]]
    non_accepted_pose_count: int                        # dropped from coverage


def _lane_lookup(state: SessionState) -> dict[tuple[str, str], LaneSpec]:
    """``(capture_sha256, lane_id) -> LaneSpec``, over every declared plan."""
    out: dict[tuple[str, str], LaneSpec] = {}
    for capture in state.captures:
        for lane in capture.plan:
            out[(capture.source_sha256, lane.lane_id)] = lane
    return out


def _v1_pose_coverage(state: SessionState, tiles_yx: tuple[int, int],
                      ) -> dict[TileKey, list[V1PoseFacts]]:
    """Which committed poses cover which tiles (``diag/seed.py``'s own
    reconstruction: page-cell origin + rot90-oriented window shape —
    the one durable statement a completed v1 state makes about "this
    tile had an assigned address").

    Deliberately narrower than ``diag/seed.py``'s own reconstruction:
    this filters to ``placement_outcome == "accepted"``, while
    ``seed_words`` iterates every pose with no outcome filter. A
    ``redundant`` pose (a second placement over ground an earlier one
    already covers) still names a lane that reached the tile, so a
    v1-only tile fed by ONLY redundant poses is under-reported here as
    "no committed v1 pose covers this tile" rather than showing the
    redundant lane(s). Measured: e029's v1 state has zero redundant
    poses (unaffected); xerox's has 35, and 5 of its 48 v1-only tiles —
    (0,0),(1,0),(2,0),(3,0),(2,4) — carry redundant-only coverage on
    lanes l00/l02/l03/r02 that this function drops silently before this
    note. Kept narrow deliberately (a redundant pose was superseded, so
    treating it as equal coverage would overstate v1's attempt); the
    report should say when it is dropping something instead of looking
    empty.
    """
    tiles_y, tiles_x = tiles_yx
    lanes = _lane_lookup(state)
    coverage: dict[TileKey, list[V1PoseFacts]] = defaultdict(list)
    for pose in state.poses:
        if pose.placement_outcome != "accepted":
            continue
        height, width = pose.window_shape_yx_cells
        if pose.rot90 % 2:
            height, width = width, height
        y0, x0 = pose.cell_origin_yx
        ty0 = max(0, y0 // _TILE_CELLS)
        tx0 = max(0, x0 // _TILE_CELLS)
        ty1 = min(tiles_y, -((y0 + height) // -_TILE_CELLS))
        tx1 = min(tiles_x, -((x0 + width) // -_TILE_CELLS))
        lane = lanes.get((pose.capture_id, pose.lane_id))
        facts = V1PoseFacts(
            pose_id=pose.pose_id,
            lane_id=pose.lane_id,
            lane_kind=lane_kind(lane) if lane is not None else "unknown",
            footing_ppc=(f"{lane.target_ppc_num}/{lane.target_ppc_den}"
                        if lane is not None else "?"),
            page=pose.page, window_id=pose.window_id,
            placement_outcome=pose.placement_outcome, rot90=pose.rot90)
        for ty in range(ty0, ty1):
            for tx in range(tx0, tx1):
                coverage[(pose.page, ty, tx)].append(facts)
    return coverage


def _v1_block_summary(state: SessionState,
                      ) -> dict[TileKey, list[V1BlockFacts]]:
    """Retained (uncertified) evidence blocks, summarised per tile.

    ``EvidenceBlock.printed_llr_f32`` is the sparse observed-cell LLR
    vector (``evidence.py``'s own docstring: "persisted only while their
    tile lacks a full certificate set"); a min/mean absolute magnitude is
    read straight off it with no origin-table or bitmap-position
    decoding, which is all a MARGIN summary needs.
    """
    out: dict[TileKey, list[V1BlockFacts]] = defaultdict(list)
    for block in state.blocks:
        if not isinstance(block, EvidenceBlock):
            continue
        llr = np.frombuffer(block.printed_llr_f32, dtype="<f4")
        if llr.size == 0:
            continue
        out[block.address].append(V1BlockFacts(
            lane_id=block.lane_id, n_observed=block.n_observed,
            min_abs_llr=float(np.min(np.abs(llr))),
            mean_abs_llr=float(np.mean(np.abs(llr)))))
    return out


def build_v1_index(state: SessionState, tiles_yx: tuple[int, int],
                   stream: str = "main") -> V1Index:
    certified: dict[TileKey, str] = {}
    for cert in state.certificates:
        if cert.stream_id != stream:
            continue
        certified[(cert.page, *cert.tile_yx)] = cert.certificate_id
    non_accepted = sum(1 for pose in state.poses
                      if pose.placement_outcome != "accepted")
    return V1Index(state=state, certified=certified,
                   coverage=_v1_pose_coverage(state, tiles_yx),
                   blocks=_v1_block_summary(state),
                   non_accepted_pose_count=non_accepted)


# --------------------------------------------------------------------
# holo2 side
# --------------------------------------------------------------------


@dataclass(frozen=True)
class H2SpendFacts:
    route: str
    footing_or_tag: str
    outcome: str
    attempts: int
    exposures: int


@dataclass(frozen=True)
class H2PoseFacts:
    footing_id: str
    page: int
    window_id: str
    window_extent_cells: tuple[int, int, int, int] | None
    window_status: str | None
    window_retired_reason: str | None
    pose_quarantined: bool
    evidence_quarantined: bool


@dataclass
class H2Index:
    store_index: StoreIndex
    spends_by_tile: dict[ResourceKey, list[SpendRecord]]


@contextmanager
def open_h2_store(state_dir: Path) -> Iterator[Store]:
    """The holo2 side, opened READ-ONLY: ``Store.open`` directly.

    Deliberately NOT ``cli.open_receiver`` — that composes a live
    session over a recipe, a work source and a provider tuple, none of
    which a read-only differential has any business constructing (it
    would also require knowing the exact provider/recipe binding the run
    used, which this instrument has no need to reconstruct). ``Store.
    open`` needs only the composed record registry (``cli.
    record_registry`` — the SAME composition root production uses, so a
    schema drift refuses loudly rather than silently). ``page_domain=()``
    disables the (write-time-only) page-gate validator; nothing here
    writes, so there is nothing for it to gate.
    """
    registry = record_registry(page_domain=())
    with Store.open(state_dir, registry, fsync=False) as store:
        yield store


def build_h2_index(store: Store) -> H2Index:
    index = StoreIndex.build(store)
    spends_by_tile: dict[ResourceKey, list[SpendRecord]] = defaultdict(list)
    for spend in store.ledger.entries():
        if spend.worker_id.family == FAMILY_PAYLOAD:
            spends_by_tile[spend.worker_id.subject].append(spend)
    return H2Index(store_index=index, spends_by_tile=dict(spends_by_tile))


def h2_certified_tiles(index: StoreIndex, stream: str) -> dict[TileKey, str]:
    out: dict[TileKey, str] = {}
    for key in index.certified_tiles:
        page, ty, tx, st = parse_tile_key(key)
        if st == stream:
            out[(page, ty, tx)] = key.__str__()
    return out


def h2_tile_facts(store: Store, h2: H2Index, page: int, ty: int, tx: int,
                  stream: str,
                  ) -> tuple[TileState, tuple[H2SpendFacts, ...],
                            tuple[H2PoseFacts, ...]]:
    """One work key's rank, its spend rows, and its covering poses."""
    key = tile_key(page, ty, tx, stream)
    record = h2.store_index.tiles.get(key)
    spends = h2.spends_by_tile.get(key, ())
    attempted = any(spend.exposures for spend in spends)
    state = tile_state(record, attempted=attempted)
    spend_facts = tuple(
        H2SpendFacts(route=spend.route,
                    footing_or_tag=spend.worker_id.scope.profile or "",
                    outcome=spend.outcome, attempts=spend.attempts,
                    exposures=spend.exposures)
        for spend in sorted(spends, key=lambda s: (s.route,
                                                    s.worker_id.scope.profile
                                                    or "")))
    pose_facts: list[H2PoseFacts] = []
    for evidence_key in h2.store_index.evidence_by_tile.get(key, ()):
        evidence = store.get(evidence_key)
        if evidence is None:
            continue
        pose = h2.store_index.poses.get(evidence.pose_id)
        window = (h2.store_index.windows.get(pose.window_id)
                  if pose is not None else None)
        extent = (parse_window_key(pose.window_id)[2]
                  if pose is not None else None)
        pose_facts.append(H2PoseFacts(
            footing_id=evidence.footing_id,
            page=pose.page if pose is not None else page,
            window_id=str(pose.window_id) if pose is not None else "?",
            window_extent_cells=extent,
            window_status=(window.status.value
                           if window is not None else None),
            window_retired_reason=(window.retired_reason
                                   if window is not None else None),
            pose_quarantined=bool(pose.quarantined) if pose else False,
            evidence_quarantined=bool(evidence.quarantined)))
    return state, spend_facts, tuple(pose_facts)


# --------------------------------------------------------------------
# the differential itself
# --------------------------------------------------------------------


@dataclass
class TileDiff:
    key: TileKey
    page_edge: bool
    v1_poses: tuple[V1PoseFacts, ...] = ()
    v1_blocks: tuple[V1BlockFacts, ...] = ()
    h2_state: TileState | None = None
    h2_spends: tuple[H2SpendFacts, ...] = ()
    h2_poses: tuple[H2PoseFacts, ...] = ()


@dataclass
class DifferentialReport:
    label: str
    format_ref: str
    tiles_yx: tuple[int, int]
    stream: str
    v1_certified: int
    h2_certified: int
    both: tuple[TileKey, ...]
    v1_only: tuple[TileDiff, ...]
    h2_only: tuple[TileDiff, ...]
    neither: int
    total_tiles: int
    v1_non_accepted_pose_count: int


def _is_page_edge(key: TileKey, tiles_yx: tuple[int, int]) -> bool:
    _page, ty, tx = key
    tiles_y, tiles_x = tiles_yx
    return ty in (0, tiles_y - 1) or tx in (0, tiles_x - 1)


def differential(v1: V1Index, store: Store, h2: H2Index,
                 tiles_yx: tuple[int, int], pages: tuple[int, ...],
                 stream: str = "main", label: str = "",
                 format_ref: str = "") -> DifferentialReport:
    v1_certs = set(v1.certified)
    h2_certs = set(h2_certified_tiles(h2.store_index, stream))
    both = tuple(sorted(v1_certs & h2_certs))
    v1_only_keys = tuple(sorted(v1_certs - h2_certs))
    h2_only_keys = tuple(sorted(h2_certs - v1_certs))

    v1_only = []
    for key in v1_only_keys:
        page, ty, tx = key
        state, spends, poses = h2_tile_facts(store, h2, page, ty, tx, stream)
        v1_only.append(TileDiff(
            key=key, page_edge=_is_page_edge(key, tiles_yx),
            v1_poses=tuple(v1.coverage.get(key, ())),
            h2_state=state, h2_spends=spends, h2_poses=poses))

    h2_only = []
    for key in h2_only_keys:
        page, ty, tx = key
        state, spends, poses = h2_tile_facts(store, h2, page, ty, tx, stream)
        h2_only.append(TileDiff(
            key=key, page_edge=_is_page_edge(key, tiles_yx),
            v1_poses=tuple(v1.coverage.get(key, ())),
            v1_blocks=tuple(v1.blocks.get(key, ())),
            h2_state=state, h2_spends=spends, h2_poses=poses))

    total_tiles = len(pages) * tiles_yx[0] * tiles_yx[1]
    neither = total_tiles - len(both) - len(v1_only) - len(h2_only)
    return DifferentialReport(
        label=label, format_ref=format_ref, tiles_yx=tiles_yx, stream=stream,
        v1_certified=len(v1_certs), h2_certified=len(h2_certs), both=both,
        v1_only=tuple(v1_only), h2_only=tuple(h2_only), neither=neither,
        total_tiles=total_tiles,
        v1_non_accepted_pose_count=v1.non_accepted_pose_count)


# --------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------


def _fmt_v1_poses(poses: tuple[V1PoseFacts, ...]) -> str:
    """One row per LANE (v1's own vocabulary): every ladder rung, mop-up
    and refinement level fits its own pose over the same physical area
    independently, so a tile deep in the ladder is routinely covered by
    a dozen poses — one per lane, occasionally two where a window
    boundary splits. Grouping by lane keeps that fact legible instead of
    listing every (lane, window) pair.
    """
    if not poses:
        return "no committed v1 pose covers this tile"
    by_lane: dict[str, list[V1PoseFacts]] = defaultdict(list)
    for pose in poses:
        by_lane[pose.lane_id].append(pose)
    rows = []
    for lane_id in sorted(by_lane, key=lambda name: (
            by_lane[name][0].lane_kind, name)):
        group = by_lane[lane_id]
        windows = sorted({pose.window_id for pose in group})
        first = group[0]
        rows.append(f"`{lane_id}` ({first.lane_kind}, {first.footing_ppc} "
                    f"ppc): window(s) {windows}")
    return "; ".join(rows)


def _fmt_v1_blocks(blocks: tuple[V1BlockFacts, ...]) -> str:
    if not blocks:
        return "no retained v1 evidence blocks (never touched, or already " \
               "certified-and-pruned under a stream this report did not " \
               "select)"
    rows = []
    for block in blocks:
        rows.append(f"lane `{block.lane_id}`: {block.n_observed} cells "
                    f"observed, |LLR| min={block.min_abs_llr:.3g} "
                    f"mean={block.mean_abs_llr:.3g}")
    return "; ".join(rows)


def _fmt_h2_spends(spends: tuple[H2SpendFacts, ...]) -> str:
    if not spends:
        return "no payload spend recorded (never attempted)"
    rows = []
    for spend in spends:
        rows.append(f"{spend.route}/{spend.footing_or_tag}: "
                    f"{spend.outcome} ({spend.attempts} attempt(s), "
                    f"{spend.exposures} CRC exposure(s))")
    return "; ".join(rows)


def _fmt_h2_poses(poses: tuple[H2PoseFacts, ...]) -> str:
    """One row per DISTINCT (footing, window) — an evidence piece exists
    per (footing, page, pose), so two committed poses of the SAME window
    (a revision) or two overlapping windows at the same footing both
    surface here as separate rows, deliberately not collapsed further.
    The window's own name IS its extent (§5.3: "the footing, region and
    extent ARE the window's name"), so the extent is what is shown —
    a window id's hash prefix is not human-legible and two SIBLING
    windows share every character up to the extent suffix anyway.
    """
    if not poses:
        return "no committed holo2 pose's evidence reaches this tile"
    seen: dict[tuple[str, str], H2PoseFacts] = {}
    for pose in poses:
        seen[(pose.footing_id, pose.window_id)] = pose
    rows = []
    for (footing_id, _window_id), pose in sorted(seen.items()):
        window = (f"{pose.window_status}"
                  + (f"({pose.window_retired_reason})"
                     if pose.window_retired_reason else ""))
        flags = []
        if pose.pose_quarantined:
            flags.append("POSE QUARANTINED")
        if pose.evidence_quarantined:
            flags.append("EVIDENCE QUARANTINED")
        flag_text = f" [{', '.join(flags)}]" if flags else ""
        rows.append(f"footing `{footing_id}`, window extent "
                    f"{pose.window_extent_cells} {window}, "
                    f"page {pose.page}{flag_text}")
    return "; ".join(rows)


def _render_tile_section(title: str, tiles: tuple[TileDiff, ...],
                         *, reverse: bool) -> list[str]:
    lines = [f"## {title} ({len(tiles)} tiles)", ""]
    if not tiles:
        lines.append("None.")
        lines.append("")
        return lines
    for diff in tiles:
        page, ty, tx = diff.key
        edge = " (PAGE-EDGE)" if diff.page_edge else ""
        lines.append(f"### page {page}, tile ({ty}, {tx}){edge}")
        lines.append("")
        lines.append(f"- **v1 covering lanes** (coverage, NOT the minting "
                     f"lane — limitation 1): {_fmt_v1_poses(diff.v1_poses)}")
        if reverse:
            lines.append(f"- **v1 retained evidence**: "
                         f"{_fmt_v1_blocks(diff.v1_blocks)}")
        lines.append(f"- **holo2 rank**: "
                     f"{diff.h2_state.name if diff.h2_state else 'UNKNOWN'}")
        lines.append(f"- **holo2 spends**: {_fmt_h2_spends(diff.h2_spends)}")
        lines.append(f"- **holo2 poses**: {_fmt_h2_poses(diff.h2_poses)}")
        lines.append("")
    return lines


def render_report(report: DifferentialReport) -> str:
    lines: list[str] = []
    lines.append(f"# Tile differential — {report.label or report.format_ref}")
    lines.append("")
    lines.append(f"Format: `{report.format_ref}`, tiles {report.tiles_yx[0]}x"
                f"{report.tiles_yx[1]}, stream `{report.stream}`. Read-only,"
                f" both states loaded as-is (v1 via `load_session`, holo2 via"
                f" `Store.open`).")
    lines.append("")
    if report.v1_non_accepted_pose_count:
        lines.append(f"v1 coverage below drops {report.v1_non_accepted_pose_count}"
                    f" non-`accepted` pose(s) (`redundant`, etc.) — a tile "
                    f"covered only by one of those can read \"no committed "
                    f"v1 pose covers this tile\" below even though v1 did "
                    f"place something there (see `_v1_pose_coverage`'s "
                    f"docstring).")
        lines.append("")
    lines.append("## (A) Certificate sets and their differences")
    lines.append("")
    lines.append(f"- v1 certified: **{report.v1_certified}**")
    lines.append(f"- holo2 certified: **{report.h2_certified}**")
    lines.append(f"- both: **{len(report.both)}**")
    lines.append(f"- v1 has, holo2 lacks: **{len(report.v1_only)}**")
    lines.append(f"- holo2 has, v1 lacks: **{len(report.h2_only)}**")
    lines.append(f"- neither certifies: **{report.neither}**")
    lines.append(f"- total tiles in domain: **{report.total_tiles}**")
    lines.append("")
    lines.extend(_render_tile_section(
        "(B) v1 has, holo2 lacks", report.v1_only, reverse=False))
    lines.extend(_render_tile_section(
        "(C) holo2 has, v1 lacks", report.h2_only, reverse=True))
    lines.append("## (D) Summary by class")
    lines.append("")
    lines.append(summary_table(report))
    lines.append("")
    lines.append("## (E) Spatial tally (v1-only tiles)")
    lines.append("")
    lines.append("Column (tx) / row (ty) counts within the v1-only list — "
                f"tiles {report.tiles_yx[0]}x{report.tiles_yx[1]}, edges at "
                f"tx/ty in {{0, {report.tiles_yx[1] - 1}}} / "
                f"{{0, {report.tiles_yx[0] - 1}}}. A count concentrated in "
                "one or two non-edge values is a placement/registration-"
                "band signal, not diffuse decode-quality noise.")
    lines.append("")
    lines.append(_tx_ty_histogram(report.v1_only))
    lines.append("")
    return "\n".join(lines)


def _v1_only_footing_set(diff: TileDiff) -> set[str]:
    return {spend.footing_or_tag for spend in diff.h2_spends}


def _has_below_floor(diff: TileDiff) -> bool:
    return any(spend.outcome == "below_floor" for spend in diff.h2_spends)


def _narrower_than_domain_footing_set(diff: TileDiff,
                                      domain: set[str]) -> bool:
    """True if this tile's spend footings are a strict subset of every
    footing exercised anywhere in the report's v1-only set — i.e. at
    least one reachable footing on OTHER tiles never ran a decoder here
    (typically because a `below_floor` row pre-empted it: no informative
    cells, no attempt, so no footing above it in the ladder ran either).
    """
    footings = _v1_only_footing_set(diff)
    return bool(footings) and footings < domain


def summary_table(report: DifferentialReport) -> str:
    def _count(tiles: tuple[TileDiff, ...], predicate) -> int:
        return sum(1 for diff in tiles if predicate(diff))

    domain_footings: set[str] = set()
    for diff in report.v1_only:
        domain_footings |= _v1_only_footing_set(diff)

    rows = [
        ("both certified", len(report.both), "—"),
        ("v1-only: holo2 NEVER-ADDRESSED",
         _count(report.v1_only, lambda d: d.h2_state == TileState.UNKNOWN),
         "no committed holo2 pose ever reached the tile"),
        ("v1-only: holo2 ADDRESSED-NOT-ATTEMPTED",
         _count(report.v1_only,
                lambda d: d.h2_state == TileState.ADDRESSED),
         "covered by a pose; no CRC-bearing attempt landed"),
        ("v1-only: holo2 ATTEMPTED-FAILED",
         _count(report.v1_only,
                lambda d: d.h2_state == TileState.ATTEMPTED),
         "a payload spend ran and did not certify"),
        ("v1-only: page-edge",
         _count(report.v1_only, lambda d: d.page_edge), "—"),
        ("v1-only: has a `below_floor` footing",
         _count(report.v1_only, _has_below_floor),
         "no decoder ran there (n_informative < k_eff) — not a CRC "
         "failure; NOT a subset of ATTEMPTED-FAILED, since one "
         "below_floor row can coexist with crc_failed rows at other "
         "footings on the same tile"),
        ("v1-only: spend-footing set narrower than the report's domain",
         _count(report.v1_only,
                lambda d: _narrower_than_domain_footing_set(
                    d, domain_footings)),
         "at least one footing that ran elsewhere in this report never "
         "ran here at all — usually the footings above a below_floor row"),
        ("holo2-only: v1 has no pose coverage",
         _count(report.h2_only, lambda d: not d.v1_poses),
         "no v1 window ever reached the tile either"),
        ("holo2-only: v1 retains uncertified evidence",
         _count(report.h2_only, lambda d: bool(d.v1_blocks)),
         "v1 tried and had not (yet) closed it"),
        ("holo2-only: page-edge",
         _count(report.h2_only, lambda d: d.page_edge), "—"),
        ("neither certifies", report.neither, "—"),
    ]
    lines = ["| class | count | note |", "|---|---:|---|"]
    for name, count, note in rows:
        lines.append(f"| {name} | {count} | {note} |")
    return "\n".join(lines)


def _tx_ty_histogram(tiles: tuple[TileDiff, ...]) -> str:
    """Compact column/row tallies over a one-sided tile list — the
    spatial structure ``summary_table`` (a per-class count table) cannot
    show: a gap concentrated in a couple of tx/ty values is a placement/
    registration-band question, not a diffuse decode-quality one."""
    if not tiles:
        return "no tiles."
    tx_hist: dict[int, int] = defaultdict(int)
    ty_hist: dict[int, int] = defaultdict(int)
    for diff in tiles:
        _page, ty, tx = diff.key
        tx_hist[tx] += 1
        ty_hist[ty] += 1
    n = len(tiles)

    def _row(hist: dict[int, int], axis: str) -> str:
        top = sorted(hist.items(), key=lambda kv: (-kv[1], kv[0]))
        shown = ", ".join(f"{axis}={k}: {v}" for k, v in top if v > 1)
        return shown or "no value repeats more than once"

    return (f"tx tally (of {n}): {_row(tx_hist, 'tx')}\n\n"
           f"ty tally (of {n}): {_row(ty_hist, 'ty')}")


# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------


def run(v1_state_path: Path, h2_state_dir: Path, format_ref: str,
       *, label: str = "", stream: str = "main") -> DifferentialReport:
    spec = resolve_format_ref(format_ref)
    # spec.tiles_yx (the public field) is Optional — None for a fossil
    # resolved through .layout; spec._tiles_yx is the total resolving
    # property the descriptor tree itself uses internally
    # (format/descriptor.py:393-397, also read at :409/:525/:537). Do not
    # "fix" this to the public name — it returns None on a layout-derived
    # identity such as the fossil this instrument decodes real sheets
    # against.
    tiles_yx = spec._tiles_yx
    v1_state = load_session(v1_state_path)
    v1_index = build_v1_index(v1_state, tiles_yx, stream=stream)
    pages = (v1_state.page_hypotheses if v1_state.page_hypotheses
            else tuple(sorted({page for page, _, _ in v1_index.certified})))
    if not pages:
        pages = (0,)
    with open_h2_store(h2_state_dir) as store:
        h2_index = build_h2_index(store)
        report = differential(v1_index, store, h2_index, tiles_yx, pages,
                              stream=stream, label=label,
                              format_ref=format_ref)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--v1-state", required=True, type=Path)
    parser.add_argument("--h2-state", required=True, type=Path)
    parser.add_argument("--format", required=True,
                        help="the printed format identity both states "
                             "decode (e.g. L:c2-r0700@3392x2368)")
    parser.add_argument("--label", default="")
    parser.add_argument("--stream", default="main")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the markdown report here (also "
                             "printed to stdout)")
    args = parser.parse_args(argv)

    report = run(args.v1_state, args.h2_state, args.format,
                label=args.label or args.format, stream=args.stream)
    text = render_report(report)
    print(text)
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
        print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
