# paper-store: the record

What has been printed, scanned and read back, byte-exact or not, one row per sheet,
with the failures. The numbers on the front page come from here; the experiment logs
the rows cite are the primary record. Setup and usage are in `HOWTO.md`.

## What the record shows

Each row is one sheet, decoded byte-exact unless marked. Densities are net payload bits over
the full A4 area, as the logs compute them. Rows marked * have no scans or jobs in an
evidence release yet.

| Engine | Format | Payload | Result | Log |
|---|---|---:|---|---|
| HP Color LaserJet Pro M281fdw | c2 K, r0700 | 465,580 B | VERIFIED, one 4800 dpi scan; first holo-format print | `experiments/029-holo-v1-first-print.md` |
| Canon imageRUNNER ADVANCE | c4, c3, c2 K (e039 A to D) | 122,892 to 657,042 B | four sheets VERIFIED | `experiments/040-canon-iradv.md` |
| HP Color LaserJet MFP M681 | c4 and c2 K (e039 A, C) | 122,892 B, 532,882 B | VERIFIED, one scan each (1200 and 2400 dpi) | `experiments/039-xerox-versalink-candidate-set.md` |
| Xerox VersaLink C7130 | c2 K, r0850 (e039 D) | 657,042 B | VERIFIED, one 1200 dpi scan | `experiments/039-xerox-versalink-candidate-set.md` |
| Xerox AltaLink C8245 | c2 cmy8 | 718,413 B | VERIFIED; first CMY8 volume read from paper | `experiments/032-xerox-altalink-payload-volumes.md` |
| Xerox AltaLink C8245 | c2 cmy8 r0700 (e033 sheet I) | 1,798,761 B | VERIFIED by the receiver alone from one 2400 dpi scan; 5,883 of 5,883 tile-streams with the analyzer; 230.7 b/mm2 | `src/holo/receiver/docs/LIFECYCLE-MEASURED-2026-09-21.md` (receiver alone), `experiments/037-sheet-i-single-capture.md` (every tile-stream) |
| Xerox AltaLink C8245 | c2 cmy8 r0850 (e033 sheet H) | 2,220,921 B | 5,883 of 5,883, receiver plus analyzer; 284.9 b/mm2, the densest in the record | `experiments/036-sheet-h-full-readout.md` |
| Xerox AltaLink C8245 | c2 cmy8, a different rung per plane | 1,782,790 B | receiver alone closed * | `experiments/046-altalink-cmy8-three-width.md` |
| Canon imageRUNNER ADVANCE | c2 cmy8 r0700, r0775 (e039 G, H) | 1,598,326 B, 1,785,886 B | VERIFIED, receiver plus analyzer, six captures each; r0850 (e039 I) NOT RECOVERED | `experiments/040-canon-iradv.md` |
| HP M281fdw (fresh toner) | c3 and c2 `cmy` (single toner per cell) | 558,886 B, 1,123,545 B | VERIFIED, one 2400 dpi scan each (PROVISIONAL) * | `experiments/044-m281-cmy-first-print.md` |
| Xerox AltaLink C8245 | c2 cmy8 r0547, duplex, cut up | 1,048,576 B | VERIFIED from scraps, see below | `experiments/035-sheet-j-confetti.md` |

What the rows rest on, and what failed:

- Experiment 033's sheet H closed byte-exact from seven scans with the analyzer; the full
  5,883 of 5,883 used 13 scans, from the receiver's stall at 4,883
  (`experiments/036-sheet-h-full-readout.md`). Its sheet I closed with the receiver alone from
  one 2400 dpi scan in 2,005 s at twelve workers
  (`src/holo/receiver/docs/LIFECYCLE-MEASURED-2026-09-21.md`), and reached 5,883 of 5,883 from
  that scan with the analyzer, 0 of 1,046 analyzer certificates scoring wrong
  (`experiments/037-sheet-i-single-capture.md`).
- On the Canon both colour closes (e039 G and H) needed the analyzer and six captures each;
  the r0850 sheet (e039 I) was NOT RECOVERED (e040 sections 040.4f, 040.4g, 040.4i). The
  same r0850 bytes printed on the AltaLink closed with the receiver alone
  (`experiments/042-altalink-cell-encodings.md`, addendum 2026-10-16/17; not yet released).
- Pitch `c1` (one dot per cell) recovered on no engine (`experiments/039-xerox-versalink-candidate-set.md`);
  `c2-cmy7` failed on the AltaLink (`experiments/032-xerox-altalink-payload-volumes.md`).
- The M281 re-screens overlapping toners, so a `c3-cmy8` sheet on it was NOT RECOVERED
  (`experiments/038-sheet-f-m281-fresh-toner.md`, `experiments/041-m281-screen-routes.md`,
  `docs/M281-COLOUR-2026-10-05.md`); the single-toner `cmy` family avoids overlaps. The
  weak-yellow ruling voids its colour results of experiments 017, 028 and 030 to 032.

**Fragment recovery.** Sheet J held a 1 MiB volume on both faces of one A4 sheet, cut into
hundreds of pieces on a paper cutter. From the loose scraps, scanned in eight platen loads,
two independent receiver runs recovered the file byte-exact; the from-scratch run over all
ten captures certified 7,887 of 11,766 tile-streams against 4,020 needed, zero wrong
certificates (`experiments/035-sheet-j-confetti.md`). A strip narrower than one tile can
never address itself. The fragment-size ladder of the earlier paperholo pilots (about 15 mm
and up self-addresses at `c3`, measured in simulation; below about 3 mm no fragment can be
located on the page) is in `docs/PILOTS-DESIGN.md`; the shred-grade sweep is open.

**The deep-time bootstrap.** `bootstrap/` designs the front leaves of a volume so that a
finder with only the paper and a general-purpose computer able to run a small Python
program can rebuild the reader: a 28-line program typed by hand, a typed data sheet, pages
of large printed marks (R2 pages) read from phone photos, then the archive pages from
flatbed scans (`bootstrap/README.md`). On 2026-10-26 the chain closed once on one HP M281
print, the R2 pages read from 300 dpi grey scans and the archive from eight 600 dpi scans;
the 321 files unpacked from the archive pages do not yet run on their own
(`bootstrap/PAPER-2026-10-26.md`). The phone-photo route closed stages 1 to 3 on 2026-10-20
(`experiments/047-bootstrap-typed-rung-first-paper-close.md`). Neither run is released yet.
