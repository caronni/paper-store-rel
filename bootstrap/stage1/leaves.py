"""leaves.py -- stage 1's leaves 3 and 4, per case (rulings 30, 43 and 44): the
listing with EVERY space shown as a middle dot (leading and interior; the
header says each dot is one space), the data leaf in the print's case and
numbered as the prompts number it (with the self-dump counter the data lines
continue the listing's numbering), set in the standard OCR-B
(pages/render_pdf.py face 'ocrb': the font file by path, never in the repo;
Menlo with a warning when it is absent).  Not the print of record:
pages/leaf3.txt and leaf4.txt are not touched.  Writes
build/stage1/<case>/leaf3.txt, leaf4.txt, leaves.pdf (leaves 3 and 4, then
every R2 page of build/stage1/<case>/r2/ with its nominal-b030 render when
e2e.py has made them).
--paper-test: build/stage1/paper-test/data-leaves.pdf = the uppercase data
leaf in Menlo, Andale Mono, the standard OCR-B and the redrawn OCR-B, then the
lowercase data leaf in the standard OCR-B (the owner's phone test, ruling 42),
with index.txt (one line: which sheets are which face and case).
Usage: python leaves.py [--case lower|upper ...] [--face NAME] [--listing-face NAME]
       [--paper-test]
Defaults since ruling 51 (2026-10-22): case upper, the listing in Menlo, the
data leaf in Andale Mono (`--face` is the data leaf's face).
"""
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'pages'))
import compose_leaves as CL  # noqa: E402
import render_pdf  # noqa: E402

BUILD = os.path.join(ROOT, 'build', 'stage1')
DOT = CL.DOT


def head3(b):
    first, N, C1, R = b['first_data_line'], b['N'], b['loop_bound'], b['reader_code']
    s0, s1 = b['slice']
    return [
        'VOLUME {V}  R1 LEAF 3  THE PROGRAM. Type the text of each line below into',
        f'a file named a.py, exactly. Each {DOT} is ONE SPACE: type one space for',
        f'every {DOT}, at the start of a line and inside it alike (one {DOT} per indent',
        'level). No space at the end of a line. The number on the left and the',
        '4-glyph code on the right are not typed. Run:  python3 a.py',
        'It prints every line\'s number and code: each code must equal the one',
        f'on the right; a line whose code differs is mistyped. Then it shows [{first}]',
        'and waits for the data of leaf 4: stop it (Ctrl-C) and fix the file',
        'unless every code matched. If it stops before printing codes, fix the',
        'line it names. Run it in the folder that holds a.py; no auto-indent',
        '(a tab or four spaces changes every indented line\'s code), no blank',
        f'line inside the file. The numbers {N} and {C1} and the code',
        f"'{R}' belong to this print only; {s0} and {s1} to the program.",
        '',
    ]


def head4(b, case):
    first, C = b['first_data_line'], b['C']
    last = first + C - 1
    if case == 'lower':
        g = ['spaces may be typed or left out. The glyphs are 0-9 and lowercase a-z',
             'without i l o u: what looks like i or l is 1, o is 0, u is v. A capital',
             'is a typo. If [n] comes back, the line was refused: type it again.']
        z = 'z'
    else:
        g = ['spaces may be typed or left out. The glyphs are 0-9 and capitals A-Z',
             'without I L O U: what looks like I or L is 1, O is 0, U is V. A small',
             'letter is a typo. If [n] comes back, the line was refused: retype it.']
        z = 'Z'
    num = ([f'The data lines are numbered on from the program\'s {first - 1} lines: the',
            f'first is [{first}], the last [{last}].'] if first > 1 else [])
    return ['%data-page',
            'VOLUME {V}  R1 LEAF 4  THE DATA. When a.py shows [n], type data line n:',
            'its 60 glyphs (fewer on the last line) and then its 4-glyph check. The',
            ] + g + num + [
            'The check of line n: start with the number n; for each glyph g of the',
            'line, n = ((n + ASCII code of g) x 1000003) mod 1048576. The check is',
            f'n written as 4 glyphs of 5 bits each, highest first (0=0 ... {z}=31).',
            f'After line {last} the program ends without a word and leaves the file b.py:',
            'that is success. Any error message means a wrong line slipped through:',
            'run a.py again and type all data lines again; nothing is kept.',
            'Next run:  python3 b.py   (in the same folder; never open or re-save',
            'b.py). It asks for files of the R2 pages, one name a line: photos or',
            'scans as PGM (P5), whole pages or parts, any way up, or a page\'s module',
            'grid typed as rows of 0 and 1. Photograph close up and more than once,',
            'sharp, the camera square to the page (within 10 degrees), at least',
            '2 pixels per module (a whole page: 0.75 megapixels or more).',
            'It asks again until the data is complete, then checks and writes c.py;',
            'an empty line stops it. An error message there: the frames or b.py are',
            'wrong; a wrong frame is harmless, start b.py again.',
            '']


def stamp(date, label=''):
    """The leaf's identity line carries the print date (the owner, 2026-10-22:
    "keep the header lines ... and add a date stamp") and, for a test print,
    which face and case the sheet is."""
    return f'    {date}' + (f'    {label}' if label else '')


def head3_bare(b, date, label=''):
    return ['VOLUME {V}  R1 LEAF 3  THE PROGRAM' + stamp(date, label), '']


def head4_bare(b, case, date, label=''):
    return ['%data-page', 'VOLUME {V}  R1 LEAF 4  THE DATA' + stamp(date, label), '']


def run(case, face='andale', prose=False, date=None, label='', listing_face='menlo'):
    # ruling 51 (2026-10-22): the listing in Menlo, the data leaf in Andale
    # Mono, the print's case uppercase; `face` is the data leaf's.
    d = os.path.join(BUILD, case)
    b = json.load(open(os.path.join(d, 'build.json')))
    a = open(os.path.join(d, 'a.py')).read()
    codes = open(os.path.join(d, 'codes.txt')).read().split('\n')
    data = open(os.path.join(d, 'data.txt')).read().split('\n')[:-1]
    date = date or datetime.date.today().isoformat()
    h3 = head3(b) if prose else head3_bare(b, date, label)
    h4 = head4(b, case) if prose else head4_bare(b, case, date, label)
    l3 = CL.leaf3(a, codes, dots='all', head=h3)
    l4 = CL.leaf4(a, data, head=h4, first=b['first_data_line'])
    assert all(len(x) <= 72 for x in h3 + h4[1:]), 'a header line over 72 columns'
    body = [ln for ln in l3.split('\n') if re.match(r'^ ?\d+ ', ln)]
    assert len(body) == b['apy_lines'] and not any(' ' in ln[3:3 + CL.WIDTH].rstrip()
                                                   for ln in body), 'a space left in the listing'
    p3, p4 = os.path.join(d, 'leaf3.txt'), os.path.join(d, 'leaf4.txt')
    open(p3, 'w', encoding='utf-8').write(l3)
    open(p4, 'w', encoding='utf-8').write(l4)
    inputs = [p3, p4]
    r2 = os.path.join(d, 'r2')
    n = 0
    while os.path.exists(os.path.join(r2, f'page_p{n}.pbm')):
        n += 1
    for p in range(n):
        inputs.append((os.path.join(r2, f'page_p{p}.pbm'), f'VOLUME {{V}}  R2 LEAF {p + 1} OF {n}'))
        nom = os.path.join(r2, f'page_p{p}.nominal-b030.pgm')
        if os.path.exists(nom):
            inputs.append(nom)
    hdr = None if prose else ''
    src3 = render_pdf.use_face(listing_face)
    pages = render_pdf.render([p3], listing_face, header=hdr)
    src = render_pdf.use_face(face)
    pages += render_pdf.render(inputs[1:], face, header=hdr)
    pages[0].save(os.path.join(d, 'leaves.pdf'), save_all=True, append_images=pages[1:],
                  resolution=render_pdf.DPI, creationDate='', modDate='')
    print(f'[{case}] leaf3.txt, leaf4.txt, leaves.pdf ({2 + n} leaves + renders; '
          f'listing {listing_face}: {src3}; data {face}: {src})')
    return src


PAPER_TEST = (('upper', 'menlo', 'Menlo'), ('upper', 'andale', 'Andale Mono'),
              ('upper', 'ocrb', 'OCR-B std'),
              ('upper', 'ocrb-redrawn', 'OCR-B redrawn'),
              ('lower', 'ocrb', 'OCR-B std'))
# the identity line must stay within the 72 columns: a longer line shrinks the
# whole text sheet's font and is cut on a data sheet


def paper_test(date=None):
    """One PDF: per (case, face) of PAPER_TEST the LISTING leaf and the DATA
    leaf (the owner, 2026-10-22: "you have not printed a.py"), bare heads with
    the date and the face/case label, no grey viewing line; index.txt says
    which sheets are which; preview-<n>.png per sheet."""
    date = date or datetime.date.today().isoformat()
    out = os.path.join(BUILD, 'paper-test')
    os.makedirs(out, exist_ok=True)
    sheets, index = [], []
    for case, face, label in PAPER_TEST:
        d = os.path.join(BUILD, case)
        b = json.load(open(os.path.join(d, 'build.json')))
        a = open(os.path.join(d, 'a.py')).read()
        codes = open(os.path.join(d, 'codes.txt')).read().split('\n')
        data = open(os.path.join(d, 'data.txt')).read().split('\n')[:-1]
        tag = f'{label} {case}'
        l3 = CL.leaf3(a, codes, dots='all', head=head3_bare(b, date, tag))
        l4 = CL.leaf4(a, data, head=head4_bare(b, case, date, tag), first=b['first_data_line'])
        assert all(len(x) <= 72 for x in head3_bare(b, date, tag) + head4_bare(b, case, date, tag)[1:]), tag
        f3 = os.path.join(out, f'leaf3-{case}-{face}.txt')
        f4 = os.path.join(out, f'leaf4-{case}-{face}.txt')
        open(f3, 'w', encoding='utf-8').write(l3)
        open(f4, 'w', encoding='utf-8').write(l4)
        src = render_pdf.use_face(face)
        got = render_pdf.render([f3, f4], face, header='')
        a0, b0 = len(sheets) + 1, len(sheets) + len(got)
        fell = face != 'menlo' and src == render_pdf.FALLBACK
        index.append(f'pp. {a0}-{b0} {case} {label} (listing, then data)' + (' [FELL BACK TO MENLO]' if fell else ''))
        sheets += got
    pdf = os.path.join(out, 'data-leaves.pdf')
    sheets[0].save(pdf, save_all=True, append_images=sheets[1:], resolution=render_pdf.DPI,
                   creationDate='', modDate='')
    for i, im in enumerate(sheets, 1):
        im.resize((im.width // 3, im.height // 3)).save(os.path.join(out, f'preview-{i:02d}.png'))
    line = f'data-leaves.pdf ({date}): ' + '; '.join(index)
    open(os.path.join(out, 'index.txt'), 'w').write(line + '\n')
    print(line)

if __name__ == '__main__':
    a = sys.argv[1:]
    fc = a[a.index('--face') + 1] if '--face' in a else 'andale'
    lf = a[a.index('--listing-face') + 1] if '--listing-face' in a else 'menlo'
    dt = a[a.index('--date') + 1] if '--date' in a else None
    for c in [a[i + 1] for i, x in enumerate(a) if x == '--case'] or ['upper']:
        run(c, fc, prose='--prose' in a, date=dt, listing_face=lf)
    if '--paper-test' in a:
        paper_test(dt)
