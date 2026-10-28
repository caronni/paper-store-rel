# Experiment 029 — first physical holo-v1 print: ink-tight c2-r0700, hardware-verified

Status at 2026-08-04 (print-day, evening): **VERIFIED byte-exact.  This is
the FIRST PHYSICAL PRINT OF HOLO FORMAT v1 and the first hardware-verified
holo volume** — 465,580 bytes recovered exactly from one A4 sheet printed
at ink-tight margins on the HP M281 and scanned once on the Canon at 4800.
Provisional-receiver evidence and single-sheet/single-day channel evidence;
explicitly NOT a rate-ladder, payload-safe-margin, or receiver
qualification.

## Objective

- Execute the e028 campaign's optional W7b payload validation
  (docs/CHARACTERIZE-WORKPLAN.md): ride the measured M281 print clip
  (~4.15–4.28 mm, e028.2/028.3) with a real payload page at tightened
  margins instead of the locked 6 mm default.
- Highest-capacity single-page profile printed to date: K-only c2@600,
  inner rung r0700, fountain dial q=0.7.

## Sheet (emit record)

- Emitted 2026-08-04 into
  `scratch/e028/holo-c2-r0700-q07-ink-counting/` by a one-off generator
  (`generate.py` in that directory; original inline form kept as
  `orig-gen`) that injected a pre-registry `hp-m281-ink` printer at
  4.5 mm.  The row now lives in `src/holo/devices/registry.py`
  (commit 462fdf2, self-declared clip-geometry probe — NOT a payload-safe
  promotion); `./confetti.py generate --coding c2-r0700 --printer
  hp-m281-ink` reproduces the spec.
- Spec `c2-r0700@3392x2368` — deliberately NOT in `FORMAT_ROWS`: blind
  discovery refuses this geometry; decode requires explicit
  `--coding c2-r0700 --printer hp-m281-ink`.  Seed
  `holo/v1/c2-r0700/3392x2368`.
- Geometry: 3392×2368 cells (53×37 tiles = 1961), cell = 2 dots = 84.67 µm;
  field 287.2×200.5 mm; margins requested 4.5 mm → actual borders
  ~4.91/4.74 mm (64-cell tile quantization), i.e. ~0.5–0.7 mm inside the
  measured print clip.
- Payload: counting bytes, 465,580 B, sha256
  `e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9dd165787af`.
  Fills the fountain capacity to within 4 bits
  (K·S = 1356·2747 = 3,724,932 vs envelope 3,724,928 bits).
- Volume: fountain-v2, K=1356 of N=1961 symbols (1 symbol/tile),
  q dial 0.7 → effective K/N 0.6915.
- `page000.ps` sha `063f3bba429ee450…`, GT sha `3e48560378b5613e…`,
  manifest (sidecar only — v1 sheets decode with zero out-of-band data).

## Print + scan log

| run | date | action | details |
|-----|------|--------|---------|
| 029.0p | 2026-08-04 evening | print | HP CLJ M281fdw (<host>), raw 9100 (manifest print path); part of print-day; media/tray = session stock, not separately recorded |
| 029.0s | 2026-08-04 21:08 | scan | Canon 4800 grey, full platen → `scratch/e028/hp-canon-c2-ink-counting.tiff` sha256 `d9c4e932b904b8173ef0bf08165f384ed2ce644105f58965d2dca14165672c22` (2.29 GB) |

## Decode

```
./confetti.py decode scratch/e028/hp-canon-c2-ink-counting.tiff \
  --scan-dpi 4800 --coding c2-r0700 --printer hp-m281-ink \
  --state <dir>/receive.state -o recovered.bin [--diag] [--complete --refine]
```

- The first plain decode verified the volume the same evening.  The
  retained state is the subsequent FULL-HARVEST run: one fresh invocation
  with `--complete --refine`, full 133-page cold hypothesis domain,
  12/12 levels (ordinary ladder 2/4/8/16 ppc + 4 mop-up + 4 refine
  levels), deferred close consulted once at the end → VERIFIED.
- Receiver status PROVISIONAL (historical stand-in constants); this is
  the first real-capture full-domain production-receiver run on record
  (policy id + qualification notes in `receive.state.diag/report.json`).

## RESULTS (029.1, from the retained state + diag)

- **Close VERIFIED: `recovered.bin` = 465,580 B, sha == golden — byte-exact.**
- **Tiles: 1940/1961 certified = 98.93%** (+5 of those from the selective
  BP150 retry), 21 failed, 0 low-confidence, 0 conflicts.  Surplus over
  K: 584 symbols.  This one sheet's yield would have carried q ≈ 0.98 —
  a single-sheet observation only; rate calls stay on multi-sheet minima.
- **Net density: 64.7 b/mm² over the payload field (59.7 b/mm² per full
  A4) = new best hardware-certified net on record** (e016: 55.1 b/mm²,
  +17%; 1.29× e016's bytes on the same nominal page size; ~2.1× the
  e018b-C2 fixed-key page's 226,178 B).
- Geometry/coverage: 1 region located+placed, mapped footprint 99.8%
  (7,818,243/7,836,156 cells); placements 1451 accepted / 161 unresolved /
  0 quarantined; words 229 match / 531 insufficient / 125 refused /
  0 conflict; LDPC 2933 calls (3279 attempts folded).
- **Failed-tile geography (state-derived) — OPERATOR ATTRIBUTION:
  HP weak horizontal lines (known M281 issue).**  Visible weak
  horizontal density lines on the printed sheet; the receiver worked
  through most of them (1940/1961 certified) and left 21 residual
  failures.  Earlier record: 001 banding probe + 002 "banding =
  bounded null" at the channel-params level; 013 F1 (sim) found
  fixed-position horizontal bands govern tile success, not mean BER;
  016.2 saw scan-varying horizontal bands on the M281 c2 volume
  (alongside the later-retracted "print-frozen edge stripes").
  - Extreme-column tiles: col 0 rows {14,15,16,20,21,22,42} (7);
    col 36 rows {20,21,22,48} (4).  Rows 20–22 fail on BOTH extreme
    columns — same y as a weak line crossing the page.
  - Interior row-42 band: (42, 1..7) + (42, 10..11) = 9 tiles,
    ≈235 mm from the top paper edge, left half — the dominant single
    residual, sitting on one of the weak lines the receiver could not
    fully erase.
  - Interior singleton (48,32).
  - Net: the ink-tight margin risk materialized as only 11 of the 106
    extreme-column tiles and ZERO of the 74 top/bottom-row tiles.
    The dominant loss is printer banding, not the margin.  (The
    margin experiment still stands as confirmation that 4.5 mm is
    survivable; it is just not what killed these tiles.)

## Receiver findings (value of the harvest run beyond the milestone)

- Two real receiver bugs found and fixed during the session:
  - **Verified-close resume crash** — `ProductionClose._gated` built
    `CloseExecution(state.close, None)` eagerly, tripping the
    verified-payload invariant on any VERIFIED resume/`--complete`
    replay; fix = terminal states consult the fountain (the documented
    PHASED-SCHEDULE behavior).  Commit 19b7e4e + regression test.
  - **Diag parked-chip overlay** — chips were frozen in pane pixels, so a
    later ladder/mop-up survey's underlay change piled them wrong-size in
    a corner; fix = lane-space chips projected through per-(capture,lane)
    survey transforms at draw, and empty mop-up surveys preserve the
    underlay.  Commit 32345ef + discriminating tests (distinct-frame
    cross-lane test with a negative control).
- Registry: `hp-m281-ink` row, commit 462fdf2.
- Scheduler observation for the record: M-level parked windows carry NO
  NeedMap pre-gate at the address stage (`place_mopup` never sees the
  certificate frontier) — under `--complete` every parked window pays the
  full priced route ladder including cold search over the whole page
  domain.  The default path is covered by close preemption (verified
  close kills the tail), so this only costs `--complete` harvests.
  Candidate optimizations, not built: predicted-span-certified skip for
  parked windows; `--page 0` for single-sheet volumes (collapses the
  133-page cold domain — the dominant observed cold cost).

## Caveats

- ONE sheet, ONE day, one engine+scanner pair.  No promotion of any
  kind follows: the 4.5 mm margin stays an experiment (E025/E028 canary
  doctrine for payload-safe qualification), r0700/q0.7 is not a ladder
  call, and the receiver stays provisional (this run is evidence toward
  the open real-capture yield/resource item, not its closure).
- Exact-spec decode, not blind discovery (geometry intentionally outside
  the catalog).
- Wall time not cleanly measured: the session was interleaved with the
  two bug fixes, and events carry no wall clock by timing-neutrality
  design.
- Operator print metadata (media brand/tray/density) not separately
  recorded.

## Artifacts

- Volume dir `scratch/e028/holo-c2-r0700-q07-ink-counting/`:
  `page000.ps`, `page000_gt.npy`, `manifest.json`, `payload-counting.bin`,
  `generate.py`, `orig-gen`, `receive.state`, `receive.state.diag/`,
  `recovered.bin`.
- Scan `scratch/e028/hp-canon-c2-ink-counting.tiff` (sha `d9c4e932…`).
- Commits: 19b7e4e (close fix), 32345ef (diag fix), 462fdf2 (registry).
- Durable memory: `.claude/memories/e029-holo-v1-first-print.md`.

## 029.2 — DONE-GEOMETRY census (2026-08-05, zero print, read-only)

The `docs/DONE-GEOMETRY.md` §8 census executed over this experiment's
retained state (sha `bdd7b293fefee87c…`) and the final invocation's diag
events (sha `68ed1b91649b8801…`, M/R tail only — earlier invocations'
logs were replaced).  Harness: `census_done_geometry.py` in this
experiment's directory; checked artifact `DONE-GEOMETRY-CENSUS.json`.
Method and full numbers: DONE-GEOMETRY §8a.  Headlines:

- **719/1,479 committed placements (48.6%) were pixel-gateable** under
  the proposed done-geometry law (conservative simulation: 1-cell union
  erosion, supported-cells-only containment).
- l02+l03 placed 630 windows for 11 certificates; **75% (472) gateable**.
- The m00 `--complete` tail planned 440 windows and spent 160 priced
  colds (133-page sweeps) + 160 rest-word decodes for 2 certificates;
  **398/440 windows (90%), 136/160 colds and word-rests (85%)
  gateable** — the quantified form of this log's earlier scheduler
  observation (`place_mopup` sees no certificate frontier).
- R lanes: 0/28 gated — the gate does not touch live refinement work.
  m01–m03 were already empty (v0.37 parked-emptiness pre-gate works).
- Gated windows minted zero certificates, provable by construction: a
  fully-done supported extent cannot contain an uncertified tile's
  pixels.
- `payload.pruned_terminal_patches` = 0 for the entire session: with one
  region and 21 never-certifying tiles, region-granular L1 cannot fire —
  the waste lives exactly in the window-granular gap the design targets.
- Caveats: one intact dense sheet (favorable regime); fragment/confetti
  census still owed; counts not seconds (events are timing-neutral).
