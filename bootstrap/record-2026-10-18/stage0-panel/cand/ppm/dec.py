import sys
# BEGIN DECODER
# Stage-0 PPM decoder. Model: contexts = the preceding 6..0 bytes (a dict
# keyed by the bytes); counts new 2, +4; escape weight 2*distinct-1 (none
# at order 0, which starts with all 256 bytes at 1); full exclusion;
# update stops at the first order already holding the byte; counts are
# never rescaled (every total < 2**32 while primer + output < 1 GB).
# Range decoder: x < g < 2**64, g starts at 1; while g < 2**56 shift in
# the next byte of s (so the first decode reads 7 bytes).
def decode(s, n, p):
    o = bytearray(p)
    T = {b'': dict.fromkeys(range(256), 1)}
    x, g, q, i = 0, 1, 0, 0
    while i < len(p) + n:
        k, e = 6, {}
        while i == len(o):
            t = T.get(bytes(o[max(0, i - k):i]), {})
            L = [z for z in t if z not in e] + [-1]
            d = max(2 * len(t) - 1, 1) * (k > 0)
            while g < 1 << 56:
                x, g, q = x << 8 | s[q], g << 8, q + 1
            w, a, j = g // sum([t.get(z, d) for z in L]), 0, 0
            while x >= a + t.get(L[j], d) * w:
                a, j = a + t.get(L[j], d) * w, j + 1
            x, g, k, z = x - a, t.get(L[j], d) * w, k - 1, L[j]
            e.update(t)
            # append z unless it is the escape -1:
            o[i:] = [z] * (z >= 0)
        for k in range(6, -1, -1):
            t = T.setdefault(bytes(o[max(0, i - k):i]), {})
            t[o[i]] = t.get(o[i], -2) + 4
            if t[o[i]] > 2:
                break
        i += 1
    return bytes(o[len(p):])
# END DECODER
if __name__ == '__main__':
    src = open(sys.argv[1], 'rb').read()
    n = int(sys.argv[3])
    pr = b''.join(open(f, 'rb').read() for f in sys.argv[4:])
    open(sys.argv[2], 'wb').write(decode(src, n, pr))
