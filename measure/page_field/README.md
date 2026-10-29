# measure/page_field — the PAGE-FIELD line's validation harness

Five tools in six modules. `extract.py` reads a PRE-W2 fact snapshot (W0;
written as a throwaway and KEPT at W6 — sheet I's snapshot is pre-W2 and this
is its only reader); `estimate.py` solves one page field per (page, plane) by
driving the receiver's OWN collector and solver over an archived run;
`convert.py` (2026-09-12) puts post-W2 `PlaneField` and `EvidenceRevision`
facts BACK into an archived snapshot that Germano's `util/strip_page_fields.py`
has stripped, so the analyzer can read a pre-W2 corpus at all;
`compare.py` scores that field against the fits that came before it;
`lane_gauge.py` scores the archived per-lane fields against each other, where
no gauge question arises. The sixth module is not a tool: `products.py` holds
what the harness REPORTS — the three records `fields.json` is assembled from
(`Declaration`, `Counts`, `PageField`; the fourth, `Archive`, stays with the
identity gate that reads it), the two tables, and the writers of the two
figures. `estimate.py` imports it, never the reverse, and `compare.py` and
`lane_gauge.py` take `column_profile` from it, so the profile they score is
the one the cross-section draws. Run everything from the
worktree root with `PYTHONPATH=src:.`; `$MAIN` below is the main checkout
as it stood then, and every `scratch/` input the records name is in the
evidence archive. The three `self-check`s write into a fresh temp dir unless
given `--work DIR`.

## extract.py — the archived-snapshot reader (W0)

W2 re-keys `PlaneField`, and `holo.receiver.snapshot.read` then raises on every
snapshot written before it. `extract.py` decodes the container itself, with its own
class table and no `holo` import. The plan retired it at W6 and the ruling of
2026-09-08 KEEPS it: sheet I's snapshot (e037, written on machine 4 before W2) is the
corpus B3's supervised row still owes and this is the only tool that can read it.
Nothing under `src/` references it (2026-09-08).

    env/bin/python -m measure.page_field.extract self-check
    env/bin/python -m measure.page_field.extract extract FACTS.npz --out DIR \
        [--events RUN_DIR/events.jsonl]
    PYTHONPATH=src:. env/bin/python -m measure.page_field.extract cross-check \
        FACTS.npz      # digest-for-digest against snapshot.read; PRE-W2 ONLY

Ragged fields are CSR: `offsets[i]:offsets[i+1]` slices the concatenation.
- `placements.npz`: capture_id, level_index, region_index, extent_cells (n,4),
  patch_ordinal, page, rot_k, page_origin_yx (n,2), native_affine (n,6 — the
  tuple `lib.geometry.compose_from_native` takes), pitch_px, cell_offsets (n+1),
  local_cells_yx (m,2 int32) = what `region_window`/`window_sites` read, no more.
- `certificates.npz`: page, ty, tx, stream_id, bit_offsets (n+1), user_bits.
- `plane_fields.npz`: the pre-W2 per-lane fields — capture_id, level_index, page,
  plane, n_certificates, n_sites, residual, median_delta_dots, delta_dots_xy
  (n,ty,tx,2), support (n,ty,tx) = PAGE-FIELD-PLAN §5's "before" column, which
  nothing reads once W2 lands.
- `captures.json`: pitch_class, pitch_px, level indices, the survey's regions,
  and `identity` — the row id the run opened with, and where that was attested.
  `levels_ppc` and the capture shape are on `data.Capture`, in no snapshot.

**The identity, and why it is not the operator's to declare.** A snapshot does
not say which format it was decoded under: `RunOpen` is an event and
`snapshot.FAMILIES` holds no events, so `read_facts` finds one only if some
future snapshot carries it (measured 2026-09-08: none of the five archives here
does). Every run does write it, as line 1 of its own `events.jsonl`, and that is
where this reads it — the sibling of `FACTS.npz` by default, or the file
`--events` names for a snapshot copied away from its run dir. With neither
source `identity` is `null`, which `estimate.py` refuses — see the gate below.
What is recorded is the resolved ROW ID, never a format reference: the
2026-09-02 re-key made one reference mean two seeds.

**How much each source proves** (stated exactly, 2026-09-08): a snapshot's own
`RunOpen`, and the SIBLING journal, are structural — a run dir's `facts.npz`
and `events.jsonl` are written together at RunDone, so the sibling is that
snapshot's run by construction. `--events` is an ASSERTION the operator makes,
and the tool cannot verify it. What it checks it checks: a run re-declares
every capture it resumes, so the snapshot's surveys must be a subset of the
journal's `CaptureOpen`s, which refuses a journal from another scan set, and a
snapshot that surveyed nothing is refused rather than attested on a vacuous
comparison. But a capture id is the scan's sha256, so two runs over the same
scans declare the same captures whatever `--format` they declared — the one
case this gate exists for. Check a copied journal by hand, as sheet I's was:
compare its run dir's `facts.npz` sha256 with the snapshot's. `RunOpen` in
`snapshot.FAMILIES` would close it in code and is a production change.

`Window` facts are read (the level indices come from them) and not written: no
consumer in the design or the plan asks for one. A run that certified nothing
extracts to an empty placements/certificates/plane-fields set, not a crash.

## estimate.py — the field, from archived facts (W0's estimator half)

    PYTHONPATH=src:. env/bin/python -m measure.page_field.estimate self-check
    PYTHONPATH=src:. env/bin/python -m measure.page_field.estimate \
        run RUN_DIR --out OUT_DIR
    PYTHONPATH=src:. env/bin/python -m measure.page_field.estimate \
        archive EXTRACT_DIR --out OUT_DIR --format REF \
        --scan A.tiff --dpi 2400 --scan B.tiff --dpi 4800

No estimator lives here: `fields_collect.prepare_collect` measures and
`fields.prepare_fields` solves, off a real `holo.receiver.store` the tool
populates from the run's placements and certificates. What the tool owns is the
order — every capture collected, then ONE solve per page — and the raster
lifetime; what it REPORTS — the records that become `fields.json`, the tables
and the figures — is `products.py` beside it.

- **THE IDENTITY GATE**, first, before a raster is opened: the declared
  `--format` must resolve to the seed the archived run was decoded under, or
  the tool refuses and names both seeds. The archived seed is derived from the
  row id `RunOpen` recorded, by the frozen rule that the canonical v2 id IS the
  seed payload (FORMAT-SPACE §16) — not by resolving that string again, which
  is the trap: `c2-cmy8-r0547@53x37` was sheet J's canonical row id when it was
  printed and decoded, and since 2026-09-02 it is the DISPLAY name of a
  different row with a different seed. The run route reads the identity from
  the run dir's `events.jsonl`, the archive route from `captures.json`; an
  archive that attests none is refused, and so is a `captures.json` written
  before the gate (re-extract it). What the gate protects is invisible without
  it: the tile codec's keystream and slot permutation follow the seed, so a
  replay under the wrong one correlates every certified template against the
  wrong known bits and measures its own null, while the furniture tiers — seeded
  separately, `sites_seed` — go on working and the products look ordinary.
- **`run`** takes a post-W3 run directory: `facts.npz` through
  `snapshot.read`, and the captures from the run dir's own `argv`, parsed by
  the receiver's own parser.
- **`archive`** takes an `extract.py` output directory and the captures on the
  command line. It is the route for sheets H, I and J, and not only because an
  extract carries no argv: an ARCHIVED argv names flags this tree no longer has
  (`--plane-fields` retired at W2, `--pages` renamed `--max-pages`), so the
  parser refuses it. Read the old argv, spell the scans and DPIs by hand.
- Only `Placement` and `Certificate` are folded. With the declared captures
  that is everything a collection reads — surveys, windows and the archived
  per-lane fields are deliberately left out, and the last of those because this
  run re-derives the field.
- One capture at a time: ingest, collect every page it is placed on, delete its
  plane rasters. A 4800-dpi sheet-H capture is a 6.9 GB tiff.
- Every declared scan is hashed BEFORE the first ingest (`intake.sha256_file`,
  production's own capture identity; sheet H's seven are 24.5 GB and 45 s of
  it). That pass buys the two guards `ingest_captures` keeps over the paths of
  one call and cannot keep across a per-capture loop: a scan set that does not
  carry the facts' captures is refused for the price of a hash, a scan declared
  twice is ingested and collected ONCE, and one source declared at two DPIs is
  refused (intake's Q2 refusal) rather than installing a second level ladder
  under the first one's lane keys.

Products under `--out` (`products.py`): `fields.json` (per (page, plane): the
tile grid, the per-tile UNCERTAINTY beside it — which is how much of the
prior's ignorance the evidence has not removed, on the prior's scale and not
a posterior deviation (design §2.4) — the support, the observation and capture
counts, the median |delta| and median uncertainty, whether the plane is KNOWN
at all — a plane no template could be built for reads unknown and not zero
(I13) — and this plane's residual energy per capture, never summed with the
other planes' (W8 R-F: two healthy word planes hid a Y ratio of 8 behind a
reported 0.040); per page: the FIELD REVISION it was solved at, each capture's
EVIDENCE REVISION, and a per-SOURCE census of the observations, which is the
number design §7.1 owes on the blind tier's retirement); one
`field-page<N>-<plane>.png` per plane at TILE resolution in the diag band's own
vocabulary, its footer carrying that plane's median uncertainty; one
`cross-section-page<N>.png` with the three planes' x profiles
along the column axis. That profile is the column effects of an additive
row-plus-column fit over the tiles with evidence — the plain column mean where a
column's support is complete, and not a peak invented out of the rows a column
is missing (measured: on the W5 sim the plain mean reads 0.72 dots where the
field reads 0.18). The cross-section footer names each plane's thinnest column.
The counts B6 asks about are printed and land in `fields.json`: pages solved,
(capture, page) collections, and lane-page fits, which is 0 by construction and
counted rather than asserted. `pages_solved` stays what B6 already says it is —
this tool solves each page once, unconditionally, so it is the harness's own
order and not what production would schedule. What production schedules ON is
the REVISION, and that is reported per page beside the field: `field_revision`
is what the standing field was solved at and `evidence_revision_by_capture` is
what each capture's collection stands at, so "how often the evidence changed"
is read off the products rather than inferred from a count of solves.

**What a replay of a FINISHED run measures** (recorded 2026-09-08, W7, from
the audit): `fields_collect.measure_window` sends a certified tile to
`measure_certified` and to nothing else, and a window's furniture set is the
tiles that are NOT certified (`fields_collect.py:588`), so a page read to
100 % yields certified-tier rows only — no anchor row, no blind sweep. Sheets
H (5,883/5,883) and I (5,880–5,883/5,883) replay that way, so every number
they produce is a statement about the certified tier at terminal facts, not
about the mixed-tier regime production runs in while the field still matters.
Sheet J at 67 % is the corpus that exercises the mix. The size of the flip is
measured on the W5 sim: holding the certificates out replaces 92 certified
rows with 91 anchor + 88 blind and moves the field by C 0.0389 / M 0.0264 /
Y 0.0804 dots.

`self-check` runs the whole path over a synthetic store — one 3x3-tile page, one
window, the Y plane printed one dot along page +x — and asserts the planted
vector comes back, that C and M do not move with it, and that the fields are
keyed (page, plane). 1.4 s, no corpus, no decode; it is what a reviewer runs.

## convert.py — the field put BACK into an archived snapshot (2026-09-12)

    PYTHONPATH=src:. env/bin/python -m measure.page_field.convert self-check
    PYTHONPATH=src:. env/bin/python -m measure.page_field.convert append \
        --facts RUN.page-field/facts.stripped.npz \
        --out RUN.page-field/facts.npz --format REF \
        --fields-json .../estimate/fields.json
    PYTHONPATH=src:. env/bin/python -m measure.page_field.convert append \
        --facts RUN.page-field/facts.stripped.npz \
        --out RUN.page-field/facts.npz --format REF --max-pages 2 \
        --scan A.tiff --dpi 2400

The archived-corpus door, second half. W2 re-keyed `PlaneField`, so
`snapshot.read` refuses a pre-W2 archive outright; `util/strip_page_fields.py`
(main, `efc839e5`, Germano's — tag-based, importing neither receiver version,
the array blob streamed through) removes the old facts, and this module puts
post-W2 ones back. STRIP FIRST, always: the input is read through
`snapshot.read` and a spine still carrying a pre-W2 node dies there.

Why the field goes back in rather than staying stripped: a stripped corpus
drops `EvidenceRevision` with it, and the sheet-J export that did so cost the
resumed receiver its revisions (9,118 → 8,977 and 8,602 → 8,276) and made it
re-solve from nothing. A converted corpus is a faithful resume base; a
stripped one is not.

- **Two sources, one append.** `--fields-json` reads a product ALREADY solved
  from this exact input — "this exact input" is a census gate over the
  snapshot's own spine — and costs a file read; `--scan/--dpi` re-solves with
  `estimate.py`'s own pieces beside this file, one capture in memory at a
  time. The identity gate runs first either way.
- **Nothing but the field moves.** The appended families are `data.PlaneField`
  and `data.EvidenceRevision` and no others; the output is read back and every
  NON-field fact's `export_facts.fact_digest` must be identical. That
  assertion is the whole claim this module makes (`export_facts.verify` itself
  is not reusable — it refuses non-certificate tails; only `fact_digests` is).
- **The original run dir is never touched.** The convention the analyzer's
  corpora follow is a SIBLING run dir `RUN.page-field/`: a symlink farm over
  every file of the original but the snapshot, plus the stripped intermediate,
  the converted `facts.npz`, and a `facts.npz.convert.json` manifest recording
  source, format ref, folded census, field revision, per-(page, plane)
  observations and the non-field digest.
- Converted 2026-09-12: `<evidence>/J-run.54028.page-field` (solve, both faces,
  6 + 2 facts), `<evidence>/J-run.52093.page-field` (solve, page 0, 3 + 1) and
  `<evidence>/analyzer/H7-mirror.page-field` (READ from
  `page-field-20260908/H-w8/estimate/fields.json`, the W8 solve of this exact
  input, 3 + 7). `analyzer/README.md` §2.1a is the recipe log.

## compare.py — against the fits that came before

    PYTHONPATH=src:. env/bin/python -m measure.page_field.compare \
        --fields OUT_DIR/fields.json \
        --analyzer <evidence>/analyzer/sweeps/field2/phase-C.json \
        --supervised <evidence>/xerox-v1-20260818/regmap-gt/plane-offsets.json \
        --lane-fields <evidence>/page-field/H7-mirror/plane_fields.npz \
        --out OUT_DIR/compare.json

Each source is optional and each prints its own table; all three in one run is
how PAGE-FIELD-PLAN §5's before-and-after columns fill from one command.

- `--analyzer` takes either of the analyzer's two products, in ONE schema.
  The standalone one is `sweeps/field2_paper.py --phase C`'s `phase-C.json`,
  GENERALISED on 2026-09-12: it lost its page-0 and `("Y", "C")` hardcodes and
  now carries one row per (page, plane) for every stream the run names and
  every live page — three rows for sheet H, six for the converted duplex sheet
  J — each row keyed by `page` and `plane`, naming `fit_refused` when the fit
  cannot stand on that (page, plane) (no lane on the page, no furniture
  anchors, an unknown stream), which this tool SKIPS rather than scores;
  reporting `clamped_tiles` over the whole grid and `clamped_supported_tiles`
  over the tiles an arm can read; and carrying the A4 by-footing block
  (`vs_lane_own_fields`, `lanes_by_footing`, `lane_pairs_by_footing`,
  `lane_pair_summary` — `lane_gauge.py`'s three statistics over each lane's
  OWN furniture field, bucketed by dpi). The key `vs_per_lane_fields` of the
  2026-09-03 product meant the retired certificate-anchored per-lane table and
  is not reused. The other product is the IN-RUN `field2.json` a ladder pass
  writes beside its ledger — the same row schema (both sides call
  `field2.summary`, so a fit is spelled identically either way) plus
  `production_field_known` and `production_field_ordinal`, the revision of
  the `PlaneField` that STOOD for that (page, plane) in the pass's inputs
  (only the `field` arms consume it), and — since the 2026-09-13 review's
  F12 — `fit_seed` and `fit_knobs`, the memo key's own provenance of each
  fit: a row is published only when that key matches the pass's seed and
  knobs, and a product whose rows stand with no `field2` arm in the
  battery says so in a `note`. The standalone phase-C product carries
  `run_dir`, `format_ref` and `mm_per_tile` in its header (F10/F11). So
  `--fields <production> --analyzer <field2.json>` is the consistency check
  of what one pass read, against the revision it read, while the phase-C
  product is the standalone measurement. Its rows are the (page, plane)
  pairs the run's `field2` arms actually fitted, read back from the memo and
  never refitted for the product — a refit would be a second measurement.
  This tool is the ONLY comparator of the two fields:
  the analyzer imports nothing from `measure/` and scores nothing against a
  published `PlaneField` itself.

  Per (page, plane) it prints the two grids tile by tile — median
  |Δx| and |Δy| (B3's bar is ≤ 0.12 dots on x), the Spearman of the two column
  profiles, and a least-squares sinusoid on each. TWO statistics against
  design §7's 0.83-dot e033 peak, each named (W7, 2026-09-08 — the older
  `peak_over_e033_dots` printed a FITTED amplitude under the word "peak", and
  e033's number is a profile MAX): `profile_max_dots` and
  `profile_max_over_e033_peak` are the like-for-like pair, and
  `fitted_amplitude_over_e033_peak` is the other statistic beside it. On sheet
  H they differ by 1.604× (0.6006 dots against the analyzer's fitted 0.37433),
  which is why the ratio has to say which one it is. The y column carries no
  bar, and since 2026-09-12 the DIRECTION of that comparison is stated: no
  sheet carries supervised y (`--supervised` scores x only), the receiver
  measures both axes everywhere and is the reference, and the analyzer's y is
  the thing under test through `median_abs_dy_dots`.
- `--supervised` (sheet I): `plane-offsets.json`'s per-patch `dY_rel_x` in scan
  pixels, aggregated per tile column and divided by `px_per_dot` — exactly the
  aggregation that directory's own `report.py` publishes as `per-column.json`.
  Spearman, period ratio, FITTED `amplitude_ratio` and, beside it, the profile
  MAX on both sides (`profile_max_dots`, `supervised_profile_max_dots`,
  `profile_max_ratio` — added at W7 for the same reason as the analyzer row's).
  The SIGN is reported, not
  asserted, on this route and on the analyzer's: no sheet-I holo3 snapshot
  exists on this machine to settle which way round the supervised measurement
  and the sampler's delta point, and the analyzer's own field carries no stated
  direction either.
- `--lane-fields`: the archived per-lane fields against the page field, and
  against each other — the lane-to-lane spread pooling is supposed to absorb.
  Scored on the plane DIFFERENTIALS (Y−C, Y−M, M−C), one row per (page, pair),
  because the two sides are gauged differently: the page field drops the
  weighted common mode of the word-ink planes (design §2.3) while the pre-W2
  fitter's median-of-three only ran where all three planes fitted at once, so
  an archived single-plane lane carries the plane-common bias whole. A
  difference of two planes of ONE fit is the same quantity under either
  convention. A lane enters a pair only if it published BOTH planes, and the
  table prints each page's lane inventory per plane so a `0 lanes` row explains
  itself. `C−M` is `M−C` negated and every statistic here is invariant under
  that sign, so it is not a fourth row.

## lane_gauge.py — the archived lanes against each other (W6)

    PYTHONPATH=src:. env/bin/python -m measure.page_field.lane_gauge \
        --fields build/page-field/H/fields.json \
        --lane-fields <evidence>/page-field/H7-mirror/plane_fields.npz \
        --dpi af580c3cf54f=1200 --dpi d792e00a45e7=1200 \
        --dpi 68c16fcbf29b=2400 --dpi 4fddac74cef1=2400 \
        --dpi f6920518c82a=4800 --dpi 9c022bd308ae=4800 \
        --dpi f642cab0416c=4800

Three tables, printed together so the correction reads beside what it corrects:
the RETRACTED per-plane lane-vs-page numbers, the gauge-free differentials
`compare.py --lane-fields` scores, and lane against lane on one plane, which
touches no page field at all. The third is what design §7's "sign-inconsistent
between footings" now rests on. The npz carries no dpi, so the footings are
DECLARED per capture and an undeclared capture is refused, never binned.
Sheet H's output is kept at `<evidence>/page-field/H/lane-gauge.txt`.

Both sinusoids are least squares on a period grid from 4 tiles to the profile's
WHOLE length, after a linear trend is projected out — the recipe of
`analyzer/sweeps/field2_paper.sinusoid_fit`, and the reason this reproduces the
analyzer's reported amplitudes (Y 0.368 against 0.374 at 16.2 against 16.0
tiles, C 0.237 against 0.243 at 18.6 against 18.5). A grid stopping at half the
profile would sit exactly on the AltaLink's ~18.5-tile period and report every
longer one as 18.5.

## The lead's replays (not run here)

Sheet **J**, one capture, 1.7 GB — the confetti page, both faces, every lane-page
mixing all four rotations:

    PYTHONPATH=src:. env/bin/python -m measure.page_field.estimate archive \
        <evidence>/page-field/J-run.54028 --out build/page-field/J \
        --format L:c2-cmy8-r0547@53x37 --max-pages 2 \
        --scan <evidence>/xerox-canon-1.9-J-c2-cmy8-r0547-confetti-2400-1a.tiff \
        --dpi 2400
    PYTHONPATH=src:. env/bin/python -m measure.page_field.compare \
        --fields build/page-field/J/fields.json \
        --lane-fields <evidence>/page-field/J-run.54028/plane_fields.npz \
        --out build/page-field/J/compare.json

**Sheet J is the FOSSIL `L:c2-cmy8-r0547@53x37`, and only that.** It was printed
and decoded on 2026-09-01/03 under the row id `c2-cmy8-r0547@53x37`, whose seed
is `holo/v2/c2-cmy8-r0547@53x37`; the canonical-identity re-key of 2026-09-02
gave that spelling to `1i300-cmy8-r0547-p120-v1@53x37`, a different seed, and
kept the printed one as the fossil. Declaring the short name today reads the
sheet with the wrong keystream and slot permutation — the certified tier then
correlates against wrong known bits and returns its own null, and nothing in
the products says so. Every sheet-J replay recorded on 2026-09-08 before the
gate declared the short name; their certified-tier numbers are void. Sheets H
and I were always declared as `L:` fossils and are unaffected.

Sheet **H**, seven captures, 2 × 0.43 GB at 1200 + 2 × 1.7 GB at 2400 + 3 × 6.9 GB
at 4800 — one at a time, in the run's own order:

    H=xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm
    PYTHONPATH=src:. env/bin/python -m measure.page_field.estimate archive \
        <evidence>/page-field/H7-mirror --out build/page-field/H \
        --format L:c2-cmy8-r0850-p120-x1@3392x2368 --max-pages 1 \
        --scan <evidence>/$H-1200dpi-a.tiff --dpi 1200 \
        --scan <evidence>/$H-1200dpi-b.tiff --dpi 1200 \
        --scan <evidence>/$H-2400dpi-a.tiff --dpi 2400 \
        --scan <evidence>/$H-2400dpi-b.tiff --dpi 2400 \
        --scan <evidence>/$H-4800dpi-a.tiff --dpi 4800 \
        --scan <evidence>/$H-4800dpi-b.tiff --dpi 4800 \
        --scan <evidence>/$H-4800dpi-c.tiff --dpi 4800
    PYTHONPATH=src:. env/bin/python -m measure.page_field.compare \
        --fields build/page-field/H/fields.json \
        --analyzer <evidence>/analyzer/sweeps/field2/phase-C.json \
        --lane-fields <evidence>/page-field/H7-mirror/plane_fields.npz \
        --out build/page-field/H/compare.json

Those seven files ARE the seven captures of `H7-mirror`, matched by sha256 on
2026-09-08 (the harness hashes them again before it ingests, so a wrong file is
refused rather than decoded):

| capture | scan | dpi | levels |
|---|---|---|---|
| `af580c3cf54f` | `$H-1200dpi-a.tiff` | 1200 | 0–1 |
| `d792e00a45e7` | `$H-1200dpi-b.tiff` | 1200 | 0–1 |
| `68c16fcbf29b` | `$H-2400dpi-a.tiff` | 2400 | 0–2 |
| `4fddac74cef1` | `$H-2400dpi-b.tiff` | 2400 | 0–2 |
| `f6920518c82a` | `$H-4800dpi-a.tiff` | 4800 | 0–3 |
| `9c022bd308ae` | `$H-4800dpi-b.tiff` | 4800 | 0–3 |
| `f642cab0416c` | `$H-4800dpi-c.tiff` | 4800 | 0–3 |

None of the crosswise (`quer`) captures is in this mirror: all seven regions are
portrait. The original `argv` is in `<evidence>/analyzer/H7-mirror/`, and
carries the retired `--plane-fields` flag this tree's parser refuses.

Measured cost of the FACT side alone, 2026-09-08 on this machine: sheet J reads
and folds in 0.8 s; sheet H reads its 1.87 GB of `local_cells_yx` in 6.6 s and
folds 7,725 placements and 4,883 certificates in 10.7 s, at 7.9 GB peak RSS —
before a single raster is opened. The collection itself is the receiver's own
cost, per capture, and is what the lead should budget for.

THAT COLLECTION COST MOVED AT W7. Sheet J's load 1a — one capture, two faces,
825 placements and 657 certificates, the standard probe for this line — reads
**65.2 s of collect CPU on the pre-W7 tree and 97.7 s at W7, +50 %** (83 s and
115 s of wall; the lead's two replays, 2026-09-08, both under the fossil),
because the certified tier's search radius went from the anchor tier's per-plane
1.5/1.5/2.5 dots to its own 2.5 on every plane at c2, and its candidate grid
from 169/169/441 to 441 (`plugins/field_tiers.CERTIFIED_RADIUS_CELLS`, design
§2.5). Budget two minutes of wall for that replay, not one. The W7 figures this
paragraph used to carry — 75.9 s before, 130.1 s after, +71 % — were the
DISPLAY-NAME replays over the ten-capture extract and are void; those runs
certified nothing, so what they timed was a null correlating at full cost.

Sheet **I** WAS owed and is not any more: Germano mounted machine 4 and machine 2 the
same evening and both snapshots (e037's one capture, e034's four) were extracted
and replayed. `--supervised` scores them.

## Where the products are

Every replay of 2026-09-08 lands under
`<evidence>/page-field-20260908/`: `H/`, **`J/` (VOID)**, `I-single-e037/`,
`I-four-e034/`, **`J-ten-e035/` (VOID)**, plus the extracted snapshots
under `snapshots/`. The W8 requalification of 2026-09-09 (the re-derived
solve, `PAGE-FIELD-PLAN.md` §5.1) lands beside them as `H-w8/`,
`I-single-e037-w8/`, `I-four-e034-w8/` and `J-ten-e035-fossil-w8/` (the
fossil identity, the only valid sheet-J replays), and the W9 replays of
2026-09-12 (the repaired tree, plan §2's W9 block) as `I-single-e037-w9/`
and `J-ten-e035-fossil-w9/`. `products.py:179-180` writes `passes` and
`converged` per page, and the claim is dated to the commit that added them,
`93d7cfad` (W9, 2026-09-12) — **the two W9 products on disk predate it**, so
read those two keys off a product written after that sha and not off the
directories above. Each carries `fields.json`, `compare.json`, `estimate.log`,
the per-plane field PNGs and the cross-sections. **The two sheet-J directories,
and `<evidence>/page-field/J` in this worktree, are VOID and not to be cited**:
they were made before the gate, under the display name, so their certified
tier read another row's bits (the recipe above says why). Void, not stale —
re-running them under the fossil is a decode-cost decision. Two housekeeping notes from
W7 (2026-09-08): `H/compare.pre-W6.json` and `J/compare.pre-W6.json` are the
superseded files that still asserted the retracted cross-gauge per-plane lane
numbers, kept beside the regenerated ones; `*/compare.pre-W7.json` are the
three that were already W6-shaped, kept across the statistic-naming edit above.
Every archive's `captures.json` was rewritten on 2026-09-08 to carry the
identity gate's record, with the file it replaced kept beside it as
`captures.pre-gate.json`; the three `.npz` files came back byte-identical
(sha256) from the re-extract, so only `captures.json` moved. Sheet I's
single-capture snapshot arrived from machine 4 without its run dir, so that run's
own 735 KB `events.jsonl` was copied into `I-single-e037/extract/` and is what
attests it (the snapshot itself is sha-identical to machine 4's `facts.npz`).

## Hand-backs to the receiver (its line, not this one)

What the analyzer's page-field phase frees on the receiver side, listed here
because this harness is where the two trees meet. Verbatim from
`analyzer/PAGE-FIELD-PLAN.md` A8, with what is measured beside each:

- **`anchor.shifted_points`** (`plugins/color_region_anchor.py:30-40`). It
  survived for ONE reader outside the receiver, `analyzer/sample.py:467`, and
  that reader is gone: `sample.read_rgb` calls `page_map.raster_points`
  directly, bit-identically over 5,000 random cases in review.
  `test_h3_page_map.py:359` already asserts no module in the receiver calls
  it. **NOT free, though**: four callers remain OUTSIDE the receiver —
  `analyzer/tests/test_analyzer_arms.py:43-44` and
  `test_analyzer_field2.py:220-225`, where it is the algebraic ORACLE the
  page-frame pins are written against, and
  `measure/c-third-layer-20260906/dump_patches{,2}.py:30`. Deleting it breaks
  the analyzer lane until those four are re-pointed at `page_map`.
- **`fields.MIN_DELTA_DOTS`** (`plugins/fields.py:85`). I8 abolished the
  floor on the production side and `field2` stopped reporting against it on
  2026-09-12. Measured: nothing in `src/holo/receiver` or `analyzer/` READS
  it; `measure/scanfield` quotes the name in provenance strings and carries
  its own `FLOOR_DOTS = 0.25`.
- **`lib/plane_field.py`'s seven kernel names** — `BANDWIDTH_TILES`,
  `KERNEL_TRUNCATION`, `TWICING_PASSES`, `MAX_DELTA_DOTS`, `gaussian_kernel`,
  `smooth`, `clamp` (`:227-238`, `:882-905`) — now unblocked, because
  `analyzer/field2_kernel.py` is the SOLE carrier: the constants and the three
  functions were adopted verbatim there on 2026-09-12 (the estimator did not
  move — every grid, surface and rms came back `np.array_equal`), and
  `arms.smooth_offsets`, the other analyzer reader, was deleted with the
  `smooth` arm the same day. Measured: inside `src/holo/receiver` those five
  names appear only at their definition site, and `smooth`/`clamp` have no
  caller outside `lib/plane_field.py` either. `tile_codes`, `evaluate` and
  `median_magnitude_dots` are LIVE receiver library and stay — the analyzer
  imports them from there, which is the point of the one mapping. The comment
  at `:227-231` then describes nothing. DELETED 2026-09-20 (branch `test-diet`), the no-caller pin with it.

Regenerating a `compare.json` costs about a second and touches no raster:

    PYTHONPATH=src:. env/bin/python -m measure.page_field.compare \
        --fields <evidence>/page-field-20260908/H/fields.json \
        --analyzer <evidence>/analyzer/sweeps/field2/phase-C.json \
        --lane-fields <evidence>/page-field/H7-mirror/plane_fields.npz \
        --out build/page-field-20260908/H/compare.json
