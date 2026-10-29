"""w4_sets.py -- the owner's acceptance SETS for the simplified reader
(2026-10-20 night ruling: "Simplify the reader! We need good enough recovery,
not perfect."), never typed.

A set passes when its payload closes from the set's frames pooled (in the
order given); a frame may read only part of its blocks.  All frames are the
generator's page `one` (and the two-page pair) as frozen in build/w4/w1f4
(the fourth set, block CRC bound to the header) plus frames rendered here
from the frozen pages with the generator's camera (build/w4/sets4/).

  A  one.nominal-b030 alone
  B  one.flatbed300 alone
  C  the four quarters (3 spm, sigma 0.45) pooled
  D  two whole-page shots at 2 spm sigma 0.45, seeds 1 and 2, pooled
  E  rot90-1, rot90-2, rot90-3, rot+4, rot-4, each alone
  F  each damage render (be_all excluded) first, then one.nominal-b030
  G  the two-page payload from its two nominal frames
  H  the loupe grid with 0.2 % flips (flip seed 2; seed 1 is in the margin:
     its chunk 128 has two flips in every copy, see w4_flipcheck.py)
Margin (reported, not acceptance): A at seeds 2 and 3, D at seeds 3 + 4,
C at seed 2, rot +-4 at seed 2, the loupe grid at seed 2, and every F
damage frame ALONE (whether the clean frame was needed).

  python w4_sets.py make                 freeze pages, render the extras
  python w4_sets.py run NAME [NAME ...]  v1/NAME.py on every set ->
                                         build/w4/sets-NAME.json
  python w4_sets.py table NAME ...       the table (+ --json PATH)
Env: W4_JOBS (default 5), W4_COMPAT_E=1 for rungs that use the v2 loader e.
"""
import json
import os
import random
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import w4_harness as wh  # noqa: E402

F = os.path.join(wh.OUT, 'w1f4')     # the generator's fourth set (block CRC bound to the header)
PAGES = os.path.join(F, 'pages')
SETS = os.path.join(wh.OUT, 'sets4')
V1 = os.path.join(HERE, 'v1')
DAMAGE = ['one.dmg-be_0', 'one.dmg-bt_7', 'one.dmg-blot_3', 'one.dmg-ring-centre',
          'one.dmg-ring-bullseye_0', 'one.dmg-scratch-h-white', 'one.dmg-scratch-d-dark',
          'one.dmg-scratch-e-dark', 'one.dmg-torn_3', 'one.dmg-crop-T',
          'one.dmg-scratch-d-dark_15', 'one.dmg-scratch-d-dark_30',
          'one.dmg-scratch-e-dark_30', 'one.dmg-scratch-v-dark_15', 'one.dmg-torn_3_120',
          'one.dmg-blot-at_179_255_40']
NOM = ['--preset', 'nominal']
Q = NOM + ['--spm', '3', '--blur', '0.45', '--persp', '0.02']
EXTRA = {   # name: (page, camera args)
    'one.n045-s2': ('one', NOM + ['--blur', '0.45', '--seed', '2']),
    'one.n045-s3': ('one', NOM + ['--blur', '0.45', '--seed', '3']),
    'one.n045-s4': ('one', NOM + ['--blur', '0.45', '--seed', '4']),
    'one.n030-s2': ('one', NOM + ['--blur', '0.30', '--seed', '2']),
    'one.n030-s3': ('one', NOM + ['--blur', '0.30', '--seed', '3']),
    'one.r+4-s2': ('one', NOM + ['--blur', '0.30', '--rotate', '4', '--seed', '2']),
    'one.r-4-s2': ('one', NOM + ['--blur', '0.30', '--rotate', '-4', '--seed', '2']),
}
for _q in ('tl', 'tr', 'bl', 'br'):
    EXTRA[f'one.q{_q}-s2'] = ('one', Q + ['--frame', _q, '--seed', '2'])


def f(n):
    return os.path.join(F, n + '.pgm')


def x(n):
    return os.path.join(SETS, n + ('.txt' if 'loupe' in n else '.pgm'))


def cam(args):
    name, page, argv = args
    import camera  # noqa: E402  (bootstrap/r2)
    out = os.path.join(SETS, name + '.pgm')
    if not os.path.exists(out):
        camera.main([os.path.join(PAGES, page + '.pbm'), out,
                     '--sidecar', os.path.join(PAGES, page + '.json')] + argv)
    return name


def loupe(name, page, flips, seed):
    rows = [ln.strip() for ln in open(os.path.join(PAGES, page + '.grid.txt'))]
    rng = random.Random(seed)
    g = [[int(c) ^ (rng.random() < flips) for c in r] for r in rows]
    open(os.path.join(SETS, name + '.txt'), 'w').write(
        ''.join(''.join('01'[v] for v in r) + '\n' for r in g))


# page_sha256 of build/w4/w1f4/<page>.nominal-b030.json, frozen here 2026-10-23
PAGE_SHA256 = {
    'one': 'b54e11adc7f8e54ad5d0329c30306a58e5032debab13c1f78d764381a0ceca3c',
    'two_p0': '7eb3f0a9937831673d11f757605e828110be5c1dc1ea91931d188708b9dc4c9f',
    'two_p1': '8646f42d71c37ddf8021792a551ca5946e20294afc73cd60b84de90d9284eb7a',
}


def make():
    import hashlib
    os.makedirs(PAGES, exist_ok=True)
    os.makedirs(SETS, exist_ok=True)
    src = os.path.join(wh.ROOT, 'build', 'w1', 'pages')
    for p in ('one', 'two_p0', 'two_p1'):
        want = PAGE_SHA256[p]
        side = f(p + '.nominal-b030')[:-4] + '.json'
        if os.path.exists(side):
            assert json.load(open(side))['page_sha256'] == want, (p, 'frozen render disagrees')
        got = hashlib.sha256(open(os.path.join(src, p + '.pbm'), 'rb').read()).hexdigest()
        assert got == want, (p, 'build/w1/pages moved on since the frozen renders')
        for ext in ('.pbm', '.json', '.grid.txt'):
            shutil.copy2(os.path.join(src, p + ext), os.path.join(PAGES, p + ext))
    sys.path.insert(0, os.path.join(wh.ROOT, 'r2'))
    with ProcessPoolExecutor(4) as ex:
        print(list(ex.map(cam, [(n, p, a) for n, (p, a) in EXTRA.items()])))
    loupe('one.loupe02-s1', 'one', 0.002, 1)
    loupe('one.loupe02-s2', 'one', 0.002, 2)


def sets():
    """-> {set: {case: frames}}, required sets first, then the margin."""
    s = {
        'A': {'A nominal-b030': [f('one.nominal-b030')]},
        'B': {'B flatbed300': [f('one.flatbed300')]},
        'C': {'C quarters': [f('one.q-' + q) for q in ('tl', 'tr', 'bl', 'br')]},
        'D': {'D 2 x sigma 0.45': [f('one.nominal-b045'), x('one.n045-s2')]},
        'E': {f'E {n}': [f('one.' + n)] for n in ('rot90-1', 'rot90-2', 'rot90-3',
                                                   'rot+4', 'rot-4')},
        'F': {f'F {n[8:]}': [f(n), f('one.nominal-b030')] for n in DAMAGE},
        'G': {'G two pages': [f('two_p0.nominal-b030'), f('two_p1.nominal-b030')]},
        'H': {'H loupe 0.2 %': [x('one.loupe02-s2')]},
        'I': set_i(),
        'margin': {
            'm A seed 2': [x('one.n030-s2')], 'm A seed 3': [x('one.n030-s3')],
            'm D seeds 3+4': [x('one.n045-s3'), x('one.n045-s4')],
            'm C seed 2': [x('one.q' + q + '-s2') for q in ('tl', 'tr', 'bl', 'br')],
            'm rot+4 seed 2': [x('one.r+4-s2')], 'm rot-4 seed 2': [x('one.r-4-s2')],
            'm H seed 1 (chunk 128: 2 flips in every copy)': [x('one.loupe02-s1')],
            'm sigma 0.45 alone': [f('one.nominal-b045')],
            'm C turned quarter': [f('one.q-tl-rot90-1')] + [f('one.q-' + q)
                                                            for q in ('tr', 'bl', 'br')],
            **{f'm F alone {n[8:]}': [f(n)] for n in DAMAGE}},
    }
    return s


P2 = os.path.join(wh.OUT, 'p2f4')     # the last page, regenerated by w4_lastpage.py
P2_PARTIAL = ('q-tl', 'q-tr', 'q-bl', 'q-br', 'centre', 'q-br-2spm')
P2_WHOLE = ('nominal-b045', 'hard-b030')
P2_MORE = ('nominal-b030', 'flatbed300')


def p2(n):
    return os.path.join(P2, 'page_p2.' + n + '.pgm')


def truth(frame):
    """(data blocks wholly in frame, the set of their chunks) from the
    render's homography_grid_modules_to_px and the page sidecar (the 18 x 18
    lattice of the block inside the image, as bootstrap/r2/genie.py)."""
    import numpy as np
    tj = json.load(open(frame[:-4] + '.json'))
    side = json.load(open(os.path.join(os.path.dirname(frame), tj['page_sidecar'])))
    Hm = np.array(tj['homography_grid_modules_to_px'])
    w, h = tj['size_px']
    n, ch = 0, set()
    for s, (bi, bj) in enumerate(side['slot_block']):
        c = side['slot_chunk'][s]
        if c is None:
            continue
        ok = True
        for r in (17 * bi + .5, 17 * bi + 17.5):
            for cc in (17 * bj + .5, 17 * bj + 17.5):
                v = Hm @ [cc, r, 1]
                x, y = v[0] / v[2] - .5, v[1] / v[2] - .5
                ok = ok and 0 <= x <= w - 1.001 and 0 <= y <= h - 1.001
        if ok:
            n, ch = n + 1, ch | {c}
    return n, ch


def set_i():
    c = {'I pooled partials': [p2(n) for n in P2_PARTIAL]}
    for n in P2_WHOLE:
        c['I whole ' + n] = [p2(n)]
    for n in P2_PARTIAL + P2_MORE:
        c['m I alone ' + n] = [p2(n)]
    return c


def slot_pass(name, rung=None):
    """the pooled data-slot coverage of the six partial frames, in process
    (w4_slots.py's spy on read_block, so a READABLE rung): -> build/w4/
    slots-NAME.json.  rung: measure that rung and file it under name (a
    minified reader proved identical in reads to its rung)."""
    import w4_slots
    ns = w4_slots.ns_of(os.path.join(V1, (rung or name) + '.py'))
    U, R, per, known = set(), set(), {}, None
    for n in P2_PARTIAL:
        inf, read, known = w4_slots.slots(ns, p2(n), known)
        U, R = U | inf, R | read
        per[n] = [len(inf), len(read & inf), sorted(inf - read)]
    out = dict(rung=rung or name, union=len(U), read=len(R & U), missed=sorted(U - R),
               per_frame=per)
    json.dump(out, open(os.path.join(wh.OUT, f'slots-{name}.json'), 'w'), indent=1)
    return out


def verdict_i(res, name=None):
    """the six partial frames pooled read every data slot that lies in some
    frame, within 3 (slots-NAME.json); each whole frame alone holds the
    page's 45 chunks (every chunk printed on the page: chunks_on_page since
    the copies went across pages, 2026-10-20 night; chunk_count on the
    frozen pages before it).  -> (pass or None if no slot pass yet, note)"""
    side = json.load(open(os.path.join(P2, 'page_p2.json')))
    held = side.get('chunks_on_page', side['chunk_count'])
    ok = all((res['I whole ' + n]['held'] or 0) == held for n in P2_WHOLE)
    sp = os.path.join(wh.OUT, f'slots-{name}.json')
    if not name or not os.path.exists(sp):
        return (None if ok else False), 'whole frames ' + ('ok' if ok else 'short')
    s = json.load(open(sp))
    return ok and s['read'] >= s['union'] - 3, f"slots {s['read']}/{s['union']}"


REQUIRED = 'ABCDEFGHI'


def run(name):
    path = os.path.join(V1, name + '.py')
    cases = {c: fr for st in sets().values() for c, fr in st.items()}
    res = wh.run_cases('S-' + name, path, cases)
    from w4_ladder import size
    out = dict(reader=os.path.relpath(path, wh.ROOT), size=size(path), cases=res)
    json.dump(out, open(os.path.join(wh.OUT, f'sets-{name}.json'), 'w'), indent=1)
    print(name, out['size'], verdict(res, name))


def verdict(res, name=None):
    out = {}
    for st, cases in sets().items():
        if st == 'margin':
            continue
        if st == 'I':
            out[st] = verdict_i(res, name)[0] if 'I pooled partials' in res else None
            out['I note'] = verdict_i(res, name)[1] if 'I pooled partials' in res else ''
        else:
            out[st] = all(res[c]['done'] for c in cases)
    out['all'] = all(out[s] for s in REQUIRED)
    m = sets()['margin']
    out['margin'] = f"{sum(res[c]['done'] for c in m if not c.startswith('m F alone'))}/" \
                    f"{sum(1 for c in m if not c.startswith('m F alone'))}"
    out['F alone'] = f"{sum(res[c]['done'] for c in m if c.startswith('m F alone'))}/{len(DAMAGE)}"
    out['secs'] = round(sum(s for c in res for s in res[c]['secs']), 1)
    out['blocks'] = sum(sum(b or 0 for b in r['blocks']) for r in res.values())
    return out


def table(names, js=None):
    from w4_ladder import size
    rows = ['| rung | raw | cm2 | glyphs | lines | A | B | C | D | E | F | G | H | I | I detail | all sets | '
            'margin | damage alone | blocks | s |', '|' + '---|' * 20]
    led = {}
    for n in names:
        d = json.load(open(os.path.join(wh.OUT, f'sets-{n}.json')))
        s, v = size(os.path.join(wh.ROOT, d['reader'])), verdict(d['cases'], n)
        led[n] = dict(size=s, verdict=v, cases={c: dict(done=r['done'], blocks=r['blocks'],
                                                         held=r['held'], need=r['need'],
                                                         secs=r['secs'])
                                                for c, r in d['cases'].items()})
        pf = ' | '.join({True: 'pass', False: '**FAIL**', None: 'n/a'}[v[k]] for k in REQUIRED)
        rows.append(f"| {n} | {s['raw']} | {s['cm2']} | {s['glyphs']} | {s['lines']} | {pf} | {v.get('I note', '')} | "
                    f"{'PASS' if v['all'] else 'fail'} | {v['margin']} | {v['F alone']} | "
                    f"{v['blocks']} | {v['secs']} |")
    print('\n'.join(rows))
    if js:
        json.dump(dict(primer='loader/a.py', sets={k: list(v) for k, v in sets().items()},
                       rungs=led), open(js, 'w'), indent=1)


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'make':
        make()
    elif a[0] == 'run':
        for n in a[1:]:
            run(n)
    elif a[0] == 'slots':                 # NAME [RUNG]
        print(json.dumps(slot_pass(a[1], a[2] if len(a) > 2 else None)))
    elif a[0] == 'runi':                  # set I only, printed per frame
        for n in a[1:]:
            res = wh.run_cases('I-' + n, os.path.join(V1, n + '.py'), set_i())
            ok, nu = verdict_i(res, n)
            print(n, 'set I', 'PASS' if ok else 'FAIL', f'(chunks in some partial frame: {nu})')
            for c, r in res.items():
                fr = r['frames'][-1]
                nb, ch = truth(os.path.join(wh.ROOT, fr))
                print(f'   {c:28s} read blocks {r["blocks"]} chunks held {r["held"]}; truth for '
                      f'{os.path.basename(fr)}: {nb} data blocks, {len(ch)} chunks; s {r["secs"]}')
    elif a[0] == 'table':
        js = None
        if '--json' in a:
            i = a.index('--json')
            js = a[i + 1]
            del a[i:i + 2]
        table(a[1:], js)
