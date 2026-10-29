#!/usr/bin/env python3
"""reroll_template_cv.py -- r2reader/reader_template.py brought to the reader
text of the convergence's fixed point (ruling 60, 2026-10-23;
bootstrap/CONVERGENCE-2026-10-23.md): TEMPLATE re-roled from the new typed
region and ROLE_TABLE given the new letters and the new order of the
module's statements.

reroll_template.py and its successors carried the roles by hand-kept scope
tables (SCOPES, FROM_LINE, AT, a relabel per moved definition).  The two
search rounds here moved five definitions, respelled locals in nine of
them and took eight equivalent spellings (tuple orders, an operand swap, a
comparison flip, //256 as >>8), so the roles are carried by MATCHING instead:
the old TEMPLATE (roles, section 20) and the new typed region (letters) are
parsed and walked in parallel -- module definitions paired by name (no
module-level name moved: a role's letter is its own), the module's other
statements and every body in order -- and every bound name of the new text
receives the role of the name it pairs with.  The walk admits exactly the
search's rewrites (rw/rewrites.py): a commutative operator's operands
swapped, a single comparison flipped, a tuple assignment's targets and
values permuted together, x>>k / x//2**k (and << / *, & / %) exchanged;
anything else fails.  Where an order is ambiguous it takes the pairing that
keeps role -> letter a function.  Proved by: role -> letter a function,
rename(new TEMPLATE, new letters) == the new region, reader_template's own
checks (bindings, splits, long names) and test_reader_identity.py.

  python3 reroll_template_cv.py --old OLD_READER.py [--new NEW_READER.py --print] [--print]
OLD_READER.py = section 20's reader_lite_v1.py (the text TEMPLATE was rolled
from; build/converge/final/reader_before.py); the new text is the tree's.
"""
import ast
import io
import itertools
import os
import re
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
R2R = os.path.dirname(HERE)
sys.path.insert(0, R2R)
import reader_template as T  # noqa: E402

OLD = os.path.abspath(sys.argv[sys.argv.index('--old') + 1])
if '--new' in sys.argv:          # a dry run on a reader not yet in the tree (with --print)
    T.typed_region.__defaults__ = (os.path.abspath(sys.argv[sys.argv.index('--new') + 1]),)
COMM = (ast.Mult, ast.BitAnd, ast.BitOr, ast.BitXor, ast.Add)
FLIP = {ast.Lt: ast.Gt, ast.Gt: ast.Lt, ast.LtE: ast.GtE, ast.GtE: ast.LtE, ast.Eq: ast.Eq, ast.NotEq: ast.NotEq}


def is_role(s):
    return s in T.LETTERS          # free names (d, N2, B2, builtins) stand for themselves


class Fail(Exception):
    pass


class Matcher:
    """Parallel walk of the role tree o and the letter tree n."""

    def __init__(self):
        self.env = {}       # role -> letter
        self.at = {}        # (line, col) in the new text -> role

    def snap(self):
        return dict(self.env), dict(self.at)

    def back(self, s):
        self.env, self.at = dict(s[0]), dict(s[1])

    def name(self, role, letter, pos):
        if is_role(role):
            if self.env.setdefault(role, letter) != letter:
                raise Fail(f'{role} -> {self.env[role]} and {letter}')
            self.at[pos] = role
        elif role != letter:
            raise Fail(f'free name {role} vs {letter}')

    def alt(self, *tries):
        s = self.snap()
        err = None
        for f in tries:
            try:
                f()
                return
            except Fail as e:
                err = e
                self.back(s)
        raise err

    def seq(self, a, b):
        if len(a) != len(b):
            raise Fail(f'lengths {len(a)} {len(b)}')
        for x, y in zip(a, b):
            self.node(x, y)

    def fields(self, o, n, skip=()):
        for f in o._fields:
            if f in skip:
                continue
            a, b = getattr(o, f), getattr(n, f, None)
            if isinstance(a, ast.AST):
                self.node(a, b)
            elif isinstance(a, list):
                if a and isinstance(a[0], ast.AST) or b and isinstance(b[0], ast.AST):
                    self.seq(a, b)
                elif a != b:
                    raise Fail(f'{type(o).__name__}.{f}')
            elif f not in ('ctx',) and a != b:
                raise Fail(f'{type(o).__name__}.{f} {a!r} {b!r}')

    def node(self, o, n):
        if isinstance(o, ast.BinOp) and isinstance(n, ast.BinOp) and type(o.op) is not type(n.op):
            return self.shift(o, n)
        if type(o) is not type(n):
            raise Fail(f'{type(o).__name__} vs {type(n).__name__}')
        if isinstance(o, ast.Name):
            return self.name(o.id, n.id, (n.lineno, n.col_offset))
        if isinstance(o, ast.arg):
            return self.name(o.arg, n.arg, (n.lineno, n.col_offset))
        if isinstance(o, ast.FunctionDef):
            self.name(o.name, n.name, (n.lineno, n.col_offset + 4))
            return self.fields(o, n, skip=('name',))
        if isinstance(o, ast.BinOp) and isinstance(o.op, COMM):
            return self.alt(lambda: self.fields(o, n),
                            lambda: (self.node(o.left, n.right), self.node(o.right, n.left)))
        if isinstance(o, ast.Compare) and len(o.ops) == 1 and len(n.ops) == 1:
            def flipped():
                if FLIP[type(o.ops[0])] is not type(n.ops[0]):
                    raise Fail('flip op')
                self.node(o.left, n.comparators[0])
                self.node(o.comparators[0], n.left)

            def direct():
                if type(o.ops[0]) is not type(n.ops[0]):
                    raise Fail('compare op')
                self.node(o.left, n.left)
                self.node(o.comparators[0], n.comparators[0])
            return self.alt(direct, flipped)
        if (isinstance(o, ast.Assign) and len(o.targets) == 1 and isinstance(o.targets[0], ast.Tuple)
                and isinstance(o.value, ast.Tuple) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Tuple)
                and isinstance(n.value, ast.Tuple) and len(o.targets[0].elts) == len(o.value.elts)
                == len(n.targets[0].elts) == len(n.value.elts)):
            k = len(o.value.elts)

            def perm(p):
                def f():
                    for i, j in enumerate(p):
                        self.node(o.targets[0].elts[i], n.targets[0].elts[j])
                        self.node(o.value.elts[i], n.value.elts[j])
                return f
            return self.alt(*[perm(p) for p in itertools.permutations(range(k))])
        return self.fields(o, n)

    def shift(self, o, n):
        """x>>k <-> x//2**k, x<<k <-> x*2**k, x&(2**k-1) <-> x%2**k (rewrites.py's shift)."""
        pairs = {(ast.RShift, ast.FloorDiv): lambda a, b: 1 << a == b, (ast.FloorDiv, ast.RShift): lambda a, b: a == 1 << b,
                 (ast.LShift, ast.Mult): lambda a, b: 1 << a == b, (ast.Mult, ast.LShift): lambda a, b: a == 1 << b,
                 (ast.BitAnd, ast.Mod): lambda a, b: a + 1 == b, (ast.Mod, ast.BitAnd): lambda a, b: a == b + 1}
        ok = pairs.get((type(o.op), type(n.op)))
        if not (ok and isinstance(o.right, ast.Constant) and isinstance(n.right, ast.Constant)
                and ok(o.right.value, n.right.value)):
            raise Fail('BinOp op')
        self.node(o.left, n.left)


def module(mt, old_body, new_body):
    """Definitions by name (the role's letter: no module-level name moved), the
    other statements in order."""
    defs_o = {T.LETTERS[s.name]: s for s in old_body if isinstance(s, ast.FunctionDef)}
    defs_n = {s.name: s for s in new_body if isinstance(s, ast.FunctionDef)}
    assert set(defs_o) == set(defs_n), set(defs_o) ^ set(defs_n)
    rest_o = [s for s in old_body if not isinstance(s, ast.FunctionDef)]
    rest_n = [s for s in new_body if not isinstance(s, ast.FunctionDef)]
    for k in defs_o:
        mt.node(defs_o[k], defs_n[k])
    mt.seq(rest_o, rest_n)


def statement_key(s):
    if isinstance(s, ast.FunctionDef):
        return f'# def {s.name}'
    if isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name):
        return f'# {s.targets[0].id} = ...'
    return None


def role_table(src, letters, new_rest):
    head, rest = src.split('ROLE_TABLE = (\n', 1)
    body, tail = rest.split('\n)\n', 1)
    groups, order, cur = {}, [], None
    for line in body.split('\n'):
        st = line.strip()
        if st.startswith('# '):
            cur = '# the session' if st.startswith('# the session') else st
            order.append(cur)
            groups[cur] = [line]
            continue
        mm = re.fullmatch(r"    \('(\w+)', '(\w+)', '(\w+)'\),", line)
        assert mm, line
        role, _, long = mm.groups()
        assert role in letters, role
        groups[cur].append(f"    ('{role}', '{letters[role]}', '{long}'),")
    new_order = [k for k in (statement_key(s) for s in ast.parse(new_rest).body) if k in groups]
    assert sorted(new_order + ['# the session']) == sorted(order), (order, new_order)
    seen = {re.fullmatch(r"    \('(\w+)'.*", x).group(1) for g in groups.values() for x in g[1:]}
    assert seen == set(letters), set(letters) ^ seen
    lines = [x for k in new_order + ['# the session'] for x in groups[k]]
    note_old = ("# pgm_field t); changeset/reroll_template.py (reroll_template_comp.py,\n"
                "# reroll_template_prog.py, reroll_template_pad.py) wrote TEMPLATE from the\n"
                "# typed text by this table's scopes.\n")
    note_new = ("# pgm_field t); changeset/reroll_template.py (reroll_template_comp.py,\n"
                "# reroll_template_prog.py, reroll_template_pad.py) wrote TEMPLATE from the\n"
                "# typed text by this table's scopes; then of the convergence of ruling 60\n"
                "# (2026-10-23: five definitions moved, locals respelled, eight equivalent\n"
                "# spellings), whose TEMPLATE changeset/reroll_template_cv.py wrote by\n"
                "# matching the old template to the new text.\n")
    if note_new not in head:
        assert head.count(note_old) == 1, 'the ROLE_TABLE note is not the one expected'
        head = head.replace(note_old, note_new)
    return head + 'ROLE_TABLE = (\n' + '\n'.join(lines) + '\n)\n' + tail


def main():
    old_region = T.region(open(OLD, 'rb').read().decode('ascii'))
    assert T.rename(T.TEMPLATE, T.LETTERS) == old_region, 'TEMPLATE is not the old text re-roled'
    new_region = T.typed_region()
    shared = T.shared_block(new_region)
    assert shared == T.shared_block(old_region) == T.shared_block(T.TEMPLATE)
    old_rest, new_rest = T.drop_shared(T.TEMPLATE), T.drop_shared(new_region)
    assert new_region == shared + new_rest
    mt = Matcher()
    module(mt, ast.parse(old_rest).body, ast.parse(new_rest).body)
    lines = new_rest.split('\n')
    toks = [t for t in tokenize.generate_tokens(io.StringIO(new_rest).readline) if t.type == tokenize.NAME]
    hit = 0
    for t in reversed(toks):
        role = mt.at.get(t.start)
        if role is None:
            continue
        (row, c0), (_, c1) = t.start, t.end
        assert lines[row - 1][c0:c1] == mt.env[role] == t.string
        lines[row - 1] = lines[row - 1][:c0] + role + lines[row - 1][c1:]
        hit += 1
    assert hit == len(mt.at), (hit, len(mt.at))
    template = shared + '\n'.join(lines)
    letters = dict(T.LETTERS)
    assert set(mt.env) <= set(letters), set(mt.env) - set(letters)
    missing = set(letters) - set(mt.env)
    assert not missing, f'roles not met in the new text: {missing}'
    letters.update(mt.env)
    assert T.rename(template, letters) == new_region, 'not the new text re-roled'
    moved = {r: (T.LETTERS[r], letters[r]) for r in letters if T.LETTERS[r] != letters[r]}
    print(f'{len(mt.at)} name tokens re-roled; {len(moved)} roles respelled:')
    for r, (a, b) in sorted(moved.items()):
        print(f'  {r}: {a} -> {b}')
    if '--print' in sys.argv:
        sys.stdout.write(template)
        return
    path = os.path.join(R2R, 'reader_template.py')
    src = open(path, encoding='ascii').read()
    src = role_table(src, letters, new_rest)
    head, tail = src.split('TEMPLATE = """', 1)
    _, tail = tail.split('"""\n', 1)
    assert '"""' not in template and '\\' not in template
    open(path, 'w', encoding='ascii', newline='\n').write(head + 'TEMPLATE = """' + template + '"""\n' + tail)
    print(f'{path}: TEMPLATE ({len(template.splitlines())} lines) and ROLE_TABLE rewritten')


if __name__ == '__main__':
    main()
