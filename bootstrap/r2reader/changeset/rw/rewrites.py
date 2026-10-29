"""rewrites.py -- compression-aware equivalent spellings, generated per site.

Each generator yields (label, new_text) for ONE site of the text; the text edit
is checked by re-parsing and comparing ast.dump with the intended transformed
tree (built on a fresh parse), so a candidate is exactly the transform asked
for (parenthesised where precedence needs it).  Semantic preconditions:
  flip      A<B -> B>A (one op of < > <= >= == !=), both sides pure
  comm      A*B, A&B, A|B, A^B -> B op A, both sides pure (ints; seq*int commutes)
  tperm     a,b=x,y -> b,a=y,x (distinct plain names, pure values)
  merge     a=x / b=y -> a,b=x,y (same block, consecutive, y does not read a, b not in x, pure)
  split     a,b=x,y -> a=x / b=y (y does not read a, pure)
  shift     x>>k <-> x//2**k (k int literal) and x&(2**k-1) <-> x%2**k, x*2**k <-> x<<k : ints only
            (applied only where the operand is not a float literal; the reader and the
            monolith's operands at these sites are ints -- the chain run is the proof)
  aug       x=x op e <-> x op=e for op in - // >> << & | ^ (Name targets; no + or *, which
            mutate lists in place)
'pure' = no call to a name in IMPURE, no attribute call other than PURE_ATTR."""
import ast, copy

IMPURE = {'input', 'print', 'open', 'next', 'exec', 'eval'}
PURE_ATTR = {'from_bytes', 'to_bytes', 'join', 'find', 'get', 'split', 'strip', 'translate',
             'index', 'count', 'replace', 'bit_length', 'items', 'keys', 'values', 'lstrip', 'hex', 'decode', 'encode'}
FLIP = {ast.Lt: ast.Gt, ast.Gt: ast.Lt, ast.LtE: ast.GtE, ast.GtE: ast.LtE, ast.Eq: ast.Eq, ast.NotEq: ast.NotEq}
OPS = {ast.Lt: '<', ast.Gt: '>', ast.LtE: '<=', ast.GtE: '>=', ast.Eq: '==', ast.NotEq: '!=',
       ast.Mult: '*', ast.BitAnd: '&', ast.BitOr: '|', ast.BitXor: '^', ast.Sub: '-', ast.FloorDiv: '//',
       ast.RShift: '>>', ast.LShift: '<<', ast.Mod: '%', ast.Add: '+'}


def pure(node, impure_fns=()):
    for x in ast.walk(node):
        if isinstance(x, (ast.Yield, ast.Await, ast.NamedExpr)): return False
        if isinstance(x, ast.Call):
            f = x.func
            if isinstance(f, ast.Name) and (f.id in IMPURE or f.id in impure_fns): return False
            if isinstance(f, ast.Attribute) and f.attr not in PURE_ATTR: return False
            if not isinstance(f, (ast.Name, ast.Attribute)): return False
    return True


def names_read(node):
    return {x.id for x in ast.walk(node) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}


class Text:
    def __init__(s, src):
        s.src = src; s.b = src.encode(); s.lines = s.b.split(b'\n')
        s.offs = [0]
        for L in s.lines: s.offs.append(s.offs[-1] + len(L) + 1)

    def off(s, ln, col): return s.offs[ln - 1] + col

    def seg(s, n): return s.b[s.off(n.lineno, n.col_offset):s.off(n.end_lineno, n.end_col_offset)]

    def span(s, n): return s.off(n.lineno, n.col_offset), s.off(n.end_lineno, n.end_col_offset)


def _locate(tree, path):
    n = tree
    for f, i in path:
        n = getattr(n, f) if i is None else getattr(n, f)[i]
    return n


def _paths(tree):
    out = []
    def rec(n, p):
        out.append((n, p))
        for f, v in ast.iter_fields(n):
            if isinstance(v, list):
                for i, c in enumerate(v):
                    if isinstance(c, ast.AST): rec(c, p + [(f, i)])
            elif isinstance(v, ast.AST): rec(v, p + [(f, None)])
    rec(tree, [])
    return out


def _try_edit(T, s0, s1, pieces, intended_dump):
    """pieces: list of alternatives; first whose parse equals intended wins."""
    for rep in pieces:
        nb = T.b[:s0] + rep + T.b[s1:]
        try:
            t = ast.parse(nb.decode())
        except SyntaxError:
            continue
        if ast.dump(t) == intended_dump:
            return nb.decode()
    return None


def gen(src, kinds=('flip', 'comm', 'tperm', 'merge', 'split', 'shift', 'aug'), impure_fns=()):
    T = Text(src)
    tree = ast.parse(src)
    P = lambda n: pure(n, impure_fns)
    for node, path in _paths(tree):
        # ---- flip
        if 'flip' in kinds and isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in FLIP \
                and P(node.left) and P(node.comparators[0]):
            t2 = ast.parse(src); n2 = _locate(t2, path)
            a, b = n2.left, n2.comparators[0]
            n2.left, n2.comparators, n2.ops = b, [a], [FLIP[type(n2.ops[0])]()]
            A, B = T.seg(node.left), T.seg(node.comparators[0]); op = OPS[FLIP[type(node.ops[0])]].encode()
            s0, s1 = T.span(node)
            r = _try_edit(T, s0, s1, [B + op + A, b'(' + B + b')' + op + A, B + op + b'(' + A + b')',
                                      b'(' + B + b')' + op + b'(' + A + b')'], ast.dump(t2))
            if r: yield (f'flip@{node.lineno}:{node.col_offset}', r)
        # ---- comm
        if 'comm' in kinds and isinstance(node, ast.BinOp) and type(node.op) in (ast.Mult, ast.BitAnd, ast.BitOr, ast.BitXor) \
                and P(node.left) and P(node.right):
            t2 = ast.parse(src); n2 = _locate(t2, path)
            n2.left, n2.right = n2.right, n2.left
            A, B = T.seg(node.left), T.seg(node.right); op = OPS[type(node.op)].encode()
            s0, s1 = T.span(node)
            r = _try_edit(T, s0, s1, [B + op + A, b'(' + B + b')' + op + A, B + op + b'(' + A + b')',
                                      b'(' + B + b')' + op + b'(' + A + b')'], ast.dump(t2))
            if r: yield (f'comm@{node.lineno}:{node.col_offset}', r)
        # ---- shift
        if 'shift' in kinds and isinstance(node, ast.BinOp) and isinstance(node.right, ast.Constant) \
                and type(node.right.value) is int and not isinstance(node.left, ast.Constant):
            k = node.right.value; op = type(node.op); alt = None
            if op is ast.RShift and 0 < k < 64: alt = (ast.FloorDiv, 1 << k)
            elif op is ast.LShift and 0 < k < 64: alt = (ast.Mult, 1 << k)
            elif op is ast.FloorDiv and k > 1 and k & (k - 1) == 0: alt = (ast.RShift, k.bit_length() - 1)
            elif op is ast.Mult and k > 1 and k & (k - 1) == 0 and False: alt = None   # seq*int: unsafe
            elif op is ast.BitAnd and k > 0 and (k + 1) & k == 0: alt = (ast.Mod, k + 1)
            elif op is ast.Mod and k > 1 and k & (k - 1) == 0: alt = (ast.BitAnd, k - 1)
            if alt:
                t2 = ast.parse(src); n2 = _locate(t2, path)
                n2.op = alt[0](); n2.right = ast.Constant(alt[1])
                A = T.seg(node.left); s0, s1 = T.span(node)
                rep = OPS[alt[0]].encode() + str(alt[1]).encode()
                r = _try_edit(T, s0, s1, [A + rep, b'(' + A + b')' + rep, b'(' + A + rep + b')'], ast.dump(t2))
                if r: yield (f'shift@{node.lineno}:{node.col_offset}', r)
        # ---- tuple assignment: permute (swap adjacent pairs) / split
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Tuple) \
                and isinstance(node.value, ast.Tuple) and len(node.targets[0].elts) == len(node.value.elts) \
                and all(isinstance(e, ast.Name) for e in node.targets[0].elts) \
                and len({e.id for e in node.targets[0].elts}) == len(node.targets[0].elts) \
                and all(P(v) for v in node.value.elts) and not any(isinstance(v, ast.Starred) for v in node.value.elts):
            tg, vs = node.targets[0].elts, node.value.elts
            n = len(tg)
            if 'tperm' in kinds:
                for i in range(n - 1):
                    t2 = ast.parse(src); n2 = _locate(t2, path)
                    e2, v2 = n2.targets[0].elts, n2.value.elts
                    e2[i], e2[i + 1] = e2[i + 1], e2[i]; v2[i], v2[i + 1] = v2[i + 1], v2[i]
                    order = list(range(n)); order[i], order[i + 1] = order[i + 1], order[i]
                    lhs = b','.join(T.seg(tg[j]) for j in order); rhs = b','.join(T.seg(vs[j]) for j in order)
                    s0, s1 = T.span(node)
                    r = _try_edit(T, s0, s1, [lhs + b'=' + rhs], ast.dump(t2))
                    if r: yield (f'tperm{i}@{node.lineno}:{node.col_offset}', r)
            if 'split' in kinds:
                tnames = [e.id for e in tg]
                ok = all(not (names_read(vs[j]) & set(tnames[:j])) for j in range(n))
                parent = _locate(tree, path[:-1]); fld, idx = path[-1]
                if ok and idx is not None and node.lineno == node.end_lineno:
                    line = T.lines[node.lineno - 1]
                    ind = line[:len(line) - len(line.lstrip())]
                    s0, s1 = T.span(node)
                    simple = T.b[T.offs[node.lineno - 1]:s0].strip() == b''   # statement starts the line
                    t2 = ast.parse(src); par2 = _locate(t2, path[:-1]); body = getattr(par2, fld)
                    new = [ast.Assign(targets=[copy.deepcopy(tg[j])], value=copy.deepcopy(vs[j]), lineno=0) for j in range(n)]
                    body[idx:idx + 1] = new
                    for sep in ([b';'] + ([b'\n' + ind] if simple else [])):
                        rep = sep.join(T.seg(tg[j]) + b'=' + T.seg(vs[j]) for j in range(n))
                        r = _try_edit(T, s0, s1, [rep], ast.dump(t2))
                        if r: yield (f'split{"nl" if sep != b";" else ""}@{node.lineno}:{node.col_offset}', r)
        # ---- merge consecutive single-name assignments
        if 'merge' in kinds:
            for fld, v in ast.iter_fields(node):
                if not (isinstance(v, list) and fld in ('body', 'orelse', 'finalbody')): continue
                for i in range(len(v) - 1):
                    a, b = v[i], v[i + 1]
                    def simple1(x):
                        return isinstance(x, ast.Assign) and len(x.targets) == 1 and isinstance(x.targets[0], ast.Name) \
                               and P(x.value) and not isinstance(x.value, ast.Tuple)
                    if not (simple1(a) and simple1(b)): continue
                    an, bn = a.targets[0].id, b.targets[0].id
                    if an == bn or an in names_read(b.value): continue
                    t2 = ast.parse(src); par2 = _locate(t2, path); body = getattr(par2, fld)
                    m = ast.Assign(targets=[ast.Tuple(elts=[copy.deepcopy(a.targets[0]), copy.deepcopy(b.targets[0])], ctx=ast.Store())],
                                   value=ast.Tuple(elts=[copy.deepcopy(a.value), copy.deepcopy(b.value)], ctx=ast.Load()), lineno=0)
                    body[i:i + 2] = [m]
                    s0 = T.span(a)[0]; s1 = T.span(b)[1]
                    rep = T.seg(a.targets[0]) + b',' + T.seg(b.targets[0]) + b'=' + T.seg(a.value) + b',' + T.seg(b.value)
                    r = _try_edit(T, s0, s1, [rep], ast.dump(t2))
                    if r: yield (f'merge@{a.lineno}:{a.col_offset}', r)
        # ---- aug
        if 'aug' in kinds and isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) \
                and type(node.op) in (ast.Sub, ast.FloorDiv, ast.RShift, ast.LShift, ast.BitAnd, ast.BitOr, ast.BitXor):
            t2 = ast.parse(src); n2 = _locate(t2, path); par2 = _locate(t2, path[:-1]); fld, idx = path[-1]
            if idx is not None:
                new = ast.Assign(targets=[ast.Name(node.target.id, ast.Store())],
                                 value=ast.BinOp(ast.Name(node.target.id, ast.Load()), type(node.op)(), copy.deepcopy(node.value)), lineno=0)
                getattr(par2, fld)[idx] = new
                s0, s1 = T.span(node); N = T.seg(node.target); E = T.seg(node.value); op = OPS[type(node.op)].encode()
                r = _try_edit(T, s0, s1, [N + b'=' + N + op + E, N + b'=' + N + op + b'(' + E + b')'], ast.dump(t2))
                if r: yield (f'unaug@{node.lineno}:{node.col_offset}', r)
        if 'aug' in kinds and isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and isinstance(node.value, ast.BinOp) and isinstance(node.value.left, ast.Name) \
                and node.value.left.id == node.targets[0].id \
                and type(node.value.op) in (ast.Sub, ast.FloorDiv, ast.RShift, ast.LShift, ast.BitAnd, ast.BitOr, ast.BitXor):
            t2 = ast.parse(src); par2 = _locate(t2, path[:-1]); fld, idx = path[-1]
            if idx is not None:
                getattr(par2, fld)[idx] = ast.AugAssign(target=ast.Name(node.targets[0].id, ast.Store()), op=type(node.value.op)(),
                                                        value=copy.deepcopy(node.value.right), lineno=0)
                s0, s1 = T.span(node); N = T.seg(node.targets[0]); E = T.seg(node.value.right); op = OPS[type(node.value.op)].encode()
                r = _try_edit(T, s0, s1, [N + op + b'=' + E], ast.dump(t2))
                if r: yield (f'aug@{node.lineno}:{node.col_offset}', r)


def top_moves(src, movable=lambda st: isinstance(st, ast.FunctionDef)):
    """Move one top-level def to another position among the top-level statements
    (line-granular).  Defs only: moving a def is safe as long as nothing CALLS it
    before its new position at module level -- checked: every module-level statement
    before the new position must not reference the def's name."""
    tree = ast.parse(src); T = Text(src); body = tree.body
    segs = []
    for i, st in enumerate(body):
        s0 = T.offs[st.lineno - 1]; s1 = T.offs[st.end_lineno]
        segs.append((s0, s1))
    head = T.b[:segs[0][0]]; tail = T.b[segs[-1][1]:]
    pieces = [T.b[a:b] for a, b in segs]
    for i, st in enumerate(body):
        if not movable(st): continue
        for j in range(len(body)):
            if j == i: continue
            order = [k for k in range(len(body)) if k != i]
            order.insert(j, i)
            pos = order.index(i)
            before = [body[k] for k in order[:pos] if not isinstance(body[k], ast.FunctionDef)]
            # a module-level (non-def) statement that runs before the def must not use it
            if any(st.name in names_read(b) for b in before): continue
            # and defs it relies on at call time are bound before any module-level call: the
            # calls happen in non-def statements; require all non-def statements to keep order
            nondef = [k for k in order if not isinstance(body[k], ast.FunctionDef)]
            if nondef != sorted(nondef): continue
            # a non-def statement after which the def is placed must not be needed... (defs are
            # only called from module statements; any module statement calling `st` must come after it)
            defs = {b.name for b in body if isinstance(b, ast.FunctionDef)}
            callers = [k for k in range(len(body)) if not isinstance(body[k], ast.FunctionDef) and names_read(body[k]) & defs]
            if callers and pos > min(order.index(u) for u in callers): continue
            nb = head + b''.join(pieces[k] for k in order) + tail
            yield (f'move {st.name} {i}->{j}', nb.decode())
