"""Production CMY7/CMY8 evidence-to-certificate attempt leaf.

This module is the color counterpart of the numerical part of
``receive.tiles``.  It deliberately owns no scheduling or persistence:
callers supply one exact :class:`~holo.receive.evidence_blocks.TileAttemptView`
and receive the durable attempt fact plus, on CRC success only, one durable
stream certificate.

The physical evidence block is shared by all CMY8 siblings.  Stream
selection happens only after the row/address payload-cell permutation has
been inverted, so attempting C never evaluates M or Y.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core import channel, color_tile, keystream
from ..core.ldpc.frame import FrameDecodeOutcome
from ..format import pilots
from ..format.descriptor import FormatSpec
from ..format.profiles import Family, StreamProfile
from . import tiles
from .color_stack import force_null_enabled
from .evidence import (
    AttemptStage,
    AttemptState,
    TileAttemptRecord,
    TileCertificateRecord,
)
from .evidence_blocks import TileAttemptView
from .records import (
    certificate_record_from_user_bits,
    stream_attempt_identity,
)


# --- The CMY7 iterative demapper (color-uplift P3/PK8) ---------------------
#
# DEMAP_ITERATIONS is how many times ONE attempt may re-demap the pack7
# mapper from the frame decoder's extrinsic before giving up.  At 1 this
# leaf executes literally the pre-campaign path, byte for byte, which is
# what makes the value a real choice rather than an accretion; it touches
# CMY8 nowhere, because the seam is inside the CMY7 branch of
# `attempt_color_tile` and the strict no-op was asserted on paper.
#
# ADOPTED at 3 against the pre-registered B7 bar: met there (p* 0.015 ->
# 0.0275, no tested p regressing) and NOT met at 2 (0.0225); 3 also
# carries B8 on its own.  On paper it took xerox c3-cmy7 from 771
# certificates to 810, a strict superset, for +45% payload CPU.  Sweep
# harness `tests/holo/_color_uplift_harness/sims.py`; record
# COLOR-UPLIFT-MEASUREMENTS §13.
#
# P4's margin-gated pack erasure was built and measured beside it and is
# RETIRED (§13.10); `channel.state_score_margins` outlives it.
DEMAP_ITERATIONS: int = 3


def effective_demap_iterations() -> int:
    """``DEMAP_ITERATIONS``, or 1 under the campaign's force-null contract.

    ``--force-null`` means "the receiver as it was", and it has to reach
    this leaf or the guard stops guarding: a force-null replay would
    iterate and drift off its 720/720 reference.  It reaches it through
    the ONE sanctioned read — `color_stack` owns
    ``HOLO_COLOR_STACK_FORCE_NULL`` and this asks it rather than the
    environment — so the contract stays a contract instead of becoming a
    second hatch.  Like everything else force-null does, it can only
    REMOVE behaviour: one demap, one decode, the pre-campaign path.
    """
    return 1 if force_null_enabled() else DEMAP_ITERATIONS


@dataclass(frozen=True, slots=True)
class ColorAttemptResult:
    """One durable color attempt and its optional newly minted certificate."""

    record: TileAttemptRecord
    certificate: TileCertificateRecord | None

    def __post_init__(self) -> None:
        if not isinstance(self.record, TileAttemptRecord):
            raise TypeError("color attempt result contains a foreign record")
        if (self.certificate is not None
                and not isinstance(self.certificate, TileCertificateRecord)):
            raise TypeError(
                "color attempt result contains a foreign certificate")
        certificate_id = (
            None if self.certificate is None
            else self.certificate.certificate_id
        )
        if self.record.certificate_id != certificate_id:
            raise ValueError(
                "color attempt record and certificate disagree")
        if self.certificate is not None:
            if (self.certificate.work_key != self.record.work_key
                    or self.certificate.origin_attempt_id
                    != self.record.attempt_id):
                raise ValueError(
                    "color attempt certificate has different provenance")


def _validate_boundary(
    view: TileAttemptView,
    spec: FormatSpec,
    stream_id: str,
    stage: AttemptStage,
    source_sha256: str,
    lane_id: str,
) -> tuple[StreamProfile, int]:
    if not isinstance(view, TileAttemptView):
        raise TypeError("color attempt requires a TileAttemptView")
    if not isinstance(spec, FormatSpec):
        raise TypeError("color attempt requires a FormatSpec")
    if not isinstance(stage, AttemptStage):
        raise TypeError("color attempt stage must be AttemptStage")
    if not isinstance(stream_id, str) or not stream_id:
        raise ValueError("color attempt stream id must be non-empty")
    if not isinstance(source_sha256, str):
        raise TypeError("color attempt source SHA-256 must be a string")
    if source_sha256 not in view.source_sha256s:
        raise ValueError(
            "color attempt source is not an evidence component")
    if not isinstance(lane_id, str) or lane_id != view.lane_id:
        raise ValueError("color attempt lane differs from its evidence")

    if spec.codec_family is Family.CMY7:
        expected_kind = "cmy7"
    elif spec.codec_family is Family.CMY8:
        expected_kind = "cmy8"
    else:
        raise ValueError(
            f"{spec.codec_id}: the color attempt leaf accepts only "
            "provisional CMY7/CMY8 rows")
    if view.kind != expected_kind:
        raise ValueError(
            f"{spec.spec_id}: {view.kind} evidence cannot drive "
            f"{expected_kind}")

    profile = spec.stream_profile(stream_id)
    page, ty, tx = view.address
    tiles_y, tiles_x = spec.layout.tiles_yx
    if (page >= spec.max_pages or ty >= tiles_y or tx >= tiles_x):
        raise ValueError("color attempt address lies outside the format")
    return profile, spec.tile_counter(page, ty, tx)


def _sequential_payload(
    view: TileAttemptView,
    spec: FormatSpec,
    counter: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Invert physical p120 placement and the address-keyed cell order."""
    payload_flat = pilots.color_payload_cell_indices(spec.family_seed)
    physical = view.llr_cells_f64.reshape(
        4096, view.arity)[payload_flat]
    physical_observed = view.observed_cells().reshape(4096)[payload_flat]
    order = keystream.color_cell_permutation(
        spec.seed, counter, spec.payload_cells)

    sequential = np.empty_like(physical)
    sequential[order] = physical
    observed = np.empty(spec.payload_cells, dtype=np.bool_)
    observed[order] = physical_observed
    return sequential, observed


def _outcome_facts(
    outcome: FrameDecodeOutcome,
) -> tuple[
    tuple[tuple[int, bool], ...],
    int,
    bool,
    bool | None,
    np.ndarray | None,
]:
    """Extract the durable facts from one frame decode.

    The decoder's outcome coherence is its own module's tested contract;
    re-verifying it here was ceremony (validation-boundary ruling
    2026-07-30).  The authority boundary lives where it belongs: the
    durable ``TileAttemptRecord`` wall refuses a CERTIFIED state without
    syndrome and CRC truth, so an incoherent outcome cannot mint.
    """
    children = tuple(
        (child.n_iters, child.syndrome_ok) for child in outcome.children)
    certified = outcome.certified_user_bits
    if certified is not None:
        certified = np.asarray(certified).astype(np.uint8, copy=False)
    return (
        children,
        sum(row[0] for row in children),
        all(row[1] for row in children),
        outcome.crc_ok,
        certified,
    )


def _children_meet_floor(
    values: np.ndarray,
    profile: StreamProfile,
) -> bool:
    """Require each child to carry its own active-information support."""
    offset = 0
    result = True
    for child in profile.fec.children:
        stop = offset + child.transmitted_bits
        supported = int(np.count_nonzero(values[offset:stop]))
        result = result and supported >= child.active_information_bits
        offset = stop
    if offset != values.size:
        raise AssertionError("CMY7 child support did not cover its bank")
    return result


def attempt_color_tile(
    view: TileAttemptView,
    spec: FormatSpec,
    stream_id: str,
    stage: AttemptStage,
    *,
    source_sha256: str,
    lane_id: str,
) -> ColorAttemptResult:
    """Attempt one CMY7 bank or exactly one unresolved CMY8 stream.

    ``n_informative`` is intentionally the physical observed payload-cell
    count.  The cheap gate uses modulation-aware support.  CMY7 first
    scatters complete-pack support through the real inverse interleave; a
    structurally starved child returns without running the expensive soft
    demapper.  A structurally eligible tile is demapped once, and every child
    must still independently carry at least its active-information count of
    actual nonzero LLRs.  CMY8 applies the latter principle directly to the
    selected plane.
    """
    profile, counter = _validate_boundary(
        view, spec, stream_id, stage, source_sha256, lane_id)
    sequential, observed = _sequential_payload(view, spec, counter)
    n_informative = int(np.count_nonzero(observed))

    cmy7_llrs: np.ndarray | None = None
    if spec.codec_family is Family.CMY7:
        interleave = keystream.cmy7_interleave_permutation(
            spec.seed, counter, profile.fec.transmitted_bits)
        complete = observed.reshape(
            -1, channel.CMY7_CELLS_PER_PACK).all(axis=1)
        mapped_support = np.repeat(
            complete, channel.CMY7_BITS_PER_PACK)
        code_support = np.empty(mapped_support.size, dtype=np.bool_)
        code_support[interleave] = mapped_support
        allowed = _children_meet_floor(code_support, profile)
        if allowed:
            dither = keystream.cmy7_dither_bits(
                spec.seed, counter, profile.fec.transmitted_bits)
            cmy7_llrs = color_tile.cmy7_demap_payload(
                sequential, observed, profile.fec, interleave, dither)
            allowed = _children_meet_floor(cmy7_llrs, profile)
    else:
        plane = spec.stream_ids.index(stream_id)
        supported = int(np.count_nonzero(
            observed & (sequential[:, plane] != 0.0)))
        allowed = supported >= profile.fec.active_information_bits

    address = view.address
    # The demap budget is part of the DECODER, so it is part of the attempt
    # identity (records.stream_attempt_identity); it is a no-op for every
    # codec but CMY7.  This module owns the environment read, records.py
    # stays env-free.
    attempt_id = stream_attempt_identity(
        spec, address, stream_id, stage, view.component_block_ids,
        demap_iterations=effective_demap_iterations())
    common = dict(
        attempt_id=attempt_id,
        source_sha256=source_sha256,
        lane_id=lane_id,
        page=address[0],
        tile_yx=address[1:],
        stage=stage,
        n_informative=n_informative,
        component_block_ids=view.component_block_ids,
        dependency_certificate_ids=view.dependency_certificate_ids,
        stream_id=stream_id,
    )
    if not allowed:
        return ColorAttemptResult(
            TileAttemptRecord(
                **common,
                state=AttemptState.BELOW_ATTEMPT_FLOOR,
                n_iters=0,
                syndrome_ok=None,
                crc_ok=None,
            ),
            None,
        )

    max_iters = (
        tiles.RETRY_BP_MAX_ITERS
        if stage is AttemptStage.RETRY150
        else tiles.BASELINE_BP_MAX_ITERS
    )
    if spec.codec_family is Family.CMY7:
        assert cmy7_llrs is not None
        # P3: the demap<->BP loop is soft iteration INSIDE one attempt
        # (RECEIVE-DESIGN 6.2a).  It is still ONE attempt: one identity,
        # one spend against the retry150 ledger, one certificate at most,
        # and `n_iters` counts every inner decode's BP work.  The demap
        # COUNT is part of that identity (see the minting call above):
        # a force-null attempt (1 iteration) and a live attempt (3) run
        # different decoders over the same evidence, so they are distinct
        # identities and can never be confused for a re-run of each other.
        # What it is NOT is one CRC exposure — the loop can invoke the
        # frame CRC once per iteration, a registered compromise on the
        # undetected-error budget (COLOR-UPLIFT-MEASUREMENTS §13.8),
        # guarded empirically by the wrong-certificate audit rather than
        # by a new bar.
        outcome = color_tile.cmy7_iterated_decode(
            cmy7_llrs, sequential, observed, profile.fec, interleave,
            dither, max_iters=max_iters, alpha=tiles.BP_ALPHA,
            demap_iterations=effective_demap_iterations())
    else:
        outcome = color_tile.cmy8_decode_stream(
            sequential[:, plane],
            profile.fec,
            keystream.cmy8_dither_bits(
                spec.seed, stream_id, counter,
                profile.fec.transmitted_bits),
            max_iters=max_iters,
            alpha=tiles.BP_ALPHA,
        )

    (
        child_outcomes,
        n_iters,
        syndrome_ok,
        crc_ok,
        certified_user_bits,
    ) = _outcome_facts(outcome)
    state = (
        AttemptState.CERTIFIED
        if certified_user_bits is not None
        else AttemptState.ATTEMPTED_FAILED
    )
    certificate = (
        None
        if certified_user_bits is None
        else certificate_record_from_user_bits(
            spec,
            page=address[0],
            tile_yx=address[1:],
            stream_id=stream_id,
            user_bits=certified_user_bits,
            origin_attempt_id=attempt_id,
            dependency_certificate_ids=view.dependency_certificate_ids,
        )
    )
    record = TileAttemptRecord(
        **common,
        state=state,
        n_iters=n_iters,
        syndrome_ok=syndrome_ok,
        crc_ok=crc_ok,
        certificate_id=(
            None if certificate is None else certificate.certificate_id),
        child_outcomes=child_outcomes,
    )
    return ColorAttemptResult(record, certificate)


__all__ = [
    "DEMAP_ITERATIONS",
    "ColorAttemptResult",
    "attempt_color_tile",
    "effective_demap_iterations",
]
