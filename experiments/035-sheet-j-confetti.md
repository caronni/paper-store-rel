# e035 — Sheet J: a duplex CMY8 confetti volume recovered byte-exact (2026-09-01 → 09-03)

**Headline: one A4 sheet printed on both sides with a 1 MiB volume,
cut into hundreds of pieces on a paper cutter, scanned as loose
scraps in eight platen loads, and recovered byte-exact — twice, by
two independent holo3 runs on machine 2 (sha256 `fbbab289f7f94b25…`,
identical to the emission). The from-scratch run over all ten
captures certified 7,887 of 11,766 tile-streams (67.0%) against a
close requirement of 4,020 (34.2%): the fountain closed with a 1.96×
surplus while 20% of the tile-streams never reached the attempt
floor. Zero wrong certificates (codec-gated throughout).**

This is the first fragment volume, the first multi-page volume and
the first duplex sheet in the holo3 record, and the first colour
confetti on paper at all (e018's confetti was K-only on the home
engine). It is also the run that exposed the receiver's single-page
default and drove the PAGE-DOMAIN line (src/holo/receiver/docs/PAGE-DOMAIN.md).

## The object

| | |
|---|---|
| format | `c2-cmy8-r0547@53x37` (display spelling; A4-4mm paper bundle) |
| pages | 2 — page 0 on the front, page 1 on the back of ONE sheet (`volume/duplex.ps`) |
| tiles | 53 × 37 = 1,961 per page × 3 streams × 2 pages = 11,766 tile-streams |
| inner code | per-plane LDPC r0547 (k 2,240 → 2,087 user bits/stream after CRC and shortening) |
| fountain | pooled over C/M/Y (esi = counter·3 + stream), fountain-v2, one block, k_total 4,020, k_meta 1,340 |
| dial | q 0.686 → K/N 0.342 |
| payload | 1,048,576 B counting pattern, sha256 `fbbab289f7f94b25736c58be46a994c441fd02552cc6022352e3d86d2fab7c83` |
| density (e033 convention, full A4 area) | net **67.2 b/mm² per printed face** at this dial, 134.5 b/mm² per physical sheet; gross symbol capacity 196.9 b/mm² per face |
| emission | `scratch/c2-cmy8-r0547-q06860-1MiB/volume/` (manifest, page000/001.ps, duplex.ps, per-page GT) |

The dial is the point of the sheet: the close needs about a third of
the tile-streams, so losing scraps, cut edges and the faces a load
happens to hide is the expected operating condition, not a failure
mode.

## Print, cut, scan (operator record, Germano)

- **Print 2026-09-01**, Xerox AltaLink C8245, `lpr -o raw`, duplex
  PostScript, light white office paper (same stock as every other
  Xerox sheet). This is one of the first duplex prints in the whole
  project, and it is on thin-ish paper: the back face sits behind
  every front-face cell and show-through is a channel factor nobody
  has measured. Nothing in these runs isolates it — the 67% harvest
  and the 7.9% failures include whatever it costs. A single-sided
  print of the same volume on the same stock would price it.
  Printed TWICE: one sheet was cut, the other scanned whole. The whole-sheet scans (`…-full-2400-{a,b}.tiff`) are a
  SECOND physical sheet and were NOT part of any run here; under the
  018b rule they must never share a state with the confetti captures.
- **Cut**: manual paper-cutting machine; stripes, squares and
  triangles (see the capture panes in the run archive).
- **Scan**: Canon flatbed, RGB, scraps laid on the platen face-up as
  they fell. Eight loads at 2400 dpi; two of them rescanned at 4800
  dpi without touching the scraps. File numbers are NOT load numbers
  — the 4800 files pair with their 2400 loads by sha only:

| ordinal | file | dpi | sha12 | survey regions | accepted poses page 0 / page 1 |
|---|---|---|---|---|---|
| 0 | confetti-2400-1a | 2400 | 2e979b414ad5 | 82 | 233 / 190 |
| 1 | confetti-2400-2a | 2400 | 37ea845a7580 | 94 | 516 / 204 |
| 2 | confetti-2400-3a | 2400 | 07cd1055c755 | 107 | 497 / 420 |
| 3 | confetti-2400-4a | 2400 | 6606c3cf899c | 107 | 384 / 521 |
| 4 | confetti-2400-6a | 2400 | 21c59f22c30e | 12 | 36 / 247 |
| 5 | confetti-2400-7a | 2400 | 843ad2d8b0e2 | 12 | 237 / 36 |
| 6 | confetti-2400-8a | 2400 | e23a2def1224 | 55 | 458 / 141 |
| 7 | confetti-2400-9a | 2400 | 2f483c0b22b7 | 52 | 183 / 537 |
| 8 | confetti-4800-1 | 4800 | d38e76945c4c | 107 | 641 / 595 — **same platen as ordinal 2** |
| 9 | confetti-4800-5a | 4800 | c63e7620194a | 107 | 514 / 701 — **same platen as ordinal 3** |

Full sha256 of all twelve scan files: `scratch/sheetJ-20260902/scan-shas.txt`.

Two things the pose counts say on their own. Every load shows BOTH
faces — the scraps really did land face-up at random, which is why a
duplex sheet fills both pages from one-sided loads. And loads 6a and
7a are the same twelve scraps turned over: 6a is 247 poses on page 1
against 36 on page 0, 7a the mirror image, and 7a's placements use
only rotations 2 and 3 where 6a uses all four. (Inferred from the
event stream; operator confirmation owed.)

## The runs

Two independent recoveries, both on the tree
`1faa7a2` (holo3 as parked 2026-08-31; `tree` file in every run dir),
`--plane-fields --complete --workers 12`, diag on :8023.

**Chain A — laptop prefix, then a three-run resume chain on machine 2:**

| run | machine | captures | wall | cpu-s | certified (cum.) | close |
|---|---|---|---|---|---|---|
| `J-run.52093` | laptop, 6 w | 1 (1a), default pages | 34 min | 11,398 | 357 | open — **saw ONE page only** |
| `J-run.54028` | laptop, resume, `--pages 100` | same | 56 min | 19,471 | 657 (+300, page 1 found) | open |
| `J-run.56088` | laptop, +2a | — | aborted at launch | — | — | moved to machine 2 |
| `J-run.66853` | machine 2, from scratch, `--pages 2` | 1a 2a 3a | 1 h 50 | 74,231 | 2,530 (C 867 / M 872 / Y 791) | open |
| `J-run.68649` | machine 2, resume | + 4a, 4800-1, 4800-5a | 4 h 16 | 172,140 | 3,400 (+870) | open |
| `J-run.78759` | machine 2, resume | + 6a | 3 h 53 | 156,045 | **4,123 (+723)** | **VERIFIED** `fbbab289…` |

**Chain B — one from-scratch run over all ten captures on machine 2:**

| run | captures | wall | jobs | cpu-s | certified | close |
|---|---|---|---|---|---|---|
| `J-run-complete.81777` | all 10 | 9 h 15 | 327,453 | 378,920 | **7,887** (C 2,686 / M 2,713 / Y 2,488) | **VERIFIED** `fbbab289…` |

Wall times are file mtimes (argv written at launch, events at exit;
holo3 events carry no clocks). Both payload files
(`<volume>/J.out`, `J-complete.out`) hash to the emission.

The first laptop run is the page-domain incident: the receiver's
default domain was one page, so the scraps that carried page 1 were
addressed and discarded. Resuming with `--pages 100` recovered them
(+300) at the price of a 100-page tile map; `--pages 2` was used
from then on. The fix is the PAGE-DOMAIN line (live page domain,
selectors = live ∪ {0}), landed on main 2026-09-02, after these runs.

## The from-scratch harvest in detail

**Per page and plane (unique tile-streams):**

| | C | M | Y | tiles with ≥1 stream | tiles with all 3 |
|---|---|---|---|---|---|
| page 0 | 1,338 | 1,345 | 1,237 | 1,356 / 1,961 | 1,234 |
| page 1 | 1,348 | 1,368 | 1,251 | 1,379 / 1,961 | 1,246 |
| both | 2,686 | 2,713 | 2,488 | 2,735 / 3,922 (69.7%) | 2,480 (63.2%) |

Y trails C and M by about 7%, uniform across both faces — the
AltaLink Y plane at r0547 has margin (the dead-band pattern of sheets
H/I at r0850/r0700 does not appear; the Y field fit is refused as too
small to publish, median 0.22 dots on page 0, 0.08 on page 1).

**Tile-stream census at exit:** CERTIFIED 7,887 · ATTEMPTED (failed)
930 · FLOOR (below attempt floor) 2,031 · ADDRESSED (reachable, not
attempted) 579 · UNKNOWN (never addressed) 339. The 2,031 + 339 =
20.1% that never got an attempt are the cut edges and the faces no
load exposed; the 930 failures (7.9%) are the residue a per-plane
r0547 code could not carry on those scraps.

**Certificates by minting plugin:** tiles.scan 3,946 · tiles.retry
1,813 · tiles.union 1,125 · tiles.local 733 · tiles.planek 224 ·
tiles.swim 46. The union (14.3%) is the multi-load dividend: scraps
seen in two loads, or in a 2400/4800 pair, certify where one view
does not. The plane arm's 224 is its largest yield on any sheet to
date. CPU by plugin: tiles.local 161,340 (42.6%), tiles.swim 108,742
(28.7%) for 46 certificates, colour head + pooled context + fields
48,963, placement + colour refinement 26,664. TileOutcomes: 8,603
certified (716 re-certifications of already-certified streams),
219,972 failed attempts, 250,919 below-floor consults; BP iterations
median 19 on certified attempts.

**When the volume became recoverable.** In the event stream the
close count first reached k_total = 4,020 at line 199,494 of 905,626:
after 63,754 jobs and **8,692 cpu-s — 2.3% of the run's CPU**, about
twelve minutes of wall at twelve workers. Everything after that was
the `--complete` full harvest. On chain A the same crossing came
13,568 cpu-s into run 78759, on top of 3,400 replayed certificates.

**Placement.** 735 survey regions over ten captures, 72/72
calibrations adopted. 7,276 poses committed by placement (+6,872
refinements, +15 revisit): routes word 719 · chain 6,267 ·
correlation 305; median residual mismatch 0.075 cells. All four
rotations occur in every load (scraps land any way up); the address
word decoded at up to 13 site errors and never beyond, exactly the
BCH t=13 bound (error histogram 1–13, mode at 9). Window retirements
84,540, of which 180 by the done-covered gate; 9,043 stale skips;
11.98 M wakes; close consults 4.5 cpu-s in total.

**Fields.** C published on both pages (median 0.47 dots page 0, 0.56
page 1 — the AltaLink C-plane magnitude seen on sheets H/I again); M
refused (0.12 dots); Y refused (0.22 / 0.08). 64 lane-pages fitted;
fields minted no certificates directly, as on sheet I.

## What the confetti dial bought

- The close needs 34.2% of tile-streams; the sheet delivered 67.0%
  after a full harvest, and had already crossed the line at 2.3% of
  the CPU. The dial has roughly 2× margin on this cut — after the
  first three loads chain A stood at 2,530 (21.5%), after six
  captures at 3,400 (28.9%), and the seventh capture carried it over.
- 69.7% of physical tiles carry at least one certificate; the
  fragment-boundary yield e015 measured on 25.4 mm K fragments was
  f* ≈ 0.70–0.78. A duplex colour sheet cut on a paper cutter lands
  at the bottom of that range — the same boundary law.
- Chain A closed with 4,123 certificates from seven captures; chain B
  harvested 7,887 from ten. The three loads chain A never saw (7a,
  8a, 9a) are where its 65% UNKNOWN lived, not a receiver
  difference.
- The 4800 rescans of two loads are inside both chains. Because they
  entered together with new loads, this sheet gives no controlled
  4800-vs-2400 answer; the two same-platen pairs (ordinals 2/8 and
  3/9) are the material for one — a resume A/B on the archived facts,
  no new scan needed.

## Branch record — the page-field receiver on sheet J: VERIFIED a third time, MERGED 2026-09-12

Recorded from the run archive 2026-09-12. The work is branch
`page-field-receiver`, tree `pre-v1-v2-deletion-136-gd7eabd21` in all
four run `tree` files, merged to main 2026-09-12; nothing here promotes
anything. The receiver-line record with the full chain table, the costs
and the confounds is `src/holo/receiver/docs/PAGE-FIELD-PLAN.md` §5.2;
the bars it feeds are `docs/PAGE-FIELD-DESIGN.md` §6 B6 and B7; the
table is NOT reprinted here.

Four runs on machine 4 at 14 workers over the same ten captures as chain B,
`--complete`, the fossil identity `L:c2-cmy8-r0547@53x37`, the page field
unconditional (that branch deleted `--plane-fields`; these runs asked for
nothing, where chains A and B asked for the v1 fitter by name), with one
analyzer ladder folded in after the first: four 2400 captures to 3,402
certificates and no close (1 h 36); the analyzer's all-arms ladder +156
in 7 h 11 wall with controls and parity not run for this campaign; the
receiver resumed on those and minted ONE (28 min); capture 6a took the
count past K with five loads (20 min, interrupted, close deferred and
never solved); all ten closed **VERIFIED**, sha `fbbab289…`, **8,102**
certificates (C 2,738 / M 2,749 / Y 2,615; tiles with ≥ 1 stream 2,768
of 3,922, 70.6 %; all three 2,613, 66.6 %) in 3 h 17. So sheet J is
recovered byte-exact a third time, from the same paper and captures, on
a different tree and machine; `J-all-20260910.bin` re-hashes to the
emission.

**Read this beside chain B, not against it.** +215 over chain B's 7,887,
of which 156 are the analyzer's, so the receiver axis is AT MOST +59
(+0.75 %) and possibly less (the fold's 156 stood for every later arm) —
and the two differ five ways at once: a resume chain against one
from-scratch run, the analyzer's certificates on one side only, the
ctrl-C in the fourth run, 14 workers against 12, and the tree. **Machine 4
cpu-seconds are not this log's machine 2 and laptop seconds and are never
compared with them**; jobs are comparable in kind (436,771 across four
runs against 327,453 in one) but chaining inflates them. The chain was
never below K after its fourth run and `--complete` defers the close, so
it has no counterpart to this log's "K reached at 2.3 % of the CPU".

**What is new about the sheet, rather than about the branch.** The page
field published on ALL six page-planes at 82 % / 81 % support, where this
log's per-lane fitter published C alone and refused M (0.12 dots) and Y
(0.22 / 0.08); Y trails C and M by 11.7–12.4 points of the page there,
the same asymmetry the certificates show at ~7 %. No tile in any plane's
field support was measured on more than 7 of the ten captures (eight
platen loads; the 4800s are rescans of 3a's and 4a's). And the
address-word contradiction alarm (D1, landed after these chains; its
first firings were sheet H's two on 2026-09-06) fired for the first time
on fragment material, on the page rule, and more than once in a run: 16
lines over two physical conflicts, both one survey region holding two
scraps — the D1 note in
`src/holo/receiver/docs/retirement_docs-2026-09/RULINGS.md`. Nothing was
quarantined and the close is byte-exact.

**The analyzer on this residue.** 156 of 2,688 covered targets (5.8 %;
the residue was 69 % never-addressed or below the attempt floor), 145 /
9 / 2 / 0 by generation, every one single-witness; handed back, the
receiver certified one tile adjacent to no analyzer key. The lever on a
fragment sheet was a capture, not a battery. The analyzer's own record is
`analyzer/J-CONFETTI-2026-09-10.md`.

**Owed, unchanged.** The 4800 pair A/B: the two rescans entered the last
run together with 7a, 8a and 9a, exactly as in both chains above, so this
chain gives no controlled 4800-against-2400 answer either. A resumed run's
census counts only its own marks, so the chain has only an uncertified
total to set beside chain B's: 3,664 against 3,879.

## Standing rules check

Single sheet, single print day, one engine pairing, one cut:
existence evidence, **no ladder promotion, no population claim**.
Receiver status remains PROVISIONAL. Two independent closes with the
identical sha are the end-to-end truth anchor; every certificate is
codec-gated (syndrome + CRC-32). The tree is recorded (`tree` file,
holo3 writes it since the e034 provenance gap). `lpr -o raw` is not
the 9100 print path; as for e031/e032, nothing here promotes the
AltaLink footing.

## Artifacts

- `scratch/sheetJ-20260902/` — per run: `argv`, `tree`,
  `report.json`, all panes, `events.jsonl.xz` (machine 2 runs 66853 /
  68649 / 78759 / complete.81777; laptop 52093 / 54028; the aborted
  56088 argv+tree); `scan-shas.txt`.
- Primary run dirs incl. `facts.npz` resume seeds (57–211 MB) stay
  on <host> (`<volume>/J-run*`); payloads `J.out` and
  `J-complete.out` there, both verified.
- Scans: `scratch/xerox-canon-1.9-J-*.tiff` (12 files, 31 GB; also
  on <host>). Emission: `scratch/c2-cmy8-r0547-q06860-1MiB/`.
- Event-stream reductions for this log: session scratchpad
  (`events_pass.py`); every number above re-derives from the
  archived events + reports.

## Owed / open

- Operator confirmation: loads 6a/7a = the same twelve scraps
  flipped; whether 8a/9a were fresh scraps or re-placements; total
  scrap count.
- The whole-sheet control: decode the second physical sheet
  (`full-2400-a/b`) as its own volume — the intact-sheet yield at
  r0547 against this cut's 67%. Costed proposal, not started.
- The 4800 pair A/B on the archived facts (see above).
- The 930 failed tile-streams: no per-scrap or per-band analysis
  yet; the residue analyzer proposed for sheet H applies unchanged.

## Addendum 2026-10-11 — the whole sheet WAS decoded

The print section above says the whole-sheet scans
(`…-full-2400-{a,b}.tiff`, published in the holo release as
`035-sheet-j-confetti/J-copy2-whole`) were part of no run here, and the
owed list carries their decode as not started. The second physical sheet
was decoded, on machine 2 on 2026-09-03, from those two 2400 dpi captures
alone: run `J-run-full.89382`, tree 1faa7a2b
(`pre-gpt-5.6-cleanup-20260804-912-g1faa7a2b`), 12 workers,
`--plane-fields --complete --pages 2`. Close **VERIFIED**, sha256
`fbbab289f7f94b25736c58be46a994c441fd02552cc6022352e3d86d2fab7c83`
(== the confetti sheet's payload, the same emission), **11,545 of
11,766** tile-streams (C 3,871 / M 3,876 / Y 3,798). The run's `argv`,
`tree` and `report.json` are published under
`035-sheet-j-confetti/J-copy2-whole/records/runs/J-run-full.89382/`, its
ten panes under
`035-sheet-j-confetti/J-copy2-whole/figures/panes/J-run-full.89382/`; a
re-run on today's tree declares the confetti row's `L:` identity (the
release README carries the command). The rule stands: the whole-sheet
captures never share a run with the confetti captures (evidence line,
docs/EVIDENCE-ARCHIVE-2026-10-08.md §8a).
