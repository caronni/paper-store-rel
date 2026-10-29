"""cm2 encoder: exact mirror of the model in a dec*.py file (the order tuple
is read from that file, so one encoder serves every variant; the round trip
proves the mirror).  Usage: python3 enc.py DEC.py IN OUT [PRIMER...]
Writes 4-byte big-endian n + coder bytes.  Deterministic, stdlib only."""
import re, sys

def orders_of(decpath):
    src = open(decpath).read()
    return tuple(int(v) for v in re.search(r'for o in \(([\d, ]+)\)', src).group(1).split(','))

def encode(data, primer, orders):
    ms = [(1 << 8 * o) - 1 for o in orders]
    D, M, t, m = max(orders), 0xFFFFFFFF, {}, len(primer)
    buf = bytearray(D) + primer + data
    a, b, out = 0, M, bytearray()
    for i in range(m + len(data)):
        c0, h = 1, int.from_bytes(buf[i:i + D], 'big')
        for j in range(8):
            cs = [t.setdefault((h & q | q + 1) << 8 | c0, [0, 0]) for q in ms]
            s1 = 1 + sum(c[1] << (c[0] == 0) << w for w, c in enumerate(cs))
            s0 = 1 + sum(c[0] << (c[1] == 0) << w for w, c in enumerate(cs))
            p = s1 * 4094 // (s0 + s1) + 1
            y = buf[D + i] >> 7 - j & 1
            if i >= m:
                xm = a + (b - a >> 12) * p
                if y:
                    b = xm
                else:
                    a = xm + 1
                while a >> 24 == b >> 24:
                    out.append(b >> 24)
                    a, b = a << 8 & M, b << 8 & M | 255
            for c in cs:
                c[y], c[1 - y] = c[y] + 1, min(c[1 - y], c[1 - y] // 4 + 2)
            c0 = c0 * 2 + y
    out.append((a >> 24) + 1)
    return bytes(out)

if __name__ == '__main__':
    data = open(sys.argv[2], 'rb').read()
    pr = b''.join(open(f, 'rb').read() for f in sys.argv[4:])
    z = encode(data, pr, orders_of(sys.argv[1]))
    open(sys.argv[3], 'wb').write(len(data).to_bytes(4, 'big') + z)
