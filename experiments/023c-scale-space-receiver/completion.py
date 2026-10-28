"""Read-only fountain completion policy for the E023c receiver.

E023c remains an LDPC-and-below receiver.  This module is the deliberately
small outer seam that answers whether its current set of CRC-certified tile
payloads is sufficient to reconstruct and verify an E018b volume.  It never
feeds fountain state, rank, or recovered bytes back into acquisition.

Only the actual ``paperholo.fountain.volume_decode`` result followed by the
manifest length and SHA-256 checks can authorize an early stop.  A symbol
count (even one at or above K) is not a completion condition.
"""
from __future__ import annotations

import hashlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
E023B = ROOT / "experiments/023b-integrated-receiver"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(E023B) not in sys.path:
    sys.path.insert(0, str(E023B))

import score_e023b as _score  # noqa: E402
from paperholo import fountain, ldpc  # noqa: E402


COMPLETION_MAGIC = "e023c-volume-completion-v1"
COMPLETION_VERSION = 1
ManifestSpec = _score.ManifestSpec


def load_manifest(path: Path | str) -> ManifestSpec:
    """Load a fully validated E018b manifest using the registered scorer."""
    return _score.load_manifest(path)


def _manifest(value: ManifestSpec | Path | str) -> ManifestSpec:
    if isinstance(value, ManifestSpec):
        return value
    return load_manifest(value)


def _tile_key(raw_key: Any) -> tuple[int, int, int]:
    if not isinstance(raw_key, tuple) or len(raw_key) != 3:
        raise ValueError(
            f"certificate key {raw_key!r} must be (page, tile_y, tile_x)")
    values = []
    for index, value in enumerate(raw_key):
        if isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, np.integer)):
            raise ValueError(
                f"certificate key {raw_key!r} component {index} "
                "must be an integer")
        values.append(int(value))
    return tuple(values)  # type: ignore[return-value]


def _user_bits(raw_bits: Any, key: tuple[int, int, int]) -> np.ndarray:
    try:
        bits = np.asarray(raw_bits)
    except Exception as exc:
        raise ValueError(
            f"certified tile {key} user bits are not an array") from exc
    if bits.ndim != 1:
        raise ValueError(
            f"certified tile {key} user bits must be one-dimensional")
    if bits.size == 0:
        raise ValueError(f"certified tile {key} has no user bits")
    try:
        binary = bool(np.all((bits == 0) | (bits == 1)))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"certified tile {key} user bits are not binary") from exc
    if not binary:
        raise ValueError(f"certified tile {key} user bits are not binary")
    return bits.astype(np.uint8, copy=True)


def certified_symbols(
    certificates: Mapping[tuple[int, int, int], Any],
    manifest: ManifestSpec | Path | str,
) -> tuple[dict[tuple[int, int], np.ndarray], dict[str, Any]]:
    """Validate certified tile payloads and extract interior symbols.

    All supplied certificates—including fountain-inert edge tiles—must have
    the exact user-bit length implied by the manifest.  Interior tiles carry
    the first ``symbol_bits`` user bits into the fountain decoder.  Arrays
    are copied, so neither validation nor decoding can mutate receiver data.
    """
    spec = _manifest(manifest)
    if not isinstance(certificates, Mapping):
        raise TypeError("certificates must be a tile-keyed mapping")

    volume = spec.volume
    compose_spec = spec.descriptor.spec()
    legal_tiles = set(ldpc.tile_grid(compose_spec.page_cells_yx))
    normalised: list[tuple[tuple[int, int, int], np.ndarray]] = []
    seen: set[tuple[int, int, int]] = set()
    for raw_key, raw_bits in certificates.items():
        key = _tile_key(raw_key)
        if key in seen:
            raise ValueError(f"duplicate canonical certificate key {key}")
        seen.add(key)
        page, ty, tx = key
        if not 0 <= page < volume.n_pages:
            raise ValueError(f"certified tile {key} lies outside the volume")
        if (ty, tx) not in legal_tiles:
            raise ValueError(f"certified tile {key} lies outside the page")
        bits = _user_bits(raw_bits, key)
        mask = ldpc.tile_shorten_mask(
            (ty, tx), compose_spec, spec.descriptor.seed)
        expected = ldpc.tile_user_capacity(mask, volume.ldpc_spec)
        if bits.size != expected:
            raise ValueError(
                f"certified tile {key} has {bits.size} user bits; "
                f"expected {expected}")
        normalised.append((key, bits))

    symbols: dict[tuple[int, int], np.ndarray] = {}
    inert = 0
    symbol_pages: set[int] = set()
    for key, bits in sorted(normalised):
        page, ty, tx = key
        esi = fountain.esi_of_tile(volume, page, (ty, tx))
        if esi is None:
            inert += 1
            continue
        if esi in symbols:
            raise ValueError(f"duplicate certified fountain symbol {esi}")
        if bits.size < volume.symbol_bits:
            # Normally unreachable after exact capacity validation, but this
            # explicit seam makes a future geometry/rate regression fatal.
            raise ValueError(
                f"certified tile {key} carries {bits.size} bits, below "
                f"fountain symbol size {volume.symbol_bits}")
        symbols[esi] = bits[:volume.symbol_bits].copy()
        symbol_pages.add(page)

    summary = {
        "certified_ldpc": len(normalised),
        "certified_fountain": len(symbols),
        "certified_fountain_inert": inert,
        "pages_with_symbols": sorted(symbol_pages),
    }
    return symbols, summary


def _block_report(diag: Mapping[str, Any]) -> list[dict[str, Any]]:
    blocks = []
    for raw in diag["blocks"]:
        blocks.append({
            "block": int(raw["block"]),
            "received": int(raw["received"]),
            "needed": int(raw["needed"]),
            "rank": int(raw["rank"]),
            "solved": bool(raw["solved"]),
            "systematic": bool(raw["systematic"]),
        })
    return sorted(blocks, key=lambda row: row["block"])


def evaluate(
    certificates: Mapping[tuple[int, int, int], Any],
    manifest: ManifestSpec | Path | str,
) -> tuple[dict[str, Any], bytes | None]:
    """Decode and verify the current certificate set without modifying it."""
    spec = _manifest(manifest)
    symbols, certificate_summary = certified_symbols(certificates, spec)
    recovered, raw_diag = fountain.volume_decode(symbols, spec.volume)
    blocks = _block_report(raw_diag)
    rank = sum(row["rank"] for row in blocks)
    needed = sum(row["needed"] for row in blocks)
    shortfall = sum(max(0, row["needed"] - row["rank"])
                    for row in blocks)
    if needed != spec.volume.k_total:
        raise ValueError(
            f"fountain diagnostic needs {needed} source symbols; "
            f"manifest declares {spec.volume.k_total}")

    actual_len = None if recovered is None else len(recovered)
    actual_sha = (
        None if recovered is None else hashlib.sha256(recovered).hexdigest())
    length_matches = (
        None if recovered is None
        else actual_len == spec.volume.data_len_bytes)
    sha_matches = (
        None if recovered is None
        else actual_sha == spec.expected_data_sha256)
    verified = bool(
        recovered is not None and length_matches and sha_matches)
    status = (
        "open" if recovered is None
        else "verified" if verified
        else "integrity_failure")

    report: dict[str, Any] = {
        "magic": COMPLETION_MAGIC,
        "version": COMPLETION_VERSION,
        "status": status,
        "manifest": {
            "file_sha256": spec.file_sha256,
            "profile": spec.profile,
            "format_id": spec.descriptor.format_id,
            "n_pages": spec.volume.n_pages,
            "expected_data_len_bytes": spec.volume.data_len_bytes,
            "expected_data_sha256": spec.expected_data_sha256,
        },
        "certificates": certificate_summary,
        "fountain": {
            "version": fountain.FOUNTAIN_VERSION,
            "symbols_received": len(symbols),
            "symbols_total": spec.volume.n_symbols_total,
            "source_symbols_needed": spec.volume.k_total,
            "rank": rank,
            "rank_shortfall": shortfall,
            "solved_all": bool(raw_diag["solved_all"]),
            "blocks": blocks,
        },
        "payload": {
            "recovered": recovered is not None,
            "verified": verified,
            "actual_len_bytes": actual_len,
            "actual_sha256": actual_sha,
            "length_matches": length_matches,
            "sha256_matches": sha_matches,
        },
    }
    return report, recovered


def completion_report(
    certificates: Mapping[tuple[int, int, int], Any],
    manifest: ManifestSpec | Path | str,
) -> dict[str, Any]:
    """Return only the deterministic JSON-compatible completion report."""
    report, _recovered = evaluate(certificates, manifest)
    return report


def should_stop(report: Mapping[str, Any], *, complete: bool = False) -> bool:
    """Stop only after verified recovery, unless exhaustive mode is set."""
    if not isinstance(complete, bool):
        raise TypeError("complete must be boolean")
    if not isinstance(report, Mapping):
        raise TypeError("completion report must be a mapping")
    payload = report.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("completion report has no payload object")
    verified = payload.get("verified")
    if not isinstance(verified, bool):
        raise ValueError("completion report payload.verified must be boolean")
    return bool(verified and not complete)
