# e036 — Sheet H read to 100%: the endrun chain and the wave that closed it (2026-09-06)

**Headline: 5,883 of 5,883 tile-streams certified on sheet H — the whole
physical page, the first sheet in this record read to 100% — close
VERIFIED byte-exact (2,220,921 bytes, sha256 `0ad329fb796dfc83…`,
identical to the e033 emission) on every closing run of the chain, and
once more by a receiver run that had nothing left to certify. C, M and
Y each 1,961/1,961.** Zero wrong certificates anywhere: every closing
run stands on the envelope sha, and every analyzer run that was scored
offline against the emission read zero wrong.

Sheet H is the e033 print (2026-08-18): Xerox AltaLink C8245,
`L:c2-cmy8-r0850-p120-x1@3392x2368` (fossil id; 53 tile rows × 37 tile
columns = 1,961 tiles × 3 streams = 5,883 tile-streams; k_total 5,277),
4 mm margins, q 0.9, **284.9 b/mm² net field — holo3's `max` capacity
byte for byte, the highest-density volume in this record** (sheet I,
e034, is the same geometry at r0700, 230.7 b/mm²). The r0850 rung had
never closed on paper; e033 predicted "wider dead bands, lower
threshold" for it, and that is what the endrun met.

This log is the campaign record for the last thousand tile-streams. It
is also the record of a second reader: the analyzer (`analyzer/`,
DESIGN v0.4), which took the sheet from the receiver's stall at 4,883 to
5,883 by minting certificates the receiver could not, folding them into
the receiver's own fact snapshots, and handing the sheet back. The
receiver's side of the story is the resume chain; the analyzer's is
`analyzer/W8-2026-09-06.md` (the wave in one page),
`analyzer/APPROACHES-2026-09-06.md` (its full trial record) and
`analyzer/MEASUREMENTS-2026-09-06-C-THIRD-LAYER.md` (the measurement
that located the loss). Machine: machine 4 (128 GB); 14 workers throughout,
except the final replay run (92223), which ran at 3.

## The captures

Canon 4800-class flatbed, RGB, thirteen captures of the one sheet.
Seven of 2026-08-18: two at 1200 dpi (`af580c3cf54f`, `d792e00a45e7`),
two at 2400 (`68c16fcbf29b`, `4fddac74cef1`), three at 4800
(`f6920518c82a`, `9c022bd308ae`, `f642cab0416c`). Six CROSSWISE of
2026-09-03/04, the sheet turned on the platen, two placements each
("top", "bot"): 2400 `1d5da05353b8` (top) and `b43feeeb615c` (bot);
4800 `20580e8e7a00`, `c047efeba3f7` (top) and `68bd6de3801e`,
`45e375e7b0ad` (bot). The crosswise six were added when the seven-capture
endrun stalled; they are the ones the multi-scan law asks for (re-placed
between scans, errors de-correlated), and the analyzer's per-lane
detectors read each of them as its own lane.

## The chain

Every count below is a receiver `report.json` or an `export-facts`
manifest; the analyzer's counts are its ledgers, all but one scored by
`analyzer score` against the emission. Walls are contended walls and are
given for scale only; the receiver's events carry no clocks by law.

| date | run | captures | certified | close |
|---|---|---|---|---|
| 09-01 | `holo3-H4-run` | 4 | 4,691 (C 1734 / M 1944 / Y 1013) | open |
| 09-02 | `holo3-H5-run.39768` | 5 | 4,809 | open |
| 09-02 | `holo3-H7-run.53468` | 7 | **4,883** — the endrun's stall, 394 short of K | open |
| 09-03 | analyzer passes H7-pass1/2 → `facts` (the first fold) | 7 | +232 over the stall → **5,115** | open |
| 09-03/04 | analyzer passes H7-pass3…5 (folded as facts-2…4, each over the 4,883 stall) | 7 | +508, +514, +554 → union 5,437 | **the union closed byte-exact at 5,391 on 2026-09-04 02:29** (pass 3; the analyzer's own close) |
| 09-04 | `holo3-Hanalyze1-run.84978` (production on the first fold) | 7 | 5,115 → 5,119 | open |
| 09-04 | facts-5 (5,119 + 318 from the ledgers = 5,437) → `holo3-H-with-facts-5-run.99413` | **13** (the crosswise six join) | 5,454 | deferred (`--complete`) |
| 09-05 | analyzer H13-pass1 (+118: C 12 / M 1 / Y 105) → facts-6 5,572 | 13 | close VERIFIED by the analyzer, 295 redundant symbols, 0 inconsistent | — |
| 09-05 | `holo3-H-with-facts-6-run.16986` | 13 | 5,574 | deferred |
| 09-06 00:25 | analyzer H14-pass1 (+5) → facts-7 5,579 | 13 | 302 redundant, 0 inconsistent | — |
| 09-06 10:05 | `holo3-H-with-facts-7-run.32018` | 13 | 5,580 | **VERIFIED — production's first verified close of sheet H** |
| 09-06 | analyzer H15-pass1 (main, `everything+field2`, 67 min) +1; W8 isolation pass I6 (patch + L3f) +102 → new-analyzer-facts-1 5,683 | 13 | 406 redundant, 0 inconsistent | — |
| 09-06 | analyzer H16-pass1 (`everything+patch --fixed-point`, two generations, 177 then 23) **+200 → 5,883** → new-analyzer-facts-2 | 13 | 606 redundant, 0 inconsistent; 200 checked, 0 wrong | — |
| 09-06 23:38 | `holo3-H-with-facts-8-run.92223` | 13 | 5,883 replayed, 0 minted | **VERIFIED**, 5,883/5,277 |

The folds are not additive: `facts`…facts-4 are successive unions over
the same 4,883 base, and facts-5 re-folds that union onto 5,119. What the
snapshots actually gained is 232 + 318 + 118 + 5 + 103 + 200 = 976,
plus the receiver's own 24 after the stall (4 + 17 + 2 + 1) = the 1,000.

Per stream at the end: C 1,961, M 1,961, Y 1,961. The M plane was
complete first (as on sheet I); C's dead band (tile columns 30–31) and
Y's bands were the last to fall, in W8's fixed-point pass.

## The 09-01 run in flight — a cost snapshot

The `holo3-H4-run` row above records only the run's final count. One
live readout of its diag pane survives, taken 2026-08-31 about twelve
hours in (14 workers, `--complete`,
`L:c2-cmy8-r0850-p120-x1@3392x2368`), written into a founding note that
day and carried here 2026-09-13 when that note was retired: jobs
407,713, cpu 557,426 s (~155 h), certificates 4,690 (C 1,733 / M 1,944 /
Y 1,013), close deferred at 4,690 of 5,277 symbols, placement done at
3,838 poses. Per plugin:

| plugin | cpu-s / cert | certs | queued at the snapshot |
|---|---:|---:|---:|
| tiles.scan | 4 | 1,286 | 0 |
| tiles.union | 5 | 687 | 0 |
| tiles.retry | 8 | 2,163 | 0 |
| tiles.planek | 97 | 264 | 3,598, not running |
| tiles.local | 1,330 | 267 | 1,789, holding 13 of 14 workers |
| tiles.swim | 5,488 | 23 | 3,582, not running |

The cheap core had finished. The literal price put `tiles.local` (220)
ahead of planek and swim, so the pool sat on local's 14-second jobs at
1,330 cpu-s per certificate while 3,598 planek jobs, priced at 97 cpu-s
per certificate, waited — the profile OPEN-2026-08-31 records at 73 %
of machine 2 run's CPU for 213 certificates — the same pattern, twelve
hours in instead of one machine 2 run. Literal
prices with no feedback from measured cost is the mechanism; the
candidate answers are recorded beside that watch item in
`src/holo/receiver/docs/conversion_docs/OPEN-2026-08-31.md`, priced by
nobody yet. This log carries no other per-certificate price for planek
or swim on this sheet (sheet I's, at r0700, are in e034: planek 8.1
cpu-s per certificate, local about 3,000): one readout of one run, a
snapshot and not a measurement campaign.

## What closed it

The receiver's mechanisms carried the sheet to 4,883 and, with the
analyzer's certificates folded back in, to 5,580 and a verified close.
The analyzer's two campaigns minted 677 and 303; the last 303 took 5,580
to the whole page:

- **W1–W7 (09-03/06)**: the analyzer as built — arms × rules × rungs on a
  blind fixed point over the receiver's own snapshot, the certificate
  cascade re-labelling neighbours' halos generation by generation —
  minted 554 over the stall, 118 more on the crosswise captures
  (H13-pass1) and 5 in H14-pass1: **677 before W8**.
- **W8 (09-06)**: the measurement that located the remaining loss — a C
  cell whose siblings M and Y are both inked reads two to four times
  worse than any other C cell, sheet-wide, and the third-layer C toner
  has no dot core, a flat red deficit at about 60% of a normal dot's
  strength — and the mechanism that read it: a linear discriminant over
  the raw pose-resampled patch, per lane, plane and sibling state,
  trained on the certified neighbours. On the 153 open C tile-streams of
  the 09-06 base the default arm alone certified 0, the patch arm alone
  96 in 1,276 CPU s, the patch battery 127 (X1, a BLIND count — the one
  W8 row with no verification score; X3's scored variant certified the
  same 127 at 0 wrong); the fixed-point pass over the whole 200-tile
  residue certified all 200, Y included, and closed. The
  wave, its cost and its rulings: `analyzer/W8-2026-09-06.md`.

Verification stood on three legs: the close's own envelope sha
(truth-free, production's only check); the fountain consistency check on
every fold from facts-6 on (the union over-determined by 295 → 606
redundant symbols, never one inconsistent) — the five folds before the
2026-09-04 separation ruling carried no consistency record at all, being
gated the other way, by `export-facts`' gate 1 against the emission
(232/508/514/554/318 checked, 0 mismatches), which is the check that
ruling removed; and the offline scorer against the emission, run on
every analyzer ledger that entered the snapshots except H15-pass1's
single certificate, which stands on its close's envelope sha and the
consistency check — zero wrong certificates in every scored run.

## The last receiver run — a finished sheet's idle cost

`holo3-H-with-facts-8-run.92223` resumed from new-analyzer-facts-2 with
every tile-stream already certified, under `--complete` and at 3
workers, and closed VERIFIED with nothing to add. What it did on the way
is the measurement the done-geometry design (docs/DONE-GEOMETRY.md) has
been waiting for: 61,441 events; 35,618 windows scheduled and 18,256
retired (12,092 "placed", 6,164 "done_covered" — `EngineStat.retired`
reads 30,405 because it counts retirements across all seventeen plugin
rows, while the cause tally and the `WindowRetired` events are place's
alone); 3,774 jobs done; 1,364,582 wakes; 13,901 stale skips; 44
calibrations adopted. Those scheduling counts are worker-sensitive and
these are the 3-worker run's. And **one placement contradiction**: on
the crosswise 2400 capture `1d5da05353b8`, a word-decoded window and a
chain-placed window agreed on tile (10,35) at rot 3 and disagreed by
exactly one cell along page x at their overlap (`-0.00,-1.01`, just over
D1's whole-cell bar); the alarm named it, quarantined nothing, and the
payload was unaffected. The D1 alarm's first firing on paper was run
32018's, earlier the same day; the specimen is deterministic and
reappeared here, and it is the regression case for whatever carries a
chain-transported window a whole cell across a rot-3 pose — that
mechanism is not measured. With every tile certified, all of that
placing was work that could mint nothing — the size of the gate that
never posing a window over done pixels would save.

## Standing rules check

Single sheet, single print day, one engine pairing: existence and
regression evidence, **no ladder promotion, no population claim** —
CLAUDE.md's rule, and the analyzer's own (nothing learned on this sheet
is stored; every filter and map is fitted at run time from the sheet's
own certificates and thrown away). Receiver status remains PROVISIONAL.
The rate ladders are set on multi-sheet minima; one sheet at 284.9 b/mm²
is a point, not a rung.

## Artifacts

- Receiver run dirs `scratch/holo3-H4-run` … `scratch/holo3-H-with-facts-8-run.92223`
  (per-run `argv`, `report.json`, `events.jsonl`, panes); the fact
  snapshots `scratch/holo3-H-analyzer-facts{,-2…-5}/facts.npz`,
  `scratch/holo3-H-analyzer-facts-{6,7}.npz` and
  `scratch/holo3-H-new-analyzer-facts-{1,2}.npz` with their manifests;
  payload `scratch/holo3-Hwith-facts-8.bin` verified.
- Analyzer ledgers, scores and closes under `scratch/analyzer/`
  (H13-pass1, H14-pass1, H15-pass1, H16-pass1, `W8/`, the union bases
  H14-union / H15-union); the emission regenerated from the fossil at
  `scratch/xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm` (manifest sha ==
  the recovered payload).
- The thirteen captures `scratch/xerox-canon-18.8-H-*.tiff`.

## Addendum 2026-10-09 — full capture hashes

The thirteen captures under the 12-hex prefixes used above, full sha256 from the raw-hash pass of 2026-10-09 (sha256 over the retained evidence)
(`scratch/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-<suffix>.tiff`):

| prefix | suffix | sha256 |
|---|---|---|
| `af580c3cf54f` | `1200dpi-a` | `af580c3cf54f26488ef0a8dc956bf7222fa3195b4a1bc99c316e0d68646d963c` |
| `d792e00a45e7` | `1200dpi-b` | `d792e00a45e77cbf8da102db64397b5271fb605b0a4976dd6866f5ba3069f3fb` |
| `68c16fcbf29b` | `2400dpi-a` | `68c16fcbf29b23d72765dbaaf96c88c8df162b90640b392f25bcd1d03f3b0ed9` |
| `4fddac74cef1` | `2400dpi-b` | `4fddac74cef1f0152d7ff1a066c9e13835bda51af1f5faaff02d6e2a707d16be` |
| `f6920518c82a` | `4800dpi-a` | `f6920518c82a2ea2d50e438259ee7caf31bdc34eaae2547cc4227b5e97c85680` |
| `9c022bd308ae` | `4800dpi-b` | `9c022bd308aea90a09ff772c3f35f9c2ca873b7815cbb313924d1cdb8be8901f` |
| `f642cab0416c` | `4800dpi-c` | `f642cab0416ccd8186fc2180c4ec3dcea0a38c45c7325ebf4feccc4cb9da4e6d` |
| `1d5da05353b8` | `2400dpi-quer-top-a` | `1d5da05353b891817b63423c235adcebb15da69ac0b99885a032996fa5f359bb` |
| `b43feeeb615c` | `2400dpi-quer-bot-a` | `b43feeeb615c2e8bdbe621722c064a1bdddae70bed9b51446e92baa078d6b706` |
| `20580e8e7a00` | `4800dpi-quer-top-a` | `20580e8e7a00845ab16de5256978f731e2c7329f7403f820c2698f066897dc24` |
| `c047efeba3f7` | `4800dpi-quer-top-b` | `c047efeba3f73ac6fb45ae0901d9288e5157bf57692a609a679322ef420c93ac` |
| `68bd6de3801e` | `4800dpi-quer-bot-a` | `68bd6de3801e5e7d40ee316d3329881bd75d9f25308915d71d624bd768d021c2` |
| `45e375e7b0ad` | `4800dpi-quer-bot-b` | `45e375e7b0ad0d0e11ddacb1f11b7e113d524990954c789e94f343ddb095c67c` |
