"""The runtime composition: eight seams of holo3, replaced in THIS process.

holo3 is never edited (project rule).  Every function below is installed
with `setattr` on an imported holo3 module inside the harness process,
each call site resolves the module attribute at call time, and
`uninstall()` puts the originals back.  The seams, by file and line as of
2026-09-03:

1. `holo3/format/identity.py:434  resolve_format_ref`
   teaches the process ONE extra id, the `PV:` sentinel, and delegates
   everything else.  Both consumers (`holo3/cli.py:86`,
   `holo3/store.py:72`) go through the module attribute.
2. `holo3/format/identity.py:489  build_site_geometry`
   returns the SOURCE cmy8 geometry for the plane-view row.  The cell
   SETS are already equal (`row.py`); this buys the cmy8 DUST ORDER, so
   `calibrate.build_site_lookup`'s `index` (calibrate.py:88-102) lines up
   with `pilots.dust_state_values`.  One caller: `holo3/store.py:74`.
3. `holo3/plugins/tiles.py:364  _attempt_k`
   the K attempt XORs `_tile_scramble_bits` (the K page scramble,
   tiles.py:154) and calls `tile_codec.decode_tile` (slot permutation and
   a shortening scatter over 4,096).  A cmy8 stream is dithered by
   `keystream.cmy8_dither_bits` and permuted by
   `keystream.color_cell_permutation` over the 3,976 payload cells.  The
   replacement runs production's own `_sequential_payload` and the cmy8
   stream codec on evidence column 0.  Single call site,
   `tiles.py:479` — `attempt_tile` and everything around it (`_combine`,
   `component_signature`, fact/event minting) stays production.
4. `holo3/plugins/calibrate.py:105  format_reference_values`
   word sites (kind 0) are ALREADY correct for C — the function asks
   `pilots.word_values(seed, counter, PLANE_K)` and a word state is 0 or
   3, so C equals the address bit.  The 20 dust sites (kind 1) are read
   from `keystream.DOMAIN_FILLER_VALUES`, which is a K page's filler, not
   the cmy8 dust cycle.  The wrapper overwrites exactly those rows.
   +20% labels per tile, and the dust cells are the only ones where C and
   M differ at all.
5. `holo3/plugins/words.py:63  reference_page`
   the same defect in the POSE scorer's reference field (`words.py:67`
   `color = family is not K`): 20 of 120 reference values wrong.  Used by
   `pose.py:195` and `cold.py:244`; the BCH word matcher itself is clean
   (`words.word_site_index`, :126, is word-sites-only).
6. `holo3/plugins/tiles.py:110  source_tag`
   certificates and events would otherwise be sourced `tiles/<stage>`.
   The plane view's mints are `planeview/<stage>` so a fold back into a
   production snapshot is never mistaken for a production tile.  `source`
   carries no control flow in holo3 (only the conflict messages at
   `store.py:904` and `tiles.py:546-547`).

7. `holo3/plugins/tiles.py:printed_cells_for` AND `holo3/plugins/
   refine.py:34`'s own binding of the same name — see
   `make_printed_cells` (added by review, 2026-09-03).  Production's
   version is the K re-encode; a plane-view tile was not printed that
   way, and the K version does not raise, it lies.  Both live consumers
   are K-only and therefore ON in a plane-view run.

8. `holo3/format/close.py  CloseProgress`
   MEASURED, and the seam map got this one wrong.  The map said the
   metadata bit is harmless because the plane-view row is not pooled and
   carries one stream, so `store._fold_certificate` (store.py:893) files
   each tile's bit at a unique index `counter` — no collision, no
   IntegrityError, and `--no-close` covers the rest.  Two of those three
   are true.  What the map missed is that the engine also runs an
   INCREMENTAL metadata gate on the certified equations
   (`engine._close_decide`, `close.CloseProgress._ingest` ->
   `_MetadataGate.observe`) whether or not the close is asked for,
   and that gate does Gaussian elimination over the LFSR coefficient
   rows.  A cmy8 stream's metadata bit is the pooled equation for index
   `counter*n_streams + plane`; filed at index `counter` those bits are
   an INCONSISTENT linear system, and the first row that reduces to
   0 = 1 raises `IntegrityError: metadata integrity failure: certified
   metadata equations inconsistent at equation index 16` and kills the
   run before
   `facts.npz` is ever written.  Measured on the synthetic e2e,
   2026-09-03, at 49 tiles.  The replacement files the bit at its TRUE
   pooled index over the source row's stream count (the equations are
   then genuinely consistent and the rank the run reports is real), and
   never calls `settle()`, so `CloseProgress.result` stays None, no
   count plan is built and nothing downstream of the gate runs.

NOT PATCHED, deliberately.  `intake.derived_planes` (intake.py:126-128)
already returns `(("g", None),)` for a single-channel raster whatever the
family, and `store.sampling_planes` (store.py:163) returns that single
plane.  `store._fold_certificate`'s own per-index consistency check
(store.py:893-909) files one bit per `counter` and never sees a second,
so it is left alone.  `k_total` is consulted only inside `close.py`, and
`--no-close` is mandatory: the plane view's fountain ESI is
`counter*3 + plane`, not `counter`.

THE TOOLBOX TRADE, stated: a K row turns OFF swim (swim.py:467/486/522),
color_region (:679), color_pooled (:168), fields/plane-fields (:778),
plane_k (:581) and uplift (`color_arms.arms_for_family(K)` is empty) —
and turns ON refine (refine.py:574/617, K-only) and revisit (:121);
both read certified printed fields, which is why seam 7 exists.
`local_ctx` keeps a real K path (`_prepare_k`, :551).  The plane view is
not the colour receiver minus colour; it is the K receiver, with
certified-feedback pose refinement the C plane has never had.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

# Imported BEFORE anything is replaced, so no module rebinds a name that
# is already a patch (`lib.ldpc.CODES` builds every rung at import; the
# `words._SITE_INDEX_CACHE` is keyed by `sites_seed`, identical for both
# rows, so it is harmless either way).
from holo3 import cli as h3_cli
from holo3 import store as h3_store
from holo3.format import close as h3_close
from holo3.format import identity, keystream, metadata, pilots, tile_codec
from holo3.format.identity import FormatRow, SiteGeometry
from holo3.lib import ldpc
from holo3.plugins import calibrate, refine, tiles, words

from .row import PLANE_OF

#: Imported for their side effects and named here so the import is not
#: mistaken for dead: `lib.ldpc` builds every LDPC rung at import
#: (ldpc.py:90) and `holo3.store` binds the plugin table.  Both must be
#: resident BEFORE a single seam is replaced.
PRIMED: tuple[object, ...] = (h3_store, ldpc)

SOURCE_PLUGIN: str = "planeview"

TILE_CELLS: int = pilots.TILE_CELLS


class SeamError(RuntimeError):
    """holo3 moved under the plane view; refuse rather than guess."""


# ------------------------------------------------------- seam verification

#: (module, attribute, required parameter names, source substrings that
#: must still be present).  Checked before a single `setattr`.
_SEAMS: tuple[tuple[Any, str, tuple[str, ...], tuple[str, ...]], ...] = (
    (identity, "resolve_format_ref", ("ref",), ("_FOSSILS", "mint_format")),
    (identity, "build_site_geometry", ("row",),
     ("word_site_cells_yx", "dust_site_cells_yx", "payload_flat")),
    (tiles, "_attempt_k",
     ("row", "geometry", "page", "ty", "tx", "counter", "dense", "stage"),
     ("_tile_scramble_bits", "decode_tile")),
    (tiles, "source_tag", ("stage",), ("PLUGIN",)),
    (tiles, "printed_cells_for",
     ("row", "geometry", "page", "ty", "tx", "user_bits"),
     ("encode_tile", "_tile_scramble_bits")),
    (refine, "printed_cells_for",
     ("row", "geometry", "page", "ty", "tx", "user_bits"), ()),
    (calibrate, "format_reference_values",
     ("row", "lookup", "page", "cells_yx"),
     ("DOMAIN_FILLER_VALUES", "word_values")),
    (words, "reference_page", ("row", "page", "sites"),
     ("dust_state_values", "DOMAIN_FILLER_VALUES")),
)

#: Seam 7 is a class, not a function; its two methods are checked apart.
_PROGRESS_METHODS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("_ingest", ("_metadata.observe", "pooled_fountain", "_processed")),
    ("_settle", ("self._metadata.settle()",)),
)

#: Production helpers the replacement attempt calls by name.
_REQUIRED_HELPERS: tuple[tuple[Any, str], ...] = (
    (tiles, "_sequential_payload"), (tiles, "_result"),
    (tiles, "_color_outcome"), (tiles, "_bank_active_bits"),
    (tiles, "_bank_transmitted_bits"), (tiles, "max_iters_for"),
    (tiles, "BP_ALPHA"), (tiles, "OUTCOME_BELOW_FLOOR"),
    (tiles, "OUTCOME_FAILED"), (tiles, "OUTCOME_CERTIFIED"),
    (tile_codec, "cmy8_decode_stream"), (tile_codec, "encode_frame"),
    (keystream, "cmy8_dither_bits"),
    (keystream, "color_cell_permutation"),
    (pilots, "dust_state_values"), (pilots, "dust_site_cells_yx"),
    (tile_codec, "states_to_planes"), (h3_cli, "main"),
)


def verify_seams() -> tuple[str, ...]:
    """Every seam exists and still looks like what the patch assumes."""
    checked: list[str] = []
    for module, name, parameters, needles in _SEAMS:
        target = getattr(module, name, None)
        if target is None or not callable(target):
            raise SeamError(
                f"{module.__name__}.{name} is absent or not callable — "
                f"holo3 moved; re-read the seam map before running")
        signature = inspect.signature(target)
        missing = [p for p in parameters if p not in signature.parameters]
        if missing:
            raise SeamError(
                f"{module.__name__}.{name}{signature} lost parameter(s) "
                f"{missing}; the plane view's replacement no longer fits")
        try:
            source = inspect.getsource(target)
        except OSError:                                   # pragma: no cover
            source = ""
        absent = [needle for needle in needles if needle not in source]
        if source and absent:
            raise SeamError(
                f"{module.__name__}.{name} no longer mentions {absent}; the "
                f"behaviour the plane view replaces has changed")
        checked.append(f"{module.__name__}.{name}{signature}")
    for module, name in _REQUIRED_HELPERS:
        if not hasattr(module, name):
            raise SeamError(
                f"{module.__name__}.{name} is absent — the plane view "
                f"calls it directly")
        checked.append(f"{module.__name__}.{name}")
    dispatch = inspect.getsource(tiles.attempt_tile)
    if "_attempt_k(" not in dispatch or "Family.K" not in dispatch:
        raise SeamError(
            "tiles.attempt_tile no longer dispatches a K row to "
            "_attempt_k; the single call site the plane view relies on "
            "is gone")
    if tiles.ARITY_BY_FAMILY[identity.Family.K] != 1:
        raise SeamError(
            f"K evidence arity is "
            f"{tiles.ARITY_BY_FAMILY[identity.Family.K]}, not 1; the plane "
            f"view reads evidence column 0")
    checked.append("tiles.attempt_tile dispatches Family.K -> _attempt_k")
    for name, needles in _PROGRESS_METHODS:
        method = getattr(h3_close.CloseProgress, name, None)
        if method is None:
            raise SeamError(
                f"close.CloseProgress.{name} is absent; the plane view "
                f"overrides it to keep the metadata gate consistent")
        source = inspect.getsource(method)
        absent = [needle for needle in needles if needle not in source]
        if absent:
            raise SeamError(
                f"close.CloseProgress.{name} no longer mentions {absent}")
        checked.append(f"close.CloseProgress.{name}")
    for helper in ("_MetadataGate", "_tile_counter"):
        if not hasattr(h3_close, helper):
            raise SeamError(f"close.{helper} is absent")
        checked.append(f"close.{helper}")
    return tuple(checked)


def make_close_progress(plane_row: FormatRow, source_row: FormatRow,
                        plane_index: int) -> type:
    """`close.CloseProgress` with the plane view's metadata gate.

    See seam 8.  For any other row this is production, method for method.
    """
    row_id = plane_row.row_id
    n_streams = len(source_row.streams)
    base = h3_close.CloseProgress

    class _PlaneViewCloseProgress(base):                # type: ignore[misc]

        def __init__(self, row: FormatRow) -> None:
            super().__init__(row)
            if getattr(row, "row_id", None) == row_id:
                # the gate over the SOURCE row: pooled, n_streams
                # equations per counter
                self._metadata = h3_close._MetadataGate(source_row)

        def _ingest(self, key: Any, cert: Any) -> None:
            if getattr(self.row, "row_id", None) != row_id:
                return super()._ingest(key, cert)
            counter = h3_close._tile_counter(self.row, cert)
            index = metadata.equation_index(counter, plane_index, n_streams)
            self._metadata.observe(index, int(cert.user_bits[0]))
            self._processed.add(key)

        def _settle(self) -> None:
            # Never settle a plane view: the decoded word would be the
            # POOLED volume's (three streams' k), and this run decodes
            # one.  `result` stays None, so no count plan is built.
            if getattr(self.row, "row_id", None) == row_id:
                return
            super()._settle()

    _PlaneViewCloseProgress.__name__ = "PlaneViewCloseProgress"
    _PlaneViewCloseProgress.__qualname__ = "PlaneViewCloseProgress"
    return _PlaneViewCloseProgress


# ---------------------------------------------------------- replacements

def make_attempt(plane_row: FormatRow) -> Callable[..., Any]:
    """`tiles._attempt_k` for a stream framed like a cmy8 stream.

    Everything below is production: `_sequential_payload` (the cell
    permutation), `cmy8_dither_bits`, `cmy8_decode_stream` (which
    un-dithers exactly once and then runs `decode_frame`), and `_result`.
    The one thing spelled out here rather than delegated to
    `_attempt_cmy8` is the evidence column: arity-1 K evidence is
    (4096, 1), so the stream reads column 0, whereas `_attempt_cmy8`
    would index `sequential[:, fact.plane]` and the row's `plane` field
    must stay `PLANE_K` for `words.addressing_plane`.
    """
    row_id = plane_row.row_id

    def _attempt_plane(row: FormatRow, geometry: SiteGeometry, page: int,
                       ty: int, tx: int, counter: int, dense: np.ndarray,
                       stage: str) -> Any:
        if row.row_id != row_id:
            return _ORIGINALS["tiles._attempt_k"](
                row, geometry, page, ty, tx, counter, dense, stage)
        stream_id = row.streams[0].stream_id
        bank = row.streams[0].rung_children
        column = np.asarray(dense, np.float64)[:, 0]
        if not np.isfinite(column).all():
            raise tiles.IntegrityError(
                f"tile ({page}, {ty}, {tx}) evidence is not finite — "
                "0.0 is the only erasure spelling")
        observed = column != 0.0
        sequential, sequential_observed = tiles._sequential_payload(
            row, geometry, counter, np.asarray(dense, np.float64), observed)
        level_llrs = sequential[:, 0]
        n_informative = int(np.count_nonzero(sequential_observed))
        supported = int(np.count_nonzero(
            sequential_observed & (level_llrs != 0.0)))
        if supported < tiles._bank_active_bits(bank):
            return tiles._result(page, ty, tx, stream_id, stage,
                                 tiles.OUTCOME_BELOW_FLOOR, n_informative,
                                 0, None, None, None)
        dither = keystream.cmy8_dither_bits(
            row.seed, stream_id, counter, tiles._bank_transmitted_bits(bank))
        n_iters, syndrome_ok, crc_ok, user_bits = tiles._color_outcome(
            tile_codec.cmy8_decode_stream(
                level_llrs, bank, dither, tiles.max_iters_for(stage),
                tiles.BP_ALPHA))
        outcome = (tiles.OUTCOME_FAILED if user_bits is None
                   else tiles.OUTCOME_CERTIFIED)
        return tiles._result(page, ty, tx, stream_id, stage, outcome,
                             n_informative, n_iters, syndrome_ok, crc_ok,
                             user_bits)

    return _attempt_plane


def _dust_plane_bits(row: FormatRow, counter: int,
                     plane_index: int) -> np.ndarray:
    """The target plane's bit at each of the tile's 20 dust sites."""
    states = pilots.dust_state_values(
        row.seed, (counter,), row.dust_base_cycle, row.n_dust)[0]
    return tile_codec.states_to_planes(states)[:, plane_index]


def make_reference_values(plane_row: FormatRow,
                          plane_index: int) -> Callable[..., np.ndarray]:
    """`calibrate.format_reference_values` with the dust rows repaired."""
    row_id = plane_row.row_id
    original = calibrate.format_reference_values

    def _reference_values(row: FormatRow, lookup: Any, page: int,
                          cells_yx: np.ndarray) -> np.ndarray:
        values = original(row, lookup, page, cells_yx)
        cells = np.asarray(cells_yx, np.int64)
        if row.row_id != row_id or cells.size == 0:
            return values
        local_y = cells[:, 0] % TILE_CELLS
        local_x = cells[:, 1] % TILE_CELLS
        dust_rows = np.flatnonzero(lookup.kind[local_y, local_x] == 1)
        if dust_rows.size:
            tile_code = ((cells[dust_rows, 0] // TILE_CELLS)
                         * row.tiles_yx[1]
                         + (cells[dust_rows, 1] // TILE_CELLS))
            for code in np.unique(tile_code):
                selected = dust_rows[tile_code == code]
                ty, tx = divmod(int(code), row.tiles_yx[1])
                bits = _dust_plane_bits(
                    row, row.tile_counter(page, ty, tx), plane_index)
                values[selected] = bits[lookup.index[
                    local_y[selected], local_x[selected]]].astype(np.int8)
        return values

    return _reference_values


def make_printed_cells(plane_row: FormatRow,
                       plane_index: int) -> Callable[..., np.ndarray]:
    """`tiles.printed_cells_for` re-encoded through the cmy8 stream.

    SEAM 8, added by review 2026-09-03.  Production's version is the K
    re-encode: `tile_codec.encode_tile` (K slot permutation and the
    shortening scatter over 4,096) XOR `_tile_scramble_bits`.  A
    plane-view tile was NOT printed that way — its payload cells are
    `encode_frame` over the stream's bank, XOR `cmy8_dither_bits`, laid
    down through `color_cell_permutation` over the 3,976 payload cells.
    The K version does not raise on a plane-view certificate (its
    known-site check is trivially satisfied: the scramble is zero at
    site cells, so `field[known] == known_values` by construction), it
    silently returns a WRONG printed field.

    Two production consumers, both K-only and both live on a plane-view
    run: `refine.certified_fields` (refine.py:117, the certified-feedback
    pose targets at refine.py:606) and `local_ctx._k_components`
    (local_ctx.py:382, the donor labels of the local-context fit).  Wrong
    targets cannot mint a wrong certificate — the LDPC syndrome and the
    CRC still gate — but they can move a good pose and poison a context
    fit, so the two mechanisms the plane view exists to give the C plane
    would have run on noise.

    The inverse of `_sequential_payload` is exact: production writes
    `sequential[order] = physical`, so `physical = sequential[order]`.
    """
    row_id = plane_row.row_id
    original = tiles.printed_cells_for

    def _printed_cells(row: FormatRow, geometry: SiteGeometry, page: int,
                       ty: int, tx: int,
                       user_bits: np.ndarray) -> np.ndarray:
        if row.row_id != row_id:
            return original(row, geometry, page, ty, tx, user_bits)
        counter = row.tile_counter(page, ty, tx)
        stream_id = row.streams[0].stream_id
        bank = row.streams[0].rung_children
        dither = np.asarray(keystream.cmy8_dither_bits(
            row.seed, stream_id, counter,
            tiles._bank_transmitted_bits(bank)), np.uint8)
        transmitted = np.asarray(tile_codec.encode_frame(
            np.asarray(user_bits, np.uint8).ravel(), bank), np.uint8) ^ dither
        order = keystream.color_cell_permutation(
            row.seed, counter, row.payload_cells)
        field = np.zeros(TILE_CELLS * TILE_CELLS, np.uint8)
        field[np.asarray(geometry.payload_flat, np.int64)] = transmitted[order]
        field = field.reshape(TILE_CELLS, TILE_CELLS)
        word_cells = np.asarray(geometry.word_cells_yx, np.int64)
        # A word state is 0 or 3 (`pilots.color_word_states`), so the C and
        # M bit at a word site IS the address-word bit; the Y bit is 0.
        word = np.asarray(pilots.word_values(
            row.seed, (counter,), pilots.PLANE_K)[0], np.uint8)
        field[word_cells[:, 0], word_cells[:, 1]] = (
            word if plane_index != 2 else np.zeros_like(word))
        dust_cells = np.asarray(geometry.extra_cells_yx, np.int64)
        if dust_cells.size:
            field[dust_cells[:, 0], dust_cells[:, 1]] = _dust_plane_bits(
                row, counter, plane_index)
        return field

    return _printed_cells


def make_reference_page(plane_row: FormatRow,
                        plane_index: int) -> Callable[..., Any]:
    """`words.reference_page` with the dust values repaired."""
    row_id = plane_row.row_id
    original = words.reference_page

    def _reference_page(row: FormatRow, page: int,
                        sites: np.ndarray | None = None) -> Any:
        page_reference = original(row, page, sites)
        if row.row_id != row_id or row.n_dust == 0:
            return page_reference
        tiles_y, tiles_x = row.tiles_yx
        dust = pilots.dust_site_cells_yx(row.sites_seed, row.n_dust)
        index = np.arange(tiles_y * tiles_x, dtype=np.int64)
        counters = page * (tiles_y * tiles_x) + index
        states = pilots.dust_state_values(
            row.seed, counters, row.dust_base_cycle, row.n_dust)
        bits = tile_codec.states_to_planes(states)[..., plane_index]
        extra_y = (index // tiles_x)[:, None] * TILE_CELLS + dust[None, :, 0]
        extra_x = (index % tiles_x)[:, None] * TILE_CELLS + dust[None, :, 1]
        values = np.array(page_reference.values, np.uint8)
        values[extra_y, extra_x] = bits
        return words.ReferencePage(page_reference.page, values,
                                   page_reference.sites)

    return _reference_page


# ------------------------------------------------------------- installer

_ORIGINALS: dict[str, Any] = {}


@dataclass
class Installation:
    """What is currently replaced, and how to put it back."""

    plane_ref: str
    source_ref: str
    stream_id: str
    plane_index: int
    seams: tuple[str, ...] = ()
    _restore: list[tuple[Any, str, Any]] = field(default_factory=list)

    def uninstall(self) -> None:
        for module, name, original in reversed(self._restore):
            setattr(module, name, original)
        self._restore.clear()
        _ORIGINALS.clear()


def install(plane_row: FormatRow, source_row: FormatRow, *,
            source_plugin: str = SOURCE_PLUGIN) -> Installation:
    """Replace the seven seams; returns the handle that puts them back."""
    if _ORIGINALS:
        raise SeamError(
            f"the plane view is already installed ({sorted(_ORIGINALS)}); "
            f"uninstall before installing again — a second install would "
            f"record a PATCH as the original and never restore holo3")
    seams = verify_seams()
    stream_id = plane_row.streams[0].stream_id
    plane_index = PLANE_OF[stream_id]
    installation = Installation(
        plane_ref=plane_row.row_id, source_ref=source_row.row_id,
        stream_id=stream_id, plane_index=plane_index, seams=seams)

    def replace(module: Any, name: str, value: Any) -> None:
        original = getattr(module, name)
        _ORIGINALS[f"{module.__name__.split('.')[-1]}.{name}"] = original
        installation._restore.append((module, name, original))
        setattr(module, name, value)

    original_resolve = identity.resolve_format_ref
    original_geometry = identity.build_site_geometry
    source_geometry = original_geometry(source_row)

    def _resolve(ref: str) -> FormatRow:
        if ref == plane_row.row_id:
            return plane_row
        return original_resolve(ref)

    def _geometry(row: FormatRow) -> SiteGeometry:
        if row.row_id == plane_row.row_id:
            return source_geometry
        return original_geometry(row)

    def _source_tag(stage: str) -> str:
        return f"{source_plugin}/{stage}"

    replace(identity, "resolve_format_ref", _resolve)
    replace(identity, "build_site_geometry", _geometry)
    replace(tiles, "_attempt_k", make_attempt(plane_row))
    replace(tiles, "source_tag", _source_tag)
    printed_cells = make_printed_cells(plane_row, plane_index)
    replace(tiles, "printed_cells_for", printed_cells)
    # `refine` binds the name at import (`from .tiles import
    # printed_cells_for`, refine.py:34), so the tiles attribute alone
    # is inert for the only two consumers — refine.certified_fields
    # and, through it, local_ctx._k_components.
    replace(refine, "printed_cells_for", printed_cells)
    replace(calibrate, "format_reference_values",
            make_reference_values(plane_row, plane_index))
    replace(words, "reference_page",
            make_reference_page(plane_row, plane_index))
    replace(h3_close, "CloseProgress",
            make_close_progress(plane_row, source_row, plane_index))
    return installation
