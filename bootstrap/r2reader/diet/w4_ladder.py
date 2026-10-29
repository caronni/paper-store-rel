"""w4_ladder.py -- run rungs on the envelope and tabulate (never typed).

  python w4_ladder.py run NAME [NAME ...]    v1/NAME.py on the envelope ->
                                             build/w4/env-NAME.json
  python w4_ladder.py table [NAME ...]       the ladder table (markdown) from
                                             those files, + ladder-2026-10-20.json
Rung sizes: the typed reader text (make_typed.reader_text) with comments
and blank lines stripped (the minifier's first step; the readable rungs
carry prose the typed reader will not), cm2 with primer = loader/a.py,
base-32 glyphs, 60-glyph data lines.  'done' counts cases whose payload
closed; 'blocks' sums the blocks accepted over every frame of every case.
"""
import io
import json
import os
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import w4_harness as wh  # noqa: E402

V1 = os.path.join(HERE, 'v1')
CLOSABLE_NOT = ('one.dmg-beall', 'one.dmg-scratch-d-dark', 'dmg scr-d-white s2')
PARTIAL = ('closeup', 'near')


def code_only(text):
    """comments and blank lines removed (tokenize: COMMENT tokens)."""
    toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    lines = text.splitlines(keepends=True)
    for t in reversed(toks):
        if t.type == tokenize.COMMENT:
            (r, c0), (_, c1) = t.start, t.end
            lines[r - 1] = lines[r - 1][:c0].rstrip() + lines[r - 1][c1:]
    return ''.join(l for l in lines if l.strip())


def size(path, n2=13854):
    t = code_only(wh.text_of(path, n2, 3000000000)).encode()
    z = len(wh.cm2_enc.encode(t, wh.APY.strip().encode(), wh.ORDERS))
    g = -(-z * 8 // 5)
    return dict(raw=len(t), cm2=z, glyphs=g, lines=-(-g // 60))


FROZEN_NOT = ('one.dmg-be_all', 'dmg scr-d-white s2')


def run(name):
    """W4_ENV=frozen: the envelope on build/w4/w1frozen, results as
    env-F-NAME.json."""
    frozen = os.environ.get('W4_ENV') == 'frozen'
    path = os.path.join(V1, name + '.py')
    tag = ('F-' if frozen else '') + name
    res = wh.run_cases(tag, path, wh.env_cases_frozen() if frozen else wh.env_cases())
    out = dict(reader=os.path.relpath(path, wh.ROOT), size=size(path), cases=res,
               envelope='frozen' if frozen else 'w1-0033')
    json.dump(out, open(os.path.join(wh.OUT, f'env-{tag}.json'), 'w'), indent=1)
    print(tag, out['size'], summary(res, frozen))


def summary(res, frozen=False):
    nc = FROZEN_NOT if frozen else CLOSABLE_NOT
    closable = [c for c in res if c not in nc and not c.startswith(PARTIAL)]
    done = sum(res[c]['done'] for c in closable)
    part = sum(sum(b or 0 for b in res[c]['blocks']) for c in res if c.startswith(PARTIAL))
    blocks = sum(sum(b or 0 for b in r['blocks']) for r in res.values())
    secs = [s for r in res.values() for s in r['secs']]
    whole = [r['secs'][0] for c, r in res.items() if len(r['secs']) == 1
             and not c.startswith(PARTIAL) and not c.startswith('loupe') and not r['done']] or [0]
    return dict(done=f'{done}/{len(closable)}', blocks=blocks, partial_blocks=part,
                failed=[c for c in closable if not res[c]['done']],
                secs_total=round(sum(secs), 1))


def table(names):
    rows = ['| rung | raw | cm2 | glyphs | data lines | done (closable cases) | blocks accepted (all frames) | '
            'close-up + near blocks | s total | failed closable cases |',
            '|---|---|---|---|---|---|---|---|---|---|']
    led = {}
    for n in names:
        p = os.path.join(wh.OUT, f'env-{n}.json')
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        s, m = size(os.path.join(wh.ROOT, d['reader'])), summary(d['cases'], d.get('envelope') == 'frozen')
        led[n] = dict(size=s, summary=m, cases={c: dict(done=r['done'], blocks=r['blocks'],
                                                         held=r['held'], need=r['need'],
                                                         secs=r['secs'])
                                                for c, r in d['cases'].items()})
        rows.append(f"| {n} | {s['raw']} | {s['cm2']} | {s['glyphs']} | {s['lines']} | {m['done']} | "
                    f"{m['blocks']} | {m['partial_blocks']} | {m['secs_total']} | "
                    f"{', '.join(m['failed'])} |")
    print('\n'.join(rows))
    return led


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'run':
        for n in a[1:]:
            run(n)
    elif a[0] == 'table':
        out = None
        if '--json' in a:
            i = a.index('--json')
            out = a[i + 1]
            del a[i:i + 2]
        names = a[1:] or sorted(f[4:-5] for f in os.listdir(wh.OUT)
                               if f.startswith('env-') and f.endswith('.json'))
        led = table(names)
        if out:
            json.dump(dict(primer='loader/a.py', primer_bytes=len(wh.APY.strip()),
                           envelope_w1_0033=list(wh.env_cases()), envelope_frozen=list(wh.env_cases_frozen()), rungs=led),
                      open(out, 'w'), indent=1)
