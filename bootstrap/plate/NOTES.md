# plate/ — the Plate, R0 (key `plate`, 2026-10-18)

## Built
- `leaf1.txt`, `leaf2.txt`, `leaf2b.txt`: 72 x 63 plain text, printable
  ASCII. Two leaves were NOT enough (content measured 189 lines after
  compaction), so leaf 2b is the third Plate leaf.
  - Leaf 1: promise; proof (8x8 block "Hello 42": marks, binary, sum,
    letter, with ink=1 / raster / MSB-first and the 16-trial rule with
    a 2x2 pictogram); THE KEY (labelled EXAMPLE, hex, length, CRC-32);
    CRC-32 spec, bit-level trace of "12" (16 steps: low bit, r>>1, new
    r), vectors; the typed stream explained.
  - Leaf 2: the checker (12 lines verbatim from ../typed/checker.py),
    its check codes, both known-answer lines, the hand-worked check;
    the 128-entry ASCII table (number, glyph, 8 marks); pangram + CRC.
  - Leaf 2b: counting primer (0-15: dec, hex, bits, dots), place value,
    scale bar sentence, R2 paragraph, custodial directive, 256-entry
    table T.
- `leaf1-2-notes.md`: what the typographer adds (bitmap block, arrows,
  100 mm bar, face, fill-ins).
- `make_plate.py`: computes every printed value (bitwise CRC cross-
  checked against zlib; check codes asserted against the checker
  builder's list). `verify_plate.py`: re-derives everything from the
  printed text alone.

## Measured
- `verify_plate.py`: ALL PASS (39 checks): block decodes to Hello 42;
  of 16 orientation x polarity trials exactly one reads Hello 42 (two
  are printable ASCII: as printed, and flipped top-bottom = "24 olleH");
  table T, all 18 trace steps, vectors 00000000 / e8b7be43 / cbf43926,
  crc("12") 4f5344cd, pangram 86dda607, key 3ed4f759 (38 B); the
  printed checker listing, run with python3: OK 1, BAD 1, OK 2, RUN
  prints 42; it accepts its own 12 printed lines (OK 2..OK 13).

## Deviations / spec questions
1. Order: the priority list put grounding (counting, scale) on leaf 2b,
   after its first use on leaf 1. Read as a set; or bind 2b first?
2. Scale bar: 2362 dots at 600 dpi = 99.9913 mm; DESIGN says 99.992
   (rounding error). The Plate prints 99.991.
3. The hand-worked check is the checker NOTES' numbers verbatim, but in
   ASCII (`*` for the middle dot, `sum` for sigma, `-`, `(mod 32768;`
   for the congruence).
4. The key contains `@`, the typed stream's indent token: a key may
   travel only in a data section (base 32) or as chr(64), never inside
   typed code. DESIGN's e016 hex seed was replaced by the holo v2
   example the task named.
5. Hash chain: DESIGN wants the Plate to print the CRC-32 of the next
   rung's text (the typed stream). Not printed: no room, stream not
   frozen. Assembler: reserve a line, or drop the claim.
6. "One day: type the checker and the typed pages" is an ESTIMATE;
   no typing time was measured.
7. English only (DESIGN: 4-6 languages; no room).
8. CRC trace in hex per bit step (low bit, shifted, result), not 32-bit
   binary registers; "every shift shown" read this way.
9. Leaf numbering: headers say PLATE n/3 (LEAF 1, 2, 2b); in-text
   references use 1, 2, 2b.
10. Fill-ins `{V}` (<= 7 chars), `{C}`, `{NBYTES}` (<= 10 digits).
