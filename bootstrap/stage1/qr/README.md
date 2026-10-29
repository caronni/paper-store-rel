# The QR codes of the for-print sheets (ruling 62, 2026-10-23)

Two QR module matrices, cross-placed on the print's stage 1-2 sheets by
`stage1/print_sheets.py` (through `make_sheets_v2.py` / `rebuild_v2.py`):

| file | placed on | content | input | version | error | mode | mask |
|---|---|---|---|---|---|---|---|
| `qr-a.pbm` | sheet 2 (the data sheet) | the exact bytes of `a.py` | 826 B, sha256 `720330aa996e0a5a21628e7086884f1ad0379b4d7c83401067b59e6afa4c8436` (= a.py) | 20 (97 x 97) | L | byte | 3 |
| `qr-d.pbm` | sheet 1 (the listing) | the 39 data lines as typed at a.py's prompts | 2,608 B, sha256 `fd3ac80e5348be72ab1e65be6e3f2560440bda01a27972a27586e84c912fb241`, from data.txt sha256 `b29bc54970fc549876be0597d3e0f8da2158d472a29d45875bbc56c7b181d2e5` | 38 (169 x 169) | L | byte | 7 |

The data lines: each line of `data.txt` (upper case) with its 4 check glyphs
after two spaces, as printed, the group spaces dropped (a.py ignores
spaces), newline-terminated (`print_sheets.data_lines`).  As printed, with
the group spaces, the text is 3,036 B and fits no QR at level L in byte mode
(version 40-L holds 2,953 B).

The PBMs are binary P4, one pixel per module, no quiet zone (the renderer
adds 4 modules), dark = 1.  `qr.json` records each input's sha and its
source file's sha; the renderer refuses a build whose `a.py` or `data.txt`
differs, so the print build needs no QR library.

Made once with segno 1.6.6 (`segno.make(data, error='l', mode='byte',
boost_error=False, micro=False)`) and checked by decoding each matrix back
with zxing-cpp 3.1.1 (4 px per module, 4-module quiet zone): 826 B and
2,608 B, byte-equal to the inputs.  Neither library is in the venv:

    PYTHONPATH=QRLIBS env/bin/python bootstrap/stage1/qr/make_qr.py [--s1 DIR]

QRLIBS = a directory holding segno and zxingcpp (for this build the
session scratchpad's `qrlibs/`); `--s1` defaults to
`bootstrap/build/sheets/stage1` (its `upper/` case).  Re-running it on the
same inputs writes byte-identical files.  On the print, rendered back
through ghostscript at 600 and at 150 dpi, zxing-cpp decodes both codes
to the exact input bytes.

Regenerated 2026-10-23 for the fixed point of CONVERGENCE-2026-10-23b.md
(c.py b4f7de22..., N2 24176 / B2 3810813523 in a.py and the data): both
inputs moved, the matrices made again by the command above, a second run
byte-identical.
