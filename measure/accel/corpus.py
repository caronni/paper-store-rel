"""The tile-attempt corpus the belief-propagation gates run on.

Built through the shipped codec plumbing — ``tile_codec.encode_tile``,
the slot permutation and the shortening included — then pushed through a
BI-AWGN channel at a spread of noise levels so the corpus spans the
three regimes that matter: clean (the first syndrome check already
passes), marginal (min-sum or sum-product has to work for it, and some
attempts fail), and hopeless.  Both receiver routes into the decoder,
``decode_tile`` and ``decode_frame``'s per-child leg, hand
``ldpc.decode`` the same object — one mother-code LLR vector with the
shortened span at -inf — so one corpus covers both.

What is stored per attempt is the mother-code LLR vector exactly as
``tile_codec.decode_tile`` would hand it to ``ldpc.decode``: shortened
positions at -inf, everything else the channel's soft value.  Both the
CPU decoder and the mlx decoder are then fed the identical vector, so
the only thing under comparison is belief propagation itself.

    PYTHONPATH=<worktree> <python> measure/accel/corpus.py --out <dir>
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from holo3.format import tile_codec
from holo3.lib import ldpc

SEED = 20260831
RATE_IDS = ("r0547", "r0550", "r0625", "r0700", "r0775", "r0850")
# n_sites: 100 is the K sim's tile shorten, 120 the p120 colour rows'.
SITE_COUNTS = (100, 120)
# One ladder wide enough to straddle every rate's cliff: r0850 gives up
# around sigma 0.55, r0550 holds to about 0.85 (measured, 2026-08-31).
SIGMA_LADDER = (0.30, 0.38, 0.45, 0.50, 0.55, 0.62,
                0.70, 0.76, 0.82, 0.88, 0.95, 1.05)
ATTEMPTS_PER_CELL = 12


def channel_llr(cells: np.ndarray, sigma: float,
                rng: np.random.Generator) -> np.ndarray:
    """BI-AWGN over the codec's sign convention.

    holo3 reads a POSITIVE llr as evidence for a set bit: ``ldpc.decode``
    negates its input and calls ``Ltot < 0`` a one, and the shortened
    known-zero span is pinned at -inf.  So bit 1 is transmitted as +1
    here, and LLR = 2y/sigma^2.  (Getting this backwards makes even a
    noiseless codeword undecodable, which is how it was caught.)
    """
    transmitted = 2.0 * np.asarray(cells, np.float64) - 1.0
    received = transmitted + rng.normal(0.0, sigma, size=transmitted.shape)
    return 2.0 * received / (sigma * sigma)


def mother_llr(llr_flat: np.ndarray, rate_id: str, n_sites: int,
               site_flat: np.ndarray, a_t: int, b_t: int) -> np.ndarray:
    """The vector decode_tile builds before calling ldpc.decode."""
    code = ldpc.CODES[rate_id]
    out = np.zeros(code.n_bits, dtype=np.float64)
    out[tile_codec.transmitted_positions(rate_id, n_sites)] = llr_flat[
        tile_codec.cell_map(site_flat, a_t, b_t)]
    out[code.k_bits - n_sites:code.k_bits] = -np.inf
    return out


def _coprime_slope(rng: np.random.Generator, n_slots: int) -> int:
    while True:
        candidate = int(rng.integers(1, n_slots))
        if math.gcd(candidate, n_slots) == 1:
            return candidate


def build(rng: np.random.Generator) -> dict:
    llrs: list[np.ndarray] = []
    truth: list[np.ndarray] = []
    meta: list[dict] = []
    for rate_id in RATE_IDS:
        code = ldpc.CODES[rate_id]
        for n_sites in SITE_COUNTS:
            cap = tile_codec.tile_capacity(rate_id, n_sites)
            site_flat = rng.choice(tile_codec.N_CELLS, size=n_sites,
                                   replace=False).astype(np.int64)
            a_t = _coprime_slope(rng, tile_codec.N_CELLS - n_sites)
            b_t = int(rng.integers(0, 4096))
            for sigma in SIGMA_LADDER:
                for _ in range(ATTEMPTS_PER_CELL):
                    user = rng.integers(0, 2, size=cap).astype(np.uint8)
                    cells = tile_codec.encode_tile(
                        user, rate_id, site_flat, a_t, b_t)
                    info = np.zeros(code.k_bits, np.uint8)
                    info[:cap] = user
                    info[cap:cap + tile_codec.CRC_BITS] = (
                        tile_codec.crc32_bits(user))
                    llr_flat = channel_llr(cells, sigma, rng)
                    llrs.append(mother_llr(llr_flat, rate_id, n_sites,
                                           site_flat, a_t, b_t))
                    truth.append(np.pad(
                        ldpc.encode(info, code),
                        (0, tile_codec.N_CELLS - code.n_bits)))
                    meta.append({
                        "rate_id": rate_id, "n_sites": int(n_sites),
                        "cap": int(cap), "sigma": float(sigma),
                        "n_bits": int(code.n_bits),
                    })
    return {"llr": np.asarray(llrs, np.float64),
            "truth": np.asarray(truth, np.uint8), "meta": meta}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    built = build(rng)
    np.save(args.out / "corpus_llr.npy", built["llr"])
    np.save(args.out / "corpus_truth.npy", built["truth"])
    (args.out / "corpus_meta.json").write_text(
        json.dumps({"seed": SEED, "attempts": built["meta"]},
                   indent=1) + "\n")
    print(f"attempts={built['llr'].shape[0]} "
          f"bytes={built['llr'].nbytes / 1e6:.1f} MB "
          f"rates={sorted({m['rate_id'] for m in built['meta']})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
