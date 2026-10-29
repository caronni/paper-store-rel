# Experiment 007 — regenerating the jobs at main

The log `experiments/007-office-disc.md` is normative. This note covers how
the three jobs published in the paperholo-era evidence release under
`007-office-disc/` are remade from the current tree. Measured 2026-10-22,
record `docs/evidence-archive/REGENERATION-2026-10-22.md` §2 and §4.3.

- **m281-disc1** (`disc1.ps`, `disc1_manifest.json`): `gen_disc1.py`, run
  from the repository root; byte-identical at every tree from `019e2936`
  (2026-07-06) through main.
- **altalink-library** (`001_patterns.ps`, `pilot_viz.ps`): experiment 001's
  `generate_patterns.py` and `experiments/pilot-lattice-viz/pilot_viz.py`,
  likewise, from `58c79142` and `446c3b82` (2026-07-04) through main.
- **fullpage-bw-kcell-c2, fullpage-color-a3-7st-c3** (the two never-printed
  2026-07-07 capacity pages; see the log's addendum of 2026-10-11):
  `regen_fullpage.py G`, with `G/regen/src` pointing at this tree's `src`,
  reproduces both PostScript files (`b3eb7999…`, `94c773df…`) at every tree
  from `cb2a8ffb` (2026-07-07) through main. The docstring's instruction to
  check out the tag `evidence/fullpage-20260707@cb2a8ffb` is historical: the
  tag is not needed. The committed driver passes `write_gt=False`, which
  leaves the manifests' `gt` block empty; with `write_gt=True` the manifests
  (`0e662822…`, `1c290842…`) and the two published payload arrays
  (`emission/*_payload.npy`) are byte-identical as well.

Decoding the printed sheet is `analyze_disc1.py` on the published captures;
the fullpage pages were never printed and have nothing to decode.
