# e039 — Xerox VersaLink: discovery pair + candidate set (c4→c1 K, CMY8 r0700→r0850, q = 0.8)

Date generated: 2026-09-16; printed 2026-09-16/17. Engine: **Xerox
VersaLink C7130 Color MFP**, firmware 1.101.2 (Fujifilm controller),
`<host>`, reached ONLY over IPPS (039.3b) — a new engine, no
registry row, no prior measurement in this record. Scanner of record:
Canon flatbed 4800 (NOT on site during these prints). Code: main at
`4337b364` + this experiment's tools, venv `env/` (free-threaded 3.14.7,
rebuilt 2026-09-16).

STATUS 2026-09-19: **PRINTED, NOT SCANNED, LOUPE VERDICTS PARTLY OWED.**
On paper, all A4-uncut-on-Legal (cut to 297 mm before scanning): the B/W
discovery sheet (job 112, `ipp-urf`), K sheets A–E (116–120, `ipp-urf`),
the colour discovery sheet (121, `ipp-pdf`) and colour F–J (123–127,
`ipp-pdf`), and seven colour-route probes (128–134: PWG cmyk_8, five PDF
variants, the sRGB chart). Measured by loupe: `ipp-urf` W8 is
bit-faithful for K (039.3f, c1 dots printed as isolated dots); `ipp-pdf`
DeviceCMYK is colour-managed and line-screened (039.3o). OWED: the loupe
verdicts on 128–134 (039.3s), the ruler check for PDF auto-scale and the
EWS snapshot (039.3q), the operator's media stock, and the Canon. The
first URF print (039.3c) is INVALID (gs pbmraw halftone, 039.3e). No
ladder, margin or receiver promotion can come from a single new engine's
first sheets.

## 039.0 Why this set

The VersaLink is the third engine in the record (M281 home, AltaLink
C8245 office). Its first print day gets, like the AltaLink's (e031 +
e033): the standard HCAL-R1 discovery pair (B/W + colour) so the
K ladder, the Y plane, plane-overlap re-screening, `cell=1` and MIC
dots are measured on this engine before any decode statistic is read;
and a candidate set of counting-payload volumes spanning c4 → c1 on K
and c3/c2/c1 on CMY8 at r0700 and above, all at q = 0.8, one page each,
A4 at the 4 mm probe footing.

**The c1 question.** Both engines measured to date print NO isolated
single 600-dpi dot (`cell=1 dead`: M281 e025; AltaLink e031 — 0.060
contrast for one black dot, 0.044 for one white hole, both polarities).
The two c1 sheets (E, J) are an EXISTENCE PROBE for the VersaLink, not
a rung: if its discovery sheet reports a live single dot, E and J are
the cheapest possible test of a true 600-dpi-addressable channel; if it
reports `cell=1 dead`, E and J will not become addressable (the c2
sheets of e030/e032 on the M281's screened path show what that looks
like) and need not be scanned. Read the discovery report first. Note
the request is `[600 600]` throughout — never request /HWResolution
above 600 (CLAUDE.md channel facts; e007.6/e009).

**What the public record says about VersaLink resolution (web, 2026-09-16).**
Xerox's own pages give the C7000 / C7020-C7030 / C7120-C7130 / C600 / C605
family "up to 1200 x 2400 dpi" print, and its print-quality-modes KB
(KB0136805) lists Standard, Enhanced and Photo ALL as 1200 x 2400 dpi
under the PostScript driver but Standard as 600 x 600 dpi under PCL; the
C405 is 600 x 600, the C415 1200 x 1200. NO public document states the
engine's native addressability, and a Xerox-forum thread titled "Are the
1200/2400 DPI (physical) specs for the VersaLink C7000/C7020 ... flat out
lies?" sits behind a login. This is the SAME spec wording the AltaLink
C8245 carries, and on that engine the raw-9100 path measured FIXED-600 on
PostScript (`/HWResolution [1200 1200]` silently refused, 007.6), on
PJL-hinted PostScript and on native PCL raster at 1200 and 2400 (e009:
content prints 2x/4x oversize, no density gain). The 1200 x 2400 claim
is a marking-engine figure (Fuji Xerox LED heads with exposure-timing
enhancement in the process direction), not evidence of a 1200-dot grid
addressable from a raw job. The only answer that counts is measured:
§039.1's second pair requests `[1200 2400]` through the discovery
instrument, whose effective-device snapshot and scale readout tell
whether the request was honoured, refused or scaled (the e009 verdict
order). That pair is an INSTRUMENT run, the one sanctioned exception to
the never-above-600 rule; every data sheet here requests `[600 600]`.

## 039.1 Discovery pair (`./confetti.py discover emit --request default --kind both`)

`scratch/versalink-20260916/discovery/`, bundle
`hcal-discovery-copy0000-default-652839a069459bad.bundle.json`
(schema `holo/characterize/bundle/v2`, stage discovery, request `default`,
request_code 0, request_dpi null, copy 0).

| kind | PostScript | sha256 | bytes | layout_digest |
|---|---|---|---:|---|
| bw | `hcal-discovery-bw-copy0000-default-f3c9e5f807ca05bf.ps` | `cdb396ff87fa44ef136bec353d7090549d7d3a3dd2883cf2c37f2a5411b48082` | 5,535,084 | `cbcab84fda635e5d…` |
| color | `hcal-discovery-color-copy0000-default-6995a5d0b5b0218d.ps` | `482a89fc6eb8ec3a00107242c6db9093e3603ce148be82d3919832f56148a53d` | 10,337,241 | `af63bd28aa9a8b03…` |

The B/W sheet's `layout_digest` (`cbcab84fda635e5d…`) is byte-identical
to e028's (M281) and e031's (AltaLink): the K-channel comparison across
all three engines is like-for-like. Analyse with
`./confetti.py discover analyze <scan> --printer <id> --print-path <path>`
as in e031 §2 (a registry row for the VersaLink is owed before
`discover calibrate --from-report` or `combine` may be fed — e031's
rule: a first single-copy report is never promoted).

**Second pair — the resolution question (`discover emit --request
1200x2400 --kind both`)**, `scratch/versalink-20260916/discovery-request-1200x2400/`,
bundle `hcal-discovery-copy0000-1200x2400-8e6de4367a509447.bundle.json`
(request `1200x2400`, request_code 5). Its `setpagedevice`
asks `/HWResolution [1200 2400]`; the sheet snapshots the effective device
before and after. Optional, NOT in the aggregate job; print it only to
answer 039.0's c1 question directly (e009's design: a 600-control that
must decode, a requested-grid field that decodes iff unlocked; the Canon
4800 is the only scanner that resolves a 1200 grid).

| kind | PostScript | sha256 | bytes |
|---|---|---|---:|
| bw | `hcal-discovery-bw-copy0000-1200x2400-08b064c74c115428.ps` | `0b5885d370fc30e46638667f29be8863900f2aba0f658998b4a209b9ed93e9e5` | 5,535,114 |
| color | `hcal-discovery-color-copy0000-1200x2400-3778ed2dd849aa35.ps` | `1e49b2edcde6e4d3a39c3e11744180d748fe8e19f1efcffa15af93e62147f9bd` | 10,337,271 |

## 039.2 Candidate set (`experiments/039-xerox-versalink/generate_set.py`)

`scratch/versalink-20260916/<tag>-…/` — `page000.ps`, `page000_gt.npy`,
`manifest.json`, `payload-counting.bin`; `SET.json` is the table below
in full. Paper bundle `A4-4mm` (600 dpi, printable 4770×6826 dots),
q = 0.8 everywhere, FORMAT-SPACE v2 identities (the `holo/v2/…` seed —
a different keystream from e033's `holo/v1/…-x1` rows). Regeneration
is byte-identical (checked on A after the run).

**Payload — the counting rule, twiddled.** `byte[i] = (i + 0x39 + k)
mod 256`, k = the sheet index (A = 0 … J = 9). e033 used `byte[i] = i
mod 256`; the offset makes every sheet of this set a pattern e033 never
printed, in addition to the seed change. The payload fills the page
exactly (`capacity --json` → `max_payload_bytes`).

| tag | format | tiles | q | payload B | K/N | net b/mm² | ink | payload sha256 | page000.ps sha256 | .ps MiB |
|---|---|---:|---|---:|---|---:|---|---|---|---:|
| A | `c4-k-r0700@26x18` | 468 | 0.8 | 122,892 | 0.765 | 17.9 | K | `930d4d0730d99601…` | `db1ed8ecb8cef33c733b3716e19661847908971012d446ff2b8790080224cce5` | 7.4 |
| B | `c3-k-r0700@35x24` | 840 | 0.8 | 225,218 | 0.781 | 32.5 | K | `16225eb249228312…` | `0bfc50177ca88ac2956cad420e16f81cb0a2fb02d321a75d49612c7f33a07f95` | 7.4 |
| C | `c2-k-r0700@53x37` | 1961 | 0.8 | 532,882 | 0.791 | 74.0 | K | `3cb654e1910d199a…` | `4b6f6cd670c6f942e7eeab80f7a8f7061294c4668e1bcbc31f37c92989311a43` | 7.7 |
| D | `c2-k-r0850@53x37` | 1961 | 0.8 | 657,042 | 0.791 | 91.3 | K | `fe8fa0b936c960fd…` | `745a17f69a7e6b356de6c3a27c26dd1b3c2ef80a6c0885cc8962d7693223c860` | 7.7 |
| E | `c1-k-r0700@106x74` | 7844 | 0.8 | 2,149,148 | 0.798 | 298.6 | K | `8937b75d36543ce0…` | `7221a1f589193385abad8864d3c2e0b960ceb679ecaeab4fee304af858183715` | 7.7 |
| F | `c3-cmy8-r0700@35x24` | 840 | 0.8 | 681,032 | 0.793 | 98.2 | CMY | `644586e9c7d80704…` | `5c2fa837bd01fed11ef2485958364361aa0a57e4b004bcfae647f529d4c2b1f4` | 29.8 |
| G | `c2-cmy8-r0700@53x37` | 1961 | 0.8 | 1,598,326 | 0.797 | 222.1 | CMY | `dde5f4f5c577f51b…` | `ad327c7a99ff854695bd548956ba66f1b395b662ba9453a098f354950378c69b` | 30.9 |
| H | `c2-cmy8-r0775@53x37` | 1961 | 0.8 | 1,785,886 | 0.797 | 248.1 | CMY | `82a20fdced6df76c…` | `af8bf851b96746ce464a43f57238f0e2b8f016dd667b028ea5da3c605332b5b7` | 30.9 |
| I | `c2-cmy8-r0850@53x37` | 1961 | 0.8 | 1,973,446 | 0.797 | 274.2 | CMY | `0d248fb3404083ad…` | `71eafcea168e5acea693dfaa485029ae3d4735318a7b74efd6003eae6a64abdb` | 30.9 |
| J | `c1-cmy8-r0700@106x74` | 7844 | 0.8 | 6,404,664 | 0.798 | 889.9 | CMY | `f39843da5fde4a7c…` | `b9d1a4047bc235d037d80fd5a8f4a01dd06f9581396e4873f7dfd1da8170d3e8` | 30.9 |

- **A** — K, coarsest rung of the ladder. Borders 7.62/7.45 mm.
- **B** — K, the e018/e029 class at r0700. Borders 6.27/7.45 mm.
- **C** — K, the e029/e032 rung (verified on M281 + AltaLink). Borders 4.91/4.74 mm.
- **D** — K, one rung up from C. Borders 4.91/4.74 mm.
- **E** — K, ONE DOT PER CELL — existence probe (cell=1 dead on both engines to date). Borders 4.91/4.74 mm.
- **F** — CMY8 pooled -v1 at c3. Borders 6.27/7.45 mm. Plane tier: not-at-this-dial (needs q <= 2/3).
- **G** — CMY8 pooled -v1, e033 sheet I's rung. Borders 4.91/4.74 mm. Plane tier: not-at-this-dial (needs q <= 2/3).
- **H** — CMY8 pooled -v1, the rung between G and I. Borders 4.91/4.74 mm. Plane tier: not-at-this-dial (needs q <= 2/3).
- **I** — CMY8 pooled -v1, e033 sheet H's rung (holo3 max). Borders 4.91/4.74 mm. Plane tier: not-at-this-dial (needs q <= 2/3).
- **J** — CMY8 at ONE DOT PER CELL — existence probe. Borders 4.91/4.74 mm. Plane tier: not-at-this-dial (needs q <= 2/3).

- q = 0.8 sits ABOVE the pooled dead-plane dial (needs q ≤ 2/3): on F–J
  a dead plane is NOT a deterministic tier, as on e033's E/F/H/I.
- net b/mm² = payload bits over the printed field area (cells × pitch),
  the e033 §033.0 convention.
- Colour sheets on a Xerox are expected to carry MIC yellow tracking
  dots (e031: 0.210/mm² on the AltaLink); K-only pages were clean there.
  To be re-measured on this engine from the discovery colour sheet.

### 039.2a The aggregate job — one file, one sheet per page

`scratch/versalink-20260916/e039-all-pages.ps` — 216,420,714 B,
sha256 `dab6e344203bfda52498b4573e68c8c8934962bec7f102622950d4e1ec1e0a4c`, built by
`experiments/039-xerox-versalink/coalesce_ps.py`: 12 pages, the default
discovery pair first (pages 1–2: bw, color) then A–J (pages 3–12). Each
page's body is its source file VERBATIM (its own `setpagedevice` request
included); only the DSC header, the `%%Page:` numbering and the trailer
are the aggregate's, and every page opens with a comment naming its
source file and sha256. The discovery pair leads because its HCAL-R1
"pre-request device snapshot" must read a fresh job's `currentpagedevice`,
not the state left by a payload page's `/HWResolution [600 600]` request.

Verified with ghostscript 10.07.1 (`-r600 -sDEVICE=bitcmyk`): pages 3–12
of the aggregate render BIT-IDENTICAL to their standalone `page000.ps`.
Pages 1–2 differ from their standalone renders ONLY because the discovery
sheet stamps a run-time nonce (`realtime`) into its printed report — the
standalone file itself renders differently on two consecutive runs
(measured), so the difference is the instrument's, not the coalescing's.

Printing the aggregate = one job of 12 sheets through the same raw path;
the per-sheet files remain the unit of record (their shas are the
identities above). The 1200x2400 request pair is deliberately NOT in it.
Why not: each HCAL-R1 sheet snapshots `currentpagedevice` BEFORE its own
request (`src/holo/characterize/emit.py:57-73`), so a discovery sheet that
follows another page in the same job reads that page's request instead of
the device default; the volume pages carry their own `/HWResolution
[600 600]` request (`page000.ps` line 9), so they are not the ones at risk.
The plan for the AltaLink catch-all (2026-10-06, e042 §042.2p) was
therefore the aggregate first and the two 1200x2400 files after it as two
separate jobs; whether they went as two jobs is not recorded. The volume
pages carry no printed label (no text operator in any `page000.ps`): they
are identified only by output order, page 3 = A … page 12 = J, so the
plan was to number the sheets in pencil as they come out and never to
shuffle the stack. That matters while eleven of those sheets stay
unscanned.

## 039.3 Printing (OPERATOR — not yet done)

- Path: `scripts/print_plane.sh <file.ps> <versalink-host>` (raw socket
  9100, the only sanctioned data-sheet path). If the VersaLink is reached
  through a CUPS queue instead (e031's `lpr -o raw` footing), record it
  as a distinct footing and never merge with `raw9100`.
- Order: discovery pair first, then A–D and F–I; E and J only if the
  discovery report shows a live single dot (039.0).
- One physical sheet per receiver state; never combine copies of one
  file, and never combine these with e033's sheets (different bits).
- Fill in: media (stock, g/m²), tray, host, date, any driver settings
  seen on the way, and the loupe check (DESIGN.md §2.4) before any
  decode statistic is trusted.

| run | date | action | details |
|---|---|---|---|
| 039.3a | 2026-09-16 | `lpr -o raw` of PostScript to the first Xerox (`<host>`), operator, office machine | FAILED: multi-hundred-page ASCII printout starting `%!PS-Adobe-3.0`. Root cause measured the same day (039.3b): the engine exposes NO PostScript. Sheets discarded. |
| 039.3b | 2026-09-16 | printer characterised over IPP (read-only) | `<host>` = **Xerox VersaLink C7130 Color MFP**, fw 1.101.2. Ports: 9100 and 515 CLOSED, 631 (IPP/IPPS) + 80/443 open. IPP `document-format-supported` = octet-stream, image/urf, image/pwg-raster, image/jpeg, application/pdf — no PostScript, no PCL (device id `COMMAND SET:PDF,URF,JPEG`). `printer-resolution-supported` = 600 dpi ONLY (URF `RS600`, `W8`, `SRGB24`). `print-scaling-supported` auto/auto-fit/fill/fit/none (default auto). `media-ready` Letter, Legal, Ledger; A4 supported if loaded. `media-left-margin-supported` 4.10 mm. A raw PostScript job on this endpoint is sensed as text — 039.3a explained. |
| 039.3c | 2026-09-16 | **PRINT, footing `ipp-urf` — INVALID as a characterisation (039.3e)**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/hcal-discovery-bw-on-legal-uncut-w8.urf <host> na_legal_8.5x14in` (Claude sent it in the operator's terminal on his "you send it"; wrapper confirmation `yes` by the operator) | The B/W discovery sheet as an Apple raster: ghostscript `pbmraw -r600` render of the A4 PostScript (the emission-gate render; 1-bit, bit-faithful for imagemasks) placed UNCUT on a Legal page (5100x8400 dots), top-aligned, 70 dots (2.96 mm) in from the left so the A4 width is centred; encoded by `experiments/039-xerox-versalink/urf_raster.py` ( W8 = 8-bit luminance grey, black 0 / white 255, URF line RLE, header bpp 8 / cs 0 / simplex / quality 4 / 600 dpi; decoder round-trip 0 mismatches). ghostscript's own `urfgray` device was REJECTED: it writes black as grey 32, which the engine would halftone as an 87 % tone. IPP job attributes: `media na_legal_8.5x14in`, `print-scaling none`, `print-color-mode monochrome`, `print-quality normal`, `sides one-sided`. Printer answered `successful-ok`, job-id 111, `processing / job-interpreting`. File sha256 `6de8ba10f4789bba85124c6ca6e7794e673074aa82a8c89f4c9f508d0ef2f129` (6,937,273 B). Media: Legal from the printer's tray (stock: OPERATOR TO FILL — the office's standard Legal). The sheet is to be CUT to 297 mm for the Canon platen; the bottom 58.6 mm is blank. NOTE: the sheet's printed "device snapshot" block ran in ghostscript, not in the printer — it reports gs's page device; the stimulus patterns are unaffected. Footing `ipp-urf` ≠ `raw9100` ≠ `lpr-raw`: never merge. |
| 039.3e | 2026-09-16 | 039.3c RULED INVALID (Germano, from the registration marks: the 8x8 corner satellites and the ladder squares printed with a hole lattice; "the characterisation sheet should only have real black, not warm black") | ROOT CAUSE, measured: the raster was ghostscript's `pbmraw` render, and `pbmraw` HALFTONES this sheet — it paints with `setcmykcolor 0 0 0 1`, gs's ICC CMYK→grey maps 100 % K to a dark grey (pnggray renders it as 32), and the 1-bit device screens that grey: plus-shaped single-dot holes on a staggered 4-row lattice in every black area (5,506,642 black dots against 6,791,232 in the true render — 19 % of the ink missing as holes). The K plane of `bitcmyk` is exact and CARRIES NO C/M/Y INK (0 dots: the sheet is real K only); `pbmraw -dUseFastColor` and `pnggray < 128` agree with it to 1,344 / 1,488 dots (0.02 %, vector-edge rounding). The payload-sheet emission checks (039.2a) used bitcmyk throughout and were never affected; the sheet-A Letter-vs-A4 "15 % mismatch" of 039.3d was this halftone's phase shifting under the translate, not geometry. The printed sheet is a faithful print of gs's screen — which is itself a first datum on the `ipp-urf` path: the engine reproduced single-dot white holes inside solids at the 600-dpi grid (loupe photo; to be measured on the corrected sheet, not this one). `urf_raster.py`/`pdf_bilevel.py` now render the K plane of bitcmyk themselves and REFUSE any CMY dot on a B/W sheet; the 039.3c files are quarantined under `scratch/versalink-20260916/urf/invalid-039.3c/`. Corrected, verified files (decoder / gs round-trip 0 mismatches): `hcal-discovery-bw-K-on-legal-uncut-w8.urf` sha256 `c9e28b3e99eccaeae4577f619f40a725baabdc1ab1a0cee64d7e63265a47885e` (5,596,897 B); `hcal-discovery-bw-K-on-legal-uncut-bilevel.pdf` sha256 `c590c8fc15d7ef0a126efe4e1d856606077ea22d3cb5936d13b3b699e3c247a6` (628,747 B). NOT yet printed. |
| 039.3f | 2026-09-16 | **PRINT, footing `ipp-urf` — the CORRECTED B/W discovery sheet**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/hcal-discovery-bw-K-on-legal-uncut-w8.urf <host> na_legal_8.5x14in` (operator ran it and confirmed `yes`; the PNG decoded from the URF was inspected first: solid satellites, solid ladder squares) | K plane of the bitcmyk render (039.3e), A4 uncut on Legal, top-aligned, x +70 dots; W8, black 0 / white 255, 600 dpi; same IPP attributes as 039.3c (Legal, scaling none, monochrome, normal, one-sided). Printer answered `successful-ok`, job-id 112, `processing / job-interpreting`. File sha256 `c9e28b3e99eccaeae4577f619f40a725baabdc1ab1a0cee64d7e63265a47885e` (5,596,897 B). Media: Legal from the printer's tray (stock: OPERATOR TO FILL — the office's standard Legal); CUT to 297 mm before scanning. Printed "device snapshot" block = ghostscript's page device (039.3c note). This is the sheet to scan for `discover analyze` on the `ipp-urf` footing. |
| 039.3i-A | 2026-09-17 | **PRINT sheet A, footing `ipp-urf`**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/A-c4-k-r0700-at-26x18-on-legal-uncut-w8.urf … na_legal_8.5x14in` (operator's `yes` per sheet) | K plane of the bitcmyk render → URF W8, A4 uncut on Legal (x +70 dots); IPP: Legal, scaling none, monochrome, normal, one-sided; `successful-ok`, job-id 116. File sha256 `32b5feec2a6b806afd0bd5f35e8210380d6ef72bd67025d2b8b7ec65120e0a7f`. Media: Legal from the tray (stock: OPERATOR TO FILL); cut to 297 mm before scanning. No scanner on site yet — loupe only. |
| 039.3i-B | 2026-09-17 | **PRINT sheet B, footing `ipp-urf`**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/B-c3-k-r0700-at-35x24-on-legal-uncut-w8.urf … na_legal_8.5x14in` (operator's `yes` per sheet) | K plane of the bitcmyk render → URF W8, A4 uncut on Legal (x +70 dots); IPP: Legal, scaling none, monochrome, normal, one-sided; `successful-ok`, job-id 117. File sha256 `168f484d05d908cbca7249690bdfefdd5b5514658198aef476a3f52af33b46f9`. Media: Legal from the tray (stock: OPERATOR TO FILL); cut to 297 mm before scanning. No scanner on site yet — loupe only. |
| 039.3i-C | 2026-09-17 | **PRINT sheet C, footing `ipp-urf`**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/C-c2-k-r0700-at-53x37-on-legal-uncut-w8.urf … na_legal_8.5x14in` (operator's `yes` per sheet) | K plane of the bitcmyk render → URF W8, A4 uncut on Legal (x +70 dots); IPP: Legal, scaling none, monochrome, normal, one-sided; `successful-ok`, job-id 118. File sha256 `fbd1eca52f952c25bc5fb7a9f7dbe97939fc235d8e84cada8ad56ed85e326f98`. Media: Legal from the tray (stock: OPERATOR TO FILL); cut to 297 mm before scanning. No scanner on site yet — loupe only. |
| 039.3i-D | 2026-09-17 | **PRINT sheet D, footing `ipp-urf`**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/D-c2-k-r0850-at-53x37-on-legal-uncut-w8.urf … na_legal_8.5x14in` (operator's `yes` per sheet) | K plane of the bitcmyk render → URF W8, A4 uncut on Legal (x +70 dots); IPP: Legal, scaling none, monochrome, normal, one-sided; `successful-ok`, job-id 119. File sha256 `2bf4f5bfae8c1c8e7a9cf81747ba74e8ae4aa478e76f3c1fbc00f85e8869b3d2`. Media: Legal from the tray (stock: OPERATOR TO FILL); cut to 297 mm before scanning. No scanner on site yet — loupe only. |
| 039.3i-E | 2026-09-17 | **PRINT sheet E, footing `ipp-urf`**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/E-c1-k-r0700-at-106x74-on-legal-uncut-w8.urf … na_legal_8.5x14in` (operator's `yes` per sheet) | K plane of the bitcmyk render → URF W8, A4 uncut on Legal (x +70 dots); IPP: Legal, scaling none, monochrome, normal, one-sided; `successful-ok`, job-id 120. File sha256 `8d320b8e7fbae2684ec6155d71f02d8abe4c2895c7e882e7e10478d95edf620f`. Media: Legal from the tray (stock: OPERATOR TO FILL); cut to 297 mm before scanning. No scanner on site yet — loupe only. |
| 039.3j | 2026-09-17 | **PRINT, footing `ipp-pdf` — the COLOUR discovery sheet as a DeviceCMYK PDF (the colour-route probe)**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/hcal-discovery-color-on-legal-uncut-cmyk.pdf … na_legal_8.5x14in color` (operator's `yes`) | One full-page /DeviceCMYK /BitsPerComponent 1 image from the bitcmyk render (overprint honoured, 039.3g), A4 uncut on Legal; IPP: application/pdf, Legal, scaling none, **print-color-mode color**, normal, one-sided; `successful-ok`, job-id 121. File sha256 `eac1cfd2e1a00a45e10c0fd4467f6a7e02c68a99ce8d085e72639cad9ab65f26` (938,350 B). LOUPE CHECKS OWED (no scanner): (a) the 100 % C, M, Y patches carry ONE toner each — any M/Y/K inside the C patch = PDF Bridge colour-manages DeviceCMYK; (b) `screen/path/opm1-CM` and `devicecmyk-CM` show both toners with no K substitution; (c) single-dot and 1-on/1-off per plane = 1:1 sampling, no re-screen; (d) MIC yellow dots present or not. The printed device-snapshot block is ghostscript's (039.3c note). |
| 039.3k | 2026-09-17 | DeviceCMYK Apple raster probe (`hcal-discovery-color-on-legal-uncut-devcmyk32.urf`, colour code 6, 32 bpp, sha256 `5af60a953d7b00d39ae27a5dd1a5a65aa8c916ac36815fc5c9f680f8be00f272`), same wrapper, `color` | **REFUSED**: `client-error-document-format-error`, job-id 122 `aborted / document-format-error` — no paper. The printer honours its urf-supported list (W8, SRGB24) literally; colour over Apple raster is closed on fw 1.101.2. Colour stays with `ipp-pdf`. |
| 039.3l-F | 2026-09-17 | **PRINT sheet F, footing `ipp-pdf`**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/F-c3-cmy8-r0700-at-35x24-on-legal-uncut-cmyk.pdf … na_legal_8.5x14in color` (operator's `yes` per sheet, printed BEFORE the colour discovery sheet's loupe verdict — by the operator's 'print regardless') | Full-page DeviceCMYK 1-bpc image from the bitcmyk render, A4 uncut on Legal; IPP: application/pdf, Legal, scaling none, color, normal, one-sided; `successful-ok`, job-id 123. File sha256 `ca35006f5e24824954c947a4d49ed004edf3328362fb3517b5b76018dd23953f`. Media: Legal from the tray (stock: OPERATOR TO FILL); cut to 297 mm before scanning. The sheet's value depends on 039.3j's loupe verdict (pure C/M/Y patches single-toner). |
| 039.3l-G | 2026-09-17 | **PRINT sheet G, footing `ipp-pdf`**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/G-c2-cmy8-r0700-on-legal-uncut-cmyk.pdf … na_legal_8.5x14in color` (operator's `yes` per sheet, printed BEFORE the colour discovery sheet's loupe verdict — by the operator's 'print regardless') | Full-page DeviceCMYK 1-bpc image from the bitcmyk render, A4 uncut on Legal; IPP: application/pdf, Legal, scaling none, color, normal, one-sided; `successful-ok`, job-id 124. File sha256 `a8116ecc8a273c2a483dafd5a3b7900a57f4bd057eae1d6318af9da2ecdb869f`. Media: Legal from the tray (stock: OPERATOR TO FILL); cut to 297 mm before scanning. The sheet's value depends on 039.3j's loupe verdict (pure C/M/Y patches single-toner). |
| 039.3l-H | 2026-09-17 | **PRINT sheet H, footing `ipp-pdf`**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/H-c2-cmy8-r0775-at-53x37-on-legal-uncut-cmyk.pdf … na_legal_8.5x14in color` (operator's `yes` per sheet, printed BEFORE the colour discovery sheet's loupe verdict — by the operator's 'print regardless') | Full-page DeviceCMYK 1-bpc image from the bitcmyk render, A4 uncut on Legal; IPP: application/pdf, Legal, scaling none, color, normal, one-sided; `successful-ok`, job-id 125. File sha256 `10bb59b085537dda27f30209a5f3806c746dc199dbd1b77ab17a90ca7b31da39`. Media: Legal from the tray (stock: OPERATOR TO FILL); cut to 297 mm before scanning. The sheet's value depends on 039.3j's loupe verdict (pure C/M/Y patches single-toner). |
| 039.3l-I | 2026-09-17 | **PRINT sheet I, footing `ipp-pdf`**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/I-c2-cmy8-r0850-at-53x37-on-legal-uncut-cmyk.pdf … na_legal_8.5x14in color` (operator's `yes` per sheet, printed BEFORE the colour discovery sheet's loupe verdict — by the operator's 'print regardless') | Full-page DeviceCMYK 1-bpc image from the bitcmyk render, A4 uncut on Legal; IPP: application/pdf, Legal, scaling none, color, normal, one-sided; `successful-ok`, job-id 126. File sha256 `dcbf929089f6b91f7c63dde10b088a32a5316c15aa88f0cdd472134ecbad64c9`. Media: Legal from the tray (stock: OPERATOR TO FILL); cut to 297 mm before scanning. The sheet's value depends on 039.3j's loupe verdict (pure C/M/Y patches single-toner). |
| 039.3l-J | 2026-09-17 | **PRINT sheet J, footing `ipp-pdf`**: `scripts/print_ipp_raster.sh scratch/versalink-20260916/urf/J-c1-cmy8-r0700-at-106x74-on-legal-uncut-cmyk.pdf … na_legal_8.5x14in color` (operator's `yes` per sheet, printed BEFORE the colour discovery sheet's loupe verdict — by the operator's 'print regardless') | Full-page DeviceCMYK 1-bpc image from the bitcmyk render, A4 uncut on Legal; IPP: application/pdf, Legal, scaling none, color, normal, one-sided; `successful-ok`, job-id 127. File sha256 `c05a47f7ccd6772825ad28d11742cdf7cd4b49c6e0a1362380ace5da33d9968b`. Media: Legal from the tray (stock: OPERATOR TO FILL); cut to 297 mm before scanning. The sheet's value depends on 039.3j's loupe verdict (pure C/M/Y patches single-toner). |

### 039.3d The `ipp-urf` route — what it is and why

The VersaLink C7130's only network print path is IPP at a fixed 600 dpi
taking rasters (URF/PWG), JPEG and PDF. A raster at 600 dpi IS the dot
pattern: the printer's RIP never sees a page description, so this path
removes an interpreter from the loop rather than adding one — provided
the engine does not smooth or re-screen rasters on the way to the drum,
which is exactly what the discovery sheet on this path measures. Colour
on this path is OPEN: the raster formats are 8-bit grey and 24-bit sRGB,
so a CMY dot pattern would pass through colour management and the
halftoner (K-only first). Letter vs A4: with `print-scaling none` the
raster lands 1:1, so either A4 goes into a tray (`iso_a4_210x297mm`) or
the A4 raster is placed on Legal and the sheet cut to 297 mm (this
print). The Letter-centred variant (`…-letter-centered-w8.urf`, sha
`83bbc1ac…`, 8.8 mm cut top and bottom) exists but was NOT printed: the
cut takes the edge-reach ladders and part of the corner satellites the
analyzer registers on. Letter-centred geometry was proven on sheet A:
the Letter render is the A4 bitmap shifted by exactly 70 x 208 dots
(cross-correlation peak; no scaling; the residual dot mismatch first seen
there was the pbmraw halftone of 039.3e, not geometry — placement is
done on the bitmap by whole dots, never by a PostScript translate). The 1200x2400 question is CLOSED on
this path: 600 dpi is the only resolution the endpoint offers.

The wrapper `scripts/print_ipp_raster.sh` mirrors `print_plane.sh`
(tty + `yes` required), bypasses CUPS (`ipptool` Print-Job straight at
`ipps://<host>/ipp/print`, self-signed certificate trusted through a
throwaway HOME), and pins scaling off.

### 039.3g The whole set for the `ipp-urf` / `ipp-pdf` routes (built 2026-09-17, verified, print state per run row)

Two transcriptions, both from ghostscript's `bitcmyk` render at 600 dpi
(the emission-gate render, the K plane exact, C/M/Y planes exact,
PostScript overprint honoured — checked on the colour discovery sheet's
`screen/path/opm1-CM` probe: 42,912 C∧M dots, identical to its composite
`devicecmyk-CM` sibling), placed A4-uncut on Legal by whole dots:

- **K sheets → Apple raster W8** (`urf_raster.py`; the route that printed
  039.3f): A–E and the B/W discovery sheet.
- **Colour sheets → PDF, one full-page 1-bit-per-component DeviceCMYK
  image** (`cmyk_pdf.py`): the colour discovery sheet and F–J. The PDF's
  MediaBox is the bitmap's size, the image covers the page, /Interpolate
  false, /Decode [0 1 ×4]; every file re-rendered by ghostscript and
  compared plane for plane (0 differing dots) before being kept. The
  route's OPEN question is the PRINTER's: whether its PDF path treats
  DeviceCMYK as its own colourants (no colour management, no K
  substitution) — footing `ipp-pdf`, distinct from `ipp-urf`; the colour
  discovery sheet on this path is the probe (loupe: are the pure C, M, Y
  patches single toners; are the per-plane gratings clean). The URF path
  cannot carry colour faithfully: this printer's URF is W8 / SRGB24 only,
  and sRGB is colour-managed.
- `print_ipp_raster.sh` sends a `*cmyk*.pdf` only with `color` as its
  4th argument (`print-color-mode color`); everything else `monochrome`.

| file (`scratch/versalink-20260916/urf/`) | bytes | sha256 |
|---|---:|---|
| `A-c4-k-r0700-at-26x18-on-legal-uncut-w8.urf` | 1,933,418 | `32b5feec2a6b806afd0bd5f35e8210380d6ef72bd67025d2b8b7ec65120e0a7f` |
| `B-c3-k-r0700-at-35x24-on-legal-uncut-w8.urf` | 3,457,629 | `168f484d05d908cbca7249690bdfefdd5b5514658198aef476a3f52af33b46f9` |
| `C-c2-k-r0700-at-53x37-on-legal-uncut-w8.urf` | 8,060,427 | `fbd1eca52f952c25bc5fb7a9f7dbe97939fc235d8e84cada8ad56ed85e326f98` |
| `D-c2-k-r0850-at-53x37-on-legal-uncut-w8.urf` | 8,066,783 | `2bf4f5bfae8c1c8e7a9cf81747ba74e8ae4aa478e76f3c1fbc00f85e8869b3d2` |
| `E-c1-k-r0700-at-106x74-on-legal-uncut-w8.urf` | 28,170,997 | `8d320b8e7fbae2684ec6155d71f02d8abe4c2895c7e882e7e10478d95edf620f` |
| `hcal-discovery-bw-K-on-legal-uncut-w8.urf` | 5,596,897 | `c9e28b3e99eccaeae4577f619f40a725baabdc1ab1a0cee64d7e63265a47885e` |
| `F-c3-cmy8-r0700-at-35x24-on-legal-uncut-cmyk.pdf` | 2,254,119 | `ca35006f5e24824954c947a4d49ed004edf3328362fb3517b5b76018dd23953f` |
| `G-c2-cmy8-r0700-on-legal-uncut-cmyk.pdf` | 3,718,034 | `a8116ecc8a273c2a483dafd5a3b7900a57f4bd057eae1d6318af9da2ecdb869f` |
| `H-c2-cmy8-r0775-at-53x37-on-legal-uncut-cmyk.pdf` | 3,718,365 | `10bb59b085537dda27f30209a5f3806c746dc199dbd1b77ab17a90ca7b31da39` |
| `I-c2-cmy8-r0850-at-53x37-on-legal-uncut-cmyk.pdf` | 3,718,310 | `dcbf929089f6b91f7c63dde10b088a32a5316c15aa88f0cdd472134ecbad64c9` |
| `J-c1-cmy8-r0700-at-106x74-on-legal-uncut-cmyk.pdf` | 12,217,530 | `c05a47f7ccd6772825ad28d11742cdf7cd4b49c6e0a1362380ace5da33d9968b` |
| `hcal-discovery-bw-K-on-legal-uncut-bilevel.pdf` | 628,747 | `c590c8fc15d7ef0a126efe4e1d856606077ea22d3cb5936d13b3b699e3c247a6` |
| `hcal-discovery-color-on-legal-uncut-cmyk.pdf` | 938,350 | `eac1cfd2e1a00a45e10c0fd4467f6a7e02c68a99ce8d085e72639cad9ab65f26` |

### 039.3h The colour question — what the record says (research 2026-09-17, four lenses, eight refuters)

- **Documentation cannot answer it.** No Xerox or Fujifilm document states how
  the C7130's built-in PDF interpreter — Fujifilm's proprietary "PDF Bridge"
  decomposer (Xerox fault codes 016-751/752 name it), NOT Adobe's — treats
  DeviceCMYK: pass-through, colour-managed, or K-substituted. The only
  documented "Color Correction: None" is a PostScript print-driver option
  and is unreachable on the direct-PDF path. Device-side knobs that exist:
  EWS System > PDL Settings > PDF > Decomposer (PDF Bridge vs PostScript,
  the latter only with the optional Adobe PostScript 3 kit, part 497K23630,
  a licence key, no hardware); Apps > Printing > General > Defaults &
  Policies > Output Color; System > Defaults and Policies > Common > Color
  Printing Optimization (Color / Economy / Black & White) and Photo Image
  Pseudo Gradation Mode. OPERATOR: snapshot these from the EWS and the
  Configuration Report's PDL line before the colour prints are read.
- **The PDF recipe as built is the right probe** (ISO 32000: DeviceCMYK
  components are the device's colourants unless a /DefaultCMYK, OutputIntent
  or ICC space re-interprets them — this file carries none): one page-sized
  /DeviceCMYK /BitsPerComponent 1 image, /Interpolate false, MediaBox = the
  media (Legal, 612x1008 pt — a refuter's catch: it must match the sheet the
  job names), PDF 1.4, far under the printer's 85 MB PDF cap; sent with
  print-scaling none, print-color-mode color. 1:1 sample-to-dot rendering is
  an implementation property, not a spec guarantee — the loupe checks it
  (single dots, 1-on/1-off gratings, checkerboard moiré per plane).
- **Apple raster cannot carry colour faithfully on this unit as advertised**
  (urf-supported W8, SRGB24 only; sRGB is colour-managed), but the format
  has a DeviceCMYK page type — colour code 6, 32 bpp chunky C,M,Y,K 0/255
  (CUPS raster-stream.c; token DEVCMYK32) — which this printer does not
  advertise. A job in that type either prints or is refused with
  document-format-error; refusal costs no paper. Built and round-trip
  verified: `hcal-discovery-color-on-legal-uncut-devcmyk32.urf` (039.3g
  table below is superseded by the run rows for this file).
- **PWG raster has NO 1-bit colour type** (PWG 5102.4 Table 12: only
  black_1 and sgray_1 are 1-bit); colour there would be cmyk_8 (32 bpp,
  15–119 MB per sheet at our cell sizes), unadvertised here. Third in line.
- **The proven route is recoverable, not gone**: PostScript 3 is an optional
  licensed kit on the C7120/25/30, and Raw TCP/IP 9100 / LPR are supported
  protocols an administrator has switched off. With either, e031–e033's
  setcmykcolor + imagemask path applies unchanged.

### 039.3m The vertical stripe on the c2/c3 colour prints — NOT in the data

Operator observation (2026-09-17, photo of the stacked colour sheets on the
desk): a lighter vertical band, full page height, at roughly 40 % of the
width, on the c2 sheets (G/H/I) and the c3 sheet (F), NOT on c1 (J) and
not on the K c4. Checked against what the printer received: the planes
decoded from the sent PDFs (`cmyk_pdf.render_cmyk` on the PDF bytes) give
a column-wise ink coverage, in 40 bins across the field, of C 0.497–0.501,
M 0.497–0.504, Y 0.486–0.492 for G and the same to ±0.005 for F — flat, no
step, no band (density maps and full-resolution strips:
`urf/{G-c2,F-c3}-density-map-16x16-from-pdf.png`,
`urf/{G-c2,F-c3}-fullres-strip-row*-from-pdf.png`). The band is the
ENGINE's: a process-direction non-uniformity whose visibility depends on
the feature size (present at 2–3-dot cells, absent at 1 and 4), i.e. a
development/transfer contrast band of the kind e038 measured on the M281
(there M/Y certified only inside one such band). Cannot be quantified
without a scan; the receiver's per-window calibration is what absorbs it.
Record it against footing `ipp-pdf` + this engine + this day; re-check on
the K sheets under raking light.

### 039.3n Sheet E (c1-K) from phone photos — NULL, inconclusive (2026-09-17)

Four 12-megapixel phone JPEGs (3072x4080; `/tmp/c1-photos/photo-2026-09-17-*.jpg`,
copied from the operator's Downloads) of the c1-K print (job 120), decoded
with holo3 as `c1-k-r0700@106x74`, `--max-pages 1 --no-close`, 2 workers,
15-minute cap, one run per (photo, pitch hypothesis) because the survey's
lattice estimator was weak on this material (line contrasts 30–70 against
100–300 on the c4 photos of 2026-09-16; lines at ~7.5, ~5.9, ~4.7, ~3.0 px
disagreeing across patches): 13 runs, **0 words, 0 certificates**. The
survey refused one (macro frame at 3590 dpi: it measures an 11.9 px
lattice, i.e. the 7100 dpi hypothesis), accepted the rest without a vote;
the macro frame at 7100 dpi covered 67,642 cells (~4x4 tiles) and committed
13 poses but read no word (its full-resolution crop is out of focus — the
phone's ultrawide macro mode at its limit); photo 3 at 2840 dpi committed 10
poses / 5 addressed, 0 words. The three low-dpi runs on the wide frames
(1740/1820/1860 dpi = 2.9–3.1 px per cell, the pitch the frames' visible
margins imply) were killed by the cap before writing a status block.
Reading: the wide frames sample a 42 µm cell with 2.5–3 camera pixels,
below what any decode in the record has worked from; the only close frame
is unfocused. A c1 decode from a phone needs ≥8 px per cell (a 20–35 mm
frame at 50 MP: tele-macro or a clip-on lens, on a stand, perpendicular),
and the Canon at 4800 dpi gives 8 px per dot for free. What the photos DO
show, dot for dot: isolated 42 µm cells printed as separate dots on this
engine via `ipp-urf` — the first engine in the record where cell=1 is
visibly alive (e025/e031: dead on the M281 and the AltaLink). To be
measured on the B/W discovery sheet's single-dot probes, not claimed from
a photo.

### 039.3o The colour PDF path is colour-managed AND re-screened — loupe verdict on 039.3j

Operator's macro photo of the colour discovery sheet (job 121): every
colour patch carries a ~45° LINE screen over the cells; the cells are not
single-toner dots but screened mixtures ("screened mush"). Verdict on
`ipp-pdf` with the composite DeviceCMYK image: NOT bit-faithful — the
Fujifilm PDF Bridge decomposer colour-manages the image and halftones it.
The K route (`ipp-urf` W8) is unaffected. Also visible: yellow tracking
dots on the white paper (MIC) — this VersaLink marks colour pages like the
AltaLink (e031). Probes prepared, not printed (each one Legal sheet):
PWG raster cmyk_8 (`pwg_raster.py`, header validated by libcups
read-back; acceptance unadvertised, a refusal costs no paper), stencil
PDFs (`stencil_pdf.py`: per-plane /ImageMask with 100 % DeviceCMYK fills
+ overprint, and the same with /Separation /Cyan /Magenta /Yellow), and the
job-attribute variants `print-quality 5` / `print-content-optimize
graphics|text` (wrapper env `PRINT_QUALITY`, `CONTENT_OPTIMIZE`). The
research on which of these can work on this controller is 039.3p.

### 039.3p The labelled COLOUR ROUTE PROBE page (built 2026-09-17, not yet printed)

`experiments/039-xerox-versalink/probe_page.py`: one Legal sheet, the same
700x700-dot test pattern (solid C/M/Y/K, random 2x2-cell fields per plane,
1-on/1-off gratings, isolated single dots, overprint blocks C+M / C+Y / M+Y
/ C+M+Y, overlapping random C/M/Y fields) drawn by eight PDF constructions
in labelled panels (ten since the 039.3q review) — 1 composite DeviceCMYK image, 2 the same under an
ExtGState /HT (600 lpi, 0°, SimpleDot, identity /TR), 3 per-plane
/ImageMask stencils with 100 % DeviceCMYK fills + overprint (/OP /OPM 1),
4 the same without overprint (knockout control), 5 stencils filled in
/Separation /Cyan /Magenta /Yellow /Black, 6 the same without overprint
(knockout control), 7 one filled rectangle per run of cells per plane
(vector, overprint), 8 an /Indexed [/DeviceCMYK] image with the 16-entry
palette, 9 one /ImageMask per INK STATE (C, M, Y, CM, CY, MY, CMY, K —
disjoint) with pure DeviceCMYK fills and NO overprint, 10 the same state
masks filled in /DeviceN [/Cyan /Magenta /Yellow]; `--ht1x1` = the page
under a HalftoneType 5 whose every colourant is a 1x1 threshold array —
plus a wrapped title block (24/18/11 pt) naming the route and the job
attributes the sheet is sent with. Verified: ghostscript renders every panel to the
pattern exactly (the knockout controls to the knockout expectation). The
same page as a PWG raster cmyk_8 (labels rasterised into K; header
validated by libcups read-back). Job-attribute variants are the same page
with a different title: `PRINT_QUALITY` 4/5 and `CONTENT_OPTIMIZE`
auto/text/graphics through the wrapper.

| file (`scratch/versalink-20260916/probe/`) | bytes | sha256 |
|---|---:|---|
| `probe-page-pdf-high-auto.pdf` | 1,083,076 | `99ced5b2ae3d88ba2b5e7a357986a8866fee5cc3c8271362510cd14deed94e85` |
| `probe-page-pdf-normal-auto-ht1x1.pdf` | 1,083,125 | `d7085280a4dddfa2b3154a3bf35c0c56e4c3fc088af3db83fb77fc43035e5a35` |
| `probe-page-pdf-normal-auto.pdf` | 1,083,078 | `fb396373ea4d3639fac9c9b5b70b312d5947db03d7d49ed3f663f421c9ac94ee` |
| `probe-page-pdf-normal-graphics.pdf` | 1,083,082 | `7861209133aaadc9b067499547b65640c7a3772ed72af18a36802b08291f5787` |
| `probe-page-pdf-normal-text.pdf` | 1,083,078 | `f12b2c5db8c03464fdb90fd5085bb8fb502b2cedf0e8cebc2bcc114e83964a2c` |
| `probe-page-pwg-cmyk8-normal-auto.pwg` | 1,232,727 | `28094ee95bacd31641919a46aa35ec18842e693ad115d5d3ace0ff7f418f45f6` |
| `srgb-chart-normal.urf` | 1,054,549 | `b1ce9d0bc427bf07b82510be842252d52ab888f4a5ae9d365e326314f4cf9b7d` |

### 039.3q What the record says about un-screening colour on this controller (research 2026-09-17, four lenses, eight refuters)

- **Mechanism, agreed by every refuter:** a halftone cannot alter a 0 % or
  100 % colourant value — that is why the W8 raster printed dot for dot.
  The "mush" means the C/M/Y values reaching the halftoner were no longer
  0/100 %: the PDF Bridge decomposer's colour conversion (the family's
  "colour correction" / press simulation, Xerox Automatic Color by default,
  no documented "none" on the PDF path), ink-limit/GCR on the 200–300 %
  overprint cells, and possibly resampling — the family's PDF direct-print
  item 405 "Layout" defaults to AUTO SCALE, so the colour PDF prints
  (039.3j, 039.3l) may be resampled by 1–2 % as well. OPERATOR: ruler the
  field width of colour sheet G against K sheet C (both 200.6 mm at c2);
  set EWS PDF Layout = 100 %, Print Mode = Standard before the next PDF.
- **Levers that only change the screen (pseudo-gradation mode, Thin
  Lines, print-quality, print-content-optimize, media-type) cannot
  restore 0/100 %** — they are A/B diagnostics, not the fix.
- **Levers that bypass conversion, ranked:** (1) object class — stencil
  fills of 100 % single colourants (probe panels 3/5) and, freed from the
  overprint dependency composite devices may ignore, per-ink-state
  stencils (panels 9/10); (2) ISO 32000-1 §8.6.6.4/5: a /Separation or
  /DeviceN colourant NAMED Cyan/Magenta/Yellow "shall apply the designated
  colorant directly", the one normative colour-management bypass in PDF
  (panels 5/10); (3) a job halftone (/HT) — readers may ignore it, but if
  honoured a 1x1 threshold re-binarises every converted value (the
  `--ht1x1` sheet); (4) the raster path: PWG cmyk_8 (unadvertised; the URF
  DeviceCMYK refusal is the prior), and the SRGB24 fixed-point chart —
  whether the device's sRGB→CMYK table maps ANY triple to a single toner
  (`srgb_chart.py`); (5) PCL 5c / PCL XL Color over octet-stream — the
  C71xx PDL guide documents `@PJL SET BITSPERPIXEL=1` per plane and PCL5c
  simple colour's 8-entry device-CMY palette IS the cmy8 alphabet; the
  Fujifilm PCL interpreter's colour correction is undocumented and its
  EWS "Image Enhancement" must be OFF — a stream the IPP port does not
  recognise can print as text (039.3a), so a tiny job first; (6) the
  Adobe PostScript 3 kit (497K23630, licence key, ~£350) — with the
  caveat a refuter found: on the Fujifilm PS path "CMYK Color Correction"
  is a default-ON job parameter with "No Correction" only in the driver
  ticket, so the kit alone does not reproduce the AltaLink result without
  that ticket; (7) capturing the Xerox driver's job stream with Color
  Adjustment = none / Image Enhancement off and splicing our planes in.
- **Zero-paper facts:** Validate-Job with ipp-attribute-fidelity=true
  answers whether print-color-mode=process-bi-level, print-rendering-intent
  and print-content-optimize=photo exist here (039.3r); the printer omits
  the REQUIRED pwg-raster-document-type-supported, so no mainstream client
  ever sends it PWG raster — every raster-colour outcome is measured, not
  read.

### 039.3r Zero-paper IPP facts (2026-09-17, Validate-Job with ipp-attribute-fidelity=true, no job created)

| attribute = value | printer's answer |
|---|---|
| print-color-mode = process-bi-level | `client-error-attributes-or-values-not-supported` — no threshold-colour mode |
| print-rendering-intent = relative | attribute itself unsupported (no ICC profiles published) |
| print-content-optimize = photo | value not supported (auto/graphics/text/text-and-graphics only) |
| print-content-optimize = text | `successful-ok` |
| print-quality = 5 (high) | `successful-ok` |
| media-type = stationery-heavyweight (bare) | attribute not supported as a job attribute (lives inside media-col) |
| fx-bi-color-print-info = none | value not supported — Fujifilm's dual-colour (red/black) mode selector, not a rendering switch |

Get-Printer-Attributes asked with `document-format=image/pwg-raster` (the
printer declares `printer-get-attributes-supported = document-format`)
returns NO `pwg-raster-*` attribute at all: the device itself documents
no PWG colour type. `pdf-versions-supported = iso-32000-1_2008`,
`pdf-k-octets-supported = 0-85000` (our largest PDF is 12 MB).

### 039.3s The probe prints (2026-09-17 17:14–17:15)

| run | date | action | details |
|---|---|---|---|
| 039.3s-128 | 2026-09-17 | **PRINT probe, job-id 128**: `probe-page-pwg-cmyk8-normal-auto.pwg` via `print_ipp_raster.sh … color` (image/pwg-raster cmyk_8, quality normal; operator's `yes`) | **ACCEPTED and completed** — the first device-CMYK job this printer has taken; the raster path that printed W8 bit-faithfully now carries C/M/Y/K 0/255. Legal, scaling none, color. `successful-ok`, completed (128–132 at 17:14:58–17:15:18; 133/134 printing at the query). sha256 `28094ee95bacd31641919a46aa35ec18842e693ad115d5d3ace0ff7f418f45f6`. LOUPE OWED per panel/patch: pure C/M/Y one toner? line screen over the random-cell fields? overprint blocks both toners, CMY block no K? |
| 039.3s-129 | 2026-09-17 | **PRINT probe, job-id 129**: `probe-page-pdf-normal-auto.pdf` via `print_ipp_raster.sh … color` (application/pdf, quality normal, no content-optimize; operator's `yes`) | ten constructions side by side. Legal, scaling none, color. `successful-ok`, completed (128–132 at 17:14:58–17:15:18; 133/134 printing at the query). sha256 `fb396373ea4d3639fac9c9b5b70b312d5947db03d7d49ed3f663f421c9ac94ee`. LOUPE OWED per panel/patch: pure C/M/Y one toner? line screen over the random-cell fields? overprint blocks both toners, CMY block no K? |
| 039.3s-130 | 2026-09-17 | **PRINT probe, job-id 130**: `probe-page-pdf-normal-auto-ht1x1.pdf` via `print_ipp_raster.sh … color` (application/pdf, quality normal, page-wide HalftoneType 5 with 1x1 threshold arrays; operator's `yes`) | job-halftone probe. Legal, scaling none, color. `successful-ok`, completed (128–132 at 17:14:58–17:15:18; 133/134 printing at the query). sha256 `d7085280a4dddfa2b3154a3bf35c0c56e4c3fc088af3db83fb77fc43035e5a35`. LOUPE OWED per panel/patch: pure C/M/Y one toner? line screen over the random-cell fields? overprint blocks both toners, CMY block no K? |
| 039.3s-131 | 2026-09-17 | **PRINT probe, job-id 131**: `probe-page-pdf-high-auto.pdf` via `print_ipp_raster.sh … color` (application/pdf, print-quality high (5); operator's `yes`) | rendering-mode A/B. Legal, scaling none, color. `successful-ok`, completed (128–132 at 17:14:58–17:15:18; 133/134 printing at the query). sha256 `99ced5b2ae3d88ba2b5e7a357986a8866fee5cc3c8271362510cd14deed94e85`. LOUPE OWED per panel/patch: pure C/M/Y one toner? line screen over the random-cell fields? overprint blocks both toners, CMY block no K? |
| 039.3s-132 | 2026-09-17 | **PRINT probe, job-id 132**: `probe-page-pdf-normal-text.pdf` via `print_ipp_raster.sh … color` (application/pdf, print-content-optimize text; operator's `yes`) | rendering-mode A/B. Legal, scaling none, color. `successful-ok`, completed (128–132 at 17:14:58–17:15:18; 133/134 printing at the query). sha256 `f12b2c5db8c03464fdb90fd5085bb8fb502b2cedf0e8cebc2bcc114e83964a2c`. LOUPE OWED per panel/patch: pure C/M/Y one toner? line screen over the random-cell fields? overprint blocks both toners, CMY block no K? |
| 039.3s-133 | 2026-09-17 | **PRINT probe, job-id 133**: `probe-page-pdf-normal-graphics.pdf` via `print_ipp_raster.sh … color` (application/pdf, print-content-optimize graphics; operator's `yes`) | rendering-mode A/B. Legal, scaling none, color. `successful-ok`, completed (128–132 at 17:14:58–17:15:18; 133/134 printing at the query). sha256 `7861209133aaadc9b067499547b65640c7a3772ed72af18a36802b08291f5787`. LOUPE OWED per panel/patch: pure C/M/Y one toner? line screen over the random-cell fields? overprint blocks both toners, CMY block no K? |
| 039.3s-134 | 2026-09-17 | **PRINT probe, job-id 134**: `srgb-chart-normal.urf` via `print_ipp_raster.sh … color` (image/urf SRGB24, quality normal; operator's `yes`) | sRGB fixed-point chart: 25 labelled patches. Legal, scaling none, color. `successful-ok`, completed (128–132 at 17:14:58–17:15:18; 133/134 printing at the query). sha256 `b1ce9d0bc427bf07b82510be842252d52ab888f4a5ae9d365e326314f4cf9b7d`. LOUPE OWED per panel/patch: pure C/M/Y one toner? line screen over the random-cell fields? overprint blocks both toners, CMY block no K? |

### 039.3t The probe sheets scanned (2026-09-29, Canon flatbed, 1200 dpi RGB)

Seven Legal probe sheets (high-gloss stock), one capture each, full platen
(10208x14032 px; the bottom ~2.3 in of each Legal sheet is off the glass, no
panel lost). Files in `scratch/<city>/`. Read by eye at full resolution and by
2-D FFT of 180–256 px windows per patch (screen = the dominant peak).
The printers: `<host>` = office printer A (039.3a only);
`<host>` = office printer B, the VersaLink C7130 (every other run).

| scan | job | sha256 | verdict |
|---|---:|---|---|
| a.tiff | 128 PWG cmyk_8 | `cf5f678ea34ee49eef3668bf5ed52ae8e69176d480cc6ee7cb8a650403ac2284` | **COLOUR DROPPED, K INVERTED**: the page is neutral grey (p99 chroma 5 levels); only the K byte is used, as luminance — K=255 prints white, K=0 (the whole background, and every C/M/Y-only area) prints dark grey. Accepted ≠ honoured: the PWG cmyk_8 route is dead. |
| b.tiff | 129 PDF normal | `f0cd3ff34654c62a6cdb99c64db00bc7f9a4ca941c69b35e61ee59965093a88d` | C/M/Y solids LINE-SCREENED at 164 lpi (C 63°, M 117°), K solid; random 2x2 fields survive as cells with screen texture inside; images (panels 1/2/8): 1-on/1-off gratings become screen tone, isolated C/M/Y dots vanish (K faint); stencils/separations/vector (3–7): single dots print in all four colours, gratings partly survive with moiré; OVERPRINT IGNORED (3/5/7 print as their knockout controls 4/6); per-state masks (9/10) and the composite image give correct overlaps. |
| c.tiff | 130 PDF + 1x1 job halftone | `ce557d9ad134e179cc06c4a04b4826ed11f231e48d7ae8b55b5d4458125f2c63` | same as b — the job halftone is ignored. |
| d.tiff | 131 PDF quality high | `fb96b1bd3ab982e2b0fc1df4318a140215bd14076e28c07d0ef4098148b47819` | same screen; image panels LOSE DATA (first grating row missing, second printed as a flat block, single dots gone); stencil gratings flattened to tone, C/M/Y single dots gone. Worse than normal. |
| e.tiff | 132 PDF optimise text | `3ce58bd333dd4d6cb6d8afb2bb157aa7b159629c99d80f28b84a4934f6208f2d` | same as b. |
| f.tiff | 133 PDF optimise graphics | `fe4929caffd0443c345dd37b06453dd6b2342206682422d92695cc519bb2cbf8` | same as b. |
| g.tiff | 134 URF SRGB24 chart | `e7b0bdcea8ec6602c6d709ce9aa45aee9d14264156916f0d29053b5027b3f750` | isolated single dots vanish in EVERY colour, K included; random 2x2 fields print. Unscreened (164-lpi power share ≤ 0.001): Y (255,255,0) and Y~2 (255,255,15) — a solid yellow a touch lighter than the PDF Y solid; R (255,0,0); M~2 (255,0,240). Magenta patches are pink (mean RGB ~226,68,122 vs the PDF M solid 184,63,73) = NOT full magenta. Every cyan variant is cyan + yellow, line-screened (share 0.17–0.34); G/B/purples/orange-yellows screened two-toner. No sRGB triple gives single-toner cyan. |

**h.tiff — the colour discovery sheet (job 121, `ipp-pdf`), 2400 dpi RGB.**
`confetti.py discover analyze … --scan-dpi 2400 --printer
xerox-versalink-c7130 --print-path ipp-pdf --media legal-high-gloss
--scanner canon-4800 --scan-mode color-no-auto --print-session
2026-09-17-<office>` → **refused**, `corner_registration_failed`, "found chiral
corners [3, 4]; need at least 3" (report
`scratch/<city>/reports/hcal-report-refused-unknown-copy0000-91f2dff8add8e4d1.json`).
Cause, by comparison with the sent PDF rendered by gs: the engine's top
unprintable margin (~4 mm) cuts the marks nearest the top edge — the
top-left corner's top arm is gone but two marks, the top-right arm (lower
on the page) survives. The A4 sheet was placed FLUSH with the Legal top
edge (039.3c placement), so the Legal clip lands on the sheet: a
PLACEMENT error of ours, not the engine's. The B/W discovery sheet (job
112) and every payload sheet A–J share that placement (their top ~4 mm
are clipped the same way). Next time: offset the A4 raster down by ≥ 6 mm
(Legal has 58 mm spare). Scale: the top ruler frame measures 96.44 mm on
the scan against 96.48 mm in the sent PDF (ratio 0.9996, horizontal) —
**the PDF route does NOT auto-scale** (the owed ruler check, closed).
Visible on the sheet: every colour area line-screened as on the probe
pages; the random fields print as cells.

WHY corners 1/2 were refused (the clip is NOT the cause — all four crosses
and satellites are on paper): the top crosses' 3-dot horizontal arm, solid
in the sent PDF, prints HATCHED (cut into diagonal dashes by the engine's
screen); on the 300-dpi corner thumbnail it falls apart into 1–2 px tall,
4 px long dashes with 5 px gaps, the component is the vertical arm alone
(w 6–8 px against a 36–95 px span gate) and no cross is found. The bottom
crosses print solid. FORCED with
`experiments/039-xerox-versalink/analyze_bridged_corners.py` (diagnostic
harness: on the corner thumbnail only, components ≤ 2 px tall and ≤ 12 px
in area are widened 3 px each side; a plain 1x7 grey opening swallowed the
satellites and found zero corners) → `status: ok`, report
`scratch/<city>/reports/hcal-report-discovery-color-copy0000-4461589f3e990e98.json`,
NOT promotable. Findings:

- **The printed page is not an affine image of the layout.** Corner fit rms
  6.26 dots, residuals ±6.26 dots in y alternating TL/TR/BR/BL (a twist);
  measured directly: the top ruler frame is tilted 6.8 mrad, the bottom one
  0.9 mrad — the top of the sheet is rotated ~6 mrad against its bottom
  (print transport or the glossy Legal sheet lifting on the platen; a
  180°-rotated rescan would attribute it). Consequence: 33 of 52 candidates
  `unmeasurable`, their fields `geometry_uncertified`; every cm4/cmy7/cmy8
  row among them. Scale 0.9995 / 0.9990.
- Clip measured: left 1.00, top 3.67, right 1.04, bottom 0.34 mm (the top
  is the Legal top edge — the placement error above).
- Highest useful authored grid [300, 300]: pure C/M/Y at c2 (2x2 cells of
  300 dpi = 4x4 dots) marginal, whole 0.30–0.55 %, window p95 1.2–2.3 %,
  ~34 b/mm²; cm4 at 300 fragile 5.1 %; every 600-grid pure plane at c3
  fragile 10–11 %; grid rulers at 600: 1-on/1-off fail in every plane (the
  screen), 2-on/2-off pass horizontally. These numbers are taken under the
  6-dot misfit above and are pessimistic by an unknown amount.
- Plane registration against K (nine targets): C median (21, −16) µm, M
  (−7, 13) µm, Y (9, 23) µm; spread across the page up to 62/69 µm for C/M
  and 118/197 µm for Y (1.5–4.7 dots).
- Scanner adequacy `inadequate` (marginal_class, sampling, solid_class) —
  the instrument's own caveat; the 2400 capture of a screened page.

**Payload decodes (holo3, `--max-pages 1 --workers 8 --diag 8023`, M-class
machine 1, 2026-09-29/30).**

- **Sheet D `c2-k-r0850@53x37` (job 119, `ipp-urf`) — VERIFIED 657,042 B,
  sha256 `fe8fa0b936c960fdf33647058704bb0aa1a63ef7e7ea070328be3ecb06b422d4`
  == the 039.2 emission's payload sha.** One Canon capture, 1200 dpi grey
  (`scratch/<city>/j-c2-k-1200dpi.tiff`); closed at 1,553 certificates
  against K 1,552 of 1,961 tiles (scan 644, retry 909), 3,086 cpu-s,
  metadata rank 24/24. The first volume recovered from a VersaLink print
  and from the `ipp-urf` footing — the K raster path carries c2 at r0850.
  Raw hard cell error against the emitted field (`cell_error.py`, below):
  **5.8 %** (median threshold; inked mean 66.6 vs blank 163.0). Single
  sheet, single capture — NO promotion.
- **Sheet E `c1-k-r0700@106x74` (job 120, `ipp-urf`) — NOT RECOVERED,
  0 certificates in four runs.** Scans: `i-c1-k-2400dpi.tiff` (RGB) and
  `i-c1-k-2400dpi-grey.tiff` (grey), both 2400 dpi.
  - Run 1, RGB alone: 7,883 cpu-s; ONE address word decoded (tile (26,48),
    9 errors of 100) placed one window, the other 213 poses are CHAIN poses
    from it; chain-pose mismatch median 0.169 (p10 0.142, p90 0.193, max
    0.200 = the placement gate `GATE_SEARCH_TRUE`); 833 windows
    `consult_refused`; 918 tiles attempted, none certified. The diag's
    "100" per tile is address-site COVERAGE by chained poses, not a word
    decode (green only from `WordOutcome`). The RGB→luma mean is not the
    cause: R/B against G 0.00 px in x, +0.14 / −0.11 px in y at left,
    centre and right (under 4 % of a 4-px dot).
  - Run 2, RGB + grey, resumed from run 1: **SCHEDULING PATHOLOGY.** 57
    cpu-hours, 0 certificates, and the grey capture NEVER PLACED: the K
    `ctx` refit (price 15, 288 fires per region, 12 cpu-s each) re-woke
    every window's `calibrate` (108 fires/window) and every tile's
    `tiles.scan`/`tiles.retry` (~127 fires/tile; retries 885,260 jobs,
    142,176 cpu-s) on the RGB capture, all priced 15–21, below the grey
    capture's first `place word_centre` at 60. On a sheet that certifies
    the storm dies as tiles retire; here nothing retires and every chain
    pose buys a region-wide cascade. Colour rows escalate by fire ordinal;
    nothing K-side did ("nothing K-side reads the fire ordinal", SCHEDULE).
  - Run 3, RGB + grey from scratch on Germano's UNCOMMITTED receiver change
    (K `calibrate`/`ctx` now price by ordinal, 82–83 at the end; `ctx` 28
    fires): the grey capture placed first (2,142 poses, 2 words across
    both), 0 certificates; `tiles.retry` still 154,026 jobs / 25,610
    cpu-s — the retry storm is reduced, not gone. Stopped by SIGINT;
    snapshot `scratch/<city>/run-E-c1-k-both2.26022/`. PROVENANCE
    (2026-10-03): the formula later COMMITTED as branch
    `receiver-rework-band` (f845e582, `max(price, 90 + 5(k−2))`, two free
    fires) cannot produce "82–83", so run 3 ran a predecessor shape;
    this log is the record of run 3, the branch was not. The branch was
    judged in the pricing study §6 and deleted 2026-10-03; the fix at
    source is `sched-lifecycle` 037440da.
  - Raw hard cell error against the emitted field, per capture, from run
    3's placements: **RGB 22.0 %** (21,113,341 placed cells;
    inked mean 69.6 vs blank 112.1) and **grey 21.5 %** (17,686,802 cells;
    68.5 vs 111.9), median threshold; the best global threshold changes it
    by ≤ 0.3 pp. Grey mode buys ~0.5 pp — the scan mode is not the limit,
    the 1-dot cell contrast is (D's c2 cells: 66.6 vs 163.0). The chain-pose
    mismatch of 0.17 was an evidence-weighted underestimate.
  - Capacity note: c1 at r0547 (the ladder floor) matches D's 657,042 B at
    source fraction 0.32 (656,821 B), but no rung helps a tile whose cells
    exceed the code's reach; at ~22 % hard error the BSC capacity is ~0.24
    bit/cell, far below r0547. A c1 row would need an inner rung near r0200
    or lower — a format change, not a rung choice.
- **Sheet J `c1-cmy8-r0700@106x74` (job 127, `ipp-pdf`) — MUSH, refused
  at the survey.** Scan `m.tiff`, 2400 dpi RGB. Spectrum (three 1024-px
  windows): 31–61 % of the power in the 150–185 lpi band (peaks 168 lpi at
  63°/117°, 149 lpi at 154°), 3–4 % at 250–600 lpi where 1-dot data lives.
  holo3: "survey … voted printed pitch 1/150 in, but the declared format
  row is 1/600 in" — the screen is the most regular lattice on the page.
- **Sheet F `c3-cmy8-r0700@35x24` (job 123, `ipp-pdf`) — NOT RECOVERED,
  0 certificates.** Scans `n.tiff` (1200 dpi RGB) and `n-2400.tiff` (2400
  dpi RGB). The survey voted 1/300 in against the declared 1/200 in and
  refused; declaring c2 (G) passed the survey and placed nothing. Cell
  edges measured: across the page the 200/in grid leads (6.3x median;
  300/in 2.9x), DOWN the page a one-axis structure at 300/in (41x) plus
  480/576/in — screen or scanner transport, not our square grid — which
  outvotes the true pitch. Forced with
  `experiments/039-xerox-versalink/decode_declared_pitch.py` (the survey's
  vote suppressed → the ruled declared-pitch fallback, RULINGS D5;
  diagnostic, not promotable): it PLACES (1 word, 281 → 402 poses, 3
  plane fields) but certifies nothing in C, M or Y; resumed with the 2400
  capture, stopped by Germano. Raw hard cell error, 3,428,142 placed cells
  of the 1200 capture (median threshold / best global threshold / joint
  8-state genie centroid): **C 16.7 / 17.1 / 16.3 %, M 24.0 / 24.1 /
  23.6 %, Y 30.4 / 30.5 / 29.5 %** — hard-decision capacity ~0.36 / 0.21 /
  0.12 bit/cell against r0700's 0.70. The joint read buys nothing: the
  screen flattened inked/blank contrast in every plane (C 87 vs 154, M 99
  vs 138, Y 88 vs 121). Placements are right (not 50 %), the print is the
  limit.

- **The B/W discovery sheet (job 112, `ipp-urf`)**, `o.tiff`, 2400 dpi
  grey: `discover analyze … --print-path ipp-urf --scan-mode grey-no-auto`
  → **ok** without any harness (the K crosses print solid on the raster
  route), report
  `scratch/<city>/reports/hcal-report-discovery-bw-copy0000-c72d638932409708.json`.
  Highest useful authored grid [300, 300]. On the 600 grid every c2
  construction is MARGINAL at 0.17–1.86 % worst (c2x3 0.17 %, vertical
  0.38 %, horizontal 0.76 %, imagemask 1.86 %; 121–135 b/mm²), c3 and up
  SOLID at 0.00 % — consistent with sheet D's close. **c1 (g600-c1)
  UNMEASURABLE: `geometry_uncertified`, 3 of 20 windows** — the same
  non-affine page misfit as the colour sheet (corner rms 5.26 dots, scale
  0.9993), now on the RASTER route too, so the twist belongs to transport
  or scanner, not to the PDF decomposer; c1 cannot absorb it, c2 can.
  600-grid K rulers: isolated dots pass (0.010), 1-on/1-off fail (h 0.367,
  v 0.285), 2-on/2-off h 0.205 fails, v 0.066 passes. Clip left 1.09, top
  3.76, right 0.32, bottom 0.46 mm. Scanner adequacy `inadequate`
  (solid_class).

**A third <city> engine: HP Color LaserJet MFP M681
(the <office> printer).** The 1200x2400-request discovery pair
(`scratch/versalink-20260916/discovery-request-1200x2400/`), raw
PostScript — `scripts/print_plane.sh` to 9100 or `lpr -o raw`, not
recorded which (machine 4 history shows the aggregate sent by print_plane to
<ip> and the 1200x2400 files copied to a second account); the
sheet's own PostScript report proves the HP interpreted our PS. Letter
stock, page set to A4 (595x842) so the bottom is lost. Scans `p.tiff`
(B/W, 2400 grey) and `q.tiff` (colour, 2400 RGB) — the same HP as sheet
A below (Germano, 2026-09-30); both analyse `ok`
without a harness; reports
`hcal-report-discovery-bw-copy0000-7da101381b28328d.json` and
`hcal-report-discovery-color-copy0000-bf8c9bf0ddc55a3c.json` in
`scratch/<city>/reports/`.
- Self-report: fw 3010.107, PS level 3, default AND effective
  HWResolution (600, 600) — the 1200x2400 request REFUSED, the fourth
  engine under the same law (M281, AltaLink, Canon e040, this).
- B/W, 600 grid: c2 FRAGILE 4.4–5.7 % (horizontal / imagemask / vertical);
  c2x3 0.72 %, c3x2 0.87 % marginal; c3 marginal 0.10 %; c4 solid 0.03 %;
  c1 unmeasurable (geometry). Rulers: dots 1.5 % fail, 1-on/1-off fail
  both axes, 2-on/2-off pass (v 9.0 %, h 17.5 %). Weaker than the
  VersaLink raster route at c2 (0.4–1.9 %); rectangular cells buy ~7x.
- Colour (raw PS, NO screen on single-plane cells): pure C c3 0.00 %,
  pure M c3 0.06 % (solid), pure C/M c2@300 solid; C stress c2 2.1 %, M
  3.9 % marginal; cm4 c2 8.6 % fragile; all 31 cmy7/cmy8/mixed rows
  `geometry_uncertified`. **Y STARVED**: density range C 0.647, M 0.557,
  K 0.598, **Y 0.286** (below the Y-starved M281's 0.351; AltaLink
  0.515); Y registration median (93, 34) µm from K.
- Geometry: corner-fit rms 10.4 (B/W) / 11.5 (colour) dots, scale 1.0005
  x / 0.9977 y; vertical streaks down both sheets. RULED 2026-09-30
  (Germano): the scanner is fine — the twist (VersaLink 5.3–6.3 dots, HP
  10.4–11.5) and the streaks are charged to the prints, not the Canon.
- **Sheet A `c4-k-r0700@26x18` from the HP — VERIFIED 122,892 B, sha256
  `930d4d0730d9960157044adb511d1574e6add45da086c652a0afb016654ba5a9` ==
  the 039.2 emission.** `r.tiff`, one 1200 dpi grey capture; closed at
  365 certificates against K 358 of 468 tiles (all `tiles.scan`), 79
  cpu-s, 6 words, 107 poses. Engine CONFIRMED by Germano 2026-09-30: the
  same HP M681 as the 1200x2400 discovery pair (consistent with
  its vertical streaks and the field cut ~0.8 in short of A4, an A4 page
  on Letter); machine 4 history shows the aggregate (sheet A = page 3) sent
  by `print_plane.sh` to <ip>, i.e. footing `raw9100`.
- **Sheet C `c2-k-r0700@53x37` from the HP — VERIFIED 532,882 B, sha256
  `3cb654e1910d199aa8ff257e8db328c3eee46782c64d5b8208faa9b038c703a8` ==
  the 039.2 emission.** `s.tiff`, one 2400 dpi grey capture; closed at
  1,555 certificates against K 1,552 of 1,961 tiles (scan 520, retry
  1,035), 2,662 cpu-s, metadata rank 24/24. Engine: the HP (same field
  cut as sheet A, printed field ending 10.76 in down the capture; the
  aggregate's page 5). One D1 address contradiction over tile (5,12)
  between two windows 160 cells apart — diagnostic only, nothing
  quarantined, the payload verified. The HP carries c2-K at r0700 despite
  its discovery sheet calling square c2 fragile (4.4–5.7 %) — e031's rule
  again: discovery tiers are channel numbers, not recoverability. Single
  sheet — NO promotion.
- **Sheet E `c1-k-r0700@106x74` from the HP — DEAD at placement.**
  `t.tiff`, one 4800 dpi grey capture (8 px per dot); engine: scanned
  before `v` (Germano: v onward is <city>), so <city>; of the two
  <city> engines only the HP trims A4 on Letter (field ends 10.77 in; the
  VersaLink E scans `i` run to 11.50 in, uncut on Legal). The trim alone
  would NOT have decided it — the Canon trims its default pages the same
  way (040.4d). The survey voted no pitch (declared
  1/600 in fallback); 5,449 `place` jobs, 1,995 cpu-s, ZERO words, zero
  poses, no tile attempted; stopped by SIGINT
  (`scratch/<city>/run-E-c1-k-4800.31549`). Worse than the VersaLink's
  c1 (one word + chained placement at 2400) — consistent with the HP's
  discovery sheet (square c2 fragile, c1 unmeasurable). c1-K is dead on
  both <city> engines.
- **Sheet F `c3-cmy8-r0700@35x24` from the HP — NOT RECOVERED, 0
  certificates.** `u.tiff`, one 2400 dpi RGB capture (field ends 10.80 in
  = the HP). **Y DEAD across two thirds of the page:** a straight vertical
  step at 3.1–3.3 in across the capture at every height from 1 to 10.4 in
  (B−G 14 left / 43 right; R and G flat, so C and M are uniform) — a
  physical Y-plane fault along the feed, matching the discovery sheet q's
  fading Y patches and crosses (Y density range 0.286). Survey accepted
  the declared pitch; 697 poses, 1 word; 42,150 jobs, 15,551 cpu-s
  (tiles.swim 11,074), 1,240 tiles attempted, 0 certified; stopped by
  Germano (`scratch/<city>/run-F-hp.32057`). Cells print UNSCREENED
  (clean c3 blocks at 2400), yet raw hard error at the placed poses
  (`cell_error.py`, 2,306,862 cells) is C 29.1 %, M 18.9 %, Y 48.3 %
  (joint 8-state C 29.3 / M 20.1 / Y 45.0); a sampling-offset search
  (±12 px) takes C to 19.7 % at dy −6 px (half a cell, ~64 µm, a C-plane
  registration offset the page fields had not yet absorbed) and M to 16.6 %
  at +2 px. Split at the Y step (final snapshot; median / joint 8-state):
  Y-alive zone (x < 2.9 in, 1,000,959 cells) C 25.4 / 25.5 %, M 20.6 /
  21.0 %, Y 45.1 / 41.5 %; Y-dead zone (x > 3.6 in, 1,506,456 cells) C
  33.3 / 33.4 %, M 17.8 / 18.5 %, Y 50.6 / 46.5 % — Y carries almost
  nothing even where it prints; C degrades across the page (its
  registration offset, not Y). Mean scan RGB per truth state: every state sits close (blank
  cells 139 vs paper ~230 — neighbour bleed + registration), Y alone moves
  B only 148→132 even where Y is alive.
  **No CMY→K substitution:** CMY cells read (109, 98, 118) left and (111,
  99, 145) right — as bright as or brighter than CM (95, 89, 120 / 101, 91,
  142), blue where Y is dead; near-black cells are 0.1–0.7 % in EVERY state
  (toner specks, not a rendering rule).
  The discovery sheet could NOT have told: its colour page carries no
  CMY-overlap-vs-K probe (screen probes are C and CM only, tone ramps
  single-plane, and every cmy7/cmy8 field was `geometry_uncertified` on
  q); it does show the Y fault (selectivity/Y −0.012, the only failing
  plane; Y range 0.286). An owed instrument addition, not built: a CMY
  overlap beside a K patch at 100 % and at a 50 % random field.
  CHECKED BY HAND on q (Germano's suggestion — Y physically missing makes
  it easy): pixel colour statistics of the matrix fields, no geometry
  needed. Neutral-dark pixels (max channel < 95, spread < 30): cmy8 fields
  in the Y-dead zone 1.1–2.9 %, cm4 fields there 0.000 %, cmy8 where Y is
  alive 6.6–7.4 %, the kcmy4 K control 15.2 %. The dead-zone dark pixels
  are TINTED — mean RGB (71, 62, 78) / (73, 64, 81), B−G ≈ +15 — against
  the K control's neutral (65, 62, 64), B−G +2: the darkest CMY cells
  (C+M plus the residual weak Y), not K toner; a full CMY→K swap would give
  ~1/8 of the cells (≈ 7 %) neutral black in the dead zone too. Confirms
  sheet F: the HP prints C, M, Y as sent, no K generation. The fountain closed over the
  lost bottom rows. Single sheet — NO promotion.

**Scan map, 2026-09-30** (`scratch/<city>/`; letters are scan order, not
sheet names): `i-c1-k-2400dpi[-grey].tiff` = sheet E; `j-c2-k-1200dpi.tiff`
= sheet D; `k.tiff`, `l.tiff` = the Codex diagnostic pages 2/3 (below);
`m.tiff` = sheet J; `n.tiff`, `n-2400.tiff` = sheet F; `o.tiff` = the B/W
discovery sheet; `p.tiff`, `q.tiff` = the HP M681's 1200x2400 discovery pair; `r.tiff` = sheet A
from the HP; `s.tiff` = sheet C from the HP;
`t.tiff` = sheet E from the HP (4800 grey); `u.tiff` = sheet F from the HP; `v.tiff` = sheet E from the <city> Canon
(logged in e040 §040.4c: 21 % raw, no tile below 15 %, 0 certificates).
`w`, `x`, `y`, `z` = the Canon's four discovery sheets, `aa` = sheet A, `ab` =
sheet B, `ac` = sheet C, `ad` + `ad-2400` = sheet D (all VERIFIED) — logged in
e040 §040.4d; `af-<city>-c2-cmy8-0700-{2400,4800,b-2400,c-2400,q1-2400,q2-2400}`
= sheet G from the Canon, six captures (on machine 4; e040 §040.4f).

**Reruns with `analyze_visible_marks.py` (2026-10-01).** h (VersaLink
colour, PDF route): corner+plus refit rms 25.0 → 16.7 px, measured
candidates 19 → 18 of 52, cmy7/cmy8 still all `geometry_uncertified`.
q (HP colour, raw PS): rms 46.0 → 31.4 px, measured 21 → 21; cm4 c2@300
1.6 %, c12@2400 1.9 %, c3@600 5.6 %; cmy7/cmy8 still unmeasured. On both
engines the page is too far from ANY affine (16–31 px rms where the
Canon's sheets fit at 7–9.5 px) and the failing per-window phase fits are
Y (HP, starved) and the screened planes (VersaLink): global placement is
not their limit, a non-affine (local) page model would be.
Sheets A–C and G–I are not scanned.

**The Codex diagnostic pages (k, l).** Not ours: a three-page PDF built on
2026-09-17 by an OpenAI Codex session on machine 4
(`xerox-600dpi-binary-cmyk-test.pdf`, 1-bit DeviceCMYK images at 600 ppi
beside vector controls; copy, capabilities dump and session transcript in
`scratch/<city>/codex-20260917/`), printed from Preview through the macOS
AirPrint queue — a footing of its own, neither `ipp-urf` nor `ipp-pdf`.
Page 2 (binary resolution target), measured at 1200 dpi: 1-pixel bars both
ways and 1-pixel checks = diagonal screen tone; vector 1-pixel bars = SOLID
(bars merged); 2-pixel vertical resolved with density drift; **2-pixel
horizontal SPLIT at one page height in all four colours — resolved bars
above, the diagonal screen below**; 4-pixel bars clean; isolated pixels:
dots vanish, holes fill. The split (not in the file; Codex checked the
image data) reads as the controller classifying image content by region
(line art → binary, tint → 164-lpi screen) with 2-pixel detail on its
decision boundary; the probe sheet's quality-high image corruption (d) is
likely the same mechanism.

**Tools added.** `experiments/039-xerox-versalink/analyze_bridged_corners.py`
(discover analyze with hatched corner arms bridged on the corner thumbnail),
`experiments/039-xerox-versalink/decode_declared_pitch.py` (holo3 decode
with the survey's pitch vote suppressed), `measure/e039-cell-truth/cell_error.py`
(raw per-plane cell error of a capture against `page000_gt.npy`, from a
holo3 snapshot's own placements; validated on D). All three are
diagnostic; nothing they produce is promotable.

**Ruling from the scans:** no job attribute reaches the colour screen
(quality, content-optimise, job halftone all inert; quality high corrupts
images). PWG cmyk_8 drops colour; URF sRGB has no cyan and kills single dots.
The PDF route screens every C/M/Y area at 164 lpi; its best construction is
per-plane stencils at normal quality (single dots and 2x2 cells survive,
overprint must be spelled out as per-ink-state masks, panels 9/10). The
colour payload sheets F–J (PDF composite images) are therefore screened
at the cell level; the payload scans answered it — c1 colour is mush (J),
c3 colour reads 16–30 % raw cell error (F), no colour certificate. On
this engine only the K raster path (`ipp-urf`) carries payload: c2-K at
r0850 VERIFIED (D), c1-K not (E).
The probe page's title block overlapping panels 1/2 is a generator layout
bug (present in the gs preview), not the engine.

## 039.4 Scans — the e039 set on four engines (state 2026-10-10)

The same ten volumes were printed on the VersaLink (IPP: K via URF, colour
via PDF), the HP M681 (raw PS) and the <city> Canon (raw PS), and as
the twelve-page catch-all `e039-all-pages.ps` (plus the 1200×2400-request
discovery pair) on the office Xerox AltaLink C8245 (`lpr -o raw`,
2026-10-06, e042 §042.3; of the volumes, D and E scanned so far). What
each engine's print did when scanned and received:

| vol | format | VersaLink C7130 | HP M681 | Canon iR-ADV | AltaLink C8245 (e042, `lpr -o raw`) |
|---|---|---|---|---|---|
| A | c4-k-r0700@26x18 | not scanned | VERIFIED 122,892 B (`r`) | VERIFIED (`aa`) | printed, not scanned |
| B | c3-k-r0700@35x24 | not scanned | not scanned | VERIFIED 225,218 B (`ab`) | printed, not scanned |
| C | c2-k-r0700@53x37 | not scanned | VERIFIED 532,882 B (`s`, 2400) | VERIFIED (`ac`, 1200) | printed, not scanned |
| D | c2-k-r0850@53x37 | VERIFIED 657,042 B (`j`, 1200) | not scanned | VERIFIED (`ad` 1200 + `ad-2400`) | VERIFIED 657,042 B (`e041-altalink-d-2400`, one 2400 grey; sha == the emission) |
| E | c1-k-r0700@106x74 | 0 certs, 22 % raw (`i`, RGB + grey) | no placement (`t`, 4800) | 0 certs, 21 % raw (`v`) | 0 certs from one 2400 + four 4800 (158,000 cpu-s); 24.3 % raw at truth-fitted poses, no tile below 15 % |
| F | c3-cmy8-r0700@35x24 | 0 certs, C/M/Y 17/24/30 % raw, screened (`n`) | 0 certs, Y dead two thirds (`u`) | not scanned | printed, not scanned |
| G | c2-cmy8-r0700@53x37 | not scanned (screened route) | not scanned (Y dead) | **VERIFIED 1,598,326 B, 5,508/5,550 (`af-*`, six captures; e040 §040.4f)** | printed, not scanned |
| H | c2-cmy8-r0775@53x37 | not scanned | not scanned | **VERIFIED 1,785,886 B, 5,024/5,550 (`ah-*`, four 2400 + two 4800; e040 §040.4i)** | printed, not scanned |
| I | c2-cmy8-r0850@53x37 | not scanned | not scanned | NOT RECOVERED: 5 certificates, all C, from six 2400 + one 4800 over two receiver runs and a lean analyzer pass (0 of 268 keys); rung confirmed by truth; the maximal pass not run, by the owner's call 2026-10-05 (`ag-*`; e040 §040.4g) | **VERIFIED 1,973,446 B with the receiver alone, four 2400 captures (`e042-canon-i-6.10-2400-{a..d}`, 4,692 at the close); 5,878/5,883 after the analyzer (e042 addendum 2026-10-16/17)** |
| J | c1-cmy8-r0700@106x74 | mush, survey refused (`m`) | not scanned | not addressable from any plane (`ae`, 4800; e040 §040.4e) | printed, not scanned |

Black: every c2–c4 print on every engine that was scanned recovered
byte-exact; c1 recovered nowhere (four engines with a c1 payload sheet
after the AltaLink's E). Colour: only the Canon prints
unscreened with a healthy Y; the VersaLink screens every colour route and
the HP's Y is starved, so their unscanned colour sheets are not expected
to differ. On the Canon the c2 colour ladder is measured at three rungs:
r0700 closes with the receiver, r0775 only with the analyzer, r0850 not
at all on this channel — and the AltaLink closes the same r0850 bytes with
the receiver alone (e042 addendum 2026-10-16/17): the engine, not the rung. The Canon's F (c3-cmy8) is the one print left
unscanned.

Canon 4800 flatbed; K sheets grey, colour sheets RGB, no auto-crop /
sharpen / contrast; decimate-to-1600 doctrine does not apply to holo3
(declare the true dpi). Re-place the sheet between captures (multi-scan
law). Filename + sha256 per capture, as e033 §033.1.

## 039.5 Decode

`./confetti3.py decode --format <display id> …` — the display ids of
the table are the v2 identities (`SET.json` `spec_id` is the canonical
spelling). No `L:` fossil is needed: nothing here is a legacy row.
