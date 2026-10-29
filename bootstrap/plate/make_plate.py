"""Generator for the Plate (R0): leaf1.txt, leaf2.txt, leaf2b.txt.

Every number printed on the Plate is computed here (CRC by a bitwise
routine, cross-checked against zlib; check codes by the TYPED-STREAM rule,
cross-checked against the checker listing in ../typed/checker.py, which is
read, never edited). Run: python3 make_plate.py  (writes the three leaves
next to this file and asserts 72 columns x 63 lines, ASCII only).
"""
import os
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 72, 63
A32 = '0123456789abcdefghijklmnopqrstuv'
GOLDEN = 'Hello 42'
PANGRAM = 'The quick brown fox jumps over the lazy dog: 0123456789.'
KEY = 'holo/v2/1i300-cmy8-r0700-p120-v1@53x37'
POLY = 0xEDB88320


def crc_bits(data, trace=None):
    r = 0xFFFFFFFF
    for b in data:
        r ^= b
        if trace is not None:
            trace.append(('in', b, r))
        for k in range(8):
            bit = r & 1
            s = r >> 1
            r = s ^ POLY if bit else s
            if trace is not None:
                trace.append(('st', bit, s, r))
    return r ^ 0xFFFFFFFF


def table():
    t = []
    for n in range(256):
        r = n
        for k in range(8):
            r = (r >> 1) ^ POLY if r & 1 else r >> 1
        t.append(r)
    return t


def check(n, payload):
    c = (n * 1000003 + sum(i * ord(x) for i, x in enumerate(payload, 1)))
    c %= 32768
    return A32[c >> 10] + A32[(c >> 5) & 31] + A32[c & 31]


def checker_lines():
    src = open(os.path.join(HERE, '..', 'typed', 'checker.py')).read()
    body = src.split('# BEGIN CHECKER\n', 1)[1].split('# END CHECKER', 1)[0]
    return body.rstrip('\n').split('\n')


CTRL = ('NUL SOH STX ETX EOT ENQ ACK BEL BS HT LF VT FF CR SO SI DLE DC1 '
        'DC2 DC3 DC4 NAK SYN ETB CAN EM SUB ESC FS GS RS US').split()


def glyph(d):
    if d < 32:
        return CTRL[d]
    if d == 32:
        return 'SP'
    if d == 127:
        return 'DEL'
    return chr(d)


def marks(v, nbits=8):
    return ''.join('#' if v >> (nbits - 1 - k) & 1 else '.'
                   for k in range(nbits))


def header(leaf, title):
    n = {'1': 1, '2': 2, '2b': 3}[leaf]
    return ['VOLUME {V}  R0 PLATE %d/3 (LEAF %s)  COPY {C}  %s'
            % (n, leaf, title)]


def proof():
    L = [
        'PROOF: THE 8 x 8 BLOCK (printed beside this text; squares 1.016 mm).',
        'Ink = 1, paper = 0. Rows top to bottom, each row left to right. The',
        'left square counts 128, then 64, 32, 16, 8, 4, 2, 1 (high bit first).',
        '       marks             binary    number                 letter',
    ]
    w = [128, 64, 32, 16, 8, 4, 2, 1]
    for i, ch in enumerate(GOLDEN.encode()):
        m = ' '.join(marks(ch))
        b = format(ch, '08b')
        s = '+'.join(str(w[k]) for k in range(8) if ch >> (7 - k) & 1)
        num = '%s = %d' % (s, ch)
        g = '(space)' if ch == 32 else chr(ch)
        L.append('row %d  %s   %s  %-22s %s' % (i + 1, m, b, num, g))
    L += [
        'These are the letters Hello 42. If you can read them, your method',
        'works. If a camera reads the block wrong, fix the light, not the',
        'program: soft light from the side, no flash (shiny toner looks white).',
        'Lost which way is up, or which is ink? Try 16 ways: these 8, each',
        'with ink = 1 and ink = 0. Only one reads Hello 42.',
        '  corners as printed: ab -> ab  ca  dc  bd    ba  ac  cd  db',
        '                      cd    cd  db  ba  ac    dc  bd  ab  ca',
    ]
    return L


def key():
    kb = KEY.encode()
    return [
        'THE KEY. EXAMPLE ONLY - each real volume prints its own key here:',
        '  %s   (%d bytes, CRC-32 %08x)' % (KEY, len(kb), zlib.crc32(kb)),
        '  hex: ' + ' '.join('%02x' % x for x in kb[:19]),
        '       ' + ' '.join('%02x' % x for x in kb[19:]),
        'For a holo v2 volume this text IS the seed of the dense pages.',
        'Without it they are noise, for ever: that keeps the data private.',
        'It is printed here, on both copies of the Plate, and nowhere else.',
        'This line is the price of privacy. Copy it with every copy of the book.',
    ]


def crc():
    L = [
        'CRC-32: A CHECK NUMBER FOR BYTES. r is a 32-bit number, start r =',
        'ffffffff (hex). For each byte b: r = r XOR b, then 8 times: if r is',
        'odd, r = (r >> 1) XOR edb88320, else r = r >> 1. End: CRC = r XOR',
        'ffffffff. (edb88320 = 04c11db7 with its 32 bits reversed.) CRCs are',
        'stored high byte first. That is all of CRC-32: one shift register.',
        'Every step for the bytes "12" = 31 32 (hex). k:bit = step k and the',
        'low bit of r before it; then r >> 1; then new r (XOR edb88320 if 1).',
    ]
    tr = []
    crc12 = crc_bits(b'12', tr)
    assert crc12 == zlib.crc32(b'12')
    k = 0
    row = []
    first = True
    for e in tr:
        if e[0] == 'in':
            if row:
                L.append('   '.join(row))
                row = []
            pre = 'start r = ffffffff. ' if first else ''
            first = False
            L.append(pre + 'byte %02x: r XOR %02x = %08x' % (e[1], e[1], e[2]))
            k = 0
        else:
            k += 1
            row.append('%d:%d %08x %08x' % (k, e[1], e[2], e[3]))
            if len(row) == 3:
                L.append('   '.join(row))
                row = []
    if row:
        L.append('   '.join(row))
    L.append('end: %08x XOR ffffffff = %08x = CRC-32 of "12".'
             % (crc12 ^ 0xFFFFFFFF, crc12))
    for v in (b'', b'a', b'123456789'):
        assert crc_bits(v) == zlib.crc32(v)
    L.append('More: no bytes -> %08x, "a" -> %08x, "123456789" -> %08x.'
             % (zlib.crc32(b''), zlib.crc32(b'a'), zlib.crc32(b'123456789')))
    return L


def typed():
    return [
        'THE TYPED PAGES. Each typed line is up to 64 characters, then 3 check',
        'characters. c = n * 1000003 + the sum of i * (ASCII number of',
        'character i), i = 1, 2, 3 ... (check characters not counted), n = the',
        'line number. Take c mod 32768; write it as 3 base-32 digits (0-9, then',
        'a-v = 10-31), high digit first. The checker (leaf 2) prints OK n (type',
        'line n) or BAD n (type line n again); it keeps only good lines. RUN',
        'ends the stream. The text is Python: ~ is a new line, @ is 4 spaces of',
        'indent. After it come a line ### and data in base 32 (5 bits per',
        'character, high bit first). At RUN the checker writes the code to a.py',
        'and runs it; that code unpacks the data: the reader of the next pages.',
    ]


def leaf1():
    L = header('1', 'WHAT THIS BOOK IS')
    L += [
        'This book keeps {NBYTES} bytes of digital data on paper. The grey',
        'pages that look like noise ARE the data. These first leaves teach',
        'you to read them, step by step; each step needs only the steps',
        'before it. One hour: read the 8 x 8 block below with a pencil.',
        'One day: type the 12-line checker (leaf 2), then the typed pages.',
        'One week: everything. A piece of a dense page the size of a',
        'fingernail still carries its own address.',
    ]
    return L + proof() + key() + crc() + typed()


def checker():
    ck = checker_lines()
    assert len(ck) == 12
    L = [
        'Type these 12 lines exactly (4 spaces before lines 4-8, 8 before 9)',
        'as checker.py in an empty folder; run python3 checker.py. Rerun it',
        'after a crash: it resumes. TEST: if 1:~@print(24)~snk -> BAD 1, then',
        'if 1:~@print(42)~snk -> OK 2; RUN -> prints 42. Delete s.txt, a.py.',
    ]
    L += ck
    codes = ['%d %s' % (n, check(n, x)) for n, x in enumerate(ck, 1)]
    want = ('1 m59, 2 fbi, 3 r0j, 4 0c6, 5 kkf, 6 rvl, 7 5of, 8 cqn, 9 0kq, '
            '10 tg5, 11 r9o, 12 u5v').split(', ')
    assert codes == want, codes
    L.append('Check codes, over each line as printed (spaces count): '
             + ', '.join(codes[:2]) + ',')
    L.append(', '.join(codes[2:]) + '.')
    assert check(1, 'if 1:~@print(42)~') == 'snk'
    assert check(1, 'if 1:~@print(24)~') == 'snm'
    L += [
    ]
    return L + hand_check()


def hand_check():
    p = 'if 1:~@print(42)~'
    s = 0
    parts = []
    for i, x in enumerate(p, 1):
        s += i * ord(x)
        parts.append('%d*%d=%d' % (i, ord(x), i * ord(x)) +
                     ('' if i == 1 else ' (%d)' % s))
    assert s == 12465
    lines = []
    cur = 'BY HAND, line 1, if 1:~@print(42)~ : i*ord (sum):'
    for q in parts:
        nxt = cur + ' ' + q + ','
        if len(nxt) > 72:
            lines.append(cur)
            cur = q + ','
        else:
            cur = nxt
    lines.append(cur[:-1] + '.')
    assert 1000003 - 30 * 32768 == 16963
    assert 16963 + 12465 == 29428 == 28 * 1024 + 756
    assert 756 == 23 * 32 + 20 and A32[28] + A32[23] + A32[20] == 'snk'
    lines += [
        'n*1000003 = 1000003 = 16963 (mod 32768; hint: 1000003 - 30*32768).',
        '16963 + 12465 = 29428. 29428 = 28*1024 + 756; 756 = 23*32 + 20.',
        'Digits 28, 23, 20 -> s n k. (Swap 42->24: the sum changes by -2.)',
    ]
    return lines


def ascii_table():
    L = ['LETTERS AS NUMBERS (ASCII): number, letter, 8 marks (# = ink = 1)']
    cols = []
    for c in range(4):
        cols.append(['%3d %-3s %s' % (d, glyph(d), marks(d))
                     for d in range(32 * c, 32 * c + 32)])
    for r in range(32):
        L.append('  '.join(cols[c][r] for c in range(4)))
    pb = PANGRAM.encode()
    L += [
        'SP = space, LF = new line. The %d bytes below have CRC-32 %08x:'
        % (len(pb), zlib.crc32(pb)),
        PANGRAM,
    ]
    return L


def leaf2():
    return header('2', 'THE CHECKER') + checker() + ascii_table()


def leaf2b():
    L = header('2b', 'COUNT, R2, CARE')
    L.append('COUNTING. dec = base 10, hex = base 16, bits = base 2, dots = how many')
    L.append(' dec hex bits dots               dec hex bits dots')
    for v in range(8):
        a = '%3d   %x %s %-16s' % (v, v, format(v, '04b'), 'o' * v)
        b = '%3d   %x %s %s' % (v + 8, v + 8, format(v + 8, '04b'),
                               'o' * (v + 8))
        L.append((a + '  ' + b).rstrip())
    L += [
        '42 = 4 tens and 2 = (oooooooooo x 4) + oo. Hex 2a = 2 x 16 + 10 = 42.',
        'LENGTH. The bar under this line is 2362 printer dots at 600 per inch',
        '= 99.991 mm. It defines the mm. Use ratios: paper grows and shrinks.',
        '',
        'THE COARSE PAGES (the next step). A grid of square modules, each 12 x',
        '12 printer dots = 0.508 mm; ink = 1. Each corner has a bullseye of',
        'rings, 13 x 13 modules. Every 17th row and column is a timing line',
        'of ink and paper in turn: the clock and the ink/paper reference.',
        'Between them sit blocks of 16 x 16 modules = 32 bytes, read row by',
        'row, high bit first: 2 bytes chunk number, 26 bytes data, 4 bytes',
        'CRC-32 of the first 28. Each chunk is printed 3 times, in 3 thirds',
        'of the page. Use a block only if its CRC is right.',
        'KEEP THIS BOOK. Dry, dark, cool. No tape, no glue. Copy the whole',
        'book, then check the copy: its 8 x 8 block must still read Hello 42.',
        'The book crosses the centuries as copies, not as one paper. A mirror',
        'image on a page is a ghost from the facing page: read the sharp',
        'original. Brown paper: look with light from the side, light from',
        'behind, or infrared; carbon ink stays black. A page has 4 corner',
        'targets; any 2 are enough.',
    ]
    return L


def emit(name, L):
    bad = []
    for i, x in enumerate(L):
        if len(x) > W:
            bad.append('%s:%d: %d columns' % (name, i + 1, len(x)))
        if not all(32 <= ord(c) < 127 for c in x):
            bad.append('%s:%d: not printable ASCII' % (name, i + 1))
        if x != x.rstrip():
            bad.append('%s:%d: trailing space' % (name, i + 1))
    if len(L) > H:
        bad.append('%s: %d lines > %d' % (name, len(L), H))
    L = L + [''] * (H - len(L))
    with open(os.path.join(HERE, name), 'w') as f:
        f.write('\n'.join(L) + '\n')
    return bad


if __name__ == '__main__':
    assert len(table()) == 256 and table()[1] == 0x77073096
    bad = []
    for n, f in (('leaf1.txt', leaf1), ('leaf2.txt', leaf2),
                 ('leaf2b.txt', leaf2b)):
        body = f()
        print(n, 'content lines', len(body))
        bad += emit(n, body)
    for x in bad:
        print('PROBLEM', x)
    assert not bad
