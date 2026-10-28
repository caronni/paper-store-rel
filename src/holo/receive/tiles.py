"""Receiver back end, stage 1: per-tile cell LLRs -> certified tiles.

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

The decode is the soft generalisation of the known-good reference chain
in tests/holo/test_roundtrip.py:reference_decode_page; that test's
hard-decision path is the +-L special case of this one, and the
qualification test in tests/holo/test_receive_backend.py pins the
re-encoded printed cells against gen.compose's page field byte-exactly.

BOUNDED-LLR INVARIANT (018.7): each calibrated physical-capture output is
bounded by its PAVA label count (plus the registered context correction)
before it reaches this module.  Independent captures are then summed exactly
as in E023b.  This boundary rejects non-finite values but deliberately does
not saturate a multiview sum: a fixed post-sum clamp changes reliability
ratios and was not part of the qualified receiver.
"""
from __future__ import annotations

import hashlib
import operator
from dataclasses import dataclass
from functools import cache
from typing import Callable, Iterable, Literal

import numpy as np

from ..core import keystream
from ..core.ldpc import tile as ldpc_tile
from ..core.ldpc.construct import LADDER
from ..format import pilots
from ..format.descriptor import FormatSpec
from .detect import readonly_array

TILE_CELLS = 64
N_CELLS = TILE_CELLS * TILE_CELLS
BASELINE_BP_MAX_ITERS = 60
RETRY_BP_MAX_ITERS = 150
BP_ALPHA = 0.8


class CertificateConflict(ValueError):
    """Two DIFFERENT certified values at one tile address.

    Both sides carry a CRC-32 certificate, so a disagreement is not a
    noise event (2^-32 class) — it is mixed sheets or an upstream fault.
    Fatal by doctrine (HOLO-DESIGN §6.3), never resolved by voting.
    """





def sha256_parts_le(*parts: bytes) -> str:
    """E023b's length-framed identity hash (8-byte little-endian lengths)."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(8, "little"))
        digest.update(part)
    return digest.hexdigest()


def sha256_parts_be(*parts: bytes) -> str:
    """E023c's length-framed identity hash (8-byte big-endian lengths)."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def dependency_identity(certificate_ids: Iterable[str]) -> str:
    """Stable identity of a canonical set of certificate dependencies."""
    ids = tuple(sorted(set(str(value) for value in certificate_ids)))
    return sha256_parts_be(
        b"e023c/dependency-set/v1",
        *(value.encode("ascii") for value in ids))


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


def attempt_identity(address: tuple[int, int, int], stage: str,
                     profile: str,
                     component_block_ids: tuple[str, ...], *,
                     stream_id: str = "main") -> str:
    """Exact E023b block-addressed tile-attempt identity.

    The established ``main`` spelling retains the byte-exact K identity.
    Non-main color streams use a separately domain-separated identity so
    C/M/Y evaluations over the same physical evidence cannot collide.
    """
    if (not isinstance(address, tuple) or len(address) != 3
            or any(type(value) is not int or value < 0 for value in address)):
        raise ValueError("tile attempt address must have three natural axes")
    if stage not in ("scan", "union", "retry150"):
        raise ValueError(f"unknown tile attempt stage {stage!r}")
    if not isinstance(profile, str) or not profile:
        raise ValueError("decoder profile must be non-empty")
    if not isinstance(stream_id, str) or not stream_id:
        raise ValueError("stream_id must be a non-empty string")
    block_ids = tuple(component_block_ids)
    if not block_ids or len(block_ids) != len(set(block_ids)):
        raise ValueError("component block ids must be non-empty and unique")
    if any(not isinstance(identity, str) or len(identity) != 64
           or any(char not in "0123456789abcdef" for char in identity)
           for identity in block_ids):
        raise ValueError("component block ids must be lowercase SHA-256")
    if stage == "scan" and len(block_ids) != 1:
        raise ValueError("a scan attempt must name exactly one block")
    if stage == "union" and len(block_ids) < 2:
        raise ValueError("a union attempt must name at least two blocks")
    parts = (
        repr(address).encode("ascii"),
        stage.encode("ascii"),
        profile.encode("ascii"),
        *(identity.encode("ascii") for identity in block_ids),
    )
    if stream_id == "main":
        return sha256_parts_le(b"e023b/tile-attempt/v2", *parts)
    return sha256_parts_le(
        b"e023b/stream-attempt/v1", stream_id.encode("ascii"), *parts)


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


def _geometry(spec: FormatSpec) -> _TileGeometry:
    return _tile_geometry(spec.family_seed, spec.n_filler)


def k_eff_bits(spec: FormatSpec) -> int:
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


def _tile_scramble_bits(spec: FormatSpec, page: int, ty: int,
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

def _descramble_validated(x: np.ndarray, spec: FormatSpec, page: int,
                          ty: int, tx: int) -> np.ndarray:
    """Descramble one already validated finite tile."""
    scr = _tile_scramble_bits(spec, page, ty, tx)
    out = x * (1.0 - 2.0 * scr.astype(np.float64))
    out[_geometry(spec).site_mask_yx] = 0.0
    return out


def _informative_count(x: np.ndarray, spec: FormatSpec) -> int:
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


def _validate_tile_address(spec: FormatSpec, counter: object, page: object,
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


def _reencode_printed_cells(spec: FormatSpec, counter: int, page: int,
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
