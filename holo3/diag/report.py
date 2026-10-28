"""The durable products: the event journal and report.json.

Above `readout` — the report is the status dict plus the post-mortem
facts — and the only place in diag that writes files.
"""
from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from .model import DiagModel
from .readout import (capture_selectors, ladder_isolation_advisory,
                      lane_label, status)


def _jsonable(value: object) -> object:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, np.ndarray):
        return {"shape": list(value.shape), "dtype": str(value.dtype)}
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return _event_dict(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _event_dict(event: object) -> dict:
    payload: dict[str, object] = {"type": type(event).__name__}
    for one_field in fields(event):
        payload[one_field.name] = _jsonable(getattr(event, one_field.name))
    return payload


def write_events_jsonl(path: Path, events: Sequence[object]) -> None:
    with path.open("w") as handle:
        for event in events:
            try:
                line = json.dumps(_event_dict(event))
            except Exception:
                line = json.dumps({"type": type(event).__name__,
                                   "unserializable": True})
            handle.write(line)
            handle.write("\n")


def _capture_facts(model: DiagModel) -> list[dict]:
    facts = []
    for ordinal in capture_selectors(model):
        capture_id = model.ordinals[ordinal]
        opened = model.captures.get(capture_id)
        survey = model.surveys.get(capture_id)
        entries = [event for (cid, _pool), event in
                   model.calibrations.items() if cid == capture_id]
        refusals: dict[str, int] = {}
        for event in entries:
            if not event.adopted:
                refusals[event.reason] = refusals.get(event.reason, 0) + 1
        regions = [] if survey is None else [
            {"region_index": mark.region_index,
             "origin_yx": list(mark.origin_yx),
             "shape_cells": list(mark.shape_cells),
             "pitch_px": mark.pitch_px,
             "support_cells": mark.support_cells,
             "step_px": mark.step_px}
            for mark in survey.regions]
        facts.append({
            "ordinal": ordinal,
            "capture": capture_id,
            "dpi": None if opened is None else opened.dpi,
            "levels_ppc": ([] if opened is None
                           else list(opened.levels_ppc)),
            "shape_yx": (None if opened is None
                         else list(opened.shape_yx)),
            "channels": None if opened is None else opened.channels,
            "regions": regions,
            "settled_causes": dict(model.settle_causes.get(capture_id, {})),
            "calibrate": {
                "adopted": sum(1 for event in entries if event.adopted),
                "seen": len(entries),
                "refusals": refusals,
            },
            "placements": {
                str(region_index): count
                for (cid, region_index), count in
                sorted(model.region_placements.items())
                if cid == capture_id},
            "live_windows": sum(1 for key in model.windows
                                if key[0] == capture_id),
        })
    return facts


def _field_facts(model: DiagModel) -> list[dict]:
    """Every lane-page's latest fit, in full — the post-mortem home for
    the numbers the status row only glances at."""
    rows = []
    for key in sorted(model.field_fits):
        fit = model.field_fits[key]
        rows.append({
            "lane": lane_label(model, fit.capture, fit.level_index),
            "capture": fit.capture,
            "level_index": fit.level_index,
            "page": fit.page,
            "n_certificates": fit.n_certificates,
            "tiles_yx": list(fit.tiles_yx),
            "block_tiles_yx": list(fit.block_tiles_yx),
            "planes": [{
                "plane": row.plane,
                "plane_name": row.plane_name,
                "fitted": row.fitted,
                "published": row.published,
                "refusal": row.refusal,
                "median_delta_dots": row.median_delta_dots,
                "n_sites": row.n_sites,
                "residual": row.residual,
                "support_tiles": row.support_tiles,
            } for row in fit.planes],
        })
    return rows


def build_report(model: DiagModel) -> dict:
    payload = status(model)
    payload["capture_facts"] = _capture_facts(model)
    payload["plane_fields"] = _field_facts(model)
    payload["ladder_isolation"] = ladder_isolation_advisory(model)
    payload["run_done"] = (None if model.run_done is None else {
        "status": model.run_done.status,
        "payload_sha256": model.run_done.payload_sha256,
        "n_bytes": model.run_done.n_bytes,
        "certified": model.run_done.certified})
    return payload


def write_report(path: Path, model: DiagModel) -> None:
    path.write_text(json.dumps(_jsonable(build_report(model)), indent=2,
                               sort_keys=True))
