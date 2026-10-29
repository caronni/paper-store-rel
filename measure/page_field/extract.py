#!/usr/bin/env python
"""Read an ARCHIVED holo3 fact snapshot without the receiver's class table.

    cd <repo>
    env/bin/python -m measure.page_field.extract self-check
    env/bin/python -m measure.page_field.extract extract FACTS.npz --out DIR
    env/bin/python -m measure.page_field.extract cross-check FACTS.npz

W2 re-keys ``PlaneField`` to (page, plane), so from W2 on
``holo.receiver.snapshot.read`` raises on every snapshot written before
it: the archived spines carry per-lane ``PlaneField`` nodes naming
fields the new class does not have, and there is no compatibility in
production by ruling (``docs/PAGE-FIELD-DESIGN.md`` §5).  The page-field
validation harness still needs those snapshots' placements and
certificates, and the per-lane fields themselves are plan §5's "before"
column, so this tool decodes the container itself -- a JSON spine
of tagged nodes plus one flat byte blob, ``src/holo/receiver/snapshot.py``
-- against its own class table.  The six classes the harness reads
become plain dicts of numpy arrays; every other node decodes to ``None``
and the arrays only it referenced are never materialised.  The extract
path imports nothing from ``holo``, so it cannot die with the schema;
the ``cross-check`` oracle does, inside its own function, and dies with
it by design.

KEPT past W6 (ruled 2026-09-08): the design's §5 throwaway clause bought
a tool that turned out to be the ONLY reader of sheet I's snapshot, which
was written on machine 4 before W2 (e037, main at ``74d7711``) and is the
corpus B3's supervised row still owes.  It stays until that replay runs.
Nothing under ``src/`` imports it and nothing may.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import lzma
import shutil
import tempfile
import time
import zipfile
from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
from pathlib import Path

import numpy as np

#: The families the harness reads.  ``Region`` is here because it is
#: nested inside ``CaptureSurvey.regions``; ``PlaneField`` because W2
#: re-keys that class and this becomes the only reader of the grids the
#: pre-W2 fitter published -- plan §5's "before" column, 6 of them on
#: sheet J and 23 on sheet H.  ``RunOpen`` because the identity gate
#: reads it (below).  ``PooledColorCtx``, ``CtxOutcome``, ``RegionCtx``
#: and ``LatticeSeed`` are the ones the harness has no use for and W2 is
#: free to re-key.
KEPT: frozenset[str] = frozenset(
    {"CaptureSurvey", "Region", "Window", "Placement", "PlaneField",
     "Certificate", "RunOpen"})

#: The event a run opens with, and the only record of WHICH FORMAT it
#: decoded under: ``data.RunOpen.format_id`` is the resolved ROW ID, and
#: the row id is the seed (``estimate.archived_seed``).  It is an EVENT,
#: not a durable fact -- ``snapshot.FAMILIES`` does not hold it, and
#: measured 2026-09-08 none of the five archives this harness reads
#: carries one -- so the walker above picks it up if a future snapshot
#: ever does, and until then it is read from the run's own
#: ``events.jsonl``, where every run writes it as line 1.
RUN_OPEN = "RunOpen"
CAPTURE_OPEN = "CaptureOpen"
EVENT_NAMES = ("events.jsonl", "events.jsonl.xz")

BLOB = "blob.npy"
META = "meta"
CHUNK = 1 << 22

ArrayTable = Sequence[Sequence]


def _spine(path: Path) -> dict:
    with np.load(path) as handle:
        return json.loads(bytes(handle[META]).decode())


def _convert(node: object, array: Callable[[int], object]) -> object:
    """One node of the spine, with ``array`` deciding what an array is.

    Called twice per file: once with a visitor that only records the
    indices a kept node reaches, then once with the materialised table.
    """
    if not isinstance(node, list):
        return node
    tag = node[0]
    if tag == "a":
        return array(node[1])
    if tag == "f":
        return Fraction(node[1], node[2])
    if tag == "t":
        return tuple(_convert(item, array) for item in node[1])
    if node[1] not in KEPT:
        return None
    return {name: _convert(value, array) for name, value in node[2]}


def wanted_arrays(spine: Mapping) -> set[int]:
    indices: set[int] = set()
    for node in spine["facts"]:
        _convert(node, indices.add)
    return indices


def _blob_arrays(path: Path, table: ArrayTable,
                 wanted: set[int]) -> dict[int, np.ndarray]:
    """The requested slices of the blob, decompressed once, in order.

    The blob is one DEFLATE member, so the offsets are not seekable; the
    stream is read through and the unwanted spans are discarded.
    """
    arrays: dict[int, np.ndarray] = {}
    with zipfile.ZipFile(path) as archive, archive.open(BLOB) as stream:
        major, _minor = np.lib.format.read_magic(stream)
        if major != 1:
            raise ValueError(f"{path}: blob is npy v{major}, expected v1")
        np.lib.format.read_array_header_1_0(stream)
        position = 0
        for index in sorted(wanted):
            start, length, kind, shape = table[index]
            if start < position:
                raise ValueError(
                    f"{path}: array {index} starts behind the stream")
            while position < start:
                skipped = stream.read(min(CHUNK, start - position))
                if not skipped:
                    raise ValueError(f"{path}: blob ends inside its table")
                position += len(skipped)
            raw = stream.read(length)
            if len(raw) != length:
                raise ValueError(f"{path}: blob ends inside array {index}")
            position += length
            arrays[index] = np.frombuffer(
                raw, dtype=np.dtype(kind)).reshape(shape)
    return arrays


def read_facts(path: Path) -> dict[str, list[dict]]:
    """The kept facts of one snapshot, by class name, in fold order."""
    spine = _spine(path)
    arrays = _blob_arrays(path, spine["arrays"], wanted_arrays(spine))
    facts: dict[str, list[dict]] = {name: [] for name in sorted(KEPT)}
    for node in spine["facts"]:
        name = node[1]
        if name in KEPT:
            facts[name].append(_convert(node, arrays.__getitem__))
    return facts


def _column(rows: Sequence[dict], field: str, dtype: np.dtype | type,
            tail: tuple[int, ...] = ()) -> np.ndarray:
    """One scalar or fixed-width field of many facts, as a column.

    The row shape is declared for the same reason ``_ragged`` declares
    its tail: with no rows there is nothing to read it off, and a
    (0,)-shaped column where the caller documented (n, 6) is a lie.
    """
    return np.array([row[field] for row in rows],
                    dtype).reshape((len(rows), *tail))


def _strings(rows: Sequence[dict], field: str) -> np.ndarray:
    return np.array([row[field] for row in rows], dtype=np.str_)


def _extents(rows: Sequence[dict]) -> np.ndarray:
    return np.array([row["window_id"][3] for row in rows],
                    np.int32).reshape((len(rows), 4))


def _ragged(rows: Sequence[dict], field: str, dtype: np.dtype | type,
            tail: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    """One array field of many facts, concatenated with its offsets.

    CONSUMES the field: sheet H's 7,725 placements carry 3.73 GB of
    ``local_cells_yx`` between them, so each source array is dropped as
    it is copied rather than held beside the concatenation.  The row
    shape is declared, not read off row zero: a run that certified
    nothing (e030's c2 sheet, e032's M281 cmy7) has no row zero.
    """
    lengths = np.array([row[field].shape[0] for row in rows], np.int64)
    offsets = np.concatenate((np.zeros(1, np.int64), np.cumsum(lengths)))
    flat = np.empty((int(offsets[-1]), *tail), dtype)
    info = np.iinfo(dtype) if np.issubdtype(dtype, np.integer) else None
    for start, row in zip(offsets, rows):
        chunk = row.pop(field)
        if info is not None and chunk.size and (
                int(chunk.max()) > info.max or int(chunk.min()) < info.min):
            raise ValueError(f"{field} does not fit {np.dtype(dtype)}")
        flat[start:start + chunk.shape[0]] = chunk
    return offsets, flat


def write_placements(rows: Sequence[dict], path: Path) -> None:
    """CONSUMES each row's ``local_cells_yx`` (``_ragged``): write once."""
    for row in rows:
        wid = row["window_id"]
        if (wid[0], wid[1], wid[2]) != (row["capture_id"], row["level_index"],
                                        row["region_index"]):
            raise ValueError(f"placement {wid} disagrees with its window id")
    offsets, cells = _ragged(rows, "local_cells_yx", np.int32, (2,))
    np.savez(path,
             capture_id=_strings(rows, "capture_id"),
             level_index=_column(rows, "level_index", np.int32),
             region_index=_column(rows, "region_index", np.int32),
             extent_cells=_extents(rows),
             patch_ordinal=_column(rows, "patch_ordinal", np.int64),
             page=_column(rows, "page", np.int32),
             rot_k=_column(rows, "rot_k", np.int32),
             page_origin_yx=_column(rows, "page_origin_yx", np.int64, (2,)),
             native_affine=_column(rows, "native_affine", np.float64, (6,)),
             pitch_px=_column(rows, "pitch_px", np.float64),
             cell_offsets=offsets,
             local_cells_yx=cells)


def write_certificates(rows: Sequence[dict], path: Path) -> None:
    """CONSUMES each row's ``user_bits`` (``_ragged``): write once."""
    offsets, bits = _ragged(rows, "user_bits", np.uint8, ())
    np.savez(path,
             page=_column(rows, "page", np.int32),
             ty=_column(rows, "ty", np.int32),
             tx=_column(rows, "tx", np.int32),
             stream_id=_strings(rows, "stream_id"),
             bit_offsets=offsets,
             user_bits=bits)


def _stack(rows: Sequence[dict], field: str,
           tail: tuple[int, ...]) -> np.ndarray:
    """One same-shaped array field of many facts, on one leading axis."""
    shapes = {row[field].shape for row in rows}
    if len(shapes) > 1:
        raise ValueError(f"{field} carries {len(shapes)} shapes: "
                         f"{sorted(shapes)}")
    if not rows:
        return np.zeros((0, *tail))
    return np.stack([row[field] for row in rows])


def write_plane_fields(rows: Sequence[dict], path: Path) -> None:
    """The fields the pre-W2 per-lane fitter published, grids and all.

    W2 re-keys the class, so ``snapshot.read`` stops decoding these
    nodes and this file is what is left of them: plan §5's "before"
    column wants the grids, not the medians already typed into it
    (measured: 287 KB for sheet J's six, 1.09 MB for sheet H's 23).
    """
    np.savez(path,
             capture_id=_strings(rows, "capture_id"),
             level_index=_column(rows, "level_index", np.int32),
             page=_column(rows, "page", np.int32),
             plane=_column(rows, "plane", np.int32),
             n_certificates=_column(rows, "n_certificates", np.int64),
             n_sites=_column(rows, "n_sites", np.int64),
             residual=_column(rows, "residual", np.float64),
             median_delta_dots=_column(rows, "median_delta_dots", np.float64),
             delta_dots_xy=_stack(rows, "delta_dots_xy", (0, 0, 2)),
             support=_stack(rows, "support", (0, 0)))


def _open_text(path: Path):
    return lzma.open(path, "rt") if path.suffix == ".xz" else path.open()


def events_head(path: Path) -> tuple[dict, tuple[str, ...]]:
    """A run's own ``RunOpen``, and the captures declared beside it.

    Every run writes ``RunOpen`` first and one ``CaptureOpen`` per
    declared capture directly after it (``engine._open``'s event order,
    dumped by ``operator._diag_products``), so this reads the head and
    stops at the first line that is neither -- sheet H's journal is
    209 MB and none of it past line 8 says anything about identity.  A
    journal that opens any other way is refused rather than searched.
    """
    opened: dict | None = None
    captures: list[str] = []
    with _open_text(path) as stream:
        for line in stream:
            event = json.loads(line)
            kind = str(event.get("type"))
            if opened is None:
                if kind != RUN_OPEN:
                    raise ValueError(
                        f"{path}: opens with {kind!r}, not {RUN_OPEN}")
                opened = event
            elif kind == CAPTURE_OPEN:
                captures.append(str(event["capture"]))
            else:
                break
    if opened is None:
        raise ValueError(f"{path}: no events")
    return opened, tuple(captures)


def sibling_events(facts_path: Path) -> Path | None:
    for name in EVENT_NAMES:
        candidate = facts_path.parent / name
        if candidate.is_file():
            return candidate
    return None


def run_identity(opens: Sequence[dict], surveys: Sequence[dict],
                 events: Path | None) -> dict | None:
    """The row id this snapshot's run opened with, and where it said so.

    ``None`` when nothing attests it -- a snapshot copied away from its
    run dir, which is how sheet I's and sheet J's arrived here from the
    machine 4 and machine 2.  `estimate.py` refuses that.  There is deliberately
    no way for the operator to type the identity in instead: a declared
    format reference is exactly what the gate exists to check, and the
    2026-09-02 re-key made the same reference mean two different seeds
    on either side of it.

    HOW STRONG EACH SOURCE IS, corrected 2026-09-08 (W7b review).  The
    snapshot's own ``RunOpen`` and the SIBLING journal are structural: a
    run dir's ``facts.npz`` and ``events.jsonl`` are written together by
    ``operator._diag_products`` at RunDone, so the sibling is that
    snapshot's run by construction.  ``--events`` is an ASSERTION the
    operator makes and this function cannot verify.  What it can check
    it checks -- a run re-declares every capture it resumes, so the
    snapshot's surveys must be a subset of the journal's
    ``CaptureOpen``s, which refuses a journal from another scan set --
    but a capture id is the scan's sha256, so two runs over the same
    scans declare the same captures whatever ``--format`` they declared,
    and that is the one case the gate exists for.  A snapshot that
    surveyed nothing gives the subset test no purchase at all and is
    refused rather than attested on a vacuous check.  What would close
    the rest is ``RunOpen`` in ``snapshot.FAMILIES``, which is a
    production change (the plan's W7b OWED list); until then a copied
    journal is checked by hand, as sheet I's was, by comparing its run
    dir's ``facts.npz`` sha256 with the snapshot's.
    """
    if opens:
        return {"format_id": str(opens[0]["format_id"]),
                "attested_by": "facts"}
    if events is None:
        return None
    opened, declared = events_head(events)
    if not surveys:
        raise ValueError(
            f"{events} cannot attest a snapshot that surveyed no capture: "
            "the only tie between a journal and a snapshot here is the "
            "capture set, and this one has none to compare")
    surveyed = {str(survey["capture_id"]) for survey in surveys}
    missing = sorted(surveyed - set(declared))
    if missing:
        raise ValueError(
            f"{events} opened {len(declared)} capture(s) and this snapshot "
            f"surveyed {len(missing)} it never opened ({missing[0][:12]}): "
            f"that journal is another run's")
    return {"format_id": str(opened["format_id"]),
            "attested_by": str(events)}


def _region_entry(region: dict) -> dict:
    return {"region_index": int(region["region_index"]),
            "origin_yx": [int(value) for value in region["origin_yx"]],
            "step_px": int(region["step_px"]),
            "extent_px": [int(value) for value in region["extent_px"]],
            "cells_shape": list(region["cells"].shape),
            "area_mm2": float(region["area_mm2"]),
            "median_tensor_score": float(region["median_tensor_score"])}


def write_captures(surveys: Sequence[dict], windows: Sequence[dict],
                   source: Path, identity: dict | None, path: Path) -> None:
    """The capture list, with the level indices the windows attest.

    A snapshot holds no ``levels_ppc`` and no capture shape: both live on
    ``data.Capture``, which the operator re-declares from argv on every
    run and which is deliberately not snapshotted.  What is here is the
    survey's own record -- pitch, and the regions it found -- plus the
    level indices the window plan actually used, and the identity the
    run opened with, which `estimate.py` gates the declared format on.
    """
    levels: dict[str, set[int]] = {}
    for window in windows:
        levels.setdefault(window["capture_id"], set()).add(
            int(window["level_index"]))
    entries = [
        {"capture_id": survey["capture_id"],
         "pitch_class": (None if survey["pitch_class"] is None
                         else str(survey["pitch_class"])),
         "pitch_px": (None if survey["pitch_px"] is None
                      else float(survey["pitch_px"])),
         "level_indices": sorted(levels.get(survey["capture_id"], ())),
         "regions": [_region_entry(region) for region in survey["regions"]]}
        for survey in surveys]
    path.write_text(json.dumps(
        {"source": str(source), "identity": identity, "captures": entries},
        indent=1))


def extract(path: Path, out: Path,
            events: Path | None = None) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    facts = read_facts(path)
    read_seconds = time.monotonic() - started
    identity = run_identity(
        facts[RUN_OPEN], facts["CaptureSurvey"],
        sibling_events(path) if events is None else events)
    write_captures(facts["CaptureSurvey"], facts["Window"], path, identity,
                   out / "captures.json")
    write_plane_fields(facts["PlaneField"], out / "plane_fields.npz")
    write_certificates(facts["Certificate"], out / "certificates.npz")
    write_placements(facts["Placement"], out / "placements.npz")
    return {"identity": identity,
            "captures": len(facts["CaptureSurvey"]),
            "windows": len(facts["Window"]),
            "placements": len(facts["Placement"]),
            "certificates": len(facts["Certificate"]),
            "plane_fields": len(facts["PlaneField"]),
            "read_seconds": round(read_seconds, 2),
            "total_seconds": round(time.monotonic() - started, 2)}


def _feed(digest: object, value: object) -> None:
    if isinstance(value, np.ndarray):
        digest.update(f"{value.dtype.str}{value.shape}".encode())
        digest.update(np.ascontiguousarray(value))
    elif isinstance(value, Mapping):
        for name in sorted(value):
            digest.update(name.encode())
            _feed(digest, value[name])
    elif isinstance(value, tuple):
        digest.update(b"(")
        for item in value:
            _feed(digest, item)
    else:
        digest.update(repr(value).encode())
    digest.update(b";")


def digest_facts(facts: Mapping[str, Sequence[Mapping]]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for name in sorted(facts):
        digest = hashlib.blake2b(digest_size=16)
        for fact in facts[name]:
            _feed(digest, fact)
        digests[name] = f"{len(facts[name])}:{digest.hexdigest()}"
    return digests


def _plain(value: object) -> object:
    """A fact tree of dataclasses as the tree of dicts this tool decodes."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain(getattr(value, field.name))
                for field in dataclasses.fields(value)}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def cross_check(path: Path) -> dict:
    """This decoder against ``holo.receiver.snapshot.read``, field by field.

    THE ORACLE IS PRE-W2 ONLY: it imports the receiver's class table, so
    it raises on an archived snapshot the moment W2 lands -- which is the
    reason the extract path above has its own.  The two sides are
    compared by digest rather than element by element so that sheet H's
    3.8 GB of arrays are held once, not twice.

    A field the archived spine does not carry (sheet J predates
    ``Placement.stood_affines``) exists on the oracle side as the class
    default and on this side not at all: it is reported, and the digests
    are taken over the fields the snapshot itself holds.
    """
    mine = read_facts(path)
    fields = {name: sorted({field for row in rows for field in row})
              for name, rows in mine.items()}
    digests = {"mine": digest_facts(mine)}
    del mine
    from holo.receiver import snapshot
    theirs: dict[str, list[dict]] = {name: [] for name in fields}
    defaults: dict[str, list[str]] = {}
    for fact in snapshot.read(path):
        name = type(fact).__name__
        if name not in KEPT:
            continue
        plain = _plain(fact)
        defaults[name] = sorted(set(plain) - set(fields[name]))
        theirs[name].append({field: plain[field] for field in fields[name]})
    digests["oracle"] = digest_facts(theirs)
    return {**digests,
            "defaults_only": {name: extra
                              for name, extra in defaults.items() if extra}}


def _pack(arrays: Sequence[np.ndarray]) -> tuple[list, np.ndarray]:
    """The writer's own packing, restated so the self-check needs no import."""
    table: list = []
    chunks: list[bytes] = []
    offset = 0
    for array in arrays:
        raw = np.ascontiguousarray(array).tobytes()
        table.append([offset, len(raw), array.dtype.str, list(array.shape)])
        chunks.append(raw)
        offset += len(raw)
    return table, np.frombuffer(b"".join(chunks), np.uint8)


def _synthetic(path: Path, opens: str | None = None) -> tuple[int, ...]:
    """An eight-node spine in the archived shape; returns the skipped indices.

    Two placements and two certificates: a one-row spine cannot tell a
    real cumsum from ``offsets = [0, total]``.  The ``LatticeSeed`` node
    is the one nothing keeps, and its array is what the skip pin looks
    for.  ``opens`` adds the ``RunOpen`` node no archive here carries,
    which is the identity gate's first source.
    """
    cells_a = np.array([[0, 0], [1, 2], [3, 4]], np.int64)
    cells_b = np.array([[5, 6], [7, 8]], np.int64)
    bits_a = np.array([1, 0, 1, 1], np.uint8)
    bits_b = np.array([0, 1, 0], np.uint8)
    region_cells = np.ones((2, 3), np.bool_)
    delta = np.arange(12, dtype=np.float64).reshape(2, 3, 2)
    support = np.ones((2, 3), np.float64)
    seed_rows = np.arange(4, dtype=np.int64)
    table, blob = _pack([region_cells, cells_a, bits_a, delta, support,
                         seed_rows, cells_b, bits_b])
    wid_a = ["t", ["cap", 0, 1, ["t", [2, 3, 4, 5]]]]
    wid_b = ["t", ["cap", 0, 1, ["t", [6, 7, 8, 9]]]]

    def _placement(wid: list, cells: int, ordinal: int, rot_k: int) -> list:
        return [
            ["window_id", wid], ["capture_id", "cap"], ["level_index", 0],
            ["region_index", 1], ["patch_ordinal", ordinal], ["page", 1],
            ["rot_k", rot_k], ["page_origin_yx", ["t", [16, 32]]],
            ["native_affine", ["t", [1.0, 0.0, 2.0, 0.0, 1.0, 3.0]]],
            ["pitch_px", 8.0], ["route", "place"],
            ["local_cells_yx", ["a", cells]], ["quality", -0.25],
            ["refine_basis", ["t", []]]]
    facts = [
        ["d", "CaptureSurvey", [
            ["capture_id", "cap"],
            ["regions", ["t", [["d", "Region", [
                ["capture_id", "cap"], ["region_index", 1],
                ["origin_yx", ["t", [7, 8]]], ["step_px", 9],
                ["cells", ["a", 0]], ["extent_px", ["t", [10, 11]]],
                ["area_mm2", 12.5], ["median_tensor_score", 0.5]]]]]],
            ["pitch_class", ["f", 3, 2]], ["pitch_px", 6.25]]],
        ["d", "Window", [
            ["window_id", wid_a], ["capture_id", "cap"], ["level_index", 0],
            ["region_index", 1], ["extent_cells", ["t", [2, 3, 4, 5]]],
            ["supported_cells", 6], ["depth", 1], ["lane_depth", 2],
            ["ordinal", 3]]],
        ["d", "Placement", _placement(wid_a, 1, 4, 3)],
        ["d", "Placement", _placement(wid_b, 6, 5, 1)],
        ["d", "LatticeSeed", [
            ["capture_id", "cap"], ["level_index", 0], ["region_index", 1],
            ["rows", ["a", 5]], ["support_cells", 7], ["window_ordinal", 3]]],
        ["d", "PlaneField", [
            ["capture_id", "cap"], ["level_index", 0], ["page", 1],
            ["plane", 2], ["delta_dots_xy", ["a", 3]],
            ["support", ["a", 4]], ["n_certificates", 5], ["n_sites", 6],
            ["residual", 0.1], ["median_delta_dots", 0.2]]],
        ["d", "Certificate", [
            ["page", 1], ["ty", 2], ["tx", 3], ["stream_id", "C"],
            ["user_bits", ["a", 2]], ["source", "scan"]]],
        ["d", "Certificate", [
            ["page", 1], ["ty", 2], ["tx", 4], ["stream_id", "M"],
            ["user_bits", ["a", 7]], ["source", "scan"]]]]
    if opens is not None:
        facts.append(["d", RUN_OPEN, [
            ["format_id", opens], ["pages", 1], ["tiles_yx", ["t", [1, 1]]],
            ["stream_ids", ["t", ["C", "M", "Y"]]], ["n_captures", 1],
            ["workers", 1], ["pitch_in", 0.0], ["display_id", opens]]])
    meta = np.frombuffer(
        json.dumps({"facts": facts, "arrays": table}).encode(), np.uint8)
    with open(path, "wb") as stream:
        np.savez_compressed(stream, meta=meta, blob=blob)
    return (5,)


def write_journal(path: Path, format_id: str,
                  captures: Sequence[str]) -> None:
    """A run journal in ``diag/report.write_events_jsonl``'s own shape.

    The trailing line is what the head reader stops at.  Shared with
    ``estimate.py``'s self-check, which pins the run route on one.
    """
    lines = [{"type": RUN_OPEN, "format_id": format_id, "pages": 1},
             *({"type": CAPTURE_OPEN, "capture": capture}
               for capture in captures),
             {"type": "WorkerSeated", "plugin": "place"}]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))


def refuses(action: Callable[[], object], why: str) -> None:
    """The self-checks' one assertion shape (`estimate.py` uses it too)."""
    try:
        action()
    except ValueError:
        return
    raise AssertionError(why)


def self_check(work: Path) -> None:
    # from empty: the identity block below asserts that a snapshot with
    # no sibling journal attests nothing, and a previous run of this
    # same check leaves the journal it wrote sitting beside it
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    path = work / "synthetic-facts.npz"
    skipped = _synthetic(path)
    spine = _spine(path)
    wanted = wanted_arrays(spine)
    assert not wanted & set(skipped), "a skipped node's array was materialised"
    assert wanted == {0, 1, 2, 3, 4, 6, 7}, wanted
    table = spine["arrays"]
    refuses(lambda: _blob_arrays(path, [table[1], table[0]], {0, 1}),
            "an array table whose offsets run backwards was decoded")
    facts = read_facts(path)
    assert {name: len(rows) for name, rows in facts.items()} == {
        "CaptureSurvey": 1, "Certificate": 2, "Placement": 2,
        "PlaneField": 1, "Region": 0, "RunOpen": 0,
        "Window": 1}, "Region is only ever nested"
    placement = facts["Placement"][0]
    assert placement["window_id"] == ("cap", 0, 1, (2, 3, 4, 5))
    assert placement["native_affine"] == (1.0, 0.0, 2.0, 0.0, 1.0, 3.0)
    assert np.array_equal(placement["local_cells_yx"],
                          [[0, 0], [1, 2], [3, 4]])
    survey = facts["CaptureSurvey"][0]
    assert survey["pitch_class"] == Fraction(3, 2)
    assert survey["regions"][0]["cells"].shape == (2, 3)
    field = facts["PlaneField"][0]
    assert field["delta_dots_xy"].shape == (2, 3, 2) and field["plane"] == 2
    refuses(lambda: write_placements([dict(placement, capture_id="other")],
                                     work / "refused.npz"),
            "a placement disagreeing with its window id was written")
    refuses(lambda: _ragged([{"cells": np.array([[2 ** 31, 0]], np.int64)}],
                            "cells", np.int32, (2,)),
            "int32 narrowing accepted an out-of-range cell")
    refuses(lambda: _stack([{"grid": np.zeros((2, 2))},
                            {"grid": np.zeros((3, 3))}], "grid", (0, 0)),
            "two tile grids of different shapes were stacked")
    counts = extract(path, work / "out")
    assert counts["placements"] == 2 and counts["certificates"] == 2
    assert counts["plane_fields"] == 1
    with np.load(work / "out" / "placements.npz") as held:
        assert np.array_equal(held["cell_offsets"], [0, 3, 5])
        assert np.array_equal(held["local_cells_yx"],
                              [[0, 0], [1, 2], [3, 4], [5, 6], [7, 8]])
        assert held["local_cells_yx"].dtype == np.int32
        assert np.array_equal(held["extent_cells"],
                              [[2, 3, 4, 5], [6, 7, 8, 9]])
        assert np.array_equal(held["native_affine"][0],
                              [1.0, 0.0, 2.0, 0.0, 1.0, 3.0])
        assert held["capture_id"][0] == "cap"
        assert np.array_equal(held["rot_k"], [3, 1])
    with np.load(work / "out" / "certificates.npz") as held:
        assert np.array_equal(held["bit_offsets"], [0, 4, 7])
        assert np.array_equal(held["user_bits"], [1, 0, 1, 1, 0, 1, 0])
        assert list(held["stream_id"]) == ["C", "M"]
    with np.load(work / "out" / "plane_fields.npz") as held:
        assert held["delta_dots_xy"].shape == (1, 2, 3, 2)
        assert held["support"].shape == (1, 2, 3)
        assert held["plane"][0] == 2 and held["median_delta_dots"][0] == 0.2
    captures = json.loads((work / "out" / "captures.json").read_text())
    entry = captures["captures"][0]
    assert entry["pitch_class"] == "3/2" and entry["level_indices"] == [0]
    assert entry["regions"][0]["cells_shape"] == [2, 3]

    # THE IDENTITY RECORD (`estimate.check_identity` is the gate that
    # reads it).  A snapshot with no RunOpen and no journal attests
    # nothing and says so; a sibling journal attests; a journal from
    # another run and a journal that does not open with RunOpen are
    # refused; and a snapshot's own RunOpen outranks any journal.
    assert captures["identity"] is None, captures["identity"]
    journal = work / "events.jsonl"
    write_journal(journal, "L:c2-cmy8-r0547@53x37", ("cap",))
    assert extract(path, work / "out")["identity"] == {
        "format_id": "L:c2-cmy8-r0547@53x37",
        "attested_by": str(journal)}, "the sibling journal was not read"
    foreign = work / "foreign.jsonl"
    write_journal(foreign, "L:c2-cmy8-r0547@53x37", ("elsewhere",))
    refuses(lambda: extract(path, work / "out", foreign),
            "another run's journal attested this snapshot")
    headless = work / "headless.jsonl"
    headless.write_text(
        json.dumps({"type": CAPTURE_OPEN, "capture": "cap"}) + "\n")
    refuses(lambda: extract(path, work / "out", headless),
            "a journal that does not open with RunOpen was read")
    refuses(lambda: run_identity([], [], journal),
            "a journal attested a snapshot with no capture to check it "
            "against")
    owned = work / "owned-facts.npz"
    _synthetic(owned, opens="L:c2-cmy8-r0700-p120-x1@3392x2368")
    assert extract(owned, work / "out")["identity"] == {
        "format_id": "L:c2-cmy8-r0700-p120-x1@3392x2368",
        "attested_by": "facts"}, "a snapshot's own RunOpen lost to a journal"
    empty = work / "empty"
    empty.mkdir(parents=True, exist_ok=True)
    write_placements([], empty / "placements.npz")
    write_certificates([], empty / "certificates.npz")
    write_plane_fields([], empty / "plane_fields.npz")
    with np.load(empty / "placements.npz") as held:
        assert np.array_equal(held["cell_offsets"], [0])
        assert held["local_cells_yx"].shape == (0, 2)
        assert held["native_affine"].shape == (0, 6)
        assert held["extent_cells"].shape == (0, 4)
    with np.load(empty / "certificates.npz") as held:
        assert np.array_equal(held["bit_offsets"], [0])
        assert held["user_bits"].shape == (0,)
    with np.load(empty / "plane_fields.npz") as held:
        assert held["delta_dots_xy"].shape == (0, 0, 0, 2)
    print("page_field.extract self-check OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("extract", help="write the harness's four files")
    run.add_argument("facts", type=Path)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--events", type=Path, default=None,
                     help="the run's own events.jsonl(.xz), for a snapshot "
                          "copied away from its run dir")
    check = sub.add_parser("cross-check", help="against snapshot.read (pre-W2)")
    check.add_argument("facts", type=Path)
    checker = sub.add_parser("self-check", help="pure, no corpus")
    checker.add_argument("--work", type=Path, default=None,
                         help="scratch directory (default: a fresh temp dir)")
    args = parser.parse_args()
    if args.command == "extract":
        print(json.dumps(extract(args.facts, args.out, args.events), indent=1))
    elif args.command == "cross-check":
        result = cross_check(args.facts)
        print(json.dumps(result, indent=1))
        if result["mine"] != result["oracle"]:
            raise SystemExit("cross-check FAILED")
        print("cross-check OK")
    else:
        work = args.work or Path(tempfile.mkdtemp(prefix="extract-self-"))
        print(f"self-check work dir: {work}")
        self_check(work)


if __name__ == "__main__":
    main()
