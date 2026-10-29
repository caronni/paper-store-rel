"""mono_inline.py -- undo python-minifier's module-level aliases one at a time
(A=len, G='big', C=None ...): delete the alias line, write the builtin name or the
literal at every occurrence that resolves to the alias binding.  Greedy best-first
by ideal cm2 bits (primer r.py).  Soundness: the alias is bound exactly once (its
own top-level line); a builtin's name is bound nowhere in the program (so the
written name resolves to the builtin); a literal is immutable; every candidate
text re-parses.  Usage: mono_inline.py SRC PRIMER OUT"""
import ast, sys, json, time, builtins, threading
from concurrent.futures import ThreadPoolExecutor
import names2 as nm, search2 as S, ev

def candidates(src):
    tree = ast.parse(src); T = src.encode(); lines = T.split(b'\n')
    offs = [0]
    for L in lines: offs.append(offs[-1] + len(L) + 1)
    occ, frozen, kws = nm.bindings(src)
    allnames = {b[1] for _, _, _, b in occ if b[0] != 'builtin'}
    stores = {}
    for node, kind, name, b in occ:
        if b[0] == 0 and (kind != 'name' or isinstance(node.ctx, ast.Store)):
            stores[b] = stores.get(b, 0) + 1
    spans = S.occ_spans(src)
    for st in tree.body:
        if not (isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)): continue
        if st.lineno != st.end_lineno: continue
        v = st.value; b = (0, st.targets[0].id)
        if stores.get(b, 0) != 1: continue
        if isinstance(v, ast.Name) and hasattr(builtins, v.id):
            if v.id in allnames: continue
            rep = v.id.encode(); alts = [rep]
        elif isinstance(v, ast.Constant) and not isinstance(v.value, (list, dict)):
            rep = T[offs[v.lineno - 1] + v.col_offset:offs[v.end_lineno - 1] + v.end_col_offset]; alts = [rep, b'(' + rep + b')']
        else:
            continue
        # the alias line itself must be exactly the statement
        L = lines[st.lineno - 1]
        if L.strip() != T[offs[st.lineno - 1] + st.col_offset:offs[st.end_lineno - 1] + st.end_col_offset]: continue
        sp = [x for x in spans[b] if not (offs[st.lineno - 1] <= x[0] < offs[st.lineno])]
        line0, line1 = offs[st.lineno - 1], offs[st.lineno]
        for rep in alts:
            # remove the alias line (its offsets are unchanged: every span is after it? not necessarily)
            # recompute: substitute first in the part after and before the line separately
            pre = S.subst(T[:line0], [x for x in sp if x[1] <= line0], rep)
            post = S.subst(T[line1:], [(a - line1, c - line1) for a, c in sp if a >= line1], rep)
            new = (pre + post).decode()
            try:
                t2 = ast.parse(new)
            except SyntaxError:
                continue
            if isinstance(v, ast.Name):
                o2, _, _ = nm.bindings(new)
                if any(b2[1] == v.id and b2[0] != 'builtin' for _, _, _, b2 in o2): continue
            yield (f'inline {b[1]}={rep.decode()}', new)
            break

if __name__ == '__main__':
    src = open(sys.argv[1]).read(); primer = open(sys.argv[2], 'rb').read(); out = sys.argv[3]
    tl = threading.local()
    def sc(t):
        h = getattr(tl, 'h', None)
        if h is None: h = tl.h = ev.Handle(40000)
        return h.bits(t, primer)
    ex = ThreadPoolExecutor(2)
    cur = src; best = sc(cur); start = best; log = []
    print(f'start {best:.1f} bits = {best / 8:.1f} B', flush=True)
    allc = [(l, sc(t) - best) for l, t in candidates(cur)]
    print('single-candidate deltas (bits):', sorted(allc, key=lambda x: x[1]), flush=True)
    while True:
        cands = list(candidates(cur))
        res = sorted(ex.map(lambda c: (sc(c[1]), c[0], c[1]), cands), key=lambda r: r[0])
        if not res or res[0][0] >= best - 1e-9: break
        b, lab, txt = res[0]
        log.append(dict(label=lab, delta_bits=b - best, bits=b)); print(lab, f'{b - best:+.1f}', flush=True)
        best, cur = b, txt
    open(out, 'w').write(cur)
    json.dump(dict(start_bits=start, end_bits=best, singles=allc, steps=log), open(out + '.json', 'w'), indent=1)
    print(f'end {best:.1f} bits = {best / 8:.1f} B ({(best - start) / 8:+.1f} B)', flush=True)
