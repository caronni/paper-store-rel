# Plate leaves 1, 2, 2b: what the typographer adds (text cannot carry it)

The three `.txt` files are the exact text, 72 columns x 63 lines each.
Set them in a monospaced face, never reflowed, no hyphenation, every
space kept (leaf 2's checker listing has 4- and 8-space indents and its
printed check codes count those spaces). On the usable area 182 x 277 mm
(A4, 10 mm margins, 18 mm gutter) this is 2.53 mm per column (10 cpi)
and 4.40 mm per line.

## Face
- OCR-B (ISO 1073-2) or equal: slashed zero (0 vs O), distinct 1 / l / I,
  distinct ` ' " ~ ^ @ # and . , ; :. Leaf 2's ASCII table is the
  glyph authority, so the face must show each of the 95 glyphs once,
  unambiguously.
- K toner only, blank versos, both Plate copies (front and back matter).

## Fill-ins (line 1 of each leaf; leaf 1 line 2)
- `{V}` volume name, at most 7 characters; `{C}` copy letter A or B;
  `{NBYTES}` the volume's byte count, at most 10 digits. The text keeps
  72 columns with these limits.
- THE KEY on leaf 1 is a labelled EXAMPLE. A real volume replaces the
  string, its hex and its CRC-32 with its own (re-run make_plate.py).

## Leaf 1: the 8 x 8 golden block as a printed bitmap
- Beside the ASCII rows (`row 1` .. `row 8`, columns 1-65; columns
  67-72 are free, 15 mm): 8 x 8 square modules, each 24 x 24 engine dots
  at 600 dpi = 1.016 mm, ink where the text shows `#`, row 1 at the top.
  Quiet zone: at least 2 white modules all round.
- Draw raster arrows ALONG its read path: one arrow left to right over
  row 1, one arrow down the left side (rows top to bottom).
- An ink = 1 pictogram next to "Ink = 1, paper = 0": a solid square
  labelled 1, an empty square labelled 0.
- The 2 x 2 key (`ab/cd` and its 8 images) may also be drawn as 8 tiny
  copies of the golden block, turned and mirrored.
- Imaging pictogram (optional): lamp at a low side angle, a crossed-out
  flash.

## Leaf 2b: the 100 mm scale bar
- In the empty line 15, under the LENGTH sentence: a solid bar exactly
  2362 engine dots long at 600 dpi (= 99.991 mm, as the text says; 2362 x 25.4 / 600 = 99.9913), at
  least 12 dots thick, no ticks.
  The bar is the unit's definition; never scale the page.

## Counting primer
- Leaf 2b's `o` dots may be drawn as filled circles, in groups of 5
  with a small gap, so they can be counted by eye.

All values in the text are computed by `make_plate.py` and re-checked
from the printed text alone by `verify_plate.py`.
