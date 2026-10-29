# e037 — Sheet I complete from a single capture: 5,883/5,883 (2026-09-07)

**Headline: one Canon 2400 dpi capture of sheet I carries the whole
page — 5,883 of 5,883 tile-streams, C 1,961/1,961, M 1,961/1,961,
Y 1,961/1,961 — close VERIFIED byte-exact (1,798,761 bytes, sha256
`2445b95db5b49bf3…`, identical to the e033 emission and to e034's
recovery), and the offline scorer read every analyzer certificate
against the emission: 1,046 checked, 0 wrong.** The second sheet in
this record read to 100% after e036's sheet H, and **the first read to
100% from a SINGLE capture**. e034 reached 5,880 on this sheet from
three 2400 captures plus a 4800 and ~84 cpu-hours; e033 §033.3's own
single-capture attempt on THIS capture reached 5,152 of the 5,277
symbols it needed and did not close, 125 short. e034's three hold-outs
— the page-corner tile (0,0,C) that resisted 565 attempts across e034's
chain, and the two Y tiles flanking the worst dead-band column,
(36,27,Y) and (36,29,Y) — are all certified here.

The claim is about the CAPTURE, not about one instrument against
another: the base run was interrupted by hand, not exhausted (next
section), so the analyzer's harvest on top of it is harvest from an
unexhausted base. What this log establishes is that the paper, read
once at 2400 dpi, holds the volume.

Sheet I is the e033 print (2026-08-18): Xerox AltaLink C8245,
`L:c2-cmy8-r0700-p120-x1@3392x2368` (fossil id; 1,961 tiles × 3 streams =
5,883 tile-streams; k_total 5,277), 4 mm, q 0.9, 230.7 b/mm² field. The
capture is e033 §033.1's "capture 1", `scratch/xerox-canon-18.8-I-c2-cmy8-r700-q90-p120-4mm-2400dpi.tiff`
(sha12 `269d81217ec4`). Machine and worker count: 14 workers is on the
argv and in every ledger; the machine (machine 4, 128 GB) is a session
fact, not artefact-backed.

## Provenance

Run 7.9 was not aimed at sheet I's readout. It came out of a 2026-09-07
survey (session fact: the session "Non-closing sheets in scan history")
of the checked-in record for printed holo-format volumes that have scans
and were never closed. That survey returned three M281 colour sheets
(e030's `c2-cmy8` and `c3-cmy8`, e032's `c2-cmy7`), all channel-dead on
the Y-starved engine — `c3-cmy8` is unclosable as printed, since `-v0`
per-stream quotas cannot reconstruct a Y block from 0 Y certificates;
e035's uncut sheet-J twin (`full-2400-{a,b}`), scanned whole and never
decoded, the one live candidate; and e033's sheets A, A2, B, C, D, E, F
and G, printed 2026-08-18 and never scanned at all. Sheet I was on none
of those lists — it had been VERIFIED since e033 — and was chosen anyway,
one capture, `--plane-fields`, as a single-capture datum for that dial
(the first such datum is a session claim, not one this tree can check).
The dial's question is the one this run does not answer; the readout is
what it produced instead.

## The base: an interrupted run, not a stall

`holo3-I-run-7.9.97950` (`--plane-fields --complete --workers 14`, one
capture) was stopped by hand at 4,833 certified (C 1786 / M 1928 /
Y 1119), close deferred, 444 short of K, after about 22 minutes of wall
(run-dir mtimes). Two honesty notes on that sentence. The tree marker is
`pre-v1-v2-deletion-93-g74d7711…-dirty` — main plus uncommitted changes,
not main. And **the stop leaves no event marker**: `events.jsonl` ends
with one `EngineStat` and `RunDone {status: open, certified: 4833}`, and
holo3's orderly stop (`engine.py`, SIGINT/SIGTERM "ask for an ORDERLY
stop — the loop breaks and `_finish` writes every product the run would
have written at exhaustion") writes exactly what exhaustion writes. That
it was an interrupt and not exhaustion is proved by the frontier, not by
a record of the signal: **13 jobs in flight and 25,334 queued** at
`RunDone`. The single ctrl-C is the operator's account.

Its scheduler block says where it was:

| row | jobs | certs | queued | cpu-s |
|---|---:|---:|---:|---:|
| tiles.scan | 11,263 | 4,435 | 0 | 971 |
| tiles.retry | 11,962 | 391 | 0 | 1,860 |
| tiles.local | 55 | 7 | 8,306 | 127 |
| tiles.planek | 0 | 0 | 8,499 | 0 |
| tiles.swim | 0 | 0 | 8,499 | 0 |
| tiles.uplift | 0 | 0 | 3 | 0 |
| fields | 6 | — | 3 | 281 |
| place / refine.color / color | 1,297 / 2,256 / 102 | — | 21 / 0 / 3 | 143 / 618 / 843 |

4,435 + 391 + 7 = 4,833: the base is scan plus retry, plus 7 from
`tiles.local`. The residue toolbox had barely started — planek and swim
never fired, and they are worth 287 of e034's +323 on this sheet
(`tiles.planek` 281, `tiles.swim` 6, the rest local and retry) and 270
on sheet J (224 + 46) — so a run to exhaustion would have stood
materially higher, and no sentence of the form "production reached 4,833
and the analyzer supplied the rest" is an instrument comparison.

`--plane-fields` ran its six fits (281 cpu-s), and the dial is
**unpriced by this run** — but not because the fields went unread. Four
rows consume `plane_field` (SCHEDULE.md): `color`, `refine.color`,
`tiles.planek`, `tiles.swim`. The first two ran hard before the
interrupt (2,358 jobs, 1,461 cpu-s, 1,097 poses) and minted nothing;
only the two that mint certificates off the fields — planek and swim —
are the ones the interrupt cut off.

## The chain

| step | what | certified | close |
|---|---|---|---|
| run 7.9 | holo3, one capture, interrupted | 4,833 | deferred |
| pass 1 | analyzer, DEFAULT battery (12 arms, no patch family), `--targets residue --fixed-point`, 14 workers | **+1,027 of 1,050** (97.8%) in 40 min wall: generations +763 (31 min), +230, +31, +3, +0 | the pass's own close VERIFIED at 5,860 |
| fold | export-facts → `holo3-I-7.9-facts-1.npz` (4,833 + 1,027) → union-base `I-7.9-union` | 5,860 | consistency 583 redundant, 0 inconsistent |
| pass 2 | analyzer on the union base, `everything+patch+pure` + L3f, `--fixed-point` | **+19 of 23** in 9 min: generations +13, +4, +1, +1 | the pass's own close VERIFIED at 5,879; 602 redundant, 0 inconsistent |
| fold | export-facts → `holo3-I-7.9-facts-2.npz` | 5,879 | 602 redundant, 0 inconsistent |
| score | emission regenerated from the fossil + pass 2's `payload.bin` (manifest sha == the payload); `analyzer score` over both ledgers | 1,046 checked | **0 wrong, 0 false accepts** |
| pass 3 | analyzer on a union base over facts-2, same `everything+patch+pure` + L3f/L7c battery, the 4 remaining rows | **+0 of 4** in 2:42 — a measured negative | close VERIFIED at 5,879 |
| fold | export-facts → `holo3-I-7.9-facts-3.npz` (added 0) | 5,879 | 602 redundant, 0 inconsistent |
| resume | holo3 `--resume holo3-I-7.9-facts-3.npz --plane-fields --complete`, the same capture | **+4, all Y, all `tiles.scan`** → **5,883** | **close VERIFIED in flight, sha `2445b95d…`** |

Pass 1, by stream and band (certified / rows): C live 64/70, C marginal
102/105, M live 16/16, M marginal 17/17, Y dead 549/561, Y live 110/112,
Y marginal 169/169. The close bar (444) was cleared 2.3× over the pass
(1.7× inside generation 0 alone). Arms at first success:
`subtract+offset` 754, `subtract+affine` 189 (45 via re-roll),
`global+offset` 51, `project+committed` 11, six others 22; rungs: L0 969,
L2 damped 41, L2 layered 9, L1 8.

Pass 2, the 19: `patch+affine` 13 (4 via re-roll), `patch+offset` 3,
`patch+field2+offset` 1, `subtract+field2c+offset` 2; 17 at L0, one each
at L1 and L2; the refit rung L3f and the erasure rung L7c minted nothing.
(0,0,C) fell in generation 3 to `patch+affine` at L0. Note that band
labels are recomputed per pass against that pass's base, so every pass-2
and pass-3 row reads `live` — the "Y dead 549/561" above is pass 1's
label, not a standing property of those tiles.

With one capture the corroboration column cannot fire: every certificate
rests on one physical reading, and the fountain and the scorer are the
checks.

**A pass that had already closed.** Pass 1's own close verified at 5,860,
pass 2's at 5,879: the analyzer runs the close at the end of every pass
and writes `payload.bin` beside the ledger. A separate `analyzer close
--run-dir <the ORIGINAL run dir>` read 4,852 (4,833 + pass 2's 19) and
refused, 425 short — it was pointed at the base run's facts instead of the
union base's. Point `close` at the union base, or use the pass's own
close; the trap is cheap to repeat.

## The last four: the analyzer refused them, plain scan took them

After pass 2 the residue was four Y tile-streams: **(17,15,Y)** — in the
tx 15–19 dead band — and **(45,29,Y)**, **(46,29,Y)**, **(47,29,Y)**, at
the deep end of the tx 27–30 band. Pass 3 threw the widest battery in
the toolbox (22 arms, nine rungs including L3f and L7c) at exactly those
four and took none of them: 161.6 s, one generation, 0 certified. That
is the analyzer's measured refusal.

holo3, resumed from the fact snapshot those passes had built, then
certified all four in **158 jobs, 455 cpu-s, 164 s wall — and it was
`tiles.scan` that minted them, at 3–7 MILLISECONDS of CPU each.** The
same plain scan row that could not read those tiles when the page was
4,833 certified reads them in milliseconds when the page is 5,879
certified. Nothing about the paper changed and no new arm was involved;
the evidence around the tile did.

**Which piece of that evidence, exactly** — the event order in
`events.jsonl` narrows it to one and rules the others out. `place`
commits 16 poses and `color` adopts pool `…/l00/p0` twice (the second
with reason `assembled_fully_certified` — the pool assembling from a
fully certified population IS the analyzer's harvest paying back);
**`tiles/scan` then attempts all four and FAILS all four**; the whole
residue toolbox attempts them and fails too (`tiles/retry150` 4 of 4,
`tiles/planek150` 3 of 3, `tiles/local150` 4 of 4, `tiles/swim150` 4 of
4, every one `attempted_failed`); `color` adopts pool `…/**l01**/p0`;
and the very next tile event is (47,29,Y) certified, then the other
three, at 9–22 BP iterations. **So the lever was the COLOUR
CALIBRATION, re-fitted over the denser certified population — not the
poses, which were committed before the failures, and not the residue
toolbox, which failed on all four.** And not the plane fields: every
`FieldFitted` event in this run lands AFTER the four certificates, and
the run published only the C field (0.37 dots); M (0.23 d) and Y
(0.13 d) were REFUSED under the floor, so no Y field existed for a Y
tile to use.

This is the cascade e034 measured for planek (82% of its mints had a
same-run neighbour predecessor) appearing at the cheapest row on the
ladder, and it is the strongest argument in this log for the
fold-and-hand-back loop: the analyzer's value here was not only the
1,046 certificates it minted, it was making four more free.

The close was then verified twice over: once in flight by the resume
(`K 5883/5277`, metadata rank 24/24, sha `2445b95db5b49bf3…`) and once
by a separate `analyzer close` over the finished run dir
(`I-7.9-final-close`, 5,883 symbols, 606 redundant, 0 inconsistent,
identical sha). Five `payload.bin` files across the chain — passes 1, 2
and 3, the final close, and the resume's own `--out` — hash byte-identical
to each other and to the emission manifest.

## What this settles, and what it does not

- e033 §033.4 measured the Y dead bands as **detector-frozen** at a
  0.42-cell x-registration sinusoid, and named the receiver-axis fix
  (per-plane pose, "PK6/A2 … REOPENED by this sheet"). It also predicted
  that re-placed scans would help only marginally and that "16 px/cell
  will NOT undo" a 0.42-cell print offset. This chain does not test the
  sampling prediction — one 2400 capture at 8 px/cell, no 4800 run — so
  that prediction stands untested here. What it does measure is the SIZE
  of the receiver-axis lever §033.4 pointed at: at 8 px/cell from ONE
  placement, arms and pose took 549 of pass 1's 561 Y-dead rows and the
  page finished with Y complete at 1,961/1,961. The sinusoid measurement
  stands; "only marginally" understates by a wide margin what a better
  detector, not a better sampler, can do against it.
- e034 gave its three hold-outs TWO different explanations: (0,0,C) was
  "Local damage, not a plane effect", and only the two Y tiles were
  called "format-axis losses, exactly where the format's own algebra says
  they should be". All three are certified here, so **both**
  characterizations are overturned, not merely the count: they were
  arm-reachable. The corner tile fell to affine registration under the
  patch filter; the two Y tiles fell in pass 1's first two generations to
  the ordinary battery (`subtract+offset` at L0 and a `global+offset`
  re-roll at L2:damped).
- NOT settled: what `--plane-fields` bought — but the resume narrows it
  from "unmeasured" to "measured at zero on four tiles". In the base run
  the fits ran and the two certificate-minting consumers never did. In
  the RESUME both consumers DID fire — `tiles.planek` 3 jobs, 1.8 cpu-s;
  `tiles.swim` 4 jobs, 17.5 cpu-s — and **minted nothing**, and the
  `fields` row cost 284.7 cpu-s — 63 % of the 455.2 cpu-s the scheduler
  accounted, 57 % of the 500.5 the process spent — to publish C alone and
  refuse M and Y under the floor. On this residue the dial
  bought zero certificates for the majority of the run's compute. That
  is four tiles, not a page, so it prices the dial only there; a dial-off
  control on the same capture is still the measurement that would price
  it for the page.
- NOT settled: whether holo3's residue toolbox, run to exhaustion on the
  UNINTERRUPTED base, would have reached the same place without the
  analyzer. The resume answers a narrower question — it took four tiles
  the analyzer had refused — and leaves the counterfactual open.
- A qualification of `analyzer/W8-2026-09-06.md` §4, not a correction to
  its number: W8 priced affine at "+1 certificate over X3 for 1.7× the
  CPU" on sheet H's wide residue, from a controlled A/B. Here
  `patch+affine` was the FIRST-SUCCESS arm on 13 of pass 2's 19. Those
  are not the same measurement — the ledger's
  own header says the arm table is "A FIRST-SUCCESS marginal, not a
  leave-one-out" — and no affine-off arm of pass 2 was run, so nothing
  here shows those 13 would have been lost without it. The comparable
  number is an affine-off re-run of the same 23 rows; until it exists,
  W8's A/B is the only priced affine figure in the record. Recorded there
  as §3.4.

## Standing rules check

Single sheet, single capture, one engine pairing: existence and regression
evidence, **no ladder promotion, no population claim**; receiver status
PROVISIONAL. One capture means no independent corroboration is possible;
the envelope sha (twice, by two closers), the fountain consistency check
on every fold and the offline scorer against the regenerated emission are
the legs, and all hold. Nothing learned on this sheet is stored.

## Owed

- The dial-off control on this capture — the only thing that prices
  `--plane-fields` here.
- e035's uncut sheet-J twin (`full-2400-{a,b}`), the survey's one live
  candidate, still undecoded. Never combine it with the sheet-J confetti.

## Artifacts

- `scratch/holo3-I-run-7.9.97950/` (argv, tree, report.json, events.jsonl,
  the one capture's rasters) — the interrupted base;
  `scratch/holo3-I-with-facts-3-run.7756/` + `scratch/holo3-I-with-facts-3.log`
  — the resume that closed it.
- `scratch/holo3-I-7.9-facts-{1,2,3}.npz` with manifests;
  `scratch/analyzer/I-7.9-union/` and `I-7.9-union-2/` (the two union bases).
- `scratch/analyzer/I-7.9-pass{1,2,3}/` (ledgers, closes, `payload.bin`);
  `scratch/analyzer/I-7.9-score/` and `I-7.9-pass3-score/` (the offline
  scores); `scratch/analyzer/I-7.9-close/` (the close trap, 4,852 / 425
  short) and `I-7.9-final-close/` (5,883, verified).
- `scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm/` (the emission
  regenerated from the fossil; manifest sha == the recovered payload).
- The session logs `scratch/analyzer-I-7.9-pass{1,2,3}.log` and
  `scratch/analyzer-I-7.9-score.log`.
