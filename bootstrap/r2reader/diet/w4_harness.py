"""w4_harness.py -- run R2 v1 readers as the typed chain runs them (never typed).

The chain: r.py = the loader's definitions (loader/make_typed.py's typed
program, line 2 up to its main part: d = cm2, e = 'big', q, k) followed by
make_typed.reader_text(READER, N2) -- the reader's '# BEGIN READER' region
without its shared block, the token N2 replaced.  N2 = 1 here: the page data
of build/w1 are not a cm2 stream for this primer, so the tail's decode is
garbage either way; a read is judged by the progress line (every chunk held
and the data CRC equal to the header's = 'done'), not by b.py.

r.py runs in a fresh directory under build/w4/runs/, fed one frame path per
line, each written only after the previous progress line (seconds per frame
are wall-clock per frame), then an empty line.

  python w4_harness.py xcheck [READER]     STEP 0: every build/w1 render
  python w4_harness.py env READER [TAG]    the envelope (cases below)
  python w4_harness.py make-env            renders the extra envelope frames
                                           into build/w4/env/ (camera.py,
                                           test_render.py, loupe grids)
Results: build/w4/<tag>.json (+ a markdown table printed).
At most JOBS (default 5) reader processes at a time.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
R2R = os.path.dirname(HERE)
ROOT = os.path.dirname(R2R)                       # bootstrap/
W1 = os.path.join(ROOT, 'build', 'w1')
OUT = os.path.join(ROOT, 'build', 'w4')
ENV = os.path.join(OUT, 'env')
PY = 'env/bin/python'
JOBS = int(os.environ.get('W4_JOBS', '5'))
sys.path.insert(0, os.path.join(ROOT, 'loader'))
sys.path.insert(0, os.path.join(ROOT, 'typed'))
import make_typed  # noqa: E402
import cm2_enc  # noqa: E402

try:                                   # make_typed v3 (cm2 v2): typed(N, C, R)
    DEFS = make_typed.typed_defs(make_typed.typed(1, 1, 'xxxx'))
except TypeError:                      # v2: typed(S, N, C, R)
    DEFS = make_typed.typed_defs(make_typed.typed(1, 1, 1, 'xxxx'))
APY = open(os.path.join(ROOT, 'loader', 'a.py')).read()
ORDERS = cm2_enc.orders_of(os.path.join(ROOT, 'typed', 'cm2_dec.py'))


def text_of(reader, n2, b2):
    """the reader's typed text as make_typed takes it (region, shared block
    dropped), with the tokens N2 and B2 replaced where present (older rungs
    carry no B2)."""
    t = make_typed.drop_shared(make_typed.region(reader, '# BEGIN READER', '# END READER'))
    return make_typed.put_token(make_typed.put_token(t, 'N2', n2)[0], 'B2', b2)[0]


def rpy_of(reader, n2=0):
    """r.py for the read runs: N2 = 0 and B2 = 0, so the tail decodes b''
    (CRC-32 0) and its assert holds.  W4_COMPAT_E=1: also define e = 'big'
    (the v2 loader's name) for rungs written against the v2 loader; the
    delivered reader uses no e."""
    compat = "e='big'\n" if os.environ.get('W4_COMPAT_E') else ''
    return DEFS + compat + text_of(reader, n2, 0)


def size(reader, n2=13854):
    """raw bytes of the typed reader text, cm2 bytes with the primer =
    loader/a.py's text (stripped, as a.py hands it), base-32 glyphs, data
    lines of 60 glyphs."""
    t = text_of(reader, n2, 3000000000).encode()
    z = len(cm2_enc.encode(t, APY.strip().encode(), ORDERS))
    g = -(-z * 8 // 5)
    return dict(raw=len(t), cm2=z, glyphs=g, lines=-(-g // 60))


def parse(line):
    out = dict(raw=line)
    m = re.search(r'(\d+) blocks', line)
    c = re.search(r'chunks (\d+) / (\S+)', line)
    if m and c:
        out.update(blocks=int(m.group(1)), held=int(c.group(1)), need=c.group(2),
                   done=line.rstrip().endswith('done'),
                   header='header read' in line or 'unread' not in line)
    else:
        out['error'] = 'unparsed'
    return out


def run(rpy, frames, wd, timeout=1800):
    shutil.rmtree(wd, ignore_errors=True)
    os.makedirs(wd)
    open(os.path.join(wd, 'r.py'), 'w').write(rpy)
    p = subprocess.Popen([PY, 'r.py'], cwd=wd, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, bufsize=1)
    lines, secs = [], []
    for f in frames:
        t = time.time()
        try:
            p.stdin.write(f + '\n')
            p.stdin.flush()
        except BrokenPipeError:
            break
        ln = p.stdout.readline()
        secs.append(round(time.time() - t, 2))
        if not ln:
            break
        lines.append(ln.split('): ', 1)[-1].split(': ', 1)[-1].strip()
                     if 'stops' in ln else ln.strip())
        if ln.rstrip().endswith('done'):
            break
    try:
        p.stdin.write('\n')
        p.stdin.flush()
    except BrokenPipeError:
        pass
    so, se = p.communicate(timeout=timeout)
    return lines, secs, p.returncode, se


def job(args):
    tag, case, rpy, frames = args
    wd = os.path.join(OUT, 'runs', tag, case)
    t0 = time.time()
    lines, secs, rc, se = run(rpy, frames, wd)
    ps = [parse(l) for l in lines]
    last = ps[-1] if ps else {}
    res = dict(case=case, frames=[os.path.relpath(f, ROOT) for f in frames],
               lines=lines, secs=secs, exit=rc,
               blocks=[x.get('blocks') for x in ps],
               held=last.get('held'), need=last.get('need'),
               done=bool(last.get('done')), stderr=se[-600:],
               wall=round(time.time() - t0, 1))
    shutil.rmtree(wd, ignore_errors=True)
    return res


def run_cases(tag, reader, cases):
    rpy = rpy_of(reader)
    jobs = [(tag, c, rpy, fr) for c, fr in cases.items()]
    res = {}
    with ThreadPoolExecutor(JOBS) as ex:
        for r in ex.map(job, jobs):
            res[r['case']] = r
            print(f"{r['case']:28s} done={r['done']!s:5s} blocks={r['blocks']} "
                  f"chunks {r['held']}/{r['need']} secs={r['secs']} "
                  f"exit={r['exit']} {r['stderr'][-150:]!r}", flush=True)
    return res


# ---- STEP 0: the generator's renders ----------------------------------------
def w1(name):
    return os.path.join(W1, 'renders', name + '.pgm')


def xcheck_cases():
    rj = json.load(open(os.path.join(W1, 'renders.json')))['renders']
    cases = {r['name']: [w1(r['name'])] for r in rj}
    cases['POOL one quarters tl+tr+bl+br'] = [w1('one.q-' + q) for q in ('tl', 'tr', 'bl', 'br')]
    cases['POOL one quarters (tl turned)'] = [w1('one.q-tl-rot90-1')] + [
        w1('one.q-' + q) for q in ('tr', 'bl', 'br')]
    cases['POOL two pages p0+p1'] = [w1('two_p0.nominal-b030'), w1('two_p1.nominal-b030')]
    return cases, {r['name']: r['genie'] for r in rj}


def xcheck(reader):
    cases, genie = xcheck_cases()
    res = run_cases('xcheck', reader, cases)
    json.dump(res, open(os.path.join(OUT, 'xcheck.json'), 'w'), indent=1)
    rows = ['| case | frames | genie: data blocks CRC-ok at the true pose / in frame, headers ok | '
            'reader: blocks accepted per frame | header | chunks held / N | done | s per frame |',
            '|---|---|---|---|---|---|---|---|']
    for c, r in res.items():
        g = genie.get(c)
        gs = (f"{g['data_crc_ok']}/{g['data_in_frame']}, {g['headers_ok']}/{g['bullseyes_in_frame']}"
              if g else '-')
        hd = ['read' if 'header read' in l else 'unread' if 'unread' in l else '?'
              for l in r['lines']]
        rows.append(f"| {c} | {len(r['frames'])} | {gs} | {r['blocks']} | {hd} | "
                    f"{r['held']}/{r['need']} | {r['done']} | {r['secs']} |")
    md = '\n'.join(rows)
    open(os.path.join(OUT, 'xcheck.md'), 'w').write(md + '\n')
    print(md)


# ---- the envelope ------------------------------------------------------------
def env_cases():
    """The owner's envelope (build/w1 renders + build/w4/env extras)."""
    c = {}
    for n in ('one.nominal-b030', 'one.nominal-b045', 'one.hard-b030', 'one.flatbed300',
              'one.rot90-1', 'one.rot90-2', 'one.rot90-3', 'one.rot+4', 'one.rot-4',
              'one.dmg-be0', 'one.dmg-beall', 'one.dmg-bt7', 'one.dmg-blot3',
              'one.dmg-ring-centre', 'one.dmg-ring-bullseye0', 'one.dmg-scratch-h-white',
              'one.dmg-scratch-d-dark', 'one.dmg-torn3', 'one.dmg-crop-T'):
        c[n] = [w1(n)]
    c['pool one quarters'] = [w1('one.q-' + q) for q in ('tl', 'tr', 'bl', 'br')]
    c['pool one quarters (tl turned)'] = [w1('one.q-tl-rot90-1')] + [
        w1('one.q-' + q) for q in ('tr', 'bl', 'br')]
    c['pool two pages'] = [w1('two_p0.nominal-b030'), w1('two_p1.nominal-b030')]
    c['one.mid'] = [w1('one.mid')]
    if os.path.isdir(ENV):
        man = json.load(open(os.path.join(ENV, 'manifest.json')))
        for case, frames in man.items():
            c[case] = [os.path.join(ENV, f) for f in frames]
    return c


W1F = os.path.join(OUT, 'w1frozen')


def env_cases_frozen():
    """The envelope on a frozen copy of the generator's renders as regenerated
    at 02:54 (designed placement, new payload, renamed and extended damage
    set): build/w4/w1frozen.  The build/w4/env extras are unchanged (they
    are the earlier page, self-consistent per case)."""
    def f(n):
        return os.path.join(W1F, n + '.pgm')
    c = {}
    for n in ('one.nominal-b030', 'one.nominal-b045', 'one.hard-b030', 'one.flatbed300',
              'one.rot90-1', 'one.rot90-2', 'one.rot90-3', 'one.rot+4', 'one.rot-4',
              'one.nominal-b030-s101', 'one.dmg-be_0', 'one.dmg-be_all', 'one.dmg-bt_7',
              'one.dmg-blot_3', 'one.dmg-ring-centre', 'one.dmg-ring-bullseye_0',
              'one.dmg-scratch-h-white', 'one.dmg-scratch-d-dark', 'one.dmg-scratch-e-dark',
              'one.dmg-torn_3', 'one.dmg-crop-T', 'one.dmg-scratch-d-dark_15',
              'one.dmg-scratch-d-dark_30', 'one.dmg-scratch-e-dark_30',
              'one.dmg-scratch-v-dark_15', 'one.dmg-torn_3_120', 'one.dmg-blot-at_179_255_40',
              'one.mid'):
        c[n] = [f(n)]
    c['pool one quarters'] = [f('one.q-' + q) for q in ('tl', 'tr', 'bl', 'br')]
    c['pool one quarters (tl turned)'] = [f('one.q-tl-rot90-1')] + [
        f('one.q-' + q) for q in ('tr', 'bl', 'br')]
    c['pool two pages'] = [f('two_p0.nominal-b030'), f('two_p1.nominal-b030')]
    man = json.load(open(os.path.join(ENV, 'manifest.json')))
    for case, frames in man.items():
        c[case] = [os.path.join(ENV, x) for x in frames]
    return c


def env(reader, tag):
    res = run_cases(tag, reader, env_cases())
    out = dict(reader=os.path.relpath(reader, ROOT), size=size(reader), cases=res)
    json.dump(out, open(os.path.join(OUT, f'env-{tag}.json'), 'w'), indent=1)
    print(json.dumps(out['size']))
    print(f"done {sum(r['done'] for r in res.values())}/{len(res)}, "
          f"blocks {sum(sum(b or 0 for b in r['blocks']) for r in res.values())}")


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    a = sys.argv[1:]
    if a[0] == 'xcheck':
        xcheck(a[1] if len(a) > 1 else os.path.join(R2R, 'reader.py'))
    elif a[0] == 'env':
        env(a[1], a[2] if len(a) > 2 else os.path.basename(a[1])[:-3])
    elif a[0] == 'size':
        for f in a[1:]:
            print(f, size(f))
