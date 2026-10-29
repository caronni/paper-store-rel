"""e2e_pipe.py v3 -- the simulated finder (rulings of 2026-10-19 evening,
amended through 2026-10-20: the Horner line check, shared definitions d, q,
k (+ n, v), cm2 v2 (rANS: the typed number is the coder state x), r.py =
a[START:END] + reader written and read in binary, the reader's tail writes
b.py).

a.py is TYPED into a fresh directory -- its listing lines written one by one,
each run with another editor's convention (LF with a final newline; CRLF; no
final newline; two blank lines after the last) -- and run as `PY a.py`;
the data lines of data.txt are typed at its prompt [n] with injected faults.
Each is asserted through the prompt the program shows before every line (the
number of the line expected next):
  REFUSED, then retyped (the page forbids them; there is no fold):
    0->o, 1->l, 1->i, v->u, a capital letter, 5->s, 2->z in a payload;
    a doubled line (typed again at [n+1]); a dropped line (line n+1 typed at
    [n]); a wrong-position line (a line from far away typed at [n]);
  ACCEPTED first time:
    a line typed WITH its group spaces; a line with a trailing space (spaces
    are stripped before the check); the LAST line typed exactly as leaf 4
    prints it (groups, the padding that aligns its check, two spaces, the
    check).
Pipe run: a line is written only after the previous prompt has arrived, so
every prompt is captured on its own.  Asserted: self-dump == codes.txt (the
codes recomputed from the Horner check as ruled, independently of
make_typed, must equal codes.txt too); the [n] prompts exactly as
predicted; exit 0, nothing on stdout after the last prompt, nothing on
stderr; r.py == the expected bytes: a.py's lines from line 2 up to the first
line starting with `for(`, then the reader text (`--reader PATH`, shared
region dropped, N2 replaced as make_typed does), and == make_typed's
published r.py (OUT/r.py) when present.
AND the KATs: the typed a.py's own definitions (a[START:END], as written in
the work directory) run by PY decode every vector of typed/kat_v2.json.
THEN, in the same directory, ONE `PY r.py` run, every `--page PATH` typed at
its prompt in the order given, then an empty line: exit 0, empty stderr,
the last progress line ends with --done TEXT (default 'done': the data
closed), and b.py == --bundle PATH (N2 = its length, B2 = its CRC-32).  A
page set that misses a chunk leaves the data open: no 'done', no b.py, the
run FAILS (since the copies went across pages, 2026-10-20 night, any
P - 2 pages of a payload of P >= 3 pages carry every chunk, and either page
of a 2-page payload does).  THE
NEGATIVE: the same r.py re-saved with CRLF line ends, fed the same pages,
must exit 1 at the reader's B2 assert (AssertionError) and write no b.py.
Without --page there is no page run (said so); --page needs --bundle.
Pipe runs: env 3.14t and homebrew 3.14, with --more also 3.9, 3.10, 3.13,
3.14t -- every interpreter feeds all the pages.  TTY run (--pty, also part
of the default run): the same keystrokes typed line by line into `PY a.py`
on a pseudo-terminal (one run); every echoed line must read [n]<typed
text>, the program must exit 0 with nothing on the screen after the last
echoed line, and r.py == the expected bytes.
The typed files are loader/a.py, data.txt, codes.txt (the print of record:
whoever ran make_typed last), or those in --typed DIR (a snapshot);
--reader/--bundle must be the ones they were built from (the build.json
next to the r.py of --out says which).
Work directories live under --work DIR (default bootstrap/build/tmp/) and are
removed after a passing run (kept and named on a failure).
Usage: python e2e_pipe.py [--reader PATH] [--n2 BYTES | --bundle PATH]
                          [--page PATH ...] [--done TEXT] [--typed DIR]
                          [--out DIR] [--work DIR] [--pipe | --pty] [--more]
"""
import json
import os
import pty
import re
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import make_typed  # noqa: E402  (reader_text: the reader as make_typed takes it)

A = sys.argv[1:]


def opt(name, default=None):
    return A[A.index(name) + 1] if name in A else default


R2 = os.path.join(ROOT, 'build', 'r2')
KATS = os.path.join(ROOT, 'typed', 'kat_v2.json')
TMP = opt('--work', os.path.join(ROOT, 'build', 'tmp'))
TYPED = opt('--typed', HERE)            # where a.py, data.txt, codes.txt are read (the print of record)
OUT = opt('--out', make_typed.OUT)
PAGES = [os.path.abspath(A[i + 1]) for i, x in enumerate(A) if x == '--page']   # fed in sequence
#                                       to ONE r.py run (absolute: r.py runs in the work directory)
DONE = opt('--done', 'done')    # the reader's progress line ends with it when the data closes
PYS = ['env/bin/python', '/opt/homebrew/bin/python3']
MORE = ['/usr/bin/python3', '/opt/homebrew/bin/python3.10', '/opt/homebrew/bin/python3.13',
        '/opt/homebrew/bin/python3.14t']
RPATH = opt('--reader', make_typed.READER)
BUNDLE = open(opt('--bundle'), 'rb').read() if '--bundle' in A else None
N2 = int(opt('--n2')) if '--n2' in A else len(BUNDLE) if BUNDLE is not None else None
assert not PAGES or BUNDLE is not None, '--page needs --bundle PATH (the b.py the pages must give)'
B2 = zlib.crc32(BUNDLE) if BUNDLE is not None else None
READER = make_typed.reader_text(RPATH, N2, B2)
# The reader's two file literals: the primer it opens and the file it writes,
# r.py and b.py before ruling 34, b.py and c.py after (the stages named by the
# program each yields); a.py writes r.py, saved under the primer's name.
PRIMER = (re.search(r"open\('(\w\.py)', ?'rb'\)", READER) or [0, 'r.py'])[1]
WRITES = (re.search(r"open\('(\w\.py)', ?'wb'\)", READER) or [0, 'b.py'])[1]
os.makedirs(TMP, exist_ok=True)
CHECK = 4
ALPHA = '0123456789abcdefghjkmnpqrstvwxyz'
EDITORS = {'LF': lambda ls: '\n'.join(ls) + '\n',
           'CRLF': lambda ls: '\r\n'.join(ls) + '\r\n',
           'no final newline': lambda ls: '\n'.join(ls),
           'two blank lines after the last': lambda ls: '\n'.join(ls) + '\n\n\n'}


def code(n, t):
    """The ruled check, retyped: n = (n + ord(c)) * 1000003 mod 2**20."""
    for c in t:
        n = (n + ord(c)) * 1000003 % 2**20
    return ALPHA[n >> 15] + ALPHA[n >> 10 & 31] + ALPHA[n >> 5 & 31] + ALPHA[n & 31]


def expected_rpy(alines):
    """r.py by the line rule: lines 2 .. the line before the first that starts
    with 'for(', each with its newline, then the reader."""
    m = next(i for i, t in enumerate(alines) if t.startswith('for('))
    return (''.join(t + '\n' for t in alines[1:m]) + READER).encode()


def sub1(t, x, y):
    """Replace the first x in the payload of data line t by y."""
    i = t[:-CHECK].index(x)
    return t[:i] + y + t[i + 1:]


def grouped(t):
    p = t[:-CHECK]
    return ' '.join(p[i:i + 5] for i in range(0, len(p), 5)) + ' ' + t[-CHECK:]


def as_printed(t):
    """A data line as leaf 4 prints it (pages/compose_leaves.grouped)."""
    return grouped(t)[:-CHECK - 1].ljust(71) + '  ' + t[-CHECK:]


def finder_stream(data):
    """The typed data lines with faults injected, the prompt expected before
    each of them, and a log of the injections."""
    used, plan = set(), {}
    C = len(data)

    def pick(pred):
        for n, t in enumerate(data, 1):
            if n not in used and 2 < n < C - 1 and pred(t):
                used.add(n)
                return n
        raise LookupError

    for x, y in (('0', 'o'), ('1', 'l'), ('1', 'i'), ('v', 'u'), ('5', 's'), ('2', 'z')):
        plan[pick(lambda t: x in t[:-CHECK])] = ('refused-twin/typo', x, y)
    n_cap = pick(lambda t: any(c.isalpha() for c in t[:-CHECK]))
    c_cap = next(c for c in data[n_cap - 1][:-CHECK] if c.isalpha())
    plan[n_cap] = ('refused-capital', c_cap, c_cap.upper())
    plan[pick(lambda t: True)] = ('doubled',)
    nd = pick(lambda t: True)
    plan[nd] = ('dropped',)                    # line n+1 typed at [n]
    plan[pick(lambda t: True)] = ('wrong-position',)
    plan[pick(lambda t: True)] = ('accepted-grouped',)
    plan[pick(lambda t: True)] = ('accepted-trailing-space',)
    plan[C] = ('accepted-as-printed-last',)

    out, prompts, log = [], [], []
    for n, t in enumerate(data, 1):
        p = plan.get(n, ('plain',))
        if p[0].startswith('refused-'):
            out += [sub1(t, p[1], p[2]), t]
            prompts += [n, n]
        elif p[0] == 'dropped':
            out += [data[n], t]
            prompts += [n, n]
        elif p[0] == 'wrong-position':
            out += [data[(n + C // 2) % C], t]     # a line from the other half
            prompts += [n, n]
        elif p[0] == 'accepted-grouped':
            out.append(grouped(t))
            prompts.append(n)
        elif p[0] == 'accepted-trailing-space':
            out.append(t + ' ')
            prompts.append(n)
        elif p[0] == 'accepted-as-printed-last':
            out.append(as_printed(t))
            prompts.append(n)
        else:
            out.append(t)
            prompts.append(n)
        if p[0] == 'doubled':
            out.append(t)                        # typed again at [n+1]
            prompts.append(n + 1)
        if p[0] != 'plain':
            log.append((n,) + p)
    return out, prompts, log


class Pipe:
    """A child on pipes whose stdout and stderr are collected by threads."""

    def __init__(self, argv, cwd):
        self.p = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.buf, self.err = bytearray(), bytearray()
        self.lock = threading.Lock()
        self.threads = [threading.Thread(target=self._pump, args=(f, b), daemon=True)
                        for f, b in ((self.p.stdout, self.buf), (self.p.stderr, self.err))]
        for th in self.threads:
            th.start()

    def _pump(self, f, b):
        fd = f.fileno()
        while True:
            d = os.read(fd, 65536)
            if not d:
                return
            with self.lock:
                b.extend(d)

    def size(self):
        with self.lock:
            return len(self.buf)

    def settle(self, mark, timeout=60.0, quiet=0.05):
        """Wait for output past `mark`, then for it to go quiet."""
        t0 = time.time()
        while self.size() <= mark:
            if time.time() - t0 > timeout or self.p.poll() is not None:
                return
            time.sleep(0.002)
        last, t1 = self.size(), time.time()
        while time.time() - t1 < quiet:
            time.sleep(0.005)
            if self.size() != last:
                last, t1 = self.size(), time.time()

    def type(self, line):
        self.p.stdin.write(line.encode() + b'\n')
        self.p.stdin.flush()


def type_apy(work, alines, editor):
    open(os.path.join(work, 'a.py'), 'wb').write(EDITORS[editor](alines).encode())


def kat_check(py, work, alines):
    """The typed a.py's own definitions part (lines 2 .. before the first
    for( line, as typed into the work directory), run by PY, decode every
    vector of typed/kat_v2.json.  Returns (ok, vectors)."""
    m = next(i for i, t in enumerate(alines) if t.startswith('for('))
    defs = ''.join(t + '\n' for t in alines[1:m])
    kat = json.load(open(KATS))
    open(os.path.join(work, 'kat.py'), 'w').write(
        defs + 'import json\n'
        f"w=json.load(open({KATS!r}))['vectors']\n"
        "print(sum(d(int(x['x'],16),x['n'],bytes.fromhex(x['primer']))==bytes.fromhex(x['data'])"
        "for x in w),len(w))\n")
    p = subprocess.run([py, 'kat.py'], capture_output=True, text=True, cwd=work, timeout=600)
    os.remove(os.path.join(work, 'kat.py'))
    nv = len(kat['vectors'])
    return p.returncode == 0 and p.stdout.split() == [str(nv), str(nv)], nv


def run_reader(py, work, pages):
    """The finder's next step: ONE `PY r.py` in the same directory, every page
    path typed at its prompt in turn, then an empty line (which only matters
    if the data has not closed by then).  Asserted: exit 0, empty stderr, the
    last progress line says DONE (the data closed), and b.py == the bundle.
    Under ruling 34 r.py is run as b.py and the output is c.py (PRIMER, WRITES).
    Returns (checks, summary)."""
    if PRIMER != 'r.py':
        shutil.copyfile(os.path.join(work, 'r.py'), os.path.join(work, PRIMER))
    t0 = time.time()
    p = subprocess.run([py, PRIMER], input=''.join(pg + '\n' for pg in pages) + '\n',
                       capture_output=True, text=True, cwd=work, timeout=3600)
    wall = time.time() - t0
    # progress lines; a line that is only the next prompt (ending ': ') is not one
    progress = [t for t in p.stdout.split('\n') if t.strip() and not t.rstrip().endswith(':')]
    last = progress[-1] if progress else ''
    bpy = os.path.join(work, WRITES)
    res = {
        f'PY {PRIMER} fed {len(pages)} page(s) in one run: exit 0, empty stderr':
            p.returncode == 0 and not p.stderr.strip(),
        f'the last progress line says {DONE!r} (the data closed)': last.rstrip().endswith(DONE),
        f'{WRITES} == the bundle ({len(BUNDLE)} B)':
            os.path.exists(bpy) and open(bpy, 'rb').read() == BUNDLE,
    }
    summary = f'{len(progress)} progress line(s), last: {last[-120:]!r}  [{wall:.1f} s]'
    if p.stderr.strip():
        summary += '\n   stderr: ' + p.stderr.strip()[-400:]
    # The negative case (ruling B2): the same r.py re-saved with CRLF line ends
    # (an editor's save on Windows) is a different primer; the reader must
    # stop at its B2 assert and write no b.py.
    neg = tempfile.mkdtemp(prefix='e2e-crlf-', dir=TMP)
    rpy = open(os.path.join(work, 'r.py'), 'rb').read()
    open(os.path.join(neg, PRIMER), 'wb').write(rpy.replace(b'\n', b'\r\n'))
    q = subprocess.run([py, PRIMER], input=''.join(pg + '\n' for pg in pages) + '\n',
                       capture_output=True, text=True, cwd=neg, timeout=3600)
    err = q.stderr.strip().split('\n')[-1] if q.stderr.strip() else ''
    nb = os.path.exists(os.path.join(neg, WRITES))
    res[f'{PRIMER} re-saved with CRLF: exit 1 at AssertionError, no {WRITES}'] = (
        q.returncode == 1 and err.startswith('AssertionError') and not nb)
    summary += f"\n   CRLF {PRIMER}: exit {q.returncode}, last stderr line {err[-80:]!r}, {WRITES} {'written' if nb else 'none'}"
    shutil.rmtree(neg)
    return res, summary


def run_pipe(py, pages, lines, prompts, codes, alines, editor):
    work = tempfile.mkdtemp(prefix='e2e-loader-', dir=TMP)
    type_apy(work, alines, editor)
    nl = len(alines)
    ch = Pipe([py, 'a.py'], work)
    ch.settle(0)
    seen = []
    head = bytes(ch.buf).decode()
    dump, first = head.split('\n')[:nl], '\n'.join(head.split('\n')[nl:])
    seen.append(first)
    t_last = time.time()
    for i, t in enumerate(lines):
        mark = ch.size()
        t_last = time.time()
        ch.type(t)
        if i < len(lines) - 1:
            ch.settle(mark)
            seen.append(bytes(ch.buf[mark:]).decode())
    ch.p.stdin.close()
    rc = ch.p.wait(timeout=3600)
    decode_s = time.time() - t_last
    for th in ch.threads:
        th.join()
    tail = bytes(ch.buf[mark:]).decode()
    rpy = os.path.join(work, 'r.py')
    got = open(rpy, 'rb').read() if os.path.exists(rpy) else None
    res = {
        'self-dump == codes.txt': dump == codes[:nl],
        'prompts as injected': seen == [f'[{n}]' for n in prompts],
        'exit 0, silent after the last prompt, empty stderr':
            rc == 0 and tail == '' and not ch.err,
        'r.py == a.py lines 2 .. before the first for( line, then the reader':
            got == expected_rpy(alines),
    }
    pub = os.path.join(OUT, 'r.py')
    if os.path.exists(pub):
        res[f'r.py == make_typed\'s {os.path.relpath(pub, ROOT)}'] = got == open(pub, 'rb').read()
    summary = 'no page run (no --page given)'
    if pages:
        more, summary = run_reader(py, work, pages)
        res.update(more)
    ok, nv = kat_check(py, work, alines)
    res[f"the typed a.py's d decodes the {nv} KAT vectors of typed/kat_v2.json"] = ok
    print(f'== pipe {py} {"+".join(os.path.basename(p) for p in pages) or "-"} '
          f'(a.py typed {editor})')
    print(f'   {len(lines)} lines typed, {len(seen)} prompts, refused '
          f'{len(seen) - len(set(seen))}, exit {rc}, after last prompt {tail!r}, '
          f'decode after the last line {decode_s:.2f} s')
    print(f'   {PRIMER}:', summary)   # the primer's name: r.py run as b.py under ruling 34
    for k, v in res.items():
        print('  ', 'PASS' if v else 'FAIL', k)
    if not all(res.values()):
        print('   prompts seen', seen[:80])
        print(bytes(ch.err).decode()[-3000:])
        print('   work dir kept:', work)
    else:
        shutil.rmtree(work)
    return all(res.values())


def drain(fd, quiet, limit):
    buf, t_last, t0 = b'', time.time(), time.time()
    while time.time() - t0 < limit:
        r, _, _ = select.select([fd], [], [], 0.02)
        if r:
            try:
                d = os.read(fd, 65536)
            except OSError:
                break
            if not d:
                break
            buf += d
            t_last = time.time()
        elif buf and time.time() - t_last > quiet:
            break
    return buf


def run_pty(py, lines, prompts, codes, alines, editor):
    """PY a.py on a pseudo-terminal, the lines keyed one by one."""
    work = tempfile.mkdtemp(prefix='e2e-loader-pty-', dir=TMP)
    type_apy(work, alines, editor)
    nl = len(alines)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(work)
        os.execve(py, [py, 'a.py'], {'PATH': '/usr/bin:/bin', 'HOME': work,
                                     'TERM': 'xterm-256color'})
    out = drain(fd, 0.3, 30)
    for t in lines:
        os.write(fd, t.encode() + b'\r')
        out += drain(fd, 0.1, 30)
    t0, status = time.time(), None
    while time.time() - t0 < 1800:            # the decode runs after the last line
        out += drain(fd, 0.5, 2)
        got, st = os.waitpid(pid, os.WNOHANG)
        if got:
            status = st
            break
    else:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
    try:
        out += drain(fd, 0.2, 2)
    except OSError:
        pass
    os.close(fd)
    txt = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', out.decode('utf-8', 'replace')).replace('\r', '')
    tl = txt.split('\n')
    want = [f'[{p}]{t}' for p, t in zip(prompts, lines)]
    rpy = os.path.join(work, 'r.py')
    res = {
        'self-dump == codes.txt': tl[:nl] == codes[:nl],
        'each line reads [n]<typed>': tl[nl:nl + len(want)] == want,
        'exit 0, nothing on the screen after the last line':
            status is not None and os.waitstatus_to_exitcode(status) == 0 and
            tl[nl + len(want):] == [''],
        'r.py == definitions + reader':
            os.path.exists(rpy) and open(rpy, 'rb').read() == expected_rpy(alines),
    }
    print(f'== pty {py} (a.py typed {editor})')
    print('   screen, the first lines after the dump and the last:')
    for x in tl[nl:nl + 3] + ['...'] + tl[nl + len(want) - 2:]:
        print('     |', x)
    for k, v in res.items():
        print('  ', 'PASS' if v else 'FAIL', k)
    if not all(res.values()):
        print('\n'.join(tl[-20:]))
        print('   work dir kept:', work)
    else:
        shutil.rmtree(work)
    return all(res.values())


def main():
    alines = open(os.path.join(TYPED, 'a.py')).read().strip().split('\n')
    data = open(os.path.join(TYPED, 'data.txt')).read().split('\n')[:-1]
    codes = open(os.path.join(TYPED, 'codes.txt')).read().split('\n')
    nl = len(alines)
    ok = [codes[:nl] == [f'{i} {code(i, t)}' for i, t in enumerate(alines, 1)]]
    print('   codes.txt == the check recomputed here:', 'PASS' if ok[0] else 'FAIL')
    lines, prompts, log = finder_stream(data)
    for entry in log:
        print('   injected', entry)
    print(f'   {len(lines)} lines typed for {len(data)}; reader {os.path.relpath(RPATH, ROOT)}'
          f' (N2 {N2}); pages, one run each: {[os.path.basename(p) for p in PAGES] or "none"}')
    eds = list(EDITORS)
    if '--pty' not in sys.argv:
        runs = PYS + ([py for py in MORE if os.path.exists(py)] if '--more' in sys.argv else [])
        for i, py in enumerate(runs):
            ok.append(run_pipe(py, PAGES, lines, prompts, codes, alines, eds[i % len(eds)]))
    if '--pipe' not in sys.argv:
        ok.append(run_pty(PYS[0], lines, prompts, codes, alines, 'no final newline'))
    print('ALL PASS' if all(ok) else 'SOME FAILED')
    sys.exit(0 if all(ok) else 1)


if __name__ == '__main__':
    main()
