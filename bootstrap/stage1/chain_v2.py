"""chain_v2.py -- the stage-1 chain with c.py as the R2 content, for the
convergence of ruling 60 (2026-10-23) and the rebuild of the candidate print
of record v2 (bootstrap/rebuild_v2.py).  build/sheets/chain_sheets.py with
every input explicit:

  --tree DIR     the bootstrap/ tree whose stage1/ (template.py,
                 make_typed.py, e2e.py, gen_readable.py), r2reader/
                 reader_lite_v1.py, typed/ and r2/ are run (default: this
                 file's bootstrap/); a staging tree under build/converge/
                 holds the round's candidate texts;
  --bundle PATH  the R2 content (default DIR/stage3/c.py);
  --frozen PATH  the spelling (default DIR/stage1/frozen_CASE.json);
  --reader PATH  the reader text in place of DIR/r2reader/reader_lite_v1.py;
  --out DIR      the build directory (make_typed's --build; the reader copy
                 reader_e2e.py goes there too).

  python bootstrap/stage1/chain_v2.py make|e2e|pages|identity CASE --out DIR [--tree DIR] [--bundle PATH] [--frozen PATH] [--reader PATH]
make: stage1/make_typed.py (the fixed point, the frontier at the record's
page bound, the proofs, the second byte-compared build).  e2e: stage1/e2e.py
(the R2 pages of the bundle under this build's b.py, renders, the typing LF /
CRLF on a second interpreter / pty, b.py's reads: c.py == the bundle, the
CRLF negative).  pages: e2e.py's page step alone (the R2 payload, gen.py's
pages, verify_grid, the nominal renders) into OUT/CASE/r2/, its record in
OUT/CASE/pages.json.  identity: stage1/test_identity.py on OUT/CASE.
"""
import os
import sys
from pathlib import Path


def arg(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else default


TREE = Path(arg('--tree', Path(__file__).resolve().parents[1])).resolve()
STAGE1 = TREE / 'stage1'
CASE = sys.argv[2]
BUNDLE = Path(arg('--bundle', TREE / 'stage3' / 'c.py')).resolve()
FROZEN = Path(arg('--frozen', STAGE1 / f'frozen_{CASE}.json')).resolve()
BUILD = Path(arg('--out')).resolve()
READER = arg('--reader')
sys.path.insert(0, str(STAGE1))
os.chdir(STAGE1)
import make_typed as M  # noqa: E402

assert Path(M.HERE).resolve() == STAGE1, (M.HERE, STAGE1)
M.BUNDLE = str(BUNDLE)
M.the_reader.__defaults__ = (str(BUNDLE),)
M.BUILD = str(BUILD)
M.READER_COPY = os.path.join(M.BUILD, 'reader_e2e.py')
if READER:
    M.READER_SRC = str(Path(READER).resolve())


def main():
    cmd = sys.argv[1]
    if cmd == 'make':
        sys.argv = [str(STAGE1 / 'make_typed.py'), '--case', CASE, '--frozen', str(FROZEN), '--build', str(BUILD)]
        M.main()
    elif cmd == 'e2e':
        import e2e
        assert e2e.M is M
        sys.exit(0 if e2e.run(CASE) else 1)
    elif cmd == 'identity':
        import test_identity
        assert test_identity.M is M
        test_identity.BUILD = M.BUILD
        r = test_identity.run(CASE)
        for k in ('mechanical', 'program', 'functions', 'committed'):
            print(f'[{CASE}] PASS {k}: {r[k]}')
    elif cmd == 'pages':
        import json
        import e2e
        assert e2e.M is M
        d = os.path.join(M.BUILD, CASE)
        rec, frames = e2e.pages(CASE, json.load(open(os.path.join(d, 'build.json'))))
        open(os.path.join(d, 'pages.json'), 'w').write(json.dumps(rec, indent=1) + '\n')
        print(json.dumps(rec))
        sys.exit(0 if rec.get('gen_rc') == 0 and rec.get('verify_rc') == 0 else 1)
    else:
        raise SystemExit(f'unknown command {cmd}')


if __name__ == '__main__':
    main()
