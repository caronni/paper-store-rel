"""The fact snapshot — the durable half of a run, dumped once at
RunDone and folded back through the ordinary store merge on `--resume`.

Durable is what the captures cannot cheaply hand back: the poses, the
certified bits, the fitted decisions.  Evidence arrays are NOT here —
they are a pure function of the rasters plus a pose, and the operator
re-declares the captures on every run, so calibrate regenerates them.
The bounded rework that follows is the whole design: done-geometry
refusals, certified-tile refusals and decision-cell no-op adoption
already stop the engine from redoing settled work.

`FAMILIES` is the include list; everything else the store folds is
either bulk evidence (WindowEvidence, ColorEvidenceRow,
ColorCtxPopulation), re-declared by the operator (Capture), scheduling
bookkeeping rather than a decision (PlaceOutcome), or carried by a
family already here (RefineOutcome adopts as a Placement; AttemptFact
is a memo over evidence this file deliberately does not hold).

The container is one DEFLATE-compressed npz: a JSON spine of tagged
nodes plus one flat byte blob for every array.  There is no version
stamp, no format guard and no integrity check — a snapshot is an
operator's own run product, and the operator is trusted with it.
Compression is a write-side choice only: `np.load` reads a stored and a
deflated npz the same way, so plain snapshots written before 2026-08-30
still resume.

Ruled 2026-08-30, knowingly: resuming with a capture DROPPED from the
declaration crashes with a bare exception (the survey fold looks its
capture up in a store that never heard of it, and raises KeyError).
The lead accepts that.  No guard is built: the operator re-declares the
captures on every run, dropping one is a typo the traceback names in
full, and the run has not written anything by then.
"""

from __future__ import annotations

import dataclasses
import json
from fractions import Fraction
from pathlib import Path

import numpy as np

from . import data
from .plugins import calibrate

NAME = "facts.npz"

FAMILIES: tuple[type, ...] = (
    data.CaptureSurvey,
    data.Window,
    data.LatticeSeed,
    data.Placement,
    calibrate.CtxOutcome,
    data.PlaneField,
    data.PooledColorCtx,
    data.Certificate,
)

_CLASSES: dict[str, type] = {
    cls.__name__: cls
    for cls in FAMILIES + (data.Region, data.RegionCtx)}


def collect(store: object) -> tuple[object, ...]:
    """The durable facts of a finished run, in fold order.

    Order is a dependency order, not a preference: surveys mint the
    frames and the window plan the placements need, windows carry the
    subdivided children the survey plan never re-mints, and
    certificates come last so the rows born by a certificate
    (`revisit`, `fields`) see the poses they enumerate.
    """
    facts: list[object] = []
    for capture_id in store.captures():
        survey = store.survey(capture_id)
        if survey is not None:
            facts.append(survey)
    wids = store.windows()
    facts.extend(store.window(wid) for wid in wids)
    regions = tuple(sorted({wid[:3] for wid in wids}))
    lanes = tuple(sorted({wid[:2] for wid in wids}))
    pages = sorted(store.live_pages())
    for region in regions:
        seed = store.lattice_seed(region)
        if seed is not None:
            facts.append(seed)
    facts.extend(store.placement(wid) for wid in store.placements())
    for region in regions:
        ctx = store.region_ctx(region)
        if ctx is not None:
            facts.append(calibrate.CtxOutcome(region, (), (), ctx))
    for capture_id, level_index in lanes:
        for page in pages:
            for field in store.lane_plane_fields(capture_id, level_index,
                                                 page):
                if field is not None:
                    facts.append(field)
    pooled: set[tuple[int, str]] = set()
    for capture_id, level_index in lanes:
        for page in pages:
            key = store.pooled_ctx_key(capture_id, level_index, page)
            if key in pooled:
                continue
            pooled.add(key)
            cell = store.pooled_color_ctx(key)
            if cell is not None:
                facts.append(cell)
    certificates = store.certificates()
    facts.extend(certificates[key] for key in sorted(certificates))
    return tuple(facts)


def _encode(value: object, arrays: list[np.ndarray]) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, np.generic):
        return _encode(value.item(), arrays)
    if isinstance(value, np.ndarray):
        arrays.append(value)
        return ["a", len(arrays) - 1]
    if isinstance(value, Fraction):
        return ["f", value.numerator, value.denominator]
    if isinstance(value, tuple):
        return ["t", [_encode(item, arrays) for item in value]]
    name = type(value).__name__
    if dataclasses.is_dataclass(value) and name in _CLASSES:
        return ["d", name,
                [[held.name, _encode(getattr(value, held.name), arrays)]
                 for held in dataclasses.fields(value)]]
    raise TypeError(f"snapshot cannot encode {name}")


def _decode(node: object, arrays: list[np.ndarray]) -> object:
    if not isinstance(node, list):
        return node
    if node[0] == "a":
        return arrays[node[1]]
    if node[0] == "f":
        return Fraction(node[1], node[2])
    if node[0] == "t":
        return tuple(_decode(item, arrays) for item in node[1])
    return _CLASSES[node[1]](
        **{name: _decode(item, arrays) for name, item in node[2]})


def _pack(arrays: list[np.ndarray]) -> tuple[list, np.ndarray]:
    table: list = []
    chunks: list[bytes] = []
    offset = 0
    for array in arrays:
        raw = np.ascontiguousarray(array).tobytes()
        table.append([offset, len(raw), array.dtype.str, list(array.shape)])
        chunks.append(raw)
        offset += len(raw)
    return table, np.frombuffer(b"".join(chunks), np.uint8)


def _unpack(table: list, blob: np.ndarray) -> list[np.ndarray]:
    raw = blob.tobytes()
    return [np.frombuffer(raw[start:start + length],
                          dtype=np.dtype(kind)).reshape(shape).copy()
            for start, length, kind, shape in table]


def write(path: Path, facts: tuple[object, ...]) -> None:
    arrays: list[np.ndarray] = []
    spine = {"facts": [_encode(fact, arrays) for fact in facts]}
    spine["arrays"], blob = _pack(arrays)
    meta = np.frombuffer(json.dumps(spine).encode(), np.uint8)
    with open(path, "wb") as stream:
        np.savez_compressed(stream, meta=meta, blob=blob)


def read(path: Path) -> tuple[object, ...]:
    with np.load(path) as handle:
        spine = json.loads(bytes(handle["meta"]).decode())
        arrays = _unpack(spine["arrays"], handle["blob"])
    return tuple(_decode(node, arrays) for node in spine["facts"])
