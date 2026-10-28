"""The four holo2 panes and the composed frame (DESIGN §10.3).

The v1 receiver composed ONE frame per page from four equal panes in a
horizontal row under fixed headings (RECEIVE-DESIGN §10.3.1). holo2 keeps
that shape and the semantic palette, and re-aims two of the four panes at
the model holo2 actually has:

======  =========================  =====================================
pane    v1                         holo2
======  =========================  =====================================
A       ACQUIRED — lane/capture    CAPTURE — regions, support, the §8.2
        space, survey regions,     window lattice, committed poses and
        window overlays            the §6 done-pixel coverage
B       PLACED — page-space        PAGE — the tile map: per work key and
        piece-hue placement        per stream, UNKNOWN/ADDRESSED/
                                   ATTEMPTED/CERTIFIED, with the piece
                                   count of the observing evidence
C       ADDRESS — BCH word sites   WORKERS — the ready queue, the worker
        per tile                   population, fires, wakes, fires in
                                   flight, stale discards (no v1 equal)
D       PAYLOAD — LDPC tiles       CLOSE — per (stream, block)
                                   have/needed/rank, metadata rank, the
                                   verified stop
======  =========================  =====================================

v1's pane B (page-space placement colouring by scrap piece) is folded
into holo2's pane A: holo2's committed pose IS the placement, and a
window that owns a pose is drawn where it lives on the capture. The
address plane that used to be pane C is the tile map's ``ADDRESSED``
state, so it lives in pane B beside the streams it addresses; that frees
pane C for the worker/queue questions §10.3 explicitly requires an
observer to answer.

Observer-side only. Every renderer takes an already-derived
:class:`~holo2.diag.panes.model.PaneModel` and returns pixels.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from ...core import CloseStatus
from ...solve import TileState
from .model import (WINDOW_DONE, WINDOW_POSED, WINDOW_RETIRED, PaneModel,
                    PaneSource)
from .paint import (AMBER, BG, BLUE, CHIP_AMBER, CHIP_BLUE, CHIP_GREEN,
                    CHIP_NEUTRAL, CHIP_REACH, CHIP_TEXT, CHIP_UNSEEN, CYAN,
                    GREEN, HUES, MUTED, ORANGE, PENDING_OUTLINE, PURPLE,
                    TEXT, Pane, TileGrid, compose, mask_edge, resize_mask)

PANE_TITLES = ("A CAPTURE", "B PAGE", "C WORKERS", "D CLOSE")
DEFAULT_PANE_WIDTH = 520

# Tile-map chips, by TileState rank. The v1 green-certified language is
# carried verbatim; ADDRESSED takes v1's "reachable" pale blue and
# ATTEMPTED takes its amber "below floor", because that is exactly what
# the two states mean here (observed but not solved / solved-attempt that
# did not certify).
TILE_CHIPS = {
    TileState.UNKNOWN.value: CHIP_UNSEEN,
    TileState.ADDRESSED.value: CHIP_REACH,
    TileState.ATTEMPTED.value: CHIP_AMBER,
    TileState.CERTIFIED.value: CHIP_GREEN,
}

WINDOW_OUTLINE = {WINDOW_POSED: GREEN, WINDOW_RETIRED: ORANGE,
                  WINDOW_DONE: CYAN}
_WINDOW_RANK = {WINDOW_RETIRED: 1, WINDOW_POSED: 2, WINDOW_DONE: 3}


def pane_size(tiles_yx: tuple[int, int],
              width: int = DEFAULT_PANE_WIDTH) -> tuple[int, int]:
    """One pane's ``(width, height)``; all four share it (§10.3.1)."""
    tiles_y, tiles_x = (max(1, int(v)) for v in tiles_yx)
    height = round(width * tiles_y / tiles_x)
    return int(width), int(min(max(height, round(width * 0.5)),
                               round(width * 2.0)))


# ---------------------------------------------------------------- pane A

def capture_pane(model: PaneModel, source: PaneSource | None,
                 width: int, height: int) -> np.ndarray:
    """Pane A: capture space — support, windows, poses, done coverage."""
    capture = model.capture
    if capture is None or not capture.regions:
        pane = Pane(width, height)
        # L15: the model already derived WHY there is nothing to draw
        # (no captures / a survey that declined / a terminal session that
        # ingests nothing). Print that, not one guessed cause for all of
        # them; the generic line is the fallback, not the answer.
        notes = [(note, MUTED) for note in model.notes]
        pane.rows(10, 12, ["capture pane unavailable",
                           *(notes or [("no surveyed region is schedulable",
                                        MUTED)])],
                  size=12)
        return pane.array()
    y0 = min(region.bbox_px[0] for region in capture.regions)
    x0 = min(region.bbox_px[1] for region in capture.regions)
    y1 = max(region.bbox_px[2] for region in capture.regions)
    x1 = max(region.bbox_px[3] for region in capture.regions)
    pad_y = max(1.0, 0.03 * (y1 - y0))
    pad_x = max(1.0, 0.03 * (x1 - x0))
    y0, x0, y1, x1 = y0 - pad_y, x0 - pad_x, y1 + pad_y, x1 + pad_x
    scale = min(width / max(1.0, x1 - x0), height / max(1.0, y1 - y0))
    underlay = (source.underlay(capture.short) if source is not None
                else None)
    canvas = _underlay_canvas(underlay, (y0, x0, y1, x1), scale, width, height)

    def to_pane(py: float, px: float) -> tuple[int, int]:
        return (int(round((px - x0) * scale)), int(round((py - y0) * scale)))

    for region in capture.regions:
        _paint_region(canvas, region, to_pane, width, height)
    pane = Pane(width, height, canvas=canvas)
    label = max(9, min(13, round(width * 0.026)))
    for order, region in enumerate(capture.regions):
        by0, bx0, by1, bx1 = region.bbox_px
        px0, py0 = to_pane(by0, bx0)
        px1, py1 = to_pane(by1, bx1)
        done = bool(region.done.any())
        pane.rect((px0, py0, px1, py1),
                  outline=GREEN if done else BLUE, width=1)
        pane.text((px0 + 2, max(0, py0 - label - 2)), str(order),
                  GREEN if done else BLUE, label)
        # Windows overlap by construction (§8.2 size 256 / step 128), so
        # the paint order IS the precedence: the strongest claim about a
        # rectangle must be the one left visible. Done last.
        for mark in sorted(region.windows,
                           key=lambda item: _WINDOW_RANK.get(item.state, 0)):
            cy0, cx0, cy1, cx1 = mark.extent_cells
            wx0, wy0 = to_pane(region.origin_yx[0] + cy0 * region.pitch_px,
                               region.origin_yx[1] + cx0 * region.pitch_px)
            wx1, wy1 = to_pane(region.origin_yx[0] + cy1 * region.pitch_px,
                               region.origin_yx[1] + cx1 * region.pitch_px)
            colour = WINDOW_OUTLINE.get(mark.state)
            if mark.state == WINDOW_DONE:
                pane.dashed((wx0, wy0, wx1, wy1), CYAN)
            else:
                pane.rect((wx0, wy0, wx1, wy1),
                          outline=colour or PENDING_OUTLINE,
                          width=2 if colour is not None else 1)
    if underlay is None:
        pane.text((6, height - 15),
                  "preview omitted: capture above the underlay budget",
                  MUTED, 10)
    return pane.array()


def _underlay_canvas(underlay, frame, scale: float, width: int,
                     height: int) -> np.ndarray:
    canvas = np.zeros((height, width, 3), np.uint8)
    canvas[:] = BG
    if underlay is None:
        return canvas
    grey, stride = underlay
    y0, x0, y1, x1 = frame
    py0 = max(0, int(y0 / stride))
    px0 = max(0, int(x0 / stride))
    py1 = max(py0 + 1, min(grey.shape[0], int(np.ceil(y1 / stride))))
    px1 = max(px0 + 1, min(grey.shape[1], int(np.ceil(x1 / stride))))
    crop = grey[py0:py1, px0:px1]
    if not crop.size:
        return canvas
    low, high = np.percentile(crop, (1.0, 99.0))
    span = max(float(high) - float(low), 1e-6)
    # v1's 1/99 stretch, then lightened toward the shell so region tints
    # and window overlays stay legible over dense print texture.
    stretched = 0.55 + 0.45 * np.clip((crop - float(low)) / span, 0.0, 1.0)
    target_h = max(1, min(height, round((py1 - py0) * stride * scale)))
    target_w = max(1, min(width, round((px1 - px0) * stride * scale)))
    resized = np.asarray(_resize_grey(stretched, (target_w, target_h)),
                         np.uint8)
    oy = min(max(0, round((py0 * stride - y0) * scale)),
             height - resized.shape[0])
    ox = min(max(0, round((px0 * stride - x0) * scale)),
             width - resized.shape[1])
    canvas[oy:oy + resized.shape[0], ox:ox + resized.shape[1]] = (
        resized[..., None])
    return canvas


def _resize_grey(values: np.ndarray, size_wh: tuple[int, int]) -> np.ndarray:
    image = Image.fromarray((values * 255.0).astype(np.uint8))
    return np.asarray(image.resize(size_wh, Image.BILINEAR), np.uint8)


def _paint_region(canvas: np.ndarray, region, to_pane, width: int,
                  height: int) -> None:
    by0, bx0, by1, bx1 = region.bbox_px
    px0, py0 = to_pane(by0, bx0)
    px1, py1 = to_pane(by1, bx1)
    x0c, y0c = max(0, px0), max(0, py0)
    x1c, y1c = min(width, px1), min(height, py1)
    if x1c <= x0c or y1c <= y0c:
        return
    box_w, box_h = max(1, px1 - px0), max(1, py1 - py0)
    support = resize_mask(region.support, (box_w, box_h))
    done = resize_mask(region.done, (box_w, box_h))
    support = support[y0c - py0:y1c - py0, x0c - px0:x1c - px0]
    done = done[y0c - py0:y1c - py0, x0c - px0:x1c - px0]
    target = canvas[y0c:y1c, x0c:x1c]
    hue = np.asarray(HUES[region.hue % len(HUES)], np.float32)
    if support.any():
        target[support] = (0.62 * target[support].astype(np.float32)
                           + 0.38 * hue).astype(np.uint8)
    if done.any():
        # §6 done pixels: certified, spent, never posed again. The green
        # wash is the only place a pane shows the done projection, and it
        # is drawn OVER the identity tint so a half-done region reads as
        # half-done rather than as a different region.
        green = np.asarray(GREEN, np.float32)
        target[done] = (0.45 * target[done].astype(np.float32)
                        + 0.55 * green).astype(np.uint8)
    if support.any():
        target[mask_edge(support)] = BLUE


# ---------------------------------------------------------------- pane B

def page_pane(model: PaneModel, width: int, height: int) -> np.ndarray:
    """Pane B: the tile map of one page, per work key and per stream."""
    plane = model.plane
    if plane is None:
        pane = Pane(width, height)
        pane.rows(10, 12, ["page pane unavailable",
                           ("no session bound to the observer", MUTED)],
                  size=12)
        return pane.array()
    grid = TileGrid(width, height, plane.tiles_yx)
    pane = grid.base()
    n_streams = max(1, plane.states.shape[0])
    font_size = grid.count_font()
    touched = np.flatnonzero(plane.states.max(axis=0).ravel()
                             | (plane.evidence > 0).ravel())
    tiles_x = plane.tiles_yx[1]
    for flat in touched:
        ty, tx = divmod(int(flat), tiles_x)
        box = grid.box(ty, tx)
        for index in range(n_streams):
            rank = int(plane.states[index, ty, tx])
            segment = grid.segment(box, index, n_streams)
            fill, outline = (CHIP_NEUTRAL if rank == TileState.UNKNOWN.value
                             else TILE_CHIPS.get(rank, CHIP_BLUE))
            pane.draw.rectangle(segment, fill=fill, outline=outline)
        count = int(plane.evidence[ty, tx])
        if count and font_size is not None:
            pane.text((box[0] + 2, box[1] + 1), str(min(count, 999)),
                      CHIP_TEXT, font_size)
    return pane.array()


# ---------------------------------------------------------------- pane C

def workers_pane(model: PaneModel, width: int, height: int) -> np.ndarray:
    """Pane C: the ready queue and the worker population (§10.3).

    No v1 equivalent — v1 had barriers and lanes where holo2 has a
    fixpoint over a ready set, so this pane is written against the
    questions DESIGN §10.3 names: queue depth and composition, running /
    sleeping / retired, sleeping keyed by subscription, per-worker fire
    counts, wakes-per-commit and the useful-re-run ratio.
    """
    pane = Pane(width, height)
    snapshot = model.snapshot
    if not snapshot:
        pane.rows(10, 12, ["worker pane unavailable",
                           ("no orchestrator snapshot is bound", MUTED)],
                  size=12)
        return pane.array()
    ready = snapshot.get("ready") or {}
    workers = snapshot.get("workers") or {}
    counters = snapshot.get("counters") or {}
    size = max(9, min(13, round(width * 0.024)))
    y = 10
    y = pane.rows(10, y, [
        (f"recipe {snapshot.get('recipe', '-')} · "
         f"{snapshot.get('mode', 'free')} · pool "
         f"{snapshot.get('pool_size', 1)}"
         + (" · --complete" if snapshot.get("complete") else ""), TEXT),
    ], size=size) + 4

    population = (
        ("ready", int(ready.get("depth", 0)), CYAN),
        ("running", len(workers.get("running") or ()), PURPLE),
        ("sleeping", int(workers.get("sleeping", 0)), BLUE),
        ("retired", int(workers.get("retired", 0)), GREEN),
        # DG-1: a decline is reported under its REAL name, and the two
        # kinds are different facts — a permanent decline is work that
        # will never be offered again, a re-offerable one is work waiting
        # for a wake. The key that used to stand here alone,
        # ``declined_done_gate``, has had no publisher since R1.
        ("declined", int(workers.get("declined", 0)), AMBER),
        ("re-offerable", int(workers.get("declined_pending", 0)), ORANGE),
    )
    y = _bars(pane, y, width, size,
              tuple((f"{name:<12}{value:>6}", value, hue)
                    for name, value, hue in population)) + 4

    by_family = ready.get("by_family") or {}
    pane.text((10, y), "ready by family", MUTED, size)
    y += size + 4
    y = _bars(pane, y, width, size,
              tuple((f"{name:<11}{value:>6}", value, CYAN)
                    for name, value in sorted(by_family.items())),
              empty="queue empty") + 4

    sleeping_by_kind = snapshot.get("sleeping_by_subscription_key") or {}
    pane.text((10, y), "sleeping by subscription kind", MUTED, size)
    y += size + 4
    pane.text((10, y),
              (" · ".join(f"{kind} {count}"
                          for kind, count in sorted(sleeping_by_kind.items()))
               or "no sleeping worker declares a read-set"),
              TEXT, size)
    y += size + 10

    # §10.3 asks an observer for per-worker fire counts. The distribution
    # is what answers the question a fixpoint raises — a worker that fired
    # once converged; a tail that fires many times is a wake-graph smell —
    # and unlike a top-N list it stays bounded on a real page.
    fires_by_worker = workers.get("fires_by_worker") or {}
    pane.text((10, y), "workers by fire count", MUTED, size)
    y += size + 4
    histogram: dict[int, int] = {}
    for count in fires_by_worker.values():
        histogram[int(count)] = histogram.get(int(count), 0) + 1
    y = _bars(pane, y, width, size,
              tuple((f"{count:>3}x {histogram[count]:>6}", histogram[count],
                     BLUE) for count in sorted(histogram)[:6]),
              empty="no worker has fired")
    if len(histogram) > 6:
        pane.text((10, y), f"… {len(histogram) - 6} more fire counts, "
                  f"max {max(histogram)}x", MUTED, size)
        y += size + 6
    y += 4

    pane.text((10, y), "counters", MUTED, size)
    y += size + 4
    pane.rows(10, y, [
        # "scheduled commits", never bare "commits": this pane draws the
        # QUEUE's numbers, and the session total (ingest's commits
        # included) is the six-row block's. One owner, two names — the two
        # used to share one word and disagree by the ingest commits.
        f"fires {counters.get('fires', 0)}"
        f" · scheduled commits {counters.get('commits', 0)}"
        f" · idle pops {counters.get('idle_pops', 0)}",
        f"wakes {counters.get('wakes', 0)}"
        f" · per commit {float(counters.get('wakes_per_commit', 0.0)):.2f}"
        f" · useful {float(counters.get('useful_rerun_ratio', 0.0)):.2f}",
        f"peak in flight {counters.get('peak_inflight', 0)}"
        f" · dispatched {counters.get('dispatched', 0)}"
        f" · cancelled {counters.get('cancelled', 0)}"
        f" · stale {counters.get('stale_discards', 0)}"
        f" ({float(counters.get('stale_discard_ratio', 0.0)):.2f})",
        f"work units {counters.get('work_units', 0)}"
        f" · consults {counters.get('consults', 0)}"
        f" · observed {counters.get('observations', 0)}",
        _outcome_line(counters.get("outcomes") or {}),
    ], size=size)
    return pane.array()


def _bars(pane: Pane, y: int, width: int, size: int,
          rows: tuple[tuple[str, int, tuple[int, int, int]], ...], *,
          empty: str | None = None) -> int:
    """Pane C's one row idiom: label, bar scaled to the block's own max.

    Every block in this pane shares the geometry, so it lives here once;
    the label text stays each caller's, because a fire-count histogram and
    a worker population do not name their rows the same way.
    """
    if not rows:
        if empty is not None:
            pane.text((10, y), empty, MUTED, size)
            y += size + 6
        return y
    top = max(1, max(value for _label, value, _hue in rows))
    for label, value, hue in rows:
        pane.text((10, y), label, TEXT, size)
        pane.bar((10 + 8 * size, y, width - 10, y + size - 2), value / top,
                 fill=hue)
        y += size + 6
    return y


def _outcome_line(outcomes: dict) -> str:
    if not outcomes:
        return "no worker outcome recorded yet"
    return "outcomes " + " · ".join(f"{name} {count}"
                                    for name, count in sorted(
                                        outcomes.items()))


# ---------------------------------------------------------------- pane D

def close_rows(snapshot: dict) -> tuple[tuple[str, int, int, int, bool], ...]:
    """``(name, needed, have, rank, solved)`` per block, from the snapshot.

    A K-row volume carries ``stream_id = None`` on its block progress (one
    implicit stream), so the block is named by its index alone rather than
    by an invented stream name.
    """
    close = snapshot.get("close") or {}
    rows: list[tuple[str, int, int, int, bool]] = []
    for entry in close.get("blocks", ()) or ():
        if not isinstance(entry, dict):
            continue
        stream = entry.get("stream")
        block = entry.get("block", "?")
        name = f"{stream}#{block}" if stream else f"block {block}"
        rows.append((name,
                     int(entry.get("needed", 0)), int(entry.get("have", 0)),
                     int(entry.get("rank", 0)), bool(entry.get("solved"))))
    return tuple(rows)


def verified_phrase(model: PaneModel) -> str:
    if model.close_status == CloseStatus.VERIFIED.value:
        sha = (model.payload_sha256 or "")[:16]
        return f"VERIFIED · sha {sha}…"
    close = model.snapshot.get("close") or {}
    return f"close {close.get('status', model.close_status)}"


def close_pane(model: PaneModel, width: int, height: int) -> np.ndarray:
    """Pane D: the fountain close — per (stream, block), and the stop."""
    pane = Pane(width, height)
    size = max(9, min(13, round(width * 0.024)))
    close = model.snapshot.get("close") or {}
    plane = model.plane
    y = pane.rows(10, 10, [
        (verified_phrase(model),
         GREEN if model.close_status == "verified" else TEXT),
        (f"row {model.row_id} · codec {model.codec_id}"
         f" · page {model.page} of {len(model.pages)}", MUTED),
        f"certified work keys {close.get('certified', 0)}"
        + (f" · page tiles done {plane.certified_tiles()}"
           f"/{plane.tiles_yx[0] * plane.tiles_yx[1]}" if plane else ""),
        f"K {close.get('symbols_used', '-')}/{close.get('k_total', '-')}"
        f" · metadata rank {close.get('metadata_rank', '-')}/24"
        f" · counters {close.get('metadata_counters', '-')}",
    ], size=size) + 8

    rows = close_rows(model.snapshot)
    pane.text((10, y), "blocks (have / needed, rank)", MUTED, size)
    y += size + 6
    if not rows:
        pane.text((10, y),
                  "the close has not been consulted at this frontier",
                  MUTED, size)
        return pane.array()
    label = max(6 * size, 90)
    for name, needed, have, rank, solved in rows:
        if y + size + 6 > height - 6:
            pane.text((10, y), f"… {len(rows)} blocks in total", MUTED, size)
            break
        pane.text((10, y), f"{name}", TEXT, size)
        pane.bar((10 + label, y, width - 78, y + size - 2),
                 have / max(1, needed), fill=GREEN if solved else BLUE)
        pane.text((width - 72, y),
                  f"{have}/{needed} r{rank}", GREEN if solved else TEXT, size)
        y += size + 6
    return pane.array()


# ------------------------------------------------------------- the frame

def render_frame(model: PaneModel, source: PaneSource | None = None, *,
                 width: int = DEFAULT_PANE_WIDTH) -> bytes:
    """One composed PNG frame: four panes in a row under fixed headings."""
    tiles_yx = model.plane.tiles_yx if model.plane is not None else (1, 1)
    pane_w, pane_h = pane_size(tiles_yx, width)
    title_size = max(9, min(15, round(pane_w * 0.032)))
    rasters = (
        capture_pane(model, source, pane_w, pane_h),
        page_pane(model, pane_w, pane_h),
        workers_pane(model, pane_w, pane_h),
        close_pane(model, pane_w, pane_h),
    )
    return compose(rasters, PANE_TITLES,
                   title_height=max(18, title_size + 9),
                   title_size=title_size)


def frame_size(model: PaneModel, width: int = DEFAULT_PANE_WIDTH
               ) -> tuple[int, int]:
    """The composed frame's ``(width, height)`` in pixels, without drawing."""
    tiles_yx = model.plane.tiles_yx if model.plane is not None else (1, 1)
    pane_w, pane_h = pane_size(tiles_yx, width)
    title_size = max(9, min(15, round(pane_w * 0.032)))
    return 4 * pane_w, max(18, title_size + 9) + pane_h


__all__ = [
    "DEFAULT_PANE_WIDTH", "PANE_TITLES", "TILE_CHIPS", "WINDOW_OUTLINE",
    "capture_pane", "close_pane", "close_rows", "frame_size", "page_pane",
    "pane_size", "render_frame", "verified_phrase", "workers_pane",
]
