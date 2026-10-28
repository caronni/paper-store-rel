"""Phase 0.2 — D5 supersession-materialization unit pins (d2e5281 layer).

Direct fixtures for the collision path of ``supersede_with_committed`` /
``apply_mopup_supersession`` (PAYLOAD-REWORK-PLAN Phase 0.2; findings
PAYLOAD-IMPROVEMENTS §8.1: the layer had ZERO direct tests).  Everything
here pins CURRENT ruled-correct behavior — no xfails:

  (a) committed cells carry over VERBATIM (values, mask, origin rows
      byte-identical), including when the fresh block DISAGREES at a
      committed cell — the disagreeing observation is dropped silently;
  (b) base-owner-wins: origin rows at committed cells are the committed
      block's even when the fresh values agree;
  (c) strictly-novel fresh cells appear with the fresh block's values
      and origins;
  (d) a fresh block with nothing novel returns None (no emission);
  (e) the materialized superset passes ``validate_block_supersession``
      against the committed block by construction;
  (f) ``apply_mopup_supersession`` partitions a mixed fresh set into
      superseded / passed-through / dropped and re-mints content
      addresses for materialized blocks only;
  (g) negative control: a hand-built NON-superset replacement still
      refuses at the (unchanged) validator.

Plus the drop-tally surface (2026-08-02 ruling, replacing ruling 11.2's
byte-inequality counter; docs/CANARY-D5-DISAGREEMENTS.md): the layer
returns ``SupersessionDrops(dropped, winner_flips)`` — ``dropped``
counts EVERY fresh observation at a committed cell (expected overlap
geometry; full-agreement collisions included), ``winner_flips`` counts
the dropped cells whose implied decision differs from the committed
owner's (K sign category / CMY7 W-relative state / CMY8 plane sign
pattern — ``winner_codes``).  Expected tallies below are hand-derived
from the constructed vectors, never recomputed through the code under
test.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

import numpy as np
import pytest

from holo.receive.evidence_blocks import (
    EvidenceBlock,
    EvidenceKind,
    EvidenceOrigin,
    SupersessionDrops,
    apply_mopup_supersession,
    block_from_rows,
    evidence_arity,
    supersede_with_committed,
    validate_block_supersession,
    winner_codes,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


_SOURCE_SHA256 = _sha("capture-a")
_OTHER_SOURCE_SHA256 = _sha("capture-b")
_LANE_ID = "l00-2ppc-1200dpi"


def _origin(
    placement_label: str,
    patch_id: int = 7,
    heldout_logloss: float = 0.25,
) -> EvidenceOrigin:
    return EvidenceOrigin(placement_label, patch_id, heldout_logloss, ())


def _cell_values(kind: EvidenceKind, seed_value: float) -> tuple[float, ...]:
    """Deterministic per-kind value vector of the exact arity."""
    return tuple(
        seed_value + 0.125 * index for index in range(evidence_arity(kind)))


def _block(
    cells: Mapping[int, Sequence[float]],
    *,
    kind: EvidenceKind = "k",
    origin_by_flat: Mapping[int, EvidenceOrigin] | None = None,
    default_origin: EvidenceOrigin | None = None,
    source_sha256: str = _SOURCE_SHA256,
    lane_id: str = _LANE_ID,
    page: int = 0,
    tile_yx: tuple[int, int] = (0, 0),
) -> EvidenceBlock:
    """Hand-build one small block; per-cell origins override the default."""
    origin = default_origin if default_origin is not None else _origin(
        "placement-base")
    overrides = dict(origin_by_flat or {})
    rows = tuple(
        (flat, np.asarray(values, np.float32), overrides.get(flat, origin))
        for flat, values in sorted(cells.items()))
    return block_from_rows(
        source_sha256, lane_id, page, tile_yx, rows, kind=kind)


def _value_bytes_at(block: EvidenceBlock, flat: int) -> bytes:
    """Exact stored float32 bytes of one observed cell."""
    stride = block.arity * 4
    position = int(np.searchsorted(block.observed_flat(), flat))
    assert int(block.observed_flat()[position]) == flat
    return block.printed_llr_f32[position * stride:(position + 1) * stride]


def _origin_row_at(block: EvidenceBlock, flat: int) -> EvidenceOrigin:
    """The origin row referenced by one observed cell."""
    position = int(np.searchsorted(block.observed_flat(), flat))
    assert int(block.observed_flat()[position]) == flat
    indices = np.frombuffer(block.origin_indices_u16, "<u2")
    return block.origins[int(indices[position])]


def _dropped_count(fresh: EvidenceBlock, committed: EvidenceBlock) -> int:
    """Reference derivation for ``dropped``: fresh cells committed observes.

    The winner-flip side is deliberately NOT re-derived through
    ``winner_codes`` here — expected flip counts are hand-annotated per
    case from the constructed vectors (the audit's differential-
    cancellation rule).
    """
    committed_flat = set(committed.observed_flat().tolist())
    return sum(1 for flat in fresh.observed_flat().tolist()
               if int(flat) in committed_flat)


# --- (a) committed-verbatim under disagreement --------------------------


@pytest.mark.parametrize("kind", ("k", "cmy8"))
def test_committed_cells_carry_verbatim_even_under_disagreement(
    kind: EvidenceKind,
) -> None:
    """(a) Colliding fresh block: committed values, mask bits, and origin
    rows survive byte-identical; the fresh observations at committed
    cells are dropped and the committed values are kept.  Hand-derived
    tally: cells 3 and 9 collide (dropped=2); cell 3 flips the winner
    (all-positive committed vector vs all-negative fresh — K sign and
    CMY8 plane pattern alike), cell 9 agrees exactly -> flips=1."""
    committed_origin = _origin("placement-committed", 3, 0.125)
    fresh_origin = _origin("placement-fresh", 9, 0.5)
    committed = _block(
        {3: _cell_values(kind, 1.5), 9: _cell_values(kind, -2.0)},
        kind=kind, default_origin=committed_origin)
    fresh = _block(
        {
            3: _cell_values(kind, -99.0),  # winner FLIP at committed cell
            9: _cell_values(kind, -2.0),   # agrees at committed cell
            40: _cell_values(kind, 0.75),  # strictly novel
        },
        kind=kind, default_origin=fresh_origin)

    merged, drops = supersede_with_committed(fresh, committed)
    assert merged is not None
    assert drops == SupersessionDrops(
        dropped=_dropped_count(fresh, committed), winner_flips=1)
    assert drops.dropped == 2
    assert merged.key == committed.key
    assert merged.kind == kind
    assert merged.observed_flat().tolist() == [3, 9, 40]

    for flat in (3, 9):
        assert _value_bytes_at(merged, flat) == _value_bytes_at(
            committed, flat)
        assert _origin_row_at(merged, flat) == committed_origin
    # The disagreeing fresh value at cell 3 is nowhere in the result.
    assert _value_bytes_at(merged, 3) != _value_bytes_at(fresh, 3)
    # Committed mask bits are a verbatim subset of the merged bitmap.
    committed_bits = np.unpackbits(
        np.frombuffer(committed.observed_bitmap, np.uint8),
        bitorder="little")
    merged_bits = np.unpackbits(
        np.frombuffer(merged.observed_bitmap, np.uint8), bitorder="little")
    assert np.array_equal(merged_bits & committed_bits, committed_bits)


# --- (b) base-owner-wins ------------------------------------------------


def test_base_owner_wins_origin_rows_at_committed_cells() -> None:
    """(b) Even when the fresh VALUE agrees, the committed block's origin
    row is kept at a committed cell; a fresh origin used only at dropped
    cells never enters the materialized origin table.  The dropped
    observation counts (dropped=1) but an origin-only difference is NOT
    a winner flip (2026-08-02 ruling: origin identity always differs
    across the pass split, so it carries no signal)."""
    committed_origin = _origin("placement-committed", 3, 0.125)
    colliding_origin = _origin("placement-collider", 9, 0.5)
    novel_origin = _origin("placement-novel", 11, 0.75)
    committed = _block(
        {3: (1.5,), 9: (-2.0,)}, default_origin=committed_origin)
    fresh = _block(
        {3: (1.5,), 40: (0.75,)},   # cell 3 agrees in value, differs in origin
        origin_by_flat={3: colliding_origin, 40: novel_origin},
        default_origin=novel_origin)

    merged, drops = supersede_with_committed(fresh, committed)
    assert merged is not None
    assert drops == SupersessionDrops(
        dropped=_dropped_count(fresh, committed), winner_flips=0)
    assert drops.dropped == 1
    assert _origin_row_at(merged, 3) == committed_origin
    assert _origin_row_at(merged, 3) != colliding_origin
    assert _origin_row_at(merged, 40) == novel_origin
    assert committed_origin in merged.origins
    assert novel_origin in merged.origins
    assert colliding_origin not in merged.origins


# --- (c) novel-only contribution ---------------------------------------


def test_novel_cells_contribute_fresh_values_and_origins() -> None:
    """(c) Cell-disjoint same-key fresh block: the union carries committed
    rows verbatim plus every fresh cell with fresh values and origins."""
    committed_origin = _origin("placement-committed", 3, 0.125)
    fresh_origin = _origin("placement-fresh", 9, 0.5)
    committed = _block(
        {3: (1.5,), 9: (-2.0,)}, default_origin=committed_origin)
    fresh = _block(
        {40: (0.75,), 41: (-0.5,)}, default_origin=fresh_origin)

    merged, drops = supersede_with_committed(fresh, committed)
    assert merged is not None
    assert drops == SupersessionDrops(dropped=0, winner_flips=0)
    assert merged.observed_flat().tolist() == [3, 9, 40, 41]
    for flat in (40, 41):
        assert _value_bytes_at(merged, flat) == _value_bytes_at(fresh, flat)
        assert _origin_row_at(merged, flat) == fresh_origin
    for flat in (3, 9):
        assert _value_bytes_at(merged, flat) == _value_bytes_at(
            committed, flat)
        assert _origin_row_at(merged, flat) == committed_origin


# --- (d) nothing-novel returns None ------------------------------------


def test_nothing_novel_returns_none_even_when_disagreeing() -> None:
    """(d) A fresh block whose cells are all committed yields None — for
    an identical block, an agreeing subset, AND a wholly-disagreeing
    same-cell block (drops alone never cause an emission).  Every
    collision counts as dropped — full agreement included (it IS a
    dropped observation; unreachable in production except deterministic
    replays).  Hand-derived flips: identical/subset agree everywhere
    (0); the disagreeing block flips only cell 9 (-2.0 -> 8.0 crosses
    zero; 1.5 -> 7.0 keeps the sign)."""
    committed = _block({3: (1.5,), 9: (-2.0,)})
    identical = _block({3: (1.5,), 9: (-2.0,)})
    agreeing_subset = _block({9: (-2.0,)})
    disagreeing = _block(
        {3: (7.0,), 9: (8.0,)},
        default_origin=_origin("placement-fresh", 9, 0.5))

    assert supersede_with_committed(identical, committed) == (
        None, SupersessionDrops(dropped=2, winner_flips=0))
    assert supersede_with_committed(agreeing_subset, committed) == (
        None, SupersessionDrops(dropped=1, winner_flips=0))
    assert supersede_with_committed(disagreeing, committed) == (
        None, SupersessionDrops(dropped=2, winner_flips=1))


# --- (e) validator passes by construction ------------------------------


@pytest.mark.parametrize("kind", ("k", "cmy7", "cmy8"))
def test_materialized_superset_passes_the_validator(
    kind: EvidenceKind,
) -> None:
    """(e) validate_block_supersession(committed, materialized) accepts
    the merge output — legality by construction, all three kinds.  The
    colliding cell 3 rescales 1.5 -> 99.0 without changing the implied
    winner (same sign / same argmax / same plane pattern): dropped=1,
    flips=0 — a magnitude-only difference is not a flip."""
    committed = _block(
        {3: _cell_values(kind, 1.5), 9: _cell_values(kind, -2.0)},
        kind=kind, default_origin=_origin("placement-committed", 3, 0.125))
    fresh = _block(
        {3: _cell_values(kind, 99.0), 40: _cell_values(kind, 0.75)},
        kind=kind, default_origin=_origin("placement-fresh", 9, 0.5))

    merged, drops = supersede_with_committed(fresh, committed)
    assert merged is not None
    assert drops == SupersessionDrops(dropped=1, winner_flips=0)
    validate_block_supersession(committed, merged)


# --- (f) apply_mopup_supersession end-to-end ---------------------------


def test_apply_partitions_and_recomputes_content_addresses() -> None:
    """(f) Mixed fresh set: colliding-with-novelty is materialized,
    non-colliding keys pass through as the SAME object, nothing-novel
    vanishes; materialized identities are re-minted content addresses
    that round-trip through the wire format."""
    committed_origin = _origin("placement-committed", 3, 0.125)
    fresh_origin = _origin("placement-fresh", 9, 0.5)
    committed_a = _block(
        {3: (1.5,), 9: (-2.0,)}, tile_yx=(0, 0),
        default_origin=committed_origin)
    committed_b = _block(
        {5: (4.0,)}, tile_yx=(1, 2), default_origin=committed_origin)

    colliding = _block(
        {3: (99.0,), 40: (0.75,)}, tile_yx=(0, 0),
        default_origin=fresh_origin)
    foreign_tile = _block(
        {7: (1.0,)}, tile_yx=(3, 3), default_origin=fresh_origin)
    nothing_novel = _block(
        {5: (4.0,)}, tile_yx=(1, 2), default_origin=fresh_origin)
    foreign_source = _block(
        {3: (2.5,)}, tile_yx=(0, 0),
        source_sha256=_OTHER_SOURCE_SHA256, default_origin=fresh_origin)

    result, drops = apply_mopup_supersession(
        (colliding, foreign_tile, nothing_novel, foreign_source),
        (committed_a, committed_b))

    # Partition + input-order preservation (dropped row removed).
    # Aggregated tally, hand-derived: the colliding block drops cell 3
    # (1.5 -> 99.0, sign kept: no flip); nothing_novel drops cell 5
    # (value-identical: no flip) -> dropped=2, flips=0.
    assert drops == SupersessionDrops(dropped=2, winner_flips=0)
    assert len(result) == 3
    merged, passed_tile, passed_source = result
    assert passed_tile is foreign_tile
    assert passed_source is foreign_source
    assert all(row.key != nothing_novel.key or row is not nothing_novel
               for row in result)

    # The materialized block equals an independently-built union block:
    # same content address, same block_id, same wire bytes.
    expected = _block(
        {3: (1.5,), 9: (-2.0,), 40: (0.75,)}, tile_yx=(0, 0),
        origin_by_flat={40: fresh_origin}, default_origin=committed_origin)
    assert merged.key == committed_a.key
    assert merged == expected
    assert merged.content_sha256 == expected.content_sha256
    assert merged.block_id == expected.block_id
    assert merged.to_bytes() == expected.to_bytes()
    assert merged.block_id != colliding.block_id
    assert merged.block_id != committed_a.block_id
    assert EvidenceBlock.from_bytes(merged.to_bytes()) == merged
    validate_block_supersession(committed_a, merged)


def test_apply_without_collisions_passes_everything_through() -> None:
    """(f) Degenerate direction: no key overlap => identity pass-through."""
    fresh = _block({3: (1.0,)}, tile_yx=(9, 9))
    committed = _block({3: (2.0,)}, tile_yx=(0, 0))
    result, drops = apply_mopup_supersession((fresh,), (committed,))
    assert result == (fresh,)
    assert drops == SupersessionDrops(dropped=0, winner_flips=0)
    assert result[0] is fresh


# --- (g) negative control: the validator is unchanged ------------------


def test_non_superset_replacement_still_refuses_at_validator() -> None:
    """(g) Hand-built illegal replacements refuse: non-superset cells,
    revised committed value, and revised committed provenance (the
    provenance arm is not covered by the existing pin)."""
    committed_origin = _origin("placement-committed", 3, 0.125)
    committed = _block(
        {3: (1.5,), 9: (-2.0,)}, default_origin=committed_origin)

    # Larger but NOT a superset (drops committed cell 9).
    with pytest.raises(
            ValueError, match="observe every committed cell"):
        validate_block_supersession(
            committed,
            _block({3: (1.5,), 40: (0.75,), 41: (0.5,)},
                   default_origin=committed_origin))
    # Superset cells but a revised committed value.
    with pytest.raises(ValueError, match="revises committed evidence"):
        validate_block_supersession(
            committed,
            _block({3: (1.5,), 9: (-2.5,), 40: (0.75,)},
                   default_origin=committed_origin))
    # Superset cells, verbatim values, but revised committed provenance.
    with pytest.raises(ValueError, match="revises committed provenance"):
        validate_block_supersession(
            committed,
            _block({3: (1.5,), 9: (-2.0,), 40: (0.75,)},
                   default_origin=_origin("placement-other", 9, 0.5)))
    # No extension at all.
    with pytest.raises(ValueError, match="extend"):
        validate_block_supersession(committed, committed)


# --- key/kind discipline at the merge boundary -------------------------


def test_merge_refuses_key_or_kind_mismatch() -> None:
    """supersede_with_committed refuses a foreign lane (key) and a same-key
    kind mismatch before touching any cells."""
    committed = _block({3: (1.5,), 9: (-2.0,)})
    with pytest.raises(ValueError, match="keep key and kind"):
        supersede_with_committed(
            _block({3: (1.5,), 40: (0.75,)}, lane_id="l01-other"),
            committed)
    committed_cmy8 = _block(
        {3: _cell_values("cmy8", 1.5)}, kind="cmy8")
    fresh_cmy7 = _block(
        {3: _cell_values("cmy7", 1.5), 40: _cell_values("cmy7", 0.5)},
        kind="cmy7")
    assert fresh_cmy7.key == committed_cmy8.key
    with pytest.raises(ValueError, match="keep key and kind"):
        supersede_with_committed(fresh_cmy7, committed_cmy8)


# --- same-placement provenance conflict at materialization -------------


def test_same_placement_conflicting_provenance_refuses_to_materialize(
) -> None:
    """CURRENT behavior pin (API fact for Phase 1/2): when a fresh NOVEL
    cell carries an origin row whose placement_id equals a committed
    origin's but whose fields differ, the union block cannot be built —
    the origin-table invariant ('one placement has conflicting
    provenance') raises out of supersede_with_committed.  An identical
    row deduplicates cleanly into one table entry."""
    shared_ok = _origin("placement-shared", 7, 0.25)
    shared_conflict = _origin("placement-shared", 7, 0.5)
    committed = _block({3: (1.5,), 9: (-2.0,)}, default_origin=shared_ok)

    merged, drops = supersede_with_committed(
        _block({40: (0.75,)}, default_origin=shared_ok), committed)
    assert merged is not None
    assert drops == SupersessionDrops(dropped=0, winner_flips=0)
    assert merged.origins == (shared_ok,)

    with pytest.raises(
            ValueError, match="conflicting provenance"):
        supersede_with_committed(
            _block({40: (0.75,)}, default_origin=shared_conflict),
            committed)


# --- the drop-tally surface (2026-08-02 ruling) -------------------------


@pytest.mark.parametrize("kind", ("k", "cmy8"))
def test_drop_tally_counts_collisions_and_winner_flips(
    kind: EvidenceKind,
) -> None:
    """Every fresh observation at a committed cell drops (value-scale
    changes, origin-only differences, and full agreement alike); winner
    flips count only implied-decision changes.  Hand-derived: cell 3
    rescales positively (no flip), cell 9 crosses zero (-2.0 -> +2.0:
    K sign and every CMY8 plane flip), cell 11 agrees fully (no flip),
    cell 40 is novel -> dropped=3, flips=1."""
    committed_origin = _origin("placement-committed", 3, 0.125)
    fresh_origin = _origin("placement-fresh", 9, 0.5)
    committed = _block(
        {
            3: _cell_values(kind, 1.5),
            9: _cell_values(kind, -2.0),
            11: _cell_values(kind, 3.0),
        },
        kind=kind, default_origin=committed_origin)
    fresh = _block(
        {
            3: _cell_values(kind, 99.0),   # magnitude-only -> no flip
            9: _cell_values(kind, 2.0),    # crosses zero -> winner flip
            11: _cell_values(kind, 3.0),   # full agreement -> no flip
            40: _cell_values(kind, 0.75),  # novel
        },
        kind=kind,
        origin_by_flat={11: committed_origin},
        default_origin=fresh_origin)

    merged, drops = supersede_with_committed(fresh, committed)
    assert merged is not None
    assert drops == SupersessionDrops(
        dropped=_dropped_count(fresh, committed), winner_flips=1)
    assert drops.dropped == 3

    agreeing = _block(
        {11: _cell_values(kind, 3.0), 41: _cell_values(kind, 0.5)},
        kind=kind, default_origin=committed_origin)
    agreed_merge, agreed_drops = supersede_with_committed(
        agreeing, committed)
    assert agreed_merge is not None
    assert agreed_drops == SupersessionDrops(dropped=1, winner_flips=0)


# --- winner_codes conventions (hand-built vectors) -----------------------


def test_winner_codes_k_sign_categories() -> None:
    """K (arity 1): the implied bit decision is the LLR sign category;
    -0.0 and +0.0 share the zero category (np.sign semantics)."""
    codes = winner_codes(
        "k", np.asarray([[1.5], [-0.5], [0.0], [-0.0]], np.float32))
    assert codes.tolist() == [1, -1, 0, 0]


def test_winner_codes_cmy7_w_relative_winner() -> None:
    """CMY7 (arity 6): six W-relative scores (color_tile.cmy7_demap_
    payload) — W (code 0) wins when no score is positive, including the
    exact-zero maximum; otherwise the winner is argmax + 1, first
    maximum on ties."""
    rows = np.asarray([
        [-1.0, -2.0, -3.0, -0.5, -4.0, -1.5],   # all negative -> W
        [0.0, -1.0, -2.0, -3.0, -4.0, -5.0],    # exact-zero max -> W
        [-1.0, 2.0, 1.0, -3.0, 0.5, -2.0],      # argmax 1 -> state 2
        [3.0, 1.0, 3.0, 0.0, -1.0, -2.0],       # tie -> first max, state 1
    ], np.float32)
    assert winner_codes("cmy7", rows).tolist() == [0, 0, 2, 1]


def test_winner_codes_cmy8_plane_sign_patterns() -> None:
    """CMY8 (arity 3): the implied (C, M, Y) bit triple is the per-plane
    sign-category pattern; any single plane crossing zero changes the
    code, and magnitude changes never do."""
    rows = np.asarray([
        [1.0, -1.0, 0.5],
        [9.0, -0.25, 2.0],    # same pattern as row 0
        [1.0, 1.0, 0.5],      # M plane flipped
        [-1.0, -1.0, -0.5],   # all flipped
    ], np.float32)
    codes = winner_codes("cmy8", rows)
    assert codes[0] == codes[1]
    assert len({int(codes[0]), int(codes[2]), int(codes[3])}) == 3
