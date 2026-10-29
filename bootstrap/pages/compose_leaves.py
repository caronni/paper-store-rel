"""compose_leaves.py -- leaves 3 and 4 from the loader of record (rulings of
2026-10-19 evening; loader v3 with cm2 v2 and the R2 pages of R2-FORMAT v1,
2026-10-20).  Not typed.  Deterministic.

  leaf3.txt  header (how to type and run a.py) + every line of loader/a.py as
             'nn <text, leading spaces shown as U+00B7, padded to 72>  <code>'
             -- the line number in the left margin, the 4-glyph check code
             in the RIGHT margin after column 72 of the text; neither typed.
  leaf4.txt  '%data-page' marker (consumed by render_pdf.py: per-character
             data-page layout) + header (the rules of the data, and how to
             feed r.py the photos of the R2 pages) + every line of
             loader/data.txt as 'nn ' + the 60 payload glyphs in groups of
             5 separated by ONE space + TWO spaces + the 4-glyph check; the
             LAST line (fewer glyphs) is padded with spaces so its check sits
             in the column of the checks above.  render_pdf.py sets the
             single space as half a cell, the double space as one full cell,
             and the padded check in the full lines' check column.  A leaf 4
             of more than 63 lines (the readable stage-2 reader) runs onto
             further sheets in the viewing PDF.

Usage: python3 compose_leaves.py [--pdf OUT.pdf] [--loader DIR] [--out DIR] [--r2 DIR]
  --loader DIR reads a.py, codes.txt, data.txt from DIR (default loader/);
  --out DIR writes leaf3.txt and leaf4.txt into DIR (default pages/);
  --r2 DIR takes the R2 pages below from DIR (default build/r2, the 10-20
  record; build.py passes its own build/build-py/r2).
  --pdf renders plate leaf1/leaf2/leaf2b, leaf3, leaf4, then every R2 page
  <--r2 DIR>/page_p{P}.pbm (P = 0, 1, ...; its overt leaf header set in type
  below the grid, "VOLUME {V}  R2 LEAF n OF m") each followed by its
  <--r2 DIR>/page_p{P}.nominal-b030.pgm render, into OUT.pdf (viewing render,
  not a print job).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOADER = os.path.join(ROOT, 'loader')
PLATE = os.path.join(ROOT, 'plate')
R2B = os.path.join(ROOT, 'build', 'r2')
WIDTH = 72
CHECK = 4
DOT = '·'


def constants(a):
    """The print's constants in loader v3's a.py (cm2 v2): N = the reader's
    bytes (r=d(v,N,a)), C = the data lines (while n<C+1:), R = the reader's
    code, and the r.py slice a[START:END] (the program's own, not the
    print's).  -> (N, C, R, START, END)"""
    N = int(re.search(r'r=d\(v,(\d+),a\)', a).group(1))
    C = int(re.search(r'while n<(\d+):', a).group(1)) - 1
    R = re.search(r"k\(0,r\)=='(\w{4})'", a).group(1)
    s0, s1 = map(int, re.search(r'write\(a\[(\d+):(\d+)\]\+r\)', a).groups())
    return N, C, R, s0, s1


def leaf3(a, codes, dots='lead', head=None):
    """dots='lead' (the print of record): leading spaces shown as DOT;
    dots='all' (ruling 30, stage 1): every space shown as DOT.  head: the
    leaf's header lines (default: the print of record's, from constants(a))."""
    al = a.strip('\n').split('\n')
    if head is None:
        N, C, R, s0, s1 = constants(a)
        head = [
            'VOLUME {V}  R1 LEAF 3  THE PROGRAM. Type the text of each line below into',
            f'a file named a.py, exactly. Each {DOT} is one space (one per indent level);',
            'no space at the end of a line. The number on the left and the 4-glyph',
            'code on the right are not typed. Run:  python3 a.py',
            'It prints every line\'s number and code: each code must equal the one',
            'on the right; a line whose code differs is mistyped. Then it shows [1]',
            'and waits for the data of leaf 4: stop it (Ctrl-C) and fix the file',
            'unless every code matched. If it stops before printing codes, fix the',
            'line it names. Run it in the folder that holds a.py; no auto-indent',
            '(a tab or four spaces changes every indented line\'s code), no blank',
            f'line inside the file. The numbers {N} and {C + 1} and the code',
            f"'{R}' belong to this print only; {s0} and {s1} to the program.",
            '',
        ]
    body = []
    for i, (t, c) in enumerate(zip(al, codes), 1):
        n, code = c.split()
        assert int(n) == i and len(code) == CHECK and len(t) <= WIDTH
        if dots == 'all':
            shown = t.replace(' ', DOT)
        else:
            lead = len(t) - len(t.lstrip(' '))
            shown = DOT * lead + t[lead:]
        body.append(f'{i:2d} {shown:<{WIDTH}}  {code}')
    return '\n'.join(head + body) + '\n'


FULL = 60                 # payload glyphs of a full data line


def grouped(t):
    p = t[:-CHECK]
    g = ' '.join(p[i:i + 5] for i in range(0, len(p), 5))
    return g.ljust(FULL + FULL // 5 - 1) + '  ' + t[-CHECK:]


def leaf4(a, data, head=None, first=1):
    """head: the header lines (default: the print of record's, from
    constants(a)); first: the number of the first data line (1; stage 1's
    self-dump counter numbers the data after the listing)."""
    if head is None:
        N, C, R, s0, s1 = constants(a)
        assert len(data) == C
        head = [
            '%data-page',
            'VOLUME {V}  R1 LEAF 4  THE DATA. When a.py shows [n], type data line n:',
            'its 60 glyphs (fewer on the last line) and then its 4-glyph check. The',
            'spaces may be typed or left out. The glyphs are 0-9 and lowercase a-z',
            'without i l o u: what looks like i or l is 1, o is 0, u is v. A capital',
            'is a typo. If [n] comes back, the line was refused: type it again.',
            'The check of line n: start with the number n; for each glyph g of the',
            'line, n = ((n + ASCII code of g) x 1000003) mod 1048576. The check is',
            'n written as 4 glyphs of 5 bits each, highest first (0=0 ... z=31).',
            f'After line {C} the program ends without a word and leaves the file r.py:',
            'that is success. Any error message means a wrong line slipped through:',
            'run a.py again and type all data lines again; nothing is kept.',
            'Next run:  python3 r.py   (in the same folder; never open or re-save',
            'r.py). It asks for files of the R2 pages, one name a line: photos or',
            'scans as PGM (P5), whole pages or parts, any way up, or a page\'s module',
            'grid typed as rows of 0 and 1. Photograph close up and more than once,',
            'sharp, the camera square to the page (within 10 degrees), at least',
            '2 pixels per module (a whole page: 0.75 megapixels or more).',
            'It asks again until the data is complete, then checks and writes b.py;',
            'an empty line stops it. An error message there: the frames or r.py are',
            'wrong; a wrong frame is harmless, start r.py again.',
            '',
        ]
    nw = max(2, len(str(first + len(data) - 1)))   # right-aligned (3 digits from line 100)
    body = [f'{n:{nw}d} {grouped(t)}' for n, t in enumerate(data, first)]
    return '\n'.join(head + body) + '\n'


def r2_pages(r2b=R2B):
    """The R2 pages in R2B (build/r2/): [(page bitmap, nominal render or None)]."""
    if not os.path.isdir(r2b):
        return []
    ps = sorted(int(m.group(1)) for f in os.listdir(r2b)
                for m in [re.fullmatch(r'page_p(\d+)\.pbm', f)] if m)
    assert ps == list(range(len(ps))), ('pages not numbered 0..m-1', ps)
    out = []
    for p in ps:
        nom = os.path.join(r2b, f'page_p{p}.nominal-b030.pgm')
        out.append((os.path.join(r2b, f'page_p{p}.pbm'), nom if os.path.exists(nom) else None))
    return out


def main():
    A = sys.argv
    src = A[A.index('--loader') + 1] if '--loader' in A else LOADER
    dst = A[A.index('--out') + 1] if '--out' in A else HERE
    a = open(os.path.join(src, 'a.py')).read()
    codes = open(os.path.join(src, 'codes.txt')).read().split('\n')
    data = open(os.path.join(src, 'data.txt')).read().split('\n')[:-1]
    out3, out4 = os.path.join(dst, 'leaf3.txt'), os.path.join(dst, 'leaf4.txt')
    open(out3, 'w', encoding='utf-8').write(leaf3(a, codes))
    open(out4, 'w', encoding='utf-8').write(leaf4(a, data))
    print('wrote', os.path.relpath(out3, ROOT), os.path.relpath(out4, ROOT))
    if '--pdf' in sys.argv:
        import render_pdf
        out = sys.argv[sys.argv.index('--pdf') + 1]
        r2b = A[A.index('--r2') + 1] if '--r2' in A else R2B
        pages = r2_pages(r2b)
        assert pages, f'no R2 page under {os.path.relpath(r2b, ROOT)}/: run bootstrap/build.py'
        inputs = [os.path.join(PLATE, f) for f in ('leaf1.txt', 'leaf2.txt', 'leaf2b.txt')] + [out3, out4]
        for p, (pbm, nom) in enumerate(pages, 1):
            inputs.append((pbm, f'VOLUME {{V}}  R2 LEAF {p} OF {len(pages)}'))
            if nom:
                inputs.append(nom)
        render_pdf.main(out, inputs)


if __name__ == '__main__':
    main()
