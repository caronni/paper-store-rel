# Experiment 028 — HCAL-R1 default discovery on the HP M281

Status at 2026-08-04 17:20 CEST: both corrected pages printed cleanly and
BOTH Canon 4800 captures (B/W grey, color RGB) are analyzed; the earlier
"color capture is not yet analyzed" wording was stale.  Both captures'
scanner-adequacy verdicts are `inadequate` (transfer-block + smoothing
gates), so all results remain provisional discovery evidence; this is not a
production-format qualification or registry promotion.  **See the 028.2
forensic addendum below: the physical-ink ladder verdicts in both reports
are RETRACTED as registration artifacts (the measured print margin is
~4.15 mm), and the analyzer fix campaign is docs/CHARACTERIZE-WORKPLAN.md.**
Same print-day, evening: the W7b tightened-margin payload validation was
executed as **experiment 029** — the first physical holo-v1 print, decoded
VERIFIED byte-exact at 4.5 mm margins
(experiments/029-holo-v1-first-print.md).

## Objective and evidence footing

- First physical run of the current `discover`/HCAL-R1 instrument on the HP
  Color LaserJet Pro MFP M281fdw, treated as an unknown engine for this
  instrument.  Earlier E025/E027 evidence used different instruments.
- Date/session: 2026-08-04, `2026-08-04-A`, Europe/<city> (CEST).
- Branch/base: `codex/main-20260804` at
  `aee59685006f6546cdd37957df5675b78bd3c463` plus the tracked portability
  correction below.
- Request footing: `default` (`request_code=0`, `request_dpi=null`); no
  `/HWResolution` request.  Stage `discovery`, copy index 0, layout/stimulus
  schema v2.
- Printer path: `scripts/print_plane.sh`, raw JetDirect to
  `<host>:9100`; no CUPS, application scaling, or fit-to-page step.
- Media: white 90 g/m² A4, the operator's usual HP stock for now.  Brand, lot,
  tray, and side/orientation were not recorded.
- Supplies: the printer is still using its old cartridges.  Operator
  correction 2026-08-04: K toner is fine — the only weak cartridge is Y
  (borne out by the measured tone ranges: K 0.656 / C 0.643 / M 0.520 vs
  Y 0.351).  Treat consumable state as part of this run's evidence
  footing; "low toner" claims are scoped to Y only.
- User authorization: in-session instruction to generate and print the K and
  CMY/color sheets, understood as one B/W/K-centric page and one color page.

## Zero-paper and emitter preflight

- `tests/holo`: 982 passed, 35 skipped, 9 expected provisional-receiver
  warnings in 180.30 s.
- `confetti.py registry` completed and the output directory was confirmed new.
- Both jobs are one-page PostScript streams and Ghostscript `nullpage` accepted
  each complete stream.
- After the portability correction: 12 characterize CLI tests, 28
  emitter/report-anchor/contract tests, and 14 opt-in live Ghostscript report
  differentials passed.  The latter poison Ghostscript's non-standard `min`
  and `max` extensions for both calibration/B/W and discovery/color identities.

## Attempt 0 — rejected bundle

Command:

```sh
env/bin/python confetti.py discover emit \
  scratch/discovery-m281-0804
```

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| bundle manifest `hcal-discovery-copy0000-default-cd1cc1c0f61d2468.bundle.json` | 1,921 | `5e26613c215d8303075bc3e5e01d2f737596b47496c3a0555aecd671ad882c3b` |
| B/W PS `hcal-discovery-bw-copy0000-default-f3c9e5f807ca05bf.ps` | 5,535,066 | `6bcc31f6faf83c6f03080863b5ab59a38d4990396a57b2ddbbdbecf4d9699b1d` |
| B/W manifest | 165,846 | `cf89f6ac047c5f7975f9e8654eb1e738d35e14ea86013bbc4982b4188bcc0656` |
| color PS `hcal-discovery-color-copy0000-default-6995a5d0b5b0218d.ps` | 10,337,223 | `9d0d1f94f93dde1f8d6f39c92408740ce0d3f2abad1ed552cdd8f8e926239e99` |
| color manifest | 271,998 | `8554a80098812644da52dcc156b3d1e9ea6dba0cd3c5501414ea4264c54cf489` |

The B/W stream was transferred once.  The printer replied
`undefined; OffendingCommand: min` and `Flushing: rest of job`; therefore
attempt 0 is rejected and supplies no characterization evidence.  The color
stream from this bundle was **not** sent.  The operator later reported no
physical error output.

Root cause: `/PUTSLOT` used `S length MAX min`; `min` is a Ghostscript
extension, not a standard PostScript operator.  Ghostscript preflight therefore
masked the portability defect.  The emitter now uses the equivalent portable
expression:

```postscript
/N S length dup MAX gt { pop MAX } if def
```

Source/test hashes used for the corrected jobs:

| File | SHA-256 |
|---|---|
| `src/holo/characterize/emit.py` | `891bbfb614ee88937401d25e4c6c998a62bdbf26dce5ac4abd4bb7f07cf0ac0a` |
| `tests/holo/test_characterize_emit.py` | `f8e2399edd5950f1d1b15a9ad7619ec2834b60e356842c7037df45b90ce56722` |
| `tests/holo/test_characterize_gs_report.py` | `6f259ec584f6aa6e37d994934508932e42c63a628f68ec2cf4bc7ddaf39c9678` |

## Corrected bundle (`r1`)

Command:

```sh
env/bin/python confetti.py discover emit \
  scratch/discovery-m281-0804-r1
```

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| bundle manifest `hcal-discovery-copy0000-default-652839a069459bad.bundle.json` | 1,921 | `171d54992587daacbefbb021ac23d48b5c2095d9aeeec06fff883d3920653109` |
| B/W PS `hcal-discovery-bw-copy0000-default-f3c9e5f807ca05bf.ps` | 5,535,084 | `cdb396ff87fa44ef136bec353d7090549d7d3a3dd2883cf2c37f2a5411b48082` |
| B/W manifest | 165,846 | `fb4948f445cdf8f5abf4982ede7f258f8e9cf05e83b92547747cbe98a32229b1` |
| color PS `hcal-discovery-color-copy0000-default-6995a5d0b5b0218d.ps` | 10,337,241 | `482a89fc6eb8ec3a00107242c6db9093e3603ce148be82d3919832f56148a53d` |
| color manifest | 271,998 | `2b8e55f4d4c9a4e62757254344dea3d19aba3ae4aa771e229670ff59c11b753f` |

## Physical print-send log

| Run | Intended physical ID | Kind | Job/result |
|---|---|---|---|
| 028.0a | none; rejected attempt | B/W/K | Original PS `6bcc31f6...`; 5,535,066 bytes transferred, then printer `/undefined min` and flushed. No valid sheet. |
| 028.0b | `e028-m281-20260804-bw-01` | B/W/K-centric | Corrected PS `cdb396ff...`; 5,535,084 bytes sent to raw 9100, exit 0, no interpreter error returned; operator confirmed a valid physical print. |
| 028.0c | `e028-m281-20260804-color-01` | color/CMY-centric with K controls | Corrected PS `482a89fc...`; 10,337,241 bytes sent to raw 9100, exit 0, no interpreter error returned; operator confirmed a valid physical print. |

Transport acceptance is not proof of physical bit fidelity.  Both intended
pages are physically present; perform and record the protocol's loupe check
before treating decode statistics as printer evidence.

## Capture 028.1a — Canon B/W discovery scan

The incoming `scratch/1.tiff` was inspected before analysis, identified as the
B/W capture from its single-channel structure, and renamed to bind the
physical sheet and capture footing:

`scratch/e028-m281-20260804-bw-01-canon-4800gray.tiff`

- 2,291,818,718 bytes; SHA-256
  `15d8716c9ad10c986f938b52befe3738777363589a44ab03e2749bc5052c847e`.
- One 40,832 x 56,128 image at true 4800 x 4800 dpi; 8-bit BlackIsZero
  grayscale; uncompressed; one contiguous full-height strip; top-left
  orientation.  The TIFF carries no scanner/software provenance tags.
- Footing supplied to the analyzer: `hp-m281`, `raw9100`,
  `white-90gsm-a4`, `canon-4800`, `grey-no-auto`, session
  `2026-08-04-A`.
- Exact operator capture command:

  ```sh
  scanimage -d pixma:04A91912_<SERIAL> --resolution 4800 --mode gray \
    --format=tiff -o 1.tiff
  ```

  This directly supports the declared `canon-4800`/`grey-no-auto` footing:
  explicit Pixma device, true 4800-dpi request, grayscale capture, direct TIFF
  output, and no application-side crop, enhancement, resampling, or lossy
  encoding options.  The resulting TIFF independently confirms 4800 x 4800
  dpi, 8-bit BlackIsZero grayscale, and no file compression.  The backend or
  scanner's internal processing is still part of this exact capture footing.

Exact command:

```sh
env/bin/python confetti.py discover analyze \
  scratch/e028-m281-20260804-bw-01-canon-4800gray.tiff \
  scratch/e028-m281-20260804-reports --scan-dpi 4800 \
  --manifest scratch/discovery-m281-0804-r1/hcal-discovery-bw-copy0000-default-f3c9e5f807ca05bf.manifest.json \
  --printer hp-m281 --print-path raw9100 --media white-90gsm-a4 \
  --scanner canon-4800 --scan-mode grey-no-auto \
  --print-session 2026-08-04-A
```

Exact analyzer stdout (exit 0; stderr empty):

```json
{
  "status": "ok",
  "report": "scratch/e028-m281-20260804-reports/hcal-report-discovery-bw-copy0000-adcffb16d31d279b.json",
  "refusal": null,
  "highest_useful_authored_grid_dpi": [
    600,
    600
  ]
}
```

Report: 2,204,544 bytes; file SHA-256
`458587be07c3c6a4295cc140b68790fb46695f84191151a4f17d2e0c920ef1c0`;
report semantic SHA-256
`adcffb16d31d279bfb87cc198f5234f94d429985076ccbee6b86daed2d06ae91`.
The v3 report passed `verify_analysis_report` unchanged.

### Integrity, identity, and device readback

- Both HCAL-R1 strips passed magic and CRC with zero repairs/errors; 2/2 valid
  placements agreed on one payload.  Identity is discovery/B&W/copy 0/default
  and matches the corrected `r1` manifest.
- Live device: `HP Color LaserJet MFP M281fdw`, LanguageLevel 3, version
  `3017`, revision 1; default and effective resolution both 600 x 600;
  595 x 842 pt, simplex/no tumble, `DeviceRGB`.  Serial and ImagingBBox were
  unavailable.  Stable device-footing digest:
  `73d115359642ddb57c76319fd18a4898434f9da65f1ba808f66202af433731f3`.
- Paper/end-sentinel density separation is 0.60468; all six paper witnesses
  are visible and clean.

### Geometry and authored-grid decision

- Orientation `r0`, not mirrored; rotation 0.3025 degrees and shear 0.02869
  degrees.  Measured scale is nominal: x 1.000600, y 1.000893 (about +0.060%
  and +0.089%).
- Four corners and all 10 internal plus marks were found.  Corner-fit RMS is
  2.128 layout dots; internal residual RMS/max are 2.540/3.212 dots.  Local
  field certification remains the authority for candidate rows.
- The 300 and 600 authored grids are usable.  The 1200, 1200x2400, and 2400
  grids are not addressable.  Highest useful authored grid: **600 x 600**.
  At 600 the K ruler resolves 2-on/2-off but not 1-on/1-off.

### Binary K candidate decision

The 8% gate applies to both the whole-field and worst-window Wilson upper
bounds.  Selected headline rows:

| Candidate | Tier/result | Whole-field error (95% upper) | Worst window (95% upper) | Information density |
|---|---|---:|---:|---:|
| 600-grid 2x2 (`code 4`) | marginal, **not provisionally usable** | 3.483% (3.702%) | 6.811% (**9.020%**) | 109.24 bit/mm² |
| 600-grid 3x3 (`code 5`) | solid, provisionally usable | 0% (0.0655%) | 0% (1.473%) | 61.99 bit/mm² |
| 600-grid 2x3 (`code 33`) | marginal, provisionally usable | 0.274% (0.4075%) | 1.639% (3.530%) | 90.48 bit/mm² |
| 600-grid 3x2 (`code 34`) | marginal, provisionally usable | 0.269% (0.4002%) | 1.116% (2.586%) | 90.58 bit/mm² |
| 300-grid 1x1 (`code 1`) | marginal, provisionally usable | 2.606% (2.889%) | 5.719% (7.923%) | 115.22 bit/mm² |

The square 600-grid c2 class misses only the conservative local-tail gate; a
clean page average must not hide that 9.02% upper bound.  The rectangular
2x3/3x2 controls are the dense 600-grid survivors, with 3x2 slightly better on
this copy.  Square 3x3 is the robust result.  K3 multilevel at 3x3 is fragile
(11.33% worst field; 19.95% worst-window upper), and K4 is unmeasurable.

The current automatic calibration shortlist, in rank/order, is:

`(1, 34, 33, 5, 2, 6, 19, 3)`

That is a candidate set for replicated calibration, not a recommendation.
Higher-authored-grid rows with equal physical pitch are excluded because their
grid rulers are not addressable.

### Scanner adequacy and claim boundary

The report-level status is `ok`, meaning the page was identified and measured;
it does **not** mean the scanner footing passed.  Scanner adequacy is complete
but `inadequate` for both solid and c2 classes:

- identity and both sampling axes pass (correlation 0.7828 horizontal, 0.6787
  vertical);
- the solid/c3 transfer block fails at 11.91% vs the exclusive 5% limit;
- the marginal/c2 block narrowly passes its pattern limit at 17.65% vs 18%;
- the compression/smoothing check fails: quiet high-pass noise is 0.853
  8-bit counts vs the required >=1.0 (the file itself is uncompressed), while
  entropy blockiness 1.004 is below the 1.25 ceiling.

Therefore this scan can nominate calibration candidates and records the
combined current printer/scanner/low-toner footing, but it does not cleanly
separate printer failure from capture-footing failure and cannot qualify the
printer, promote a registry row, or establish production receiver margins.
The exact `scanimage` command confirms that no application-side processing
step caused this verdict; it does not supersede the measured adequacy gate.

### Tone, morphology, transport, and margins

- K tone is monotonic with zero violations, coverage-density correlation
  0.98824, and density dynamic range 0.66482.  This is specifically the old,
  low-toner cartridge state.
- One-dot structure is effectively collapsed: the 1-dot checker is 48.96%
  error and isolated 1-dot density separation is only 0.0042.  The 2-dot
  checker is still 18.50% error.  Strong anisotropy remains: 2-dot horizontal
  lines are 11.89% error versus 2.37% for vertical lines.
- Both transport rails are valid.  X phase span/RMS are 1.137/0.178 source
  dots; Y is substantially larger at 3.964/0.705 source dots.
- No payload-safe rectangle or capacity bounds were derived; every payload
  edge has `safe_gap_mm: null`.  Physical ink ticks are a separate diagnostic
  and must not be substituted for a payload margin.

## Capture 028.1b — Canon color discovery scan

The incoming `scratch/2.tiff` was monitored until its byte size and mtime had
remained unchanged for 60 seconds, structurally inspected, and renamed to:

`scratch/e028-m281-20260804-color-01-canon-4800rgb.tiff`

- 6,875,455,728 bytes; capture SHA-256
  `d0f12451dfc16d06ce904a2bad324e7d1f2b30d6096d558168d1064bdc7aeb8d`.
- One 40,832 x 56,128 RGB image at 4800 x 4800 dpi, 8 bits/channel,
  uncompressed chunky layout, one contiguous full-height strip, top-left
  orientation.  The first and last pixels are readable through the same
  memory-mapped path used by the analyzer.
- `scanimage` emitted a nonconforming big-endian ClassicTIFF for this >4-GiB
  pixel payload.  Its `StripByteCounts` LONG is 2,580,488,192, exactly the
  correct 6,875,455,488 pixel bytes modulo 2^32.  The file length is exactly
  the 240-byte data offset plus the full expected pixel payload, with neither
  missing nor trailing bytes.  `tifffile` and libtiff both recover the
  contiguous full raster; preserve this original capture/hash, and use a
  separate BigTIFF derivative if broad reader compatibility is later needed.
- Analyzer footing: `hp-m281`, `raw9100`, `white-90gsm-a4`, `canon-4800`,
  `color-no-auto`, session `2026-08-04-A`.  The exact operator capture command
  has not yet been recorded for this color scan; the TIFF independently
  establishes RGB, 4800 dpi, and no file compression, but not every backend
  option represented by the human footing label.

Exact command:

```sh
env/bin/python confetti.py discover analyze \
  scratch/e028-m281-20260804-color-01-canon-4800rgb.tiff \
  scratch/e028-m281-20260804-reports --scan-dpi 4800 \
  --manifest scratch/discovery-m281-0804-r1/hcal-discovery-color-copy0000-default-6995a5d0b5b0218d.manifest.json \
  --printer hp-m281 --print-path raw9100 --media white-90gsm-a4 \
  --scanner canon-4800 --scan-mode color-no-auto \
  --print-session 2026-08-04-A
```

Exact analyzer stdout (exit 0; stderr empty):

```json
{
  "status": "ok",
  "report": "scratch/e028-m281-20260804-reports/hcal-report-discovery-color-copy0000-2b9fd82615a7fc5d.json",
  "refusal": null,
  "highest_useful_authored_grid_dpi": [
    600,
    600
  ]
}
```

Report: 2,740,889 bytes; file SHA-256
`3a039a768380857e8be1d01289cf1312131b4630b7656834d88abaf739c6434c`;
report semantic SHA-256
`2b9fd82615a7fc5df0517b20974ad62c2330c6a20b71be9441048e8154f46114`.
The v3 report passed `verify_analysis_report` unchanged.

### Color integrity, geometry, and authored-grid decision

- Both HCAL-R1 strips passed magic and CRC with zero repairs/errors; 2/2
  placements agreed on the color/copy-0/default identity and corrected color
  manifest.  The live device footing exactly matches the B/W sheet, including
  digest `73d115359642ddb57c76319fd18a4898434f9da65f1ba808f66202af433731f3`.
- Orientation is `r0`, not mirrored; rotation 0.12088 degrees and shear
  0.02425 degrees.  Measured scale is x 1.000238, y 1.001275.  All 10 internal
  plus marks are present; residual RMS/max are 2.932/5.305 layout dots.
- The 300 and 600 authored grids are usable; 1200, 1200x2400, and 2400 are not
  addressable.  At 600, all K/C/M/Y rulers resolve 2-on/2-off but not
  1-on/1-off.  Highest useful authored grid is **600 x 600**.
- Both transport rails are valid.  X phase span/RMS are 1.112/0.243 source
  dots; Y is much larger at 6.004/1.635 source dots.

### Color candidate decision

The current 600-grid headline rows are:

| Candidate | Result | Whole-field error (95% upper) | Worst window (95% upper) | Information density |
|---|---|---:|---:|---:|
| pure M c3 (`code 39`) | solid, provisional | 0% (0.106%) | 0% (1.368%) | 62.00 bit/mm² |
| pure Y c3 (`code 40`) | marginal, provisional | 0.566% (0.873%) | 1.404% (3.553%) | 58.87 bit/mm² |
| pure C c3 (`code 38`) | unmeasurable | geometry uncertified | geometry uncertified | none |
| pure M c2 stress (`code 52`) | marginal, provisional | 2.748% (3.126%) | 4.604% (6.428%) | 114.22 bit/mm² |
| pure C c2 stress (`code 51`) | fragile, not provisional | 5.524% (6.043%) | 8.243% (10.624%) | 96.53 bit/mm² |
| pure Y c2 stress (`code 53`) | fragile, not provisional | 13.209% (13.966%) | 15.932% (18.821%) | 62.18 bit/mm² |
| direct CM4 c3 (`code 63`) | marginal, provisional | 2.295% (2.829%) | 4.192% (6.912%) | 114.83 bit/mm² |
| direct CMY7 c3 (`code 64`) | fragile, not provisional | 9.631% (10.638%) | 13.245% (17.534%) | 140.16 bit/mm² |
| direct CMY8 c3 (`code 65`) | fragile, not provisional | 12.156% (13.259%) | 17.770% (22.609%) | 142.02 bit/mm² |

The c2 CMY7/CMY8 fields and the sequential-overprint c3 CMY7/CMY8 controls
are geometry-uncertified.  This copy supports provisional two-plane CM4 and
some single-plane modes; it does **not** support a three-plane CMY payload
claim.  This is not merely a 600-grid exclusion: the best measured CMY7 row,
300-grid 2x2 `code 58`, has 3.472% whole-field error (4.357% upper) but a
6.452% worst window whose 11.468% upper fails the 8% local-tail gate.  The
corresponding CMY8 `code 59` has a 15.846% worst-window upper.  The automatic
calibration shortlist is
`(63, 57, 52, 40, 35, 39, 36, 37)`; it is a nomination, not promotion, and
includes 300-grid controls to preserve the grid question.

### Tone, registration, selectivity, and screening

- All K/C/M/Y tone series are monotonic with zero violations.  Dynamic range
  is K 0.6561, C 0.6428, M 0.5199, and Y only 0.3508; correlations are
  0.9928, 0.9886, 0.9930, and 0.9727 respectively.  Yellow is the weakest
  radiometric plane on this old/low-toner footing.
- All nine registration targets are complete.  The worst plane offset from K
  is 229.69 micrometres, driven by a local Y offset; registration is spatially
  variable rather than one constant global shift.
- C/M/Y selectivity probes pass descriptively.  Intended-minus-worst-other
  density is C 0.4544, M 0.2555, Y 0.3503.
- All four matched screening controls are complete and resolved.  The report
  contains path- and content-matched spectral deltas, but correctly limits
  them to descriptive single-copy evidence requiring repeat prints before
  mechanism attribution.

### Color scanner adequacy, margins, and claim boundary

Scanner adequacy is complete but `inadequate` for both solid and c2 classes:

- both sampling-axis correlations pass the minimum (0.5694 horizontal,
  0.6654 vertical);
- the c3 transfer block fails at 15.18% vs the exclusive 5% limit;
- the c2 transfer block fails at 20.0% vs the exclusive 18% limit;
- the smoothing/compression-content gate fails: quiet high-pass noise is
  0.662 8-bit counts vs the required >=1.0, while entropy blockiness 1.002 is
  below the 1.25 ceiling.  The TIFF itself is uncompressed.

No payload-safe rectangle or capacity bound is established.  The discovery
edge arms are direct CMY7 c2/c3; neither exact interior reference is
provisionally usable, and many local fields are geometry-uncertified.  The
separately scored physical-ink ladder certifies 5 mm on top/left/bottom but is
nonmonotonic on the right (5/6 mm pass, 8/10 mm fail); it is not a payload
margin and cannot be substituted for one.

The report-level `status: ok` means the page was identified and measured.
Its explicit `production_receiver_claim: false`, inadequate scanner footing,
single low-toner copy, incomplete local geometry, absent payload rectangle,
and failed CMY7/CMY8 rows prevent printer-profile or production color
promotion.

## Remaining capture work

- The Canon B/W and RGB discovery captures are now both analyzed.  Record the
  exact color `scanimage` command when available.
- Canon reference capture remains full A4 at true DPI with the white lid and
  auto-crop, geometric correction, sharpening, despeckle, and adaptive
  contrast disabled.  **Protocol addition (028.2): inset the page ~5 mm from
  the platen origin on both axes so all four paper edges land in-frame with
  visible background** — this makes the print-to-paper registration directly
  measurable and the small-gap edge probes observable.
- HP flatbed/ADF captures, if later authorized, are separate scanner footings
  and must not be merged with Canon evidence.

## 028.2 — Forensic addendum (2026-08-04 afternoon session): ink-ladder
## verdicts retracted; true margins measured; feed skew; focus check

Same-day forensic pass over the B/W capture, triggered by the operator's
ruler contradicting the report ("legible marks out to 3 mm on one side,
6 mm on the other" vs a 10 mm ladder verdict).  All numbers below are
direct pixel measurements on
`e028-m281-20260804-bw-01-canon-4800gray.tiff` against the report's
corner-fit affine and the r1 manifest geometry; crops for eyeballing are
in `scratch/e028-hand-margin/` (operator-confirmed).  Fix campaign:
**docs/CHARACTERIZE-WORKPLAN.md** (this section is its W0).

### Retraction: physical-ink ladder verdicts (both reports)

The per-tick verdicts in `physical_ink_extent` are REGISTRATION
ARTIFACTS, not ink measurements.  The rule
(`solid_density_p05 >= paper + 0.05`) demands the brightest 5% of the
exact 28-dot window be ink, i.e. tolerates ~1.4 dots of displacement,
while the true tick displacements are 1–3 dots (print wander + affine
extrapolation at page extremes; plus-mark residuals reach 3.2 dots).
Measured truth table (B/W, ink fraction in the nominal 28-dot window /
best window within ±10 dots):

- gaps ≤3 mm: 0% ink everywhere — genuinely unprinted (correct fails);
- 3.5 mm: 33–38% — partially printed (clipped at the margin boundary);
- 4 mm: 65–75% / 74–81% — printed, still edge-clipped;
- 5, 6, 8, 10 mm: 82–92% / **96.7–99.5%** — fully printed on every edge.
  The analyzer failed 12 of these 16 solid ticks; the four passes cleared
  the 0.0885 density bar by as little as 0.0005 (alignment luck).

The B/W "safe_gap 10 mm / left None" ladder and the color sheet's
right-edge nonmonotonicity are hereby RETRACTED as verdicts; the color
right-edge 8/10 mm ticks are to be re-examined after the W1 fix (if
still absent after registration, that becomes a real finding).

### Measured true print margin (B/W sheet)

First ink from the physical page edge, dense profile along each edge:
top 4.14 mm / bottom 4.15 mm / left 4.13 mm / right 4.28 mm (median
onset along the edges 6.5–7.0 mm — most edge run-length has no content
until the 5 mm canary fields).  This matches the historical M281
margin fact (007.6: ticks survive to 4 mm) and the operator's ruler.
The payload edge canaries corroborate: at 5/6.5/8/10 mm the c3 robust
arms read 1.5–1.8% Wilson upper on all four edges (c2 stress arms
2–7%, with two real 5 mm tail readings: left 9.03%, right 19.1%);
the ≤3.5 mm arms are `geometry_uncertified` precisely because the ink
stops at the clip line.

### Why the payload rectangle was refused (mechanism, not retraction)

Every gap failed on `exact_references_ok`: the rule ANDs BOTH arms'
interior references, and the c2 stress arm's interior reference
(candidate 4, 600-c2) misses the 8% worst-window gate at 9.02% —
whole-field 3.48% (3.70% upper).  One interior tail therefore vetoed
the whole page's margin product, including the c3-only claim the data
supports.  Note the equal-pitch context: candidate 4's 84.7 µm twins
(300-c1 / 1200-c4 / 2400-c8) read 2.61–3.48% whole-field,
`equivalent-within-1pct`, and 300-c1's worst window (7.92% upper)
straddles the same 8% gate from below — the usable/not-usable flip
between physical twins is gate-straddling position variance.  Per the
2026-08-04 ruling, the verdict layer is deleted by the workplan (W3):
the print margin is the measured clip line; the canary ladder is data.

### Print-to-paper registration (new engine fact) and capture geometry

Using the visible bottom paper edge (shadow line) as physical
reference: the paper sits flush on the platen (tilt 0.05°; top edge at
or ≤0.4 mm above the scan frame — the scan's first rows are paper
across the full width, no background visible), while the printed
content is rotated 0.30° in the scan ⇒ **content is skewed
~0.25–0.3° on the sheet, left side ~1.2 mm up, pivoting near the
right edge** (top-left: content extends ~1.26 mm above the paper edge,
i.e. off-paper; top-right ~0; bottom-left content sits 1.17 mm above
the paper's bottom edge; bottom-right ~0.05 mm).  Single impression —
print-to-print variance unknown.  The top ticks' `unobservable`
verdicts remain correct in effect (their printed positions are
off-raster/off-paper at that corner).  An earlier same-day claim that
"the page hangs ~1.5 mm off the top of the scan frame" is corrected by
this measurement: the −292 px was the printed layout frame, not the
paper.

### Capture sharpness check (operator question: "hazy in Preview")

Edge-spread 10–90% rise across fully printed tick edges: 95–129 µm
(2.2–3.0 printer dots), uniform across all four page corners and both
axes ⇒ the page is in focus; the file is genuinely soft relative to
its 4800 dpi pixel grid (true optical response ~1200–1600 dpi class —
consistent with decimate-first being the measured-best Canon footing),
and paper fiber texture is crisply resolved.  Quiet-zone high-pass
noise ~1 8-bit count corroborates a smoothed capture chain.  macOS
Preview's proxy rendering adds display-side mush; no defocus problem
exists, and nothing here threatens 600 dpi decode.

## 028.3 — Analyzer v4 re-analysis (same evening; workplan W1–W6 landed)

The CHARACTERIZE-WORKPLAN campaign executed same-day: report schema v4
re-analyzed BOTH existing captures (no reprint; reports in
`scratch/e028-m281-20260804-reports-v4/`).  Regression bars all PASS:

- **Measurement layer byte-unchanged**: candidate whole-field errors and
  payload arm Wilson uppers identical to the v3 reports on both sheets —
  only the verdict/aggregation layer moved.
- **Print margin (registered ticks, layout frame)**: B/W clip
  left 4.19 / top 4.25 / bottom 4.25 / right 4.28 mm — hand-measured
  truth 4.13/4.14/4.15/4.28 (within 0.11 mm).  Color sheet:
  left 4.17 / top 4.25 / bottom 4.19 / right 4.25 mm.  Ladders read the
  physical truth on every edge of both sheets: ≤3 mm absent, 3.5 and
  4 mm partial, 5–10 mm full — **the 028.1 ladder verdicts (B/W "10 mm",
  color right-edge nonmonotonicity) are confirmed registration
  artifacts; the color 8/10 mm right ticks are fully printed.**
- **Payload edge curves**: c3 robust arms at interior level from 5 mm on
  three B/W edges (one 8 mm straggler), c2 stress arms carry real 5 mm
  tails on left/right (9.03%/19.1% uppers) — data, no verdicts.
- **Capacity at the measured clip (4.3 mm margins)**: ~6.7 Mbit
  info-bound at the 84.7 µm K channel, ~5.3 Mbit at 3×2 — the numbers
  the deleted rectangle never produced.
- **Registration map**: 38 (B/W) / 46 (color) aperiodic observations,
  max 3.6 / 5.3 dots — the supervised displacement evidence the old
  p05 tick rule was implicitly sensitive to.
- **Paper edges**: only the right edge is solidly detected (ample
  background; paper's right edge measured ~0.9 mm inside the virtual
  layout frame edge = cut width/placement, mild ~0.15° tilt);
  bottom is sparse (frame-end glow/vignette rejected by the
  sustained-background gate), left/top honestly not-visible — the page
  sat flush at the platen origin (see the 028.2 inset protocol).  **Caveat on the 028.2 feed-skew numbers**: the bottom
  shadow rows used at x ≤ 21 mm sat within 3–6 px of the raster end and
  were plausibly the frame-end darkening, not the paper edge; the
  content-vs-paper *rotation* (~0.25°, content 0.30° in-scan vs paper
  ~0.05–0.15°) stands on the uncontaminated right-side evidence, but the
  ~1.2 mm translation estimate is downgraded to indicative.  The v4
  right-edge measurement places the paper's right edge ~0.8–1.4 mm
  inside the virtual layout frame edge (paper cut width/placement),
  which also means clip-line distances measured from the layout frame
  understate nothing but are not paper-edge-referenced on this
  impression.  A properly inset capture resolves all of this directly.
- The equal-pitch shortlist now collapses twins: B/W heads with the
  84.7 µm club (rep 300-c1, members 300-c1/600-c2/1200-c4/2400-c8,
  position spread 0.9 pp, flagged as straddling the 8% gate).

Suite at landing: full `tests/holo` 989 passed / 37 skipped, including
the new margins fixture battery and the two updated slow synthetic
round-trips.

## 028.4 — Canon 4800 knife-edge (zero print): the owed optical MTF item

Operator laid a snap-off utility blade on the platen (~29° slant — ideal
for the super-resolved slanted-edge method) and scanned 4800 dpi grey:
`scratch/canon-4800-knife-edge-20260804-gray.tiff` (33,214,944 bytes,
sha256 `58a3ceb1e52b…`, 9872×16320 LZW grey; note the LZW suggests an
app in the save path — footing caveat, but the numbers cross-check
against the paper-scan g2 data below).  Edge-spread measured by
normal-projected 0.1-px binning over ~2,200 columns per edge:

**Geometry correction (operator re-read, same evening — the first
interpretation's height ladder is RETRACTED):** the blade lies on its
flat face, so the dark body in the crops is steel IN CONTACT with the
glass (the focus plane, grinding striations resolved); the lighter
stripe along the cutting side is the underside taper lifting off the
glass; the bright line is the apex itself (elevated, with light piping
underneath); and the spine-side transition is contaminated by the cast
shadow of the ~0.4 mm wall.  The 55→81→106 µm progression therefore
mixes apex elevation, a physically-gradual grind-start tangent, and
shadow penumbra — **the "+25 µm per 0.25 mm CIS depth-of-field"
quantification is withdrawn** (the qualitative statement that elevated
features read softer stands, unquantified).

Corrected glass-level evidence — the snap-score grooves on the flush
face (operator's suggestion; true in-focus targets):

| feature | height | measurement |
|---|---|---|
| snap-score groove, narrowest | 0 (flush face) | **FWHM 9.5 px = 50 µm** (upper bound on the LSF; physical groove width unknown) |
| score groove flank, cleanest | 0 | 10–90 rise ≈ 7 px = **37 µm** (low contrast, −6 counts — noisy) |
| apex line (white→taper) | slightly elevated | 10–90 rise 10.3 px = 55 µm |

Findings (corrected):

- **Canon glass-level edge response ≈ 40–55 µm 10–90 rise; MTF50 of
  order 9–14 lp/mm, MTF10 ≈ 17 lp/mm** (padded-FFT; the first FFT
  attempt was frequency-quantization garbage, retracted in-session).
  17 lp/mm ≈ an ~860-dpi-Nyquist information ceiling — the measured
  decimate-to-1600 doctrine has its optical explanation, and nominal
  4800 is ~5.6× oversampled per axis.
- **Cross-check against the printed sheet**: implied MTF at the g2
  grating frequency (5.9 lp/mm) is ~0.6–0.75 vs the measured g2
  correlations 0.68/0.78 — consistent.
- **Toner-vs-scanner decomposition** of the printed 95–129 µm edge
  rises: scanner ~45 µm ⇒ toner-only ≈ √(110²−45²) ≈ **100 µm ≈ 2.4
  printer dots — the print, not the scanner, owns the printed edge
  softness** (RET/satellite/development).
- A specular halo (~+20 counts) rides the apex line (light piping
  under the lifted edge) — physical, not scanner flare.
- Background (white lid) high-pass noise 0.32 counts vs ~0.9 on paper
  quiet zones: most "quiet-zone noise" on sheets is paper texture, not
  sensor noise — sharpening the reading of the adequacy smoothing gate.

Crops: `scratch/e028-hand-margin/blade-{overview,spine-native,cutting-native,score-native}.png`
(the score crop resolves speckle inside the groove — an in-focus
sanity check).

### Strip payloads (for the record)

Both strips per sheet decode to identical 160-byte HCAL-R1 payloads:
discovery/bw/copy-0/default and discovery/color/copy-0/default,
layout digests cbcab84f… / af63bd28…, availability 0b1011111101111
(serial + ImagingBBox refused by the printer), LanguageLevel 3,
600×600 default and effective, 595×842 pt, simplex, DeviceRGB,
product "HP Color LaserJet MFP M281fdw", version "3017    " (printer's
own padding), revision 1, print nonces 1,778,767,580 / 1,778,804,933
(37.35 s apart = the interpretation gap between the two jobs),
CRC-16 0xBEED / 0xDA83.
