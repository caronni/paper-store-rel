"""Pure payload-tile joins: frame + dither/interleave + channel mapper."""

import numpy as np
import pytest

from holo.core import channel, color_tile
from holo.core.ldpc.frame import FecBankProfile, FecChildProfile


CMY7_BANK = FecBankProfile(
    "cmy7-p120-v0",
    (
        FecChildProfile("r0550", 0),
        FecChildProfile("r0625", 677),
        FecChildProfile("r0625", 677),
    ),
)
CMY8_BANKS = (
    FecBankProfile("cmy8-C-p120-v0", (FecChildProfile("r0550", 120),)),
    FecBankProfile("cmy8-M-p120-v0", (FecChildProfile("r0550", 120),)),
    FecBankProfile("cmy8-Y-p120-v0", (FecChildProfile("r0547", 120),)),
)
CMY8_BANKS_BY_STREAM = dict(zip(
    channel.PLANE_ORDER, CMY8_BANKS, strict=True))


def _named(values):
    return dict(zip(channel.PLANE_ORDER, values, strict=True))


def _named_columns(values: np.ndarray) -> dict[str, np.ndarray]:
    return {
        stream_id: values[:, plane]
        for plane, stream_id in enumerate(channel.PLANE_ORDER)
    }


def _state_scores(states: np.ndarray, q: int, strength: float = 16.0
                  ) -> np.ndarray:
    """Independent test likelihoods, normalized relative to state W."""
    s = np.asarray(states, dtype=np.int64)
    absolute = np.full(s.shape + (q,), -strength)
    np.put_along_axis(absolute, s[..., None], 0.0, axis=-1)
    return absolute[..., 1:] - absolute[..., :1]


def _affine_order(size: int, multiplier: int, offset: int) -> np.ndarray:
    order = (multiplier * np.arange(size, dtype=np.int64) + offset) % size
    assert np.unique(order).size == size
    return order


def test_cmy7_clean_roundtrip_through_interleave_dither_and_states():
    rng = np.random.default_rng(7001)
    n = CMY7_BANK.transmitted_bits
    order = _affine_order(n, 3, 917)
    dither = rng.integers(0, 2, n, dtype=np.uint8)
    user = rng.integers(0, 2, CMY7_BANK.user_bits, dtype=np.uint8)

    states = color_tile.cmy7_encode_payload(user, CMY7_BANK, order, dither)
    assert states.shape == (3976,)
    assert states.max() <= int(channel.CMYState.MY)
    result = color_tile.cmy7_decode_payload(
        _state_scores(states, 7), np.ones(states.size, dtype=np.uint8),
        CMY7_BANK, order, dither)
    assert result.ok
    assert np.array_equal(result.certified_user_bits, user)


def test_cmy7_incomplete_pack_is_exact_erasure():
    n = CMY7_BANK.transmitted_bits
    order = np.arange(n)
    dither = np.zeros(n, dtype=np.uint8)
    states = np.zeros(3976, dtype=np.uint8)
    scores = _state_scores(states, 7)
    observed = np.ones(3976, dtype=np.uint8)
    observed[2] = 0
    llrs = color_tile.cmy7_demap_payload(
        scores, observed, CMY7_BANK, order, dither)
    assert np.array_equal(llrs[:11], np.zeros(11))
    assert np.all(llrs[11:] < 0.0)


def test_cmy8_streams_roundtrip_independently():
    rng = np.random.default_rng(8001)
    n = CMY8_BANKS[0].transmitted_bits
    dither = rng.integers(0, 2, (n, 3), dtype=np.uint8)
    users = tuple(
        rng.integers(0, 2, bank.user_bits, dtype=np.uint8)
        for bank in CMY8_BANKS
    )
    states = color_tile.cmy8_encode_payload(
        _named(users), CMY8_BANKS_BY_STREAM, _named_columns(dither))
    assert states.shape == (3976,)
    llrs = channel.cmy8_raw_marginal_llrs(_state_scores(states, 8))
    results = color_tile.cmy8_decode_payload(
        _named_columns(llrs), CMY8_BANKS_BY_STREAM,
        _named_columns(dither))
    assert tuple(results) == color_tile.CMY_STREAMS
    assert all(result.ok for result in results.values())
    assert all(np.array_equal(result.certified_user_bits, user)
               for result, user in zip(results.values(), users))


def test_cmy8_stream_mappings_are_named_not_positional():
    rng = np.random.default_rng(8004)
    n = CMY8_BANKS[0].transmitted_bits
    dither = rng.integers(0, 2, (n, 3), dtype=np.uint8)
    users = tuple(
        rng.integers(0, 2, bank.user_bits, dtype=np.uint8)
        for bank in CMY8_BANKS
    )
    canonical_users = _named(users)
    canonical_dither = _named_columns(dither)
    expected = color_tile.cmy8_encode_payload(
        canonical_users, CMY8_BANKS_BY_STREAM, canonical_dither)

    # Mapping insertion order is irrelevant; semantic names own the planes.
    reverse = tuple(reversed(channel.PLANE_ORDER))
    got = color_tile.cmy8_encode_payload(
        {name: canonical_users[name] for name in reverse},
        {name: CMY8_BANKS_BY_STREAM[name] for name in reverse},
        {name: canonical_dither[name] for name in reverse},
    )
    assert np.array_equal(got, expected)

    with pytest.raises(TypeError, match="stream-ID mapping"):
        color_tile.cmy8_encode_payload(  # type: ignore[arg-type]
            users, CMY8_BANKS_BY_STREAM, canonical_dither)
    missing = dict(canonical_users)
    missing.pop("Y")
    with pytest.raises(ValueError, match="exactly"):
        color_tile.cmy8_encode_payload(
            missing, CMY8_BANKS_BY_STREAM, canonical_dither)


def test_cmy8_one_bad_stream_does_not_suppress_siblings():
    rng = np.random.default_rng(8002)
    n = CMY8_BANKS[0].transmitted_bits
    dither = rng.integers(0, 2, (n, 3), dtype=np.uint8)
    users = tuple(
        rng.integers(0, 2, bank.user_bits, dtype=np.uint8)
        for bank in CMY8_BANKS
    )
    states = color_tile.cmy8_encode_payload(
        _named(users), CMY8_BANKS_BY_STREAM, _named_columns(dither))
    llrs = channel.cmy8_raw_marginal_llrs(_state_scores(states, 8))
    # One hard C error with zero iterations makes C's syndrome fail.  M/Y
    # remain separate clean frames and certify immediately.
    llrs[0, 0] *= -1.0
    results = color_tile.cmy8_decode_payload(
        _named_columns(llrs), CMY8_BANKS_BY_STREAM,
        _named_columns(dither), max_iters=0)
    assert not results["C"].ok
    assert results["M"].ok and results["Y"].ok
    assert np.array_equal(results["M"].certified_user_bits, users[1])
    assert np.array_equal(results["Y"].certified_user_bits, users[2])


@pytest.mark.parametrize("bad_mask", range(8))
def test_cmy8_all_stream_success_subsets_are_independent(bad_mask: int):
    rng = np.random.default_rng(8100 + bad_mask)
    n = CMY8_BANKS[0].transmitted_bits
    dither = rng.integers(0, 2, (n, 3), dtype=np.uint8)
    users = tuple(
        rng.integers(0, 2, bank.user_bits, dtype=np.uint8)
        for bank in CMY8_BANKS
    )
    states = color_tile.cmy8_encode_payload(
        _named(users), CMY8_BANKS_BY_STREAM, _named_columns(dither))
    llrs = channel.cmy8_raw_marginal_llrs(_state_scores(states, 8))
    for plane in range(3):
        if bad_mask & (1 << plane):
            llrs[0, plane] *= -1.0

    results = color_tile.cmy8_decode_payload(
        _named_columns(llrs), CMY8_BANKS_BY_STREAM,
        _named_columns(dither), max_iters=0)
    for plane, stream_id in enumerate(color_tile.CMY_STREAMS):
        expected_ok = not bool(bad_mask & (1 << plane))
        assert results[stream_id].ok is expected_ok
        if expected_ok:
            assert np.array_equal(
                results[stream_id].certified_user_bits, users[plane])
        else:
            assert results[stream_id].certified_user_bits is None


def test_cmy8_single_stream_primitive_has_no_sibling_work(monkeypatch):
    rng = np.random.default_rng(8003)
    n = CMY8_BANKS[0].transmitted_bits
    dither = rng.integers(0, 2, (n, 3), dtype=np.uint8)
    users = tuple(
        rng.integers(0, 2, bank.user_bits, dtype=np.uint8)
        for bank in CMY8_BANKS
    )
    states = color_tile.cmy8_encode_payload(
        _named(users), CMY8_BANKS_BY_STREAM, _named_columns(dither))
    llrs = channel.cmy8_raw_marginal_llrs(_state_scores(states, 8))

    calls = []
    original = color_tile.decode_frame

    def recording_decode(values, bank, *, max_iters, alpha):
        calls.append(bank.profile_id)
        return original(values, bank, max_iters=max_iters, alpha=alpha)

    monkeypatch.setattr(color_tile, "decode_frame", recording_decode)
    result = color_tile.cmy8_decode_stream(
        llrs[:, 1], CMY8_BANKS[1], dither[:, 1])
    assert result.ok
    assert np.array_equal(result.certified_user_bits, users[1])
    assert calls == ["cmy8-M-p120-v0"]


def _noisy_cmy7(seed: int, p: float, erasure: float = 0.0):
    """One encoded CMY7 bank observed through an honest per-plane BSC."""
    rng = np.random.default_rng(seed)
    n = CMY7_BANK.transmitted_bits
    order = _affine_order(n, 5, 311)
    dither = rng.integers(0, 2, n, dtype=np.uint8)
    user = rng.integers(0, 2, CMY7_BANK.user_bits, dtype=np.uint8)
    states = color_tile.cmy7_encode_payload(user, CMY7_BANK, order, dither)
    bits = np.asarray(
        [[(s >> k) & 1 for k in range(3)] for s in range(7)], np.int8)
    lam = float(np.log((1.0 - p) / p))
    truth = bits[states]
    seen = truth ^ (rng.random(truth.shape) < p).astype(np.int8)
    scores = np.where(seen == 1, lam, -lam) @ bits[1:].T.astype(np.float64)
    observed = (rng.random(states.size) >= erasure).astype(np.uint8)
    return user, order, dither, scores, observed


def test_cmy7_iterated_decode_at_one_is_the_frame_decode():
    """P3's R2 pin: DEMAP_ITERATIONS == 1 is literally today's call."""
    user, order, dither, scores, observed = _noisy_cmy7(4242, 0.02)
    llrs = color_tile.cmy7_demap_payload(
        scores, observed, CMY7_BANK, order, dither)
    reference = color_tile.decode_frame(
        llrs, CMY7_BANK, max_iters=60, alpha=0.8)
    once = color_tile.cmy7_iterated_decode(
        llrs, scores, observed, CMY7_BANK, order, dither,
        max_iters=60, alpha=0.8, demap_iterations=1)
    assert once.children == reference.children
    assert once.crc_ok == reference.crc_ok
    assert once.crc_invoked == reference.crc_invoked
    assert once.extrinsic_llrs is None
    if reference.certified_user_bits is None:
        assert once.certified_user_bits is None
    else:
        assert np.array_equal(
            once.certified_user_bits, reference.certified_user_bits)


def test_cmy7_iterated_decode_sums_bp_work_and_hides_soft_output():
    """n_iters stays the BP sum over every inner decode of one attempt."""
    user, order, dither, scores, observed = _noisy_cmy7(99, 0.024)
    llrs = color_tile.cmy7_demap_payload(
        scores, observed, CMY7_BANK, order, dither)
    once = color_tile.cmy7_iterated_decode(
        llrs, scores, observed, CMY7_BANK, order, dither,
        max_iters=60, alpha=0.8, demap_iterations=1)
    assert not once.ok                       # the case the loop exists for
    twice = color_tile.cmy7_iterated_decode(
        llrs, scores, observed, CMY7_BANK, order, dither,
        max_iters=60, alpha=0.8, demap_iterations=2)
    assert twice.extrinsic_llrs is None
    single = sum(child.n_iters for child in once.children)
    doubled = sum(child.n_iters for child in twice.children)
    assert doubled > single
    assert doubled <= 2 * 2 * 60 * len(CMY7_BANK.children)
    if twice.ok:
        assert np.array_equal(twice.certified_user_bits, user)


def test_cmy7_iterated_decode_stops_at_the_crc():
    """A clean bank certifies on the first inner decode and stops there."""
    user, order, dither, scores, observed = _noisy_cmy7(7, 0.001)
    llrs = color_tile.cmy7_demap_payload(
        scores, observed, CMY7_BANK, order, dither)
    reference = color_tile.decode_frame(llrs, CMY7_BANK, max_iters=60)
    assert reference.ok
    thrice = color_tile.cmy7_iterated_decode(
        llrs, scores, observed, CMY7_BANK, order, dither,
        max_iters=60, alpha=0.8, demap_iterations=3)
    assert thrice.ok
    assert np.array_equal(thrice.certified_user_bits, user)
    assert [child.n_iters for child in thrice.children] == [
        child.n_iters for child in reference.children]


def test_cmy7_prior_keeps_unobserved_packs_exactly_erased():
    """The support gate counts nonzero LLRs; a prior must not resurrect."""
    user, order, dither, scores, observed = _noisy_cmy7(
        1234, 0.02, erasure=0.05)
    rng = np.random.default_rng(5)
    prior = rng.normal(0.0, 5.0, CMY7_BANK.transmitted_bits)
    null = color_tile.cmy7_demap_payload(
        scores, observed, CMY7_BANK, order, dither)
    primed = color_tile.cmy7_demap_payload(
        scores, observed, CMY7_BANK, order, dither, prior)
    assert np.count_nonzero(null == 0.0) > 0
    assert np.array_equal(null == 0.0, primed == 0.0)


def test_cmy7_iterated_decode_refuses_a_degenerate_budget():
    user, order, dither, scores, observed = _noisy_cmy7(3, 0.01)
    llrs = color_tile.cmy7_demap_payload(
        scores, observed, CMY7_BANK, order, dither)
    with pytest.raises(ValueError, match="demap_iterations must be >= 1"):
        color_tile.cmy7_iterated_decode(
            llrs, scores, observed, CMY7_BANK, order, dither,
            demap_iterations=0)
