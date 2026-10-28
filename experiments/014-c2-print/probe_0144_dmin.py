#!/usr/bin/env python
"""014.4 mechanism check: is the decoy-mismatch floor the window code's
minimum distance? Pilot values per tile = codeword(counter) XOR a
tile-INDEPENDENT keystream, so decoy-vs-true value disagreement at a
tile-aligned shift is exactly the Hamming distance between two codewords
of the (100,23) d>=27 code. Prediction: min decoy mismatch ~= d/n + (1-2d/n)
*BER with d small multiples of 27 -- and the argmin decoys are small
tile shifts."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/014-c2-print"))

from paperholo import compose, pilots
from paperholo.modulation import rng
import gen_e014

SEED = gen_e014.SEED
spec = gen_e014.make_spec()
layout = spec.pilot
plane = spec.plane
tiles_y, tiles_x = (spec.page_cells_yx[0] // layout.period_cells,
                    spec.page_cells_yx[1] // layout.period_cells)
geo = {"tiles_x": tiles_x, "tiles_per_page": tiles_y * tiles_x}

def word_bits(ty, tx):
    return pilots.encode_word(layout, SEED, plane, 0, ty, tx, **geo)

# codeword distance between a reference tile and its neighbourhood
ty0, tx0 = 20, 15
ref = word_bits(ty0, tx0)
print("Hamming distance cw(tile) vs cw(tile+shift), ref tile (20,15):")
for dy, dx in [(0, 1), (0, 2), (0, 3), (1, 0), (2, 0), (1, 1), (0, 5),
               (5, 0), (3, 2), (10, 7)]:
    d = int(np.sum(ref != word_bits(ty0 + dy, tx0 + dx)))
    print(f"  shift ({dy:2d},{dx:2d}): d = {d:3d}/100")

# distance distribution over many random tile pairs
rs = rng(SEED, b"e014/dmin-probe")
ds = []
for _ in range(400):
    a = (int(rs.integers(0, tiles_y)), int(rs.integers(0, tiles_x)))
    b = (int(rs.integers(0, tiles_y)), int(rs.integers(0, tiles_x)))
    if a == b:
        continue
    ds.append(int(np.sum(word_bits(*a) != word_bits(*b))))
ds = np.asarray(ds)
print(f"\nrandom tile pairs (n={ds.size}): d min {ds.min()} "
      f"p5 {np.percentile(ds,5):.0f} median {np.median(ds):.0f} "
      f"max {ds.max()}  (code guarantee d>=27; mean of random pair "
      f"~ n/2 - codeword-bias)")
print(f"floor prediction: min decoy mismatch ~= d_min/100 + "
      f"(1-2*d_min/100)*BER; at d_min={ds.min()} BER 5%: "
      f"{ds.min()/100 + (1-2*ds.min()/100)*0.05:.3f}")
