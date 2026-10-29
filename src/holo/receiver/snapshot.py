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
still resume.  Array WIDTH is the same kind of choice: the spine records
each array's dtype and the reader restores it, so a snapshot written at
a width this code no longer mints reads back at the width it was written
(`data.Placement.local_cells_yx`, int64 before 2026-09-13).

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

#: AttemptFact is excluded deliberately: a replayed attempt landing
#: ahead of its evidence orphans its retry row (lean-resume ruling,
#: 2026-08-31; pinned).
FAMILIES: tuple[type, ...] = (
    data.CaptureSurvey,
    data.Window,
    data.LatticeSeed,
    data.Placement,
    calibrate.CtxOutcome,
    data.PlaneField,
    data.PooledColorCtx,
    data.Certificate,
    data.EvidenceRevision,
)

_CLASSES: dict[str, type] = {
    cls.__name__: cls
    for cls in FAMILIES + (data.Region, data.RegionCtx)}

#: Fields a family no longer carries but the WIRE still does, at their
#: old positions and always empty: `CtxOutcome` lost its window rows
#: 2026-10-03 (the store corrects the rows standing at merge), and a
#: snapshot written on either side of that change must read on the
#: other -- `collect` never wrote anything but `()` there.
_WIRE_EMPTY_FIELDS: dict[str, tuple[tuple[int, str], ...]] = {
    "CtxOutcome": ((1, "inputs"), (2, "outputs")),
}


def collect(store: object) -> tuple[object, ...]:
    """The durable facts of a finished run, in fold order.

    Order is a dependency order, not a preference: surveys mint the
    frames and the window plan the placements need, windows carry the
    subdivided children the survey plan never re-mints, and
    certificates come last so the rows born by a certificate
    (`fields.collect`) see the poses they enumerate.

    `FieldObservations` is deliberately absent: it is derived from the
    placements, the certificates and the rasters, all three of which a
    resume re-declares, so the collection re-arms and re-measures while
    the page's standing `PlaneField` is folded back ahead of it (I10).
    Its ORDINAL is not derivable that way, so it is carried: one
    `EvidenceRevision` per capture-page (design §2.7).
    """
    facts: list[object] = []
    for capture_id in store.captures():
        survey = store.survey(capture_id)
        if survey is not None:
            facts.append(survey)
    wids = store.windows()
    # PARENTS BEFORE CHILDREN, by depth: a child Window carries its
    # parent's id and the window fold links both ends of the relation,
    # which it can only do once the parent's state exists.  Sorting by
    # the window id alone puts a quarter's extent AHEAD of the extent it
    # is a quarter of.
    facts.extend(store.window(wid) for wid in
                 sorted(wids, key=lambda wid: store.window(wid).depth))
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
            facts.append(calibrate.CtxOutcome(region, ctx))
    for page in pages:
        for field in store.page_plane_fields(page):
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
    # Last, because the fold takes the HIGHER of the restored number and
    # whatever the replayed placements and certificates counted on their
    # way past: the revision counts events, and a replay sees only the
    # facts those events left behind (I12).
    for capture_id in store.captures():
        for page in pages:
            revision = store.evidence_revision(capture_id, page)
            if revision:
                facts.append(data.EvidenceRevision(
                    capture_id=capture_id, page=page, revision=revision))
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
        fields = [[held.name, _encode(getattr(value, held.name), arrays)]
                  for held in dataclasses.fields(value)]
        for position, wire_name in _WIRE_EMPTY_FIELDS.get(name, ()):
            fields.insert(position, [wire_name, ["t", []]])
        return ["d", name, fields]
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
    wire_only = {wire_name for _position, wire_name
                 in _WIRE_EMPTY_FIELDS.get(node[1], ())}
    held: dict[str, object] = {}
    for name, item in node[2]:
        value = _decode(item, arrays)
        if name in wire_only:
            if value != ():
                raise ValueError(
                    f"snapshot: {node[1]}.{name} is a retired wire field "
                    f"and must be empty")
            continue
        held[name] = value
    return _CLASSES[node[1]](**held)


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
