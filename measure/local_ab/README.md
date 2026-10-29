# local_ab — union vs per-origin, for the `tiles.local` row

`tiles.local` re-reads one failed tile under a locally re-fitted head.
On colour it builds ONE `TileCut` per covering lane — the whole colour
head re-fitted over that lane's covering windows — and then makes a
SINGLE attempt over all of them, which `tiles._combine` sums. That is a
union.

The multi-scan law (main `CLAUDE.md`, F1∘F6) says equal-weight combining
can LOSE to best-single when the errors are print-correlated, and
`tiles.retry` already does the opposite: it MIRRORS the failed attempt's
origin, so a scan-origin retry re-attempts one capture alone.

So: on multi-capture material, would mirroring the origin — one attempt
per lane — win tiles the union loses?

**Nothing in `src/holo/receiver/` changes.** The union arm is `local_ctx._attempt`
itself.

---

## 1. The verdict

**PER-ORIGIN WINS, AND THE UNION NEVER WON ALONE.** Two crop cases off
sheet I's three 2400 dpi captures, 153 armed subjects between them:

| arm | certificates | both | union only | per-origin only | neither |
|---|---:|---:|---:|---:|---:|
| union (as landed) | 2 | 2 | **0** | — | — |
| per-origin (one attempt per lane) | **6** | 2 | — | **4** | 147 |
| N0 null (wrong address) | **0** | | | | |

Per-origin is a strict superset here: it took every tile the union took
and four more. **1,271 certificates checked against the emitted payload
across the whole battery, 0 wrong**, and the null certified nothing.

**It costs 3%.** The expensive half is the per-lane head re-fit, and
both arms share it:

| | I-nw | I-tl | total |
|---|---:|---:|---:|
| component build (SHARED) | 217.7 s | 1220.8 s | 1438.5 s |
| union attempts | 3.9 s | 20.3 s | 24.2 s |
| per-origin attempts, every lane | 10.5 s | 60.6 s | 71.1 s |

Adding per-origin to the row costs **+46.9 s on 1,462.7 s = +3.2%**, and
triples the yield (2 → 6). Measured build cost is **3.0–3.2 s per lane**,
a little under the 4.28 s the task estimated.

### The mechanism, in iteration counts

On `I-nw` tile (0, 2), lane `6ae9d958/L2` certified stream C in **10**
belief-propagation iterations and stream Y in **24** — trivially easy
decodes. The other two lanes failed at the 300-iteration ceiling, and so
did the union of all three. Summing a clean lane with two bad ones
destroyed a decode that was nearly free on its own: two wrong lanes
outvote one right one.

`I-tl` shows the same shape at coarser rungs — tile (0, 6) Y at 4 px/cell
(union fails, `adc56e18/L1` certifies in 51) and tile (4, 7) Y at
2 px/cell (union fails, `e80789d2/L0` certifies in 32).

### Why "best-single" cannot be chosen once

The winning lane is different every time: `6ae9d958/L2`, `adc56e18/L1`,
`adc56e18/L2`, `e80789d2/L0`. No capture is globally best, so the arm
has to try each lane on the tile, not pick a favourite capture.

### What the union really buys, and why to keep it

`tiles._combine` unions the OBSERVED SET as well as summing the LLRs, so
a lane whose own window coverage is thin can come back
`below_attempt_floor` where the combined observation clears the code's
support floor. That happened **10 times** across the two cases. It never
converted into a union-only certificate here — but it is a real effect
and the reason the recommendation is ADDITIVE (keep the union, add the
per-lane attempts) rather than a replacement.

### Scope, stated

One sheet, one print, two crops, 153 subjects, 4 disagreements. Sheet I's
three captures are three platen placements of ONE print at ONE dpi, so
`cover_lanes` at a fixed rung never mixes resolutions — this measurement
therefore says nothing about `measure/yask`'s separate worry, that
equal-weight summation across 1200/2400/4800 dpi lanes may not be
monotone. holo3's unions are same-rung by construction
(`tiles.assemble_union` fixes `ppc`), so that worry does not apply to
this row at all.

---

## 2. How the two arms are built

Both arms consume the SAME components. `local_ctx._prepare_color`'s body
is run once per subject —

```
plans      = local_ctx._color_lane_plans(store, page, ty, tx, ppc)
components = local_ctx._color_components(row, geometry, plans,
                                         store.certificates(), page, ty, tx)
```

— and that is the expensive half: one `color_region.region_job` per
lane, the whole QDA class model, detector calibration, registration
residuals and context matrix re-fitted over the covering windows alone.
It is charged ONCE and reported separately from either arm's decode
cost, because a production per-origin stage would reuse it too.

| arm | what it does |
|---|---|
| **union** (as landed) | `local_ctx._attempt(...)`, verbatim — one `tiles.attempt_tile` over every component |
| **per-origin** | one `tiles.attempt_tile` per component, same `STAGE_LOCAL150`, so the same 150-iteration BP budget |
| **N0 null** | the union arm's components re-labelled to a neighbouring tile address — same pixels, wrong address |

`_combine` does two things, and it matters that they are two: it SUMS
the LLRs, and it UNIONS the observed set (`observed[flat] = True` per
component). So per-origin is not merely a noisier union — a lane whose
window coverage is partial can come back `below_attempt_floor` on its
own where the combined observation clears the floor.

**Nothing is fed back.** Neither arm's certificates enter the store, so
no subject is helped by another's win and both arms see byte-identical
evidence. Both yields are lower bounds on a scheduled production stage —
equally, so the comparison is unaffected.

## 3. What is checked, and what would void the battery

* **Ground truth.** The EMITTED payload (`payload-counting.bin` from the
  e033 generation set) is sha-gated, then re-encoded through
  `src/holo`'s own generation arithmetic — the pooled-CMY8 branch of
  `crop_parity._gt.reconstruct` — into per-tile user bits. The
  comparison lives at USER BITS, upstream of the slot permutation and
  the colour cell permutation (memory: truth-path discipline).
* **The decode's own certificates** are audited against it BEFORE the
  A/B is allowed to start.
* **Every A/B certificate** is audited the same way.
* **The null must certify nothing.** A certificate there means the
  harness can manufacture one.
* **The arm must be the row.** `_ab.verify_row` runs
  `local_ctx.prepare_local` — the callable the engine would have
  dispatched — on a sample of the same subjects and compares verdicts.

Exit 0 healthy · **2** a wrong certificate or a null that certified ·
**3** ground truth refused validation.

## 4. Two decisions that shape the measurement

### The row is DETACHED from the decode

`tiles.local` IS the union arm. If the decode runs it, every tile the
union would win is certified before the A/B starts and then dropped
from the population by `has_certificate` — the union would score zero by
construction and the challenger would be measured on its leftovers.

So the decode runs with the row removed from `engine.DESCRIPTORS`.
`ARMING_STAGES` is `(scan, union, retry150)` and all of those still run,
so the population is exactly what production arms the row on. The cost,
stated: in production a local certificate can feed the next tile's local
head; here neither arm gets that, withheld from both equally.

### The crops are cut on PAGE CORNERS

`measure/yask/README.md` records the measured negative: an ordinary
`holo3 decode` of a crop cut ENTIRELY INSIDE the printed field surveys
into fragments and places nothing, because `survey._adaptive_threshold`
is an Otsu split whose two modes are paper and print. Its named fallback
is "cut crops that include real page margin", and that is what every
case here does — anchored on a corner, so the crop carries both the
top/bottom and the left paper margin. Measured on `I-tl`: the survey
finds 3 regions and 2,516,484 support cells, and the page places.

A crop still changes what a colour head pools over (`crop_parity`'s
colour caveat). It matters much less here than for a parity battery:
this is a WITHIN-CROP A/B where both arms consume identical components,
so the crop moves the level of both arms together, not the comparison.

## 5. The battery

Two cases, both cut on the top-left page corner of sheet I
(`L:c2-cmy8-r0700-p120-x1@3392x2368`, the pooled-CMY8 volume that
closed), each decoded from all three 2400 dpi captures at once.

| case | tile rect | halo | crop | decode | certs | armed | subjects |
|---|---|---:|---|---:|---:|---:|---:|
| `I-nw` | ty 0–3, tx 0–7 | 128 | 3 × 61 MB | 1,517 s (budget) | 158 | 163 | 24 |
| `I-tl` | ty 0–8, tx 0–12 | 192 | 3 × 175 MB | 3,190 s | 514 | 506 | 129 |

`I-nw` stopped at its 25-minute decode budget; `I-tl` ran to exhaustion.
Both stores were audited before the A/B: 158 and 514 decode
certificates, **0 wrong**.

Per-case reports: `<evidence>/local-ab/reports/I-nw.md`, `I-tl.md`, and the
roll-up via `measure.local_ab.summarize`.

### Recommendation

**Hybrid, as an additive stage inside the row.** Keep the union attempt
— it is 1.4% of the row's cost and it clears an observation floor the
single lanes sometimes miss — and when it fails, attempt each covering
lane on its own before giving up. Measured: +3.2% CPU, 2 → 6
certificates, 0 wrong, 0 nulls. That is the toolbox doctrine's shape
exactly: additive over a complete residue, gated by the same codec, one
certificate pays.

Not proposed here: any change to `tiles.union` or `tiles.scan`. This
measurement is about the LOCAL row's residue, where the head is re-fitted
per lane and a lane is therefore a genuinely independent read.

## 6. The simulated control

`src/holo/receiver/tests/_h3_sims.py`'s hard pair is the multi-scan law's own
regime, built on purpose: ONE emitted colour page rendered twice, once
in register and once with the Y plane displaced by a rounded sinusoid,
both with the same noise draw. Not two independent looks at one sheet —
one good look and one systematically wrong one.

Two things it settled before any real battery ran.

**Its residue never arms the local row.** On a 10×10-tile page a colour
row covers exactly ONE tile, so `neighbourhood_tiles` returns the target
alone, `certified_neighbours` is empty, and `_local_eligible` refuses.
Reported by the census, not inferred.

**On easy material there is no second lane at all.** At the suite's
pinned constants the pair decodes 300/300 GT-exact and the positive
control finds NO certified address with two covering lanes: done
geometry means the second capture is never placed where the first
already succeeded. The union question only ever arises where one capture
was not enough — which is worth stating plainly, because it bounds how
much a per-origin stage could ever be worth.

That is why the positive control exists: subjects taken from CERTIFIED
addresses, whose answer is known in advance. It is what exercises the
arms here, and a residue population could not have — a residue that
fails everywhere is equally consistent with a correct harness and a
broken one.

## 7. Invocation

Always from the worktree root, always `PYTHONPATH=.`:

```sh
# cut one case's three crops (one per 2400 dpi capture) and print its record
PYTHONPATH=src:. env/bin/python -m measure.local_ab._cases --case I-tl \
    --evidence-root <evidence> --out build/local-ab/crops

# the battery: decode + both arms + the null + every audit
PYTHONPATH=src:. env/bin/python -m measure.local_ab.harness \
    --case I-tl --workers 3 --decode-diag 8026 \
    --evidence-root <evidence> --out build/local-ab

# the simulated control (seconds, no sheet, no evidence root)
PYTHONPATH=src:. env/bin/python -m measure.local_ab._sim --workers 1 \
    --probe 40 --out build/local-ab
PYTHONPATH=src:. env/bin/python -m measure.local_ab._sim --workers 1 \
    --noise-sd 140 --amplitude-dots 6.0 --probe 40 --out build/local-ab
```

Artifacts land in `--out` (crops, run dirs, `reports/`). The captures,
the archived event log and the generation set are read-only, under
`--evidence-root` (or `$PAPER_EVIDENCE_ROOT`, refused by name when
neither is given — `measure/_evidence.py`) — the published evidence
archive (the 2026-10-09 note below).

2026-10-09: inputs renamed to the published archive paths — sheet I's three 2400 dpi captures
`paper-store-evidence-holo-2026-10/033-xerox-rung-experiments/I/captures/I-canon-2400rgb{,-displaced,-displaced2}.tiff`
(published as `.tiff.jxl`, rebuilt by the release's `tools/unpack.sh`) and its emitted payload
`…/I/emission/payload-counting.bin`. The overnight harvest's event log
(`holo3-overnight-events/sheet-I-events.jsonl.xz`, the poses the crops are cut by and the
production baseline) is NOT in the published archive (tier delete: event journals excluded by
rule) and nothing rebuilds it, so `_cases` and `harness` now refuse by name at the harvest; the
battery's result records are published under `034-sheet-i-full-readout/records/local-ab/`.

---

## Addendum, 2026-08-31 — the hybrid landed, and what a replay can prove

§1's recommendation is built. `tiles.local` now attempts the union
first and, on its failure, each covering lane alone at the same
`STAGE_LOCAL150` gate, stopping at the first certificate
(`src/holo/receiver/plugins/local_ctx.py`, `attempt_sets`). Lane order is
`tiles.component_signature`'s key — the order `store.cover_lanes`
enumerates captures in and `tiles._combine` sums them — so the row has
one lane order, not two. A single-lane subject makes exactly the
attempt it made before: the union IS that lane there.

`--replay` runs `local_ctx.prepare_local` itself, plus both arms and
the null, on every subject.

### THE STORES DO NOT REPRODUCE, and that is the headline finding

Re-decoding does not reproduce this measurement's store, and neither
budget nor worker count fixes it.

| case | recorded | replay A | replay B |
|---|---:|---:|---:|
| `I-tl` decode certificates | 514 | 555 | 552 |
| `I-tl` armed subjects (>=2 lanes) | 129 | 33 | 42 |
| `I-nw` decode certificates | 158 | — | 172 |
| `I-nw` armed subjects (>=2 lanes) | 24 | — | 18 |

Two causes, both measured. A decode at more than one worker is
PATH-DEPENDENT: an early certificate suppresses windows through
done-geometry, so two runs can stop at different fixed points. That is
not inferred — the two `I-tl` columns are THE SAME COMMAND run twice to
exhaustion at four workers, and they landed on 555 certificates over 33
armed subjects and 552 over 42. Neither is the record's 514/129.

And both recorded runs were made on a machine at load 75 — `I-nw`'s
"1,517 s (budget)" run EXHAUSTED in 627 s on an idle machine, 172
certificates deep, without ever reaching its 1,500 s budget. The
recorded residue is partly an artefact of a loaded machine.

The consequence is exact and unavoidable: a tile the ordinary rows
have since certified is no longer residue, so the four per-origin-only
wins cannot all be replayed — three of them are certified tiles now.
**The literal 2 + 4 = 6 is not reachable by re-decoding.** A replay
that reported it would be reporting a store it did not have.

### What IS store-independent, and what it says

The hybrid's defining property does not depend on convergence: the row
must certify exactly where `union or per-origin` does, by the same
lane. Measured over both cases, on every subject:

| | `I-tl` | `I-nw` | total |
|---|---:|---:|---:|
| subjects | 42 | 18 | 60 |
| **row == either arm, same lane** | 42/42 | 18/18 | **60/60** |
| shared with this measurement | 36 | 15 | 51 |
| reproduced the recorded VERDICT | 36/36 | 15/15 | **51/51** |
| reproduced verdict AND winner | 36/36 | 14/15 | 50/51 |
| certificates the row minted | 1 | 2 | 3 |
| wrong certificates | 0 | 0 | **0** |
| N0 null certificates | 0 | 0 | **0** |

**The lane pass reproduced a measured per-origin-only win exactly.**
`I-nw` tile (0, 2) stream Y at 8 px/cell: the union arm failed, the
per-origin arm certified on lane `6ae9d958/L2`, and the row certified
on `6ae9d958/L2`. That is the whole mechanism, end to end, on paper.

### The one shared subject whose WINNER moved, and why

`I-nw` tile (0, 2) stream C at 8 px/cell. Recorded: the union failed
and lane `6ae9d958/L2` won. Replayed: the UNION certified it, so the
row took it at the first attempt and never reached the lane pass. Same
address, same bits, audited against the emitted payload — 0 wrong.

This is the more-converged store showing through: 172 certificates
against the recorded 158 means more certified neighbours, hence a
stronger local head, hence a union attempt that now succeeds where it
once failed. It is the union half of the hybrid earning its keep, not
a regression — and it is why the replay reports verdict parity (15/15)
separately from winner parity (14/15).

### The schedule, verified on real material

`I-tl`: 165 attempts over 42 subjects = one union attempt each, plus
three lane attempts on each of the 41 whose union failed, plus the
early exit on the one union win (1 + 41x4 = 165). `I-nw`: 68 attempts
over 18 subjects, same arithmetic. So the lane pass ran 123 + 48 times
against real multi-capture evidence and produced no wrong certificate
and no spurious win.

Cost, measured: the component build still dominates, and it is shared
by both halves — 421.3 s of `I-tl`'s 445.1 s row CPU, 136.3 s of
`I-nw`'s 145.7 s. The lane pass is the cheap half of a cheap half.

### Invocation

```sh
PYTHONPATH=src:. env/bin/python -m measure.local_ab.harness \
    --case I-nw --workers 2 --replay --fresh
```

Exit 4 = the row is not the arms' union (a row defect). Exit 5 = a
subject BOTH runs had did not reproduce. Replays write
`<case>-replay.json/.md`; the recorded reports above are never
rewritten.
