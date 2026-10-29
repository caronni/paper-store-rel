"""test_reader_identity.py -- the long form and the short form of the typed
stage-2 reader are functionally identical (ruling 35 of RECORD-2026-10-20;
the long form generated from the short form and kept beside it as its form
of record, ruling 48), by the pattern of bootstrap/stage1/test_identity.py.

  A. the typed text is the template renamed: rename(TEMPLATE, LETTERS) is
     bootstrap/r2reader/reader_lite_v1.py's region between '# BEGIN READER'
     and '# END READER', byte for byte; the template's roles are the typed
     program's bindings (every role occurrence resolves where its letter
     resolves, every other name is free: d, N2, B2, builtins); every letter
     split into two roles within one scope can be two variables (no load of
     one role sees a store of the other); the long names are distinct and
     capture nothing;
  B. reader_long_v1.py is gen_reader_long.py's output, its shared block is
     the region's, and its ast, every long name mapped back to its role, is
     the template's (statements, order, expressions; literal spellings with
     the same value compare equal: 0xEDB88320 is 3988292384, checked); its
     names are long names or free names only;
  C. the program: reader_lite_v1.py and reader_long_v1.py, N2 and B2 replaced
     in both by the build's values (bootstrap/build/build-py/readers.json,
     build.py's output root; whole NAME tokens), each beside a copy of
     bootstrap/build/build-py/loader/r.py saved as b.py (the primer the
     reader opens, ruling 34), fed a capture set of bootstrap/build/build-py/r2
     (absolute paths, one per line, then an empty line, from one file):
     exit 0, nothing on stderr, the same output, the same c.py, and c.py ==
     bootstrap/build/build-py/bundle/b.py.  Two sets (SETS): the
     three nominal frames, and a set that runs the other input paths (an
     unreadable name, a quarter frame, a turned page, and a typed text grid
     turned into a P5 PGM by the Plate's one-liner, grid_to_pgm.py, run as
     the Plate prints it, python3 -c LINE, in a directory holding the grid
     as grid.txt); both close.
     The four runs go at once, each in its own subfolder of one temporary
     folder under bootstrap/build/changeset/ (each writes c.py), removed
     afterwards;
  D. mutations: one-token changes of the long form (a constant, a tuple's
     order, a dropped 'and sign', a name, the walk's gate, the pose's tie
     key) each make B fail; and three template changes that keep A's byte
     identity each fail the binding or the split check (A's byte identity
     alone does not prove the roles).
Usage: python3 test_reader_identity.py   (or pytest on this file); ~1 min.
"""
import ast
import builtins
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tokenize
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reader_template as T  # noqa: E402
import gen_reader_long as G  # noqa: E402

BOOT = os.path.dirname(HERE)
BUILD = os.path.join(BOOT, 'build')
BUILD_PY = os.path.join(BUILD, 'build-py')   # build.py's own output root (its BUILD)
SCRATCH = os.path.join(BUILD, 'changeset')
PLATE = os.path.join(HERE, 'grid_to_pgm.py')
LONG = os.path.join(HERE, 'reader_long_v1.py')
R_PY = os.path.join(BUILD_PY, 'loader', 'r.py')
BUNDLE = os.path.join(BUILD_PY, 'bundle', 'b.py')
READERS = os.path.join(BUILD_PY, 'readers.json')
R2 = os.path.join(BUILD_PY, 'r2')
SETS = (   # (what, frames): the first set is the task's; the second runs the other input paths
    ('the three nominal frames', [os.path.join(R2, f'page_p{k}.nominal-b030.pgm') for k in range(3)]),
    ('an unreadable name, a quarter frame, a page turned 90 degrees, a text grid through grid_to_pgm.py',
     [os.path.join(R2, f) for f in ('no-such-frame.pgm', 'page_p2.q-tl.pgm', 'page_p0.rot90-1.pgm')]
     + [('grid', os.path.join(R2, 'page_p1.grid.txt'))]),
)


def plate_line():
    """The Plate's one-liner: grid_to_pgm.py's last line (its docstring says
    the Plate prints it for python3 -c)."""
    return open(PLATE, encoding='ascii').read().rstrip('\n').split('\n')[-1]


def frame_path(frame, tmp):
    """A frame of SETS as the path fed to the reader: a ('grid', text) entry
    is converted by the Plate's line, run as the Plate prints it (no
    arguments: the grid copied to tmp/grid.txt, the line run in tmp, and
    tmp/grid.pgm is the frame)."""
    if not isinstance(frame, tuple):
        return frame
    shutil.copy(frame[1], os.path.join(tmp, 'grid.txt'))
    subprocess.run([sys.executable, '-c', plate_line()], cwd=tmp, check=True)
    return os.path.join(tmp, 'grid.pgm')


def put_token(text, name, value):
    """Every NAME token `name` replaced by the decimal value (strings and
    comments untouched; make_typed.put_token's rule) -> (text, count)."""
    toks = [t for t in tokenize.generate_tokens(io.StringIO(text).readline)
            if t.type == tokenize.NAME and t.string == name]
    lines = text.splitlines(keepends=True)
    for t in reversed(toks):
        (row, c0), (_, c1) = t.start, t.end
        lines[row - 1] = lines[row - 1][:c0] + str(value) + lines[row - 1][c1:]
    return ''.join(lines), len(toks)


def b_holds(long_text):
    """Requirement B, written here independently of the generator: the long
    form's ast without its shared block, long names mapped back to roles,
    equals the template's typed region's ast."""
    inverse = {v: k for k, v in T.LONG_NAMES.items()}
    tree = ast.parse(T.drop_shared(long_text))
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            n.id = inverse.get(n.id, n.id)
        elif isinstance(n, ast.arg):
            n.arg = inverse.get(n.arg, n.arg)
        elif isinstance(n, ast.FunctionDef):
            n.name = inverse.get(n.name, n.name)
    return ast.dump(tree) == ast.dump(ast.parse(T.drop_shared(T.TEMPLATE)))


def check_a():
    typed = T.typed_region()
    assert T.typed_text() == typed, 'rename(TEMPLATE, LETTERS) is not reader_lite_v1.py\'s region'
    problems = T.check_bindings()
    assert not problems, problems
    problems = T.check_splits()
    assert not problems, problems
    problems = T.check_long_names()
    assert not problems, problems
    split = ', '.join(f'{c} in {T.bindings(T.drop_shared(T.TEMPLATE))[2][at].name}: {"/".join(rs)}'
                      for at, c, rs in T.splits())
    return (f'the typed text is the template renamed ({len(typed.encode())} bytes, byte for byte); '
            f'{len(T.ROLES)} roles are its bindings; splits sound ({split}); '
            f'{len(set(T.LONG_NAMES.values()))} long names, distinct')


def check_b():
    text = open(LONG, 'rb').read().decode('ascii')
    assert text == G.generate(), 'reader_long_v1.py is not gen_reader_long.py\'s output'
    assert T.shared_block(text) == T.shared_block(T.typed_region()), 'the shared block differs'
    assert b_holds(text), 'the long form\'s ast is not the template\'s'
    long_tree = ast.parse(T.drop_shared(text))
    names = {n.id for n in ast.walk(long_tree) if isinstance(n, ast.Name)}
    names |= {n.arg for n in ast.walk(long_tree) if isinstance(n, ast.arg)}
    names |= {n.name for n in ast.walk(long_tree) if isinstance(n, ast.FunctionDef)}
    stray = sorted(n for n in names if n not in set(T.LONG_NAMES.values()) | T.FREE
                   and not hasattr(builtins, n))
    assert not stray, f'names in the long form that are neither long names nor free: {stray}'
    numbers = [t.string for t in tokenize.generate_tokens(io.StringIO(T.drop_shared(text)).readline)
               if t.type == tokenize.NUMBER]
    consts = [n.value for n in ast.walk(long_tree) if isinstance(n, ast.Constant)]
    assert numbers.count('0xEDB88320') == 1 and '3988292384' not in numbers
    assert consts.count(3988292384) == 1 and 3988292384 == 0xEDB88320
    lines = text.split('\n')
    return (f'reader_long_v1.py is the generator\'s output ({len(lines) - 1} lines, longest '
            f'{max(map(len, lines))}); its ast with the names mapped back is the template\'s; '
            f'0xEDB88320 == 3988292384 as an ast constant; shared block verbatim')


def check_c():
    rec = json.load(open(READERS))
    n2, b2 = rec['n2'], rec['b2']
    bundle = open(BUNDLE, 'rb').read()
    assert len(bundle) == n2 and zlib.crc32(bundle) == b2, 'readers.json does not describe the bundle'
    os.makedirs(SCRATCH, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='reader-identity-', dir=SCRATCH)
    procs, feeds, written = {}, [], {}
    try:
        for k, (what, frames) in enumerate(SETS):
            feed = os.path.join(tmp, f'frames{k}.txt')
            with open(feed, 'w', newline='\n') as f:
                f.write(''.join(frame_path(fr, tmp) + '\n' for fr in frames) + '\n')
            for name, src in (('typed', T.READER), ('long', LONG)):
                folder = os.path.join(tmp, f'{name}{k}')
                os.makedirs(folder)
                text = open(src, 'rb').read().decode('ascii')
                text, k2 = put_token(text, 'N2', n2)
                text, k3 = put_token(text, 'B2', b2)
                assert (k2, k3) == (1, 1), (name, k2, k3)
                with open(os.path.join(folder, os.path.basename(src)), 'w', newline='\n') as f:
                    f.write(text)
                shutil.copy(R_PY, os.path.join(folder, 'b.py'))
                feeds.append(open(feed))
                procs[name, k] = subprocess.Popen(
                    [sys.executable, os.path.basename(src)], cwd=folder, stdin=feeds[-1],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        outs = {key: p.communicate(timeout=900) for key, p in procs.items()}
        for (name, k), p in procs.items():
            out, err = outs[name, k]
            assert p.returncode == 0 and err == '', (name, k, p.returncode, err[-2000:])
            path = os.path.join(tmp, f'{name}{k}', 'c.py')
            written[name, k] = open(path, 'rb').read() if os.path.exists(path) else None
    finally:
        for f in feeds:
            f.close()
        shutil.rmtree(tmp)
    report = []
    for k, (what, frames) in enumerate(SETS):
        assert outs['typed', k][0] == outs['long', k][0], f'set {k}: the programs printed different lines'
        assert written['typed', k] == written['long', k] == bundle, f'set {k}: c.py differs'
        lines = [ln for ln in outs['typed', k][0].split('\n') if ln.strip()]
        report.append(f'{what}: the same {len(lines)} progress lines, closed '
                      f'("...{lines[-1][-34:]}")')
    return (f'N2 = {n2}, B2 = {b2}; exit 0, empty stderr, c.py byte-identical between the two '
            f'and == build/build-py/bundle/b.py ({len(bundle)} B) on each set; ' + '; '.join(report))


LONG_MUTATIONS = (
    ('a changed constant', 'register >> 1 ^ 0xEDB88320 *', 'register >> 1 ^ 0xEDB88321 *'),
    ('a swapped tuple order', 'in (2, block_column), (3, block_row):',
     'in (3, block_row), (2, block_column):'),
    ("a dropped 'and sign'", 'if neighbour and sign:', 'if neighbour:'),
    ('a swapped name', 'abs(try_x - offset_x)', 'abs(try_x - offset_y)'),
    ("the walk's gate (a white slot no longer walked through)", 'if block_read != None:', 'if block_read:'),
    ("the pose's tie key (the largest |r| preferred)", '-abs(try_rotation)', 'abs(try_rotation)'),
)
TEMPLATE_MUTATIONS = (
    ("the walk's read test reads the cell column role (a split that is not sound)",
     'if Walk_Read:Walk_Got', 'if Walk_Cx:Walk_Got', 'splits'),
    ("the ring list in find_bullseyes' generator written as the generator's own role",
     'for Bulls_Rx,Bulls_Ry,Bulls_Rk in Rings)', 'for Bulls_Rx,Bulls_Ry,Bulls_Rk in Bulls_Ry)', 'bindings'),
    ('a binding left as its letter', 'Walk_Sign=(Walk_Along>0)', 'm=(Walk_Along>0)', 'bindings'),
)


def check_d():
    text = open(LONG, 'rb').read().decode('ascii')
    assert b_holds(text)
    for what, old, new in LONG_MUTATIONS:
        assert text.count(old) == 1, (what, text.count(old))
        bad = text.replace(old, new)
        ast.parse(bad)
        assert not b_holds(bad), f'B does not see {what}'
    for what, old, new, check in TEMPLATE_MUTATIONS:
        assert T.TEMPLATE.count(old) == 1, what
        bad = T.TEMPLATE.replace(old, new)
        assert T.rename(bad, T.LETTERS) == T.typed_region(), f'{what}: A should still hold'
        found = T.check_splits(bad) if check == 'splits' else T.check_bindings(bad)
        assert found, f'the {check} check does not see {what}'
    return (f'B fails on each of {len(LONG_MUTATIONS)} long-form mutations '
            f'({"; ".join(w for w, _, _ in LONG_MUTATIONS)}); '
            f'{len(TEMPLATE_MUTATIONS)} template mutations keep the byte identity and fail the '
            f'binding or split check')


def test_a_typed_text_is_the_template():
    check_a()


def test_b_long_form_is_the_template():
    check_b()


def test_c_same_program_on_frames():
    check_c()


def test_d_mutations_are_seen():
    check_d()


if __name__ == '__main__':
    for tag, fn in (('A', check_a), ('B', check_b), ('C', check_c), ('D', check_d)):
        print(f'PASS {tag}: {fn()}', flush=True)
