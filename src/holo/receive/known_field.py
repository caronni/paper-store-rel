"""The KnownField carrier: what the receiver KNOWS about printed cells.

One derivation, one law.  For a set of absolute page cells this module
answers "which physical components are known here, and on whose
authority" — and it is the SINGLE enforcement point of the RECEIVE-DESIGN
§6.2a provenance law:

* FORMAT authority — canonical BCH word and color dust sites are exact by
  construction (``color_anchoring.color_reference_states``);
* CERTIFIED authority — prior-barrier CRC certificates project onto their
  own tile's payload cells through the canonical production leaf
  ``color_projection.project_certified_color_tile``, which labels only the
  components its certificates actually own (a partially certified CMY8
  tile labels ONLY the certified plane); and
* NOTHING ELSE.  Candidate decisions, detector marginals, sibling-plane
  inference, and same-barrier certificates are not knowledge and never
  enter here.  Certificates label, suppress, and (from P9) condition;
  they are never candidates.

The carrier is transient and kind-neutral: it describes cells, not
detectors, so cmy7, cmy8, and (were K ever to migrate) K all read the
same shape.

SEAMS RESERVED (documented, deliberately not built here):

* the P9 masked VIEW — P9/PK10 evaluates gates and fits pattern-stratified
  strata against a deterministically masked reading of this field.  That
  is a view, never a mutation: the carrier this constructor returns always
  states the cell's true knowledge, and every other consumer (QDA fit,
  context conditioning, registration templates, ownership labels) reads it
  unmasked.
* the pixel-space view — the planned payload -> raw-pixel channel-model
  loop projects the same knowledge through committed geometry onto
  capture pixels (docs/DONE-GEOMETRY.md).  Its inputs are exactly this
  carrier's, at a finer resolution.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core import channel
from ..format.descriptor import FormatSpec
from .color_anchoring import color_reference_states
from .color_projection import (
    CertifiedColorProjection,
    project_certified_color_tile,
)
from .evidence import TileCertificateRecord
from .payload_model import _immutable


# ``provenance`` values.  Word/dust are format authority; ``CERTIFIED``
# marks a payload cell carrying at least one prior-barrier certified
# component (a fully certified cell additionally resolves ``states``).
PROVENANCE_UNKNOWN = -1
PROVENANCE_WORD = 0
PROVENANCE_DUST = 1
PROVENANCE_CERTIFIED = 2


@dataclass(frozen=True, slots=True)
class KnownRows:
    """Per-cell known printed field for one aligned window row set.

    All arrays are read-only and aligned to the ``(N, 2)`` page cells the
    constructor was given, in that order.

    ``states`` carries the physical state id (``C | M<<1 | Y<<2``) where
    every component is known and ``-1`` where any component is unknown.
    Its dtype is ``int8`` — the format's own state dtype and the dtype
    every consumer already requires (see the module note in
    :func:`build_known_rows`).
    """

    states: np.ndarray               # (N,)   int8,  -1 = not fully known
    component_bits: np.ndarray       # (N, 3) uint8, C/M/Y printed bits
    component_mask: np.ndarray       # (N, 3) bool,  which bits are known
    furniture_kind: np.ndarray       # (N,)   int8,  0 word / 1 dust / -1
    provenance: np.ndarray           # (N,)   int8,  PROVENANCE_*
    site_keys: np.ndarray            # (N,)   int64, physical cell ids
    dependency_certificate_ids: tuple[str, ...]


class KnownFieldError(ValueError):
    """The provenance law was violated while building a KnownField."""


def _site_keys(
    spec: FormatSpec,
    page: int,
    cells: np.ndarray,
) -> np.ndarray:
    """Absolute page-major physical cell ids.

    Same SEMANTICS as ``_payload_context._physical_cell_ids`` — one stable
    identity per physical cell, ordered lexicographically by
    ``(page, y, x)`` — in the absolute rather than the region-compacted
    form: a KnownField is built per window and its keys must compare
    across windows, regions, and lanes, so there is no population to rank
    against.
    """
    cells_y, cells_x = spec.layout.cells_yx
    return (
        np.int64(page) * np.int64(cells_y) * np.int64(cells_x)
        + cells[:, 0] * np.int64(cells_x)
        + cells[:, 1]
    )


def _validate(
    states: np.ndarray,
    bits: np.ndarray,
    known: np.ndarray,
    furniture_kind: np.ndarray,
    provenance: np.ndarray,
    certified_tile: np.ndarray,
) -> None:
    """Enforce the §6.2a provenance law on a finished field.

    Cheap and vectorized — a handful of passes over ``(N, 3)`` booleans
    beside a QDA fit.  Each check names an authority failure this
    constructor is the last line of defence against.
    """
    complete = known.all(axis=1)
    if not np.array_equal(states >= 0, complete):
        raise KnownFieldError(
            "known field: a state is resolved exactly when all three "
            "components are known")
    if complete.any() and not np.array_equal(
            channel.states_to_planes(states[complete]), bits[complete]):
        raise KnownFieldError(
            "known field: resolved states disagree with component bits")
    if np.any(bits[~known] != 0):
        raise KnownFieldError(
            "known field: an unknown component carries a bit")
    furniture = furniture_kind >= 0
    if not np.all(known[furniture]):
        raise KnownFieldError(
            "known field: format-known furniture is partially known")
    labelled = known.any(axis=1)
    if np.any(labelled & ~furniture & ~certified_tile):
        raise KnownFieldError(
            "known field: a payload cell is labelled without certificate "
            "authority")
    if np.any((provenance < PROVENANCE_UNKNOWN)
              | (provenance > PROVENANCE_CERTIFIED)):
        raise KnownFieldError("known field: provenance value is unknown")
    if not np.array_equal(provenance >= 0, labelled):
        raise KnownFieldError(
            "known field: a labelled cell must name its authority")
    if not np.array_equal(
            provenance == PROVENANCE_CERTIFIED, labelled & ~furniture):
        raise KnownFieldError(
            "known field: certified provenance is not a payload label")
    if not np.array_equal(provenance[furniture], furniture_kind[furniture]):
        raise KnownFieldError(
            "known field: furniture provenance is not its format kind")


def build_known_rows(
    spec: FormatSpec,
    page: int,
    aligned_cells_yx: np.ndarray,
    certificate_index: dict[
        tuple[int, int, int], tuple[TileCertificateRecord, ...]
    ],
    projection_cache: dict[
        tuple[int, int, int], CertifiedColorProjection
    ],
) -> KnownRows:
    """Derive one window's known printed field.

    Format furniture first, prior certified components overlaid on top;
    a cell whose three components are all known additionally resolves to a
    physical state.  ``projection_cache`` is the caller's per-capture
    memo of ``project_certified_color_tile`` results (one projection per
    covered tile address), and is written through here.

    DTYPE NOTE (PK2 deviation, deliberate): the lead's interface sketch
    spelled ``states`` as int64.  Physical states are ``0..7`` with ``-1``
    for unknown, every existing consumer (``color_fitting``,
    ``color_detect``, ``_Rows.states``) reads int8, and a full-page color
    lane carries millions of cells — int64 here would cost 8x the memory
    for zero information and would force a lossy cast at every consumer.
    ``site_keys`` IS int64: page-major cell ids overflow int32 on real
    page geometries.
    """
    cells = np.asarray(aligned_cells_yx, np.int64)
    states, furniture_kind = color_reference_states(spec, page, cells)
    resolved_states = np.asarray(states, np.int8).copy()
    bits = np.zeros((resolved_states.size, 3), np.uint8)
    known = np.zeros((resolved_states.size, 3), np.bool_)
    furniture = resolved_states >= 0
    if np.any(furniture):
        bits[furniture] = channel.states_to_planes(
            resolved_states[furniture])
        known[furniture] = True

    tile_y = cells[:, 0] // 64
    tile_x = cells[:, 1] // 64
    tile_code = tile_y * spec.layout.tiles_yx[1] + tile_x
    certified_tile = np.zeros(resolved_states.size, np.bool_)
    dependencies: set[str] = set()
    for code in np.unique(tile_code):
        ty, tx = divmod(int(code), spec.layout.tiles_yx[1])
        address = (page, ty, tx)
        records = certificate_index.get(address, ())
        if not records:
            continue
        projection = projection_cache.get(address)
        if projection is None:
            projection = project_certified_color_tile(
                records, spec, address)
            projection_cache[address] = projection
        selected = np.flatnonzero(tile_code == code)
        local_y = cells[selected, 0] % 64
        local_x = cells[selected, 1] % 64
        projected_bits = projection.component_bits[local_y, local_x]
        projected_known = projection.known_mask[local_y, local_x]
        selected_bits = bits[selected]
        selected_bits[projected_known] = projected_bits[projected_known]
        bits[selected] = selected_bits
        known[selected] |= projected_known
        certified_tile[selected] = True
        dependencies.update(projection.dependency_certificate_ids)

    complete = known.all(axis=1)
    if np.any(complete):
        resolved_states[complete] = channel.planes_to_states(bits[complete])
    # Furniture kind IS the provenance for format-known cells; a payload
    # cell that carries any known component got it from a prior-barrier
    # certificate projection and from nowhere else.
    provenance = np.where(
        furniture_kind >= 0, furniture_kind,
        np.where(known.any(axis=1), np.int8(PROVENANCE_CERTIFIED),
                 np.int8(PROVENANCE_UNKNOWN))).astype(np.int8)
    _validate(resolved_states, bits, known, furniture_kind, provenance,
              certified_tile)
    return KnownRows(
        states=_immutable(resolved_states, np.int8),
        component_bits=_immutable(bits, np.uint8),
        component_mask=_immutable(known, np.bool_),
        # Read-only like every other field, which is also what the label
        # rows in ``color_anchoring._label_site_rows`` already carry;
        # nothing has ever written through this array.
        furniture_kind=_immutable(furniture_kind, np.int8),
        provenance=_immutable(provenance, np.int8),
        site_keys=_immutable(_site_keys(spec, page, cells), np.int64),
        dependency_certificate_ids=tuple(sorted(dependencies)),
    )


__all__ = [
    "PROVENANCE_CERTIFIED", "PROVENANCE_DUST", "PROVENANCE_UNKNOWN",
    "PROVENANCE_WORD", "KnownFieldError", "KnownRows", "build_known_rows",
]
