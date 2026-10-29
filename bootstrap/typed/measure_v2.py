"""measure_v2.py -- the cm2 v2 (rANS) round's measurements (2026-10-20).

Every variant of the typed loader is a full program text (BASE below with
string edits), packed to its OWN fixed point on the reader payload (the
stand-in reader, N2 13854, primer = the variant's a.py text): the typed total
= a.py characters (newlines not counted) + data.txt characters (60 glyphs +
4 check glyphs per line).  Each packed variant is then decoded by its own d
(exec'd from its text) and must give the reader back: the semantics passed to
the encoder (orders, tag, low) are proved, not assumed.
  P1  the reader payload as above (the loader's typing)
  P2  the page bundle build/w3/payloads/bundle_b.py (38,579 B, a snapshot of
      build/bundle/b.py) with primer build/w3/payloads/page_primer_r.py
      (28,077 B, a snapshot of build/loader/r.py: the v1 loader's
      definitions + the full reader) -- bytes of x, the page's capacity
Measured:
  orders  the order tuple: typed total on P1 and bytes on P2, untagged and
          tagged keys
  coder   v2 against v1 (the 10-18 range coder, typed/cm2_v1_enc.py) on P1
          and P2 with the same orders and primer: bytes, and the worst
          per-bit cost of each (v1 clamps p to [1, 4095]/4096)
  micro   the program's spelling choices, typed totals on P1
  timing  decode wall time of the typed d itself (exec'd from the program),
          P1 and P2, whole-history h % 256**k against masks h & 256**k-1
Usage: python measure_v2.py [orders|orders2|coder|micro|timing|... ...]
         [--reader PATH --n2 N] [--bundle PATH --primer PATH] [--result PATH]
(default sections: orders coder micro timing; default payloads: the stand-in
and the snapshots above; default result typed/measure_v2-result.json).  With
another reader the micro table (the stand-in's) is skipped."""
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
W3 = os.path.join(ROOT, 'build', 'w3')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'loader'))
import cm2_v1_enc as V1       # noqa: E402  the 10-18 range coder, kept for this comparison
import cm2_enc as V2          # noqa: E402  the v2 encoder (model, encode_int)


def _opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


A32 = '0123456789abcdefghjkmnpqrstvwxyz'
N2 = int(_opt('--n2', 13854))
if '--reader' in sys.argv:                  # another reader: --reader PATH --n2 N (no 'e' variant)
    import make_typed as _mt
    import zlib as _z
    READER = {'big': _mt.reader_text(_opt('--reader', None), N2,
                                     _z.crc32(open(_opt('--bundle', ''), 'rb').read()))}
else:                                       # the stand-in, and its spelling with a shared e
    READER = {'big': open(os.path.join(W3, 'stage', 'standin_big.py')).read().replace('N2', str(N2)),
              'e': open(os.path.join(W3, 'stage', 'standin_e.py')).read().replace('N2', str(N2))}
BUNDLE = open(_opt('--bundle', os.path.join(W3, 'payloads', 'bundle_b.py')), 'rb').read()
PAGE_PRIMER = open(_opt('--primer', os.path.join(W3, 'payloads', 'page_primer_r.py')), 'rb').read()
T8 = (0, 1, 2, 3, 4, 6, 8, 12)

BASE = """a=open('a.py').read().strip().encode()
def d(x,n,r):
 z=[256**q for q in(0,1,2,3,4,6,8,12)]
 m,t,h=len(r),{},0
 for i in range(m+n):
  u=1
  for j in range(8):
   g=[t.setdefault((h%q,u),[0,0])for q in z]
   p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
   if i<m:y=r[i]>>7-j&1
   else:f,o=divmod(x,sum(p));y=o>=p[0];x=f*p[y]+o-p[0]*y
   for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
   u=2*u+y
  h=h<<8|u&255
 return h.to_bytes(m+n,'big')[m:]
q,n,v='0123456789abcdefghjkmnpqrstvwxyz',1,0
def k(n,t):
 for c in t:n=(n+c)*1000003
 return''.join(q[n>>s&31]for s in(15,10,5,0))
for(i,t)in enumerate(a.splitlines(),1):print(i,k(i,t))
while n<@C1@:
 t=input([n]).replace(' ','')
 if k(n,t[:-4].encode())==t[-4:]:
  n+=1
  for c in t[:-4]:v=v*32+q.index(c)
r=d(v,@N@,a)
assert k(0,r)=='@R@'
open('r.py','wb').write(a[@D@:@E@]+r)"""
SEM = dict(orders=T8, tag=False, low=0)
ORD_LINE = ' z=[256**q for q in(0,1,2,3,4,6,8,12)]'

# micro-choices: (name, [(old, new)], semantics override, reader key)
DRAFT_DEC = (" if i<m:y=r[i]>>7-j&1\n   else:f,o=divmod(x,sum(p));y=o>=p[0];x=f*p[y]+o-p[0]*y",
             " s=sum(p)\n   y=r[i]>>7-j&1 if i<m else x%s<p[1]\n   if i>=m:x=x//s*p[y]+x%s-p[1]*(not y)")
MICRO = [
    ('base (bytes, divmod, low 0, h%q, untagged, T8)', [], {}, 'big'),
    ("decode lines as drafted (s=sum(p); x%s twice; low 1; (not y))", [DRAFT_DEC], {'low': 1}, 'big'),
    ('x%s once, s=sum(p) line', [(" if i<m:y=r[i]>>7-j&1\n   else:f,o=divmod(x,sum(p));y=o>=p[0];x=f*p[y]+o-p[0]*y",
                                  " s=sum(p)\n   if i<m:y=r[i]>>7-j&1\n   else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y")],
     {}, 'big'),
    ('low 1 with divmod: y=o<p[1], -p[1]*(y<1)',
     [("y=o>=p[0];x=f*p[y]+o-p[0]*y", "y=o<p[1];x=f*p[y]+o-p[1]*(y<1)")], {'low': 1}, 'big'),
    ('masks: 256**q-1 and h&q', [('256**q for', '256**q-1 for'), ('(h%q,u)', '(h&q,u)')], {}, 'big'),
    ('tagged key (h%q+q,u)', [('(h%q,u)', '(h%q+q,u)')], {'tag': True}, 'big'),
    ("k: four explicit terms", [("return''.join(q[n>>s&31]for s in(15,10,5,0))",
                                 'return q[n>>15&31]+q[n>>10&31]+q[n>>5&31]+q[n&31]')], {}, 'big'),
    ("shared e='big' (d uses e; the reader spells e)",
     [("q,n,v='0123", "e,q,n,v='big','0123"), ("h.to_bytes(m+n,'big')", 'h.to_bytes(m+n,e)')], {}, 'e'),
    ('str lines with ord(), text-mode write',
     [("a=open('a.py').read().strip().encode()", "a=open('a.py').read().strip()"),
      ('n=(n+c)*1000003', 'n=(n+ord(c))*1000003'), ('k(n,t[:-4].encode())', 'k(n,t[:-4])'),
      ('r=d(v,@N@,a)', 'r=d(v,@N@,a.encode()).decode()'),
      ("open('r.py','wb')", "open('r.py','w')")], {}, 'big'),
    ('bounded h (last 12 bytes) + an output buffer b',
     [(' m,t,h=len(r),{},0\n', " m,t,h,b=len(r),{},0,b''\n"),
      ('  h=h<<8|u&255\n', '  h=(h<<8|u&255)%z[-1];b+=bytes([u&255])\n'),
      (" return h.to_bytes(m+n,'big')[m:]", ' return b[m:]')], {}, 'big'),
    ('u=1 merged: m,t,h,u=...,1 and h=...;u=1',
     [(' m,t,h=len(r),{},0\n', ' m,t,h,u=len(r),{},0,1\n'), ('  u=1\n', ''),
      ('  h=h<<8|u&255\n', '  h=h<<8|u&255;u=1\n')], {}, 'big'),
]
ORDERS = [(0, 1, 2, 3, 4, 6), T8, (0, 1, 2, 3, 4, 6, 8), (0, 1, 2, 3, 4, 6, 12),
          (0, 1, 2, 3, 4, 5, 6, 8, 12), (0, 1, 2, 3, 4, 6, 8, 12, 16), (0, 1, 2, 3, 4, 6, 8, 16),
          (1, 2, 3, 4, 6, 8, 12), (0, 1, 2, 3, 5, 8, 12), (0, 1, 2, 3, 4, 6, 9, 12),
          (0, 1, 2, 3, 4, 5, 6, 7, 8, 12), (0, 1, 2, 3, 4, 6, 8, 11)]
ORDERS2 = [(0, 1, 2, 3, 4, 6, 8, 12, 16, 24), (0, 1, 2, 3, 4, 6, 8, 12, 16, 20),
           (0, 1, 2, 3, 4, 6, 8, 12, 16, 32), (0, 1, 2, 3, 4, 6, 12, 16), (0, 1, 2, 3, 4, 6, 8, 16, 24),
           (0, 1, 2, 3, 4, 6, 8, 12, 20), (0, 1, 2, 3, 4, 6, 8, 12, 24), (0, 1, 2, 3, 4, 6, 10, 16),
           (0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32), (0, 1, 2, 3, 4, 6, 12, 24), (0, 1, 2, 3, 4, 6, 16),
           (0, 1, 2, 3, 4, 6, 8, 12, 18), (0, 1, 2, 3, 4, 6, 9, 16), (0, 1, 2, 3, 4, 6, 9, 12, 16),
           (0, 1, 2, 3, 4, 6, 8, 12, 16, 22), (0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 40)]


def hcheck(n, t):
    for c in t.encode():
        n = (n + c) * 1000003
    return ''.join(A32[n >> s & 31] for s in (15, 10, 5, 0))


def b32(x):
    out = []
    while x:
        out.append(A32[x & 31])
        x >>= 5
    return ''.join(reversed(out))


def apply(tpl, edits):
    for old, new in edits:
        assert tpl.count(old) == 1, ('edit does not match once', old)
        tpl = tpl.replace(old, new)
    return tpl


def with_orders(tpl, orders):
    return apply(tpl, [(ORD_LINE, ' z=[256**q for q in' + str(orders).replace(' ', '') + ']')])


def pack(tpl, reader, sem):
    raw = reader.encode()
    N, R = len(raw), hcheck(0, reader)

    def build(C):
        p = tpl.replace('@N@', str(N)).replace('@C1@', str(C + 1)).replace('@R@', R)
        return p.replace('@D@', str(p.index('\n') + 1)).replace('@E@', str(p.index('\nfor(') + 1))

    def attempt(C):
        prog = build(C)
        x = V2.encode_int(raw, prog.strip().encode(), sem['orders'], sem['tag'], sem['low'])
        s = b32(x)
        lines = [s[i:i + 60] for i in range(0, len(s), 60)]
        return prog, x, lines

    prog, x, lines = attempt(1)
    best = None
    for C in range(max(1, len(lines) - 1), len(lines) + 2):
        prog, x, lines = attempt(C)
        if len(lines) == C:
            al = prog.split('\n')
            cost = sum(map(len, al)) + sum(len(t) + 4 for t in lines)
            if best is None or cost < best['typed']:
                best = {'typed': cost, 'a.py chars': sum(map(len, al)), 'a.py lines': len(al),
                        'data chars': sum(len(t) + 4 for t in lines), 'data lines': C,
                        'glyphs': len(''.join(lines)), 'x bits': x.bit_length(), 'prog': prog, 'x': x}
    assert best, 'no fixed point'
    ns = {}
    src = best['prog']
    exec(src[src.index('\n') + 1:src.index('\nfor(') + 1], ns)
    t0 = time.time()
    got = ns['d'](best['x'], N, best['prog'].strip().encode())
    best['decode s'] = round(time.time() - t0, 2)
    assert got == raw, 'the variant does not decode its own reader: semantics mismatch'
    del best['x']
    return best


def job_micro(args):
    name, edits, over, rk = args
    sem = dict(SEM, **over)
    r = pack(apply(BASE, edits), READER[rk], sem)
    r.pop('prog')
    return 'micro', name, r


def job_orders(args):
    orders, tag = args
    tpl = with_orders(BASE, orders)
    if tag:
        tpl = apply(tpl, [('(h%q,u)', '(h%q+q,u)')])
    sem = dict(SEM, orders=orders, tag=tag)
    r = pack(tpl, READER['big'], sem)
    r.pop('prog')
    r['page bytes'] = (V2.encode_int(BUNDLE, PAGE_PRIMER, orders, tag).bit_length() + 7) // 8
    return 'orders', f'{orders}{" tagged" if tag else ""}', r


def v1_bits(data, primer, orders):
    """The v1 model's probability of each coded bit (12-bit, clamped), and the
    v1 encoder's actual bytes."""
    ms = [(1 << 8 * o) - 1 for o in orders]
    D, t, m = max(orders), {}, len(primer)
    buf = bytearray(D) + primer + data
    worst, total = 0.0, 0.0
    for i in range(m + len(data)):
        c0, h = 1, int.from_bytes(buf[i:i + D], 'big')
        for j in range(8):
            cs = [t.setdefault((h & q | q + 1) << 8 | c0, [0, 0]) for q in ms]
            s1 = 1 + sum(c[1] << (c[0] == 0) << w for w, c in enumerate(cs))
            s0 = 1 + sum(c[0] << (c[1] == 0) << w for w, c in enumerate(cs))
            p = s1 * 4094 // (s0 + s1) + 1
            y = buf[D + i] >> 7 - j & 1
            if i >= m:
                cost = -math.log2((p if y else 4096 - p) / 4096)
                worst, total = max(worst, cost), total + cost
            for c in cs:
                c[y], c[1 - y] = c[y] + 1, min(c[1 - y], c[1 - y] // 4 + 2)
            c0 = c0 * 2 + y
    return worst, total / 8, len(V1.encode(bytes(data), bytes(primer), orders))


def job_coder(args):
    name, data, primer = args
    out = {}
    for orders in ((0, 1, 2, 3, 4, 6), T8, T8 + (16,)):
        bits = V2.model(data, primer, orders, False)
        costs = [-math.log2((p1 if y else p0) / (p0 + p1)) for y, p0, p1 in bits]
        x = V2.encode_int(data, primer, orders, False)
        bitsT = V2.model(data, primer, orders, True)
        xT = V2.encode_int(data, primer, orders, True)
        w1, ent1, by1 = v1_bits(data, primer, orders)
        out[str(orders)] = {
            'v2 bytes (untagged)': (x.bit_length() + 7) // 8,
            'v2 model entropy bytes': round(sum(costs) / 8, 1),
            'v2 worst bit cost (bits)': round(max(costs), 2),
            'v2 bits costing > 12': sum(c > 12 for c in costs),
            'v2 bytes (tagged)': (xT.bit_length() + 7) // 8,
            'v2 tagged worst bit cost': round(max(-math.log2((p1 if y else p0) / (p0 + p1))
                                                  for y, p0, p1 in bitsT), 2),
            'v1 bytes (range coder, 12-bit clamp)': by1,
            'v1 model entropy bytes': round(ent1, 1),
            'v1 worst bit cost (bits)': round(w1, 2)}
    return 'coder', name, out


MASKS = [('256**q for', '256**q-1 for'), ('(h%q,u)', '(h&q,u)')]
SLINE = [(" if i<m:y=r[i]>>7-j&1\n   else:f,o=divmod(x,sum(p));y=o>=p[0];x=f*p[y]+o-p[0]*y",
          " s=sum(p)\n   if i<m:y=r[i]>>7-j&1\n   else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y")]
TIMING_D = {
    'whole-history h, h%q, divmod (base)': BASE,
    'whole-history h, masks h&q, divmod': apply(BASE, MASKS),
    'whole-history h, masks h&q, x%s and x//s': apply(BASE, MASKS + SLINE),
    'bounded h (last 12 bytes) + output buffer, h%q, divmod': apply(BASE, [
        (' m,t,h=len(r),{},0\n', " m,t,h,b=len(r),{},0,b''\n"),
        ('  h=h<<8|u&255\n', '  h=(h<<8|u&255)%z[-1];b+=bytes([u&255])\n'),
        (" return h.to_bytes(m+n,'big')[m:]", ' return b[m:]')]),
}


def job_timing(args):
    name, payload = args
    tpl = TIMING_D[name]
    if payload == 'P1':
        r = pack(tpl, READER['big'], SEM)
        return 'timing', f'{name} | P1 reader {len(READER["big"])} B', {'decode s': r['decode s']}
    x = V2.encode_int(BUNDLE, PAGE_PRIMER, T8)
    ns = {}
    exec(tpl[tpl.index('\n') + 1:tpl.index('\nfor(') + 1], ns)
    t0 = time.time()
    got = ns['d'](x, len(BUNDLE), PAGE_PRIMER)
    dt = time.time() - t0
    assert got == BUNDLE
    return 'timing', f'{name} | P2 bundle {len(BUNDLE)} B, primer {len(PAGE_PRIMER)} B', \
        {'decode s': round(dt, 1)}


def job_v1_timing(_):
    import cm2_v1_dec as D1
    z = V1.encode(BUNDLE, PAGE_PRIMER, T8)
    t0 = time.time()
    assert D1.decode(z, len(BUNDLE), PAGE_PRIMER) == BUNDLE
    return 'timing', f'v1 range coder (typed/cm2_v1_dec.py) | P2 bundle', \
        {'decode s': round(time.time() - t0, 1)}


SECTIONS = ('orders', 'orders2', 'coder', 'micro', 'timing', 'timing-bounded', 'micro-bounded')
RESULT = _opt('--result', os.path.join(HERE, 'measure_v2-result.json'))


def main():
    want = [a for a in sys.argv[1:] if a in SECTIONS] or ['orders', 'coder', 'micro', 'timing']
    if 'micro' in want and 'e' not in READER:
        want.remove('micro')                # the micro table is the stand-in's (it has an e spelling)
    jobs = []
    if 'micro' in want:
        jobs += [(job_micro, m) for m in MICRO]
    if 'orders' in want:
        jobs += [(job_orders, (o, tag)) for o in ORDERS for tag in (False, True)]
    if 'orders2' in want:
        jobs += [(job_orders, (o, False)) for o in ORDERS2]
    if 'coder' in want:
        jobs += [(job_coder, ('P1 reader (primer = the base a.py)',
                              READER['big'].encode(), BASE.encode())),
                 (job_coder, ('P2 bundle (primer = page r.py)', BUNDLE, PAGE_PRIMER))]
    if 'timing' in want:
        jobs += [(job_timing, (n, p)) for n in TIMING_D for p in ('P1', 'P2')]
        jobs += [(job_v1_timing, None)]
    if 'timing-bounded' in want:
        jobs += [(job_timing, (n, p)) for n in TIMING_D if n.startswith('bounded')
                 for p in ('P1', 'P2')]
    if 'micro-bounded' in want:
        jobs += [(job_micro, m) for m in MICRO if m[0].startswith('bounded')]
    path = RESULT
    res = json.load(open(path)) if os.path.exists(path) else {}
    t0 = time.time()
    with ProcessPoolExecutor(8) as pool:
        futs = [pool.submit(f, a) for f, a in jobs]
        for fu in futs:
            sec, name, r = fu.result()
            res.setdefault(sec, {})[name] = r
            print(sec, '|', name, '|', json.dumps(r), flush=True)
    res['wall s (last run)'] = round(time.time() - t0, 1)
    json.dump(res, open(path, 'w'), indent=1)


if __name__ == '__main__':
    main()
