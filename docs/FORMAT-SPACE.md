# FORMAT-SPACE — the v2 identity grammar and orthogonal coding lattice

Status: **v1.0 — BUILT** (2026-08-19; design ratified through three
ruling rounds — §14 — and the full workplan P0–P6 executed the same day
on branch `format-space`; the build record with measured results is §15.
Deviations discovered during the build are folded into §5/§6/§10 and
listed in §15.3). This document is the governing amendment set to
HOLO-DESIGN (identity, registry, devices chapters) and supersedes the
isolated `c4-row` branch — whose worktree and ref were DROPPED
2026-08-19 after the emission goldens were carried (nothing remained
that main lacks; the full branch diff survives as main's parked patch
f1bc0d0). The fossil sunset (§8) remains user-declared and OPEN.
**AMENDED 2026-08-30 (§16, branch `canonical-identity`): the canonical
form is now the FULLY EXPLICIT spelling and the short spelling is
display-only. MERGED 2026-09-02 (user ruling).** The shortest-form rule read three mutable tables, so a
sanctioned edit to any of them re-keyed printed sheets; §2.1, §3, §4, §6
and §8 below are amended accordingly.

Scope ruling (user, 2026-08-19): legacy identities survive only as a
**fossil catalogue** — historical descriptors plus their exact AES
generation strings — which keeps today's receiver working on the printed
record and is **trashed on a user-declared sunset (~two weeks)**. Outside
that catalogue we make a fresh start: the new identity grammar is free to
be genuinely best, unconstrained by historical naming. Supporting legacy
sheets (AES starting keys + subsystem parameters) does not limit what we
define now.

---

## 1. Motivation

The e033 rung experiments (sheets A–I) proved the physics — first colour
rung above r0550 on paper, first pooled close on paper, 230.7 b/mm² — and
indicted the format plumbing: adding two experiment rows took edits to 13
files, because three orthogonal axes (codec family, rung, site count) are
fused into hand-assembled singleton profiles dispatched by object
identity, and the geometry axis (margins) is fused into pseudo-printer
registry rows. The review of that branch found real bugs of exactly the
predicted class (identity dispatch giving `-x1` rows a K dust field), and
the methodological ruling followed: rebuild by derivation, not by patching.

This document defines the derived target: a parametric coding lattice in
which every axis is independent, identity is a single parseable string,
and the string is the AES seed.

## 2. Principles

1. **Identity is a string; the string is the seed.** One canonical
   format-id fully describes a printed format; `parse(format_id)`
   reconstructs everything with no registry lookup. The row seed is the
   canonical id in a versioned namespace. **Two directions, both
   required (amended 2026-08-30): a string once printed means the same
   thing forever, AND a format once minted has the same canonical string
   forever.** The second is what makes the first safe, and it holds only
   because canonicalization reads no table that may change — no class
   registry, no defaults. Any spelling rule that consults a mutable table
   belongs to display (§4), never to the seed.
2. **Frozen substrate.** The v1 printed mechanics do not change (user
   input 6): tile = 64×64 cells; the C1 address word (BCH(127,50,t=13) →
   (100,23), 18-bit flat counter, d=27); word-site placement law (the
   site-seed draw, `holo/v1/sites/pN`); the LDPC metadata bit, its LFSR equation stream
   and encoding; the LDPC mother codes (all n=4096); the 15-domain
   keystream table and colour stream auxiliaries; the KDF prefix
   `holo/v1|` (a KDF label, not a version claim — unchanged forever);
   CRC-32 inner framing; fountain-v2 and the pooled outer code.
   `p<100` word subsampling is **unknown/reserved** — the e026 line, not
   this one.
3. **Families are closed constructors.** k / cmy7 / cmy8 are the three
   codec families; each is a *function* from parameters to a profile.
   Non-pooled CMY8 does not exist in the new space (obsolete; fossils
   only). Dispatch is on the family enum, never on object identity or id
   substrings.
4. **Geometry is the tile matrix.** What the format cares about is the
   tile matrix (it defines neighbour addresses in counter space, y-step =
   tiles_x). Media and margins are generation-time conveniences for
   choosing a matrix and placing it on paper; they are manifest facts,
   not identity (user inputs 1, 12).
5. **Physical pitch, engine grids, and scan grids are three different
   things.** Identity carries physical pitch only. Print resolution is a
   device fact recorded in the manifest; scan resolution is a capture
   fact. They meet only as derived quantities (dots/cell at emission,
   px/cell at survey) (user inputs 4, 7).
6. **Derive, don't patch.** Every consumer site changes against a
   pre-authored behavior table; reviews finding missed sites indict the
   generator of the table, not the site.

## 3. The axes

| Axis | Values | Freedom | Enters keying via |
|---|---|---|---|
| Cell pitch | named classes c1…c4 or explicit rational n/d inch | free per sheet | format-id |
| Codec family | k, cmy7, cmy8 (closed enum) | free | format-id |
| Rungs | k: one rung; cmy8: triplet (r_C,r_M,r_Y); cmy7: baked per generation | any LADDER member; ladder appendable | format-id |
| Furniture | p ≥ 100: 100 word sites + (p−100) dust/filler | k, cmy8 free; cmy7 baked | format-id + site seed |
| Generation | v{G} per family, default FROZEN (v1 for every family today) — never "current"; always spelled in the canonical form | append-only semantic bundles | format-id |
| Tile matrix | any TY×TX ≥ 1×1 within counter space | free (10×10 scraps to A3 fields) | format-id |
| Engine grid (`--dpi`), paper profile (`--paper`), placement | emission facts | free | **never** |

The pooled source-fraction dial `q`, plane tiers, and payload content are
generation knobs, not identity — unchanged.

## 4. Cell pitch: exact rationals, named sugar, no privileged grid

**Internal representation:** exact rational inches (`fractions.Fraction`),
never floats, never metric. Metric and TeX units cannot represent inch
grids without fractions (1/600 in = 42333.3̅ nm; scaled points don't
divide either); the only fraction-free representation of this lattice is
the rational itself. Micrometers are **display only**.

**External representation — two token forms, one canonical string per
pitch:**

- **Explicit rational:** `{n}i{d}` ≡ n/d inch, reduced (gcd(n,d)=1).
  Any positive rational is lawful format; engines gate printability.
- **Named classes:** frozen registered names for common rationals.
  **Input and DISPLAY sugar only (amended 2026-08-30) — never canonical.**
  The parser accepts `c2`, `1i300` and `2i600` alike and normalizes all
  three to the canonical `1i300`; `c2` is what gets printed back at a
  human:

| Class | Pitch (exact) | Display | 600 dpi | 300 dpi | 1200 dpi |
|---|---|---|---|---|---|
| c1 | 1/600 in | 42.3 µm | 1 dot | — (½ dot) | 2 dots |
| c2 | 1/300 in | 84.7 µm | 2 dots | 1 dot | 4 dots |
| c3 | 1/200 in | 127.0 µm | 3 dots | — (1½) | 6 dots |
| c4 | 1/150 in | 169.3 µm | 4 dots | 2 dots | 8 dots |

**No grid is privileged** (ruling, second round). The class registry
happens to hold 600-grid multiples because those are the measured
engines; nothing in the machinery anchors on 600. A 1200-dpi engine
needs no registry change: it prints c1 at 2 dots/cell (the density
doubling, floor permitting), and its intermediate pitches are already
expressible — a 3-dot cell on that grid is `1i400` (63.5 µm), and
`1i400` stays that sheet's canonical name whether or not the pitch later
earns a class. New names append to the registry when a pitch earns one;
numbers are never reinterpreted, **and since 2026-08-30 an append cannot
touch identity at all: it adds a display name, nothing more.** (Before
that amendment it could: registering a name for a pitch spelled as a
rational changed that pitch's canonical string, hence its AES row seed,
hence the readability of anything printed under it. `1i400` — this
paragraph's own example — was the likeliest casualty.)

**Emission rule:** `dots_per_cell = pitch × engine_dpi` must be a
positive integer — and that is the *only* gate (ruling, third round:
there is no minimum-cell floor; it was artificial). `c1 --dpi 600` and
`1i600` emit freely for whoever wants to try. What was actually
measured — *both 600-dpi engines fail to develop isolated single
dots* — is characterization knowledge that lives in the device
documentation and informs the operator; it never refuses an emission.
"c2@600 = c1@300" stops being a synonym puzzle: both sheets are simply
**c2** (pitch 1/300 in); the manifest records which grid emitted them,
and the receiver never needs to know.

## 5. Families

Each family is a constructor from (rungs, sites, generation) to an
immutable profile carrying a `family` enum tag. The frozen singletons
(`CMY7_P120_V0`, `CMY8_P120_V0`) are privatized; the resulting
ImportErrors enumerate every consumer for the behavior-table rewrite.

**k(rung, p=100)** — 1 stream `"main"`, W/K alphabet, word states (W,K).
Extra sites beyond 100 are keystream-known filler cells (placement/
context evidence). Shortening = p (all mothers n=4096, transmitted =
4096−p = payload cells); user bits = k_bits − p − 32 (CRC).

**cmy7(p=120, gen=v1)** — 1 stream `"main"`, 7-state pack7 (11 bits / 4
cells), word states (W,CM), dust from the 20-entry base cycle. The rung
axis is *coarser by nature*: pack7's FEC is a joint 3-child bank whose
shortening is baked to the payload cell count, so rung/site variation
means a new baked bank = a new **generation**. gen v1 ≙ today's bank
(r0550 + 2×r0625/677, p120 fixed). A future generation may rebake.

**cmy8(rungs=(r_C,r_M,r_Y), p=120)** — 3 streams C/M/Y, 8-state
presence, per-plane independent LDPC, **pooled fountain always** (one
fountain over esi = counter·3 + stream, stream-exact quotas, per-stream
metadata equations — the semantics adopted 2026-08-13/14). Per-plane
shortening = p; per-plane user bits = k_bits(rung) − p − 32. Dust from
the 6-entry base cycle. Rung triplets are the format-side lever the
measured Y-registration sinusoid asks for — with a constraint the
frozen pooled algebra imposes (found during the build): **one pooled
fountain has one symbol width, so a gen-v1 triplet's rungs must share
`k_bits`** — LIFTED 2026-09-04 under gen-v1 (ruling; §17,
docs/CMY8-COLUMN-GROUPS.md): the pool's symbol is the widest plane's
width and a narrower plane carries column groups of it, so any triplet
is constructible; equal-width triplets are the one-group case,
bit-identical to the frozen pool. src/holo's constructors no longer
gate on width at all (the grouping is derived where generation and
planning need it); holo3's identity checks the grouping's feasibility
after the per-rung floor.

**Furniture bound (k, cmy8):** 100 ≤ p ≤ min_stream(k_bits) − 34 (at
least one payload bit + metadata after CRC). Large p (e.g. p300 = 200
dust sites) is a legitimate design point: more known-content cells for
cold search, placement-by-context, and smaller recoverable scraps, priced
in payload (user input 5). The site seed `holo/v1/sites/p{p}` (accessor
`family_seed` in src/holo and holo2, `sites_seed` in holo3) is the
**unchanged** frozen template, so any new sheet at p120 shares the exact
measured site layout — and the placement lineage — of every p120 sheet
ever printed.

## 6. The identity grammar

```
format-id  = coding-id "@" tiles-y "x" tiles-x
coding-id  = pitch "-" family [ "-" rungs ] [ "-" sites ] [ "-" gen ]

pitch      = class | rational
class      = "c" 1*DIGIT                      ; §4 registry (c1..c4 today)
rational   = 1*DIGIT "i" 1*DIGIT              ; n/d inch, reduced; ALWAYS
           ;                                     the canonical spelling
           ;                                     (a class name is display
           ;                                     sugar, §4)
family     = "k" | "cmy7" | "cmy8"            ; explicit always, k included
rungs      = rung                             ; k: required (its one rung)
           | rung                             ; cmy8: uniform shorthand
           | rung "x" rung "x" rung           ; cmy8: mixed, C,M,Y order
           ;                                     cmy7: no rung token
rung       = "r" 4DIGIT                       ; must exist in LADDER
sites      = "p" 1*DIGIT                      ; ALWAYS spelled canonically;
           ;                                     omissible on input, filling
           ;                                     from the FROZEN defaults
           ;                                     k→p100, cmy7/cmy8→p120
gen        = "v" 1*DIGIT                      ; ALWAYS spelled canonically;
           ;                                     omissible on input, frozen
           ;                                     default v1 (per-family)
tiles-y    = 1*DIGIT                          ; ≥ 1
tiles-x    = 1*DIGIT                          ; ≥ 1
```

**Canonical and display (amended 2026-08-30).** There are two spellings
of one format, and exactly one of them is ever seeded.

- **Canonical** — the string the seed is made of, and the only string
  written to a seed, manifest, state file or directory name:
  `{n}i{d}-family[-rungs]-p{sites}-v{gen}@TYxTX`. Reduced rational pitch,
  sites and generation ALWAYS spelled, uniform cmy8 triplets still
  contracted. It is a pure function of the parsed parameters and of the
  frozen family/rung/enum spellings — of **no mutable table**.
- **Display** — the short spelling: registered class name where one
  exists, defaults omitted, triplets contracted. What every message,
  log, diag pane and CLI listing shows, and what a person types. Never
  stored, never seeded.

The parser accepts either, plus any lawful mixture, and normalizes to
canonical: `c2-cmy8-r0700x0700x0700-p120-v1@53x37`, `c2-cmy8-r0700@53x37`
and `1i300-cmy8-r0700@53x37` all resolve to canonical
`1i300-cmy8-r0700-p120-v1@53x37`, whose display spelling is
`c2-cmy8-r0700@53x37`.

The four laws (each a test, in every tree that parses identities):

1. `seed == b"holo/v2/" + canonical_id` — the seed is a pure function of
   the canonical id, and no exported function maps a raw `str` to seed
   bytes.
2. `resolve(canonical_id).canonical_id == canonical_id` — canonical is a
   fixed point.
3. `resolve(display_id).canonical_id == canonical_id` — display round-trips.
4. **Canonical ids and seeds are invariant under any edit to the class
   registry or the defaults tables.** This is the load-bearing one: it is
   what the shortest-form rule silently violated, and it is checked by
   monkeypatching a new class in and re-resolving the corpus.

The contracted uniform triplet survives because expanding it consults
only the family's rung arity (k: 1, cmy7: 0, cmy8: 3) — a fixed property
of the closed `Family` enum, not a registry, so no table edit can move
it. A future generation that changed a family's arity would have to
spell its rungs in full under its own `-v` token: any contraction rule
added later must be keyed by (family, generation), both of which the
canonical string already carries.

The defaults tables remain load-bearing for *input* (a short spelling
omits `p` and `v`), which is why they are frozen per family rather than
"current": a stored canonical string is immune, but a display string in
an experiment log must keep its meaning too. Generation tokens map v1 to the
current semantics of each family (k: today's k-v1; cmy7: today's pack7
bank; cmy8: pooled). LADDER today: r0547, r0550, r0625, r0700, r0775,
r0850 (k = 2240…3520, all n = 4096); r0300 does not exist; new rungs
join by data + ladder entry, no grammar change (user input 2).

**Seeds:**

```
row seed     = "holo/v2/" + canonical format-id          (fresh namespace)
site seed    = "holo/v1/sites/p{p}"                       (FROZEN, shared)
KDF          = SHA-256("holo/v1|" + seed)[0:16]           (FROZEN)
```

The site seed was called the *family* seed until 2026-08-30. The name
was misleading — it has nothing to do with the `Family` enum; it is
keyed by SITE COUNT alone, which is exactly why equal-density sheets of
different families share a lattice. The bytes are unchanged and frozen;
holo3 spells the accessor `sites_seed`, and src/holo and holo2 owe the
same rename.

The v2 namespace makes the fresh start explicit and collision-proof
against every legacy string (legacy: `holo/v1/<id>/<cells_y>x<cells_x>`
with `/`-separated *cell* geometry; new: `@`-joined *tile* geometry).
The asymmetry — the site seed staying v1 — is deliberate: site placement
is a frozen subsystem address like a domain byte, and sharing it keeps
E022/E023-lineage placement behavior valid across old and new sheets.

**Examples:**

These are DISPLAY spellings; each resolves to a canonical string that
spells the reduced rational pitch, sites and generation in full — e.g.
`c2-k-r0700@53x37` → canonical `1i300-k-r0700-p100-v1@53x37`.

```
c2-k-r0700@53x37                the e029/B/C format point, new-space twin
c4-k-r0550@26x18                sheet A's twin (c4 = 169.3 µm; 2 dots on a 300 engine)
c3-k-r0550@10x10                a scrap-scale test sheet (fast e2e tests)
c2-cmy8-r0700@53x37             sheet I's twin (uniform triplet, pooled)
c2-cmy8-r0550x0550x0547@53x37   a lawful mixed triplet (equal k_bits —
                                the gen-v1 width-class law, §5)
c2-cmy8-r0550-p300@10x10        dust-heavy scrap format (200 dust sites)
c2-k-r0850@76x53                A3 at 4 mm, once an A3 engine day happens
1i400-k-r0700@40x28             illustrative: a 1200-dpi engine's 3-dot
                                cell (63.5 µm) — expressible today, no
                                registry change
```

**Derived names** follow the same grammar mechanically: LDPC bank ids
`{family}[-{plane}]-{rungs}-p{p}-v{G}`, codec ids, manifest fields, build
directory names. Where a new bank is numerically identical to a legacy
one (k banks are), identical ids are correct — they are the same
mathematical object; certificate identities still differ via seed and
spec id.

## 7. Geometry: the tile matrix is the object

`Format = coding × tile matrix`. The matrix is first-class and free: a
10×10-tile scrap sheet is as lawful as a 76×53 A3 field. Validation:
TY ≥ 1, TX ≥ 1, pages × TY × TX ≤ 2¹⁸ (counter space). Neighbour
addressing derives from the matrix alone (vertical neighbour = ±TX in
counter space) — which is *why* it is identity and media is not.

**SheetLayout** (emission-side, not identity): places the field on paper.
Inputs: a paper profile (§9) and a centering policy; or nothing (a
matrix chosen directly is centered on the chosen media). A `fit` helper
derives the largest matrix for (paper profile, pitch) — the current
derivation, demoted from identity-maker to convenience:

| media, margin, pitch | cells | tiles |
|---|---|---|
| A4 6 mm c2 | 3328×2304 | 52×36 |
| A4 6 mm c3 | 2240×1536 | 35×24 |
| A4 6 mm c4 | 1664×1152 | 26×18 |
| A4 4 mm c2 | 3392×2368 | 53×37 |
| A4 4 mm c3 | 2240×1536 | 35×24 (= 6 mm) |
| A3 4 mm c2 | 4864×3392 | 76×53 |

(Machine-checked against `derive_field`; note 4.0 mm and 4.5 mm requests
quantize to the same c2 field — e029 and e033-B/C share a spec.)
The manifest records media, engine dpi, dots/cell, origin, and borders;
the receiver measures pose from the scan and needs none of it.

## 8. The fossil catalogue

A single module: historical descriptors with their exact AES generation
strings and subsystem parameters. While it lives, the current receiver
decodes every legacy sheet unchanged; on the sunset date the legacy
decode paths and the fossil entries are deleted. The *mechanism* — a
name → canonical-format-string alias table, with an optional seed
override — survives the sunset and is then reused for convenience
aliases (e.g. holo3-style `max`, `resilient` names mapping to full
format strings) (user input 9).

**Why the mechanism was needed, and why v2 no longer needs it (amended
2026-08-30):** byte-matching exists because a legacy string re-parsed
under new rules could normalize into a *different* seed. Under the
shortest-form canonical rule that hazard applied to v2 identities too —
they were one class registration away from re-keying, and a printed v2
sheet would have needed a fossil entry to survive it. With the canonical
form now table-independent (§6), **no registry append or defaults edit
can ever re-key a v2 identity, so fossilization is never needed for that
cause.** The catalogue stays for v1, whose seed law is genuinely
different, and for the alias role below.

**Resolution rule (ruling, second round): fossil ids never reach the new
parser.** They are opaque keys, matched byte-exactly against the
catalogue and resolved directly onto their frozen v1 seed strings and
parameter bundles — no grammar, no normalization. On every new surface
they carry the prefix **`L:`** (e.g.
`--format L:c2-cmy8-r0700-p120-x1@3392x2368`), so the route is visible
at the call site and the two namespaces cannot collide even in
principle. A near-miss refuses with the closest catalogue entries
listed. Existing state files (schema ≤ 25 — sheet I's verified state
among them) store bare legacy spec ids; the legacy loader keeps
accepting those unchanged until sunset. New-schema states only ever
contain new-grammar ids.

Twelve fossil codings; fourteen v1 spec-level seed strings (all
machine-verified against `derive_field`; every seed byte string gets a
frozen golden in P0), plus the one v2-namespace row added 2026-09-03:

| # | Spec id | Row seed (`holo/v1/…`; row 15 `holo/v2/`) | Evidence |
|---|---|---|---|
| 1 | c3-r0550@2240x1536 | …/c3-r0550/2240x1536 | catalog; printed e033 A2 (6 mm), G (4 mm, same cells) |
| 2 | c2-r0550@3328x2304 | …/c2-r0550/3328x2304 | catalog; goldens, unprinted |
| 3 | c2-r0700@3328x2304 | …/c2-r0700/3328x2304 | catalog; goldens, unprinted |
| 4 | c2-r0700@3392x2368 | …/c2-r0700/3392x2368 | e029 VERIFIED 465,580 B; e032 VERIFIED; e033 B, C |
| 5 | c2-cmy7-p120-v0@3328x2304 | …/c2-cmy7-p120-v0/3328x2304 | e032 print; failed live, closed 686,859 B by the uplift campaign |
| 6 | c3-cmy7-p120-v0@2240x1536 | …/c3-cmy7-p120-v0/2240x1536 | e032 VERIFIED 301,600 B |
| 7 | c2-cmy8-p120-v0@3328x2304 | …/c2-cmy8-p120-v0/3328x2304 | e030 fail; e032 VERIFIED 718,413 B (first CMY8 from paper) |
| 8 | c3-cmy8-p120-v0@2240x1536 | …/c3-cmy8-p120-v0/2240x1536 | e030 partial (663 certs) |
| 9 | c2-cmy8-p120-v1@3328x2304 | …/c2-cmy8-p120-v1/3328x2304 | catalog; sim + emit goldens |
| 10 | c3-cmy8-p120-v1@2240x1536 | …/c3-cmy8-p120-v1/2240x1536 | catalog; printed e033 F (4 mm, same cells) |
| 11 | c2-cmy8-p120-v1@3392x2368 | …/c2-cmy8-p120-v1/3392x2368 | e033 D, E printed |
| 12 | c4-r0550@1664x1152 | …/c4-r0550/1664x1152 | e033 A printed (branch coding) |
| 13 | c2-cmy8-r0700-p120-x1@3392x2368 | …/c2-cmy8-r0700-p120-x1/3392x2368 | e033 I **VERIFIED 1,798,761 B** |
| 14 | c2-cmy8-r0850-p120-x1@3392x2368 | …/c2-cmy8-r0850-p120-x1/3392x2368 | e033 H printed (holo3-max twin) |
| 15 | c2-cmy8-r0547@53x37 | `holo/v2/c2-cmy8-r0547@53x37` | e035 sheet J **VERIFIED 1,048,576 B**; the one v2-namespace row — see below |

**Row 15 — the v2 fossil the amendment above predicted (added
2026-09-03).** Sheet J was printed 2026-09-01 under the shortest-form
rule; §16 landed 2026-09-02. Its display id `c2-cmy8-r0547@53x37` still
parses and still resolves — onto `1i300-cmy8-r0547-p120-v1@53x37`, a
*different* seed — so without the entry nothing raises and the sheet
descrambles to coin flips.

The window is closed: the canonical form is now table-independent, so no
print from 2026-09-02 on can re-key, and this table should never gain a
second v2 row for this cause (pinned by
`test_exactly_one_fossil_is_a_v2_namespace_row`). Row 15 lives in
holo3's catalogue only. `src/holo`'s cannot hold it — that module's law
is that the legacy recipe reproduce the frozen seed
(`resolve_fossil_spec`, `_self_check`), and a `holo/v1` recipe cannot
produce `holo/v2` bytes; `c2-cmy8-r0547` is not in the legacy `CODINGS`
either. Consequently neither src/holo nor holo2 can decode sheet J;
holo3 is its only reader. The key-set asymmetry is declared as
`sheet-j-v2-fossil` in holo3's drift registry. It also means row 15 must
NOT be deleted with the v1 entries at the sunset — it is a live sheet's
only decode route, not decode-only history (inference, not yet ruled;
belongs with the open sunset ruling).

Also carried while fossils live: the legacy bank/codec id strings (they
are hashed into persisted certificate and decoder identities, so sheet
I's verified state replays bit-identically), the legacy `-v0` per-stream
fountain semantics, and the K family-token-less id forms. Sheets A–J are
printed; H, I and J are scanned so far — reprints are possible and
another fossil is cheap (user input 10). paperholo-format sheets
(e016–e018b lineage) are out of scope: they belong to the legacy
paperholo reader, not to src/holo.

## 9. Paper profiles (printers demoted out of generation)

Ruling (second round): generation stops selecting printers. The idea of
the printer registry as a capability / rastering profile never matured —
drop it from the generation path rather than carry the scaffolding. What
generation actually needs is a **paper profile**: a named
(media, per-edge margin) bundle consumed by the `fit` helper and
SheetLayout:

```
--paper A4-6mm      the locked conservative bundle (default)
--paper A4-4mm      the measured-probe bundle (ink reach 3.5–4.3 mm on
                    both engines; e028/e031/e033 footing)
--paper A3-4mm      appended when the A3 day happens
```

plus `--dpi` (engine grid for the dots/cell computation, default 600 —
the only measured class; 300/1200 become expressible without code
change). There is **no minimum-cell floor** (third-round ruling): the
only emission check is integrality (§4). The isolated-1-dot-dead
measurement stays where measured facts live — the printers/scanners
registry, which survives as *documentation* (print-path law, MIC notes,
capability records) but exits the generation code path; the
`hp-m281-ink` / `xerox-altalink-c8245-ink` pseudo-printers are deleted
with it. Keying-neutral throughout: none of this ever entered a seed.

## 10. Receiver contract (explicit-identity path)

One flag: `--format <format-id>`. Parse → full spec → decode; no
printer or paper argument at decode time, ever (the matrix is in the
id). The resumable state persists the canonical format string (~~schema
bump~~ — struck 2026-08-22: the holo2 catch-up wave built the identical
contract with NO schema-version bump, RULINGS B6 — the schema did not
change, one of its values did; see `holo2/docs/CATCHUP-PLAN.md`); a
resume reconstructs the spec by parsing — the catalog no
longer gates lawfulness, and the entire off-catalog fallback complex
(the "stream 'M' is not declared" incident class) is deleted rather
than guarded. Fossil ids arrive as `--format L:<legacy-spec-id>` and
resolve by direct match (§8) onto the legacy seeds and pipeline until
sunset. **Discovery integration is explicitly deferred** (user
input 11): cold-start hypothesis sets, their operational/null budgets,
and matrix inference from scans are a later design; this document solves
expressiveness.

## 11. Validation rules (consolidated)

1. pitch = registered class or reduced `{n}i{d}` rational on input; the
   canonical spelling is always the reduced rational, class names are
   input/display sugar (§16); family ∈ {k, cmy7, cmy8}.
2. Every rung ∈ LADDER; arity 1 (k), 3-or-contracted-1 (cmy8), 0 (cmy7).
3. cmy7: p and rungs fixed by generation (v1: p120).
4. k: p ≥ 100; cmy8: p > 100 (colour furniture includes dust);
   both ≤ min_stream(k_bits) − 34; p < 100 reserved.
5. TY, TX ≥ 1; pages × TY × TX ≤ 2¹⁸.
6. Canonical form at every serialization point; parser normalizes.
7. `L:`-prefixed ids bypass all grammar rules: byte-exact catalogue
   match or refusal (§8).
8. Emission: dots/cell = pitch × engine_dpi ∈ ℤ⁺ (no floor beyond
   integrality); field fits the paper profile.
9. Build-time: grammar injective; no new seed collides with any fossil
   seed (namespace-disjoint by construction, asserted anyway).

## 12. Workplan

Derive-don't-patch discipline throughout: each phase lands from a
pre-authored spec/behavior table, separately reviewable, suite green at
every commit. The `c4-row` branch stays isolated as the experimental
record; its semantic content is subsumed by P1–P5, its e033 artifacts
are already on main.

- **P0 — Fossil shim + seed goldens.** New `format/fossils.py` (the
  catalogue above, verbatim strings); a golden test freezing all 14 row
  seeds + the p100/p120 family seeds as exact bytes; zero behavior
  change. *Exit: goldens green on main; current receiver provably
  untouched.*
- **P1 — Lattice core.** Pitch registry (rational type), family
  constructors, grammar emit/parse/normalize; privatize the profile
  singletons; author the dispatch behavior table (from the 2026-08-19
  consumer sweep: ~40 sites across identity, codec-id, cell_dots, and
  stream-id classes) and re-derive every site onto the family enum.
  *Exit: parser round-trips the whole lattice; ImportError sweep clean;
  behavior table checked in as the test matrix.*
- **P2 — Identity/geometry split.** Format = coding × matrix; SheetLayout
  + `fit`; manifest v2 (canonical id, seed, engine dpi, dots/cell,
  placement). *Exit: new-space emit of the six §7 geometries + a 10×10
  scrap sheet, byte-stable under regeneration.*
- **P3 — Paper profiles.** `--paper` bundles (A4-6mm, A4-4mm) + `--dpi`;
  printers exit the generation path; pseudo-printers deleted. *Exit:
  the e029/e033 geometries reproduce via `--paper A4-4mm`; a `c1 --dpi
  600` sheet emits without complaint.*
- **P4 — Generation on the lattice.** emit/compose/plan accept the new
  Format; small-matrix centering; per-family fast roundtrips at 10×10
  (a real suite speedup — full-page e2e stays in the slow lane).
  *Exit: seven-coding gate net green plus new-space equivalents.*
- **P5 — Receiver explicit path.** `--format`, ~~state schema bump~~
  (canonical id persisted — struck 2026-08-22, same correction as §10:
  no schema-version bump was needed), catalog-free resume; fossil route
  for legacy ids. *Exit: sheet I's verified state replays bit-identically
  through the fossil route; a new-space sim sheet decodes end-to-end via
  `--format` only.*
- **P6 — Acceptance.** Full suite; archived-corpus non-regression (the
  deferred task #1: the 12,516-tile uplift corpus); goldens; then merge.
- **Sunset (user-declared, ~2 weeks).** Delete fossil decode paths,
  legacy registry rows, legacy tests; the catalogue file survives as the
  alias table (convenience names → canonical format strings).

## 13. Deferred / out of scope

Discovery integration (§10); ~~the `--no-close` line~~ (DONE
2026-08-19 post-merge: rebuilt from the state×mode table, detach
ruling — RECEIVE-DESIGN §9a); ~~holo2/confetti2 lattice parity
(H-wave)~~ (DONE 2026-08-22: the catch-up wave — RULINGS §A/§B/§G/§H —
carried the full v2 grammar, the `L:`-only legacy route, colour
FORMATS, rung parity, the pitch axis and `--format`/`--no-close` into
holo2; record: `holo2/docs/CATCHUP-PLAN.md`); `p<100` word subsampling
(e026); the A2 per-plane pose line;
characterization protocol for any new engine class (a 300-dpi engine
still owes the e001 protocol before first print); the first A3 print
day.

## 14. Decisions — RATIFIED (2026-08-19)

1. Row-seed namespace `holo/v2/` — ratified.
2. c1 in the pitch registry from day one, engine-gated — ratified.
3. Aliases are mutable conveniences, never keyed; only canonical
   strings enter seeds — ratified.
4. Pitch grammar admits explicit reduced rationals (`{n}i{d}`) beside
   the named classes; no privileged grid — ruled this round (§4).
5. Fossil ids carry the `L:` prefix and are matched directly, never
   parsed — ruled this round (§8).
6. Generation selects `--paper` bundles (A4-6mm, A4-4mm), not
   printers — ruled this round (§9).
7. No minimum-cell emission floor; integrality is the only gate, and
   the 1-dot-dead measurement is documentation, not a refusal — ruled
   third round (§4, §9).

## 15. Build record (2026-08-19, branch `format-space`)

### 15.1 What landed, by phase

- **P0** (`fb79f04`): `format/fossils.py` — 14 frozen identities with
  verbatim AES seeds, the p100/p120 family seeds, frozen parameter
  bundles for the three branch-minted codings (incl. the
  certificate-hashed `-x1` bank ids), import-time recipe/record
  self-check, seed-byte goldens with an independent second copy in
  `test_fossil_seeds.py`.
- **P1** (`e582be5`): `Family` (str,Enum aligned to the evidence-block
  kinds) on every `CodecProfile`; dust base cycles as codec facts (the
  pilots dust law restated over the cycle — bit-identical at p120 by
  golden, generic in n_dust); constructors `k_codec`/`cmy7_codec`/
  `cmy8_codec` (grammar-derived names; gen-v1 width-class law);
  `lattice.py` (grammar, rational pitch, normalizing parse, canonical
  id = seed under `holo/v2/`); the v1/v2 namespace split in
  `descriptor.py`; `resolve.resolve_format_ref` total over
  L:/legacy/catalog/v2 — **no state schema change needed**, and the
  off-catalog one-stream fallback bug class deleted; ~35 dispatch sites
  converted per `docs/FORMAT-SPACE-DISPATCH.md`.
- **P2–P4** (`7b6e49b`): `gen/sheet.py` (paper profiles A4-6mm/A4-4mm/
  A3-6mm/A3-4mm, `SheetLayout`, `fit`); emission `_Placement` split
  (v1 = derived FieldLayout, refuses paper/dpi; v2 = SheetLayout);
  `PSDoc` engine_dpi; manifest v2 fields; CLI
  `generate|capacity --format/--paper/--dpi` + `fit` subcommand;
  off-600 emission works end to end (`1i400 --dpi 1200`).
- **P5** (`6fcfa46`): decode `--format` (v2 id or `L:` fossil), resume
  through the total resolver; the two exit qualifications below.

### 15.2 Measured qualification results

- **Sheet-I replay through the fossil route**: the 2.85 GB VERIFIED
  state of e033 sheet I loaded + fully validated in **207.6 s** on the
  rebuilt tree — 5297 certificate identities recomputed against the
  fossil-reconstructed seed and frozen `-x1` bank ids; stream split
  M 1958 / C 1895 / Y 1444 and close payload sha `2445b95d…` identical
  to the live decode. (This state is the one that crashed the live
  session on the off-catalog fallback — the hole the resolver closes.)
- **v2 end-to-end**: the `c3-k-r0550@7x7` sheet (seed now
  `holo/v2/1i200-k-r0550-p100-v1@7x7`, §16) decodes byte-exact
  from an ideal capture with identity supplied as one format string;
  49/49 tiles, close VERIFIED (`test_lattice_receive.py`, fast lane).
- **v1 byte-identity**: every pre-existing emit/keystream/row golden
  passes untouched at every phase commit.
- **Fit law**: all six recorded geometries reproduced (incl. borders);
  A4-4mm c2 = 53×37 = the printed sheet-I matrix.
- **Suites**: tests/holo full runs green at each phase (P1: 1274;
  P2–P4: 1305 passed / 42 skipped); the P6 full-repo run and the
  PK-FINAL corpus-state validation are recorded in the P6 commit.
- **holo2**: the close-carry oracle's own `ORIGIN_MOVED` tripwire
  declared the family-enum origin move; **retired 2026-08-22** — the
  catch-up wave's WP-1.1 gave holo2 the same `Family` enum dispatch
  (`spec.codec_family is Family.K`, replacing the `codec_id == 'k-v1'`
  string compares), and the pair now compares LIVE again (measured:
  `drifted=[]` on both `fountain_close`/`close_progress`). See
  `holo2/docs/CATCHUP-PLAN.md`.
- **Corpus (PK-FINAL states)**: the recorded color-uplift final states
  load + fully validate on the rebuilt tree across families and
  engines — xerox-c2-k VERIFIED 1930 certs, xerox-c3-cmy7 VERIFIED
  810, xerox-c2-cmy8 VERIFIED 5466 (66.6 s), hp-c2-cmy8 OPEN 15 (the
  never-closed capture — both terminal shapes covered).
- **Colour v2 e2e**: `c3-cmy8-r0550x0550x0547@10x10` (pooled, mixed
  triplet, v2 seed) closes byte-exact on the synthetic colour scan
  model — first measured by the adversarial review (273 certs,
  C/M/Y 91/91/91), pinned in the slow lane
  (`test_lattice_receive.py`); the review also closed `c3-cmy7@10x10`
  100/100.
- **Adversarial review (opus, whole branch)**: the v1 byte-law lens
  came back CLEAN by cross-tree BYTE comparison — main-vs-branch
  emission of three v1 rows identical, and the fossil route
  byte-identical to the actual `c4-row` tree that printed sheets
  A/H/I; the dust rewrite verified equivalent over all counters, both
  families, p=101..129. Ten findings (none a format fork) were
  dispositioned in the P6 fix set: the P5 commit amended green; the
  corpus-harness `scale_plan` call healed; cmy8 refuses p=100 and
  validates the fossil bank-id override; off-600 decode refuses with
  the pending message instead of a traceback; the dispatch table
  completed + enforced by `test_dispatch_hygiene.py`; pseudo-printer
  retirement re-scoped to the sunset (§9); cli.py split at the
  1000-line seam (`cli_gen.py`); the ORIGIN_MOVED whole-module skip
  accepted as documented and self-retiring.

### 15.3 Deviations from the v0.3 design, all recorded in place

1. **Gen-v1 cmy8 triplets were width-classed** (§5, as built on
   2026-08-19): the frozen pooled fountain had one symbol width, so
   triplet rungs had to share k_bits, and the full Y-lever
   (`r0700x0700x0550` as INDEPENDENT-PLANES §H priced it) needed a
   width-heterogeneous pool. LIFTED 2026-09-04 (§17,
   docs/CMY8-COLUMN-GROUPS.md): the lever was ruled and built as
   `r0700x0700x0547`, the same Y width.
2. **Off-600 pitches**: identity, planning and emission are fully
   general; the receiver's raster path guards off-600 with an explicit
   "pending" refusal (§10) — no current scan exists to qualify it.
3. **cmy8 requires dust** (§11.4): p = 100 parses arithmetically but
   colour addressing/calibration consume dust furniture, so the
   constructor refuses it — found by the adversarial review, fixed in
   P6.
4. **Pseudo-printers retire at the sunset, not at P3** (§9): they
   carry the legacy `--coding --printer` route until the fossils go.
5. **Corpus non-regression scope** (P6): full re-decode of the eight
   archived captures stays the separately-scheduled task (the original
   deferral); P6 validates the recorded PK-FINAL states (every
   certificate identity recomputed) across K/CMY7/CMY8 on both engines
   plus the sheet-I replay.

## 16. Amendment — canonical vs display identity (2026-08-30)

Branch `canonical-identity`. Amends §2.1, §3, §4, §6, §8.

**The defect.** The canonical form was the SHORTEST spelling, so
`canonical_coding_id` read `_CLASS_BY_PITCH`, `_DEFAULT_SITES` and
`_DEFAULT_GEN`. All three are declared append-only or "current". The seed
is the canonical string. Therefore a sanctioned table edit changed the
seed of an already-minted identity: registering a class name for a pitch
that had none re-canonicalized every rational spelling of it, and moving
a family default did the same. The next 600-grid class is `c5` =
five dots = `1/120` inch. Under the shortest-form rule, appending it
would have turned `1i120-k-r0550@7x7` into `c5-k-r0550@7x7` and
re-keyed the sheet. The failure is silent — the sheet descrambles to
coin flips and reads as a bad scan, not as a version error. §4's own
worked example, `1i400`, was the likeliest casualty (it is not a
600-grid class at all).

Note which direction broke. §2.1 guaranteed "a string once printed means
the same thing forever", and *parsing* was indeed stable. The seed is
made the other way — parameters → string — and that direction was not
stable. Both directions are now stated.

**The fix.** Canonical becomes fully explicit; the short spelling becomes
`display_id`, accepted as input and shown to people, never stored and
never seeded. Canonicalization then reads no mutable table, and the four
laws of §6 are testable — law 4 (invariance under a table edit) being the
one that would have caught this.

**Two things it buys beyond the fix.** Fossilization can never again be
needed for a v2 identity (§8). And the canonical string now spells every
lattice parameter explicitly — pitch as a rational, family, rung names,
site count, generation and geometry — with no mutable table standing
between the string and its meaning. Rung names and the family still
point into frozen code tables (LADDER, the codec banks), so deep-time
recovery per docs/BOOTSTRAP-DESIGN.md still ships those tables beside
the seed; the old form could not even be interpreted without the code's
mutable tables, which is the defect this amendment removes.

**Cost, and why now.** Every existing v2 canonical string changes, so
every v2 golden re-freezes. Nothing printed is affected (sheet J,
printed inside the window, is the one exception — §8 row 15, added
2026-09-03): sheets A–I,
e029/e030/e032, the colour-uplift corpus and the sheet-I quals are all
legacy identities on `holo/v1/` seeds, byte-frozen by the fossil
catalogue. The affected set is a few dozen v2 strings, all in tests,
oracles, docs and regenerable sim stimuli. This is the last moment that
is true: after the first v2 print, the same change costs a fossil entry
per printed sheet, forever.

**Landing order.** The canonical form is a cross-tree contract. holo3
pins it against src/holo (`test_v2_grammar_resolution_matches_v1`:
row_id and seed equality on six v2 ids) and holo3's sim sheets are
RENDERED by src/holo, so the three trees move together. This landing
covers src/holo, holo2 and holo3. The public doors are string +
parameters: holo3 `resolve_format_ref` / `mint_format`; src/holo
`resolve_format_ref` / `parse_format_id` / `mint` / `make_format`.

**Also in this amendment.** The *family seed* is renamed the **site
seed** (`sites_seed`): it is keyed by site count alone and has nothing to
do with the `Family` enum, which the old name implied. The bytes
`holo/v1/sites/pN` are frozen and unchanged — accessor rename only,
proved byte-identical by the cross-tree drift gate. And the
constructibility test for generation now checks membership in a frozen
defined-generation set instead of equality with the current default, so
a canonical id that spells `-v1` stays constructible if the default ever
moves.

**Landing record (2026-09-02).** The user ruled the merge of branch
`canonical-identity` to main on 2026-09-02; that ruling is the
declaration of the v2 golden re-freeze as a format fork. The amendment
text above is dated 2026-08-30; the branch was rebuilt on the
PAGE-DOMAIN main of 2026-09-02 before landing. Review follow-through
riding in the same merge: holo3's `RunOpen` event now records the
canonical `row_id` in `format_id` and the short spelling in a new
`display_id` field; holo3 `mint_format` refuses non-positive pitch;
src/holo's cached v2 coding constructor refuses a non-canonical id;
holo2 gained the defaults-table half of law 4; `display_id` is now
pinned across trees by the holo2 oracle and the holo3 drift gate; two
unrelated `SiteGeometry` positional-argument repairs in measure/ rode
along. The `family_seed` → `sites_seed` accessor rename above is
holo3-only for now — src/holo and holo2 still spell it `family_seed`
and owe the same rename as a separate byte-null change.

## 17. Amendment — the width-heterogeneous pool (RULED + BUILT 2026-09-04)

Amends §5 (the cmy8 width-class law) and §15.3(1). Branch
`cmy8-column-groups`; design, rulings and build record:
docs/CMY8-COLUMN-GROUPS.md.

**What it lifts.** The §5 constraint was a consequence of the frozen -v1
pool XORing whole symbols. The pool is GF(2)-column-separable (the
frozen solver eliminates the generator rows once and carries the symbol
bits as values), so a mixed triplet carries ONE symbol width — the
widest plane's — as Z column groups of a rational partition, a lighter
plane holding fewer consecutive groups per tile, its groups rotating
over the block-assignment key order (exact per-page quotas per group
and spatial whiteness). The symbol algebra, blocks, K field, metadata
equations and every uniform triplet are unchanged: uniform is the
one-group case under the frozen fill order, bit-identical by
construction — the fork guard, as n = 1 was for pooling. Capacity tiers
are weighted by groups carried: the dead-Y ceiling rises, the
any-one-plane ceiling falls (the heavy planes bind); the reserve covers
B·Z solves, Z per block.

**Grammar.** Unchanged: `r{C}x{M}x{Y}` already parsed (§6). Ruled: the
semantics live under gen-v1 (no mixed identity was ever emitted, so
nothing forks); (Z, bounds, carried) are a pure function of the triplet
(argmin mean spare over Z ≤ 32, ties to the smaller Z) and are not
spelled in the id. First rows pinned by emission goldens: the
triplets r0700x0700x0547 (Y at r0547) and r0850x0850x0775 as c3 rows at
10x10, and the lever as `c2-cmy8-r0700x0700x0547@53x37`.

**Scope (ruled).** src/holo sheet generation and the holo3 receiver;
src/holo/receive and holo2 untouched — the v1 receiver fails a mixed row
on its common-width property, holo2 keeps refusing, and the cross-tree
oracles record both as intended divergences (`INTENDED_DIVERGENCES`,
`ORIGIN_MOVED` for the fountain and streamset carries). Exact widths at
p120 for the record: S = k_bits − p − 33 (2087 / 2407 / 2727 / 3047 /
3367 for r0550 / r0625 / r0700 / r0775 / r0850). F14 unchanged: nothing
is printed.
