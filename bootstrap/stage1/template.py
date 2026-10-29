"""template.py -- the ONE source of stage 1's a.py (ruling 43, 2026-10-21).

TEMPLATE is the typed program in its typed spelling, with every identifier
written as a ROLE (a capitalised word: the typed program has no capital, so
a role that escapes substitution is caught by the audit).  Three things are
derived from it, and nothing else is a source:
  - the typed a.py: the role names replaced by single letters (a letter map,
    searched by search.py, item 11), after the frozen rewrite candidates
    chosen by the search (item 10) and the order tuple (item 7);
  - the long form readable.py (gen_readable.py): the SAME text, the roles
    replaced by descriptive names, laid out one statement per line by the
    ast, with comments;
  - the search's candidate texts (search.py).
The template carries the taken items 2 ('b.py' for the loader's output), 3
(k and the alphabet above d) and 7 (the order tuple a parameter of d with a
default; the reader calls d(x, N2, primer) and so decodes the R2 pages with
that default).  Placeholders: @A@ the alphabet (--case), @O@ the default
order tuple, @N@ the reader's bytes, @C1@ the loop bound (first data line +
C), @R@ the reader's check code, @D@/@E@ the b.py slice (fixed point in
make_typed.py).  One space per indent level.
d's to_bytes takes the default byte order, 'big' (ruling 53; the ,'big'
argument removed 2026-10-23 in the convergence of ruling 60, 6 characters):
a.py, and the b.py it writes, which carries d, need Python 3.11 or later.
"""
import ast
import io
import re
import tokenize

LOWER = '0123456789abcdefghjkmnpqrstvwxyz'          # Crockford, lowercase (the print of record)
UPPER = LOWER.upper()                                # the same set, uppercase (item 8, explored)
ALPHABETS = {'lower': LOWER, 'upper': UPPER}
FRONTIER = ((0, 1, 2, 3, 4, 6), (0, 1, 2, 3, 4, 6, 8), (0, 1, 2, 3, 4, 6, 8, 12),
            (0, 1, 2, 3, 4, 6, 8, 12, 16))           # the order-tuple frontier (record 10-20, panel 18)
LONG_TUPLE = FRONTIER[-1]                            # typed/cm2_dec.py's tuple, the KATs'

TEMPLATE = """Prog=open('a.py').read().strip().encode()
Alpha,Line,Num='@A@',1,0
def Check(Seed,Text):
 for Byte in Text:Seed=(Seed+Byte)*1000003
 return''.join(Alpha[Seed>>Shift&31]for Shift in(15,10,5,0))
def Dec(State,Count,Primer,Orders=@O@):
 Masks=[256**Order-1 for Order in Orders]
 Len,Table,Hist=len(Primer),{},0
 for Pos in range(Len+Count):
  Part=1
  for Bit in range(8):
   Pairs=[Table.setdefault((Hist&Mask,Part),[0,0])for Mask in Masks]
   Weights=[1+sum(Pair[Yc]<<Index+(Pair[1-Yc]<1)for(Index,Pair)in enumerate(Pairs))for Yc in(0,1)]
   Sum=sum(Weights)
   if Pos<Len:Y=Primer[Pos]>>7-Bit&1
   else:Slot=State%Sum;Y=Slot>=Weights[0];State=State//Sum*Weights[Y]+Slot-Weights[0]*Y
   for PairU in Pairs:PairU[Y],PairU[1-Y]=PairU[Y]+1,min(PairU[1-Y],PairU[1-Y]//4+2)
   Part=2*Part+Y
  Hist=Hist<<8|Part&255
 return Hist.to_bytes(Len+Count)[Len:]
for(Idx,Td)in enumerate(Prog.splitlines(),1):print(Idx,Check(Idx,Td))
while Line<@C1@:
 Typed=input([Line]).replace(' ','')
 if Check(Line,Typed[:-4].encode())==Typed[-4:]:
  Line+=1
  for Glyph in Typed[:-4]:Num=Num*32+Alpha.index(Glyph)
Out=Dec(Num,@N@,Prog)
assert Check(0,Out)=='@R@'
open('b.py','wb').write(Prog[@D@:@E@]+Out)"""

# Today's letters (the print of record, loader/a.py), the search's start.
BASE_LETTERS = {
    'Prog': 'a', 'Alpha': 'q', 'Line': 'n', 'Num': 'v', 'Check': 'k', 'Seed': 'n', 'Text': 't',
    'Byte': 'c', 'Shift': 's', 'Dec': 'd', 'State': 'x', 'Count': 'n', 'Primer': 'r',
    'Orders': 'w', 'Masks': 'z', 'Order': 'q', 'Len': 'm', 'Table': 't', 'Hist': 'h',
    'Pos': 'i', 'Part': 'u', 'Bit': 'j', 'Pairs': 'g', 'Mask': 'q', 'Weights': 'p',
    'Index': 'q', 'Pair': 'c', 'Yc': 'y', 'Sum': 's', 'Y': 'y', 'Slot': 'o', 'PairU': 'c',
    'Idx': 'i', 'Td': 't', 'Typed': 't', 'Glyph': 'c', 'Out': 'r'}
FIXED = {'Dec': 'd'}          # the reader calls d(...): the one name the stage-2 text needs
ROLES = tuple(BASE_LETTERS)
LETTERS = tuple(c for c in 'abcdefghijkmnopqrstuvwxyz')     # no l (the typed-subset rule)

# The long form's names (gen_readable.py), one per role.
LONG_NAMES = {
    'Prog': 'program', 'Alpha': 'alphabet', 'Line': 'line_number', 'Num': 'number',
    'Check': 'check', 'Seed': 'code', 'Text': 'text', 'Byte': 'byte', 'Shift': 'shift',
    'Dec': 'decode', 'State': 'state', 'Count': 'count', 'Primer': 'primer',
    'Orders': 'orders', 'Masks': 'masks', 'Order': 'order', 'Len': 'primer_length',
    'Table': 'counters', 'Hist': 'history', 'Pos': 'position', 'Part': 'partial',
    'Bit': 'bit_index', 'Pairs': 'pairs', 'Mask': 'mask', 'Weights': 'weights',
    'Index': 'index', 'Pair': 'pair', 'Yc': 'outcome', 'Sum': 'total', 'Y': 'bit',
    'Slot': 'slot', 'PairU': 'counter_pair', 'Idx': 'listing_number', 'Td': 'listing_line',
    'Typed': 'typed', 'Glyph': 'glyph', 'Out': 'reader'}
assert set(LONG_NAMES) == set(BASE_LETTERS) == set(ROLES)


# ---- the rewrite candidates (item 10), frozen -------------------------------
# Each is (id, what, fn): fn(text) -> the rewritten template, or None when it
# does not apply (its target was rewritten by another candidate).  Every
# candidate is an equivalent spelling: the same statements in the same order
# of effects (proved for the chosen set by make_typed's proofs and
# test_identity.py, which run the typed program).

def _sub(old, new, count=1):
    def f(t):
        if t.count(old) != count:
            return None
        return t.replace(old, new)
    return f


def _seq(*fs):
    def f(t):
        for g in fs:
            t = g(t)
            if t is None:
                return None
        return t
    return f


def _tokens_all(old, new):
    """Every occurrence (at least one)."""
    def f(t):
        return t.replace(old, new) if old in t else None
    return f


def _perm(line_re, order):
    """Permute a parallel assignment 'A,B,C=x,y,z' (the line matched by
    line_re, its indentation kept) into the given order of its targets."""
    def f(t):
        lines = t.split('\n')
        hits = [i for i, s in enumerate(lines) if re.fullmatch(line_re, s.strip())]
        if len(hits) != 1:
            return None
        s = lines[hits[0]]
        ind = s[:len(s) - len(s.lstrip())]
        lhs, rhs = s.strip().split('=', 1)
        tv = lhs.split(',')
        vals = _split_top(rhs)
        if len(tv) != len(vals) or len(tv) != len(order):
            return None
        lines[hits[0]] = ind + ','.join(tv[k] for k in order) + '=' + ','.join(vals[k] for k in order)
        return '\n'.join(lines)
    return f


def _split_top(s):
    out, depth, cur, q = [], 0, '', None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
            continue
        if ch in '\'"':
            q = ch
        elif ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur)
            cur = ''
        else:
            cur += ch
    return out + [cur]


def _swap_alpha_and_check(t):
    lines = t.split('\n')
    ia = [i for i, s in enumerate(lines) if s.startswith(('Alpha', 'Line', 'Num')) and "'@A@'" in s]
    ic = [i for i, s in enumerate(lines) if s.startswith('def Check(')]
    if len(ia) != 1 or len(ic) != 1 or ia[0] + 1 != ic[0]:
        return None
    j = ic[0] + 1
    while j < len(lines) and lines[j].startswith(' '):
        j += 1
    block = lines[ic[0]:j]
    return '\n'.join(lines[:ia[0]] + block + [lines[ia[0]]] + lines[j:])


def _sum_inline(t):
    old = '   Sum=sum(Weights)\n'
    if t.count(old) != 1 or t.count('   else:') != 1:
        return None
    t = t.replace(old, '')
    return t.replace('   else:', '   else:Sum=sum(Weights);')


def _u1_merge(t):
    """Item 13 as a candidate spelling (not a change by itself): Part=1 moves
    into the init and the history line."""
    if t.count('  Part=1\n') != 1:
        return None
    t = t.replace('  Part=1\n', '')
    m = re.search(r'(?m)^  Hist=(.*)$', t)
    i = re.search(r'(?m)^ ((?:\w+,)*Hist(?:,\w+)*)=(.*)$', t)
    if not m or not i:
        return None
    t = t[:m.start()] + '  Part,Hist=1,' + m.group(1) + t[m.end():]
    i = re.search(r'(?m)^ ((?:\w+,)*Hist(?:,\w+)*)=(.*)$', t)
    return t[:i.start()] + ' ' + i.group(1) + ',Part=' + i.group(2) + ',1' + t[i.end():]


def _selfdump_counter(t):
    old = 'for(Idx,Td)in enumerate(Prog.splitlines(),1):print(Idx,Check(Idx,Td))'
    for o in (old, old.replace('for(Idx,Td)in', 'for Idx,Td in')):
        if t.count(o) == 1:
            return t.replace(o, 'for Td in Prog.splitlines():print(Line,Check(Line,Td));Line+=1')
    return None


def _line_inc_last(t):
    m = re.search(r'(?m)^  Line\+=1\n(  for Glyph in .*)$', t)
    if not m:
        return None
    return t[:m.start()] + m.group(1) + '\n  Line+=1' + t[m.end():]


INIT_RE = r'Len,Table,Hist=len\(Primer\),\{\},0'
ALPHA_RE = r"Alpha,Line,Num='@A@',1,0"
CANDIDATES = [
    ('selfdump-counter', 'the self-dump counts with the data counter: prompts continue the '
     "listing's numbering ([L+1] ...); the enumerate goes", _selfdump_counter),
    ('update-split', "the counter update as two statements: c[1-y]=min(...);c[y]+=1",
     _sub('PairU[Y],PairU[1-Y]=PairU[Y]+1,min(PairU[1-Y],PairU[1-Y]//4+2)',
          'PairU[1-Y]=min(PairU[1-Y],PairU[1-Y]//4+2);PairU[Y]+=1')),
    ('update-split-b', "the counter update as two statements: c[y]+=1;c[1-y]=min(...)",
     _sub('PairU[Y],PairU[1-Y]=PairU[Y]+1,min(PairU[1-Y],PairU[1-Y]//4+2)',
          'PairU[Y]+=1;PairU[1-Y]=min(PairU[1-Y],PairU[1-Y]//4+2)')),
    ('sum-inline', 's=sum(p) moved into the else branch (its only reader)', _sum_inline),
    ('part-double', 'u=2*u+y as u+=u+y', _sub('Part=2*Part+Y', 'Part+=Part+Y')),
    ('part-double-b', 'u=2*u+y as u=u*2+y', _sub('Part=2*Part+Y', 'Part=Part*2+Y')),
    ('hist-minus', 'u&255 as u-256 (u is 256..511 after eight bits)',
     _sub('Hist<<8|Part&255', 'Hist<<8|Part-256')),
    ('hist-mod', 'u&255 as u%256', _sub('Hist<<8|Part&255', 'Hist<<8|Part%256')),
    ('num-order', 'v=v*32+... as v=32*v+...', _sub('Num=Num*32+', 'Num=32*Num+')),
    ('find', 'q.index(c) as q.find(c) (the line passed its check first)',
     _sub('Alpha.index(Glyph)', 'Alpha.find(Glyph)')),
    ('slot-cmp', 'y=o>=p[0] as y=p[0]<=o', _sub('Y=Slot>=Weights[0]', 'Y=Weights[0]<=Slot')),
    ('state-order', '...-p[0]*y as ...-y*p[0]',
     _sub('+Slot-Weights[0]*Y', '+Slot-Y*Weights[0]')),
    ('out-is-num', 'the decoded reader bound to v (r=d(v,..) as v=d(v,..))',
     _seq(_sub('Out=Dec(Num,', 'Num=Dec(Num,'), _sub('Check(0,Out)', 'Check(0,Num)'),
          _sub('+Out)', '+Num)'))),
    ('u1-merge', 'item 13 (u=1 merged into the init and the history line), as a candidate',
     _u1_merge),
    ('masks-merge', 'the masks line merged into the init line',
     _seq(_sub(' Masks=[256**Order-1 for Order in Orders]\n Len,Table,Hist=len(Primer),{},0',
               ' Masks,Len,Table,Hist=[256**Order-1 for Order in Orders],len(Primer),{},0'))),
    ('alpha-check-order', 'def k above the alphabet line (both stay above d)',
     _swap_alpha_and_check),
    ('enum-paren-sum', 'for(q,c)in as for q,c in (inside the weights)',
     _sub('for(Index,Pair)in', 'for Index,Pair in')),
    ('enum-paren-dump', 'for(i,t)in as for i,t in (the self-dump)',
     _sub('for(Idx,Td)in', 'for Idx,Td in')),
    ('yc-list', 'for y in(0,1) as for y in[0,1]', _sub('for Yc in(0,1)', 'for Yc in[0,1]')),
    ('boost-first', 'c[y]<<q+(c[1-y]<1) as c[y]<<(c[1-y]<1)+q',
     _sub('Pair[Yc]<<Index+(Pair[1-Yc]<1)for', 'Pair[Yc]<<(Pair[1-Yc]<1)+Index for')),
    ('boost-gt', '(c[1-y]<1) as (1>c[1-y])', _sub('(Pair[1-Yc]<1)', '(1>Pair[1-Yc])')),
    ('min-order', 'min(c,c//4+2) as min(c//4+2,c)',
     _sub('min(PairU[1-Y],PairU[1-Y]//4+2)', 'min(PairU[1-Y]//4+2,PairU[1-Y])')),
    ('xor-y', '1-y as y^1 in the update', _tokens_all('1-Y]', 'Y^1]')),
    ('xor-yc', '1-y as y^1 in the weights', _tokens_all('1-Yc]', 'Yc^1]')),
    ('check-order', 'n=(n+c)*K as n=(c+n)*K', _sub('Seed=(Seed+Byte)', 'Seed=(Byte+Seed)')),
    ('pos-gt', 'if i<m as if m>i', _sub('if Pos<Len:', 'if Len>Pos:')),
    ('range-order', 'range(m+n) as range(n+m)', _sub('range(Len+Count)', 'range(Count+Len)')),
    ('check-swap', 'if k(...)==t[-4:] as if t[-4:]==k(...)',
     _sub('if Check(Line,Typed[:-4].encode())==Typed[-4:]:',
          'if Typed[-4:]==Check(Line,Typed[:-4].encode()):')),
    ('assert-literal-first', "assert k(0,r)=='...' as assert'...'==k(0,r)",
     lambda t: (re.sub(r"assert Check\(0,(\w+)\)=='@R@'", r"assert'@R@'==Check(0,\1)", t)
                if re.search(r"assert Check\(0,(\w+)\)=='@R@'", t) else None)),
    ('line-inc-last', 'n+=1 after the digit loop instead of before', _line_inc_last),
    ('bit-shift', 'r[i]>>7-j&1 as r[i]<<j>>7&1 (a byte shifted left first)',
     _sub('Primer[Pos]>>7-Bit&1', 'Primer[Pos]<<Bit>>7&1')),
] + [(f'init-perm-{"".join(map(str, o))}', f'm,t,h=... in the order {o}', _perm(INIT_RE, o))
     for o in ((0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))] + [
    (f'alpha-perm-{"".join(map(str, o))}', f'q,n,v=... in the order {o}', _perm(ALPHA_RE, o))
    for o in ((0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))]
CAND = {c[0]: c for c in CANDIDATES}
assert len(CAND) == len(CANDIDATES)


def apply_edits(edits, text=TEMPLATE):
    for e in edits:
        t = CAND[e][2](text)
        assert t is not None, f'candidate {e} does not apply'
        text = t
    return text


def first_data_line(text):
    """The number of the first data line of a ROLE text (the template with
    its edits, before the renaming): 1, or the listing's line count + 1 when
    the self-dump counts with the data counter."""
    assert 'Prog' in text, 'first_data_line needs the role text'
    if 'print(Line,' in text:
        return text.count('\n') + 2
    return 1


def fill(text, case, orders):
    return text.replace('@A@', ALPHABETS[case]).replace('@O@', str(tuple(orders)).replace(' ', ''))


def rename(text, names):
    """Replace every NAME token that is a role by names[role] (strings and
    comments untouched).  Placeholders (@N@ ...) may stand in the text."""
    toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    lines = text.split('\n')
    for t in reversed(toks):
        if t.type == tokenize.NAME and t.string in names:
            (r, c0), (_, c1) = t.start, t.end
            lines[r - 1] = lines[r - 1][:c0] + names[t.string] + lines[r - 1][c1:]
    return '\n'.join(lines)


def placeholder_free(text):
    """The text with the numeric placeholders set to stand-in values, for the
    parser and the symbol tables."""
    return (text.replace('@O@', '(0,)').replace('@N@', '9').replace('@C1@', '9').replace('@R@', 'xxxx')
            .replace('@D@', '9').replace('@E@', '9'))


COMPS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _scopes(src):
    """The scopes of a program by its ast (the module, every def, every
    comprehension -- each comprehension its own scope, as the language
    defines it; symtable merges inlined comprehensions into the function
    since 3.12, which would forbid legal reuse).  Per scope: the names bound
    in it, the names used in it, and the free names of its inner scopes
    passing through.  -> [(path, sorted identifiers)] in a fixed order."""
    out = []

    def visit(node, path):
        bound, used, kids = set(), set(), []

        def walk(n, top=False):
            if not top and isinstance(n, (ast.FunctionDef, ast.Lambda) + COMPS):
                if isinstance(n, ast.FunctionDef):
                    bound.add(n.name)
                    for dflt in n.args.defaults:
                        walk(dflt)
                elif isinstance(n, COMPS):
                    walk(n.generators[0].iter)          # evaluated in the enclosing scope
                kids.append(n)
                return
            if isinstance(n, ast.Name):
                (bound if isinstance(n.ctx, ast.Store) else used).add(n.id)
            elif isinstance(n, ast.arg):
                bound.add(n.arg)
            for c in ast.iter_child_nodes(n):
                if top and isinstance(node, ast.FunctionDef) and c in node.args.defaults:
                    continue
                if top and isinstance(node, COMPS) and c is node.generators[0].iter:
                    continue
                walk(c)

        if isinstance(node, COMPS):
            for g in node.generators:
                for n in ast.walk(g.target):
                    if isinstance(n, ast.Name):
                        bound.add(n.id)
                for i, g in enumerate(node.generators):
                    if i:
                        walk(g.iter)
                    for c in g.ifs:
                        walk(c)
            for part in ((node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,)):
                walk(part)
        else:
            walk(node, top=True)
        me = len(out)
        out.append(None)
        free = set()
        for i, k in enumerate(kids):
            kid_ids, kid_bound = visit(k, path + (i,))
            free |= kid_ids - kid_bound
        ids = bound | used | free
        out[me] = (path, sorted(ids))
        return ids, bound

    visit(ast.parse(src), ())
    return out


# Roles of one scope that may share a letter because their lives do not
# overlap (sequential reuse, as today's t serves the self-dump and the input
# loop): the module's loop variables and the decoded reader; the order tuple,
# read only by the first statement of d.
_MOD_EARLY, _MOD_LATE = ('Idx', 'Td'), ('Typed', 'Glyph')
SHAREABLE = {frozenset(p) for p in
             [(a, b) for a in _MOD_EARLY for b in _MOD_LATE + ('Out',)] +
             [(b, 'Out') for b in _MOD_LATE] +
             [('Orders', r) for r in ('Masks', 'Len', 'Table', 'Hist', 'Pos', 'Part', 'Bit',
                                      'Pairs', 'Weights', 'Sum', 'Y', 'Slot', 'PairU')]}


def conflicts(text):
    """Pairs of roles that share a scope (by the ast's scopes) and are not
    SHAREABLE: they must get different letters.  Everything else may share
    one."""
    src = placeholder_free(text)
    out = set()
    for _, ids in _scopes(src):
        rs = [i for i in ids if i in BASE_LETTERS]
        for a in rs:
            for b in rs:
                if a < b and frozenset((a, b)) not in SHAREABLE:
                    out.add((a, b))
    return out


def valid_letters(text, letters, conf=None):
    """A letter map is valid when the fixed names are kept, no role is l or a
    capital, and no two conflicting roles share a letter (the renamed
    program is then the template's program: each scope keeps its bindings
    apart; make_typed's proofs and test_identity.py run it)."""
    for r, c in FIXED.items():
        if letters[r] != c:
            return False
    if any(letters[r] not in LETTERS for r in ROLES):
        return False
    for a, b in (conflicts(text) if conf is None else conf):
        if letters[a] == letters[b]:
            return False
    return True


def typed_text(edits, letters, case, orders):
    """The typed program with placeholders @N@ @C1@ @R@ @D@ @E@ still in."""
    t = apply_edits(edits)
    t = rename(t, letters)
    return fill(t, case, orders)


def bake(text, N, C1, R):
    """Set the print's constants; the slice a[D:E] (line 2 up to the self-dump
    line, the first line that starts with 'for') is computed from the text."""
    start = text.index('\n') + 1
    lines = text.split('\n')
    m = next(i for i, s in enumerate(lines) if i > 0 and s.startswith('for'))
    end = sum(len(s) + 1 for s in lines[:m])
    assert '@' not in text[:end].replace("'@A@'", '')
    t = text.replace('@D@', str(start)).replace('@E@', str(end))
    t = t.replace('@N@', str(N)).replace('@C1@', str(C1)).replace('@R@', R)
    assert t[:end] == text[:end], 'a placeholder before the main part'
    return t, start, end


def check_ast_equal(a, b, inverse_a=None, inverse_b=None):
    """ast dumps of two programs equal after mapping each one's names back to
    roles (inverse maps letter/long name -> role are scope-blind, so they are
    applied only where unambiguous: used for the long form, whose names are
    all distinct)."""
    def norm(src, inv):
        tree = ast.parse(src)
        if inv:
            for n in ast.walk(tree):
                if isinstance(n, ast.Name) and n.id in inv:
                    n.id = inv[n.id]
                elif isinstance(n, ast.arg) and n.arg in inv:
                    n.arg = inv[n.arg]
                elif isinstance(n, ast.FunctionDef) and n.name in inv:
                    n.name = inv[n.name]
        return ast.dump(tree, include_attributes=False)
    return norm(a, inverse_a) == norm(b, inverse_b)
