"""H5 P2's plumbing pins: certified reconstructions as label sites.

The carried arithmetic — the re-encode itself — is byte-compared against
v1's own ``CertifiedTileLabels`` in
``tests/holo2_oracles/test_oracle_certified_labels.py`` (pin (a)). What is
pinned HERE is the NEW plumbing, in P1's own style: durable records over a
real store, staged races over the real commit engine.

* mint-once, twice over (pin (b)): one frontier is reconstructed once and
  handed back as the SAME object, and a GROWN frontier re-encodes only
  what arrived — asserted by array identity, which is the only way to say
  "did not recompute" without counting calls;
* conflict fatality (pin (c)): two certificates disagreeing at one tile
  raise loudly and the error NAMES the tile — pinned both at the law's
  own function and end to end through a plane;
* prospective-only (pin (d)): a certificate staged but not committed
  contributes nothing at fire time, and the same certificate committed
  contributes everything — the same batch, the same fit, two answers;
* the re-arm (pin (e)): a new certificate moves the pool's member-set
  version and re-arms the FIT, while a payload decode stays current until
  an ADOPTION commits (the P1 scoping pin's sibling).

THE FIXTURE is a (2, 2)-tile c2 page whose printed ink IS four real
re-encoded tiles, so the certified labels, the cold format field and the
page's own ink are one coherent truth — and the marginal carries the same
deliberate neighbour-ink miscalibration P1's fixture uses, so the ordered
nine-bin fit has something real to learn from the enriched population.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest
from scipy import ndimage

from holo2.capture import CaptureRecord, FootingSpec, RegionRecord
from holo2.capture import capture_key, region_key
from holo2.core import (CertificateConflict, FootingId, ProgressSink,
                        ResourceKey)
from holo2.core.blobs import stage_array
from holo2.core.commit import CommitBatch, CommitEngine, Write
from holo2.core.store import Store
from holo2.solve import calibration, payload
from holo2.solve.calibration import CtxFitWorker, ctx_pool_key
from holo2.solve.certified_labels import (LABEL_KIND_CERTIFIED,
                                          CertifiedLabelError,
                                          CertifiedLabelSource, CertifiedTile,
                                          FormatOnlyLabels,
                                          collate_certified, frontier_of)
from holo2.solve.records import (COLLECTION_CERTIFIED, EvidenceObservation,
                                 MintRef, PoseRecord, TileRecord,
                                 WindowRecord, WindowStatus,
                                 calibration_collection_key, calibration_key,
                                 evidence_key, pack_observed_cells, tile_key,
                                 window_key)
from holo2.solve.records import CalibrationRecord, HeldoutGate
from holo2.solve.reference import V1ReferenceField
from holo2.solve.tiles import printed_cells_for
from holo2.solve.tilemap import StoreIndex, TileMap
from holo2.format.format_v1 import tile_format
from holo2.format.registry_rows import format_row

SPEC = tile_format("c2-k-r0550", (2, 2))
STREAM = "main"
TILE = 64

CAPTURE = "ab" * 32
FOOTING = FootingId("cap:1/1")
REGION = region_key(CAPTURE, (0, 0), 8, (128, 128))
IDENTITY_AFFINE = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)

WINDOW_A = window_key(FOOTING, REGION, (0, 0, 128, 128))
POSE_A = PoseRecord(WINDOW_A, FOOTING, 0, IDENTITY_AFFINE)
POOL = ctx_pool_key(FOOTING, REGION)

ALL_TILES = ((0, 0), (0, 1), (1, 0), (1, 1))

#: Seeded user bits per tile, and the printed field they re-encode to.
#: The page's INK is those four fields, so a certified label, the cold
#: format field and the ink under the detector are one truth.
_RNG = np.random.default_rng(20260818)
USER_BITS = {
    (ty, tx): _RNG.integers(0, 2, SPEC.tile_user_bits, dtype=np.uint8)
    for ty, tx in ALL_TILES
}
PRINTED = {
    (ty, tx): printed_cells_for(SPEC, (0, ty, tx), bits)
    for (ty, tx), bits in USER_BITS.items()
}

_INK = np.zeros(SPEC.cells_yx, bool)
for _ty, _tx in ALL_TILES:
    _INK[_ty * TILE:(_ty + 1) * TILE,
         _tx * TILE:(_tx + 1) * TILE] = PRINTED[(_ty, _tx)].astype(bool)

_KERNEL = np.ones((3, 3), np.uint8)
_KERNEL[1, 1] = 0
_COUNTS = ndimage.convolve(_INK.astype(np.uint8), _KERNEL,
                           mode="constant", cval=0)
PAGE_LLR = ((2.0 * _INK.astype(np.float64) - 1.0) * 2.0
            + 0.35 * (_COUNTS.astype(np.float64) - 4.0))

_MASK = stage_array(np.ones(16, np.uint8))
_MARGINAL_PARAMS = stage_array(np.zeros(2, np.float64))
_REFERENCE = V1ReferenceField(SPEC)


def _tile_llr(ty: int, tx: int) -> np.ndarray:
    return PAGE_LLR[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE]


# ------------------------------------------------------------- the ground

def _ground() -> list[Write]:
    return [
        Write(capture_key(CAPTURE), CaptureRecord(
            source_sha256=CAPTURE, dpi_true=1200.0, shape_px=(1024, 1024),
            dtype="uint8", channels=1, platen_backing=200.0,
            footings=(FootingSpec(FOOTING, Fraction(1), CAPTURE),))),
        Write(REGION, RegionRecord(
            capture_sha256=CAPTURE, support_mask_ref=_MASK.ref, pitch_in_vote=Fraction(8, 600),
            support_origin_px=(0, 0), support_step_px=8,
            support_extent_px=(128, 128))),
    ]


def _placement(pose: PoseRecord) -> tuple[list[Write], list]:
    """One committed full-page placement with its per-tile pieces."""
    marginal = calibration_key(pose.window_id, "pava-v1",
                               _MARGINAL_PARAMS.ref.sha256)
    writes: list[Write] = [
        Write(pose.window_id, WindowRecord(
            pose.footing_id, REGION, (0, 0, 128, 128), WindowStatus.ACTIVE)),
        Write(marginal, CalibrationRecord(
            scope=pose.window_id, algorithm="pava-v1",
            params_ref=_MARGINAL_PARAMS.ref,
            heldout=HeldoutGate(adopted=True, logloss_delta=-0.1))),
        Write(pose.resource_key(), pose),
    ]
    blobs = []
    for ty, tx in ALL_TILES:
        seen = np.ones((TILE, TILE), bool)
        blob = stage_array(_tile_llr(ty, tx).astype(np.float32))
        mask = stage_array(pack_observed_cells(seen))
        blobs.extend((blob, mask))
        writes.append(Write(
            evidence_key(pose.footing_id, 0, ty, tx, STREAM,
                         pose.resource_key()),
            EvidenceObservation(
                footing_id=pose.footing_id, page=0, ty=ty, tx=tx,
                stream=STREAM, pose_id=pose.resource_key(),
                llr_ref=blob.ref, observed_ref=mask.ref,
                calibration_id=marginal)))
    return writes, blobs


def _certificate(ty: int, tx: int, *, bits: np.ndarray | None = None,
                 stream: str = STREAM) -> tuple[Write, object]:
    """One committed certificate at (0, ty, tx), durable-shaped."""
    user_bits = USER_BITS[(ty, tx)] if bits is None else bits
    symbol = stage_array(np.asarray(user_bits[1:], np.uint8))
    return Write(tile_key(0, ty, tx, stream), TileRecord(
        minting=MintRef(POSE_A.resource_key(), "scan", "test-profile"),
        bits_ref=symbol.ref, metadata_bit=int(user_bits[0]),
        observed_by=(FOOTING,))), symbol


def _seed(store: Store, *, certified: tuple[tuple[int, int], ...] = ()
          ) -> CommitEngine:
    engine = CommitEngine(store)
    writes, blobs = _placement(POSE_A)
    writes = list(_ground()) + writes
    blobs = [_MASK, _MARGINAL_PARAMS] + blobs
    for ty, tx in certified:
        write, symbol = _certificate(ty, tx)
        writes.append(write)
        blobs.append(symbol)
    engine.apply(CommitBatch(writes=tuple(writes), blobs=tuple(blobs)))
    return engine


class _View:
    """The plane reads the calibration and payload paths make, over a store."""

    def __init__(self, store: Store) -> None:
        self._store = store
        self._index = StoreIndex.build(store)
        self._tiles = TileMap(self._index, (STREAM,), (2, 2))

    def index(self) -> StoreIndex:
        return self._index

    def record(self, key: ResourceKey) -> object | None:
        return self._store.get(key)

    def read_array(self, ref) -> np.ndarray:
        return self._store.read_array(ref)

    def tile(self, key: ResourceKey):
        return self._tiles.record(key)

    def evidence_on(self, key: ResourceKey) -> tuple[ResourceKey, ...]:
        return self._index.evidence_by_tile.get(key, ())

    def has_footing(self, footing_id: str) -> bool:
        return True


def _worker(source: CertifiedLabelSource | None = None) -> CtxFitWorker:
    return CtxFitWorker(POOL, FOOTING, REGION,
                        source or CertifiedLabelSource(_REFERENCE))


def _fire(engine: CommitEngine, source: CertifiedLabelSource | None = None):
    worker = _worker(source)
    result = worker.run(_View(engine.store), (), ProgressSink("fit"))
    if result.writes or result.blobs:
        return result, engine.apply(CommitBatch(writes=result.writes,
                                                blobs=result.blobs))
    return result, None


# ------------------------------------------------- the enrichment happens

def test_a_certified_tile_makes_every_one_of_its_cells_a_label(
        new_store) -> None:
    """The point of P2, on the harvest the fit actually runs.

    One certificate turns its tile from the format's ~100 predictable
    sites into 4096 label sites, and the values are the printed truth the
    page's own ink was built from — so the pooled population grows by
    exactly that tile's previously-unknown cells.
    """
    cold = _seed(new_store("cold"))
    warm = _seed(new_store("warm"), certified=((0, 0),))
    reference_cold = CertifiedLabelSource(_REFERENCE).field(
        _View(cold.store))
    reference_warm = CertifiedLabelSource(_REFERENCE).field(
        _View(warm.store))

    members = (POSE_A.resource_key(),)
    s_cold, v_cold = calibration.region_populations(
        _View(cold.store), reference_cold, FOOTING, members)
    s_warm, v_warm = calibration.region_populations(
        _View(warm.store), reference_warm, FOOTING, members)

    grew = (s_warm.labels.size + v_warm.labels.size) - (
        s_cold.labels.size + v_cold.labels.size)
    # Derived independently of the production path: the harvest keeps
    # cells with a COMPLETE eight-neighbourhood, and over a fully observed
    # page the only incomplete ones in tile (0, 0) are the page's own
    # first row and column. So the enrichment adds exactly the tile's
    # valid cells that the format could not already predict.
    valid = np.ones((TILE, TILE), bool)
    valid[0, :] = valid[:, 0] = False
    known = _REFERENCE.page(0).sites[:TILE, :TILE]
    assert grew == int((valid & ~known).sum()) > 3800
    # ... and the new labels are TRUE: the enriched field's values over the
    # certified tile are the printed cells the page's ink was built from.
    page = reference_warm.page(0)
    assert np.array_equal(page.values[:TILE, :TILE], PRINTED[(0, 0)])
    assert page.sites[:TILE, :TILE].all()


def test_the_enriched_fit_adopts_on_the_certified_population(
        new_store) -> None:
    """End to end: the enriched pool fits, adopts, and records the count.

    The pool record carries the enrichment in its EXISTING
    ``label_site_count_by_kind`` field — no new record kind — which is
    also what moves the pool's member-set version.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1)))
    result, commit = _fire(engine)
    assert result.outcome == calibration.OUTCOME_ADOPTED
    assert commit is not None

    pool = engine.store.get(POOL)
    assert pool is not None
    counts = pool.label_site_counts()
    assert counts[LABEL_KIND_CERTIFIED] == 2
    assert counts["ctx-search"] > 0 and counts["ctx-validation"] > 0


# --------------------------------------------------- mint-once (pin (b))

def test_one_frontier_is_reconstructed_once(new_store) -> None:
    """Pin (b): the same frontier hands back the same object.

    Certificates are terminal and immutable (L5), so the certified
    work-key tuple DETERMINES the frontier's content — which is what makes
    "no change, no work" exact rather than optimistic.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1)))
    source = CertifiedLabelSource(_REFERENCE)
    view = _View(engine.store)

    first = source.frontier(view)
    assert source.frontier(view) is first, "an unchanged frontier is one mint"
    assert source.frontier(_View(engine.store)) is first, (
        "and it is the CONTENT that decides, not the view object")
    assert source.field(view) is source.field(view)
    # The enriched page is minted once too.
    assert source.field(view).page(0) is source.field(view).page(0)


def test_a_grown_frontier_re_encodes_only_what_arrived(new_store) -> None:
    """Pin (b)'s stronger half, asserted by ARRAY IDENTITY.

    A new certificate must not re-encode the ones already minted: the
    retained tiles come back as the very same arrays, which is the only
    statement of "did not recompute" that cannot be faked by an equal
    value.
    """
    engine = _seed(new_store(), certified=((0, 0),))
    source = CertifiedLabelSource(_REFERENCE)
    before = source.frontier(_View(engine.store))
    held = before.by_address[(0, 0, 0)].printed_cells

    write, symbol = _certificate(0, 1)
    engine.apply(CommitBatch(writes=(write,), blobs=(symbol,)))
    after = source.frontier(_View(engine.store))

    assert after is not before and after.n_tiles == 2
    assert after.by_address[(0, 0, 0)].printed_cells is held, (
        "the retained certificate must not be re-encoded")
    assert np.array_equal(after.by_address[(0, 0, 1)].printed_cells,
                          PRINTED[(0, 1)])


# ---------------------------------------------- conflict fatality (pin c)

def test_conflicting_certified_fields_at_one_tile_are_fatal() -> None:
    """Pin (c) at the law's own function: loud, and it names the tile."""
    cells = PRINTED[(0, 0)]
    other = cells.copy()
    other[7, 9] ^= 1
    left = CertifiedTile((0, 3, 4), "a" * 64, cells)
    right = CertifiedTile((0, 3, 4), "b" * 64, other)

    with pytest.raises(CertificateConflict) as raised:
        collate_certified((left, right))
    message = str(raised.value)
    assert "(0, 3, 4)" in message, "the error must name the tile"
    assert "a" * 64 in message and "b" * 64 in message

    # An identical re-arrival is NOT a conflict — that is what makes a
    # re-indexed or multi-stream input harmless rather than fatal.
    same = CertifiedTile((0, 3, 4), "c" * 64, cells.copy())
    assert set(collate_certified((left, same))) == {(0, 3, 4)}
    assert frontier_of((left, same)).n_tiles == 1


def test_a_disagreeing_second_stream_is_fatal_end_to_end(new_store) -> None:
    """Pin (c) through the production frontier, over a real store.

    The conflict law is about one PLACE on the paper, so the harvest
    groups by address across streams: a second certified record at one
    tile whose bits re-encode differently is refused, loudly, by name.
    """
    engine = _seed(new_store(), certified=((0, 0),))
    rogue_bits = USER_BITS[(1, 1)]      # different bits, same address
    write, symbol = _certificate(0, 0, bits=rogue_bits, stream="rogue")
    engine.apply(CommitBatch(writes=(write,), blobs=(symbol,)))

    source = CertifiedLabelSource(_REFERENCE)
    with pytest.raises(CertificateConflict) as raised:
        source.frontier(_View(engine.store))
    assert "(0, 0, 0)" in str(raised.value)


def test_a_reencode_that_contradicts_the_format_is_fatal() -> None:
    """The live half of the truth-path discipline, and its own error.

    The payload scramble is zeroed at site cells, so a healthy certificate
    reproduces the format's word and filler values exactly. A field that
    does not is a certificate read at the wrong address or under a forked
    keystream — caught before one wrong label enters a fit.
    """
    forged = PRINTED[(0, 0)].copy()
    sites = _REFERENCE.page(0).sites[:TILE, :TILE]
    ys, xs = np.nonzero(sites)
    forged[ys[0], xs[0]] ^= 1           # one format-known site, flipped

    class _Frontier:
        by_address = {(0, 0, 0): CertifiedTile((0, 0, 0), "d" * 64, forged)}

        @staticmethod
        def of_page(page):
            return (_Frontier.by_address[(0, 0, 0)],)

    from holo2.solve.certified_labels import _EnrichedReferenceField

    field = _EnrichedReferenceField(_REFERENCE, _Frontier())
    with pytest.raises(CertifiedLabelError) as raised:
        field.page(0)
    assert "(0, 0, 0)" in str(raised.value)
    assert "d" * 64 in str(raised.value)


# ------------------------------------------------- prospective-only (d)

def test_an_uncommitted_certificate_contributes_nothing(new_store) -> None:
    """Pin (d): staged is not committed, and only committed is truth.

    The same certificate, the same fit, two answers — before the commit
    the enriched field is the cold field itself (the SAME provider
    object, so the pre-P2 harvest is bit-for-bit intact), and after it the
    tile's every cell is a label.
    """
    engine = _seed(new_store())
    source = CertifiedLabelSource(_REFERENCE)

    write, symbol = _certificate(0, 0)   # staged, deliberately NOT applied
    batch = CommitBatch(writes=(write,), blobs=(symbol,))
    view = _View(engine.store)
    assert source.frontier(view).n_tiles == 0
    assert source.field(view) is _REFERENCE, (
        "with nothing committed the fit labels from the cold field itself")
    before, _ = _fire(engine, source)
    pool_before = engine.store.get(POOL).label_site_counts()
    assert pool_before[LABEL_KIND_CERTIFIED] == 0

    engine.apply(batch)                  # ... now it is committed
    after_view = _View(engine.store)
    assert source.frontier(after_view).n_tiles == 1
    assert source.field(after_view) is not _REFERENCE
    after, _ = _fire(engine, source)
    assert engine.store.get(POOL).label_site_counts()[
        LABEL_KIND_CERTIFIED] == 1
    assert before.outcome == after.outcome == calibration.OUTCOME_ADOPTED


# ------------------------------------------------------ the re-arm (e)

def test_a_new_certificate_re_arms_the_fit_but_not_a_decode(
        new_store) -> None:
    """Pin (e), the P1 scoping pin's sibling.

    A certificate is new LABEL material, so the fit's read-set names
    ``COLLECTION_CERTIFIED`` — the collection the tile family already
    declares — and a new one re-arms it. A payload decode subscribes to
    exactly one region-scoped key (the pool's calibration collection,
    versioned on ADOPTION only), so the same certificate leaves it
    current: labels move fits, only adoptions move decodes.
    """
    engine = _seed(new_store(), certified=((0, 0),))
    fit = _worker()
    decode = payload.RealPayloadWorker(
        tile_key(0, 1, 1, STREAM), SPEC,
        stage=payload.tile_chain.AttemptStage.SCAN, scope=str(FOOTING))
    view = _View(engine.store)

    fit_keys = fit.read_keys(view)
    decode_keys = decode.read_keys(view)
    assert COLLECTION_CERTIFIED in fit_keys, (
        "the enriched half of the population re-arms on the EXISTING "
        "certified collection — no new wake kind")
    assert COLLECTION_CERTIFIED not in decode_keys
    assert calibration_collection_key(POOL) in decode_keys

    fit_identity = engine.attempt_identity(fit_keys)
    decode_identity = engine.attempt_identity(decode_keys)

    write, symbol = _certificate(0, 1)          # a NEW certificate lands
    engine.apply(CommitBatch(writes=(write,), blobs=(symbol,)))
    fresh = _View(engine.store)

    assert not engine.is_current(fit.read_keys(fresh), fit_identity), (
        "a new certificate is new label material: the fit re-arms")
    assert engine.is_current(decode.read_keys(fresh), decode_identity), (
        "... and a decode is untouched until an ADOPTION commits")

    _fire(engine)                               # now the fit adopts
    assert not engine.is_current(
        decode.read_keys(_View(engine.store)), decode_identity), (
        "the adoption is what re-arms the decode")


def test_the_enrichment_is_dialed_and_defaults_to_format_only(
        new_store) -> None:
    """The fold ruling's pin (H5 P2, 2026-08-18).

    Enrichment measured +68% on the verdicts wall with zero yield on
    every corpus measured so far, so it is DIALED and the default is
    format-only (§6.2a: an arm that cannot prove universal
    non-regression does not run universally; the yield case — pools too
    label-poor to clear the adoption floors — is owed its measurement).
    A format-only fit also reads NO certified collection: its labels
    cannot move with a certificate, so subscribing one would spend once
    per certificate batch for nothing.
    """
    engine = _seed(new_store(), certified=((0, 0),))
    view = _View(engine.store)
    plain = CtxFitWorker(POOL, FOOTING, REGION,
                         FormatOnlyLabels(_REFERENCE))
    enriched = _worker()
    assert COLLECTION_CERTIFIED not in plain.read_keys(view)
    assert COLLECTION_CERTIFIED in enriched.read_keys(view)
    row = format_row("c2-k-r0550", (2, 2))
    assert not calibration.CtxCalibrationProvider(row)._labels.enriches, (
        "the DEFAULT provider is format-only — flip it only with the "
        "measured yield case in hand")
    assert calibration.CtxCalibrationProvider(
        row, certified_labels=True)._labels.enriches


def test_the_pool_member_set_version_moves_with_the_enrichment(
        new_store) -> None:
    """Pin (e)'s durable half: enrichment versions the pool record.

    The pool's own key is what carries the label population's high-water
    mark, and a certificate that adds labels moves it — through the
    EXISTING ``LabelPool`` field, with no new durable state.
    """
    engine = _seed(new_store(), certified=((0, 0),))
    _fire(engine)
    first = engine.table.version(POOL)
    assert engine.store.get(POOL).label_site_counts()[
        LABEL_KIND_CERTIFIED] == 1

    write, symbol = _certificate(0, 1)
    engine.apply(CommitBatch(writes=(write,), blobs=(symbol,)))
    _fire(engine)
    assert engine.table.version(POOL) > first
    assert engine.store.get(POOL).label_site_counts()[
        LABEL_KIND_CERTIFIED] == 2


def test_the_certified_frontier_is_not_quarantine_filtered(
        new_store) -> None:
    """Done is inviolable: a condemned POSE does not un-certify bits.

    Quarantine is a judgement about GEOMETRY. The pose-scoped half of the
    harvest still filters on it at pool assembly (P1's pin); the
    certificate frontier does not, because whether the bits under a
    placement decoded is not a question the placement's condemnation
    answers.
    """
    from dataclasses import replace

    engine = _seed(new_store(), certified=((0, 0),))
    engine.apply(CommitBatch(writes=(
        Write(POSE_A.resource_key(), replace(POSE_A, quarantined=True)),)))
    view = _View(engine.store)

    assert calibration.pool_members(view, FOOTING, REGION) == (), (
        "the POSE is condemned and leaves the pool")
    assert CertifiedLabelSource(_REFERENCE).frontier(view).n_tiles == 1, (
        "the CERTIFICATE stands: done is inviolable")


def test_a_certificate_without_bits_is_refused(new_store) -> None:
    """L5, stated where the label harvest would otherwise invent a field."""
    engine = _seed(new_store())
    symbol = stage_array(np.asarray(USER_BITS[(0, 0)][1:], np.uint8))
    engine.apply(CommitBatch(writes=(
        Write(tile_key(0, 0, 0, STREAM), TileRecord(
            minting=MintRef(POSE_A.resource_key(), "scan", "test-profile"),
            bits_ref=symbol.ref, metadata_bit=None)),), blobs=(symbol,)))
    with pytest.raises(CertifiedLabelError) as raised:
        CertifiedLabelSource(_REFERENCE).frontier(_View(engine.store))
    assert "(0, 0, 0)" in str(raised.value)
