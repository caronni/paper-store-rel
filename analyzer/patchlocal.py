"""P1g — the patch filter's LOCAL5 training scope (W8 B3).

BLIND.  Nothing here may import :mod:`analyzer.truth`,
:mod:`analyzer.oracle` or :mod:`analyzer.score`.

WHY.  The measurement that produced MEAS §5b's 0.119 trained on WHOLE
certified edge tiles of the same lane — every in-tile cell of tiles 29
and 32 — and applied the filter to a dead tile with no label of its own.
A halo-48 footprint at tile 30 reaches 48 of tile 29's 64 columns and
cannot reach tile 32 at all, so the production estimator is strictly
poorer than the measured one.  This module is the estimator the
measurement used, blind: the 5x5 neighbourhood's OWN certified cargo,
read at the committed pose through the same sample grid, offered to
`patch.patch_score` as extra labelled rows.  It is a TRAIN-SCOPE knob
(`patch_train_scope="local5"`), not a default — S11 of APPROACHES §3
decides.

WHAT IT MAY SEE.  `unmix._sample_frame` lays every certificate a
NON-target tile holds plus that tile's furniture, and refuses the target
tile outright; the target's own cargo therefore never enters a training
set through this door, and `neighbourhood_tiles` excludes the target
tile as well.  Labels are the neighbour's own `known` bits, the state
comes from its siblings, and word sites are marked so the per-state fits
can drop them (ruling 11).

MEMORY (the review's blocker).  One memo entry per (lane, TILE), NOT per
target: a tile in the middle of a pass is in 24 targets' neighbourhoods
and is read once.  Each entry keeps at most
`PATCH_LOCAL_MAX_ROWS_PER_TILE` = 512 rows, chosen by `fold_hash` rank
so the choice is deterministic and stable across targets, as float32
features + bits + state + cells: 295 KB at 144 features, 1.2 MB at 576,
6.3 MB at the 3,072 features a 4800-dpi lane's WIDEST candidate geometry
asks for.  The store is an LRU under a lock bounded BY BYTES
(`PATCH_LOCAL_MAX_BYTES`, 512 MB per process) as well as by entry count
(`PATCH_LOCAL_MAX_ENTRIES` = 512), because the entry count alone stopped
being a memory bound when the harvest moved onto the walk's own geometry
(review 2026-09-06): 512 entries x 6.3 MB is 3.2 GB per worker.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from holo.receiver.plugins import color_model, color_sites

from . import calibrate as cal
from . import frame as frame_mod
from . import patch as patch_mod
from . import patchgrid
from . import sample as sample_mod
from . import statecal
from . import unmix as unmix_mod
from .types import Key, Lane, PLANE_OF, RunInputs

#: The neighbourhood radius: 2 tiles = the 5x5 block, 24 neighbours.
LOCAL_RADIUS_TILES: int = 2
#: Rows kept per (lane, tile) entry, by `fold_hash` rank.
PATCH_LOCAL_MAX_ROWS_PER_TILE: int = 512
#: Entries kept in the LRU store, per process.
PATCH_LOCAL_MAX_ENTRIES: int = 512
#: ... and the bound that actually holds when the harvest geometry is
#: wide: total resident bytes of the store's arrays, per process.  512 MB
#: is ~80 entries at a 4800-dpi lane's widest geometry (the 5x5
#: neighbourhood is 24 tiles, so three targets' worth) and every one of
#: the 512 at the narrow ones.
PATCH_LOCAL_MAX_BYTES: int = 512 * 1024 * 1024
#: Salts the row-cap ranking so it is independent of the fold split and
#: of the cross-fit halves.
LOCAL_ROW_SALT: int = 0x4C4F4341
_STORE_LOCK = threading.Lock()


@dataclass(frozen=True)
class _GridSpec:
    """What `patchgrid` reads off an axes bag — nothing else."""

    samples_per_cell: int
    window_cells: float


def _store(inputs: RunInputs) -> OrderedDict:
    store = inputs._cache.get("patch_local_labels")
    if store is None:
        store = OrderedDict()
        inputs._cache["patch_local_labels"] = store
    return store


def _entry_bytes(value: Any) -> int:
    """Resident bytes of one store entry.

    An entry is `harvest_tile`'s five-array tuple, or `()` for a tile
    that gave nothing; anything else weighs nothing here.
    """
    if not isinstance(value, tuple) or not value:
        return 0
    return int(sum(int(np.asarray(part).nbytes) for part in value))


def _remember(store: OrderedDict, cache_key: tuple, value: Any) -> None:
    """LRU insert under the shared lock, bounded by entries AND by bytes."""
    with _STORE_LOCK:
        store[cache_key] = value
        store.move_to_end(cache_key)
        total = sum(_entry_bytes(item) for item in store.values())
        while len(store) > PATCH_LOCAL_MAX_ENTRIES or (
                total > PATCH_LOCAL_MAX_BYTES and len(store) > 1):
            _key, dropped = store.popitem(last=False)
            total -= _entry_bytes(dropped)


def _recall(store: OrderedDict, cache_key: tuple) -> Any:
    with _STORE_LOCK:
        if cache_key not in store:
            return None
        store.move_to_end(cache_key)
        return store[cache_key]


def _capped(cells: np.ndarray, rows: np.ndarray) -> np.ndarray:
    """The `PATCH_LOCAL_MAX_ROWS_PER_TILE` rows of lowest `fold_hash`."""
    if rows.size <= PATCH_LOCAL_MAX_ROWS_PER_TILE:
        return rows
    draw = cal.fold_hash(cells[rows], LOCAL_ROW_SALT)
    order = np.argsort(draw, kind="stable")[:PATCH_LOCAL_MAX_ROWS_PER_TILE]
    return np.sort(rows[order])


def _cap_entry(entry: tuple[np.ndarray, ...] | None,
               ) -> tuple[np.ndarray, ...] | None:
    """Trim one entry to the row cap — the STORE's own bound.

    `harvest_tile` caps before it extracts (it is the cheaper place), but
    the resident bound is a property of what the store holds, so it is
    enforced here as well: whatever a harvest returns, an entry is at
    most `PATCH_LOCAL_MAX_ROWS_PER_TILE` rows wide.
    """
    if not entry:
        return entry
    rows = int(entry[1].size)
    if rows <= PATCH_LOCAL_MAX_ROWS_PER_TILE:
        return entry
    keep = _capped(np.asarray(entry[3], np.int64), np.arange(rows))
    return tuple(np.asarray(part)[keep] for part in entry)


def harvest_tile(inputs: RunInputs, certs: Mapping[Key, Any], lane: Lane,
                 page: int, tile_yx: tuple[int, int],
                 forbidden: tuple[int, int], plane: int,
                 axes: Mapping[str, Any],
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray,
                            np.ndarray, np.ndarray] | None:
    """One neighbour tile's labelled patches, or None if it gives none.

    Returns ``(features (m, F) float32, bits (m,), state (m,), cells
    (m, 2), word (m,))`` at the COMMITTED pose (this is a label source,
    not an arm: it does not search).

    `axes` is the WALK'S WIDEST geometry, not the spec's own (review
    2026-09-06).  The harvest runs before any population has chosen, so
    extracting at the inherited width meant every population that chose
    another one threw these rows away — silently, and for exactly the
    coreless third-layer population that prefers the wider window.  Cut
    once at the widest grid, and `patchcache.derive_block` slices each
    chosen candidate out of it.
    """
    n_ty, n_tx = int(tile_yx[0]), int(tile_yx[1])
    cell_dots = color_sites.cell_dots_of(inputs.row)
    fp = frame_mod.tile_footprint(inputs.row, int(page), n_ty, n_tx, 0,
                                  geometry=inputs.geometry)
    lfp = sample_mod.lane_footprint(lane, fp)
    if lfp is None or not np.any(lfp.observed):
        return None
    try:
        crops = sample_mod.open_crops(lane, lfp, bound_dots=0.0,
                                      cell_dots=cell_dots, keep_raw=True)
    except sample_mod.SampleError:
        return None
    read = sample_mod.read_rgb(crops, lfp, arm="patch-local")
    if read.refusal is not None:
        return None
    bits, known = unmix_mod._sample_frame(inputs, certs, fp, forbidden)
    cells = np.asarray(fp.page_cells_yx, np.int64)
    observed = np.asarray(lfp.observed, bool)
    labelled = np.asarray(known[:, plane], bool) & observed
    if not np.any(labelled):
        return None
    rows = _capped(cells, np.flatnonzero(labelled))
    grid_spec = _GridSpec(int(axes["samples_per_cell"]),
                          float(axes["window_cells"]))
    channels = tuple(int(c) for c in axes["channels"])
    features, inside = patchgrid.extract(
        crops, read.points_yx, read.linear_by_owner, lfp.owner_index,
        rows, patchgrid.grid_cells(grid_spec, float(crops.pitch_px_level)),
        channels)
    if str(axes["features"]) == "rings":
        features = patchgrid.ring_features(
            features, patchgrid.ring_matrix(grid_spec,
                                            float(crops.pitch_px_level)),
            len(channels))
    rows = rows[inside]
    features = features[inside]
    if not rows.size:
        return None
    #: ONE convention for the sibling state (B2 ruling 6): `statecal`'s,
    #: over the bare arrays `_sample_frame` hands back — this module used
    #: to re-implement its body inline (review 2026-09-06).
    state = statecal.sibling_state_of(bits, known, int(plane))
    _states, kinds = color_model.reference_states(
        inputs.row, inputs.geometry, int(page), cells)
    word = np.asarray(kinds, np.int8) == 0
    return (np.asarray(features, np.float32),
            np.asarray(bits[rows, plane], np.uint8), state[rows],
            cells[rows], word[rows])


def _flat_key(cells_yx: np.ndarray) -> np.ndarray:
    """One sortable int64 per page cell — ``y * 2**32 + x``."""
    cells = np.asarray(cells_yx, np.int64)
    if not cells.size:
        return np.zeros(0, np.int64)
    return (cells[:, 0] << np.int64(32)) + cells[:, 1]


def _outside(cells_yx: np.ndarray, forbidden_flat: np.ndarray) -> np.ndarray:
    """Which of `cells_yx` are NOT in the sorted `forbidden_flat` set."""
    flat = _flat_key(cells_yx)
    if not forbidden_flat.size or not flat.size:
        return np.ones(flat.size, bool)
    position = np.searchsorted(forbidden_flat, flat)
    hit = position < forbidden_flat.size
    hit[hit] = forbidden_flat[position[hit]] == flat[hit]
    return ~hit


def local_patch_labels(inputs: RunInputs, certs: Mapping[Key, Any],
                       key: Key, lane: Lane, spec: patch_mod.PatchSpec,
                       *, unmix_mode: str = "patch",
                       footprint_cells_yx: np.ndarray | None = None,
                       radius_tiles: int = LOCAL_RADIUS_TILES,
                       ) -> tuple[patch_mod.PatchLabels | None, dict]:
    """The 5x5 neighbourhood's certified cargo as patch training rows.

    One memo entry per (lane, stream, certificate set, page, tile, walk
    geometry) — the target tile is not part of the key, because the
    harvest does not depend on it: `neighbourhood_tiles` excludes the
    target and `_sample_frame` refuses it.  That is what makes the store
    bounded (the first draft keyed it by target and grew without bound).

    THE FOLD CONTRACT (DESIGN §4.8; review 2026-09-06).  A halo-48
    footprint reaches deep into its neighbours, so a neighbour cell can
    be BOTH a harvested training row here and a SEARCH- or SELECT-fold
    cell of the target footprint — measured at ~11 % of the footprint's
    select fold on r0850 geometry.  Every arm's `label_llr`, `select_arm`'s
    paired test and `platt`'s weights are then partly in-sample.  So
    every harvested row that lies INSIDE the target footprint is dropped
    at assembly (the footprint's own fit-fold rows are already the halo
    training set, so nothing that may be trained on is lost), and the
    count is published as `patch_local_rows_dropped_footprint`.  The drop
    is target-dependent and the memo is not: it happens here, after the
    per-tile entries are recalled.
    """
    # function-local: `arms` imports THIS module for the loader call, so a
    # module-level import here would close the cycle.
    from .arms import neighbourhood_tiles

    page, ty, tx, stream_id = key
    plane = PLANE_OF[str(stream_id)]
    token = frame_mod._certs_token(inputs, certs)
    tiles = neighbourhood_tiles(inputs, int(ty), int(tx), int(radius_tiles))
    _inherited, _auto, axes, _refused = patch_mod.walk_geometry(
        spec, str(unmix_mode))
    axes_id = (int(axes["samples_per_cell"]), float(axes["window_cells"]),
               tuple(int(c) for c in axes["channels"]),
               str(axes["features"]))
    store = _store(inputs)
    parts: list[tuple[np.ndarray, ...]] = []
    n_tiles = n_hit = 0
    for tile_yx in tiles:
        cache_key = (lane.lane_id, str(stream_id), token, int(page),
                     (int(tile_yx[0]), int(tile_yx[1])), axes_id)
        entry = _recall(store, cache_key)
        if entry is None:
            entry = harvest_tile(inputs, certs, lane, int(page), tile_yx,
                                 (int(ty), int(tx)), plane, axes)
            entry = _cap_entry(entry)
            _remember(store, cache_key, entry if entry is not None else ())
        else:
            n_hit += 1
        if not entry:
            continue
        parts.append(entry)
        n_tiles += 1
    detail = {"patch_local_tiles_read": int(n_tiles),
              "patch_local_tiles_offered": int(len(tiles)),
              "patch_local_memo_hits": int(n_hit)}
    if not parts:
        return None, {**detail, "patch_local_refused": "no_labelled_tile"}
    width = max(int(part[0].shape[1]) for part in parts)
    keep = [part for part in parts if int(part[0].shape[1]) == width]
    detail["patch_local_tiles_dropped"] = int(len(parts) - len(keep))
    cells = np.concatenate([part[3] for part in keep])
    forbidden = (np.sort(_flat_key(footprint_cells_yx))
                 if footprint_cells_yx is not None else np.zeros(0, np.int64))
    take = _outside(cells, forbidden)
    detail["patch_local_rows_dropped_footprint"] = int(
        np.count_nonzero(~take))
    if not np.any(take):
        return None, {**detail,
                      "patch_local_refused": "every_row_is_in_the_footprint"}
    labels = patch_mod.PatchLabels(
        features=np.concatenate([part[0] for part in keep])[take],
        bits=np.concatenate([part[1] for part in keep])[take],
        state=np.concatenate([part[2] for part in keep])[take],
        cells_yx=cells[take],
        word=np.concatenate([part[4] for part in keep])[take],
        n_tiles=int(len(keep)), axes=dict(axes), detail=detail)
    return labels, detail
