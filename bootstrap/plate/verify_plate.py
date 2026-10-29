"""Independent check of the Plate TEXT (reads only leaf1/2/2b.txt).

Re-derives every printed number from the printed rules and compares; runs
the printed checker listing (as printed on leaf 2) on its own known-answer
lines and on its own 12 lines. Run: python3 verify_plate.py  (exit 0 = all
PASS). Uses a scratch folder from $PLATE_TMP or tempfile.
"""
import os
import re
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def ok(cond, what):
    print(('PASS ' if cond else 'FAIL ') + what)
    if not cond:
        fails.append(what)


def leaf(n):
    return open(os.path.join(HERE, n)).read().split('\n')[:-1]


L1, L2, L3 = leaf('leaf1.txt'), leaf('leaf2.txt'), leaf('leaf2b.txt')
for name, L in (('leaf1', L1), ('leaf2', L2), ('leaf2b', L3)):
    ok(len(L) == 63 and max(map(len, L)) <= 72
       and all(all(32 <= ord(c) < 127 for c in x) for x in L),
       '%s: 63 lines, <= 72 columns, printable ASCII' % name)

# 1. golden block
rows = [x for x in L1 if re.match(r'row [1-8]  ', x)]
ok(len(rows) == 8, 'golden block has 8 rows')
grid, text = [], ''
for r in rows:
    m = re.match(r'row \d  ((?:[#.] ){7}[#.])   ([01]{8})  ([0-9+]+) = (\d+)'
                 r'\s+(.*)$', r)
    bits = [1 if c == '#' else 0 for c in m.group(1).split(' ')]
    v = int(''.join(map(str, bits)), 2)
    w = [128, 64, 32, 16, 8, 4, 2, 1]
    ok(m.group(2) == ''.join(map(str, bits))
       and sum(int(t) for t in m.group(3).split('+')) == v
       and sum(w[k] for k in range(8) if bits[k]) == v == int(m.group(4)),
       'golden %s: marks = binary = sum = %d' % (r[:5], v))
    g = m.group(5)
    text += ' ' if g == '(space)' else g
    ok(chr(v) == (' ' if g == '(space)' else g), 'golden %s letter' % r[:5])
    grid.append(bits)
ok(text == 'Hello 42', 'golden block reads %r' % text)


def rot(g):
    return [list(r) for r in zip(*g[::-1])]


hits = []
for mirror in (0, 1):
    h = [r[::-1] for r in grid] if mirror else grid
    for k in range(4):
        for pol in (0, 1):
            b = bytes(int(''.join(str(x ^ pol) for x in r), 2) for r in h)
            if b == b'Hello 42':
                hits.append((mirror, k, pol))
        h = rot(h)
ok(hits == [(0, 0, 0)], 'of 16 trials only "as printed, ink=1" reads Hello 42')
i = [k for k, x in enumerate(L1) if 'corners as printed' in x][0]
top = L1[i].split('->')[1].split()
bot = L1[i + 1].split()[1:]
pics = set(a + b for a, b in zip(top, bot))
d8 = set()
g = [['a', 'b'], ['c', 'd']]
for mirror in (0, 1):
    h = [r[::-1] for r in g] if mirror else g
    for k in range(4):
        d8.add(''.join(h[0] + h[1]))
        h = rot(h)
ok(len(top) == 8 and pics == d8, 'pictogram = the 8 turns/mirrors of ab/cd')

# 2. CRC by the printed definition alone (no table)
def crc(data):
    r = 0xFFFFFFFF
    for b in data:
        r ^= b
        for _ in range(8):
            r = (r >> 1) ^ 0xEDB88320 if r & 1 else r >> 1
    return r ^ 0xFFFFFFFF


for x in L1:
    for s, h in re.findall(r'"([0-9a-z]*)" -> ([0-9a-f]{8})', x):
        ok(crc(s.encode()) == int(h, 16) == zlib.crc32(s.encode()),
           'vector "%s" -> %s' % (s, h))
    if 'no bytes ->' in x:
        ok(crc(b'') == int(x.split('no bytes -> ')[1][:8], 16), 'vector ""')

# trace on leaf 1
tr = [x for x in L1 if re.match(r'\d:[01] [0-9a-f]{8} [0-9a-f]{8}', x)
      or 'byte 3' in x]
r = 0xFFFFFFFF
steps = []
for b in b'12':
    r ^= b
    steps.append(('in', b, r))
    for k in range(8):
        bit, s = r & 1, r >> 1
        r = s ^ 0xEDB88320 if bit else s
        steps.append((k + 1, bit, s, r))
printed = []
for x in tr:
    m = re.search(r'byte ([0-9a-f]{2}): r XOR [0-9a-f]{2} = ([0-9a-f]{8})', x)
    if m:
        printed.append(('in', int(m.group(1), 16), int(m.group(2), 16)))
    for k, bit, s, rr in re.findall(
            r'(\d):([01]) ([0-9a-f]{8}) ([0-9a-f]{8})', x):
        printed.append((int(k), int(bit), int(s, 16), int(rr, 16)))
ok(printed == steps, 'CRC trace of "12": all %d steps match' % len(steps))
end = [x for x in L1 if x.startswith('end: ')][0]
ok(end.startswith('end: %08x XOR ffffffff = %08x' % (r, r ^ 0xFFFFFFFF))
   and r ^ 0xFFFFFFFF == zlib.crc32(b'12'), 'CRC trace end value')

# 3. key
ki = [k for k, x in enumerate(L1) if x.startswith('THE KEY')][0]
key = L1[ki + 1].split()[0]
m = re.search(r'\((\d+) bytes, CRC-32 ([0-9a-f]{8})\)', L1[ki + 1])
hx = bytes(int(t, 16) for t in
           (L1[ki + 2].split(':')[1] + L1[ki + 3]).split())
ok(hx == key.encode() and int(m.group(1)) == len(hx)
   and crc(hx) == int(m.group(2), 16), 'key %s: hex, length, CRC' % key)

# 4. ASCII table
ai = [k for k, x in enumerate(L2) if x.startswith('LETTERS AS NUMBERS')][0]
seen = {}
for x in L2[ai + 1:ai + 33]:
    for d, gl, mk in re.findall(r'(\d+) (\S+)\s+([#.]{8})', x):
        seen[int(d)] = (gl, mk)
good = len(seen) == 128
for d, (gl, mk) in seen.items():
    v = int(mk.replace('#', '1').replace('.', '0'), 2)
    good &= v == d
    if 33 <= d <= 126:
        good &= gl == chr(d)
ok(good, 'ASCII table: 128 entries, marks = number, glyph = chr')
pi = [k for k, x in enumerate(L2) if 'bytes below have CRC-32' in x][0]
pm = re.search(r'The (\d+) bytes below have CRC-32 ([0-9a-f]{8})', L2[pi])
pg = L2[pi + 1].encode()
ok(len(pg) == int(pm.group(1)) and crc(pg) == int(pm.group(2), 16)
   and len(set(c for c in L2[pi + 1].lower() if c.isalpha())) == 26
   and all(str(n) in L2[pi + 1] for n in range(10)),
   'pangram: 26 letters, 10 digits, length and CRC')

# 5. counting
cnt = 0
for x in L3:
    for d, h, b, dots in re.findall(r'(\d+)   ([0-9a-f]) ([01]{4}) ?(o*)', x):
        cnt += int(d) == int(h, 16) == int(b, 2) == len(dots)
ok(cnt == 16, 'counting rows: dec = hex = bits = dots, 16 of 16')

li = [k for k, x in enumerate(L3) if x.startswith('LENGTH.')][0]
dots = int(re.search(r'(\d+) printer dots at 600', L3[li]).group(1))
mm = re.search(r'= (\d+\.\d+) mm', L3[li + 1]).group(1)
ok('%.3f' % (dots * 25.4 / 600) == mm and L3[li + 2] == '',
   'scale bar: %d dots at 600 dpi = %s mm, bar line empty' % (dots, mm))

# 6. checker, as printed on leaf 2
ci = 4  # listing starts after header + 3 instruction lines... find it
ci = [k for k, x in enumerate(L2) if x.startswith("A = '0123")][0]
ck = L2[ci:ci + 12]
ok(ck[-1].startswith('exec('), 'checker listing is 12 lines')
codes = dict(re.findall(r'(\d+) ([0-9a-v]{3})[,.]',
                        ' '.join(L2[ci + 12:ci + 14])))
A = '0123456789abcdefghijklmnopqrstuv'


def check(n, p):
    c = (n * 1000003 + sum(i * ord(x) for i, x in enumerate(p, 1))) % 32768
    return A[c >> 10] + A[c >> 5 & 31] + A[c & 31]


ok(all(codes.get(str(n)) == check(n, x) for n, x in enumerate(ck, 1)),
   'printed check codes of the 12 checker lines')
tmp = os.environ.get('PLATE_TMP') or tempfile.mkdtemp()


def run(lines):
    d = tempfile.mkdtemp(dir=tmp)
    open(os.path.join(d, 'checker.py'), 'w').write('\n'.join(ck) + '\n')
    p = subprocess.run([sys.executable, '-u', 'checker.py'], cwd=d,
                       input='\n'.join(lines) + '\n', capture_output=True,
                       text=True, timeout=30)
    return p.stdout.split('\n')


o = run(['if 1:~@print(24)~snk', 'if 1:~@print(42)~snk', 'RUN'])
ok(o[:4] == ['OK 1', 'BAD 1', 'OK 2', '42'],
   'known answers: OK 1, BAD 1, OK 2, RUN prints 42 (got %r)' % o[:4])
o = run([x + check(n, x) for n, x in enumerate(ck, 1)])
ok(o[:13] == ['OK %d' % n for n in range(1, 14)],
   'self-test: the checker accepts its own 12 printed lines')
hand = ' '.join(L2[ci + 14:ci + 24])
terms = re.findall(r'(\d+)\*(\d+)=(\d+)(?: \((\d+)\))?', hand)
s, good = 0, len(terms) == 17
for i, (a, o_, prod, run_) in enumerate(terms, 1):
    s += i * ord('if 1:~@print(42)~'[i - 1])
    good &= int(a) == i and int(o_) * i == int(prod)
    good &= (run_ == '' and i == 1) or int(run_ or s) == s
ok(good and s == 12465 and '29428' in hand and check(1, 'if 1:~@print(42)~')
   == 'snk', 'hand-worked check: 17 terms, 12465, 29428, snk')
print('ALL PASS' if not fails else '%d FAIL' % len(fails))
sys.exit(1 if fails else 0)
