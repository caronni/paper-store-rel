#!/usr/bin/env python3
"""cannot_prog.py -- the 'cannot read' path of the progress-line text
(RESULTS-2026-10-22 section 18), which no acceptance case reaches: one
session per text (build/progress/reader_before.py, r2reader/reader_lite_v1.py)
fed photo 1, a missing file, photo 2, a file that is not a PGM (this
script), photo 3; the photos' primer scratch/typed/r.py under the name b.py,
N2 50533 / B2 327353449 baked in.  Prints both transcripts and whether c.py
== scratch/typed/b.py.  Outputs in build/progress/cannot/.

  python bootstrap/r2reader/changeset/cannot_prog.py
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_sets as RS   # noqa: E402  (PHOTOS, PY, make_typed.put_token)

OUT = os.path.join(RS.ROOT, 'build', 'progress', 'cannot')
TEXTS = {'before': os.path.join(RS.ROOT, 'build', 'progress', 'reader_before.py'),
         'prog': os.path.join(RS.ROOT, 'r2reader', 'reader_lite_v1.py')}


def main():
    want = open(os.path.join(RS.PHOTOS, 'b.py'), 'rb').read()
    feed = [os.path.join(RS.PHOTOS, '1.pgm'), os.path.join(OUT, 'missing.pgm'),
            os.path.join(RS.PHOTOS, '2.pgm'), os.path.abspath(__file__), os.path.join(RS.PHOTOS, '3.pgm')]
    for k, path in TEXTS.items():
        wd = os.path.join(OUT, k)
        shutil.rmtree(wd, ignore_errors=True)
        os.makedirs(wd)
        src = RS.make_typed.put_token(open(path).read(), 'N2', RS.PHOTO_N2)[0]
        src = RS.make_typed.put_token(src, 'B2', RS.PHOTO_B2)[0]
        open(os.path.join(wd, 'v.py'), 'w').write(src)
        shutil.copy2(os.path.join(RS.PHOTOS, 'r.py'), os.path.join(wd, 'b.py'))
        p = subprocess.run([RS.PY, 'v.py'], cwd=wd, input=''.join(f + '\n' for f in feed) + '\n',
                           capture_output=True, text=True, timeout=600)
        got = os.path.join(wd, 'c.py')
        same = os.path.exists(got) and open(got, 'rb').read() == want
        print(f'== {k}: exit {p.returncode}, stderr {p.stderr.strip()[-200:]!r}, c.py == scratch/typed/b.py: {same}')
        sys.stdout.write(p.stdout.replace(RS.PHOTOS + os.sep, '').replace(OUT + os.sep, '').replace(
            os.path.abspath(__file__), 'cannot_prog.py') + '\n')


if __name__ == '__main__':
    main()
