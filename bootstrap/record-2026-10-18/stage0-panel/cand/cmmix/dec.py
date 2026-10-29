"""cmmix stage-0 decoder (60-line budget, 48 used): bitwise context mixing
over orders 0-4, a hashed order-7 context, an identifier context, a
line-above context and a match model; three integer logistic mixers summed
in the stretch domain; carry-less 32-bit binary arithmetic coder."""
import sys
# BEGIN DECODER
# Integers only. Every multiply may wrap mod 2^64 (checked: byte-identical);
# signed 64-bit holds every other intermediate (|weights| < 2^17 measured).
# F = 2^32-1 (coder, word hash), M = 2^24-1 (table index), h = last 7 bytes.
# sq[x] = 4096/(1+exp(-(x-2048)/256)) by Euler steps upward from x=0,
# s = sq*2^20, start 1460000 (sets sq[2048] = 2048; max error < 1).
# st = inverse of sq on 10-bit probabilities (st[p>>2]).
# P(bit=1) = p/4096. T: 16-bit probabilities, N: hit counts (<= 30),
# R[n] = 65536/(n+1.2): the update rate. W: mixer weights, 1.0 = 65536.
# K: bit c set iff byte c is in [0-9A-Za-z_]. Line above: pl, ls = starts
# of the previous and current line; b[ls-1] (a newline) marks "past end".
# Match: mt maps a 6-byte hash to the last position; ml = match length.
def decode(src, n, primer):
    F, M, s = 4294967295, 16777215, 1460000
    sq, st, K = [0] * 4096, [0] * 1024, 0x7fffffe87fffffe03ff000000000000
    for x in range(4096):
        sq[x] = s >> 20
        s += s * ((4096 << 20) - s) >> 40
        st[sq[x] >> 2] = x - 2048
    T, N, mt = [32768] * (M + 1), [0] * (M + 1), [0] * 1048576
    R, G = [655360 // (k * 10 + 12) for k in range(31)], 0x9E3779B1
    W = [[16384] * 9 for k in range(131584)]
    b = bytearray(8) + primer + bytearray(n)
    lp, s, x1, x2, x, k, h = 8 + len(primer), src + bytes(8), 0, 0, 0, 0, 0
    wh, mp, ml, pl, ls, P = 0, 0, 0, 8, 8, 0x6F4F2A1
    for i in range(8, len(b)):
        c, c0, h = b[i - 1], 1, (h << 8 | b[i - 1]) & 0xFFFFFFFFFFFFFF
        wh = (wh + c + 1) * 773 * (K >> c & 1) & F
        pl, ls = (ls, i) if c == 10 else (pl, ls)
        r = b[min(pl + i - ls, ls - 1)] << 8 | min(i - ls, 40)
        H = [0, h & 255, h & 65535, h & 16777215, h & F, wh, r, h * G >> 9]
        ml, mp = (ml + (ml < 15)) * (ml > 0), mp + 1
        mp = mp if ml else mt[h * G >> 28 & 1048575]
        ml, mt[h * G >> 28 & 1048575] = ml or int(mp > 0), i
        for j in range(8):
            X = [((H[q] * 8 + q) * G >> 20) + c0 * P & M for q in range(8)]
            X.append(M - ml * 2 - (b[mp] >> 7 - j & 1))
            S = [st[T[t] >> 6] for t in X]
            w, u = W[c0 + 256 * (ml > 0)], W[512 + c * 256 + c0]
            v = W[66048 + ((h & 65535) * G >> 24 & 255) * 256 + c0]
            d = sum([(w[q] + u[q] + v[q] * 2) * S[q] for q in range(9)]) >> 18
            p = sq[max(-2047, min(2047, d)) + 2048]
            y = b[i] >> 7 - j & 1
            if i >= lp:
                # CODER
                while (x1 ^ x2) >> 24 == 0:
                    x1, x2 = x1 << 8 & F, x2 << 8 & F | 255
                    x, k = x << 8 & F | s[k], k + 1
                xm = x1 + (x2 - x1 >> 12) * p
                x1, x2, y = (x1, xm, 1) if x <= xm else (xm + 1, x2, 0)
                # /CODER
            for t in X:
                T[t] += ((y << 16) - T[t]) * R[N[t]] >> 16
                N[t] += N[t] < 30
            g = (y << 12) - p
            for q in range(9):
                w[q], u[q] = w[q] + (S[q] * g >> 10), u[q] + (S[q] * g >> 10)
                v[q] += S[q] * g >> 10
            c0 = c0 + c0 + y
            ml = ml * (b[mp] >> 7 - j & 1 == y)
        b[i] = c0 & 255
    return bytes(b[lp:])
# END DECODER


if __name__ == "__main__":
    src = open(sys.argv[1], "rb").read()
    n = int(sys.argv[2])
    pr = open(sys.argv[4], "rb").read() if len(sys.argv) > 4 else b""
    open(sys.argv[3], "wb").write(decode(src, n, pr))
