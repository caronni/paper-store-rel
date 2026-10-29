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

## Amendment 2026-10-11 — a fourth family, `cmy` (FORMAT-SPACE §19)

Legend addition: Cy = `Family.CMY`. docs/CMY-DESIGN.md §6(l) asked for
this table to be re-derived for a fourth family BEFORE code; that did
not land at W0 (7bad672c). The build converted the sites below against
the design's §6 table instead — W1 128ed3cb, W2a 6926f6ef, each refuted
by an Opus reader — and this note records them as converted. The table
above is left as authored; its `receive/…` rows name the v1 receiver
retired 2026-09-05 at `284ae3e` and are history (holo3's cmy dispatch
is src/holo/receiver/docs/CMY-RECEIVER-PLAN.md's).

| Site (src/holo) | Decides | Predicate on family, 2026-10-11 |
|---|---|---|
| format/lattice.py `_RUNG_ARITY`, `parse_coding_id`, `CodingParams` | rung arity; one rung → all streams; rung token required | table {K 1, C7 0, C8 3, Cy 2}; expand when arity > 1; required when arity ≠ 0 |
| format/lattice.py `_DEFAULT_SITES` | input default p | Cy → 120 |
| format/lattice.py `_coding_for_id` | the family constructor | explicit K / C7 / C8 / Cy branches, an `else` that refuses (was: bare `else` = C8) |
| format/lattice.py `_coding_for_id` pooled; format/descriptor.py `Coding._validate_v2` | pooled outer code | in (C8, Cy) |
| format/profiles.py `CodecProfile.__post_init__`, `state_ids` | alphabet law; word/dust state checks; the dust-cycle requirement | colour alphabet = a subsequence of `STATE_NAMES`; membership in the derived `state_ids`; Cy exempt from the cycle requirement and refusing a cycle |
| format/pilots.py `color_word_states`, `decode_color_word` | the word's states and lawful set | the codec's `word_states` (now a REQUIRED argument); Cy adds the domain-9-keyed Y at '0' sites and admits Y as lawful |
| format/pilots.py `dust_state_values` | dust source vector | Cy → the per-tile balance law; others the `dust_base_cycle` fact, unchanged |
| gen/color_compose.py `COLOR_FAMILIES` (both gates) | colour-only entry | in (C7, C8, Cy) |
| gen/color_compose.py `_payload_states` | the encode | C7 pack7 branch; one shared branch over `_PER_STREAM_ENCODERS` {C8 → `cmy8_encode_payload`, Cy → `cmy_encode_payload`}, the dither aux = stream ordinal + 1 passed as an integer (C8 bit-identical) |
| gen/emit.py `_emit_color_volume` | colour emitter gate | in `COLOR_FAMILIES` |
| gen/emit.py `color_route`, `_put_color_field` | the route | the engine record's `color_route`; no engine → cmyk1; `rgb` only for Cy (C7/C8 refused) |
| gen/manifest.py `_cmy_law_block`, `_renderer_block`, tier keys | cmy law fields; the route's renderer block; tier wording | is Cy; `rgb_solid` None → the cmyk1 block, byte-identical |
| gen/plan.py `tier_word` | "plane" vs "stream" tier | is Cy → "stream" |
| cli_gen.py `_engine`, `_engine_block`; `generate`/`capacity` | engine resolution, route check, record | not K → check the route (`capacity` refuses what `generate` would) |
| cli.py `--printer` | the flag's meaning beside `--format` | the emission engine for every family (the FORMAT-SPACE §9 fence that refused it beside `--format` is removed) |

Unchanged, and correct for Cy as they stand: `gen/compose.py`'s K-leaf
gate and `gen/emit.py` `source_packed_for` (refuse if not K);
`gen/emit.py` `emit_volume`'s colour route and `gen/manifest.py`
`is_color` (not K → colour); cli_gen's `registry` / `_coding_detail`
K-vs-colour printing (no cmy row is in CODINGS). Owed: `fit`'s skeleton
list prints k, cmy7 and cmy8 only (generator plan W2b).

**Selectors W2b retires (CMY-DESIGN R21; generator plan W2b, after
P1).** `--coding` and `--profile` on `generate`/`capacity`;
`devices/profiles.py` `make_spec` and `get_printer`; `registry -v`'s
per-printer derived geometry; the `hp-m281-ink` registry row; the
legacy meaning of `--printer` (printer margins → page geometry for a
`--coding`/`--profile` row); `emit_volume(printer_id=)`, kept beside
`printer=` for the evidence-archive recipes, retired with them or kept
with a recorded reason (those recipes move only on the owner's word).
After W2b `--format` (v2, or `L:` for a fossil) is the one identity
door.

*2026-10-12, W2b part (i) landed:* `fit`'s cmy skeleton line is done;
`Printer.color_route` None (the `default` engine) makes every colour
family refuse on both commands; `make_spec`, `get_printer`, `--profile`,
`--coding` on `capacity` and the derived geometry are gone. RETAINED until
part (ii), on the owner's ruling, for the evidence recipes only: `--coding`
on `generate` (opens onto a fossil, nothing else), the `hp-m281-ink` row,
`emit_volume(printer_id=)`.
