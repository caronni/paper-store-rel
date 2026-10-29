"""measure/cmy_calibration — R11's yield measurement: which calibration of the cmy evidence to build.

The question (CMY-DESIGN §2.7, §2.9, §7(c), §7(e); ruling row §12 R11): the durable cmy evidence is three
W-relative scores (sC, sM, sY) from an alphabet-masked QDA, calibrated per (capture, region) by monotone PAVA
maps and demapped into six consumer forms (hi, lo, hi|lo=0/1, lo|hi=0/1).  Which chain of maps — lo-first,
hi-first, six maps, or none (the bounded raw statistic) — gives the most certified tiles under typical receiver
use (whole pages with 1-2 captures, 1-3 tile fragments cold, a dead Y), and with which dead-Y map, conditional
floors / validation source and region gate.

Modules (each runnable through the stage driver, `python -m measure.cmy_calibration --stage ...`):
  config     paths, the ten band-captures, seeds, parameters
  extract    scan -> per-cell feature cache (imports measure.e041_scale_readout.read_window), parity gate
  chains     QDA scores, bound, demap, folds, stratified PAVA, floors, label-space collapse, erasure law
  fit        regions, p120 furniture emulation, one calibration context under five policies, region gates
  estimators information / log-loss / error / ECE / slope, window and cluster bootstraps, Wilson, McNemar
  ldpc_sim   resampled-LLR block trials on the receiver's own LDPC decoder, any-stage success, tile yield
  regimes    R-P page, R-C cold start, R-D dead Y, nulls, single pose
  twocap     R-2 two captures summed; the Gaussian synthetic S1 with exact Bayes LLRs
  controls   C1-C9
  decide     the pre-registered reading rules D1-D4 and the synthesis
  run        the stages and the JSON of record
  report     report.md + figures from the JSON (plots: PIL charts)
  smoke      the synthetic-page smoke (--quick < 60 s, exits non-zero on a failed assertion)
  scorelane  the M1 gate: holo3's production cmy score lane on e044 sheet B at truth-fitted poses, the per-cell
             score divisor at 20 vs lifted (its own driver, `python -m measure.cmy_calibration.scorelane`)
  cond_gate  G13's (R*, alpha*) table: the scaled confusion channel on which BICM fails and the conditioned decode
             certifies (its own driver, `python -m measure.cmy_calibration.cond_gate`; RESULTS-2026-10-12-cond.md)
Artefacts: --art, default build/cmy-calibration/ (the run of record's: scratch/cmy-calibration-20261010/, not
committed).  Inputs by flag only (the 2026-10-09 ruling): the scans and manifests under --evidence-root (or
$PAPER_EVIDENCE_ROOT) at their published paths, the e041 scale readouts under --scale-root; scorelane and cond_gate
name their e044 / e043c inputs by flag (config's and each driver's docstring).
"""
