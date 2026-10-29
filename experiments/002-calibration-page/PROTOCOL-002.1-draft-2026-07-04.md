# Run protocol 002.1 — composite emission probe (DRAFT)

Goal: find a composite emission path that is **bit-faithful** on the M281 RIP.
002.0 canary A proved `put_cmyk_bitmap` (DeviceCMYK 1-bit `image`) is
re-screened (~165 lpi ±14° / ~212 lpi 45° plane-angle screens, 28.5 dB peaks)
while single-plane `imagemask` is clean. This sheet prints the same
overlapping-plane content through five emission paths and lets the scan pick
the winner. Hardware rules apply: ask the user before any print/scan; one
sheet, one log entry.

## Artifact

- `gen_composite_probe.py` -> `build/composite_probe.ps` (sha256 in
  `build/composite_probe_manifest.json`, key `ps_sha256`; jobid + seed on the
  printed header), `build/composite_probe_gt/*.npy` (per-plane INTENT ground
  truth). Byte-identical regeneration; the manifest sha gates reuse.
- Preflight gate (must be green before printing):
  `env/bin/pytest -q tests/test_composite_probe.py` — determinism, geometry,
  psgen default-path byte-identity (gridtest sha `904a5393...`), and the gs
  tiffsep overprint-semantics round-trip.

## Page inventory (rows top to bottom; each of P0-P3 carries the SAME bits)

| row | y (mm) | emission path | content |
|---|---|---|---|
| P0 | 28 | `put_cmyk_bitmap` composite image (control; known re-screened) | CM c3 50% field 15x15, CMY field 15x15, CM solid 8x8 |
| P1 | 52 | sequential per-plane `imagemask`, overprint OFF | same bits |
| P2 | 76 | + `true setoverprint` (OPM 0) | same bits |
| P3 | 100 | + guarded OPM 1 (`1 setoverprintmode`, gs bool fallback) | same bits |
| P4 | 124 | single-plane `imagemask` references | C/M/Y c3 50% fields 15x15; C/M/Y solids 8x8 |

Paint order inside P1-P3 is C, then M, then Y — without overprint the later
plane wins at overlap. Registration: calpage-identical chiral corner marks +
65-node plus lattice; quiet zone 25x25 at (38,150) is the white/noise
reference. No machine strips (quick probe; header text carries job/seed).

## What ghostscript predicts (measured, gs 10.07, tiffsep 600 dpi — semantics
only; gs does NOT model the RIP's screening)

- P0: all separations == GT exactly (clean in gs; screening happens on the
  real RIP only).
- P1: knockout — C sep == C&~M, M&~Y etc.; CM solid's C plate EMPTY.
- P2: identical to P1. Strict PLRM: DeviceCMYK zero components knock out at
  OPM 0. Adobe-derived RIPs may default OPM=1 — the sheet decides.
- P3: all separations == GT exactly (overprint + OPM 1 preserves).
- P4: exact.
- gs quirk log: `1 setoverprintmode` (Adobe integer form) is a /typecheck on
  gs 10.07 (wants boolean) — psgen emits int-then-bool, dual-guarded.
  Composite devices (png16m, tiff32nc) ignore overprint even with
  `-dOverprint=/simulate`: never judge P2/P3 from a composite preview.

## Physical run

1. Preflight green; record `composite_probe.ps` sha256 in the 002 RESULTS log.
2. Print ONE sheet via the user's chosen raw path (port 9100 canonical:
   `../../scripts/print_plane.sh build/composite_probe.ps`; `lpr -o raw`
   acceptable for this scratch sheet per 002.0 precedent). USER CONFIRMS
   FIRST.
3. Loupe check before scanning: P4 fields sharp cells (as 002.0); P1 CM solid
   should look magenta-only if knockout happened; P0 fields should show the
   rosette/screen texture seen in 002.0 composites.
4. Scan: flatbed 1200 dpi RGB (48-bit if offered), descreen / sharpen /
   auto-contrast OFF, full page including all four corner marks. Save to
   `scans/`, record sha256. (Grey scan optional; all discriminators below use
   the color scan's r/g/b channels.)
5. Log the run in `experiments/002-calibration-page.md` RESULTS as 002.1:
   date, engine, media, driver path, settings, scan sha256.

## Analysis (point cal_core at THIS manifest — do not touch cal_core)

```python
mf   = cal_core.load_manifest(cal_core.BUILD / "composite_probe_manifest.json")
scan = cal_core.load_scan("scans/<scan>.png"); cal_core.register(scan, mf)
```
Verified on a synthetic 1200 dpi render: 69/69 landmarks, residual RMS 0.003
dots; `reg["ruler_check"]` reports a caught KeyError (no rulers on this page)
— harmless by design, ignore it. Registration gates as 002.0: >=3 corners,
residual RMS < 3 dots, null controls 0.50±0.02 on every BER.

Three discriminators, each per variant, each with a P4 control:

1. **Screening spectrum** (canary-A analysis from cal_canary): 2-D FFT of
   each field/solid patch (r channel for C, g for M, b for Y); FAIL if
   plane-angle screen peaks (~165/212 lpi class) exceed the control bar set
   by the P4 patches and the quiet zone. P0 must FAIL (it is the positive
   control — if P0 measures clean, the analysis is broken, not the channel).
2. **Per-plane BER** (cell=3 hard decode vs intent GT, `decode_patch` or
   cell_means+median as in 002.0): compare each variant's C/M/Y field BER to
   the matching P4 reference BER on the same scan.
3. **Knockout signature**: split C-plane cell errors of `field_cm` by the M
   ground truth (and M-plane errors of `field_cmy` by Y GT). Knockout ⇒
   err(C | M=1) -> ~1.0 for C=1 cells (measured 0.50 over all cells at p=0.5)
   while err(C | M=0) stays at reference level; also the CM solid's C density
   collapses to ~0 in the overlap. Preserved ⇒ err(C|M=1) ≈ err(C|M=0),
   accepting the crosstalk penalty under M ink (finding 2 of 002.0: apply the
   measured unmix before concluding).

## Decision rule

Evaluate P1, P2, P3 in that order; ADOPT the first variant that is
- screen-free: no plane-angle screen peaks above the P4/quiet-zone control
  bar in any of its patches, AND
- knockout-free: err(plane | overlap)/err(plane | clear) compatible with 1
  (no site-selective error concentration), CM solid overlap carries BOTH
  inks, AND
- BER-equivalent: each plane's field BER within +0.02 absolute of its P4
  reference (null controls valid).

Then: amend DESIGN.md §2.4 (composite emission = adopted path), switch the
composite/state/overlay families of gen_calpage to it, and re-run the 002.0
composite measurements (the §11 simultaneous-CMY decision reopens with a
clean channel).

If NONE passes: fall back to (a) a Separation-colorspace emission probe
(`[/Separation /Cyan ...] setcolorspace` — preserves overlap in gs even at
OPM 0; needs its own sheet), or (b) keep put_cmyk_bitmap and model the
screened channel as measured (002.0 numbers stand: Y collapses at 24% BER —
this fallback likely kills simultaneous CMY). Either way the DESIGN.md §2.4
raw-path clause needs an amendment describing what the RIP actually does.

## Expected outcomes cheat-sheet

| observation on scan | conclusion |
|---|---|
| P1 clean spectrum, no knockout | RIP composites plane buffers independently — adopt P1 (simplest) |
| P1 knocked out, P2 clean+preserved | RIP honors setoverprint with OPM-1-like defaults — adopt P2 |
| P1,P2 knocked out, P3 clean+preserved | strict-PLRM RIP, OPM operator honored — adopt P3 |
| P3 knocked out too | OPM ignored by RIP — Separation-space probe next |
| P1-P3 screen like P0 | RIP re-screens ALL overlapping content — fallback (b) |
| P0 measures screen-free | analysis broken (positive control failed) — fix before concluding |
