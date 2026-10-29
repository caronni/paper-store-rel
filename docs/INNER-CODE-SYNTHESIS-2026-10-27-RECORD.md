# Inner code and LLR chain: the record behind docs/INNER-CODE-SYNTHESIS-2026-10-27.md (2026-10-27)

Four independent assessments of the same three questions were taken on
2026-10-26 and 2026-10-27: what LDPC v1 is for and how it meets the cell
evidence, whether LDPC v2 (SET-1) is better and what to do with it, and
whether the literature holds anything better. This document folds them
into one record. It changes no design of record. The
normative texts stay `docs/FEC-DESIGN.md` (v1), `docs/LDPC-LADDER-V2.md`
(v2), `src/holo/receiver/docs/API.md`, `SCHEDULE.md` and
`conversion_docs/02-ldpc.md` (the receiver). Positions taken here are the
synthesis' positions. The owner has ruled on none of them as of
2026-10-27 unless a line says so.

Source tags: [R] the repository, with the file; [F] the Fable assessment
and its three research workers; [A] Astra; [GBo] Grok Bots; [GBu] Grok
Build; [S] the Fable synthesis turn of 2026-10-27, which computed the
BSC bounds and extracted the shortening table. A number carries the tag
of whoever measured it. Every number tagged only [F workers], [A], [GBo]
or [GBu] is unverified in this project's harnesses unless a sentence
says it was checked here. Terms are defined in section 14.

## 1. Scope and sources

### 1.1 The frame

The owner's four prompting thoughts set the questions this document
answers beyond the original three: whether shortened codes have a
problem at the low rungs (section 6); whether the meaning of an LLR is
fully honoured before the decoder (section 4, where that sentence is the
thesis); whether a 5G comparison at the high rungs is worth anything
when the ladder is near the finite-length bound (section 7.2); and
whether polar codes with a CRC, or anything else the literature pass
skipped, deserve a look (section 7.3 and 7.4). Pilot density p is a
free design axis (the owner, 2026-10-27): K emits and decodes at any
lawful p (100, 150, 200, 300; `docs/P-AXIS-DESIGN.md` §3), cmy8 at any p
above 100 since `docs/HOLO-DESIGN.md` §13.37, cmy7 alone is locked at
p120; p100 and p120 are the defaults, and a higher p buys shredder
resistance and calibration labels at the cost of user bits. The v2
record measured shortening at p120 and p300; p200 is not a measured
level.

### 1.2 The sources

| source | what it did itself | what is verified here | what is not |
|---|---|---|---|
| [F] | read v1, v2, the receiver, the measured record; three research workers on code families, decoder and LLR literature, paper-storage prior art | the repo numbers it quotes, with the stale ones corrected in this document (150-iteration gains, shortening caveat) | the workers' derived numbers (polar at 4096, headroom estimates) |
| [A] | read the implementations and the latest v2 results; replayed recorded decoder failure seeds; primary literature with links | the decoder blind spot (confirmed in code, 8.1); the metadata bit (in `02-ldpc.md`) | the replay counts (61 and 3), the external papers' numbers, the campaign timing figures (which disagree with the controlled twins numbers, 5.3) |
| [GBo] | read the public repository; ran a numba copy of `decode.py` reported bit-exact; simulated v1 r0700 and r0850, v2 r0703 and r0859, and two 5G NR codes on AWGN, BSC and a synthetic print proxy; three plots | the plot readings at the shared rates agree with the repo's AWGN gaps and BSC crossovers; the weight-4 word in r0850 (checked against the frozen matrix in the coverage pass: all checks satisfied); its one-in-a-thousand BSC wrong-decode rate (the twins' r0850 BSC walk recorded 10 undetected in 30,000) | the harness, the 5G construction, the print proxy, the trial counts (about 3000 per point on AWGN and BSC, about 2000 on the proxy), its 30 percent iteration claim (5.3) |
| [GBu] | read v1, v2, the receiver and the record; literature; answered five follow-up questions | the repo numbers it quotes, with two stale ones corrected here (the 150-iteration gains and the 22 ms figure, both from the pre-PBRL picks) | its analyzer figure of claimed 6 percent against measured 16 percent error on colour states, not located in the repo in two passes |
| [S] | the shortening table from the SET-1 records, the decoder fallback path, the BSC finite-length bounds, the absence of polar from `ladder2/docs/LITERATURE.md`, the address decoder's call path | all of it, after the coverage pass corrected its Z arithmetic (6.3), its page-edge premise (2, 6.3, 7.3) and its address-decoder citation (3.6) | nothing further |

One disambiguation [A]: "LDPC v1", the receiver's own version numbers,
and the `holo/v2/` format namespace are three separate version axes.
This document says v1 and v2 for the code ladders only.

### 1.4 What each assessment recommended, in one line

- [A] v2 is the better collection, broader rates and fewer weak
  codewords, but not to be switched to wholesale yet; keep the
  LDPC/CRC/fountain architecture, preserve SET-1, qualify it selectively,
  and make the next comparison use real shortened frames, realistic cell
  evidence and recovery per unit of computation; benchmark first.
- [GBo] v2 is better than v1 only modestly; keep LDPC, retire v1's top
  rung r0850, rebuild the whole ladder as one rate-compatible family; the
  bigger levers are in the LLRs.
- [GBu] v1 is the right code for what is printed; v2 is a better ladder
  by a small amount at the old rates and by a real amount where v1 has no
  rung; if a later format needs the high or fragment rungs, freeze SET-1
  as it stands; generate no more codes with the v1 recipe; open no new
  lifting search; the remaining yield is in the LLRs.
- [F] do not abandon and do not replace; adopt SET-1 for reach in the
  next format version; re-rank rather than re-lift; two cheap twins runs
  (5G, and a bounded-LLR channel) settle the rest.

## 2. The tile as a channel

The inner code is the code of one geometric tile: 64 by 64 cells, so a
binary mother code of length 4096, one slot per cell [R
`src/paperholo/ldpc.py`]. A tile must turn soft cell readings into
certified user bits or be discarded. It is not a page code. Interleaving
stops at the tile on purpose: a fragment has to certify from the cells it
contains [GBu]. The v1 codes were designed to certify one tile at a time
from the blind receiver's soft cell evidence at 1 to 7 percent raw cell
error [F].

The chain above and below it [A, R]:

    scan → cell evidence → LLRs → LDPC → syndrome AND CRC → fountain → envelope and SHA

LDPC repairs errors and erasures inside a tile. The CRC-32 refuses wrong
tile results. The fountain repairs missing tiles and fragments, treating
every failed tile as one erasure symbol of a dense GF(2) system solved per
block [R `docs/FOUNTAIN-DESIGN.md`; GBo]. The envelope and the file hash
say whether the file came back. All four assessments find this division
right for the problem.

Three classes of input reach the decoder [R `02-ldpc.md`]: measured cells
as finite LLRs, erasures as LLR 0 (fragments and uncovered cells are
first-class, they cast no vote), and shortened positions as minus
infinity (known zero: the pilot and furniture sites, which are never
printed). In the holo format every payload tile carries the same site
count, pilots colocated, no partial tiles [R `docs/HOLO-DESIGN.md` F1;
`tile_codec.py` at `transmitted_positions`]. Page-edge shortening of
partial tiles belongs to the v1 paperholo stack only [R
`docs/FEC-DESIGN.md`]; the coverage pass corrected the first draft on
this point, which had carried the v1 premise into three arguments.

The decoder assumes its inputs are independent given the codeword and
that magnitude is reliability. Paper breaks both in three measured ways
[R experiments 013 and 018, `docs/RUNG-LADDER-STUDY-2026-09-30.md`]:

- Errors come in bands and slip bursts inside a tile, so tile success is
  governed by the tails, not the mean cell error (013 F1). The codes were
  qualified on memoryless channels [GBu]. The design left the warp-slip
  bursts to the fountain rather than to an interleaver, accepting that
  they violate the decoder's independence assumption [GBu].
- A cell can carry the wrong sign at a large magnitude when its sample
  position is uncertain. The 2026-09-30 study injected such cells at
  magnitude 20, the decoder clip, into the construction search's
  finalists: at 0.1 percent of cells they cost 30 to 89 block failures
  per 100 at the 1 percent point (10 per 100 for one IRAA variant); at
  0.5 percent every finalist failed 99 to 100 per 100. That is a worst
  case above the production bound, since production LLRs cannot exceed
  about 7 by construction and 12 after context (section 4), not a
  measured production loss [R study §4; critic].
- Summing the LLRs of two scans of the same printed defect is not exact,
  because the scans do not acquire independent print errors [A], and
  experiment 013 found the sum loses to the best single scan when the
  scans slip relative to each other (013 F3) [GBu].

Where the fountain sits in that picture [GBo, synthetic channel]: under
burst damage every code loses 25 to 60 percent of frames alike, so
bursts belong to the fountain, not to the matrix.

## 3. LDPC v1

### 3.1 The six frozen codes

Six frozen draws, seed label `ldpc-v1/<rate_id>`, JSON in
`src/holo/core/ldpc/data` with a byte-identical copy in
`src/holo/receiver/lib/ldpc_data`, sha-pinned [R].

| rate_id | k | true rate | role | printed on |
|---|---|---|---|---|
| r0547 | 2240 | 0.547 | the fragment rung | sheet J three times, every cmy8 Y bank |
| r0550 | 2240 | 0.547 | a second draw of the same k, ruled meaningless; a weight-6 word on two information bits | fossil rows e030, e032, e033, e038; cmy8 C and M banks |
| r0625 | 2560 | 0.625 | | never |
| r0700 | 2880 | 0.703 | the original c3 design point | sheets I at 100 percent, e029, e032, e039 A to C |
| r0775 | 3200 | 0.781 | heavy columns drop to degree 8 | e039 sheet H, unscanned |
| r0850 | 3520 | 0.859 | heavy columns drop to degree 6; top of the ladder | sheet H at 100 percent (e036), VersaLink D (e039) |

Six graphs, five rates [A]. The construction is extended irregular
repeat-accumulate: a quasi-cyclic information part at Z 64 with 30
percent heavy columns (degree 10 where the parity side allows it) and
degree-3 columns elsewhere, a seeded Fisher-Yates row interleaver, and a
bit-serial dual-diagonal accumulator. Each code is a greedy seeded draw
under four rules, distinct rows, a tap-gap parity-weight floor of 24, the
exact QC 4-cycle rule, and a row-degree cap, restarted until it passes
[R `src/paperholo/ldpc.py` docstring; `docs/FEC-DESIGN.md`]. The codes
have girth 6 [GBo]. Heavy columns sit at the front because the payload
fills information bits from the front and shortening eats the tail, so
the payload sits on the best-protected variables [R `02-ldpc.md` §2;
GBu].

The recipe was the survivor of three measured failures [GBu, from
FEC-DESIGN]: a block-circulant accumulator produced weight-8 to weight-10
codewords and undetected decodes; a QC accumulator without the
interleaver produced weight-(d+2) words; a uniform degree-3 profile
missed the r0700 gate. The per-column gap floor forces every
single-information-bit codeword to weight 25 or more. Pairs of
information bits are not bounded, and that residual is why a tile
certifies on syndrome and CRC together. The recipe is defective below
k about 1300, where 8 to 22 percent of checks carry no information edge
[R `docs/LDPC-LADDER-V2.md`]; the 2026-09-30 study's balanced placement,
spreading the information edges evenly over the rows, removed every
information-free row at the search lengths [R study].

### 3.2 Framing and shortening

Information bits are [user | crc32(user) | zeros(p)]; the CRC is zlib,
MSB-first [R `tile_codec.py`]. Shortening consumes the information tail
only; parity is always transmitted, and colocation gives every tile the
same site count [R `tile_codec.py` comment at `transmitted_positions`].
User bits per tile are k minus p minus 32 [R `tile_capacity`], and the
first user bit is the metadata bit, so the fountain payload is one bit
fewer [R `02-ldpc.md` §1; A]: r0547 at p120 carries 2088 user bits and
2087 fountain bits in 3976 printed cells. The pilot sites are the
shortened tail: p100 the K default, the exact word; p120 the colour
default, the 100-site word plus 20 deterministic dust sites; K emits and
decodes at any lawful p (100, 150, 200, 300) and cmy8 at any p above
100, with p100 refused for cmy; cmy7 is locked at p120 [R
`docs/HOLO-DESIGN.md` F4, §13.37, line 200; `docs/P-AXIS-DESIGN.md` §3].

On the e012 page that is 2,189,231 user bits at r0700, about 40.8 bits
per square millimetre if every tile certifies; experiment 013 measured
35.7 through the blind pipeline at 87.5 percent tile success [R
`experiments/013-ldpc-roundtrip.md`].

### 3.3 The decoder

[R `src/holo/receiver/lib/ldpc.py`]. Finite LLRs are clipped to plus or
minus 20, infinities become plus or minus 1e9, the sign is flipped into
the textbook convention. Flooding normalized min-sum with alpha 0.8 runs
at most 60 iterations with early exit on a zero syndrome. If the
syndrome is still wrong, one exact sum-product pass of 60 iterations
runs from the same channel LLRs. That retry measured 4.0 against 1.6
percent block error at the r0700 p 0.035 gate. Retrying from the
min-sum posterior would be a different, unmeasured decoder. The
extrinsic returned is relative to the clipped input.

The certificate is syndrome AND CRC [R `tile_codec.decode_tile`, the
comparison at `tile_codec.py:247`]. A syndrome-only pass is not a
certificate. Syndrome-valid wrong words are counted as failures. The
record stands at 0 wrong certificates in 69,066,304 audited cells [R
`02-ldpc.md`].

Stages [R `plugins/tiles.py`]: scan at 60, union at 60 once two captures
hold evidence (the union stage SUMS the captures' LLRs, nothing clamps
after the sum, because each capture's LLR is already bounded by its own
PAVA label count), then the retry stages retry150, local150, uplift_a3,
uplift_a4b, planek150, swim150 and cond150, each on its own evidence. A
retry needs a failed baseline: a decoder ran on this exact evidence and
lost. Experiment 030 counted 35,281 LDPC calls for 663 certificates, 621
from scan and 42 from retry150 [R `experiments/030-holo-cmy8-hp-canon.md`].
Note on the word "union": in the v1 record the "tile-level union" is a
selection among per-scan decodes; in holo3 the union stage is the LLR sum
that 013 F3 found loses to the best single scan [critic].

Colour uses the same codes as banks [R `02-ldpc.md`]: cmy8 at p120
decodes C and M on r0550 and Y on r0547 as separate streams; cmy7
decodes a three-child bank, r0550 unshortened and two r0625 shortened by
677, through three demap-decode passes with the extrinsic prior clipped
at 20, and may invoke the frame CRC up to three times per attempt, a
registered undetected-error-budget compromise [R `02-ldpc.md` §cmy7].
Rate choice is the format row's, keyed on p, so a placed window can try
each rung's decode at no addressing cost [F]. The counting floor refuses
an attempt whose informative cells number fewer than the unknown
information bits [R 2026-09-30 study; GBu].

Throughput: the July paperholo v1 codec measured 176 tiles per second
whole-page including gathering, a page being about 840 tiles [R
`docs/FEC-DESIGN.md`; GBu]; that is the v1 stack's number, not holo3's.

### 3.4 Measured codec performance

Under the v2 protocol, the batched twin of the production decoder (60
min-sum plus sum-product 60, alpha 0.8, clip 20) on BIAWGN with
5,000-trial confirm walks and two 10^5-trial acceptance points [R
`measure/ladder2-v1-twins/README.md`, 2026-10-19]:

| rung | gap to Shannon dB | gap to NA dB | BSC p at 1 % | undetected per 10^5 at 1 % / +0.5 dB | the undetected words | ms, iterations per decode near 1 % |
|---|---|---|---|---|---|---|
| r0850 | 0.812 | 0.492 | 0.0089 | 9 / 5 | pair words of total weight 4 | 2.47, 11.8 |
| r0775 | 0.789 | 0.472 | 0.0199 | 11 / 6 | pair words of weight 5 to 7 | 3.67, 18.0 |
| r0700 | 0.843 | 0.520 | 0.0346 | 3 / 1 | two pair words of weight 7, one 4-bit | 6.05, 28.1 |
| r0625 | 0.899 | 0.564 | 0.0484 | 41 / 32 | its weight-6 pair word, 65 of 73 | 6.05, 30.1 |
| r0547 | 0.981 | 0.628 | 0.0653 | 8 / 1 | weights 12 to 26, 2 to 10 info bits | 6.09, 33.4 |
| r0550 | 1.046 | 0.694 | 0.0611 | 181 / 89 | its weight-6 pair word, 182 of 270 | 5.17, 29.1 |

The waterfalls agree with the 2026-10-01 confirm within 0.01 dB. The
150-iteration column moves the frozen codes by 0.003 to 0.065 dB. The
cost column is the twins' `decode_cost` record, one worker of the batched
decoder [R twins results]. Density-evolution thresholds, asymptotic, put
v1 at 0.31 to 0.39 dB from capacity [GBo, who says these match the
repo's own numbers where it reports them; not checked here].

On paper the top rung's envelope is measured [R
`experiments/039-xerox-versalink-candidate-set.md`]: sheet D at r0850
closed at 5.8 percent raw cell error; sheet E at 22 percent raw error
gave no certificate.

r0850 has a weight-4 codeword at bits 1902, 2856, 3723 and 4064 [GBo;
checked against the frozen matrix in the coverage pass, every check
satisfied], so its minimum distance is at most 4; the twins run records
its minimum pair word at weight 4 [R twins README]. About one frame in a
thousand on the BSC converges to a wrong codeword there [GBo]; the twins'
r0850 BSC walk recorded 10 undetected in 30,000 trials [R twins results].
The CRC catches every one, so the frames are wasted, not corrupted. The
6-cycle count does not predict this: v2's r0859 has about eleven times
more 6-cycles, and its smallest word found by [GBo] weighs 8, which is
below the published record's minimum found weight of 9 [R `CODES.md`]
and would be a new finding if confirmed.

Three of the six frozen codes fail the v2 floor bar (r0775 at 11 / 6,
r0625 at 41 / 32, r0550 at 181 / 89) and r0850 passes at the edge. The
bar refuses codes no worse than the ones that close sheets on paper:
r0850 read sheet H to 100 percent from the same floor regime [R twins
README; `docs/LDPC-LADDER-V2.md` R3].

### 3.5 Standing

Repo law: the frozen v1 ladder stays the law for every printed sheet,
and SET-1 replaces nothing [R `docs/LDPC-LADDER-V2.md` status line]. The
receiver keeps its loader for every sheet that exists, including the
bootstrap material [A, F, GBu]. Position, not law: no more codes are
generated with the v1 recipe [GBu].

### 3.6 The address word is a different job

The pilot address code is a shortened binary BCH, BCH(127, 50, t 13) cut
to 100 transmitted bits and a 23-bit message, an 18-bit tile counter
plus 5 known-zero pads, designed distance 27 [R `src/holo/core/bch.py`,
`docs/HOLO-DESIGN.md` F3]. It corrects 13 errors, or any mix with 2e + f
at most 26 when missing sites are declared as erasures [GBu]; both
libraries implement `decode_erasures` with that budget, and the
production word path (`plugins/words.py`) calls the errors-only decoder
at full strength t 13 [R `core/bch.py`, `receiver/lib/bch.py`; critic].
The pads are fixed zero so that, once the row seed is known, every
printed pilot bit is predictable, and that predictability is the
correlation template for cold start; a data-dependent pad was measured
to flip 39 to 40 of the 100 bits and was rejected [GBu]. The redundancy
is intentional: rate 0.23 sits far below the payload ladder because the
word is a lock and a calibration source [GBu].

The word has to lock a phase hypothesis before any payload exists, on
100 bits, and a wrong lock has to be refused. Algebraic decoding gives a
unique word or a refusal, and the pad gate refuses another factor of 32;
a random 100-bit string does not land on a codeword. At 5 percent raw
error the mean is 5 errors in 100 bits and 14 or more is several
standard deviations out. Declared erasures cover the fragment case
inside the 2e + f budget, the same regime the low payload rungs serve.
Soft-decoding the address word would not improve the payload LLRs: the
labels are exact once the hypothesis is right, and a short soft code on
those 100 bits would spend a decoder, a matrix and a bootstrap
description to recover hypotheses the bounded-distance decoder already
accepts or correctly refuses [GBu]. The hard construction is the right
one for its job.

## 4. The LLR contract and where it leaks

### 4.1 The contract

The code never sees a probability. It sees an LLR in the house
convention: positive means bit 1, L = log P(1)/P(0), the hard bit is
L > 0, 0 is an erasure, infinities are known bits [R `02-ldpc.md`]. A
probability of 0.9 is about +2.20, 0.99 about +4.60 [A]. The decoder
does not need Gaussian observations; Gaussian noise is the benchmark
the graphs were selected on, not a production requirement [A].

The contract at the decoder's input is: calibrated, so that the
magnitude matches the empirical error of the cells carrying it;
conditionally independent across cells given the codeword; and bounded
by what the evidence can support. Normalized min-sum is invariant to a
global scale of its inputs apart from the clips; it is not tolerant of a
large magnitude with the wrong sign. The sum-product retry is scale
sensitive. So only relative miscalibration, the clips, and the retry
can move a result; scaling every input the same way cannot change the
ideal unclipped min-sum decision [A, F workers].

### 4.2 The chain, stage by stage

[R `API.md`, `lib/pava.py`, `plugins/color_model.py`,
`plugins/tiles.py`, `format/tile_codec.py`]

1. K detector: a per-cell darkness score, (median minus mean) over
   spread, larger meaning more ink [GBu]. Pilots in the window are
   known bits, split into a fit set and a held-out set [GBu].
2. Per-window isotonic calibration (pool-adjacent-violators) maps score
   to an empirical ink probability, held inside 1/(n+2) to its
   complement for n labels, with an absolute floor of 1/(1+e^20) [R
   `pava.py` CAL_PROBABILITY_FLOOR]. The LLR is the logit, so |L| cannot
   exceed log(n+1), about 6.9 at a thousand labels. This is the 018.7
   invariant, by construction: uncalibrated scores had reached 5e5 and
   the loudest, least calibrated windows poisoned every union.
3. A nine-bin inked-neighbour context offset, monotone, moves a cell by
   at most 4; the result is clamped at 12 [R `pava.py`].
4. Colour: cmy8 takes each plane's LLR as the log-sum-exp difference of
   the QDA state scores with and without that plane's ink, and clips a
   degenerate plane to 2 so an unsupported plane becomes near-erasure
   while its siblings stay useful. Modern cmy keeps a calibrated joint
   model through marginal and conditional maps, and a certified sibling
   enables conditional decoding [A, `plugins/color_chain.py`]. cmy7
   packs four cells into eleven bits and iterates demap and decode
   three times with the extrinsic prior clipped at 20. These mechanisms
   are to be retained and credited in any comparison with an alternative
   code or decoder [A].
5. Captures of one tile are summed, with no post-sum clamp.
6. The keystream descramble multiplies each payload LLR by plus or
   minus 1, which keeps the magnitude; site cells are zeroed; cells are
   scattered to codeword positions through the cell map; shortened
   positions are pinned at minus infinity. NaN or infinity from a
   detector is a fault [GBu].
7. The decoder clips at 20 as a backstop.

### 4.3 Where the meaning leaks, each with its measured instance

- **Capture summation assumes independence.** Naive multi-scan LLR
  summation lost to the best single scan when the scans slipped
  relative to each other (013 F3). The designed fix, per-scan
  pilot-agreement weights, is unbuilt; the v1 interim was a selection
  among per-scan decodes, and holo3's union stage sums. The analyzer's
  T1 arm scales the combined LLR by a temperature on the premise that
  multi-lane sums on a print-frozen channel are over-confident; measured
  as I7, it did not rescue a channel the detector could not read, and
  says nothing about a patch channel [R `analyzer/DESIGN.md` L2,
  `analyzer/APPROACHES-2026-09-06.md` I7; GBu]. The literature's result
  under heavy-tailed noise is that linear LLR combination loses to
  selection by 1 to 10 dB [F workers, Mei], which is the 013 F3 shape.
  The fixes in order [F workers]: re-run the isotonic calibration on the
  combined score instead of summing calibrated LLRs; saturate or erase
  each scan before summing; keep per-scan selection beside the sum.
  [GBo] found a CRC-gated retry with LLRs clipped to 2 to 5 recovered
  about 15 percent of burst failures with no false accepts, on its
  synthetic channel: the same mechanism.
- **Colour magnitudes are over-confident on inked sibling states.** The
  analyzer built the erase-state arm L7c against the measured
  over-confidence on M plus Y, and records one map over-confident in
  one region and under-confident elsewhere [R `analyzer/DESIGN.md:643`,
  L7c]. [GBu] quotes magnitudes claiming about 6 percent error where
  cells were wrong 16 percent of the time; that figure was not located
  in the repo in two passes. Erasing the least-confident cells of a bad
  state and refitting from a tile's own confident cells moved yield by
  a small measured amount [GBu].
- **Geometry is absent from the magnitude.** A cell with an uncertain
  sample position can still be dark and loud. That is the
  confidently-wrong tail of the 2026-09-30 study (section 2, with its
  context). The right response is an erasure, LLR 0, not a clamp. Where
  a clamp is used, its level under a slip rate p is ln((1−p)/p): 6.9 at
  one per thousand, 5.8 at three, 5.3 at five per thousand; the
  log(n+1) bound of about 6.9 at a thousand labels is right only while
  slip stays under one per thousand inside a window [F workers].
  Explicit erasure flags for detected strips and slips are the same
  idea [GBo].
- **The context offset and its clamp.** Additive on a calibrated logit;
  calibrated only if the context model is. Its own held-out calibration
  is not in the record read for this synthesis.
- **Shared registration error and neighbour interference.** Separate
  scalar LLRs cannot represent shared registration errors,
  neighbouring-cell interference or colour-state dependence [A]. The
  marginal LLRs discard the dot-gain correlation between neighbouring
  cells; detecting that jointly and iterating with the decoder (Marrow
  and Wolf, ITW 2003) is a lever outside the matrix [GBo].
- **Input confidence and internal saturation are different things.**
  Internal saturation in the decoder can create floors (Butler and
  Siegel; also `LITERATURE.md` item 8), but raising the input clip lets
  confidently-wrong cells do more damage; removing the clip at 20 is not
  a justified blanket fix [A].
- **Mismatch has a predictor.** Generalized mutual information computed
  from the LLRs predicts soft-decoder performance better than raw cell
  error [A, Alvarado; Nguyen and Lampe]. It is a diagnostic, not a
  substitute for running the decoder on correlated print evidence.

### 4.4 What is missing is an audit

Every certified tile yields 4096 true bits, and on a sheet with a known
payload the emitted field gives the truth for failed tiles too, which
is the set the audit must not exclude (Astra's review, 2026-10-27).
Snapshots keep poses, certified bits and decisions; evidence arrays and
attempt facts are excluded by design and regenerated from the stored
captures on a replay [R `src/holo/receiver/snapshot.py`]. Reliability
diagrams per stage, per plane and per printer, and a per-tile
generalized mutual information, are therefore a replay of the captures
with the evidence kept, not a lookup, and still no new scans.
The per-tile spread of that number is also the deciding input to the
system-split question (section 10). The analyzer's separation ruling
applies: ground truth is an audit, never a knob or a gate [R
`analyzer/DESIGN.md`].

## 5. LDPC v2, SET-1

### 5.1 What it is

Tool `ladder2/`, design `docs/LDPC-LADDER-V2.md` v0.7. The search was
stopped by the owner on 2026-10-24 with SET-1 published in
`ladder2/codes/`, one accepted code per rung, twelve rungs, k from 3712
to 832. The branch was merged to main the same day (merge commit
22820b80; the "NOT merged" lines of `docs/FEC-DESIGN.md` are stale).
Not printed, not integrated in generator, receiver or analyzer; a later
format version [R status line; git; critic].

Every code is pure quasi-cyclic: a base matrix of circulants, block
dual-diagonal parity, Z 32 or 64, punctured state nodes allowed up to
128 per code (R2). The v1 bit-level interleaver cannot be written in the
v2 description, so a v2 loader is new code and old sheets stay on the v1
matrices [R §2, §10]. Lifting is QC-PEG with ACE, an exact
two-information-bit pair-weight gate and a light-column word gate. The
literature pass of 2026-10-18 had already adopted QC-PEG, ACE, PEXIT, a
punctured precode plus a degree-1 extension at low rate, and a
minimum-weight gate before v2 built them [GBu; R `LITERATURE.md`].
Selection ran eight campaigns (c1 to c8) and over fifty million decodes
through the production decoder's bit-exact twin, with a rung final on
paired fresh trials and rank v4 [R `ladder2/results/LEADERBOARD.md`].
Campaigns after the first accept round moved the top rungs by hundredths
of a decibel; the bottom moved more because the family changed [GBu].
Verification: 100,000-trial acceptance points, fresh common-condition
finals, and 20,000 fresh verification trials per published file [A, R
`ladder2/codes/VERIFY.md`]. Elkelesh et al.'s decoder-in-the-loop code
design is already how v2 selects; what distinguishes the next search
from that literature is only the objective [S].

Families by rung, where the campaigns measured them [R §1.2; GBu]:

- F1, PEXIT-profiled irregular repeat-accumulate, holds r0906 through
  r0625. At high rate there are only 6 to 14 block rows of parity; the
  code wants heavy information columns and one accumulator.
- F3, punctured XOR-state graphs, hold r0547 through r0406. In the first
  campaign they led F1 by 0.05 to 0.11 dB from r0406 down and tied
  around r0547.
- F2, protograph-based raptor-like (a punctured precode node plus a
  degree-1 extension), holds r0359 through r0203. It was behind by 0.29
  to 0.35 dB at r0547 and r0469 when first measured; in c8 its Z 32 form
  stayed behind the published codes by 0.04 to 0.36 dB at r0469 to
  r0313; it won the bottom by 0.14 to 0.42 dB and roughly halved the
  iterations there. Against early v2 the latest PBRL picks improved the
  bottom by 0.4 to 0.46 dB [A]. [A] keeps PBRL as the leading low-rate
  family.
- F4 near-regular was admitted and did not win a rung. F5, an
  accumulator precode tried upward, lost: +0.27 dB at r0859 and no floor
  improvement anywhere [R `docs/TODO.md`; GBu].

There is one decoder for all twelve rungs, the production identity (60
min-sum plus sum-product 60, R6). A punctured node is a variable held at
LLR 0. The family is only the shape of H: one JSON shape, one loader,
one decoder [GBu]. Running the bottom construction across the top would
repeat a measured loss, and forcing one protograph onto every rung gives
up tenths at one end or the other [GBu].

### 5.2 The ladder

[R `ladder2/results/LEADERBOARD.md`, `ladder2/codes/CODES.md`, the SET-1
records, `docs/LDPC-LADDER-V2.md` §1]

| rung | k | family · Z | gap to Shannon dB (rung final) | gap to NA dB | user bits p120 / p300 | BSC p_cap (capacity) | BSC p at 1 % (S3) | undetected per 10^5, S4 at 1 % / +0.5 dB | iterations, ms per decode near 1 % |
|---|---|---|---|---|---|---|---|---|---|
| r0906 | 3712 | F1 · 32 | 0.794 | 0.46 | 3560 / 3380 | 0.0120 | 0.0044 | 3 / 1 | 10.0, 3.36 |
| r0859 | 3520 | F1 · 32 | 0.715 | 0.40 | 3368 / 3188 | 0.0199 | 0.0089 | 3 / 0 | 15.4, 4.24 |
| r0781 | 3200 | F1 · 32 | 0.733 | 0.42 | 3048 / 2868 | 0.0350 | 0.0194 | 2 / 0 | 19.2, 5.01 |
| r0703 | 2880 | F1 · 32 | 0.759 | 0.44 | 2728 / 2548 | 0.0525 | 0.0330 | 2 / 0 | 29.0, 7.35 |
| r0625 | 2560 | F1 · 32 | 0.812 | 0.48 | 2408 / 2228 | 0.0724 | 0.0490 | 0 / 0 | 29.6, 7.21 |
| r0547 | 2240 | F3 · 64 | 0.848 | 0.50 | 2088 / 1908 | 0.0951 | 0.0712 | 1 / 0 | 53.5, 14.09 |
| r0469 | 1920 | F3 · 32 | 0.920 | 0.54 | 1768 / 1588 | 0.1207 | 0.0931 | 0 / 0 | 61.6, 16.33 |
| r0406 | 1664 | F3 · 32 | 0.999 | 0.60 | 1512 / 1332 | 0.1437 | 0.1130 | 1 / 0 | 67.0, 18.73 |
| r0359 | 1472 | F2 · 64 | 1.035 | 0.61 | 1320 / 1140 | 0.1627 | 0.1320 | 2 / 0 | 49.2, 14.06 |
| r0313 | 1280 | F2 · 64 | 1.022 | 0.57 | 1128 / 948 | 0.1834 | 0.1526 | 3 / 2 | 62.4, 17.13 |
| r0250 | 1024 | F2 · 32 | 1.107 | 0.60 | 872 / 692 | 0.2145 | 0.1816 | 9 / 3 | 51.3, 12.35 |
| r0203 | 832 | F2 · 32 | 1.216 | 0.66 | 680 / 500 | 0.2411 | 0.2077 | 9 / 1 | 68.8, 18.16 |

The gap-to-NA column is the rung-final gap minus the ladder table's
normal-approximation offset above Shannon at n 4096 and epsilon 0.01,
which runs from 0.317 dB at r0781 to 0.557 at r0203; the S3 records'
own `gap_na_db` at the five shared rungs reads 0.396, 0.413, 0.423,
0.478 and 0.489, a different estimator. p_cap is the capacity crossover,
1 − h(p) = R, which no code reaches; the next column is what the code
reaches. Iterations and milliseconds are the leaderboard's per-decode
numbers at the grid point nearest the 1 percent point, one worker of the
batched decoder; the rung finals at +0.5 dB read 4.5 iterations at r0906
and 32 at r0203, and the §1.2 table's cost at x_ref reads 2.64 and 22.21
ms [R]. Edge counts run from 15,936 to 17,664 [R records]. The bottom
two picks were accepted on the bar itself, 19 and 20 undetected in 2 by
10^5 pooled over acceptance and final, under the owner's ruling of
2026-10-24 ("Take the new picks"): the CRC covers integrity, and the
waterfall and the iteration cut are real [R R3; GBu]. The published
r0203 record also shows the lift's own weight gate failed, pair weight
81 against the campaign's target of 93 after four retries, while the
acceptance expectations (bars 24 and 20) were met; it was selected
under rank v4, rule a [R `r0203-z32.json`]. The silent-failure residue
at the worst measured undetected rate is near 1e-13 per attempt,
because a wrong codeword still has to match a 32-bit CRC [R §3.7; GBu].

### 5.3 Like for like at the shared rates

The frozen v1 codes under the v2 protocol against the SET-1 picks. The
v1 gaps are the twins' S3 walk; the v2 gaps are the rung finals, and v1
was not part of the paired final [A]. Undetected counts are per 10^5 at
the 1 percent point and at +0.5 dB. Cost is milliseconds and iterations
per decode, each code near its own 1 percent point, one worker [R twins
results; leaderboard]:

| rate | v1 gap dB | v2 gap dB | v2 gain dB | v1 BSC p at 1 % | v2 BSC p at 1 % | v1 undetected | v2 undetected | v1 ms, it | v2 ms, it |
|---|---|---|---|---|---|---|---|---|---|
| 0.859 | 0.812 | 0.715 | 0.097 | 0.0089 | 0.0089 | 9 / 5 | 3 / 0 | 2.47, 11.8 | 4.24, 15.4 |
| 0.781 | 0.789 | 0.733 | 0.056 | 0.0199 | 0.0194 | 11 / 6 | 2 / 0 | 3.67, 18.0 | 5.01, 19.2 |
| 0.703 | 0.843 | 0.759 | 0.084 | 0.0346 | 0.0330 | 3 / 1 | 2 / 0 | 6.05, 28.1 | 7.35, 29.0 |
| 0.625 | 0.899 | 0.812 | 0.087 | 0.0484 | 0.0490 | 41 / 32 | 0 / 0 | 6.05, 30.1 | 7.21, 29.6 |
| 0.547 | 0.981 | 0.848 | 0.133 | 0.0653 | 0.0712 | 8 / 1 | 1 / 0 | 6.09, 33.4 | 14.09, 53.5 |

[A] reads the same gains from v1's stored S4-corrected thresholds as
0.105, 0.065, 0.077, 0.075 and 0.137 dB, and 0.219 dB against r0550;
the difference to the column above is the correction method, within the
final's resolution. An earlier v2 pick at r0859 had read 0.747 against
0.812 [GBu]. The selection effect on the v2 side is bounded at about
0.01 dB [F] to 0.02 dB [R leaderboard header]. Density-evolution
thresholds put v2 at 0.18 to 0.27 dB from capacity against v1's 0.31 to
0.39 [GBo, unverified]. At the same noise level the 5,000-trial campaign
points Astra read put block failure at 2.04 falling to 0.48 percent at k
2880 and 4.10 falling to 0.76 percent at k 2240 [A, file not named].
Decode time per [A] rose from about 8.7 to 14.1 ms at k 2240 and fell
from 7.5 to 6.0 ms at k 2880, from separate campaign runs; [GBo]
measured about 30 percent fewer iterations at rate 0.7. The controlled
numbers in the cost columns disagree in direction at k 2880: cost rose
from 6.05 to 7.35 ms and iterations are equal, and at k 2240 iterations
rose from 33 to 54 [R; critic]. [GBo] also reports about 1.3 percent more
noise tolerance for v2 on its synthetic print proxy, and about 0.1 dB on
AWGN [GBo].

Reading. On AWGN v2 is better at every shared rate by 0.06 to 0.13 dB.
On the hard-decision channel the picture is mixed at the same
resolution: v1 is ahead at 0.703 and 0.781 by 0.05 to 0.10 dB-equivalent
(the crossovers 0.0346 against 0.0330 and 0.0199 against 0.0194), v2 is
ahead at 0.547 by 0.26, and 0.859 and 0.625 are ties; [GBo]'s BSC plot
shows the same ordering at 0.703. The BSC figures are simulated
thresholds, not permissible whole-page error rates [A]. The v2 search
ranked on BIAWGN with the BSC as a tie-break, so its gain is mostly a
soft-channel gain. Paper LLRs are soft but bounded at 7 to 12, so the
truth lies between the two columns and is unmeasured [F]. At r0703 the
0.08 dB is a crossover change of about 0.0015, invisible under the 1
percentage point content-dependent variance of experiment 013 [F]. The
ladder is spaced about 1 dB apart; near r0700 a tenth of a decibel is
about 1 percent of relative rate, a few tenths of a bit per square
millimetre against the 35 to 41 measured, and tile failures, pilot
overhead and LLR calibration are larger terms; the tenth matters when a
sheet is parked on the edge of a rung, where the waterfall is steep
[GBu].

Floors moved more than waterfalls [R twins README]: the frozen codes'
undetected words are almost all two-information-bit words of total
weight 4 to 7, which the CRC catches deterministically for every
information pattern of weight 3 or less and of weight 4 wherever k minus
p is at most 3000 [R `ladder2/lib/crc_cover.py`, §3.7]. The v2 codes'
undetected words are heavier and carry more information bits (weights 7
to 26, 1 to 12 information bits). "Undetected" in every research table
means parity-valid but wrong before the CRC, never a silently corrupted
file; heavier recurring words are caught every time or never for a fixed
code, so the 2^-32 model is a heuristic [A, R §3.7]. Observed rates near
1e-4 are not confidence guarantees that the true rate is below 1e-4,
and a minimum found weight is not a minimum distance [A].

### 5.4 Where v2 is actually better: reach

- r0906 gives 3560 user bits per tile at p120 against r0859's 3368,
  5.7 percent more, for the clean c3 rows at 0.06 to 0.5 percent cell
  error [F, R].
- The six rungs from r0469 down reach measured BSC crossovers of 0.093
  to 0.208 at 1 percent where v1's fragment rung r0547 reaches 0.065
  (the capacity crossovers, 0.12 to 0.24 against 0.095, are the ceiling
  no code reaches) [R records; critic]. A fragment needs about 18 to 23
  percent of a tile at the bottom rungs against 53 percent at r0547, by
  the attempt floor k minus p over the printed cells [F, from R]. Weak
  colour planes and the 10 to 15 percent channels have no v1 code at
  all.
- Decode cost is mostly the operating point: edge counts are similar,
  and low-rate tiles decode at a noisier channel point where belief
  propagation takes longer to settle [GBu]. It also depends on family at
  equal rate: SET-1's F3 r0547 takes 54 iterations against v1's 33, and
  PBRL roughly halved the iterations at the bottom [R; critic]. Before
  PBRL r0203 ran around 90 iterations; the published pick runs 32 at
  +0.5 dB and 69 near the 1 percent point [R].

### 5.5 Cost of switching

A new format version: a v2 loader with punctured nodes and Z 32, tokens
`ldpc-v2/<token>` (R5), capacity tables, goldens, the attempt-floor and
column-group arithmetic [R §10]. Single seed, codec simulation only,
nothing printed. A v1 printed codeword cannot simply be decoded with a
v2 matrix; a sign-adjusted LLR replay is only a surrogate under explicit
channel assumptions [A]. New codes enter under new immutable identities;
individual rate and configuration combinations are promoted after
candidate-specific physical qualification [A].

### 5.6 The cost spread

Near the 1 percent point the leaderboard reads 3.36 ms and 10 iterations
at r0906 against 18.16 ms and 69 iterations at r0203, a factor of 5.4 in
time; at x_ref the §1.2 table reads 2.64 against 22.21 ms, a factor of 8;
the rung finals at +0.5 dB read 4.5 against 32 iterations [R]. A sheet
has one rung, so the factor is between a clean sheet and a weak or
fragmentary one, not between neighbours on a page. A bottom-rung page of
about 840 tiles is on the order of 20 seconds for one worker if every
tile is decoded; the 1 percent that fail pay the full budget and the
retry, the rest exit early. Campaign runs took hours only because they
were 10^5 trials per point [GBu]. The scheduler prices an attempt and
can defer the 150-iteration retry. The spread becomes a problem only if
one placed window decodes many rungs at the long budget; once the format
row is known each tile is one code. A worse code should not be picked to
flatten a curve that a layered schedule, if it holds up, would flatten
directly [GBu].

## 6. Shortening at the bottom

### 6.1 The measured penalty

Every SET-1 record carries the S3 walk of the code shortened by 120 and
by 300 bits, each gap measured against Shannon at the shortened rate
(k−p)/(4096−p): the batched decoder at 60 plus sum-product 60, 5,000
trials per point on a 0.05 dB grid, resolution about 0.02 dB [R
`ladder2/codes/*.json`, `measured.s3.short_gap_db`; extracted 2026-10-27
by S]. Shortening removes whole circulants, (2, 5) block columns at Z 64
and (4, 10) at Z 32 [R `ladder2/lib/families_rank.py`]. Gaps in dB:

| rung | family · Z (pick / runner-up) | mother | p120 | p300 | runner-up mother | runner-up p120 | runner-up p300 |
|---|---|---|---|---|---|---|---|
| r0906 | F1 · 32 / F1 · 64 | 0.799 | 0.830 | 0.830 | 0.797 | 0.801 | 0.796 |
| r0859 | F1 · 32 / F1 · 32 | 0.715 | 0.711 | 0.731 | 0.723 | 0.725 | 0.742 |
| r0781 | F1 · 32 / F1 · 32 | 0.730 | 0.768 | 0.760 | 0.728 | 0.756 | 0.745 |
| r0703 | F1 · 32 / F1 · 64 | 0.746 | 0.775 | 0.780 | 0.756 | 0.765 | 0.773 |
| r0625 | F1 · 32 / F1 · 64 | 0.813 | 0.830 | 0.854 | 0.837 | 0.840 | 0.859 |
| r0547 | F3 · 64 / F3 · 64 | 0.842 | 0.826 | 0.894 | 0.873 | 0.850 | 1.018 |
| r0469 | F3 · 32 / F3 · 64 | 0.903 | 0.984 | 1.175 | 0.910 | 0.958 | 1.243 |
| r0406 | F3 · 32 / F3 · 64 | 1.016 | 1.056 | 1.125 | 1.004 | 1.046 | 1.112 |
| r0359 | F2 · 64 / F2 · 64 | 1.015 | 1.075 | 1.143 | 1.042 | 1.045 | 1.216 |
| r0313 | F2 · 64 / F2 · 64 | 1.046 | 1.073 | 1.244 | 1.012 | 1.068 | 1.309 |
| r0250 | F2 · 32 / F2 · 32 | 1.147 | 1.336 | 1.711 | 1.139 | 1.280 | 1.560 |
| r0203 | F2 · 32 / F2 · 64 | 1.233 | 1.485 | 2.164 | 1.278 | 1.270 | 1.893 |

The mother column is the S3 gap, not the rung final's, so it differs from
section 5.2 by the final's correction. The shortened rate at r0203-p300
is 0.14; at r0203 the 300 shortened bits are 36 percent of the
information side.

### 6.2 Reading

- Above r0547 shortening is free at both densities: at most 0.04 dB.
- Below it the penalty is large and not monotone in the shortened
  fraction: at p300 it reads 0.27, 0.11, 0.13, 0.20, 0.56 and 0.93 dB
  from r0469 down, so r0469 (F3, Z 32) is an outlier above its
  neighbours and the code matters as much as the fraction [critic].
- Rank v4 scored the unshortened mother. Every colour row runs at p120
  and K at p100, so the deployed configuration is the one the rank did
  not look at. At r0203 the runner-up (Z 64) beats the pick (Z 32) by
  0.21 dB at p120 and 0.27 at p300 with a mother 0.045 dB worse; at
  r0250 by 0.06 and 0.15. The r0203 difference at p120 is larger than
  any waterfall gain v2 made over v1 at a shared rate.
- The mechanism is visible in the published r0203 record (F2, Z 32, 129
  block columns of which 103 parity, 32 punctured nodes, information
  columns of degree 9 to 12, 2720 degree-1 extension parity nodes): its
  extension profile has rows with a single information edge, and when
  that column is shortened the printed extension bit becomes a
  repetition of a core parity bit: a second observation of one bit where
  the cell could have protected many. The
  structure block counts information-free rows for the mother only (0);
  the shortened code's count is not recorded.
- The §3.6 design rule orders the information columns by the PEXIT
  thresholds of the code shortened by its last two and last five block
  columns, "lowest-degree last" as the tie-break fallback, and PEXIT
  puts the heaviest class last at several rungs. PEXIT is exactly what
  Jayasooriya et al. report misranks punctured and degree-1 structures
  at low rate; [A] names full or hybrid density evolution plus earlier
  finite-length decoder measurements as the safeguards, and notes the
  repository already holds evidence of such misranking. Full density
  evolution is built (`ladder2/lib/de_full.py`), equals PEXIT within
  0.02 dB where no DE floor binds, and its optimiser is parked until a
  compiled kernel brings a threshold under about 10 s [R `docs/TODO.md`].
  The literature pass's own item 7 says shortening whole circulants
  chosen by PEXIT rather than the default tail changes thresholds by
  0.34 to 0.51 dB at 802.11n and 16e scale (Wei 2020) [R `LITERATURE.md`].
- The shortening paragraph of `docs/LDPC-LADDER-V2.md` §1.2 still
  carries the superseded F3 picks' penalties, 0.27 / 0.47 / 0.75 at the
  bottom three; the SET-1 F2 picks read 0.20 / 0.56 / 0.93, and [F]'s
  caveat of "up to 0.26 at p120 and 0.75 at p300" carried the stale
  figures.
- Pilot density is a free axis (the owner, 2026-10-27): K at 100, 150,
  200 or 300, cmy8 at any p above 100, cmy7 locked at p120; a higher p
  buys shredder resistance and calibration labels. The deployed defaults are p100 (K) and p120 (colour), every
  tile of a row alike; p300 is the second measured level and stands for
  the high-p rows the format allows and has not yet exercised. Nothing
  between or beyond is measured.

So the issue is real, part of it is a ranking artefact fixable from the
ledger, and part of it is structural: fixable by the shortening order,
or by designing the bottom rungs at their deployed configuration.

### 6.3 Mother codes at the printed length

An alternative raised 2026-10-27: mother codes of length 3996, 3896 and
3796 per rung, each already at a printed length, shortened by at most
100 bits to reach the lengths between. The coverage pass corrected the
first draft's arithmetic and premises here. What the ledger and the
bounds say:

- 3996 is the K row's printed length, and shortened by 20 it is the
  colour row's 3976, so a 3996 mother serves both existing rows
  directly; 3896 and 3796 would serve high-p rows, which the format
  allows and has not yet exercised.
- What a native code could recover, computed as the shortened pick's
  distance above a code sitting at the ladder-typical 0.66 dB over the
  normal approximation at the shortened length and rate [S, bounds
  reproduced against the ladder table]:

| rung | p | shortened rate | Shannon moves by, dB | pick's 1 % point moves by, dB | pick above NA at shortened length, dB | a native code would gain, dB |
|---|---|---|---|---|---|---|
| r0203 | 120 | 0.179 | 0.63 | 0.37 | 0.89 | 0.23 |
| r0203 | 300 | 0.140 | 1.82 | 0.89 | 1.48 | 0.82 |
| r0250 | 120 | 0.227 | 0.49 | 0.30 | 0.80 | 0.14 |
| r0250 | 300 | 0.191 | 1.37 | 0.81 | 1.12 | 0.46 |
| r0469 | 120 | 0.453 | 0.22 | 0.14 | 0.60 | 0.00 |
| r0469 | 300 | 0.427 | 0.59 | 0.31 | 0.77 | 0.11 |
| r0547 | 120 | 0.533 | 0.18 | 0.19 | 0.46 | none |
| r0547 | 300 | 0.511 | 0.46 | 0.41 | 0.52 | none |

  The mechanism is capacity moving away faster than the shortened code
  follows: shortening never raises a code's absolute threshold, but at
  r0203 the Shannon limit moves 1.82 dB between rate 0.203 and 0.140
  while the shortened code's 1 percent point moves 0.89 dB. At p120 the
  r0203 runner-up already sits at 1.270 dB, within 0.01 dB of that
  native-code estimate; at r0250 the runner-up recovers 0.06 of the
  0.14.
- Quasi-cyclic lengths are multiples of Z: the largest at or below the
  three printed lengths are 3968, 3872 (Z 32) or 3840 (Z 64), and 3776,
  so the residual shortening would be 20 to 56 bits. v2 also allows
  punctured nodes (R2), so a mother may be longer than the printed
  length and need no residual at all [critic].
- The cost is three times the codes, searches, frozen files, goldens,
  capacity tables and bootstrap descriptions, for a gain of 0.1 to 0.2
  dB at p120 at the two bottom rungs over the best existing codes and
  nothing above them.
- Extra shortening of the next rung up already gives intermediate user
  payloads from the existing mothers, and the cells it frees can carry
  calibration labels (section 7.4). Ladder spacing is answered by that,
  not by shorter mothers.

Position: a mother at the printed length pays only at the two bottom
rungs: by tenths at p120, and by up to 0.8 dB at p300, which is the
configuration a shredder-resistant row (high p, low rung) would use. At
the defaults the same tenths come cheaper from selecting, and if needed
lifting, those two rungs at p120 with the 4096 mother and
whole-circulant shortening; for high-p rows a mother designed at that p
is the right tool. Either path reopens the owner's ruling of 2026-10-24
on those picks (section 11).

## 7. The yardsticks and the challengers

### 7.1 Finite-length bounds on both channels

On AWGN the normal approximation at n 4096 and epsilon 0.01 sits 0.32 to
0.56 dB above Shannon by rung, and SET-1 sits 0.40 to 0.66 dB above it
at every rung [R §1, `docs/TODO.md`]. The normal approximation is an
ML-style estimate of the best code's performance, not a bound and not
BP-reachable [R §1.1]. No
belief-propagation code is known to close that at this length: every
published result within 0.3 dB of the bound uses OSD, ML or GRAND-type
decoding at n 1024 or shorter, and no 2023 to 2026 BP-class result at n
2000 to 8000 comes within 0.3 dB of it [F workers]. The workers' own
headroom estimate for a better BP code is at most 0.2 to 0.3 dB at the
middle and low rungs and 0.1 to 0.2 at the high ones [F workers,
derived].

The same bound on the BSC, computed 2026-10-27 [S; the AWGN half
reproduces the ladder table exactly]: with the crossover p_NA solving
R = 1 − h(p) − sqrt(V(p)/n) Q^-1(0.01) + log2(n)/(2n), and a
hard-decision-equivalent dB scale p = Q(sqrt(2 Es/N0)) so that both
channels read on one axis:

| rung | p Shannon | p NA | v2 p at 1 % | v2 share of NA | v2 above NA, dB-eq | v2 above NA on AWGN | v1 p at 1 % | v1 above NA, dB-eq | v1 above NA on AWGN |
|---|---|---|---|---|---|---|---|---|---|
| r0906 | 0.0120 | 0.0087 | 0.0044 | 0.50 | 0.84 | 0.46 | | | |
| r0859 | 0.0199 | 0.0155 | 0.0089 | 0.58 | 0.81 | 0.40 | 0.0089 | 0.81 | 0.49 |
| r0781 | 0.0350 | 0.0290 | 0.0194 | 0.67 | 0.75 | 0.42 | 0.0199 | 0.70 | 0.47 |
| r0703 | 0.0525 | 0.0451 | 0.0330 | 0.73 | 0.71 | 0.44 | 0.0346 | 0.61 | 0.52 |
| r0625 | 0.0724 | 0.0637 | 0.0490 | 0.77 | 0.71 | 0.48 | 0.0484 | 0.74 | 0.56 |
| r0547 | 0.0951 | 0.0851 | 0.0712 | 0.84 | 0.58 | 0.50 | 0.0653 | 0.84 | 0.63 |
| r0469 | 0.1207 | 0.1095 | 0.0931 | 0.85 | 0.63 | 0.54 | | | |
| r0406 | 0.1437 | 0.1316 | 0.1130 | 0.86 | 0.68 | 0.60 | | | |
| r0359 | 0.1627 | 0.1499 | 0.1320 | 0.88 | 0.65 | 0.61 | | | |
| r0313 | 0.1834 | 0.1700 | 0.1526 | 0.90 | 0.63 | 0.57 | | | |
| r0250 | 0.2145 | 0.2002 | 0.1816 | 0.91 | 0.68 | 0.60 | | | |
| r0203 | 0.2411 | 0.2262 | 0.2077 | 0.92 | 0.70 | 0.66 | | | |

On the hard side the ladder sits 0.1 to 0.4 dB further from its bound
than on AWGN, most at the top rate (0.41 at r0859) and least at 0.547
(0.08); at the bottom rungs the two channels read nearly alike. Paper
is neither channel, its errors correlated and its confidences imperfect,
with magnitudes bounded at 7 to 12 per capture.

### 7.2 The 5G cross-check

`docs/TODO.md` carries it as FUTURE: one 5G NR base graph (BG2, and BG1
at the top rates) lifted to n about 4096 at three shared rates, measured
on the twins harness under the production decoder; "it improves no rung;
it says whether any known construction does better at this length and
decoder"; a few hours. `ladder2/docs/LITERATURE.md` adopted the 5G and
PBRL pattern for the low half and the 5G graphs only as an external
benchmark, item 9. No published 5G NR or AR4JA curve at n about 4000
and 1 percent with its gap to the normal approximation was found by the
literature pass or by the workers [R LITERATURE "not confirmed"; F
workers]. [GBu] calls it the right yardstick, still unrun, and not
evidence that 5G is ahead. [A] calls 5G NR the most useful independent
reference, particularly BG2 at the lower rates.

[GBo] ran that comparison outside the project, with v1 r0700 and r0850,
v2 r0703 and r0859, and what it describes as an untuned 5G NR BG1 code
cut to 4096 printed bits at k 2880 and k 3520, through a numba copy of
the production decoder, on three channels, with about 3000 trials per
point on AWGN and BSC and about 2000 on the print proxy (zero-failure
points drawn at 0.5/N). The proxy's axis is a noise parameter sw with no
mapping to raw cell error. Read from the plots:

| k | channel | reading |
|---|---|---|
| 3520 | AWGN | v2 and 5G tie at the 1 % point near 2.70 dB; v1 about 0.1 dB behind; at 2.9 dB v2 reaches the zero-failure bound while 5G flattens near 7e-4 and v1 near 3e-3, which suggests shoulders in 5G and in r0850 (consistent with its weight-4 word) |
| 3520 | BSC | v1 and v2 tie; 5G about five times lower frame error at p 0.0085 to 0.0095 |
| 3520 | print proxy | v2 and 5G tie; v1 behind by about four times at the knee |
| 2880 | AWGN | v2 0.50 dB, 5G 0.56, v1 0.60 at 1 % [GBo text]; the 5G curve is steeper and crosses below v2 at 0.7 dB (about 3e-4 against 7e-4) |
| 2880 | BSC | 5G best, v1 second, v2 last, matching the repo's crossover order; at p 0.030 5G is about six times below v1 and ten times below v2, and all three converge near 1e-1 at p 0.039 |
| 2880 | print proxy | v2 slightly ahead of 5G (3.6e-3 against 5e-3 at sw 0.45); v1 about four times worse |

The lowest points rest on tens of failures, and the harness, the 5G
rate matching and the print proxy are unverified here. [GBo]'s own
reading is that the BSC result matters less because the receiver is
soft; this synthesis reads it the other way, because the paper channel's
magnitudes are bounded and the hard side is where the room is (7.1), so
the two positions stand against each other until the in-house run. Two
structural facts make the plot reading plausible: k 3520 is BG1 at
lifting size 160 exactly (2Z = 320 punctured high-degree systematic
nodes, where v2 capped punctured nodes at 128 under R2, and punctured
cells are free on paper); and v2 ranked on AWGN with the BSC as
tie-break. For k 2880 at rate 0.703, BG2's specified range ends at rate
2/3 [R LITERATURE §5G], so a standard-conformant code is BG1 with filler
or shortened bits (Z 144 leaves 288 fillers), which matches [GBo]'s
"untuned BG1"; k 3712 would be BG1 at Z 176 with 160 fillers, appended
after the CRC as known zeros and never transmitted [R LITERATURE §5G;
lifting sizes 144, 160, 176 from TS 38.212 Table 5.3.2-1, listed there
as not re-checked]. BG2 tops out at k 3840 and BG1 at 8448 [GBu]. A
2026 distance paper on BG1 at n 9984 shows minimum distance only in 8
to 14 and a floor a random code of that size would not have [GBu, arXiv
2607.04716, unverified]. 5G NR uses LDPC for shared data and polar for
control [GBu].

So the check is worth running, not for 0.1 dB on AWGN but because it
tests the ranking objective on the hard side of the channel, and because
a standard graph is documented outside this repository, which the
bootstrap chain can use. Matching must be exact: transmitted length,
useful bits, fillers, puncturing and decoder budget [A]. Standardization
alone does not make a code better on paper [A].

### 7.3 Polar with a CRC

Not in the project's 2026-10-18 literature pass: `LITERATURE.md` has no
entry [S]. [A] rates it the most useful challenger from a genuinely
different family: length 4096 fits naturally, soft inputs and the
existing CRC overhead fit the problem, and list size is a substantial
cost trade-off; benchmark representative rates before any thought of
replacement. [GBo] rates it not worth a switch at this length. The
numbers [F workers; GBu]: CRC-aided successive cancellation list
decoding at list 32 sits 0.63 to 0.79 dB above the normal approximation
at N 2048 in the fetched sources, 0.55 to 0.75 derived at 4096, at about
the same operation count as the LDPC decoder; against the ladder's 0.40
to 0.50 at the shared rates; list 128 buys about 0.13 dB more at four
times the work; a hybrid decoder reaches 0.025 dB from the
finite-blocklength capacity at n 128, rate 1/2 and block error 1e-3
(Piao et al.), and PAC codes match ML there with list 128 or sequential
decoding, gains that shrink at n 4096 where the decoder is a list or a
search, not 60 iterations of min-sum. The usual engineering split: polar
wins below a few hundred information bits, the two are comparable
through a few hundred, LDPC wins above about a thousand, which is also
where decoder parallelism starts to matter [GBu].

Two project-specific costs come on top [S; CRC accounting per critic]:

- The certificate. A list decoder uses the CRC to choose among L
  candidates. Each consultation of the CRC by a wrong candidate costs
  2^-32. Today the SET-1-class codes present a syndrome-valid wrong word
  in at most 1e-4 of attempts (about 2e-14 per attempt per consultation)
  and the deployed r0550 in 1.8e-3 (about 4e-13); cmy7's three
  consultations per attempt are a registered compromise [R `02-ldpc.md`].
  With list 32 every failed attempt presents 32 candidates: about 7e-9
  per failed attempt, 7e-11 per attempt at the 1 percent point, two to
  four orders of magnitude worse depending on the code it replaces. F9
  would need a second CRC outside the list, 32 more bits per tile, or a
  longer one.
- Known bits. LDPC pins any cell at minus infinity for free in mechanism
  (no new code, no new decoder), at the measured shortening cost of
  section 6. Polar shortening wants fixed codeword indices, and the
  pilot lattice is not that, so pilot cells would have to leave the
  codeword; in holo every tile of a row has the same p, so one frozen
  set per row suffices, which is workable.

A new format and a new decoder, with no gain on the numbers found, which
are derived and unverified.

### 7.4 The other families, and ladder spacing

| direction | assessment | sources |
|---|---|---|
| optimize the code against the actual decoder and channel | [A]'s strongest direction: published work optimizes finite length, channel, iteration budget and decoder behaviour (Elkelesh et al.); keep v2's machinery, change what it rewards; gains reported elsewhere are not promises here | A |
| AR4JA / CCSDS protographs | k 4096 at rate 1/2 with 100 AMS iterations sits 0.92 dB from Shannon, 0.65 above NA, against SET-1's 0.48 to 0.63; ties the high rungs only at longer lengths | F workers |
| long PBRL (k 16384) | 0.53 to 0.77 dB from Shannon at FER 1e-5, eight times the length and a harder target; at n 4096 and 1 % a 0.7 to 0.8 dB gap is what a good BP code looks like, and SET-1's top rungs are in that band | GBu, Chen et al. 2015 |
| 10GBASE-T (2048, 1723) | 0.72 dB above NA | F workers |
| rate-compatible families (one base graph, rate by k) | cost 0 to 0.2 dB at mid rates against per-rate codes; a 5G-style base graph or a protograph raptor-like family built with v2's tooling is the candidate if one is wanted; [GBo] recommends rebuilding the ladder this way | F workers, GBo |
| non-binary LDPC | 0.2 to 0.3 dB only against untuned binary codes at 20 to 70 times the operations ([F]'s closing message said 0.3 to 0.5; the worker figure is 0.2 to 0.3), GF(8) about 0 to 0.1 dB here; vector messages can retain information the bit marginals lose, but coupling colour planes compromises independent recovery when one plane collapses; these cells are binary and the 7-state colour path is already a demapper in front of a binary code; [GBo] would try it for the colour modes at much higher cost; [A] would test joint demapping around the binary codes first; colour only, if at all | F workers, A, GBo, GBu |
| OSD after BP | closes 1.2 dB of a 1.75 dB gap at n 128 and about 0.5 dB at (504, 252); at n 4096 and k 2240 order 2 is millions of re-encodings per failed tile, buying a BP-to-ML gap that the iteration study prices under 0.1 dB at the top and, on the SET-1 picks, 0.01 to 0.08 dB everywhere (8.5); a second decoder on failed tiles is a different machine from a new mother code; [F] calls it worth about zero at this length and rate; [A] a bounded rescue attempt, lower priority | F workers, GBu, A |
| spatially coupled, staircase, product codes | threshold saturation and floors near 1e-15 on long chains; coupling across tiles spends fragment locality and breaks tiles as fountain symbols; sub-block-local SC pays about 3.6 dB between local and global thresholds; finite-length and boundary trade-offs; [A] lower priority | F workers, GBo, GBu, A |
| generalized LDPC, product-like codes | listed as challengers in the synthesis turn; no number at this length was found | S |
| soft Reed-Solomon, BCH | hard RS discards confidence; soft RS needs substantial machinery; lower priority | A |
| DVB-S2 | blocks far too long for a tile | GBo |
| neural, KO-type codes | real at n 256 and below; not rebuildable from a seed and a docstring by a later reader | GBu |
| the PBRL add-on of Ro et al. 2025 | strengthens weak variable nodes and lowers PBRL floors; abstract verified by [A], no matched 4096 curves; a targeted experiment, not a redesign | A |
| RaptorQ (RFC 6330) | interesting only if the dense fountain gets too slow at scale | GBo |
| Project Silica | the same layering: LDPC plus checksum per sector, erasure coding across sectors | GBo |

[GBo]'s overall literature verdict: no clear winner at 2 to 3.5 kbit
with soft input. Most prior paper-storage systems use hard decoding,
Reed-Solomon or Golay with interleaving or XOR groups (Bulan and
Sharma's colour barcodes use soft LDPC decoding, per Astra's review,
unverified): PaperBack about 64 to 74 bits
per square millimetre marginal, Optar about 26, JAB Code regular LDPC
with bit-flipping, HiQ about 42.7, HCCB about 24.8, QR codes Reed-Solomon;
none beats per-tile LDPC plus CRC plus fountain by more than 5 percent
at equal length, and PaperBack's split is structurally this project's
with hard decisions [F workers; GBo].

Ladder spacing [GBo]: near rate 0.7 a tenth of a decibel is worth about
0.0075 in rate, while the 0.078 step between rungs wastes about 0.039 of
rate on average, roughly five times v2's gain; a family moving k in
steps of 32 to 64 would recover more payload than any waterfall gain.
Two corrections [S]: the fountain lets a rung run at a few percent block
error, so the real waste is less than half a step; and extra shortening
of the next rung up already yields intermediate user payloads from the
existing codes. "Rate" there means user bits per tile, not code rate:
r0781 shortened by 320 keeps rate 0.763 and gives r0703's payload with
320 cells freed for labels instead of parity, so the measurement (r0781
shortened by 160 and 320 against r0703 native, twins harness) pits 320
parity cells against 320 label cells [critic]. A finer ladder does not
need new codes until that measurement says so.

## 8. Decoder items not applied

### 8.1 The sum-product blind spot

Confirmed in code 2026-10-27 [S; first reported by A].
`src/holo/receiver/lib/ldpc.py:176` runs the sum-product pass only when
the min-sum syndrome fails. A min-sum pass that lands on a
syndrome-valid wrong word returns clean; the CRC fails at
`format/tile_codec.py:247`; the attempt is FAILED; `plugins/tiles.py:382`
arms retry150 on the same evidence, which is the same deterministic
trajectory to the same word; sum-product is skipped again. Stages that
run on different evidence (union, local150, uplift, planek150, swim150,
cond150) can still reach sum-product when min-sum fails there [critic].
[A]'s replay of recorded failure seeds found 61 such min-sum outcomes
and recovered 3 by forcing SP60 from the original evidence:
selected-case evidence on unshortened Gaussian trials, not a population
estimate, and [A] expects only a small overall gain. For the receiver's
own codes the class runs at 1.8e-3 of attempts for r0550 and 1.1e-4 for
r0775 at their 1 percent points, and on paper at higher raw error it is
unmeasured; for the SET-1 picks it is at most about 1e-4 (11 per 10^5 at
r0203). The attempt facts record syndrome_ok and crc_ok but are not
persisted in snapshots [R `src/holo/receiver/snapshot.py`], so the count
is a replay with attempt logging. The fix, CRC-aware alternate decoding, is
bounded and backward compatible [A], and adds one CRC consultation per
failed attempt to the budget of 7.3.

### 8.2 Layered scheduling

`LITERATURE.md` item 6 adopts it together with degree-dependent
normalization; the analyzer carries it as an L2 arm and second workhorse
(damped 151 plus layered 65 of 508 certificates); the receiver runs
flooding [R `analyzer/DESIGN.md` L2]. Hocevar's result is the same
waterfall in about half the iterations; for the long PBRL codes of Chen
et al. the two schedules differ by under 0.05 dB at 100 iterations [R
LITERATURE §PBRL]. [F workers]: about 0.15 dB at equal 33 iterations, at
most 0.1 at 60.

Where it lands, corrected against the SET-1 records [critic]: the R6
paragraph of `docs/LDPC-LADDER-V2.md` §1.2 measured the pre-PBRL picks,
where 60 to 150 iterations gained 0.01 to 0.03 dB on the top rungs, 0.03
to 0.08 through the middle, and 0.19, 0.12 and 0.35 dB at r0313, r0250
and r0203 at 1.6 to 1.9 times the CPU; [GBu]'s argument that the cap
costs decibels only at the bottom rests on those numbers. The published
SET-1 picks gain 0.012 to 0.078 dB from 150 iterations on every rung
(0.074, 0.057 and 0.078 at the bottom three), because the PBRL change
already collected the bottom-end gain. So on SET-1 a layered schedule is
a cost item, halving the iterations and the cost spread of 5.6, not a
waterfall item. [GBu] still ranks it the one avenue worth measuring; [A]
would judge it by recovered payload per CPU second rather than iteration
counts, and notes it benefits already printed material. The uncertainty
is the floor: a different schedule can change which trapping sets fire,
so the 10^5-trial undetected counts would have to be rerun [GBu].

### 8.3 Degree-dependent normalization

`LITERATURE.md` item 6 adopts per-check-degree normalization designed by
density evolution for min-sum, paired with the layered schedule;
unbuilt. Zhang, Fossorier, Gu and Zhang (GLOBECOM 2005, MERL TR2005-158)
on a length-16200 irregular code: belief propagation threshold 0.77 dB,
single-scale min-sum 0.90, degree-dependent 0.85, so about 0.05 of a
0.13 dB gap, on a different code, at the threshold [GBu]. A
two-dimensional scheme (alpha per check degree, beta per variable
degree) is worth about 0.3 dB over single-alpha at 200 iterations, but
the sum-product retry already collects most of that, so the end-to-end
gain is at most 0.05 to 0.1 dB [F workers]; what it would still buy is
fewer tiles entering the retry and possibly a slightly lower floor than
belief propagation on approximation error [GBu, F workers]. It does not
remove low-weight codewords; those are in the matrix and the CRC already
turns them into erasures [GBu]. [GBu] does not expect it to move a rung;
[A] would measure it by recovered payload per CPU second. Learned decoder
weights equal degree-shared weights at 50 or more iterations; floor
post-processing is irrelevant at 1 percent [F workers].

### 8.4 A low-clip retry stage

[GBo]'s CRC-gated retry with LLRs clipped to 2 to 5 recovered about 15
percent of burst failures with no false accepts, on its synthetic
channel. It is the per-scan saturation of 4.3 applied at the decoder
instead of the combiner, and it would be an attempt stage, priced by the
scheduler like retry150 and entered in the CRC budget of 7.3.

### 8.5 The iteration cap and demapping

At the bottom rungs raising the cap from 60 to 150 was worth 0.12 to
0.35 dB on the pre-PBRL picks and is worth 0.06 to 0.08 dB on the SET-1
picks (8.2). Three demap-decode passes capture nearly all of the
turbo-demapping gain, which cmy7 already runs; the gain is about zero
with Gray labelling and equalized interference [F workers].

## 9. Beyond the matrix

The inner code sits 0.40 to 0.66 dB above the finite-length bound, an
estimate of the best code under a strong decoder, and no
belief-propagation code at this length is
known to come within 0.3 dB of it. A new family on the tile re-spends
part of that margin for tenths at most. The failures that dominate are
in the LLRs [GBu, F, A, GBo]. Directions, all outside the matrix:

- **The magnitude should carry the geometry, not only the ink.**
  Depress the LLR where the pose residual, the pitch fit or the
  neighbour model disagrees; erase, do not clamp [GBu, F workers].
- **One round of feedback inside the tile.** DESIGN §6 called joint
  equalization and decoding the cheapest large gain in the system. The
  decoder already returns an extrinsic LLR; feeding the confident part
  back as labels, refitting the local score-to-probability map, and
  decoding once more stays inside the tile, so the tile still certifies
  from its own scraps' merged evidence. The analyzer prototyped that
  loop. It is a photometric
  iteration, not a second code [GBu].
- **Joint neighbour detection.** Detect the dot-gain correlation
  between neighbouring cells jointly and iterate with the decoder
  (Marrow and Wolf) [GBo]. Zhang, Chen and Mow model the print-capture
  channel as spatially nonlinear, nonstationary and input-dependent and
  gain from soft LDPC with channel estimation; the mechanism transfers,
  the numbers do not [A].
- **Per-scan selection and recalibration** before any sum (4.3).
- **Certified neighbours as labels.** Shared information between
  neighbouring tiles belongs in the channel estimate: a certified
  neighbour is a better label source for the next window's calibration.
  It is not a parity check that should reach across a tear [GBu].
- **No parity across a tear.** Coupling tiles into one page code runs
  against the fragment requirement; the page-level mechanism that
  matches it is the fountain [GBu, GBo, F workers]. Correction
  (2026-10-27, Grok Build's review): the unit of certification is the
  tile, not the physical piece. Pilots place scraps into cell
  coordinates and a torn tile is decoded from the weighted-sum union of
  the scraps that cover it [R `docs/PILOTS-DESIGN.md` §15.2, §15.7]; the
  certificate is the tile's, so the merged evidence certifies, never a
  scrap on its own. The codeword stays
  tile-sized so that merge is spent finishing one tile; "a fragment
  certifies alone" elsewhere in this record means that, not that a
  scrap decodes by itself.

## 10. The system split

[F workers] On a channel uniform across tiles the 1 percent inner
target is already optimal within 0.3 percent of throughput; the
published "optimal inner block error 10 to 30 percent" results are
fading results. With a per-tile quality spread of 0.5 dB, retargeting
gains 2 to 3.5 percent; at 1 dB, 3 to 13 percent. Pooling soft
information across tiles has a 10 to 60 percent ceiling at those
spreads; no printed or optical system demonstrates it, and it costs
fragment locality. Assigning rate by position at write time captures
part of that gain at zero locality cost, which the per-plane rungs
already do and per-region rungs would extend. In the fountain, 2^-delta
is the probability that a block still fails with K plus delta symbols,
and the expected excess is about 1.6 symbols per block [R
`docs/FOUNTAIN-DESIGN.md`]. The deciding number is the per-tile capacity
spread on real scans, which the snapshots hold (4.4).

## 11. Positions and the objective

The synthesis' positions, none ruled on by the owner as of 2026-10-27.
Where a position departs from one of the four assessments or would
reopen an owner ruling, the line says so.

1. v1 stays the law for every printed row (repo law); its loader and
   matrices are kept forever, including for the bootstrap material.
2. SET-1 is not abandoned and not replaced. It is the ladder of the next
   format version for the customers v1 cannot serve: the top rung for
   lossless c3 rows, the bottom rungs for fragments and weak planes
   [with A, GBu, F]. [GBo] would retire r0850 and rebuild the ladder as
   one rate-compatible family; this synthesis does not, for the reasons
   in 7.4. [A] would retain v2 and qualify it selectively, benchmark
   first; [GBu] would freeze SET-1 as it stands.
3. No lifting search is reopened under the current objective [with GBu,
   whose reason is that the last campaigns found the top rungs limited
   by the finite-length bound and the bottom rungs by the floor bar;
   with A, who warns against searching more seeds under the current
   objective]. If the ladder is re-judged it is re-ranked first: every
   S3 walk recorded its BSC point and its p120 and p300 points, so a
   rank on the deployed configuration and on the hard channel costs
   nothing to compute from the ledger. A bounded-LLR channel with a
   confidently-wrong fraction of 0.1 to 0.5 percent of cells, the
   channel paper presents [F], is not in the ledger and is a new
   twins-harness run of a few hours (section 12).
4. The two bottom rungs would be selected at p120 from the ledger, and
   lifted there if the runner-ups still disappoint. This departs from
   [GBu]'s freeze-as-is and would reopen the owner's ruling of 2026-10-24
   ("Take the new picks") and the stop of the search; it is proposed,
   not taken.
5. The quantity to optimize is useful bits per tile times the
   probability of correct certification, per area and per CPU-second,
   adjusted for fountain rank and decoding cost [A]. A better 1 percent
   threshold is evidence; it is not the deployment decision. Any
   regeneration gives deployed shortening, burst geometry and decoder
   cost direct weight and keeps the existing structural safeguards and
   the mix of families [A]; PBRL stays the leading low-rate family [A].
6. What the rank rewards changes before the lifting tooling runs again
   [A]; the machinery already selects through the production decoder
   (Elkelesh), so the objective is the only difference [S].
7. CRC exposure is a budget, not an axiom. Every consultation of the CRC
   by a candidate decode costs 2^-32 per wrong candidate; the production
   chain already consults it per stage on different evidence and up to
   three times per cmy7 attempt as a registered compromise [R
   `02-ldpc.md`]. Any decoder change states its CRC consultations per
   attempt and enters that budget: 8.1 and 8.4 add one each per failed
   attempt, a polar list decoder adds L [critic].
8. Codes enter the format under immutable identities and are promoted
   per rate and configuration after physical qualification [A].
9. Standard graphs, if one measures as well as the ladder, carry a
   documentation value for deep time that a seeded draw does not.
10. The existing calibration and conditional-demapping mechanisms (PAVA,
    cmy8, the cmy joint model, cmy7 iteration) are retained and credited
    in every comparison with an alternative [A].

## 12. Measurements, by information per hour

| # | measurement | harness and cost | decision it informs |
|---|---|---|---|
| 1 | re-rank the bottom rungs on the ledger's p120 and p300 numbers | none; the records hold them | the two bottom picks (reopens the 2026-10-24 ruling) |
| 2 | count syndrome-ok, CRC-fail attempts on a replay with attempt logging (attempt facts are not persisted in snapshots) | a replay of one sheet | forcing sum-product on that outcome, a few lines, receiver-side, benefits printed sheets; expected gain small [A] |
| 3 | the 5G rerun: BG1 at 160 for k 3520, BG1 at 144 with 288 fillers (or BG2 outside its rate range, stated as such) for k 2880, BG1 at 176 with 160 fillers for k 3712; AWGN and BSC | twins harness; a few hours | the ranking objective; the punctured-node cap; a standard graph as a documented alternative |
| 4 | the six v1 twins and the twelve SET-1 codes on a BIAWGN with LLRs clipped at 7 and a confidently-wrong fraction of 0.1 to 0.5 percent [F] | twins harness; about half an hour per channel point set | whether the 0.1 dB transfers to a paper-like channel; the rank of position 3 |
| 5 | reliability audit per stage against certified truth, and per-tile GMI spread | existing holo3 snapshots; hours | which LLR stage to fix first; whether per-tile spread justifies rate by region |
| 6 | the multi-scan combining fix: recalibrate the combined score, selection, per-scan saturation, and a clip-5 retry stage on union failures | multi-capture holo sheets behind the union stage (experiment 013's scans are paperholo-format and need the v1 stack); days | the oldest measured loss |
| 7 | shortening structure at the bottom: information-free rows after shortening per candidate and order; the order variants on the existing picks; a lift of r0203 and r0250 at p120 (departs from [GBu]'s freeze-as-is; reopens the ruling) | ladder2; hours to a day | the bottom-rung codes |
| 8 | layered schedule and degree-dependent normalization in the batched twin, twelve rungs, undetected counts rerun; judged by recovered payload per CPU second [A] | ladder2; hours | a receiver-side decoder change, mostly cost on SET-1 |
| 9 | extra shortening as a finer payload ladder: r0781 shortened by 160 and 320 against r0703 native, parity cells against label cells | twins harness; half an hour | whether ladder spacing needs new codes |
| 10 | polar list-32 at 4096 on the same harness | new code; a day | closes the question with a number beside the certificate arithmetic |
| 11 | the application benchmark: p120 and p300 framing per [A] (p100 and p120 are the defaults; higher p is lawful), spatial error patterns, fragment masks, repeat captures, held-out acquisitions; certified useful bits per area, per computation, full fountain recovery | receiver on real scans for v1; for v2 it needs a v2 loader and a printed v2 sheet, a physical run on its own go, or the surrogate 5.5 rejects; days plus | the deployment decision for any code; Gaussian and BSC stay diagnostics [A] |
| 12 | v2 against 5G and a bounded polar challenger at identical useful payload and computation | twins harness; after 3 and 10 | whether any regeneration is warranted [A] |
| 13 | the Ro et al. add-on on one bottom rung | ladder2; hours | a targeted PBRL floor experiment [A] |
| 14 | re-measure the 0.1 dB with real scans through the PAVA LLRs, and exercise the cmy7 iterative path, which no external harness touched | same constraint as 11 for v2 | whether the soft gain transfers [GBo] |

[A]'s own order of work differs from this table: first the application
benchmark (11), then decoder improvements on existing v1 material (2, 8,
6), then v2 against 5G and polar (12), then regenerate only where the
benchmark finds a deficit (7), then new immutable identities. The table
above orders by information per hour; both orders agree that the
benchmark decides deployment and that regeneration comes last.

Things to consider beside the table: the second loader's place in the
bootstrap chain; the stale paragraphs in `docs/LDPC-LADDER-V2.md` §1.2
(shortening, and the R6 iteration numbers) and in `docs/FEC-DESIGN.md`
("NOT merged"); what the floor bar means once the CRC is counted; the
cost spread at the bottom and the scheduler; that `docs/TODO.md`'s
framing of the 5G item as improving no rung predates [GBo]'s curves; and
that the decoder-side and input-side work in sections 4, 8 and 9 is
where the remaining decibels are.

## 13. Appendix: external sources named by the assessments

Verified in no harness of this project unless a section says otherwise.

- Polyanskiy, Poor, Verdú: the normal approximation (section 7.1).
- Chen, Vakilinia, Divsalar, Wesel, IEEE Trans. Commun. 2015, arXiv
  1403.2111: protograph-based raptor-like codes [GBu, GBo].
- Richardson and Kudekar 2018; 3GPP TS 38.212: 5G NR LDPC [R
  LITERATURE; A; GBu].
- arXiv 2607.04716: BG1 minimum distance at n 9984 [GBu].
- Tal and Vardy, arXiv 1206.0050: list decoding of polar codes [A].
- Piao, Niu, Dai, Dong, arXiv 1910.03254; Li, Yao, Abbe, arXiv
  2005.13711: polar and PAC at n 128 [GBu].
- Zhou et al., arXiv 2306.00443: OSD after BP [GBu].
- Zhang, Fossorier, Gu, Zhang, GLOBECOM 2005, MERL TR2005-158:
  degree-dependent normalization [GBu, A, R LITERATURE].
- Hocevar, SiPS 2004: layered decoding [GBu, GBo, R LITERATURE].
- Elkelesh et al., arXiv 1903.03128: decoder-in-the-loop code design [A].
- Jayasooriya et al., arXiv 1605.04665: PEXIT misranking at low rate [A].
- Ro et al. 2025: PBRL add-on structure [A].
- Butler and Siegel, arXiv 1202.2826: saturation and floors [A; R
  LITERATURE item 8].
- arXiv 1111.7265: mismatched LLR correction [A].
- Alvarado et al.; Nguyen and Lampe: generalized mutual information and
  BICM mismatch [A].
- Davey and MacKay; arXiv 0805.1327: non-binary LDPC, BICM analysis [A].
- Cheng (uOttawa): soft-decision Reed-Solomon decoding [A].
- Chalmers publication 530220: finite-length spatially coupled codes [A].
- Marrow and Wolf, ITW 2003: joint detection for two-dimensional ISI
  [GBo].
- Zhang, Chen, Mow: print-capture channel modelling and estimation [A].
- Mei: selection against linear combining under impulsive noise [F
  workers].
- Wei 2020: whole-circulant shortening patterns [R LITERATURE item 7].
- Karimi and Banihashemi, arXiv 1902.07332: trapping sets in QC
  protograph codes [R LITERATURE].
- RFC 6330 RaptorQ; Project Silica; PaperBack, Optar, JAB Code, HiQ,
  HCCB, QR [GBo, F workers].

## 14. Glossary

- **NA, normal approximation**: Polyanskiy, Poor and Verdú's
  approximation of the best achievable rate at length n and block error
  epsilon, an ML-style estimate, not a bound and not BP-reachable; here
  n 4096, epsilon 0.01.
- **gap**: Es/N0 at 1 percent block error minus the Shannon limit at the
  code's rate, on BIAWGN, in dB; **gap to NA** the same against the
  bound.
- **p at 1 %**: the BSC crossover probability at which the code reaches
  1 percent block error; **p_cap** the capacity crossover, 1 − h(p) = R.
- **S3, S4**: the v2 selection stages of `docs/LDPC-LADDER-V2.md` §3.4:
  S3 the 5,000-trial confirm walk and its BSC and shortened walks, S4
  the two 10^5-trial acceptance points at the 1 percent point and at
  +0.5 dB.
- **rung final, x_ref**: every contender of a rung decoded at one Es/N0
  x_ref and at x_ref + 0.5 dB on one fresh trial range; **rank v4, rule
  a**: the leaderboard's ranking and the campaign's undetected bar of at
  most 1e-4 at both S4 points.
- **R2, R3, R5, R6**: rulings in `docs/LDPC-LADDER-V2.md` §9: punctured
  state nodes at most 128 per code; the floor bars; v2 token naming; the
  selection decoder is the production identity.
- **F9**: the certification discipline, syndrome AND CRC, in
  `02-ldpc.md`. **018.7**: the incident and invariant that bound every
  LLR by its own label count.
- **F1 to F5**: the v2 code families (IRA, PBRL, punctured XOR-state,
  near-regular, accumulator precode), not the experiment-013 findings
  F1 to F4, which are named with their experiment.
- **e-IRA**: extended irregular repeat-accumulate. **QC**: quasi-cyclic.
  **PEG, ACE**: progressive edge growth lifting; approximate cycle
  extrinsic message degree. **PEXIT**: protograph EXIT-chart threshold
  analysis. **DE**: density evolution. **PBRL**: protograph-based
  raptor-like. **NMS, SP**: normalized min-sum, sum-product. **AMS**:
  adjusted min-sum. **OSD**: ordered-statistics decoding. **GRAND**:
  guessing random additive noise decoding. **PAC**: polarization-adjusted
  convolutional codes. **SCL**: successive cancellation list decoding.
  **BICM**: bit-interleaved coded modulation. **GMI**: generalized mutual
  information. **QDA**: the quadratic discriminant colour-state model of
  cmy8. **PAVA**: pool-adjacent-violators isotonic regression.
- **c1 to c8**: the v2 campaigns; **c3 rows**: the clean format rows at
  0.06 to 0.5 percent cell error; **W8, T1, L2, L7c, I7**: analyzer work
  packages, arms and measurements in `analyzer/DESIGN.md` and
  `analyzer/APPROACHES-2026-09-06.md`.
- **twins**: `measure/ladder2-v1-twins`, the frozen v1 codes run under
  the v2 protocol; **the 2026-10-01 confirm**: the earlier v1 confirm
  walk whose waterfalls the twins reproduce within 0.01 dB.
