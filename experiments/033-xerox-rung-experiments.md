# e033 — AltaLink rung-experiment set: first r0700 colour close + the Y-registration sinusoid

Date: 2026-08-18. Engine: Xerox AltaLink C8245 (office). Scanner of
record: Canon flatbed (2400/4800 RGB). Code: branch `c4-row` (worktree
`<checkout>`), commits `bcd352c` (c4 row + 4mm AltaLink
row + CMY8 rate rungs + family dispatch), `6b18508` (resume spec
threading), `202aac6`+`103cc7c`+`ad4a561` (`--no-close`). Main carries
only the parked patch (`f1bc0d0`); NOTHING from this branch is ratified
or merged. Format amendments in HOLO-DESIGN §4.1 (c4) and the CMY8
rate-rung amendment, plus RECEIVE-DESIGN v0.56 — all PROPOSED.

STATUS: one sheet decoded (I) — VERIFIED byte-exact. Nine sheets await
scanning. Single-sheet evidence, provisional receiver: NO ladder or
margin promotion from anything below.

## 033.0 Candidate set (generated 2026-08-18, printed same day)

`scratch/xerox-v1-20260818/`, one page per volume, counting payload
filling the page exactly (regenerate: `generate_set.py`, needs the
branch). Print details (path/media/settings): OPERATOR TO FILL.

| tag | coding | margin | tiles | q | payload B | K/N | net b/mm² | ink |
|-----|--------|--------|-------|---|-----------|-----|-----------|-----|
| A  | c4-r0550 (NEW, proposed)   | 6mm | 468  | 0.3 | 32,622    | 0.265 | 4.2   | K |
| A2 | c3-r0550                   | 6mm | 840  | 0.3 | 62,120    | 0.281 | 8.0   | K |
| B  | c2-r0700                   | 4mm | 1961 | 0.7 | 465,580   | 0.691 | 59.7  | K |
| C  | c2-r0700                   | 4mm | 1961 | 0.9 | 600,183   | 0.891 | 77.0  | K |
| D  | c2-cmy8-p120-v1            | 4mm | 1961 | 0.5 | 763,023   | 0.497 | 97.9  | CMY |
| E  | c2-cmy8-p120-v1            | 4mm | 1961 | 0.9 | 1,376,601 | 0.897 | 176.6 | CMY |
| F  | c3-cmy8-p120-v1            | 4mm | 840  | 0.9 | 586,932   | 0.893 | 75.3  | CMY |
| G  | c3-r0550                   | 4mm | 840  | 0.9 | 194,861   | 0.881 | 25.0  | K |
| H  | c2-cmy8-r0850-p120-x1 (NEW)| 4mm | 1961 | 0.9 | 2,220,921 | 0.897 | 284.9 | CMY |
| I  | c2-cmy8-r0700-p120-x1 (NEW)| 4mm | 1961 | 0.9 | 1,798,761 | 0.897 | 230.7 | CMY |

- 4mm = `xerox-altalink-c8245-ink` registry row (geometry PROBE — the
  AltaLink printable clip was never measured e028-style; only c2 gains
  from 4mm, c3/c4 fields are quantization-identical to 6mm).
- H reproduces holo3's `max` capacity byte-for-byte (2,220,921 B, payload
  sha `0ad329fb…`) — two independent stacks agreeing on the same
  configuration's capacity. The .ps bits differ (seed namespaces).
- E/F/H/I sit ABOVE the pooled dead-plane dial (needs q ≤ 2/3): a dead
  plane is not a deterministic tier on these sheets. D (q=0.5) keeps it.
- Colour sheets carry the AltaLink MIC yellow dots (e031: 0.210/mm²).

## 033.1 Sheet I — scans

| file (scratch/) | sha256 | true dpi | note |
|---|---|---|---|
| xerox-canon-18.8-I-…-2400dpi.tiff | `269d8121…` | 2400 | capture 1 |
| …-2400dpi-displaced.tiff | `a410631d…` | 2400 | initially misdeclared 1200 (033.2) |
| …-2400dpi-displaced2.tiff | `36b90a50…` | 2400 | capture 3 |
| …-4800dpi.tiff | `5d242053…` | 4800 | mechanism scan, NOT yet ingested |

All platen placements distinct (multi-scan doctrine).

## 033.2 The misdeclared-dpi incident (operator + receiver both correct)

The first decode declared `--scan-dpi 1200` for what was a 2400 dpi
raster (scanimage resolution vs filename mixup). The survey measured
8 px/cell, which at declared 1200 snaps to c_dots=4; the spec says c2;
`place.py`'s pitch-contradiction guard refused every window; all levels
committed vacuously in seconds. DPI is operator-declared truth — a wrong
declaration is a wrong-geometry hypothesis and the refusal is the
designed behaviour. Footnote: on main, survey c_dots=4 was an invalid
VALUE; the branch's c4 row made it a legal verdict, so the failure
surfaced as a clean geometry mismatch. The same file re-entered the
fresh state correctly declared and contributed normally.

## 033.3 Sheet I — decode timeline (all runs: branch `c4-row`, Canon RGB)

1. Single capture (`269d8121`, 2400): full 12-level plan (`--refine`),
   reach 5152/5277 — SHORTFALL 125. Certificates concentrated M>C>>Y.
2. Fresh state, three 2400 captures, `--refine`: **CLOSE VERIFIED
   in-flight — 1,798,761 bytes, sha `2445b95db5b49bf3…` == the emitted
   counting payload, byte-exact** (`recovered.bin` cmp-identical).
   Final certificates 5,297/5,883: M 1958 (99.7% of 1961), C 1895
   (95.3%), Y 1444 (73.6%). K/N 0.897.
3. `--complete` resume: crashed at LOAD — "stream 'M' is not declared"
   (033.5); state undamaged; the close had already verified in run 2.

**Headlines (single sheet, no promotion):** first colour rung above
r0550 ever recovered from paper; first pooled-fountain close on paper
(`reach … over 1 block(s)` — one fountain across C/M/Y; the -v0
per-stream shape would have needed Y to stand alone); first off-catalog-
geometry colour volume; net 230.7 b/mm² field ≈ 3.6× e029's certified
record (existence proof only — provisional receiver, q=0.9, one sheet).

## 033.4 The Y dead bands: detector-frozen, and the mechanism is MEASURED

Y failures were strongly column-banded (full page height): residue/53 by
tile_x = [7,1,21,5,0,0,0,14,53,38,37,39,0,0,0,45,49,45,31,47,2,0,0,0,4,
3,5,43,50,24,12,0,2,0,0,0,4] — groups 8–11, 15–19, 27–29.

Scan-side analysis (read-only, 2400 capture 1;
`scratch/xerox-v1-20260818/I-y-band-analysis.png`):
- DC blue absorption (Y toner mass): FLAT across dead bands (±1.5 DN,
  corr with residue ≈ 0, both platen orientations).
- Y-specific HF modulation (crosstalk-removed B residual): 14.1–15.1
  everywhere vs 4.4 paper-noise floor — uniform to ~5%.
- PSD shape: identical dead vs clean (cell 0.125 / dot 0.25 peaks full
  strength; clean-to-clean spread exceeds dead-to-clean).
- Event ledger: dead-band Y attempts fail with FULL evidence
  (informative = 3976 = every payload cell; `attempted_failed` 12,455) —
  LLR quality, not missing evidence.

GT cross-correlation (user hypothesis: "Y runs out of phase";
`scratch/xerox-v1-20260818/regmap-gt/`, rerunnable
`measure_plane_offsets.py`, 481 patches, GT unpack sha-validated against
the manifest, affine re-anchored — scanner scale +0.1%):
- **The Y plane carries a SINUSOIDAL x-registration error: peak 3.33 px
  @2400 = 0.83 printer dot = 0.42 cell, period ≈ 18.5 tiles ≈ 100 mm
  (roller-circumference class). Dead columns sit on the extrema, clean
  on the zero crossings. Spearman(|ΔY_x|, residue) = +0.80 (p = 4e-9;
  independently recomputed). ΔY_y flat (+0.07, n.s.).**
- Failure threshold sharp near 0.5 dot: |ΔY_x| ≤ 0.25 dot → residue
  1.3/53; 0.62–0.75 dot → 39.8/53.
- Why C/M survive: address words are W/CM states → the plane-common pose
  locks to the C/M MEAN; C and M each deviate ≤ ~0.27 cell while Y
  reaches 0.42 cell. Matches the full-evidence LDPC-failure signature
  exactly.
- Scanner finding (separable control): dCM_x sweeps ±4 px ODD-symmetric
  about the scan axis, anti-correlated with residue = Canon R−G lateral
  chromatic aberration. dCM_y ≈ −1.5 px ≈ 0.37 dot constant (real,
  slowly-varying C-above-M print registration). Lateral CA is
  necessarily odd; the Y term is EVEN — no scan-lens mechanism produces
  it. With the three-placement replication, the sinusoid is the
  printer's.
- The ~35% mop-up winner-flip canary on this sheet is the same
  mechanism, seen by the two-view consistency check.

Consequences: re-placed scans help only marginally (print-fixed offset;
capture-side variation flips threshold-straddling tiles — observed:
Y 1377 → 1444 across two extra captures). 16 px/cell will NOT undo a
0.42-cell print offset — prediction for the 4800 mechanism run: bands
persist. The receiver-axis fix is per-plane pose (PK6/A2, measured-
negative on smooth τ 0.1–0.3 dot captures, REOPENED by this sheet:
banded, plane-specific, 3–8× larger). Prediction for sheet H (r0850,
thinner parity): wider dead bands, lower threshold — falsifiable before
its decode.

## 033.5 Receiver findings (branch, fixed same day)

- **Off-catalog colour resume refused at load** ("stream 'M' is not
  declared"): SessionIndex resolves streams by catalog lookup of the
  state's row id; `--coding` + non-default-printer geometry is not a
  catalog row → opaque one-stream fallback. K states at this geometry
  (e029) survived by luck. Fix `6b18508`: the load path threads the
  request's reconstructed spec (the parameter SessionIndex always had).
  Side effect, deliberate: off-catalog K resumes get full validation.
- **`--no-close`** (`202aac6`, `103cc7c`, `ad4a561`): run and commit all
  flag-bounded capture work, perform no fountain close work (no eager
  checks — implies `--complete`; no final solve; no terminal replay).
  Motivation: every resume of a verified state otherwise re-solves the
  close to reproduce the payload.
- **Terminal sessions skip capture ingestion entirely** (v0.33
  immutability, confirmed live: new sources never register on a VERIFIED
  state). Mechanism experiments on new captures need fresh states.
  Documented as-is in RECEIVE-DESIGN v0.56.

## 033.6 Owed

- Nine sheets unscanned (A, A2, B, C, D, E, F, G, H). H before decode:
  the 033.4 prediction is pre-registered.
- 4800 mechanism run on sheet I (fresh state, `--no-close`): does the
  Y-band residue persist at 16 px/cell? (Predicted: yes.)
- Print-day operator details for 033.0 (path/media/settings).
- Per-plane pose (A2 revival) is a separate line of inquiry — this
  campaign closes at its own finish line.
- Branch ratification rulings: c4 amendment; rate-rung amendment incl.
  the `-x1` naming (pooled rows currently signal pooling via `-v1`; the
  `-x1` rungs are pooled but do not say so — naming grammar needs a
  ruling before any merge); `family` field's default `"k"`.

## 033.4a Correction (2026-08-21): the residue table is a mid-run snapshot

The §033.4 per-column residue table sums to 581 (Y certified 1380) —
captured before the third capture's tail finished; the archived
VERIFIED state ends at 517 (Y 1444). Comparisons should score against
the archived state (docs/PLANE-FIELDS.md §6.4 scores against both).

## 033.7 Branch record — CLOSED (2026-08-19)

The `c4-row` branch and its worktree are DROPPED. The FORMAT-SPACE v2
identity lattice (docs/FORMAT-SPACE.md v1.0, merged to main 03a350c)
rebuilt every semantic this experiment ran on, by derivation:

- All ten sheet identities (A–I incl. c4-r0550 and both c2 `-x1` rows)
  are fossils with byte-frozen AES seeds (`format/fossils.py`); decode
  via `--format L:<legacy-spec-id>`. Sheet I's 2.85 GB VERIFIED state
  replays bit-identically through the fossil route on main (5297
  certificate identities recomputed; close sha 2445b95d… unchanged).
- The branch's c4 compose golden was carried verbatim and the `-x1`
  emission goldens (which the branch itself never pinned — its F7
  debt) were minted on main after byte-verification against the branch
  tree's own emission in BOTH directions (tests/holo/
  test_fossil_seeds.py, commit eec9af4).
- `--no-close` was re-implemented correctly on main from the ruled
  state×mode table with the DETACH semantics this session's 4800-scan
  incident motivated (RECEIVE-DESIGN §9a, commit 4ad4918) — the owed
  sheet-I 4800 mechanism run can proceed on main with a fresh state or
  by detaching the verified one.
- The never-printed c3 `-x1` pair was deliberately dropped (no sheet
  froze it); it can return as a fossil if a print ever surfaces.

Provenance: the complete branch diff remains committed on main as the
parked patch (f1bc0d0); the branch commits themselves are unreferenced.
Still owed from 033.6: the nine unscanned sheets, the 4800 mechanism
run, operator print-day details, holo2 c4/lattice parity (H-wave).

