"""Receiver back end, stage 1: per-tile cell LLRs -> certified tiles.

CARRIED (holo2 firewall: copy-and-adapt, never import) from
``src/holo/receive/tiles.py``, with the K numerical leaf ``attempt_k_tile``
from ``src/holo/receive/payload.py``.  Every numeric line is the original;
the ONLY adaptation is the record boundary — the same seam H2b adapted in
``close_record_from_result``.  Pinned by ``tests/holo2_oracles/test_oracle_tiles.py``.

RECEIVE-DESIGN §2.6. This module is PURE: no scans, no geometry, no
poses. It takes the LLRs somebody else sampled for one hypothesized
tile and runs the format-mandatory chain to a CRC certificate:

    calibrated cell LLRs (64x64, POSITIVE = ink = bit 1)
      -> PAYLOAD DESCRAMBLE   (DOMAIN_PAYLOAD keystream at ABSOLUTE cell
                               addresses flips LLR signs; site cells are
                               forced to 0.0 = erasure)
      -> attempt floor        (n_informative >= k_eff, pre-decode)
      -> ldpc_tile.decode_tile — which owns the remaining two format
         steps: the per-tile AFFINE SLOT-PERMUTATION inversion (a_t, b_t
         from keystream.slot_perm_params) and the uniform info-tail
         SHORTENING (site count known 0). They are deliberately NOT
         duplicated here.
      -> syndrome + CRC-32 certification
      -> re-encode of the PRINTED cells (the certified-field substrate
         that later boosts Lane-C correlation density and supplies
         detector labels — §1 consequence 1).

BOUNDED-LLR INVARIANT (018.7, DESIGN L2): each calibrated physical-capture
output is bounded by its PAVA label count (plus the registered context
correction) before it reaches this module.  Independent captures are then
summed exactly as in E023b.  This boundary rejects non-finite values but
deliberately does not saturate a multiview sum: a fixed post-sum clamp
changes reliability ratios and was not part of the qualified receiver.

HOLO2 ADAPTATIONS (nothing numerical):

* the format identity arrives as :class:`~holo2.format.format_v1.TileFormat` —
  the exact fields the chain reads off v1's ``FormatSpec``, and nothing
  else (the same restriction ``CloseSpec`` applies to the close).
* ``attempt_k_tile`` returns a transient :class:`TileAttempt` instead of
  v1's ``(TileAttemptRecord, TileCertificateRecord | None)``.  DESIGN §5.5
  makes the attempt record transient (it folds to counters at commit) and
  §5.2 puts the certified content in ``TileRecord`` — certified bits in
  the blob sidecar, the metadata bit as a field, and the minting attempt
  as a :class:`~holo2.core.records.MintRef`.  :func:`certified_tile_record`
  is that mapping; the decode above it is untouched.
* v1's durable-identity helpers (``sha256_parts_le/_be``,
  ``dependency_identity``, ``attempt_identity``) are NOT carried: holo2
  names an attempt by its read-set (``identity.py``, DESIGN §7), so a
  second identity scheme would be a second source of truth.
  ``decoder_profile`` IS carried — it names the executed decoder, which
  the attempt still has to state.
* ``CertifiedSymbolConflict`` lives in ``fountain_close`` (H2b carried it
  there); it is one class for the whole receiver, not one per module.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass
from enum import Enum
from functools import cache

import numpy as np

from ..format import (LADDER, METADATA_BITS_PER_TILE, STREAM_MAIN,
                      TileFormat, keystream, ldpc_tile, pilots)
from .detect import readonly_array
from ..core import BlobRef
from .records import MintRef, TileRecord

TILE_CELLS = 64
N_CELLS = TILE_CELLS * TILE_CELLS
BASELINE_BP_MAX_ITERS = 60
RETRY_BP_MAX_ITERS = 150
BP_ALPHA = 0.8


class AttemptStage(str, Enum):
    """§8.3's attempt stages, spelled exactly as v1 spells them."""

    SCAN = "scan"
    UNION = "union"
    RETRY150 = "retry150"


class AttemptState(str, Enum):
    """The three outcomes of one tile evaluation (v1 spellings)."""

    BELOW_ATTEMPT_FLOOR = "below_attempt_floor"
    ATTEMPTED_FAILED = "attempted_failed"
    CERTIFIED = "certified"


def decoder_profile(rate_id: str, max_iters: int, alpha: float) -> str:
    """Exact stable decoder-profile spelling from E023b."""
    if not isinstance(rate_id, str) or not rate_id:
        raise ValueError("rate_id must be a non-empty string")
    if (isinstance(max_iters, (bool, np.bool_))
            or int(max_iters) != max_iters or max_iters < 0):
        raise ValueError("max_iters must be a non-negative integer")
    if not np.isfinite(alpha) or alpha <= 0.0:
        raise ValueError("alpha must be finite and positive")
    return (f"{rate_id}/decode_tile-max{int(max_iters)}-"
            f"alpha{float(alpha):g}")


# ----------------------------------------------------------- tile geometry

@dataclass(frozen=True)
class _TileGeometry:
    """Per-family site geometry (identical in every tile — colocation)."""

    site_flat: np.ndarray          # (n_sites,) sorted flat cell indices
    site_mask_yx: np.ndarray       # (64, 64) bool
    word_cells_yx: np.ndarray      # (100, 2)
    filler_cells_yx: np.ndarray    # (F, 2)


@cache
def _tile_geometry(family_seed: bytes, n_filler: int) -> _TileGeometry:
    """Cached because every tile of every page shares it and the site
    draws are keystream work (§9.4: no repeated derivation)."""
    word, filler = pilots.site_cells_yx(family_seed, n_filler)
    site_flat = pilots.site_cell_indices(family_seed, n_filler)
    mask = np.zeros(N_CELLS, dtype=bool)
    mask[site_flat] = True
    return _TileGeometry(
        site_flat=readonly_array(site_flat, np.int64),
        site_mask_yx=readonly_array(
            mask.reshape(TILE_CELLS, TILE_CELLS), np.bool_),
        word_cells_yx=readonly_array(word, np.int64),
        filler_cells_yx=readonly_array(filler, np.int64))


def _geometry(spec: TileFormat) -> _TileGeometry:
    return _tile_geometry(spec.family_seed, spec.n_filler)


def k_eff_bits(spec: TileFormat) -> int:
    """Unknown info bits per tile = k_bits - n_sites (the shortened
    info tail is known zero). This is the counting bound the attempt
    floor uses: fewer informative observations than unknowns cannot
    determine the codeword under ANY decoder."""
    return LADDER[spec.rate_id].k_bits - spec.n_sites


@cache
def _tile_scramble_bits_for(seed: bytes, plane: int, family_seed: bytes,
                            n_filler: int, page: int, ty: int,
                            tx: int) -> np.ndarray:
    """Derive and retain one immutable absolute scramble.

    Descramble, successful re-encode, retries, and certificate validation all
    revisit the same tile.  This output-invariant, unbounded cache removes
    repeated 4096-cell keystream work without introducing a policy limit.
    """
    geom = _tile_geometry(family_seed, n_filler)
    yy = np.repeat(np.arange(ty * 64, (ty + 1) * 64, dtype=np.int64), 64)
    xx = np.tile(np.arange(tx * 64, (tx + 1) * 64, dtype=np.int64), 64)
    scr = keystream.bits(seed, keystream.DOMAIN_PAYLOAD, plane,
                         page, yy, xx).reshape(TILE_CELLS, TILE_CELLS)
    return readonly_array(scr & ~geom.site_mask_yx, np.uint8)


def _tile_scramble_bits(spec: TileFormat, page: int, ty: int,
                        tx: int) -> np.ndarray:
    """(64, 64) uint8 payload scramble for one tile, at ABSOLUTE cell
    addresses, site cells zeroed.  Qualification pins the complete receive
    re-encoding against the corresponding slice of Track-1
    ``gen.compose.compose_page_cells``; receive itself remains dependent only
    on core/ + format/."""
    return _tile_scramble_bits_for(
        spec.seed, spec.plane, spec.family_seed, spec.n_filler,
        page, ty, tx)


@cache
def _slot_permutation(seed: bytes, counter: int,
                      n_slots: int) -> tuple[int, int]:
    a, b = keystream.slot_perm_params(seed, counter, n_slots)
    return int(a[0]), int(b[0])


def _as_tile_llrs(llr_cells: np.ndarray) -> np.ndarray:
    """Return one finite ``(64, 64)`` float64 decoder input unchanged.

    Erasure is represented by exactly 0.0.  A NaN or infinity is a
    detector/API fault, not evidence and not an alternate erasure spelling:
    accepting infinity here used to turn an entry excluded by
    the k_eff pre-decode floor into a maximum-strength decoder input.
    """
    x = np.asarray(llr_cells, dtype=np.float64)
    if x.shape != (TILE_CELLS, TILE_CELLS):
        raise ValueError(f"llr_cells must be (64, 64), got {x.shape}")
    if not np.isfinite(x).all():
        raise ValueError("llr_cells must be finite — detector fault "
                         "(use 0.0 for an erasure)")
    return x


# --------------------------------------------------------------- the chain

def _descramble_validated(x: np.ndarray, spec: TileFormat, page: int,
                          ty: int, tx: int) -> np.ndarray:
    """Descramble one already validated finite tile."""
    scr = _tile_scramble_bits(spec, page, ty, tx)
    out = x * (1.0 - 2.0 * scr.astype(np.float64))
    out[_geometry(spec).site_mask_yx] = 0.0
    return out


def _informative_count(x: np.ndarray, spec: TileFormat) -> int:
    live = (x != 0.0) & ~_geometry(spec).site_mask_yx
    return int(np.count_nonzero(live))


def _nonnegative_int(value: object, name: str) -> int:
    """Exact integer validation; never truncate a float into an address."""
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be an integer, not bool")
    try:
        result = operator.index(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if result < 0:
        raise ValueError(f"{name} must be nonnegative")
    return result


def _validate_tile_address(spec: TileFormat, counter: object, page: object,
                           ty: object, tx: object
                           ) -> tuple[int, int, int, int]:
    """Canonicalise and bind one counter/address to a complete legal page."""
    c = _nonnegative_int(counter, "counter")
    p = _nonnegative_int(page, "page")
    y = _nonnegative_int(ty, "ty")
    x = _nonnegative_int(tx, "tx")
    # The 18-bit space can leave a tail smaller than one whole page.  Those
    # counters are representable by BCH but no legal volume may print them.
    if c >= spec.max_pages * spec.tiles_per_page:
        raise ValueError(f"counter {c} is outside the complete-page "
                         f"address space for {spec.spec_id}")
    expected = spec.tile_address(c)
    if expected != (p, y, x):
        raise ValueError(f"counter {c} addresses {expected}, not {(p, y, x)}")
    return c, p, y, x


def _reencode_printed_cells(spec: TileFormat, counter: int, page: int,
                            ty: int, tx: int, user_bits: np.ndarray,
                            a_t: int, b_t: int) -> np.ndarray:
    """Certified user bits -> the tile exactly as printed, (64, 64) uint8.

    Recreates the tile portion of Track-1 ``compose_page_cells``, but takes
    the RECOVERED user bits (metadata bit already in place) instead of
    re-deriving them from (version, k_total), which a single certified tile
    does not know.  Qualification compares the result to the corresponding
    page slice byte-for-byte.
    """
    geom = _geometry(spec)
    cells = ldpc_tile.encode_tile(user_bits, spec.rate_id, geom.site_flat,
                                  a_t, b_t)
    tile = cells.reshape(TILE_CELLS, TILE_CELLS).copy()
    word = pilots.word_values(spec.seed, counter, spec.plane)[0]
    tile[geom.word_cells_yx[:, 0], geom.word_cells_yx[:, 1]] = word
    if geom.filler_cells_yx.size:
        fy, fx = geom.filler_cells_yx[:, 0], geom.filler_cells_yx[:, 1]
        tile[fy, fx] = keystream.bits(
            spec.seed, keystream.DOMAIN_FILLER_VALUES, spec.plane,
            page, ty * 64 + fy, tx * 64 + fx)
    return tile ^ _tile_scramble_bits(spec, page, ty, tx)


# ------------------------------------------------------------ the attempt

@dataclass(frozen=True)
class TileAttempt:
    """One tile evaluation, transient (DESIGN §5.5).

    ``user_bits`` is present only when the attempt CERTIFIED — the chain
    never exposes uncertified payload bits (L5), exactly as v1's
    ``TileFraming`` never returns them without ``ok``.
    """

    state: AttemptState
    stage: AttemptStage
    page: int
    tile_yx: tuple[int, int]
    counter: int
    stream_id: str
    decoder_profile: str
    n_informative: int
    n_iters: int
    syndrome_ok: bool | None
    crc_ok: bool | None
    user_bits: np.ndarray | None = None

    @property
    def certified(self) -> bool:
        return self.state is AttemptState.CERTIFIED

    @property
    def metadata_bit(self) -> int | None:
        """The single LDPC metadata bit of a certified tile (§5.2)."""
        if self.user_bits is None:
            return None
        return int(self.user_bits[0])

    @property
    def symbol_bits(self) -> np.ndarray | None:
        """The fountain symbol a certified tile carries (uint8 bits)."""
        if self.user_bits is None:
            return None
        return self.user_bits[METADATA_BITS_PER_TILE:]


def attempt_k_tile(
    llr_cells: np.ndarray,
    spec: TileFormat,
    address: tuple[int, int, int],
    stage: AttemptStage,
) -> TileAttempt:
    """The K/main numerical leaf: one tile evaluation, LLRs to certificate.

    Numerically identical to v1's ``holo.receive.payload.attempt_k_tile``;
    what differs is only what comes out (a transient attempt instead of two
    durable v1 records) and what does not go in (v1's identity arguments —
    holo2 binds an attempt to its read-set upstream, DESIGN §7).
    """
    page, ty, tx = address
    counter, page, ty, tx = _validate_tile_address(
        spec, spec.tile_counter(page, ty, tx), page, ty, tx)
    max_iters = (
        RETRY_BP_MAX_ITERS
        if stage is AttemptStage.RETRY150
        else BASELINE_BP_MAX_ITERS
    )
    profile = decoder_profile(spec.rate_id, max_iters, BP_ALPHA)
    x = _as_tile_llrs(llr_cells)
    n_informative = _informative_count(x, spec)
    common = dict(
        stage=stage,
        page=page,
        tile_yx=(ty, tx),
        counter=counter,
        stream_id=STREAM_MAIN,
        decoder_profile=profile,
        n_informative=n_informative,
    )
    if n_informative < k_eff_bits(spec):
        return TileAttempt(
            **common, state=AttemptState.BELOW_ATTEMPT_FLOOR,
            n_iters=0, syndrome_ok=None, crc_ok=None)
    llr = _descramble_validated(x, spec, page, ty, tx)
    a_t, b_t = _slot_permutation(
        spec.seed, counter, spec.n_transmitted_slots)
    fr = ldpc_tile.decode_tile(
        llr.ravel(), spec.rate_id, _geometry(spec).site_flat,
        a_t, b_t, max_iters=max_iters, alpha=BP_ALPHA)
    # decode_tile documents ok == syndrome_ok AND crc_ok; VERIFIED here
    # because `ok` is all that stands between a BP fixed point and a
    # certificate.
    if not (fr.ok and fr.syndrome_ok and fr.crc_ok
            and fr.user_bits is not None):
        return TileAttempt(
            **common, state=AttemptState.ATTEMPTED_FAILED,
            n_iters=fr.n_iters, syndrome_ok=fr.syndrome_ok,
            crc_ok=fr.crc_ok)
    user_bits = np.asarray(fr.user_bits, np.uint8)
    if user_bits.shape != (spec.tile_user_bits,):
        raise ValueError(
            f"{spec.spec_id}: decoder returned {user_bits.shape} user bits, "
            f"not ({spec.tile_user_bits},)")
    return TileAttempt(
        **common, state=AttemptState.CERTIFIED,
        n_iters=fr.n_iters, syndrome_ok=True, crc_ok=True,
        user_bits=readonly_array(user_bits, np.uint8))


def printed_cells_for(spec: TileFormat, address: tuple[int, int, int],
                      user_bits: np.ndarray) -> np.ndarray:
    """Re-encode one tile's printed field from its ADDRESS and user bits.

    The durable-side door of :func:`printed_cells` (H5 P2): a committed
    ``TileRecord`` keeps the metadata bit and a blob reference to the
    symbol, never the transient attempt, so the label harvest reassembles
    the user bits and asks here.  Same arithmetic, same single
    ``_reencode_printed_cells`` call — the address is re-validated against
    its own counter, which for an attempt-derived call is the identity it
    already passed.
    """
    page, ty, tx = address
    counter, page, ty, tx = _validate_tile_address(
        spec, spec.tile_counter(page, ty, tx), page, ty, tx)
    bits = np.asarray(user_bits, np.uint8).ravel()
    if bits.shape != (spec.tile_user_bits,):
        raise ValueError(
            f"{spec.spec_id}: printed-field re-encode needs "
            f"({spec.tile_user_bits},) user bits, got {bits.shape}")
    a_t, b_t = _slot_permutation(spec.seed, counter, spec.n_transmitted_slots)
    return _reencode_printed_cells(spec, counter, page, ty, tx, bits, a_t, b_t)


def printed_cells(spec: TileFormat, attempt: TileAttempt) -> np.ndarray:
    """Re-encode the complete printed 64x64 field of a certified tile.

    Word/filler sites and the page scramble included — the certified-field
    substrate the detector labels from and the placement lane correlates
    against.  Refused for an uncertified attempt: there is nothing to
    re-encode, and inventing one would be self-training (L6).
    """
    if attempt.user_bits is None:
        raise ValueError("printed cells exist only for a certified tile")
    return printed_cells_for(
        spec, (attempt.page, *attempt.tile_yx), attempt.user_bits)


def certified_tile_record(attempt: TileAttempt, *, minting: MintRef,
                          bits_ref: BlobRef,
                          observed_by: tuple[str, ...] = (),
                          baselined: tuple[str, ...] = ()) -> TileRecord:
    """The §5.2 ``TileRecord`` one certified attempt produces.

    ``bits_ref`` is the caller's blob reference for ``attempt.symbol_bits``
    (the store owns bulk values, and only the session may append to the
    sidecar), so this function stays pure and the certified content stays
    content-addressed. ``baselined`` carries the current record's failed
    baselines forward — a certificate ends the retries but may not erase
    the history the transition law protects.
    """
    if not attempt.certified:
        raise ValueError(
            f"{attempt.state.value} is not a certificate — CERTIFIED is "
            "terminal and monotone (DESIGN §5.2/L5)")
    return TileRecord(
        minting=minting,
        bits_ref=bits_ref,
        metadata_bit=attempt.metadata_bit,
        observed_by=tuple(sorted(set(observed_by))),
        baselined=tuple(sorted(set(baselined))),
    )


__all__ = [
    "BASELINE_BP_MAX_ITERS", "BP_ALPHA", "N_CELLS", "RETRY_BP_MAX_ITERS",
    "TILE_CELLS", "AttemptStage", "AttemptState", "TileAttempt",
    "attempt_k_tile", "certified_tile_record", "decoder_profile",
    "k_eff_bits", "printed_cells", "printed_cells_for",
]
