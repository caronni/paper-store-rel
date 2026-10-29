# measure/scanner — Canon LiDE 400 per-channel optical characterization

Two instruments:

| entry | question | inputs |
|---|---|---|
| `blue_mtf` | how sharp is the scanner's **blue** channel, where Y is read? | the e028 knife edge + the e028 colour discovery sheet |
| `ink_psf` | is **yellow toner** really the broad ink, or was that a low cartridge? | the e028 **and** e031 discovery pairs, one code path |

`ink_psf` is the E6 replication (2026-08-23) and it also carries a
per-plane registration arm; its section is at the bottom of this file.

**Nothing here is a test and nothing here runs under `pytest`.** `measure/`
is outside `testpaths`; on the `measure/plane_fields` precedent (user
ruling 2026-08-21: measurement-instrument code lives in neither `tests/`
nor `scratch/`) this package is the home for the scanner instrument.

Answers docs/INDEPENDENT-PLANES.md **§4.I item 3** (scheduled in §6 as
**P2**): e028 measured the scanner of record's **luma** MTF from a knife
edge (glass-level MTF10 ≈ 17 lp/mm, §028.4) and e033 found an R−G lateral
CA, but the **blue** channel — where the Y plane is read — was never
characterized, while Y measures "optically soft" on sheet I. The question
is how much of that softness is *scanner blue optics* and how much is
*toner scatter*.

Read-only, archived captures only. **No scan, no print, no hardware.**

## How to run

```
cd <repo>
PYTHONPATH=measure env/bin/python -m scanner.blue_mtf --all \
    --evidence-root <evidence> --out build/scanner
```

`scanner` is the package and every module imports its siblings
relatively, so `-m scanner.<entry>` is the only supported invocation.
`src` is NOT needed: nothing here imports `holo` (numpy + tifffile + PIL).

| flag | what it does |
|---|---|
| `--selftest` | synthetic slanted edges with a known σ and shift; calibrates the estimators (seconds) |
| `--knife` | the glass-level **luma** anchor from the e028 blade scan (~1 min) |
| `--color` | the per-channel differentials from the e028 RGB capture (~4 min) |
| `--inks` | the **toner half**: per-ink (C/M/Y/K) edge width on the same sheet, each ink read in the channel that sees it, with that channel's scanner σ removed in quadrature. Needs `--knife` (the σ anchor) and `--color` (the split) |
| `--all` | all four, then the figure |
| `--tone {srgb,gamma22,none}` | which capture transfer function to invert — **the robustness control**; writes to `blue-mtf-<tone>.json` |
| `--segments N` | x segments per strip rule (default 8) |
| `--verify-sha` | hash both inputs against the recorded values (the colour scan is 6.9 GB, ~40 s) |
| `--evidence-root DIR` | the published evidence archive root the input paths below join (else `$PAPER_EVIDENCE_ROOT`; refused by name when neither is given; `--selftest` needs none) |
| `--out DIR` | required: where the JSON and figure land |

## Inputs (both read-only, both sha-pinned in `blue_mtf.py`, relative to `--evidence-root`; in the evidence archive)

| file | sha256 | record |
|---|---|---|
| `paper-store-evidence-holo-2026-10/028-discovery-m281/knife-edge/captures/knife-edge-canon-4800grey.tiff` | `58a3ceb1e52b…` | experiments/028 §028.4 — 9872×16320 **grey**, 4800 dpi, LZW |
| `paper-store-evidence-holo-2026-10/028-discovery-m281/discovery/captures/discovery-color-canon-4800rgb.tiff` | `d0f12451dfc1…` | experiments/028 capture 028.1b — 56128×40832 **RGB**, 4800 dpi, uncompressed |

2026-10-09: inputs renamed to the published archive paths (the table above, and `ink_psf.py`'s
`SHEETS`: the e031 pair under `paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/`
`captures/`, `reports/production/`, `reports/w8/`, the e028 pair and both page plans under
`paper-store-evidence-holo-2026-10/028-discovery-m281/discovery/` `captures/`, `reports/`, `jobs/`).
An uncompressed capture is published as `.tiff.jxl` and rebuilt by the release's `tools/unpack.sh`
(byte-identical, so the sha pins hold); both tools refuse by name when an input is absent.

## Outputs

`<out>/blue-mtf.json` (+ `blue-mtf.png`): inputs
and their hashes, the self-test table, every groove and every K target
with its per-channel MTF50/MTF10/10-90 rise, the per-target
differentials, and the per-family aggregate.

## Why a PRINTED target can answer a SCANNER question

The knife-edge capture is **grey**, so it anchors luma and nothing else —
there is no colour glass-level capture in the corpus. The per-channel work
therefore runs on K-toner targets in an RGB capture, and leans on one
fact: **a K edge is the same physical edge in every channel.** Take a
channel ratio and every print-side term — toner scatter, paper
light-spread, development raggedness, the printer's edge jitter — cancels,
because it is channel-common. What survives is scanner-side:

* `dsigma2_um2` = σ_c² − σ_G², from `ln(MTF_c/MTF_G) = −2π²·Δσ²·f²`.
  Equivalently the difference of the LSF second moments, which add under
  convolution; no Gaussian assumption about the *target*, only about the
  scanner-side *difference*.
* `shift_px` — derivative-weighted least-squares registration of the two
  normalized ESFs, after width-matching (a translation-only fit between
  profiles of different width is biased toward zero; the self-test
  measures that at −27 %, and the width-match removes it).

Edges are measured on **both polarities** of every target, because a
measured offset is `displacement + p·asymmetry`: a real lateral
displacement moves a white→black and a black→white edge the same way,
while a channel-dependent PSF asymmetry moves them oppositely. The
polarity mean is the registration number; the half-difference is the
asymmetry. Line targets (the 2-dot cross bars) cannot be split this way.

## Targets on the e028 colour discovery sheet

| family | what | n | axis | LSF window |
|---|---|---|---|---|
| `solid-K-edge` | the four edges of `tone/K/1.0` (8×5 mm, the layout's only large solid-K area) | 2 per axis | x and y | ±80 px — wide, so its Δσ² is **unbiased** |
| `strip-rule-edge` | the outer edges of both HCAL-R1 strip frames, 8 x segments each | 32 | y | ±18 px (the rule is ~37 px thick) |
| `cross-bar` | `registration/rXcY/K`, 3×3 platen positions, one vertical + one horizontal 2-dot bar each | 9 per axis | x and y | ±26 px |

`--inks` adds the `selectivity/{C,M,Y}` solids (5×6 mm at x_mm 139/145/151)
plus `tone/K/1.0`, each read only in the channel its ink absorbs. That arm
is the *other* half of the split and carries its own caveat: one sheet,
one capture, the M281's colour toner was low on this print day (the
operator wrote "color toner low" on the sheet), and the leading/trailing
edge asymmetry is as large as the ink-to-ink difference. A direction, not
a number — and **not** a measurement of sheet I, which is a different
engine, sheet and capture dpi.

## Caveats that belong with any number taken from here

- **The knife-edge MTF is a lower bound.** That scan has no clean
  glass-level *step*: the spine transition carries a ~0.6 mm cast-shadow
  penumbra from the blade's 0.4 mm wall and the cutting side is a
  physically gradual grind (028.4 retracted its first reading for exactly
  this). The usable target is the snap-score groove — a *line* of unknown
  physical width — so its FWHM is an upper bound on the LSF and its MTF a
  lower bound. 028.4's rule of reading the **narrowest** groove is kept.
- **Panel A / the K-target MTF is print × scan**, not the scanner. Read
  the channel order inside an edge, not the level. Above ~4 lp/mm the
  absolute curve also carries LSF-window ringing, so MTF50 is meaningful
  there and MTF10 is not.
- **Tight windows understate |Δσ²|** (the self-test: −69 % at ±18 px on a
  σ=45 µm target). The `strip-rule` and `cross-bar` magnitudes are lower
  bounds; only `solid-K-edge` is unbiased, and it has n=2 per axis.
  **Amended by E6** (below): the `cross-bar` numbers recorded here also
  carried a MODEL error — an intercept-free `f²` fit on a LINE target,
  where the spectra are not DC-matched — worth ±100 µm² on the e028
  sheet. With `compare_channels(allow_intercept=True)` the family
  replicates on a second sheet and the window-bias story above is what
  is left.
- **Everything is at 4800 dpi on one capture, one print day, one sheet.**
  Sheet I — where the Y softness was measured — was captured at 2400 dpi,
  a mode this instrument has not characterized; a CIS line-timing offset
  in particular need not scale the same way.
- Paper light-spread is wavelength-dependent and *longer* in red, so a
  paper-side bias works AGAINST finding red the broad channel. The
  measured direction is therefore conservative, not flattered.
- `luma601` is carried as an internal check: it is a fixed linear mixture
  of R, G and B, so its Δσ² and shift must equal the mixture of theirs.
  They do (strip family: +2.3 µm² measured, +2.3 predicted).

---

# `ink_psf` — the same measurement on a second engine (E6, 2026-08-23)

The `--inks` numbers above are **consumable-confounded**: the M281's
colour toner was low on the e028 print day and the operator wrote it on
the sheet, so "yellow toner scatters more" and "this cartridge is empty"
are the same number there. The AltaLink e031 discovery pair breaks the
tie — same scanner, same 4800 dpi, the **same authored page** (identical
`page_plan_semantic_sha256`), and an engine whose Y is measured healthy
(e031 §7: tone range 0.515 against 0.351; density over paper at 25 %
coverage 0.0714 against 0.0110).

```
cd <repo>
PYTHONPATH=measure env/bin/python -m scanner.ink_psf --all \
    --evidence-root <evidence> --out build/scanner/e031
```

`--all` is both colour sheets plus the two B/W sheets (a K-only reference
in luma); `--sheets`, `--arms`, `--tone`, `--verify-sha`, `--evidence-root`, `--out` are as
in `blue_mtf`. One run is ~35 s and peaks around 1.5 GB, almost all of it
the knife-edge anchor. Artefacts:
`<out>/e031-ink-psf.{json,png}`.

## No pinned pixels — targets come from the page plan

`blue_mtf` pinned every e028 target as a raw pixel box found once by
hand. That does not port: the e031 sheet is the same authored page but a
different impression, so every box moves. `_sheet.py` composes the two
artefacts the repo already writes for every discovery capture —

* the **page manifest** (`discover emit`) — each probe's authored box in
  layout dots;
* the **HCAL report** (`discover analyze`) —
  `geometry.affine_layout_to_scan`, fitted from the four corner marks

— and refines locally from there. Manifest and report are matched on
`page_plan_semantic_sha256`, so the wrong page plan is a refusal rather
than a silent mislocation. Validated against the old pins: `tone/K/1`
predicts x `[16557, 18067]` against the hand-found `[16558, 18060]`.

**Use `*_source_dots`, not `*_layout_dots`, for anything positional.**
The emitter places rasters at the rounded integer; the two differ by up
to 0.5 dot = 21 µm, which is the size of the plane offsets arm 3
measures.

## Three arms

1. **channel** — the scanner half, unchanged in principle from
   `blue_mtf`: a K edge is the same physical edge in R, G and B, so a
   channel ratio is scanner-side.
2. **ink** — the toner half. Each ink read in the channel it absorbs
   (C→R, M→G, Y→B, K→G) on its `tone/<plane>/1` solid, **all four
   edges**, so both polarities on both axes; the pooled scanner sigma
   for that channel and axis comes out in quadrature. `selectivity/{C,M,Y}`
   is carried as the secondary family (it is what `blue_mtf --inks` used).
3. **registration** — per-plane lateral offset from K, from the nine
   `registration/rXcY/{K,C,M,Y}` crosses, each plane compared with the K
   bar **read in the same channel** so the scanner's lateral CA cancels
   identically instead of being corrected for.

## What E6 changed in the method (and why the old ink numbers move)

Three defects, all found on real data, all fixed opt-in so `blue_mtf`'s
recorded output stays **byte-identical** (verified: its whole `color`
block is unchanged):

- **Plateaus are not flat.** A solid patch shades toward its own edge —
  the M281's starved yellow lightens by ~8 counts over the last 180 µm.
  Normalizing against two constant levels turns that ramp into edge
  width. `analyze_edge(plateau_guard_um=…)` fits a straight line to each
  side beyond a guard band (250 µm here, ≥3.8 σ for the widest edge) and
  normalizes against the two lines.
- **First-crossing 10/90 is not local.** The e028 yellow patch carries a
  mottle bump 90 px inside its own ink plateau that rises past 0.1; the
  first-crossing rule anchored there and reported a **563 µm rise on an
  ordinary 113 µm edge**. The crossings are now found by walking
  *outward* from the 50 % point.
- **One scanner deserves one anchor.** The K patch gives only n=2 edges
  per axis per sheet and the per-sheet estimate swings by ±3 µm, which
  would land straight in the cross-engine comparison. `scanner_sigmas`
  pools the K-patch edges of every colour sheet (n=4/axis), so a residual
  error in the anchor shifts both engines together and cancels.

## Results (both sheets, srgb tone curve, 4 edges per ink)

σ_ink (µm), `tone/<plane>/1`, scanner removed in quadrature:

| ink | Xerox AltaLink C8245 (e031) | HP M281fdw (e028) |
|---|---:|---:|
| K | 36.8 ± 1.2 | 39.6 ± 2.4 |
| C | 37.3 ± 2.2 | 38.1 ± 1.4 |
| M | 37.7 ± 1.0 | 36.8 ± 2.0 |
| **Y** | **34.8 ± 4.7** | **46.0 ± 2.8** |

**Y's breadth was the cartridge.** The stable statistic is Y against its
own sheet's K/C/M mean: **+7.7 / +7.7 / +10.5 µm on the M281** and
**−2.5 / −2.2 / −3.0 µm on the AltaLink**, under sRGB / gamma-2.2 / no
decode respectively. On the AltaLink the four inks are one club (spread
2.9 µm); on the M281 Y stands 6–9 µm outside it. Corroboration from the
line targets on the same sheets: the M281's Y 2-dot bars are at once the
**narrowest and faintest** on the page (FWHM 98.9 µm against K's 119.1,
peak 0.43 against 0.61) while the AltaLink's sit with the club — thin,
ragged development, not scatter. B/W-sheet K references (luma): AltaLink
33.6, M281 35.7 µm.

The order *within* the AltaLink club is not stable under the tone-curve
control and should not be read; the club-vs-Y contrast is.

## The replication test, and the model defect it found

Two sheets of one page through one scanner give every target family a
replication test it never had. It failed loudly. Δσ² vs G (µm²), as
originally fitted:

| family | e031 R | e031 B | e028 R | e028 B |
|---|---:|---:|---:|---:|
| `solid-K-edge/y` (n=2) | +18.2 | −49.7 | +35.9 | −51.0 |
| `strip-rule-edge/y` (n=32) | +4.1 | −17.0 | +15.3 | −22.3 |
| `cross-bar/x` (n=9) | **+4.0** | **−32.8** | **+102.1** | **−107.3** |
| `cross-bar/y` (n=9) | −2.4 | −24.8 | +89.2 | −94.8 |

The EDGE families agree; the cross-bar LINE family is out by 3×, and its
R and B are near-perfectly antisymmetric — the signature of a *constant*
being absorbed, not of a width difference. It was:

> `compare_channels` fits `ln(ratio) = −2π²·Δσ²·f²` **with no constant
> term.** For an EDGE that is correct — `analyze_edge` normalizes each
> channel's ESF on its own plateaus, so its LSF integrates to 1 in every
> channel and the ratio really is 1 at DC. For a LINE it is wrong:
> `line_metrics` normalizes by the **peak** and leaves the spectrum in
> linear reflectance, so the DC ratio is the channels' ink **contrast**
> ratio. The M281's slightly warm black reads 4.5 % weaker in R than in
> G; the fit had nowhere to put that constant except the `f²` slope.

Ruled out first: it is not the baseline window (re-fitting with 60
end-bins, or a fitted line, moves e028's B by 3 µm² and leaves the gap
intact). The amplitude intercept is the whole of it —

| cross-bar/x | e028 R | e028 B | e031 R | e031 B |
|---|---:|---:|---:|---:|
| intercept-free | +102.1 | −107.3 | +4.0 | −32.8 |
| **with intercept** | **−5.9** | **−12.8** | **−6.1** | **−9.5** |
| amplitude ratio c/G | 0.955 | 1.041 | 0.996 | 1.010 |

`compare_channels(allow_intercept=True)` is now used for the cross-bar
family (and only there — an edge does not need it and a free parameter
only adds variance), the fitted `amplitude_ratio` is reported, and
**every family replicates**. B is sharper than G in all of them on both
sheets; the magnitude grows with the LSF window, largest on the ±80 px
K-patch, which is exactly what the self-test's window bias predicts.

Pooled anchor (K-patch edges of both sheets, n=4/axis): σ_R/σ_G **1.033**
on both axes; σ_B/σ_G **0.937** on y (Δσ² −50.4 ± 8.1 µm², the sheets
independently −51.0 / −49.7) and **unresolved** on x (−3.7 ± 47.3, the
two sheets' n=2 estimates cancelling). B-sharpest / R-broadest stands;
the **0.86** end of the recorded "σ_B 0.86–0.97 × σ_G" was `cross-bar/x`
before the fix and should not be carried. Luma anchor reproduces: MTF10
17.82 lp/mm against 028.4's ~17.

## Per-plane registration, from the discovery sheet itself

`layout.py:615` puts one target's K/C/M/Y crosses **4 mm apart in x**, so
every "plane offset" carries `baseline × local page-scale residual` —
which is why the analyzer's own `plane_registration` reports up to 115 µm
on the e031 sheet and why e031 §5 called that number an upper bound.
Regressing the three planes' offsets ON their 4/8/12 mm baseline
separates the two; the **fit residual** says whether the split is
meaningful.

| sheet | axis | displacement (µm) | local scale (µm/mm) | fit residual |
|---|---|---:|---:|---:|
| AltaLink e031 | x | +6.3 ± 2.5 (+0.149 dot) | −0.17 ± 1.79 | 3.6 µm |
| AltaLink e031 | y | +18.4 ± 2.0 (+0.435 dot) | +0.24 ± 0.49 | 2.2 µm |
| M281 e028 | x | +2.6 ± 8.1 (+0.060 dot) | +1.55 ± 1.10 | 5.9 µm |
| M281 e028 | y | +89.5 ± 11.1 | −12.68 ± 0.90 | **15.1 µm** |

- On the **AltaLink**, the three colour planes share ONE line to within
  2–4 µm: they are collectively displaced from K by (+0.15, +0.44) dot
  and **no plane has an offset of its own**. The apparent 115 µm was the
  baseline. The local x-scale residual is ±6 µm/mm and *column*-
  structured, repeating down all three rows (col 0 ≈ −1, col 1 ≈ +6.3,
  col 2 ≈ −6.1); col 1's +6 appears on **both** engines, so that part is
  scanner- or method-side, and col 2's does not.
- On the **M281** the model does not apply (residual 15.1 µm): read the
  raw means instead — C +28.1, M +9.4, **Y −73.3 µm = −1.7 dot** in the
  process direction. That is a second mechanism behind e030's Y-empty
  CMY8 failure, alongside the starved cartridge.
- Estimator control: every offset is recomputed with a half-max midpoint
  instead of a centroid (a one-sided per-ink toner tail would drag a
  centroid and fake exactly this). The two agree to ≤2.6 µm everywhere;
  both are in the JSON.

## Caveats that belong with any number taken from here

- Everything the `blue_mtf` caveat list says still applies: σ_luma is an
  upper bound so every ink σ is a **lower** bound; the absolute MTF of a
  printed target is print × scan; single sheets, single captures, one
  print day per engine, **no promotion**.
- Three x-columns of registration crosses **cannot** sample e033's
  ~100 mm-period Y sinusoid. CHARACTERIZE-WORKPLAN W11 item 2 (a
  page-spanning per-plane registration track) stands unchanged.
- The AltaLink sheet was printed via `lpr -o raw`, not the mandated
  socket-9100 path (e031 §1), and its scanner-adequacy verdict is
  `inadequate`. Channel physics, not a registry footing.
- The two ink comparisons are one sheet per engine. This measures these
  two impressions, not the two engines.
