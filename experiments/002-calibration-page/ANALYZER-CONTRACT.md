# ANALYZER-CONTRACT — cal_core.py (experiment 002, FROZEN)

Contract between `cal_core.py` (the analyzer foundation) and the five family
analyzers (`structural`, `density_color`, `modulation`, `transport`, `meta`),
which are developed in parallel against this document. Everything below is
frozen: signatures, return shapes, coordinate conventions, report keys.
If a family needs something the core does not provide, it extends its OWN file
— it does not change cal_core signatures.

Proven on the real CAL-1 scans (HP CLJ M281fdw print, 1200 dpi flatbed):

| scan | sha256 (prefix) | orientation | px/dot x,y | rot | landmarks | resid RMS (dots) | max |
|---|---|---|---|---|---|---|---|
| `scans/test-scan-calpage-bw.png` (grey) | `aa1dff262688` | upright, no mirror | 2.00014, 2.00279 | 0.361° | 17/17 | 1.79 (corners+plus 2.05) | 3.29 |
| `scans/test-scan-calpage-color.png` (color) | `2bbb87042851` | upright, no mirror | 2.00014, 2.00726 | 0.361° | 17/17 | 1.90 (corners+plus 2.18) | 3.63 |

The 3.3–3.6-dot maxima are three plus marks in one page row (y≈177 mm) moving
coherently by +3.5 dots in y with lock quality q≈0.9 — real transport warp
(001-class), not misregistration. **Treat the global affine as good to ~2 dots
RMS, ~4 dots worst-case; every fine measurement must use the per-patch local
lock (`patch_view`) or the dense-warp decoder (`decode_patch`).**

## 0. Environment and imports

```python
import sys
sys.path.insert(0, "experiments/002-calibration-page")
import cal_core as cc
```

- Python: `env/bin/python` (numpy/scipy/PIL).
- `cal_core` sets `PIL.Image.MAX_IMAGE_PIXELS = None` and inserts both its own
  directory (for `gen_calpage` builders) and
  `experiments/001-engine-characterization` (for `scanlab`) into `sys.path`.
- Re-exports of proven experiment-001 primitives — import them FROM cal_core:
  `cc.xcorr_offset`, `cc.level_fields`, `cc.fit_gmm_z`, `cc.llr_field`,
  `cc.residual_y_profile`, `cc.detect_steps` (see scanlab.py docstrings).
- cal_core uses no randomness. If your family needs any, it must flow from
  `paperholo.modulation.rng(seed, label)` (CLAUDE.md).
- Constants: `cc.SCAN_DPI = 1200`, `cc.HW_DPI = 600`, `cc.PX_PER_DOT = 2.0`
  (nominal — the measured value is in the registration report),
  `cc.BUILD` (build dir), `cc.MANIFEST_PATH`.

## 1. Coordinate conventions (normative)

- **layout dots**: the 600-dpi generator grid of `build/calpage_manifest.json`.
  Origin = page top-left, x right, y down. All manifest
  `x_dots/y_dots/w_dots/h_dots` are in this frame.
- **scan px**: pixel coordinates of the ORIENTED scan arrays (after
  `register()` has rot90/mirrored them upright), x right, y down, array
  indexing `[y, x]`.
- **affine** `coef = np.ndarray([a, b, c, d, e, f])`:
  `sx = a*x + b*y + c`, `sy = d*x + e*y + f` (layout dots → scan px; scanlab
  convention). Helpers: `cc.affine_apply(coef, xy_dots)`,
  `cc.affine_invert(coef)`, `cc.affine_stats(coef)`.
- **resampled rasters** (`warp_channel`, `PatchView.channels`): pixel `[i, j]`
  samples layout position `(x0_dots + j/sub, y0_dots + i/sub)` — corner-
  aligned, exactly like `scanlab.warp_dots`. `sub` = samples per dot
  (default 2).
- **Ink is DARK** (low values) in every channel, every raster, every scan.
- Cell-grid arrays (GT cells, `cell_means`) are indexed `[cell_row, cell_col]`
  = `[y, x]`; cell (r, c) covers layout dots
  `[y0 + r*cell, y0 + (r+1)*cell) x [x0 + c*cell, ...)`.

## 2. Scan loading

```python
scan = cc.load_scan(path, *, compute_sha256: bool = True) -> dict
```

Keys: `path` str, `sha256` str|None, `kind` `'grey'|'color'`,
`grey` float32 (H,W), `channels` dict — `{'grey': <same array>}` plus
`{'r','g','b': uint8 (H,W)}` for color scans, `white/black/thresh` robust grey
levels (p90/p1/midpoint), `scan_dpi=1200`, `hw_dpi=600`, `px_per_dot=2.0`.
After `register()`: `orientation`, `affine`, `registration`, `manifest`.

**Rule: K geometry is measured on the grey scan; C, M, Y (and all color
measurements) on the color scan channels** — Y is near-invisible in grey.
Channel↔plane mapping: `cc.REG_CHANNEL_FOR_PLANE = {'K':'grey','C':'r','M':'g','Y':'b'}`,
resolved per entry by `cc.reg_channel_for(scan, entry)`.

Worked example (real):
```python
scan = cc.load_scan("scans/test-scan-calpage-color.png")
# scan['kind']=='color', scan['grey'].shape==(14028, 9920), sha256 2bbb8704...
```

## 3. Registration

```python
manifest = cc.load_manifest()                    # default MANIFEST_PATH
e        = cc.entry(manifest, "K/encode_c3")     # patch OR infrastructure, KeyError if absent
reg      = cc.register(scan, manifest=None, *, refine=True, use_quads=True) -> dict
```

`register` finds the 4 chiral corner marks (satellite counts 1/2/3/4 =
TL/TR/BR/BL) on a ×4 downsample, resolves rotation/mirror (brute-forces the 8
hypotheses if the page is not upright), physically reorients the scan arrays
(`scan['channels']` are replaced; orientation op = fliplr-if-mirrored, then
`np.rot90(k)`), fits the affine from corner blob centers, then refines it with
template xcorr on 17 K-plane landmarks (4 corner marks + 8 plus marks + 5 K
reg-quads; templates rebuilt byte-identically from `gen_calpage`). Rulers are
a cross-check only, never in the fit. Raises `cc.RegistrationError` if <3
corners or <6 landmarks lock — in that case NO downstream number is valid.

Report dict (also `scan['registration']`): `orientation`
`{'rot90_ccw': int, 'mirrored': bool}`, `corners_found`
(n_sat/x_px/y_px/inward), `inward_diagonals_match` bool,
`corner_blob_fit_rms_px`, `affine` [a..f], `px_per_dot_x/y`, `rotation_deg`,
`shear_deg`, `mirrored`, `n_landmarks_used/total`, `residual_rms_dots`
(all landmarks), `residual_rms_core_dots` (corners+plus — the <3-dot
acceptance gate), `residual_max_dots`, `landmarks` (per-landmark
name/class/dx/dy/q/ok/resid_dots), `ruler_check`
`{'top_baseline_dy_dots','left_baseline_dx_dots'}`.

Worked example (real, color scan): `residual_rms_dots=1.903`,
`residual_rms_core_dots=2.183`, ruler check (+0.26, −0.49) dots; orientation
recovery was verified by feeding rot90/rot180/mirrored copies of the real bw
scan — all recovered to the identical 1.789-dot RMS solution.

The global affine is K-referenced. C/M/Y planes carry their own engine
misregistration on top (measured example: `M/encode_c3` locks at dy=+2.49
dots) — per-plane offsets are a measurement (transport family, reg quads), not
a registration error.

## 4. Patch views — families never hand-roll resampling

```python
v = cc.patch_view(scan, entry_or_name, *,
                  margin_dots=8, sub=2,
                  local="auto",            # 'auto'|'gt'|'footprint'|'none'
                  channel="auto",          # 'grey'|'r'|'g'|'b' or auto-by-plane
                  template_dots=None,      # custom ink=1 dot bitmap, patch-sized
                  max_shift_dots=8.0, min_quality=0.2) -> cc.PatchView
```

`PatchView` fields: `name`, `entry` (manifest dict), `x0_dots/y0_dots`
(= entry origin − margin), `w_dots/h_dots` (incl. 2×margin), `margin_dots`,
`sub`, `channels` dict (float32 rasters: `grey` always; `r,g,b` on color
scans), `reg_channel`, `local_mode` `'gt'|'template'|'footprint'|'none'`,
`local_offset_dots` `(dy, dx)`, `local_quality` float|None, `local_locked`
bool, `affine`. Methods: `v.img(channel=None)` (registration channel by
default), `v.crop(channel=None)` (margin stripped, exactly
`entry.h_dots*sub × entry.w_dots*sub`).

Semantics: the local offset is measured by GT/template xcorr in the
registration channel, then ALL channels are resampled WITH the offset applied
— **a locked raster already sits on the nominal dot grid; do not shift
again.** `local_locked=False` ⇒ offset NOT applied, raster is global-affine
only; treat fine geometry as ±2 dots.

`local='auto'` policy: GT/nominal-bits template for aperiodic ground-truthed
kinds; patch **footprint** (solid rectangle) for periodic kinds
(`cc.PERIODIC_KINDS`: lines, checker, dots, holes, nyquist_comb,
dot_grid_1dot, lines_1dot, phase_pair, phase_grating,
raster_probe_imagemask — GT xcorr would lock a wrong period multiple) and for
footprint-only kinds (`cc.FOOTPRINT_KINDS`: solid, overlay_solid,
contone_setgray, raster_probe_rectfill); none for blank/print-time infra
(quiet_zone, machine_strip, ruler, text_block, end_sentinel).

Quality calibration (measured on the real scans): true GT locks q=0.53–0.98;
deliberately wrong (16-dot-rolled) GT template q=0.10–0.16 (footprint-driven
floor); dead/blank content q≈0.05 (`dotgrid1_Y` → unlocked, correct).
`min_quality=0.2` separates these. Lower it deliberately for sparse patterns
and say so in your family report.

Worked examples (real, color scan):
```python
v = cc.patch_view(scan, "K/encode_c3")
# v.local_mode='gt', v.local_locked=True, offset=(-1.39,-0.06), q=0.709
v = cc.patch_view(scan, "Y_encode_c3")
# v.reg_channel='b', locked=True, q=0.733 (blue channel — Y invisible in grey)
v = cc.patch_view(scan, "K/solid")     # footprint lock, q=0.944
```

Low-level resampler (only when a rect is not a manifest entry, e.g. ruler
segments, strip rows):
```python
a = cc.warp_channel(scan, channel, x0_dots, y0_dots, w_dots, h_dots, *,
                    coef=None, sub=2, offset_dots=(0.0, 0.0)) -> float32 array
```

Cell aggregation:
```python
m = cc.cell_means(view, cell_dots=None, channel=None) -> float32 (ny, nx)
# cell_dots defaults to entry.params['cell_dots']; trailing partial cells dropped
```

**BER measurements MUST use `decode_patch` (dense warp), not naive
`cell_means` thresholding**: on `K/encode_c3` the naive path reads 10.7–11.9%
BER where the v4 decoder reads 4.5% (001 reference: 4.7%). Naive means are
fine for densities/quick looks only.

## 5. Ground truth

```python
gt  = cc.load_gt(entry)          -> uint8 dot bitmap (ink=1) | None    # from entry['gt'] npy
aux = cc.load_gt_named(rel)      -> np.ndarray                         # e.g. params['states_gt']
nb  = cc.nominal_bits(entry)     -> uint8 dot bitmap | None
gc  = cc.gt_cells(entry)         -> uint8 cell bitmap | None           # gt[::cell, ::cell]
```

`nominal_bits` = saved GT if present, else the printed bitmap rebuilt
byte-identically from the `gen_calpage` builders + manifest params (audited:
215/220 patches reconstruct with correct shapes; only `contone_setgray` and
`raster_probe_rectfill` are print-time-only → None). Encoding patches embed
the seed-fixed pilot lattice (`paperholo.pilots.pilot_sites`, block 6,
period 64, seed `paper-store/exp002-calpage`).

## 6. Density / paper white (color scan)

```python
wm = cc.white_model(scan, *, grid_step_dots=24, pad_dots=10, clip_sigma=3.0) -> dict
w  = cc.white_at(wm, x_dots, y_dots, channel)     # vectorized evaluation
d  = cc.density(view, wm, channels=("r","g","b")) -> {channel: float32 D array}
```

`white_model` samples the blank page grid (quiet zone + all patch surrounds;
every manifest patch/infra/label rect padded by `pad_dots` is excluded) and
fits a per-channel 2-D quadratic with sigma clipping. `density` computes
`D = −log10(v / white_local)` per raster pixel (v clipped ≥ 1.0). Pass
`channels=('grey',)` on the grey scan.

Worked example (real, color scan): `n_samples=20950`, fit rms
{r 4.7, g 4.8, b 1.8} counts; median central densities —
K/solid D(r,g,b)=(1.43, 1.27, 1.22); C/solid (1.15, 0.25, 0.11);
M/solid (0.04, 2.40, 0.39); Y/solid (−0.01, 0.02, 0.76). Unmix-ready.

## 7. Decode + null control (the 001.2 discipline)

```python
out = cc.decode_patch(scan, entry_or_name, *, channel="auto",
                      null_shift_cells=8, **decode_kw) -> dict
```

Wraps `scanlab.decode_cells` v4 (dense poly2 warp + step-preserving y-profile
+ blind soft LLR stage; GT used for registration templates and scoring only)
on the plane-appropriate channel, and ALWAYS appends the null control. Output
= scanlab's dict (`ber, errors, cells, clustered, err_map, means, gt_cells,
warp_windows_*, poly_resid_rms_dots`, `soft{gmm, llr, llr_ctx, z, ber_llr,
mi_bits, conf_curve, reliability, ...}`, optional `diag_yprof`/`steps`) plus
`ber_null`, `null_ok`, `channel`. Square ground-truthed patches only
(`banding_K` is non-square → use `patch_view` + row statistics).

Worked example (real, color scan): `K/encode_c3` → BER 4.46% hard, 3.50%
soft, MI 0.851 bits/cell, 50/50 warp windows, `ber_null=0.505`, `null_ok`.

Standalone controls (for family-specific decoders — confusion matrices,
multilevel, strips):
```python
cc.null_control_ber(pred_cells, gt_cells, shift_cells=8) -> float   # must be 0.50±0.02
cc.ber_with_null(pred_cells, gt_cells, shift_cells=8, tol=0.02)
   -> {'ber','n_cells','ber_null','null_ok','shift_cells'}
```

**Every BER/confusion measurement in every family runs a null control and
reports it.** Every canary verdict goes through:
```python
cc.canary_verdict(name, status, statistic, control, note="") -> dict
# status ∈ {'pass','fail','indeterminate'}; never a bare boolean.
```

## 8. Report shape and family namespaces

```python
rep = cc.report_init(scan) -> dict      # after register()
cc.report_merge(rep, payload) -> rep    # recursive; collision on any non-dict
                                        # leaf raises ValueError (disjointness
                                        # is enforced mechanically)
cc.save_report(rep, path)               # numpy-safe JSON
```

Skeleton (channel-measurement panel §7 + header):
`scan`, `registration` (filled by core), `engine`, `geometry`,
`channel_params`, `modulation`, `recommendation`, `canaries`,
`families.{structural,density_color,modulation,transport,meta}`.

Ownership (curated keys; raw detail goes under `families/<yours>` — never
write into another family's namespace):

| family | curated keys | canaries |
|---|---|---|
| structural | `channel_params.{psf_sigma_dots, gain_edge_dots, dev_threshold_dots, min_feature_dots}` | D (phase pairs), F (RET/edges) |
| density_color | `channel_params.{tvi, dmax, mottle_sigma, scan_noise_rgb, crosstalk_matrix, cond_number}` | B (contone screen), C (toner save) |
| modulation | `modulation.*`, `recommendation.*` | A (re-screening spectra) |
| transport | `geometry.*`, `channel_params.{banding, transport_steps, warp_rms_dots, plane_offsets}` | E (rescale) |
| meta | `engine.*` (strip decode, header echo) | G (interpreter fingerprint) |

Canary keys: `canaries.<ID>` with the `canary_verdict` dict.

## 9. Known limitations and caveats (read before blaming the channel)

1. Local lock is RIGID (dy,dx). Internal patch warp (≈1 dot across 20 mm,
   steps included) remains — use `decode_patch` for cell-accurate work, or
   `cc.residual_y_profile`/`cc.detect_steps` for transport diagnostics.
2. The affine is K-referenced; C/M/Y `patch_view` offsets contain real
   plane misregistration (M measured at ≈+2.5 dots y). That is signal.
3. `decode_patch` rejects non-square patches; `banding_K` (472×2680 dots) is
   analyzed via `patch_view` row statistics.
4. Periodic kinds get footprint locks (±~0.5 dot on patch boundary); absolute
   phase within the period is the family's own measurement.
5. Grey scan has no `r/g/b` channels; `patch_view` on it registers everything
   against `grey` (Y patches will simply not lock there — expected).
6. The scanner y-scale differs between the two real scans (2.00279 vs
   2.00726 px/dot) — never mix affines across scans; register each scan.
7. `stripdec.py` currently fails on the real scans — strip decode on scan
   data is the meta family's task (use `warp_channel` on the
   `machine_strip_*` infra rects; the printed header echo is the manual
   cross-check, jobid `2b7b26b5`).
8. Memory: color scan ≈ 1.1 GB resident (grey float32 + 3 uint8 channels +
   lazy float32 channel cache used by `decode_patch`). Load one scan per
   process if you run families in parallel.

## 10. Proof-of-foundation runs (reproduce with)

```
env/bin/python experiments/002-calibration-page/cal_core.py \
    scans/test-scan-calpage-bw.png scans/test-scan-calpage-color.png
```

which registers both scans, locks `K/encode_c3` (q≈0.71 vs 0.15 wrong-template
floor), naive-decodes it, and prints the null control (0.503/0.503).
