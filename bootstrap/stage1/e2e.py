"""e2e.py -- stage 1 end to end, per case (ruling 43), on the build in
build/stage1/<case>/ (make_typed.py writes it).

A. The R2 pages against the NEW primer: payload = cm2 v2 (typed/cm2_enc.py)
   of build/bundle/b.py (the bundle of record, untouched) primed with this
   build's b.py at its default tuple, the state x as big-endian bytes;
   r2/gen.py pages, r2/verify_grid.py, and r2/camera.py renders of every
   page at nominal blur 0.30 (build.py's 'nominal-b030': --preset nominal
   --blur 0.30 --seed 1), into build/stage1/<case>/r2/.  gen.py's
   orientation refusal (exit 3) is reported, not padded around: padding
   would change the bundle, and c.py is compared with the bundle of record.
B. The typing, as bootstrap/loader/e2e_pipe.py does it: a.py written line by
   line into a fresh directory under an editor's convention, run as `PY
   a.py`, the data lines typed at the prompt with injected faults (each
   refused and retyped: the look-alikes 0->O/o, 1->L/l, 1->I/i, V->U/v->u,
   5->S/s, 2->Z/z in the print's case, a letter in the other case, a doubled
   line, a dropped line, a line from far away; accepted: a line with its
   group spaces, one with a trailing space, the last line as the leaf prints
   it).  Runs: pipes on env python (a.py typed LF) and homebrew python3 (a.py
   typed CRLF -- the CRLF positive: text mode makes it decode), a pty on env
   python (no final newline).  Asserted each time: the self-dump == codes.txt
   (and the codes recomputed here), the prompts as injected, exit 0 and
   silence after the last prompt, b.py == the build's b.py, the typed d
   decodes typed/kat_v2.json's vectors (the long tuple passed as w).
C. The chain: after each pipe run, in the same directory, ONE `PY b.py` (the
   reader, stage 2) fed the three pages' renders in order, then an empty
   line: exit 0, the last progress line 'done', c.py == build/bundle/b.py
   byte for byte; the progress lines (blocks accepted, chunks held) are kept.
   THE NEGATIVE: the same b.py re-saved with CRLF line ends, the same pages:
   exit 1 at the reader's B2 assert (AssertionError), no c.py.
Output: build/stage1/<case>/e2e.json, e2e.txt.
Usage: python e2e.py [--case lower|upper ...] [--no-pages] [--build DIR]  (default both
cases; --build: the build make_typed.py --build wrote, in place of build/stage1/)
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import template as T  # noqa: E402
import make_typed as M  # noqa: E402

PYS = ['env/bin/python', '/opt/homebrew/bin/python3']
EDITORS = {'LF': lambda ls: '\n'.join(ls) + '\n',
           'CRLF': lambda ls: '\r\n'.join(ls) + '\r\n',
           'no final newline': lambda ls: '\n'.join(ls)}
CHECK = 4
PROGRESS = re.compile(r'([^:]*): (?:([^:]*), )?(\d+) blocks(?: accepted)?, chunks (\d+) / (\S+) '
                      r'(?:- )?(done|more frames needed|more)\s*$')
# The typed reader from ruling 56 on (amended 2026-10-22): '9@ 500/557'
# after its prompt -- the seeds found, '@', chunks held / the header's total
# ('?' before a header) -- no name, no blocks count, no flag; 'cannot read'
# alone for a file that fails to load.  The older wordings still parse.
PROGRESS56 = re.compile(r'(?:^|\s)(\d+)@ (\d+)/(\S+)\s*$')
CANNOT56 = re.compile(r'(?:^|\s)cannot read\s*$')
TWINS = {'lower': (('0', 'o'), ('1', 'l'), ('1', 'i'), ('v', 'u'), ('5', 's'), ('2', 'z')),
         'upper': (('0', 'O'), ('1', 'L'), ('1', 'I'), ('V', 'U'), ('5', 'S'), ('2', 'Z'))}


def progress_lines(stdout, frames):
    """Per frame [name, note, blocks, held, total, flag] from a reader's
    stdout, every wording.  The older lines name the frame and carry the
    blocks and the flag.  The 9@ line (ruling 56) names no frame -- it is
    the frame typed in its turn -- and has no blocks (None) and no flag:
    'done' when held == total (the reader's own done signal is its exit with
    the output written), 'more' otherwise; 'cannot read' alone keeps the
    session's held and total."""
    per = []
    for ln in stdout.split('\n'):
        m = PROGRESS.search(ln)
        if m:
            per.append([m[1].strip(), m[2] or '', int(m[3]), int(m[4]),
                        int(m[5]) if m[5].isdigit() else m[5], m[6]])
            continue
        m, c = PROGRESS56.search(ln), CANNOT56.search(ln)
        if m or c:
            name = frames[len(per)] if len(per) < len(frames) else '?'
            if m:
                held, tot = int(m[2]), int(m[3]) if m[3].isdigit() else m[3]
                per.append([name, m[1] + '@', None, held, tot, 'done' if held == tot else 'more'])
            else:
                held, tot = (per[-1][3], per[-1][4]) if per else (0, '?')
                per.append([name, 'cannot read', None, held, tot, 'more'])
    return per


def code(n, t, alpha):
    """The ruled check, retyped: n = (n + ord(c)) * 1000003 mod 2**20."""
    for c in t:
        n = (n + ord(c)) * 1000003 % 2**20
    return alpha[n >> 15] + alpha[n >> 10 & 31] + alpha[n >> 5 & 31] + alpha[n & 31]


# ---- A. the pages ---------------------------------------------------------------
def pages(case, b):
    import gen
    d = os.path.join(M.BUILD, case, 'r2')
    os.makedirs(d, exist_ok=True)
    bundle = open(M.BUNDLE, 'rb').read()
    bpy = open(os.path.join(M.BUILD, case, 'b.py'), 'rb').read()
    z = M.cm2_enc.encode(bundle, bpy, tuple(b['orders']))
    open(os.path.join(d, 'payload.bin'), 'wb').write(z)
    p = subprocess.run([M.PY, os.path.join(ROOT, 'r2', 'gen.py'), 'pages', 'payload.bin', 'page'],
                       cwd=d, capture_output=True, text=True)
    rec = dict(payload_bytes=len(z), pages=gen.n_pages(len(z)),
               capacity_bytes=gen.geometry()['capacity_bytes'] * gen.n_pages(len(z)),
               chunks=gen.n_chunks(len(z)), gen_rc=p.returncode)
    if p.returncode:
        rec['gen_stderr'] = p.stderr.strip()[-300:]
        return rec, []
    grids = [f'page_p{q}.grid.txt' for q in range(rec['pages'])]
    v = subprocess.run([M.PY, os.path.join(ROOT, 'r2', 'verify_grid.py')] + grids
                       + ['--payload', 'payload.bin', '--pbm'], cwd=d, capture_output=True, text=True)
    rec['verify_grid'] = v.stdout.strip().split('\n')[-1]
    rec['verify_rc'] = v.returncode
    frames = []
    for q in range(rec['pages']):
        f = f'page_p{q}.nominal-b030.pgm'
        r = subprocess.run([M.PY, os.path.join(ROOT, 'r2', 'camera.py'), f'page_p{q}.pbm', f,
                            '--sidecar', f'page_p{q}.json', '--preset', 'nominal', '--blur',
                            '0.30', '--seed', '1'], cwd=d, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-1000:]
        frames.append(os.path.join(d, f))
    sides = [json.load(open(os.path.join(d, f'page_p{q}.json'))) for q in range(rec['pages'])]
    rec['chunks_per_page'] = [s['chunk_count'] for s in sides]
    rec['headroom_bytes'] = rec['capacity_bytes'] - len(z)
    return rec, frames


# ---- B. the typing -----------------------------------------------------------------
def sub1(t, x, y):
    i = t[:-CHECK].index(x)
    return t[:i] + y + t[i + 1:]


def grouped(t):
    p = t[:-CHECK]
    return ' '.join(p[i:i + 5] for i in range(0, len(p), 5)) + ' ' + t[-CHECK:]


def as_printed(t):
    return grouped(t)[:-CHECK - 1].ljust(71) + '  ' + t[-CHECK:]


def finder_stream(data, first, case):
    """e2e_pipe's injected faults, numbered from the first data line."""
    used, plan = set(), {}
    C = len(data)

    def pick(pred):
        for i, t in enumerate(data):
            if i not in used and 1 < i < C - 2 and pred(t):
                used.add(i)
                return i
        raise LookupError

    for x, y in TWINS[case]:
        plan[pick(lambda t: x in t[:-CHECK])] = ('refused-twin/typo', x, y)
    i_cap = pick(lambda t: any(c.isalpha() for c in t[:-CHECK]))
    c0 = next(c for c in data[i_cap][:-CHECK] if c.isalpha())
    plan[i_cap] = ('refused-other-case', c0, c0.swapcase())
    plan[pick(lambda t: True)] = ('doubled',)
    plan[pick(lambda t: True)] = ('dropped',)
    plan[pick(lambda t: True)] = ('wrong-position',)
    plan[pick(lambda t: True)] = ('accepted-grouped',)
    plan[pick(lambda t: True)] = ('accepted-trailing-space',)
    plan[C - 1] = ('accepted-as-printed-last',)
    out, prompts, log = [], [], []
    for i, t in enumerate(data):
        n = first + i
        p = plan.get(i, ('plain',))
        if p[0].startswith('refused-'):
            out += [sub1(t, p[1], p[2]), t]
            prompts += [n, n]
        elif p[0] == 'dropped':
            out += [data[i + 1], t]
            prompts += [n, n]
        elif p[0] == 'wrong-position':
            out += [data[(i + C // 2) % C], t]
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
            out.append(t)
            prompts.append(n + 1)
        if p[0] != 'plain':
            log.append((n,) + p)
    return out, prompts, log


class Pipe:
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


def kat_check(py, work, alines, letters):
    """The typed a.py's definitions (lines 2 .. before the self-dump line, as
    typed into the work directory) decode typed/kat_v2.json (long tuple)."""
    m = M.main_line(alines)
    defs = ''.join(t + '\n' for t in alines[1:m])
    nv = len(json.load(open(M.KATS))['vectors'])
    open(os.path.join(work, 'kat.py'), 'w').write(
        defs + 'import json\n'
        f"w=json.load(open({M.KATS!r}))['vectors']\n"
        f"print(sum({letters['Dec']}(int(x['x'],16),x['n'],bytes.fromhex(x['primer']),"
        f"{str(T.LONG_TUPLE).replace(' ', '')})==bytes.fromhex(x['data'])for x in w),len(w))\n")
    p = subprocess.run([py, 'kat.py'], capture_output=True, text=True, cwd=work, timeout=600)
    os.remove(os.path.join(work, 'kat.py'))
    return p.returncode == 0 and p.stdout.split() == [str(nv), str(nv)], nv


def read_pages(py, work, frames, bundle):
    """C. One `PY b.py` in the work directory, the frames typed in turn."""
    t0 = time.time()
    p = subprocess.run([py, 'b.py'], input=''.join(f + '\n' for f in frames) + '\n',
                       capture_output=True, text=True, cwd=work, timeout=3600)
    wall = time.time() - t0
    per = [[os.path.basename(x[0])] + x[1:] for x in progress_lines(p.stdout, frames)]
    cpy = os.path.join(work, 'c.py')
    got = open(cpy, 'rb').read() if os.path.exists(cpy) else None
    res = {
        f'PY b.py fed {len(frames)} page(s) in one run: exit 0, empty stderr':
            p.returncode == 0 and not p.stderr.strip(),
        "the last progress line says 'done'": bool(per) and per[-1][-1] == 'done',
        f'c.py == build/bundle/b.py ({len(bundle)} B)': got == bundle,
    }
    neg = tempfile.mkdtemp(prefix='s1-crlf-', dir=work)
    bpy = open(os.path.join(work, 'b.py'), 'rb').read()
    open(os.path.join(neg, 'b.py'), 'wb').write(bpy.replace(b'\n', b'\r\n'))
    q = subprocess.run([py, 'b.py'], input=''.join(f + '\n' for f in frames) + '\n',
                       capture_output=True, text=True, cwd=neg, timeout=3600)
    err = q.stderr.strip().split('\n')[-1] if q.stderr.strip() else ''
    nc = os.path.exists(os.path.join(neg, 'c.py'))
    res['b.py re-saved with CRLF: exit 1 at AssertionError, no c.py'] = (
        q.returncode == 1 and err.startswith('AssertionError') and not nc)
    shutil.rmtree(neg)
    info = dict(per_frame=per, blocks=None if any(x[2] is None for x in per) else sum(x[2] for x in per),
                held=per[-1][3] if per else 0, need=per[-1][4] if per else '?', wall_s=round(wall, 1),
                crlf=dict(rc=q.returncode, err=err, c_py=nc))
    return res, info


def run_pipe(py, editor, alines, lines, prompts, codes, want_bpy, letters, frames, bundle, tmp):
    work = tempfile.mkdtemp(prefix='s1-e2e-', dir=tmp)
    open(os.path.join(work, 'a.py'), 'wb').write(EDITORS[editor](alines).encode())
    nl = len(alines)
    ch = Pipe([py, 'a.py'], work)
    ch.settle(0)
    head = bytes(ch.buf).decode()
    dump, seen = head.split('\n')[:nl], ['\n'.join(head.split('\n')[nl:])]
    for i, t in enumerate(lines):
        mark = ch.size()
        ch.type(t)
        if i < len(lines) - 1:
            ch.settle(mark)
            seen.append(bytes(ch.buf[mark:]).decode())
    ch.p.stdin.close()
    rc = ch.p.wait(timeout=3600)
    for th in ch.threads:
        th.join()
    tail = bytes(ch.buf[mark:]).decode()
    bp = os.path.join(work, 'b.py')
    got = open(bp, 'rb').read() if os.path.exists(bp) else None
    res = {
        'self-dump == codes.txt': dump == codes[:nl],
        'prompts as injected': seen == [f'[{n}]' for n in prompts],
        'exit 0, silent after the last prompt, empty stderr': rc == 0 and tail == '' and not ch.err,
        "b.py == the build's b.py": got == want_bpy,
    }
    ok, nv = kat_check(py, work, alines, letters)
    res[f"the typed d decodes the {nv} KAT vectors (long tuple as w)"] = ok
    info = dict(interpreter=py, editor=editor, lines_typed=len(lines), prompts=len(seen),
                refused=len(seen) - len(set(seen)))
    if frames and got is not None:
        more, rinfo = read_pages(py, work, frames, bundle)
        res.update(more)
        info['read'] = rinfo
    info['checks'] = res
    if all(res.values()):
        shutil.rmtree(work)
    else:
        info['work_kept'] = work
        info['stderr'] = bytes(ch.err).decode()[-2000:]
    return all(res.values()), info


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


def run_pty(py, editor, alines, lines, prompts, codes, want_bpy, tmp):
    work = tempfile.mkdtemp(prefix='s1-e2e-pty-', dir=tmp)
    open(os.path.join(work, 'a.py'), 'wb').write(EDITORS[editor](alines).encode())
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
    while time.time() - t0 < 1800:
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
    bp = os.path.join(work, 'b.py')
    res = {
        'self-dump == codes.txt': tl[:nl] == codes[:nl],
        'each line reads [n]<typed>': tl[nl:nl + len(want)] == want,
        'exit 0, nothing on the screen after the last line':
            status is not None and os.waitstatus_to_exitcode(status) == 0 and
            tl[nl + len(want):] == [''],
        "b.py == the build's b.py": os.path.exists(bp) and open(bp, 'rb').read() == want_bpy,
    }
    info = dict(interpreter=py, editor=editor, tty=True, checks=res)
    if all(res.values()):
        shutil.rmtree(work)
    else:
        info['work_kept'] = work
        info['screen_tail'] = tl[-20:]
    return all(res.values()), info


def run(case, with_pages=True):
    d = os.path.join(M.BUILD, case)
    b = json.load(open(os.path.join(d, 'build.json')))
    alpha = T.ALPHABETS[case]
    alines = open(os.path.join(d, 'a.py')).read().strip().split('\n')
    data = open(os.path.join(d, 'data.txt')).read().split('\n')[:-1]
    codes = open(os.path.join(d, 'codes.txt')).read().split('\n')
    want_bpy = open(os.path.join(d, 'b.py'), 'rb').read()
    bundle = open(M.BUNDLE, 'rb').read()
    letters = b['letters']
    rec = dict(case=case, codes_recomputed=codes[:len(alines)] == [
        f'{i} {code(i, t, alpha)}' for i, t in enumerate(alines, 1)])
    frames = []
    if with_pages:
        rec['pages'], frames = pages(case, b)
    first = b['first_data_line']
    lines, prompts, log = finder_stream(data, first, case)
    rec['injected'] = log
    tmp = os.path.join(d, 'tmp')
    os.makedirs(tmp, exist_ok=True)
    runs = []
    for py, editor in zip(PYS, ('LF', 'CRLF')):
        runs.append(run_pipe(py, editor, alines, lines, prompts, codes, want_bpy, letters,
                             frames, bundle, tmp))
    runs.append(run_pty(PYS[0], 'no final newline', alines, lines, prompts, codes, want_bpy, tmp))
    rec['runs'] = [r[1] for r in runs]
    rec['all_pass'] = rec['codes_recomputed'] and all(r[0] for r in runs) and (
        not with_pages or (rec['pages'].get('gen_rc') == 0 and rec['pages'].get('verify_rc') == 0))
    shutil.rmtree(tmp, ignore_errors=True)
    json.dump(rec, open(os.path.join(d, 'e2e.json'), 'w'), indent=1)
    out = [f'== stage 1 e2e, case {case}: {"ALL PASS" if rec["all_pass"] else "SOME FAILED"}',
           f'   codes.txt == the check recomputed here: {rec["codes_recomputed"]}']
    if with_pages:
        pg = rec['pages']
        out.append(f"   pages: payload {pg['payload_bytes']} B, {pg['pages']} pages, headroom "
                   f"{pg.get('headroom_bytes')} B, chunks {pg['chunks']} {pg.get('chunks_per_page')}, "
                   f"gen exit {pg['gen_rc']}, verify_grid: {pg.get('verify_grid')}")
    out += [f'   injected {x}' for x in log]
    for r in rec['runs']:
        out.append(f"== {'pty' if r.get('tty') else 'pipe'} {r['interpreter']} (a.py typed "
                   f"{r['editor']})" + (f": {r['lines_typed']} lines typed, {r['prompts']} prompts, "
                                         f"refused {r['refused']}" if 'prompts' in r else ''))
        if 'read' in r:
            rr = r['read']
            for f in rr['per_frame']:
                out.append(f'   b.py read {f[0]}: {f[1]}, {f[2]} blocks accepted, chunks {f[3]} / '
                           f'{f[4]} {f[5]}' if f[2] is not None else
                           f'   b.py read {f[0]}: {f[1]} {f[3]}/{f[4]}')   # the 9@ line (ruling 56)
            out.append(f"   CRLF b.py: exit {rr['crlf']['rc']}, {rr['crlf']['err']!r}, c.py "
                       f"{'written' if rr['crlf']['c_py'] else 'none'}")
        for k, v in r['checks'].items():
            out.append(f"   {'PASS' if v else 'FAIL'} {k}")
        if 'work_kept' in r:
            out.append(f"   work dir kept: {r['work_kept']}")
    open(os.path.join(d, 'e2e.txt'), 'w').write('\n'.join(out) + '\n')
    print('\n'.join(out), flush=True)
    return rec['all_pass']


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--build' in a:
        M.BUILD = os.path.abspath(a[a.index('--build') + 1])
    cases = [a[i + 1] for i, x in enumerate(a) if x == '--case'] or ['lower', 'upper']
    oks = [run(c, '--no-pages' not in a) for c in cases]
    sys.exit(0 if all(oks) else 1)
