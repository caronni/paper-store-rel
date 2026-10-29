"""The durable products: the event journal and report.json.

Above `readout` — the report is the status dict plus the post-mortem
facts — and the only place in diag that writes files.

Written on every run, `--diag` or not (contract ruling 13-2,
00-contract.md:300; DIAG-DESIGN §5).
"""
from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from .model import DiagModel
from .readout import (capture_label, capture_selectors,
                      ladder_isolation_advisory, plane_name_of, status)


def _jsonable(value: object) -> object:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, np.ndarray):
        # Arrays reduce to shape+dtype and bytes to hex: the journal records
        # that an array rode the event, never its contents — events.jsonl is a
        # post-mortem index, not a data dump (pinned in test_h3_diag).
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
            # One unencodable event costs its own line, not the journal: these are
            # post-run products and no diag failure may change payload, status or
            # exit code (DIAG-DESIGN §0).  Contrast `operator._write_snapshot`, where
            # a fact the writer cannot encode is still fatal.
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
        fallback = model.pitch_fallbacks.get(capture_id)
        facts.append({
            "ordinal": ordinal,
            "capture": capture_id,
            "pitch_fallback": (None if fallback is None else {
                "declared_pitch_in": fallback.declared_pitch_in,
                "pitch_px": fallback.pitch_px,
                "n_regions": fallback.n_regions}),
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
    """Every page's solved field, in full — the post-mortem home for the
    numbers the status row only glances at, and the one place the
    residual energies PER (CAPTURE, PLANE) are written down (design
    §2.6, W8 R-F).  The status row names the loudest one; every one of
    them is here, beside each plane's own uncertainty and the evidence
    revision the page was solved at."""
    rows = []
    for page in sorted(model.field_solves):
        solved = model.field_solves[page]
        rows.append({
            "page": solved.page,
            "revision": solved.revision,
            "passes": solved.passes,
            "converged": solved.converged,
            "tiles_yx": list(solved.tiles_yx),
            "block_tiles_yx": list(solved.block_tiles_yx),
            "planes": [{
                "plane": row.plane,
                "plane_name": row.plane_name,
                "known": row.known,
                "held": row.held,
                "median_delta_dots": row.median_delta_dots,
                "median_uncertainty_dots": row.median_uncertainty_dots,
                "support_tiles": row.support_tiles,
                "n_observations": row.n_observations,
                "n_captures": row.n_captures,
            } for row in solved.planes],
            "residual_by_capture_plane": [{
                "capture": capture,
                "capture_label": capture_label(model, capture),
                "plane": plane,
                "plane_name": plane_name_of(solved, plane),
                "energy": energy,
                "expected": expected,
                "n_observations": count,
            } for capture, plane, energy, expected, count
                in solved.residual_by_capture_plane],
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
