# Office print bundle 2026-07-08 (AltaLink C8245, raw 9100)

Default run = 5 sheets, all K-only imagemask (=> NO MIC yellow dots, page
stays anonymous — measured 007.7/007.8):

| file | what | why now |
|---|---|---|
| e012.ps ×2 | layout_version 3 archive page (c3 K + p60b6.v3 pilots, random payload, NO furniture) | THE pilot-format hardware sheet (M-P3 office half) + print-to-print Δ on engine 2; sim gate PASSED, envelope pre-registered in experiments/012-pilot-print.md |
| e004.ps | finalists checkerboard (A3/A4/B1/B2 tiles) | 007.9 queued: different-day engine-2 variance — the last standing engine-2 characterization need |
| e006bw.ps | loop page BW (c2/B1 bands + strips) | 007.9 queued: engine-2 c2-class day variance (this is the honest c2 sheet — see README note) |
| e006c.ps | loop page color | 007.9 queued (home Y-starved sample comparison; office Y is healthy) |

PRINT: ./print_office.sh            (all five)
       ./print_office.sh e012.ps e012.ps      (just the two v3 sheets)

Bring ALL sheets home. Do NOT scan at the office (AltaLink scan path is
JPEG — erases <5-dot features, cannot carry pilot decode; 007.2).
Home scan protocol: 1200 dpi grey, descreen/sharpen/auto-contrast OFF,
3–4 RE-PLACED scans per sheet (004.0b), 90°-rotated placements welcome
(free with v3 pilots). Label sheets with print order + engine.

WHY NO c2 PILOT SHEET (the honest answer to "one at c3 and one at c2"):
a layout_version-3 c2 page does not exist, and building one tonight would
skip the sim-before-toner gate. More importantly it would be undecodable
by the current blind receiver: at c2's 11-14% hard BER the (100,23) t=13
words fail (~mean 12 errors), and the designed c2-class machinery
(ctx-detected pilot bits, p60b4 duplicated words) is spec'd but unbuilt.
e006bw covers engine-2 c2 channel measurement properly (strips + GT).
A gated v3-c2 sheet goes on the queue for the next office visit if wanted.
