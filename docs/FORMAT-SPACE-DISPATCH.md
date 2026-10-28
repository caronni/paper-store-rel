# FORMAT-SPACE dispatch behavior table (P1)

The derived record of every codec-identity dispatch site in src/holo and
what it decides, re-expressed on the `Family` enum (FORMAT-SPACE §5,
"derive, don't patch"). Authored from the 2026-08-19 consumer sweep of
main BEFORE conversion; the conversion implements exactly this table.
A reviewer finding a site missing from this table indicts the table's
generator, not the site.

Legend: K = `Family.K`, C7 = `Family.CMY7`, C8 = `Family.CMY8`.
"family" below always means `spec.codec_family` / `codec.family`.

## Retired dispatch forms

- Object identity against the frozen singletons (`codec is CMY7_P120_V0`)
  — the singletons are module-private; sites converted to family.
- codec-id string comparison (`spec.codec_id == "k-v1"`, the
  cmy7/cmy8-v0 literals, the viewer's `"cmy8" in codec_id` substring) —
  codec_id is an informative label, never a dispatch key.
- Dust-base selection by identity — the dust base CYCLE is a
  `CodecProfile` field (`dust_base_cycle`); `pilots.dust_state_values`
  consumes the fact and dispatches on nothing.

## The table

| Site | Decides | Predicate on family |
|---|---|---|
| gen/emit.py `source_packed_for` | K-only packing | refuse if not K |
| gen/emit.py `emit_volume` | route to colour emitter | not K → colour |
| gen/emit.py `_emit_color_volume` | colour gate | in (C7, C8) else refuse |
| gen/color_compose.py encode | pack7 vs 3-plane encode | C7 / C8 branch |
| gen/color_compose.py gate | colour-only entry | in (C7, C8) |
| format/pilots.py `dust_state_values` | dust base | fact: `codec.dust_base_cycle` (no dispatch) |
| receive/color_attempts.py evidence kind | expected evidence | C7 / C8 branch |
| receive/color_attempts.py demap paths ×2 | CMY7 interleave+demap, demap↔BP | is C7 |
| receive/color_anchoring.py `_color_kind` | evidence kind + arity | C7→"cmy7", C8→"cmy8" |
| receive/color_divergence.py | divergence audit kind | C7 / C8 branch |
| receive/color_projection.py gate | certified projection | in (C7, C8) |
| receive/color_projection.py re-encode | pack7 vs per-plane | is C7 |
| receive/color_fitting.py `n_states` | 7 vs 8 | C7→7 else 8 |
| receive/color_fitting.py fit path | equal-prior QDA vs CMY8 detector | is C7 |
| receive/color_fitting.py collapsed-support, P1 held-out | CMY7-only arms | is C7 |
| receive/color_stack.py head-fit arm | CMY7-only | is C7 |
| receive/cascade.py `uplift_arms_for_codec` | arm schedule | (family, n_streams): K→(), n_streams<2→drop sibling arm, else all |
| receive/cascade.py `_derivation_kind`, colour-rgb predicate | rgb vs grey lanes | not K (and 3 channels) |
| receive/_runtime_validation.py attempt floors | k_eff vs payload-cells | K vs not-K |
| receive/_runtime_validation.py demap multiplier | CMY7 passes | is C7 |
| receive/_runtime_validation.py evidence kind | block kind | `family.value` (total; None-branch deleted) |
| receive/records.py decoder ids | K `rate_id/decode_tile…` vs colour `bank/decode_frame…` (+`-demap{n}` C7) | K vs not-K; is C7 |
| receive/records.py printed-field reconstruction | K + "main" only | is K |
| receive/records.py divergence kernel | K vs colour kernel | K vs not-K |
| receive/fountain_close.py per-stream bookkeeping ×4 | stream labels, block spaces | K vs not-K |
| receive/fountain_close.py no-attribution close | one block space | K or pooled |
| receive/production.py payload class | K vs colour payload | K vs not-K |
| receive/placement/reference.py field content ×2 | colour word states + dust refs | in (C7, C8) — the c4-row branch bug site, now unrepresentable |
| receive/diag/viewer.py stream tuple | C/M/Y panes | is C8 |
| cli.py `holo info` ×3 | K vs colour rendering | K vs not-K |
| gen/compose.py `compose_page_cells` | K-leaf gate | refuse if not K |
| gen/manifest.py `is_color` | colour manifest fields | not K |
| receive/session.py divergence replay guard | colour comparison kernel | not K |
| receive/cascade.py `scale_plan`/`_scale_plan` **signature** | lane plan takes `(codec_family, n_streams)` instead of a codec-id string | threaded: cascade, runtime.py, _runtime_validation.py, tests, `_color_uplift_harness/replay.py` |

## Unchanged, deliberately

- `stream_id == "main"` hash-domain split (receive/tiles.py) — stream
  naming is a frozen per-family fact, not dispatch to convert.
- `cell_dots` comparisons (survey/place/discovery/cascade scale math) —
  raster facts; v2 600-grid rows flow through unchanged, off-600
  pitches are guarded at `FormatSpec.cell_dots`/`.layout` (pending).
- Evidence-block magics/arities keyed by "k"/"cmy7"/"cmy8" — these ARE
  the Family values (the enum was aligned to the durable record).
- `pooled_fountain` checks — the outer-code axis, orthogonal to family
  by design (v0 colour rows are unpooled CMY8).

## Test matrix

The table is enforced by: `tests/holo/test_lattice.py` +
`tests/holo/test_families.py` (constructor/grammar law), the extended
colour-reference parametrization, the seven-coding real-payload gate,
and the fossil seed goldens (`tests/holo/test_fossil_seeds.py`). The residual
checks are AUTOMATED in `tests/holo/test_dispatch_hygiene.py`: no
singleton names and no codec-id comparisons outside src/holo/format/,
and no `scale_plan(codec_id=…)` callers anywhere.
