# format — DESIGN

Printed-format v1 truth: what the sheet IS. Addressing, coding, close.
Imports `core` only (plus stdlib/numpy/cryptography). format knows
nothing about how a capture is read and nothing about scheduling.

Constitution: `holo2/docs/DESIGN.md`. Public surface + rationale: the
`__init__.py` docstring.

## Purpose

holo2 decodes the **unchanged** printed format v1. Generation, the
format anchors, the goldens, the registries and the characterize
instrument all stay in `src/holo`; this package is the receiver-side
copy of the same truth, carried and adapted under the firewall
(`ENGINEERING.md`), pinned against `src/holo` by oracles in
`tests/holo2_oracles/`.

The contents, in dependency order: `family` (the `Family` enum — the one
legal dispatch key, importing no sibling so it can sit at the bottom of
the order), `bch` (the address word code), `pilots` (the colocated
site lattice), `keystream` (AES-128-CTR as a pure function of address),
`ldpc/` (mother codes, BP decoder, tile framing), `metadata` (the
one-bit addressed channel), `close_spec` (`CloseSpec`/`CloseStreamProfile`
— the format input surface a close reads, holo2-original), `lattice`
(the v2 identity GRAMMAR: pitch registry, `CodingParams`, canonical
spelling, `parse_format_id` — pure string law, builds no codec),
`families` (the COLOUR family constructors — `CodecFacts`, the stream
layout and the derived bank names for cmy7/cmy8), `format_v1` (coding
constants, the v1 identity law, the K coding constructor, one tile
format), `fossils` (the byte-matched legacy catalogue with its
import-time self-check), `registry_rows` (`FormatRowSpec` — the printed
sheet a decode names — plus `make_format`, the family constructor
table), `resolve` (the total resolver: `L:` → v2 grammar), `envelope`,
`streamset`, `fountain`, `fountain_close`.

**format is a leaf, not a policy.** It answers "what does this address
mean", "is this codeword legal", "do these certified symbols assemble
into the declared volume". It never decides what to attempt.

## Public surface

`holo2.format.__all__`, pinned by `holo2/tests/test_surfaces.py`. The
integrity refusals (`EnvelopeError`, `FountainIntegrityError`,
`MetadataIntegrityError`, `StreamSetIntegrityError`) are NOT on it since
B4: all four are raised and handled inside format, and
`test_error_taxonomy.py` derives DECLARED from `__all__`, so one is
declared in the same diff as the first cross-package handler that names
it. B4 also flattened `registry_rows` into `format_row` /
`tile_format_for` / `native_cell_pitch_px` (four callers, one function
each — and `format_row` left again at C5, below);
`ldpc_tile` stayed a namespace because its only caller is a
carried, AST-pinned function in `solve/tiles.py`. Its importers are `solve` and the
composition root (`cli`, which names the printed row); R2 removed the
last `engine → format` edge by making the close a provider
(`solve/close.py`), so the engine can no longer name a fountain state
even by accident.

WP-1.2 (2026-08-22) turned the old three-row `CODINGS` registry into an
ALIAS TABLE of lattice points, `LEGACY_CODINGS`, on the ground that a
registry beside a grammar is two identity mechanisms where L16 allows
one. **C2 (2026-08-22, RULINGS G1) finished that argument: the table
left the surface AND the tree.** A legacy coding NAME is not an identity
— a printed sheet is named by a whole `L:` line, coding *and* geometry,
matched byte-exactly — so a table of half-names could only ever build
sheets nobody printed. Its one cross-package consumer was `cli.py`'s
`--coding` **choices**; C2 made that flag name a v2 coding id validated
by CONSTRUCTION at the boundary, because a grammar is not an argparse
`choices` list, and **C5 (2026-08-22, RULINGS G6) replaced the flag
itself with `--format`**, which takes a whole identity — v2 id or
`L:<id>` — so the legacy route an operator lost at C2 is back.
`format_v1.coding_for` therefore mints from the v2 grammar ALONE, and a
legacy row is rebuilt from its frozen catalogue bundle by
`fossils.resolve_fossil_spec` — the one permanent legacy route.

**The grammar's door is on the surface since C5**, under B4's law in
both directions: `resolve_format_ref`, `ResolvedRef` and
`format_row_for` joined in the diff whose `cli.py` first imports them,
and `format_row` LEFT in the same diff, that import having been its only
cross-package consumer — a coding id with geometry stated separately is
half an identity no operator surface spells any more (it stays in
`registry_rows` for the constructors and tests that take the pair
apart). `parse_format_id` stays off: outside `format` a reference is
RESOLVED, never parsed. Net across C2 and C5: −2 (`LEGACY_CODINGS`,
`format_row`) +3. All refusals on these paths are builtins
(`ValueError`/`KeyError`), so nothing is owed to the taxonomy either.

**Aliases are mutable conveniences, never keyed; only canonical strings
enter seeds** (P14, `docs/FORMAT-SPACE.md` §14 decision 3, carried
2026-08-22) — the reason `LEGACY_CODINGS` could be deleted above without
moving a single seed, and the reason `fossils.py`'s `L:` table is
byte-matched rather than parsed: a legacy name is a lookup key into a
frozen bundle, never an input the grammar normalizes.

## Owned record families

**None.** format writes no durable record. `FormatRowSpec` is a
composition-time constant that rides in `SessionIdentity` (engine's
family) by its row id, and `CloseRecord` is core's. This is deliberate:
the printed format is not session state.

## The laws format enforces, and where

| law | where |
|---|---|
| **L5** a certificate is zero LDPC syndrome AND CRC-32, or there is none | `ldpc/tile.py`, `ldpc/decode.py`; the false-accept budget ≈ 2⁻³² per attempt is the CRC's |
| **L8** whole-word rival evaluation over the complete domain | `bch.py` — the (127,50,t=13)→(100,23) word code, true min distance d=27 EXACT, spectrum 27:3 28:8 31:119 32:247 |
| **L9** metadata trusts at GF(2) rank 24 AND ≥48 distinct certified counters; verified stop = canonical envelope + SHA-256 + minimal-K + zero padding, total or nothing; counts are advice | `metadata.py`, `fountain_close.py` |
| **L2** LLRs are bounded at emission | the emitter's invariant, not the decoder's: `ldpc/decode.py:116-118` **coerces** rather than refuses — finite LLRs are clipped to ±`LLR_CLIP` (20), ±inf is mapped to ±`LLR_KNOWN` (1e9), and NaN passes through `np.clip` untouched. An unbounded input is therefore silently normalised here; nothing in format detects the emitter that produced it |

The close is the one place where a *count* must never be mistaken for a
verdict: `close_count_ready` is the gate, `close_volume` is the answer,
and the stop is the SHA.

`close_count_ready` is **not** cheap — it runs
`metadata_from_certificates` (the full GF(2) elimination over the
certified metadata equations) and builds one `fountain.VolumeCode` per
stream through `distinct_esi_block_counts` — and since P3-1 landed
(2026-08-13) the production consult no longer calls it per certificate:
`solve/close.py` keeps the incremental gate and reserves the carried
functions for what stays theirs — `decode_metadata` as the ONE
interpretation authority (called once, at the rank-24/48-distinct trust
transition) and `close_volume` as the sole source of every durable
outcome, computing from the full certificate set. These functions are
unchanged, still pinned, and still the reference the incremental state
is property-tested against (`holo2/tests/solve/test_close_state.py`).
The format-axis addition was names only: the gate's dependencies joined
`format.__all__` (`coefficient_mask`, `decode_metadata`,
`MetadataDecode`, `METADATA_WORD_BITS`, `MIN_METADATA_EQUATIONS`,
`SUPPORTED_METADATA_VERSIONS`, `VolumeCode`, `volume_code_for` — the
last publishing `_volume_code` so the colour-args derivation can never
fork into a second copy).

## Measured facts format relies on

These are format anchors, not receiver measurements; their record is
`docs/HOLO-DESIGN.md` and the printed-format goldens in `src/holo`.

- d=27 EXACT with the spectrum above — the number L7's derived support
  floors are worked against (`solve`'s business, `format`'s constant).
- metadata: 1 LDPC user bit per tile via degree-24 LFSR rows; rank 24
  recovers, trust at ≥48 distinct certified equations.
- fountain-v2: per-page exact block quotas, keystream shuffle, two-tier
  promise; per-(stream, block) accounting throughout, because a global
  symbol count is duplicate-gameable (measured).
- the verified volumes holo2 must reproduce byte-for-byte:
  e029 `c2-r0700` 465,580 B; e032 `c2-cmy8` 718,413 B, `c3-cmy7`
  301,600 B (`experiments/029`, `experiments/032`).

Equivalence with `src/holo` is not an aspiration here — it is pinned:
`tests/holo2_oracles/test_oracle_close.py` and `test_oracle_tiles.py` run both
implementations on shared fixtures.

## TO-FIX — format's ledger

**F-nn** = the adversarial review with its severity scale; **S-n** = the
root ledger (`holo2/docs/DESIGN.md` §15); **P3-n** = phase-3 hardening
findings (`holo2/docs/HARDENING-WORKLIST.md`, WP-2). Adjudication is
H3.5's.

| id | defect | where | sev |
|---|---|---|---|
| F-15 | **CLOSED (phase 3)** — `FormatRowSpec.__post_init__` now validates the whole declared domain: `tiles_yx > 0` and `n_pages * tiles_y * tiles_x` inside the 18-bit counter, at the one production construction point (`format_row`, reached from `cli.py`). The recommended fourth immutable sheet descriptor was **not** taken (a fourth description of one sheet next to `FormatRowSpec`/`TileFormat`/`CloseSpec`); the `TileMap.counts()` half stays `solve`'s | `registry_rows.FormatRowSpec` | HIGH |
| S1 | **CLOSED (phase 3)** — the close's class is `CertifiedSymbolConflict`; `core.CertificateConflict` keeps the commit-time name. The rename is a declared adaptation, recorded in `test_oracle_close.py`'s `RENAMED_SYMBOLS`. The copies of this row in `holo2/docs/DESIGN.md` §15 and `core/DESIGN.md` are now dischargeable by their owners | `fountain_close.py:54` (WP-1.0 review fix: was `:66` pre-split) | HIGH |
| Q10 | the surplus-audit doctrine is stated two ways: the carried close calls certified disagreements fatal while its inherited post-solve surplus audit is report-only. Final SHA success plus a contradictory surplus certificate is VERIFIED-with-warning **or** terminal failure — one of them, before qualification | `fountain_close.py` | — |
| P3-1 | **CLOSED (BUILT 2026-08-13; ruled 2026-08-12, verdict user-upgraded 2026-08-13 "now-ish")** — the count gate no longer repeats the whole close per certificate. `solve/close.py` keeps `_CloseState` (in-memory, derived, DISPOSABLE): an incremental GF(2) eliminator over the metadata equations (the word is UNIQUE at rank 24 — later equations check, never revise; a contradiction is L5-terminal; the 48-distinct floor is the false-accept budget of ≥24 surplus parity checks, ≤ ~2⁻²⁴ residual), the carried `decode_metadata` called ONCE at the trust transition as the interpretation authority, per-(stream, block) distinct-ESI counters through `volume_code_for` built once per stream at K-trust, ZERO symbol-blob reads before a close attempt, and an EXACT re-close gate (a solved block stays solved, so an open attempt reruns only when an unsolved block gains a distinct symbol or metadata turns terminal). Every durable outcome is still the carried `close_volume` on the full set; equivalence with `close_count_status`/`metadata_from_certificates` is pinned at every prefix (`holo2/tests/solve/test_close_state.py`). Rider (same user ask): `--complete` now OBSERVES mid-run — consult modes `observe`/`close`/`final`, counting stays live, the decision stays deferred. **GATE RE-MEASURED 2026-08-13** (same driver, same sheet): REAL sheet VERIFIED byte-identical, perfect echo 1,357/1,873/2,643; consults 1,358 = **0.74 s = 0.1% of wall** (was 34.1 s = 6.0%, −46x); counting median 0.3 ms; exactly two `close_volume` runs — n=1356 open (102 ms), n=1357 verified (132 ms) — both necessary. Residual per-consult growth (0.2 ms at n≤400 → 0.8 ms at n>900) is the certified-key skip-scan over the per-commit-rebuilt index — F-17's row, not this one. Baseline for the record: MEASURED 2026-08-12, 1,358 consults = 34.1 s = 6.0%, linear ≈30 µs/certificate, deciding elimination 129 ms; at the 2^18 ceiling one consult would have cost ~7.5 s, so this was also the multi-page prerequisite | `solve/close.py` `_CloseState`; `fountain_close` unchanged | CLOSED |
| W1.2 | **CLOSED 2026-08-22 (RULINGS G3, "if src/holo supports the codes, so must src/holo2")** — was a declared limit: `LADDER` named six rungs and `format/ldpc/data/` carried only two (`r0550`, `r0700`), so a lawful identity naming any of the other four (`c2-k-r0850@76x53`) parsed, named a real sheet, and could not be built here, refused AT THE CONSTRUCTOR (the deleted `format_v1.CARRIED_RUNGS` mechanism and its H2 refusal). Now closed: `r0547.json`/`r0625.json`/`r0775.json`/`r0850.json` joined the data directory byte-for-byte (shas in `ldpc/construct.py`'s module docstring), so every `LADDER` rung is carried, the H2 refusal and its subset table are gone (a second mechanism policing a now-empty gap is guard mass, L17 — `LADDER` was the one mechanism all along, L16), and the oracle pin (`test_oracle_tiles.py::test_the_ldpc_data_is_byte_identical`) names all six files | `format_v1._k_coding`; `ldpc/construct.py` | CLOSED |
| C2-1 | **CLOSED 2026-08-22 (RULINGS G1)** — was two identity mechanisms: a byte-matched catalogue of whole `L:` identities beside a three-name legacy alias table that `format_row`/`coding_for` also routed through. A coding name is half an identity and selects no printed sheet, so the table could only build sheets nobody printed. Now: `LEGACY_CODINGS` deleted, each catalogue entry carries its own frozen `LegacyCoding` bundle beside LITERAL spec-id and seed bytes, and `L:` is the spelling on every surface (row id, persisted `format_row_id`, `CloseSpec.spec_id`, policy id, diag). Seeds unmoved. The debt it left — `fossils._legacy_row`/`_legacy_tile_format`, the private bridge that kept ~60 synthetic fixture sites minting legacy geometries — was PAID by C4 (see C4-1) | `fossils.py`, `format_v1.py`, `registry_rows.py`, `resolve.py` | CLOSED |
| C3-1 | **CLOSED 2026-08-22 (RULINGS G4/H2, "we wanted to move away from literal 600 dpi hardcoding")** — was `src/holo`'s deviation §15.3-2, copied: identity carried a physical `pitch_in` but every row also carried `cell_dots: int`, and FOUR constants spelled the engine grid (`registry_rows.PRINT_DPI`, `format_v1._PITCH_DPI` twice — the `_k_coding` refusal AND the `_validate_v2` invariant —, `capture.survey.PRINT_DPI`, `capture.scale_space._PRINT_DPI`), so a receiver that never observes a printer nonetheless assumed one ran at 600 dpi. Now: `Coding`/`TileFormat`/`FormatRowSpec` carry `pitch_in: Fraction` and no dots; `native_cell_pitch_px(dpi_true, pitch_in) = pitch x dpi` (exact, arithmetically identical to `c x dpi / 600` at every 600-grid pitch); the footing ladder and the survey's vote are pitch; refusal H3 (off-600) is folded into H4, whose set `format_v1.SCOPE_PITCHES` restated DESIGN §7's c2/c3 scope in inches (and was itself deleted hours later — C3b-1 below). `cell_dots` survives ONLY as frozen emission evidence on a fossil bundle (beside the `engine_dpi` that gives it meaning) and in `holo2/measure`'s renderers (`_fixtures.dots_per_cell`, `ENGINE_DPI`). Byte-identity canary: the verdicts gate, 39 green, every decode unchanged | `format_v1.py`, `registry_rows.py`, `fossils.py`, `capture/{survey,scale_space,ingest,records,catalog}.py`, `solve/{ingest,plans}.py` | CLOSED |
| C3b-1 | **CLOSED 2026-08-22 (RULINGS H1, "the c4 format is just 1i150-k-r0550@26x18")** — was holo2's own decode scope: `format_v1.SCOPE_PITCHES` refused every pitch but c2/c3 at two constructors (`_k_coding` for K, `FormatRowSpec.__post_init__` for colour), so five lawful identities `src/holo` builds were nameable and unbuildable here. Once C3 made pitch DATA the set defended nothing constructible — px/cell is `pitch_in x dpi_true` at any pitch, and only the blind survey's candidate ladder ever enumerates pitches — so it was guard mass over a measured fact (L17, P11). Now: the tuple, the message, both sites and all three pinning catalogues are deleted; `c4-k-r0550@26x18`, `c1-k-r0700@10x10`, `1i400-k-r0700@40x28` and the two colour twins moved into the oracle's buildable batteries, where every codec fact is compared member by member against `src/holo`. Landed with the twelfth fossil, `L:c4-r0550@1664x1152` (e033 sheet A) — needed as an `L:` line because its v2 twin seeds under `holo/v2/`, one physical format with two keystreams. **Review fix (C3b-c4):** deleting the set also deleted the only statement that a row's pitch is POSITIVE (it refused 0 and negatives as a side effect of naming two members), which left `FormatRowSpec`'s "the WHOLE declared domain is validated here" false and `native_cell_pitch_px` returning 0 and -4 px/cell in silence; the floor is restored at both sites, distinguished in prose from the deleted set — a non-positive pitch is a sheet that CANNOT EXIST, H1(a)'s set refused sheets holo2 had merely not MET | `format_v1.py`, `registry_rows.py`, `fossils.py` | CLOSED |
| C4-1 | **CLOSED 2026-08-22 (RULINGS G5, "migrate these to the new syntax and regenerate the fixtures")** — was the debt C2-1 left: `fossils._legacy_row`/`_legacy_tile_format`, a private bridge building a catalogued legacy CODING at an UNCATALOGUED geometry (`c3-r0550` on 2x2 tiles) so the synthetic fixtures could stay v1 identities. Half an identity, which G1 had already ruled cannot name a printed sheet, kept alive by 66 call sites in 27 files. Now: every synthetic page is a v2 identity (`c3-k-r0550@8x8`) resolved by BOTH trees from one string, every printed one is an `L:` line through `resolve_fossil_spec`, and both functions are deleted. `holo2/measure/verdicts/_fixtures` lost `media_for_tiles` — the last media→tiles inversion — and its canary gained the emission cell size (holo2's pitch × a NAMED engine dpi vs `src/holo`'s own `cell_dots`). Two verdict constants re-measured on the new pages, neither loosened (`FRAMES_CUT` 1→3 around the named F-16 re-earn hole; the subdivision arm's field 12x12→11x11 at the unchanged ramp, all three of its integers unmoved). `LEGACY_ROW_GOLDENS`' eight SYNTHETIC rows went with their subject; the four catalogued ones are pinned harder by `test_legacy_seeds`' twelve identities × four kinds of golden | `fossils.py`, `verdicts/_fixtures.py`, the eleven measure drivers, the four cross-tree oracles | CLOSED |
| C5-1 | **CLOSED 2026-08-22 (RULINGS G6, "yes, the --format syntax looks better")** — was: the identity door existed and no operator could open it. `resolve_format_ref`/`format_row_for` were reachable only from inside `format`, so the CLI took `--coding` + `--tiles-y` + `--tiles-x` — three arguments an operator had to keep in agreement to name half an identity — and NO holo2 surface could spell a printed `L:` sheet at all between C2 and this package (`L:c2-r0700@3392x2368` is both hardware-certified K volumes). Now: `--format ID` takes the whole identity, the door is on the public surface (and `format_row` left it, same law, same diff), a non-canonical spelling echoes `format normalized:` and proceeds, and every refusal an operator meets is the resolver's own sentence. A lawful COLOUR id names and builds its row here and dies at F1 with a message and a non-zero exit rather than a traceback | `resolve.py`, `__init__.py`, `cli.py` | CLOSED |
| C2-2 | **CLOSED 2026-08-22 (RULINGS G2)** — was: a lawful colour identity could be named and not built (refusal H1 at the constructor), so holo2 could parse sheet I's twin and produce nothing. Now `families.colour_codec` + `registry_rows.make_format` build a full colour `FormatRowSpec` — streams, fountain domains, derived codec/bank ids, dust furniture, `pooled_fountain` — and the ONE refusal left is F1 at `tile_format_for`, which every decode composition opens. **Owed to the colour port**: the alphabet, the evidence width, the mappers, the dust VALUE law and `pilots`'s six uncarried colour functions | `families.py`, `registry_rows.py` | CLOSED |
| P3-2 | three pinned close functions iterate a **set** (`distinct_esi_block_counts:474`, `close_count_status:526-530`, and since the cmy8-v1 leaf sync the pooled twin `pooled_distinct_esi_block_counts:450`), which the receiver-path determinism rule forbids. Recorded, not fixed: all are carried code, the values are `int` counters accumulated into an index-addressed array (order-independent by construction), and touching them costs the carry pin. It becomes real the day a carry adapts these lines | `fountain_close.py:450,474,526-530` (WP-1.0 review fix: were `:558,582,634-638` pre-split) | LOW |

**Identity carries PITCH; dots belong to whoever lays ink** (C3,
2026-08-22, RULINGS G4). A cell's width in dots is meaningless without
the dpi of the engine that printed it, and the receive path never has
one: what it has is a capture's operator-declared dpi, so px/cell is
`pitch_in x dpi_true` and nothing here divides by 600. The pitch is an
exact `Fraction` of an inch on every row of both namespaces — a v2 row
takes it from its id, a legacy row from its frozen catalogue bundle —
which is why `format_row_id` alone still reconstructs a printed sheet.
Two places still count dots, both of them honest: a fossil bundle keeps
the dots its sheet was PRINTED at beside the `engine_dpi` that scales
them (independent evidence, compared against the recipe's pitch by
`fossils._self_check`), and `holo2/measure`'s renderers take an
explicit `ENGINE_DPI` because emitting a raster is exactly the act that
needs one. The scope refusal moved with the unit and then
went: `SCOPE_PITCHES` was DESIGN §7's "only c2/c3 cell sizes" restated
as `{1/300, 1/200}` inch, and package C3b DELETED it under RULINGS
H1(a) ("every registered pitch class (c1..c4) and every lawful rational
builds") together with `scope_refusal`, both refusal sites and the
three catalogues that pinned them. Not a widening — adding `1/150`
alone would have left `c1` and the lawful rational `1i400` refused, i.e.
H1(a) half-executed. **No pitch refuses anywhere in `format` now**: what
still refuses at a constructor is the family (F1) and the algebra the
frozen numbers impose (`lattice.require_constructible`), which are
statements about sheets that cannot exist rather than about sheets this
tree has not met.

**Colour rows are NAMEABLE and BUILDABLE; colour CODECS fail fatally.**
This paragraph used to say "`CODINGS` carries the cmy7/cmy8 rows" (never
true of holo2), then "nameable, refused at the constructor" (WP-1.2).
RULINGS G2 (2026-08-22) settles it: holo2 implements the colour FORMATS.
The v2 grammar is total over all three families; `families.colour_codec`
mints the codec facts — three per-plane presence streams with their
frozen fountain domains for cmy8, one joint base-7 pack7 stream for
cmy7, the derived codec and FEC bank ids, the dust furniture — and
`registry_rows.make_format` turns any lawful colour identity into a real
`FormatRowSpec`, `pooled_fountain=True` for every v2 cmy8 row. What
holo2 will not do is DECODE one: `tile_format_for` raises "colour codecs
arrive with the colour port; holo2 cannot decode {family}" (refusal row
F1), and it is the door every decode composition opens in a provider
constructor, so a colour row dies before the first fire. Nothing here
predicts which family recovers on paper — CMY7 is a joint stream with no
per-plane fallback, CMY8 degrades plane by plane, and the e032 ordering
inversion is what L14 is about.

## Carried leaves

Origins are the real module paths, and every "adaptation" cell states
what the pin's own tables declare. The pins are
`tests/holo2_oracles/test_oracle_tiles.py` (`bch`, `pilots`, `ldpc/*`) and
`tests/holo2_oracles/test_oracle_close.py` (the rest) — **not**
`test_oracle_carry_source.py`, which covers `src/holo/receive`'s capture
and solve carries and contains no format entry.

| leaf | from | adaptation |
|---|---|---|
| `bch` | `holo/core/bch.py` | none |
| `pilots` | `holo/format/pilots.py` | 6 names NOT carried — the colour surface (`color_payload_cell_indices`, `color_site_cells_yx`, `color_word_states`, `decode_color_word`, `dust_site_cells_yx`, `dust_state_values`); it needs the codec-profile registry and arrives with H7 |
| `ldpc/{construct,decode,tile}` | `holo/core/ldpc/…` | none (the frozen mother-code JSON is copied too, sha-verified at carry time) |
| `keystream` | `holo/core/keystream.py` | 8 names NOT carried (the colour draw forms + `payload_bits`, which draws a whole page for the generator); `_color_stream_aux` is published as `color_stream_aux` |
| `metadata`, `envelope`, `streamset` | `holo/format/…` | none |
| `fountain` | `holo/core/fountain.py` | 10 names NOT carried — the generator-side capacity/budget helpers (`max_k_for`, `page_capacity_sufficient`, `source_budget`, …, incl. their pooled siblings `pooled_page_capacity_sufficient`/`pooled_max_k_for_pages`) |
| `fountain_close` | `holo/receive/fountain_close.py` | `metadata_progress` (v1's §10.4 observer projection) NOT carried; `close_record_from_result` adapted to holo2's §5.5 `CloseRecord`; renamed `FormatSpec`→`CloseSpec` and `CertificateConflict`→`CertifiedSymbolConflict` (S1); the consult gate became a recipe entry and the provider wrapper lives in `solve/close.py`. WP-1.0 (2026-08-22): `CloseStreamProfile`/`CloseSpec` moved out to `close_spec.py` — those two classes were always the `HOLO2_ONLY_PREFIXES` entries for this pair, never part of the origin's carried code, so the module now holds only this origin's + `close_progress`'s carried code. WP-1.1 (2026-08-22): the four K-vs-colour branches read `spec.codec_family is Family.K`, re-synchronising the carry with FORMAT-SPACE P1 — this pair's `ORIGIN_MOVED` entry retired and the pair compares LIVE again (measured: drifted `['_volume_code', 'close_volume', 'metadata_from_certificates']` → `[]`) |
| `family` (`Family`) | `holo/format/profiles.py:32-41` | the ENUM only, verbatim (10 lines). The rest of that module — the codec-profile hierarchy — is NOT carried and will not be: `format_v1` restates the K facts as arithmetic. No pair of its own: the close pair's live comparison pins the SPELLING (`Family.K` must be byte-equal to the origin's), and the VALUES `k` and `cmy8` are pinned live by the cross-tree lookup `Family(spec.codec_family.value)` in `tests/holo2_oracles/test_oracle_close.py:78` — a by-value lookup on a `str` enum, so it raises the moment a holo2 value moves, and both the K and the CMY8 fixture exercise it. `cmy7` is the only value not yet pinned in-tree; the colour port's oracle closes it |
| `format_v1`, `registry_rows` (`FormatRowSpec`), `close_spec` (`CloseSpec`, `CloseStreamProfile`) | holo2-original | — |
| `families` (`CodecFacts`, `StreamFacts`, `FecBankFacts`, `colour_codec`) | holo2-original; the ARITHMETIC restated from `holo/format/families.py` + `profiles.py` under RULINGS G2 (2026-08-22) | NOT a carry and given no `CARRY_PAIRS` entry, for the same reason `lattice`/`fossils`/`resolve` are not: holo2 has no `CodecProfile` hierarchy, no alphabet and no mapper, so an AST proof would fail on every function. What is pinned instead is the FACTS, member by member and cross-tree, in `tests/holo2_oracles/test_oracle_lattice.py`: stream ids, per-stream symbol bits and fountain aux, pooled flag, codec id, FEC bank ids and children, dust count and cycle, over every lawful colour identity of the battery and every colour fossil |
| `lattice`, `fossils`, `resolve` | holo2-original; REASONING carried from `docs/FORMAT-SPACE.md` §4/§6/§8/§10 and its P1–P13 | NOT carries and deliberately given no `CARRY_PAIRS` entry: they are reimplementations against a design, so an AST proof would fail on every function and force an `ADAPTED` row apiece — guard mass with no signal (L17). What is pinned instead is the STRING LAW, behaviourally and cross-tree, in `tests/holo2_oracles/test_oracle_lattice.py`: canonical spelling, v2 seed and family seed over all three families, the K codec facts member by member, the TWELVE legacy identities through the `L:` route (C2, 2026-08-22, twelfth added by C3b — one spelling each side, the marker the only difference), and refusal parity on every class both trees state |

A carry is a copy with a declared adaptation; every executable line is
the original unless the oracle's `NOT_CARRIED` / `ADAPTED` /
`RENAMED_SYMBOLS` tables say otherwise.

`ldpc/construct.py:8-12` states a **stale** carried-data path
(`holo2/src/holo2/ldpc/data/…`; the files live at
`holo2/src/holo2/format/ldpc/data/…`). Left in place: that module is
AST-pinned and outside the phase-3 format package's file scope.
