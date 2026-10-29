import numpy as np, json, sys
from holo.core.ldpc.decode import encode
from holo.core.ldpc.construct import load_code
out = {}
for rid in ["r0550", "r0547"]:
    c = load_code(rid); k = c.spec.k_bits; m = c.spec.m_bits
    # parity part of every single-info-bit codeword (systematic)
    P = np.stack([encode(np.eye(1, k, i, dtype=np.uint8)[0], rid)[k:] for i in range(k)]).astype(np.uint8)
    assert P.shape == (k, m)
    Pp = np.packbits(P, axis=1)  # k x m/8
    popcnt = np.array([bin(x).count("1") for x in range(256)], np.uint8)
    best = (10**9, None); hist = {}
    for i in range(k):
        x = np.bitwise_xor(Pp[i+1:], Pp[i])
        w = popcnt[x].sum(axis=1) + 2
        if len(w):
            j = int(np.argmin(w)); wm = int(w[j])
            for ww in w[w <= 12]: hist[int(ww)] = hist.get(int(ww), 0) + 1
            if wm < best[0]: best = (wm, (i, i+1+j))
    # verify the argmin by re-encoding
    i, j = best[1]; e = np.zeros(k, np.uint8); e[i] = e[j] = 1
    wv = int(encode(e, rid).sum())
    out[rid] = {"min_w2": best[0], "argmin": [int(i), int(j)], "reencoded_weight": wv, "hist_w<=12": dict(sorted(hist.items()))}
    print(rid, out[rid], flush=True)
json.dump(out, open("scratch/rung-ladder-20260930/refute_c1/pairs.json", "w"), indent=1)
