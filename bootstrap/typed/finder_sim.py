"""Simulated finder for checker.py (test harness; not typed).

  python3 finder_sim.py [SEED ...]        (default seeds 1 2 3)

Extracts the 12 typed lines of checker.py (between '# BEGIN CHECKER' /
'# END CHECKER') into a fresh folder, runs them with `python3 -u` through a
pipe, and types a stream made by typist.py: code = the cm2 decoder region
(bootstrap/typed/cm2_dec.py) + a tiny glue/echo program, data = R2-FORMAT.md
compressed by cm2 with primer = the code section's typed text.  Mishaps:
payload substitution, check substitution, adjacent and distant
transposition, dropped line, doubled line, garbage lines; the finder retypes
whatever the checker names.  Two crashes (kill -9) with resume.  After RUN
it types lines the exec'd program must echo.  Asserts: every verdict is the
expected one, a.py == the decoded code section, the program's decoded data
== R2-FORMAT.md, the echoes arrive.  Also runs the Plate known-answer test
and the subset rules on the checker's own lines."""
import ast, os, random, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import typist as T          # noqa: E402
import cm2_v1_enc as cm2_enc  # noqa: E402  (the 10-18 range coder; cm2_enc.py is v2 since 2026-10-20)

PROGRAM = '''\
v = 0
for ch in t[1]:
    v = v * 32 + A.index(ch)
k = 5 * len(t[1]) // 8
z = (v >> 5 * len(t[1]) - 8 * k).to_bytes(k, 'big')
r = decode(z[4:], int.from_bytes(z[:4], 'big'), t[0].encode())
open('out.bin', 'wb').write(r)
print('PROG', len(r))
w = input()
while w != 'END':
    print('ECHO', w)
    w = input()
print('DONE')
'''
KA_ACCEPT = 'if 1:' + chr(126) + chr(64) + 'print(42)' + chr(126) + 'snk'
KA_REJECT = 'if 1:' + chr(126) + chr(64) + 'print(24)' + chr(126) + 'snk'


def typed_checker():
    src = open(os.path.join(HERE, 'checker.py')).read()
    body = src.split('# BEGIN CHECKER\n', 1)[1].split('# END CHECKER', 1)[0]
    return body


def subset_report(body):
    lines = [l for l in body.split('\n') if l.strip()]
    bad = []
    for k, l in enumerate(lines, 1):
        if len(l) > 72:
            bad.append(f'line {k} has {len(l)} chars')
        if any(ch in l for ch in '~@;\t') or l != l.rstrip():
            bad.append(f"line {k} has '~', '@', ';', a tab or trailing space")
    for nd in ast.walk(ast.parse(body)):
        if isinstance(nd, (ast.Import, ast.ImportFrom)):
            bad.append('import')
        if isinstance(nd, ast.Constant) and isinstance(nd.value, float):
            bad.append('float literal')
        if isinstance(nd, ast.BinOp) and isinstance(nd.op, ast.Div):
            bad.append("true division '/'")
        if isinstance(nd, ast.Call) and getattr(nd.func, 'id', '') == 'hash':
            bad.append('hash()')
    return len(lines), sum(len(l) for l in lines), bad


class Checker:
    def __init__(self, d):
        self.p = subprocess.Popen([sys.executable, '-u', 'c.py'], cwd=d, text=True,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self):
        out = self.p.stdout.readline()
        assert out, 'checker died'
        return out.split()

    def send(self, line):
        self.p.stdin.write(line + '\n')
        self.p.stdin.flush()

    def kill(self):
        self.p.kill()
        self.p.wait()


def mishap(kind, lines, want, rng):
    """(typed text, verdict expected) for one mishap on line `want`."""
    good = lines[want - 1]
    p, c = good[:-3], good[-3:]
    if kind == 'sub':
        i = rng.randrange(len(p))
        ch = rng.choice([x for x in T.ALPHA + 'xyz()=+:, ' if x != p[i]])
        return p[:i] + ch + p[i + 1:] + c
    if kind == 'subcheck':
        i = rng.randrange(3)
        return p + c[:i] + rng.choice([x for x in T.ALPHA if x != c[i]]) + c[i + 1:]
    if kind in ('swap', 'swapfar'):
        idx = [(i, j) for i in range(len(p)) for j in range(i + 1, len(p))
               if p[i] != p[j] and (j == i + 1) == (kind == 'swap')]
        if not idx:
            return mishap('sub', lines, want, rng)
        i, j = rng.choice(idx)
        q = list(p)
        q[i], q[j] = q[j], q[i]
        return ''.join(q) + c
    if kind == 'drop':
        return lines[want]
    if kind == 'double':
        return lines[want - 2]
    g = ['', ' ', 'RUN ', 'run', 'R U N', 'x' * 500, '###', good[:-1],
         good + 'q', good.upper(), 'é中Ж☃', '\x00\x01\x7f',
         c, 'BAD 3', '0' * 67, ''.join(rng.choice(
             [chr(rng.randrange(32, 0x3000)) for _ in range(60)]) for _ in range(67))]
    return rng.choice(g)


def run_stream(seed, d, lines, code_text):
    rng = random.Random(seed)
    kinds = ['sub', 'subcheck', 'swap', 'swapfar', 'drop', 'double', 'garbage']
    stats = {k: 0 for k in kinds}
    stats.update(typed=0, rerolls=0, crash_pre=0, crash_post=0)
    nchk = len(lines) - 1
    crash_at = sorted(rng.sample(range(5, nchk - 5), 2))
    ch = Checker(d)
    v = ch.read()
    assert v == ['OK', '1'], v
    want = 1
    while want <= nchk:
        kind = None
        if rng.random() < 0.45:
            kind = kinds[stats['typed'] % len(kinds)] if rng.random() < 0.6 else rng.choice(kinds)
            if (kind == 'drop' and want == nchk) or (kind == 'double' and want == 1):
                kind = 'sub'
        if kind:
            for _ in range(100):
                text = mishap(kind, lines, want, rng)
                if text[-3:] != T.check(want, text[:-3]):
                    break
                stats['rerolls'] += 1          # the 1-in-32768 lucky pass: retry
            stats[kind] += 1
        else:
            text = lines[want - 1]
        ch.send(text)
        stats['typed'] += 1
        if len(crash_at) == 2 and want - 1 >= crash_at[0] and not kind:
            ch.kill()                          # power cut before the verdict
            stats['crash_pre'] += 1
            crash_at.pop(0)
            ch = Checker(d)
            v = ch.read()
            assert v[0] == 'OK' and int(v[1]) in (want, want + 1), v
            want = int(v[1])
            continue
        v = ch.read()
        exp = ['BAD', str(want)] if kind else ['OK', str(want + 1)]
        assert v == exp, (seed, want, kind, repr(text), v, exp)
        want = int(v[1])                       # the finder does what it is told
        if len(crash_at) == 1 and want - 1 >= crash_at[0] and not kind:
            ch.kill()                          # crash after a clean OK
            stats['crash_post'] += 1
            crash_at.pop(0)
            ch = Checker(d)
            v = ch.read()
            assert v == ['OK', str(want)], v
    ch.send('RUN')
    v = ch.read()
    assert v[0] == 'PROG', v
    for w in ['hello', 'second line typed after RUN', 'x' * 70]:
        ch.send(w)
        assert ch.read() == ['ECHO'] + w.split(), w
    ch.send('END')
    assert ch.read() == ['DONE']
    ch.p.wait()
    assert open(os.path.join(d, 'a.py')).read() == T.decode_code(code_text)
    return stats, int(v[1])


def plate_test(d):
    ch = Checker(d)
    assert ch.read() == ['OK', '1']
    ch.send(KA_REJECT)
    assert ch.read() == ['BAD', '1']
    ch.send(KA_ACCEPT)
    assert ch.read() == ['OK', '2']
    ch.send('RUN')
    assert ch.read() == ['42']
    ch.p.wait()
    assert open(os.path.join(d, 'a.py')).read() == 'if 1:\n    print(42)\n'


def main(seeds):
    body = typed_checker()
    nl, nc, bad = subset_report(body)
    print(f'checker: {nl} lines, {nc} chars (no indent counted: '
          f'{sum(len(l.strip()) for l in body.split(chr(10)))}); violations: {bad or "none"}')
    assert not bad
    dec = open(os.path.join(HERE, 'cm2_v1_dec.py')).read()
    code_text = T.encode_code(T.region(dec) + PROGRAM)
    payload = open(os.path.join(HERE, '..', 'R2-FORMAT.md'), 'rb').read()
    orders = cm2_enc.orders_of(os.path.join(HERE, 'cm2_v1_dec.py'))
    z = cm2_enc.encode(payload, code_text.encode(), orders)
    data = len(payload).to_bytes(4, 'big') + z
    lines = T.encode(code_text, data)
    assert T.decode_lines(lines) == (code_text, T.b32(data))
    print(f'stream: {len(lines) - 1} checked lines + RUN ({len(code_text)} code chars, '
          f'{len(payload)} B payload -> {len(data)} B -> {len(T.b32(data))} base-32 chars)')
    root = tempfile.mkdtemp(prefix='finder_sim_')
    try:
        d = os.path.join(root, 'plate')
        os.mkdir(d)
        open(os.path.join(d, 'c.py'), 'w').write(body)
        plate_test(d)
        print('plate known-answer test: reject -> BAD 1, accept -> OK 2, RUN -> 42: PASS')
        d = os.path.join(root, 'self')
        os.mkdir(d)
        open(os.path.join(d, 'c.py'), 'w').write(body)
        ch = Checker(d)
        assert ch.read() == ['OK', '1']
        own = [l for l in body.split('\n') if l.strip()]
        for n, l in enumerate(own, 1):
            ch.send(l + T.check(n, l))
            assert ch.read() == ['OK', str(n + 1)], n
        ch.kill()
        print(f'self-test: the checker accepts its own {len(own)} printed lines: PASS')
        for s in seeds:
            d = os.path.join(root, f's{s}')
            os.mkdir(d)
            open(os.path.join(d, 'c.py'), 'w').write(body)
            stats, n = run_stream(s, d, lines, code_text)
            assert open(os.path.join(d, 'out.bin'), 'rb').read() == payload
            print(f'seed {s}: PASS {stats}; program decoded {n} B == R2-FORMAT.md')
    finally:
        shutil.rmtree(root)


if __name__ == '__main__':
    main([int(a) for a in sys.argv[1:]] or [1, 2, 3])
