# Experiment 005 — density ladder (development-density as a channel knob)

**Question.** Every dominant b/w failure mode measured in 001–004 is
development-density physics: B1's day-2 white-cell closure (fa 15.4% at the
worst tile), B2's whole-2-run dropouts (18.5% of 2-runs), grey-level
instability. DENSITY has been sitting at the device default (3) for every
experiment to date. Does moving it shift the ~0.15–0.19 b/dot channel
constant, and in which direction per candidate?

## 005.0 — read-only PJL/PS recon (2026-07-05, zero paper, user-authorized)

`scripts/pjl_recon.py <host>` →
`build/pjl-recon-2026-07-05.txt` (PJL INFO ID/CONFIG/VARIABLES/STATUS + a
stopped-guarded no-showpage PS probe on the 9100 backchannel). Findings:

- **DENSITY=3, RANGE 1–5, PJL-settable** → the ladder is per-job
  programmatic: `@PJL SET DENSITY=n` envelope around the byte-identical
  sha-gated PS payload. `SET` only (never `DEFAULT`): nothing persists.
- **RET=ON (ENUMERATED OFF/ON)** — HP Resolution Enhancement has been
  silently ON under every measurement in 001–004. Edge-rendering modifier;
  plausibly entangled with the measured +0.3–0.7 dot edge gain and 1-dot
  feature behavior. NEW Layer-0 variable; needs its own one-variable probe.
- ECONOMODE=OFF (toggleable) — coarse extra density point if needed.
- PS level: `statusdict` has NO density operators (setprintdensity /
  printdensity absent); `currentpagedevice` keys are standard. PJL is the
  only density path.
- Hygiene facts: PRTPSERRS=OFF (no PS error pages possible), device PJL
  default DUPLEX=ON (our jobs explicitly set /Duplex false — verified in
  the e004 stream audit), RESOLUTION=600 [2 ENUMERATED].

## Planned ladder (NOT yet printed — each print needs explicit user go)

Reuse `experiments/004-finalists-checkerboard/build/e004.ps` verbatim
(sha c5c35d94…, byte-identical payload; the density-3 print + scan already
exist as run 004.0 — the ladder's midpoint is free):

| run | envelope | purpose |
|---|---|---|
| 005.1 | DENSITY=1 | starve development: does white closure vanish? do 2-run dropouts worsen or improve? |
| 005.2 | DENSITY=5 | saturate: closure worst-case; solids/edge gain response |
| 005.3 | DENSITY=3 RET=OFF | isolate RET's contribution to edge gain / small-feature survival |

Print via `scripts/print_density.sh build/e004.ps <n> [RET=OFF]`; scan per
the E004 protocol (1200 grey + color, enhancements off); log every envelope
+ scan sha here. Analysis: analyze_e004.py per sheet + the 004.0a run-length
and closure metrics as the primary densitometer; ref-row solids give
absolute density per print.

## Run log

| run | date | action | envelope | payload sha256 |
|---|---|---|---|---|
| 005.1 | 2026-07-05 ~21:00 | PRINTED one sheet (user-authorized batch): e004.ps verbatim via scripts/print_density.sh | @PJL SET DENSITY=1 | c5c35d94c0940b82a612dc48c7721130240709cce094a3438fce790d08f9ca68 |
| 005.2 | 2026-07-05 ~21:01 | PRINTED one sheet | @PJL SET DENSITY=5 | same |
| 005.3 | 2026-07-05 ~21:01 | PRINTED one sheet | @PJL SET DENSITY=3 + @PJL SET RET=OFF | same |

Output-tray order: D1, D5, D3-RETOFF — label sheets on emergence. Scan per
E004 protocol when convenient (1200 grey + color, enhancements OFF); the
004.0 print+scans serve as the D3/RET=ON midpoint.

## 005.1-005.3 RESULTS (2026-07-05, scans 005.1/2/3.png, 1200 dpi color)

Analyzer: 004-*/density_ladder_analysis.py -> build/density_ladder_report.json.
Baseline = the 004.0 print (D3/RET=ON, finalists-1-col). Subset instruments:
6 B1 tiles (edge-heavy), 4 B2 tiles, ref-row solids vs clean margin paper.

| sheet | K-solid D | blind cov | B1 ctx | B1 fa(w->i) | B2 BER | 2-run dropout |
|---|---|---|---|---|---|---|
| D3 RET=ON (004.0) | 1.149 | 0.4825 | 8.89% | 10.31% | 14.41% | 0.187 |
| D1 | 0.983 | 0.4817 | 9.31% | 11.14% | 14.18% | 0.182 |
| D5 | 0.829 | 0.4821 | 8.88% | 10.21% | 14.23% | 0.182 |
| D3 RET=OFF | 0.932 | 0.4829 | 8.86% | 10.22% | 14.35% | 0.184 |

Findings:

1. **@PJL SET DENSITY: NO measurable effect on the raw PS path.** Cell-level
   channel dead flat across settings (coverage 0.4817-0.4829, B1 ctx/fa, B2
   BER and 2-run dropout all within noise), and solid density shows no
   ordering by setting (D5 is the LIGHTEST — opposite sign, see 3). Either
   the M281 ignores PJL DENSITY for PS jobs or it never reaches the EP
   process this way. Untested residue: EWS-set density + one print.
2. **RET=OFF: no effect on any metric** — RET does not touch 600 dpi 1-bit
   imagemask rendering. Retires the "RET silently ON during all
   measurements" concern: the record is RET-insensitive.
3. **NEW channel fact: solid-K Dmax fluctuates print-to-print by up to
   ~0.32 D** (1.149/0.983/0.829/0.932 across four byte-identical jobs;
   paper ref scanner-stable at +/-2%) while the CELL-level channel stays
   flat — solid-regime and cell-regime development are decoupled; Dmax is
   NOT a densitometer for the cell channel (cf. CAL-1's K_floor_limited).
4. **All four same-evening prints decode identically (~8.9% ctx subset)**:
   the day-1 (4.6%) -> day-2 (8.2-8.9%) drift is SLOW engine/environment
   state, not any per-job setting, and within-batch stationarity is
   excellent. Loop consequence: per-batch canary + rate adaptation is
   viable; density settings are not a lever; multi-scan combining (004.0b)
   remains the working channel-side gain.
