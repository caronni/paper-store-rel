#!/usr/bin/env python3
"""grid_test.py -- the loupe path after the change set (never typed): the
Plate's one-liner (r2reader/grid_to_pgm.py) on the diet's text grids, then
the reader, in process with a spy on rb (as run_sets.slots), per block row
and column of the page lattice.

Grids: build/w4/w1f4/pages/one.grid.txt (clean) and build/w4/sets4/
one.loupe02-s{1,2}.txt (0.2 % flips, set H and the margin case) -- each whole,
one row short (the last line not typed), two rows short, one column short
(the last character of every line not typed).  Conversions: the one-liner
(six white modules) and, as controls for the padding's purpose, the same
construction with 4, 2 and 0 white modules (in Python here; the 6 case is
checked byte-identical to the one-liner's output).  Readers: each file given;
one that still has the text-grid branch also reads the grid text natively.
Per run: data blocks read of those printed, chunks held of the page's,
done (every chunk + the data CRC), and the data blocks read in the first and
last block row and column.  -> build/changeset/grid_test.json + a table.

  python grid_test.py READER.py [...]
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
R2R = os.path.dirname(HERE)
ROOT = os.path.dirname(R2R)
sys.path.insert(0, HERE)
import run_sets as R   # noqa: E402

OUT = os.path.join(ROOT, 'build', 'changeset', 'grid_test')
PAGES = os.path.join(ROOT, 'build', 'w4', 'w1f4', 'pages')
GRIDS = {'clean': os.path.join(PAGES, 'one.grid.txt'),
         'loupe s2': os.path.join(ROOT, 'build', 'w4', 'sets4', 'one.loupe02-s2.txt'),
         'loupe s1': os.path.join(ROOT, 'build', 'w4', 'sets4', 'one.loupe02-s1.txt')}
CUTS = {'whole': lambda r: r, 'row short': lambda r: r[:-1], '2 rows short': lambda r: r[:-2],
        'column short': lambda r: [x[:-1] for x in r]}


def pgm(rows, pad):
    w = max(map(len, rows)) + 2 * pad
    e = [''] * pad
    return b'P5 %d %d 255\n' % (w, len(rows) + 2 * pad) + bytes(
        255 * (c < '1') for ln in e + rows + e for c in ('0' * pad + ln).ljust(w, '0'))


def read_grid(ns, frame, side, pad):
    """-> (blocks read per data slot set, chunks, done)"""
    got = []
    rb = ns['rb']

    def spy(*a):
        out = rb(*a)
        if out:
            got.append((a[0][0] / 16, a[0][1] / 16, out))
        return out
    ns['rb'] = spy
    ns['h'], ns['j'], ns['z'] = ns['ld'](frame)
    ns['e'] = b''
    r = ns['fm']()
    e = r[1]
    ns['e'] = e
    blocks = ns['wk'](*r[0]) if e else []
    ns['rb'] = rb
    data = {tuple(b): c for b, c in zip(side['slot_block'], side['slot_chunk']) if c is not None}
    sc = 3 if pad is None else 1          # the native text path draws 3 px per module
    off = 12 if pad is None else pad      # ... after 4 white modules
    read = set()
    for x, y, _ in got:
        bj, bi = round((x / sc - off - 9) / 17), round((y / sc - off - 9) / 17)
        if (bi, bj) in data:
            read.add((bi, bj))
    held = {int.from_bytes(b[:2], 'big') for b in blocks}
    n = side['chunk_count']
    return read, held, data, n, bool(e)


def main():
    readers = [os.path.abspath(a) for a in sys.argv[1:]]
    os.makedirs(OUT, exist_ok=True)
    side = json.load(open(os.path.join(PAGES, 'one.json')))
    BW, BH = max(b[1] for b in side['slot_block']), max(b[0] for b in side['slot_block'])
    # the one-liner, byte for byte, against pgm(.., 6) on the whole grids
    for g, path in GRIDS.items():
        o = os.path.join(OUT, 'oneliner.pgm')
        subprocess.run([R.PY, R.G2P, path, o], check=True)
        rows = open(path).read().split()
        assert open(o, 'rb').read() == pgm(rows, 6), ('one-liner differs', g)
    print('the one-liner == pgm(rows, 6) on', list(GRIDS))
    res = []
    for rd in readers:
        name = os.path.basename(rd)[:-3]
        native = R.has_grid_branch(rd)
        for g, path in GRIDS.items():
            rows = open(path).read().split()
            for cut, fn in CUTS.items():
                rr = fn(rows)
                for pad in (6, 4, 2, 0) + ((None,) if native else ()):
                    if pad is None:
                        fr = os.path.join(OUT, f'{g}-{cut}.txt'.replace(' ', '_'))
                        open(fr, 'w').write(''.join(x + '\n' for x in rr))
                    else:
                        fr = os.path.join(OUT, f'{g}-{cut}-pad{pad}.pgm'.replace(' ', '_'))
                        open(fr, 'wb').write(pgm(rr, pad))
                    ns = R.ns_of(rd)
                    try:
                        read, held, data, n, hdr = read_grid(ns, fr, side, pad)
                        err = ''
                    except Exception as ex:   # noqa: BLE001  (recorded)
                        read, held, data, n, hdr, err = set(), set(), {}, side['chunk_count'], False, repr(ex)[:120]
                    done = hdr and all(i in held for i in range(n))
                    edge = {k: sum(1 for b in read if f(b)) for k, f in (
                        ('top', lambda b: b[0] == 0), ('bottom', lambda b: b[0] == BH),
                        ('left', lambda b: b[1] == 0), ('right', lambda b: b[1] == BW))}
                    tot = {k: sum(1 for b in data if f(b)) for k, f in (
                        ('top', lambda b: b[0] == 0), ('bottom', lambda b: b[0] == BH),
                        ('left', lambda b: b[1] == 0), ('right', lambda b: b[1] == BW))} if data else {}
                    row = dict(reader=name, grid=g, cut=cut, pad='text' if pad is None else pad,
                               data_read=len(read), data=len(data), held=len(held & set(range(n))),
                               need=n, done=done, edge=edge, edge_total=tot, err=err)
                    res.append(row)
                    print(f"{name:16s} {g:9s} {cut:13s} pad {row['pad']!s:4s} data {len(read)}/{len(data)} "
                          f"chunks {row['held']}/{n} done={done} edges {edge} of {tot} {err}", flush=True)
    json.dump(res, open(os.path.join(ROOT, 'build', 'changeset', 'grid_test.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
