# crop_parity — ground truth and crop geometry (the harness's live remainder)

What stays here is what the analyzer and the other instruments still
import:

* `_gt.py` — per-tile expected USER BITS for a whole identity, re-encoded
  from the volume's sha-verified recovered payload through `src/holo`
  generation arithmetic (K, per-stream colour and pooled colour each
  following its own emitter), stopped at the user-bit boundary. Live
  through `analyzer/truth.py`, `measure/yask`, `measure/local_ab`.
  Measured green 2026-08-29 against every archived holo1 certificate:
  e029 1,940/1,940, xerox-c2-cmy7 1,559/1,559, xerox-c2-cmy8 5,370/5,370,
  zero mismatches.
* `_geometry.py` — pure crop geometry over plain data (no I/O).
* `cases/<volume>/cases.json` + `cases-census.md` — the case manifests
  the harness cut on 2026-08-29 (holo1 vs holo3 per-tile gaps on six
  volumes, recomputed from the conversion's parity record); read by
  `measure/angle_residue.py`.

2026-10-09: the harness side (`cases.py`, `harness.py`, `_selfcheck.py`,
`_h3run.py`, `_census.py`, `_report.py`, `_state.py`, `_paths.py`,
`_volumes.py`) and its full README (invocation, the volume table, the
2026-08-29 smoke proof on `e029-c01`) left the tree; the last tree with
them is `66528640` (`git show 66528640:measure/crop_parity/README.md`).
Its inputs — the scans, the archived holo1 states, the parity record —
are in the evidence archive.
