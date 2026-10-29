"""The plane-view `FormatRow`: one cmy8 stream, framed as a K page.

WHY A ROW AT ALL.  The literal experiment is "filter C, treat the whole
page as K": emit one greyscale capture per RGB capture holding the
unmixed C plane, and let the PRODUCTION receiver run its K pipeline over
them — its own survey, placement, word matching, PAVA calibration,
region context, refine and revisit, and the multi-capture union.  holo3
picks that pipeline off `row.family`, so the run needs a row whose family
is K and whose every format quantity is still the cmy8 stream's.

WHAT IS ALREADY IDENTICAL (measured, asserted below on every build).
`identity.build_site_geometry` gives a K row at p120
`pilots.filler_site_cells_yx(sites_seed, 20, word)` and a cmy8 row
`pilots.dust_site_cells_yx(sites_seed, 20)` — and the latter IS the
former, re-sorted by flat index (`pilots.py:102-107`).  So for the sheet-H
identity the two geometries agree byte-for-byte in `word_cells_yx`,
`shorten_flat`, `payload_flat` (3,976), `slot_a` and `slot_b`; only
`extra_cells_yx` differs in ROW ORDER, over the same 20 cells.  The K
attempt floor `tiles.k_eff_bits` (3,520 − 120 = 3,400) is exactly the
cmy8 bank's `_bank_active_bits`, and `StreamFact.user_bits` is 3,368 on
both sides.  Nothing downstream breaks on 120 sites.

WHAT IS NOT.  The row id is the AES seed, so `mint_format` alone would
key the whole format off the wrong bytes; the seed is transplanted.  And
at every WORD site the printed state is 0 or 3 — C is 1 exactly where the
K address bit is 1 — so K's word decoder reads C's word unchanged, but
the 20 DUST sites carry the cmy8 dust cycle, not K's filler keystream.
That is a value defect, not a geometry one, and `patches.py` repairs it
at the two places that read it.

Nothing here monkeypatches anything; `patches.py` does that.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np

from holo.receiver.format import identity
from holo.receiver.format.identity import Family, FormatRow

#: The sentinel prefix of a plane-view format ref.  `patches.install`
#: teaches `identity.resolve_format_ref` this one id and nothing else, so
#: an unpatched process refuses it loudly instead of minting something.
PLANE_REF_PREFIX: str = "PV:"

#: Plane index per cmy8 stream id (`tile_codec.states_to_planes`: bit i
#: is plane i, so state 3 is C=1, M=1, Y=0).
PLANE_OF: dict[str, int] = {"C": 0, "M": 1, "Y": 2}


class PlaneRowError(RuntimeError):
    """The plane view cannot be framed for this format identity."""


def plane_view_ref(source_ref: str, stream_id: str) -> str:
    """The sentinel id of the plane view of `stream_id` of `source_ref`."""
    return f"{PLANE_REF_PREFIX}{source_ref}/{stream_id}"


def parse_plane_view_ref(ref: str) -> tuple[str, str]:
    """The (source format ref, stream id) a sentinel id names."""
    if not ref.startswith(PLANE_REF_PREFIX):
        raise PlaneRowError(
            f"{ref!r} is not a plane-view ref (want {PLANE_REF_PREFIX}…)")
    body = ref[len(PLANE_REF_PREFIX):]
    source_ref, sep, stream_id = body.rpartition("/")
    if not sep or not source_ref or stream_id not in PLANE_OF:
        raise PlaneRowError(
            f"{ref!r}: expected {PLANE_REF_PREFIX}<source ref>/<C|M|Y>")
    return source_ref, stream_id


def source_stream_fact(source_row: FormatRow, stream_id: str) -> Any:
    for fact in source_row.streams:
        if fact.stream_id == stream_id:
            return fact
    raise PlaneRowError(
        f"{source_row.row_id} has no stream {stream_id!r} "
        f"(streams: {[f.stream_id for f in source_row.streams]})")


def _assert_geometry_agrees(plane_row: FormatRow,
                            source_row: FormatRow) -> dict[str, Any]:
    """The headline claim, re-checked on every build (never assumed)."""
    plane_geometry = identity.build_site_geometry(plane_row)
    source_geometry = identity.build_site_geometry(source_row)
    report: dict[str, Any] = {}
    for name in ("word_cells_yx", "shorten_flat", "payload_flat",
                 "slot_a", "slot_b"):
        mine = np.asarray(getattr(plane_geometry, name))
        theirs = np.asarray(getattr(source_geometry, name))
        if not np.array_equal(mine, theirs):
            raise PlaneRowError(
                f"plane view refused: the K geometry's {name} differs from "
                f"{source_row.row_id}'s — holo3's site construction moved "
                f"and the plane view is no longer the same page")
        report[name] = tuple(int(value) for value in mine.shape)
    mine = set(map(tuple, np.asarray(
        plane_geometry.extra_cells_yx).tolist()))
    theirs = set(map(tuple, np.asarray(
        source_geometry.extra_cells_yx).tolist()))
    if mine != theirs:
        raise PlaneRowError(
            "plane view refused: the K filler sites are not the cmy8 dust "
            "sites; only their ROW ORDER may differ")
    report["extra_cells_same_set"] = True
    report["extra_cells_same_order"] = bool(np.array_equal(
        np.asarray(plane_geometry.extra_cells_yx),
        np.asarray(source_geometry.extra_cells_yx)))
    return report


def build_plane_row(source_ref: str,
                    stream_id: str = "C") -> tuple[FormatRow, FormatRow,
                                                   dict[str, Any]]:
    """(plane-view row, source row, the agreement report).

    The plane-view row is family K — so holo3 runs its K pipeline — with
    the SOURCE row's AES seed, pitch, tile matrix, site count and rung,
    and one stream carrying the source stream's id.  `plane` stays
    `keystream.PLANE_K` because `words.addressing_plane` reads it for a K
    row and the printed word values are `pilots.word_values(seed,
    counters, PLANE_K)` on both sides; the tile attempt takes its plane
    index from the arity-1 evidence column, not from this field.
    """
    if stream_id not in PLANE_OF:
        raise PlaneRowError(f"stream {stream_id!r} not in {sorted(PLANE_OF)}")
    if stream_id == "Y":
        # A word state is 0 or 3 (`pilots.color_word_states`), so C and M
        # carry the address-word bit at every word site and Y carries
        # NOTHING there: a Y plane view has no addressing signal at all,
        # and the word labels every reference path hands the K pipeline
        # would be the C/M word, not the printed Y.  Refuse rather than
        # run a page whose 100 word sites are a lie.
        raise PlaneRowError(
            "the plane view is defined for C and M only: word states are "
            "0 or 3, so the Y plane is blank at every word site and the "
            "page has no address signal")
    source_row = identity.resolve_format_ref(source_ref)
    if source_row.family is not Family.CMY8:
        raise PlaneRowError(
            f"{source_ref} is family {source_row.family.value}; the plane "
            f"view needs cmy8 (per-plane independent LDPC streams)")
    fact = source_stream_fact(source_row, stream_id)
    if len(fact.rung_children) != 1:
        raise PlaneRowError(
            f"{source_ref} stream {stream_id} has a {len(fact.rung_children)}"
            f"-child bank; the plane view frames one rung")
    rung = str(fact.rung_children[0][0])
    minted = identity.mint_format(
        pitch=source_row.pitch_in, family=Family.K, rungs=(rung,),
        sites=source_row.n_sites, gen=1, tiles_yx=source_row.tiles_yx)
    ref = plane_view_ref(source_ref, stream_id)
    plane_row = dataclasses.replace(
        minted,
        row_id=ref,
        display_id=ref,
        seed=source_row.seed,
        n_dust=source_row.n_dust,
        dust_base_cycle=source_row.dust_base_cycle,
        streams=(dataclasses.replace(minted.streams[0],
                                     stream_id=stream_id),))
    if plane_row.sites_seed != source_row.sites_seed:
        raise PlaneRowError(
            f"sites seed {plane_row.sites_seed!r} != "
            f"{source_row.sites_seed!r}; the site lattice would differ")
    if plane_row.streams[0].rung_children != fact.rung_children:
        raise PlaneRowError(
            f"bank {plane_row.streams[0].rung_children} != "
            f"{fact.rung_children}")
    if plane_row.streams[0].user_bits != fact.user_bits:
        raise PlaneRowError(
            f"user bits {plane_row.streams[0].user_bits} != {fact.user_bits}")
    if plane_row.payload_cells != source_row.payload_cells:
        raise PlaneRowError(
            f"payload cells {plane_row.payload_cells} != "
            f"{source_row.payload_cells}")
    report = _assert_geometry_agrees(plane_row, source_row)
    report.update({
        "plane_view_ref": ref,
        "source_ref": source_ref,
        "stream_id": stream_id,
        "plane_index": PLANE_OF[stream_id],
        "rung": rung,
        "n_sites": int(source_row.n_sites),
        "n_dust": int(source_row.n_dust),
        "payload_cells": int(source_row.payload_cells),
        "user_bits": int(fact.user_bits),
        "seed": source_row.seed.decode("ascii", "replace"),
        "minted_k_row_id": minted.row_id,
    })
    return plane_row, source_row, report
