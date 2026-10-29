"""Stage-0 BWT decoder, coder (ii): direct binary CM on the BWT output (no MTF).
usage: python3 dec.py COMPRESSED OUT N [PRIMERFILE ...]"""
import sys
# BEGIN DECODER
# src = 4-byte primary index + carryless range-coder stream; a, z, x, m are
# 32-bit (M); squash Q maps -2048..2047 -> 1..4095; S inverts it; mixer
# weights are 16.16 fixed point; >> on negatives is an arithmetic shift.
def decode(src, n, primer):
    s, M, h = src + bytes(4), (1 << 32) - 1, len(primer)
    g = sorted(primer[i:] for i in range(h))
    g = bytearray(primer[h - len(w) - 1] for w in g) + bytearray(n)
    a, z, x, q = 0, M, int.from_bytes(s[4:8], 'big'), iter(s[8:])
    Q, S, j, P, W = [0] * 4096, [-2048] * 4096, 1 << 31, {}, {}
    for i in range(2048):
        Q[2048 + i], Q[2047 - i] = j >> 20, 4096 - (j >> 20)
        j += j * (M + 1 - j) >> 40
    for i in range(4096):
        S[Q[i]:] = [i - 2048] * (4096 - Q[i])
    b, f, r = 0, 0, 0
    for k in range(h + n):
        c = 1
        for d in range(7, -1, -1):
            e = ((b | 256) >> d + 1 == c) * (1 + (b >> d & 1))
            e = e or ((f | 256) >> d + 1 == c) * (3 + (f >> d & 1))
            K = [c, 1 << 16 | b << 8 | c, 1 << 17 | e << 4 | min(r, 15)]
            C = [P.setdefault(i, [32768, 3]) for i in K]
            T, w = [S[i[0] >> 4] for i in C], W.setdefault(c, [21845] * 3)
            p = sum(w[i] * T[i] for i in range(3)) >> 16
            p = Q[max(min(p, 2047), -2048) + 2048]
            m = a + (z - a >> 12) * p
            y = g[k] >> d & 1 if k < h else int(x <= m)
            a, z = (a, z) if k < h else (a, m) if y else (m + 1, z)
            while (a ^ z) >> 24 == 0:
                a, z, x = a << 8 & M, z << 8 & M | 255, x << 8 & M | next(q)
            for i, v in enumerate(C):
                w[i] += T[i] * ((y << 12) - p) >> 11
                v[0] += (65536 - v[0]) * 2 // v[1] if y else -(v[0] * 2 // v[1])
                v[1] = min(v[1] + 2, (31, 31, 255)[i])
            c = 2 * c + y
        g[k], f, r = c - 256, b if c - 256 != b else f, (r + 1) * (c - 256 == b)
        b = g[k]
    g, o = g[h:], bytearray(n)
    T, i = sorted(range(n), key=lambda j: g[j]), int.from_bytes(s[:4], 'big')
    for k in range(n):
        o[k], i = g[T[i]], T[i]
    return bytes(o)
# END DECODER
if __name__ == '__main__':
    pr = b''.join(open(p, 'rb').read() for p in sys.argv[4:])
    out = decode(open(sys.argv[1], 'rb').read(), int(sys.argv[3]), pr)
    open(sys.argv[2], 'wb').write(out)
