# FINDINGS: what the bootstrap line measured, 2026-10-18 to 10-26 (written 2026-10-23; §15-§16 added 2026-10-26)

The measured knowledge of the bootstrap line, one short section per finding,
for a reader with ten minutes. Each section gives the date, the measurement,
what it changed and where the full record is. The authority is the RECORD
(RECORD-2026-10-20.md for rulings 1-68, RECORD-2026-10-19.md and
RECORD-2026-10-18.md for the earlier rounds); the numbers are quoted from
the files named, never re-derived here. Everything is MEASURED on machine 1 in
simulation unless it says paper or ESTIMATE, except the compressor
exploration's figures of ruling 32 (sections 9 and 10), which the owner's
cloud session measured in a cloud container. One sheet set, one typist: NO
promotion of anything.

The stages, by ruling 34 (named by the program each one yields): stage 1 is
`a.py`, typed by hand from a printed listing; stage 2 is the data sheet
typed at a.py's prompt, which yields `b.py`, the typed reader of the
printed R2 pages (R2-FORMAT.md); stage 3 is the R2 (bullseye) pages, read
by b.py from phone photos, which yield `c.py`, the pure-Python receiver of
the holo K row c3-k-r0547-p100 with its archive layer; stage 4 is the
release, which c.py reads from scans of the holo archive pages. Stage 0 is
the Plate.

## 1. The chain closed on paper with a phone (2026-10-20)

The owner printed the build of record (3450f87f), typed a.py from the
listing, entered the 48 data lines by phone OCR and paste, photographed the
three R2 leaves with a phone camera, and r.py (today's b.py) wrote its
output byte-identical to the bundle (sha256 579e5f1c…). Two leaves were
turned 90°, one had a strong exposure gradient, the third was shot in two
halves, and either half closes. 3,895 typed characters in about 40 minutes.

What the typist got wrong: on a.py three slips in 826 characters (missed
`:` characters and one missed `[`), caught by the self-dump; on the data
lines 71 attempts for 48 lines, 17 lines retyped, every slip caught by the
line check. The camera's confusions were g→q 7, v→y 4, i→j 2, o→0 2 and
four singletons; the alphabet had left out i, l, o, u for the eye, but the
camera's pairs g/q and v/y sit inside it.

What it changed: ruling 30 (a middle dot for every space of the listing),
then the OCR study of ruling 42 (uppercase removes q read as g; base 36 out
because both glyphs of a look-alike pair become valid) and ruling 51 (Menlo
for the listing, Andale Mono uppercase for the data sheet, by the owner's
eye on the printed paper-test set).
Pointer: PAPER-2026-10-20.md; RECORD-2026-10-20.md "The first close on
paper", rulings 30, 42, 43, 51; experiments/047.

## 2. The typed reader's unread up-left blocks were a code bug (2026-10-22)

After the cross-page placement (ruling 29) the typed reader left 13 to 15
blocks per page unread even from a perfect grid, most of them diagonally
up-left of a bullseye. The 10-21 diagnosis blamed the learned axes. The
measurement says the source is two one-sided tie-breaks in `max()`: the
per-block refinement `ft` took the largest offset among exactly tied
scores, the rotation search `fm` the largest tied step. The failing
diagonal follows the image under quarter turns of the grid, and the ties
exist only where scores are exactly flat (the 0/1 grid, the exact raster,
the perfect spm-7 render). The far corner's error is 0.54 module, not the
"third of a module" of 10-21.

fix0 breaks `ft`'s tie toward the candidate nearest the current estimate,
and `fm`'s toward the smallest rotation: the three grids go from 595 / 593
/ 591 to 609 / 609 / 609 chunks, the exact raster from 60 to 608; nominal
renders and photos move within ±2 chunks. Ruling 47 put it into b.py; the
change set measured it at +15 typed, the rotation tie +1.
Pointer: RECORD-2026-10-20.md "The typed reader's unread up-left blocks";
r2reader/axes/RESULTS-2026-10-22.md "Short answer", with STATIC, DIAG and
JUDGE beside it.

## 3. Fix #2 refused: a per-block frame fit is noisier at 2 samples per module (2026-10-22)

Fix #2 fits each block's own pose on its own 68 timing modules and drops
the learned axes (−116 characters). At 2 samples per module that fit is
noisier than the learned centre difference it replaces: on b045 seed 2
the median axis error is 1.46 % against 1.01 %, the centre 0.118 against
0.085 module. Over seed sweeps it loses 81 chunks over six b030 pages and
635 over nine b045 pages, two b045 pools the reader of record closes fail,
and the refuter's envelope edge loses 183 over 10 pages. On the photos it
reads 9 more blocks (unread 16 → 7) at 2.2-2.5× the walk wall. Refused as
specified (the owner's call under ruling 45); the owner's idea of the walk's
state as block corners stays a candidate for the photos.
Pointer: r2reader/axes/RESULTS-2026-10-22.md "Short answer"; RECORD
"The typed reader's unread up-left blocks", the owner's call.

## 4. The CRC-gated walk: a trade, kept (2026-10-22)

The walk used to pass through a block when its timing modules alternated
at 60 % of their contrast. The gated walk passes through a bullseye, a
block whose CRC-32 checks and a white slot, and goes round a block whose
CRC fails. It saves 32 glyphs and costs +33-49 % wall on a whole page.
Measured where blocks fail most: at the envelope edge (spm 1.5, blur 0.40)
it holds fewer chunks on 6 of 12 frames (Σ 4,637 → 4,538; no text closes
there); with all 15 bullseyes ringed by blots it accepts 0 blocks where the
reader of record reads 542 blocks / 484 chunks; on the sigma 0.45 quarters
it gains, 2,300 → 2,618 pooled. The alternative without the gate types
3,517 / 3,517 (+47 / +48). Ruling 52 kept the gated text ("okay. ruled
text it is."): smallest, reads the most where reading is hard, its two
losses bounded.
Pointer: RECORD rulings 45 and 52 and "The b.py change set APPLIED and
MEASURED"; r2reader/changeset/RESULTS-2026-10-22.md §11, §12.

## 5. The quarters' gain is the seed pass-through; weak walks claim first by being nearer (2026-10-22)

The union gate (timing test OR CRC OR white) and its leave-one-out put the
whole quarter gain on one clause: the record and the alternative never
walk from a seed whose own timing frame fails the 60 % test, the gated
text walks from every seed. One tr quarter reads 128 blocks with the
clause and 0 without; the CRC/white clause moves 1-2 blocks.

The edge losses come from the same seeds. 270 of the union's 280 lost
chunks sit on blocks a weak seed's walk claimed first and failed to read,
and 258 of 280 were claimed first because the block is NEARER the weak
seed in walk steps, not because the walk started earlier. So sorting the
seeds (S1) keeps the losses (265). Deferring the weak seeds to a second
walk over the unclaimed cells (S2) loses nothing against the alternative
and has the best quarter sums (2,631 pooled), at 3,577 / 3,578 typed and
44 lines. S2 was measured on the alternative's text, not on the gated one;
it is an owed line (ruling 52).
Pointer: r2reader/changeset/RESULTS-2026-10-22.md §13 (leave-one-out),
§15 (the poisoning table and "Side by side").

## 6. One bullseye left: the walk reaches the page, the page is lost at the finder and the header (2026-10-22)

With 14 of 15 bullseyes destroyed, every text's walk reaches all 615
surviving data blocks from the one seed, out to 45 steps, whenever the
header reads, with one exception: the ruled text at blur 0.45 seed 2 never
reaches one block per render, a block whose four neighbours all failed
their CRC. The gated text reads the most and closes the page alone on
five renders (n030-A-ink, s7-A in both polarities, s7-B-ink, s7-C-ink),
the other texts only on s7-A. At blur 0.45, 14 of 32 renders yield
nothing in every text: the survivor is not found (8) or its header does
not check (6). The finder's threshold is `(min+max)//2` of every 97th
pixel; one sample landing in a blacked block moves it from 129 to 127,
and that flips which survivor is found and whose header reads, with the
survivor's own pixels identical. A knife edge in the finder and header,
not in the walk. Nothing changed yet: the finder's threshold is an owed
line (ruling 52), and ruling 55 cites this as the lone-bullseye weak spot.
Pointer: r2reader/changeset/RESULTS-2026-10-22.md §14 ("When the page is
lost outright: the header", "Plain answer").

## 7. The percentile threshold made the finder worse (2026-10-22)

The 5th-to-95th-percentile midpoint of the same sample, proposed to steady
the threshold, finds FEWER bullseyes on blurred pages: 38 → 20 over the 12
envelope-edge frames, and one edge pool holds 0 where the ruled text holds
453. It loses the header on 18 of 129 captures the ruled text reads, the
quarter pools fall from 2,618 to 1,623, set I's slot pass fails at 99/172,
and it costs +3 / +4 typed. Not applied; the composite took the arms F1
to F4.
Pointer: r2reader/changeset/RESULTS-2026-10-22.md §16 "F6"; RECORD ruling
54.

## 8. The format round: the ring check carries real work (2026-10-22)

Three bullseye variants that let the reader drop its ring check (ruling
55) type 3,356 (V3), 3,315 (V1) and 3,341 / 3,340 (V2) against the ruled
3,470 / 3,469: the two data lines the ring check is worth. Only the record
in its coarse rendering passes every acceptance set. The variants admit
false seeds (V3 776 on 54 set captures, V1 1,346, V2 98, the record 0);
none injects a wrong block (0 of 29,799 false-walk reads accepted), but
they cost chunks through the pose, since the walk takes its pitch from the
first seed and the rotation vote counts every seed (a measured pitch of
768 against the true 517). The refuter's reading stands: the round
measured the reader port as much as the formats. The ring check had been
hiding three weaknesses: a scale-free comb, the first-seed pitch with the
all-seed vote, and a dedupe that lets an earlier false candidate suppress
a true bullseye. Rendering the rings as true 600-dpi circles is worse for
every kind, the record included. No variant adopted; a second round with
the port fixed is the owner's call.
Pointer: RECORD "The format round MEASURED"; format-round/
RESULTS-2026-10-22.md §9 (and §3 for the false seeds).

## 9. The compressor's model is at a local optimum; the text is the lever (2026-10-20/21)

The owner's cloud session tried about seventy model arms in a.py's style,
each round-tripped: none pays its characters (the best saves 14 glyphs for
71 characters). What pays is the text the decoders read: names chosen by
compressed size plus equivalent rewrites took the reader of that day from
3,894 to 3,788 typed at 0 decoder characters, and the monolith from 10,599
to 9,876 B. strong2 cannot reach 14 archive pages for T1. This became the
rename-and-rewrite search used on all three stages: a.py's rewrites −29 and
names −30 (stage 1), −112 typed on b.py in the change set, and the pipeline
that keeps c.py on two R2 pages (today's c.py's minified text alone,
24,625 B, is 10,681 B through cm2, 73 B over the 10,608 B of two pages;
stage3/RESULTS-2026-10-22.md §6).
Pointer: RECORD ruling 32 (compressor-exploration/ASSESSMENT-2026-10-20.md,
LEVERS-2026-10-21.md); "Stage 1 built"; "Stage 3 COMPOSED".

## 10. Prior art: Crinkler ties, ZPAQ costs a page, "nothing public smaller" is untested (2026-10-20/21)

cm2, cm1 and strong2 are our names for Matt Mahoney's PAQ-family
techniques. Crinkler transliterated to Python types 3,896 against the
record's 3,895 at cm2's decode speed; its one transferable idea,
compressor-searched sparse masks and weights typed as data, gives −32
(3,863) but is over-fitted to the payload and needs a re-search on every
reader change. At archive size Crinkler's fixed weights take T1 to 18
pages against strong2's 15. A minimal ZPAQ decoder costs one more R2 page
and keeps T1 at 15. Ruling 32 corrected the published-ceiling ESTIMATES
(paq8l is 0.911 of strong2 on our tree) and recorded that "nothing public
is smaller and better" is UNTESTED: no public decoder of cm2's size was
run on the fixtures.
Pointer: RECORD rulings 31 and 32; priorart/SURVEY-2026-10-20.md,
priorart/crinkler/README.md, priorart/zpaq/README.md.

## 11. The primer's worth, and why the typed leaves and the R2 pages are a matched pair (2026-10-21)

Priming the R2 payload's compression with the reader's own text buys 137
to 222 B (1.4-2.2 %). Fully decoupled, the reader would type about 3
characters fewer and the R2 content would cost 144-229 B more (both
ESTIMATES from ideal bits). The tie runs both ways: the payload decodes
only against the reader's exact bytes, and the reader carries the
content's length and CRC-32 baked, so the data lines change with every
c.py and the pages with every b.py. Ruling 33: no decoupling until the
sizes are ideal. A side effect seen on 10-22: when the progress words left
b.py, the stand-in bundle (which still contains them) grew 18 B because
its primer no longer did.
Pointer: RECORD ruling 33 (its table); r2reader/changeset/
RESULTS-2026-10-22.md §18 "Sizes".

## 12. Words are the costly characters: the progress line (2026-10-22)

The progress line went from the composite's `NAME: N bullseyes, B blocks,
chunks H / T more` (ruling 54's words had already dropped `accepted`) to
`9@ 500/557` (ruling 56 as amended). Estimated at about 30
glyphs, it measured −71 typed (3,408 / 3,407 → 3,337 / 3,336) and one data
line fewer (41 → 40): the name echo, the blocks count and the done/more
flag went with the words, and moving the done check inside the `try`
saved about 7 more glyphs. Reads unchanged, call for call on 129 captures.
Ruling 58 then allowed the literal `@` in b.py, which the audit had
refused inside string literals too: −2 / −1, so b.py types 3,335 /
3,335 on 40 data lines, reads identical on 129 captures (applied
2026-10-23). Ruling 59 then applied the grey padding of the image buffer
in place of the sampler's clamps (one image of mid-grey 128 appended at
load; §17's padt was the first form, §19 (B) the arm): 3,326 / 3,325
typed on 40 lines (−9 / −10), the finder's threshold byte-identical on 129
captures and 199 break frames, no chunk lost, the ten frames §19 (B) named
reading differently with equal or better counts and no other. With c.py
as the content the chain types 3,319 / 3,318 and c.py is 9,966 / 9,971 B
through cm2, 2 R2 pages.
Pointer: RECORD rulings 56, 58, 59 and "The progress line APPLIED";
r2reader/changeset/RESULTS-2026-10-22.md §18, §19 (A), §19 (B), §20.

## 13. Python 3.11's byte-order defaults (2026-10-22)

From 3.11 `int.from_bytes` and `to_bytes` default to big-endian, so the six
`,'big'` arguments in b.py's typed region go: −12 / −11 typed on top of the
refinement arm (3,415 / 3,414 against 3,427 / 3,425). Ruling 53 set the
chain's floor at 3.11. Found with it: under Python 3.9.6 that text answers
`cannot read` on both frames of the close control, exits 0 and writes no
c.py, so an old interpreter fails silently. Nothing enforces the floor at
run time: the early probe was refused (ruling 63, "probe means growth"),
and sheet 1 says "Run a.py with Python >= 3.11" (ruling 65). a.py's own
`,'big'` went in the first convergence (39da92bc).
Pointer: RECORD ruling 53 and "The composite APPLIED"; r2reader/changeset/
RESULTS-2026-10-22.md §16 ("F1" row, the Python 3.9.6 row), §17.

## 14. What c.py is, and what it is not (2026-10-20 to 10-22)

c.py (then 23,793 B; 24,176 B `b4f7de22…` since 8b2ad284; no import) is generated mechanically from
stage3/c_readable.py by the minifier and the rename pipeline, each step
proven by ast. c_readable.py is the record's receiver_arch.py after a
scripted retarget to r0547 plus six documented hunks, and make_c.py
`--provenance` checks exactly that (ruling 57). receiver.py itself, the
root of that chain, was WRITTEN from src/holo's format law by the R3 round
of 2026-10-20 (four Opus readers mapping src/holo, one builder): a
hand-made distillation cross-checked against holo, not derived from it.
The cross-checks: holo's own receiver decodes the same simulated scans
(ruling 24), and VERIFIED the r0547 volume c.py closes (6,262 metadata
equations, 429 s). In simulation c.py reads 321 of 321 files byte-exact,
plain and with 40 % of every page's tiles blanked. It handles one row
only: no colour, no other rung, no fragments or mirrored scans, tilt
within ±10° (ruling 24). It keeps its archive layer (strong2 and the ustar
unpacker) as built (ruling 61, the owner, 2026-10-23). The deep review of
c_readable.py as a distillation of the K receiver closed on 2026-10-23
(7b7c17f0, stage3/review/): format and acceptance law bit-identical to
holo's, four reach gaps, ruled by ruling 63 and repaired (§15).
Pointer: RECORD rulings 24, 36, 57, 58, 61 and "Stage 3's source promoted";
stage3/README.md; stage3/RESULTS-2026-10-22.md §3, §6.

## 15. The v2 print on paper, and c.py repaired (2026-10-23)

The owner printed the candidate print of record v2 (print-2026-10-23.pdf
1d6a7697…) and typed it: stages 1-3 closed byte-exact (scratch/typed2/,
c.py 92c48a39…). Archive page 03 did NOT decode, neither scaled to fit
(96.3 %), nor from the PDF at 100 %, nor through the raw PostScript path.
The cause was c.py's phase-contrast floor of 2.0, calibrated on the
simulator, which scores 2.67, where pixma scans of correct prints score
1.55-1.74. The repair (8affb97b): the floor 1.2 with the address word's
CRC as the arbiter over candidate lattices, three trial pitches (1, 0.96,
1.04), a per-tile retry at ±1/8 cell; then the batch (da0cd032): LDPC
alpha 0.75 → 0.8 (holo's), the neighbouring-dpi fallback (ruling 65), one
progress line. Page 03 then read 840 / 840 on all six scans, at hints off
by −4 / +5 % and at the wrong standard dpi. The new c.py moved b.py's baked
N2 / B2, so ruling 60's convergence re-ran (CONVERGENCE-2026-10-23b.md) and
found the chain and make_c's pipeline in a two-cycle (b4f7de22 ↔
c0ffe2a5); rule (d') keeps the member whose own chain prints smaller,
taken by ruling 67 (2026-10-26). Result: the candidate print of record v3,
print-2026-10-23.pdf 4989446c…, 3,289 / 3,289 typed on 39 lines, c.py
24,176 B, R2 10,133 B, 475 B spare.
What it changed: simulation alone had qualified a reader that could not
read paper; every stage-4 change since is measured on real scans.
Pointer: stage3/RESULTS-2026-10-22.md "The repair of 2026-10-23";
CONVERGENCE-2026-10-23b.md; RECORD ruling 67; docs/EXPERIMENT-LOG.md.

## 16. The whole chain closed on paper; the release does not run (2026-10-26)

**The close.** The owner printed v3 (4989446c…, 19 pages, the HP M281),
typed sheets 1-2; a.py wrote b.py, b.py read the R2 pages from 300 dpi grey
scans and wrote c.py, c.py read 600 dpi pixma scans of the archive pages
and CLOSED THE VOLUME on the first eight: placed / certified 840/832,
840/840, 840/806, 840/774, 839/802, 840/829, 840/840, 839/541 (page 8
decoded only until the count was met); 6,264 symbols held of 6,260;
payload.bin 1,648,660 B, SHA-256 78d9a4b4…168e (the record's T1
container); 321 files unpacked. a.py, b.py and c.py sha-equal to the chain
(720330aa…, 761138cd…, b4f7de22…). Every page `turn 180`. The dpi fallback
fired on paper (d-03 entered without a dpi: `no tile placed at 1200 dpi,
trying 600 dpi`, then read); d-01 fed twice changed nothing (32 decoded, 24
certified, held count unchanged). Ruling 37's "600 dpi is enough at c3"
holds on paper.

**The margin at 600 dpi.** Seven whole pages certified 5,723 (817.6 a page,
the worst 774), so the eighth page is needed; the 6,264 is where c.py
stopped, not a spare. At the mean the volume closes on 8 pages, at the
worst page's rate on 9 (6,260 / 774 = 8.09); in the 1,200 dpi simulation on
8 (840 a page). Two pages placed 839 of 840; whether the missing tile sits
beside the left-margin header strip (0dfb3fed) is NOT measured.

**THE STAGE-4 PAYLOAD GAPS.** The release as unpacked does not run.
(1) T1's selection law, `src/holo/**/*.py` + `docs/**/*.md` (not
docs/archive/) + CLAUDE.md (r3/arch/trees.py:3, :45-48), leaves out every
non-.py file under src/holo: the twelve LDPC code tables (six under
src/holo/core/ldpc/data, the same six blob-identical under
src/holo/receiver/lib/ldpc_data, 161,840 B) are JSON, and the archived
holo3 dies at import (`FileNotFoundError` on
receiver/lib/ldpc_data/r0547.json). NEW on paper. (2) The archive carries
no requirements file: KNOWN, ruling 40 (holo3's imports are not in the
tree; "magically has all imports"), and met in practice on 10-26, when the
session built the venv from the repo's requirements.txt (1,819 B at
2115a595, floors, not pins). (3) c.py unpacks flat names (`%2F` for `/`):
NEW on paper; the session wrote scratch/typed3/unflatten.py; no sheet and
no file of the archive restores the tree. (4) The receiver's normative
docs (src/holo/receiver/docs/, API.md and SCHEDULE.md among them) are not
in it. THE FIX is a selection law for the release tree and a requirements
file (with the venv recipe of its header) inside the archive. It changes
the container and so stage 4 (new archive pages); c.py is
content-independent (ruling 39), so stages 1-3 do not move. The owner's
ruling owed on the selection; ruling 41 in full (RECORD-2026-10-20.md:978-982):

> 41. **The tree** is "the paper-store / holo release", to be ruled
> eventually; for now think paper/src, "but it will be more" (the
> readable sources of stages 1–3 do not travel in T1 today: bootstrap/ is
> not in it). Speculation recorded as such: a stage 4 in
> cmy8-r0850x0775x0700 to carry a lot more data.

Three choices put to him:
- ALL TRACKED FILES under src/holo: +164 files, 9,746,575 B at 2115a595
  (the 12 tables + 152 under receiver/docs: 97 .md, 47 .json, 4 .jsonl, 2
  .patch, 1 .log, 1 .txt); xz -9e of those 152 is 1,477,240 B, so ESTIMATE
  about +1.1 MB after strong2 (T1's xz / strong2 ratio 1.30) and about 26
  archive pages in all (the planner: 26 pages hold 2,871,805 B);
- src/holo PLUS ITS DATA DIRECTORIES ONLY: +12 files, 161,840 B (xz -9e
  18,832 B); ESTIMATE still over the 15-page line, whose margin is 6,352 B
  (the planner: 15 pages hold 1,655,012 B, 16 pages 1,765,630), so 16 pages;
- ALL OF src/ ("for now think paper/src"): src/holo and src/paperholo, 438
  tracked files, 15,080,318 B at 2115a595 (src/holo 407, src/paperholo 31);
  not sized in pages.
Any choice: a release from today's tree is a new container: at HEAD
4a4b2f4d 67 files of T1's selection differ from 2115a595 (37 modified, 30
added; 351 files, 9,672,949 B against 321 / 9,275,981). The strong2 size
and the page count are to be measured (13 minutes, 1.4 GB), then the
simulated round trip, then a print on the owner's go.

**The archived receiver on the pages.** With the 164 files brought in from
git, the archived holo3 ran from the release tree on d-01..d-09
(`--complete`): 7,554 of 7,560 tiles certified, 7,554 symbols held of
6,260, stopped by the owner before the close (no state directory). Its
harvest tail: 152 queued `cold_rest` placements, every window on a page
edge ((960,0,1160,200), (0,0,200,200), …), windows without tiles whose ink
(the platen's edge shadow along the top, the header strip down the left)
reads as support, which the done-geometry gate cannot retire; about 2 s
each. A receiver thread.

**300 dpi cannot read the archive row.** c3 at 300 dpi is 1.5 px per cell,
below 2 px; the repaired reader finds no lattice on typed2/03-b-300.pgm or
03-c-300.pgm. The fallback list stays 600/1200/2400 (the owner:
"understood").

**Other families** (capacity planner, source fraction 0.5, A4-6mm, the
1,648,660 B volume): K c3 35x24 15 pages (as printed), K c2 52x36 7, cmy8
c3 6, cmy8 c2 3, cmy c3 r0547x0547 8, cmy c2 4, cmy c3 r0850 (e044 B's row)
5. Caveats: cmy8 is screened on the M281 (e041); c.py is a K receiver and a
colour monolith neither exists nor would fit two R2 pages; c2 at 600 dpi is
2 px per cell.

**Compressors.** The owner's lrzip -zpaq of the unpacked tar is 1,853,119 B
(the records' libzpaq level 4 / mid, 16 pages) and his xz -9e about 500 KB
worse than strong2 (the records' 2,149,928 B against 1,648,648). The
records already hold the lead: paq8l -8 1,502,611 (−8.9 %, 14 pages),
libzpaq level 5 1,628,217 (−1.2 %), lpaq1 -9 1,677,993 (+1.8 %).

**Deferred by ruling.** A whole-file check code for a.py (each line's code
chained on the previous one, or one extra code over the file, so the last
code checks the whole listing before a data line is typed; about +10-15
typed characters; re-opens a convergence round): "let's keep this in mind
for the future. not doing that right now." (ruling 68).
Pointer: PAPER-2026-10-26.md; RECORD-2026-10-20.md ruling 68 and "The first
complete close on paper"; docs/EXPERIMENT-LOG.md; docs/TODO.md, Bootstrap.

## Open questions

The live list is docs/TODO.md, section Bootstrap, one line each with its
pointer (since 2026-10-26). The list that stood here on 2026-10-23 is in
git at d60ec72b.

## What is not measured yet

- A second typist, a second printer, a second scanner; a phone or photo
  route for the archive pages. One print, one typist (the designer).
- The archive pages at 1200 or 2400 dpi on paper, out of order, partial,
  damaged or aged; turns other than 180 on paper; tilt beyond 0.5°.
- Where the unplaced tile of d-05 and d-08 sits (beside the header strip
  or not).
- The release tree with its data files and requirements: its strong2 size,
  page count and simulated round trip; holo's receiver closing the volume
  from the release tree (the 10-26 run was stopped).
- The printed QR codes read by a phone (only renders were decoded); how
  sheets 1-2 were entered on 10-26 is not stated.
- The repaired c.py on the review's rough channel and at scale ±1.5 %
  (rough1200 p0/p1/p3, rough600 T1, A s0985/s1015), the c4 and `_os`
  variants and the other channel variants at r0547 (stage3/RESULTS).
- make_c.py's (d') claim that the tree keeps b4f7de22 with c0ffe2a5 in it is
  inferred, not run; longer cycles are not detected
  (CONVERGENCE-2026-10-23b.md).
- Walls of the composite, the progress-line, the literal-`@` and the
  padded texts: all four were measured under other sessions' load and
  report no wall (RESULTS §17, §18, §19, §20).
