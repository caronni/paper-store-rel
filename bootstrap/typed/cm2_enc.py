"""cm2 v2 encoder: the cm2 count-mixing model with a big-integer rANS coder
(2026-10-20).  Exact mirror of the model in typed/cm2_dec.py (the order
tuple is read from that file).  Two passes:
  1. forward: run the model over primer + data and keep, for every bit of
     the data, the bit y and the two weights (p0, p1);
  2. backward: from x = 0, push the bits in REVERSE order,
       x = x // p_y * s + cum_y + x % p_y,   s = p0 + p1,
       cum_0 = 0, cum_1 = p0  (bit 0 owns the slots [0, p0), bit 1 [p0, s)),
     and output the final x.
The decoder pops them in forward order (slot = x % s; y = slot >= p0;
x = x // s * p_y + slot - cum_y) and ends with x == 0.  No window, no
renormalisation, no probability clamp: x is one Python int, the printed
number itself.
Model (cm2's, unchanged in its counts): for every bit, one counter pair per
order k in the tuple, keyed by (the last k bytes as one integer, the partial
byte u with its leading 1); weights p_y = 1 + sum over the orders (index w)
of count_y << (w + [count_other == 0]); update count_y += 1, count_other =
min(count_other, count_other // 4 + 2).  With tag=True the key adds 256**k,
so the orders never share a counter (with tag=False an order-k key equals an
order-j key while the last k - j bytes are 0, e.g. at the start, and the
shared counter is updated once per order that names it -- mirrored here).
API: model(data, primer, orders, tag) -> [(y, p0, p1)] per data bit;
encode_int(...) -> x; encode(...) -> x as big-endian bytes, minimal length
(the page's container); orders_of(decpath).
Usage: python3 cm2_enc.py DEC.py IN OUT [PRIMER...]   (OUT = x, big-endian)"""
import re
import sys


def orders_of(decpath):
    src = open(decpath).read()
    return tuple(int(v) for v in re.search(r'for o in \(([\d, ]+)\)', src).group(1).split(','))


def model(data, primer, orders, tag=False):
    z = [256 ** o for o in orders]
    top = max(z) * 256
    t, h, m, out = {}, 0, len(primer), []
    buf = bytes(primer) + bytes(data)
    for i, byte in enumerate(buf):
        u = 1
        hs = [h % q + (q if tag else 0) for q in z]
        for j in range(8):
            g = [t.setdefault((c, u), [0, 0]) for c in hs]
            p = [1 + sum(c[y] << w + (c[1 - y] < 1) for w, c in enumerate(g)) for y in (0, 1)]
            y = byte >> 7 - j & 1
            if i >= m:
                out.append((y, p[0], p[1]))
            for c in g:
                c[y], c[1 - y] = c[y] + 1, min(c[1 - y], c[1 - y] // 4 + 2)
            u = 2 * u + y
        h = (h << 8 | byte) % top
    return out


def encode_int(data, primer, orders, tag=False, low=0):
    """low = the bit that owns the low slots [0, p_low): 0 as printed (cum_1 =
    p0), 1 the outside draft's convention (cum_0 = p1)."""
    x = 0
    for y, p0, p1 in reversed(model(data, primer, orders, tag)):
        py = p1 if y else p0
        cum = (p0 if y else 0) if low == 0 else (0 if y else p1)
        x = x // py * (p0 + p1) + cum + x % py
    return x


def encode(data, primer, orders, tag=False, low=0):
    x = encode_int(data, primer, orders, tag, low)
    return x.to_bytes((x.bit_length() + 7) // 8, 'big')


if __name__ == '__main__':
    data = open(sys.argv[2], 'rb').read()
    pr = b''.join(open(f, 'rb').read() for f in sys.argv[4:])
    open(sys.argv[3], 'wb').write(encode(data, pr, orders_of(sys.argv[1])))
