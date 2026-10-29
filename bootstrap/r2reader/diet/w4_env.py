"""w4_env.py -- the extra envelope frames for the 2026-10-20 diet ladder
(never typed).  Renders with the GENERATOR's camera (bootstrap/r2/camera.py,
in-process through its main()) from the generator's pages in build/w1/pages,
plus loupe grid texts with seeded flips, into build/w4/env/, and writes
build/w4/env/manifest.json: case -> frame files (pooled in that order), and
build/w4/env/genie.json: frame -> genie.read() (the truth-pose readout).

The build/w1 renders (seed 1 of every case) are used as they are; this adds
seeds 2 and 3 of the envelope cases, the quarters of the two-page payload,
thirds, close-ups (one bullseye, tilted, any quarter turn) and loupe grids.
Usage: python w4_env.py   (deterministic; at most 4 render processes)
"""
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PAGES = os.path.join(ROOT, 'build', 'w1', 'pages')
ENV = os.path.join(ROOT, 'build', 'w4', 'env')
sys.path.insert(0, os.path.join(ROOT, 'r2'))


def cam(args):
    name, page, argv = args
    import camera  # noqa: E402  (bootstrap/r2)
    out = os.path.join(ENV, name + '.pgm')
    if not os.path.exists(out):
        camera.main([os.path.join(PAGES, page + '.pbm'), out,
                     '--sidecar', os.path.join(PAGES, page + '.json')] + argv)
    import genie  # noqa: E402
    return name, genie.read(out, os.path.join(PAGES, page))


def loupe(name, page, flips, seed, turns=0):
    rows = [ln.strip() for ln in open(os.path.join(PAGES, page + '.grid.txt'))]
    rng = random.Random(seed)
    g = [[int(c) ^ (rng.random() < flips) for c in r] for r in rows]
    for _ in range(turns):                       # quarter turns clockwise
        g = [[g[len(g) - 1 - i][c] for i in range(len(g))] for c in range(len(g[0]))]
    open(os.path.join(ENV, name + '.txt'), 'w').write(
        ''.join(''.join('01'[v] for v in r) + '\n' for r in g))
    return name + '.txt'


def main():
    os.makedirs(ENV, exist_ok=True)
    side = json.load(open(os.path.join(PAGES, 'one.json')))
    wd, hd = side['page_w_dots'], side['page_h_dots']
    jobs, man = [], {}

    def add(case, frames):
        man[case] = []
        for name, page, argv in frames:
            jobs.append((name, page, argv))
            man[case].append(name + '.pgm')

    nom = ['--preset', 'nominal']
    for s in (2, 3):
        add(f'whole-2-030 s{s}', [(f'one.n030-s{s}', 'one', nom + ['--blur', '0.30', '--seed', str(s)])])
        add(f'whole-2-045 s{s}', [(f'one.n045-s{s}', 'one', nom + ['--blur', '0.45', '--seed', str(s)])])
        add(f'whole-15-030 s{s}', [(f'one.h030-s{s}', 'one',
                                    ['--preset', 'hard', '--blur', '0.30', '--seed', str(s)])])
        add(f'mid s{s}', [(f'one.mid-s{s}', 'one', nom + ['--spm', '3', '--blur', '0.45', '--frame', 'mid',
                                                       '--seed', str(s)])])
    add('flatbed300 s2', [('one.fb-s2', 'one', ['--preset', 'flatbed300', '--seed', '2'])])
    add('rot+4 s2', [('one.r+4-s2', 'one', nom + ['--blur', '0.30', '--rotate', '4', '--seed', '2'])])
    add('rot-4 s2', [('one.r-4-s2', 'one', nom + ['--blur', '0.30', '--rotate', '-4', '--seed', '2'])])
    add('rot-4 turn1 s3', [('one.r-4t1-s3', 'one', nom + ['--blur', '0.30', '--rotate', '-4',
                                                          '--rot90', '1', '--seed', '3'])])
    add('rot+4 turn3 s3', [('one.r+4t3-s3', 'one', nom + ['--blur', '0.30', '--rotate', '4',
                                                          '--rot90', '3', '--seed', '3'])])
    rng = random.Random(20261020)
    q = ['--preset', 'nominal', '--spm', '3', '--blur', '0.45', '--persp', '0.02']
    add('pool one quarters s2 turned', [
        (f'one.q{f}-s2', 'one', q + ['--frame', f, '--rot90', str(rng.randrange(4)), '--seed', '2'])
        for f in ('tl', 'tr', 'bl', 'br')])
    add('pool two pages 8 quarters', [
        (f'{p}.q{f}', p, q + ['--frame', f, '--seed', str(3 + i)])
        for i, (p, f) in enumerate([(p, f) for p in ('two_p0', 'two_p1')
                                    for f in ('tl', 'tr', 'bl', 'br')])])
    add('pool one thirds', [(f'one.{f}', 'one', ['--preset', 'nominal', '--spm', '2.5', '--blur', '0.3',
                                                  '--frame', f, '--seed', '4'])
                             for f in ('top', 'mid', 'bot')])
    add('pool two pages s2', [('two_p0.n030-s2', 'two_p0', nom + ['--blur', '0.30', '--seed', '2']),
                              ('two_p1.n030-s2', 'two_p1', nom + ['--blur', '0.30', '--seed', '3'])])
    dmg = [('be:4', 'be4'), ('be:11', 'be11'), ('bt:0+8', 'bt0+8'), ('blot-at:200:300:6', 'blot200'),
           ('ring-bullseye:7', 'ringb7'), ('scratch-v-dark', 'scr-v-dark'),
           ('scratch-d-white', 'scr-d-white'), ('torn:0', 'torn0'), ('crop-L', 'crop-L'),
           ('crop-B', 'crop-B'), ('crop-R', 'crop-R')]
    for kind, tag in dmg:
        add(f'dmg {tag} s2', [(f'one.dmg-{tag}-s2', 'one', nom + ['--blur', '0.30', '--seed', '202',
                                                                 '--damage', kind])])
    bulls = [b['centre_dots_xy'] for b in side['bullseyes']]
    for i, k in enumerate((0, 4, 8, 13)):
        cx, cy = bulls[k]
        rot = (4, -4, 2, -2)[i]
        add(f'closeup b{k} rot{rot:+d}', [(f'one.cu-b{k}', 'one', [
            '--preset', 'nominal', '--spm', '4', '--blur', '0.3', '--persp', '0.02',
            '--crop', str((cx - 360) / wd), str((cy - 360) / hd), str(720 / wd), str(720 / hd),
            '--rotate', str(rot), '--rot90', str(i % 4), '--seed', str(10 + i)])])
    for i, k in enumerate((1, 6, 10, 14)):
        cx, cy = bulls[k]
        rot = (-4, 4, -3, 3)[i]
        add(f'near b{k} rot{rot:+d}', [(f'one.near-b{k}', 'one', [
            '--preset', 'nominal', '--spm', '3', '--blur', '0.45', '--persp', '0.02',
            '--crop', str((cx - 780) / wd), str((cy - 780) / hd), str(1560 / wd), str(1560 / hd),
            '--rotate', str(rot), '--rot90', str((i + 1) % 4), '--seed', str(20 + i)])])
    with ProcessPoolExecutor(4) as ex:
        gen = dict(ex.map(cam, jobs))
    for s in (1, 2, 3):
        man[f'loupe-0.2 s{s}'] = [loupe(f'one.loupe02-s{s}', 'one', 0.002, s, turns=s - 1)]
    man['loupe-0.2 two pages'] = [loupe('two_p0.loupe02', 'two_p0', 0.002, 4),
                                  loupe('two_p1.loupe02', 'two_p1', 0.002, 5, turns=2)]
    json.dump(man, open(os.path.join(ENV, 'manifest.json'), 'w'), indent=1)
    json.dump(gen, open(os.path.join(ENV, 'genie.json'), 'w'), indent=1)
    for c, fr in man.items():
        print(c, [(f, gen.get(f[:-4], {}).get('data_crc_ok'), gen.get(f[:-4], {}).get('data_in_frame'),
                   gen.get(f[:-4], {}).get('bullseyes_in_frame')) for f in fr])


if __name__ == '__main__':
    main()
