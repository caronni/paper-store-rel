"""search.py -- the rewrite search on a.py's own text (item 10) and the joint
name search (item 11), ruling 43 of 2026-10-21.  Reproducible: no RNG, a
fixed order of everything, the candidate list frozen in template.CANDIDATES.

The objective is the TYPED TOTAL: a.py characters + data glyphs + 4 check
glyphs per data line (newlines not counted, as the record counts).  Every
character of a.py is typed raw, so a spelling that saves one character saves
one typed character; and a.py is the primer of the data lines, so its
spelling and its single-letter names move the data glyphs at no a.py cost.
The coder is the exact one: the data are the cm2 v2 state x of the reader
(make_typed.the_reader(): r2reader/reader_lite_v1.py through its e2e copy,
N2 and B2 baked) with the candidate a.py as primer.  Decisions are taken on
the SMOOTH total, a.py characters + bits/5 * (1 + 4/60) from the model's
ideal code length (the exact state is within one bit of it, measured: 14,377
exact against 14,377.5 ideal on the print's reader), so a candidate is not
accepted or refused by where a glyph or a line boundary happens to fall;
every stage also reports the EXACT total (encode_int, base-32 digits,
ceil(G/60) lines).  The model is cm2_enc.model's (typed/cm2_enc.py); its
agreement with compressor-exploration/harness/cm2lab.py and with the typed
d() is checked once at start (one case: the base a.py and the reader).

Stages, per case:
  1. base -- the template (items 2, 3, 7), today's letters; the tuple the
     run would choose (make_typed.frontier: the typed total among the tuples
     that keep the R2 page count) is the tuple of the search;
  2. each rewrite candidate alone against the base (its gain, smooth and
     exact);
  3. greedy: the candidates in the order of their gains alone, each
     re-evaluated on the current text and taken when it lowers the smooth
     total (a candidate whose target an earlier one rewrote is skipped);
  4. names: coordinate descent over the roles (template.ROLES, d fixed),
     every legal letter for the role and the swap with the one conflicting
     role holding it, the best taken when it lowers the total; passes until
     none changes (at most 4);
  5. the rewrite candidates again on the renamed text: each one not taken is
     tried, each one taken is tried removed, until nothing changes; then one
     more names pass if anything moved;
  6. the frontier on the final text (reported; make_typed chooses per run).
Output: build/stage1/<case>/search.json; with --freeze also
stage1/frozen_<case>.json (the edits, the letters and the record), which
make_typed.py reads.
Usage: python search.py --case lower|upper [--freeze] [--workers 4]
"""
import concurrent.futures as cf
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'compressor-exploration', 'harness'))
import template as T  # noqa: E402
import make_typed as M  # noqa: E402

SMOOTH = (1 + 4 / 60) / 5           # typed characters per bit of x (glyphs + their checks)
EPS = 1e-6
MAXPASS = 4
_W = {}


def ideal_bits(data, primer, orders):
    tot = 0.0
    for y, p0, p1 in M.cm2_enc.model(data, primer, orders):
        tot += math.log2((p0 + p1) / (p1 if y else p0))
    return tot


def _init(case, C):
    reader, _, _ = M.the_reader()
    _W.update(case=case, reader=reader.encode(), N=len(reader.encode()),
              R=M.check(0, reader, T.ALPHABETS[case]), C=C)


def program(edits, letters, orders):
    text = T.typed_text(edits, letters, _W['case'], orders)
    first = T.first_data_line(T.apply_edits(edits))
    prog, _, _ = T.bake(text, _W['N'], first + _W['C'], _W['R'])
    return prog


def evaluate(job):
    edits, letters, orders, exact = job
    prog = program(edits, letters, orders)
    ch = M.chars(prog)
    bits = ideal_bits(_W['reader'], prog.strip().encode(), orders)
    r = dict(chars=ch, bits=bits, smooth=ch + bits * SMOOTH)
    if exact:
        x = M.cm2_enc.encode_int(_W['reader'], prog.strip().encode(), orders)
        G = len(M.b32(x, T.ALPHABETS[_W['case']]))
        C = -(-G // M.PAYLOAD)
        r.update(glyphs=G, lines=C, exact=ch + G + M.CHECK * C)
    return r


class Search:
    def __init__(self, case, workers):
        self.case = case
        self.ex = cf.ProcessPoolExecutor(workers, initializer=_init, initargs=(case, 48))
        _init(case, 48)
        self.log = []

    def many(self, jobs):
        return list(self.ex.map(evaluate, jobs, chunksize=1))

    def one(self, edits, letters, orders, exact=False):
        return self.ex.submit(evaluate, (edits, letters, orders, exact)).result()


def present_roles(text):
    import io
    import tokenize
    names = {t.string for t in tokenize.generate_tokens(io.StringIO(text).readline)
             if t.type == tokenize.NAME}
    return [r for r in T.ROLES if r in names and r not in T.FIXED]


def names_pass(S, edits, letters, orders, cur):
    text = T.apply_edits(edits)
    conf = T.conflicts(text)
    partners = {r: {b if a == r else a for a, b in conf if r in (a, b)} for r in T.ROLES}
    changes = []
    for r in present_roles(text):
        moves = []
        for L in T.LETTERS:
            if L == letters[r]:
                continue
            m = dict(letters)
            m[r] = L
            if T.valid_letters(text, m, conf):
                moves.append((f'{r} {letters[r]}->{L}', m))
                continue
            holders = [x for x in partners[r] if letters[x] == L]
            if len(holders) == 1:
                m[holders[0]] = letters[r]
                if T.valid_letters(text, m, conf):
                    moves.append((f'{r} {letters[r]}->{L} (swap with {holders[0]})', m))
        res = S.many([(edits, m, orders, False) for _, m in moves])
        if not res:
            continue
        i = min(range(len(res)), key=lambda i: (res[i]['smooth'], i))
        if res[i]['smooth'] < cur['smooth'] - EPS:
            changes.append(dict(move=moves[i][0], gain=round(res[i]['smooth'] - cur['smooth'], 3)))
            letters, cur = moves[i][1], res[i]
    return letters, cur, changes


def rewrite_pass(S, edits, letters, orders, cur):
    """Stage 5: add any candidate not taken, remove any taken, best first,
    until nothing lowers the total."""
    log = []
    while True:
        trials = []
        for cid, _, fn in T.CANDIDATES:
            if cid in edits:
                e = [x for x in edits if x != cid]
                try:
                    T.apply_edits(e)
                except AssertionError:
                    continue
                trials.append((f'-{cid}', e))
            elif fn(T.apply_edits(edits)) is not None:
                trials.append((f'+{cid}', edits + [cid]))
        trials = [(n, e) for n, e in trials if T.valid_letters(T.apply_edits(e), letters)]
        res = S.many([(e, letters, orders, False) for _, e in trials])
        if not res:
            return edits, cur, log
        i = min(range(len(res)), key=lambda i: (res[i]['smooth'], i))
        if res[i]['smooth'] >= cur['smooth'] - EPS:
            return edits, cur, log
        log.append(dict(move=trials[i][0], gain=round(res[i]['smooth'] - cur['smooth'], 3)))
        edits, cur = trials[i][1], res[i]


def agreement(case):
    """The exact coder once, three ways: cm2_enc (the encoder make_typed
    uses), the exploration's cm2lab mirror, and the typed d() decoding it."""
    import cm2lab
    _init(case, 48)
    reader, _, _ = M.the_reader()
    raw = reader.encode()
    prog = program([], dict(T.BASE_LETTERS), T.LONG_TUPLE)
    pr = prog.strip().encode()
    x1 = M.cm2_enc.encode_int(raw, pr, T.LONG_TUPLE)
    x2 = cm2lab.encode_x(cm2lab.model(raw, pr, orders=T.LONG_TUPLE))
    d = M.defs(prog)['d']
    ok = x1 == x2 and d(x1, len(raw), pr) == raw
    ib = ideal_bits(raw, pr, T.LONG_TUPLE)
    return dict(cm2_enc_equals_cm2lab=x1 == x2, typed_d_round_trip=d(x1, len(raw), pr) == raw,
                exact_bits=x1.bit_length(), ideal_bits=round(ib, 2), ok=ok)


def run(case, workers, freeze):
    t0 = time.time()
    agree = agreement(case)
    assert agree['ok'], agree
    print('coder agreement:', agree, flush=True)
    S = Search(case, workers)
    letters = dict(T.BASE_LETTERS)
    base_spec = dict(case=case, edits=[], letters=letters)
    reader, n2, b2 = M.the_reader()
    rows, ch = M.frontier(base_spec, reader, open(M.BUNDLE, 'rb').read(), M.R2_PAGES_BOUND)
    orders = tuple(ch['orders'])
    frontier0 = [{k: v for k, v in r.items() if k != 'packed'} for r in rows]
    print('base frontier:', [(tuple(r['orders']), r['total'], r.get('r2_pages')) for r in frontier0],
          '-> search tuple', orders, flush=True)
    base = S.one([], letters, orders, True)
    print('base', base, flush=True)

    # 2. each candidate alone
    alone = []
    jobs = [(cid, [cid]) for cid, _, fn in T.CANDIDATES if fn(T.TEMPLATE) is not None]
    res = S.many([(e, letters, orders, True) for _, e in jobs])
    for (cid, _), r in zip(jobs, res):
        alone.append(dict(id=cid, what=T.CAND[cid][1], chars=r['chars'] - base['chars'],
                          smooth=round(r['smooth'] - base['smooth'], 3),
                          exact=r['exact'] - base['exact']))
    print('alone:', [(a['id'], a['smooth'], a['exact']) for a in alone], flush=True)

    # 3. greedy
    edits, cur, greedy = [], base, []
    for a in sorted(alone, key=lambda a: (a['smooth'], a['id'])):
        if a['smooth'] >= 0:
            break
        e = edits + [a['id']]
        try:
            text = T.apply_edits(e)
        except AssertionError:
            greedy.append(dict(id=a['id'], taken=False, why='target rewritten by an earlier one'))
            continue
        if not T.valid_letters(text, letters):
            greedy.append(dict(id=a['id'], taken=False, why='letters invalid'))
            continue
        r = S.one(e, letters, orders)
        g = round(r['smooth'] - cur['smooth'], 3)
        if r['smooth'] < cur['smooth'] - EPS:
            edits, cur = e, r
            greedy.append(dict(id=a['id'], taken=True, gain=g))
        else:
            greedy.append(dict(id=a['id'], taken=False, gain=g))
    after_rewrite = S.one(edits, letters, orders, True)
    print('after the rewrite greedy:', edits, after_rewrite, flush=True)

    # 4. names
    names_log = []
    for p in range(MAXPASS):
        letters, cur, ch_ = names_pass(S, edits, letters, orders, cur)
        names_log.append(ch_)
        print(f'names pass {p + 1}:', ch_, round(cur['smooth'], 2), flush=True)
        if not ch_:
            break
    after_names = S.one(edits, letters, orders, True)

    # 5. rewrites again, then names once more
    edits, cur, re_log = rewrite_pass(S, edits, letters, orders, cur)
    print('rewrite re-pass:', re_log, flush=True)
    if re_log:
        for p in range(MAXPASS):
            letters, cur, ch_ = names_pass(S, edits, letters, orders, cur)
            names_log.append(ch_)
            print('names again:', ch_, flush=True)
            if not ch_:
                break
        edits, cur, re2 = rewrite_pass(S, edits, letters, orders, cur)
        re_log += re2
    final = S.one(edits, letters, orders, True)
    print('final', edits, final, flush=True)

    # 6. the frontier on the final text
    fin = [dict(orders=list(o), **S.one(edits, letters, o, True)) for o in T.FRONTIER]
    S.ex.shutdown()
    rec = dict(case=case, coder_agreement=agree, search_tuple=list(orders),
               base_frontier=frontier0,
               base=base, alone=alone, greedy=greedy, after_rewrite=after_rewrite,
               names=names_log, after_names=after_names, rewrite_repass=re_log, final=final,
               final_frontier_unpacked=fin, wall_s=round(time.time() - t0, 1),
               note='smooth = chars + bits*(1+4/60)/5 from ideal bits; exact = chars + G + '
                    '4*ceil(G/60) at the loop bound of 48 lines (make_typed runs the fixed point)')
    out = os.path.join(M.BUILD, case)
    os.makedirs(out, exist_ok=True)
    spec = dict(case=case, edits=edits, letters=letters,
                record=dict(base_exact=base['exact'], after_rewrite_exact=after_rewrite['exact'],
                            after_names_exact=after_names['exact'], final_exact=final['exact'],
                            search_tuple=list(orders), alone=alone, greedy=greedy,
                            names=names_log, rewrite_repass=re_log))
    json.dump(rec, open(os.path.join(out, 'search.json'), 'w'), indent=1)
    if freeze:
        json.dump(spec, open(os.path.join(HERE, f'frozen_{case}.json'), 'w'), indent=1)
    print(f'wrote {out}/search.json' + (f' and stage1/frozen_{case}.json' if freeze else '')
          + f'  [{rec["wall_s"]} s]')


if __name__ == '__main__':
    a = sys.argv[1:]
    run(a[a.index('--case') + 1] if '--case' in a else 'lower',
        int(a[a.index('--workers') + 1]) if '--workers' in a else 4, '--freeze' in a)
