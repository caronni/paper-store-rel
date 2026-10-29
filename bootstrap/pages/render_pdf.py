"""Render the bootstrap leaves to ONE viewing PDF (A4, 300 dpi): text leaves
typeset 72 x 63 in a monospace face, bitmap leaves (the R2 pages and their
camera renders) placed as images. VIEWING ONLY — a print job for a data page
is a PostScript imagemask through scripts/print_plane.sh (DESIGN.md §2.4),
never this PDF.

DATA-PAGE MODE: a text leaf whose first line is exactly `%data-page` (the
marker; it is consumed, not drawn) is set character by character on a fixed
cell of CELL_MM = 2.35 mm.  A line of the form
    'nn ' + groups of 1-5 glyphs [0-9a-z] separated by ONE space + TWO spaces
    + a 4-glyph check
is a data line: the number right-aligned in two cells, one cell, the groups
with HALF a cell between them, ONE full cell, the check.  A shorter line (the
last data line, padded with spaces in the text) puts its check in the same
column as a full line of 12 groups of 5.  Every other line
of such a page is drawn one character per cell.  Other text leaves are set
as before (72 x 63, or wider when a line needs it, up to 96 columns).
A text leaf longer than 63 lines continues on further sheets (the grey
viewing header says "continued k of n"); the leaf text itself is unchanged.

BITMAP CAPTION: an input given as (path, caption) -- from Python, see
compose_leaves.py -- draws the caption in type below the module grid: the
R2 page's overt leaf header (R2-FORMAT v1 "Geometry": volume, rung, leaf n
of m; no reader reads it).  The grid's bottom edge comes from the gen.py
sidecar beside the bitmap (PATH minus extension + .json: y0_dots, H,
module_dots); without a sidecar the caption sits 10 mm above the sheet's
bottom edge.  Only the viewing render carries it: the page bitmap (and so
a print job made from it) does not.

FACE (stage 1, ruling 43): main(..., face=NAME) sets every leaf in one face,
read by path, never copied into the repo:
  'ocrb'          the standard's own OCR-B, the DEFAULT face of stage 1
                  (Debian fonts-ocr-b 0.3.1, Skala from Schwarz's METAFONT,
                  public domain / permissive; $OCRB_FONT overrides the path)
  'ocrb-redrawn'  Matthew Anderson's redrawing (CC BY 4.0, non-commercial
                  click-through): the unzipped copy under build/ocr/fonts/,
                  else the OTF inside scratch/fonts/ocrb-2015-10-27.zip
  'andale', 'menlo'  the system faces
A face that is absent falls back to Menlo with a WARNING (not an error).  A
character the face has no glyph for (the standard OCR-B has no middle dot
U+00B7) is drawn from Menlo, centred in the face's cell on the face's
baseline.  Without face the fonts are chosen as before and every line is
drawn whole, so the build of record renders unchanged.  Data lines may be
lowercase or uppercase (item 8).

Usage: python3 render_pdf.py OUT.pdf leaf1.txt leaf2.txt ... [page.pbm ...]
                             [--face ocrb|ocrb-redrawn|andale|menlo]
"""
import io
import json
import os
import re
import sys
import zipfile
from PIL import Image, ImageDraw, ImageFont

DPI = 300
A4 = (int(210 / 25.4 * DPI), int(297 / 25.4 * DPI))      # 2480 x 3508
MARGIN = int(10 / 25.4 * DPI)                              # 10 mm
COLS, ROWS = 72, 63
FONTS = ["/System/Library/Fonts/Menlo.ttc",
         "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
         "/System/Library/Fonts/Supplemental/Courier New.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
         "/usr/share/fonts/truetype/freefont/FreeMono.ttf"]


HERE = os.path.dirname(os.path.abspath(__file__))
FACES = {
    "ocrb": [os.environ.get("OCRB_FONT"),
             "scratch/fonts/fonts-ocr-b-0.3.1/OCRB.otf"],
    "ocrb-redrawn": [os.path.join(os.path.dirname(HERE), "build", "ocr", "fonts",
                                  "ocrb-2015-10-27", "OCR-B-Regular.otf"),
                     ("scratch/fonts/ocrb-2015-10-27.zip",
                      "ocrb-2015-10-27/OCR-B-Regular.otf")],
    "andale": ["/System/Library/Fonts/Supplemental/Andale Mono.ttf"],
    "menlo": ["/System/Library/Fonts/Menlo.ttc"],
}
FACE = []          # set by use_face(): the font source tried before FONTS
FALLBACK = FONTS[0]


def use_face(face):
    """face None: the fonts as before.  A name of FACES: that face first;
    Menlo with a warning when no copy is found.  Returns the source used (a
    path, 'zip:PATH', or None)."""
    del FACE[:]
    if face is None:
        return None
    assert face in FACES, face
    for src in FACES[face]:
        if isinstance(src, tuple):
            zp, member = src
            if os.path.exists(zp):
                with zipfile.ZipFile(zp) as z:
                    if member in z.namelist():
                        FACE.append(z.read(member))
                        return "zip:" + zp
        elif src and os.path.exists(src):
            FACE.append(src)
            return src
    print(f"render_pdf.py: WARNING: face {face!r} not found ("
          + ", ".join(str(x) for x in FACES[face] if x) + "): the leaves fall back to Menlo",
          file=sys.stderr)
    FACE.append(FALLBACK)
    return FALLBACK


def _truetype(src, size):
    return ImageFont.truetype(io.BytesIO(src) if isinstance(src, bytes) else src, size)


_GLYPH = {}


def has_glyph(font, ch):
    k = (id(font), ch)
    if k not in _GLYPH:
        _GLYPH[k] = ch == " " or font.getmask(ch).getbbox() is not None
    return _GLYPH[k]


_FB = {}


def fallback_for(font):
    """Menlo at the size whose advance fits the face's cell."""
    if id(font) not in _FB:
        adv, size = font.getlength("M"), 6
        while _truetype(FALLBACK, size + 1).getlength("M") <= adv:
            size += 1
        _FB[id(font)] = _truetype(FALLBACK, size)
    return _FB[id(font)]


def draw_line(d, x, y, line, font, cell=None, fill=0):
    """A line in a face: whole when the face has every glyph (the record's
    path); else one cell per character, a missing glyph from Menlo on the
    face's baseline.  cell: the advance (default the face's 'M')."""
    if all(has_glyph(font, ch) for ch in line) and cell is None:
        d.text((x, y), line, font=font, fill=fill)
        return
    adv = font.getlength("M") if cell is None else cell
    base = y + font.getmetrics()[0]
    for i, ch in enumerate(line):
        cx = x + i * adv
        if has_glyph(font, ch):
            d.text((cx + (adv - font.getlength(ch)) / 2, base), ch, font=font, fill=fill,
                   anchor="ls")
        else:
            fb = fallback_for(font)
            d.text((cx + adv / 2, base), ch, font=fb, fill=fill, anchor="ms")


def font_for_width(width_px, cols):
    for path in FACE + FONTS:
        try:
            size = 10
            while True:
                f = _truetype(path, size + 1)
                if f.getlength("M" * cols) > width_px:
                    return _truetype(path, size)
                size += 1
        except OSError:
            continue
    return ImageFont.load_default()


def sheets(lines, header):
    """Split a leaf's lines into sheets of ROWS lines -> [(lines, header)]."""
    while lines and lines[-1].strip() == "":
        lines = lines[:-1]
    parts = [lines[i:i + ROWS] for i in range(0, max(1, len(lines)), ROWS)]
    if len(parts) == 1:
        return [(parts[0], header)]
    return [(p, f"{header} (continued {k} of {len(parts)})" if k > 1
             else f"{header} (sheet 1 of {len(parts)})")
            for k, p in enumerate(parts, 1)]


def text_page(lines, header):
    im = Image.new("L", A4, 255)
    d = ImageDraw.Draw(im)
    width = A4[0] - 2 * MARGIN
    cols = min(96, max(COLS, max((len(l) for l in lines), default=0)))
    font = font_for_width(width, cols)
    pitch = (A4[1] - 2 * MARGIN) // (ROWS + 1)
    draw_line(d, MARGIN, MARGIN // 2, header, font, fill=120)
    for i, line in enumerate(lines[:ROWS]):
        draw_line(d, MARGIN, MARGIN + (i + 1) * pitch, line.rstrip("\n")[:cols], font)
    return im


CELL_MM = 2.35
DATA_MARK = "%data-page"
DATA_LINE = re.compile(r"^ *(\d+) ((?:[0-9a-zA-Z]{1,5} )*[0-9a-zA-Z]{1,5}) {2,}([0-9a-zA-Z]{4})$")
FULL_GROUPS = 12          # a full data line: 12 groups of 5


def data_page(lines, header, nw=2):
    """Per-character layout on a CELL_MM grid; data lines get half-cell gaps
    between groups and a full cell before the check.  nw: the cells of the
    line number (2, or 3 for a leaf of 100 lines or more), the same on every
    sheet of the leaf so the check column does not move."""
    im = Image.new("L", A4, 255)
    d = ImageDraw.Draw(im)
    cell = CELL_MM / 25.4 * DPI
    font = font_for_width(int(cell), 1)
    pitch = (A4[1] - 2 * MARGIN) // (ROWS + 1)
    draw_line(d, MARGIN, MARGIN // 2, header, font_for_width(A4[0] - 2 * MARGIN, COLS), fill=120)

    def put(x, y, ch):
        if has_glyph(font, ch):
            d.text((x + (cell - font.getlength(ch)) / 2, y), ch, font=font, fill=0)
        else:
            draw_line(d, x, y, ch, font, cell=cell)

    for i, line in enumerate(lines[:ROWS]):
        y, x = MARGIN + (i + 1) * pitch, MARGIN
        m = DATA_LINE.match(line)
        if not m:
            for ch in line.rstrip("\n"):
                put(x, y, ch)
                x += cell
            continue
        num, groups, chk = m.groups()
        for ch in num.rjust(nw):
            put(x, y, ch)
            x += cell
        x += cell
        for g in groups.split(" "):
            for ch in g:
                put(x, y, ch)
                x += cell
            x += cell / 2
        x += cell / 2          # the last group's half cell + this = one full cell
        x = max(x, MARGIN + (nw + 1 + FULL_GROUPS * 5.5 + 0.5) * cell)   # the check column
        for ch in chk:
            put(x, y, ch)
            x += cell
        assert x <= A4[0] - MARGIN, "data line wider than the page"
    return im


def bitmap_page(path, caption=None):
    im = Image.open(path).convert("L")
    # the 600-dpi page bitmap is already A4-sized in dots; downsample 2x for viewing
    im = im.resize(A4, Image.LANCZOS)
    if caption:
        side = os.path.splitext(path)[0] + ".json"
        x, y = MARGIN, A4[1] - MARGIN
        if os.path.exists(side):
            g = json.load(open(side))
            if {"x0_dots", "y0_dots", "H", "module_dots", "page_h_dots"} <= set(g):
                s = A4[1] / g["page_h_dots"]
                x = int(g["x0_dots"] * s)                          # the grid's left edge
                y = int((g["y0_dots"] + g["H"] * g["module_dots"]) * s) + int(2 / 25.4 * DPI)
        d = ImageDraw.Draw(im)
        draw_line(d, x, y, caption, font_for_width(A4[0] - 2 * MARGIN, COLS))
    return im


def main(out, inputs, face=None, header=None):
    pages = render(inputs, face, header)
    pages[0].save(out, save_all=True, append_images=pages[1:], resolution=DPI,
                  creationDate='', modDate='')     # no timestamps: byte-identical rebuilds
    print(f"wrote {os.path.basename(out)}: {len(pages)} pages")


def render(inputs, face=None, header=None):
    """The sheets of the inputs in one face -> [PIL image] (main's body; a
    caller may join the sheets of several faces into one PDF).  header: the
    grey line over every text or data sheet; None = the viewing-render line
    naming the file (the print of record), '' = none (stage 1's leaves carry
    their own header line with the date)."""
    use_face(face)
    pages = []
    for p in inputs:
        p, caption = (p, None) if isinstance(p, str) else p
        if p.endswith((".pbm", ".png", ".pgm")):
            pages.append(bitmap_page(p, caption))
        else:
            lines = open(p, encoding="utf-8").read().split("\n")
            hdr = (f"paper-store bootstrap — {p.rsplit('/', 1)[-1]} — VIEWING RENDER, not a print job"
                   if header is None else header)
            if lines and lines[0] == DATA_MARK:
                nw = max([2] + [len(m.group(1)) for m in map(DATA_LINE.match, lines) if m])
                pages += [data_page(ls, h, nw) for ls, h in sheets(lines[1:], hdr)]
            else:
                pages += [text_page(ls, h) for ls, h in sheets(lines, hdr)]
    return pages


if __name__ == "__main__":
    a = sys.argv[1:]
    face = None
    if "--face" in a:
        i = a.index("--face")
        face = a[i + 1]
        a = a[:i] + a[i + 2:]
    main(a[0], a[1:], face)
