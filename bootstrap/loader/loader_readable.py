# loader_readable.py -- the readable reference of a.py v3, the program the
# finder types (rulings of 2026-10-19 evening, amended through 2026-10-20:
# the Horner line check, the definitions-then-reader layout, cm2 v2 with a
# big-integer rANS coder).  It behaves exactly like a.py: make_typed.py
# proves it on a known answer, each program run as its own a.py.  Like a.py
# it reads ITS OWN FILE, which must be called a.py, so it runs only when
# saved under that name: `python3 a.py`.
# Typed subset (for a.py): no imports, no floats, no true division (floor
# division is fine), no backslashes, no double quotes, no capital letters,
# builtins only.
#
# Layout: line 1 reads the program's own text; then the SHARED DEFINITIONS
# d, q, k (and the input loop's start values n, v, merged into q's line in
# a.py); then the MAIN part.  The program writes r.py as its shared
# definitions followed by the decoded reader, so the reader may use d, q and
# k and must define none of them (n and v it may rebind).  In a.py the
# definitions are the text from the start of line 2 up to the self-dump line,
# the first line that starts with `for(`, and the slice is two baked numbers,
# a[START:END], fixed by make_typed like N and C; here, in the reference that
# is never typed, they are the text between the two four-equals-sign marker
# lines below, found by searching.
#
# 1. The program's own text, as bytes.  It is the subject of the self-dump
#    (step 6), the cm2 primer (step 8) and the source of r.py's definitions.
#    .strip() drops leading and trailing whitespace, so whether the editor
#    ends the file with a newline cannot matter; reading in text mode turns
#    CRLF into LF, so the editor's line ends cannot matter either.
a = open('a.py').read().strip().encode()

#==== shared definitions (copied into r.py, used by the reader) ====


# 2. d: cm2 v2, the stage-0 decoder (typed/cm2_dec.py is the same decoder
#    with the 10-18 reference's names).  x is the whole coded message as ONE
#    integer -- the number the data lines spell in base 32 -- n the number of
#    bytes to produce, primer the bytes the model learns from first.
#
#    rANS in one paragraph.  For every bit the model gives two positive
#    weights p0 and p1 (s = p0 + p1): the larger p_y, the likelier bit y.
#    The encoder pushed the bits into x in reverse order, from x = 0, each as
#    x = x // p_y * s + cum_y + x % p_y, where bit 0 owns the slots [0, p0)
#    and bit 1 the slots [p0, s) (cum_0 = 0, cum_1 = p0); a bit of
#    probability p_y / s multiplies x by about s / p_y, so it costs about
#    log2(s / p_y) bits of x.  Decoding pops them in forward order: the slot
#    x % s says which bit it is (y = slot >= p0), and x = x // s * p_y + slot
#    - cum_y takes it out again.  x only shrinks, and it is exactly 0 after
#    the last bit.  No window, no renormalisation, no rounding of the
#    weights: Python's integers carry x at its full length.
#
#    The model (cm2's, the same counts as 10-18).  The bytes are produced one
#    bit at a time, most significant first; the primer's bytes go first and
#    only train the model (their bits are read, not decoded).  For every bit
#    and every order o in the tuple, one counter pair [count0, count1], keyed
#    by (the last o bytes as one integer, the bits of the current byte so far
#    behind a leading 1).  p_y = 1 + the sum over the orders (w its index in
#    the tuple, so higher orders weigh more) of count_y << (w + 1 if
#    count_other is 0 else w).  After the bit: count_y += 1, count_other =
#    min(count_other, count_other // 4 + 2).  Two orders whose keys coincide
#    (the last bytes are 0, as at the very start) share one counter pair,
#    which is then updated once for each of them.  h holds the whole history
#    as one integer; h & (256**o - 1) is its last o bytes, a cheap mask.
def d(x, n, primer):
    masks = [256 ** o - 1 for o in (0, 1, 2, 3, 4, 6, 8, 12, 16)]
    m, counts, h = len(primer), {}, 0
    for i in range(m + n):
        partial = 1
        for j in range(8):
            pairs = [counts.setdefault((h & mask, partial), [0, 0]) for mask in masks]
            p = [1 + sum(c[y] << w + (c[1 - y] < 1) for w, c in enumerate(pairs))
                 for y in (0, 1)]
            if i < m:
                y = primer[i] >> 7 - j & 1
            else:
                quotient, slot = divmod(x, p[0] + p[1])
                y = slot >= p[0]
                x = quotient * p[y] + slot - p[0] * y
            for c in pairs:
                c[y], c[1 - y] = c[y] + 1, min(c[1 - y], c[1 - y] // 4 + 2)
            partial = 2 * partial + y
        h = h << 8 | partial & 255
    return h.to_bytes(m + n, 'big')[m:]


# 3. q: the alphabet, base-32 Crockford printed lowercase -- 32 glyphs, no
#    i, l, o, u.  Nothing is folded: the page says a glyph that looks like i
#    or l IS 1, one that looks like o IS 0, one that looks like u IS v.  A
#    twin typed anyway, or a capital, fails the check and the line is
#    retyped.  n, v: the input loop's start values (step 7), merged into
#    this line in a.py, so r.py carries them too; the reader may rebind them.
q = '0123456789abcdefghjkmnpqrstvwxyz'
n, v = 1, 0


# 4. k: the check code of line n with the bytes t (the 10-19 Horner check):
#    seeded with the line number, for each byte add it, then multiply by
#    1000003; the code is bits 0..19 of the result as four glyphs of 5 bits,
#    most significant first.  (The 10-19 form reduced mod 2**20 after every
#    step; the low 20 bits are the same, so the codes are the same.)  n is
#    1, 2, ... for the lines of the listing and the data lines, 0 for the
#    reader's whole text.  One wrong glyph, two glyphs swapped at any
#    distance and the right line at the wrong number never pass (refute5); a
#    random wrong line passes with probability 1/1048576.  (The seed and the
#    first character are multiplied alike: a wrong number n' AND a first
#    character moved by exactly n - n' code points pass together.)
def k(n, t):
    for c in t:
        n = (n + c) * 1000003
    return ''.join(q[n >> s & 31] for s in (15, 10, 5, 0))

#==== main ====


# 5. Print-time constants.  make_typed.py writes the print's values here:
#    N = reader length in bytes, C = data lines, R = the reader's check code.
#    C sits inside the primer, so the encoder iterates it to a fixed point;
#    they belong to ONE print.  (The reader carries one more, the length of
#    the page's decompressed bundle.)
N = 4564
C = 48
R = 'y98y'

# 6. Self-dump: line number and check code of every line of this program as
#    it stands in the file, exactly, to compare with the codes printed in the
#    right margin of the listing before any data is typed.
for i, t in enumerate(a.splitlines(), 1):
    print(i, k(i, t))

# 7. The checked input loop.  The prompt is [n], n the number of the data
#    line expected next; a line whose check fails is not taken and [n] is
#    shown again.  Spaces are removed first: the page prints 12 groups of 5,
#    the finder may type the spaces or not.  Each line: payload glyphs (60,
#    fewer on the last) + 4 check glyphs.  An accepted payload goes straight
#    into the integer v, 5 bits per glyph (n and v start at 1 and 0, step 3):
#    v becomes x, the coder's state, digit by digit.  The loop ends after
#    line C.
while n < C + 1:
    t = input([n]).replace(' ', '')
    if k(n, t[:-4].encode()) == t[-4:]:
        n += 1
        for c in t[:-4]:
            v = v * 32 + q.index(c)

# 8. x = v decoded by cm2 to N bytes with this program's own text as primer.
#    The reader's check code must be R (the reader's text alone, line number
#    0), else the program stops with a traceback before writing anything --
#    a wrong x decodes to other bytes, and x only shrinks, so a wrong number
#    cannot run longer or grow larger than a right one.  Then r.py is
#    written, in binary: the shared definitions (steps 2-4, exactly as they
#    stand in this file), then the reader; its bytes are the primer the
#    reader hands cm2 when it decompresses the page.  Nothing is printed:
#    silence is success.  The finder runs `python3 r.py` next.
r = d(v, N, a)
assert k(0, r) == R
shared = a[a.index(b'#==== shared'):a.index(b'#==== main')]
open('r.py', 'wb').write(shared + r)
