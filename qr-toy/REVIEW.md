# Pre-commit review — 2026-09-09

Reviewed against main `134b31f6774c4ede5faf23aa70b092f4c7b98bf4`.
Changes are confined to `qr-toy/`; production format, receiver and planner
code are unchanged. Three independent review passes covered acquisition,
generation/comparison, and the FEC calculations/documentation.

## Corrections

- Reject triangular and singular clutter proposals without aborting the
  remaining acquisition candidates.
- Exclude unobserved known cells from calibration instead of treating their
  white fill as measured evidence; composite transparent palette images correctly.
- Make expected-file read failures and output-directory errors explicit;
  retain pose and aperture provenance for each LDPC attempt.
- Load the optional QR library on demand, preserve `--help` without it,
  provide installation guidance, and record its actual installed version.
- Validate FEC study inputs, preserve tiny RS probabilities in log form,
  bound confidence intervals, and record software/source provenance.
- Add types and readable formatting. Separate implemented behavior from
  proposed compact layouts, including the production metadata constraint.
- Preserve original photo and FEC measurement records under `records/`.
  Generated artifacts and original JPEGs remain local and ignored.

## Verification

Environment: CPython 3.14.7 free-threaded, invoked through `env/bin/python`.

- `python -m pytest qr-toy -n 0 -q`: **43 passed**.
- `python -m pyflakes qr-toy/*.py`: clean.
- All three original JPEGs replay to the expected payload SHA256, retaining
  hard-cell-error/LDPC-iteration pairs **0/0, 0/0, 53/1**.
- Regenerated counting `tile.ps` and `comparison.ps` are byte-identical to
  the original artifacts. Tests verify their raster geometry against PNG.
- Twenty-four deterministic FEC trials match the original calculation
  exactly. The original 19,000-trial record is retained unchanged; it was
  not rerun for formatting and numerical-reporting changes.
- Receiver suite: **1,843 passed, 338 skipped**. The initial sandboxed run
  could not open local HTTP test sockets; the rerun with socket access passed.

## Existing repository failures

The default repo suite completed with **1,434 passed, 85 skipped and three
failures** in `analyzer/tests/test_analyzer_walkeval.py`:

- `test_the_walk_knobs_off_reproduce_the_pre_change_path_exactly` for
  `auto_named_shrinkage` and `named`.
- `test_a_run_that_names_its_shrinkage_is_untouched_by_the_nesting`.

The same three hash mismatches reproduce in a clean `git archive` of the
main commit above, with no `qr-toy/` directory present. They are recorded
as pre-existing baseline failures. No analyzer code or expected hashes were
changed as part of this review.
