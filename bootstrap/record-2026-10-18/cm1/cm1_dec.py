"""cm1 stage-1 decoder: cmmix's model family with BOUNDED tables.

Bitwise context mixing: orders 0-4, a 7-byte context, a word context and a
line-above context (8 contexts) + a match model; three integer logistic
mixers summed in the stretch domain; carry-less 32-bit arithmetic coder
(byte-identical to cmmix's).  Pure Python, no imports in the decoder.

    decode(src, n, primer, k=22) -> bytes     (k = table bits, 16..24)

Memory: T = 2^k + 131584 16-bit slots, mt = 2^(k-2) 32-bit positions,
W = 1,184,256 32-bit weights, plus the n-byte output buffer; at k=22 that
is 8.65 + 4.19 + 4.74 = 17.6 MB of tables.  memoryview.cast fixes the
widths: "H" = 2 bytes, "I" = "i" = 4 bytes (native order; never stored).
Encoder: cm1_enc.py derives it from the text between the markers below.
Known answer: KAV at the end of this file; `python3 cm1_dec.py --kav`.
CLI: python3 cm1_dec.py IN N OUT [PRIMER [K]]"""
# BEGIN DECODER
# Integers only.  F = 2^32-1 (coder, word hash), Q = 2^64-1 (bucket hash).
# sq[x] = 4096/(1+exp(-(x-2048)/256)) by Euler steps upward from x=0,
# s = sq*2^20, start 1460000 (sets sq[2048] = 2048; as cmmix).
# st = inverse of sq on 10-bit probabilities (st[p >> 2]).
# T slot = 12-bit probability P(1)*4096 << 4 | 4-bit hit count n (<= 15);
# update p += ((y << 12) - p) * R[n] >> 16, R[n] = 65536/(n + 1.2).
# Every all-0x80 byte pattern reads 0x8080: p = 2056, n = 0 (fresh slot).
# Slots come in buckets of 16: slot 0 = a 16-bit check, slots 1..15 = the
# 15 bit-states of one nibble (cn = 1, then cn*2+bit).  Orders 0 and 1 are
# DIRECT (at D, no check).  Contexts 2..7 are hashed at bits 0 and 4:
# z = ((H*8 + q)*32 + c0) * E mod 2^64, bucket t = top k-4 bits << 4, check
# = the 16 bits below; t or its pair t^16 is used if its check matches,
# else the one whose slot 1 has the lower count is reset (check, 0x8080).
# U, V: the match model's 32 16-bit probabilities and counts (<= 30),
# index 2*ml + predicted bit.  mt: last position per 6-byte hash.
# W: mixer weights MINUS 16384 (1.0 = 65536), zero-initialized: set w by
# c0 and ml>0, set u by (c, c0), set v by hashed order-2 and c0.
# K: bit c set iff byte c is in [0-9A-Za-z_].  pl, ls = starts of the
# previous and current line; b[ls-1] (a newline) marks "past its end".
def decode(src, n, primer, k=22):
    F, Q, s = 4294967295, 18446744073709551615, 1460000
    sq, st, K = [0] * 4096, [0] * 1024, 0x7fffffe87fffffe03ff000000000000
    for x in range(4096):
        sq[x] = s >> 20
        s += s * ((4096 << 20) - s) >> 40
        st[sq[x] >> 2] = x - 2048
    D, A, G, E = 1 << k, 68 - k, 0x9E3779B1, 0x9E3779B97F4A7C15
    T = memoryview(bytearray(b"\x80" * (2 * D + 263168))).cast("H")
    Z = memoryview(bytearray(b"\x80" * 30)).cast("H")
    mt = memoryview(bytearray(D)).cast("I")
    W = memoryview(bytearray(4737024)).cast("i")
    U, V, B = [32768] * 32, [0] * 32, [0] * 8
    R = [655360 // (j * 10 + 12) for j in range(31)]
    b = bytearray(8) + primer + bytearray(n)
    lp, s, x1, x2, x, kk, h = 8 + len(primer), src + bytes(8), 0, 0, 0, 0, 0
    wh, mp, ml, pl, ls = 0, 0, 0, 8, 8
    for i in range(8, len(b)):
        c, c0, h = b[i - 1], 1, (h << 8 | b[i - 1]) & 0xFFFFFFFFFFFFFF
        wh = (wh + c + 1) * 773 * (K >> c & 1) & F
        pl, ls = (ls, i) if c == 10 else (pl, ls)
        r = b[min(pl + i - ls, ls - 1)] << 8 | min(i - ls, 40)
        H = [0, 0, h & 65535, h & 16777215, h & F, wh, r, h]
        ml, mp = (ml + (ml < 15)) * (ml > 0), mp + 1
        o = h * G >> 50 - k & (D >> 2) - 1
        mp = mp if ml else mt[o]
        ml, mt[o] = ml or int(mp > 0), i
        for j in range(8):
            if j == 0 or j == 4:
                B[0], B[1] = D + c0 * 16, D + 512 + c * 512 + c0 * 16
                for q in range(2, 8):
                    z = ((H[q] * 8 + q) * 32 + c0) * E & Q
                    t, cz = z >> A << 4, z >> A - 16 & 65535
                    if T[t] != cz:
                        if T[t ^ 16] == cz:
                            t = t ^ 16
                        else:
                            if T[t + 1] & 15 > T[t ^ 17] & 15:
                                t = t ^ 16
                            T[t], T[t + 1:t + 16] = cz, Z
                    B[q] = t
                cn = 1
            X = [t + cn for t in B]
            e = b[mp] >> 7 - j & 1
            mi = ml * 2 + e
            S = [st[T[t] >> 6] for t in X] + [st[U[mi] >> 6]]
            w, u = (c0 + 256 * (ml > 0)) * 9, (512 + c * 256 + c0) * 9
            v = (66048 + ((h & 65535) * G >> 24 & 255) * 256 + c0) * 9
            d = sum([(W[w + q] + W[u + q] + W[v + q] * 2 + 65536) * S[q]
                     for q in range(9)]) >> 18
            p = sq[max(-2047, min(2047, d)) + 2048]
            y = b[i] >> 7 - j & 1
            if i >= lp:
                # CODER
                while (x1 ^ x2) >> 24 == 0:
                    x1, x2 = x1 << 8 & F, x2 << 8 & F | 255
                    x, kk = x << 8 & F | s[kk], kk + 1
                xm = x1 + (x2 - x1 >> 12) * p
                x1, x2, y = (x1, xm, 1) if x <= xm else (xm + 1, x2, 0)
                # /CODER
            for t in X:
                pt, nt = T[t] >> 4, T[t] & 15
                pt += ((y << 12) - pt) * R[nt] >> 16
                T[t] = pt << 4 | nt + (nt < 15)
            U[mi] += ((y << 16) - U[mi]) * R[V[mi]] >> 16
            V[mi] += V[mi] < 30
            g = (y << 12) - p
            for q in range(9):
                dq = S[q] * g >> 10
                W[w + q] += dq
                W[u + q] += dq
                W[v + q] += dq
            c0, cn = c0 + c0 + y, cn + cn + y
            ml = ml * (e == y)
        b[i] = c0 & 255
    return bytes(b[lp:])
# END DECODER


# Known-answer vectors: (k, primer, plaintext, coded bytes as hex).
_P = b"cm1 known answer: def f(x):\n    return x * 2\n" * 3
KAV = [(16, b"", _P, "9570238bb0a96e4e598c4da008ad90deed2f21c1"
        "c30ee1fa90d9592eb2a06bc767ba1cd0c7"),
       (18, b"def g(y):\n    return y + 1\n", _P,
        "3d64aaf8dbc31cb77eb33ce5b5ec52c8a1e5919b27bd9a1e")]


def kav():
    return all(decode(bytes.fromhex(hx), len(pl), pr, k) == pl
               for k, pr, pl, hx in KAV)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--kav"]:
        ok = kav()
        print("KAV", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)
    a = sys.argv[1:]
    src = open(a[0], "rb").read()
    pr = open(a[3], "rb").read() if len(a) > 3 and a[3] != "-" else b""
    kb = int(a[4]) if len(a) > 4 else 22
    open(a[2], "wb").write(decode(src, int(a[1]), pr, kb))
