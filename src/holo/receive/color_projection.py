"""Certified color records -> exact known physical C/M/Y components.

This is the color counterpart of K's certified printed-field reconstruction,
but its mask is component-valued.  A CMY7 certificate owns the whole physical
payload state.  Each CMY8 certificate owns only its named payload component;
certifying C is never authority for M or Y.  Addressed word and dust
furniture are format facts, so all three of their components are known even
when no payload stream is certified.

The leaf is deliberately pure.  It validates durable certificate records,
re-encodes the protected frame, and projects it onto one canonical 64x64
tile.  It owns no scheduling, photometry, or refinement policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from ..core import channel, color_tile, keystream
from ..core.ldpc.frame import encode_frame
from ..format import pilots
from ..format.descriptor import FormatSpec
from ..format.profiles import Family
from .evidence import TileCertificateRecord, certificate_work_index
from .fountain_close import CertifiedStreamSymbol
from .records import certificate_for_close, validate_certificate_record


def _readonly(value: np.ndarray, dtype: np.dtype | type) -> np.ndarray:
    array = np.ascontiguousarray(value, dtype=dtype)
    return np.frombuffer(array.tobytes(), dtype=np.dtype(dtype)).reshape(
        array.shape
    )


@dataclass(frozen=True, slots=True)
class CertifiedColorProjection:
    """Known C/M/Y presence bits for one canonical physical tile."""

    address: tuple[int, int, int]
    component_bits: np.ndarray
    known_mask: np.ndarray
    dependency_certificate_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (not isinstance(self.address, tuple) or len(self.address) != 3
                or any(type(value) is not int or value < 0
                       for value in self.address)):
            raise ValueError(
                "certified color projection needs a non-negative address")
        bits = np.asarray(self.component_bits)
        mask = np.asarray(self.known_mask)
        if (bits.shape != (64, 64, 3)
                or bits.dtype.kind not in "buif"
                or not np.isfinite(bits).all()
                or not np.isin(bits, (0, 1)).all()):
            raise ValueError(
                "component_bits must be a finite 64x64x3 bit array")
        if mask.shape != (64, 64, 3) or mask.dtype.kind != "b":
            raise ValueError("known_mask must be a 64x64x3 boolean array")
        dependencies = tuple(self.dependency_certificate_ids)
        if tuple(sorted(set(dependencies))) != dependencies:
            raise ValueError(
                "projection dependencies must be sorted unique")
        if any(
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for value in dependencies):
            raise ValueError(
                "projection dependencies must be lowercase SHA-256")
        object.__setattr__(
            self, "component_bits", _readonly(bits, np.uint8))
        object.__setattr__(self, "known_mask", _readonly(mask, np.bool_))
        object.__setattr__(
            self, "dependency_certificate_ids", dependencies)


def _validated_address(
    spec: FormatSpec,
    address: tuple[int, int, int],
) -> int:
    if not isinstance(spec, FormatSpec):
        raise TypeError("certified color projection requires FormatSpec")
    if spec.codec_family not in (Family.CMY7, Family.CMY8):
        raise ValueError(
            f"{spec.codec_id}: certified color projection accepts only "
            "CMY7/CMY8 rows")
    if (not isinstance(address, tuple) or len(address) != 3
            or any(type(value) is not int or value < 0 for value in address)):
        raise ValueError(
            "certified color projection address must contain three "
            "non-negative integers")
    counter = spec.tile_counter(*address)
    if spec.tile_address(counter) != address:
        raise ValueError("certified color projection address is non-canonical")
    return counter


def _certificate_user_bits(
    record: TileCertificateRecord,
    spec: FormatSpec,
) -> np.ndarray:
    certified = certificate_for_close(record, spec)
    if not isinstance(certified, CertifiedStreamSymbol):
        raise TypeError("color certificate reconstructed as a K certificate")
    return np.concatenate((
        np.asarray([certified.metadata_bit], dtype=np.uint8),
        certified.symbol,
    ))


def _install_furniture(
    bits: np.ndarray,
    known: np.ndarray,
    spec: FormatSpec,
    counter: int,
) -> None:
    word, dust = pilots.color_site_cells_yx(spec.family_seed)
    word_states = pilots.color_word_states(spec.seed, [counter])[0]
    dust_states = pilots.dust_state_values(
        spec.seed, [counter], spec.codec)[0]
    bits[word[:, 0], word[:, 1]] = channel.states_to_planes(word_states)
    bits[dust[:, 0], dust[:, 1]] = channel.states_to_planes(dust_states)
    known[word[:, 0], word[:, 1]] = True
    known[dust[:, 0], dust[:, 1]] = True


def project_certified_color_tile(
    records: Iterable[TileCertificateRecord],
    spec: FormatSpec,
    address: tuple[int, int, int],
) -> CertifiedColorProjection:
    """Reconstruct exactly the components authorized at ``address``.

    ``records`` may be empty, in which case the result contains only the
    known word/dust furniture.  Exact duplicate records are harmless.
    Different valid certificates for one address/stream are an integrity
    conflict.  Records for another row, address, or stream are refused.
    """
    counter = _validated_address(spec, address)
    rows = tuple(records)
    for record in rows:
        if not isinstance(record, TileCertificateRecord):
            raise TypeError(
                "certified color projection contains a foreign record")
        validate_certificate_record(record, spec)
        if (record.page, *record.tile_yx) != address:
            raise ValueError(
                "certificate addresses another physical tile")
    certificate_work_index(rows)

    by_stream: dict[str, TileCertificateRecord] = {}
    for record in rows:
        by_stream.setdefault(record.stream_id, record)

    bits = np.zeros((64, 64, 3), dtype=np.uint8)
    known = np.zeros((64, 64, 3), dtype=np.bool_)
    _install_furniture(bits, known, spec, counter)

    payload_flat = pilots.color_payload_cell_indices(spec.family_seed)
    order = keystream.color_cell_permutation(
        spec.seed, counter, spec.payload_cells)

    if spec.codec_family is Family.CMY7:
        record = by_stream.get("main")
        if record is not None:
            profile = spec.stream_profiles[0]
            sequential_states = color_tile.cmy7_encode_payload(
                _certificate_user_bits(record, spec),
                profile.fec,
                keystream.cmy7_interleave_permutation(
                    spec.seed, counter, profile.fec.transmitted_bits),
                keystream.cmy7_dither_bits(
                    spec.seed, counter, profile.fec.transmitted_bits),
            )
            physical_states = sequential_states[order]
            flat_bits = bits.reshape(4096, 3)
            flat_known = known.reshape(4096, 3)
            flat_bits[payload_flat] = channel.states_to_planes(
                physical_states)
            flat_known[payload_flat] = True
    else:
        flat_bits = bits.reshape(4096, 3)
        flat_known = known.reshape(4096, 3)
        for plane, profile in enumerate(spec.stream_profiles):
            record = by_stream.get(profile.stream_id)
            if record is None:
                continue
            sequential = encode_frame(
                _certificate_user_bits(record, spec), profile.fec)
            sequential ^= keystream.cmy8_dither_bits(
                spec.seed,
                profile.stream_id,
                counter,
                profile.fec.transmitted_bits,
            )
            flat_bits[payload_flat, plane] = sequential[order]
            flat_known[payload_flat, plane] = True

    dependencies = tuple(sorted({
        record.certificate_id for record in by_stream.values()
    }))
    return CertifiedColorProjection(
        address, bits, known, dependencies)


# Mint-once projection cache (rework Phase 6.1; the color analog of
# records.printed_cells_from_record).  A projection is a pure function of
# the format identity, the address, and the exact certificate set (each
# certificate_id binds spec_id, seed, address, stream, and the certified
# user bits), so each distinct certificate set re-encodes at most once per
# process.  ~16 KB per projection — negligible at corpus scale.
# Validation runs at the mint inside project_certified_color_tile; the
# projection dataclass is immutable and served shared thereafter.
_PROJECTION_CACHE: dict[
    tuple[str, tuple[int, int, int], tuple[str, ...]],
    CertifiedColorProjection,
] = {}


def cached_certified_color_projection(
    records: Iterable[TileCertificateRecord],
    spec: FormatSpec,
    address: tuple[int, int, int],
) -> CertifiedColorProjection:
    """Mint-once :func:`project_certified_color_tile` per certificate set."""
    rows = tuple(records)
    key = (
        spec.spec_id,
        address,
        tuple(sorted({row.certificate_id for row in rows})),
    )
    cached = _PROJECTION_CACHE.get(key)
    if cached is not None:
        return cached
    projection = project_certified_color_tile(rows, spec, address)
    _PROJECTION_CACHE[key] = projection
    return projection


__all__ = [
    "CertifiedColorProjection",
    "cached_certified_color_projection",
    "project_certified_color_tile",
]
