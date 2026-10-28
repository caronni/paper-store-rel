"""PK10 / arm A4b: KnownField-conditioned CMY8 marginalization.

The pins this packet is judged by (RECEIVE-DESIGN §6.2a, P9 ruling, and
COLOR-UPLIFT-PLAN §3's risk register):

* the marginalization kernel is a GENERALIZATION, not a fork — an
  unconditioned call is bit-for-bit the historical expression, and the
  conditioned one restricts to exactly the states a certified SIBLING
  allows (never the plane's own value);
* THE SCOPED MASKING LAW, pinned three ways: a masked cell contributes
  its full state to the QDA, its masked pattern to exactly one stratum,
  and its true bits to registration/anchoring;
* R9 — conditioning reads the KnownField and nothing else: no marginal,
  no candidate, no same-barrier certificate, and (this arm's own
  narrowing) no FORMAT furniture at emission;
* R10 — a conditioning-driven evidence change is LEGITIMATELY different
  evidence: the emitted block carries the conditioning certificates in
  its dependency ids, the divergence audit pairs it as a new identity,
  and mop-up supersession keeps the committed bytes and counts the
  difference as advice;
* R11 — the pattern-stratified PAVA is the safety: a stratum that cannot
  earn its map, or that is starved, falls back to the UNCONDITIONED
  marginal exactly;
* the exact null: cmy7 and K are no-ops, force-null is a no-op, and a
  cell with no certified sibling is byte-identical to today.
"""
from __future__ import annotations

import sys

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter
from scipy.special import logsumexp

from holo.core import channel
from holo.format import metadata
from holo.format.registry import get_format_row
from holo.gen.color_compose import compose_color_tile
from holo.receive import color_conditioning as cc
from holo.receive import (
    color_context,
    color_detect,
    color_fitting,
    color_payload,
    color_stack,
)
from holo.receive.color_payload import collect_color_evidence
from holo.receive.payload_model import EvidenceSource
from holo.receive.placement.model import (
    AddressResult,
    AffinePose,
    CandidateScore,
    PlacedPatch,
    PlacedSegment,
    PoseSegment,
    PoseWindow,
)
from holo.receive.records import certificate_record_from_user_bits
from holo.receive.scan import open_capture

ROW = "c3-cmy8-p120-v0@2240x1536"
CMY7_ROW = "c3-cmy7-p120-v0@2240x1536"
LANE = "l00-3ppc-600dpi"
PPC = 4
K_TOTAL = 837
BLUR_PX = 1.0
TILES_YX = (3, 4)


# ---------------------------------------------------------------------------
# the kernel
# ---------------------------------------------------------------------------


def _scores(seed: int, rows: int = 64) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0, 2.0, (rows, 8))


def test_unconditioned_marginal_is_the_historical_expression() -> None:
    """A generalization, not a fork: no KnownField ⇒ the same bytes."""
    scores = _scores(0xA4B0)
    got = color_detect.cmy8_marginal_llrs(scores)
    for plane in range(3):
        one = color_detect._CMY8_STATE_BITS[:, plane]
        expected = (logsumexp(scores[:, one], axis=1)
                    - logsumexp(scores[:, ~one], axis=1))
        assert np.array_equal(got[:, plane], expected)
    # An all-unknown KnownField is the SAME array, not merely close.
    blank = np.zeros((scores.shape[0], 3), np.bool_)
    assert np.array_equal(
        got,
        color_detect.cmy8_marginal_llrs(
            scores, blank, np.zeros_like(blank, np.uint8)))


@pytest.mark.parametrize("plane", (0, 1, 2))
@pytest.mark.parametrize("sibling_bits", ((0, 0), (0, 1), (1, 0), (1, 1)))
def test_conditioned_marginal_is_the_exact_state_subset(
    plane: int, sibling_bits: tuple[int, int],
) -> None:
    """2-vs-2 and 1-vs-1 are the literal consistent-state log ratios."""
    scores = _scores(0xA4B1 + plane, rows=8)
    first, second = color_detect.CMY8_SIBLINGS[plane]
    mask = np.zeros((scores.shape[0], 3), np.bool_)
    bits = np.zeros((scores.shape[0], 3), np.uint8)
    # Row 0 knows one sibling, row 1 knows both; the rest know nothing.
    mask[0, first] = True
    bits[0, first] = sibling_bits[0]
    mask[1, first] = mask[1, second] = True
    bits[1, first], bits[1, second] = sibling_bits
    got = color_detect.cmy8_marginal_llrs(scores, mask, bits)

    def states(fixed: dict[int, int]) -> tuple[list[int], list[int]]:
        allowed = [
            state for state in range(8)
            if all((state >> at) & 1 == value for at, value in fixed.items())
        ]
        return ([s for s in allowed if (s >> plane) & 1],
                [s for s in allowed if not (s >> plane) & 1])

    ones, zeros = states({first: sibling_bits[0]})
    assert len(ones) == len(zeros) == 2
    assert np.isclose(
        got[0, plane],
        logsumexp(scores[0, ones]) - logsumexp(scores[0, zeros]))
    ones, zeros = states({first: sibling_bits[0], second: sibling_bits[1]})
    assert len(ones) == len(zeros) == 1
    # Arity 2 is a bare difference and must be EXACT, not approximate.
    assert got[1, plane] == scores[1, ones[0]] - scores[1, zeros[0]]
    # Rows with nothing known keep the unconditioned value byte for byte.
    assert np.array_equal(
        got[2:], color_detect.cmy8_marginal_llrs(scores)[2:])


def test_a_plane_is_never_conditioned_on_its_own_certified_value() -> None:
    """Knowing C changes M and Y; it must never change C itself."""
    scores = _scores(0xA4B2, rows=6)
    mask = np.zeros((6, 3), np.bool_)
    bits = np.zeros((6, 3), np.uint8)
    mask[:, 0] = True
    bits[:, 0] = 1
    got = color_detect.cmy8_marginal_llrs(scores, mask, bits)
    raw = color_detect.cmy8_marginal_llrs(scores)
    assert np.array_equal(got[:, 0], raw[:, 0])
    assert not np.array_equal(got[:, 1], raw[:, 1])
    assert not np.array_equal(got[:, 2], raw[:, 2])
    # And the subset really is "states with C=1", not a re-weighting.
    allowed = color_detect.cmy8_sibling_allowed(1, mask, bits)
    assert np.array_equal(
        allowed[0], np.asarray([(s & 1) == 1 for s in range(8)]))


# ---------------------------------------------------------------------------
# the reveal field and the masking law
# ---------------------------------------------------------------------------


def test_reveal_field_extends_the_hash_family_without_colliding() -> None:
    """§6.2a's named &4 is the low bit; &8 is what "both" needed."""
    yy, xx = np.meshgrid(np.arange(64), np.arange(64), indexing="ij")
    cells = np.stack((yy.ravel(), xx.ravel()), axis=1).astype(np.int64)
    codes = cc.masking_reveal_codes(cells)
    hashed = 131 * cells[:, 0] + 17 * cells[:, 1]
    # The spec's reveal bit IS this field's sibling selector.
    assert np.array_equal((codes & 1).astype(bool), (hashed & 4) != 0)
    assert np.array_equal((codes & 2).astype(bool), (hashed & 8) != 0)
    # Exactly one pattern per cell, and the four are equinumerous.
    assert np.array_equal(np.bincount(codes, minlength=4), np.full(4, 1024))
    # Disjoint from the QDA split (&1) and P1's sub-split (&2): a cell's
    # mask cannot correlate with which side of either it landed on.
    for code in range(4):
        selected = codes == code
        assert np.count_nonzero(selected & ((hashed & 1) == 0)) == 512
        assert np.count_nonzero(selected & ((hashed & 2) == 0)) == 512


def test_pattern_view_reveals_only_the_pattern_s_own_siblings() -> None:
    """The VIEW is derived from the code — it is never a KnownField."""
    for plane in range(3):
        first, second = color_detect.CMY8_SIBLINGS[plane]
        view = cc.pattern_view_mask(plane, np.arange(4))
        assert not view[:, plane].any()
        assert view[:, first].tolist() == [False, True, False, True]
        assert view[:, second].tolist() == [False, False, True, True]


def test_pattern_codes_never_read_the_plane_s_own_column() -> None:
    known = np.asarray([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]], bool)
    codes = cc.conditioning_pattern_codes(known)
    # C known: no effect on C's own code, sib1 of M, sib1 of Y.
    assert codes[0].tolist() == [0, 1, 1]
    assert codes[1].tolist() == [1, 0, 2]
    assert codes[2].tolist() == [2, 2, 0]
    assert codes[3].tolist() == [3, 3, 3]


# ---------------------------------------------------------------------------
# the fixture: a cmy8 field with PARTIAL certified knowledge
# ---------------------------------------------------------------------------


def _candidate() -> CandidateScore:
    return CandidateScore(
        0, (0, 0), 0, 0.0, 0.0, 0, 0, 1000, 1000, 20.0, True, "pk10-test")


def _grid(shape: tuple[int, int]) -> np.ndarray:
    yy, xx = np.meshgrid(
        np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    return np.stack((yy, xx), axis=-1).reshape(-1, 2).astype(np.int32)


def _compose(spec, tiles_yx, seed):
    rng = np.random.default_rng(seed)
    field = np.empty((tiles_yx[0] * 64, tiles_yx[1] * 64), np.uint8)
    symbols_by_tile = {}
    for ty in range(tiles_yx[0]):
        for tx in range(tiles_yx[1]):
            symbols = {
                stream.stream_id: rng.integers(
                    0, 2, stream.symbol_bits, dtype=np.uint8)
                for stream in spec.stream_profiles
            }
            symbols_by_tile[(ty, tx)] = symbols
            field[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64] = (
                compose_color_tile(
                    spec, spec.tile_counter(0, ty, tx), symbols, K_TOTAL))
    return field, symbols_by_tile


def _raster(field: np.ndarray):
    planes = channel.states_to_planes(field)
    rgb = np.repeat(np.repeat(
        (1 - planes) * np.uint8(255), PPC, axis=0), PPC, axis=1
    ).astype(np.float64)
    for plane in range(3):
        rgb[..., plane] = gaussian_filter(
            rgb[..., plane], BLUR_PX, mode="nearest")
    return open_capture(
        np.clip(np.round(rgb), 0, 255).astype(np.uint8), 600.0)


def _patch(patch_id: int, shape_cells: tuple[int, int]) -> PlacedPatch:
    center = (PPC - 1.0) * 0.5
    pose = AffinePose(
        (center, center), ((float(PPC), 0.0), (0.0, float(PPC))),
        (0.5, 0.5), float(PPC), 0.0)
    local = _grid(shape_cells)
    segment = PoseSegment(
        PoseWindow(patch_id, 0, (0, 0), shape_cells), pose,
        local.shape[0], 1.0, (float(PPC), float(PPC)), 0.0)
    return PlacedPatch(
        patch_id, 0, 0, "pk10-test", _candidate(), (),
        PlacedSegment(segment, (0, 0), 0, local), (), False,
        local.astype(np.int32))


def _certificates(spec, symbols_by_tile, per_stream):
    """``per_stream`` maps a stream id to the tiles certified for it."""
    meta = metadata.encode_metadata(0, K_TOTAL)
    records = []
    for stream_id, tiles in sorted(per_stream.items()):
        for ty, tx in tiles:
            counter = spec.tile_counter(0, ty, tx)
            user = np.concatenate((
                np.asarray([metadata.tile_bit(meta, counter)], np.uint8),
                symbols_by_tile[(ty, tx)][stream_id]))
            records.append(certificate_record_from_user_bits(
                spec, page=0, tile_yx=(ty, tx), stream_id=stream_id,
                user_bits=user, origin_attempt_id=f"pk10-{stream_id}-{ty}{tx}"))
    return tuple(records)


def _fixture(per_stream=None, row=ROW):
    spec = get_format_row(row)
    field, symbols = _compose(spec, TILES_YX, 0xC01A0)
    raster = _raster(field)
    patch = _patch(0, (TILES_YX[0] * 64, TILES_YX[1] * 64))
    address = AddressResult((patch,), (), (), ((0, "placed"),), 1)
    source = EvidenceSource(raster.source.sha256, LANE)
    certs = (() if per_stream is None
             else _certificates(spec, symbols, per_stream))
    return spec, raster, address, source, certs, field


# C on every tile, M on a strict subset: the hp c3-cmy8 shape (C dense,
# M sparse), which is exactly what makes M|C a real cert-cross stratum
# and every C-only tile a deployment target.
_C_TILES = tuple(
    (ty, tx) for ty in range(TILES_YX[0]) for tx in range(TILES_YX[1]))
_M_TILES = ((0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1))


def _region(evidence):
    assert len(evidence.regions) == 1
    return evidence.regions[0]


#: The arm override ``_collect`` runs under.  ``None`` is the standard
#: ladder, where since PK-CLEAN A4b is UNREACHABLE; the ``u_lane``
#: fixture below flips it to the arm's own supplemental lane.
_ARM: str | None = None


def _collect(per_stream=None, row=ROW):
    spec, raster, address, source, certs, _field = _fixture(per_stream, row)
    return collect_color_evidence(
        raster, source, address, spec, certificates=certs,
        arm_override=_ARM)


@pytest.fixture
def u_lane(monkeypatch):
    """Run the ladder through A4b's SUPPLEMENTAL LANE, where it is live.

    The arm is OVERRIDE-ONLY in the tree (PK-CLEAN; PK10's referendum
    said it does not earn a place in the standard ladder, and PK4.3's
    supplemental-lane law says an arm in that position is scheduled
    rather than gated).  Unreachable there means ABSENT: ``color_stack``
    never gathers a population.  The MECHANISM still has to be tested —
    the u-lane runs it on every colour cmy8 capture — so every test below
    that is about what A4b DOES asks for this fixture, and the pin that
    the standard ladder does nothing is
    :func:`test_the_standard_ladder_is_the_arm_never_built_path_bit_exact`.
    """
    monkeypatch.setattr(
        sys.modules[__name__], "_ARM", color_stack.UPLIFT_ARM_A4B)


# ---------------------------------------------------------------------------
# the exact nulls
# ---------------------------------------------------------------------------


def test_lane_zero_never_gathers_a_population_or_moves_a_byte(
    u_lane,
) -> None:
    """No certificate anywhere ⇒ the arm refuses before it costs anything."""
    without = _collect()
    region = _region(without)
    assert region.conditioning.reason == cc.CONDITIONING_REASON_NO_CELLS
    assert region.conditioning.strata == ()
    assert not region.conditioning.adopted
    assert region.conditioning.cells_arity1 == 0


def test_cmy7_regions_are_a_strict_no_op() -> None:
    """A4b is CMY8's half of the rung; cmy7 emits not even a key."""
    evidence = _collect(row=CMY7_ROW)
    region = _region(evidence)
    assert region.conditioning == cc.ConditioningSummary()
    assert region.conditioning.reason == ""


def test_force_null_never_fits_conditioning(u_lane, monkeypatch) -> None:
    per_stream = {"C": _C_TILES, "M": _M_TILES}
    live = _region(_collect(per_stream=per_stream))
    assert live.conditioning.reason != ""
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    null = _region(_collect(per_stream=per_stream))
    assert null.conditioning == cc.ConditioningSummary()


def test_format_furniture_alone_never_conditions_an_emitted_cell(
    u_lane,
) -> None:
    """R9's narrowing: only CERTIFIED authority reaches the deployment
    population.  Furniture is known exactly, and is still excluded — its
    cells are erased by the certification chain, so conditioning them
    would move bytes for no decode at all."""
    spec, raster, address, source, _certs, _field = _fixture()
    evidence = collect_color_evidence(
        raster, source, address, spec, certificates=())
    region = _region(evidence)
    # Every window row carries format furniture (word + dust) with all
    # three components known...
    assert region.n_train > 0
    # ...and the emitted population still counts ZERO conditioned cells.
    assert region.conditioning.cells_arity1 == 0
    assert region.conditioning.cells_arity2 == 0


# ---------------------------------------------------------------------------
# THE OVERRIDE-ONLY LAW (PK-CLEAN; PK10's referendum, PK4.3's law)
# ---------------------------------------------------------------------------


def test_the_standard_ladder_is_the_arm_never_built_path_bit_exact(
    monkeypatch,
) -> None:
    """UNREACHABLE ≡ ABSENT, on a capture where the arm WOULD have fired.

    The referendum's outcome is that A4b does not earn a place in the
    standard ladder on this corpus (COLOR-UPLIFT-MEASUREMENTS §9), and
    PK-CLEAN retired the flag that used to express that, because a flag
    is still something to flip: the arm is now reachable only from its
    supplemental lane.  Unreachable has to mean the receiver as it was,
    not the receiver with a gate closed: same evidence bytes, same page
    cells, same region summary, and not one diagnostic key.  The
    certificates here are the C+M set that makes the forced arm adopt —
    proven by the fixture-sharing tests below — so this pin cannot pass
    vacuously.
    """
    spec, raster, address, source, certs, _field = _fixture(
        {"C": _C_TILES, "M": _M_TILES})
    shipped = collect_color_evidence(
        raster, source, address, spec, certificates=certs)
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    never_built = collect_color_evidence(
        raster, source, address, spec, certificates=certs)
    monkeypatch.delenv(color_stack.FORCE_NULL_ENV, raising=False)

    assert not hasattr(cc, "CONDITIONING_PARKED")
    assert len(shipped.windows) == len(never_built.windows)
    for left, right in zip(shipped.windows, never_built.windows, strict=True):
        assert np.array_equal(left.page_cells_yx, right.page_cells_yx)
        # Byte-exact, not merely close: A4b parked may not perturb one
        # float32 of durable evidence.
        assert left.evidence_values.tobytes() == right.evidence_values.tobytes()
        assert left.heldout_logloss == right.heldout_logloss
        assert (left.dependency_certificate_ids
                == right.dependency_certificate_ids)
    # The summary is the DEFAULT instance, so `production_color` emits no
    # `color.conditioning.*` key at all — the existing zero-keys path.
    assert _region(shipped).conditioning == cc.ConditioningSummary()
    assert _region(shipped).conditioning.reason == ""
    from holo.receive._production_diagnostics import color_region_details

    keys = {row.name for row in color_region_details(_region(shipped))}
    assert not any(name.startswith("color.conditioning") for name in keys)


def test_the_standard_ladder_gathers_no_population_at_all(
    monkeypatch,
) -> None:
    """Cheaper than a gate refusal: nothing is fitted, nothing gathered."""
    calls: list[str] = []
    monkeypatch.setattr(
        color_stack, "fit_conditioned_marginals",
        lambda *a, **k: calls.append("fit"))
    monkeypatch.setattr(
        color_stack, "emitted_conditioning_arities",
        lambda *a, **k: calls.append("census") or (0, 0))
    _collect(per_stream={"C": _C_TILES, "M": _M_TILES})
    assert calls == []


def test_the_u_lane_is_what_the_fixture_does(u_lane) -> None:
    """The arm is not deleted — it is SCHEDULED, and the lane runs it.

    ``arm_override`` is the whole reachability test (no constant, no
    flag), and the region gate it used to face is measured and published
    but no longer consulted: the verdict a forced lane reports is
    ``region_gate_forced``, never ``adopted``.
    """
    assert _ARM == color_stack.UPLIFT_ARM_A4B
    region = _region(_collect(per_stream={"C": _C_TILES, "M": _M_TILES}))
    assert region.conditioning.reason == cc.CONDITIONING_REASON_REGION_FORCED
    assert region.conditioning.adopted is True


# ---------------------------------------------------------------------------
# the live arm
# ---------------------------------------------------------------------------


def test_partial_certificates_make_a_real_conditioned_population(
    u_lane,
) -> None:
    evidence = _collect(per_stream={"C": _C_TILES, "M": _M_TILES})
    region = _region(evidence)
    conditioning = region.conditioning
    assert conditioning.reason != cc.CONDITIONING_REASON_NO_CELLS
    # C certified everywhere ⇒ M and Y marginalize 2-vs-2 on every
    # emitted cell of a C-only tile, and 1-vs-1 where M certified too.
    assert conditioning.cells_arity1 > 0
    assert conditioning.cells_arity2 > 0
    by_key = {(row[0], row[1]): row for row in conditioning.strata}
    assert len(by_key) == 9  # three planes x three nonempty patterns
    # The two-source provenance law, per stratum: cert-cross material
    # only exists where a sibling really certified, the masked furniture
    # floor exists everywhere.
    assert all(row[4] > 0 for row in conditioning.strata)
    assert conditioning.cert_cells > 0
    assert conditioning.masked_cells > 0
    # M given C is the stratum the uplift target's C∩M tiles feed.
    m_given_c = by_key[(1, 1)]
    assert m_given_c[3] > 0, "M|C must have cert-cross material"
    # ...and the region RENDERS.  The stratum Details name planes through
    # `channel.PLANE_ORDER`, and the only populated-strata path runs on a
    # u-lane, so a missing import there is invisible to every other test
    # and fatal on the one lane that publishes them.
    from holo.receive._production_diagnostics import color_region_details

    keys = {row.name for row in color_region_details(region)}
    assert "color.conditioning.strata" in keys


def _arm_pair(monkeypatch, per_stream):
    """(live, force-null) evidence over the SAME certificates.

    The only honest A4b differential.  Toggling the certificates instead
    would move the KnownField, which moves the QDA's own owner
    population — a partially certified cell resolves no state and cannot
    own, a fully certified one can — so a cert-vs-no-cert pair measures
    two arms AND two detectors.  Toggling force-null holds everything
    else: A3 is unreachable on both sides (its own u-lane is a different
    lane) and the cmy7 head does not exist on a cmy8 region.

    ``live`` runs the arm's SUPPLEMENTAL LANE, which since PK-CLEAN is
    the only place A4b runs at all — force-null skips u-lanes in
    production, so the null side is the same lane with the whole stack
    off, which is exactly the pre-campaign evidence path.
    """
    spec, raster, address, source, certs, field = _fixture(per_stream)
    live = collect_color_evidence(
        raster, source, address, spec, certificates=certs,
        arm_override=color_stack.UPLIFT_ARM_A4B)
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    try:
        null = collect_color_evidence(
            raster, source, address, spec, certificates=certs,
            arm_override=color_stack.UPLIFT_ARM_A4B)
    finally:
        monkeypatch.delenv(color_stack.FORCE_NULL_ENV, raising=False)
    return live, null, certs, spec, field


def _tile_of(cells: np.ndarray) -> np.ndarray:
    return np.stack((cells[:, 0] // 64, cells[:, 1] // 64), axis=1)


def test_conditioning_changes_only_cells_with_a_certified_sibling(
    u_lane, monkeypatch,
) -> None:
    """The head is an OVERWRITE: a plane with no certified sibling on
    that cell keeps its bytes, whatever the arm did elsewhere."""
    live, null, _certs, _spec, _field = _arm_pair(
        monkeypatch, {"C": _C_TILES, "M": _M_TILES})
    assert _region(live).conditioning.adopted
    window, base = live.windows[0], null.windows[0]
    assert np.array_equal(window.page_cells_yx, base.page_cells_yx)
    tiles = _tile_of(np.asarray(window.page_cells_yx, np.int64))
    m_certified = np.asarray([
        (int(ty), int(tx)) in set(_M_TILES) for ty, tx in tiles])
    # C's own siblings are M and Y.  On a C-only tile neither is
    # certified, so C's marginal is pattern ∅ and its bytes must not
    # move; where M certified too, C is legitimately conditioned.
    assert np.array_equal(
        window.evidence_values[~m_certified, 0],
        base.evidence_values[~m_certified, 0])
    assert not np.array_equal(
        window.evidence_values[m_certified, 0],
        base.evidence_values[m_certified, 0])
    # M has a certified sibling (C) everywhere, so M moves everywhere it
    # was not already suppressed.
    assert np.any(window.evidence_values[:, 1] != base.evidence_values[:, 1])


def test_conditioned_evidence_moves_toward_the_truth(
    u_lane, monkeypatch,
) -> None:
    """R11's point from the other side: with an honest calibration the
    sharpened evidence must not be sharpened the WRONG way."""
    live, null, _certs, _spec, field = _arm_pair(
        monkeypatch, {"C": _C_TILES, "M": _M_TILES})
    assert _region(live).conditioning.adopted
    cells = np.asarray(live.windows[0].page_cells_yx, np.int64)
    truth = channel.states_to_planes(field[cells[:, 0], cells[:, 1]])
    sign = np.where(truth > 0, 1.0, -1.0)
    live_loss = np.logaddexp(
        0.0, -sign * live.windows[0].evidence_values).mean()
    null_loss = np.logaddexp(
        0.0, -sign * null.windows[0].evidence_values).mean()
    assert live_loss < null_loss


# ---------------------------------------------------------------------------
# R10: conditioning-dependent evidence is legitimately different evidence
# ---------------------------------------------------------------------------


def test_emitted_evidence_names_the_conditioning_certificates(
    u_lane,
) -> None:
    per_stream = {"C": _C_TILES, "M": _M_TILES}
    spec, raster, address, source, certs, _field = _fixture(per_stream)
    evidence = collect_color_evidence(
        raster, source, address, spec, certificates=certs)
    named = set(evidence.windows[0].dependency_certificate_ids)
    assert named == {row.certificate_id for row in certs}
    # And the blocks carry them into persistence, which is where the
    # divergence audit and mop-up supersession read provenance from.
    blocks = color_payload.color_blocks_from_frontier(evidence)
    assert blocks
    for block in blocks:
        for origin in block.origins:
            assert set(origin.dependency_certificate_ids) <= named
            assert origin.dependency_certificate_ids


def test_divergence_audit_pairs_conditioned_evidence_as_a_new_identity(
    u_lane, monkeypatch,
) -> None:
    """R10: same cell, different KnownField ⇒ a different evidence block
    id, so the audit records a fresh pairing instead of a contradiction."""
    from holo.receive.records import certificate_divergence

    live, null, certs, spec, _field = _arm_pair(
        monkeypatch, {"C": _C_TILES, "M": _M_TILES})
    assert _region(live).conditioning.adopted
    live_blocks = color_payload.color_blocks_from_frontier(live)
    null_blocks = color_payload.color_blocks_from_frontier(null)
    by_address = {row.address: row for row in null_blocks}
    moved = [row for row in live_blocks
             if row.block_id != by_address[row.address].block_id]
    assert moved, "conditioning must actually move an evidence block"
    audited = certificate_divergence(
        tuple(live_blocks) + tuple(null_blocks), certs, spec)
    identities = [row.divergence_id for row in audited]
    assert len(identities) == len(set(identities))
    # Both readings of the same tile are audited and neither is refused;
    # the conditioning-driven change is legitimately different evidence,
    # not a contradiction to resolve.
    per_block = {row.evidence_block_id: row for row in audited}
    disagreement = [
        (per_block[block.block_id].n_disagree,
         per_block[by_address[block.address].block_id].n_disagree)
        for block in moved
        if block.block_id in per_block
        and by_address[block.address].block_id in per_block]
    assert disagreement
    # And the audit's verdict on conditioned evidence is never worse in
    # aggregate — conditioning on certified truth cannot argue against it.
    assert (sum(row[0] for row in disagreement)
            <= sum(row[1] for row in disagreement))


def test_mopup_supersession_keeps_committed_bytes_under_conditioning(
    u_lane, monkeypatch,
) -> None:
    """R10: the extension-only rule is about CELLS, not about agreement;
    a fresh conditioned observation at a committed cell is dropped and
    counted as advice, never treated as a fault."""
    from holo.receive.evidence_blocks import supersede_with_committed

    live, null, _certs, _spec, _field = _arm_pair(
        monkeypatch, {"C": _C_TILES, "M": _M_TILES})
    assert _region(live).conditioning.adopted
    committed = color_payload.color_blocks_from_frontier(null)[0]
    fresh = next(
        row for row in color_payload.color_blocks_from_frontier(live)
        if row.address == committed.address)
    assert fresh.block_id != committed.block_id
    merged, drops = supersede_with_committed(fresh, committed)
    # Every cell was already committed, so nothing is novel: the mop-up
    # vanishes and the difference is a tally, not an exception.
    assert merged is None
    assert drops.dropped == len(committed.observed_flat())
    assert drops.winner_flips >= 0


# ---------------------------------------------------------------------------
# R11 and the masking law, at the fitter
# ---------------------------------------------------------------------------


def _detector_and_populations(seed: int, n: int = 900):
    """A synthetic CMY8 detector with a fittable stratum population."""
    rng = np.random.default_rng(seed)
    means = np.asarray([
        [1.0, 1.0, 1.0], [0.2, 1.0, 1.0], [1.0, 0.2, 1.0],
        [0.2, 0.2, 1.0], [1.0, 1.0, 0.2], [0.2, 1.0, 0.2],
        [1.0, 0.2, 0.2], [0.2, 0.2, 0.2]])
    states = rng.integers(0, 8, n)
    features = means[states] + rng.normal(0.0, 0.35, (n, 3))
    detector = color_detect.fit_cmy8_detector(
        features, states, features, states)
    scores = color_detect.qda_log_scores(detector.qda, features)
    bits = channel.states_to_planes(states.astype(np.int8))
    pattern = np.repeat(
        (rng.integers(0, 4, n)).astype(np.int8)[:, None], 3, axis=1)
    population = cc.ConditioningPopulation(
        scores=scores, bits=bits,
        labelled=np.ones((n, 3), np.bool_), pattern=pattern,
        kinds=(np.arange(n) % 2).astype(np.int8),
        from_certificates=np.zeros(n, np.bool_))
    return detector, population


def test_starved_stratum_falls_back_to_the_unconditioned_marginal() -> None:
    detector, population = _detector_and_populations(0xA4B5, n=900)
    tiny = cc.ConditioningPopulation(
        scores=population.scores[:20], bits=population.bits[:20],
        labelled=population.labelled[:20], pattern=population.pattern[:20],
        kinds=population.kinds[:20],
        from_certificates=population.from_certificates[:20])
    fit = cc.fit_conditioned_marginals(detector, tiny, population)
    assert fit.head is None
    assert fit.reason == cc.CONDITIONING_REASON_NO_STRATUM
    assert {row.reason for row in fit.strata} == {
        cc.CONDITIONING_REASON_STARVED}
    assert all(row.calibration is None for row in fit.strata)


def test_a_starved_stratum_leaves_its_cells_byte_identical() -> None:
    """The fallback is the incumbent map on the unconditioned marginal —
    the same arrays, not an identity transform."""
    detector, population = _detector_and_populations(0xA4B6, n=900)
    fit = cc.fit_conditioned_marginals(detector, population, population)
    if fit.head is None:
        pytest.skip("the region gate refused on this synthetic channel")
    # Blank out one stratum by hand and check its cells do not move.
    strata = [list(row) for row in fit.head.strata]
    strata[1][1] = None
    starved = cc.Cmy8ConditionedHead(
        tuple(tuple(row) for row in strata))  # type: ignore[arg-type]
    features = np.random.default_rng(3).normal(0.6, 0.4, (40, 3))
    mask = np.zeros((40, 3), np.bool_)
    bits = np.zeros((40, 3), np.uint8)
    mask[:, 0] = True           # C known ⇒ M sits in stratum (1, 1)
    got = starved.llrs(detector, features, mask, bits)
    plain = detector.llrs(features)
    assert np.array_equal(got[:, 1], plain[:, 1])


def test_no_certified_sibling_is_byte_identical_through_the_head() -> None:
    detector, population = _detector_and_populations(0xA4B7, n=900)
    fit = cc.fit_conditioned_marginals(detector, population, population)
    if fit.head is None:
        pytest.skip("the region gate refused on this synthetic channel")
    features = np.random.default_rng(11).normal(0.6, 0.4, (64, 3))
    blank = np.zeros((64, 3), np.bool_)
    assert np.array_equal(
        fit.head.llrs(detector, features, blank,
                      np.zeros_like(blank, np.uint8)),
        detector.llrs(features))


def test_unsupported_planes_stay_exactly_zero_under_conditioning() -> None:
    """A component-local erasure outranks every calibration."""
    detector, population = _detector_and_populations(0xA4B8, n=900)
    fit = cc.fit_conditioned_marginals(detector, population, population)
    if fit.head is None:
        pytest.skip("the region gate refused on this synthetic channel")
    dead = cc.Cmy8ConditionedHead(fit.head.strata)
    from dataclasses import replace as _replace

    starved_support = _replace(
        detector,
        calibration_support=_replace(
            detector.calibration_support,
            components=(
                _replace(detector.calibration_support.components[0],
                         supported=False, reason="class_labels:0"),
                *detector.calibration_support.components[1:])))
    features = np.random.default_rng(5).normal(0.6, 0.4, (16, 3))
    mask = np.ones((16, 3), np.bool_)
    mask[:, 0] = False
    bits = np.zeros((16, 3), np.uint8)
    values = dead.llrs(starved_support, features, mask, bits)
    assert np.array_equal(values[:, 0], np.zeros(16))


def _context_head(n_states: int, seed: int):
    """A fully adopted A5 matrix head with small, finite, nonzero curves."""
    rng = np.random.default_rng(seed)
    offsets = rng.normal(
        0.0, 0.15, (n_states, 3, color_context.N_CONTEXT_BINS))
    return color_context.ContextHead(
        locus=color_context.LOCUS_STATES,
        variant=color_context.CONTEXT_VARIANT_MATRIX,
        offsets=offsets,
        applied=np.ones(offsets.shape[:-1], np.bool_),
    )


def test_a4b_and_a5_compose_on_a_conditioned_cmy8_cell() -> None:
    """The A4b∘A5 branch — deployed, and until now covered by no test.

    A u-a4b lane can carry BOTH heads: A4b conditions a plane on the
    states its certified siblings fix, and A5 corrects the state scores
    before that marginalization.  Neither gate ever scored the
    composition (A5's bins and fit population are cut UNCONDITIONED, and
    A4b earned itself against the unconditioned incumbent — the asymmetry
    recorded at ``color_stack``'s A5 block), so what this pins is the
    mechanics: the composed path is well formed, it is the context-only
    path EXACTLY wherever no sibling is known, and where one is known it
    really does compose rather than dropping either head.
    """
    detector, population = _detector_and_populations(0xA4C1, n=900)
    conditioned = cc.fit_conditioned_marginals(
        detector, population, population)
    if conditioned.head is None:
        pytest.skip("the region gate refused on this synthetic channel")
    head = _context_head(detector.qda.n_states, 0xA4C2)

    both = color_fitting._DetectorFit(
        detector.qda, detector, 0.0, 0.0, 0.0, 0, 0, (),
        conditioned=conditioned.head, context=head)
    context_only = color_fitting._DetectorFit(
        detector.qda, detector, 0.0, 0.0, 0.0, 0, 0, (), context=head)

    rng = np.random.default_rng(0xA4C3)
    features = rng.normal(0.6, 0.4, (48, 3))
    bins = rng.integers(
        -1, color_context.N_CONTEXT_BINS, (48, 3)).astype(np.int8)
    blank = np.zeros((48, 3), np.bool_)
    bits = np.zeros((48, 3), np.uint8)

    composed, divisor = both.evidence_with_divisor(
        features, blank, bits, bins)
    plain = context_only.evidence_with_divisor(features, blank, bits, bins)[0]
    assert np.isfinite(composed).all()
    assert composed.shape == (48, 3)
    # No certified sibling ⇒ byte-identical to the context-only path.
    assert np.array_equal(composed, plain)
    # The divisor is CMY7's saturation canary; CMY8 has none, composed
    # or not.
    assert divisor is None

    # With a sibling known both heads are live: the result stays finite,
    # it moves off the context-only path on the conditioned planes, and
    # the known plane's own column is untouched (a plane is never
    # conditioned on its own certified value).
    mask = np.zeros((48, 3), np.bool_)
    mask[:, 0] = True
    moved = both.evidence_with_divisor(features, mask, bits, bins)[0]
    assert np.isfinite(moved).all()
    assert not np.array_equal(moved[:, 1:], plain[:, 1:])
    assert np.array_equal(moved[:, 0], plain[:, 0])
    # …and A5 is genuinely part of that composition: dropping it moves
    # the same cells again, so this is not the A4b-only path in disguise.
    conditioned_only = color_fitting._DetectorFit(
        detector.qda, detector, 0.0, 0.0, 0.0, 0, 0, (),
        conditioned=conditioned.head)
    without_a5 = conditioned_only.evidence_with_divisor(
        features, mask, bits, None)[0]
    assert not np.array_equal(moved, without_a5)


def test_pattern_zero_cells_are_never_refitted_by_a_stratum() -> None:
    """The ∅ stratum IS the incumbent's own map: A4b never replaces it."""
    detector, population = _detector_and_populations(0xA4B9, n=900)
    fit = cc.fit_conditioned_marginals(detector, population, population)
    if fit.head is None:
        pytest.skip("the region gate refused on this synthetic channel")
    assert all(row[0] is None for row in fit.head.strata)
    assert all(row.pattern != 0 for row in fit.strata)


def test_one_masked_cell_lands_in_exactly_one_stratum_per_plane() -> None:
    """The masking law's second pin, counted."""
    detector, population = _detector_and_populations(0xA4BA, n=900)
    fit = cc.fit_conditioned_marginals(detector, population, population)
    for plane in range(3):
        rows = [row for row in fit.strata if row.plane == plane]
        assert sorted(row.pattern for row in rows) == [1, 2, 3]
        # Every cell of the population carries exactly one pattern for
        # this plane, so the strata partition it (pattern 0 sits out).
        counted = sum(row.n_cert + row.n_masked for row in rows)
        assert counted == int(np.count_nonzero(
            population.pattern[:, plane] != 0))


def test_a_stratum_that_cannot_earn_its_map_is_refused(monkeypatch) -> None:
    """R11: the pre-gate is real — a map that does not beat the incumbent
    on its own held-out cells never reaches the region comparison."""
    detector, population = _detector_and_populations(0xA4BB, n=900)
    monkeypatch.setattr(
        cc, "_binary_nll",
        lambda llrs, bits: np.zeros(np.asarray(llrs).shape[0]))
    fit = cc.fit_conditioned_marginals(detector, population, population)
    # Every candidate now ties the incumbent exactly, and a tie is a
    # refusal (strict improvement, 1e-9).
    assert fit.head is None
    assert {row.reason for row in fit.strata} == {
        cc.CONDITIONING_REASON_GATE_FAILED}


def test_the_masked_view_never_reaches_the_known_field() -> None:
    """The masking law's first and third pins: the carrier the QDA,
    context, registration and anchoring read is untouched."""
    from holo.receive.known_field import build_known_rows

    spec = get_format_row(ROW)
    cells = _grid((64, 64)).astype(np.int64)
    before = build_known_rows(spec, 0, cells, {}, {})
    # Compute a full masked view over the same cells...
    codes = cc.masking_reveal_codes(cells)
    assert codes.shape == (cells.shape[0],)
    for plane in range(3):
        cc.pattern_view_mask(plane, codes)
    after = build_known_rows(spec, 0, cells, {}, {})
    assert np.array_equal(before.states, after.states)
    assert np.array_equal(before.component_bits, after.component_bits)
    assert np.array_equal(before.component_mask, after.component_mask)
    # And the carrier is read-only, so no view could have written it.
    assert not before.component_bits.flags.writeable
    assert not before.component_mask.flags.writeable


def test_conditioning_does_not_change_the_fitted_qda(
    u_lane, monkeypatch,
) -> None:
    """The masking law's FIRST pin, measured on the real path: a masked
    cell contributes its FULL state to the QDA, so the region model is
    identical with the arm on and off."""
    per_stream = {"C": _C_TILES, "M": _M_TILES}
    live = _region(_collect(per_stream=per_stream))
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    null = _region(_collect(per_stream=per_stream))
    assert live.n_train == null.n_train
    assert live.n_heldout == null.n_heldout
    assert live.class_counts == null.class_counts
    assert live.calibration_labels == null.calibration_labels
    assert live.selected_heldout_logloss == null.selected_heldout_logloss
    assert live.baseline_heldout_logloss == null.baseline_heldout_logloss


def test_conditioning_summary_refuses_an_incoherent_record() -> None:
    with pytest.raises(cc.ConditioningError):
        cc.ConditioningSummary(reason="no_stratum_adopted", adopted=True)
    with pytest.raises(cc.ConditioningError):
        cc.ConditioningSummary(reason="adopted", cells_arity1=-1)
    # A never-measured loss is negative, never NaN: two summaries must
    # stay comparable by ``==`` (the R-delta identity test does exactly
    # that with whole region summaries).
    assert cc.ConditioningSummary() == cc.ConditioningSummary()
    assert cc.ConditioningSummary().incumbent_nll < 0.0
