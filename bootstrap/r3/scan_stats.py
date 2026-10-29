"""Per-scan statistics and stage timings for receiver.py (harness).

For each scan: the receiver's own stages, timed separately, over EVERY placed
tile (no early close): PGM read, lattice, placement, then per tile the cell
sampling + calibration, the payload scramble (AES), the slot map, LDPC +
CRC; then the fountain close from this page's certified symbols alone.
Against the generator's truth (harness only, never the receiver): the raw
hard cell error of the calibrated reads and whether every certified symbol
is the true one.
  PYTHONPATH=src env/bin/python bootstrap/r3/scan_stats.py [SCAN[:DPI] ...]
(no arguments = every scan in build/r3; at most 6 processes)
Writes build/r3/stats/<scan>.json and prints one line per scan.
"""
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[0] / "build" / "r3"
sys.path.insert(0, str(HERE))


def gt_cells(R):
    pages = []
    cd = R.CELL_DOTS
    for gt in sorted((OUT / "vol").glob("page*_gt.npy")):
        dots = np.unpackbits(np.load(gt), axis=1, bitorder="big")
        pages.append(dots[cd // 2::cd, cd // 2::cd])
    return pages


def one(arg):
    import receiver as R
    name, _, dpi = arg.partition(":")
    dpi = int(dpi or (2400 if name.startswith("s2400") else 1200))
    path = OUT / name
    T = {}
    t = time.perf_counter()
    sc = R.Scan(str(path), dpi)
    T["read"] = time.perf_counter() - t
    t = time.perf_counter()
    lat = sc.find_lattice()
    T["lattice"] = time.perf_counter() - t
    rx = R.Receiver()
    t = time.perf_counter()
    placed = rx.place_page(sc, lat)
    T["placement"] = time.perf_counter() - t
    page = rx.page
    cells = gt_cells(R)[page]
    T.update(sampling=0.0, scramble=0.0, slotmap=0.0, ldpc=0.0)
    cert, wrong, err, n = {}, 0, 0, 0
    truth = json.loads((OUT / "volume.json").read_text())
    for tile, d in placed.items():
        counter = page * R.TILES_PER_PAGE + tile[0] * R.TILES_X + tile[1]
        word = R.printed_word(counter)
        t0 = time.perf_counter()
        llr = sc.tile_llrs(lat, tile, d, word)
        t1 = time.perf_counter()
        scr = R.payload_scramble(page, 64 * tile[0], 64 * tile[1])
        t2 = time.perf_counter()
        a, b = R.slot_params(counter)
        L = [0.0] * R.N_CODE
        for j in range(R.SLOTS):
            cell = R.NONSITE[(a * j + b) % R.SLOTS]
            x = llr[cell]
            L[j if j < R.SHORT[0] else j + 100] = -x if scr[cell] else x
        t3 = time.perf_counter()
        L = R.ldpc_decode(L)
        r = L and R.certify(L)
        t4 = time.perf_counter()
        T["sampling"] += t1 - t0
        T["scramble"] += t2 - t1
        T["slotmap"] += t3 - t2
        T["ldpc"] += t4 - t3
        g = cells[64 * tile[0]:64 * tile[0] + 64, 64 * tile[1]:64 * tile[1] + 64].ravel()
        e = sum(int(x < 0) != int(c) for x, c in zip(llr, g) if x != 0)
        err += e
        n += sum(1 for x in llr if x != 0)
        if r:
            cert[counter] = r
    # every certified symbol against the true one (source rows from the
    # payload's envelope, repair rows as XORs of them)
    payload = (OUT / "payload.bin").read_bytes()
    K, S = truth["manifest"]["volume"]["k_total"], R.SYMBOL_BITS
    env = R.sha256(payload) + len(payload).to_bytes(4, "big") + payload
    stream = int.from_bytes(env, "big") << (K * S - 8 * len(env))
    src = [stream >> S * (K - 1 - k) & ((1 << S) - 1) for k in range(K)]
    t = time.perf_counter()
    M = R.solve_metadata({c: m for c, (m, _) in cert.items()})
    vol = R.Volume(M, 1)
    closed = True
    try:
        for c, (m, s) in sorted(cert.items()):
            vol.add(c, s)
    except R.Conflict:
        closed = False
    closed = closed and vol.payload is not None
    T["fountain"] = time.perf_counter() - t
    for c, (m, s_) in cert.items():
        if c < K:
            want = src[c]
        else:
            mask, want = vol.coefficients(c), 0
            for k in range(K):
                if mask >> k & 1:
                    want ^= src[k]
        wrong += s_ != want
    res = {"scan": name, "dpi": dpi, "page": page, "turn": 90 * sc.rot,
           "placed": len(placed), "certified": len(cert), "wrong_certificates": wrong, "raw_cell_error": err / max(n, 1),
           "closes_alone": bool(closed and vol.payload == payload), "K": vol.K,
           "seconds": {k: round(v, 2) for k, v in T.items()},
           "total_s": round(sum(T.values()), 1)}
    (OUT / "stats").mkdir(exist_ok=True)
    (OUT / "stats" / (name + ".json")).write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    args = sys.argv[1:] or sorted(p.name for p in OUT.glob("*.pgm"))
    with Pool(min(6, len(args))) as pool:
        for r in pool.imap(one, args):
            s = r["seconds"]
            print(f"{r['scan']:18s} page {r['page']} turn {r['turn']:3d} placed {r['placed']:3d} "
                  f"certified {r['certified']:3d} wrong {r['wrong_certificates']} raw {100 * r['raw_cell_error']:.3f} % "
                  f"alone {'closes' if r['closes_alone'] else 'open  '} "
                  + " ".join(f"{k} {v:.1f}" for k, v in s.items()) + f" total {r['total_s']}",
                  flush=True)
