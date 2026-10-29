# Sheet H, the C plane: the three-ink state, measured (2026-09-06)

Session note, scratch only (main is off limits by ruling). Every number below
comes from the offline `analyzer score` tool plus two per-cell dumps driven
through the analyzer's own sampler at the default arm's pose. Truth is the
sheet-H emission regenerated from the fossil identity and the payload the
close recovered (sha 0ad329fb…, manifest-gated).

## 1. Where C fails

Pooled cell error of the C decision by the TRUE state of the sibling planes at
the cell, default arm `subtract+offset`, both ledgers (H13-pass1, H14-pass1):

| C rows | siblings blank | M only | Y only | M and Y |
|---|---|---|---|---|
| dead band (cols 30–31) | 0.065 | 0.060 | 0.053 | 0.214 |
| marginal | 0.069 | 0.067 | 0.053 | 0.133 |
| live | 0.059 | 0.069 | 0.052 | 0.106 |
| certified reference tiles (M+Y state, arm) | | | | 0.051 |

M under C+Y is the best-read state on the sheet (0.020); Y is flat across
states. The effect is C-specific, sheet-wide, worst in the band.

## 2. It is in the pixels, not in the receiver

Four arms truth-scored on the same C rows (`H14-score-C-{raw,head,conditional,affine}`):
raw red-channel-as-K 0.268 / subtract+offset 0.214 / head 0.215 /
conditional (empirical per-state clusters) 0.228 / subtract+affine 0.217 on
the dead band's M+Y cells. Registration improves every other state by ~0.005
and leaves this one alone. M alone does not hurt, Y alone does not, both do:
a three-layer effect.

Per capture (13 lanes, 1200/2400/4800, rotated and not): M+Y error 0.17–0.26
in every lane; AUC of the red channel for the C decision on M+Y cells rises
only from 0.84 (1200) to 0.88 (4800), against 0.97 for other states.

## 3. What the red channel shows (per-cell dump, `H14-cells-C.npz`, 2.1M cells)

Aperture-filtered red level by true printed state, dead band:
W 0.62, C 0.38, CM 0.37, CY 0.37, M 0.61, Y 0.63, MY 0.62, **CMY 0.47** (sd
0.090 vs 0.066 for C). One C layer on paper takes 0.24 off the red level;
the same layer on an M+Y pile takes 0.15 in the band, 0.19 in the open
tiles elsewhere, 0.21 on certified tiles. Not bimodal: 43 % of the band's
CMY cells sit above the MY cells' 10th percentile, 3 % above their median.

Raw 24×24-px red patches at 4800 dpi (`H14-patches-C.npz`), mean radial
profile from the cell centre outwards:

| dead band | r 0–2 px | 2–4 | 4–6 | 6–8 | 8–10 | 10–13 |
|---|---|---|---|---|---|---|
| C on paper | 0.359 | 0.367 | 0.381 | 0.402 | 0.425 | 0.450 |
| **C on M+Y** | 0.472 | 0.471 | 0.469 | 0.467 | 0.467 | 0.470 |
| M+Y, no C | 0.634 | 0.628 | 0.616 | 0.599 | 0.581 | 0.562 |

The third-layer C has no dot core: its deficit is flat across the cell and
its surround. A box aperture centred on the cell reads it at 60 % strength.
Most plausible mechanism: the third toner layer on a two-layer pile is laid
diffusely (charge screening / transfer on toner), which also explains why the
plane laid third is the one that suffers. Toner order not verified.

Context: on M+Y cells in the band the error FALLS with the number of C-inked
neighbours (0.33 isolated → 0.18 at eight), the opposite of the usual
context trend; the isolated dot on a pile is the worst case.

## 4. What compensates, measured

Oracle bounds on the dead band's M+Y cells, single lane: best red threshold
0.208, QDA on RGB 0.194, arm 0.231. Combined over the 11–13 lanes:

| calibration of the arm's LLRs | M+Y err | all-state err |
|---|---|---|
| as given | 0.219 | 0.088 |
| per-(lane, state) Platt, fitted on the certified neighbours (blind-able) | 0.191 | 0.076 |
| same, fitted on the marginal tiles | 0.166 | 0.070 |
| per-(lane, state) Platt, oracle | 0.155 | 0.066 |
| per-(lane, state, context) Platt, oracle | 0.143 | 0.059 |

The arm's LLRs are OVER-confident on M+Y cells (|L| 2–4 claims 5.8 %,
measures 15.7 %) and UNDER-confident on every other state (a ≈ 1.3). Per-tile
information rate with a production-style final calibration, blind variant:
dead band median 0.797 → 0.836, marginal 0.912 → 0.922, live 0.912 → 0.919;
no sampled tile crosses 1.0 from calibration alone. Per-state calibration is
only possible where the siblings are certified (the band: cargo cleanable 1.0;
the open live/marginal C tiles: 0.0, their Y is open too).

A blind per-(tile, lane, state) two-Gaussian mixture on the red channel is
worse than the arm everywhere except the band's M+Y cells (0.219 → 0.190).

**Learned patch discriminant** (linear, 576 px, red only, shrinkage LDA,
tile-parity cross-validation, truth labels), 4800-dpi lanes, single lane:

| group | cells | box mean | patch LDA |
|---|---|---|---|
| dead band, M+Y | 85k | 0.208 | **0.149** |
| dead band, M+Y, isolated C (0–1 neighbours) | | 0.329 | 0.109 |
| dead band, siblings blank | 30k | 0.083 | 0.047 |
| certified tiles, M+Y | 57k | 0.095 | 0.056 |
| certified tiles, siblings blank | 20k | 0.075 | 0.028 |
| live open, M+Y / blank | | 0.115 / 0.096 | 0.066 / 0.047 |
| marginal open, M+Y / blank | | 0.158 / 0.097 | 0.127 / 0.059 |

Trained on certified tiles and applied to the band: M+Y 0.196, blank 0.050,
so the ordinary-cell gain transfers and the three-ink gain is partly
band-local (the patches were cut at integer-pixel pose; a pose-resampled
patch should close most of that gap). The discriminant for ordinary cells is
centre-negative / surround-positive (a centre-surround filter); for C on
M+Y it is flat and wide, matching the profile above. This is DESIGN §13's
"patch discriminant — the largest untried lever", now measured on C.

Combined-lane rate estimate with patch LLRs: see §5.

## 5. Combined-lane estimate (4800 lanes only, 3.3–3.6 lanes per cell)

Per (lane, state) patch LDA, tile-parity CV, Platt per lane, clipped sum over
the lanes, one final per-tile Platt (even/odd cells), R from the state-
reweighted mean information (`analyze_combined.py`, `H14-patches-C2.npz`):

| group | detector | blank | M | Y | M+Y | R per tile median (min–max) | tiles ≥ 1.0 |
|---|---|---|---|---|---|---|---|
| dead | arm | 0.058 | 0.059 | 0.050 | 0.198 | 0.639 (0.48–0.85) | 0/14 |
| dead | **patch LDA** | 0.031 | 0.032 | 0.026 | **0.034** | **0.956 (0.88–1.06)** | **2/14** |
| marginal | arm | 0.056 | 0.066 | 0.042 | 0.124 | 0.791 | 0/8 |
| marginal | patch LDA | 0.048 | 0.055 | 0.045 | 0.115 | 0.899 | 0/8 |
| live | arm | 0.053 | 0.068 | 0.045 | 0.068 | 0.833 | 0/8 |
| live | patch LDA | 0.030 | 0.034 | 0.027 | 0.028 | 0.968 | 1/8 |

The single-lane M+Y error of the patch filter (0.149) falls to 0.034 over
3.3 lanes, where the arm's 0.231 falls only to 0.198: the filter's residual
errors are capture noise and average out, the box mean's are print-frozen
and do not (the multi-scan law, again). With all 13 lanes the arm gains
+0.16 R over its 4800-only figure; the same lift would put the band's
median above 1.0.

Caveats: truth labels for training (blind training uses certified cells —
ordinary-cell gain transfers, the band's three-ink gain is partly band-local);
per-state filters need certified siblings (true in the band, not for the
open live/marginal C tiles, whose Y is open too — their rows are optimistic);
patches cut at integer pixels; red channel only; 4800 lanes only.

## 5b. The proposal in miniature: halo-trained, then segment the tile's own M+Y population

`analyze_selftrain.py`. Per 4800 lane: LDA trained ONLY on the certified
edge tiles' three-ink cells (the halo's labels), applied to each dead-band
tile's M+Y cells; then refined by self-training on that tile's own cells
(pseudo-labels from the 60 % most confident, 4 rounds); a decoder-feedback
proxy hands 25 % of the tile's cells their true bit (what BP returns when on
track). Mean over 85 tile×lane pairs, single lane / combined over the lanes:

| detector | single lane | combined (6 lanes/cell) |
|---|---|---|
| box mean, tile-median threshold | 0.203 | 0.191 |
| halo-trained patch filter, no target labels | **0.119** | **0.062** |
| + self-training on the tile's own M+Y cells | 0.114 | 0.060 |
| + decoder-feedback proxy (25 % of cells) | 0.085 | 0.049 |
| permutation control (shuffled halo labels) | 0.460 | |

The per-LANE halo training is what matters (a filter pooled across lanes
transferred at 0.196; per lane 0.119 — the pooled analytic under-read the
gain). Segmenting the tile's own population adds little once the halo filter
exists; decoder feedback adds more. All blind-able: labels are certified
neighbours, then the tile's own confident cells, then BP's confident cells.

## 6. Consequences

- Receiver, in order of value: (1) the learned per-plane, per-lane, per-state
  patch filter in cell coordinates, trained on certified cells (blind by
  construction); (2) per-state LLR calibration where siblings are certified,
  plus the context axis; (3) nothing spectral — the red channel already
  carries all there is, a filter-and-read-as-K is the worst arm.
- Format, next print: C's third-layer loss is sheet-wide (~0.10–0.21 on a
  quarter of its cells), so C wants the rung margin as much as Y; or an
  alphabet that never prints CMY (cmy7's state set with cmy8's codec: a new
  row). A modulation constraint against isolated C dots on M+Y cells would
  target the worst case but is coding-theory work.
- Artefacts: scratch/analyzer/H14-score-full, H14-score-C-*, H14-cells-C.npz,
  H14-patches-C.npz, H14-patches-C2.npz (with cell coordinates), and the
  scripts in this session's scratchpad (dump_cells.py, analyze_cells.py,
  dump_patches*.py, analyze_patches.py, analyze_combined.py).
