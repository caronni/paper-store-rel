# Experiment 019 — PLATEN-SEGMENT: lattice-candidate acquisition

**The front stage of the fragment receiver: take one platen scan and hand the
next stages a clean set of candidate payload-lattice regions.** Angle, pitch,
pilots and BCH are all downstream (next). Zero print — all analysis on
existing scans + synthetic fixtures.

## Goal and scope

Input: one glass-platen scan — **4800 dpi, grey, c3** confetti (3 print-dots/
cell at 600 dpi → 24 px/cell native). Confetti are real scissor-cut scraps of
a printed archive sheet; a scrap = a printed **field** (~50 % coverage
scrambled lattice) usually with some blank **paper margin** at its torn edge,
lying on a scanner **backing** (white lid, or a dark sheet).

Output: `list[LatticeCandidate]` — each a connected region of cell-scale
**modulation** (the payload field), with its mask (raw glass frame, no angle
correction), bbox, area, and a **sub-grain** flag. Plus an annotated PNG.

Does NOT (deliberately): measure pitch, correct angle, lock the lattice, read
pilots, or decode. It answers only *"where is there a payload lattice, and how
big is each patch."*

## The detector — `segment.find_lattice_candidates`

Five decisions, each measured, no legacy paths:

1. **Signal = modulation, not brightness.** A payload field is the only thing
   on the platen that varies at the cell pitch; blank paper margins and the
   backing are homogeneous and carry no bits by definition. The statistic is
   the per-cell local **standard deviation** (`_activity_map`). This is
   **backing-independent** (works on a white lid or a black sheet — it never
   reads `backing`) and immune to the `estimate_backing` border-flip. On a
   white-lid scan it also drops the *paper margins* that the receiver's
   `|mean − backing|` segmenter engulfs (019 §Qualification).

2. **Multi-cell window (`win_cells = 2`).** A c3 cell is SOLID (one bit = a
   whole 24 px block one colour), so a *one-cell* std window reads modulation
   only via cell-boundary misalignment — fragile (real-e018 field-std p10 =
   10, right on the threshold). A 2-cell window always spans a transition:
   p10 rises to 32. Cost is **flat in window size** (`uniform_filter` is O(N)
   running sums — measured 1.79→1.85 s from 24→144 px); the cost lever is dpi,
   not the window.

3. **Growth = hysteresis from an eroded seed** (replaces blind grow/erode):
   - strict-threshold **seed** `act > std_hi`, then **eroded** (`seed_erode`)
     — a real field's seed core is solid (98 % of cells > `std_hi` on real
     toner) and survives; a thin high-std **edge line** (torn-paper margin,
     scrap-edge step) has no solid core and vanishes → no thin-sliver false
     candidates, and the disconnected scrap-edge ring dies here too;
   - `binary_propagation` grows the seed into connected **loose** cells
     (`act > std_lo`) — a signal-following boundary that keeps faint field
     joined to the core without seeding lid noise (connectivity lets `std_lo`
     sit below the lid tail);
   - a light `open` despeckles; a **signal-strength gate** then drops any
     candidate whose MEDIAN cell modulation is below `min_med_std` (a
     weakly-modulated lid/edge blob — measured: real fields median 37–44, a
     lid sliver 12). **No `fill_holes`:** on a scrambled field interior holes
     are rare and, where real, are data-absent (better left as an erasure for
     the FEC than claimed as lattice) — measured a no-op (0.3 % of cells, 0
     candidates changed) and a latent enclosed-lid risk. Connectivity keeps a
     field one blob regardless.

4. **No angle correction.** Candidates stay in the raw glass frame;
   `lattice_angle`/rotation belong to the next stage.

5. **Sub-grain flag.** A candidate whose equivalent square is `< grain_mm`
   (6 mm ≈ 47 cells) is flagged: below the measured correlation self-placement
   floor (016.7), it has too few pilot sites to localize from its own pilots
   in isolation → it needs optical jigsaw (neighbour adjacency) or the fountain
   tolerates its loss.

**Native footing, no decimation.** The pipeline runs at the input dpi (24 px/
cell at 4800). A real A4 scan is 2.3 Gpx → ~41 GB measured RSS, peaking ~50 GB
with the `uniform_filter` temps — **tight** on a 64 GB box; `--decimate 3` (→
1600) gives headroom and is an explicit opt-in, never a silent default. Input
is memmap-loaded; an RGB TIFF is reduced to luma; a 16-bit scan is normalized
to 8-bit grey units; a degenerate/tiny image returns `[]`.

The receiver's `segment.segment_pieces` (the `|mean−backing|` path the 018
session decoder rides) is **untouched** — byte-identical to pre-019, kept for
its edge-to-edge-confetti case where field == scrap.

## Calibration (real e018, native 24 px/cell, measured)

Per-cell 2-cell-window std:

| region | std p50 | frac > STD_HI (22) |
|---|---|---|
| data field (real toner) | **42.7** | 97.9 % |
| lid / blank paper | **1.0–1.1** | 0–2 % |

A ~40× gap in the bulk. The distributions do overlap in the *tails* (lid p99
≈ 41 from a 1-cell window; a torn-edge step is high-std), which is exactly why
growth needs the eroded-seed shape test **and** a signal-strength gate, not a
single threshold. `std_hi=22` seeds the field's solid core; `std_lo=8` (below
the lid p90 8.7, safe under connectivity) recovers faint field; `seed_erode=2`
removes thin edge slivers; `min_med_std=25` (below the 37–44 real-field band,
well above a measured 12 lid artifact) drops weakly-modulated blobs. Together
they take confetti-1 from 20 candidates (with lid slivers) to **17 clean**.

## Qualification (measured comparisons)

**(a) Hysteresis vs blind grow/erode** (`qualify_e019.py`, constructed
solid-cell fields with exact GT — normal / interior-quiet-zone / torn / faint):

| metric | blind (close+open+dilate) | HYSTERESIS |
|---|---|---|
| IoU vs GT field | 0.82–0.85 | **0.90–0.96** |
| mask area / true field | 1.16–1.22 (grow-out bloat) | **1.04–1.11** |
| components (incl. field with interior blank) | 1 | 1 |

Hysteresis is uniformly tighter, follows the torn boundary instead of a bloated
box, and an interior blank neither fragments the field (connectivity) nor gets
claimed as lattice (the quiet 0.90 vs 0.96 is that honestly-excluded hole).

**(b) Multi-cell vs per-cell window** (real e018): field-std p10 10 (1 cell) →
22 (1.5) → **32** (2 cells) — the per-cell fragility fixed, no "grey mush"
(variance rises with the window; mush is a mean effect).

**(c) Modulation (019) vs deviation (018)** (`compare_texture_vs_deviation.py`,
same scan/footing): on confetti-1 the receiver's `deviation` finds ~24 patches,
modulation ~19; the ~5 deviation-only patches all read per-mask modulation
**std < 8 = no data** (blank paper strips / torn-edge shadows) — the 018.2
"toner-free phantoms". Modulation misses no real field (a strict subset).

## Real run — six e018 4800-dpi scans → six PNGs in `scratch/e019/`

All six segmented with the final detector (native, ~3.3 min/scan): **confetti
1/2/3 = 17 / 10 / 8 candidates; the re-scans (2ndtake) = 17 / 10 / 8** —
identical counts across re-scans (repeatable), **0 sub-grain, 0 false**
candidates. The seed-erode + median-strength gates took confetti-1 from 20
(with lid slivers) to **17 clean** = the 018.2 real-piece count. The large
empty lid area produces zero candidates. Blue contour hugs the torn data-field
edge and excludes the white paper margins; the receiver's `deviation` segmenter
would add ~5 non-data phantoms here (019.3 §Qualification).

**Adversarial review** (workflow, 3 lenses → verify-by-reproduction): 12
confirmed, 1 refuted. Fixed: RGB-TIFF luma reduction (a native-default crash on
colour scans — real Canon scans are RGB), 16-bit + degenerate-input guards,
`--dots-per-cell` (c2 support), a `dropped_below_med_std` diagnostic (surfaces
a silently-gated faint field), two GT-anchored test tightenings, and **dropped
the calibration-coupled `--win-cells`/`--std` CLI knobs** — they silently
decouple from the fixed `min_med_std`/`seed_erode` gates, so they were a
footgun, not a feature (the thresholds are calibration internals, tunable only
at the API).

## Deliverables

- `src/paperholo/segment.py` — `LatticeCandidate` + `find_lattice_candidates`
  (+ `_activity_map`); `segment_pieces` reverted to pre-019 (receiver intact).
- `experiments/019-platen-segment/gen_platen_fixture.py` — deterministic
  solid-cell black-backing + white-margin c3 fixture (demo/tests).
- `experiments/019-platen-segment/analyze_e019.py` — ingest → acquire → PNG.
- `experiments/019-platen-segment/qualify_e019.py` — hysteresis-vs-blind
  qualification (GT cases + figure).
- `experiments/019-platen-segment/compare_texture_vs_deviation.py` — 019-vs-018
  detector comparison on a real scan.
- `tests/test_e019.py` — GT-anchored (9): fields-not-margin, backing-agnostic,
  sub-grain, hysteresis quiet-zone, torn-shape, multi-cell, viz, and the
  `segment_pieces` receiver-revert guard.

## Limits / deferred (honest)

- Thresholds calibrated on **white-lid** e018; the **black-backing +
  white-margin** case is fixture-only (no such real scan exists yet).
- An interior blank in a field is left as a hole (honest data-absence for the
  FEC, not filled). A low-modulation run that reaches the field EDGE and cuts
  across it would still split the field into two candidates — genuine but rare
  on a scrambled field.
- Sub-grain candidates are flagged, not recovered — that needs the jigsaw /
  fountain stages.
- Everything past detection (angle, pitch, pilots, BCH) is the next stage.
