#!/usr/bin/env python
"""CROP-HARNESS GROUND TRUTH — reconstruction + the validation gate.

NOT A TEST and not a driver: import-only, the truth half of the crop
harness (HANDOFF-CROP Deliverable B step 3; split out of
``crop_harness.py`` at the 1,000-line seam signal, the same law that
carved ``parity_k_report.py``). Its refusal path and reconstruction
coverage are pinned in ``tests/holo2_oracles/test_oracle_crop_harness.py``.

THE RECONSTRUCTION (memory: truth-path discipline). Per-tile expected
user bits for the WHOLE identity are re-encoded from the golden payload
through ``src/holo``'s own generation path — exactly
``gen/compose.compose_page_cells``'s arithmetic, stopped at the user-bit
boundary: ``user[0] = metadata.tile_bits(encode_metadata(0, k_total))``,
``user[1:] = VolumeCode(k_total, symbol_bits, seed).encode_symbols(
pack_source(envelope.wrap(payload), …))``, with ``k_total`` from
``source_symbol_count``. The reconstruction is q-independent: q only
sizes the page count in ``plan_volume``, and the page count is an input
here (1 for both sheets). The two recorded traps are avoided by
construction: no ``make_data`` is consulted (the payload comes from the
sha-verified recovered bin), and no slot-raster order is touched (the
comparison lives at USER BITS, upstream of ``encode_tile``'s slot
permutation).

PRIOR ART, extended not duplicated: ``scratch/holo2-catchup/detect/
a2_probe.py`` reconstructs per-tile truth from v1's certified bits (its
measured LSB-first ``packed_user_bits`` note is carried in
:func:`v1_certified_bits`); this module extends the truth to the full
1,961-tile domain so the ``neither`` targets have truth too.

THE GATE. :func:`validate_gt_against_archives` checks every v1-certified
tile's certificate bits on BOTH archived sheets against the
reconstruction, exactly — a SUPERSET of the handoff's both-certified bar
(both ⊆ cert_v1), chosen because it needs no holo2 state open and is
strictly harder: a v1-only certificate that disagreed with GT would
itself be a wrong certificate worth refusing over. Measured green
2026-08-28: 1,940/1,940 (e029) and 1,930/1,930 (xerox), zero
mismatches. On ANY mismatch :class:`GTValidationError` refuses the whole
report (the harness maps it to exit 3).
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_ROOT / "src", _ROOT / "holo2" / "src"):
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)

import numpy as np                                              # noqa: E402

from holo.core import fountain                                  # noqa: E402
from holo.format import envelope, metadata                      # noqa: E402
from holo.format.envelope import source_symbol_count            # noqa: E402
from holo.format.resolve import resolve_format_ref              # noqa: E402
from holo.gen.emit import METADATA_VERSION                      # noqa: E402
from holo.receive.session import load_session                   # noqa: E402

TileKey = tuple[int, int, int]     # (page, ty, tx) — tile_differential's

#: The golden payload of both K sheets — the same constant
#: ``parity_k.GOLDEN_K_SHA`` names; spelled here so this module needs no
#: harness import (the dependency arrow runs harness -> gt only).
GOLDEN_K_SHA = ("e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9"
                "dd165787af")
GOLDEN_K_BYTES = 465_580

#: Recovered-payload files to reconstruct GT from, tried in order; each
#: candidate is sha- and length-verified before use (both are recorded
#: recoveries of the SAME volume, byte-identical — verified 2026-08-28).
GOLDEN_PAYLOAD_CANDIDATES: tuple[Path, ...] = (
    _ROOT / "scratch/holo2-catchup/real/complete.bin",
    _ROOT / "scratch/holo2-catchup/real/e029-complete.bin",
)

#: The archived v1 full-sheet states (HANDOFF-CROP "The record") — the
#: GT-validation corpus. READ-ONLY, plain file reads via load_session;
#: never decoded against, never written.
ARCHIVED_V1_STATES: dict[str, Path] = {
    "e029": Path("scratch/e028/"
                 "holo-c2-r0700-q07-ink-counting/receive.state"),
    "xerox": Path("scratch/in/"
                  "holo-xerox-c2-counting-receive.state"),
}


class GTValidationError(Exception):
    """Ground truth failed validation — nothing may be reported."""


@dataclass(frozen=True)
class GroundTruth:
    format_ref: str
    payload_sha256: str
    tiles_yx: tuple[int, int]
    tile_user_bits: int
    #: (page, ty, tx) -> uint8 user bits ([0] = the metadata bit,
    #: [1:] = the fountain symbol) — the WHOLE tile domain.
    user_bits: dict[TileKey, np.ndarray]


def load_golden_payload(
        candidates: Iterable[Path] = GOLDEN_PAYLOAD_CANDIDATES) -> bytes:
    """The sha-verified golden payload, or a loud refusal."""
    tried: list[str] = []
    for path in candidates:
        if not path.is_file():
            tried.append(f"{path}: absent")
            continue
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if sha != GOLDEN_K_SHA or len(data) != GOLDEN_K_BYTES:
            tried.append(f"{path}: sha {sha[:12]}…/{len(data)} B, want "
                         f"{GOLDEN_K_SHA[:12]}…/{GOLDEN_K_BYTES} B")
            continue
        return data
    raise GTValidationError(
        "no golden payload file verified: " + "; ".join(tried))


def reconstruct_gt(format_ref: str, payload: bytes,
                   pages: int = 1) -> GroundTruth:
    """Re-encode the payload through src/holo's generation arithmetic.

    Exactly ``gen/compose.compose_page_cells``'s user-bit assembly (see
    the module docstring for the trap analysis); q-independent because
    ``k_total = source_symbol_count(len(payload), symbol_bits)`` and the
    page count is an input, not a plan.
    """
    spec = resolve_format_ref(format_ref)
    # spec._tiles_yx over the public field for the same reason
    # tile_differential.run documents: the public tiles_yx is None on a
    # layout-derived fossil identity, which is what this harness decodes.
    tiles_y, tiles_x = spec._tiles_yx
    tpp = spec.tiles_per_page
    k_total = source_symbol_count(len(payload), spec.aggregate_symbol_bits)
    src = fountain.pack_source(envelope.wrap(payload), k_total,
                               spec.symbol_bits)
    volume_code = fountain.VolumeCode(k_total, spec.symbol_bits, spec.seed,
                                      tiles_per_page=tpp)
    meta_word = metadata.encode_metadata(METADATA_VERSION, k_total)
    user_bits: dict[TileKey, np.ndarray] = {}
    for page in range(pages):
        esis = np.arange(page * tpp, (page + 1) * tpp, dtype=np.int64)
        symbols = volume_code.encode_symbols(src, esis)
        counters = np.array([spec.tile_counter(page, ty, tx)
                             for ty in range(tiles_y)
                             for tx in range(tiles_x)], dtype=np.int64)
        meta_bits = metadata.tile_bits(meta_word, counters)
        for idx in range(tpp):
            ty, tx = idx // tiles_x, idx % tiles_x
            user = np.empty(spec.tile_user_bits, dtype=np.uint8)
            user[0] = meta_bits[idx]
            user[1:] = symbols[idx]
            user.setflags(write=False)
            user_bits[(page, ty, tx)] = user
    return GroundTruth(
        format_ref=format_ref,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        tiles_yx=(tiles_y, tiles_x),
        tile_user_bits=int(spec.tile_user_bits),
        user_bits=user_bits)


def v1_certified_bits(state: Any, tile_user_bits: int,
                      stream: str = "main") -> dict[TileKey, np.ndarray]:
    """Per-tile certified user bits out of a v1 SessionState.

    v1 packs its certified user bits LSB-FIRST — the a2_probe measured
    note (2026-08-23: "MSB-first agrees with holo2's own certified bits
    at 0.4989, little at 1.0"), carried verbatim, never re-derived.
    """
    out: dict[TileKey, np.ndarray] = {}
    for cert in state.certificates:
        if cert.stream_id != stream:
            continue
        bits = np.unpackbits(
            np.frombuffer(cert.packed_user_bits, np.uint8),
            bitorder="little")[:tile_user_bits]
        out[(cert.page, *cert.tile_yx)] = bits
    return out


def validate_gt_bits(gt_bits: Mapping[TileKey, np.ndarray],
                     observed: Mapping[TileKey, np.ndarray],
                     label: str) -> int:
    """PURE core of the GT gate: every observed tile must match exactly.

    Returns the number of validated tiles; raises :class:`GTValidationError`
    naming every mismatching tile (and any tile outside the GT domain —
    a domain miss is a reconstruction bug, not a data fact).
    """
    mismatches: list[str] = []
    for key in sorted(observed):
        expected = gt_bits.get(key)
        if expected is None:
            mismatches.append(f"{key}: outside the GT domain")
            continue
        got = observed[key]
        if got.shape != expected.shape:
            mismatches.append(f"{key}: {got.shape} bits vs GT "
                              f"{expected.shape}")
        elif not np.array_equal(got, expected):
            n_bad = int(np.count_nonzero(got != expected))
            mismatches.append(f"{key}: {n_bad} bit(s) differ")
    if mismatches:
        raise GTValidationError(
            f"GT validation FAILED on {label}: "
            f"{len(mismatches)} tile(s) disagree with the re-encoded "
            f"golden payload — refusing to report anything. "
            + "; ".join(mismatches[:20])
            + ("; …" if len(mismatches) > 20 else ""))
    return len(observed)


def validate_gt_against_archives(gt: GroundTruth) -> dict[str, int]:
    """The GT gate: BOTH archived sheets' v1 certificates, exactly.

    A superset of HANDOFF-CROP's both-certified bar (both ⊆ cert_v1),
    chosen because it needs no holo2 state open and is strictly harder:
    a v1-only certificate that disagreed with GT would itself be a wrong
    certificate worth refusing over.
    """
    validated: dict[str, int] = {}
    for sheet, path in sorted(ARCHIVED_V1_STATES.items()):
        if not path.is_file():
            raise GTValidationError(
                f"archived v1 state for {sheet} is absent at {path} — "
                "cannot validate GT; refusing to report anything")
        state = load_session(path)
        validated[sheet] = validate_gt_bits(
            gt.user_bits, v1_certified_bits(state, gt.tile_user_bits),
            label=f"{sheet} ({path})")
    return validated
