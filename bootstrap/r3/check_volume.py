"""The volume logic of receiver.py (section 8 and read_scan) against holo's
own fountain encoder, without scans: the scan stage is replaced by a stand-in
that hands read_scan the true certified tiles of a page.  Harness only.

  PYTHONPATH=src env/bin/python bootstrap/r3/check_volume.py [cadence|mixed|timing ...]

cadence: random K+1..K+3 repair-only symbol sets of a K = 1519 volume (the
         refuter's case): every set whose rank is K must close, in ingest
         order, with no retry.
mixed:   sessions that mix volumes (another size; the SAME size) in any order.
timing:  one ingest of K + 16 tiles (half source, half repair) and the close,
         K = 1000, 2000, 4000, 16384 (random but consistent symbols: the
         close reaches rank K and fails its SHA-256 by construction; the time
         covers the coefficient draws, the reduction and the back-substitution).
"""
import hashlib
import random
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import receiver as R  # noqa: E402
from holo.core import fountain  # noqa: E402
from holo.format import envelope, metadata  # noqa: E402

SEED = R.FORMAT_ID.encode()


def volume_tiles(payload, n_pages):
    """{counter: (metadata bit, symbol int)} for every tile of the volume."""
    S = R.SYMBOL_BITS
    K = -(-8 * (36 + len(payload)) // S)
    code = fountain.VolumeCode(K, S, SEED, tiles_per_page=R.TILES_PER_PAGE)
    src = fountain.pack_source(envelope.wrap(payload), K, S)
    esis = np.arange(n_pages * R.TILES_PER_PAGE, dtype=np.int64)
    sym = code.encode_symbols(src, esis)
    meta = metadata.tile_bits(metadata.encode_metadata(0, K), esis)
    weights = 1 << np.arange(S - 1, -1, -1, dtype=object)
    return K, {int(c): (int(meta[c]), int(np.dot(sym[c].astype(object), weights)))
               for c in esis}


def rank(K, rows):
    """GF(2) rank of the volume's rows over K columns (an independent check)."""
    v = R.Volume(encode_M(K), 0)
    basis = {}
    for c in rows:
        m = 1 << c if c < K else v.coefficients(c)
        while m:
            low = (m & -m).bit_length() - 1
            if low not in basis:
                basis[low] = m
                break
            m ^= basis[low]
    return len(basis)


def encode_M(K):
    return sum(((K >> 17 - j) & 1) << 1 + j for j in range(18))


def cadence():
    payload = random.Random(1).randbytes(400_000)
    K, tiles = volume_tiles(payload, 4)
    print(f"cadence: K = {K}")
    closed = deficient = missed = 0
    for trial in range(40):
        rng = random.Random(trial)
        extra = rng.choice([1, 2, 3])
        pool = list(range(840, 4 * 840))
        rng.shuffle(pool)
        chosen = pool[:K + extra]
        v = R.Volume(encode_M(K), 1)
        for c in chosen:
            v.add(c, tiles[c][1])
        r = rank(K, chosen)
        ok = v.payload == payload
        closed += ok
        deficient += (r < K)
        missed += (r == K and not ok)
        print(f"  trial {trial}: K+{extra}, rank {r}, closed in order: {ok}"
              + ("  MISSED" if r == K and not ok else ""), flush=True)
    print(f"cadence: {closed} closed, {deficient} rank-deficient, {missed} missed (must be 0)")
    return missed == 0 and closed + deficient == 40


class FakeScan:
    """read_scan's view of a scan, minus the pixels."""
    def __init__(self, name, dpi):
        self.name, self.rot = name, 0

    def find_lattice(self):
        return 1


def session(scans, tiles_of):
    """Run read_scan over (name, page) scans whose tiles come from tiles_of[name]."""
    R.Scan = FakeScan
    rx = R.Receiver()
    current = {}

    def place_page(sc, lat):
        page, tiles = tiles_of[sc.name]
        rx.page = page
        current.clear()
        current.update(tiles)
        return {divmod(c - page * R.TILES_PER_PAGE, R.TILES_X): None for c in tiles}

    def decode_tile(sc, lat, tile, d, counter):
        return current.get(counter)

    rx.place_page, rx.decode_tile = place_page, decode_tile
    for name in scans:
        print("   ", rx.read_scan(name, 1200))
    return rx


def page_of(tiles, page, drop=0.0, seed=0):
    rng = random.Random(seed)
    lo = page * R.TILES_PER_PAGE
    return page, {c: tiles[c] for c in range(lo, lo + R.TILES_PER_PAGE) if rng.random() >= drop}


def mixed():
    ok = True
    pb = random.Random(1).randbytes(400_000)          # B: 4 pages, K 1519
    pa = random.Random(2).randbytes(60_000)           # A: 1 page, K 228
    pa2 = random.Random(3).randbytes(60_000)          # A2: another volume, A's size
    KB, tb = volume_tiles(pb, 4)
    KA, ta = volume_tiles(pa, 1)
    KA2, ta2 = volume_tiles(pa2, 1)
    assert KA == KA2
    want = {hashlib.sha256(p).hexdigest(): n for n, p in (("B", pb), ("A", pa), ("A2", pa2))}
    cases = [
        ("B3, A0 (other size), B2, B1", ["B3", "A0", "B2", "B1"], {"B", "A"}),
        ("A0 thin 60 % cut, then B0, B1", ["A0cut", "B0", "B1"], {"B", "A"}),
        ("A0 part, A2-0 part (same size), A0 rest", ["A0h1", "A2h1", "A0h2"], {"A"}),
        ("A2-0 half first, then A0 whole", ["A2h1", "A0"], set()),
        ("B2 thin (20 tiles), B3, B1", ["B2thin", "B3", "B1"], {"B"}),
    ]
    tiles_of = {
        "B0": page_of(tb, 0), "B1": page_of(tb, 1), "B2": page_of(tb, 2), "B3": page_of(tb, 3),
        "A0": page_of(ta, 0), "A0cut": page_of(ta, 0, 0.6, 5),
        "A0h1": (0, {c: v for c, v in ta.items() if c % 2 == 0 and c < 300}),
        "A0h2": (0, {c: v for c, v in ta.items() if c % 2 == 1 or c >= 300}),
        "A2h1": (0, {c: v for c, v in ta2.items() if c % 2 == 1 and c < 400}),
        "B2thin": (2, {c: tb[c] for c in range(2 * 840, 2 * 840 + 20)}),
    }
    for label, scans, expect in cases:
        print(f"mixed: {label}")
        rx = session(scans, tiles_of)
        got = {want.get(hashlib.sha256(v.payload).hexdigest(), "WRONG")
               for v in rx.volumes if v.payload is not None}
        good = got == expect
        print(f"    volumes {len(rx.volumes)}, complete: {sorted(got)}; expected {sorted(expect)}: "
              f"{'OK' if good else 'FAIL'}")
        ok &= good
    return ok


def timing():
    for K in (1000, 2000, 4000, 16384):
        rng = random.Random(K)
        v = R.Volume(encode_M(K), 1)
        src = list(range(K))
        rng.shuffle(src)
        cs = src[:K // 2] + list(range(K, K + K - K // 2 + 16))
        rng.shuffle(cs)
        src = [rng.getrandbits(R.SYMBOL_BITS) for _ in range(K)]
        val = {}
        for c in cs:                       # consistent symbols: repair = XOR of sources
            if c < K:
                val[c] = src[c]
                continue
            m, x = v.coefficients(c), 0
            while m:
                bit = m & -m
                x ^= src[bit.bit_length() - 1]
                m ^= bit
            val[c] = x
        t = time.time()
        refused = False
        for c in cs:
            try:
                v.add(c, val[c])
            except R.Conflict:             # at the close: random data, no envelope
                refused = True
                break
        print(f"timing: K = {K}: {len(cs)} tiles in, rank {len(v.rows)}, "
              f"ingest + close {time.time() - t:.1f} s (SHA wrong by construction: {refused})",
              flush=True)
    return True


if __name__ == "__main__":
    what = sys.argv[1:] or ["cadence", "mixed", "timing"]
    res = {w: globals()[w]() for w in what}
    print("RESULT", res)
