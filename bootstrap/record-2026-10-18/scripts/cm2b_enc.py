"""cm2 encoder with a BOUNDED context map: the exact key is reduced modulo 2^k
(one extra '% M' in the key expression). Measures what bounding costs cm2."""
import sys, resource
def encode(data, primer, orders, k):
    k = k or 64
    ms = [(1 << 8 * o) - 1 for o in orders]
    D, M, t, m = max(orders), 0xFFFFFFFF, {}, len(primer)
    MOD = 1 << k if k else 0
    buf = bytearray(D) + primer + data
    a, b, out = 0, M, bytearray()
    for i in range(m + len(data)):
        c0, h = 1, int.from_bytes(buf[i:i + D], 'big')
        for j in range(8):
            if MOD:
                cs = [t.setdefault((((h & q | q + 1) << 8 | c0) * 0x9E3779B97F4A7C15 & 0xFFFFFFFFFFFFFFFF) >> (64 - k), [0, 0]) for q in ms]
            else:
                cs = [t.setdefault((h & q | q + 1) << 8 | c0, [0, 0]) for q in ms]
            s1 = 1 + sum(c[1] << (c[0] == 0) << w for w, c in enumerate(cs))
            s0 = 1 + sum(c[0] << (c[1] == 0) << w for w, c in enumerate(cs))
            p = s1 * 4094 // (s0 + s1) + 1
            y = buf[D + i] >> 7 - j & 1
            if i >= m:
                xm = a + (b - a >> 12) * p
                if y: b = xm
                else: a = xm + 1
                while a >> 24 == b >> 24:
                    out.append(b >> 24); a, b = a << 8 & M, b << 8 & M | 255
            for c in cs:
                c[y], c[1 - y] = c[y] + 1, min(c[1 - y], c[1 - y] // 4 + 2)
            c0 = c0 * 2 + y
    out.append((a >> 24) + 1)
    return bytes(out), len(t)
if __name__ == "__main__":
    f, k = sys.argv[1], int(sys.argv[2])
    data = open(f, "rb").read()
    z, n = encode(data, b"", (0,1,2,3,4,6,8,12), k)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    print(f"{f.rsplit('/',1)[-1]:16s} k={k:2d}  {len(z):7d} B  dict entries {n:9d}  peak RSS {rss:5d} MB")
