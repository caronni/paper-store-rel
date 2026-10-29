"""Part-by-part check of receiver.py against src/holo (the format authority)
and the standard library, then the whole code chain on the generator's own
cells (no scan, no acquisition): every tile of the test volume decoded from
hard cell values, the volume closed from page 0 alone and from a random 60 %
of each page's tiles.  Harness only (uses holo, numpy, hashlib, zlib).
  PYTHONPATH=src env/bin/python bootstrap/r3/check_parts.py [--c4]
"""
import hashlib
import json
import math
import random
import sys
import time
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
C4 = "--c4" in sys.argv
if C4:
    src = (HERE / "receiver.py").read_text().replace("CELL_DOTS = 3 ", "CELL_DOTS = 4 ", 1)
    (HERE.parents[0] / "build" / "r3" / "c4").mkdir(parents=True, exist_ok=True)
    p = HERE.parents[0] / "build" / "r3" / "c4" / "receiver_c4.py"
    p.write_text(src)
    sys.path.insert(0, str(p.parent))
    import receiver_c4 as R  # noqa: E402
else:
    import receiver as R  # noqa: E402
from holo.core import keystream, keystream_spec  # noqa: E402
from holo.format import pilots  # noqa: E402
from holo.format.resolve import resolve_format_ref  # noqa: E402

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


rng = random.Random(1)
for n in (0, 1, 55, 56, 63, 64, 65, 1000, 200000):
    d = bytes(rng.randrange(256) for _ in range(n))
    if R.sha256(d) != hashlib.sha256(d).digest():
        check(f"sha256 len {n}", False)
check("sha256 == hashlib on 9 lengths", True)
fips = R.aes_encrypt(R.aes_key(bytes(range(16))), 0x00112233, 0x44556677, 0x8899aabb, 0xccddeeff)
check("AES FIPS-197 C.1", b"".join(x.to_bytes(4, "big") for x in fips).hex()
      == "69c4e0d86a7b0430d8cdb78070b4c55a")
# the receiver's id against holo's own resolution of the display name (not
# against itself: the keystream checks below take their seed from holo too)
spec = resolve_format_ref("c4-k-r0550@26x18" if C4 else "c3-k-r0550@35x24")
seed = spec.seed
check("FORMAT_ID == holo's seed " + seed.decode(), seed.decode() == R.FORMAT_ID)
check("SITES_ID == holo's family seed", spec.family_seed.decode() == R.SITES_ID)
for args in ((1, 3, 0, 5, 7), (6, 0, 0, 839, 0), (7, 0, 0, 1000, 3), (2, 3, 0, 99, 0),
             (1, 3, 1, 2239, 1535)):
    if R.keystream(R.ROW_KEY, *args) != keystream_spec.block(seed, *args):
        check(f"keystream {args}", False)
check("keystream == keystream_spec.block", True)
check("sites == pilots.word_site_cells_yx",
      [tuple(map(int, s)) for s in pilots.word_site_cells_yx(R.SITES_ID.encode())] == R.SITES)
cs = [0, 1, 5, 839, 840, 1679, 262143 - 63]
ref = pilots.word_values(seed, cs)
check("printed_word == pilots.word_values",
      all(list(map(int, ref[i])) == R.printed_word(c) for i, c in enumerate(cs)))
check("slot_params == keystream.slot_perm_params",
      all(tuple(R.slot_params(c)) == tuple(int(v) for v in keystream_spec.slot_perm_param(seed, c, R.SLOTS))
          for c in (0, 1, 2, 3, 500, 1679)))
pb = keystream.payload_bits(seed, 3, 1, (128, 128))
check("payload_scramble == keystream.payload_bits",
      R.payload_scramble(1, 64, 64) == [int(v) for v in pb[64:128, 64:128].ravel()])
d = bytes(range(256)) * 3
check("crc32 == zlib", R.crc32(d) == zlib.crc32(d))
check("cos_sin", all(abs(R.cos_sin(a)[0] - math.cos(math.radians(a))) < 1e-12
                     and abs(R.cos_sin(a)[1] - math.sin(math.radians(a))) < 1e-12
                     for a in (-45, -10, -0.5, 0, 0.3, 1.5, 10, 45)))

# ---- the code chain on the generator's cells
OUT = HERE.parents[0] / "build" / "r3" / ("c4" if C4 else "")
vt = json.loads((OUT / "volume.json").read_text())
payload = (OUT / "payload.bin").read_bytes()
cd = R.CELL_DOTS
pages = []
for gt in sorted((OUT / "vol").glob("page*_gt.npy")):
    dots = np.unpackbits(np.load(gt), axis=1, bitorder="big")
    pages.append(dots[cd // 2::cd, cd // 2::cd])         # page cells, 1 = ink


def tile_symbol(page, ty, tx, noise=0.0, nrng=None):
    cells = pages[page][ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64].ravel()
    llr = [(-4.0 if c else 4.0) for c in cells]
    if noise:
        for i in range(len(llr)):
            if nrng.random() < noise:
                llr[i] = -llr[i]
    counter = page * R.TILES_PER_PAGE + ty * R.TILES_X + tx
    scr = R.payload_scramble(page, 64 * ty, 64 * tx)
    a, b = R.slot_params(counter)
    L = [0.0] * R.N_CODE
    for j in range(R.SLOTS):
        cell = R.NONSITE[(a * j + b) % R.SLOTS]
        x = llr[cell]
        L[j if j < R.SHORT[0] else j + 100] = -x if scr[cell] else x
    t = time.time()
    L = R.ldpc_decode(L)
    dt = time.time() - t
    return (L and R.certify(L)), counter, dt


# word sites of the cells == printed_word
w_ok = all(
    [int(pages[0][ty * 64 + u, tx * 64 + v]) for u, v in R.SITES]
    == R.printed_word(ty * R.TILES_X + tx) for ty, tx in ((0, 0), (3, 7), (R.TILES_Y - 1, R.TILES_X - 1)))
check("printed words found at the sites of the GT cells", w_ok)

nrng = random.Random(7)
times = []
for noise in (0.02, 0.05):
    good = 0
    for i in range(10):
        r, c, dt = tile_symbol(0, i, i % R.TILES_X, noise, nrng)
        good += bool(r)
        times.append((noise, dt))
    print(f"  LDPC at {noise:.0%} flipped cells: {good}/10 certified, "
          f"{sum(t for n, t in times if n == noise) / 10 * 1000:.0f} ms/tile")



def close_from(items):
    """The receiver's volume path: K from the metadata bits (48 tiles), then
    every symbol into the fountain until it closes."""
    meta, held, vol = {}, [], None
    for c, (m, s) in items:
        meta[c] = m
        held.append((c, s))
        if vol is None:
            M = R.solve_metadata(meta)
            if M is None:
                continue
            vol = R.Volume(M, 1)
            for cc, ss in held:
                vol.add(cc, ss)
        else:
            vol.add(c, s)
        if vol.payload is not None:
            break
    return vol


def page0_tiles():
    for ty in range(R.TILES_Y):
        for tx in range(R.TILES_X):
            r, c, _ = tile_symbol(0, ty, tx)
            assert r, (ty, tx)
            yield c, r


t = time.time()
vol = close_from(page0_tiles())
check(f"page 0 alone closes (K={vol.K}, symbols {len(vol.symbols)}, "
      f"{time.time() - t:.0f} s)", vol.payload == payload)

drng = random.Random(3)
keep = []
for page in range(len(pages)):
    tiles = [(ty, tx) for ty in range(R.TILES_Y) for tx in range(R.TILES_X)]
    keep += [(page, t) for t in drng.sample(tiles, int(0.6 * len(tiles)))]
drng.shuffle(keep)
t = time.time()
vol = close_from((c, r) for r, c, _ in (tile_symbol(page, ty, tx) for page, (ty, tx) in keep))
check(f"random 60 % of both pages' tiles closes (K={vol.K}, symbols {len(vol.symbols)}, "
      f"repair rows used {sum(1 for c in vol.symbols if c >= vol.K)}, {time.time() - t:.0f} s)",
      vol.payload == payload)
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
