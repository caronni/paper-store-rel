#!/usr/bin/env python3
"""make_pages.py -- the acceptance sets' pages in every format-round
configuration (never typed).

The w4 sets render from four frozen pages: build/w4/w1f4/pages/{one, two_p0,
two_p1} and build/w4/p2f4/page_p2 (the last made by gen.py at 1d309208, before
the copies went across pages, so the current generator cannot regenerate it
from its payload).  A variant differs from the record ONLY inside the 15
bullseye blocks (README: geometry, timing, placement, data blocks and header
bytes are the record's), so each variant page is made from the frozen record
page: its grid's bullseye blocks re-drawn by gen_variant (the variant's RING,
the record's 68 header bits read off the record's header modules and put on
the variant's), the page rendered by gen_variant.render (coarse or dot).

  python make_pages.py check     the transform against the generator builder's
                                 stage-1 sets: transform(record-coarse page) ==
                                 gen_variant's page, .grid.txt and .pbm, for
                                 every configuration and page
  python make_pages.py make      -> build/format-round/sets/CFG/{pages,p2f4}/
Every page: the record render of its source grid == the source .pbm (the
transform's own round trip), the 15 blocks' header bits agree, the variant's
orientation refusal (turned_reads_passing) reported.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_common as C   # noqa: E402

SOURCES = {   # (sub-directory, page name): source prefix (record, frozen)
    ('pages', 'one'): os.path.join(C.BOOT, 'build', 'w4', 'w1f4', 'pages', 'one'),
    ('pages', 'two_p0'): os.path.join(C.BOOT, 'build', 'w4', 'w1f4', 'pages', 'two_p0'),
    ('pages', 'two_p1'): os.path.join(C.BOOT, 'build', 'w4', 'w1f4', 'pages', 'two_p1'),
    ('p2f4', 'page_p2'): os.path.join(C.BOOT, 'build', 'w4', 'p2f4', 'page_p2'),
}


def read_grid(path):
    return np.array([[int(c) for c in ln.strip()] for ln in open(path) if ln.strip()], dtype=np.uint8)


def read_pbm(path):
    raw = open(path, 'rb').read()
    p1 = raw.index(b'\n') + 1
    p2 = raw.index(b'\n', p1) + 1
    w, h = map(int, raw[p1:p2].split())
    return np.unpackbits(np.frombuffer(raw[p2:], dtype=np.uint8)).reshape(h, -1)[:, :w]


def transform(src, kind, rings):
    """-> (grid, page, side, info) for the variant of the record page src."""
    G = C.gen_module('record', 'coarse')
    grid = read_grid(src + '.grid.txt')
    side = json.load(open(src + '.json'))
    g = G.geometry(side['module_dots'])
    for k in ('x0_dots', 'y0_dots', 'page_w_dots', 'page_h_dots', 'W', 'H'):
        assert g[k] == side[k], (src, k)
    assert (G.render(grid, g) == read_pbm(src + '.pbm')).all(), (src, 'record render != pbm')
    hb = None
    for bi, bj in G.BULLSEYES:
        blk = grid[17 * bi + 1:17 * bi + 17, 17 * bj + 1:17 * bj + 17]
        b = [int(blk[r, c]) for r, c in G.HEADER_MODULES]
        assert b[68:] == [0] * 11, (src, 'header tail')
        assert hb is None or b[:68] == hb, (src, 'header bits differ between blocks')
        hb = b[:68]
    assert ''.join(map(str, hb)) == side['header']['bits'], (src, 'sidecar header bits')
    G = C.gen_module(kind, rings)
    ring = np.array([[1 if v == 'ink' else 0 for v in row] for row in G.RING], dtype=np.uint8)
    bits = hb + [0] * (len(G.HEADER_MODULES) - 68)
    for (r, c), x in zip(G.HEADER_MODULES, bits):
        ring[r, c] = x
    out = grid.copy()
    for bi, bj in G.BULLSEYES:
        out[17 * bi + 1:17 * bi + 17, 17 * bj + 1:17 * bj + 17] = ring
    page = G.render(out, g)
    turned = G.turned_reads_passing(bits)
    nside = dict(side)
    if not G.is_record():
        nside['spec'] = side['spec'] + f" + format-round variant {kind}/{rings} (bootstrap/format-round/README.md)"
        nside['variant'] = dict(G.variant_record(), made_by='bootstrap/format-round/measure/make_pages.py '
                                '(the frozen record page, bullseye blocks re-drawn)',
                                source_page=os.path.relpath(src, C.BOOT))
        nside['header'] = dict(side['header'], white_tail_modules=len(G.HEADER_MODULES) - 68,
                               modules_block_local_rc=[list(m) for m in G.HEADER_MODULES])
    info = dict(src=os.path.relpath(src, C.BOOT), modules_changed=int((out != grid).sum()),
                dots_changed_vs_record=int((page != read_pbm(src + '.pbm')).sum()),
                orientation_turned_reads_passing=turned)
    return out, page, nside, info


def write(prefix, grid, page, side):
    G = C.gen_module('record', 'coarse')
    os.makedirs(os.path.dirname(prefix), exist_ok=True)
    with open(prefix + '.grid.txt', 'w', newline='\n') as f:
        for row in grid:
            f.write(''.join('01'[v] for v in row) + '\n')
    G.write_pbm(prefix + '.pbm', page)
    side = dict(side)
    side['files'] = {'.grid.txt': C.sha(prefix + '.grid.txt'), '.pbm': C.sha(prefix + '.pbm')}
    json.dump(side, open(prefix + '.json', 'w'), indent=1)


def check():
    rec = os.path.join(C.STAGE1_PAGES, 'record-coarse')
    bad = 0
    for cfg in C.CONFIGS:
        k, r = C.kind_of(cfg), C.rings_of(cfg)
        for p in (0, 1, 2):
            grid, page, side, info = transform(os.path.join(rec, f'page_p{p}'), k, r)
            ref = os.path.join(C.STAGE1_PAGES, cfg, f'page_p{p}')
            gok = (grid == read_grid(ref + '.grid.txt')).all()
            pok = (page == read_pbm(ref + '.pbm')).all()
            ry = json.load(open(ref + '.json'))
            hok = side['header'] == ry['header']
            print(f'{cfg} p{p}: grid {"==" if gok else "!="} pbm {"==" if pok else "!="} '
                  f'header record {"==" if hok else "!="} gen_variant; {info}')
            bad += not (gok and pok and hok)
    print('check', 'PASS' if not bad else f'FAIL {bad}')
    return bad


def make():
    rec = {}
    for cfg in C.CONFIGS:
        k, r = C.kind_of(cfg), C.rings_of(cfg)
        for (sub, name), src in SOURCES.items():
            grid, page, side, info = transform(src, k, r)
            dst = os.path.join(C.SETS_OUT, cfg, sub, name)
            write(dst, grid, page, side)
            info['pbm_sha256'] = C.sha(dst + '.pbm')
            rec[f'{cfg}/{sub}/{name}'] = info
            print(cfg, sub, name, info, flush=True)
            if cfg == 'record-coarse':
                assert info['pbm_sha256'] == C.sha(src + '.pbm'), (cfg, name)
    C.jdump(rec, os.path.join(C.SETS_OUT, 'pages.json'))


if __name__ == '__main__':
    {'check': check, 'make': make}[sys.argv[1]]()
