# The composite pose — printer field ∘ paper pose ∘ scanner field

Version 0.1 — 2026-08-22. Status: DESIGN (INDEPENDENT-PLANES §6 P4), not
built. Records the 2026-08-22 ruling on WHERE (INDEPENDENT-PLANES P3):
the unification is executed in src/holo as a null-proof refactor (the
corpus and instruments are there); holo2 adopts the CONCEPT as doctrine
and, if colour lands holo2-native, designs the composite in from day one.
Governing neighbours: docs/INDEPENDENT-PLANES.md (staging),
docs/PLANE-FIELDS.md (the (a)-field solver that survives into this
design), docs/RECEIVE-DESIGN.md (amendment owed at build).

---

## 1. The idea in one paragraph (user design, 2026-08-22)

Three physical mechanisms stand between "this dot on the ideal page" and
"these scanner pixels in this capture": (a) the printer deforms the
emitted page, per plane, print-frozen — a FIELD over the page; (b) the
paper is stressed, cut, and laid on a platen at some position and
orientation — a POSE per window; (c) the scanner's optics and mechanics
deform what it sees, per channel, fixed to the platen — a FIELD over the
platen. The mapping used to be "the pose" (b alone, with (a) and (c)
silently folded in). It is now ONE composite pose made of the three,
every reader of raw pixels goes through it and nothing else, and every
residual any reader measures is attributed back to the frame whose
invariance class it belongs to. Introduce all three with identity
defaults first; the composite then equals today's pose exactly, which is
the acceptance gate.

---

## 2. The three frames and their invariance classes

The decomposition is right because the invariance classes are different
— and an invariance class IS a pooling rule: evidence pools over exactly
the index set its frame is invariant across.

| frame | what it models | indexed by | invariant across | plane/channel axis | default | durable record |
|---|---|---|---|---|---|---|
| (a) printer field F | toner placement per plane: the AltaLink Y sinusoid (0.83 dot, ~100 mm) and whatever else the engine does | sheet × tile (page space, print dots) × plane | captures, lanes, platen placements | per PLANE (ink: C, M, Y; K = n=1) | identity (Δ=0, A=I) | SheetField (new) |
| (b) paper pose P | paper stress/cut/hygroexpansion + where on the platen, which orientation | capture × window (or subdivided window) | planes | plane-COMMON (measured ×11, §INDEPENDENT-PLANES 2.4) | today's AffinePose | PoseRecord (exists) |
| (c) scanner field S | optics + transport: lateral CA (R−G measured, e033), scale (+0.3–0.6% Canon), y-transport steps (home flatbed) | scanner × platen position × channel | sheets, captures on that scanner | per CHANNEL (sensor: R, G, B; luma for K) | identity (σ=0) | ScannerField (new; needs a scanner id on CaptureFacts) |
| — lane rescale L | exact-rational native↔lane pixel-centre map | lane | everything | none | — | AreaPixelTransform (exists) |

L is NOT a physical frame and stays outside the composite; it is a
coordinate convention.

**Plane vs channel.** (a) is indexed by INK plane; (c) by SENSOR channel.
They are different axes that today's single field would conflate. The
sampler for plane p reads channel ch(p) (C←R, M←G, Y←B; K←luma), so
plane p's sample point is S_{ch(p)} ∘ P ∘ F_p.

---

## 3. The forward composite

Notation: u = a point in ideal page space (print dots, page frame; cells
and tiles are integer lattices on it); v = a point on the physical sheet;
x = native scan pixels on the platen; x' = sensor position per channel;
y = lane pixels.

    v  = F_p(u)   = u + Δ_p(u) + (A_p(u) − I)·(u − u_tile)        (a), per plane
    x  = P_w(v)   = J_w · v + o_w        (rot_k inside J_w)        (b), per window
    x' = S_c(x)   = x + σ_c(x)                                    (c), per channel
    y  = L(x')                                                    lane rescale

    sample point for (window w, plane p, cell u):  y = L(S_{ch(p)}(P_w(F_p(u))))

With identity defaults (Δ ≡ 0, A ≡ I, σ ≡ 0) this is y = L(P_w(u)) —
exactly today's `AffinePose.points()` through the lane transform. That
identity is the NULL PROOF of the whole refactor (§8).

**Consistency with the W2 seam.** `_features_with_page_fraction` applies
a per-plane translation in window-LOCAL dot axes through J:
`points = P_w(u) + J_w·Δ_p`. Since P_w(u + Δ_p) = P_w(u) + J_w·Δ_p, the
existing seam is the translation-only special case of (a)∘(b) composed
in the correct order. It is kept as a behaviour reference, not as code.

**Composition order is fixed by physics**, not convention: (a) acts on
the page before it is paper; (b) acts on paper before it is light; (c)
acts on light before it is pixels. Any other order mis-attributes.

**(a) for K.** With one plane there is no differential; F_K carries only
the optional plane-common component (§4.2). Today: identity. The
K instance question (INDEPENDENT-PLANES §4.J) is whether that component
is ever worth solving — not now.

---

## 4. Representations

### 4.1 (a) — the printer field
A 2-D array over tiles of the page, per plane, each entry a LOCAL AFFINE
(translation Δ in print dots + a 2×2 A), coupled by a smoothness prior.
- **Represent fully, regularize by measured invariance** (user ruling:
  n = 1 printer is no basis for amputating the representation). Data
  model carries six dof per tile per plane; the SOLVER frees translation
  and shrinks A hard toward the plane-common value (sheet I: per-plane A
  deviation is noise-level, sd 0.024% vs 0.274% common). Adoption is
  gated per dof, per plane, per region — identity until evidence.
- **Coupling range.** The measured sinusoid has period ~100 mm = 18.5
  tiles (tile = 128 dots = 5.42 mm at 600 dpi) ⇒ correlation length
  ~4–5 tiles. The dead bands are 3–4 tiles wide, so certified
  neighbours on both sides inform every dead tile; column 8 (page edge,
  one-sided) is the only true extrapolation. Kernel bandwidth follows
  from the shortest period the engine is believed to produce; the
  nonparametric form stays (no basis assumption), the bandwidth is a
  measured prior.
- **Cross-plane coupling: NOT the signed pooled mean.** PLANE-FIELDS
  §6.5.4b (confirmed by review): C/M antisymmetry cancels in the pooled
  mean and Y is shrunk toward ~Y/3. Replace with shrink-to-zero or
  leave-one-out; an uncovered plane gets the natural zero, never another
  plane's field (P1).
- **Differential first, common optional.** Δ_p is defined RELATIVE to
  the plane-common frame — that is what one capture can identify (the
  pilot, regmap and ceiling all measured exactly this). A print-frozen
  plane-common component (page-scale warp the printer itself imposes)
  is only identifiable against (b) with ≥2 differently-placed captures;
  the slot exists, the solver fills it only under that condition (§5).
- Coupling across LANES: same field, different L. Across CAPTURES: same
  field, different P_w. One SheetField per state; every (capture, lane)
  execution reads it and writes to it (the per-lane pass,
  INDEPENDENT-PLANES §4.B).

### 4.2 (b) — the paper pose
Today's AffinePose per window, with rot_k, subdivision where built, the
PoseRecord durability and the hint transport — unchanged in meaning.
Changes: ONE implementation (the four inline re-expansions collapse,
the duplicated page→scan hint affine collapses), and (b) becomes a
WRITER target: plane-common residuals from any reader refine it.

### 4.3 (c) — the scanner field
Per scanner, per channel, over platen coordinates. CA is smooth and
odd-symmetric laterally (e033's R−G control), scale is near-constant:
a low-order polynomial or coarse platen grid per channel suffices.
Default identity. Populated EITHER from characterization (the blue-
channel knife-edge item, INDEPENDENT-PLANES §4.I) OR from a multi-
capture solve under re-placement (§5). Needs: a scanner identity on
CaptureFacts (the state does not record which scanner today).
MEASURED 2026-08-22 (Canon LiDE 400, 4800 dpi, `measure/scanner/`): the
geometric part of (c) is near-identity — per-channel offsets ≤0.005 dot
in x, a constant ~0.03–0.04 dot R−B in y (CIS line timing, inferred),
no platen-position dependence found; B is the sharpest channel. So on
this scanner a single capture's differential field is (a), not (a)+(c).
DESIGN CONSEQUENCE: the printer frame needs a PHOTOMETRIC sibling to
its geometric field — a per-ink PSF (σ Y 51 > K 46 > C 43 > M 25 µm on
the M281 sheet) — which is where Y's 2–3-cell smear lives; that is the
ISI-equalization lever's model, not the scanner's.

---

## 5. Identifiability — what each capture multiplicity can separate

| residual observed | single capture | ≥2 captures, SAME placement | ≥2 captures, RE-PLACED |
|---|---|---|---|
| per-plane, page-correlated | → (a) differential | → (a) differential | → (a) differential |
| plane-common, smooth page-scale | → (b) (absorbs any (a)-common) | → (b) (still confounded) | (a)-common separable from (b): same in page coords, (b) differs |
| per-channel, platen-correlated | → confounded INTO (a) differential | confounded | (c) separable from (a): fixed in platen coords while the page moved |

Consequences: the multi-scan doctrine ("re-place the sheet between
scans") is now ALSO the identifiability doctrine; on a single capture
the (a) differential is (a)+(c) mixed and must be labelled so; the
solver's pooling rules are this table read row by row.

---

## 6. Writers — residual attribution (the genuinely new design)

Every reader that measures a residual reports it in its own frame; the
service attributes it by §5. Today anchors and probes measure at the
plane-common pose and report ABSOLUTE misregistration; after this
design they measure AFTER the composite and report the RESIDUAL, so the
evidence layer can see whether a correction worked.

| reader | measures | frame | attribution | today |
|---|---|---|---|---|
| word solves (address stage) | fine offset of BCH site lattice | window-local, luma | plane-common → (b) refinement; if read per channel (A.2), per-plane → (a) | DISCARDED |
| registration anchors (word/dust) | per-plane NCC offset around known cells | window-local dots, per plane | per-plane residual → (a) differential (weight = NCC quality; dust is a HINT-grade source, ×2.3 overshoot measured) | absolute, at plane-common pose |
| certified probes (W4) | per-plane NCC against re-encoded certified cells | window-local, per plane | → (a) differential; with re-placed captures also (a)-common / (c) | absolute; label-only windows only; 256-site budget |
| closer wins (translation swim) | the offset that CERTIFIED | window-local, per plane | → (a) tier-(i), highest weight (decode-gated truth) | n/a |
| pose refinement (certified_refine / refine_color_window) | plane-common affine improvement | window | → (b) | (b) only, plane-blind sampling |
| region calibration fit | — | — | consumer only (samples through the composite) | fits at plane-common pose |
| cold lane / word scoring | — | cell space, post-sampling | consumer only — inherits plane-awareness from the sampler for free | — |
| diag | — | — | consumer; must draw windows through the composite (today: axis-aligned boxes, rotation/shear-blind) | scalar box scale |

Weights follow measured reliability: decode-gated > certified-probe NCC
> word anchors > dust. Magnitudes from direct NCC are calibrated to
DECODE-OPTIMAL, not physical, offsets (the ×1.5–2.3 overshoot,
INDEPENDENT-PLANES §2.3) — the calibration constant is a measured
property of the detector, re-measured when the detector changes.

**MEASURED 2026-08-23 — the certified-probe plane-common lane is REFUSED
at this evidence tier** (INDEPENDENT-PLANES §2.11, the P5 bar; instrument
`measure/plane_fields/pose_writer.py`). Feeding the plane-common part of
a window's certified probes back to that window's pose, over all 334 open
slots of the W6 sheet-I state, three captures unioned, on a frozen and an
E1-refit footing: **−5 certificates and +2.1 pp cell BER**, with the harm
LINEAR in the correction (+9.3 pp per print dot) and largest exactly
where the window's sites agree most. Two mechanisms, both measured: the
field is fed each plane's FULL local offset and already absorbs a quarter
to three quarters of that plane-common residual (regression slope of
field-common on pose 0.25–0.75 by axis and capture, correlation
0.42–0.72), so a writer stacked on it double-counts; and
removing the double-count by construction only cuts the harm by two
thirds — the sign is still wrong. The calibration warning in the
paragraph above is the explanation: a DECODE-OPTIMAL-calibrated offset
survives plane-DIFFERENTIAL use, where the calibration error cancels
between planes, and does not survive plane-COMMON use. **Row "certified
probes" keeps its per-plane attribution; the plane-common attribution
belongs to decode-gated writers (word solves, `certified_refine`) only,
until a different evidence tier is measured.** The per-window local
affine is measured too and is statistically real (leave-one-site-out:
better on 77–80% of windows, 0.27 → 0.23 dot) and decision-irrelevant
(14.65% vs 14.67% cell BER, 0 certificates either way).

---

## 7. The service (code-level sketch, src/holo/receive)

One module owns the composite; nothing else computes logical→raster.

    points_for(capture, lane, window, plane, cells_local) -> lane px (N, 2)
        # L ∘ S_{ch(plane)} ∘ P_window ∘ F_plane, vectorized per window row;
        # F looked up per tile (bilinear over the field's tile bins),
        # S looked up per platen position; identity fields short-circuit.
    report_residual(capture, lane, window, plane, offset_local_dots,
                    quality, source) -> None
        # attribution per §5/§6; writes to SheetField / PoseRecord /
        # ScannerField evidence, never to the fields directly (solve is
        # a separate, explicit step — the PLANE-FIELDS solver).
    solve(state) -> SheetField, ScannerField   # explicit; monotone evidence

State: SheetField (per state — the sheet is the state's subject),
ScannerField (per scanner id), PoseRecord (per capture × window, exists).
Events: one `pose.composite` report per (capture, lane) with per-frame
stats (replaces `payload.plane_fields` as the pinned vehicle — FieldStats
and the E band read it; the Details-vehicle bug class dies here because
the producer defines the event).

Performance rule: the sampling leaf stays vectorized per window row;
the field lookups are O(tiles) per window, not O(cells). Measure the
sampling share of lane cost before and after (today unknown).

---

## 8. Null-proof build plan (each step gated before the next)

Gate for steps 1–4: BYTE-IDENTICAL outputs on the archived corpus — the
eight colour-uplift captures' certificate digests and close shas, the
sheet-I fossil replay (5297 certificate identities, payload sha
2445b95d…), the K/cmy7/cmy8 PK-FINAL states, v1 goldens untouched. No
policy-id bump for behaviour-identical steps.

0. P1 fixes first (INDEPENDENT-PLANES §6): shrinkage target, uncovered-
   plane zero, F fold, `done_tiles`, stale shell test, instrument no-ops.
1. Collapse the four inline pose re-expansions onto `AffinePose.points()`
   (placement/geometry `_fit_phase`, `sample_segment`; placement/search
   `refine_patch_pose`; color_anchoring `_features_with_page_fraction`).
2. Dedupe rot_k (`_payload_sampling.rotated_points` vs
   `placement/reference.rotate_points` — derived equal, pin it with a
   test) and the page→scan hint affine (`place.placement_hint` vs
   `production._page_to_view_affine`).
3. Introduce the composite with identity fields and route every raster
   read through `points_for` — the 9 crop sites and 11 interpolation
   sites of Appendix A, tier 1 (colour path) then tier 2 (K, placement,
   certified_refine).
4. Writers: anchors and probes measure after the composite; word solves
   report; the closer (when built) reports. At identity fields this is
   still byte-identical.
5. Populate (a)-translation from the existing PLANE-FIELDS solver
   through the service (retire `field_corrected_features` as code, keep
   it as the reference). Gate changes to STRICT SUPERSET + measured
   yield on archived sheet I (INDEPENDENT-PLANES §6 P5 bar).
6. Scanner id on CaptureFacts; (c) slot with identity; characterization
   hook.
7. Consumers built on the service — out of this doc's scope:
   per-lane monotone pass (B), certified furniture (G), the closer (C),
   per-window refinement (D), plane-aware addressing (A.2).

---

## 9. Open questions

- Is (a)-common ever worth solving, or does (b) absorb it harmlessly
  forever? Needs two re-placed captures of one sheet solved jointly
  (sheet I has three 2400s — a free test once step 5 lands).
- (c) from characterization or from solve? Probably both: the
  knife-edge gives scale and CA cheaply; the solve validates on real
  pages.
- Field bandwidth as a per-engine prior vs always-measured — after the
  W11 registration track measures a second sheet.
- The holo2 port shape: SheetField as a journaled, commutatively-merged
  family (monotone evidence) with the solve as a derived view — fits the
  commit wall; to be written into holo2/docs/DESIGN as doctrine at the
  H-wave.
- Sampling cost share (unmeasured) — the one number that could force a
  different service shape.

---

## Appendix A — seam inventory (read 2026-08-22; inferences flagged)

Canonical transform: `AffinePose.points()` (placement/model.py:363),
`cells @ J.T + origin`; 8 call sites. Pose carried as
`patch.segment.segment.pose`; K and colour share one point set
(`_payload_sampling._window_rows` :75 → `_sample_rows` :235 and
`color_sampling.crop_features` :189).

| consumer | site | transform | sampling | plane-aware |
|---|---|---|---|---|
| survey / segmentation | survey.py:60,306; _survey_tensor.py:110,132 | none — integer step_px grid (pre-pose, legitimate) | box decimation + structure tensor | blind (luma) |
| pose fit (phase objective) | placement/geometry.py:322 `_fit_phase` | inline re-expansion #1 | map_coordinates(order=1) on uniform_filter crop | blind |
| window sampling | placement/geometry.py:457,469 `sample_segment` | inline re-expansion #2 | map_coordinates ×2 | blind |
| cold lane / cold search | placement/search.py:257,376,429; place.py:1477 | none — post-sampling, cell space | fftconvolve on evidence arrays | n/a (inherits) |
| word read / validation | placement/search.py:107,932,969,1063; words.py:185-287 | none — reads sampled bits | mask select + weighted mismatch | blind (inherits) |
| placement refinement | placement/search.py:807,845-861 | inline re-expansion #3 (+ own `_pose_candidate` twin) | map_coordinates | blind |
| place_committed / label / mop-up | place.py:547,714,1505-1529; _payload_reuse.py:316,326 | PoseRecord → AffinePose → `sample_segment` | as above | blind |
| certified refine (K) | certified_refine.py:220,602,622,735 | `AffinePose.points()` | map_coordinates, own aperture crop | blind |
| colour refine | color_refine.py:396,416,816 | `AffinePose.points()` + imported `_pose_candidate` | map_coordinates per channel, mode=nearest | BLIND — three planes, one point set |
| K payload sampling | _payload_sampling.py:75,108,197,208,235,397 | `AffinePose.points()`; `rotated_points` :56 | uniform_filter + map_coordinates | blind (n=1) |
| colour base features | color_payload.py:346,358; color_sampling.py:124,147,170,189 | reuses `_window_rows` points | uniform_filter ×3 + map_coordinates ×3 | BLIND — one point set, three channels |
| colour corrected features | color_anchoring.py:556,585-590,604-608; color_field.py:772 | `pose.matrix()` + per-plane local delta (inline re-expansion #4, necessarily) | points_crop + map_coordinates per plane | YES — the only one |
| registration anchors | color_anchoring.py:227,280,323,353,384,447 | `AffinePose.points()` on a 2 px/dot rectified lattice | weighted NCC, parabolic peak | plane-selective, pose plane-blind |
| certified probes / projection | color_field.py:309,375,488,565; color_projection.py:131 | reuses `_rectified_ncc` | as anchors | plane-selective, pose plane-blind |
| field solve / serve | color_field.py:602; plane_fields.py:187,529 | tile-space field, `_rotate_delta_xy` :118 page↔local | bilinear over tile bins | YES |
| diag underlay / pane A | production.py:75; diag/presentation.py:387,428; diag/scan_model.py:153,213,308 | scalar scale + axis-aligned boxes | Image.resize | blind; rotation/shear-blind (read, not rendered) |
| lane rescale | scale_space.py:161,168,174,187; runtime_model.py:123-134 | AreaPixelTransform | coordinate math | — |
| page↔scan hint affine | place.py:245,270,283; production.py:241,243 | duplicated 2×3 affine, `pose.matrix() @ inv(rotation)` | none | — |

rot_k implementations (four): `_payload_sampling.rotated_points` :56;
`placement/reference.rotation_affine` :227 + `rotate_points` :248
(derived equal, not executed); `np.rot90` on arrays (search.py:129-131,
286,941,959; words.py:226); `color_field._ROTATIONS` :108 /
`_rotate_delta_xy` :118.

Raster read surface: 9 crop sites (`crop_luma`/`crop_native`), 11
interpolation sites (`map_coordinates`). Tier 1 (colour path, 4
functions): `color_sampling.sample/crop_features/points_crop`,
`color_anchoring._features_with_page_fraction`,
`color_anchoring._rectified_ncc`, `color_refine._sample_planes`.
Tier 2 (3 functions): `_payload_sampling._window_crop/_sample_rows`
(owner of APERTURE_CELLS and the halo contract), `certified_refine.
prepare_region_image/_sample`, `placement/geometry.prepare_region/
sample_segment/_fit_phase`.

Not read: tests/ — existing equivalence pins may already cover some
duplicates.
