"""make_typed.py v4 -- stage 1 of the bootstrap (bootstrap/stage1/, ruling 43
of 2026-10-21; v3 = bootstrap/loader/make_typed.py, the print of record).

What changed against v3 (the rest -- the fixed point on C, the base-32
data lines with their Horner checks, the proofs -- is v3's):
  - the typed program comes from template.py (one source, roles for
    names), with the rewrite candidates and the letter map that search.py
    chose and froze in frozen_<case>.json (items 10 and 11; without that
    file the template's base spelling and today's letters, with a warning);
  - item 2: a.py writes b.py (v3: r.py); the reader it carries is the e2e
    copy of r2reader/reader_lite_v1.py with its two file literals following
    the stage names (ruling 34): it reads its primer from 'b.py' (was
    'r.py') and writes 'c.py' (was 'b.py').  The copy lives in
    build/stage1/reader_e2e.py; r2reader/reader_lite_v1.py is not touched;
  - item 3: k and the alphabet line above d (the b.py slice starts with them);
  - item 4: the baked constants (the reader's bytes, its check code, the loop
    bound, the slice) by the fixed point, as in v3;
  - item 7: def d(x,n,r,w=(...)) -- the order tuple a parameter with a
    default; the default is chosen PER RUN over template.FRONTIER by the
    typed total (a.py characters + data glyphs + 4 per line, newlines not
    counted), among the tuples whose R2 payload (cm2 of build/bundle/b.py
    primed with this run's b.py, the reader decoding it with the default)
    keeps the record's page count (R2_PAGES_BOUND, 3); a tuple whose a.py
    has no fixed point of the loop bound (C lines code to C+1 and C+1 to C)
    is recorded as such and not chosen (2026-10-23);
  - item 8 (explored): --case lower|upper -- the alphabet constant, and so the
    data glyphs and the check glyphs, in that case; nothing else changes;
  - with the 'selfdump-counter' candidate the data lines are numbered after
    the listing ([L+1] ...), their checks seeded with those numbers.
Proofs, every run: (1) units -- the typed d against the long form's d, the
reference typed/cm2_dec.py (the long tuple, the KAT vectors of
typed/kat_v2.json passed as w) and the encoder typed/cm2_enc.py at the
chosen tuple; the typed k against the long form's k and the formula; the
linear census; (2) whole program -- a known-answer reader packed with its
own fixed point, the typed a.py and the long form (readable.py, beside it in
the same directory, reading the same a.py) run on the same keystrokes:
the same screen, the same b.py (= the slice + the known answer), which runs
and prints the answer; a wrong reader code fires the assert in both, no
b.py.  The files are built twice and compared byte for byte.
Output: build/stage1/<case>/ a.py, data.txt, codes.txt, b.py, readable.py,
build.json (every constant, the frontier, the search record), sizes.txt.
Usage: python make_typed.py --case lower|upper [--frozen PATH] [--out DIR] [--build DIR]
(--build: the build directory in place of build/stage1/, the reader copy included)
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
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'typed'))
sys.path.insert(0, os.path.join(ROOT, 'r2'))
import cm2_enc  # noqa: E402
import template as T  # noqa: E402
import gen_readable  # noqa: E402

DEC = os.path.join(ROOT, 'typed', 'cm2_dec.py')
KATS = os.path.join(ROOT, 'typed', 'kat_v2.json')
READER_SRC = os.path.join(ROOT, 'r2reader', 'reader_lite_v1.py')
BUILD = os.path.join(ROOT, 'build', 'stage1')
READER_COPY = os.path.join(BUILD, 'reader_e2e.py')
BUNDLE = os.path.join(ROOT, 'build', 'bundle', 'b.py')
# The record's R2 page count, frozen 2026-10-23 (control rebuild): the frontier's gate; c.py needs 2.
R2_PAGES_BOUND = 3
PY = sys.executable
PAYLOAD = 60
CHECK = 4
MOD = 1 << 20
MAXLINE = 72
K = 1000003
SHARED_BEGIN = '#--- shared with the loader (not typed) ---'
SHARED_END = '#--- end shared ---'
# The e2e copy's two literals (ruling 34: the loader writes b.py, the reader c.py).
LITERALS = (("open('r.py','rb')", "open('b.py','rb')"), ("open('b.py','wb')", "open('c.py','wb')"))


# ---- the reader (v3's helpers, unchanged) -----------------------------------
def region(path, begin, end):
    s = open(path).read()
    if begin + '\n' not in s:
        return s
    return s.split(begin + '\n', 1)[1].split(end, 1)[0]


def drop_shared(s):
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
    toks = [t for t in tokenize.generate_tokens(io.StringIO(s).readline)
            if t.type == tokenize.NAME and t.string == name]
    if not toks:
        return s, 0
    lines = s.splitlines(keepends=True)
    for t in reversed(toks):
        (row, c0), (_, c1) = t.start, t.end
        lines[row - 1] = lines[row - 1][:c0] + str(value) + lines[row - 1][c1:]
    return ''.join(lines), len(toks)


def reader_copy():
    """build/stage1/reader_e2e.py = r2reader/reader_lite_v1.py with the two
    file literals of ruling 34 (each must occur exactly once; a no-op where
    the reader already carries the new literal, since the 2026-10-22 change set)."""
    s = open(READER_SRC).read()
    for old, new in LITERALS:
        if s.count(new) == 1 and old not in s:
            continue
        assert s.count(old) == 1, ('literal not found once in the reader', old)
        s = s.replace(old, new)
    os.makedirs(BUILD, exist_ok=True)
    if not os.path.exists(READER_COPY) or open(READER_COPY).read() != s:
        open(READER_COPY, 'w').write(s)
    return READER_COPY


def reader_text(path, n2, b2):
    s = drop_shared(region(path, '# BEGIN READER', '# END READER'))
    s, k = put_token(s, 'N2', n2)
    assert k, 'the reader has no N2 token'
    s, k = put_token(s, 'B2', b2)
    assert k, 'the reader has no B2 token'
    return s


def the_reader(bundle=BUNDLE):
    b = open(bundle, 'rb').read()
    return reader_text(reader_copy(), len(b), zlib.crc32(b)), len(b), zlib.crc32(b)


# ---- the check and the digits ----------------------------------------------
def check(n, t, alpha):
    """Horner (ruling 5 of 2026-10-19) over the characters of t (ASCII)."""
    for c in t:
        n = (n + ord(c)) * K % MOD
    return ''.join(alpha[n >> sh & 31] for sh in (15, 10, 5, 0))


def b32(x, alpha):
    out = []
    while x:
        out.append(alpha[x & 31])
        x >>= 5
    return ''.join(reversed(out))


def primer_of(prog):
    return prog.strip().encode()


# ---- the spec: the frozen search result --------------------------------------
def load_spec(case, path=None):
    path = path or os.path.join(HERE, f'frozen_{case}.json')
    if not os.path.exists(path):
        print(f'WARNING: {os.path.relpath(path, ROOT)} absent: the template\'s base spelling '
              'and the letters of record (run search.py --case ' + case + ' --freeze)',
              file=sys.stderr)
        return dict(case=case, edits=[], letters=dict(T.BASE_LETTERS), frozen=None)
    s = json.load(open(path))
    assert s['case'] == case, (s['case'], case)
    return dict(case=case, edits=s['edits'], letters=s['letters'], frozen=os.path.relpath(path, ROOT),
                search=s)


def builder(spec, orders):
    """-> build(N, C, R) -> (program, first data line number, slice)."""
    text = T.typed_text(spec['edits'], spec['letters'], spec['case'], orders)
    first = T.first_data_line(T.apply_edits(spec['edits']))

    def build(N, C, R):
        prog, s0, s1 = T.bake(text, N, first + C, R)
        return prog, first, (s0, s1)
    return build


class NoFixedPoint(AssertionError):
    """pack() found no C within one of the estimate whose a.py codes the reader
    into exactly C data lines (the line count flips with the loop bound)."""


def pack(reader, build, alpha, orders):
    """Fixed point of C (data lines), which sits inside the primer as the loop
    bound (v3).  -> dict(prog, C, data lines, x, first, slice); NoFixedPoint
    when there is none (C lines -> C+1 lines and C+1 -> C, measured
    2026-10-23 at (0,...,8,12) on the 24,163 B c.py)."""
    raw = reader.encode()
    N, R = len(raw), check(0, reader, alpha)

    def attempt(C):
        prog, first, sl = build(N, C, R)
        x = cm2_enc.encode_int(raw, primer_of(prog), orders)
        s = b32(x, alpha)
        lines = [s[i:i + PAYLOAD] for i in range(0, len(s), PAYLOAD)]
        if len(lines) != C:
            return None, len(lines)
        dl = [t + check(n, t, alpha) for n, t in enumerate(lines, first)]
        return dict(prog=prog, C=C, dl=dl, x=x, first=first, slice=sl, N=N, R=R), len(lines)

    _, c0 = attempt(1)
    best = None
    for C in range(max(1, c0 - 1), c0 + 2):
        got, _ = attempt(C)
        if got and (best is None or cost(got) < cost(best)):
            best = got
    if not best:
        raise NoFixedPoint('no C fixed point near the estimate')
    return best


def chars(prog):
    return sum(map(len, prog.strip().split('\n')))


def cost(p):
    """The typed total: a.py characters + data characters (newlines not counted)."""
    return chars(p['prog']) + sum(map(len, p['dl']))


# ---- the subset audit ---------------------------------------------------------
def module_bindings(src):
    out, todo = set(), list(ast.parse(src).body)
    while todo:
        x = todo.pop()
        if isinstance(x, ast.FunctionDef):
            out.add(x.name)
            continue
        if isinstance(x, (ast.Lambda,) + T.COMPS):
            continue
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
            out.add(x.id)
        todo.extend(ast.iter_child_nodes(x))
    return out


def main_line(lines):
    """The self-dump line: the first unindented line after line 1 that starts
    with 'for'."""
    return next(i for i, s in enumerate(lines) if i > 0 and s.startswith('for'))


def audit(a, spec):
    """The typed-subset rules (rulings 5, 7, 8, 9, 11 of 2026-10-19; the layout
    rulings of 2026-10-20; ruling 43): integers only, no imports, no floats,
    no '/', builtins only; capitals only inside the alphabet literal."""
    alpha = T.ALPHABETS[spec['case']]
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
        if isinstance(x, ast.Name) and x.id == 'l':
            bad.append('identifier l')
    codes = [m for m in re.findall(r"'([^']{4})'", a.split('\n')[-2]) if set(m) <= set(alpha)]
    rest = a.replace(f"'{alpha}'", '')
    for c in codes[:1]:                  # the reader's check code, in the alphabet's case
        rest = rest.replace(f"'{c}'", '')
    if any(c.isupper() for c in rest):
        bad.append('capital letter outside the alphabet literal and the reader code')
    if '\\' in a or '"' in a or '\t' in a:
        bad.append('backslash, double quote or tab')
    calls = [x.func.id for x in ast.walk(tree)
             if isinstance(x, ast.Call) and isinstance(x.func, ast.Name)]
    if calls.count('print') != 1:
        bad.append('a print beside the self-dump')
    lines = a.split('\n')
    if not (lines[-2].startswith('assert') and lines[-1].startswith("open('b.py','wb').write(")):
        bad.append('program does not end with the assert and the write of b.py')
    start = a.index('\n') + 1
    m = main_line(lines)
    end = sum(len(s) + 1 for s in lines[:m])
    L = spec['letters']
    want = {L['Alpha'], L['Line'], L['Num'], L['Check'], L['Dec']}
    if module_bindings(a[start:end]) != want:
        bad.append(f'definitions bind {sorted(module_bindings(a[start:end]))}, not {sorted(want)}')
    if f'def {L["Dec"]}(' not in a[start:end] or f'def {L["Check"]}(' not in a[start:end]:
        bad.append('the definitions do not hold d and k')
    if a[start:end].index(f'def {L["Dec"]}(') < a[start:end].index(f'def {L["Check"]}('):
        bad.append('k is not above d (item 3)')
    if f'[{start}:{end}]' not in lines[-1]:
        bad.append(f'the b.py slice is not a[{start}:{end}]')
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


# ---- proofs -------------------------------------------------------------------
def defs(src):
    """The module-level functions and constant assignments of a program."""
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
    """v3's census: Horner mod 2**20 passes no single substitution, wrong line
    number or ASCII transposition up to maxlen glyphs."""
    P = [pow(K, x, MOD) for x in range(maxlen + 1)]
    single = sum(dl * P[x] % MOD == 0 for dl in range(1, 256) for x in range(maxlen + 1))
    swaps = sum(dl * (P[x1] - P[x2]) % MOD == 0 for dl in range(1, 128)
                for x1 in range(1, maxlen + 1) for x2 in range(x1 + 1, maxlen + 1))
    return single, swaps, 255 * (maxlen + 1) + 127 * maxlen * (maxlen - 1) // 2


def kat_vectors():
    kat = json.load(open(KATS))
    assert tuple(kat['orders']) == T.LONG_TUPLE
    return [(int(v['x'], 16), v['n'], bytes.fromhex(v['primer']), bytes.fromhex(v['data']))
            for v in kat['vectors']]


def prove_units(typed_src, long_src, spec, orders):
    L, alpha = spec['letters'], T.ALPHABETS[spec['case']]
    ty, lf = defs(typed_src), defs(long_src)
    td, tk = ty[L['Dec']], ty[L['Check']]
    ld, lk = lf[T.LONG_NAMES['Dec']], lf[T.LONG_NAMES['Check']]
    ref = {}
    exec(region(DEC, '# BEGIN DECODER', '# END DECODER'), ref)
    rng = random.Random(20261021)
    for trial in range(30):
        n = rng.randrange(0, 500)
        data = bytes(rng.choice(b'abcdefgh \n()=:01') if trial % 2 else rng.randrange(256)
                     for _ in range(n))
        pr = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 300)))
        for o in (orders, T.LONG_TUPLE):
            x = cm2_enc.encode_int(data, pr, o)
            got = [td(x, n, pr, o), ld(x, n, pr, o)]
            if o == orders:
                got += [td(x, n, pr), ld(x, n, pr)]          # the default
            if o == T.LONG_TUPLE:
                got.append(ref['decode'](x, n, pr))
            assert all(g == data for g in got), ('decoders differ', trial, o)
    for x, n, pr, data in kat_vectors():
        assert td(x, n, pr, T.LONG_TUPLE) == ld(x, n, pr, T.LONG_TUPLE) == data, 'KAT'
    for trial in range(3000):
        n = rng.randrange(0, MOD)
        t = ''.join(chr(rng.randrange(32, 127)) for _ in range(rng.randrange(0, 80)))
        want = n
        for c in t:
            want = (want + ord(c)) * 1000003 % 1048576
        want = alpha[want >> 15] + alpha[want >> 10 & 31] + alpha[want >> 5 & 31] + alpha[want & 31]
        b = t.encode()
        assert tk(n, b) == lk(n, b) == check(n, t, alpha) == want, ('checks differ', n, t)
    single, swaps, tried = linear_census()
    assert single == 0 and swaps == 0
    assert ty[L['Alpha']] == lf[T.LONG_NAMES['Alpha']] == alpha and len(set(alpha)) == 32
    assert not set(alpha.lower()) & set('ilou')
    return tried


def run_in(cwd, name, stdin_lines, timeout=900):
    p = subprocess.run([PY, name], input='\n'.join(stdin_lines) + '\n', capture_output=True,
                       text=True, cwd=cwd, timeout=timeout)
    bp = os.path.join(cwd, 'b.py')
    out = open(bp, 'rb').read() if os.path.exists(bp) else None
    if out is not None:
        os.remove(bp)
    return p, out


def grouped(t):
    p = t[:-CHECK]
    return ' '.join(p[i:i + 5] for i in range(0, len(p), 5)) + ' ' + t[-CHECK:]


def kat_stream(dl, first, alpha):
    """v3's known-answer keystrokes: line 1 doubled, a typo on line 2 then the
    right line, line 3 typed with its group spaces, the rest plain with a
    trailing space on the last."""
    assert len(dl) >= 4
    s, t = alpha[25], alpha[26]                     # 's' / 't' in the case of the print
    bad = dl[1][:5] + (s if dl[1][5] != s else t) + dl[1][6:]
    lines = [dl[0], dl[0], bad, dl[1], grouped(dl[2])] + dl[3:-1] + [dl[-1] + ' ']
    prompts = [first, first + 1, first + 1, first + 1, first + 2] + list(
        range(first + 3, first + len(dl)))
    return lines, ''.join(f'[{p}]' for p in prompts)


def known_answer(spec, orders):
    L, alpha = spec['letters'], T.ALPHABETS[spec['case']]
    x = cm2_enc.encode_int(b'hello, finder', b'primer', orders)
    y = cm2_enc.encode_int(b'long tuple', b'primer', T.LONG_TUPLE)
    rng = random.Random(42)
    kat = (f"print('known answer',6*7,{L['Check']}(7,b'abc'),{L['Alpha']}[31],"
           f"d({x},13,b'primer'),d({y},10,b'primer',{str(T.LONG_TUPLE).replace(' ', '')}))\n"
           + ''.join('# ' + ''.join(rng.choice(alpha) for _ in range(66)) + '\n'
                     for _ in range(6)))
    want = (f"known answer 42 {check(7, 'abc', alpha)} {alpha[31]} b'hello, finder' "
            "b'long tuple'\n")
    return kat, want


def prove_program(spec, orders):
    """The typed a.py and the long form on the same keystrokes, in one
    directory (the long form reads the a.py beside it): the same screen, the
    same b.py; b.py runs; a wrong reader code stops both before b.py."""
    alpha = T.ALPHABETS[spec['case']]
    kat, want = known_answer(spec, orders)
    p = pack(kat, builder(spec, orders), alpha, orders)
    prog, dl, first = p['prog'], p['dl'], p['first']
    long_src = gen_readable.readable(spec['edits'], spec['case'], orders, p['N'],
                                     first + p['C'], p['R'], *p['slice'])
    lines, prompts = kat_stream(dl, first, alpha)
    al = prog.split('\n')
    want_dump = '\n'.join(f'{i} {check(i, t, alpha)}' for i, t in enumerate(al, 1)) + '\n'
    with tempfile.TemporaryDirectory() as td:
        open(os.path.join(td, 'a.py'), 'w').write(prog + '\n')
        open(os.path.join(td, 'readable.py'), 'w').write(long_src)
        r1, b1 = run_in(td, 'a.py', lines)
        r2, b2 = run_in(td, 'readable.py', lines)
        for r in (r1, r2):
            assert r.returncode == 0 and r.stderr == '', (r.returncode, r.stderr[-2000:])
        assert r1.stdout == r2.stdout == want_dump + prompts, 'screens differ'
        assert b1 == b2 == (prog[p['slice'][0]:p['slice'][1]] + kat).encode(), 'b.py differs'
        open(os.path.join(td, 'b.py'), 'wb').write(b1)
        r3 = subprocess.run([PY, 'b.py'], capture_output=True, text=True, cwd=td, timeout=120)
        assert r3.returncode == 0 and r3.stdout == want, (r3.stdout, r3.stderr)
        os.remove(os.path.join(td, 'b.py'))
        R = p['R']
        open(os.path.join(td, 'a.py'), 'w').write(prog.replace(f"'{R}'", "'zzzz'") + '\n')
        open(os.path.join(td, 'readable.py'), 'w').write(long_src.replace(f"'{R}'", "'zzzz'"))
        for name in ('a.py', 'readable.py'):
            r, b = run_in(td, name, lines)
            assert r.returncode == 1 and 'AssertionError' in r.stderr and b is None, name
    return dict(kat_lines=len(dl), first=first)


# ---- the tuple, per run ------------------------------------------------------
def r2_payload(bundle_bytes, bpy, orders):
    return cm2_enc.encode(bundle_bytes, bpy, orders)


def frontier(spec, reader, bundle_bytes, pages_max):
    """Every tuple of the frontier, packed; the R2 payload computed in order of
    the typed total until one keeps the page count."""
    import gen  # noqa: E402  (r2/gen.py: n_pages)
    alpha = T.ALPHABETS[spec['case']]
    rows = []
    for o in T.FRONTIER:
        try:
            p = pack(reader, builder(spec, o), alpha, o)
        except NoFixedPoint:
            rows.append(dict(orders=list(o), total=None, no_fixed_point=True))
            continue
        rows.append(dict(orders=list(o), total=cost(p), apy_chars=chars(p['prog']),
                         glyphs=len(b32(p['x'], alpha)), lines=p['C'], packed=p))
    chosen = None
    for r in sorted((r for r in rows if r['total'] is not None),
                    key=lambda r: (r['total'], len(r['orders']))):
        p = r['packed']
        bpy = (p['prog'][p['slice'][0]:p['slice'][1]] + reader).encode()
        z = r2_payload(bundle_bytes, bpy, tuple(r['orders']))
        r['r2_bytes'], r['r2_pages'] = len(z), gen.n_pages(len(z))
        if r['r2_pages'] <= pages_max:
            chosen = r
            break
    assert chosen, 'no tuple of the frontier keeps the R2 page count'
    return rows, chosen


# ---- the print ---------------------------------------------------------------
def build_print(spec, reader, n2, b2, out, pages_max, bundle_bytes):
    alpha = T.ALPHABETS[spec['case']]
    rows, ch = frontier(spec, reader, bundle_bytes, pages_max)
    orders = tuple(ch['orders'])
    p = ch['packed']
    prog, dl, first = p['prog'], p['dl'], p['first']
    bad = audit(prog, spec)
    assert not bad, bad
    al = prog.split('\n')
    s0, s1 = p['slice']
    bpy = (prog[s0:s1] + reader).encode()
    long_src = gen_readable.readable(spec['edits'], spec['case'], orders, p['N'], first + p['C'],
                                     p['R'], s0, s1)
    lc, dc = chars(prog), sum(map(len, dl))
    G = len(b32(p['x'], alpha))
    codes = [f'{i} {check(i, t, alpha)}' for i, t in enumerate(al, 1)]
    counts = [
        f'a.py lines {len(al)} chars {lc} (newlines not counted), longest {max(map(len, al))}',
        f'data lines {p["C"]} (numbered {first}..{first + p["C"] - 1}) chars {dc} incl. checks, '
        f'no spaces (G {G} base-32 glyphs = x of {p["x"].bit_length()} bits; reader N {p["N"]} '
        f'bytes, N2 {n2}, B2 {b2}; orders {orders})',
        f'typed chars {lc + dc}',
        f'b.py {len(bpy)} bytes = definitions a[{s0}:{s1}] + reader {p["N"]}'
        f' (the primer of the R2 pages, written and read in binary)',
        f'R2 payload {ch["r2_bytes"]} B, {ch["r2_pages"]} pages (record {pages_max})',
    ]
    rec = dict(case=spec['case'], alphabet=alpha, reader=os.path.relpath(READER_COPY, ROOT),
               reader_source=os.path.relpath(READER_SRC, ROOT), reader_literals=LITERALS,
               bundle=os.path.relpath(BUNDLE, ROOT), n2=n2, b2=b2, N=p['N'], C=p['C'], G=G,
               first_data_line=first, loop_bound=first + p['C'], reader_code=p['R'],
               slice=[s0, s1], orders=list(orders), apy_lines=len(al), apy_chars=lc,
               data_chars=dc, typed_total=lc + dc, x_bits=p['x'].bit_length(),
               bpy_bytes=len(bpy), r2_payload_bytes=ch['r2_bytes'], r2_pages=ch['r2_pages'],
               r2_pages_of_record=pages_max,
               frontier=[{k: v for k, v in r.items() if k != 'packed'} for r in rows],
               edits=spec['edits'], letters=spec['letters'], frozen=spec.get('frozen'),
               search=spec.get('search', {}).get('record'))
    files = {
        'a.py': (prog + '\n').encode(),
        'data.txt': ('\n'.join(dl) + '\n').encode(),
        'codes.txt': ('\n'.join(codes + counts) + '\n').encode(),
        'b.py': bpy,
        'readable.py': long_src.encode(),
        'build.json': (json.dumps(rec, indent=1) + '\n').encode(),
        'sizes.txt': ('\n'.join(counts) + '\n').encode(),
    }
    return files, counts, rec, (prog, long_src, orders)


def main():
    global BUILD, READER_COPY
    a = sys.argv[1:]
    if '--build' in a:
        BUILD = os.path.abspath(a[a.index('--build') + 1])
        READER_COPY = os.path.join(BUILD, 'reader_e2e.py')
    case = a[a.index('--case') + 1] if '--case' in a else 'lower'
    assert case in T.ALPHABETS
    spec = load_spec(case, a[a.index('--frozen') + 1] if '--frozen' in a else None)
    out = a[a.index('--out') + 1] if '--out' in a else os.path.join(BUILD, case)
    os.makedirs(out, exist_ok=True)
    reader, n2, b2 = the_reader()
    bundle_bytes = open(BUNDLE, 'rb').read()
    pages_max = R2_PAGES_BOUND
    assert T.valid_letters(T.apply_edits(spec['edits']), spec['letters']), 'letter map invalid'
    files, counts, rec, (prog, long_src, orders) = build_print(
        spec, reader, n2, b2, out, pages_max, bundle_bytes)
    tried = prove_units(prog, long_src, spec, orders)
    kp = prove_program(spec, orders)
    print(f'equivalence: units + KATs + known answer (typed and long form, one directory, data '
          f'lines from [{kp["first"]}]) PASS (census: 0 of {tried} single errors pass)')
    again, _, _, _ = build_print(spec, reader, n2, b2, out, pages_max, bundle_bytes)
    assert again == files, 'regeneration is not byte-identical'
    for name, data in files.items():
        open(os.path.join(out, name), 'wb').write(data)
    print(f'case {case}; spelling {spec.get("frozen") or "template base"}; reader '
          f'{os.path.relpath(READER_COPY, ROOT)} (N2 {n2}, B2 {b2})')
    print('frontier: ' + '; '.join(f"{tuple(r['orders'])} {r['total'] or 'no C fixed point'}" +
                                  (f" (R2 {r['r2_bytes']} B {r['r2_pages']} p)" if 'r2_bytes' in r else '')
                                  for r in rec['frontier']))
    print('\n'.join(counts))
    print(f"orders {tuple(rec['orders'])}  N={rec['N']} C={rec['C']} G={rec['G']} reader code "
          f"{rec['reader_code']} slice a[{rec['slice'][0]}:{rec['slice'][1]}] -> {out}")


if __name__ == '__main__':
    main()
