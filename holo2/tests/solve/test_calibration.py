"""H5 P1's plumbing pins: the region ctx arm around the carried fit.

The fit arithmetic itself is character-pinned in
``tests/holo2_oracles/test_oracle_tiles.py`` and byte-compared against
v1's own code in ``tests/holo2_oracles/test_oracle_ctx_apply.py`` (pin
(a)); what is pinned HERE is the NEW plumbing, in the placement carry's
own style — durable records over a real store, staged races over the
real commit engine:

* the LabelPool assembly: committed placements only, quarantine filtered
  at pool assembly (``is_quarantined``'s third reader);
* adopt AND refuse both exercised, the refusal committing its reason,
  and the refused path proven bit-identical to pre-H5 (pin (b));
* bin −1 cells untouched by the applied correction (pin (c));
* duplicate observations of one physical label weigh ONE in the pooled
  fit (pin (d)) — asserted the strong way, as byte-identical params;
* the re-arm race, staged (pin (e), the W5 staleness pin's sibling): a
  decode in flight when its region's fit adopts dies stale at the wall's
  existing check and re-decodes CALIBRATED.

The fixture is the one geometry every number here is derived from: a
(2, 2)-tile c2 page, one full-page placement whose per-tile pieces carry
a marginal LLR with a DELIBERATE neighbour-ink miscalibration
(``0.35 * (count - 4)``), so the ordered nine-bin correction has
something real and monotone to learn — and adopts.
"""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import numpy as np
from scipy import ndimage

from holo2.capture import CaptureRecord, FootingSpec, RegionRecord
from holo2.capture import capture_key, region_key
from holo2.core import FootingId, ProgressSink, ResourceKey
from holo2.core.blobs import stage_array
from holo2.core.commit import CommitBatch, CommitEngine, Write
from holo2.core.store import Store
from holo2.solve import calibration, ctx_apply, detect, payload
from holo2.solve.calibration import CtxFitWorker, ctx_pool_key, pool_members
from holo2.solve.ctx_apply import (apply_component_context,
                                   component_corrections)
from holo2.solve.records import (CalibrationRecord, EvidenceObservation,
                                 HeldoutGate, PoseRecord, WindowRecord,
                                 WindowStatus, calibration_collection_key,
                                 calibration_key, evidence_key,
                                 pack_observed_cells,
                                 region_pose_collection_key, tile_key,
                                 window_key)
from holo2.solve.certified_labels import CertifiedLabelSource
from holo2.solve.reference import V1ReferenceField
from holo2.solve.tilemap import StoreIndex, TileMap
from holo2.format.format_v1 import tile_format

SPEC = tile_format("c2-k-r0550", (2, 2))
STREAM = "main"
TILE = 64

CAPTURE = "ab" * 32
FOOTING = FootingId("cap:1/1")
SPARSE_FOOTING = FootingId("cap:2/1")
REGION = region_key(CAPTURE, (0, 0), 8, (128, 128))
IDENTITY_AFFINE = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)

WINDOW_A = window_key(FOOTING, REGION, (0, 0, 128, 128))
WINDOW_B = window_key(FOOTING, REGION, (0, 0, 64, 128))
WINDOW_SPARSE = window_key(SPARSE_FOOTING, REGION, (0, 0, 128, 128))
POSE_A = PoseRecord(WINDOW_A, FOOTING, 0, IDENTITY_AFFINE)
POSE_B = PoseRecord(WINDOW_B, FOOTING, 0, IDENTITY_AFFINE)
POSE_SPARSE = PoseRecord(WINDOW_SPARSE, SPARSE_FOOTING, 0, IDENTITY_AFFINE)

POOL = ctx_pool_key(FOOTING, REGION)
SPARSE_POOL = ctx_pool_key(SPARSE_FOOTING, REGION)

#: The page's marginal LLR, derived once: printed ink is the reference
#: field's values at format-known sites and a seeded draw elsewhere, and
#: the miscalibration is additive in the true neighbour-ink count with a
#: magnitude (0.35 * |count - 4| <= 1.4 < 2.0) that can never flip the
#: sign — so provisional ink recomputed from the LLR at fire time is the
#: printed ink, exactly.
_REFERENCE = V1ReferenceField(SPEC)
_PAGE = _REFERENCE.page(0)
_RNG = np.random.default_rng(7)
_INK = _RNG.random(SPEC.cells_yx) < 0.45
_INK[_PAGE.sites] = _PAGE.values[_PAGE.sites].astype(bool)
_KERNEL = np.ones((3, 3), np.uint8)
_KERNEL[1, 1] = 0
_COUNTS = ndimage.convolve(_INK.astype(np.uint8), _KERNEL,
                           mode="constant", cval=0)
PAGE_LLR = ((2.0 * _INK.astype(np.float64) - 1.0) * 2.0
            + 0.35 * (_COUNTS.astype(np.float64) - 4.0))

_MASK = stage_array(np.ones(16, np.uint8))
_MARGINAL_PARAMS = stage_array(np.zeros(2, np.float64))


def _tile_llr(ty: int, tx: int) -> np.ndarray:
    return PAGE_LLR[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE]


def _ground() -> list[Write]:
    return [
        Write(capture_key(CAPTURE), CaptureRecord(
            source_sha256=CAPTURE, dpi_true=1200.0, shape_px=(1024, 1024),
            dtype="uint8", channels=1, platen_backing=200.0,
            footings=(FootingSpec(FOOTING, Fraction(1), CAPTURE),
                      FootingSpec(SPARSE_FOOTING, Fraction(2), CAPTURE)))),
        Write(REGION, RegionRecord(
            capture_sha256=CAPTURE, support_mask_ref=_MASK.ref, pitch_in_vote=Fraction(8, 600),
            support_origin_px=(0, 0), support_step_px=8,
            support_extent_px=(128, 128))),
    ]


def _placement(pose: PoseRecord, tiles: tuple[tuple[int, int], ...], *,
               observed: np.ndarray | None = None
               ) -> tuple[tuple[Write, ...], tuple]:
    """One committed placement: window, pose, marginal fit, tile pieces."""
    marginal = calibration_key(pose.window_id, "pava-v1",
                               _MARGINAL_PARAMS.ref.sha256)
    writes: list[Write] = [
        Write(pose.window_id, WindowRecord(
            pose.footing_id, REGION,
            (0, 0, 128, 128) if pose is not POSE_B else (0, 0, 64, 128),
            WindowStatus.ACTIVE)),
        Write(marginal, CalibrationRecord(
            scope=pose.window_id, algorithm="pava-v1",
            params_ref=_MARGINAL_PARAMS.ref,
            heldout=HeldoutGate(adopted=True, logloss_delta=-0.1))),
        Write(pose.resource_key(), pose),
    ]
    blobs = []
    for ty, tx in tiles:
        seen = (np.ones((TILE, TILE), bool) if observed is None
                else observed)
        llr = np.where(seen, _tile_llr(ty, tx), 0.0)
        blob = stage_array(llr.astype(np.float32))
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
    return tuple(writes), tuple(blobs)


ALL_TILES = ((0, 0), (0, 1), (1, 0), (1, 1))


def _seed(store: Store, *, poses: tuple[PoseRecord, ...] = (POSE_A,)
          ) -> CommitEngine:
    engine = CommitEngine(store)
    writes = list(_ground())
    blobs = [_MASK, _MARGINAL_PARAMS]
    for pose in poses:
        if pose is POSE_B:
            tiles: tuple[tuple[int, int], ...] = ((0, 0), (0, 1))
            observed = None
        elif pose is POSE_SPARSE:
            tiles = ((0, 0),)
            observed = np.zeros((TILE, TILE), bool)
            observed[:20, :20] = True       # a handful of known sites
        else:
            tiles = ALL_TILES
            observed = None
        placement, staged = _placement(pose, tiles, observed=observed)
        writes.extend(placement)
        blobs.extend(staged)
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


def _worker(footing: FootingId = FOOTING) -> CtxFitWorker:
    # A FRESH label source per worker: the caches are the provider's in
    # production, and a test that shared one would hide a recompute bug.
    return CtxFitWorker(ctx_pool_key(footing, REGION), footing, REGION,
                        CertifiedLabelSource(_REFERENCE))


def _fire(engine: CommitEngine, footing: FootingId = FOOTING):
    """Run one fit and commit what it proposed, as the engine would."""
    worker = _worker(footing)
    result = worker.run(_View(engine.store), (), ProgressSink("fit"))
    if result.writes or result.blobs:
        return result, engine.apply(CommitBatch(writes=result.writes,
                                                blobs=result.blobs))
    return result, None


# --------------------------------------------------------- pool assembly

def test_the_pool_is_committed_members_quarantine_filtered(new_store) -> None:
    """Prospective-only, and ``is_quarantined`` as the third reader.

    Labels come from format-known cells of COMMITTED placements only, and
    a condemned placement leaves the pool at ASSEMBLY — the same one-line
    predicate the consult and the payload read-set already ask, because
    "never offered", "never decoded" and "never labels" must not drift.
    """
    engine = _seed(new_store(), poses=(POSE_A, POSE_B))
    view = _View(engine.store)
    assert pool_members(view, FOOTING, REGION) == tuple(sorted(
        (POSE_A.resource_key(), POSE_B.resource_key())))

    engine.apply(CommitBatch(writes=(
        Write(POSE_B.resource_key(), replace(POSE_B, quarantined=True)),)))
    assert pool_members(_View(engine.store), FOOTING, REGION) == (
        POSE_A.resource_key(),)


def test_the_fit_descriptor_frontier_is_the_pool_scopes(new_store) -> None:
    """Eligibility is expansion: no member, no descriptor (§3a)."""
    engine = _seed(new_store(), poses=(POSE_A, POSE_SPARSE))
    scopes = calibration.pool_scopes(_View(engine.store))
    assert scopes == tuple(sorted(((FOOTING, REGION),
                                   (SPARSE_FOOTING, REGION))))


# ----------------------------------------------- adopt AND refuse (pin b)

def test_an_adopting_fit_commits_the_record_and_bumps_adoption(
        new_store) -> None:
    """The adopt half of pin (b), over durable records.

    The fixture's marginal carries a monotone neighbour-ink bias, so the
    carried held-out gate ADOPTS; the record lands under (pool,
    algorithm, params address); the pool record lands grow-only; and the
    pool's calibration collection — the ONE region-scoped key a decode
    subscribes to — moves from absent to one member ON the adoption.
    """
    engine = _seed(new_store())
    before = engine.table.version(calibration_collection_key(POOL))
    result, commit = _fire(engine)
    assert result.outcome == calibration.OUTCOME_ADOPTED
    assert commit is not None

    fits = StoreIndex.build(engine.store).context_fits.get(POOL, ())
    assert len(fits) == 1
    record = engine.store.get(fits[0])
    assert isinstance(record, CalibrationRecord)
    assert record.heldout.adopted and record.heldout.refusal_reason is None
    assert record.scope == POOL and record.algorithm == "ctx-pava-v1"
    # The nine offsets are non-increasing in the bin — the ordered model
    # the carried fit is constrained to, learned off the planted bias.
    offsets = np.asarray(engine.store.read_array(record.params_ref))[:9]
    assert np.all(np.diff(offsets) <= 1e-10) and offsets[0] > offsets[-1]

    pool = engine.store.get(POOL)
    assert pool is not None and WINDOW_A in pool.member_window_ids
    assert engine.table.version(calibration_collection_key(POOL)) == (
        before + 1), "adoption is exactly what versions the subscription key"


def test_a_refused_fit_commits_its_reason_and_wakes_nobody(
        new_store) -> None:
    """The refuse half of pin (b): reason durable, adoption key untouched.

    The sparse footing's one 20x20 corner cannot clear the carried
    floors, so the fit refuses INSIDE the fit — no chain of workers — and
    commits the refusal as a CalibrationRecord whose held-out gate names
    the reason. The pool's calibration collection does not move: a decode
    never wakes on a refusal.
    """
    engine = _seed(new_store(), poses=(POSE_A, POSE_SPARSE))
    before = engine.table.version(calibration_collection_key(SPARSE_POOL))
    result, commit = _fire(engine, SPARSE_FOOTING)
    assert result.outcome.startswith(calibration.OUTCOME_REFUSED_PREFIX)
    assert commit is not None

    assert StoreIndex.build(engine.store).context_fits.get(
        SPARSE_POOL, ()) == (), "a refusal never enters the adopted index"
    refusals = [record for key in engine.store.keys()
                if key.kind == "calibration"
                for record in (engine.store.get(key),)
                if isinstance(record, CalibrationRecord)
                and record.scope == SPARSE_POOL]
    assert len(refusals) == 1
    assert not refusals[0].heldout.adopted
    assert refusals[0].heldout.refusal_reason == result.outcome[
        len(calibration.OUTCOME_REFUSED_PREFIX):]
    assert engine.table.version(
        calibration_collection_key(SPARSE_POOL)) == before


def test_the_refused_path_is_bit_identical_to_pre_h5(new_store) -> None:
    """Pin (b)'s cheapest and most important regression bar, unit form.

    With no ADOPTED fit standing — refusals included — the payload fire's
    assembled tensor is the SAME OBJECT the freeze produced: the null
    correction is the identity, no copy, no arithmetic, so the refused
    path is bit-for-bit the pre-H5 path by construction.
    """
    engine = _seed(new_store(), poses=(POSE_A, POSE_SPARSE))
    _fire(engine, SPARSE_FOOTING)               # a REFUSED record stands
    view = _View(engine.store)
    worker = payload.RealPayloadWorker(
        tile_key(0, 0, 0, STREAM), SPEC,
        stage=payload.tile_chain.AttemptStage.SCAN, scope=str(FOOTING))
    evidence = worker._evidence_keys(view)
    fits = worker._fits(view, evidence)
    pieces = worker._pieces(view, evidence, fits)
    assert pieces
    owner, owners, bins = payload.RealPayloadWorker._freeze_with_owners(
        list(pieces))
    assert component_corrections(view, owners) == ()
    assert apply_component_context(
        owner.llr, owner.observed, (), bins) is owner.llr
    llr, _pose, _contributors = worker._decoder_input(view, pieces, fits)
    assert np.array_equal(llr, owner.llr)


# ------------------------------------------------------- bin −1 (pin c)

def test_bin_minus_one_cells_keep_their_marginal(new_store) -> None:
    """Pin (c): incomplete neighbourhoods are untouched, byte for byte.

    Two ways a cell earns bin −1 at assembly: the component's tile-edge
    ring (its neighbours live in sibling tiles this fire may not see),
    and the ring around an unobserved hole. Both keep the marginal LLR
    exactly; complete-neighbourhood cells take the clipped correction.
    """
    engine = _seed(new_store())
    _fire(engine)
    view = _View(engine.store)
    found = ctx_apply.adopted_context_offsets(view, POOL)
    assert found is not None
    _key, offsets = found

    observed = np.ones((TILE, TILE), bool)
    observed[30:34, 30:34] = False              # an unobserved hole
    marginal = np.where(observed, _tile_llr(0, 0), 0.0)
    corrected = apply_component_context(
        marginal, observed, ((np.ones((TILE, TILE), bool), offsets),))
    assert corrected is not marginal

    ring = np.zeros((TILE, TILE), bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    hole_halo = ndimage.binary_dilation(
        ~observed, structure=np.ones((3, 3), bool)) & observed
    untouched = ring | hole_halo | ~observed
    assert np.array_equal(corrected[untouched], marginal[untouched]), (
        "bin −1 cells must keep their marginal LLR, bit for bit")
    interior = ~untouched
    assert not np.array_equal(corrected[interior], marginal[interior]), (
        "the fixture must actually correct something")
    # And the corrected cells are exactly the carried kernel's answer.
    ys, xs = np.nonzero(observed)
    counts, valid = detect.context_neighbour_counts(
        np.stack((ys, xs), 1).astype(np.int64), marginal[observed] > 0.0)
    bins = np.full((TILE, TILE), -1, np.int8)
    bins[observed] = detect.context_bins(counts, valid=valid)
    reference = detect.apply_context_offsets(marginal, bins, offsets)
    assert corrected.tobytes() == reference.tobytes()


# ------------------------------------------ duplicates weigh one (pin d)

def test_duplicate_observations_weigh_one_in_the_pool(new_store) -> None:
    """Pin (d), asserted the strong way: byte-identical fit params.

    Pose B re-observes half of pose A's cells with identical content, so
    every duplicated site enters the pooled populations twice at weight
    one half — and the fit's every number (offsets, unique supports,
    weighted losses) equals the single-copy fit's exactly.

    RE-PINNED AT F1 (2026-08-23, ruling J2-1), and the number that moved
    says why: the params blob now also carries the PER-WINDOW held-out
    losses the ownership freeze ranks candidates by, which are per-member
    by definition — so two members cannot address the same blob as one,
    and the two stores no longer mint the same calibration key. What pin
    (d) is about, the POOLED fit, is unchanged and is asserted here
    directly on the fit half of the blob, byte for byte; the member half
    is asserted to be exactly the one/two windows each store has.
    """
    single = _seed(new_store("single"))
    doubled = _seed(new_store("doubled"), poses=(POSE_A, POSE_B))
    result_single, _ = _fire(single)
    result_doubled, _ = _fire(doubled)
    assert result_single.outcome == calibration.OUTCOME_ADOPTED
    assert result_doubled.outcome == calibration.OUTCOME_ADOPTED

    def params(engine):
        (key,) = StoreIndex.build(engine.store).context_fits[POOL]
        record = engine.store.get(key)
        return np.asarray(engine.store.read_array(record.params_ref),
                          np.float64).ravel()

    fit_single, fit_doubled = params(single), params(doubled)
    width = calibration.PARAM_LENGTH
    assert fit_single[:width].tobytes() == fit_doubled[:width].tobytes(), (
        "the pooled fit must be byte-identical with the duplicates in")
    assert int(fit_single[width]) == 1
    assert int(fit_doubled[width]) == 2
    # And the strictly stronger claim the member half allows (review fix,
    # 2026-08-23): pose A's PUBLISHED loss is unchanged by pose B's
    # arrival. A ``_MemberHeldout`` is built from that pose's own pieces
    # alone (``_pieces_by_pose`` -> ``_member_cells``) and the two stores'
    # fit halves are byte-identical above, so A's loss MUST be bit-equal
    # in both — a defect letting the POOLED harvest contaminate a
    # per-member loss passed the counts and fails here.
    digest_a = calibration.member_digest(POSE_A.resource_key())
    published_single = calibration.published_losses(fit_single)
    published_doubled = calibration.published_losses(fit_doubled)
    assert published_single[digest_a] == published_doubled[digest_a]
    assert set(published_doubled) == {
        digest_a, calibration.member_digest(POSE_B.resource_key())}


# ----------------------------------------------- the re-arm race (pin e)

def test_a_decode_in_flight_when_its_fit_adopts_dies_stale(
        new_store) -> None:
    """Pin (e), STAGED — the W5 staleness pin's sibling.

    The decode's read-set names its own tile's pieces plus exactly ONE
    region-scoped key (the pool's calibration collection, versioned on
    adoption only). Identity taken, the fit adopts, and the identity no
    longer binds at the wall's EXISTING staleness check — no new wake
    kind. The re-armed decode then assembles the CALIBRATED tensor: the
    carried kernel's own answer, applied at assembly, pieces untouched.
    """
    engine = _seed(new_store())
    work = tile_key(0, 0, 0, STREAM)
    worker = payload.RealPayloadWorker(
        work, SPEC, stage=payload.tile_chain.AttemptStage.SCAN,
        scope=str(FOOTING))
    view = _View(engine.store)
    keys = worker.read_keys(view)
    assert calibration_collection_key(POOL) in keys, (
        "the ONE region-scoped subscription key rides the identity")
    assert not any(key.kind == "pool" for key in keys), (
        "a decode never subscribes to the pool record — that key moves "
        "per label batch, and the law says adoption only")
    cold_keys = worker._evidence_keys(view)
    cold = worker._fits(view, cold_keys)
    marginal_llr, _pose, _c = worker._decoder_input(
        view, worker._pieces(view, cold_keys, cold), cold)

    identity = engine.attempt_identity(keys)    # the decode is in flight
    assert engine.is_current(keys, identity)    # ... and would land now

    _fire(engine)                               # the region's fit ADOPTS

    fresh = _View(engine.store)
    rederived = worker.read_keys(fresh)
    assert not engine.is_current(rederived, identity), (
        "the in-flight decode dies stale at the wall's existing check")
    (fit_key,) = fresh.index().context_fits[POOL]
    assert fit_key in rederived, (
        "the re-armed decode reads the adopted record it decodes under")

    # The re-decode is CALIBRATED: assembly applies the adopted offsets
    # through the carried kernel, and the evidence pieces kept their
    # marginal LLRs (frozen — nothing rewrote them).
    warm_keys = worker._evidence_keys(fresh)
    warm = worker._fits(fresh, warm_keys)
    calibrated, _pose2, _c2 = worker._decoder_input(
        fresh, worker._pieces(fresh, warm_keys, warm), warm)
    assert not np.array_equal(calibrated, marginal_llr)
    found = ctx_apply.adopted_context_offsets(fresh, POOL)
    assert found is not None
    owner, owners, bins = payload.RealPayloadWorker._freeze_with_owners(
        list(worker._pieces(fresh, warm_keys, warm)))
    expected = apply_component_context(
        owner.llr, owner.observed,
        ((next(iter(owners.values())), found[1]),), bins)
    assert calibrated.tobytes() == expected.tobytes()


# ------------------------------------------------- the fit's own re-arm

def test_the_fit_re_arms_on_membership_and_dies_on_quarantine(
        new_store) -> None:
    """The member-set half of CA2's spend identity, as §7 staleness.

    The fit's read-set is the pool, the region's pose collection and the
    member poses — so a NEW member re-arms it (the collection bumps), a
    condemnation mid-flight kills it (the pose version bumps), and it
    deliberately does NOT name the adoption collection its own commit
    would bump (that would buy one guaranteed wasted refit per adoption).
    """
    engine = _seed(new_store())
    worker = _worker()
    view = _View(engine.store)
    keys = worker.read_keys(view)
    assert POOL in keys
    assert region_pose_collection_key(FOOTING, REGION) in keys
    assert POSE_A.resource_key() in keys
    assert calibration_collection_key(POOL) not in keys
    assert not any(key.kind == "evidence" for key in keys)

    identity = engine.attempt_identity(keys)
    placement, staged = _placement(POSE_B, ((0, 0), (0, 1)))
    engine.apply(CommitBatch(writes=placement, blobs=staged))
    assert not engine.is_current(worker.read_keys(_View(engine.store)),
                                 identity), "a new member re-arms the fit"

    identity = engine.attempt_identity(worker.read_keys(_View(engine.store)))
    engine.apply(CommitBatch(writes=(
        Write(POSE_B.resource_key(), replace(POSE_B, quarantined=True)),)))
    assert not engine.is_current(worker.read_keys(_View(engine.store)),
                                 identity), "a condemnation kills the fit"


# ------------------------------------------------- the maintained index

def test_context_fits_is_maintained_equal_to_built(new_store) -> None:
    """The F-17 discipline for the new bucket: advance == rebuild."""
    engine = _seed(new_store())
    index = StoreIndex.build(engine.store)
    worker = _worker()
    result = worker.run(_View(engine.store), (), ProgressSink("fit"))
    commit = engine.apply(CommitBatch(writes=result.writes,
                                      blobs=result.blobs))
    advanced = index.updated(engine.store, commit.changed_keys)
    rebuilt = StoreIndex.build(engine.store)
    assert advanced.context_fits == rebuilt.context_fits
    assert advanced.context_fits[POOL] == rebuilt.context_fits[POOL]


def test_an_identical_refit_is_idempotent(new_store) -> None:
    """Same members, same labels, same fit: the same key, a no-op write."""
    engine = _seed(new_store())
    _fire(engine)
    result, commit = _fire(engine)
    assert result.outcome == calibration.OUTCOME_ADOPTED
    assert commit is None or not commit.changed_keys, (
        "an identical re-derivation moves nothing durable")


# ------------------------------- where the ranking statistic may read

def test_the_ranking_statistic_reads_only_format_fixed_sites(
        new_store) -> None:
    """F-09, pinned where the property NOW lives (review fix 2026-08-23).

    Since F1 the ownership freeze ranks by a statistic OF the evidence,
    so what keeps owner selection out of self-confirmation is no longer
    "no evidence value" — it is WHERE that statistic reads: only cells
    whose values the FORMAT fixes, never a payload cell. The old pin
    (``test_freeze_ownership.py``'s ``test_ownership_reads_no_payload_
    cell_value``) scales the LLRs and shows the freeze ignores them,
    which would keep passing if ``member_window_losses`` started reading
    payload cells. THIS is the fork that would matter, so it is asserted
    on the harvest itself: the member's held-out sample is exactly
    ``known & heldout`` over the member's own cells — a subset of
    ``reference.page(...).sites`` — and its labels ARE the reference
    field's values there.
    """
    engine = _seed(new_store("sites"))
    plane = _View(engine.store)
    _search, _validation, heldouts = calibration.region_fit_inputs(
        plane, _REFERENCE, FOOTING, (POSE_A.resource_key(),))
    (member,) = heldouts

    # The same cells the harvest derives, through the same two helpers.
    grouped = calibration._pieces_by_pose(
        plane, FOOTING, frozenset({POSE_A.resource_key()}))
    cells, marginal = calibration._member_cells(
        plane, grouped[POSE_A.resource_key()])
    heldout = (((131 * cells[:, 0] + 17 * cells[:, 1]) & 1) == 1)
    known = _PAGE.sites[cells[:, 0], cells[:, 1]]
    select = known & heldout

    assert select.any(), "the fixture must rank on something"
    assert member.marginal.size == int(select.sum()), (
        "the ranked sample is the format-known held-out sites, no more")
    assert np.array_equal(member.marginal, marginal[select])
    assert _PAGE.sites[cells[select, 0], cells[select, 1]].all(), (
        "every ranked site is one the FORMAT fixes")
    assert np.array_equal(
        member.labels,
        _PAGE.values[cells[select, 0], cells[select, 1]].astype(bool)), (
        "and its labels are the format's own values, not a payload guess")
