"""test_identity.py -- the long form and the short form of stage 1 are
functionally identical (ruling 35), per case, on the build in
build/sheets/stage1/<case>/ (bootstrap/rebuild_v2.py writes it, through
chain_v2.py make; --build DIR for another, e.g. build/stage1 after
make_typed.py).

  1. mechanical: a.py is template.TEMPLATE with the frozen edits, the
     letters, the alphabet, the tuple and the print's constants, byte for
     byte; readable.py is gen_readable's output for the same inputs, and its
     ast, every descriptive name mapped back to its role, is the template's
     ast (the same statements, order and expressions);
  2. the program: a.py and readable.py, side by side in one directory (the
     long form reads that a.py, as a.py does), each fed data.txt at its
     prompts: exit 0, nothing on stderr, the same screen, and b.py byte-
     identical between the two and to build/stage1/<case>/b.py;
  3. k(): the typed check and the long form's equal on 1,000 random byte
     strings with random line numbers (and both equal to the formula);
  4. d(): the typed decoder and the long form's equal on three payloads --
     the reader from data.txt's number (primer a.py, the default tuple), a
     random 3 KB text primed with b.py at the default tuple, and a KAT vector
     of typed/kat_v2.json with the long tuple passed as w;
  5. the committed long form (upper only): stage1/a_readable_upper.py minus
     its header (through COMMITTED_END) is the build's readable.py.
Usage: python test_identity.py [--case lower|upper ...] [--build DIR]   (default: both)
       or pytest bootstrap/stage1/test_identity.py
"""
import json
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import template as T  # noqa: E402
import gen_readable  # noqa: E402
import make_typed as M  # noqa: E402

BUILD = os.path.join(os.path.dirname(HERE), 'build', 'sheets', 'stage1')   # bootstrap/rebuild_v2.py's OUT/stage1
COMMITTED = {'upper': os.path.join(HERE, 'a_readable_upper.py')}           # the long form kept in the tree
COMMITTED_END = "# ---- end of the committed copy's header; readable.py follows ----\n"


def load(case):
    d = os.path.join(BUILD, case)
    b = json.load(open(os.path.join(d, 'build.json')))
    rd = lambda f: open(os.path.join(d, f), 'rb').read()   # noqa: E731
    return d, b, rd


def mechanical(case):
    d, b, rd = load(case)
    orders = tuple(b['orders'])
    rt = gen_readable.role_text(b['edits'], case, orders, b['N'], b['loop_bound'],
                                b['reader_code'], *b['slice'])
    typed = T.rename(rt, b['letters'])
    assert (typed + '\n').encode() == rd('a.py'), 'a.py is not the template renamed'
    long_src = gen_readable.readable(b['edits'], case, orders, b['N'], b['loop_bound'],
                                     b['reader_code'], *b['slice'])
    assert long_src.encode() == rd('readable.py'), 'readable.py is not gen_readable\'s output'
    inv = {v: k for k, v in T.LONG_NAMES.items()}
    assert T.check_ast_equal(long_src, rt, inverse_a=inv), 'long form ast != template ast'
    return 'a.py == template renamed; readable.py == gen_readable; long-form ast == template ast'


def program(case):
    d, b, rd = load(case)
    data = rd('data.txt').decode().split('\n')[:-1]
    with tempfile.TemporaryDirectory() as td:
        open(os.path.join(td, 'a.py'), 'wb').write(rd('a.py'))
        open(os.path.join(td, 'readable.py'), 'wb').write(rd('readable.py'))
        outs = []
        for name in ('a.py', 'readable.py'):
            p = subprocess.run([M.PY, name], input='\n'.join(data) + '\n', capture_output=True,
                               text=True, cwd=td, timeout=900)
            bp = os.path.join(td, 'b.py')
            got = open(bp, 'rb').read() if os.path.exists(bp) else None
            if got is not None:
                os.remove(bp)
            assert p.returncode == 0 and p.stderr == '', (name, p.returncode, p.stderr[-1000:])
            outs.append((p.stdout, got))
    (s1, b1), (s2, b2) = outs
    assert s1 == s2, 'the screens differ'
    assert b1 == b2 == rd('b.py'), 'b.py differs'
    return f'same screen ({len(s1.splitlines())} lines), b.py byte-identical ({len(b1)} B)'


def functions(case, n_check=1000):
    d, b, rd = load(case)
    L = b['letters']
    ty = M.defs(rd('a.py').decode())
    lf = M.defs(rd('readable.py').decode())
    tk, lk = ty[L['Check']], lf[T.LONG_NAMES['Check']]
    td, ld = ty[L['Dec']], lf[T.LONG_NAMES['Dec']]
    alpha = T.ALPHABETS[case]
    rng = random.Random(20261021)
    for _ in range(n_check):
        n = rng.randrange(0, 1 << 20)
        t = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 90)))
        want = n
        for c in t:
            want = (want + c) * 1000003 % 1048576
        want = ''.join(alpha[want >> s & 31] for s in (15, 10, 5, 0))
        assert tk(n, t) == lk(n, t) == want, (n, t)
    orders = tuple(b['orders'])
    num = 0
    for line in rd('data.txt').decode().split('\n')[:-1]:
        for c in line[:-4]:
            num = num * 32 + alpha.index(c)
    apy = rd('a.py').decode().strip().encode()
    r1 = td(num, b['N'], apy)
    assert r1 == ld(num, b['N'], apy) and M.check(0, r1.decode(), alpha) == b['reader_code']
    txt = bytes(rng.choice(b'abcdefghijklmnopqrstuvwxyz (),:=0123456789\n') for _ in range(3000))
    x = M.cm2_enc.encode_int(txt, rd('b.py'), orders)
    assert td(x, len(txt), rd('b.py')) == ld(x, len(txt), rd('b.py')) == txt
    kx, kn, kp, kd = M.kat_vectors()[-1]
    assert td(kx, kn, kp, T.LONG_TUPLE) == ld(kx, kn, kp, T.LONG_TUPLE) == kd
    return (f'k equal on {n_check} random byte strings and line numbers; d equal on 3 payloads '
            f'(the reader {len(r1)} B, a text of {len(txt)} B primed with b.py, a KAT vector of '
            f'{kn} B at the long tuple)')


def committed(case):
    if case not in COMMITTED:
        return 'none kept for this case (generated)'
    _, _, rd = load(case)
    s = open(COMMITTED[case], 'rb').read()
    end = COMMITTED_END.encode()
    assert s.count(end) == 1, 'the committed long form has no header marker'
    assert s.split(end, 1)[1] == rd('readable.py'), 'the committed long form is not the build\'s readable.py'
    return f"{os.path.basename(COMMITTED[case])} minus its header == the build's readable.py"


def run(case):
    return dict(case=case, mechanical=mechanical(case), program=program(case),
                functions=functions(case), committed=committed(case))


def test_lower():
    run('lower')


def test_upper():
    run('upper')


if __name__ == '__main__':
    a = sys.argv[1:]
    cases = [a[i + 1] for i, x in enumerate(a) if x == '--case'] or ['lower', 'upper']
    if '--build' in a:
        BUILD = os.path.abspath(a[a.index('--build') + 1])
    for c in cases:
        r = run(c)
        print(f'[{c}] PASS mechanical: {r["mechanical"]}')
        print(f'[{c}] PASS program: {r["program"]}')
        print(f'[{c}] PASS functions: {r["functions"]}')
        print(f'[{c}] PASS committed: {r["committed"]}')
