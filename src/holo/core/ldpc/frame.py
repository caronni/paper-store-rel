"""CRC framing over one or more shortened binary LDPC mother codes.

This is the modulation-independent part of tile FEC.  The established K
path in :mod:`holo.core.ldpc.tile` remains unchanged; color codecs use this
layer because their binary code bits do not have a one-bit-per-cell physical
layout.

Each child is shortened only at the tail of its systematic information
positions.  Its transmitted positions are therefore exactly
``[0, k-s) + [k, n)``.  A bank owns one outer CRC across the concatenated
active-information prefixes, irrespective of how many children it contains.

LLRs use the house convention: positive means bit 1, zero is an erasure, and
the shortened zero tails are restored as ``-inf`` before BP decoding.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .construct import LADDER
from .decode import decode_soft, encode
from .tile import CRC_BITS, crc32_bits


@dataclass(frozen=True)
class FecChildProfile:
    """One ordered mother-code child and its fixed information-tail cut."""

    code_id: str
    shortened_info_tail: int = 0

    def __post_init__(self) -> None:
        if self.code_id not in LADDER:
            raise ValueError(f"unknown LDPC code {self.code_id!r}")
        s = self.shortened_info_tail
        if not isinstance(s, int) or isinstance(s, bool):
            raise TypeError("shortened_info_tail must be an integer")
        k = LADDER[self.code_id].k_bits
        if not 0 <= s < k:
            raise ValueError(
                f"{self.code_id}: shortened_info_tail={s} must be in "
                f"[0, {k})")

    @property
    def active_information_bits(self) -> int:
        return LADDER[self.code_id].k_bits - self.shortened_info_tail

    @property
    def transmitted_bits(self) -> int:
        return LADDER[self.code_id].n_bits - self.shortened_info_tail


@dataclass(frozen=True)
class FecBankProfile:
    """An ordered set of children sharing one outer CRC frame."""

    profile_id: str
    children: tuple[FecChildProfile, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id:
            raise ValueError("profile_id must be a non-empty string")
        children = tuple(self.children)
        if not children:
            raise ValueError("an FEC bank needs at least one child")
        if not all(isinstance(child, FecChildProfile) for child in children):
            raise TypeError("children must contain only FecChildProfile")
        object.__setattr__(self, "children", children)
        if self.active_information_bits <= CRC_BITS:
            raise ValueError(
                f"{self.profile_id}: active information cannot hold a CRC")

    @property
    def active_information_bits(self) -> int:
        return sum(child.active_information_bits for child in self.children)

    @property
    def transmitted_bits(self) -> int:
        return sum(child.transmitted_bits for child in self.children)

    @property
    def user_bits(self) -> int:
        """Bits protected by the bank CRC (metadata and payload together)."""
        return self.active_information_bits - CRC_BITS


def transmitted_positions(child: FecChildProfile) -> np.ndarray:
    """Ascending transmitted code positions for one shortened child."""
    spec = LADDER[child.code_id]
    active = child.active_information_bits
    return np.concatenate((
        np.arange(active, dtype=np.int64),
        np.arange(spec.k_bits, spec.n_bits, dtype=np.int64),
    ))


def _binary_vector(bits: np.ndarray, size: int, name: str) -> np.ndarray:
    raw = np.asarray(bits).ravel()
    if raw.size != size:
        raise ValueError(f"{name} must contain exactly {size} bits, "
                         f"got {raw.size}")
    if raw.dtype.kind not in "buif" or not np.isfinite(raw).all():
        raise ValueError(f"{name} must contain only finite 0 or 1 values")
    if not np.isin(raw, (0, 1)).all():
        raise ValueError(f"{name} must contain only 0 or 1")
    return raw.astype(np.uint8, copy=False)


def encode_frame(
    user_bits: np.ndarray,
    bank: FecBankProfile,
) -> np.ndarray:
    """Encode one CRC-protected user frame into aggregate transmitted bits."""
    user = _binary_vector(user_bits, bank.user_bits, "user_bits")
    frame = np.concatenate((user, crc32_bits(user)))
    transmitted: list[np.ndarray] = []
    offset = 0
    for child in bank.children:
        spec = LADDER[child.code_id]
        active = child.active_information_bits
        info = np.zeros(spec.k_bits, dtype=np.uint8)
        info[:active] = frame[offset:offset + active]
        offset += active
        codeword = encode(info, child.code_id)
        transmitted.append(codeword[transmitted_positions(child)])
    assert offset == frame.size
    return np.concatenate(transmitted)


@dataclass(frozen=True)
class ChildDecodeOutcome:
    """Syndrome result for one child, in bank order."""

    child_index: int
    code_id: str
    shortened_info_tail: int
    n_iters: int
    syndrome_ok: bool


@dataclass(frozen=True)
class FrameDecodeOutcome:
    """One bank PASS.

    ``crc_ok`` is ``None`` when a child syndrome failed, which also proves
    that THIS pass did not invoke the CRC.  Uncertified user bits are never
    exposed.  Scope, since the outer iterated CMY7 decode exists: one
    outcome describes one pass, and an iterated attempt reports its FINAL
    pass's outcome — so ``None`` there does NOT say the CRC went uninvoked
    during the attempt.  Earlier passes may each have reached it, bounded
    by ``color_attempts.DEMAP_ITERATIONS`` (the registered exposure
    compromise, COLOR-UPLIFT-MEASUREMENTS §13.8).

    ``extrinsic_llrs`` is present only when the caller asked for it and is
    never durable: it is the decoder's own soft output over the bank's
    transmitted positions, in code order and the house LLR convention, for
    a demapper that iterates INSIDE one attempt.  It is not evidence, it is
    not a certificate, and it must not cross an attempt boundary
    (RECEIVE-DESIGN 6.2a, the two iteration laws).
    """

    children: tuple[ChildDecodeOutcome, ...]
    crc_invoked: bool
    crc_ok: bool | None
    certified_user_bits: np.ndarray | None
    extrinsic_llrs: np.ndarray | None = None

    @property
    def ok(self) -> bool:
        return bool(self.crc_ok)


def decode_frame(
    code_llrs: np.ndarray,
    bank: FecBankProfile,
    *,
    max_iters: int = 60,
    alpha: float = 0.8,
    want_extrinsic: bool = False,
) -> FrameDecodeOutcome:
    """Decode all children and certify the shared frame at most once.

    ``alpha`` is the normalized-min-sum scaling forwarded to every child
    :func:`decode`; receive-side callers pass it explicitly so durable
    attempt identities describe the executed decoder (ruling 3.4/§13a).

    ``want_extrinsic`` additionally returns the children's soft output,
    gathered at their transmitted positions and concatenated in the same
    code order as ``code_llrs``.  The decode itself is bit-identical either
    way; the flag only controls whether the array is kept.
    """
    raw_llrs = np.asarray(code_llrs)
    if raw_llrs.dtype.kind not in "buif":
        raise ValueError("code_llrs must be a real numeric array")
    llrs = raw_llrs.astype(np.float64, copy=False).ravel()
    if llrs.size != bank.transmitted_bits:
        raise ValueError(
            f"code_llrs must contain exactly {bank.transmitted_bits} values, "
            f"got {llrs.size}")
    if np.isnan(llrs).any():
        raise ValueError("code_llrs must not contain NaN")
    if not isinstance(max_iters, int) or isinstance(max_iters, bool):
        raise TypeError("max_iters must be an integer")
    if max_iters < 0:
        raise ValueError("max_iters must be >= 0")

    outcomes: list[ChildDecodeOutcome] = []
    active_frames: list[np.ndarray] = []
    extrinsics: list[np.ndarray] = []
    offset = 0
    for child_index, child in enumerate(bank.children):
        spec = LADDER[child.code_id]
        n_tx = child.transmitted_bits
        positions = transmitted_positions(child)
        mother_llr = np.zeros(spec.n_bits, dtype=np.float64)
        mother_llr[positions] = llrs[offset:offset + n_tx]
        offset += n_tx
        if child.shortened_info_tail:
            mother_llr[
                child.active_information_bits:spec.k_bits
            ] = -np.inf
        syndrome_ok, hard, n_iters, extrinsic = decode_soft(
            mother_llr, child.code_id, max_iters=max_iters, alpha=alpha)
        if want_extrinsic:
            extrinsics.append(extrinsic[positions])
        outcomes.append(ChildDecodeOutcome(
            child_index=child_index,
            code_id=child.code_id,
            shortened_info_tail=child.shortened_info_tail,
            n_iters=int(n_iters),
            syndrome_ok=bool(syndrome_ok),
        ))
        active_frames.append(
            hard[:child.active_information_bits].astype(np.uint8))
    assert offset == llrs.size

    children = tuple(outcomes)
    soft = np.concatenate(extrinsics) if want_extrinsic else None
    if not all(child.syndrome_ok for child in children):
        return FrameDecodeOutcome(
            children=children,
            crc_invoked=False,
            crc_ok=None,
            certified_user_bits=None,
            extrinsic_llrs=soft,
        )

    frame = np.concatenate(active_frames)
    user = frame[:-CRC_BITS]
    crc_ok = bool(np.array_equal(frame[-CRC_BITS:], crc32_bits(user)))
    return FrameDecodeOutcome(
        children=children,
        crc_invoked=True,
        crc_ok=crc_ok,
        certified_user_bits=user if crc_ok else None,
        extrinsic_llrs=soft,
    )
