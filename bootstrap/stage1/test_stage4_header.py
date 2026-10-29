"""test_stage4_header.py -- make_sheets_v2.py's stage-4 margin header (the
owner's ruling of 2026-10-23), on a synthetic page with the volume's field
(rows 148..6868, columns 176..4784 at 600 dpi):
  1. the strips' ink lies between the clip line (CLIP_MM) and the field's
     first ink column, nothing outside the strip column changes, the page
     number's strip starts at the field's first ink row (its text ends
     there, reading bottom to top) and the header's ends at the last + 1;
  2. a header longer than the field beside it is refused with a message, and
     so is a field that leaves no margin between the clip line and itself;
  3. the headed PostScript of a one-imagemask page carries the column as a
     second imagemask before showpage, the page itself unchanged;
  4. when the volume and the lead's sample are on disk (build/stage3/e2e/
     T1/vol, build/sheets/sample/): page 1 headed with the header derived
     from the volume's manifest (stage4_header) in grey equals
     stage4-p1-header-sample.png pixel for pixel, and in 1 bit that PNG
     through Pillow's convert('1') (the sample PDF's page).
Usage: python test_stage4_header.py   or   pytest bootstrap/stage1/test_stage4_header.py
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_sheets_v2 as M  # noqa: E402

BUILD = os.path.join(os.path.dirname(HERE), 'build')
HEAD = 'BOOTSTRAP     RELEASE 2115a595 - STAGE 4 PAYLOAD C3-K-R0547 Q=0.5     2026-10-23'
FY0, FY1, FX0, FX1 = 148, 6868, 176, 4784


def field():
    a = np.zeros((M.PS.PAGE[1], M.PS.PAGE[0]), np.uint8)
    a[FY0:FY1:7, FX0:FX1] = 1
    a[FY0:FY1, FX0:FX1:5] = 1
    a[FY1 - 1, FX0:FX1] = 1
    return a


def test_strip_in_the_margin():
    a = field()
    for num in ('1/15', '15/15'):
        im, col, bits, rec = M.margin_header(a, HEAD, num)
        ink = ~np.array(im)
        side = ink.copy()
        side[:, FX0:] = False
        xs = np.flatnonzero(side.any(0))
        ys = np.flatnonzero(side.any(1))
        assert xs[0] >= M.CLIP_MM * M.MM2 and xs[-1] < FX0, (xs[0], xs[-1])
        assert FY0 <= ys[0] and ys[-1] < FY1
        assert (ink[:, FX0:] == (a[:, FX0:] == 1)).all()
        assert col[1] == FY0 and col[3] == FY1
        assert (bits == ink[col[1]:col[3], col[0]:col[2]]).all() and not side[:, :col[0]].any()
        n, h = M.margin_strip(num), M.margin_strip(HEAD)
        assert not bits[n.height:FY1 - FY0 - h.height].any()           # the two strips, the white between
        assert bits[:n.height].any() and bits[-h.height:].any()
        assert 4.6 < rec['header_ink_mm'][0] and rec['header_ink_mm'][2] < 7.0, rec


def test_long_header_refused():
    try:
        M.margin_header(field(), HEAD * 3, '1/15')
    except SystemExit as e:
        assert 'do not fit' in str(e), e
    else:
        raise AssertionError('a header longer than the field was accepted')
    narrow = field()
    narrow[FY0:FY1, 120:FX0] = narrow[FY0:FY1, FX0:FX0 + FX0 - 120]  # the field starts at x 120: no margin
    try:
        M.margin_header(narrow, HEAD, '1/15')
    except SystemExit as e:
        assert 'leaves the margin' in str(e), e
    else:
        raise AssertionError('a strip column reaching the field was accepted')


def test_headed_ps():
    a = field()
    im, col, bits, _ = M.margin_header(a, HEAD, '1/15')
    page = ('%!PS-Adobe-3.0\n%%BoundingBox: 0 0 596 842\n%%Page: 1 1\ngsave\n21.120000 17.760000 translate\n'
            'IMAGE\ngrestore\nshowpage\n%%Trailer\n%%EOF\n')
    out = M.headed_ps(page, col, bits)
    head, rest = out.split('IMAGE\ngrestore\n')
    assert head == page.split('IMAGE')[0] and rest.endswith('grestore\nshowpage\n%%Trailer\n%%EOF\n')
    w, h = col[2] - col[0], col[3] - col[1]
    assert f'{w} {h} true [{w} 0 0 -{h} 0 {h}]\n' in rest and f'{col[0] * 0.12:.6f} 17.760000 translate' in rest
    hx = ''.join(rest.split('imagemask\n')[1].split('>')[0].split())
    assert bytes.fromhex(hx) == np.packbits(bits, axis=1).tobytes()


def test_sample_page_1():
    vol = os.path.join(BUILD, 'stage3', 'e2e', 'T1', 'vol', 'page000.k.npy')
    smp = os.path.join(BUILD, 'sheets', 'sample', 'stage4-p1-header-sample.png')
    if not (os.path.exists(vol) and os.path.exists(smp)):
        print('test_sample_page_1: skipped, no volume or sample on disk')
        return
    a, ref = np.load(vol), Image.open(smp)
    import json
    man = json.load(open(os.path.join(os.path.dirname(vol), 'manifest.json')))
    head = M.stage4_header(man, '2026-10-23')
    assert head == HEAD, head                       # the values come from the volume, not the literal
    im, _, _, _ = M.margin_header(a, head, '1/15', grey=True)
    assert (np.array(im) == np.array(ref)).all(), 'page 1 is not the sample'
    im, _, _, _ = M.margin_header(a, head, '1/15')
    assert (np.array(im) == np.array(ref.convert('1'))).all(), 'page 1, 1 bit, is not the sample PDF\'s page'


if __name__ == '__main__':
    for t in (test_strip_in_the_margin, test_long_header_refused, test_headed_ps, test_sample_page_1):
        t()
        print(t.__name__, 'ok')
