"""w4_lastpage.py -- set I's last page with the CURRENT generator (never typed).

The pipeline's build/r2/page_p2.* carry the old block CRC; this regenerates a
3-page payload of the same length (11,756 B: the first 11,756 bytes of
build/r2/payload.bin; 453 chunks, the last page 45) with bootstrap/r2/gen.py
into build/w4/p2f4/, and renders the same eight frames as the pipeline's
page_p2.* with the camera parameters recorded in their sidecars
(build/w4/p2/page_p2.*.json): preset, every parameter, frame or crop, seed,
quarter turns.  Usage: python w4_lastpage.py

Since the copies went across pages (R2-FORMAT v1, amended 2026-10-20
night) the current generator gives page 2 of this payload all three
groups (453 chunks, no white slot): it no longer makes set I's near-white
page.  The frozen build/w4/p2f4/ predates the amendment; regenerate it with
bootstrap/r2/gen.py at 1d309208, or use a 1-page payload of 45 chunks
(the same slots; r2/xpage_e2e.py part F).
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OLD = os.path.join(ROOT, 'build', 'w4', 'p2')
NEW = os.path.join(ROOT, 'build', 'w4', 'p2f4')
PY = 'env/bin/python'
FRAMES = ('q-tl', 'q-tr', 'q-bl', 'q-br', 'centre', 'q-br-2spm', 'nominal-b045',
          'hard-b030', 'nominal-b030', 'flatbed300')


def render(n):
    sys.path.insert(0, os.path.join(ROOT, 'r2'))
    import camera  # noqa: E402
    t = json.load(open(os.path.join(OLD, f'page_p2.{n}.json')))
    a = [os.path.join(NEW, 'page_p2.pbm'), os.path.join(NEW, f'page_p2.{n}.pgm'),
         '--sidecar', os.path.join(NEW, 'page_p2.json'), '--preset', t['preset'],
         '--seed', str(t['seed']), '--rot90', str(t.get('rot90', 0))]
    for k in camera.PARAMS:
        a += [f'--{k}', repr(t['params'][k])]
    if t.get('crop_frac'):
        a += ['--crop'] + [repr(v) for v in t['crop_frac']]
    camera.main(a)
    return n


def main():
    os.makedirs(NEW, exist_ok=True)
    subprocess.run([PY, os.path.join(ROOT, 'r2', 'gen.py'), 'pages',
                    os.path.join(ROOT, 'build', 'r2', 'payload.bin'),
                    os.path.join(NEW, 'page'), '--length', '11756'], check=True)
    with ProcessPoolExecutor(4) as ex:
        print(list(ex.map(render, FRAMES)))


if __name__ == '__main__':
    main()
