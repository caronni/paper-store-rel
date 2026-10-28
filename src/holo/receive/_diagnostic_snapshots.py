"""Thin pass-through snapshot builders for the live diag viewer.

The runtime attaches ``snapshot_factory`` thunks (closing over live stage
products) to selected events.  A builder here packages those references into
one small tagged dict — no typed mirror, no copies, no rendering.  The viewer
(:mod:`holo.receive.diag.viewer`) opts in per event name via
``wants_snapshot`` and consumes the references immediately inside the
observer boundary; scalar-only observers never trigger a builder, so the
headless event stream stays byte-identical.

Builders nothing currently consumes return ``None`` so an accidental
invocation stays free; ``EventSink.emit`` simply attaches the value to the
event's optional ``snapshot`` field.
"""
from __future__ import annotations

from typing import Callable

import numpy as np


def lane(*args: object, **kwargs: object) -> None:
    return None


def survey(payload_survey: object, regions: object,
           preview: object = None) -> dict[str, object]:
    return {"kind": "survey", "survey": payload_survey,
            "regions": regions, "preview": preview}


def window(
    attempt: object,
    placed: object | None,
    *,
    pitch_px: object = None,
    region_origin_yx: object = None,
    ordinal: int = 0,
    queue_total: int = 0,
    anchor_count: int = 0,
) -> dict[str, object]:
    return {
        "kind": "window", "attempt": attempt, "placed": placed,
        "pitch_px": pitch_px, "region_origin_yx": region_origin_yx,
        "ordinal": ordinal, "queue_total": queue_total,
        "anchor_count": anchor_count,
    }


def window_phase(
    region_index: int,
    window_value: object,
    phase_name: str,
    *,
    segment: object = None,
    attempted_routes: tuple[str, ...] = (),
    candidate: object = None,
    patch_id: int | None = None,
    pitch_px: object = None,
    region_origin_yx: object = None,
    ordinal: int = 0,
    queue_total: int = 0,
    anchor_count: int = 0,
) -> dict[str, object]:
    return {
        "kind": "window_phase", "region_index": region_index,
        "window": window_value, "phase": phase_name, "segment": segment,
        "attempted_routes": attempted_routes, "candidate": candidate,
        "patch_id": patch_id, "pitch_px": pitch_px,
        "region_origin_yx": region_origin_yx, "ordinal": ordinal,
        "queue_total": queue_total, "anchor_count": anchor_count,
    }


def address(product: object) -> dict[str, object]:
    return {"kind": "address", "product": product}


def address_progress(
    placements: object,
    attempts: object,
    region_states: object,
    hypotheses_evaluated: int,
) -> dict[str, object]:
    return {
        "kind": "address_progress", "placements": placements,
        "attempts": attempts, "region_states": region_states,
        "hypotheses_evaluated": hypotheses_evaluated,
    }


def committed(state: object, spec: object) -> dict[str, object]:
    return {"kind": "committed", "state": state, "spec": spec}


def barrier(
    candidate: object,
    delta: object,
    base_digest: object,
    source_sha256: object,
    close_value: object,
    spec: object,
) -> dict[str, object]:
    return {
        "kind": "barrier", "state": candidate, "delta": delta,
        "base_digest": base_digest, "source_sha256": source_sha256,
        "close": close_value, "spec": spec,
    }


def session_summary(
    state: object,
    spec: object,
    *,
    base_state_sha256: object = None,
    close_value: object = None,
) -> dict[str, object]:
    return {
        "kind": "session_summary", "state": state, "spec": spec,
        "base_state_sha256": base_state_sha256, "close": close_value,
    }


def close_factory(
    state: object,
    record: object,
    progress: Callable[[], object],
    spec: object,
) -> Callable[[], dict[str, object]]:
    """Lazy close snapshot; ``progress`` runs only when a viewer opted in.

    The ``deferred_counts`` marking is single-sourced from the progress
    value's ``count_only`` flag (a deferred barrier or a count-gated skip
    never computed rank/solve), so a view never renders a fake rank 0.
    """
    def build() -> dict[str, object]:
        value = progress()
        return {
            "kind": "close", "state": state, "record": record,
            "progress": value, "spec": spec,
            "deferred_counts": bool(getattr(value, "count_only", False)),
        }
    return build


def close(*args: object, **kwargs: object) -> None:
    return None


def context(*args: object, **kwargs: object) -> None:
    return None


def refinement(*args: object, **kwargs: object) -> None:
    return None


def payload(frontier: object, spec: object) -> dict[str, object] | None:
    """Owner-frozen geometric reach: per page, the touched 64-cell tiles.

    Feeds pane D's reachable/evidence layer at the exact one-owner freeze
    (RECEIVE-DESIGN §10.3.3); built lazily, only when snapshots are enabled.
    """
    layout = getattr(spec, "layout", None)
    if layout is None:
        return None
    tiles_x = int(layout.tiles_yx[1])
    pages: dict[int, np.ndarray] = {}
    for page in getattr(frontier, "pages", ()):
        cells = np.asarray(page.cells_yx, np.int64)
        if cells.ndim != 2 or not len(cells):
            continue
        pages[int(page.page)] = np.unique(
            (cells[:, 0] // 64) * tiles_x + cells[:, 1] // 64)
    return {"kind": "payload_reach", "tiles_x": tiles_x, "pages": pages}


def payload_progress(*args: object, **kwargs: object) -> None:
    return None


def attempt(*args: object, **kwargs: object) -> None:
    return None


def plane_fields(report: object) -> dict[str, object]:
    """PLANE-FIELDS W2 snapshot: the exaggerated per-plane quiver.

    The pinned shape (docs/PLANE-FIELDS.md §6.2 W5) is a compact
    ``[plane_index, tile_y, tile_x, dx_dots, dy_dots]`` list plus the
    exaggeration the pane should draw at.  The report builds it — this
    stays the thin pass-through every other builder here is.
    """
    return report.snapshot()  # type: ignore[attr-defined]


__all__ = [
    "address", "address_progress", "attempt", "barrier", "close",
    "close_factory",
    "committed", "context", "lane", "payload", "payload_progress",
    "plane_fields",
    "refinement", "session_summary", "survey", "window", "window_phase",
]
