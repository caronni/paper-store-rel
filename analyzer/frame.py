"""The footprint and its known bits — DESIGN §4.3 (half) and §4.5.

BLIND.  Nothing here may import :mod:`analyzer.truth` or
:mod:`analyzer.oracle`: every bit this module lays down comes from the
FORMAT (word and dust furniture, which is a pure function of the seed and
the tile counter) or from a CERTIFICATE the run already earned.  A test
may compare the result to the emitted field; the instrument may not.

Two objects, deliberately separate (DESIGN §4.3):

* :class:`~analyzer.types.TileFootprint` — lane-independent.  The 64x64
  cells of one tile plus a halo, clipped to the page, in row-major page
  order, with the in-tile and cargo masks.
* :class:`~analyzer.types.KnownFrame` — the bits and the known mask over
  exactly those cells.

THE TARGET-KEY EXCLUSION is the whole point of the second object.  The
projection cache in `residue.py` (`inputs._cache['projection_page']`) is
TARGET-INCLUSIVE: it lays every certified stream's own payload, so a
frame cut out of it would hand a parity-sample target its own answer.
This module therefore calls `color_sites.certified_projection` per target
with a certificate mapping the target key is hidden from, and asserts the
result: ``known[in_tile & cargo, target_plane].sum() == 0``.  A failure
is a RUN ABORT, not a warning.

The one deliberate exception is the METADATA CELL.  `user_bits[0]` of the
target stream is knowable without the target's certificate — the 24-bit
metadata word comes from OTHER tiles' certificates (`close.
metadata_from_certificates`) — so its printed cell is a legitimate known
bit of the target plane inside the target tile.  It is injected AFTER the
assertion and its footprint row is reported as `metadata_cell`; the
assertion therefore means "no certificate of the target leaked", which is
what it is for.

MEMO.  `known_frame` memoises certified projections per CERTIFICATE
MAPPING: a monotone token per mapping (`_certs_token`), and one memo dict
per token keyed by ``(page, ty, tx, excluded_key)``.  Every tile but the
target's shares the ``None`` entry, so the memo is per-target where it
must be and bounded everywhere else.  The token is what makes
`--withhold` (DESIGN §8) real: two calls with the SAME footprint and
target but DIFFERENT certificate mappings must not share a projection, or
the withheld certificates come straight back out of the cache.  Tokens
are drawn under a lock and NEVER recycled, so no two mappings can ever
alias — see `_certs_token`.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping as AbcMapping
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

import numpy as np

from holo.receiver.format import identity, keystream, tile_codec
from holo.receiver.plugins import color_model, color_sites
from holo.receiver.plugins.tiles import stream_fact

from .residue import discriminating_mask
from .types import (Key, KnownFrame, PLANE_OF, RunInputs, STREAMS,
                    TileFootprint)

#: `pilots.TILE_CELLS`, restated (inputs.py does the same).
TILE_CELLS = 64

_GEOMETRY_MEMO: dict[str, Any] = {}


class FrameError(RuntimeError):
    """The known-bit frame is not what the format says it must be."""


def geometry_of(row: Any) -> Any:
    """`identity.build_site_geometry(row)`, memoised by `row_id`."""
    row_id = str(row.row_id)
    hit = _GEOMETRY_MEMO.get(row_id)
    if hit is None:
        hit = identity.build_site_geometry(row)
        _GEOMETRY_MEMO[row_id] = hit
    return hit


class HaloError(ValueError):
    """A `--halo-cells` value this module will not turn into a halo."""


def parse_halo_cells(value: Any) -> dict[str, int]:
    """`--halo-cells`: a bare width, or a PER-PLANE one (2026-09-07).

    `48` keeps today's meaning — every plane — and `C=48,M=48,Y=32` names
    them.  The named spelling must name ALL THREE: a partial one would
    take the rest from whatever the profile happened to say, and the run
    set this repair exists for is exactly the case a reader must be able
    to diff.  X1's `wide-halo` profile is C 48 / M 48 / Y 32 while
    `--halo-cells 48` sets 48/48/48 — inert on a C-only target list (the
    halo is looked up per stream) but NOT inert for a Y-plane or
    mixed-stream re-run, which is what HALO-CHANNEL-2026-09-07 §1 records
    and §4.5 repairs.

    The parser lives here because `frame` already owns what a halo IS
    (`tile_footprint`); `types` is at its line cap and cannot import
    this module anyway.
    """
    if isinstance(value, Mapping):
        given = {str(k).strip().upper(): int(v) for k, v in value.items()}
    else:
        text = str(value).strip()
        if not text:
            raise HaloError("--halo-cells is empty")
        if "=" not in text:
            try:
                width = int(text)
            except ValueError as error:
                raise HaloError(
                    f"--halo-cells {text!r} is neither a width nor a "
                    f"per-plane spelling like C=48,M=48,Y=32") from error
            given = {name: width for name in STREAMS}
        else:
            given = {}
            for item in text.split(","):
                name, separator, width = item.partition("=")
                if not separator:
                    raise HaloError(
                        f"--halo-cells {item!r} wants PLANE=WIDTH")
                try:
                    given[name.strip().upper()] = int(width)
                except ValueError as error:
                    raise HaloError(
                        f"--halo-cells {item!r} has no width") from error
    unknown = sorted(set(given) - set(STREAMS))
    if unknown:
        raise HaloError(f"--halo-cells names {unknown}, not one of "
                        f"{list(STREAMS)}")
    missing = [name for name in STREAMS if name not in given]
    if missing:
        raise HaloError(f"--halo-cells must name every plane; {missing} "
                        f"missing (a bare width sets all three)")
    if any(width < 0 for width in given.values()):
        raise HaloError("--halo-cells must not be negative")
    return {name: int(given[name]) for name in STREAMS}


# ------------------------------------------------------------ footprint

def tile_footprint(row: Any, page: int, ty: int, tx: int,
                   halo_cells: int, *,
                   geometry: Any = None) -> TileFootprint:
    """The tile's cells plus `halo_cells` of halo, clipped to the page.

    `geometry` is optional only to keep PLAN §1.2's signature; it is
    memoised per format row when absent.  Cells come out in ROW-MAJOR
    page order, which `sample.lane_footprint` relies on (it locates a
    window's cells by `searchsorted` on the flat page key).
    """
    geometry = geometry_of(row) if geometry is None else geometry
    cells_y, cells_x = row.cells_yx
    halo = max(0, int(halo_cells))
    y0 = max(0, ty * TILE_CELLS - halo)
    y1 = min(cells_y, (ty + 1) * TILE_CELLS + halo)
    x0 = max(0, tx * TILE_CELLS - halo)
    x1 = min(cells_x, (tx + 1) * TILE_CELLS + halo)
    if y0 >= y1 or x0 >= x1:
        raise FrameError(
            f"tile ({ty}, {tx}) is outside a {cells_y}x{cells_x} page")
    ys = np.arange(y0, y1, dtype=np.int64)
    xs = np.arange(x0, x1, dtype=np.int64)
    grid_y, grid_x = np.meshgrid(ys, xs, indexing="ij")
    cells = np.stack((grid_y.ravel(), grid_x.ravel()), axis=1)
    in_tile = ((cells[:, 0] >= ty * TILE_CELLS)
               & (cells[:, 0] < (ty + 1) * TILE_CELLS)
               & (cells[:, 1] >= tx * TILE_CELLS)
               & (cells[:, 1] < (tx + 1) * TILE_CELLS))
    cargo = np.zeros(cells.shape[0], np.bool_)
    cargo[color_sites.cargo_row_indices(geometry, cells)] = True
    for array in (cells, in_tile, cargo):
        array.setflags(write=False)
    return TileFootprint(
        page=int(page), ty=int(ty), tx=int(tx), halo_cells=halo,
        page_cells_yx=cells, in_tile=in_tile, cargo=cargo,
        page_shape_cells_yx=(int(cells_y), int(cells_x)))


def footprint_tiles(fp: TileFootprint) -> tuple[tuple[int, int], ...]:
    """Every (ty, tx) the footprint touches, target tile included."""
    cells = fp.page_cells_yx
    codes = np.unique((cells[:, 0] // TILE_CELLS) * (1 << 20)
                      + (cells[:, 1] // TILE_CELLS))
    return tuple((int(code >> 20), int(code & ((1 << 20) - 1)))
                 for code in codes.tolist())


# --------------------------------------------------- certificate views

@dataclass(frozen=True)
class _BitsOnly:
    """What `certified_projection` reads off a certificate."""

    user_bits: np.ndarray


def _as_certificate(value: Any) -> Any:
    if hasattr(value, "user_bits"):
        return value
    return _BitsOnly(np.asarray(value, np.uint8))


class _WithoutKey(AbcMapping):
    """`certs` with ONE key hidden — the target-key exclusion, cheaply.

    Copying a 5,883-entry dict per target would cost more than the
    projection it feeds; `certified_projection` only asks `in` and `[]`,
    but the full Mapping protocol is implemented so a future caller that
    iterates cannot be surprised.
    """

    def __init__(self, base: Mapping[Key, Any], hidden: Key | None):
        self._base = base
        self._hidden = hidden

    def __getitem__(self, key: Key) -> Any:
        if self._hidden is not None and key == self._hidden:
            raise KeyError(key)
        return _as_certificate(self._base[key])

    def __contains__(self, key: object) -> bool:
        if self._hidden is not None and key == self._hidden:
            return False
        return key in self._base

    def __iter__(self) -> Iterator[Key]:
        for key in self._base:
            if self._hidden is None or key != self._hidden:
                yield key

    def __len__(self) -> int:
        n = len(self._base)
        if self._hidden is not None and self._hidden in self._base:
            n -= 1
        return n


#: How many certificate mappings keep a LIVE projection memo.  Tokens are
#: never recycled (see `_certs_token`); this bounds only how much cached
#: work is retained — the driver uses one full set per generation plus a
#: handful of withheld variants, and an evicted mapping still gets
#: CORRECT frames, only a cold memo.
_MAX_CERT_SETS = 8

#: Guards the creation of the per-`RunInputs` registry itself.  Everything
#: after that is guarded by the registry's own lock.
_REGISTRY_LOCK = threading.Lock()


def _registry(inputs: RunInputs) -> dict:
    registry = inputs._cache.get("frame_certs_registry")
    if registry is None:
        with _REGISTRY_LOCK:
            registry = inputs._cache.get("frame_certs_registry")
            if registry is None:
                registry = {"lock": threading.Lock(), "by_id": {},
                            "memo": {}, "order": [], "next_token": 0}
                inputs._cache["frame_certs_registry"] = registry
    return registry


def _certs_token(inputs: RunInputs, certs: Mapping[Key, Any]) -> int:
    """A MONOTONE token for THIS certificate mapping (DESIGN §8).

    The projection memo must not hand a `--withhold` frame a projection
    computed from the full certificate set: the withheld certificates
    would come back through the cache and the positive control would
    measure nothing.  Mappings are not hashable, and `id()` alone is
    unsafe because a dead object's id is reused — so the registry holds a
    STRONG reference to every mapping it has tokenised, which is what
    makes `id()` unique for as long as the token exists.

    THE COUNTER NEVER RESETS (W3).  The previous spelling cleared the
    whole registry at `_MAX_CERT_SETS` and handed out token 0 again; on
    threads that ALIASES — one worker's fresh mapping takes the token
    another worker's live mapping is still writing memo entries under,
    and a withheld certificate comes straight back out of the cache.
    Tokens are drawn from a monotone counter under a lock instead, and
    only the CACHED WORK is bounded: the oldest mapping's memo (and its
    strong reference) is dropped, its token is retired for good, and if
    that mapping is used again it is given a NEW token and a cold memo.
    """
    registry = _registry(inputs)
    with registry["lock"]:
        entry = registry["by_id"].get(id(certs))
        if entry is not None:
            return int(entry[0])
        token = int(registry["next_token"])
        registry["next_token"] = token + 1
        registry["by_id"][id(certs)] = (token, certs)
        registry["memo"][token] = {}
        registry["order"].append((token, id(certs)))
        while len(registry["order"]) > _MAX_CERT_SETS:
            old_token, old_id = registry["order"].pop(0)
            registry["memo"].pop(old_token, None)
            held = registry["by_id"].get(old_id)
            if held is not None and held[0] == old_token:
                registry["by_id"].pop(old_id, None)
        return token


def _projection(inputs: RunInputs, certs: Mapping[Key, Any], page: int,
                ty: int, tx: int, excluded: Key | None,
                ) -> tuple[np.ndarray, np.ndarray] | None:
    # The token FIRST, and the memo taken from the registry BY that token:
    # a memo dict is per-token, so an eviction can never mix two mappings'
    # projections and a reader holding a dict keeps reading it safely.
    registry = _registry(inputs)
    token = _certs_token(inputs, certs)
    memo = registry["memo"].get(token)
    if memo is None:                       # evicted between the two calls
        memo = {}
    cache_key = (page, ty, tx, excluded)
    if cache_key in memo:
        return memo[cache_key]
    view = _WithoutKey(certs, excluded)
    projection = color_sites.certified_projection(
        inputs.row, inputs.geometry, page, ty, tx, view)
    memo[cache_key] = projection
    return projection


# ---------------------------------------------------------- known bits

def metadata_cell_of(row: Any, geometry: Any, key: Key
                     ) -> tuple[int, int, int]:
    """``(flat_cell, dither_bit_0, permutation_position)`` of info bit 0.

    * the printed cell that carries the frame's info index 0 is
      ``geometry.payload_flat[j]`` with ``j`` the position where the
      colour permutation maps SEQUENTIAL index 0
      (`certified_projection` writes ``flat_bits[payload_flat] =
      sequential[order]``, so cell ``payload_flat[j]`` carries
      ``sequential[order[j]]``);
    * the printed bit is ``metadata_bit ^ dither[0]`` — `encode_frame`
      puts ``user_bits[0]`` at mother index 0, `transmitted_positions`
      starts at 0, and the dither is applied in the sequential domain.
    """
    page, ty, tx, stream_id = key
    counter = row.tile_counter(int(page), int(ty), int(tx))
    order = keystream.color_cell_permutation(
        row.seed, counter, row.payload_cells)
    positions = np.flatnonzero(np.asarray(order, np.int64) == 0)
    if positions.size != 1:
        raise FrameError(
            f"colour permutation of {key} maps sequential 0 to "
            f"{positions.size} positions")
    j = int(positions[0])
    flat_cell = int(np.asarray(geometry.payload_flat, np.int64)[j])
    dither = keystream.cmy8_dither_bits(
        row.seed, stream_fact(row, str(stream_id)).dither_aux, counter,
        row.payload_cells)
    return flat_cell, int(dither[0]), j


def known_frame(inputs: RunInputs, certs: Mapping[Key, Any],
                fp: TileFootprint, target: Key, *,
                metadata_known: bool,
                metadata_bit: int | None = None) -> KnownFrame:
    """Every bit the analyzer may know over `fp`, target key excluded.

    `certs` is the certificate mapping the caller wants used — under
    `--withhold` (DESIGN §8) the withheld keys are already gone from it.
    `metadata_bit` is the BLIND metadata bit of the target stream (the
    driver reads it from `inputs.metadata_bit` — the run's OWN certified
    metadata word, which is why it left the scoring module on
    2026-09-04); it is injected only when `metadata_known` and the bit is
    not None.
    """
    page, ty, tx, stream_id = target
    if int(page) != int(fp.page) or int(ty) != int(fp.ty) \
            or int(tx) != int(fp.tx):
        raise FrameError(
            f"target {target} is not the footprint's tile "
            f"({fp.page}, {fp.ty}, {fp.tx})")
    plane = PLANE_OF[str(stream_id)]
    cells = fp.page_cells_yx
    n = cells.shape[0]
    bits = np.zeros((n, 3), np.uint8)
    known = np.zeros((n, 3), np.bool_)

    # 1. furniture — word and dust, a pure function of seed and counter.
    states, kinds = color_model.reference_states(
        inputs.row, inputs.geometry, int(page), cells)
    furniture = np.asarray(kinds, np.int8) >= 0
    if np.any(furniture):
        rows = np.flatnonzero(furniture)
        bits[rows] = tile_codec.states_to_planes(
            np.asarray(states, np.int8)[rows])
        known[rows] = True

    # 2. certified projections, the target key hidden from all of them.
    tile_index = ((cells[:, 0] // TILE_CELLS) * (1 << 20)
                  + (cells[:, 1] // TILE_CELLS))
    local_flat = ((cells[:, 0] % TILE_CELLS) * TILE_CELLS
                  + cells[:, 1] % TILE_CELLS)
    n_projected = 0
    for n_ty, n_tx in footprint_tiles(fp):
        excluded = target if (n_ty == int(ty) and n_tx == int(tx)) else None
        projection = _projection(inputs, certs, int(page), n_ty, n_tx,
                                 excluded)
        if projection is None:
            continue                       # furniture only, already laid
        n_projected += 1
        tile_bits, tile_known = projection
        flat_bits = tile_bits.reshape(-1, 3)
        flat_known = tile_known.reshape(-1, 3)
        rows = np.flatnonzero(
            tile_index == (n_ty * (1 << 20) + n_tx))
        take = local_flat[rows]
        hit = flat_known[take]
        bits[rows] = np.where(hit, flat_bits[take], bits[rows])
        known[rows] |= hit

    # 3. THE ASSERTION (DESIGN §4.5) — before the metadata injection, so
    #    it means exactly "no certificate of the target leaked".
    inside = fp.in_tile & fp.cargo
    leaked = int(np.count_nonzero(known[inside, plane]))
    if leaked:
        raise FrameError(
            f"target-key exclusion FAILED for {target}: {leaked} in-tile "
            f"cargo cell(s) of plane {plane} are known — the frame is "
            f"contaminated (run abort, DESIGN §4.5)")

    # 4. the metadata cell of the target stream.
    metadata_cell: int | None = None
    if metadata_known and metadata_bit is not None:
        flat_cell, dither0, _j = metadata_cell_of(
            inputs.row, inputs.geometry, target)
        cell_y = int(ty) * TILE_CELLS + flat_cell // TILE_CELLS
        cell_x = int(tx) * TILE_CELLS + flat_cell % TILE_CELLS
        rows = np.flatnonzero((cells[:, 0] == cell_y)
                              & (cells[:, 1] == cell_x))
        if rows.size == 1:
            metadata_cell = int(rows[0])
            bits[metadata_cell, plane] = int(metadata_bit) ^ dither0
            known[metadata_cell, plane] = True

    # 5. splits and the label arithmetic.
    regressors = known.all(axis=1)
    labels = known[:, plane].copy()
    sibling_planes = [index for index in range(3) if index != plane]
    siblings = known[:, sibling_planes[0]] & known[:, sibling_planes[1]]
    discriminating = discriminating_mask(bits, known, str(stream_id))
    n_discriminating = int(np.count_nonzero(discriminating & ~inside))

    for array in (bits, known, furniture, regressors, labels, siblings):
        array.setflags(write=False)
    kinds = np.asarray(kinds, np.int8)
    kinds.setflags(write=False)
    return KnownFrame(
        bits=bits, known=known, furniture=furniture,
        metadata_cell=metadata_cell, regressors=regressors, labels=labels,
        siblings=siblings, n_discriminating=n_discriminating,
        furniture_kind=kinds, target=target,
        detail={
            "n_cells": int(n),
            "n_tiles_projected": int(n_projected),
            "n_known_target_plane": int(np.count_nonzero(labels)),
            "n_regressors": int(np.count_nonzero(regressors)),
            "n_siblings": int(np.count_nonzero(siblings)),
            "n_furniture": int(np.count_nonzero(furniture)),
            "n_discriminating_in_tile": int(
                np.count_nonzero(discriminating & inside)),
            "metadata_injected": metadata_cell is not None,
        })
