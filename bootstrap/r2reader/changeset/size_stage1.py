#!/usr/bin/env python3
"""size_stage1.py (changeset copy of ideation/size_stage1.py: the two literals
substituted only where the reader still carries the old ones) -- a reader variant's data-sheet size under STAGE 1's primer
(the new a.py of ruling 43, bootstrap/stage1/, the primer of the next build),
beside the ladder's convention (loader/a.py of record, diet/w4_ladder.size).
Adapted from the refuter's check of 2026-10-22 (never typed).

  python bootstrap/r2reader/ideation/size_stage1.py READER.py [...]

Per reader and case (lower / upper alphabet): the typed text with stage 1's
two renamed literals (ruling 34), N2 and B2 the bundle's, packed by
stage1/make_typed.pack (the loader's frozen spelling and letters, the order
tuple (0,1,2,3,4,6,8)): glyphs, data lines, the typed total (a.py + data).
Scratch copies go under bootstrap/build/ideation/stage1/.
"""
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))  # r2reader/changeset
ROOT = os.path.dirname(os.path.dirname(HERE))          # bootstrap/
sys.path.insert(0, os.path.join(ROOT, 'stage1'))
import make_typed as M   # noqa: E402
import template as T     # noqa: E402

OUT = os.path.join(ROOT, 'build', 'changeset', 'stage1-sizes')
ORDERS = (0, 1, 2, 3, 4, 6, 8)


def main():
    os.makedirs(OUT, exist_ok=True)
    bundle = open(M.BUNDLE, 'rb').read()
    n2, b2 = len(bundle), zlib.crc32(bundle)
    paths = [os.path.abspath(a) for a in sys.argv[1:]]
    rows = []
    for case in ('lower', 'upper'):
        spec = M.load_spec(case)
        alpha = T.ALPHABETS[case]
        build = M.builder(spec, ORDERS)
        for path in paths:
            src = open(path).read()
            for old, new in M.LITERALS:
                if src.count(new) == 1 and old not in src:
                    continue
                assert src.count(old) == 1, (path, old)
                src = src.replace(old, new)
            p = os.path.join(OUT, os.path.basename(path)[:-3] + f'_{case}.py')
            open(p, 'w').write(src)
            t = M.reader_text(p, n2, b2)
            r = M.pack(t, build, alpha, ORDERS)
            g = len(M.b32(r['x'], alpha))
            rows.append((os.path.basename(path)[:-3], case, len(t.encode()), g, r['C'], M.cost(r)))
    print('| reader | case | typed bytes | glyphs | data lines | typed total (a.py + data) |')
    print('|---|---|---|---|---|---|')
    for n, case, nb, g, c, cost in rows:
        print(f'| {n} | {case} | {nb} | {g} | {c} | {cost} |')


if __name__ == '__main__':
    main()
