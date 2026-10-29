"""print_sheets.py -- the stage 1-3 sheets of the for-print PDF (ruling 62,
2026-10-23: rendering only, the payloads frozen).  Called by
make_sheets_v2.py, which appends the 15 stage-4 pages, their bitmaps unchanged
and the margin strip of make_sheets_v2.margin_header laid into the left
margin (7 pt Menlo rotated to read bottom to top, ink at x 4.7-6.9 mm:
"BOOTSTRAP     RELEASE <commit> - STAGE 4 PAYLOAD <row> Q=<q>     <date>"
from the field's bottom corner up, "n/N" ending at its top corner), and
writes print-DATE.pdf.

Every sheet is A4 at 600 dpi with a header at the top in the sheet's
monospace face, one character per CELL_MM cell from the 10 mm margin, its
baseline HEAD_BASE_MM below the top edge, so the three fields (BOOTSTRAP,
program and stage, date) sit in the same columns on all four sheets:
  sheet 1  leaf 3 (the listing, Menlo) without its identity line
  sheet 2  leaf 4 (the data sheet, Andale Mono) without its identity line,
           its line numbers set [n] as a.py's prompts show them, right-
           justified, each ']' flush left of the line's first data glyph
           (ruling 63; bracket_data_page)
  sheets 3-4  the R2 page bitmaps, 1 bit, the header in the raster's top
           margin above the grid (Menlo), no caption below the grid.
Sheets 1 and 2 are rendered by pages/render_pdf.py's text_page and by
bracket_data_page (data_page's layout with the bracketed numbers; both at
300 dpi, its 10 mm margins), doubled pixel for pixel to 600 dpi, and get in
the free space AIR_MM below their text's lowest ink: the cross-placed QR
code (sheet 1 the data sheet's lines, sheet 2 a.py), right-bound to the
rightmost ink of the text above it (sheet 1 the margin, sheet 2 the data
block's edge, 12.9 mm in; 2026-10-23), its caption under it; left of it, from the sheet's left margin, the owner's
instruction text of 2026-10-23 verbatim (TEXT_PT, the sheet's face, first
cap height level with the QR's top, the paragraphs re-wrapped to the column,
no command split); and under both, from the left margin, the code the text
calls "the code below": grid_to_pgm.py's last line as its python3 -c
command (no arguments: the line names grid.txt and grid.pgm), every space
a middle dot (CODE_PT Menlo, hard-wrapped at statement boundaries, no
character added or dropped).  The QR module matrices are read
from stage1/qr/ (qr-a.pbm, qr-d.pbm, made once by qr/make_qr.py); qr.json
holds the sha of each code's input, and a build whose a.py or data.txt
moved is refused.
"""
import hashlib
import json
import os
import sys
import textwrap

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(BOOT, 'pages'))
import render_pdf as RP  # noqa: E402

QR_DIR = os.path.join(HERE, 'qr')
GRID_TO_PGM = os.path.join(BOOT, 'r2reader', 'grid_to_pgm.py')
DPI = 600
UP = DPI // RP.DPI                       # the text sheets doubled
MM = DPI / 25.4
CELL = RP.CELL_MM * MM                   # the header's character cell (the data sheet's)
HEAD_BASE_MM = 14.0                      # the header's baseline below the top edge
TEXT_PT = 8                              # the instructions, in the sheet's face
CAPTION_PT = 7                           # the QR captions, in the sheet's face
CODE_PT = 10                             # the code block, Menlo on both sheets (7 until 2026-10-23)
MODULE_DOTS = 14                         # QR module 14 dots = 0.593 mm
QUIET = 4                                # QR quiet zone, modules
AIR_MM = 12.0                            # the payload text's lowest ink -> the QR's ink and the first cap height
GAP_MM = 5.0                             # the instruction column -> the QR's quiet zone
CODE_AIR_MM = 5.0                        # the instructions and the caption -> the code block
LEADING = 1.3                            # the instructions' line pitch, in font sizes
PARA_AIR = 0.6                           # air between the paragraphs, in line pitches
CODE_LEADING = 1.3
LEFT = RP.MARGIN * UP                    # 10 mm
PAGE = (4960, 7016)                      # A4 at 600 dpi, the R2 pages' size (render_pdf's
                                         # 300-dpi sheet doubled is 4960 x 7014: padded white)
RIGHT = PAGE[0] - RP.MARGIN * UP
BOTTOM = PAGE[1] - RP.MARGIN * UP


def sha(b):
    return hashlib.sha256(b).hexdigest()


def headers(date, n_r2):
    """The four headers: BOOTSTRAP, program and stage, date in fixed columns."""
    progs = ['A.PY - STAGE 1 INPUT READER', 'B.PY - STAGE 2 DATA SHEET']
    progs += [f'C.PY - STAGE 3 MONOLITH {p}/{n_r2}' for p in range(1, n_r2 + 1)]
    w = max(map(len, progs))
    out = [f'BOOTSTRAP   {p:<{w}}   {date}' for p in progs]
    assert all(len(h) <= 72 for h in out) and len({h.index(date) for h in out}) == 1
    return out


def data_lines(text):
    """The data sheet's lines as a finder types them: data.txt's lines with
    the two spaces before the check as printed, the group spaces dropped
    (as printed, 3,036 B, they do not fit a version-40 QR at level L)."""
    ls = text.split('\n')
    assert ls[-1] == '' and all(ls[:-1])
    return ''.join(f'{t[:-4]}  {t[-4:]}\n' for t in ls[:-1]).encode('ascii')


def qr_inputs(upper):
    """{'qr-a': a.py's bytes, 'qr-d': the data lines} of a stage-1 build."""
    return {'qr-a': open(os.path.join(upper, 'a.py'), 'rb').read(),
            'qr-d': data_lines(open(os.path.join(upper, 'data.txt')).read())}


def load_qr(name, data, source):
    """The stored module matrix of QR `name` (True = dark), refused unless its
    recorded input sha is the sha of `data` and its source's sha the sha of
    the file `source` (the build's a.py or data.txt)."""
    meta = json.load(open(os.path.join(QR_DIR, 'qr.json')))[name]
    if sha(open(source, 'rb').read()) != meta['source_sha256']:
        raise SystemExit(f'{name}: {source} is not the file the stored QR was made from '
                         f'({meta["source_sha256"][:16]}...): run stage1/qr/make_qr.py')
    if sha(data) != meta['input_sha256']:
        raise SystemExit(f'{name}: the stored QR encodes {meta["input_sha256"][:16]}..., the build has '
                         f'{sha(data)[:16]}... ({meta["source"]} moved): run stage1/qr/make_qr.py')
    p = os.path.join(QR_DIR, name + '.pbm')
    assert sha(open(p, 'rb').read()) == meta['pbm_sha256'], p
    dark = ~np.array(Image.open(p).convert('1'))
    n = 17 + 4 * meta['version']
    assert dark.shape == (n, n), (p, dark.shape)
    for y, x in ((0, 0), (0, n - 7), (n - 7, 0)):          # the three finder patterns
        f = dark[y:y + 7, x:x + 7]
        assert f[0].all() and f[6].all() and f[:, 0].all() and f[:, 6].all() and f[2:5, 2:5].all() \
            and not f[1, 1:6].any(), (p, 'finder')
    return dark, meta


def face_font(face, size_px):
    """The face's first present file, else Menlo (render_pdf.use_face's fallback;
    make_sheets_v2.font_lines reports what was drawn)."""
    src = next((s for s in RP.FACES[face] if isinstance(s, str) and os.path.exists(s)), RP.FALLBACK)
    return RP._truetype(src, size_px)


def cell_font(face):
    s = 10
    while face_font(face, s + 1).getlength('M') <= CELL:
        s += 1
    return face_font(face, s)


def draw_header(im, text, face):
    """The header in the sheet's face, one character per CELL from the left
    margin, baseline at HEAD_BASE_MM -> its bounding box."""
    f = cell_font(face)
    y = round(HEAD_BASE_MM * MM) - f.getmetrics()[0]
    d = ImageDraw.Draw(im)
    RP.draw_line(d, LEFT, y, text, f, cell=CELL)
    box = d.textbbox((LEFT, y), text, font=f)
    return (box[0], box[1], LEFT + round(len(text) * CELL), box[3])


def pt_font(face, pt):
    return face_font(face, round(pt / 72 * DPI))


NBSP = ' '
KEEP = ('Python >= 3.11', 'djpeg -grayscale p.jpg > p.pgm', '9@ 150/', 'line 2', 'line 67', '(1 = ink)')


def wrap(t, cols):
    """t at cols, the KEEP spans (and the whole line when t is a lone command)
    never broken across lines; no word added, dropped or split."""
    for k in KEEP:
        t = t.replace(k, k.replace(' ', NBSP))
    out = [ln.replace(NBSP, ' ') for ln in textwrap.wrap(t, cols, break_long_words=False, break_on_hyphens=False,
                                                         replace_whitespace=False)]
    assert max(map(len, out)) <= cols, ('a word wider than the column', out)
    return out


def alphabet_line(b, apy):
    """The number of the one line of a.py that holds the alphabet string."""
    alpha = b['alphabet']
    assert alpha[:10] == '0123456789' and alpha == ''.join(sorted(alpha))
    hits = [i for i, t in enumerate(apy.split('\n'), 1) if f"'{alpha}'" in t]
    assert len(hits) == 1, ('the alphabet is not on exactly one line of a.py', hits)
    return hits[0]


def grid_command():
    """grid_to_pgm.py's last line as the shell command (it names grid.txt and
    grid.pgm itself, no arguments), every space a middle dot."""
    grid = open(GRID_TO_PGM).read().rstrip('\n').split('\n')[-1]
    assert '"' not in grid and '·' not in grid and '$' not in grid and '`' not in grid
    return f'python3 -c "{grid}"'.replace(' ', '·')


def code_lines(cmd, cols):
    """The command in lines of at most cols, no character added or dropped:
    the fewest lines plus break penalties (0 after a statement's ';' or a
    ')+' before a name, 1 after a visible space, 2 after a ',', 5 inside a
    quoted string), then the shortest longest line."""
    quoted, inq = [], None
    for ch in cmd:
        if inq is None and ch in "\'\"" or ch == inq:
            inq = ch if inq is None else None
        quoted.append(inq not in (None, '"'))                 # the -c argument itself is the outer "..."

    def pen(k):
        ch = cmd[k]
        if quoted[k]:
            return 5
        if ch == ';' or ch == '+' and cmd[k - 1] == ')' and cmd[k + 1].isalpha():
            return 0
        return {'\u00b7': 1, ',': 2}.get(ch)

    cut = [(k + 1, pen(k)) for k in range(1, len(cmd) - 1) if pen(k) is not None]
    best = {0: (0, 0, [])}                       # break -> (lines + penalties, longest, breaks)
    for k, p in sorted(cut) + [(len(cmd), 0)]:
        opts = [(c + 1 + p, max(w, k - j), bs + [k]) for j, (c, w, bs) in best.items() if 0 < k - j <= cols]
        if opts:
            best[k] = min(opts)
    assert len(cmd) in best, ('the command does not break into lines of', cols)
    bs = [0] + best[len(cmd)][2]
    return [cmd[a:b] for a, b in zip(bs, bs[1:])]


def paragraphs(b, pages, sheet, apy):
    """The owner's text of 2026-10-23, verbatim (sheet 2 says 'of sheet 1' for
    'above'; the opening parenthesis of paragraph 2 added) -> paragraphs, each
    a list of its hard lines (paragraph 3 sets the djpeg example on a line of
    its own, as he wrote it); the numbers of the build asserted."""
    k = alphabet_line(b, apy)
    assert k == 2, ('the alphabet moved off line 2 of a.py', k)
    first, last, n_a = b['first_data_line'], b['first_data_line'] + b['C'] - 1, b['apy_lines']
    assert last == b['loop_bound'] - 1 and first == n_a + 1 and (n_a, last) == (28, 67)
    assert pages['chunks'] == 390, pages['chunks']    # 383 for c.py 92c48a39 (9,947 B), 390 for b4f7de22 (10,133 B)
    where = 'above' if sheet == 1 else 'of sheet 1'
    return [
        [f'Type the {n_a} lines {where} into a.py, middle dots are spaces. Do not enter the checksums. Run a.py '
         'with Python >= 3.11. Verify the checksums. They must match exactly as a.py seeds the decompressor.'],
        [f'At each prompt: Type its data line from sheet 2, the alphabet is in line {k} of a.py, spaces optional. '
         f'After line {last} a.py writes b.py.'],
        ['Run b.py. Provide grey images (photo or scan) of entire or partial stage 3 pages until c.py is written. '
         'Images are 8-bit grey PGM (P5) files,',
         'e.g.  djpeg -grayscale p.jpg > p.pgm',
         f'The line 9@ 150/{pages["chunks"]} means: bullseyes found on current image, total blocks held of needed. '
         'Without a camera: write the image dots as text lines of 0/1 (1 = ink) in grid.txt and convert them to a '
         'PGM along the lines of the code below.'],
        ['Scan the dense archive sheets grey to PGM and run c.py: it writes payload.bin, decodes the archive and '
         'unpacks the release.'],
    ]


def place_qr(im, dark, x_right, y_top):
    """The modules, ink right edge at x_right, quiet zone top at y_top -> the
    ink box (x0, y0, x1, y1)."""
    n = dark.shape[0]
    side = n * MODULE_DOTS
    x0, y0 = x_right - side, y_top + QUIET * MODULE_DOTS
    a = np.array(im)
    q = QUIET * MODULE_DOTS
    assert (a[y0 - q:y0 + side + q, x0 - q:x0 + side + q] == 255).all(), 'the QR quiet zone is not blank'
    a[y0:y0 + side, x0:x0 + side] = np.where(np.kron(dark, np.ones((MODULE_DOTS, MODULE_DOTS), bool)), 0, 255)
    im.paste(Image.fromarray(a))
    return x0, y0, x0 + side, y0 + side


def bracket_data_page(lines, nw):
    """render_pdf.data_page's per-character CELL_MM layout (300 dpi, its
    margins, its face), the line number printed as the prompt shows it, [n],
    right-justified in nw + 2 cells so every closing bracket sits one cell
    left of the first data glyph, one cell of air between (ruling 63); the groups, the half-cell
    gaps and the check column as data_page sets them, one cell further right."""
    im = Image.new('L', RP.A4, 255)
    d = ImageDraw.Draw(im)
    cell = RP.CELL_MM / 25.4 * RP.DPI
    font = RP.font_for_width(int(cell), 1)
    pitch = (RP.A4[1] - 2 * RP.MARGIN) // (RP.ROWS + 1)

    def put(x, y, ch):
        if RP.has_glyph(font, ch):
            d.text((x + (cell - font.getlength(ch)) / 2, y), ch, font=font, fill=0)
        else:
            RP.draw_line(d, x, y, ch, font, cell=cell)

    lay = []
    for i, line in enumerate(lines[:RP.ROWS]):
        y, x = RP.MARGIN + (i + 1) * pitch, RP.MARGIN
        m = RP.DATA_LINE.match(line)
        if not m:
            for ch in line.rstrip('\n'):
                put(x, y, ch)
                x += cell
            continue
        num, groups, chk = m.groups()
        for ch in f'[{num}]'.rjust(nw + 2):
            put(x, y, ch)
            x += cell
        x += cell                      # one cell of air after the bracket
        x0 = x
        for g in groups.split(' '):
            for ch in g:
                put(x, y, ch)
                x += cell
            x += cell / 2
        x += cell / 2
        x = max(x, RP.MARGIN + (nw + 3 + RP.FULL_GROUPS * 5.5 + 0.5) * cell)
        xc = x
        for ch in chk:
            put(x, y, ch)
            x += cell
        assert x <= RP.A4[0] - RP.MARGIN, 'data line wider than the page'
        lay.append(tuple(round((v - RP.MARGIN) / cell, 6) for v in (x0, xc, x)))
    assert len({v[0] for v in lay}) == 1 and len({v[1] for v in lay}) == 1
    return im, dict(number_cells=[0, nw + 2], first_data_cell=lay[0][0], check_cell=lay[0][1],
                    line_end_cells=max(v[2] for v in lay), cell_mm=RP.CELL_MM)


def ink_rows(im):
    """The first and last rows of im holding ink."""
    r = np.flatnonzero((np.array(im) < 255).any(axis=1))
    return int(r[0]), int(r[-1])


def text_sheet(lines, face, data, head, qr, caption, b, pages, sheet, apy):
    """Sheet 1 or 2: the leaf's lines by render_pdf, doubled to 600 dpi, the
    header; in the free space below, AIR_MM under the text's lowest ink: the
    QR right-bound with its caption under it, the owner's text left of it
    (its first cap height level with the QR's top), and under both, from the
    left margin, the code block.  -> (image, layout record, the printed
    lines)"""
    RP.use_face(face)
    if data:
        nw = max([2] + [len(m.group(1)) for m in map(RP.DATA_LINE.match, lines) if m])
        im300, numcol = bracket_data_page(lines, nw)
    else:
        im300 = RP.text_page(lines, '')
    im = Image.new('L', PAGE, 255)
    im.paste(im300.resize((im300.width * UP, im300.height * UP), Image.NEAREST), (0, 0))
    pitch = (RP.A4[1] - 2 * RP.MARGIN) // (RP.ROWS + 1)
    first_row = UP * (RP.MARGIN + 2 * pitch)                       # row 1 (row 0 is blank)
    hb = draw_header(im, head, face)
    assert hb[3] < first_row, ('the header reaches the text', hb, first_row)
    assert (np.array(im)[hb[3] + 1:first_row] == 255).all()
    text_bottom = ink_rows(im)[1]
    top = text_bottom + round(AIR_MM * MM)                         # the QR's ink top
    q = QUIET * MODULE_DOTS
    dark, meta = qr
    text_right = int(np.where((np.array(im)[first_row:text_bottom + 1] < 128).any(0))[0][-1])
    qb = place_qr(im, dark, text_right + 1, top - q)                # right-bound to the text's right ink edge
    assert qb[1] == top
    d = ImageDraw.Draw(im)
    fc = pt_font(face, CAPTION_PT)
    cy = qb[3] + q - fc.getbbox('Q')[1]                            # the caption's cap height one quiet zone under
    d.text((qb[0], cy), caption, font=fc, fill=0)
    cb = d.textbbox((qb[0], cy), caption, font=fc)
    assert cb[2] <= RIGHT, ('the caption', cb)
    f = pt_font(face, TEXT_PT)
    adv = f.getlength('M')
    x_lim = qb[0] - q - round(GAP_MM * MM)
    cols = int((x_lim - LEFT) // adv)
    lp = round(f.size * LEADING)
    y = top - f.getbbox('T')[1]                                    # the first cap height level with the QR's top
    ins, boxes = [], []
    for para in paragraphs(b, pages, sheet, apy):
        if ins:
            y += round(lp * PARA_AIR)
        for hard in para:
            got = wrap(hard, cols)
            assert ' '.join(got) == hard, ('the wrap changed the words', hard)
            for ln in got:
                RP.draw_line(d, LEFT, y, ln, f)
                boxes.append(d.textbbox((LEFT, y), ln, font=f))
                ins.append(ln)
                y += lp
    ib = (LEFT, min(bx[1] for bx in boxes), max(bx[2] for bx in boxes), max(bx[3] for bx in boxes))
    assert ib[2] <= x_lim, ('the instructions reach the QR', ib, x_lim)
    fk = pt_font('menlo', CODE_PT)
    kadv = fk.getlength('M')
    kx, ky0 = LEFT, max(ib[3], cb[3])                             # under both, the sheet's left margin
    kcols = int((RIGHT - kx) // kadv)
    code = code_lines(grid_command(), kcols)
    grid = open(GRID_TO_PGM).read().rstrip('\n').split('\n')[-1]
    assert ''.join(code).replace('·', ' ') == f'python3 -c "{grid}"'
    ky = ky0 + round(CODE_AIR_MM * MM) - fk.getbbox('T')[1]
    klp = round(fk.size * CODE_LEADING)
    kboxes = []
    for ln in code:
        RP.draw_line(d, kx, ky, ln, fk, cell=kadv)
        kboxes.append(d.textbbox((kx, ky), ln, font=fk))
        ky += klp
    kb = (kx, min(bx[1] for bx in kboxes), max(bx[2] for bx in kboxes), max(bx[3] for bx in kboxes))
    assert kb[2] <= RIGHT and kb[3] <= BOTTOM, ('the code block', kb)
    assert ink_rows(im)[1] == max(kb[3], cb[3], ib[3], qb[3]) - 1 <= BOTTOM, 'ink outside the boxes'
    rec = dict(header=head, header_box_mm=[round(v / MM, 1) for v in hb],
               qr=dict(name=meta['name'], version=meta['version'], modules=dark.shape[0],
                       module_mm=round(MODULE_DOTS / MM, 3), ink_box_mm=[round(v / MM, 1) for v in qb]),
               caption=caption, caption_box_mm=[round(v / MM, 1) for v in cb],
               instructions_box_mm=[round(v / MM, 1) for v in ib], instruction_lines=len(ins),
               instruction_cols=cols, small_font_px=f.size, caption_font_px=fc.size,
               text_bottom_mm=round(text_bottom / MM, 1),
               code_box_mm=[round(v / MM, 1) for v in kb], code_lines=len(code), code_cols=kcols,
               code_font_px=fk.size, bottom_air_mm=round((BOTTOM - ink_rows(im)[1]) / MM, 1))
    if data:
        rec['data_layout'] = numcol
    return im, rec, ins + code


def r2_sheet(pbm, head):
    """An R2 page: the bitmap with the header in its top margin."""
    im = Image.open(pbm).convert('1')
    assert im.size == PAGE, im.size
    src = np.array(im)
    g = json.load(open(os.path.splitext(pbm)[0] + '.json'))
    hb = draw_header(im, head, 'menlo')
    out = np.array(im)
    m = np.zeros_like(src, dtype=bool)
    m[hb[1]:hb[3] + 1, hb[0]:hb[2] + 1] = True
    assert (out[~m] == src[~m]).all() and (src[m]).all(), 'the header touched the grid'
    assert hb[3] < g['y0_dots'] - 4 * g['module_dots'], ('the header is too close to the grid', hb)
    return im, dict(header=head, header_box_mm=[round(v / MM, 1) for v in hb],
                    grid_top_mm=round(g['y0_dots'] / MM, 1), pbm_sha256=sha(open(pbm, 'rb').read()))


def build(upper, date):
    """The four stage 1-3 sheets -> (images, record)."""
    b = json.load(open(os.path.join(upper, 'build.json')))
    pages = json.load(open(os.path.join(upper, 'pages.json')))
    r2 = os.path.join(upper, 'r2')
    n_r2 = 0
    while os.path.exists(os.path.join(r2, f'page_p{n_r2}.pbm')):
        n_r2 += 1
    assert n_r2 == pages['pages'] == b['r2_pages']
    heads = headers(date, n_r2)
    inp = qr_inputs(upper)
    qa = load_qr('qr-a', inp['qr-a'], os.path.join(upper, 'a.py'))
    qd = load_qr('qr-d', inp['qr-d'], os.path.join(upper, 'data.txt'))
    apy = open(os.path.join(upper, 'a.py')).read()
    l3 = open(os.path.join(upper, 'leaf3.txt'), encoding='utf-8').read().split('\n')
    l4 = open(os.path.join(upper, 'leaf4.txt'), encoding='utf-8').read().split('\n')
    assert l3[0].startswith('VOLUME {V}  R1 LEAF 3') and l3[1] == ''
    assert l4[0] == RP.DATA_MARK and l4[1].startswith('VOLUME {V}  R1 LEAF 4') and l4[2] == ''
    l3, l4 = l3[1:], [l4[0]] + l4[2:]                  # the identity lines out, the text unchanged
    while l3[-1] == '':
        l3.pop()
    while l4[-1] == '':
        l4.pop()
    s1, r1, i1 = text_sheet(l3, 'menlo', False, heads[0], qd,
                            "QR: the data sheet's 39 lines, as typed at a.py's prompts", b, pages, 1, apy)
    s2, r2r, i2 = text_sheet(l4[1:], 'andale', True, heads[1], qa,
                             'QR: a.py, the 28 lines of sheet 1', b, pages, 2, apy)
    assert b['C'] == 39 and b['apy_lines'] == 28
    sheets, recs = [s1, s2], [r1, r2r]
    for p in range(n_r2):
        im, rec = r2_sheet(os.path.join(r2, f'page_p{p}.pbm'), heads[2 + p])
        sheets.append(im)
        recs.append(rec)
    return sheets, dict(sheets=recs, instructions={'sheet 1': i1, 'sheet 2': i2},
                        grid_to_pgm_sha256=sha(open(GRID_TO_PGM, 'rb').read()),
                        qr={k: json.load(open(os.path.join(QR_DIR, 'qr.json')))[k] for k in ('qr-a', 'qr-d')})
