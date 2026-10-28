"""solve's record shapes: the R3 fitness pass, pinned where it is owned.

The families themselves are exercised everywhere a worker writes one; what
is pinned here is the part that is a DECISION rather than arithmetic — the
observed-cell bitset's encoding, the page domain the pose family validates
against, the two tile-map merges every worker makes, and the tile
transition law now that it travels with the family instead of living
inside ``core.commit``.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo2.core import (BlobRef, CertificateConflict, MalformedKeyError,
                        ResourceKey)
from holo2.solve import (EvidenceObservation, MintRef, PoseRecord, TileRecord,
                         pose_key,
                         calibration_key, evidence_key,
                         pack_observed_cells, record_families, tile_key,
                         unpack_observed_cells)
from holo2.solve.records import carry_tile, join_tiles
from conftest import FOOTING, POSE, WINDOW

_KEY = tile_key(0, 1, 2, "main")


def _family(name: str):
    for family in record_families((0, 1)):
        if family.name == name:
            return family
    raise AssertionError(f"no {name} family")


# ------------------------------------------------------- observed bitset

@pytest.mark.parametrize("shape", [(64, 64), (8, 8), (1, 4)])
def test_the_observed_mask_round_trips_at_one_bit_per_cell(shape) -> None:
    rows, cols = shape
    mask = np.zeros(shape, bool)
    mask[::3, ::2] = True
    packed = pack_observed_cells(mask)
    assert packed.dtype == np.uint8
    assert packed.size == (rows * cols + 7) // 8
    np.testing.assert_array_equal(unpack_observed_cells(packed, shape), mask)


def test_identical_masks_are_one_blob() -> None:
    """The common "saw the whole tile" case dedups: same bytes, same sha."""
    whole = pack_observed_cells(np.ones((64, 64), bool))
    again = pack_observed_cells(np.ones((64, 64), bool))
    assert whole.tobytes() == again.tobytes()
    assert whole.nbytes == 512                    # 4096 cells, one bit each


# ------------------------------------- the canonical affine (pose v4, W1)

def test_a_committed_affine_is_canonical() -> None:
    """W0-B's measurement, RATIFIED: six native-pixel decimals, no -0.0.

    The fitter carries noise terms of order 1e-7 and renders a clean 6.0
    as ``5.9999998885931`` (measured on the W0-B fixtures). Rounding at
    the RECORD is what makes the key and the value it names agree: two
    fits that differ only by that noise are one pose, and a term that
    rounds to a negative zero cannot mint a second key for one geometry.
    """
    noisy = (5.9999998885931, -4.0015e-10, 3.25, 9.74e-7, 6.0, -2.5)
    record = PoseRecord(WINDOW, FOOTING, 0, noisy)
    assert record.native_affine == (6.0, 0.0, 3.25, 1e-06, 6.0, -2.5)
    assert repr(record.native_affine[1]) == "0.0", "no negative zero"
    assert record.resource_key() == pose_key(WINDOW, 0, record.native_affine)
    assert record.resource_key() == PoseRecord(
        WINDOW, FOOTING, 0, (6.0, 0.0, 3.25, 1e-06, 6.0, -2.5)).resource_key()


def test_canonicalisation_is_not_deduplication() -> None:
    """The honest half (W0-B): equivalent-fit jitter still mints two poses.

    Measured blind-vs-seeded jitter on one window reaches 1.2e-3 — three
    orders ABOVE the quantum — so two paths onto one window remain two
    poses, and that is pose semantics' problem (the collection, the
    +-3-cell chain gate), never the key's. The quantum keeps them apart
    on purpose: the smallest measured DISTINCT-pose separation, 3.245e-5,
    is 32 quanta.
    """
    one = PoseRecord(WINDOW, FOOTING, 0, (6.0, 0.0, 3.25, 0.0, 6.0, -2.5))
    other = PoseRecord(WINDOW, FOOTING, 0,
                       (6.0012, 0.0, 3.25, 0.0, 6.0, -2.5))
    assert one.resource_key() != other.resource_key()
    apart = PoseRecord(WINDOW, FOOTING, 0,
                       (6.0 + 3.245e-5, 0.0, 3.25, 0.0, 6.0, -2.5))
    assert one.resource_key() != apart.resource_key()


# ------------------------------------------------------- the pose domain

def test_a_pose_is_validated_against_the_declared_page_domain() -> None:
    validate = _family("PoseRecord").validate
    affine = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    inside = PoseRecord(WINDOW, FOOTING, 1, affine)
    outside = PoseRecord(WINDOW, FOOTING, 4, affine)
    validate(inside.resource_key(), inside)    # validators are key-aware
    with pytest.raises(ValueError, match="page domain"):
        validate(outside.resource_key(), outside)
    # v5 since H4 W5: the quarantine marking is a field, so the family
    # gained a wire version AND the transition law below.
    assert _family("PoseRecord").version == 5


def test_a_pose_must_agree_with_the_key_it_is_stored_under() -> None:
    """Window, page and affine ARE the pose: the key rebuilds from them."""
    validate = _family("PoseRecord").validate
    record = PoseRecord(WINDOW, FOOTING, 1, (1.0, 0.0, 0.0, 0.0, 1.0, 0.0))
    validate(record.resource_key(), record)
    with pytest.raises(ValueError, match="record identifies"):
        validate(PoseRecord(WINDOW, FOOTING, 0,
                            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)).resource_key(),
                 record)
    with pytest.raises(ValueError, match="its window"):
        stray = PoseRecord(WINDOW, "other:2/1", 1,
                           (1.0, 0.0, 0.0, 0.0, 1.0, 0.0))
        validate(stray.resource_key(), stray)


def test_an_evidence_piece_must_agree_with_the_key_it_is_stored_under() -> None:
    """The fallible key parse is a VALIDATOR now, not a post-commit callback."""
    validate = _family("EvidenceObservation").validate
    ref = BlobRef("ab" * 32, 4)
    record = EvidenceObservation(
        footing_id=FOOTING, page=0, ty=1, tx=2, stream="K",
        pose_id=POSE, llr_ref=ref, observed_ref=ref,
        calibration_id=calibration_key(WINDOW, "pava-v1", ref.sha256))
    validate(record.resource_key(), record)
    with pytest.raises(MalformedKeyError, match="not an evidence key"):
        validate(ResourceKey("evidence", ("bad",)), record)
    with pytest.raises(ValueError, match="record identifies"):
        validate(evidence_key("cap:2/1", 0, 1, 2, "K", POSE), record)


def test_no_declared_domain_gates_no_page() -> None:
    """A unit test that never names a lineage still gets a usable family."""
    for family in record_families():
        if family.name == "PoseRecord":
            record = PoseRecord(WINDOW, FOOTING, 7,
                                (1.0, 0.0, 0.0, 0.0, 1.0, 0.0))
            family.validate(record.resource_key(), record)   # any page
            break
    else:
        raise AssertionError("no PoseRecord family")


def test_a_page_index_is_structurally_non_negative() -> None:
    with pytest.raises(ValueError, match="page index"):
        PoseRecord(WINDOW, FOOTING, -1, (1.0, 0.0, 0.0, 0.0, 1.0, 0.0))


# ------------------------------------------------------ the tile merges

def test_a_certificate_is_the_mint_that_made_it() -> None:
    """Tile family v4: ``certified`` derives, it is not carried."""
    assert not TileRecord().certified
    assert not TileRecord(observed_by=("a:2/1",), baselined=("a:2/1",)).certified
    assert TileRecord(minting=MintRef("pose-1", "scan", "d")).certified


def test_the_merge_carries_the_certificate_and_unions_the_footings() -> None:
    """One merge for every writer: nothing certified moves, the sets grow.

    ``carry_tile`` UNIONS rather than trusting the call site — a caller
    that passes only its new footings keeps the provenance §6 needs, and
    a pre-merging caller gets the same record because a union is
    idempotent.
    """
    minting = MintRef("pose-1", "scan", "fixture-decoder")
    current = TileRecord(minting=minting, metadata_bit=1,
                         observed_by=("a:2/1", "b:4/1"))
    gained_only = carry_tile(current, ("c:8/1",))
    assert gained_only.minting == minting and gained_only.metadata_bit == 1
    assert gained_only.observed_by == ("a:2/1", "b:4/1", "c:8/1")
    assert carry_tile(current, ("a:2/1", "b:4/1", "c:8/1")) == gained_only
    fresh = carry_tile(None, ("b:4/1",))
    assert fresh.minting is None and fresh.bits_ref is None
    assert fresh.metadata_bit is None and fresh.observed_by == ("b:4/1",)


def test_a_failed_scan_names_its_baseline_and_a_union_does_not() -> None:
    """``baselined`` is the per-footing fact the retry route derives from.

    A footing enters it exactly when ITS scan ran a decoder and failed
    (the caller passes ``baseline=``); a union failure, and an attempt
    below the floor, name none — their evidence is not one footing's.
    Monotone: a later merge carries every earlier baseline.
    """
    first = carry_tile(None, ("a:2/1",), baseline="a:2/1")
    assert first.baselined == ("a:2/1",)
    second = carry_tile(first, ("a:2/1", "b:2/1"), baseline="b:2/1")
    assert second.baselined == ("a:2/1", "b:2/1")
    union_failed = carry_tile(second, second.observed_by)
    assert union_failed.baselined == ("a:2/1", "b:2/1")
    assert carry_tile(None, ("b:2/1",)).baselined == ()


# ------------------------------------------------------- the tile JOIN

_MINT = MintRef("pose-1", "scan", "fixture-decoder")
_BITS = BlobRef("aa" * 32, 8, dtype="|u1", shape=(8,))


def test_the_family_declares_the_join_the_fire_already_ran() -> None:
    """H4 W2 ruling 1: one algebra, two sides of the wall.

    The hook the tile family registers IS ``join_tiles``, and
    :func:`carry_tile` is that same function with the gain expressed as
    a record — so "the wall re-applies the fire's operation" is an
    identity here, not an argument about two implementations agreeing.
    """
    assert _family("TileRecord").merge is join_tiles
    current = TileRecord(observed_by=("a:2/1",))
    assert carry_tile(current, ("b:4/1",), baseline="b:4/1") == join_tiles(
        None, current, TileRecord(observed_by=("b:4/1",),
                                  baselined=("b:4/1",)))


def test_the_join_is_idempotent_commutative_and_associative() -> None:
    """The three properties the wall's licence rests on, exhaustively.

    If ⊔ were not all three, "re-apply the proposal against what stands"
    would depend on which fire got there first — which is precisely the
    conflict the compare-and-swap was manufacturing.
    """
    a = TileRecord(observed_by=("a:2/1",), baselined=("a:2/1",))
    b = TileRecord(observed_by=("b:4/1",))
    c = TileRecord(minting=_MINT, bits_ref=_BITS, metadata_bit=1,
                   observed_by=("c:8/1",))
    join = lambda x, y: join_tiles(None, x, y)              # noqa: E731
    for left in (a, b, c):
        assert join(left, left) == left                     # idempotent
        for right in (a, b, c):
            assert join(left, right) == join(right, left)   # commutative
            for third in (a, b, c):
                assert join(join(left, right), third) == join(
                    left, join(right, third))               # associative


def test_a_stale_proposal_loses_nothing_and_takes_nothing_back() -> None:
    """THE lost-gains case, at the algebra.

    Two fires join their own gain onto ONE snapshot; the second lands on
    a store that already holds the first. Both gains stand, in both
    sets — which is what the wall's re-application buys, and what the
    old last-write-wins threw away without a word.
    """
    snapshot = TileRecord(observed_by=("a:2/1",))
    first = carry_tile(snapshot, ("b:4/1",))
    second = carry_tile(snapshot, ("c:8/1",), baseline="c:8/1")
    merged = join_tiles(_KEY, first, second)
    assert merged.observed_by == ("a:2/1", "b:4/1", "c:8/1")
    assert merged.baselined == ("c:8/1",)


def test_certified_content_is_carried_from_whichever_side_holds_it() -> None:
    certified = TileRecord(minting=_MINT, bits_ref=_BITS, metadata_bit=1,
                           observed_by=("a:2/1",))
    bare = TileRecord(observed_by=("b:4/1",))
    for merged in (join_tiles(_KEY, certified, bare),
                   join_tiles(_KEY, bare, certified)):
        assert merged.minting == _MINT and merged.bits_ref == _BITS
        assert merged.metadata_bit == 1
        assert merged.observed_by == ("a:2/1", "b:4/1")


def test_two_disagreeing_certificates_are_the_fatal_event() -> None:
    """A join that cannot join has nothing to return (L5, F-11).

    Fault-injected on each half of what "certified content" means: the
    symbol bits, and the metadata bit that rides them.
    """
    certified = TileRecord(minting=_MINT, bits_ref=_BITS, metadata_bit=1)
    other = BlobRef("bb" * 32, 8, dtype="|u1", shape=(8,))
    with pytest.raises(CertificateConflict, match="disagree"):
        join_tiles(_KEY, certified, TileRecord(
            minting=_MINT, bits_ref=other, metadata_bit=1))
    with pytest.raises(CertificateConflict, match="disagree"):
        join_tiles(_KEY, certified, TileRecord(
            minting=_MINT, bits_ref=_BITS, metadata_bit=0))


def test_two_agreeing_certificates_keep_the_STANDING_mint() -> None:
    """Corroboration, not contradiction — the one relaxation (H4 W2).

    Two routes on one work key can decode the same bits under different
    attempts. The content must agree; the provenance is the first
    certificate's, and the second's observation still lands.
    """
    standing = TileRecord(minting=_MINT, bits_ref=_BITS, metadata_bit=1,
                          observed_by=("a:2/1",))
    rival = TileRecord(minting=MintRef("pose-2", "union", "fixture-decoder"),
                       bits_ref=_BITS, metadata_bit=1,
                       observed_by=("b:4/1",))
    merged = join_tiles(_KEY, standing, rival)
    assert merged.minting == _MINT
    assert merged.observed_by == ("a:2/1", "b:4/1")


# --------------------------------------------------- the tile transition

def test_the_tile_law_travels_with_the_family() -> None:
    """L5/§11.3, unchanged by R3 — it just stopped living in core.commit."""
    transition = _family("TileRecord").transition
    certified = TileRecord(
        minting=MintRef("pose-1", "scan", "fixture-decoder"),
        observed_by=("cap:2/1",))
    transition(_KEY, certified, TileRecord(
        minting=certified.minting,
        observed_by=("cap:2/1", "cap:8/1")))          # gaining a footing is fine
    with pytest.raises(CertificateConflict):
        transition(_KEY, certified, TileRecord(observed_by=("cap:2/1",)))
    with pytest.raises(CertificateConflict):
        transition(_KEY, certified, TileRecord(
            minting=MintRef("pose-2", "scan", "fixture-decoder"),
            observed_by=("cap:2/1",)))
    with pytest.raises(CertificateConflict):
        transition(_KEY, certified, TileRecord(minting=certified.minting))


def test_a_certified_tile_may_not_lose_its_baselines() -> None:
    """History rides the certificate: retries ended, the record stays."""
    transition = _family("TileRecord").transition
    certified = TileRecord(
        minting=MintRef("pose-1", "scan", "fixture-decoder"),
        observed_by=("cap:2/1",), baselined=("cap:2/1",))
    transition(_KEY, certified, TileRecord(
        minting=certified.minting,
        observed_by=("cap:2/1",), baselined=("cap:2/1", "cap:8/1")))
    with pytest.raises(CertificateConflict):
        transition(_KEY, certified, TileRecord(
            minting=certified.minting, observed_by=("cap:2/1",)))


def test_a_certificate_cannot_be_minted_without_naming_its_route() -> None:
    """The provenance the review found missing is now unrepresentable-if-absent.

    One descriptor per route made the route a durable NAME (the spend
    row it was taken under), so a ``MintRef`` that states neither the
    route nor the decoder is refused rather than stored empty
    (HARDENING-SYSTEMIC-REVIEW P1).
    """
    minted = MintRef("pose-1", "retry150",
                     "r0550/decode_tile-max150-alpha0.8")
    assert (minted.route, minted.decoder_profile) == (
        "retry150", "r0550/decode_tile-max150-alpha0.8")
    for route, profile in (("", "r0550/decode_tile-max60-alpha0.8"),
                           ("scan", "")):
        with pytest.raises(ValueError, match="names the route"):
            MintRef("pose-1", route, profile)
