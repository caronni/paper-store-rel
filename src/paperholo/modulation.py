"""Layer 1 — cell modulation and scrambling (DESIGN.md §4).

Variant M-A: solid on/off cells of `cell` x `cell` printer dots, XOR-scrambled with a
seeded, address-keyed keystream. The scrambler provides DC balance, whiteness (R3) and
self-clocking content; it does NOT provide absolute addressing (§5.2, v0.3).

TODO(M1): distribution shaping to ~37.5% ink (§4.4); per-cell soft demodulation with
2-D equalization instead of block-mean + threshold.
TODO(prod): swap blake2b/Philox keying for AES-CTR keyed per cell address so any
fragment regenerates exactly its own keystream slice (same property, standard crypto).
That swap is a format-axis (layout_version) decision; meanwhile the numpy-internal
stream semantics are pinned in-repo by keystream_ref.py (pure-Python bit-exact
reference) + tests/test_keystream_ref.py + tests/golden_keystream_vectors.json.
"""
from __future__ import annotations

import hashlib

import numpy as np


def rng(seed: bytes, label: bytes) -> np.random.Generator:
    """Seeded generator for a (seed, label) pair via BLAKE2b -> Philox.

    The single source of randomness in codec and experiment paths (CLAUDE.md):
    everything derives from an explicit seed plus a domain-separation label.
    """
    h = hashlib.blake2b(seed + label, digest_size=16).digest()
    return np.random.Generator(np.random.Philox(key=int.from_bytes(h, "little")))


def keystream(seed: bytes, plane: int, page: int, shape: tuple[int, int]) -> np.ndarray:
    """Deterministic {0,1} keystream for one plane of one page.

    Keyed by (seed, plane, page) via BLAKE2b -> Philox counter RNG, so every page/plane
    is independently regenerable from the public seed alone (DESIGN.md R5).
    """
    gen = rng(seed, bytes([plane & 0xFF]) + page.to_bytes(4, "little"))
    return gen.integers(0, 2, size=shape, dtype=np.uint8)


def scramble(bits: np.ndarray, ks: np.ndarray) -> np.ndarray:
    """XOR with keystream. Involution: scramble(scramble(b, ks), ks) == b."""
    return np.bitwise_xor(bits.astype(np.uint8), ks)


def cells_to_dots(cell_bits: np.ndarray, cell: int = 3) -> np.ndarray:
    """Expand a cell-resolution bit array to printer-dot resolution (solid cells)."""
    return np.kron(cell_bits.astype(np.uint8), np.ones((cell, cell), dtype=np.uint8))


def dots_to_cells_hard(scan: np.ndarray, cell_px: int, ink_dark: bool = True) -> np.ndarray:
    """Naive hard demodulation: block-mean over aligned cells, midpoint threshold.

    Assumes the scan is already resampled to the cell grid (sync's job, §5). This is a
    test/bring-up tool; real demod is soft (LLRs) with 2-D equalization (§6, TODO M2).
    """
    h = (scan.shape[0] // cell_px) * cell_px
    w = (scan.shape[1] // cell_px) * cell_px
    m = scan[:h, :w].reshape(h // cell_px, cell_px, w // cell_px, cell_px).mean(axis=(1, 3))
    # Median threshold: the scrambler pins ink density near 50% (DESIGN.md 4.2), so the
    # median splits the classes and self-adapts to dot gain / banding bias, unlike a
    # fixed 0.5. Residual errors are 2-D ISI -- the inner LDPC's job (DESIGN.md 6).
    thresh = float(np.median(m))
    bits = m < thresh if ink_dark else m >= thresh
    return bits.astype(np.uint8)
