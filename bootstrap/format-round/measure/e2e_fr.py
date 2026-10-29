#!/usr/bin/env python3
"""e2e_fr.py -- stage1/e2e.py unchanged but for its page step: e2e.pages is
replaced by a copy that calls format-round/gen/gen_variant.py (--bullseye
FR_KIND --rings FR_RINGS) and format-round/gen/verify_variant.py (the same
flags) where e2e.pages calls r2/gen.py and r2/verify_grid.py; the payload,
the camera arguments and everything else as e2e.pages.  Same arguments as
e2e.py (--case ... --build DIR).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_common as C   # noqa: E402

sys.path.insert(0, os.path.join(C.BOOT, 'stage1'))
import e2e as E2   # noqa: E402

KIND, RINGS = os.environ['FR_KIND'], os.environ['FR_RINGS']
M, ROOT = E2.M, E2.ROOT
FLAGS = ['--bullseye', KIND, '--rings', RINGS]


def pages(case, b):
    import gen
    d = os.path.join(M.BUILD, case, 'r2')
    os.makedirs(d, exist_ok=True)
    bundle = open(M.BUNDLE, 'rb').read()
    bpy = open(os.path.join(M.BUILD, case, 'b.py'), 'rb').read()
    z = M.cm2_enc.encode(bundle, bpy, tuple(b['orders']))
    open(os.path.join(d, 'payload.bin'), 'wb').write(z)
    p = subprocess.run([M.PY, C.GEN, 'pages', 'payload.bin', 'page'] + FLAGS,
                       cwd=d, capture_output=True, text=True)
    rec = dict(payload_bytes=len(z), pages=gen.n_pages(len(z)),
               capacity_bytes=gen.geometry()['capacity_bytes'] * gen.n_pages(len(z)),
               chunks=gen.n_chunks(len(z)), gen_rc=p.returncode, generator=os.path.relpath(C.GEN, ROOT),
               generator_flags=FLAGS)
    if p.returncode:
        rec['gen_stderr'] = p.stderr.strip()[-300:]
        return rec, []
    grids = [f'page_p{q}.grid.txt' for q in range(rec['pages'])]
    v = subprocess.run([M.PY, C.VERIFY] + grids + ['--payload', 'payload.bin', '--pbm'] + FLAGS,
                       cwd=d, capture_output=True, text=True)
    rec['verify_grid'] = v.stdout.strip().split('\n')[-1]
    rec['verify_rc'] = v.returncode
    frames = []
    for q in range(rec['pages']):
        f = f'page_p{q}.nominal-b030.pgm'
        r = subprocess.run([M.PY, os.path.join(ROOT, 'r2', 'camera.py'), f'page_p{q}.pbm', f,
                            '--sidecar', f'page_p{q}.json', '--preset', 'nominal', '--blur',
                            '0.30', '--seed', '1'], cwd=d, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-1000:]
        frames.append(os.path.join(d, f))
    sides = [json.load(open(os.path.join(d, f'page_p{q}.json'))) for q in range(rec['pages'])]
    rec['chunks_per_page'] = [s['chunk_count'] for s in sides]
    rec['headroom_bytes'] = rec['capacity_bytes'] - len(z)
    rec['variant'] = sides[0].get('variant', {}).get('kind', 'record'), sides[0].get('variant', {}).get('rings', 'coarse')
    return rec, frames


E2.pages = pages

if __name__ == '__main__':
    a = sys.argv[1:]
    if '--build' in a:
        M.BUILD = os.path.abspath(a[a.index('--build') + 1])
    cases = [a[i + 1] for i, x in enumerate(a) if x == '--case'] or ['lower', 'upper']
    oks = [E2.run(c, '--no-pages' not in a) for c in cases]
    sys.exit(0 if all(oks) else 1)
