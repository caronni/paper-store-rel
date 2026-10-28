"""H5 P2 pin (a): certified label cells against v1's own CertifiedTileLabels.

What P2 carries from v1 is the RE-ENCODE — a certified tile's user bits
turned back into the complete printed 64x64 field, which is what makes
every cell of that tile a trustworthy label site. v1 owns that arithmetic
in ``holo.receive.certified_refine.CertifiedTileLabels`` (minted through
``CertificateFrontier.from_certificates``, which is also where v1's
conflict law lives), so the bar here is the only trustworthy one: build a
real generator page, certify real tiles through BOTH trees' decode
chains, and byte-compare the label cells holo2's PRODUCTION harvest
publishes against the cells v1's own code mints.

Nothing is retyped — v1's values come from calling v1 (the e012 lesson:
retyped ground truth forks silently) — and the comparison is taken at two
depths, because the enrichment has two: the frontier's per-tile field,
and the enriched REFERENCE FIELD the calibration pools actually read
(``sites``/``values``), which is where a mis-slice or an off-by-one tile
offset would hide.

Both packages may be imported HERE, outside the holo2 tree, which is the
standing every oracle in this directory has.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pytest

from holo.core import fountain as h_fountain
from holo.format import metadata as h_metadata
from holo.format.descriptor import FormatSpec
from holo.format.resolve import resolve_format_ref as h_resolve_format_ref
from holo.gen.compose import compose_page_cells
from holo.gen.emit import source_packed_for
from holo.gen.plan import plan_volume
from holo.receive.certified_refine import CertificateFrontier
from holo.receive.evidence import AttemptStage as HAttemptStage
from holo.receive.payload import attempt_k_tile as h_attempt_k_tile

from holo2.core import BlobRef
from holo2.format.registry_rows import tile_format_for
from holo2.solve import tiles as h2_tiles
from holo2.solve.certified_labels import (CertifiedLabelSource,
                                          certificate_identity)
from holo2.solve.records import MintRef, TileRecord, tile_key
from holo2.solve.reference import V1ReferenceField
from holo2.format.resolve import format_row_for

# v2 IDENTITIES since 2026-08-22 (package C4, RULINGS G5), on exactly the
# tile matrices the retired 68x68 mm synthetic media used to derive (8x8
# at c3, 12x12 at c2): geometry is identity (FORMAT-SPACE §7), so the
# page is a string both trees resolve rather than two hand-built
# descriptions of one sheet.  The same three FORMATS as
# ``test_oracle_tiles.py``, which is the module this recipe is shared
# with.
FORMATS = ("c3-k-r0550@8x8", "c2-k-r0550@12x12", "c2-k-r0700@12x12")
IDEAL_LLR = 5.0
_ORACLE_SHA = "cd" * 32
STREAM = "main"


# ------------------------------------------------------------- fixtures

@dataclass(frozen=True)
class PageFixture:
    """One real generator page, on both sides' description of its format."""

    format_ref: str
    spec: FormatSpec                    # holo's
    fmt: object                         # holo2's TileFormat
    field: np.ndarray

    def tile(self, ty: int, tx: int) -> np.ndarray:
        return self.field[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]


def _build_page(format_ref: str) -> PageFixture:
    """The same real-generator recipe ``test_oracle_tiles.py`` uses."""
    spec = h_resolve_format_ref(format_ref)
    payload = hashlib.sha256(format_ref.encode()).digest() * 100
    plan = plan_volume(spec, len(payload), 0.5)
    assert plan.n_pages == 1
    source = source_packed_for(payload, plan)
    counters = np.arange(spec.tiles_per_page, dtype=np.int64)
    code = h_fountain.VolumeCode(plan.k_total, plan.symbol_bits, spec.seed,
                                 tiles_per_page=spec.tiles_per_page)
    symbols = code.encode_symbols(source, counters)
    field = compose_page_cells(spec, 0, symbols, plan.k_total)
    h_metadata.tile_bits(h_metadata.encode_metadata(0, plan.k_total),
                         counters)
    row = format_row_for(format_ref, plan.n_pages)
    return PageFixture(format_ref, spec, tile_format_for(row), field)


@pytest.fixture(scope="module")
def pages() -> dict[str, PageFixture]:
    return {format_ref: _build_page(format_ref) for format_ref in FORMATS}


def _llr_from(tile: np.ndarray) -> np.ndarray:
    return (tile.astype(np.float64) * 2.0 - 1.0) * IDEAL_LLR


class _CertifiedPlane:
    """The two reads ``CertifiedLabelSource`` makes of a plane.

    A structural stand-in for ``SessionPlane`` — an index and a blob read
    — because what is under test is the label arithmetic, not the store.
    Durable-shaped throughout: real ``TileRecord``s under real tile keys,
    the symbol reached only through a ``BlobRef``, exactly as a committed
    certificate is.
    """

    def __init__(self, certificates: dict[tuple[int, int, int], np.ndarray],
                 *, stream: str = STREAM) -> None:
        self._blobs: dict[str, np.ndarray] = {}
        tiles: dict[object, TileRecord] = {}
        for (page, ty, tx), user_bits in certificates.items():
            symbol = np.asarray(user_bits[1:], np.uint8)
            sha = hashlib.sha256(symbol.tobytes()).hexdigest()
            self._blobs[sha] = symbol
            tiles[tile_key(page, ty, tx, stream)] = TileRecord(
                minting=MintRef(tile_key(page, ty, tx, stream),
                                "scan", "oracle-profile"),
                bits_ref=BlobRef(sha, symbol.nbytes, "uint8", symbol.shape),
                metadata_bit=int(user_bits[0]))
        self._tiles = tiles

    def index(self):
        plane = self

        class _Index:
            tiles = plane._tiles
            certified_tiles = tuple(sorted(plane._tiles))
        return _Index()

    def read_array(self, ref: BlobRef) -> np.ndarray:
        return self._blobs[ref.sha256]


def _both_sides(page: PageFixture, ty: int, tx: int):
    """One tile certified through BOTH chains: v1's record, holo2's bits."""
    llr = _llr_from(page.tile(ty, tx))
    _record, certificate = h_attempt_k_tile(
        llr, page.spec, (0, ty, tx), HAttemptStage.SCAN,
        source_sha256=_ORACLE_SHA, lane_id="h5p2-oracle",
        component_block_ids=(hashlib.sha256(
            f"{page.format_ref}-{ty}-{tx}".encode()).hexdigest(),))
    attempt = h2_tiles.attempt_k_tile(
        llr, page.fmt, (0, ty, tx), h2_tiles.AttemptStage.SCAN)
    assert attempt.certified and attempt.user_bits is not None
    return certificate, attempt


ADDRESSES = ((0, 0), (1, 2), (2, 1))


# --------------------------------------------------------------- pin (a)

@pytest.mark.parametrize("format_ref", FORMATS)
def test_frontier_label_cells_are_v1_certified_tile_labels(
        pages: dict[str, PageFixture], format_ref: str) -> None:
    """Pin (a): the harvested frontier, byte-for-byte against v1's mint.

    v1's side is ``CertificateFrontier.from_certificates`` — its own
    mint-once cache, its own conflict check, its own
    ``CertifiedTileLabels`` — over the certificates v1's own decoder
    produced. holo2's side is the production
    ``CertifiedLabelSource.frontier``, walking a durable-shaped index.
    """
    page = pages[format_ref]
    certificates = []
    holo2_bits: dict[tuple[int, int, int], np.ndarray] = {}
    for ty, tx in ADDRESSES:
        certificate, attempt = _both_sides(page, ty, tx)
        certificates.append(certificate)
        holo2_bits[(0, ty, tx)] = np.asarray(attempt.user_bits, np.uint8)

    v1_frontier = CertificateFrontier.from_certificates(page.spec,
                                                        certificates)
    v1_labels = v1_frontier.by_address()

    source = CertifiedLabelSource(V1ReferenceField(page.fmt))
    h2_frontier = source.frontier(_CertifiedPlane(holo2_bits))

    assert set(h2_frontier.by_address) == set(v1_labels)
    for address, tile in h2_frontier.by_address.items():
        assert tile.printed_cells.tobytes() == (
            v1_labels[address].printed_cells.tobytes()), (
            f"certified label cells forked at {address}")
        # ... and they are the generator's own printed truth, not merely
        # agreement between two receivers.
        assert np.array_equal(tile.printed_cells,
                              page.tile(address[1], address[2]))


@pytest.mark.parametrize("format_ref", FORMATS)
def test_the_enriched_field_publishes_those_cells(
        pages: dict[str, PageFixture], format_ref: str) -> None:
    """The label field the POOLS read carries v1's cells, in place.

    The depth that matters for the harvest: ``region_populations`` reads
    ``sites``/``values`` at absolute page coordinates, so this pins the
    placement of the re-encoded tile as well as its content — every cell
    of a certified tile known and equal to v1's, and every cell outside
    one exactly as the cold-legal field had it.
    """
    page = pages[format_ref]
    certificates = []
    holo2_bits: dict[tuple[int, int, int], np.ndarray] = {}
    for ty, tx in ADDRESSES:
        certificate, attempt = _both_sides(page, ty, tx)
        certificates.append(certificate)
        holo2_bits[(0, ty, tx)] = np.asarray(attempt.user_bits, np.uint8)
    v1_labels = CertificateFrontier.from_certificates(
        page.spec, certificates).by_address()

    base = V1ReferenceField(page.fmt)
    cold = base.page(0)
    source = CertifiedLabelSource(base)
    enriched = source.field(_CertifiedPlane(holo2_bits)).page(0)

    certified_mask = np.zeros(cold.sites.shape, bool)
    for _page, ty, tx in v1_labels:
        ys, xs = slice(ty * 64, ty * 64 + 64), slice(tx * 64, tx * 64 + 64)
        certified_mask[ys, xs] = True
        assert enriched.values[ys, xs].tobytes() == (
            v1_labels[(0, ty, tx)].printed_cells.tobytes())
        assert enriched.sites[ys, xs].all(), (
            "every cell of a certified tile is a label site")
        # THE ENRICHMENT, stated where it happens: this tile went from the
        # format's ~100 predictable sites to all 4096 of its cells.
        assert cold.sites[ys, xs].sum() < 64 * 64
    assert enriched.sites.sum() == cold.sites.sum() + sum(
        64 * 64 - int(cold.sites[ty * 64:ty * 64 + 64,
                                 tx * 64:tx * 64 + 64].sum())
        for _page, ty, tx in v1_labels), (
        "enrichment adds exactly the certified tiles' unknown cells")

    outside = ~certified_mask
    assert np.array_equal(enriched.sites[outside], cold.sites[outside])
    assert np.array_equal(enriched.values[outside], cold.values[outside])


@pytest.mark.parametrize("format_ref", FORMATS)
def test_the_certified_reencode_agrees_with_the_format_field(
        pages: dict[str, PageFixture], format_ref: str) -> None:
    """Truth-path discipline: validate the re-encode on CERTIFIED tiles.

    The payload scramble is zeroed at site cells, so a healthy
    certificate's re-encode must reproduce the cold field's word and
    filler values BIT-EXACTLY. That is a real standing invariant — the
    enrichment enforces it on every mint — and this pins that it holds on
    the generator's own truth, which is what makes the enforcement a
    detector of forked keystreams rather than a tautology.
    """
    page = pages[format_ref]
    cold = V1ReferenceField(page.fmt).page(0)
    for ty, tx in ADDRESSES:
        _certificate, attempt = _both_sides(page, ty, tx)
        printed = h2_tiles.printed_cells(page.fmt, attempt)
        ys, xs = slice(ty * 64, ty * 64 + 64), slice(tx * 64, tx * 64 + 64)
        known = cold.sites[ys, xs]
        assert known.any(), "a tile always carries format-known sites"
        assert np.array_equal(printed[known], cold.values[ys, xs][known])


def test_the_identity_is_a_function_of_address_and_bits() -> None:
    """The per-certificate cache key names everything the re-encode uses.

    Address (counter, page scramble, slot permutation) and the certified
    user bits (metadata bit + symbol content address) — so two stores that
    certified one tile to one value share a mint, and any change to either
    is a different identity rather than a stale hit.
    """
    base = certificate_identity((0, 1, 2), 1, "ab" * 32)
    assert base == certificate_identity((0, 1, 2), 1, "ab" * 32)
    assert base != certificate_identity((1, 1, 2), 1, "ab" * 32)
    assert base != certificate_identity((0, 2, 1), 1, "ab" * 32)
    assert base != certificate_identity((0, 1, 2), 0, "ab" * 32)
    assert base != certificate_identity((0, 1, 2), 1, "cd" * 32)
