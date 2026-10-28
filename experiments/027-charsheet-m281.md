# Experiment 027 — charsheet-1 on the HP M281 (first physical track-2 data)

First physical run of the holo track-2 characterization instrument
(HOLO-DESIGN §13.13/§13.14; src/holo/characterize). Two BYTE-IDENTICAL
copies of one sheet — including identical PRND content draws (the
emitter has no copy axis; user-flagged 2026-07-20 post-print). What
this pair honestly measures: print-to-print repeatability at FIXED
content (engine/day noise isolated from content), the first real
payload-safe-rectangle measurements, and one copy serves the same-sheet
cross-scanner sensor pair. What it does NOT provide: independent
content draws — A+B pooled must never be presented as two independent
sheets, and this is NOT a multi-sheet-minima start. Open discussion
(REASONING-LOG 2026-07-20): copy axis for the emitter; which e025
properties (machine strip, morphology/tone arms, c1/c4 anchors, motif
factorials) return in a companion instrument page.

## Sheet

- Emitted 2026-07-20: `./confetti.py characterize emit --printer hp-m281`
  -> `build/charsheet1-hp-m281-a87c3d2fb40b/` (regenerable, sha-gated;
  build/ is git-ignored — these shas gate reuse):
  - charsheet.ps  sha256 `447718ada69c339403ad29a0c403841f74afcb088dbd833c9181d106aa25d11d`
  - GT (packed)   sha256 `a87c3d2fb40b3f5b54661d9aa8a1b03d422368a2b6dd528ea43616e34a7c0d2b`
- Contents: 3x3 stratified c2+c3 PRND fields, 54 production coupon
  tiles (c2-r0550 / c2-r0700 / c3-r0550), 4-edge canary ladders
  {3.5, 4.25, 5.0, 5.75}mm + 12mm references (permuted orders, 2 reps
  short / 3 reps long edges), solid ticks 2.0-6.0mm, corner Ls, GT-bound
  ID row, 4 blank witnesses.
- NOTE: this hp-m281 sheet differs from the frozen default-printer
  layout golden only in the ID row (printer_id is part of the layout
  identity hash).

## Print log

| run | date | engine | media | path | file | result |
|-----|------|--------|-------|------|------|--------|
| 027.0a | 2026-07-20 | HP CLJ M281fdw (<host>) | plain A4 | raw 9100 via scripts/print_plane.sh | charsheet.ps (sha 447718ad… verified at send) | SENT — 8,768,321 bytes accepted |
| 027.0b | 2026-07-20 | HP CLJ M281fdw (<host>) | plain A4 | raw 9100 via scripts/print_plane.sh | charsheet.ps (sha 447718ad… verified at send) | SENT — 8,768,321 bytes accepted |

Both sends completed with the wrapper's sha verification; jobs sent
back-to-back (JetDirect buffered). User authorization in-session
2026-07-20 ("print now").

Mark copies A/B on the BACK of each sheet (front-side marks would enter
the scan).

## Scan protocol (user)

Canon flatbed, GREY, descreen/sharpen/auto-contrast OFF, **all four
paper edges inside the frame** (the margin instruments live at
2.0-12mm from the paper edge). Per sheet:

1. One 1200 dpi grey scan (primary footing).
2. Optional but valuable: one extra 1200 dpi scan of copy A with the
   sheet re-placed (multi-scan variance), and/or one 2400 dpi scan of
   copy A (fine-footing ladder for c2).

Suggested names: `scans/m281-charsheet1-{A,B}-canon-1200gray.tiff`.

## Analysis (after scans arrive)

```
./confetti.py characterize analyze scans/m281-charsheet1-A-canon-1200gray.tiff \
    --scan-dpi 1200 --sheet build/charsheet1-hp-m281-a87c3d2fb40b \
    --footings 1,2 --png scratch/charsheet1-A-overview.png
```

Envelope (pre-registered, from the record — NOT pass/fail gates, the
analyzer refuses on its own gates; these are sanity anchors):
- qualified=True, 4/4 corners, ID match.
- c3 fields: low-% BER class (M281 c3 hardware anchors 2-4% at 2px/dot
  footing; the supervised per-window number should sit at or below).
- c2 fields at 1200 (2px/dot): 8-14% class (the known coarse-footing
  regime); at --footings 2 worse, monotone.
- c3-r0550 coupons: expected word+payload exact at c3-class BER.
- Payload-safe rectangle: FIRST REAL MEASUREMENT — the e025 pair never
  established one; margins may legitimately come out at any gap or
  refuse. Ink reach expectation ~3.5-4.0mm (measured e025 ticks).

## Results

### 027.1 — copy (unspecified A/B), Canon 4800 grey, first real data

Scan: `scratch/a.tiff`, sha256 `23c61775bd97db8285ce36f60f2fbbb7dd
69caa514c0d92a3284a31cfb8af01b`, 40832x56128 uint8 grey.
Report: `scratch/charsheet1-a-4800-report.json` (+ overview PNG).
Command: `characterize analyze scratch/a.tiff --scan-dpi 4800
--sheet build/charsheet1-hp-m281-a87c3d2fb40b --footings 1,2,4`.

**GATE INCIDENT (fixed pre-result, one variable):** first pass REFUSED
on corner rms 13.26 px — a PIXEL constant (6.0, calibrated on 1200-dpi
sim renders where rms read 0.01-2 px). 13.26 px at 4800 = **1.66
dots** = the measured M281 print-frozen wander class that a 4-corner
affine cannot absorb. Gate re-expressed in dots (<= 3.0 dots); the
should-pass-control-fails-the-gate rule applied.

**QUALIFIED. Headline numbers (supervised floor arm, reporting-parity
cells only):**

| channel | 4800 native (16px/dot eq) | /2 (2400) | /4 (1200, 2px/dot) |
|---|---|---|---|
| c3 | **0.0123%** | 0.0085% | 0.0133% |
| c2 | **5.08%** | 5.73% | 6.19% |

- **c3 is ~100x cleaner than the working 2-4% anchors** once geometry
  (48-cell windows + band y-refinement) and detector (per-window
  min-error) are solved — and stays clean even at the 1200 footing.
  The old anchors were blind-receiver numbers; this is the channel.
  Rate-ladder implication (single sheet, floor arm — NOT a freeze):
  c3 has enormous rung headroom on this engine.
- c2 5.1% at native = the known regime (production ctx reads 2-5%;
  the floor-vs-ctx gap is expected and is the Arm-2/arm-3 story).
  Monotone degradation across the footing ladder as designed.
- **Coupons at the capacity cliff, textbook:** c3-r0550 18/18 strict;
  c2-r0550 17/18 (one stratum failure); **c2-r0700 4/18** — at 5.1%
  hard-decision BER the r0700 rung (hard capacity edge ~5.0%) sits
  exactly on its cliff. Real datum: c2-r0700 on this engine needs
  soft/ctx detection, hard-decision is marginal.
- **First measured payload-safe rectangle on record** (e025 never
  established one): c2 margins T/B/L/R = 4.25/3.5/4.25/5.0 mm, c3 =
  4.25 mm all edges; physical ink reach 4.0 mm on every edge (matches
  the <=4 mm cross-engine tick fact). The 6.0 mm policy margin has
  ~1.5-2 mm measured headroom; right edge is the weakest (c2 5.0 mm).
- CAVEAT for the generic-sheet design: a 6 mm canary patch at gap g
  spans g..g+6 mm, so a pass at g=3.5 < ink reach 4.0 reflects the
  patch AGGREGATE, not its leading edge — per-row-band canary grading
  is the v2-instrument refinement.
- All 4/4 corners, orientation margin 1.95, corner rms 1.66 dots =
  the real warp; F5 memory fix held at true 4800 (2.29 GB scan).

One content draw, one print, one scan, supervised floor arm — rate
decisions wait for copy B + days + the production-detector arm.
