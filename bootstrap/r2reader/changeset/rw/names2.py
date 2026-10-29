"""names2.py -- scope-exact renaming (extends loader/review/names.py, 2026-10-19).

Adds what the monolith needs: class scopes (invisible to nested functions;
bindings in a class body are attributes and are FROZEN), `nonlocal`, `except
... as NAME`; works on byte offsets (ast col_offset is UTF-8).  Every rename is
re-proved: each occurrence re-resolves to (same scope, mapped name), builtins
stay builtins, no two bindings merge, frozen bindings never move, and no
renamed argument name is ever used as a call keyword.
"""
import ast, re

class Scope:
    def __init__(s, n, parent, kind):
        s.n, s.parent, s.kind, s.bound, s.nonlocal_ = n, parent, kind, set(), set()

def _targets(node, out):
    for x in ast.walk(node):
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
            out.append(x)

def _nonlocals(body):
    out = set()
    def walk(n):
        for ch in ast.iter_child_nodes(n):
            if isinstance(ch, (ast.FunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            if isinstance(ch, ast.Nonlocal):
                out.update(ch.names)
            walk(ch)
    for st in body:
        if isinstance(st, ast.Nonlocal): out.update(st.names)
        walk(st)
    return out

def bindings(src):
    tree = ast.parse(src); _ROOT[0] = tree
    for x in ast.walk(tree):
        assert not isinstance(x, (ast.Global, ast.NamedExpr, ast.Delete, ast.Import,
                                  ast.ImportFrom, ast.AsyncFunctionDef, ast.Match)), type(x)
    scopes, occ = [], []
    def new(parent, kind):
        s = Scope(len(scopes), parent, kind); scopes.append(s); return s
    def bind(sc, name):
        if name not in sc.nonlocal_: sc.bound.add(name)
    def visit(node, sc):
        if isinstance(node, ast.FunctionDef):
            bind(sc, node.name); occ.append((node, 'def', node.name, sc))
            for d in node.decorator_list + node.args.defaults + [k for k in node.args.kw_defaults if k]:
                visit(d, sc)
            assert not node.returns
            fs = new(sc, 'def'); fs.nonlocal_ = _nonlocals(node.body)
            for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                assert not a.annotation
                fs.bound.add(a.arg); occ.append((a, 'arg', a.arg, fs))
            assert not node.args.vararg and not node.args.kwarg
            for st in node.body: visit(st, fs)
            return
        if isinstance(node, ast.ClassDef):
            bind(sc, node.name); occ.append((node, 'class', node.name, sc))
            for d in node.decorator_list + node.bases + [k.value for k in node.keywords]:
                visit(d, sc)
            cs = new(sc, 'class')
            for st in node.body: visit(st, cs)
            return
        if isinstance(node, ast.Lambda):
            for d in node.args.defaults: visit(d, sc)
            ls = new(sc, 'lambda')
            for a in node.args.args:
                ls.bound.add(a.arg); occ.append((a, 'arg', a.arg, ls))
            visit(node.body, ls); return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            gens = node.generators
            visit(gens[0].iter, sc)
            cs = new(sc, 'comp')
            for k, g in enumerate(gens):
                tg = []; _targets(g.target, tg)
                for t in tg: cs.bound.add(t.id)
                if k: visit(g.iter, cs)
                visit(g.target, cs)
                for c in g.ifs: visit(c, cs)
            if isinstance(node, ast.DictComp): visit(node.key, cs); visit(node.value, cs)
            else: visit(node.elt, cs)
            return
        if isinstance(node, ast.Nonlocal):
            for nm in node.names: occ.append((node, 'nonlocal', nm, sc))
            return
        if isinstance(node, ast.ExceptHandler):
            if node.type: visit(node.type, sc)
            if node.name:
                bind(sc, node.name); occ.append((node, 'except', node.name, sc))
            for st in node.body: visit(st, sc)
            return
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store): bind(sc, node.id)
            occ.append((node, 'name', node.id, sc)); return
        for ch in ast.iter_child_nodes(node): visit(ch, sc)
    mod = new(None, 'module')
    for st in tree.body: visit(st, mod)

    def resolve(name, sc, kind):
        s = sc
        if kind == 'nonlocal':          # the enclosing function's binding
            s = sc.parent
            while s.kind == 'class': s = s.parent
        first = True
        while s is not None:
            if (first or s.kind != 'class') and name in s.bound:
                return (s.n, name)
            first = False
            s = s.parent
        return ('builtin', name)
    out = []
    for node, kind, name, sc in occ:
        b = resolve(name, sc, kind)
        out.append((node, kind, name, b))
    frozen = {(s.n, nm) for s in scopes if s.kind == 'class' for nm in s.bound}
    kws = {k.arg for x in ast.walk(tree) if isinstance(x, ast.Call) for k in x.keywords if k.arg}
    return out, frozen, kws

_PRE = {'def': rb'def\s+', 'class': rb'class\s+'}

def _spans(lines, occ):
    sp = []
    for node, kind, name, _ in occ:
        ln, c = node.lineno, node.col_offset
        L = lines[ln - 1]; nb = name.encode()
        if kind in _PRE:
            c = re.compile(_PRE[kind]).match(L, c).end()
        elif kind == 'except':
            c = re.compile(rb'\bas\s+').search(L, c).end()
        elif kind == 'nonlocal':
            c = re.compile(rb'(?<![A-Za-z0-9_])' + re.escape(nb) + rb'(?![A-Za-z0-9_])').search(L, c + 8).start()
        assert L[c:c + len(nb)] == nb, (ln, c, name)
        sp.append((ln, c, c + len(nb)))
    return sp

class Unsound(Exception):
    pass

def rename(src, m):
    occ, frozen, kws = bindings(src)
    lines = src.encode().split(b'\n')
    sp = _spans(lines, occ)
    edits = {}
    for (node, kind, name, b), (ln, c0, c1) in zip(occ, sp):
        if b in m and m[b] != name:
            if b[0] == 'builtin' or b in frozen: raise Unsound('frozen ' + str(b))
            if kind == 'arg' and (name in kws or m[b] in kws): raise Unsound('keyword arg')
            edits.setdefault(ln, []).append((c0, c1, m[b].encode()))
    for ln, es in edits.items():
        t = lines[ln - 1]
        for c0, c1, new in sorted(es, reverse=True):
            t = t[:c0] + new + t[c1:]
        lines[ln - 1] = t
    out = b'\n'.join(lines).decode()
    try:
        new = bindings(out)[0]
    except SyntaxError as e:
        raise Unsound('syntax')
    check(occ, new, m)
    return out

def check(old, new, m):
    if len(old) != len(new): raise Unsound('occurrence count')
    back = {}
    for (_, k0, n0, b0), (_, k1, n1, b1) in zip(old, new):
        want = b0 if b0[0] == 'builtin' else (b0[0], m.get(b0, b0[1]))
        if k0 != k1 or b1 != want: raise Unsound(f'{n0}->{n1}: {b0} became {b1}, want {want}')
        if back.setdefault(b1, b0) != b0: raise Unsound(f'{b0} and {back[b1]} both became {b1}')

def table(src):
    occ, frozen, kws = bindings(src)
    out = {}
    for _, _, _, b in occ:
        if b[0] != 'builtin' and b not in frozen: out[b] = out.get(b, 0) + 1
    return out

def strip_names(src):
    """ast.dump with every renamable identifier replaced by its binding id (rename-invariant)."""
    occ, frozen, kws = bindings(src)
    ids = {}
    for node, kind, name, b in occ:
        key = b if b[0] == 'builtin' or b in frozen else ('B', ids.setdefault(b, len(ids)))
        tag = repr(key)
        if kind == 'name': node.id = tag
        elif kind == 'arg': node.arg = tag
        elif kind in ('def', 'class', 'except'): node.name = tag
        elif kind == 'nonlocal': node.names = [tag if x == name else x for x in node.names]
    return ast.dump(_ROOT[0])
_ROOT = [None]
