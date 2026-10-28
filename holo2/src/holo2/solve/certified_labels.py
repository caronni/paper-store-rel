"""CA1's label enrichment: certified reconstructions (H5 P2).

A certified tile's payload bits, re-encoded through the format, are
GROUND TRUTH at every one of that tile's 4096 cells — not merely at the
~100 word sites and the filler the format predicts unaided. This module
turns that fact into label sites the calibration pools may trust, by
publishing a :class:`~holo2.solve.reference.ReferenceFieldProvider` that
is the cold-legal field OVERLAID with the committed certificate frontier.
``calibration.region_populations`` needs no change at all: it already
reads ``sites``/``values`` off whatever provider it is handed, so the
enrichment is entirely a statement about which field that is.

WHAT IS CARRIED, AND WHAT IS NEW (read this before comparing to v1).
The ARITHMETIC is v1's ``CertifiedTileLabels`` exactly — the certified
user bits re-encoded to the complete printed field, mint-once cached,
and CONFLICTING CERTIFIED FIELDS AT ONE TILE FATAL, never silently
resolved (``src/holo/receive/certified_refine.py:79`` and
``CertificateFrontier.from_certificates``). The COMPOSITION is new:
v1 feeds certified reconstructions to POSE REFINEMENT (RF1,
``certified_refine.collect_segment_labels``) and never to a calibration
fit — v1's one label channel for both PAVA and the ctx arm is
``_payload_sampling.format_reference_values``, which leaves cargo at −1.
The census anticipated exactly this step and marked it unbuilt (PROVIDERS
CA1: "format words + filler, LATER + certified reconstructions"); H5 P2
is that "later". So pin (a) compares the RE-ENCODE against v1's own
``CertifiedTileLabels`` — the part that is carried — and the harvest that
consumes it is holo2's, pinned on its own terms.

WHY THIS IS NOT SELF-TRAINING (L6). A certificate is CRC- and
syndrome-verified truth about what the paper carries; re-encoding it is
a format computation, not a detector opinion. The correction the enriched
fit produces is applied to the tiles that are NOT yet certified, so the
labels and the subjects are disjoint by construction. ``solve/tiles.py``
says as much where the re-encode lives: the certified field is "the
substrate the detector labels from".

TWO FATAL DISAGREEMENTS, both loud and both naming the tile:

* :class:`~holo2.core.CertificateConflict` — two certified records at one
  tile address whose printed fields differ. v1's carried law. In holo2's
  store this is defence in depth rather than a live hazard, because the
  work key embeds the stream and the commit wall already refuses a
  differing ``bits_ref`` at one key (``records.carry_tile``); it is
  enforced here anyway because "two certificates disagree" is a
  zero-wrong-invariant breach and the frontier is assembled from an
  index, not from the wall.
* :class:`CertifiedLabelError` — a certified reconstruction that
  disagrees with the FORMAT field at a format-known site of its own tile.
  This one is live and cheap: the payload scramble is zeroed at site
  cells (``tiles._tile_scramble_bits``), so a healthy certificate's
  re-encode reproduces the word and filler values BIT-EXACTLY, and any
  disagreement means the certificate is being read at the wrong address,
  the wrong page or under a forked keystream — the e012 failure class,
  caught before a single wrong label enters a fit.

QUARANTINE. Certificates are certificate-backed and done is inviolable,
so the frontier is NOT quarantine-filtered — a condemned POSE says
nothing about whether the bits under it decoded. The pose-scoped half of
the harvest is unchanged and still passes ``quarantine.is_quarantined``
at pool assembly (``calibration.pool_members``), which is where the
predicate belongs.

MINT-ONCE, TWICE OVER. Per CERTIFICATE, the re-encoded field is cached by
content address and never recomputed — v1's ``_PRINTED_CELLS_CACHE`` rule,
and the reason a growing frontier costs one re-encode per NEW certificate
rather than one per certificate per fit. Per FRONTIER, the assembled page
field is cached too, keyed on the certified work-key tuple: certificates
are terminal and immutable (L5), so that tuple DETERMINES the frontier's
content, and an unchanged frontier hands back the identical object.
Only the current frontier's pages are retained — a fit always runs on the
newest — so the page-sized arrays do not accumulate one copy per commit.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping

import numpy as np

from ..core import CertificateConflict, ResourceKey
from ..format import TILE_CELLS, TileFormat
from .detect import readonly_array
from .records import TileRecord, parse_tile_key
from .reference import ReferenceFieldProvider, ReferencePage
from .tiles import printed_cells_for
from .view import PlaneView

#: ``(page, ty, tx)`` — one physical tile, stream-blind on purpose (the
#: conflict law is about one PLACE on the paper).
TileAddress = tuple[int, int, int]

#: The pool record's count kind for enriched sites (``LabelPool``'s
#: existing ``label_site_count_by_kind``, no new record). Its movement is
#: what makes the enrichment visible in the pool's own durable shape.
LABEL_KIND_CERTIFIED = "ctx-certified-cells"


class CertifiedLabelError(ValueError):
    """A certified reconstruction contradicts the format's own field."""


@dataclass(frozen=True)
class CertifiedTile:
    """One certificate's exact printed 64x64 field (v1 ``CertifiedTileLabels``).

    Same three fields and the same validation as the carried type: a
    non-negative three-part address, a lowercase SHA-256 identity, and a
    read-only 64x64 array of 0/1. The identity is holo2's own content
    address for the certificate (:func:`certificate_identity`) rather than
    v1's ``certificate_id``, because holo2's durable certificate IS its
    address plus its bits, and nothing else may name it.
    """

    address: TileAddress
    identity: str
    printed_cells: np.ndarray

    def __post_init__(self) -> None:
        if len(self.address) != 3 or any(
                isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, np.integer))
                or int(value) < 0 for value in self.address):
            raise ValueError(
                "certified labels need a non-negative tile address")
        if len(self.identity) != 64 or any(
                char not in "0123456789abcdef" for char in self.identity):
            raise ValueError("certificate identity must be lowercase SHA-256")
        cells = np.asarray(self.printed_cells)
        if cells.shape != (TILE_CELLS, TILE_CELLS) or not np.all(
                (cells == 0) | (cells == 1)):
            raise ValueError(
                "certified printed field must be a 64x64 bit array")
        object.__setattr__(self, "address",
                           tuple(int(value) for value in self.address))
        object.__setattr__(self, "printed_cells",
                           readonly_array(cells, np.uint8))


def certificate_identity(address: TileAddress, metadata_bit: int,
                         symbol_sha256: str) -> str:
    """The content address of one certificate's printed interpretation.

    Everything the re-encode is a function of, and nothing else: the tile
    address (which fixes the counter, the page scramble and the slot
    permutation) and the certified user bits (the metadata bit plus the
    symbol's own content address). Two stores that certified the same tile
    to the same bits mint the same identity, which is what lets the
    per-certificate cache be shared and provably stale-free.
    """
    page, ty, tx = (int(value) for value in address)
    material = f"{page}|{ty}|{tx}|{int(metadata_bit)}|{symbol_sha256}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def collate_certified(tiles: Iterable[CertifiedTile]
                      ) -> Mapping[TileAddress, CertifiedTile]:
    """Index certified fields by address — v1's conflict law, as a function.

    THE law, in the one place both the production frontier and its pin can
    reach it: a second certified field at an address that DIFFERS from the
    first is fatal and names the tile. It is never voted, never
    tie-broken, and never resolved by recency — two certificates
    disagreeing about printed cells is a breach of the zero-wrong
    invariant, not an ambiguity. An identical re-arrival is a no-op, which
    is what makes multi-stream and re-indexed inputs harmless.
    """
    by_address: dict[TileAddress, CertifiedTile] = {}
    for tile in tiles:
        prior = by_address.get(tile.address)
        if prior is None:
            by_address[tile.address] = tile
        elif not np.array_equal(prior.printed_cells, tile.printed_cells):
            raise CertificateConflict(
                "conflicting certified printed fields at tile "
                f"{tile.address}: certificates {prior.identity} and "
                f"{tile.identity} disagree")
    return MappingProxyType(dict(sorted(by_address.items())))


@dataclass(frozen=True)
class CertifiedFrontier:
    """The committed certificate frontier, conflict-free and by address."""

    frontier_id: str
    by_address: Mapping[TileAddress, CertifiedTile]
    _by_page: Mapping[int, tuple[CertifiedTile, ...]] = field(
        init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        grouped: dict[int, list[CertifiedTile]] = {}
        for address, tile in self.by_address.items():
            grouped.setdefault(address[0], []).append(tile)
        object.__setattr__(self, "_by_page", MappingProxyType(
            {page: tuple(rows) for page, rows in grouped.items()}))

    @property
    def n_tiles(self) -> int:
        return len(self.by_address)

    def of_page(self, page: int) -> tuple[CertifiedTile, ...]:
        """This page's certified tiles, in address order.

        Grouped ONCE at construction rather than filtered per call: the
        harvest asks per member pose, so a linear scan here would be
        (members x certificates) on a sheet with thousands of each.
        """
        return self._by_page.get(int(page), ())


def frontier_of(tiles: Iterable[CertifiedTile]) -> CertifiedFrontier:
    """Collate and identify one frontier (the conflict law runs here)."""
    by_address = collate_certified(tiles)
    material = "\n".join(f"{address}|{tile.identity}"
                         for address, tile in by_address.items())
    return CertifiedFrontier(
        hashlib.sha256(material.encode("utf-8")).hexdigest(), by_address)


class FormatOnlyLabels:
    """The P1 label field behind the same door as the enriched one.

    THE DEFAULT SOURCE (H5 P2 fold ruling, 2026-08-18): certified
    enrichment measured +68% on the verdicts wall (the fit walks a ~40x
    label population) with ZERO yield on every corpus measured so far —
    its value case, pools too label-poor to clear the adoption floors
    (fragments, hard sheets), is owed its measurement at P3/H6. The
    campaign's §6.2a law applies: an arm that cannot prove universal
    non-regression does not run universally. Constructing
    :class:`CertifiedLabelSource` instead of this is the whole dial
    (``CtxCalibrationProvider(row, certified_labels=True)``); flipping
    the default is a one-line change to make WITH the measurement in
    hand, not before it.
    """

    enriches = False

    def __init__(self, base: ReferenceFieldProvider) -> None:
        self._base = base
        self.spec: TileFormat = base.spec

    def field(self, plane: PlaneView) -> ReferenceFieldProvider:
        return self._base


class CertifiedLabelSource:
    """Mint-once certified reconstructions, and the enriched label field.

    Held by the calibration PROVIDER (one per row, beside its
    ``V1ReferenceField``), so the caches live exactly as long as the
    provider does and a fit fire pays for the certificates that ARRIVED
    since the last one — never for the frontier it already re-encoded.
    """

    enriches = True

    def __init__(self, base: ReferenceFieldProvider) -> None:
        self._base = base
        self.spec: TileFormat = base.spec
        # Keyed by certificate content address, and holding the whole
        # CertifiedTile rather than its cells: the validating constructor
        # COPIES its input, so caching one level lower would repeat a
        # 4096-cell copy per fit even where it repeats no re-encode.
        self._minted: dict[str, CertifiedTile] = {}
        self._keys: tuple[ResourceKey, ...] | None = None
        self._frontier: CertifiedFrontier | None = None
        self._field: _EnrichedReferenceField | None = None

    # -- the frontier ------------------------------------------------------

    def frontier(self, plane: PlaneView) -> CertifiedFrontier:
        """The committed certificate frontier of one plane.

        Keyed on ``index().certified_tiles``: certificates are TERMINAL
        and immutable (L5), so the certified work-key tuple determines the
        content, and an unchanged tuple returns the identical object with
        no store reads and no re-encodes at all.
        """
        index = plane.index()
        keys = tuple(index.certified_tiles)
        if self._frontier is not None and self._keys == keys:
            return self._frontier
        tiles: list[CertifiedTile] = []
        for key in keys:
            record = index.tiles.get(key)
            if record is None or not record.certified:
                continue
            page, ty, tx, _stream = parse_tile_key(key)
            tiles.append(self._tile(plane, (page, ty, tx), record))
        frontier = frontier_of(tiles)
        self._keys = keys
        self._frontier = frontier
        return frontier

    def _tile(self, plane: PlaneView, address: TileAddress,
              record: TileRecord) -> CertifiedTile:
        """One certified record as its printed field, minted at most once."""
        if record.bits_ref is None or record.metadata_bit is None:
            raise CertifiedLabelError(
                f"tile {address} is CERTIFIED without bits or metadata bit "
                "(L5) — no printed field can be reconstructed")
        identity = certificate_identity(address, record.metadata_bit,
                                        record.bits_ref.sha256)
        cached = self._minted.get(identity)
        if cached is not None:
            return cached
        symbol = np.asarray(plane.read_array(record.bits_ref), np.uint8)
        user_bits = np.concatenate(
            (np.asarray([record.metadata_bit], np.uint8), symbol.ravel()))
        minted = CertifiedTile(address, identity,
                               printed_cells_for(self.spec, address,
                                                 user_bits))
        self._minted[identity] = minted
        return minted

    # -- the enriched field ------------------------------------------------

    def field(self, plane: PlaneView) -> ReferenceFieldProvider:
        """The reference field a fit should label from, right now.

        The base field when nothing is certified — the SAME provider, so a
        cold pool's harvest is bit-for-bit the pre-P2 harvest — and the
        overlaid field otherwise, cached whole per frontier.
        """
        frontier = self.frontier(plane)
        if not frontier.n_tiles:
            return self._base
        if self._field is None or self._field.frontier is not frontier:
            self._field = _EnrichedReferenceField(self._base, frontier)
        return self._field


class _EnrichedReferenceField:
    """The cold-legal field, overlaid with certified reconstructions.

    A ``ReferenceFieldProvider`` by structure (``spec`` + ``page``), which
    is all ``calibration.region_populations`` ever asks for. Pages with no
    certified tile hand back the BASE page object untouched, so enrichment
    costs nothing where it buys nothing.
    """

    def __init__(self, base: ReferenceFieldProvider,
                 frontier: CertifiedFrontier) -> None:
        self._base = base
        self.spec: TileFormat = base.spec
        self.frontier = frontier
        self._pages: dict[int, ReferencePage] = {}

    def page(self, page: int) -> ReferencePage:
        cached = self._pages.get(int(page)) if isinstance(
            page, (int, np.integer)) and not isinstance(
                page, (bool, np.bool_)) else None
        if cached is not None:
            return cached
        base = self._base.page(page)        # validates the page domain
        rows = self.frontier.of_page(int(page))
        if not rows:
            return base
        minted = self._enrich(base, rows, int(page))
        self._pages[int(page)] = minted
        return minted

    @staticmethod
    def _enrich(base: ReferencePage, rows: tuple[CertifiedTile, ...],
                page: int) -> ReferencePage:
        """Overlay one page's certified fields, checking the format first.

        Tiles are disjoint, so each slice is written once and the mask
        read for the agreement check is always the BASE mask.
        """
        values = np.array(base.values, np.uint8)
        sites = np.array(base.sites, bool)
        for tile in rows:
            _page, ty, tx = tile.address
            ys = slice(ty * TILE_CELLS, (ty + 1) * TILE_CELLS)
            xs = slice(tx * TILE_CELLS, (tx + 1) * TILE_CELLS)
            known = sites[ys, xs]
            printed = tile.printed_cells
            if not np.array_equal(values[ys, xs][known], printed[known]):
                raise CertifiedLabelError(
                    f"certified reconstruction at tile {tile.address} "
                    f"(certificate {tile.identity}) disagrees with the "
                    "format field at a format-known site — the certificate "
                    "is being read at the wrong address or under a forked "
                    "keystream")
            values[ys, xs] = printed
            sites[ys, xs] = True
        return ReferencePage(page, values, sites)


__all__ = [
    "LABEL_KIND_CERTIFIED", "CertifiedFrontier", "CertifiedLabelError",
    "CertifiedLabelSource", "CertifiedTile", "FormatOnlyLabels",
    "TileAddress", "certificate_identity", "collate_certified",
    "frontier_of",
]
