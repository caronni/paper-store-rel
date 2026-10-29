"""Printed-format qualification kept inside ``src/holo``.

These bump-don't-edit page digests predate Track 2 and pin the complete
Track-1 format chain.  They independently pin the vectorized page composer
under the committed counter-addressed metadata amendment.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from ..core import fountain
from ..format.fossils import resolve_fossil_spec
from ..gen import compose, emit, plan


@dataclass(frozen=True, slots=True)
class GeneratorCase:
    name: str
    digest: str


# Each coding's page is its 6 mm A4 fossil (R21: ``L:`` is the one legacy
# door; the same object the retired printer derivation built).
_FOSSIL_IDS = {
    "c3-r0550": "c3-r0550@2240x1536",
    "c2-r0700": "c2-r0700@3328x2304",
    "c2-r0550": "c2-r0550@3328x2304",
}
_GOLDENS = {
    "c3-r0550": "9513732c2f72ede3d7e60b40b0fb1a57a931de5e1ff40fabb76cda86d7c630e1",
    "c2-r0700": "9231bbe836d07062fd1d3a2a645f22aac1929e3c6cf04ebd21e57a0f0c5f5397",
    "c2-r0550": "714f9dd6a8a6c50bf8b40e1304f8b0673f6c95bb22bd6a9d6ec95b4e67092235",
}


def _page_digest(coding_id: str, payload: bytes, q: float) -> str:
    spec = resolve_fossil_spec(_FOSSIL_IDS[coding_id])
    volume = plan.plan_volume(spec, len(payload), q)
    source = emit.source_packed_for(payload, volume)
    code = fountain.VolumeCode(
        volume.k_total, volume.symbol_bits, spec.seed, spec.tiles_per_page)
    esis = np.arange(spec.tiles_per_page, dtype=np.int64)
    symbols = code.encode_symbols(source, esis)
    cells = compose.compose_page_cells(spec, 0, symbols, volume.k_total)
    return hashlib.sha256(np.packbits(cells).tobytes()).hexdigest()


def qualify() -> tuple[GeneratorCase, ...]:
    fixtures = (
        ("c3-r0550", hashlib.sha256(b"holo-roundtrip").digest() * 160, 0.35),
        ("c2-r0700", hashlib.sha256(b"holo-c2").digest() * 320, 0.75),
        ("c2-r0550", hashlib.sha256(b"holo-c2-r0550").digest() * 32, 0.70),
    )
    output = []
    for coding_id, payload, q in fixtures:
        digest = _page_digest(coding_id, payload, q)
        if digest != _GOLDENS[coding_id]:
            raise AssertionError(
                f"{coding_id} printed-format fork: {digest}")
        output.append(GeneratorCase(coding_id, digest))
    return tuple(output)


if __name__ == "__main__":
    for case in qualify():
        print(f"PASS {case.name}: {case.digest}")
