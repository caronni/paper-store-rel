# TODO

Possible work, one line each, with where it was found. Not ruled, not
prioritised. Detail lives at the pointer.

## Analyzer

- The fixed point's re-target (`fixedpoint._retarget`) could include a
  neighbour's certificate in another stream. Found on e042 sheet I
  (`experiments/042-altalink-cell-encodings.md`, addendum 2026-10-16/17).
- The generation-tick test in `analyzer/tests/test_analyzer_progress.py`
  races the driver's progress counter under load (`git show
  dbafcaad^:CLAUDE.md`, Suite, KNOWN FLAKE 2026-09-20).
- `--ctx-mode local5|page` with any patch-family arm crashes a worker
  (UnmixError) instead of refusing — a CLI guard (e040 §040.4f, §040.5).

## Receiver (holo3)

- `PavaMap.llrs` interpolates probability linearly between PAVA nodes;
  logit interpolation recovers 0.02–0.12 bit (`git show
  dbafcaad^:CLAUDE.md`, holo3 bullet, OWED 2026-10-10; `measure/cmy_calibration/RESULTS-2026-10-10.md`).
- The cross-capture sum of stored scores is overconfident on two
  captures of one sheet (same source).
- After a support refusal an armed parent latches once its children are
  minted; a later better lattice seed cannot revive it until the
  afterlife — base's behaviour, or lift the latch on a new seed?
  (`src/holo/receiver/docs/SCHED-LIFECYCLE-REVIEW-2026-10-17.md` §7, R1).
- `pose_refused` on a RING pass may keep RING ahead of an armed SUBDIVIDE
  on every wake, the same shape as D1 of that review — unprobed (§7).
- `cached_decode` refuses a traced run dir only at publication, after
  the decode; a pre-run refusal is stricter than needed (§7, R4).
- `measure/donegeo_realstate.py` has no test; its first run on a real
  post-2026-09-21 journal should check `WorkerRetired.cause` (§7, R6a).
- The residue rows' order and escalation per encoding: local's re-fires
  are the dearest minting work on every colour sheet while planek (cmy8)
  and swim (cmy) first fires are the cheapest and run last; the retry
  pays on cmy8 and confetti, not on cmy; resumes re-walk the residue for
  nothing (`measure/sched_trace/YIELD-OVER-CPU-2026-10-18.md`; the
  isolation arms need the LADDER §7.2 hatches). The price balance BUILT
  on it is `src/holo/receiver/docs/PRICE-BALANCE-2026-10-18.md`; owed:
  its paper A/B (the note's §5), the resume re-walk (ruling 13), a sixth
  ladder level's retry at 251 (the note's §4).
- A per-codec pricing table: the residue band's, the retry's and the
  field cadence's literals per family (K, cmy, cmy8; cmy7-by-erasure
  inherits cmy8 until measured), the backbone family-invariant, one
  ladder printed and pinned per family, plus a confetti column (J:
  the retry's first fires pay, the swim's later fires do not) picked by
  an explicit flag or a derived default. The cmy retry at 241 is the
  embryo (`tiles_sched._retry_cost` reads the family); each column set
  on multi-sheet minima with its provenance named — today codec and
  engine are confounded (cmy8 = AltaLink, cmy = M281). Yield-fed prices
  that MOVE within a run were examined 2026-10-18 and not pursued: the
  measured yield variation is per encoding and per fire ordinal, a
  falling price needs a wake (PRICING-ESCALATION F7), and thread time
  cannot feed a deterministic price.
- Need-sorting at the close: among EQUAL-priced seats pop the tile whose
  fountain block or column group is furthest below need — a rank
  between price and arrival sequence, never a price (above-need
  certificates feed the field, the context and the refit). Early in a
  run every block is below need and the ranks tie; near the close it
  focuses. Needs the per-block / per-group shortness as a store cell
  the certificate fold writes (today in the close's diag status), read
  in coarse bands. Evidence: e046 M1 (count reached at 53 % of the CPU,
  groups never ready), e044 M2 (all 19 groups open at the symbol count,
  close 17 certificates later). Changes time-to-close, not the
  `--complete` outcome.
- The page field's re-collect cadence: what the right trigger is
  (held 2026-10-18; today 180 × its fire ordinal, which with the
  escalating residue rows now interleaves with their re-fires; the
  candidate is the stale-tile count per plane — `PRICE-BALANCE-2026-10-18.md`
  §2, the census note §6).

- Page-edge `cold_rest` windows hold the harvest's tail: on the 600 dpi
  pixma scans of the bootstrap archive pages (c3-k-r0547, d-01..d-09) 152
  queued placements, every window on a page edge ((960,0,1160,200),
  (0,0,200,200), …), no tiles inside but ink counted as support (the
  platen's edge shadow along the top, the stage-4 header strip down the
  left) that the done-geometry gate cannot retire; ~2 s each. The archived
  holo3 of 2115a595 with `--complete --diag 8023`, stopped before the close
  (`bootstrap/PAPER-2026-10-26.md`; scans in the main checkout's
  scratch/typed3/).

## Experiments

- e046's log lists print, scan and decode as owed while
  `scratch2/e046/M1..M3` and `A1..A5` exist on machine 1 with M1 VERIFIED
  (`f8c0be63…`, two captures, 5,165 certificates at exhaustion) — the
  §046.1 rows are owed.

## LDPC ladder v2 (`ladder2/`, docs/LDPC-LADDER-V2.md; branch `ldpc-ladder-v2`)

- The planner's acceptance bar (union bound at Shannon + 0.8 dB) admits
  codes at the 1e-4 undetected edge by construction: the S4 refusals sit
  at 11–54 per 10⁵ at the 1 % point. A margin (Shannon + 0.5 dB, or the
  bar one weight up) or a bar on the post-CRC rate is §9 R3's call
  (design §4.3, §9 R3). Its constant 10.8 is 10.87 rounded down (one
  weight short at r0547/r0469) and assumes 64 words at Z 32 too; the
  lifter's gate knob (16) sits below the bar from r0469 down — make it
  max(gate bar, acceptance bar) (design §3.3, 2026-10-19 review).
- BUILT 2026-10-19 behind CampaignConfig flags, off for c1-rank /
  c2-accept and on for c3-search (design §8.1 Wave A; the Opus refuter's
  dispositions in §3.4): the S2 operating-region rate rule with a Poisson
  tail test at few trials, distinct-trial S3 counts recorded (the rate
  stays point-trial, refuter M3), Z in the S1 key, all-duplicate
  candidates dead for backfill, S4 walking down the ranking, the
  lifter's gate raised above the acceptance bar and extended to
  three-bit words (`lift_bar_margin`, `lift_gate_triples`). Still open
  here: the lifter's gate knob is below the acceptance bar whenever the
  levers are off (the margin lever is the fix, c1/c2 ran without it).
- `_apply_accept_bar` and the acceptance verdict never check that the
  digests are present (§4 item 1 says they are); latent.
- DONE 2026-10-20: the leaderboard ranking `v2` breaks ties within
  0.02 dB by the floor (fewer S4 undetected decodes) and no longer ranks
  on decode cost, whose v1 comparison used iterations measured at
  different Es/N0 grid points (the SET-1 review; design §1.2). SET-1
  stays on `v1`; SET-2 (the v2 picks) is the owner's call. Open: a cost
  comparison at a COMMON Es/N0 if cost should ever rank again, and the
  ranking statistic itself — the S3 1 % point carries the winner's
  curse at ~0.02 dB, an S4-corrected point would rank more honestly.
- `s2_keep` (4 + best per family) does not scale with the candidate
  pool: in c3-search (24 candidates, six seeds) c2-accept's accepted
  r0547 code fell out of the S2 picks before S3, and the S4 backfill
  then walked r0547 down to an F2 0.35 dB slower — scale the keep with
  the pool (8 at 24 candidates) and cap the backfill at, say, 0.1 dB
  behind the rung's fastest refused code (design §8.1, c3-search).
  BUILT 2026-10-20, off by default, no campaign sets them yet:
  `s2_keep_frac` (keep ≥ ceil(frac × the S2 pool), the pool being one
  best seed per candidate; 1/3 keeps that code, which sits at S2 rank
  18 of 52, and every SET-1 code in c3's pools, at 271 more S3 picks,
  ~40 M decodes), `s2_keep_within_db` (keep every code within that
  many dB of the best S2 es1; 0.031 keeps it at 56 more picks, ~8 M,
  but misses the SET-1 codes 0.05–0.47 dB behind) and
  `s4_backfill_max_db` (the walk skips every code more than that
  behind the ranking's best S3 1 % point and walks on in rank order —
  rank_s3 is not monotone in s3_es1 — and a rung whose within-cap walk
  is all refused alarms on the cap; at 0.1, c3's r0547 skips the F2
  0.39 dB behind).
  Tests: `ladder2/tests/test_l2_campaign_keep.py`.
- The planner's acceptance judges single and pair minima only; a
  recorded `triple_min` below the bar refuses nothing before S4 (by
  design; refuter L1).
- Small z (BUILT 2026-10-19, `ladder2/lib/peg_repair.py`,
  `families_cap.py`; `ladder2/docs/SMALL-Z-2026-10-19.md`) and the span
  rule (BUILT, `families_span.py`; `ladder2/docs/LAST-ROWS-2026-10-19.md`):
  k 3520's floor is reachable (z 32 span 3), k 3712's costs 0.07–0.11 dB
  for pair/triple ≥ 10 on every code. The CROWDING check is BUILT
  (2026-10-20): `ladder2/lib/floors_words.py` finds every
  codeword of ≤ t_max light-column information bits under a weight
  (exhaustive on the accumulator; recall and the union-bound floor
  against S4 in `measure/ladder2-floor-words/README.md`) and the lift
  gate `gate_words` / `word_bar` (CampaignConfig.lift_gate_words,
  word_bar_for) re-places against it. c6-low and c7-top (2026-10-23/24)
  lifted every rung with it: at the top four rungs no waterfall gain
  beyond the tie window (the finite-length price binds there), two
  picks moved on the pooled floor; PBRL at z 32 with the gate (c8-low,
  2026-10-24) took r0250 / r0203 at the floor bar's edge and lost
  everywhere above — the bottom rungs' lever is now a FLOOR lever for
  z 32 PBRL, and R3's ruling on the bar.
- F5, the ARA precode family, is BUILT and measured (branch `l2-ara`,
  `ladder2/lib/families_ara.py`, `ladder2/docs/ARA-2026-10-20.md`): not
  a floor lever (the accumulator maps u_j + u_{j+1} to one state flip;
  r0625 +0.04–1.0 dB, r0859 +0.27 dB and up, r0406's waterfall-tied
  full ARA at 3–6× the F3 reference's undetected share). Owed if wanted:
  S4 on the one clean F5 code (r0406 f 0.5 light, +0.086 dB, 0 of
  30,000); the lifter's distinct-shift mask and weight gate for
  punctured state columns (`peg.py`: 21 of 48 F5 lifts kept a repeated
  state shift); a precoder whose lightest input is not weight 2.
- Full density evolution is BUILT (`ladder2/lib/de_full.py`, 2026-10-19)
  and equals PEXIT within 0.02 dB where no DE floor binds; a DE-driven
  profile optimiser is parked until a compiled box-plus kernel brings a
  threshold under ~10 s (now ~150 cpu-s at 2¹¹ points; design §3.2).
- FUTURE (the owner stopped the search 2026-10-24 with SET-1 as
  published): the external cross-check — one 5G NR base graph (BG2, and
  BG1 at the top rates) lifted to n ≈ 4096 at three shared rates and
  measured on this harness under the production decoder, as the
  literature reference beside the ladder (ladder2/docs/LITERATURE.md).
  It improves no rung; it says whether any known construction does
  better at this length and decoder, where the ladder sits
  0.40–0.66 dB above the finite-length bound at every rung and the
  bottom four are floor-bound. A few hours; the one measurement that
  would close the search question for the record.
- `ladder2/lib/campaign_plan.py` is 1,090 lines after the 2026-10-20
  planner and gate plumbing: split it along the S3/S4 acceptance seam.
- `ladder2/lib/mc.py` records the undetected words' weights but not the
  words: a few stored words per code would let the CRC cover be checked
  per word rather than per weight class (design §3.7).
- F2 WEIGHT RULE (BUILT 2026-10-20; `ladder2/lib/families_pbrl.py`,
  `CampaignConfig.f2_rule`, record measure/ladder2-pbrl-weight/README.md).
  Under `f2_rule="weightn"` (pairs target), F2 at z 64 leads the published
  SET-1 code by 0.47 / 0.22 / 0.17 / 0.13 dB at r0203 / r0250 / r0313 /
  r0359. 10 of 12 codes read 0 undetected in 4,000 trials.
  - DONE: c6-low (2026-10-23) — its F2 weightn z 64 codes hold r0359 …
    r0203 in SET-1, −0.14 … −0.42 dB on the rung final, S4-accepted and
    clean on the pooled floor (the fastest F2 at r0250 / r0203 fail it).
  - DONE: c8-low (2026-10-24), z 32 under the word gate — r0250 / r0203
    by 0.08 / 0.06 dB at the bar's edge (pooled 19 / 20 of 20), behind
    at r0469–r0313; the fastest z 32 codes fail the bar by 2–5 counts.
  - DONE 2026-10-21 (refuter): ruled F2 lifts gate at max(campaign bar,
    T) (`campaign_plan.lift_kw_for_cand`). The rule bounds the SUPPORT
    (B ≥ T), not a codeword; the gate at T was met by 8 of 48 measured
    lifts (exact pairs 0.59–1.0 T), and an unmet gate keeps the best
    attempt for the acceptance bar of 24.
  - Owed (a ruling): whether a ruled F2 lift that misses T should be
    refused rather than judged at the common acceptance bar.
  - Owed: the z 32 crowding words (3–6 bits, weight 29–42) that the
    target does not reach.

## Bootstrap (`bootstrap/`, docs/BOOTSTRAP-DESIGN.md)

The live open list of the deep-time chain since 2026-10-26; it replaces
bootstrap/README.md "Open", FINDINGS.md "Open questions" and the stage
READMEs' lists (RECORD-2026-10-20.md "Owed after this session" is kept as
written). RECORD = bootstrap/RECORD-2026-10-20.md; rulings by number;
relative paths are under bootstrap/.

### Stage 4, the release (what c.py restores)

- The release tree's selection law, the owner's ruling: T1 =
  `src/holo/**/*.py` + `docs/**/*.md` + CLAUDE.md (`r3/arch/trees.py:3,
  :45-48`) carries no non-.py file under src/holo, so the twelve LDPC
  tables are missing and the archived holo3 dies at import
  (FileNotFoundError r0547.json, found on paper 2026-10-26); ruling 41 in
  full: "The tree is "the paper-store / holo release", to be ruled
  eventually; for now think paper/src, "but it will be more" (the readable
  sources of stages 1–3 do not travel in T1 today: bootstrap/ is not in
  it). Speculation recorded as such: a stage 4 in cmy8-r0850x0775x0700 to
  carry a lot more data."; the three choices are all tracked files under
  src/holo (+164 files, 9.7 MB, ESTIMATE ~26 pages), src/holo plus its
  data directories (+12 files, 161,840 B, ESTIMATE 16 pages) or all of
  src/ (438 files, 15.1 MB at 2115a595, not sized), with whether
  src/holo/receiver/docs/, bootstrap/'s readable sources and analyzer/
  travel, then measure (strong2, the capacity planner), run the simulated
  round trip and print on his go, stages 1-3 unmoved (ruling 39)
  (FINDINGS.md §16; RECORD:978-982).
- A requirements file (with the venv recipe of its header) inside the
  archive: the gap was known (ruling 40: holo3's imports are not in the
  tree, the release "magically has all imports") and was met in practice
  on 10-26, when the session built the release venv from the repo's
  requirements.txt (floors, not pins), and numpy-free reference
  implementations stay the far answer (RECORD:970-976; FINDINGS.md §16).
- Flat names, new on paper: c.py writes 321 files as `a%2Fb` and the
  session wrote scratch/typed3/unflatten.py; the options are the shell
  line of `r3/arch/README.md:85` as a sheet sentence (rendering only), an
  unflatten script at the head of the release tree, or the `_os` unpacker
  in c.py (+21-23 B, re-opens the convergence), the owner's call (today's
  record PAPER-2026-10-26.md).
- Release from a current commit: the stage-4 pages carry the T1 of
  2115a595 and at HEAD 4a4b2f4d 67 files of the selection differ (37
  modified, 30 added), so regenerate with the tree ruling (13 min encode;
  the header strip takes the commit, make_sheets_v2.margin_header)
  (FINDINGS.md §16).
- The self-unpacking payload ("the strong2 decoder and unpacker into d"),
  the decoder and the ustar unpacker as a preamble of payload.bin instead
  of c.py's section 10 so that c.py stays a format receiver, is the
  release step's option under ruling 61 (the layer kept as built), its
  exec route measured at R2 9,655 B, 953 B spare on the 10-21 base
  (superseded: today R2 10,133 B, 475 B spare), and since it shrinks c.py,
  b.py's N2/B2 change and the convergence re-runs: price it with the next
  release volume (`compressor-exploration/LEVERS-2026-10-21.md:233-235`;
  RECORD:1836).
- Where the unplaced tile of d-05 and d-08 sits (839 / 840 placed on
  paper), beside the left-margin header strip (0dfb3fed) or not: a c.py or
  holo3 diag on the existing scans, on the owner's go (today's record
  PAPER-2026-10-26.md).
- The stage-4 sheets' bigger margins (ruling 62) wait for the next
  regeneration; the header strip is done (0dfb3fed), the bitmap untouched
  (RECORD:1969-1971, :2238-2239).
- holo3 from the release tree to the close on d-01..d-09 once the data
  files are in, with the result and its sha recorded (the 10-26 run was
  stopped by the owner at 7,554 / 7,560 certified) (today's record
  PAPER-2026-10-26.md).
- The 600 dpi margin: seven whole pages certified 5,723 of 6,260 (817.6 a
  page, worst 774), so the volume needs 8 pages at the mean and 9 at the
  worst page's rate, and a second scanner or 1200 dpi on paper would say
  more (today's record PAPER-2026-10-26.md).
- Other families for the archive (planner, q 0.5) are K c2 7 pages, cmy8
  c3 6, cmy8 c2 3, cmy c3 8, cmy c2 4 and cmy c3 r0850 5, but c.py is
  K-only and a colour monolith would not fit 2 R2 pages, so no action
  without a ruling (FINDINGS.md §16).
- Archive codec levers: paq8l -8 at −8.9 % (14 pages, pure-Python decode
  ~24-36 h ESTIMATE), source-code contexts in strong2 (ruling 31(c)), the
  strong2 A/Bs (bit-history counter, indent / line-start / identifier
  contexts, identifier dictionary), Roadroller on T1-T3, counter cap 8/11
  and AQC at the next codec revision, with the 10-26 lrzip -zpaq
  (1,853,119 B) and xz -9e matching the recorded rows (RECORD:803-806,
  :2177-2180; LEVERS §§1-4; `r3/arch/README.md:263-270`;
  `priorart/zpaq/README.md:33-49`).
- The archive row: r0700 at q 0.5 as the page lever (ruling 27) or c.py
  retargeted to the ladder v2 SET-1 codes now on main (ruling 36, "for
  later"), either of which changes c.py and re-opens the convergence
  (RECORD:529, :937-947).
- R3's open questions: the runtime target (~40 s a page on an M1), partial
  pages and confetti, one volume or many (K > 16,384, i.e. over 4,315,100
  B, is refused; ruling 63 sets no K rule), and stop at the first close or
  read on (`r3/README.md:514-532`).
- Ageing: re-scan the oldest sheets, mechanical stress on c3 pages, sub-Tg
  heat, an ISO 11798 battery, old printouts, a natural-ageing shelf (the
  10-26 printed pages could start it), and the optional paper test on the
  printed e033 sheets A/A2/G (r0550), hardware, each on the owner's go
  (RECORD:556-563, :2214-2217; `r3/AGING-2026-10-20.md`).

### Stage 3, c.py (`bootstrap/stage3/`)

- Re-qualify the repaired c.py on the review's rough channel and at scale
  ±1.5 % (rough1200 p0/p1/p3, rough600 T1 15 pages, A s0985/s1015), of
  which only rough1200 p2 and rough600 p3 were re-run: a simulation, on
  the owner's go (`stage3/review/REFUTER-2026-10-23.md:66-69, :183-188`).
- The repair's owed lines: the local-scale cure (each tile's step from its
  placed neighbours; the per-tile retry stands in), the arbiter taking the
  FIRST lattice that places ≥ 3 tiles, the text page's cost (363 s at
  1200, 486 s at 300) and the fallback's ~200 s on a 600 scan declared
  1200 (`stage3/RESULTS-2026-10-22.md:630-646, :720-723, :858-861`).
- Not run: 2400 dpi on paper, the c4 and `_os` variants, the channel
  variants at r0547 (base1200, s2400, rot15, combo, turns), turn 90/270,
  tilt > 0.5° and pages in reverse order, while turn 180 on every page and
  a re-fed page's idempotence were measured on paper on 10-26
  (RECORD:1952; today's record PAPER-2026-10-26.md).
- The review's minors, never ruled one by one (payload.bin overwritten by
  a second session, refusal messages that name verified scans, a truncated
  raster accepted silently, check_tar accepting GNU/PAX, the archive
  encoder derived from receiver_arch.py, the first tile's 23 clean bits),
  are most likely refused in ruling 63's spirit: ask once
  (RECORD:1881-1888).
- make_c's (d'): that the tree keeps b4f7de22 with c0ffe2a5 in it is
  inferred, not run (~20 min), and longer cycles are not detected
  (`CONVERGENCE-2026-10-23b.md:78-82`).
- M2 ran one sweep; more sweeps and the reader's rewrite kinds on the
  monolith were not run (R2 bytes only; 475 B spare today)
  (`stage3/RESULTS-2026-10-22.md:263-264`).
- `stage3/lab/ev.py`'s docstring default orders (0,…,8) lag the chain's
  (0,1,2,3,4,6), which make_c.py sets in code (RECORD:1946-1947).

### Stage 2, b.py and the R2 page (`bootstrap/r2reader/`, R2-FORMAT.md)

- S2's deferred second walk and the finder's threshold are owed lines
  under ruling 52, and any b.py change moves the data sheet and re-opens
  the convergence (RECORD:1446-1447).
- A second format round with the reader port fixed (page-wide pitch
  consensus, a seed-quality rule for the pose, dd's dedupe fix; 114-155
  typed measured), and candidate V4, a cross of the two middle stripes:
  the owner's call (ruling 62) (RECORD:1615-1619, :1987-1991;
  `format-round/RESULTS-2026-10-22.md:647`).
- The reader search's declined winners (ruling 62 point 3;
  CONVERGENCE-2026-10-23b r1 (2)): fold into the next regeneration
  (RECORD:1967-1968; `CONVERGENCE-2026-10-23b.md:35`).
- The half-page trade-off (ruling 19): the 46 mm straight strip, under
  which a page torn on its vertical centre line loses 9-10 chunks whole,
  or the straddling design at 8.7 mm (RECORD:2204-2206).
- The walk's state as block corners (the owner's idea for the photos),
  per-block pose (fix #2 refused as specified, −60 to −90 glyphs if a
  carrier is found) and the ideation not built (timing-crossing seeds, a
  two-stage chain parked by ruling 33, syndrome decoding)
  (RECORD:1264-1268; `r2reader/ideation/IDEAS-2026-10-22.md` §3.3).
- The xpage_e2e 57-capture set never ran on the rewritten reader: confirm
  whether the acceptance sets cover it (RECORD:832-833, :1168-1169).
- Primer decoupling: none until the sizes are ideal (ruling 33)
  (RECORD:879).

### Stage 1, a.py and the data sheet (`bootstrap/stage1/`)

- The whole-file check code for a.py (each line's code chained on the
  previous one, or one code over the file; +10-15 typed), "let's keep this
  in mind for the future. not doing that right now." (ruling 68): fold
  into the next regeneration with any other a.py change (RECORD:2271).
- The Crinkler masks and weights in cm2 (item 12 of ruling 43) come last,
  on the final reader text, and were never re-measured on the current
  reader (RECORD:1097, :2174-2176).
- The name search is single-move coordinate descent; pairs and restarts
  were not run (`stage1/RESULTS.md:172-173, :277-279`).
- The sources of truth per program (template.py, reader_lite_v1.py,
  c_readable.py; ruling 58's note) await the owner's confirmation
  (RECORD:1765).
- "Page 4: the owner's pending change to the loader listing": absorbed by
  ruling 43's a.py or not, ask (RECORD:2182).
- The printed QR codes were read on paper on 10-26 (sheet 2's data taken
  from its QR, sheet 1's as a cross-check); the reading device is not stated
  (`stage1/qr/README.md`; today's record PAPER-2026-10-26.md).
- A second typist who did not design the chain, and a timed typing session
  (10-20 about 40 min; 10-26 not recorded) (PAPER-2026-10-20.md; today's
  record PAPER-2026-10-26.md).

### Stage 0, the Plate (`bootstrap/plate/`, the 10-18 draft)

- Cut to one leaf, deferred by ruling 38 until stages 1-3 are fixed, it
  owes the release volume's hash (ruling 39), the progress line, letter
  reuse and the module/inner bindings of y, s, r, b, z, "600 dpi or more
  for the archive pages" (2026-10-26), the spec gaps (`>>` and `&` on
  negatives, setdefault, precedence), a primed known-answer vector of at
  least 1 KB, the leaf naming and binding, the hash-chain line and a front
  page naming the pages and their order (31e), while sheets 1-2 already
  print the floor, the grid one-liner and the progress line (rulings
  62-66) (RECORD:956; `stage1/RESULTS.md:305-307`).
- Micr'Olonys' full text, the nearest prior art (RECORD:806).

### Process and evidence

- Promote v3 (print-2026-10-23.pdf 4989446c…, closed on paper 2026-10-26)
  to the print of record, and say what becomes of loader/ (the 10-20
  print) and build.py: the owner's ruling, ruling 67's "Owed to paper"
  being done (RECORD:2106; today's record PAPER-2026-10-26.md).
- An experiments/048 writeup of the 10-26 close, or the bootstrap note
  alone (written): the owner's call (today's record PAPER-2026-10-26.md).
- The merge to main and any push are the owner's go; main moved after the
  merge (370a1d68, CLAUDE.md +2 lines), so CLAUDE.md meets once more, and
  the local ref shows "ahead 118" with no divergence, so the record's
  `--force-with-lease` looks stale (not re-fetched) (RECORD:2218-2219).
- The tree cleanup table of 2026-10-23 awaits the owner's word
  (RECORD:1833-1834).
- Before any wipe of bootstrap/build/: build/w4 (the acceptance sets'
  frozen frames) and build/changeset (renders, names maps) are not cleanly
  regenerable, so commit compact fixtures or ledger them, the owner's call
  (`ARCHIVE-INDEX-2026-10-23.md:268-286`).
- The CONVERGENCE-2026-10-23b §7 items not run: the slow lanes,
  sizes_c.py, the lowercase sheets rendered, build.py, and the text-page
  and wrong-dpi rows on the final c.py
  (`CONVERGENCE-2026-10-23b.md:189-195`).
- Reproducibility is host-bound: the font files (Menlo, Andale Mono) are
  not in the tree, only their sha256 in build/sheets/MANIFEST.txt
  (47dfbab5) (RECORD:2226-2227).
- ARCHIVE-INDEX's items left at the judge's defaults: the shelf layout (11
  git mv), one driver for every family, strong / strong2 / Crinkler / ZPAQ
  never sized on T1_8k / T2_16k / T3_32k, and folding the wrapper chains
  (`ARCHIVE-INDEX-2026-10-23.md:239`).

## Elsewhere, open lists kept in place

- Scheduling line: `src/holo/receiver/docs/SCHED-OPEN-2026-10-03.md`.
- Page field: `docs/PAGE-FIELD-DESIGN.md` §7.1.
- Diag viewer: `src/holo/receiver/docs/DIAG-DESIGN.md` §8.
- CMY family rulings owed: `git show dbafcaad^:CLAUDE.md`, CMY FAMILY bullet.
- Rung ladder rulings: `docs/RUNG-LADDER-STUDY-2026-09-30.md` §8–§9.
- Evidence re-release after paper-store-rel, the adjustments owed: `docs/evidence-archive/NEXT-RUN.md`, section of 2026-10-27.
