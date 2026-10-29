"""Pure provisional CMY7, CMY8 and CMY payload-tile codecs.

This module joins the already-frozen binary frame and channel-mapper leaves.
It deliberately does not know page geometry, pilot/dust furniture, physical
cell coordinates, fountain symbols, or scanner photometry.

CMY7 convention
---------------

``interleave_order[j]`` names the aggregate FEC bit placed at interleaved
position ``j``.  Dither bit ``j`` is XORed there, consecutive groups of 11
map to four state slots, and the inverse scatters demapped LLR ``j`` back to
code position ``interleave_order[j]``.  A pack with any unobserved state slot
is an eleven-bit erasure.

CMY8 convention
---------------

The final axis is always C, M, Y.  Each component owns an independent FEC
frame and dither; direct presence mapping merely colocates their transmitted
bits in one physical state.  Decode outcomes remain independent.

CMY convention
--------------

Two streams, ``hi`` and ``lo``, each an independent FEC frame and dither
whose bits are one LABEL bit per cell; the frozen label table maps the
pair to a W/C/M/Y presence state.  Each stream decodes through
:func:`cmy8_decode_stream` on its label-bit LLRs.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TypeVar

import numpy as np

from . import channel
from .ldpc.decode import LLR_CLIP
from .ldpc.frame import (
    FecBankProfile,
    FrameDecodeOutcome,
    decode_frame,
    encode_frame,
)

CMY_STREAMS: tuple[str, ...] = channel.PLANE_ORDER
_StreamValue = TypeVar("_StreamValue")


def _permutation(order: np.ndarray, size: int) -> np.ndarray:
    raw = np.asarray(order)
    if raw.ndim != 1 or raw.size != size:
        raise ValueError(
            f"interleave_order must have shape ({size},), got {raw.shape}")
    if raw.dtype.kind not in "iu":
        raise ValueError("interleave_order must contain integers")
    out = raw.astype(np.int64, copy=False)
    if (out.size and (int(out.min()) < 0 or int(out.max()) >= size)) \
            or np.unique(out).size != size:
        raise ValueError("interleave_order must be a permutation")
    return out


def _bits(values: np.ndarray, shape: tuple[int, ...], name: str) -> np.ndarray:
    raw = np.asarray(values)
    if raw.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {raw.shape}")
    if raw.dtype.kind not in "buif" or not np.isfinite(raw).all() \
            or not np.isin(raw, (0, 1)).all():
        raise ValueError(f"{name} must contain only finite 0/1 values")
    return raw.astype(np.uint8, copy=False)


def cmy7_encode_payload(
    user_bits: np.ndarray,
    bank: FecBankProfile,
    interleave_order: np.ndarray,
    dither_bits: np.ndarray,
) -> np.ndarray:
    """Encode one CMY7 user frame to sequential physical state slots."""
    n_code = bank.transmitted_bits
    if n_code % channel.CMY7_BITS_PER_PACK:
        raise ValueError(
            f"{bank.profile_id}: {n_code} transmitted bits do not form "
            f"complete {channel.CMY7_BITS_PER_PACK}-bit packs")
    order = _permutation(interleave_order, n_code)
    dither = _bits(dither_bits, (n_code,), "dither_bits")
    code_bits = encode_frame(user_bits, bank)
    mapped_bits = code_bits[order] ^ dither
    groups = mapped_bits.reshape(-1, channel.CMY7_BITS_PER_PACK)
    return channel.cmy7_map(groups).reshape(-1)


def cmy7_demap_payload(
    relative_state_scores: np.ndarray,
    observed_slots: np.ndarray,
    bank: FecBankProfile,
    interleave_order: np.ndarray,
    dither_bits: np.ndarray,
    prior_code_llrs: np.ndarray | None = None,
) -> np.ndarray:
    """CMY7 state scores -> aggregate binary-code LLRs.

    ``relative_state_scores`` has six W-relative scores per sequential state
    slot.  A four-slot pack is used only when every slot is observed;
    otherwise all eleven output LLRs for that pack are exactly zero.

    ``prior_code_llrs`` is the optional a-priori vector of an iterative
    demapper, in CODE order (the same order as the return value).  It is
    de-interleaved and un-dithered into the mapper's own bit order, folded
    into the pack metric, and removed again from the result, so the return
    value is the extrinsic LLR and remains the decoder's channel input.
    An unobserved pack still returns exactly zero for all eleven bits.
    """
    n_code = bank.transmitted_bits
    if n_code % channel.CMY7_BITS_PER_PACK:
        raise ValueError("CMY7 bank does not form complete packs")
    n_packs = n_code // channel.CMY7_BITS_PER_PACK
    n_cells = n_packs * channel.CMY7_CELLS_PER_PACK
    scores_raw = np.asarray(relative_state_scores)
    if np.iscomplexobj(scores_raw):
        raise ValueError("relative_state_scores must be real")
    scores = scores_raw.astype(np.float64, copy=False)
    if scores.shape != (n_cells, 6) or not np.isfinite(scores).all():
        raise ValueError(
            f"relative_state_scores must be finite with shape "
            f"({n_cells}, 6), got {scores.shape}")
    observed = _bits(observed_slots, (n_cells,), "observed_slots").astype(bool)
    packs = scores.reshape(n_packs, channel.CMY7_CELLS_PER_PACK, 6).copy()
    complete = observed.reshape(
        n_packs, channel.CMY7_CELLS_PER_PACK).all(axis=1)
    packs[~complete] = 0.0

    dither = _bits(dither_bits, (n_code,), "dither_bits")
    order = _permutation(interleave_order, n_code)
    signs = 1.0 - 2.0 * dither
    if prior_code_llrs is None:
        mapped_prior = None
    else:
        raw_prior = np.asarray(prior_code_llrs)
        if np.iscomplexobj(raw_prior):
            raise ValueError("prior_code_llrs must be real")
        prior = raw_prior.astype(np.float64, copy=False).ravel()
        if prior.shape != (n_code,) or not np.isfinite(prior).all():
            raise ValueError(
                f"prior_code_llrs must be finite with shape ({n_code},), "
                f"got {prior.shape}")
        mapped_prior = (prior[order] * signs).reshape(
            n_packs, channel.CMY7_BITS_PER_PACK)

    mapped_llrs = channel.cmy7_soft_demap(
        packs, mapped_prior).reshape(n_code)
    if mapped_prior is not None:
        # The prior alone factorizes exactly over the full 2,048-pattern
        # codebook, so an erased pack's extrinsic is zero up to rounding.
        # The support gate counts nonzero LLRs, so make it exactly zero.
        mapped_llrs.reshape(
            n_packs, channel.CMY7_BITS_PER_PACK)[~complete] = 0.0

    mapped_llrs *= signs
    code_llrs = np.empty(n_code, dtype=np.float64)
    code_llrs[order] = mapped_llrs
    return code_llrs


def cmy7_iterated_decode(
    code_llrs: np.ndarray,
    relative_state_scores: np.ndarray,
    observed_slots: np.ndarray,
    bank: FecBankProfile,
    interleave_order: np.ndarray,
    dither_bits: np.ndarray,
    *,
    max_iters: int = 60,
    alpha: float = 0.8,
    demap_iterations: int = 1,
) -> FrameDecodeOutcome:
    """Decode ``code_llrs``, optionally re-demapping from decoder feedback.

    ``code_llrs`` is the caller's already-computed first demap of the same
    ``relative_state_scores`` / ``observed_slots`` (the receive leaf needs
    it before this call, for its support gate).  At
    ``demap_iterations == 1`` this is EXACTLY :func:`decode_frame` on that
    vector — the same object, byte for byte.

    Above one, the pack7 mapper is re-run with the decoder's extrinsic
    output as its a-priori vector and the frame decoded again, stopping as
    soon as the CRC certifies.  The loop is confined to one attempt: no
    state escapes it, the returned outcome carries no soft output, and the
    per-child ``n_iters`` are the SUM over every inner decode, so the
    durable attempt record still measures the whole attempt's BP work.
    """
    if not isinstance(demap_iterations, int) \
            or isinstance(demap_iterations, bool):
        raise TypeError("demap_iterations must be an integer")
    if demap_iterations < 1:
        raise ValueError("demap_iterations must be >= 1")
    outcome = decode_frame(
        code_llrs, bank, max_iters=max_iters, alpha=alpha,
        want_extrinsic=demap_iterations > 1)
    if demap_iterations == 1:
        return outcome

    totals = [child.n_iters for child in outcome.children]
    for index in range(1, demap_iterations):
        if outcome.ok or outcome.extrinsic_llrs is None:
            break
        prior = np.clip(outcome.extrinsic_llrs, -LLR_CLIP, LLR_CLIP)
        outcome = decode_frame(
            cmy7_demap_payload(
                relative_state_scores, observed_slots, bank,
                interleave_order, dither_bits, prior),
            bank, max_iters=max_iters, alpha=alpha,
            want_extrinsic=index + 1 < demap_iterations)
        for child_index, child in enumerate(outcome.children):
            totals[child_index] += child.n_iters
    children = tuple(
        replace(child, n_iters=total)
        for child, total in zip(outcome.children, totals, strict=True))
    return replace(outcome, children=children, extrinsic_llrs=None)


def cmy7_decode_payload(
    relative_state_scores: np.ndarray,
    observed_slots: np.ndarray,
    bank: FecBankProfile,
    interleave_order: np.ndarray,
    dither_bits: np.ndarray,
    *,
    max_iters: int = 60,
    demap_iterations: int = 1,
) -> FrameDecodeOutcome:
    """Soft-demap and decode one whole CMY7 bank."""
    llrs = cmy7_demap_payload(
        relative_state_scores, observed_slots, bank, interleave_order,
        dither_bits)
    if demap_iterations == 1:
        return decode_frame(llrs, bank, max_iters=max_iters)
    return cmy7_iterated_decode(
        llrs, relative_state_scores, observed_slots, bank, interleave_order,
        dither_bits, max_iters=max_iters,
        demap_iterations=demap_iterations)


def _stream_values(
    values: Mapping[str, _StreamValue],
    name: str,
) -> tuple[_StreamValue, ...]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} must be a stream-ID mapping")
    supplied = tuple(values)
    if set(supplied) != set(CMY_STREAMS) or len(supplied) != len(CMY_STREAMS):
        raise ValueError(
            f"{name} must contain exactly {CMY_STREAMS}, got {supplied}")
    return tuple(values[stream_id] for stream_id in CMY_STREAMS)


def _cmy8_banks(
    banks_by_stream: Mapping[str, FecBankProfile],
) -> tuple[tuple[FecBankProfile, ...], int]:
    raw = _stream_values(banks_by_stream, "banks_by_stream")
    if not all(isinstance(bank, FecBankProfile) for bank in raw):
        raise TypeError("banks_by_stream values must be FecBankProfile")
    banks = tuple(raw)
    sizes = tuple(bank.transmitted_bits for bank in banks)
    if len(set(sizes)) != 1:
        raise ValueError(f"CMY8 stream transmitted sizes differ: {sizes}")
    return banks, sizes[0]


def cmy8_encode_payload(
    user_bits_by_stream: Mapping[str, np.ndarray],
    banks_by_stream: Mapping[str, FecBankProfile],
    dither_bits_by_stream: Mapping[str, np.ndarray],
) -> np.ndarray:
    """Encode independent C/M/Y frames to direct CMY8 state slots."""
    banks, n_cells = _cmy8_banks(banks_by_stream)
    users = _stream_values(user_bits_by_stream, "user_bits_by_stream")
    dithers = _stream_values(
        dither_bits_by_stream, "dither_bits_by_stream")
    presence = np.empty((n_cells, 3), dtype=np.uint8)
    for plane, (stream_id, user, bank, dither) in enumerate(zip(
            CMY_STREAMS, users, banks, dithers, strict=True)):
        dither_vector = _bits(
            np.asarray(dither), (n_cells,),
            f"dither_bits_by_stream[{stream_id!r}]")
        presence[:, plane] = encode_frame(
            np.asarray(user), bank) ^ dither_vector
    return channel.cmy8_map(presence)


def cmy_encode_payload(
    user_bits_by_stream: Mapping[str, np.ndarray],
    banks_by_stream: Mapping[str, FecBankProfile],
    dither_bits_by_stream: Mapping[str, np.ndarray],
) -> np.ndarray:
    """Encode the hi and lo frames of one CMY tile to presence states."""
    streams = channel.CMY_LABEL_STREAMS
    for name, values in (("user_bits_by_stream", user_bits_by_stream),
                         ("banks_by_stream", banks_by_stream),
                         ("dither_bits_by_stream", dither_bits_by_stream)):
        if not isinstance(values, Mapping):
            raise TypeError(f"{name} must be a stream-ID mapping")
        if sorted(values) != sorted(streams):
            raise ValueError(
                f"{name} must contain exactly {streams}, "
                f"got {tuple(values)}")
    hi, lo = (
        encode_frame(np.asarray(user_bits_by_stream[stream_id]),
                     banks_by_stream[stream_id])
        ^ _bits(np.asarray(dither_bits_by_stream[stream_id]),
                (banks_by_stream[stream_id].transmitted_bits,),
                f"dither_bits_by_stream[{stream_id!r}]")
        for stream_id in streams)
    return channel.cmy_label_states(hi, lo)


def cmy8_decode_payload(
    level_llrs_by_stream: Mapping[str, np.ndarray],
    banks_by_stream: Mapping[str, FecBankProfile],
    dither_bits_by_stream: Mapping[str, np.ndarray],
    *,
    max_iters: int = 60,
) -> dict[str, FrameDecodeOutcome]:
    """Convenience decode of all three explicitly named CMY8 streams.

    Receiver scheduling should normally call :func:`cmy8_decode_stream` for
    each unresolved stream so a certified sibling is never retried.
    """
    banks, _n_cells = _cmy8_banks(banks_by_stream)
    llrs = _stream_values(
        level_llrs_by_stream, "level_llrs_by_stream")
    dithers = _stream_values(
        dither_bits_by_stream, "dither_bits_by_stream")
    return {
        stream_id: cmy8_decode_stream(
            np.asarray(stream_llrs),
            bank,
            np.asarray(dither),
            max_iters=max_iters,
        )
        for stream_id, stream_llrs, bank, dither in zip(
            CMY_STREAMS, llrs, banks, dithers, strict=True)
    }


def cmy8_decode_stream(
    level_llrs: np.ndarray,
    bank: FecBankProfile,
    dither_bits: np.ndarray,
    *,
    max_iters: int = 60,
    alpha: float = 0.8,
) -> FrameDecodeOutcome:
    """Decode exactly one unresolved CMY8 component stream.

    ``alpha`` forwards to :func:`decode_frame` (ruling 3.4/§13a: the
    receive path threads its BP_ALPHA explicitly)."""
    n_cells = bank.transmitted_bits
    raw = np.asarray(level_llrs)
    if np.iscomplexobj(raw):
        raise ValueError("level_llrs must be real")
    llrs = raw.astype(np.float64, copy=False)
    if llrs.shape != (n_cells,) or np.isnan(llrs).any():
        raise ValueError(
            f"level_llrs must be non-NaN with shape ({n_cells},), "
            f"got {llrs.shape}")
    dither = _bits(dither_bits, (n_cells,), "dither_bits")
    undithered = llrs * (1.0 - 2.0 * dither)
    return decode_frame(undithered, bank, max_iters=max_iters, alpha=alpha)
