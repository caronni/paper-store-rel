"""make_sheets_v2.py -- the sheets of the bootstrap chain, stages 1-3, as PDF:
build/sheets/make_sheets.py (the interim set of 2026-10-23) with its inputs
and outputs explicit, for the candidate print of record v2 (the convergence
of ruling 60, CONVERGENCE-2026-10-23.md, re-run in CONVERGENCE-2026-10-23b.md)
and bootstrap/rebuild_v2.py.

Inputs:
  --s1 DIR   a stage-1 chain build with c.py as the content (stage1/chain_v2.py
             make, both cases, plus its R2 pages: chain_v2.py pages): DIR/upper/
             {a.py, codes.txt, data.txt, build.json, r2/page_p*.pbm + .json}
             and DIR/lower/{sizes.txt, build.json};
  --vol DIR  the stage-3 volume (stage3/e2e_c.py volume: build/stage3/e2e/T1/vol,
             c3-k-r0547@35x24, the record's T1 container): page0NN.k.npy, .ps,
             _gt.npy, manifest.json, each page checked against its imagemask
             and the manifest's shas;
  --c-py, --reader, --template, --frozen-dir: the texts whose shas the
             manifest records;
  --out DIR  where the PDFs, previews and MANIFEST.txt go;
  --date     the identity lines' date (default 2026-10-23).
Stages 1 and 2 (ruling 34: stage 1 = a.py, stage 2 = the data sheet): leaf 3
(the listing, Menlo) and leaf 4 (the data, Andale Mono) set
by stage1/leaves.py's run() (its BUILD pointed at --s1), bare heads with the
identity line and the date, rendered by pages/render_pdf.py at 300 dpi.
Stage 3: the R2 pages gen.py made, the 600-dpi bitmaps themselves, 1 bit,
each with its leaf caption drawn in type 2 mm below the grid at 600 dpi.
Stage 4: the 15 holo K pages (the archive sheets), each with its HEADER in
the left margin (the owner's ruling of 2026-10-23, after the printed sample),
the bitmap not shifted: HEAD4_PT Menlo, turned to read bottom to top, centred
in the white between the M281's print clip CLIP_MM (e028) and the field's
first ink column (text 4.7-6.9 mm from the left edge); the header starts at
the field's bottom edge, 'BOOTSTRAP     RELEASE <commit> - STAGE 4 PAYLOAD
<row> Q=<q>     <date>' (the commit stage3/e2e_c.py's T1_COMMIT, the row and
q the volume manifest's), the page number n/N ends at the field's top edge
(the manifest's boxes give y from the page's top edge, as the images do).
The strips are drawn in grey and made 1 bit by Pillow's convert('1'), the
lead's sample of that day reproduced pixel for pixel; the headed PostScript
of the same pages, OUT/stage4-ps/page0NN.ps, is holo's page0NN.ps with the
margin column as a second imagemask before showpage, rendered back by
ghostscript equal to the PDF's page.  The chain PDF has all of them at
600 dpi (the text sheets doubled pixel for pixel).  Every 1-bit page is
checked by rendering the PDF back with ghostscript at 600 dpi.
The FOR-PRINT PDF (ruling 62), print-DATE.pdf: the stage 1-3 sheets of
stage1/print_sheets.py (headers at the top, the cross-placed QR codes read
from stage1/qr/, the instructions; the R2 pages without the caption below
the grid), then the 15 stage-4 pages appended unchanged (their image
streams byte-equal to stage4-archive-pages.pdf's, checked); previews
preview-print-01..05.png (the four stage 1-3 sheets and the first stage-4
page, a third of 600 dpi).  The two system faces (Menlo, Andale Mono; macOS's,
not redistributable, no copy in the tree) are recorded in MANIFEST.txt by path
and sha256; one that differs from FONT_SHA256 or is missing gives a WARNING
line there and on stderr, never a failure.

  python bootstrap/stage1/make_sheets_v2.py --s1 DIR --vol DIR --out DIR [--c-py P] [--reader P] [--template P] [--frozen-dir D] [--date D]
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zlib

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(BOOT, 'stage1'))
sys.path.insert(0, os.path.join(BOOT, 'pages'))
import leaves  # noqa: E402
import print_sheets as PS  # noqa: E402
import render_pdf as RP  # noqa: E402
from PIL import PdfParser  # noqa: E402

CASE = 'upper'
DPI2 = 600
GS = '/opt/homebrew/bin/gs'
MM2 = DPI2 / 25.4
CLIP_MM = 4.2                            # the M281's print clip, all edges (e028)
HEAD4_PT = 7                             # the stage-4 header, Menlo
E2E_C = os.path.join(BOOT, 'stage3', 'e2e_c.py')   # T1_COMMIT, the release the volume carries
# The faces of the print of record, measured on machine 1 2026-10-23 (macOS 26.7.1).
FONT_SHA256 = {'/System/Library/Fonts/Menlo.ttc':
               'dc256e0b39c2a6fec947129d421fef41b8b429f58f9b6e5d1b148c87f775c1f6',
               '/System/Library/Fonts/Supplemental/Andale Mono.ttf':
               'ca436a8f07f6699107542ebe19dcc9478f12aa666927699e9fa10115e7d2ee95'}


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def font_lines():
    """One 'fonts:' line per face (the source render_pdf.use_face takes: the
    face's path, or Menlo in its place), and a WARNING line, also on stderr,
    when that file is not the print of record's."""
    lines = []
    draws = {'menlo': 'sheets 1-4 (the listing, the code blocks, the R2 headers) and the stage-4 headers',
             'andale': 'sheet 2 (the data sheet)'}
    for face in ('menlo', 'andale'):
        want = RP.FACES[face][0]
        src = RP.use_face(face)
        got = sha(src) if src and os.path.isfile(src) else 'missing'
        lines.append(f'fonts: {face}: {src}, sha256 {got}')
        if src != want or got != FONT_SHA256[want]:
            w = (f'WARNING: font {face}: {src} {got[:16]}, the print of record\'s {want} '
                 f'{FONT_SHA256[want][:16]}...: {draws[face]} not pixel-identical to the print of record')
            print(w, file=sys.stderr)
            lines.append(w)
    return lines


def _g4_strip_only(save):
    """Pillow's PDF writer stores a 1-bit page as its group-4 TIFF minus the
    8-byte header (PdfImagePlugin._write_image: stream = tiff[8:]), so the
    stream carries libtiff's IFD after the G4 data, and that IFD holds a byte
    libtiff leaves uninitialised: the interim build's stage-3 PDF changed sha
    from run to run at equal pixels.  Here the TIFF Pillow writes for the PDF
    is cut to 8 bytes + the one strip (StripOffsets / StripByteCounts), so the
    stream is the G4 data alone: deterministic, the same pixels."""
    def wrapped(self, fp, format=None, **kw):
        if format == 'TIFF' and kw.get('compression') == 'group4' and isinstance(fp, io.BytesIO):
            t = io.BytesIO()
            save(self, t, format, **kw)
            raw = t.getvalue()
            tif = Image.open(io.BytesIO(raw))
            (off,), (cnt,) = tif.tag_v2[273], tif.tag_v2[279]
            fp.write(b'\0' * 8 + raw[off:off + cnt])
            return None
        return save(self, fp, format, **kw)
    return wrapped


def save_pdf(path, pages, dpi):
    save = Image.Image.save
    Image.Image.save = _g4_strip_only(save)
    try:
        pages[0].save(path, save_all=True, append_images=pages[1:], resolution=dpi,
                      creationDate='', modDate='')
    finally:
        Image.Image.save = save


def caption_600(im, side, text):
    """The caption in type below the grid, at 600 dpi: render_pdf.bitmap_page's
    position (the grid's left edge; 2 mm below its bottom edge) and its font
    rule (72 columns across the sheet between 10 mm margins), doubled."""
    g = json.load(open(side))
    x = g['x0_dots']
    y = g['y0_dots'] + g['H'] * g['module_dots'] + int(2 / 25.4 * DPI2)
    RP.use_face('menlo')
    font = RP.font_for_width(2 * (RP.A4[0] - 2 * RP.MARGIN), RP.COLS)
    d = ImageDraw.Draw(im)
    d.text((x, y), text, font=font, fill=0)
    box = d.textbbox((x, y), text, font=font)
    assert box[3] < g['page_h_dots'] - int(4.2 / 25.4 * DPI2), 'caption below the printable edge'
    return box


def stage4_header(man, date):
    """The header of every stage-4 page: the release (T1_COMMIT's first 8 hex),
    the row (c<cell dots>-<family>-<rate> of the manifest's coding), the
    source fraction q (holo generate --source-fraction, the manifest's q_dial)."""
    m = re.search(r'^T1_COMMIT = "([0-9a-f]{40})"', open(E2E_C).read(), re.M)
    assert m, E2E_C
    row = f"c{man['dots_per_cell']}-{man['coding_id'].split('-')[1]}-{man['rate_id']}".upper()
    return f"BOOTSTRAP     RELEASE {m.group(1)[:8]} - STAGE 4 PAYLOAD {row} Q={man['volume']['q_dial']:g}     {date}"


def margin_strip(text):
    """text in HEAD4_PT Menlo (print_sheets.pt_font: render_pdf's face), drawn
    grey at its textbbox offsets with 1 px of white around, turned to read
    bottom to top."""
    f = PS.pt_font('menlo', HEAD4_PT)
    bb = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), text, font=f)
    im = Image.new('L', (bb[2] - bb[0] + 2, bb[3] - bb[1] + 2), 255)
    ImageDraw.Draw(im).text((1 - bb[0], 1 - bb[1]), text, font=f, fill=0)
    return im.rotate(90, expand=True)


def margin_header(a, header, number, grey=False):
    """The stage-4 page a (1 = ink) with header and number in the left margin:
    x0 centres the header's strip between CLIP_MM and the field's first ink
    column, the header's strip ends at the field's last ink row + 1, the
    number's starts at its first.  -> (the page, 1 bit (grey: L), the column
    (x0, y0, x1, y1) both strips lie in, its bits (1 = ink), record);
    refused when the strips meet, reach the clip line or the field."""
    rows, cols = np.flatnonzero(a.any(1)), np.flatnonzero(a.any(0))
    fy0, fy1, fx0 = int(rows[0]), int(rows[-1]) + 1, int(cols[0])
    clip = CLIP_MM * MM2
    h, n = margin_strip(header), margin_strip(number)
    x0 = round((clip + fx0) / 2 - h.width / 2)
    hb = (x0, fy1 - h.height, x0 + h.width, fy1)
    nb = (x0, fy0, x0 + n.width, fy0 + n.height)
    if nb[3] > hb[1]:
        raise SystemExit(f'stage-4 header: {header!r} and {number!r} take {h.height} + {n.height} dots, the field '
                         f'is {fy1 - fy0} dots tall: they do not fit beside it')
    col = (x0, fy0, x0 + max(h.width, n.width), fy1)
    if x0 < clip or col[2] > fx0:
        raise SystemExit(f'stage-4 header: the strip column x {x0}..{col[2]} dots leaves the margin between the '
                         f'clip line ({clip:.1f}) and the field ({fx0})')
    im = Image.fromarray(np.where(a == 1, 0, 255).astype(np.uint8))
    if not grey:
        im, h, n = im.convert('1'), h.convert('1'), n.convert('1')
    im.paste(h, hb[:2])
    im.paste(n, nb[:2])
    ink = np.array(im) < 128 if grey else ~np.array(im)
    m = np.zeros(a.shape, bool)
    m[col[1]:col[3], col[0]:col[2]] = True
    assert (ink[~m] == (a[~m] == 1)).all() and not a[m].any(), 'the header touched the field'
    xs = np.flatnonzero(ink[m.any(1)][:, :fx0].any(0))
    assert xs[0] >= clip and xs[-1] < fx0, ('the header ink', xs[0], xs[-1])

    def box(b):
        ys, xs = np.nonzero(ink[b[1]:b[3], b[0]:b[2]])
        return [round(float(v) / MM2, 1) for v in (b[0] + xs.min(), b[1] + ys.min(), b[0] + xs.max() + 1,
                                                   b[1] + ys.max() + 1)]
    rec = dict(header=header, number=number, header_ink_mm=box(hb), number_ink_mm=box(nb), column_dots=list(col))
    return im, col, ink[col[1]:col[3], col[0]:col[2]], rec


def headed_ps(txt, col, bits):
    """holo's page PostScript with the margin column as a second imagemask (the
    same device dots at 600 dpi, holo's construct) before showpage."""
    x0, y0, x1, y1 = col
    w, h = x1 - x0, y1 - y0
    tail = 'grestore\nshowpage\n'
    assert txt.count(tail) == 1 and '%%BoundingBox: 0 0 596 842\n' in txt
    hx = np.packbits(bits, axis=1).tobytes().hex()
    pt = 72 / DPI2
    mask = (f'gsave\n{x0 * pt:.6f} {(PS.PAGE[1] - y1) * pt:.6f} translate\n{w * pt:.6f} {h * pt:.6f} scale\n'
            f'0.000 0.000 0.000 1.000 setcmykcolor\n{w} {h} true [{w} 0 0 -{h} 0 {h}]\n'
            'currentfile /ASCIIHexDecode filter imagemask\n'
            + ''.join(hx[i:i + 128] + '\n' for i in range(0, len(hx), 128)) + '>\ngrestore\n')
    return txt.replace(tail, 'grestore\n' + mask + 'showpage\n')


def stage4_pages(vol, date, ps_out=None):
    """The 15 stage-4 pages, each checked against its GT and imagemask, headed
    in the left margin; ps_out: the headed PostScript written there."""
    man = json.load(open(os.path.join(vol, 'manifest.json')))
    assert man['format_id'] == '1i200-k-r0547-p100-v1@35x24' and man['volume']['n_pages'] == 15
    oy, ox = man['origin_dots_yx']
    head = stage4_header(man, date)
    pages, rec = [], []
    for pg in man['pages']:
        k = pg['page']
        ps, gt = os.path.join(vol, pg['ps']), os.path.join(vol, pg['gt'])
        g = np.load(gt)
        assert sha(ps) == pg['ps_sha256'] and hashlib.sha256(g.tobytes()).hexdigest() == pg['gt_sha256'], k
        assert list(g.shape) == pg['gt_packed_shape'], k
        a = np.load(os.path.join(vol, f'page{k:03d}.k.npy'))
        assert a.shape == (man['page_dots_xy'][1], man['page_dots_xy'][0]) and a.dtype == np.uint8
        bits = np.unpackbits(g, axis=1, bitorder=pg['gt_bitorder'])
        h, w = bits.shape
        assert (a[oy:oy + h, ox:ox + w] == bits).all() and a.sum() == bits.sum(), k
        txt = open(ps, encoding='ascii').read()
        m = re.search(r'(\d+) (\d+) true \[\1 0 0 -\2 0 \2\]\ncurrentfile /ASCIIHexDecode filter imagemask\n', txt)
        assert m and (int(m.group(1)), int(m.group(2))) == (w, h), k
        hexdata = re.sub(r'\s', '', txt[m.end():].split('>', 1)[0])
        assert bytes.fromhex(hexdata) == g.tobytes(), f'page {k}: the imagemask is not the GT'
        im, col, bits, hr = margin_header(a, head, f"{k + 1}/{len(man['pages'])}")
        assert hr['column_dots'][1:4:2] == [oy, oy + h] and ox == int(np.flatnonzero(a.any(0))[0]), k
        pages.append(im)
        r = dict(page=k, ps_sha256=pg['ps_sha256'], ink_dots=int(a.sum()), **hr)
        if ps_out:
            p = os.path.join(ps_out, pg['ps'])
            open(p, 'w', encoding='ascii').write(headed_ps(txt, col, bits))
            r.update(headed_ps=p, headed_ps_sha256=sha(p))
        rec.append(r)
    return man, pages, rec


def r2_pages(d, date):
    n = 0
    while os.path.exists(os.path.join(d, f'page_p{n}.pbm')):
        n += 1
    pages, rec = [], []
    for p in range(n):
        pbm = os.path.join(d, f'page_p{p}.pbm')
        im = Image.open(pbm).convert('1')
        assert im.size == (4960, 7016), im.size
        src = np.array(im)
        text = f'VOLUME {{V}}  R2 LEAF {p + 1} OF {n}' + leaves.stamp(date)
        box = caption_600(im, os.path.join(d, f'page_p{p}.json'), text)
        out = np.array(im)
        cap = np.zeros_like(src, dtype=bool)
        cap[box[1]:box[3] + 1, box[0]:box[2] + 1] = True
        assert (out[~cap] == src[~cap]).all(), 'the caption touched the module grid'
        pages.append(im)
        rec.append(dict(page=p, pbm=os.path.relpath(pbm, os.path.dirname(BOOT)), pbm_sha256=sha(pbm), caption=text))
    return pages, rec


def gs_check(pdf, pages, dpi):
    """Render the PDF (or a list of PostScript pages) back with ghostscript at
    dpi and compare every pixel of every 1-bit page with its source."""
    with tempfile.TemporaryDirectory() as t:
        subprocess.run([GS, '-q', '-dNOPAUSE', '-dBATCH', '-dSAFER', '-sDEVICE=pgmraw', f'-r{dpi}',
                        '-dInterpolateControl=0', f'-sOutputFile={t}/p%03d.pgm',
                        *([pdf] if isinstance(pdf, str) else pdf)], check=True)
        got = sorted(os.listdir(t))
        assert len(got) == len(pages), (pdf, len(got), len(pages))
        bad = []
        for f, im in zip(got, pages):
            if im.mode != '1':
                continue
            r = np.array(Image.open(os.path.join(t, f))) >= 128
            s = np.array(im)
            if r.shape != s.shape or (r != s).any():
                bad.append((f, r.shape, s.shape, int((r != s).sum()) if r.shape == s.shape else None))
        assert not bad, (pdf, bad)
    return sum(im.mode == '1' for im in pages)


def image_streams(pdf):
    """The image XObjects of a Pillow-written PDF, in object order: [(the
    dictionary without /Length as text, the stream's bytes)]."""
    p = PdfParser.PdfParser(pdf)
    out = []
    for k in sorted(p.xref_table.keys()):
        try:
            o = p.read_indirect(PdfParser.IndirectReference(k, 0))
        except Exception:
            continue
        if isinstance(o, PdfParser.PdfStream) and o.dictionary.get(PdfParser.PdfName(b'Subtype')) == b'Image':
            dic = {n.name: v for n, v in o.dictionary.items() if n.name != b'Length'}
            out.append((repr(sorted(dic.items())), bytes(o.buf)))
    p.close()
    return out


def preview(im, path):
    g = im.convert('L')
    g.resize((im.width // 3, im.height // 3), Image.LANCZOS).save(path)


def arg(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else default


def rel(p):
    return os.path.relpath(os.path.abspath(p), os.path.dirname(BOOT))


def build(s1, vol, out, c_py, reader, template, frozen_dir, date):
    os.makedirs(out, exist_ok=True)
    leaves.BUILD = s1
    face = leaves.run(CASE, 'andale', date=date, listing_face='menlo')
    d = os.path.join(s1, CASE)
    p3, p4 = os.path.join(d, 'leaf3.txt'), os.path.join(d, 'leaf4.txt')
    RP.use_face('menlo')
    s1p = RP.render([p3], 'menlo', header='')
    s1b = RP.render([p4], 'andale', header='')
    n3, n4 = len(s1p), len(s1b)
    s1p += s1b
    out1 = os.path.join(out, 'stages1-2-listing-data-upper.pdf')
    save_pdf(out1, s1p, RP.DPI)
    r2, r2rec = r2_pages(os.path.join(d, 'r2'), date)
    out2 = os.path.join(out, 'stage3-r2-pages.pdf')
    save_pdf(out2, r2, DPI2)
    g2 = gs_check(out2, r2, DPI2)
    psd = os.path.join(out, 'stage4-ps')
    shutil.rmtree(psd, ignore_errors=True)
    os.makedirs(psd)
    man, s3, s3rec = stage4_pages(vol, date, psd)
    out3 = os.path.join(out, 'stage4-archive-pages.pdf')
    save_pdf(out3, s3, DPI2)
    g3 = gs_check(out3, s3, DPI2)
    gps = gs_check([r['headed_ps'] for r in s3rec], s3, DPI2)
    up = [im.resize((im.width * 2, im.height * 2), Image.NEAREST) for im in s1p]
    chain = up + r2 + s3
    outc = os.path.join(out, f'chain-{date}.pdf')
    save_pdf(outc, chain, DPI2)
    gc = gs_check(outc, chain, DPI2)
    for f in os.listdir(out):
        if f.startswith('preview-') and f.endswith('.png'):
            os.remove(os.path.join(out, f))
    for i, im in enumerate(s1p + r2 + s3, 1):
        preview(im, os.path.join(out, f'preview-{i:02d}.png'))
    ps_, prec = PS.build(d, date)
    printp = ps_ + s3
    outp = os.path.join(out, f'print-{date}.pdf')
    save_pdf(outp, printp, DPI2)
    gp = gs_check(outp, printp, DPI2)
    st4 = image_streams(out3)
    assert image_streams(outp)[len(ps_):] == st4 and len(st4) == len(s3), 'the stage-4 pages are not unchanged'
    for i, im in enumerate(printp[:len(ps_) + 1], 1):
        preview(im, os.path.join(out, f'preview-print-{i:02d}.png'))
    b = json.load(open(os.path.join(d, 'build.json')))
    pay = os.path.join(d, 'r2', 'payload.bin')
    files = [('stages1-2-listing-data-upper.pdf', out1, len(s1p)), ('stage3-r2-pages.pdf', out2, len(r2)),
             ('stage4-archive-pages.pdf', out3, len(s3)), (f'chain-{date}.pdf', outc, len(chain)),
             (f'print-{date}.pdf', outp, len(printp))]
    srcs = [('stage1/template.py', template), ('stage1/frozen_lower.json', os.path.join(frozen_dir, 'frozen_lower.json')),
            ('stage1/frozen_upper.json', os.path.join(frozen_dir, 'frozen_upper.json')),
            ('r2reader/reader_lite_v1.py', reader), ('stage3/c.py', c_py)]
    for case in ('lower', 'upper'):
        for f in ('a.py', 'data.txt', 'b.py', 'r2/payload.bin'):
            srcs.append((f'{f} ({case})', os.path.join(s1, case, f)))
    lines = [f'bootstrap sheets of {date}: the candidate print of record v2 (stages 1-4, ruling 34), the fixed point of the',
             'convergence of ruling 60 (bootstrap/CONVERGENCE-2026-10-23.md, re-run on the repaired c.py in',
             'bootstrap/CONVERGENCE-2026-10-23b.md); viewing PDFs, never printed, but',
             f'print-{date}.pdf, the for-print PDF of ruling 62.',
             'Built by bootstrap/rebuild_v2.py (stage1/chain_v2.py make + pages, both cases; stage1/make_sheets_v2.py).',
             '', 'PDFs (sha256, pages, bytes):']
    for name, p, n in files:
        lines.append(f'  {sha(p)}  {name}  ({n} pages, {os.path.getsize(p):,} B)')
    lines.append(f'  ghostscript at {DPI2} dpi, every pixel of every 1-bit page equal: stage 3 (R2) {g2}, '
                 f'stage 4 (archive) {g3}, chain {gc} 1-bit pages of {len(chain)}, print {gp} 1-bit pages '
                 f'of {len(printp)}')
    lines += ['', f'print-{date}.pdf (ruling 62; stage1/print_sheets.py): the stage 1-3 sheets at 600 dpi with '
              'headers, then the', f'  {len(s3)} stage-4 pages appended unchanged (image streams byte-equal to '
              'stage4-archive-pages.pdf\'s)']
    for r in prec['sheets']:
        q = r.get('qr')
        lines.append(f"  {r['header']}  header box {r['header_box_mm']} mm"
                     + (f"; QR {q['name']} v{q['version']} {q['modules']} modules at {q['module_mm']} mm, ink "
                        f"{q['ink_box_mm']} mm; instructions {r['instruction_lines']} lines x {r['instruction_cols']}"
                        f" cols {r['instructions_box_mm']} mm" if q else f"; grid top {r['grid_top_mm']} mm"))
    for k in ('qr-a', 'qr-d'):
        m = prec['qr'][k]
        lines.append(f"  {k}: {m['source']} sha {m['source_sha256'][:16]}..., input {m['input_bytes']} B sha "
                     f"{m['input_sha256'][:16]}..., version {m['version']}-{m['error']} {m['mode']} mask {m['mask']}; "
                     f"{m['decode']}")
    lines.append(f"  r2reader/grid_to_pgm.py sha {prec['grid_to_pgm_sha256'][:16]}... (its last line quoted on "
                 'sheets 1 and 2)')
    lines += ['', 'texts and stage-1 outputs (sha256, bytes):']
    for name, p in srcs:
        lines.append(f'  {sha(p)}  {name}  ({os.path.getsize(p):,} B)')
    c = open(c_py, 'rb').read()
    lines += ['', f"c.py: {len(c):,} B, CRC-32 {zlib.crc32(c)} (the reader's N2 / B2)"]
    for case in ('lower', 'upper'):
        bj = json.load(open(os.path.join(s1, case, 'build.json')))
        lines.append(f"stage 1 ({case}): typed total {bj['typed_total']} = a.py {bj['apy_chars']} chars "
                     f"({bj['apy_lines']} lines) + data {bj['data_chars']} chars ({bj['C']} lines, G {bj['G']} "
                     f"glyphs); reader N {bj['N']}, code {bj['reader_code']}, slice a[{bj['slice'][0]}:"
                     f"{bj['slice'][1]}], b.py {bj['bpy_bytes']} B, orders {tuple(bj['orders'])}; R2 payload "
                     f"{bj['r2_payload_bytes']} B, {bj['r2_pages']} pages (bound {bj['r2_pages_of_record']})")
        pj = os.path.join(s1, case, 'pages.json')
        if os.path.exists(pj):
            pg = json.load(open(pj))
            lines.append(f"  R2 pages ({case}): payload {pg['payload_bytes']} B, {pg['pages']} pages, capacity "
                         f"{pg['capacity_bytes']} B, headroom {pg['headroom_bytes']} B, chunks {pg['chunks']} "
                         f"{pg.get('chunks_per_page')}, verify_grid {pg.get('verify_grid')}")
    lines += ['', f'stages 1-2 sheets: leaf 3 (listing, Menlo) {n3} sheet(s), leaf 4 (data, Andale Mono) {n4} sheet(s); '
              f'data face source {face}',
              *font_lines(),
              'stage 2 sheets: ' + '; '.join(f"leaf {r['page'] + 1}: {r['pbm']} sha {r['pbm_sha256'][:16]}..."
                                             for r in r2rec),
              f"stage 3 sheets: {len(s3)} pages of {man['format_id']} (paper {man['paper']}), payload "
              f"{man['payload']['bytes']:,} B sha {man['payload']['sha256'][:16]}..., k_total "
              f"{man['volume']['k_total']}, {man['volume']['n_symbols_total']} symbols",
              '  ' + '; '.join(f"p{r['page']} ps {r['ps_sha256'][:12]}" for r in s3rec),
              f'stage 4 headers (left margin, {HEAD4_PT} pt Menlo, bottom to top, between the {CLIP_MM} mm clip and '
              f'the field; ink boxes x0 y0 x1 y1 mm); the headed PostScript stage4-ps/ (holo\'s page + the margin '
              f'column as a second imagemask), ghostscript at {DPI2} dpi equal to the PDF\'s page: {gps} of {len(s3)}',
              *(f"  p{r['page']} {r['header']!r} {r['header_ink_mm']}, {r['number']!r} {r['number_ink_mm']}; "
                f"{os.path.relpath(r['headed_ps'], out)} {r['headed_ps_sha256']}" for r in s3rec),
              '', 'previews: preview-01..%02d.png = the sheets above in chain order, a third of each sheet\'s size'
              % len(s1p + r2 + s3) + '; preview-print-01..%02d.png = print-%s.pdf\'s first %d pages, a third of '
              '600 dpi' % (len(ps_) + 1, date, len(ps_) + 1)]
    open(os.path.join(out, 'MANIFEST.txt'), 'w').write('\n'.join(lines) + '\n')
    return lines


def main():
    s1 = os.path.abspath(arg('--s1'))
    out = os.path.abspath(arg('--out'))
    lines = build(s1, os.path.abspath(arg('--vol')), out,
                  os.path.abspath(arg('--c-py', os.path.join(BOOT, 'stage3', 'c.py'))),
                  os.path.abspath(arg('--reader', os.path.join(BOOT, 'r2reader', 'reader_lite_v1.py'))),
                  os.path.abspath(arg('--template', os.path.join(BOOT, 'stage1', 'template.py'))),
                  os.path.abspath(arg('--frozen-dir', os.path.join(BOOT, 'stage1'))),
                  arg('--date', '2026-10-23'))
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
