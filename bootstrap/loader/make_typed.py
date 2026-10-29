"""make_typed.py v3 -- OUR side of the typed rung (unconstrained, never typed).

Shape (rulings of 2026-10-19 evening, amended through 2026-10-20): the finder
types the listing into a file a.py and runs `python3 a.py`; the program reads
its own text, prints a self-dump (line number + 4-glyph code per line), takes
the data lines at the prompt [n], decodes the reader with cm2 (primer = its
own text), checks it against the printed reader code and writes r.py -- and
prints nothing more: silence is success, a traceback is failure.  The finder
then runs `python3 r.py` in its own process.

v3 (2026-10-20 night, cm2 v2): the coder is a big-integer rANS decoder over
cm2's count model (typed/cm2_dec.py is its readable reference, cm2_enc.py
the encoder; the 10-18 range coder is kept as cm2_v1_*).  The typed number
IS the coder state x: the data lines are x's base-32 digits, no length, no
padding, no S.  The fixed point is on C alone (the loop bound sits in the
primer): G = the digits of x, C = ceil(G / 60).
  - The line check stays the 10-19 Horner check: k(n, t) over the BYTES of
    t, n = (n + c) * 1000003 (unbounded: the low 20 bits are the 10-19
    value), four glyphs q[n>>15&31] .. q[n&31]; n is the 1-based line number
    for listing and data lines, 0 for the reader's whole text.
  - The program is line 1 (its own text, as bytes), the SHARED DEFINITIONS
    (d = the cm2 v2 decoder; `q,n,v=<alphabet>,1,0`: the alphabet and the
    data loop's start values; k = the check), then the MAIN part, whose
    first line is the self-dump `for(i,t)in ...`.  r.py = a[START:END] + the
    reader, both baked numbers (END depends only on the definitions, which
    the fixed point does not touch: asserted), written in binary: its bytes
    are the page's primer and the reader reads them with open('r.py','rb').
    The reader may use d, q, k and must define none of them (n, v come along
    and may be rebound); there is no e: d spells 'big' once.
  - The order tuple is read from typed/cm2_dec.py, one source for the typed
    d, the readable d, the encoder and the KAT vectors.
  - The reader text: the region between '# BEGIN READER' / '# END READER'
    if present (else the whole file), minus every block of lines from
    '#--- shared with the loader (not typed) ---' to '#--- end shared ---',
    with every NAME token N2 replaced by the decompressed bundle length
    (--n2 BYTES or --bundle PATH), BEFORE the fixed point.

The typed form is HAND-MINIFIED: TYPED below is carried as text, not derived
from loader_readable.py by a minifier.  Equivalence is proved here, every run:
  (1) unit: the typed d() against the readable d() and typed/cm2_dec.py, on
      random messages encoded by typed/cm2_enc.py and on the KAT vectors of
      typed/kat_v2.json; the typed k() against the readable k() and the
      ruling's formula spelled out; the linear census mod 2**20: no single
      substitution, no ASCII transposition (any distance) and no wrong line
      number passes the check for lines up to 72 glyphs;
  (2) whole program: both programs instantiated for a known answer that
      calls d, q and k, each with its OWN fixed point, each run as its own
      a.py in a temp dir with injected data on stdin (a refused typo, a
      doubled line, a line typed with its group spaces, a trailing space):
      transcript as predicted, exit 0, empty stderr, r.py == the program's
      own definitions + the known answer; then r.py run on its own prints
      the expected line; a wrong reader code fires the assert, no r.py.
Then the print: the C fixed point for the real reader, base-32 data lines
with Horner checks, and the files (written to OUT, default bootstrap/build/loader/)
  a.py       the listing the finder types -- the file itself, exactly
  data.txt   the C data lines, one per line, no spaces, nothing else
  codes.txt  printed in the listing's right margin, never typed: line
             number + code of every line of a.py, then the counts
  r.py       what a.py writes: definitions + reader, byte for byte -- the
             primer the page's compression must use
and the print's constants are written into loader_readable.py's main part;
a.py, data.txt and codes.txt are copied into loader/ as the print of record.
Regeneration is byte-identical (asserted: the files are built twice).
The reader's tokens: N2 (the bundle's length) and B2 (the bundle's CRC-32,
decimal) are replaced as NAME tokens before the fixed point; a reader
without B2 is refused, and so is B2 without --bundle (its tail must decode,
assert its CRC-32 of the result == B2, and only then write b.py).
Usage: python make_typed.py [--reader PATH] [--n2 BYTES | --bundle PATH] [--out DIR]
                            [--no-record]   (OUT only: a.py etc. not copied into loader/)
"""
import ast
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import tokenize
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'typed'))
import cm2_enc  # noqa: E402  (v2: model, encode_int)

DEC = os.path.join(ROOT, 'typed', 'cm2_dec.py')
KATS = os.path.join(ROOT, 'typed', 'kat_v2.json')
READER = os.path.join(ROOT, 'r2reader', 'reader_lite.py')   # STAND-IN until the diet reader exists
OUT = os.path.join(ROOT, 'build', 'loader')
READABLE = os.path.join(HERE, 'loader_readable.py')
ORDERS = cm2_enc.orders_of(DEC)
A32 = '0123456789abcdefghjkmnpqrstvwxyz'          # Crockford, lowercase
PAYLOAD = 60
CHECK = 4
MOD = 1 << 20
MAXLINE = 72
SHARED = ('d', 'q', 'k')                         # the definitions r.py hands the reader
CARRIED = ('n', 'v')                             # also bound there (merged), not reserved
MAIN = 'for('                                    # the first line starting with it = the main part
SHARED_BEGIN = '#--- shared with the loader (not typed) ---'
SHARED_END = '#--- end shared ---'
READABLE_BEGIN = '#==== shared definitions'      # loader_readable.py's own markers
READABLE_MAIN = '#==== main'

# The typed program.  @N@ reader bytes, @C1@ data lines + 1, @R@ the reader's
# check code, @D@ the offset of line 2 (len(line 1) + 1), @E@ = END, the
# offset of the main part's first line (both baked: they precede every
# print-time constant, so no fixed point can move them), @O@ the order tuple
# of typed/cm2_dec.py; everything else is literal.  One space per indent
# level.  Names: d = cm2 v2 (x the state, r primer, z masks, t counters, h
# history, u partial byte, g the counter pairs, p the weights, s their sum,
# o the slot), q alphabet, k check, n line expected, v the integer, r the
# reader.  The measured spelling choices: typed/measure_v2-result.json.
TYPED = """a=open('a.py').read().strip().encode()
def d(x,n,r):
 z=[256**q-1 for q in@O@]
 m,t,h=len(r),{},0
 for i in range(m+n):
  u=1
  for j in range(8):
   g=[t.setdefault((h&q,u),[0,0])for q in z]
   p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
   s=sum(p)
   if i<m:y=r[i]>>7-j&1
   else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y
   for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
   u=2*u+y
  h=h<<8|u&255
 return h.to_bytes(m+n,'big')[m:]
q,n,v='@A@',1,0
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
open('r.py','wb').write(a[@D@:@E@]+r)""".replace('@A@', A32).replace('@O@', str(ORDERS).replace(' ', ''))
START = TYPED.index('\n') + 1
END = TYPED.index('\n' + MAIN) + 1
assert '@' not in TYPED[:END]                    # no placeholder before END
TYPED = TYPED.replace('@D@', str(START)).replace('@E@', str(END))


def typed(N, C, R):
    prog = TYPED.replace('@N@', str(N)).replace('@C1@', str(C + 1)).replace('@R@', R)
    assert prog[:END] == TYPED[:END] and prog.index('\n' + MAIN) + 1 == END   # END is fixed
    return prog


def typed_defs(prog):
    """The definitions part of the typed program, a[START:END]: exactly the
    lines from 2 up to the line before the first line starting with 'for('."""
    lines = prog.split('\n')
    m = next(i for i, t in enumerate(lines) if t.startswith(MAIN))
    assert prog[START:END] == ''.join(t + '\n' for t in lines[1:m])
    return prog[START:END]


def readable_defs(prog):
    return prog[prog.index(READABLE_BEGIN):prog.index(READABLE_MAIN)]


def readable(N, C, R, src=None):
    src = open(READABLE).read() if src is None else src
    assert f'for o in {ORDERS}' in src, 'loader_readable.py carries another order tuple'
    for name, val in (('N', N), ('C', C), ('R', repr(R))):
        src, n = re.subn(rf'(?m)^{name} = .*$', f'{name} = {val}', src)
        assert n == 1, name
    return src


def region(path, begin, end):
    s = open(path).read()
    if begin + '\n' not in s:
        return s          # a file that IS the region (reader_lite.py)
    return s.split(begin + '\n', 1)[1].split(end, 1)[0]


def drop_shared(s):
    """Remove every block of lines SHARED_BEGIN .. SHARED_END (inclusive):
    the shared definitions a standalone reader carries.  A marker-less file
    is returned unchanged; a marker that is not an exact line is refused."""
    lines = s.splitlines(keepends=True)
    out, inside = [], False
    for t in lines:
        bare = t.rstrip('\r\n')
        if bare == SHARED_BEGIN:
            assert not inside, 'nested shared region'
            inside = True
        elif bare == SHARED_END:
            assert inside, 'end of a shared region that never began'
            inside = False
        elif '#--- shared' in bare or '#--- end shared' in bare:
            raise AssertionError(f'shared-region marker that is not an exact line: {bare!r}')
        elif not inside:
            out.append(t)
    assert not inside, 'shared region never ends'
    return ''.join(out)


def put_token(s, name, value):
    """Replace every NAME token `name` by the decimal value (strings and
    comments are not touched); returns (text, how many were replaced)."""
    toks = [t for t in tokenize.generate_tokens(io.StringIO(s).readline)
            if t.type == tokenize.NAME and t.string == name]
    if not toks:
        return s, 0
    lines = s.splitlines(keepends=True)
    for t in reversed(toks):
        (row, c0), (_, c1) = t.start, t.end
        lines[row - 1] = lines[row - 1][:c0] + str(value) + lines[row - 1][c1:]
    out = ''.join(lines)
    assert not [t for t in tokenize.generate_tokens(io.StringIO(out).readline)
                if t.type == tokenize.NAME and t.string == name]
    return out, len(toks)


def put_tokens(s, n2, b2):
    """The reader's two baked tokens (rulings of 2026-10-20): N2 = the
    decompressed bundle's length, B2 = the bundle's CRC-32 (decimal), which
    the reader's tail asserts on what it decoded before it writes b.py.  A
    reader with N2 needs --n2 or --bundle, one without takes neither; a
    reader without B2 is refused, and so is B2 without --bundle."""
    if n2 is not None:
        s, k = put_token(s, 'N2', n2)
        assert k, '--n2/--bundle given but the reader has no N2 token'
    else:
        assert not put_token(s, 'N2', 0)[1], \
            'the reader carries the token N2: give --n2 BYTES or --bundle PATH'
    assert put_token(s, 'B2', 0)[1], \
        'the reader has no B2 token: its tail must assert its CRC-32 of b.py == B2'
    assert b2 is not None, 'the reader carries the token B2: give --bundle PATH (B2 is its CRC-32)'
    return put_token(s, 'B2', b2)[0]


def bundle_crc(path):
    return zlib.crc32(open(path, 'rb').read())


def reader_text(path, n2, b2):
    return put_tokens(drop_shared(region(path, '# BEGIN READER', '# END READER')), n2, b2)


K = 1000003


def check(n, t):
    """Horner, multiply after the add (ruling 5 of 2026-10-19), over the
    characters of t (ASCII: the same as over its bytes)."""
    for c in t:
        n = (n + ord(c)) * K % MOD
    return ''.join(A32[n >> sh & 31] for sh in (15, 10, 5, 0))


def b32(x):
    """The base-32 digits of the integer x, most significant first."""
    out = []
    while x:
        out.append(A32[x & 31])
        x >>= 5
    return ''.join(reversed(out))


def primer_of(prog):
    """What the finder's a.py hands the program: the file text, stripped."""
    return prog.strip().encode()


def pack(text, build):
    """Fixed point of C (data lines), which sits inside the primer as the loop
    bound: x = encode(reader, primer = the program for C), G = x's base-32
    digits, and C must equal ceil(G / 60).  build(N, C, R) -> program text.
    Returns (program, C, data lines, x)."""
    raw = text.encode()
    N, R = len(raw), check(0, text)

    def attempt(C):
        prog = build(N, C, R)
        x = cm2_enc.encode_int(raw, primer_of(prog), ORDERS)
        s = b32(x)
        lines = [s[i:i + PAYLOAD] for i in range(0, len(s), PAYLOAD)]
        if len(lines) != C:
            return None, len(lines)
        return (prog, C, [t + check(n, t) for n, t in enumerate(lines, 1)], x), len(lines)

    _, c0 = attempt(1)
    best = None
    for C in range(max(1, c0 - 1), c0 + 2):
        got, _ = attempt(C)
        if got and (best is None or cost(got) < cost(best)):
            best = got
    assert best, 'no C fixed point near the estimate'
    return best


def cost(packed):
    prog, _, dl, _ = packed
    return len(prog.strip()) + sum(map(len, dl))


def names_of(tree):
    out = set()
    for x in ast.walk(tree):
        if isinstance(x, ast.Name):
            out.add(x.id)
        elif isinstance(x, ast.arg):
            out.add(x.arg)
        elif isinstance(x, ast.FunctionDef):
            out.add(x.name)
    return out


SCOPES = (ast.FunctionDef, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp,
          ast.GeneratorExp)


def module_bindings(src):
    """Names bound in the module scope of src."""
    out, todo = set(), list(ast.parse(src).body)
    while todo:
        x = todo.pop()
        if isinstance(x, ast.FunctionDef):
            out.add(x.name)
            continue
        if isinstance(x, SCOPES):
            continue
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
            out.add(x.id)
        todo.extend(ast.iter_child_nodes(x))
    return out


def audit(a):
    """The typed-subset rules for the typed program (rulings 5, 7, 8, 9, 11 of
    2026-10-19; the layout rulings of 2026-10-20)."""
    tree = ast.parse(a)
    bad = []
    for x in ast.walk(tree):
        if isinstance(x, (ast.Import, ast.ImportFrom)):
            bad.append('import')
        if isinstance(x, ast.Constant) and isinstance(x.value, (float, complex)):
            bad.append('float literal')
        if isinstance(x, ast.BinOp) and isinstance(x.op, ast.Div):
            bad.append('true division')
        if isinstance(x, ast.Name) and x.id in ('exec', 'eval', 'compile'):
            bad.append(x.id)
    if 'l' in names_of(tree):
        bad.append('identifier l')
    if any(c.isupper() for c in a):
        bad.append('capital letter')
    if '\\' in a or '"' in a or '\t' in a:
        bad.append('backslash, double quote or tab')
    calls = [x.func.id for x in ast.walk(tree)
             if isinstance(x, ast.Call) and isinstance(x.func, ast.Name)]
    if calls.count('print') != 1:
        bad.append('a print beside the self-dump')
    lines = a.split('\n')
    if not (lines[-2].startswith('assert ') and lines[-1].startswith("open('r.py','wb').write(")):
        bad.append('program does not end with the assert and the write')
    start = a.index('\n') + 1
    main = a.index('\n' + MAIN) + 1 if '\n' + MAIN in a else -1
    if main < 0:
        bad.append(f'no line starts with {MAIN!r}')
    else:
        if module_bindings(a[start:main]) != set(SHARED) | set(CARRIED):
            bad.append(f'definitions bind {sorted(module_bindings(a[start:main]))}, '
                       f'not {SHARED} + {CARRIED}')
        if not a[start:main].startswith('def d('):
            bad.append('line 2 is not def d(')
        if f'a[{start}:{main}]' not in a:
            bad.append(f'the r.py slice is not a[{start}:{main}] (line 2 .. the main part)')
        if 'index(' in lines[-1]:
            bad.append('the r.py slice searches the text')
    for tok in tokenize.generate_tokens(io.StringIO(a).readline):
        if tok.type == tokenize.NUMBER and not tok.string.isdigit():
            bad.append(f'non-plain numeric literal {tok.string}')
        if tok.type == tokenize.OP and tok.string in ('/', '/='):
            bad.append('/')
    for i, t in enumerate(lines, 1):
        if len(t) > MAXLINE:
            bad.append(f'line {i} longer than {MAXLINE}')
        if t != t.rstrip():
            bad.append(f'trailing space on line {i}')
        for mt in re.finditer('l', t):
            j = mt.start()
            if not (j > 0 and t[j - 1].isalpha() or j + 1 < len(t) and t[j + 1].isalpha()):
                bad.append(f'lone l on line {i}')
    return bad


def defs(src):
    """The module-level functions and constant assignments of a program,
    without running its other top-level statements (which read a.py and the
    keyboard)."""
    def const(v):
        return isinstance(v, ast.Constant) or (
            isinstance(v, ast.Tuple) and all(isinstance(e, ast.Constant) for e in v.elts))
    tree = ast.parse(src)
    keep = [x for x in tree.body if isinstance(x, ast.FunctionDef) or (
        isinstance(x, ast.Assign) and const(x.value))]
    ns = {}
    exec(compile(ast.Module(keep, []), '<defs>', 'exec'), ns)
    return ns


def linear_census(maxlen=MAXLINE):
    """Horner is linear mod 2**20: the check of line n with text t (length L)
    is n*K^L + sum ord(t_j)*K^(L-j), j = 0..L-1.  A substitution of
    difference delta at exponent x (1..L) changes it by delta*K^x, a
    transposition of two characters delta apart at exponents x1 < x2 by
    delta*(K^x1 - K^x2), a wrong line number m by (m-n)*K^L.  K is odd, so
    K^x is a unit: a single substitution or a wrong line number passes only
    if 2**20 divides the difference -- never for differences below 2**20.
    Enumerated: substitution and line-number differences 1..255 at every
    exponent 0..maxlen, transpositions of ASCII characters (differences
    1..127) at every pair of exponents 1..maxlen.  Returns (single
    substitutions or wrong line numbers passing, transpositions passing,
    patterns tried)."""
    assert K % 2 == 1
    P = [pow(K, x, MOD) for x in range(maxlen + 1)]
    single = sum(dl * P[x] % MOD == 0 for dl in range(1, 256) for x in range(maxlen + 1))
    swaps = sum(dl * (P[x1] - P[x2]) % MOD == 0 for dl in range(1, 128)
                for x1 in range(1, maxlen + 1) for x2 in range(x1 + 1, maxlen + 1))
    tried = 255 * (maxlen + 1) + 127 * maxlen * (maxlen - 1) // 2
    return single, swaps, tried


def kat_vectors():
    kat = json.load(open(KATS))
    assert tuple(kat['orders']) == ORDERS, 'typed/kat_v2.json is for another order tuple'
    return [(int(v['x'], 16), v['n'], bytes.fromhex(v['primer']), bytes.fromhex(v['data']))
            for v in kat['vectors']]


def prove_units(typed_src, readable_src):
    ty, rd = defs(typed_src), defs(readable_src)
    ref = {}
    exec(region(DEC, '# BEGIN DECODER', '# END DECODER'), ref)
    rng = random.Random(20261020)
    for trial in range(40):
        n = rng.randrange(0, 600)
        data = bytes(rng.choice(b'abcdefgh \n()=:01') if trial % 2 else rng.randrange(256)
                     for _ in range(n))
        pr = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 300)))
        x = cm2_enc.encode_int(data, pr, ORDERS)
        outs = (ref['decode'](x, n, pr), ty['d'](x, n, pr), rd['d'](x, n, pr))
        assert outs[0] == outs[1] == outs[2] == data, ('decoders differ', trial)
    for x, n, pr, data in kat_vectors():
        assert ty['d'](x, n, pr) == rd['d'](x, n, pr) == ref['decode'](x, n, pr) == data, 'KAT'
    for trial in range(5000):
        n = rng.randrange(0, MOD)              # a seed is a line number (0: the reader's text)
        t = ''.join(chr(rng.randrange(32, 127)) for _ in range(rng.randrange(0, 80)))
        want = n
        for c in t:                            # the ruling's formula, spelled out
            want = (want + ord(c)) * 1000003 % 1048576
        want = A32[want >> 15] + A32[want >> 10 & 31] + A32[want >> 5 & 31] + A32[want & 31]
        b = t.encode()
        assert ty['k'](n, b) == rd['k'](n, b) == check(n, t) == want, ('checks differ', n, t)
    single, swaps, tried = linear_census()
    assert single == 0 and swaps == 0, ('the 20-bit check passes a single error', single, swaps)
    assert ty['q'] == rd['q'] == A32 and len(set(A32)) == 32 and 'e' not in ty
    assert not set(A32) & set('ilou')
    return tried


def run_as_apy(py, prog, stdin_lines, cwd):
    """Run a program saved as a.py in its own directory."""
    open(os.path.join(cwd, 'a.py'), 'w').write(prog)
    p = subprocess.run([py, 'a.py'], input='\n'.join(stdin_lines) + '\n',
                       capture_output=True, text=True, cwd=cwd, timeout=600)
    rpy = os.path.join(cwd, 'r.py')
    return p, open(rpy, 'rb').read().decode() if os.path.exists(rpy) else None


def grouped(t):
    """A data line as printed: 12 groups of 5, then the check."""
    p = t[:-CHECK]
    return ' '.join(p[i:i + 5] for i in range(0, len(p), 5)) + ' ' + t[-CHECK:]


def kat_stream(dl):
    """Known-answer stdin: line 1 doubled, a typo on line 2 then the right
    line, line 3 typed with its group spaces, the rest plain with a trailing
    space on the last.  Returns the lines and the expected prompt string."""
    assert len(dl) >= 4
    bad = dl[1][:5] + ('s' if dl[1][5] != 's' else 't') + dl[1][6:]
    lines = [dl[0], dl[0], bad, dl[1], grouped(dl[2])] + dl[3:-1] + [dl[-1] + ' ']
    prompts = [1, 2, 2, 2] + list(range(3, len(dl) + 1))
    return lines, ''.join(f'[{p}]' for p in prompts)


def known_answer():
    """A reader that calls every shared definition, and the line it prints."""
    x = cm2_enc.encode_int(b'hello, finder', b'primer', ORDERS)
    rng = random.Random(42)        # incompressible enough for >= 4 lines
    kat = (f"print('known answer',6*7,k(7,b'abc'),q[31],d({x},13,b'primer'))\n" + ''.join(
        '# ' + ''.join(rng.choice(A32) for _ in range(66)) + '\n' for _ in range(6)))
    want = f"known answer 42 {check(7, 'abc')} z b'hello, finder'\n"
    assert len(kat.encode()) >= 256
    return kat, want


def prove_program(typed_build, readable_build):
    kat, want = known_answer()
    results = []
    for build, own_defs in ((readable_build, readable_defs), (typed_build, typed_defs)):
        prog, C, dl, x = pack(kat, build)
        lines, prompts = kat_stream(dl)
        with tempfile.TemporaryDirectory() as td:
            p, rpy = run_as_apy(sys.executable, prog, lines, td)
            r2 = subprocess.run([sys.executable, 'r.py'], capture_output=True, text=True,
                                cwd=td, timeout=60)
        nl = len(prog.strip().splitlines())
        out = p.stdout.split('\n')
        dump, rest = out[:nl], '\n'.join(out[nl:])
        want_dump = [f'{i} {check(i, t)}' for i, t in enumerate(prog.strip().splitlines(), 1)]
        assert p.returncode == 0 and p.stderr == '', (p.returncode, p.stderr)
        assert dump == want_dump, 'self-dump wrong'
        assert rest == prompts, ('transcript', rest, prompts)
        assert rpy == own_defs(prog.strip()) + kat, 'r.py is not definitions + reader'
        assert r2.returncode == 0 and r2.stdout == want, (r2, want)
        results.append((rpy[-len(kat):], r2.stdout))
    # (each transcript was checked against its own prediction above; the two
    # primers differ, so the two programs may need a different number of lines)
    assert results[0] == results[1], results
    # A wrong reader code makes the assert fire before r.py exists (traceback, exit 1).
    prog, C, dl, x = pack(kat, typed_build)
    with tempfile.TemporaryDirectory() as td:
        p, rpy = run_as_apy(sys.executable, prog.replace(check(0, kat), 'zzzz'), dl, td)
    assert p.returncode == 1 and 'AssertionError' in p.stderr and rpy is None


def build_print(reader, readable_src, out, n2, rpath=None, b2=None, bpath=None):
    prog, C, dl, x = pack(reader, typed)
    bad = audit(prog)
    assert not bad, bad
    assert prog == prog.strip()
    al = prog.split('\n')
    for t in dl:
        assert len(t) <= PAYLOAD + CHECK
    N, R = len(reader.encode()), check(0, reader)
    rpy = (typed_defs(prog) + reader).encode()
    lc, dc = sum(map(len, al)), sum(map(len, dl))
    codes = [f'{i} {check(i, t)}' for i, t in enumerate(al, 1)]
    codes += [
        f'a.py lines {len(al)} chars {lc} (newlines not counted), longest {max(map(len, al))}',
        f'data lines {C} chars {dc} incl. checks, no spaces (G {dc - CHECK * C} base-32'
        f' glyphs = x of {x.bit_length()} bits; reader N {N} bytes'
        + (f', N2 {n2}' if n2 is not None else '') + (f', B2 {b2}' if b2 is not None else '')
        + f'; orders {ORDERS})',
        f'typed chars {lc + dc}',
        f'r.py {len(rpy)} bytes = definitions a[{START}:{END}] + reader {N}'
        f' (the primer of the page, written and read in binary)',
    ]
    files = {
        os.path.join(out, 'a.py'): (prog + '\n').encode(),
        os.path.join(out, 'data.txt'): ('\n'.join(dl) + '\n').encode(),
        os.path.join(out, 'codes.txt'): ('\n'.join(codes) + '\n').encode(),
        os.path.join(out, 'r.py'): rpy,
        os.path.join(out, 'build.json'): (json.dumps(      # what refute5 and rebuild.py read
            {'reader': rpath and os.path.abspath(rpath), 'bundle': bpath and os.path.abspath(bpath),
             'n2': n2, 'b2': b2, 'orders': ORDERS, 'N': N,
             'C': C, 'G': len(b32(x)), 'reader code': R, 'slice': [START, END]},
            indent=1) + '\n').encode(),
        READABLE: readable(N, C, R, readable_src).encode(),
    }
    return files, codes[len(al):], (N, C, R, len(b32(x)))


def main():
    a = sys.argv[1:]
    rpath = a[a.index('--reader') + 1] if '--reader' in a else READER
    out = a[a.index('--out') + 1] if '--out' in a else OUT
    assert not ('--n2' in a and '--bundle' in a), 'give --n2 or --bundle, not both'
    n2 = (int(a[a.index('--n2') + 1]) if '--n2' in a else
          os.path.getsize(a[a.index('--bundle') + 1]) if '--bundle' in a else None)
    b2 = bundle_crc(a[a.index('--bundle') + 1]) if '--bundle' in a else None
    record = '--no-record' not in a
    os.makedirs(out, exist_ok=True)
    reader = reader_text(rpath, n2, b2)
    readable_src = open(READABLE).read()
    assert not audit(typed(99999, 99, 'xyzw')), audit(typed(99999, 99, 'xyzw'))

    tried = prove_units(typed(1, 1, 'xyzw'), readable_src)
    prove_program(typed, lambda N, C, R: readable(N, C, R, readable_src))
    print(f'equivalence: units + KATs + known answer PASS (linear census: 0 of {tried} single'
          ' substitutions, wrong line numbers and transpositions pass)')

    bpath = a[a.index('--bundle') + 1] if '--bundle' in a else None
    files, counts, (N, C, R, G) = build_print(reader, readable_src, out, n2, rpath, b2, bpath)
    again, _, _ = build_print(reader, readable(1, 1, 'xxxx', readable_src), out, n2, rpath, b2,
                              bpath)
    assert again == files, 'regeneration is not byte-identical'
    for path, data in files.items():
        if record or path != READABLE:
            open(path, 'wb').write(data)
    if record:                      # the print of record (--no-record: OUT only, for tests)
        for f in ('a.py', 'data.txt', 'codes.txt'):
            open(os.path.join(HERE, f), 'wb').write(files[os.path.join(out, f)])
    print('reader', os.path.relpath(rpath, ROOT), f'(N2 {n2}, B2 {b2})')
    print('\n'.join(counts))
    print(f'N={N} C={C} G={G} reader code {R} slice a[{START}:{END}] orders {ORDERS}')


if __name__ == '__main__':
    main()
