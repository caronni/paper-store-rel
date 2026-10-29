"""Encoder for dec.py (BWT + direct binary CM on the BWT output; unconstrained,
mirrors dec.py's model bit for bit). usage: python3 enc.py IN OUT [PRIMERFILE ...]"""
import sys


def bwt(s):
    """Rotation BWT by prefix doubling over cyclic ranks -> (last column, primary index)."""
    n = len(s)
    if n == 0:
        return b'', 0
    rank = list(s)
    sa = sorted(range(n), key=rank.__getitem__)
    k = 1
    while k < n:
        key = [rank[i] * (n + 257) + rank[(i + k) % n] for i in range(n)]
        sa.sort(key=key.__getitem__)
        new = [0] * n
        r = 0
        prev = key[sa[0]]
        for i in sa:
            if key[i] != prev:
                r += 1
                prev = key[i]
            new[i] = r
        rank = new
        if r == n - 1:
            break
        k *= 2
    return bytes(s[(i - 1) % n] for i in sa), sa.index(0)


def primer_bwt(primer):
    h = len(primer)
    return bytes(primer[h - len(w) - 1] for w in sorted(primer[i:] for i in range(h)))


def tables():
    M = (1 << 32) - 1
    Q, S, j = [0] * 4096, [-2048] * 4096, 1 << 31
    for i in range(2048):
        Q[2048 + i], Q[2047 - i] = j >> 20, 4096 - (j >> 20)
        j += j * (M + 1 - j) >> 40
    for i in range(4096):
        S[Q[i]:] = [i - 2048] * (4096 - Q[i])
    return Q, S


def encode(data, primer=b''):
    L, idx = bwt(data)
    h, n = len(primer), len(data)
    g = primer_bwt(primer) + L
    M = (1 << 32) - 1
    out = bytearray(idx.to_bytes(4, 'big'))
    a, z = 0, M
    Q, S = tables()
    P, W, b, f, r = {}, {}, 0, 0, 0
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
            y = g[k] >> d & 1
            if k >= h:
                m = a + (z - a >> 12) * p
                a, z = (a, m) if y else (m + 1, z)
                while (a ^ z) >> 24 == 0:
                    out.append(z >> 24)
                    a, z = a << 8 & M, z << 8 & M | 255
            for i, v in enumerate(C):
                w[i] += T[i] * ((y << 12) - p) >> 11
                v[0] += (65536 - v[0]) * 2 // v[1] if y else -(v[0] * 2 // v[1])
                v[1] = min(v[1] + 2, (31, 31, 255)[i])
            c = 2 * c + y
        f, r = b if c - 256 != b else f, (r + 1) * (c - 256 == b)
        b = c - 256
    out.append((a >> 24) + 1)
    return bytes(out)


if __name__ == '__main__':
    pr = b''.join(open(p, 'rb').read() for p in sys.argv[3:])
    open(sys.argv[2], 'wb').write(encode(open(sys.argv[1], 'rb').read(), pr))
