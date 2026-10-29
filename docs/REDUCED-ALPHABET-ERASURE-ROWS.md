# Reduced-alphabet rows by controlled erasure — the cmy7 alternative

Status: DESIGN NOTE, 2026-10-05. The arithmetic in §3–§4 is brute-forced
(the enumeration is in §3) and was independently re-derived in review;
nothing here is built as a format row, simulated, or printed. The one
paper probe of the construction's output is e041's S1dash (sheet F with
every payload CMY triple removed by the cell-ordinal rule; the print,
scan and cell-level record are in §6 of this note), which measured the
M281's screening unchanged and moved hard cell error by C −2.7, M −1.6,
Y +1.9 points, one print each, uncontrolled. This note is the parked
replacement for the cmy7 line, closed the same day (§1). HOLO-DESIGN,
FORMAT-SPACE and PRINTED-FORMAT are untouched.

## 1. Why this note exists — the cmy7 record and its close

cmy7 (`pack7`) forbids the CMY triple with a constraint code: eleven code
bits map to four cells as radix-7 digits, one joint three-child LDPC bank,
one stream per tile, no per-plane codeword (COLOR-INTEGRATION-DESIGN §7;
PRINTED-FORMAT: "a pack with any unobserved slot is an 11-bit erasure …
there is no per-plane fallback"). It was built for the M281, whose triple
measured toxic in the weak-Y epoch (002.0c, e017.6). The record since:

- **e032** (AltaLink, 2026-08-05/06): c2-cmy7 FAILED on both engines while
  c2-cmy8 closed; c3-cmy7 closed (301,600 B). The colour-uplift campaign
  later closed the AltaLink c2-cmy7 capture at 686,859 B — its 18 % cell
  error was detector-frozen, not print-frozen (COLOR-UPLIFT-MEASUREMENTS
  §14.3), so that failure was never proof of the joint-symbol mechanism.
  e032's ordering inversion stands: discovery tiers predict neither level
  nor order of recovery.
- **AltaLink**: cmy8 reads every plane to 100 % with the triple printed, at
  r0700 from one capture (e037) and at r0850 (e036). cmy8 out-carries cmy7
  at every rung (3 × 2,087 = 6,261 vs 5,973 symbol bits per tile at r0550;
  CMY8-COLUMN-GROUPS §3, COLOR-INTEGRATION-DESIGN §7.3) and has a rung
  axis; cmy7's bank is baked per generation (FORMAT-SPACE §5).
- **e038** (M281, fresh toner, 2026-09-13/14): the composite page is
  re-screened by the engine; C reads 839/840, M and Y fail in every state
  outside one 4–5 mm band (single-ink M 8.6 %, M under C 17.5 %, under
  both 23 %; Y 15 / 21 / 26 %). cmy8's per-plane degradation is MEASURED
  there (a complete C plane with M and Y failing); that a pack7 tile, which
  needs all three planes in every pack, would certify nothing at those
  rates is inference — no pack7 sheet was printed on fresh toner. Every
  weak-Y-epoch M281 result, the triple verdicts included, was INVALIDATED
  by ruling (2026-09-14).
- **e040** (Canon iR-ADV, healthy Y, unscreened cells): the discovery sheet
  measured cmy7 at 1.7–3.5 % against cmy8 at 4.4–8 % per cell — the largest
  relative triple-free advantage on any engine — and sheet G
  (c2-cmy8-r0700) closed VERIFIED and read to 5,508 of 5,550 regardless.
- **S1dash** (M281, 2026-10-05; the probe of §6): sheet F with its 418,044
  payload triples reduced to two-ink cells is screened exactly like S1 —
  the same 164/211 lpi lattices, the same rendering band at tile column
  12 (e041's screen map and spectra, both with S1 comparisons; §6). Hard
  cell error against its own GT: C 7.0 → 4.3 %, M 15.3 → 13.7 %,
  Y 28.7 → 30.6 %, one print each, different print sessions, uncontrolled.
  The whites' blue channel rose 148 → 161 although white cells carry no
  yellow of their own: that print laid Y lighter page-wide, either engine
  state between prints or a coverage response to the sparser page — the
  latter WOULD be an alphabet effect; a same-batch S1 reprint beside an
  S1dash separates them (owed, not needed for the close). M and Y stay two
  to five times above what r0550 and r0547 carry. The screen is the wall,
  not the triple.

**CLOSED 2026-10-05, on the owner's instruction to wrap the line up and
park this construction as its replacement.** The printed cmy7 sheets stay
readable through the `L:` fossil route (two fossil identities,
`c2-cmy7-p120-v0` and `c3-cmy7-p120-v0`, three printed sheets: c3 and c2
on the AltaLink, c2 on the M281); no cmy7 row is planned (this line's
recommendation: the erasure row below, not pack7, for any future
reduced alphabet); e032's owed item 3 is disposed by this note. What cmy7 was *for* —
forbidding a printed state — survives as the construction below, which
keeps cmy8's independent per-plane codewords and pays for the forbidden
states with known-position erasures instead of a joint symbol. It is at
hand for a less dense alphabet (3–5 states per cell) if an engine or a
route ever needs one.

## 2. The construction

Let the printed alphabet be an allowed set `A` of ink subsets of {C, M, Y}
containing W. Prefer `A` **subset-closed** (if a state is allowed, every
subset of its inks is allowed): forbidding CMY alone, every overlap, or
every overlap but CM all qualify; "two-ink states only" does not.

- **Codewords are cmy8's.** Three independent per-plane LDPC codewords per
  tile, the pooled fountain, the column-group pool, the metadata equations,
  the furniture lattice: untouched. The per-plane bit `x_p` of a cell is
  what the codeword says.
- **Per cell, a plane order** `o(cell)` — a permutation of (C, M, Y) the
  receiver can reconstruct: a keystream domain (preferred; white, and
  without the stripe structure of §6's ordinal rule) or a pure function of
  the cell address.
- **Encoder: greedy admission in order.** Start with the empty kept set;
  for each plane `p` in `o`: keep `p`'s ink iff `x_p = 1` and
  `kept ∪ {p} ∈ A`. Print the kept set. Nothing outside `A` is ever
  printed, for any `A ∋ W`, and every kept ink is a true 1. Closure is
  what makes every allowed state REACHABLE: without it allowed states go
  unprinted and their capacity is lost (`{W, CM, MY, CY}` carries 0 bits
  per cell; "all but C alone" uses seven states yet reaches only 2.417,
  with ε_C = 7/12).
- **Receiver: replay.** Given the printed state `s` and the order `o`, walk
  the planes in order with `sofar = ∅`: if `sofar ∪ {p} ∈ A` the plane is
  CERTAIN, `x_p = [p ∈ s]`, and `p` joins `sofar` when it is in `s`;
  otherwise the plane is ERASED (its ink could not have been printed
  whatever `x_p` was). Under noise the same replay becomes a per-cell map
  `g_o : {0,1}³ → A` and the plane LLR is the cmy8 marginalization with
  that map:

      LLR_p = log Σ_{x : x_p = 1} P(z | g_o(x))  −  log Σ_{x : x_p = 0} P(z | g_o(x))

  over the eight inputs with a uniform prior, `P(z | state)` the detector's
  state likelihoods (today's `cmy8_raw_marginal_llrs` is the special case
  `g = identity`). A clean two-ink reading on a cell whose last plane is
  erased gives that plane LLR exactly 0 — an erasure, not an error.
- **The 7-state case is the victim rule.** With `A` = all but CMY the
  greedy keeps the first two planes in order and drops the third only when
  all three are on; the "victim" is the last plane in the cell's order
  (verified over all 48 order × input pairs). S1dash's rule,
  `v = (cy·1536 + cx) mod 3`, is this with a fixed cyclic order — and since
  1536 ≡ 0 (mod 3) it reduces to `cx mod 3` on F: a period-3 column
  stripe among the triple cells, one more reason to prefer the keystream
  order for a row.
- **Furniture.** Word sites print W/CM: nothing to do while CM ∈ `A` (the
  7-, 6- and 5-state rows); for an `A` without CM (the 4- and 3-state
  rows) the word-site states must be redrawn inside `A`, a format change
  of its own (new site constants), not only a dust cycle. Dust states must
  be drawn inside `A` (cmy8's six-state dust cycle contains the triple;
  cmy7 already carries a five-state cycle), and the detector trains an
  `|A|`-class model.

## 3. Numbers — brute force over the 8 inputs × 6 orders

Per-plane erasure fraction `ε_p`, clean-channel capacity `Σ_p (1 − ε_p)`
bits per cell, against the ideal `log2 |A|` of a joint code over the same
alphabet. Uniform over the six orders.

| alphabet `A` | `|A|` | ε per plane C / M / Y | capacity b/cell | ideal | loss vs ideal |
|---|---|---|---|---|---|
| all states (cmy8) | 8 | 0 / 0 / 0 | 3.000 | 3.000 | 0 |
| no CMY (cmy7's alphabet) | 7 | 1/12 each | **2.750** | 2.807 | 0.057 |
| no CMY, no MY | 6 | 0 / 1/4 / 1/4 | 2.500 | 2.585 | 0.085 |
| W, singles, CM | 5 | 5/24 / 5/24 / 5/12 | 2.167 | 2.322 | 0.155 |
| W + singles only | 4 | 5/12 each | 1.750 | 2.000 | 0.250 |
| W, C, M (two planes, singles) | 3 | 1/4 / 1/4 | 1.500 | 1.585 | 0.085 |

A cyclic order (the three rotations equally used) gives the same capacity
in every row, but the per-plane marginals match the table only for the
symmetric alphabets (8, 7, 4 states); for the 6- and 5-state rows they
depend on the rotation class (no-CMY-no-MY under CMY → MYC → YCM gives
0 / 1/6 / 1/3; the other class 0 / 1/3 / 1/6).

Readings. The 7-state erasure row reaches exactly pack7's 2.75 bits per
cell with no joint symbol: at equal clean-channel capacity the joint
symbol buys nothing, and what it costs is structural — no per-plane
fallback; its noise performance against the erasure row is unsimulated.
Over the three-plane rows the loss against a joint code grows as the
alphabet shrinks (2.0 % at seven states, 3.3 % at six, 6.7 % at five,
12.5 % at four; the two-plane 3-state row is a different structure at
5.4 %), which is the price of per-plane independence; a joint code over a
4-state alphabet would be a cmy7-shaped object, with the same structural
cost. Uneven `ε` (the 6- and 5-state rows) is the column-group pool's design
case: the plane that erases more takes the lighter rung, and the order
class fixes which plane that is. Mean toner coverage falls with the
alphabet: 150 % (8 states), 137.5 % (7), 125 % (6), 108.3 % (5), 87.5 %
(4). Whether an engine renders the sparser page differently is a
page-level question only a print answers (S1dash, §6: screening
unchanged on the M281's PostScript route).

Enumeration (what produced the table; keep it beside any change):

```python
import itertools, math
P = ('C', 'M', 'Y')
def greedy(x, order, allowed):
    kept = set()
    for p in order:
        if x[p] and frozenset(kept | {p}) in allowed: kept.add(p)
    return frozenset(kept)
def replay(s, order, allowed):            # per plane: certain or erased
    out, sofar = {}, set()
    for p in order:
        if frozenset(sofar | {p}) in allowed:
            out[p] = 'certain'
            if p in s: sofar.add(p)
        else:
            out[p] = 'erased'
    return out
def analyse(allowed, planes=P, orders=None):
    orders = orders or list(itertools.permutations(planes))
    inputs = [dict(zip(planes, b)) for b in itertools.product((0, 1), repeat=len(planes))]
    erased = {p: 0 for p in planes}
    for o in orders:
        for x in inputs:
            s = greedy(x, o, allowed)
            for p, verdict in replay(s, o, allowed).items():
                if verdict == 'certain': assert (p in s) == bool(x[p])
                else: erased[p] += 1
    n = len(orders) * len(inputs)
    eps = {p: erased[p] / n for p in planes}
    return eps, sum(1 - e for e in eps.values()), math.log2(len(allowed))
```

## 4. What the ladder can carry

The LDPC sees its physical noise plus a known-position erasure fraction
`ε`, so a rung's rate on the surviving bits is `R_tx / (1 − ε)` with
`R_tx = (k − 120) / 3976` on a p120 tile (the shortened rate; the
rung-ladder study's Shannon column uses the mother rate k/4096, so its
numbers differ by definition). Frozen ladder plus the study's two
candidates (RUNG-LADDER-STUDY-2026-09-30 §7):

| rung | k | R_tx | 7-state R_eff (ε = 1/12) | 4-state R_eff (ε = 5/12) |
|---|---|---|---|---|
| r0547 / r0550 | 2,240 | 0.533 | 0.582 | 0.914 |
| r0625 | 2,560 | 0.614 | 0.669 | 1.052 |
| r0700 | 2,880 | 0.694 | 0.757 | 1.190 |
| r0775 | 3,200 | 0.775 | 0.845 | 1.328 |
| r0850 | 3,520 | 0.855 | 0.933 | 1.466 |
| k 1,664 ("r0400" candidate) | 1,664 | 0.388 | 0.424 | 0.666 |
| k 1,280 ("r0300" candidate) | 1,280 | 0.292 | 0.318 | 0.500 |

Seven states: r0550–r0700 behave like plain cmy8 just under one rung up
(0.582 / 0.669 / 0.757 against the next rungs' 0.614 / 0.694 / 0.775);
r0775 has plain r0850's noise budget at 9.4 % fewer bits; r0850 is out.
Four states: every frozen rung is out (R_eff ≥ 0.91); the alphabet is
printable only with the low rungs the study searched (k 1,664 → 0.67,
k 1,280 → 0.50), which is the "less dense" situation this note is parked
for. Shannon limits at the 7-state rungs, BSC crossover on the surviving
bits: r0550 0.085, r0625 0.061, r0700 0.040, r0775 0.022, r0850 0.008
(plain cmy8: 0.099, 0.076, 0.055, 0.036, 0.021).

## 5. What building it would take, and where it would and would not help

Format axis (layout bump, new goldens): a cmy8-family row carrying `A` and
the order domain (or a sibling family — the identity grammar's choice is
the owner's); the emitter's greedy pass over the composed planes (one
function, after `color_compose`); one keystream domain for the order; the
dust cycle, and for an `A` without CM the word states, drawn inside `A`.
Receiver: the per-cell map in the cmy8 marginalization (the one formula of
§2), the `|A|`-class detector, the page field and everything downstream
unchanged. Simulation before toner: the honest per-plane BSC with `ε`
erasures overlaid, then the engine profiles. The cost is small; the
reason it is not built is that no measured customer exists:

- **Does not help** where the engine re-screens the composite regardless of
  content: the M281 on every route tried — PostScript (S1dash, §6), PCL 5c
  device CMY and PCL XL (e041's S3c and S9/S9b probes: M and Y wash out in
  every state under either screen selection, and the CMY state reads as a
  three-toner composite, not K) — and the VersaLink's PDF route, which
  screens every C/M/Y area at 164 lpi whatever the job says (e039
  §039.3t).
- **Would help**, if such an engine or route appears: one whose defect is
  a specific overlap state. The AltaLink's third-layer C at r0850 was such
  a case and was solved on the receiver axis instead (analyzer W8); a
  colour-managed route whose ink limit or GCR acts on 300 % coverage would
  be another, and none measured so far behaves that way (the VersaLink's
  PDF Bridge flattens all planes, not the triple).
- **Alternatives considered and dominated**: distribution shaping of the
  planes (DESIGN §4.4) never reaches zero and cannot shape parity bits;
  selected mapping over keystream salts costs more than pack7 for any
  useful residual; decoder-side flag-and-erase costs 12.5 % and depends on
  detecting the state the engine mis-renders; pack7 itself. Any scheme with
  independent per-plane codewords and a forbidden state pays at least the
  information the erasure carries; the greedy rule is the simplest that
  makes the receiver's uncertainty an exact, known-position erasure.

## 6. The probe: tool, print, scan, measurement (S1dash, 2026-10-05)

`experiments/041-m281-screen-routes/make_notriple_sheet.py` turns an
existing cmy8 page into its 7-state variant for a print probe: it rewrites
every payload triple cell in F's PostScript hex stream to a two-ink cell
with the victim `v = (cy·1536 + cx) mod 3` (0 drop C, 1 drop M, 2 drop Y;
a column stripe on F, §2), keeps the dust furniture by default
(`--include-dust` flips it too), writes the modified ground truth beside
the job, and gates the output against F's GT, the receiver's site geometry
and a ghostscript render. It is a probe, not a row: a receiver reads the
flips as about 4.2 % added bit errors per plane under the F fossil, so the
honest readout of such a sheet is cell error against its own GT.

**Physical run (hardware rule record; one sheet, NO promotion).**

| item | value |
|---|---|
| job | `scratch/m281-routes-20261004/S1dash-notriple.ps`, 31,208,456 B, sha `2d00b316cff952d363bd2f2e2085d8b33a590a3cee63a4df8c08b68e7278f7c3` — S1's PJL wrapper (BITSPERPIXEL=1, RET=OFF; JOB NAME E041-S1DASH-NOTRIPLE) around F's page with 418,044 payload triples flipped (C/M/Y 139,370 / 138,892 / 139,782), 3,762,396 hex digits, 2,800 dust triples left |
| ground truth | `S1dash-notriple-gt/page000_gt.npy`, array sha `81f5596aa9ddfec0…` (manifest), file sha `299dd5b2b561ddae…` |
| print | HP CLJ Pro M281fdw `<host>`, raw 9100 (`scripts/print_plane.sh`), sent after the job was built (2026-10-04 18:09) and before the scan began (2026-10-05 00:39:09, the TIFF's birth time); exact time unrecorded. This session never invoked the print script; e041 row 041.13s attributes the print to "that session", which is wrong — whether the operator or the e041 session (under its standing go of that night) sent the job is unrecorded. Media assumed as e038's (the operator's usual 90 g/m² A4, same tray), unconfirmed for this sheet |
| scan | 2026-10-05 00:39–00:46, Canon 2400 RGB, `scratch/e041/e041-s1dash-notriple-2400.tiff`, 1,718,864,112 B, sha `953e3e474c7a1e2e…` (e041 row 041.13s); laid as-is, where S1's capture was read rot180 — one more uncontrolled difference beside the print session (M/Y-vs-C registration +5.8 px on S1, −0.6 px here) |
| receiver decode (interrupted, uncontrolled) | `scratch/e041/S1dash-run.58534`: `./confetti3.py decode … --dpi 2400 --format L:c3-cmy8-p120-v1@2240x1536 --workers 8`, tree 9b7e9b82, 01:06–01:22, stopped with 11,513 jobs queued: 867 certified, C 827 / M 33 / Y 7, close open. The flips count as errors under the F fossil (~4.2 % per plane), and S1's reading was a two-capture run (830 at 13 min, C 801 / M 28 / Y 1), so the two are not comparable; recorded, not read |
| screening (e041's instruments, untracked in the `m281-routes` worktree: `measure/e041_screen_map.py`, `e041_spectrum.py`, `e041_screen_fine.py`; logs `scratch/e041/screen-map-S1dash.log`, `spectra-S1dash.log`, `fine-screen-S1dash-G.log`) | same two lattices as every PostScript print on this engine (164 lpi ±14°, 211 lpi 45°); whole-field medians 165 lpi G 569 (S1 462, F 470), 212 lpi B 1,286 (S1 1,240); fine-screen median 37 — S1 has no fine-screen measurement; S1dash's 37 sits above the PostScript variants S7b 29 and S9 32 and well above the unscreened AltaLink control's 20 (noise 7); band at tile column 12 as on every sheet (165 lpi G 124 against 570–670 beside it); whole-field mean R/G/B 133.1 / 123.5 / 137.0 vs S1 131.8 / 125.2 / 129.0 |
| cell error vs own GT (`measure/e041_gt_compare.py`, same worktree; `scratch/e041/gt-compare-S1dash.log` vs `gt-compare-S1.log`; this line's reading) | whole-page medians: C d′ 5.41, hard error 4.3 % (S1 5.37 / 7.0 %); M 3.11 / 13.7 % (S1 3.15 / 15.3 %); Y 1.68 / 30.6 % (S1 1.92 / 28.7 %). Band column 12: C 2.6 %, M 5.4 %, Y 24.8 %. Per-state mean R/G/B: W 174/156/161 (S1 175/152/148), M 169/91/126 (S1 166/106/123), Y 181/152/129 (S1 177/148/123), CM 93/102/138 (S1 97/106/129); the 2,800 dust CMY cells 93/109/127 |
| reading | the engine does the same thing to the triple-free page; C −2.7, M −1.6, Y +1.9 points, one print each, different sessions, uncontrolled; whites' B +13 = Y laid lighter page-wide on this print (engine state or coverage response, unseparated); M and Y stay far above the rungs |
| owed | a same-batch S1 reprint beside an S1dash to separate drift from a coverage response — only if the question is ever reopened |

e041's log (branch `m281-screen-routes`, uncommitted at the time of this
note) owns the scan row and the screening measurement and hands the
cell-level reading to this line, which is why it is recorded here.

## 7. Record

- 2026-10-06: the four-state alphabet {W + singles} got a measured
  customer (the M281 lays single toners solid and screens every composite
  pixel; e041, branch `m281-screen-routes`, since MERGED) and a DESIGN of its own,
  docs/CMY-DESIGN.md — the `cmy` family carries the cell's two LABEL bits
  as two cmy8-style streams on frozen rungs (2.0 b/cell, no erasures).
  This note's three-plane form of that alphabet (§3–§4: 1.750 b/cell,
  ε 5/12, every frozen rung out) is the recorded rejected alternative;
  the seven-state row and everything else here stand as parked, except
  §5's "does not help … the M281 on every route tried": that clause
  predates e041's content-driven screener (every pixel a single toner is
  never screened) and no longer holds for single-toner pixels.
- e032 owed item 3 ("reconsider whether cmy7-pack7 earns its density at
  c2") — disposed by §1: nowhere measured on any engine at c2; at c3 by
  inference from the c2 closes, since the only colour close at c3 in the
  record is cmy7's own (e032, 301,600 B) and no c3-cmy8 sheet has been
  read on a healthy engine (AltaLink F unscanned by ruling; VersaLink and
  M681 F 0 certificates; M281 F screened).
- COLOR-DESIGN D1 carries a dated status line pointing here; its 017.6
  triple numbers and 002.0c MI figures are weak-Y-epoch and invalidated
  (e038 ruling).
- `src/holo/devices/registry.py` `hp-m281` colour text amended from "CMY
  triple toxic" to the measured mechanism (composite re-screen on every
  route tried; M/Y under every rung except one band; the triple-free page
  screened identically).
- No HOLO-DESIGN amendment: the graceful-degradation preference e032's
  item 3 asked for is recorded here, not in the normative spec (the freeze
  is user-declared; this note is a parked design, not format law).
- 2026-10-05/06, c2 on the M281: the seven-state alphabet does not read
  there as DOT-MIXED cells. S12 A21 (c2 dot-mixed diagonal pairs, all eight
  states; uniform/smooth, three patches pooled, per-state errors from
  `scratch/e041/mixture/S12-ps-mixture-patches.csv`) read CM 30 %, CY 38 %,
  MY 11 %, CMY 56 % against 2–8 % for W and the singles: dropping the triple
  is necessary at c2, not sufficient. S17 asked whether column or row pairs
  fix it (e041 §041.5n). They do not: U8 / U9 / U11 (cmy7; column / row /
  diagonal pairs) read 20.2 / 22.6 / 18.3 %, U10 (cmy8, diagonal) 23.6 %.
  The two-toner 2+2 cells read 73 %, and even solid single-toner 2×2 cells
  read only 87–89 % under a 1–1.5-dot misregistration (§041.5o item 3, "c2
  dot-mixed is closed"; one print, one 4800 capture). A smaller
  subset-closed `A` such as {W, C, M, Y, MY} (log2 5 = 2.32 b/cell, 324 b/mm²
  raw against seven states' 392) was never printed at c2. The four-state
  set is the `cmy` family's. On the AltaLink, which lays overlaps solid, the
  seven-state alphabet reads 9.0 % at c2 against cmy8's 14.2 % (e042
  §042.4), so the row's c2 question stays open on that engine.
