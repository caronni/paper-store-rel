"""The run dir, typed — DESIGN §2, PLAN §1.2.

A finished holo3 decode leaves four things behind and this module turns
all four into one value:

* ``report.json`` — capture identity (id, dpi, channels, levels_ppc,
  shape), the declared pages and the close block (incl. its GF(2) rank,
  which DESIGN §1 reads rather than re-derives);
* ``events.jsonl`` — ``RunOpen`` carries the format ref and the printed
  pitch, ``TileOutcome`` the run's own mints (the withhold set of the
  positive control, §8);
* ``facts.npz`` — the flat fact tuple (``holo3.snapshot.read``): the
  accepted placements, the certificates, the plane fields and the pooled
  colour context;
* ``<capture12>/l{NN}-{r,g,b}.npy`` — the per-lane plane rasters, opened
  as mmaps and never read here.

``argv`` is provenance only [R].

Two deliberate refusals: the analyzer is cmy8-only and says so at
startup, and a lane whose raster files are absent is named, not skipped.

LANE POLICY.  ``finest-covering`` is a PER-TILE rule (DESIGN §4.2), so
``load_run`` exposes a lane for EVERY level that holds an accepted
placement and :func:`finest_covering` resolves the rule for one tile.
``rung_ppc`` reproduces production's shared-ppc pairing by filtering the
lane set down to one ppc.
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator, Sequence

import numpy as np

from holo3 import snapshot
from holo3.format import close as fmt_close
from holo3.format import identity, metadata
from holo3.plugins import calibrate, intake

from .types import CaptureFact, Key, Lane, LaneId, RunInputs

__all__ = ["InputsError", "load_run", "metadata_bit", "metadata_bits"]

RASTER_PLANES: tuple[str, ...] = ("r", "g", "b")
LANES_ALL = "all"
LANES_FINEST_COVERING = "finest-covering"
LANE_POLICIES: tuple[str, ...] = (LANES_ALL, LANES_FINEST_COVERING)

#: `pilots.TILE_CELLS`, restated so a census need not import the format.
TILE_CELLS = 64


class InputsError(RuntimeError):
    """The run dir does not say what the analyzer needs it to say."""


# --------------------------------------------------------------- readers

def read_report(run_dir: Path) -> dict:
    path = Path(run_dir) / "report.json"
    if not path.exists():
        raise InputsError(f"{path} is absent — not a finished run dir")
    return json.loads(path.read_text("utf-8"))


def iter_events(run_dir: Path) -> Iterator[dict]:
    """Stream ``events.jsonl`` line by line (it is megabytes)."""
    path = Path(run_dir) / "events.jsonl"
    if not path.exists():
        raise InputsError(f"{path} is absent")
    with open(path, "r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_run_open(run_dir: Path) -> dict:
    for event in iter_events(run_dir):
        if event.get("type") == "RunOpen":
            return event
    raise InputsError(f"{run_dir}/events.jsonl carries no RunOpen")


def read_tile_outcomes(run_dir: Path) -> dict[Key, list[dict]]:
    """Every ``TileOutcome`` of the run, grouped by key, in order.

    REQUIRED for `controls` and for the census column
    ``production_attempts``; optional otherwise (DESIGN §2).
    """
    out: dict[Key, list[dict]] = {}
    for event in iter_events(run_dir):
        if event.get("type") != "TileOutcome":
            continue
        key: Key = (int(event["page"]), int(event["ty"]), int(event["tx"]),
                    str(event["stream_id"]))
        out.setdefault(key, []).append(event)
    return out


def run_mint_keys(run_dir: Path) -> tuple[Key, ...]:
    """The run's OWN certified mints — the positive control's withhold set."""
    keys: list[Key] = []
    seen: set[Key] = set()
    for key, events in read_tile_outcomes(run_dir).items():
        if any(event.get("result") == "certified" for event in events):
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return tuple(sorted(keys))


# ----------------------------------------------------------------- lanes

def _levels_of(capture: CaptureFact, pitch_in: Fraction) -> tuple:
    levels = intake.build_levels(capture.dpi, pitch_in, capture.shape_px)
    declared = tuple(capture.levels_ppc)
    built = tuple(str(level.ppc) for level in levels)
    if declared and built != declared:
        raise InputsError(
            f"capture {capture.sha12}: report declares levels {declared} "
            f"but intake.build_levels gives {built}")
    return levels


def _open_rasters(run_dir: Path, capture: CaptureFact,
                  level_index: int) -> tuple[np.ndarray, ...]:
    if capture.channels != 3:
        raise InputsError(
            f"capture {capture.sha12} has {capture.channels} channel(s); "
            f"the analyzer is cmy8-only and needs RGB")
    plane_dir = Path(run_dir) / capture.sha12
    rasters: list[np.ndarray] = []
    for plane in RASTER_PLANES:
        path = intake.plane_path(plane_dir, level_index, plane)
        if not path.exists():
            raise InputsError(f"raster {path} is absent")
        rasters.append(np.load(path, mmap_mode="r"))
    return tuple(rasters)


def _build_lanes(run_dir: Path, captures: tuple[CaptureFact, ...],
                 placements: list, pitch_in: Fraction,
                 rung_ppc: Fraction | None) -> tuple[Lane, ...]:
    by_lane: dict[LaneId, list] = {}
    for placement in placements:
        by_lane.setdefault(
            (placement.capture_id, int(placement.level_index)),
            []).append(placement)
    facts = {capture.capture_id: capture for capture in captures}
    lanes: list[Lane] = []
    for lane_id in sorted(by_lane):
        capture_id, level_index = lane_id
        capture = facts.get(capture_id)
        if capture is None:
            raise InputsError(
                f"placement names capture {capture_id[:12]} which "
                f"report.json does not declare")
        levels = _levels_of(capture, pitch_in)
        if level_index >= len(levels):
            raise InputsError(
                f"capture {capture.sha12} has {len(levels)} levels; a "
                f"placement claims level {level_index}")
        level = levels[level_index]
        if rung_ppc is not None and Fraction(level.ppc) != rung_ppc:
            continue
        rows = sorted(by_lane[lane_id],
                      key=lambda item: (int(item.page), item.window_id))
        native = float(np.median([float(item.pitch_px) for item in rows]))
        lanes.append(Lane(
            capture_id=capture_id,
            ordinal=capture.ordinal,
            level_index=level_index,
            dpi=capture.dpi,
            ppc=Fraction(level.ppc),
            frame=Fraction(level.scale),
            pitch_px_native=native,
            pitch_px_level=native / float(level.scale),
            rasters=_open_rasters(run_dir, capture, level_index),
            placements=tuple(rows),
        ))
    return tuple(lanes)


# ------------------------------------------------------------- metadata

def _metadata_word(version: int, k: int) -> int:
    """The 24-bit state, re-assembled from what `decode_metadata` returns.

    `metadata.decode_metadata` hands back (version, k) rather than the
    word it solved for; the inverse of its own unpacking (metadata.py
    :96-101) is exact: bit 0 is the version, k's MSB..LSB are bits 1..18,
    the top 5 are known zero.
    """
    if not 0 <= k < metadata.MAX_K:
        raise InputsError(f"metadata k={k} is outside {metadata.K_BITS} bits")
    word = int(version) & 1
    for i in range(metadata.K_BITS):
        word |= ((k >> (metadata.K_BITS - 1 - i)) & 1) << (1 + i)
    return word


def metadata_max_index(row: Any) -> int:
    n = len(row.streams)
    return (metadata.max_equation_index(n) if row.pooled_fountain
            else metadata.MAX_COUNTER)


def metadata_bit(inputs: RunInputs, key: Key) -> int | None:
    """The tile-stream's metadata bit — ``user_bits[0]`` (DESIGN §1).

    BLIND, and that is why it lives HERE rather than in `truth.py`: the
    24-bit word comes from the run's OWN certified equations
    (`close.metadata_from_certificates`, trusted at rank 24 and >= 48
    distinct equations, resolved in `_metadata_state` above), and the bit
    is that word evaluated at this tile's equation — which is exactly
    what `holo3/format/close.py` inverts.  Returns ``None`` while the
    word is untrusted.

    It sat in `truth.py` until 2026-09-04 with a docstring explaining
    that it was blind anyway; the ruling that took truth out of the run
    made that arrangement untenable — a blind driver may not import the
    scoring module for any reason at all — so the helper moved to the
    module that owns the metadata word.
    """
    word = inputs.metadata_word
    if word is None:
        return None
    page, ty, tx, stream_id = key
    row = inputs.row
    counter = row.tile_counter(int(page), int(ty), int(tx))
    n_streams = len(row.streams)
    if row.pooled_fountain:
        index = metadata.equation_index(
            counter, inputs.stream_index(stream_id), n_streams)
        max_index = metadata.max_equation_index(n_streams)
    else:
        index = counter
        max_index = metadata.MAX_COUNTER
    table = metadata.coefficient_table(max_index)
    return int((int(table[index]) & int(word)).bit_count() & 1)


def metadata_bits(inputs: RunInputs,
                  keys: Sequence[Key]) -> dict[Key, int | None]:
    return {key: metadata_bit(inputs, key) for key in keys}


def _metadata_state(certificates, row) -> tuple[int | None, int | None,
                                                str, int | None]:
    try:
        version, k_total, state = fmt_close.metadata_from_certificates(
            certificates, row)
    except Exception as exc:                       # FountainIntegrityError
        return None, None, f"integrity_failure: {exc}", None
    if state != "ready" or k_total is None:
        return None, version, state, None
    k = (k_total // len(row.streams)) if row.pooled_fountain else k_total
    return _metadata_word(int(version), int(k)), version, state, k_total


# ------------------------------------------------------------- load_run

def load_run(run_dir: Path | str, *, lanes: str = LANES_FINEST_COVERING,
             rung_ppc: Fraction | int | str | None = None,
             format_ref: str | None = None) -> RunInputs:
    """Read a finished run dir into a `RunInputs` (PLAN §1.2).

    `format_ref` REPLACES the id the run's own ``RunOpen`` declares.  A
    format id is the AES seed, so a run dir whose id no longer mints the
    seed it was emitted with is unreadable without one: sheet J was
    emitted and decoded as the bare ``c2-cmy8-r0547@53x37``, which the
    canonical-identity merge now mints differently, and must be analyzed
    as ``L:c2-cmy8-r0547@53x37`` (PLAN §6).  Both ids are recorded in
    the provenance as ``format_ref_override``; the override must still
    resolve, and its pitch must still match the ``RunOpen``'s.
    """
    run_dir = Path(run_dir)
    if lanes not in LANE_POLICIES:
        raise InputsError(f"lane policy {lanes!r} not in {LANE_POLICIES}")
    rung = None if rung_ppc is None else Fraction(rung_ppc)

    report = read_report(run_dir)
    run_open = read_run_open(run_dir)
    declared_ref = str(run_open["format_id"])
    override = str(format_ref) if format_ref else None
    format_ref = override or declared_ref
    try:
        row = identity.resolve_format_ref(format_ref)
    except ValueError as error:
        raise InputsError(
            f"format ref {format_ref!r} does not resolve: {error}") from error
    if row.family is not identity.Family.CMY8:
        raise InputsError(
            f"{format_ref} is family {row.family.value}; the analyzer is "
            f"cmy8-only (DESIGN scope ruling)")
    pitch_in = Fraction(row.pitch_in)
    declared_pitch = float(run_open.get("pitch_in", pitch_in))
    if abs(float(pitch_in) - declared_pitch) > 1e-12:
        raise InputsError(
            f"RunOpen pitch_in {declared_pitch} != format pitch "
            f"{float(pitch_in)}")
    geometry = identity.build_site_geometry(row)

    captures = tuple(
        CaptureFact(
            capture_id=str(fact["capture"]),
            ordinal=int(fact["ordinal"]),
            dpi=float(fact["dpi"]),
            channels=int(fact["channels"]),
            levels_ppc=tuple(str(value) for value in fact["levels_ppc"]),
            shape_px=(int(fact["shape_yx"][0]), int(fact["shape_yx"][1])),
        )
        for fact in report["capture_facts"])

    facts = snapshot.read(run_dir / snapshot.NAME)
    placements: list = []
    certificates: dict[Key, Any] = {}
    plane_fields: dict[tuple[str, int, int, int], Any] = {}
    pooled_ctx: dict[tuple[int, str], Any] = {}
    lattice_seeds: list = []
    windows: dict[Any, Any] = {}
    surveys: dict[str, Any] = {}
    for fact in facts:
        name = type(fact).__name__
        if name == "Placement":
            placements.append(fact)
        elif name == "Certificate":
            certificates[(int(fact.page), int(fact.ty), int(fact.tx),
                          str(fact.stream_id))] = fact
        elif name == "PlaneField":
            plane_fields[(str(fact.capture_id), int(fact.level_index),
                          int(fact.page), int(fact.plane))] = fact
        elif name == "PooledColorCtx":
            pooled_ctx[(int(fact.page), str(fact.rung))] = fact
        elif name == "LatticeSeed":
            lattice_seeds.append(fact)
        elif name == "Window":
            windows[fact.window_id] = fact
        elif name == "CaptureSurvey":
            surveys[str(fact.capture_id)] = fact

    declared_pages = tuple(int(page) for page in report.get("pages", ()))
    placed_pages = {int(item.page) for item in placements}
    live = sorted(placed_pages & set(declared_pages)) if declared_pages \
        else sorted(placed_pages)
    if not live:
        raise InputsError(
            f"no page carries an accepted placement (placed "
            f"{sorted(placed_pages)}, declared {declared_pages[:8]}…)")

    lane_rows = _build_lanes(run_dir, captures, placements, pitch_in, rung)
    if not lane_rows:
        raise InputsError(
            f"no lane survives (rung_ppc={rung}); the run has placements "
            f"at ppc {sorted({str(p.level_index) for p in placements})}")

    word, version, state, k_total = _metadata_state(
        certificates.values(), row)

    close_report = dict(report.get("close") or {})
    blocks = close_report.get("blocks") or []
    rank_report = (int(blocks[0]["rank"])
                   if len(blocks) == 1 and blocks[0].get("rank") is not None
                   else None)  # an unsolved close reports rank null

    argv_path = run_dir / "argv"
    provenance = {
        "run_dir": str(run_dir),
        "argv": argv_path.read_text("utf-8").strip()
        if argv_path.exists() else None,
        "revision": report.get("revision"),
        "run_done": report.get("run_done"),
        "n_facts": len(facts),
        "n_placements": len(placements),
        "n_certificates": len(certificates),
    }
    if override is not None:
        provenance["format_ref_override"] = {
            "run_open": declared_ref, "used": override}
    return RunInputs(
        run_dir=run_dir,
        format_ref=format_ref,
        row=row,
        geometry=geometry,
        pitch_in=pitch_in,
        tiles_yx=tuple(row.tiles_yx),
        cells_yx=tuple(row.cells_yx),
        live_pages=tuple(live),
        declared_pages=declared_pages,
        captures=captures,
        lanes=lane_rows,
        lane_policy=lanes,
        rung_ppc=rung,
        certificates=certificates,
        plane_fields=plane_fields,
        pooled_ctx=pooled_ctx,
        lattice_seeds=tuple(lattice_seeds),
        windows=windows,
        surveys=surveys,
        metadata_word=word,
        metadata_version=version,
        metadata_state=state,
        k_total=k_total,
        rank_report=rank_report,
        close_report=close_report,
        provenance=provenance,
    )


# ----------------------------------------------------------- coverage

def _placement_page_cells(inputs: RunInputs, placement: Any) -> np.ndarray:
    extent = placement.window_id[3]
    shape = (int(extent[2]) - int(extent[0]),
             int(extent[3]) - int(extent[1]))
    return calibrate.window_page_cells(placement, shape, inputs.cells_yx)


def lane_tile_coverage(inputs: RunInputs, lane_id: LaneId,
                       page: int) -> np.ndarray:
    """(tiles_y, tiles_x) count of DISTINCT page cells this lane owns.

    Cells are de-duplicated across the lane's placements first — two
    windows overlapping the same tile must not read as double coverage.
    """
    cache = inputs._cache.setdefault("lane_tile_coverage", {})
    hit = cache.get((lane_id, page))
    if hit is not None:
        return hit
    lane = inputs.lane(lane_id)
    height, width = inputs.cells_yx
    seen = np.zeros(height * width, dtype=bool)
    for placement in lane.placements:
        if int(placement.page) != int(page):
            continue
        cells = _placement_page_cells(inputs, placement)
        if cells.size:
            seen[cells[:, 0] * width + cells[:, 1]] = True
    flat = np.flatnonzero(seen)
    tiles_y, tiles_x = inputs.tiles_yx
    counts = np.zeros(tiles_y * tiles_x, dtype=np.int64)
    if flat.size:
        cy, cx = np.divmod(flat, width)
        codes = (cy // TILE_CELLS) * tiles_x + (cx // TILE_CELLS)
        counts += np.bincount(codes, minlength=tiles_y * tiles_x)
    counts = counts.reshape(tiles_y, tiles_x)
    counts.setflags(write=False)
    cache[(lane_id, page)] = counts
    return counts


def page_tile_coverage(inputs: RunInputs, page: int) -> np.ndarray:
    """(tiles_y, tiles_x) count of page cells covered by SOME lane."""
    cache = inputs._cache.setdefault("page_tile_coverage", {})
    hit = cache.get(page)
    if hit is not None:
        return hit
    height, width = inputs.cells_yx
    seen = np.zeros(height * width, dtype=bool)
    for lane in inputs.lanes:
        for placement in lane.placements:
            if int(placement.page) != int(page):
                continue
            cells = _placement_page_cells(inputs, placement)
            if cells.size:
                seen[cells[:, 0] * width + cells[:, 1]] = True
    flat = np.flatnonzero(seen)
    tiles_y, tiles_x = inputs.tiles_yx
    counts = np.zeros(tiles_y * tiles_x, dtype=np.int64)
    if flat.size:
        cy, cx = np.divmod(flat, width)
        codes = (cy // TILE_CELLS) * tiles_x + (cx // TILE_CELLS)
        counts += np.bincount(codes, minlength=tiles_y * tiles_x)
    counts = counts.reshape(tiles_y, tiles_x)
    counts.setflags(write=False)
    cache[page] = counts
    return counts


def finest_covering(inputs: RunInputs, page: int, ty: int, tx: int, *,
                    cover_fraction: float = 1.0,
                    fallback: bool = True) -> tuple[LaneId, ...]:
    """The `finest-covering` lane set for ONE tile (DESIGN §4.2).

    Per capture, the FINEST level (largest ppc) whose accepted placements
    cover at least `cover_fraction` of the tile's 64x64 cells.  A capture
    whose every level falls short contributes no lane — the naive
    "finest" would silently drop the tile instead (the 4800 capture's
    finest level covers few tiles on sheet I).

    `fallback` is DESIGN §4.2's second clause, moved here in W1d so the
    census and the reader agree by construction (it lived in
    `sample.lanes_for_tile` at W1b, PLAN §6): when no level of a capture
    reaches the fraction, that capture still contributes the level with
    the LARGEST NON-ZERO coverage — partial coverage is evidence, and
    the observed mask carries the rest, so a tile never has zero lanes
    while any level sees it.  Pass `fallback=False` for the strict rule
    (`sample.fallback_captures` asks for exactly that, to name the
    captures the fallback rescued).
    """
    need = cover_fraction * TILE_CELLS * TILE_CELLS
    best: dict[str, tuple[Fraction, LaneId]] = {}
    partial: dict[str, tuple[int, Fraction, LaneId]] = {}
    for lane in inputs.lanes:
        counts = int(lane_tile_coverage(inputs, lane.lane_id, page)[ty, tx])
        if counts >= need:
            current = best.get(lane.capture_id)
            if current is None or lane.ppc > current[0]:
                best[lane.capture_id] = (lane.ppc, lane.lane_id)
        elif fallback and counts > 0:
            seen = partial.get(lane.capture_id)
            if seen is None or (counts, lane.ppc) > (seen[0], seen[1]):
                partial[lane.capture_id] = (counts, lane.ppc, lane.lane_id)
    chosen: dict[str, LaneId] = {
        capture: best[capture][1] for capture in best}
    for capture, entry in partial.items():
        chosen.setdefault(capture, entry[2])
    order = {lane.lane_id: index for index, lane in enumerate(inputs.lanes)}
    return tuple(sorted((chosen[capture] for capture in sorted(chosen)),
                        key=order.__getitem__))
