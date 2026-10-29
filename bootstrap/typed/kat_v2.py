"""kat_v2.py -- known-answer vectors for the cm2 v2 coder (2026-10-20).

Derives, with typed/cm2_enc.py (v2, the orders read from typed/cm2_dec.py),
the exact x of a few small messages and writes typed/kat_v2.json: for each
vector the primer and the data (hex), n = len(data), and x as hex (big
integer, most significant digit first).  Every vector is checked against the
readable decoder typed/cm2_dec.py before it is written, and the run is
deterministic (asserted: derived twice).  make_typed.py and e2e_pipe.py check
the typed loader's own d against these vectors.
Usage: python kat_v2.py [--check]   (--check: verify the file, write nothing)"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cm2_dec  # noqa: E402
import cm2_enc  # noqa: E402

OUT = os.path.join(HERE, 'kat_v2.json')
ORDERS = cm2_enc.orders_of(os.path.join(HERE, 'cm2_dec.py'))
TEXT = (b"def k(n,t):\n for c in t:n=(n+c)*1000003\n"
        b" return''.join(q[n>>s&31]for s in(15,10,5,0))\n") * 3
VECTORS = [
    ('empty message, empty primer', b'', b''),
    ('one byte, empty primer', b'', b'A'),
    ('a line, empty primer', b'', b'hello, finder\n'),
    ('the same line, primed', b'hello, ', b'hello, finder\n'),
    ('zero bytes (orders share counters)', b'', bytes(40)),
    ('a 3-times repeated text, primed by its first line', TEXT[:40], TEXT),
]


def derive():
    out = []
    for name, primer, data in VECTORS:
        x = cm2_enc.encode_int(data, primer, ORDERS)
        assert cm2_dec.decode(x, len(data), primer) == data, name
        out.append({'name': name, 'primer': primer.hex(), 'data': data.hex(), 'n': len(data),
                    'x': format(x, 'x'), 'x bits': x.bit_length()})
    return {'coder': 'cm2 v2 (rANS), typed/cm2_enc.py + typed/cm2_dec.py',
            'orders': list(ORDERS), 'vectors': out}


def check(kat, dec):
    """Decode every vector with dec(x, n, primer); True when all match."""
    return all(dec(int(v['x'], 16), v['n'], bytes.fromhex(v['primer'])) == bytes.fromhex(v['data'])
               for v in kat['vectors'])


def main():
    k = derive()
    assert derive() == k, 'not deterministic'
    if '--check' in sys.argv:
        old = json.load(open(OUT))
        assert old == k, 'kat_v2.json differs from a fresh derivation'
        print('kat_v2.json: matches a fresh derivation;', len(k['vectors']), 'vectors')
        return
    json.dump(k, open(OUT, 'w'), indent=1)
    print('wrote', OUT, len(k['vectors']), 'vectors, orders', ORDERS)


if __name__ == '__main__':
    main()
