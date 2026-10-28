"""Focused production color evidence-to-certificate attempt tests."""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

from holo.core import channel, color_tile, keystream
from holo.core.ldpc.frame import (
    ChildDecodeOutcome,
    FrameDecodeOutcome,
)
from holo.devices.profiles import make_spec
from holo.format import pilots
from holo.receive import (
    _runtime_validation,
    color_attempts,
    color_stack,
    tiles,
)
from holo.receive.evidence import AttemptStage, AttemptState
from holo.receive.evidence_blocks import (
    EvidenceOrigin,
    TileAttemptView,
    block_from_rows,
    tile_attempt_view,
)
from holo.receive.records import stream_attempt_identity


ADDRESS = (0, 0, 1)
LANE = "native"


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _relative_scores(
    states: np.ndarray,
    n_states: int,
    strength: float = 24.0,
) -> np.ndarray:
    absolute = np.full(states.shape + (n_states,), -strength, np.float64)
    np.put_along_axis(
        absolute, np.asarray(states)[..., None], 0.0, axis=-1)
    return absolute[..., 1:] - absolute[..., :1]


def _view(
    spec,
    kind: str,
    sequential_values: np.ndarray,
    sequential_observed: np.ndarray | None = None,
    *,
    source_label: str = "capture",
    address: tuple[int, int, int] = ADDRESS,
) -> TileAttemptView:
    values = np.asarray(sequential_values)
    if values.shape != (spec.payload_cells, values.shape[-1]):
        raise AssertionError("test evidence has wrong payload shape")
    observed = (
        np.ones(spec.payload_cells, bool)
        if sequential_observed is None
        else np.asarray(sequential_observed, bool)
    )
    counter = spec.tile_counter(*address)
    order = keystream.color_cell_permutation(
        spec.seed, counter, spec.payload_cells)
    placed = values[order]
    placed_observed = observed[order]
    payload_flat = pilots.color_payload_cell_indices(spec.family_seed)
    origin = EvidenceOrigin(
        "placed-window", 17, 0.125, (_sha("dependency"),))
    rows = [
        (int(flat), placed[index], origin)
        for index, flat in enumerate(payload_flat)
        if placed_observed[index]
    ]
    block = block_from_rows(
        _sha(source_label),
        LANE,
        address[0],
        address[1:],
        rows,
        kind=kind,
    )
    return tile_attempt_view((block,))


def _user_bits(certificate, size: int) -> np.ndarray:
    return np.unpackbits(
        np.frombuffer(certificate.packed_user_bits, np.uint8),
        bitorder="little",
    )[:size]


def _clean_cmy7(coding_id: str):
    spec = make_spec(coding_id)
    profile = spec.stream_profiles[0]
    rng = np.random.default_rng(2207)
    user = rng.integers(0, 2, profile.user_bits, dtype=np.uint8)
    counter = spec.tile_counter(*ADDRESS)
    states = color_tile.cmy7_encode_payload(
        user,
        profile.fec,
        keystream.cmy7_interleave_permutation(
            spec.seed, counter, profile.fec.transmitted_bits),
        keystream.cmy7_dither_bits(
            spec.seed, counter, profile.fec.transmitted_bits),
    )
    view = _view(spec, "cmy7", _relative_scores(states, 7))
    return spec, profile, user, view


def _clean_cmy8(coding_id: str):
    spec = make_spec(coding_id)
    rng = np.random.default_rng(2208)
    users = {
        profile.stream_id: rng.integers(
            0, 2, profile.user_bits, dtype=np.uint8)
        for profile in spec.stream_profiles
    }
    counter = spec.tile_counter(*ADDRESS)
    banks = {
        profile.stream_id: profile.fec
        for profile in spec.stream_profiles
    }
    dithers = {
        profile.stream_id: keystream.cmy8_dither_bits(
            spec.seed,
            profile.stream_id,
            counter,
            profile.fec.transmitted_bits,
        )
        for profile in spec.stream_profiles
    }
    states = color_tile.cmy8_encode_payload(users, banks, dithers)
    marginal = channel.cmy8_raw_marginal_llrs(
        _relative_scores(states, 8))
    view = _view(spec, "cmy8", marginal)
    return spec, users, view


def _child_outcome(
    profile,
    syndromes: tuple[bool, ...],
    *,
    crc_ok: bool | None,
    user_bits: np.ndarray | None = None,
) -> FrameDecodeOutcome:
    children = tuple(
        ChildDecodeOutcome(
            index,
            child.code_id,
            child.shortened_info_tail,
            index + 2,
            syndrome,
        )
        for index, (child, syndrome) in enumerate(
            zip(profile.fec.children, syndromes, strict=True))
    )
    return FrameDecodeOutcome(
        children,
        crc_invoked=all(syndromes),
        crc_ok=crc_ok,
        certified_user_bits=user_bits,
    )


@pytest.mark.parametrize(
    "coding_id",
    ("c2-cmy7-p120-v0", "c3-cmy7-p120-v0"),
)
def test_clean_cmy7_attempt_inverts_both_permutations_and_dither(
    coding_id: str,
) -> None:
    spec, profile, expected_user, view = _clean_cmy7(coding_id)

    result = color_attempts.attempt_color_tile(
        view,
        spec,
        "main",
        AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0],
        lane_id=LANE,
    )

    assert result.record.state is AttemptState.CERTIFIED
    assert result.record.n_informative == spec.payload_cells
    assert result.record.syndrome_ok is True
    assert result.record.crc_ok is True
    assert len(result.record.child_outcomes) == 3
    assert result.certificate is not None
    assert np.array_equal(
        _user_bits(result.certificate, profile.user_bits), expected_user)
    assert result.record.attempt_id == stream_attempt_identity(
        spec,
        ADDRESS,
        "main",
        AttemptStage.SCAN,
        view.component_block_ids,
        # A CMY7 attempt's demap budget is part of its DECODER, hence part
        # of its identity: the reconstruction reads the same effective
        # count the minting call did.
        demap_iterations=color_attempts.effective_demap_iterations(),
    )
    assert result.record.dependency_certificate_ids == (
        _sha("dependency"),)


@pytest.mark.parametrize(
    "coding_id",
    ("c2-cmy8-p120-v0", "c3-cmy8-p120-v0"),
)
def test_cmy8_attempt_selects_only_requested_stream_and_shares_blocks(
    monkeypatch: pytest.MonkeyPatch,
    coding_id: str,
) -> None:
    spec, users, view = _clean_cmy8(coding_id)
    calls: list[tuple[str, int]] = []
    original = color_tile.cmy8_decode_stream

    def recording_decode(values, bank, dither, *, max_iters, alpha):
        calls.append((bank.profile_id, max_iters))
        return original(values, bank, dither, max_iters=max_iters,
                        alpha=alpha)

    monkeypatch.setattr(color_tile, "cmy8_decode_stream", recording_decode)
    m = color_attempts.attempt_color_tile(
        view,
        spec,
        "M",
        AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0],
        lane_id=LANE,
    )
    c = color_attempts.attempt_color_tile(
        view,
        spec,
        "C",
        AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0],
        lane_id=LANE,
    )

    assert calls == [
        ("cmy8-M-p120-v0", 60),
        ("cmy8-C-p120-v0", 60),
    ]
    assert m.certificate is not None and c.certificate is not None
    assert np.array_equal(
        _user_bits(m.certificate, users["M"].size), users["M"])
    assert np.array_equal(
        _user_bits(c.certificate, users["C"].size), users["C"])
    assert m.record.component_block_ids == c.record.component_block_ids
    assert m.record.attempt_id != c.record.attempt_id
    assert m.record.stream_id == "M" and c.record.stream_id == "C"


@pytest.mark.parametrize(
    ("coding_id", "sufficient_packs", "below_counts"),
    (
        ("c2-cmy7-p120-v0", 552, (2257, 1865, 1884)),
        ("c3-cmy7-p120-v0", 557, (2193, 1895, 1918)),
    ),
)
def test_cmy7_floor_is_per_child_after_inverse_interleaving(
    monkeypatch: pytest.MonkeyPatch,
    coding_id: str,
    sufficient_packs: int,
    below_counts: tuple[int, int, int],
) -> None:
    spec = make_spec(coding_id)
    profile = spec.stream_profiles[0]
    address = (0, 0, 0)
    values = _relative_scores(
        np.zeros(spec.payload_cells, np.uint8), 7)
    insufficient_packs = 546
    observed = np.zeros(spec.payload_cells, bool)
    observed[:insufficient_packs * 4 + 3] = True
    below = _view(
        spec, "cmy7", values, observed, source_label=f"below-{coding_id}",
        address=address)

    def must_not_decode(*args, **kwargs):
        raise AssertionError("CMY7 decoder crossed the cheap floor")

    original_demap = color_tile.cmy7_demap_payload

    def must_not_demap(*args, **kwargs):
        raise AssertionError("CMY7 soft demapper crossed the structural floor")

    monkeypatch.setattr(color_tile, "cmy7_iterated_decode", must_not_decode)
    monkeypatch.setattr(
        color_tile, "cmy7_demap_payload", must_not_demap)
    result = color_attempts.attempt_color_tile(
        below,
        spec,
        "main",
        AttemptStage.SCAN,
        source_sha256=below.source_sha256s[0],
        lane_id=LANE,
    )
    monkeypatch.setattr(
        color_tile, "cmy7_demap_payload", original_demap)
    counter = spec.tile_counter(*address)
    code_llrs = original_demap(
        values,
        observed,
        profile.fec,
        keystream.cmy7_interleave_permutation(
            spec.seed, counter, profile.fec.transmitted_bits),
        keystream.cmy7_dither_bits(
            spec.seed, counter, profile.fec.transmitted_bits),
    )
    offsets = np.cumsum(
        (0, *(child.transmitted_bits for child in profile.fec.children)))
    assert tuple(
        int(np.count_nonzero(code_llrs[start:stop]))
        for start, stop in zip(offsets[:-1], offsets[1:], strict=True)
    ) == below_counts
    assert result.record.state is AttemptState.BELOW_ATTEMPT_FLOOR
    assert result.record.n_informative == insufficient_packs * 4 + 3
    assert result.record.child_outcomes == ()
    assert result.record.syndrome_ok is None
    assert result.certificate is None

    calls = 0

    def failed_decode(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _child_outcome(
            profile, (False, False, False), crc_ok=None)

    monkeypatch.setattr(color_tile, "cmy7_iterated_decode", failed_decode)
    observed[:] = False
    observed[:sufficient_packs * 4] = True
    exact = _view(
        spec, "cmy7", values, observed, source_label=f"exact-{coding_id}",
        address=address)
    attempted = color_attempts.attempt_color_tile(
        exact,
        spec,
        "main",
        AttemptStage.SCAN,
        source_sha256=exact.source_sha256s[0],
        lane_id=LANE,
    )
    assert calls == 1
    assert attempted.record.state is AttemptState.ATTEMPTED_FAILED
    assert attempted.record.n_informative == sufficient_packs * 4


@pytest.mark.parametrize(
    "coding_id",
    ("c2-cmy7-p120-v0", "c3-cmy7-p120-v0"),
)
def test_cmy7_structural_support_cannot_replace_actual_llr_support(
    monkeypatch: pytest.MonkeyPatch,
    coding_id: str,
) -> None:
    spec = make_spec(coding_id)
    view = _view(
        spec,
        "cmy7",
        np.zeros((spec.payload_cells, 6), np.float64),
        source_label=f"neutral-{coding_id}",
    )
    demap_calls = 0
    original_demap = color_tile.cmy7_demap_payload

    def neutral_demap(*args, **kwargs):
        nonlocal demap_calls
        demap_calls += 1
        llrs = original_demap(*args, **kwargs)
        assert not np.any(llrs)
        return llrs

    def must_not_decode(*args, **kwargs):
        raise AssertionError("CMY7 decoder crossed the actual-LLR floor")

    monkeypatch.setattr(color_tile, "cmy7_demap_payload", neutral_demap)
    monkeypatch.setattr(color_tile, "cmy7_iterated_decode", must_not_decode)
    result = color_attempts.attempt_color_tile(
        view,
        spec,
        "main",
        AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0],
        lane_id=LANE,
    )

    assert demap_calls == 1
    assert result.record.state is AttemptState.BELOW_ATTEMPT_FLOOR
    assert result.record.n_informative == spec.payload_cells
    assert result.record.child_outcomes == ()
    assert result.record.syndrome_ok is None
    assert result.certificate is None


def test_cmy8_floor_uses_nonzero_support_in_the_selected_plane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = make_spec("c2-cmy8-p120-v0")
    profile = spec.stream_profiles[0]
    values = np.zeros((spec.payload_cells, 3))
    observed = np.ones(spec.payload_cells, bool)
    below = _view(spec, "cmy8", values, observed, source_label="below8")

    def must_not_decode(*args, **kwargs):
        raise AssertionError("CMY8 decoder crossed the cheap floor")

    monkeypatch.setattr(color_tile, "cmy8_decode_stream", must_not_decode)
    result = color_attempts.attempt_color_tile(
        below,
        spec,
        "C",
        AttemptStage.SCAN,
        source_sha256=below.source_sha256s[0],
        lane_id=LANE,
    )
    assert result.record.state is AttemptState.BELOW_ATTEMPT_FLOOR
    assert result.record.n_informative == spec.payload_cells

    calls = 0

    def failed_decode(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _child_outcome(profile, (False,), crc_ok=None)

    monkeypatch.setattr(color_tile, "cmy8_decode_stream", failed_decode)
    values[:profile.fec.active_information_bits, 0] = 1.0
    exact = _view(spec, "cmy8", values, observed, source_label="exact8")
    attempted = color_attempts.attempt_color_tile(
        exact,
        spec,
        "C",
        AttemptStage.SCAN,
        source_sha256=exact.source_sha256s[0],
        lane_id=LANE,
    )
    assert calls == 1
    assert attempted.record.n_informative == spec.payload_cells


@pytest.mark.parametrize(
    ("syndromes", "crc_ok", "expected_syndrome", "expected_crc"),
    (
        ((True, False, True), None, False, None),
        ((True, True, True), False, True, False),
    ),
)
def test_failed_child_and_crc_authority_are_exposed_exactly(
    monkeypatch: pytest.MonkeyPatch,
    syndromes: tuple[bool, ...],
    crc_ok: bool | None,
    expected_syndrome: bool,
    expected_crc: bool | None,
) -> None:
    spec = make_spec("c2-cmy7-p120-v0")
    profile = spec.stream_profiles[0]
    view = _view(
        spec, "cmy7", _relative_scores(
            np.zeros(spec.payload_cells, np.uint8), 7),
        source_label=f"failure-{syndromes}")
    outcome = _child_outcome(profile, syndromes, crc_ok=crc_ok)
    monkeypatch.setattr(
        color_tile, "cmy7_iterated_decode",
        lambda *args, **kwargs: outcome)

    result = color_attempts.attempt_color_tile(
        view,
        spec,
        "main",
        AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0],
        lane_id=LANE,
    )

    assert result.record.state is AttemptState.ATTEMPTED_FAILED
    assert result.record.child_outcomes == tuple(
        (index + 2, syndrome)
        for index, syndrome in enumerate(syndromes))
    assert result.record.n_iters == sum(
        index + 2 for index in range(len(syndromes)))
    assert result.record.syndrome_ok is expected_syndrome
    assert result.record.crc_ok is expected_crc
    assert result.certificate is None


def test_retry150_changes_only_stage_identity_and_iteration_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = make_spec("c2-cmy8-p120-v0")
    profile = spec.stream_profiles[2]
    values = np.zeros((spec.payload_cells, 3))
    values[:, 2] = 1.0
    view = _view(
        spec, "cmy8", values, source_label="retry")
    limits: list[int] = []

    def failed_decode(*args, max_iters, **kwargs):
        limits.append(max_iters)
        return _child_outcome(profile, (False,), crc_ok=None)

    monkeypatch.setattr(color_tile, "cmy8_decode_stream", failed_decode)
    ordinary = color_attempts.attempt_color_tile(
        view,
        spec,
        "Y",
        AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0],
        lane_id=LANE,
    )
    retry = color_attempts.attempt_color_tile(
        view,
        spec,
        "Y",
        AttemptStage.RETRY150,
        source_sha256=view.source_sha256s[0],
        lane_id=LANE,
    )

    assert limits == [60, 150]
    assert ordinary.record.component_block_ids == (
        retry.record.component_block_ids)
    assert ordinary.record.attempt_id != retry.record.attempt_id
    assert retry.record.attempt_id == stream_attempt_identity(
        spec,
        ADDRESS,
        "Y",
        AttemptStage.RETRY150,
        view.component_block_ids,
    )


def test_union_attempt_retains_both_physical_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = make_spec("c2-cmy8-p120-v0")
    profile = spec.stream_profiles[0]
    first = _view(
        spec, "cmy8", np.zeros((spec.payload_cells, 3)),
        source_label="union-first")
    second = _view(
        spec, "cmy8", np.zeros((spec.payload_cells, 3)),
        source_label="union-second")
    union = tile_attempt_view((*first.components, *second.components))
    monkeypatch.setattr(
        color_tile,
        "cmy8_decode_stream",
        lambda *args, **kwargs: _child_outcome(
            profile, (False,), crc_ok=None),
    )

    result = color_attempts.attempt_color_tile(
        union,
        spec,
        "C",
        AttemptStage.UNION,
        source_sha256=second.source_sha256s[0],
        lane_id=LANE,
    )

    assert result.record.source_sha256 == second.source_sha256s[0]
    assert result.record.component_block_ids == union.component_block_ids
    assert len(result.record.component_block_ids) == 2
    with pytest.raises(ValueError, match="scan attempt"):
        color_attempts.attempt_color_tile(
            union,
            spec,
            "C",
            AttemptStage.SCAN,
            source_sha256=second.source_sha256s[0],
            lane_id=LANE,
        )


def test_wrong_codec_kind_stream_and_provenance_fail_closed() -> None:
    cmy8 = make_spec("c2-cmy8-p120-v0")
    view = _view(
        cmy8, "cmy8", np.zeros((cmy8.payload_cells, 3)))
    arguments = dict(
        source_sha256=view.source_sha256s[0],
        lane_id=LANE,
    )
    with pytest.raises(ValueError, match="not declared"):
        color_attempts.attempt_color_tile(
            view, cmy8, "main", AttemptStage.SCAN, **arguments)
    with pytest.raises(ValueError, match="cannot drive"):
        color_attempts.attempt_color_tile(
            view,
            make_spec("c2-cmy7-p120-v0"),
            "main",
            AttemptStage.SCAN,
            **arguments,
        )
    with pytest.raises(ValueError, match="accepts only"):
        color_attempts.attempt_color_tile(
            view,
            make_spec("c2-r0550"),
            "main",
            AttemptStage.SCAN,
            **arguments,
        )
    with pytest.raises(ValueError, match="not an evidence component"):
        color_attempts.attempt_color_tile(
            view,
            cmy8,
            "C",
            AttemptStage.SCAN,
            source_sha256=_sha("other"),
            lane_id=LANE,
        )
    with pytest.raises(ValueError, match="lane differs"):
        color_attempts.attempt_color_tile(
            view,
            cmy8,
            "C",
            AttemptStage.SCAN,
            source_sha256=view.source_sha256s[0],
            lane_id="other",
        )


def test_adversarial_decoder_outcomes_cannot_mint_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = make_spec("c2-cmy8-p120-v0")
    profile = spec.stream_profiles[0]
    values = np.zeros((spec.payload_cells, 3))
    values[:, 0] = 1.0
    view = _view(
        spec, "cmy8", values, source_label="adversarial")
    # Shape/provenance re-verification of our own decoder was removed as
    # ceremony (validation-boundary ruling 2026-07-30).  The authority
    # boundary is the durable-record wall: a CERTIFIED attempt row refuses
    # to exist without syndrome and CRC truth, so even a hostile decoder
    # outcome cannot mint authority.
    child = profile.fec.children[0]
    contradictory = FrameDecodeOutcome(
        children=(ChildDecodeOutcome(
            0, child.code_id, child.shortened_info_tail, 0, False),),
        crc_invoked=True,
        crc_ok=True,
        certified_user_bits=np.zeros(profile.user_bits, np.uint8),
    )
    monkeypatch.setattr(
        color_tile, "cmy8_decode_stream",
        lambda *args, **kwargs: contradictory)
    with pytest.raises(ValueError, match="inconsistent certified attempt"):
        color_attempts.attempt_color_tile(
            view,
            spec,
            "C",
            AttemptStage.SCAN,
            source_sha256=view.source_sha256s[0],
            lane_id=LANE,
        )


def test_color_attempts_thread_bp_alpha_to_the_bp_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ruling 3.4/§13a call-threading pin: both color decode routes (CMY7
    via cmy7_iterated_decode, CMY8 via cmy8_decode_stream) deliver
    alpha=tiles.BP_ALPHA to the core BP decode."""
    from holo.core.ldpc import frame as ldpc_frame
    from holo.receive import tiles

    seen: list[float] = []
    original = ldpc_frame.decode_soft

    def capturing_decode(llr, rate_id, max_iters=60, alpha=None):
        assert alpha is not None, "alpha must be threaded explicitly"
        seen.append(alpha)
        return original(llr, rate_id, max_iters=max_iters, alpha=alpha)

    monkeypatch.setattr(ldpc_frame, "decode_soft", capturing_decode)

    spec7, _profile, _user, view7 = _clean_cmy7("c3-cmy7-p120-v0")
    r7 = color_attempts.attempt_color_tile(
        view7, spec7, "main", AttemptStage.SCAN,
        source_sha256=view7.source_sha256s[0], lane_id=LANE)
    assert r7.record.state is AttemptState.CERTIFIED

    spec8, _users, view8 = _clean_cmy8("c3-cmy8-p120-v0")
    r8 = color_attempts.attempt_color_tile(
        view8, spec8, "M", AttemptStage.SCAN,
        source_sha256=view8.source_sha256s[0], lane_id=LANE)
    assert r8.record.state is AttemptState.CERTIFIED

    assert seen and set(seen) == {tiles.BP_ALPHA}


def test_shipped_cmy7_codec_leaf_constants() -> None:
    """What the leaf ships, and the measured reason for the value.

    PK8, adjudicated against the pre-registered bars in
    COLOR-UPLIFT-MEASUREMENTS 3: B7 is MET at three demap<->BP iterations
    (p* 0.015 -> 0.0275, no tested p regressing) and NOT met at two
    (0.0225); B8 is MET by the same arm alone.  PK9's margin gate was a
    measured NEGATIVE (36 tiles below baseline at the bar point) and is
    RETIRED, so there is no second constant to pin here (13.10).
    """
    assert color_attempts.DEMAP_ITERATIONS == 3
    assert not hasattr(color_attempts, "MARGIN_ERASURE_FLOOR")
    assert not hasattr(color_attempts, "margin_erased_observed")


@pytest.mark.parametrize("iterations", (2, 3))
def test_demap_iterations_stay_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
    iterations: int,
) -> None:
    """P3 rides inside ONE attempt: one record, one stage, one certificate.

    The BP work of every inner decode is summed into ``n_iters``, and the
    runtime wall that prices attempt work accepts exactly that budget.

    What "one attempt" does NOT mean is "the same attempt as a run with a
    different budget" (review disposition 2026-08-10).  The demap count is
    part of the DECODER — a 1-iteration attempt and a 3-iteration attempt
    run different algorithms over identical evidence — so it is part of
    the attempt identity, and the two can never be mistaken for a re-run
    of each other in a ledger.  The CERTIFICATE id is unchanged, because
    that one is content-addressed and neither decoder is in it.
    """
    spec, profile, user, view = _clean_cmy7("c3-cmy7-p120-v0")
    monkeypatch.setattr(color_attempts, "DEMAP_ITERATIONS", 1)
    once = color_attempts.attempt_color_tile(
        view, spec, "main", AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0], lane_id=LANE)
    monkeypatch.setattr(color_attempts, "DEMAP_ITERATIONS", iterations)
    many = color_attempts.attempt_color_tile(
        view, spec, "main", AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0], lane_id=LANE)

    assert many.record.attempt_id != once.record.attempt_id
    assert many.record.attempt_id == stream_attempt_identity(
        spec, ADDRESS, "main", AttemptStage.SCAN, view.component_block_ids,
        demap_iterations=iterations)
    assert once.record.attempt_id == stream_attempt_identity(
        spec, ADDRESS, "main", AttemptStage.SCAN, view.component_block_ids,
        demap_iterations=1)
    assert many.record.stage is AttemptStage.SCAN
    assert many.record.n_informative == once.record.n_informative
    assert many.record.state is AttemptState.CERTIFIED
    assert many.certificate.certificate_id == once.certificate.certificate_id
    assert many.record.n_iters == sum(
        row[0] for row in many.record.child_outcomes)
    _runtime_validation.validate_attempts((many.record,), spec)


def test_force_null_and_live_cmy7_attempts_are_distinct_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A null attempt and a live attempt are not the same attempt.

    ``--force-null`` reaches the CMY7 leaf by making
    ``effective_demap_iterations()`` return 1, so the two arms decode the
    SAME evidence with DIFFERENT decoders.  Before the review disposition
    of 2026-08-10 they minted the same attempt id, which is how a ledger
    ends up unable to tell a null run from a live one — and the policy id
    is no help there, because it names the constant, not the hatch.
    """
    spec, _profile, _user, view = _clean_cmy7("c3-cmy7-p120-v0")
    args = (spec, ADDRESS, "main", AttemptStage.SCAN,
            view.component_block_ids)

    monkeypatch.delenv(color_stack.FORCE_NULL_ENV, raising=False)
    assert color_attempts.effective_demap_iterations() == 3
    live = stream_attempt_identity(
        *args, demap_iterations=color_attempts.effective_demap_iterations())

    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    assert color_attempts.effective_demap_iterations() == 1
    null = stream_attempt_identity(
        *args, demap_iterations=color_attempts.effective_demap_iterations())

    assert live != null
    # The KWARG DEFAULT is the historical identity, and the segment is a
    # CMY7 leaf: K and CMY8 are untouched whatever is passed.
    assert stream_attempt_identity(*args) == stream_attempt_identity(
        *args, demap_iterations=None)
    k_spec = make_spec("c2-r0700")
    k_args = (k_spec, ADDRESS, "main", AttemptStage.SCAN,
              view.component_block_ids)
    assert stream_attempt_identity(*k_args) == stream_attempt_identity(
        *k_args, demap_iterations=1) == stream_attempt_identity(
        *k_args, demap_iterations=3)
    cmy8_spec = make_spec("c3-cmy8-p120-v0")
    cmy8_args = (cmy8_spec, ADDRESS, "M", AttemptStage.SCAN,
                 view.component_block_ids)
    assert stream_attempt_identity(*cmy8_args) == stream_attempt_identity(
        *cmy8_args, demap_iterations=3)


def test_color_uplift_codec_constants_do_not_reach_cmy8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P3 is a CMY7-only seam — assert the CMY8 no-op."""
    spec, users, view = _clean_cmy8("c3-cmy8-p120-v0")
    monkeypatch.setattr(color_attempts, "DEMAP_ITERATIONS", 1)
    baseline = color_attempts.attempt_color_tile(
        view, spec, "M", AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0], lane_id=LANE)
    monkeypatch.setattr(color_attempts, "DEMAP_ITERATIONS", 3)
    forced = color_attempts.attempt_color_tile(
        view, spec, "M", AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0], lane_id=LANE)
    assert forced.record == baseline.record
    assert forced.certificate.certificate_id \
        == baseline.certificate.certificate_id


def test_policy_id_names_the_cmy7_codec_leaf_constants() -> None:
    """A decode's declared identity must name what the leaf actually runs.

    ``color_policy`` keeps the token a hand-bumped literal on purpose, so
    this is the pin that stops the literal and the live constants from
    drifting apart: at the pinned nulls the token says nothing (the
    pre-campaign identity, because the path is the pre-campaign path), and
    any other value has to be spelled into it.
    """
    from holo.receive.color_policy import COLOR_PAYLOAD_POLICY_ID as token

    if color_attempts.DEMAP_ITERATIONS == 1:
        assert "demapiter" not in token
    else:
        assert f"cmy7-demapiter{color_attempts.DEMAP_ITERATIONS}-" in token
    # PK9 is retired, so nothing in the token may claim a margin gate.
    assert "marginerase" not in token


def _failing_cmy7(coding_id: str, corrupt: float = 0.13):
    """A CMY7 view that clears the support floor and FAILS its first decode.

    The iteration exists for exactly this tile, so it is the one the
    force-null pin has to be built on: on a tile that certifies at once
    the loop stops immediately and proves nothing.
    """
    spec = make_spec(coding_id)
    profile = spec.stream_profiles[0]
    rng = np.random.default_rng(90210)
    user = rng.integers(0, 2, profile.user_bits, dtype=np.uint8)
    counter = spec.tile_counter(*ADDRESS)
    states = color_tile.cmy7_encode_payload(
        user,
        profile.fec,
        keystream.cmy7_interleave_permutation(
            spec.seed, counter, profile.fec.transmitted_bits),
        keystream.cmy7_dither_bits(
            spec.seed, counter, profile.fec.transmitted_bits),
    )
    wrong = (states.astype(np.int64)
             + rng.integers(1, 7, states.size)) % 7
    hit = rng.random(states.size) < corrupt
    shown = np.where(hit, wrong, states).astype(np.uint8)
    return spec, user, _view(
        spec, "cmy7", _relative_scores(shown, 7, strength=6.0),
        source_label=f"failing-{coding_id}")


def test_force_null_reaches_the_codec_leaf() -> None:
    """The campaign's one environment contract still means what it says.

    RECEIVE-DESIGN §6.2a (v0.51) promises `--force-null` is EXACTLY the
    pre-campaign receiver.  A codec-leaf constant would quietly break that,
    so the leaf asks `color_stack` — the single sanctioned reader — instead
    of growing a second hatch.
    """
    import os

    from holo.receive import color_stack

    assert color_attempts.effective_demap_iterations() \
        == color_attempts.DEMAP_ITERATIONS
    previous = os.environ.get(color_stack.FORCE_NULL_ENV)
    os.environ[color_stack.FORCE_NULL_ENV] = "1"
    try:
        assert color_stack.force_null_enabled() is True
        assert color_attempts.effective_demap_iterations() == 1
    finally:
        if previous is None:
            del os.environ[color_stack.FORCE_NULL_ENV]
        else:
            os.environ[color_stack.FORCE_NULL_ENV] = previous
    assert color_attempts.effective_demap_iterations() \
        == color_attempts.DEMAP_ITERATIONS


def test_force_null_never_enters_the_iterated_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The decisive unit pin: count the demaps, not the constant.

    A tile that fails its first decode re-demaps once per extra iteration.
    Under force-null it must demap exactly ONCE — the pre-campaign path —
    and the durable record must carry the single-pass BP budget.
    """
    from holo.receive import color_stack

    spec, _user, view = _failing_cmy7("c3-cmy7-p120-v0")
    calls: list[int] = []
    original = color_tile.cmy7_demap_payload

    def counting_demap(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(color_tile, "cmy7_demap_payload", counting_demap)

    live = color_attempts.attempt_color_tile(
        view, spec, "main", AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0], lane_id=LANE)
    assert live.record.state is AttemptState.ATTEMPTED_FAILED
    iterated = len(calls)
    assert iterated > 1, "the fixture must exercise the loop"

    calls.clear()
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    nulled = color_attempts.attempt_color_tile(
        view, spec, "main", AttemptStage.SCAN,
        source_sha256=view.source_sha256s[0], lane_id=LANE)

    assert len(calls) == 1
    assert nulled.record.state is AttemptState.ATTEMPTED_FAILED
    assert nulled.record.n_iters < live.record.n_iters
    assert nulled.record.n_iters == 2 * tiles.BASELINE_BP_MAX_ITERS * len(
        spec.stream_profiles[0].fec.children)
    _runtime_validation.validate_attempts((nulled.record,), spec)
