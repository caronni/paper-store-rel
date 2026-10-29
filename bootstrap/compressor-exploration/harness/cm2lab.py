"""cm2lab: exact mirror of the owner's a.py d() (2026-10-20), parametrized.
Model per bit: for each order o in ORDERS, counter pair c=[n0,n1] keyed by
(h & (256**o-1), u) where h = ALL bytes so far (primer+output) as one int and
u = partial byte with leading 1.  Weights p_y = 1 + sum_w c[y] << (w + boost*(c[1-y] < 1))
(w = index in the tuple).  Update: c[y] += 1; c[1-y] = upd(c[1-y]) (default min(c, c//4+2)).
Coder: big-int rANS, exact: slot o = x % s, y = o >= p0, x = x//s*p_y + o - p0*y.
ideal_bits = sum -log2(p_y/s).  Exact size = x.bit_length().
run(data, primer, **params) -> dict(ideal_bytes, exact_bytes, b32_chars, lines64, secs)
Every param defaults to a.py's value, so run(data, primer) IS a.py's model."""
import math, time

def model(data, primer, orders=(0,1,2,3,4,6,8,12,16), boost=1, upd=None,
          shift=None, init=(0,0), tag=False, prior=1, extra=None):
    """Yields (y, p0, p1) for every DATA bit (primer bits train only).
    upd: f(count_other)->new (default min(c, c//4+2)); shift: f(w)->weight shift (default w);
    extra: optional f(state)->list of additional (c_pair, shift) inputs (for match/word arms)."""
    if upd is None: upd = lambda c: min(c, c // 4 + 2)
    if shift is None: shift = lambda w: w
    z = [256 ** o - 1 for o in orders]
    tg = [256 ** o if tag else 0 for o in orders]
    t, h, m = {}, 0, len(primer)
    buf = bytes(primer) + bytes(data)
    out = []
    for i, byte in enumerate(buf):
        u = 1
        for j in range(8):
            g = [t.setdefault((h & q | tt, u), list(init)) for q, tt in zip(z, tg)]
            p = [prior + sum(c[y] << shift(w) + boost * (c[1 - y] < 1) for w, c in enumerate(g)) for y in (0, 1)]
            y = byte >> 7 - j & 1
            if i >= m:
                out.append((y, p[0], p[1]))
            for c in g:
                c[y], c[1 - y] = c[y] + 1, upd(c[1 - y])
            u = 2 * u + y
        h = h << 8 | byte
    return out

def ideal_bits(trip):
    return sum(-math.log2((p1 if y else p0) / (p0 + p1)) for y, p0, p1 in trip)

def encode_x(trip):
    x = 0
    for y, p0, p1 in reversed(trip):
        py = p1 if y else p0
        x = x // py * (p0 + p1) + (p0 if y else 0) + x % py
    return x

def run(data, primer, exact=True, **params):
    t0 = time.time()
    trip = model(data, primer, **params)
    ib = ideal_bits(trip)
    res = {'ideal_bytes': ib / 8, 'secs': time.time() - t0}
    if exact:
        x = encode_x(trip)
        bits = x.bit_length()
        res.update(exact_bytes=bits / 8, b32_chars=-(-bits // 5), lines60=-(-(-(-bits // 5)) // 60), x=x)
    return res

def decode_ref(x, n, primer, apath='a.py'):
    """The owner's d() verbatim, exec'd from a.py's text (the def block only)."""
    src = open(apath).read()
    body = src[src.index('def d('):src.index('q,n,v=')]
    ns = {}
    exec(body, ns)
    return ns['d'](x, n, primer)

if __name__ == '__main__':
    import sys
    data = open(sys.argv[1], 'rb').read()
    primer = open(sys.argv[2], 'rb').read().strip()
    r = run(data, primer)
    print({k: v for k, v in r.items() if k != 'x'})
    if len(sys.argv) > 3 and sys.argv[3] == 'verify':
        t0 = time.time()
        out = decode_ref(r['x'], len(data), primer)
        print('roundtrip', out == data, 'decode secs', round(time.time() - t0, 2))
