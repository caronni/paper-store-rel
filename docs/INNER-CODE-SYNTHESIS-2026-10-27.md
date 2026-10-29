# Inner code and LLR chain: what moves the needle

2026-10-27. The conclusions of four independent assessments of LDPC v1,
LDPC v2 (SET-1), the LLR chain and the literature, reduced to what bears
on the next actions. The provenance of the ladder and ledger numbers is
in `docs/INNER-CODE-SYNTHESIS-2026-10-27-RECORD.md`, sheet-level
numbers cite their experiment files inline, and numbers from the
external assessments and their literature searches are unverified in
this project and are marked so here. Nothing here is a ruling; the
decisions the owner would have to take are listed in section 8. The
designs of record stay `docs/FEC-DESIGN.md`, `docs/LDPC-LADDER-V2.md`,
`docs/P-AXIS-DESIGN.md`, `docs/PILOTS-DESIGN.md` and the receiver's
`API.md`, `SCHEDULE.md` and `conversion_docs/02-ldpc.md`. To learn what
v2 is, read `docs/LDPC-LADDER-V2.md` §1.2 or the record's section 5;
this document only says what to do about it.

**Terms used throughout.** A *rung* is one code of a ladder; v2 names
follow the true rate (v2:r0703 is k 2880 of 4096), v1 names are
historical labels (v1:r0700 is also k 2880; v1:r0547 and v1:r0550 are
two draws at k 2240; v1:r0850 and v2:r0859 are different codes at rate
0.859). *p* is the pilot density, the furniture sites per tile, shortened
out of the code. The *soft channel* is BIAWGN; the *hard channel* is the
BSC, whose *crossover* is the bit-flip probability at which a code reaches
1 percent block error, the *1 percent point*. The *gap* is Es/N0 at that
point minus the Shannon limit at the code's rate, in dB. *The bound* is
shorthand for the finite-length normal approximation at n 4096 and 1
percent: an estimate of what the best code reaches under a strong
decoder, not a converse bound, and not BP-reachable
(`docs/LDPC-LADDER-V2.md` §1.1). *dB-eq* converts a
hard-channel crossover to an equivalent Es/N0 through p = Q(sqrt(2
Es/N0)), so both channels read on one scale. A tile *certifies* when its
syndrome and its CRC-32 both pass; a sheet *closes* when the fountain
recovers the file. The *attempt floor* is the smallest number of
observed cells at which the receiver will try to decode a tile, a
counting floor, not a recovery threshold. The *twins harness* is the
batched bit-exact copy of the production decoder on which both ladders
were measured; *the ledger* is every candidate's recorded walks,
including each code shortened by 120 and by 300 bits. The *four
assessments* are Astra, Grok Bots, Grok Build and Fable; the first
three ran outside this repository, and Grok Bots is the one that ran
simulations. Actions are numbered A1 to A17 in section 7, and the short
version uses the same numbers.

## The short version

The inner code is not where the yield is. v1 sits 0.47 to 0.69 dB above
the bound on the soft channel and SET-1 0.40 to 0.66, and nothing in the
literature closes that with a belief-propagation decoder at this length.
What loses tiles on paper is what reaches the decoder: over-confident
cells, slip bursts, and evidence combined as if independent. None of it
is sized on paper yet. The one sized instance, 12 tiles of 72 lost to
naive scan summing in experiment 013, is simulated, and holo3's
scan-first scheduling already avoids it. The largest measured losses on
real sheets, the M and Y planes certifying 43 and 0 of 840 tiles on
e030's c3 sheet (`experiments/030-holo-cmy8-hp-canon.md`), are detector
and colour-model losses. That is receiver work, and it helps
every printed sheet.

v2 is worth having for reach, not for the shared rates. At the five
rates both ladders cover it buys 0.06 to 0.13 dB on the soft channel, a
mixed result on the hard one, and costs more per decode at its own
operating point. Its value is the rungs v1 lacks: a top rung carrying
5.7 percent more per tile on clean rows, and six fragment rungs whose
attempt floor falls from 53 percent of a tile to 45 and then 18
percent. Recovery at those floors is unmeasured. v1 stays the law for
every printed sheet.

The one real defect found is at the bottom of v2. Its two lowest codes
were ranked unshortened, and no tile is decoded that way. At the colour
default p120 a re-rank from the ledger recovers 0.21 dB at v2:r0203 and 0.06
at v2:r0250; at the one high density measured, p300, which is what a
shredder-resistant row would run, a code designed at that density is
the candidate for up to 0.8 dB more, conditional on such a code being
built and measured. Pilot density is a free axis for K and cmy8, and its
calibration value, the other thing a higher p buys, has never been
measured.

**Do next**, numbered as in section 7. Costs are one
worker; snapshots keep poses and decisions, not evidence or attempt
facts, so anything that reads evidence or attempts is a replay of the
stored captures, not a lookup.

- A1 Count syndrome-ok, CRC-fail attempts on a replay with attempt
  logging and force sum-product on that outcome. Recoverability; the
  class is at most 18 percent of v1:r0550's failures at its 1 percent
  point, and a selected replay recovered 5 percent of the class. A
  replay of one sheet, then a few lines.
- A2 Break the same replay's attempts down by stage and outcome.
  Execution; e030 spent 35,281 LDPC calls on 663 certificates, and sheet
  D's 909 of 1,553 certificates came from retry stages at 3,086 cpu-s.
  The LDPC layer is a small share of sheet cpu, so this prices the
  attempt economy, not the decode.
- A3 Audit the LLR chain against the emitted field, failed tiles
  included, stage by stage and plane by plane, with the pilot labels
  subsampled per window. Recoverability; decides which of A7 to A10 to
  build and prices the calibration side of a higher p. A replay with the
  evidence kept, about a day.
- A4 and A6 Run all eighteen codes on a bounded-LLR soft channel with a
  confidently-wrong fraction, and the 5G graphs beside them. Decides the
  ranking objective and whether v2's 0.1 dB transfers. Half an hour per
  channel point set for the codes; a day to build the 5G construction.
- A12 Re-rank every rung on the ledger's hard-channel and shortened
  points. Free; effective only once SET-1 is integrated; reopens the
  ruling of 2026-10-24 on the bottom picks.
- A11 Layered scheduling, measured on the six v1 codes first as cpu per
  recovered payload at a fixed budget. Execution; about half the
  iterations at every rung by Hocevar's result, time per iteration and
  the effect on which tiles certify unmeasured.
- A14 A v2 loader and format version for the rungs v1 lacks. Reach.
  Days, plus a printed qualification sheet on its own go.

## 1. The needles

| needle | measured as | where it stands | what moves it |
|---|---|---|---|
| recoverability | tiles certified per page; raw cell error tolerated; fragment size that still certifies | holo3: v1:r0850 read sheet H to 100 percent (e036, cmy8 p120, 5,883 tile-streams) and closed sheet D at 5.8 percent raw error (e039, 1,553 certificates of 1,961 tiles); v1:r0700 at c1 gave nothing at 22 percent raw (e039 sheet E); e030's c3-cmy8 sheet certified C 620, M 43, Y 0 of 840 tiles per plane (`experiments/030-holo-cmy8-hp-canon.md`). v1 stack density reference, simulated: 40.8 bits per mm² at 100 percent tiles, 35.7 at 87.5 (e013). Attempt floor 53 percent of a tile at v1:r0547; fragment recovery unmeasured | the detector and colour model first, then the LLR chain; the fragment rungs; p-aware codes at the bottom |
| reach | rates and channels a code exists for | v1 0.547 to 0.859; SET-1 0.203 to 0.906 | integrating SET-1 in the next format version |
| execution | cpu-s per closed sheet; LDPC calls per certificate; ms per decode | sheet D: 3,086 cpu-s, 909 of 1,553 certificates from retries; e030: about 53 LDPC calls per certificate; per decode v1 2.5 to 6.1 ms, SET-1 3.4 to 18.7 ms near each code's 1 percent point; a c3 page is 840 tiles, c2 1,961, c1 7,844. Placement is about 99 percent of K cpu at p300 (`docs/P-AXIS-DESIGN.md` §3), so the LDPC layer is a small share | placement and detection cost first; attempt economy; a layered schedule |
| certification safety | wrong certificates | 0 in 69,066,304 audited cells of certified tiles; under the random-CRC model each consultation by a wrong candidate passes at 2^-32, and for a fixed pattern the verdict is deterministic | nothing that consults the CRC more often without entering the budget |
| deep time | can a reader rebuild the code from the documents | v1 from a docstring and a seed; SET-1 from frozen JSON | a standard graph, if one measures as well |

## 2. Where the inner code stands

**v1.** Six frozen extended-IRA codes of length 4096, one slot per cell
of a 64 by 64 tile, five rates from 0.547 to 0.859. Pilots are
shortened information bits, erasures are LLR 0, a tile certifies on
syndrome and CRC-32 together. The production decoder runs normalized
min-sum at 60 iterations and one sum-product retry of 60 from the
channel LLRs. On the soft channel the codes sit 0.79 to 1.05 dB from
Shannon and 0.47 to 0.69 above the bound. All six carry
two-information-bit codewords, of weight 4 to 7 at five of them, which
the CRC catches outright, and heavier words it catches under the
random-CRC model; the frames are wasted, and no wrong certificate has
been observed. Three of them
(v1:r0775, v1:r0625, v1:r0550) fail v2's undetected-word bar;
v1:r0850 passes it at the edge, with a weight-4 word, and still closed
sheets.

**v2, SET-1.** Twelve quasi-cyclic codes, rates 0.203 to 0.906, three
families by rung (irregular repeat-accumulate from v2:r0906 to v2:r0625,
punctured-state graphs from v2:r0547 to v2:r0406, raptor-like
protographs below, the bottom constructions having been tried upward
and lost), all on one decoder, selected through the twins harness over
fifty million decodes, merged to main on 2026-10-24, not printed and not
integrated. They sit 0.72 to 1.22 dB from Shannon and 0.40 to 0.66 above
the bound; every one passes the undetected-word bar, the bottom two at
the bar itself. Integration is a new format version with a second
loader; the v1 matrices cannot be written in the v2 description.

**Like for like at the shared rates.** The frozen codes run under v2's
own protocol against the SET-1 picks. Undetected words are
syndrome-valid wrong words per 10^5 decodes at the 1 percent point.
Cost is per decode near each code's own 1 percent point, one worker, so
not an equal-channel comparison: it does not show that v2 is slower at
the same noise.

| rate | v1 code | v2 gain on the soft channel, dB | hard-channel crossover, v1 → v2 | undetected per 10^5, v1 → v2 | ms per decode, v1 → v2 |
|---|---|---|---|---|---|
| 0.859 | v1:r0850 | 0.10 | 0.0089 → 0.0089, 0.00 dB-eq | 9 → 3 | 2.5 → 4.2 |
| 0.781 | v1:r0775 | 0.06 | 0.0199 → 0.0194, v1 ahead by 0.05 dB-eq | 11 → 2 | 3.7 → 5.0 |
| 0.703 | v1:r0700 | 0.08 | 0.0346 → 0.0330, v1 ahead by 0.10 dB-eq | 3 → 2 | 6.1 → 7.4 |
| 0.625 | v1:r0625 | 0.09 | 0.0484 → 0.0490, v2 ahead by 0.03 dB-eq | 41 → 0 | 6.1 → 7.2 |
| 0.547 | v1:r0547 | 0.13 | 0.0653 → 0.0712, v2 ahead by 0.26 dB-eq | 8 → 1 | 6.1 → 14.1 |

What the gain is worth. In threshold terms, 0.1 dB at rate 0.7 moves the
tolerated raw cell error by about 0.15 percentage points, less than the
1 percentage point of content-dependent variation experiment 013 saw
between simulated pages. In failure terms near a rung's edge the same
shift is large: at one soft-channel point the 5,000-trial campaign
records, as Astra read them (file not named, unverified here), show
block failure 2.04 falling to 0.48 percent at k 2880 and 4.10 falling
to 0.76 at k 2240. Modest in threshold, large near
threshold, unmeasured on paper. The v2 search ranked on the soft channel
with the hard one as tie-break, and paper's errors are correlated and
its confidences imperfect, so neither channel is paper and the soft gain
is not known to transfer. The cost at 0.547 is the F3 family's iteration
count, 54 against 33, each at its own operating point.

**Reach, which is the actual gain.** v2:r0906 carries 3560 user bits per
tile at the default colour density against v2:r0859's 3368. The six
rungs below 0.547 reach measured hard-channel crossovers of 0.093 to
0.208 where v1:r0547 reaches 0.065, and the attempt floor falls from 53
percent of a tile at v1:r0547 to 45 at v2:r0469 and 18 at v2:r0203.
Recovery at those floors is unmeasured, and a torn tile is decoded from
the merged evidence of its scraps, not scrap by scrap (section 3). Weak
colour planes and channels at 10 to 15 percent raw error have no v1 code
at all.

**Verdict.** Keep v1 as the law for printed rows. Adopt SET-1 in the
next format version for the rungs v1 lacks. Do not regenerate the middle
for a tenth of a decibel, and do not open another lifting search under
the current objective: the top is within reach of the bound, the
bottom's loss is in shortening and ranking (section 4), and the ladder
can be re-ranked from its own ledger without a new search.

## 3. What loses tiles today: the LLR chain

The decoder assumes two things of its inputs: that magnitude is
reliability, and that cells are independent given the codeword. Paper
breaks both, and every one of the four assessments puts the remaining
yield here. It is not sized in dB on paper; the measured instances are
below, and A3 sizes it.

The chain, for K; colour has its own calibrated joint-state model with
conditional maps, and cmy7 already iterates demapping with decoding. A
per-cell darkness score is calibrated per window by isotonic regression
against the pilot labels in that window, which bounds every LLR at
log(n+1), about 6.9 at a thousand labels, by construction. A context
offset of up to 4 follows, clamped at 12. Captures of one tile are
summed without a clamp, so a multi-capture tile can exceed any single
capture's bound. The decoder clips at 20 as a backstop. Normalized
min-sum is invariant to a global scale, so only relative miscalibration,
the clips and the sum-product retry can change a decision. The label
count per window sets the ceiling of every LLR and the quality of the
calibration; it grows with the pilot density, though a window spans more
than one tile, so the two are not the same number. That is the
calibration side of the p axis of section 4.

Where the meaning leaks, with the measured instance for each:

- **Evidence combined as if independent.** Experiment 013 F3, simulated
  adversarial print, three scans: the singles certified 56, 56 and 69
  tiles of 72, the LLR sum 57, and taking any certified tile from the
  per-scan decodes 70. The sum loses when the scans slip against each
  other, because a slipped region contributes confidently-wrong LLRs.
  holo3 already decodes each capture alone in its scan stage and sends
  only the unresolved frontier to the union stage, which sums, so that
  loss is avoided by construction; what is unsized is whether the union
  of unresolved tiles loses the same way. The designed fix, weights from
  pilot agreement, exists for scraps (the weighted-sum union of
  `docs/PILOTS-DESIGN.md` §15.2 and §15.7) and not for captures. The analyzer's
  temperature arm, built on the premise that multi-lane sums are
  over-confident, did not rescue a channel the detector could not read.
  The published result for heavy-tailed noise is that linear
  combination loses to selection by 1 to 10 dB (literature, unverified).
  The fixes, in order: re-calibrate the combined score instead of
  summing calibrated LLRs; saturate or erase each capture before
  summing; keep selection beside the sum. Grok Bots' CRC-gated retry
  with LLRs clipped to 2 to 5 recovered about 15 percent of burst
  failures on its synthetic channel (unverified), which is the same
  mechanism applied at the decoder.
- **Geometry absent from the magnitude.** A cell whose sample position
  is uncertain can still read dark and loud. The 2026-09-30 study
  injected such cells at magnitude 20 into the construction search's
  finalists: 0.1 percent of cells cost 30 to 89 block failures per 100
  (10 for one variant), 0.5 percent failed every finalist. A single
  capture's LLR cannot reach 20, so for single-capture tiles this is a
  worst case; summed captures can. The right response is an erasure
  where the pose residual, the pitch fit or the neighbour model
  disagrees, not a clamp; where a clamp is used, its level under a slip
  fraction s is ln((1−s)/s), 6.9 at one per thousand and 5.3 at five.
- **Colour over-confidence.** The analyzer measured over-confidence on
  the inked sibling states of M plus Y and built an erase-state arm
  against it; one map is over-confident in one region and
  under-confident elsewhere. Scalar per-plane LLRs cannot carry
  colour-state dependence, shared registration error or neighbour
  interference; the dot-gain correlation between neighbouring cells is
  discarded, and joint detection iterated with the decoder (Marrow and
  Wolf, ITW 2003) is the literature's remedy. Both wait on the audit.
- **The context offset.** Additive on a calibrated logit, so calibrated
  only if the context model is. No held-out audit of it is on record.

What is missing is not a model but an audit, with two safeguards. Truth
comes from the emitted field of a sheet whose payload is known, which
covers failed tiles and so does not condition the audit on decoder
success; the e039 raw-error measurement already works that way. And
snapshots keep poses and decisions, not evidence: evidence is a function
of the stored rasters and a pose, regenerated on every run, so the audit
is a replay of the captures with the evidence kept, not a lookup and not
new scans. From that, reliability diagrams per stage, per plane and per
printer, and a per-tile generalized mutual information, follow.
Subsampling the pilot labels per window prices fewer labels at the
present geometry; what more, differently placed pilots buy needs an
emitted high-p sheet. The per-tile spread of the GMI also decides whether
rate by region at write time is worth anything: on a channel uniform
across tiles the 1 percent target is already optimal within 0.3 percent
of throughput, at a 0.5 dB spread retargeting gains 2 to 3.5 percent, at
1 dB up to 13 (literature, unverified). Ground truth stays an audit,
never a knob, by the analyzer's own ruling.

Beyond the audit, the one structural idea all four assessments share:
one round of feedback inside the tile. The decoder already returns an
extrinsic LLR; feeding its confident part back as labels, refitting the
local calibration, and decoding once more stays inside the tile. DESIGN
§6 called joint equalization and decoding the cheapest large gain in the
system; the analyzer's feedback refit L3f measured +3 certificates on
sheet H and +13 on sheet J (`analyzer/DESIGN.md`, L3f), a small result
on top of a tuned chain, and
it refuses to learn from a word that closed the syndrome and failed the
CRC, because that extrinsic is confidently wrong. Any feedback design
keeps that refusal.

The unit of certification is the tile, not the physical piece. Pilots
place scraps into cell coordinates and a torn tile is decoded from the
weighted-sum union of the scraps that cover it (`docs/PILOTS-DESIGN.md`
§15.2 and §15.7); the certificate is the tile's, so it is the merged
evidence that certifies, never a scrap on its own. The codeword stays
tile-sized so that merge is spent finishing one tile;
shared information between neighbouring tiles belongs in the channel
estimate, not in a parity check that spans tiles.

## 4. Pilot density, shortening, and the bottom rungs

Pilot density p is a design axis, not two fixed rows. K emits and
decodes at p 100, 150, 200 or 300; cmy8 at any p above 100 (p100
refused for colour, since M appears only in dust); only cmy7 is locked
at p120. The defaults are p100 for K and p120 for colour. A higher p
buys shredder resistance, because a smaller scrap can lock and
calibrate, and more calibration labels per window, which raises the LLR
ceiling of section 3; it costs user bits, since every pilot is a
shortened information bit, and at the bottom rungs it costs decoding
margin through shortening. The axis exists in design and implementation
and has barely been exercised. Only p120 and p300 are measured in the
ledger; p150 and p200 are lawful and unmeasured.

The trade at three rungs, from the ledger (label value unmeasured):

| rung | user bits p120 / p300 | attempt floor p120 / p300 | shortening penalty p120 / p300 |
|---|---|---|---|
| v2:r0906 | 3560 / 3380 | 90 / 90 percent of a tile | +0.03 / +0.03 dB |
| v2:r0547 | 2088 / 1908 | 53 / 51 percent | −0.02 / +0.05 dB |
| v2:r0203 | 680 / 500 | 18 / 14 percent | +0.25 / +0.93 dB |

Shortening is free at the top and expensive at the bottom. Gaps to
Shannon at the shortened rate, in dB, for the SET-1 picks and their
runner-ups; every gap cell is absolute and the last column is a
difference; the unshortened column is the S3 walk, which differs from
the rung-final gaps of section 2 by a few hundredths:

| rung | pick, unshortened | pick at p120 | pick at p300 | runner-up, unshortened | runner-up at p120 | runner-up at p300 | runner-up minus pick, p120 / p300 |
|---|---|---|---|---|---|---|---|
| v2:r0906 to v2:r0625 | 0.72 to 0.81 | 0.71 to 0.83 | 0.73 to 0.85 | 0.72 to 0.84 | 0.73 to 0.84 | 0.74 to 0.86 | within 0.03 |
| v2:r0547 | 0.842 | 0.826 | 0.894 | 0.873 | 0.850 | 1.018 | +0.02 / +0.12 |
| v2:r0469 | 0.903 | 0.984 | 1.175 | 0.910 | 0.958 | 1.243 | −0.03 / +0.07 |
| v2:r0406 | 1.016 | 1.056 | 1.125 | 1.004 | 1.046 | 1.112 | −0.01 / −0.01 |
| v2:r0359 | 1.015 | 1.075 | 1.143 | 1.042 | 1.045 | 1.216 | −0.03 / +0.07 |
| v2:r0313 | 1.046 | 1.073 | 1.244 | 1.012 | 1.068 | 1.309 | −0.01 / +0.07 |
| v2:r0250 | 1.147 | 1.336 | 1.711 | 1.139 | 1.280 | 1.560 | −0.06 / −0.15 |
| v2:r0203 | 1.233 | 1.485 | 2.164 | 1.278 | 1.270 | 1.893 | −0.21 / −0.27 |

Shortening moves every one of the top five rungs by at most 0.04 dB.
Three things follow.

- **The rank looked at the wrong configuration.** Rank v4 scored the
  unshortened code, and no SET-1 tile would ever be decoded that way.
  At v2:r0203 the runner-up (Z 64) beats the pick (Z 32) by 0.21 dB at
  p120 and 0.27 at p300, with an unshortened gap 0.045 dB worse; at
  v2:r0250 by 0.06 and 0.15. The ledger holds every number needed to
  re-rank all twelve rungs on their shortened and hard-channel walks;
  no decode is required. Adopting a runner-up needs its floor points at
  the shortened configuration and the 20,000-trial verification the
  picks had, and reopens the owner's ruling of 2026-10-24 that took the
  current picks.
- **The mechanism is structural, and partly a shortening-order
  artefact.** Some extension rows of the published v2:r0203 carry a
  single information edge; shorten that bit and the printed extension
  bit becomes a second observation of one core parity bit, a
  repetition: evidence for one bit where the cell could have protected
  many. How much of the loss that accounts for is not separated out.
  The column order was chosen by PEXIT on the shortened code, and PEXIT
  is the tool the literature says misranks punctured and degree-1
  structures at low rate; full density evolution is built and parked on
  speed. The literature puts whole-circulant shortening patterns 0.34
  to 0.51 dB apart in threshold (Wei 2020, unverified here). Counting
  information-free rows after shortening and walking the order variants
  on the existing picks costs hours and needs no search.
- **A mother code at the printed length is the candidate where high p
  meets a low rung.** Shortening lowers the rate, which lowers the
  Shannon limit by 1.82 dB at v2:r0203 between the unshortened rate and
  the p300 rate, but improves the code's 1 percent point by only 0.89
  dB; the gap widens by 0.93 dB. If a code designed at the shortened
  length and rate reached the ladder's usual distance above the bound,
  which no candidate has yet demonstrated, it would gain over the
  current pick, shortened:

| rung | at p120 | at p300 |
|---|---|---|
| v2:r0203 | 0.23 dB | 0.82 dB |
| v2:r0250 | 0.14 dB | 0.46 dB |
| v2:r0469 | none | 0.11 dB |
| v2:r0547 | none | none |

These are conditional targets for a construction that does not exist,
not measured gains. v2:r0313 to v2:r0406 carry 0.11 to 0.20 dB penalties
at p300 and were not estimated. At the colour default p120 the v2:r0203
runner-up already sits within 0.01 dB of the target, so re-ranking
captures it. At a high density a dedicated mother is the candidate, and
only at the bottom two rungs. A family of mothers at 3996 (p100), 3896
(p200) and 3796 (p300) at every rung is therefore not a ladder question
but a bottom-rung question: three times the codes everywhere buys
nothing above v2:r0469, and one code per high-p configuration at the
bottom targets up to 0.8 dB at p300. v2 allows punctured nodes, so such
a mother need not be shorter than 4096; an exact printed length would
need rate-matching beyond the whole-circulant representation.

Ladder spacing is a separate question with a cheaper answer. Rungs are
0.078 apart in rate from 0.859 to 0.469 and 0.05 to 0.06 elsewhere.
Grok Bots prices a half step wasted at about five times v2's gain; the
fountain's tolerance of a few percent block error makes the real waste
less than half a step, and extra shortening of the next rung up yields
any intermediate payload from the existing codes. v2:r0781 shortened by
320 keeps rate 0.763 and gives v2:r0703's payload with 320 cells freed,
so the half-hour twins run that prices the parity side (v2:r0781
shortened by 160 and 320 against v2:r0703) answers half the question;
the other half, what those cells buy as calibration labels, is A3's.

## 5. The decoder's attempt logic

Four items, none of them a new matrix, and all of them under one rule:
every change states how often it consults the CRC.

**A blind spot, confirmed in code.** The sum-product retry runs only
when min-sum fails the syndrome. A min-sum pass that lands on a
syndrome-valid wrong word returns clean, fails the CRC outside the
decoder, and the 150-iteration retry then re-runs the same deterministic
trajectory on the same evidence to the same word. Sum-product never sees
that tile unless a later stage brings new evidence. Astra found it,
replayed 61 such outcomes and recovered 3 by forcing sum-product
(unverified, selected cases). For the deployed codes the class is at
most 1.8e-3 of attempts for v1:r0550, the cmy8 C and M bank code, and
between 3e-5 (v1:r0700) and 4.1e-4 (v1:r0625, never printed) for the
other five at their 1 percent points, upper bounds because the counts
include wrong words reached through sum-product. On paper it is
unmeasured, and attempt facts are not persisted in snapshots, so the
count is a replay with attempt logging on. The fix is a few lines,
backward compatible, adds one CRC consultation per failed attempt, and
is expected to be small.

**Attempt economy.** The receiver's LDPC cost is attempts, not decodes.
e030 spent 35,281 LDPC calls on 663 certificates, 621 from the scan stage
and 42 from retry150; sheet D took 3,086 cpu-s for 1,553 certificates,
909 of them from retry stages. The same replay that counts A1 gives stage
and outcome per attempt, and a breakdown that shows which stages certify
and which only spend is the first execution lever at this layer. The
layer itself is small: placement is about 99 percent of K cpu at p300.

**A low-clip retry stage.** Grok Bots' CRC-gated retry at clip 2 to 5 is
the per-capture saturation of section 3 applied at the decoder. It would
be an attempt stage priced by the scheduler like retry150, with one CRC
consultation per failed attempt.

**Layered scheduling is mostly an execution item.** The argument that
the iteration cap costs decibels at the bottom rested on the pre-PBRL
picks, where 60 to 150 iterations gained 0.19, 0.12 and 0.35 dB at the
bottom three rungs. On the published SET-1 codes the same change gains
0.012 to 0.078 dB on every rung, because the raptor-like family already
collected it. A layered schedule reaches the same waterfall in about
half the iterations (Hocevar's result, literature). What that does to
time in the vectorized numpy
decoder, where a sequential schedule costs more per iteration, is
unmeasured, and so is its effect on which tiles certify, since a
different schedule fires different trapping sets; so it is measured as
cpu per recovered payload at a fixed budget on the six v1 codes first,
with the floors of all eighteen codes re-measured, and not by iteration
counts. Degree-dependent normalization is worth 0.05 to 0.1 dB end to
end at most for yield (literature, unverified), because the sum-product retry already collects
most of what it offers; its execution effect, fewer tiles entering the
retry, rides along with the schedule change.

**CRC consultations are a budget.** Under the random-CRC model, each
time a candidate decode is checked against the CRC a wrong candidate
passes with probability 2^-32; for a fixed error pattern the verdict is
deterministic, and `ladder2/lib/crc_cover.py` proves coverage of every
information pattern of weight 3 or less at every rung, and of weight 4
wherever k minus p is at most 3000. The model is the bookkeeping;
proven coverage and measured wrong certificates are the two things it
does not replace. The chain already consults the CRC once per stage on
new evidence and up to three times per cmy7 attempt, an accepted
exception recorded in `02-ldpc.md`. Per attempt today the v1 codes
expose between about 7e-15 (v1:r0700) and 4e-13 (v1:r0550) under the
model; a list-32 polar decoder would present 32
candidates per failed attempt, about 7e-11 per attempt at the 1 percent
point, two to four orders of magnitude more. The budget has no ruled
ceiling yet (section 8).

## 6. Yardsticks and challengers

**The bounds.** On the soft channel the ladder is 0.40 to 0.66 dB above
the bound. On the hard channel, computed this week, the five shared
rates sit 0.08 to 0.41 dB further from their bound than on the soft one,
most at 0.859 and least at 0.547; from 0.547 down the two channels read
within 0.1 dB of each other. v2's hard-channel crossovers reach 50 to 92
percent of the bound's over the ladder. Paper is neither channel: its
errors are correlated and its confidences imperfect. But its magnitudes
are bounded, so the hard-channel room at the top is a reasonable place
to look, and that is where Grok Bots' 5G curves land.

**5G NR.** `docs/TODO.md` frames the cross-check as a reference that
improves no rung but closes the search question for the record. Grok
Bots ran it outside the project with an untuned BG1 cut to 4096 printed
bits: at k 3520 it ties v2 on the soft channel and beats both ladders on
the hard one by about five times in frame error; at k 2880 it sits
between v1 and v2 on the soft channel and ahead of both on the hard one.
About 3000 trials per point, an unverified harness, no rate-matching
details. Two things make it plausible: k 3520 is BG1 at lifting size 160
exactly, with 320 punctured high-degree nodes where v2 capped punctured
nodes at 128 and punctured cells cost nothing on paper; and v2 ranked on
the soft channel. Grok Bots reads its own hard-channel result as
mattering less because the receiver is soft; this document reads it the
other way, because paper's magnitudes are bounded. The in-house run
needs a day to build the BG1 construction (Z 160 for k 3520; Z 144 with
288 filler bits for k 2880, since BG2's specified range ends at rate
2/3; Z 176 with 160 fillers for k 3712) and a few hours of decoding. If
the curves hold, the ranking objective changes and a standard graph
becomes a documented alternative for deep time; if they do not, the
TODO's framing stands.

**Polar with a CRC: lower priority on the numbers.** Absent from the
project's literature pass. At list 32 it sits 0.55 to 0.75 dB above the
bound at this length by the workers' numbers, which are extrapolated
from length 2048 and unverified, against the ladder's 0.40 to 0.50 at
the shared rates, at about the same operation count; list 128 buys 0.13
dB more at four times the work; the near-bound results are at n 128. It
would also need its own certificate under the budget of section 5,
since the list decoder consumes the CRC, and the pilot sites would have
to leave the codeword with one frozen set per density. Astra wants it
benchmarked; the one condition under which that is worth a day is the
5G run showing the hard side is the room and a CRC ceiling being ruled.

**Lower priority, one line each; the numbers are the assessments' and
their literature searches', unverified.** AR4JA at rate 1/2 and the 10GBASE-T
RS-LDPC code: 0.65 and 0.72 dB above the bound, behind the ladder
(unverified). Long raptor-like codes: in the same band as SET-1's top at
eight times the length. Non-binary LDPC: 0.2 to 0.3 dB only against
untuned binary codes at 20 to 70 times the cost; not on K; for colour
only after joint demapping around the binary codes is measured. OSD
after min-sum: millions of re-encodings per failed tile for a gap the
iteration study prices under 0.1 dB at the top; extra iterations do not
bound what a different decoder could add, so this is a cost judgement,
not a measured no. Spatially coupled, staircase and product codes: they
spend tile locality, the one thing the design refused to spend.
Rate-compatible families: 0 to 0.2 dB behind per-rate codes at mid
rates; a candidate only if the ladder is ever rebuilt. Neural codes:
real at n 256 and below, not rebuildable from a docstring. Most prior
paper-storage systems use hard decoding, Reed-Solomon or Golay with
interleaving (JAB Code: regular LDPC with bit-flipping; Bulan and
Sharma's colour barcodes use soft LDPC decoding, per Astra, unverified
here), at about 25 to 74 bits per mm²; no matched comparison exists, and
the literature workers' claim that none beats this stack by more than 5
percent at equal length is unverified.

## 7. Actions

Ordered by what each decides per hour, with what it needs first. Items
marked ◇ change the production receiver and touch `API.md` and
`SCHEDULE.md`; items marked ‡ reopen the owner's ruling of 2026-10-24.
Snapshots hold poses and decisions only, so every row that reads
evidence or attempts is a replay of stored captures.

| id | action | needle | expected effect | cost | needs first / decides |
|---|---|---|---|---|---|
| A1 | count syndrome-ok, CRC-fail attempts on a replay with attempt logging; force sum-product on that outcome ◇ | recoverability | class at most 18 percent of v1:r0550's failures at its 1 percent point, about 1 percent at v1:r0775; a selected replay recovered 5 percent of the class; expect order 1 percent of failures on r0550 rows | a replay of one sheet, then a few lines; +1 CRC consultation per failed attempt | nothing; the count decides the fix |
| A2 | from the same replay, attempts by stage and outcome; prune or defer stages that never certify ◇ | execution at the LDPC layer | e030 53 calls per certificate; sheet D 909 of 1,553 certificates from retries at 3,086 cpu-s; the layer is a small share of sheet cpu | the A1 replay; judged per cpu-second | nothing; decides the scheduler change |
| A3 | reliability audit per LLR stage and plane against the emitted field, failed tiles included; per-tile GMI spread; pilot labels subsampled per window | recoverability | decides which of A7 to A10 to build; prices rate by region (0 to 13 percent); prices fewer labels at the present geometry | a replay of stored captures with evidence kept; about a day; audit only, under the analyzer's separation ruling | nothing; gates A7 to A10 |
| A4 | all eighteen codes on a bounded-LLR soft channel with 0.1 to 0.5 percent confidently-wrong cells | recoverability | whether v2's 0.06 to 0.13 dB transfers to a paper-like channel | half an hour per point set | nothing; gates decision (b) |
| A5 | the v1 half of the application benchmark: replayed real captures at the deployed p, fragment masks, repeat captures, held-out acquisitions; certified user bits per area and per cpu-second | all | the yardstick that judges A1, A2, A7 to A11 | days | nothing; gates deployment of A7 to A11 |
| A6 | 5G cross-check: BG1 at Z 160 (k 3520), Z 144 with 288 fillers (k 2880), Z 176 with 160 fillers (k 3712); soft and hard channels | recoverability at the top rates; deep time | if Grok Bots' unverified curves hold, up to about 0.4 dB-eq on the hard side at the top (derived from the section 6 bound table); then the objective changes | a day to build, hours to run | nothing; gates decision (b) |
| A7 | combining rework: recalibrate the combined score, selection beside the sum, per-capture saturation ◇ | recoverability on multi-capture rows | unsized on paper: the 013 loss (12 of 72, simulated) is already avoided by scan-first scheduling; the open question is the union of unresolved tiles | days, on e030's captures | A3 |
| A8 | geometry-aware erasure: erase cells where pose, pitch or neighbour model disagree ◇ | recoverability on slip and banding sheets | attacks the confidently-wrong tail; unsized | days | A3 |
| A9 | a low-clip retry stage, clip 2 to 5 ◇ | recoverability | Grok Bots' 15 percent of burst failures, synthetic, unverified | a day; +1 CRC consultation per failed attempt | A3; judged by A5 |
| A10 | one round of in-tile feedback: extrinsic to labels to refit to decode, keeping L3f's refusal of CRC-rejected syndrome-closed words ◇ | recoverability | analyzer L3f measured +3 on sheet H, +13 on sheet J | days; +1 CRC consultation per round | A3; judged by A5 |
| A11 | layered schedule: six v1 codes first, then SET-1; floors re-measured on all eighteen; measured as cpu per recovered payload at a fixed budget ◇ | execution at the LDPC layer | about half the iterations at every rung; time per iteration and the effect on which tiles certify unmeasured | hours to measure | nothing; judged by A5 |
| A12 | re-rank all twelve rungs on the ledger's hard-channel and shortened walks ‡ | recoverability of fragment and high-p rows | 0.21 dB at v2:r0203 and 0.06 at v2:r0250 at p120; 0.27 and 0.15 at p300 | free to compute; adopting a runner-up needs its floor points and verification | effective only with A14 |
| A13 | information-free rows after shortening, and shortening-order variants on the existing v2:r0203 and v2:r0250 picks | recoverability of high-p rows | part of the 0.9 dB at p300, unsized | hours, ladder2 | nothing; gates A15 |
| A14 | a v2 loader and format version for the rungs v1 lacks | reach | v2:r0906 +5.7 percent user bits on clean rows; attempt floor 18 to 45 percent of a tile against 53, recovery at those floors unmeasured | days, plus a printed qualification sheet on its own go | the format version decision |
| A15 | a mother designed at the deployed high p for v2:r0203 and v2:r0250 ‡ | recoverability of high-p fragment rows | conditional targets of up to 0.82 and 0.46 dB at p300, for a construction not yet demonstrated | a day of search per code, plus acceptance, verification, freeze, goldens, bootstrap text | the objective of decision (b), A13, and a planned high-p row |
| A16 | v2:r0781 shortened by 160 and 320 against v2:r0703, parity cells against label cells | recoverability via finer payload choice | whether ladder spacing needs new codes | half an hour | nothing; the label half is A3 |
| A17 | housekeeping: the stale shortening and iteration paragraphs in `docs/LDPC-LADDER-V2.md` §1.2 and the "NOT merged" lines in `docs/FEC-DESIGN.md` | none | readers of the designs of record stop getting wrong numbers | minutes | nothing |

Deferred, with the reason: the Ro et al. PBRL add-on (a floor experiment
on one bottom rung, after A13); v2 against 5G and polar at identical
payload (after A6); re-measuring v2's 0.1 dB on real scans (needs A14
and a printed v2 sheet); polar list decoding (lower priority, section
6). Not worth doing on the evidence: regenerating the middle rungs;
searching more seeds under the current objective; degree-dependent
normalization alone for yield; non-binary on K, and for colour before
joint demapping is measured; spatially coupled decoding on the tile,
and OSD on cost; a full family of mother lengths at every rung.

## 8. Decisions this leaves with the owner

- (a) **Re-rank the bottom two rungs on their shortened walks**, and
  adopt runner-ups where they win. Reopens the ruling of 2026-10-24
  ("Take the new picks"). Trigger: A12; effective with A14.
- (b) **The objective of any future search**, replacing rank v4: useful
  bits per tile times the probability of correct certification, per
  area and per cpu-second, on the shortened code, on a channel with
  bounded magnitudes and a confidently-wrong fraction, with deployed
  shortening, burst geometry and decoder cost weighted directly.
  Reopens the search stop of 2026-10-24. Needs A4, A5 and A6 before it
  can be computed.
- (c) **A ceiling for the CRC budget**, in wrong certificates per
  printed page or per archive, so that A1, A9 and A10 and any list
  decoder can be checked against it. Constrains the cmy7 exception in
  `02-ldpc.md` and the floor bar R3 of `docs/LDPC-LADDER-V2.md`.
- (d) **What physical qualification means** for a new code or density:
  one printed sheet per rate and p on its own go, read to closure with
  tile-level certification counted, since fountain slack can hide
  tile-level regressions, before promotion under an immutable identity.
- (e) **The v2 format version**: whether and when the second loader
  enters the receiver and the bootstrap chain. Trigger for A12, A14 and
  A15.
- (f) **Which p a shredder-resistant row runs at**, since only p120 and
  p300 are measured and the calibration side of the axis is unmeasured
  until A3.

Standing and not in question: v1 is the law for every printed row; the
existing calibration and conditional-demapping mechanisms are kept and
credited in every comparison; receiver-side work comes before code work,
because that is where the losses are, measured on colour and unsized on
K, and it helps printed sheets.
