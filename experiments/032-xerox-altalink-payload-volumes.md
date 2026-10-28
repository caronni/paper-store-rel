# Experiment 032 — AltaLink C8245 payload volumes: first VERIFIED CMY8, and the CMY7-at-c2 failure

Print day 2026-08-05/06, office Xerox AltaLink C8245, Canon 4800 captures.
Companion to experiment 031 (the HCAL-R1 discovery pair from the same
sheets' print run). **Five volumes were driven to completion: three closed
VERIFIED byte-exact, two failed.**

The headline: **`c2-cmy8-p120-v0` closed VERIFIED, 718,413 bytes** — the
coding and engine combination that e030 could not recover on the Y-starved
M281. This is the first CMY8 volume ever recovered from paper.

The second finding is the more useful one for the format: **CMY7 at c2
failed on both engines, while CMY8 at c2 closed on the AltaLink** — the
opposite of how the discovery sheet ranked them.

## Provenance and honesty boundary

The decodes were run by the operator in their own sessions; this log is
written from the persisted state records (`*-receive.state.diag/status.json`
and `report.json`) plus the emit manifests and payload hashes. **I did not
run these decodes.** Every number below is copied from a state record or
recomputed from files on disk; nothing is re-derived from the captures.

All four volumes were emitted during the e030 wave (`scratch/e030/…`,
`scratch/e028/…`) and re-printed on the AltaLink, so `manifest.printer_id`
still reads `hp-m281` / `hp-m281-ink`. That is an emit-time parameter, not a
claim about which engine printed the sheet — the page geometries are A4 and
the margins (6.0 mm colour, 4.5 mm for `c2-r0700`) sit comfortably inside
the AltaLink's measured clip (e031 §5: ~2.0 mm left/bottom, 3.98 mm right).

Receiver status is **PROVISIONAL** on every run
(`qualification_status: provisional`, `production_receiver_claim false`);
the v1 physical/null false-accept gate, channel-BER envelope and support
margin are not frozen. A VERIFIED close is a byte-exact recovery, not a
qualification.

## Results

| volume | engine | spec | close | bytes |
|---|---|---|---|---:|
| `holo-xerox-c2-cmy8-q05-counting` | AltaLink | `c2-cmy8-p120-v0@3328x2304` | **VERIFIED** | 718,413 |
| `holo-xerox-c2-counting` | AltaLink | `c2-r0700@3392x2368` (K) | **VERIFIED** | 465,580 |
| `holo-xerox-c3-cmy7-counting` | AltaLink | `c3-cmy7-p120-v0@2240x1536` | **VERIFIED** | 301,600 |
| `holo-xerox-c2-cmy7-counting` | AltaLink | `c2-cmy7-p120-v0@3328x2304` | **FAILED** | — |
| `holo-hp-c2-cmy7-counting` | M281 | `c2-cmy7-p120-v0@3328x2304` | **FAILED** | — |

### Byte-exactness confirmed independently of the receiver

The recovered file hashes equal the emitted `payload-counting.bin` hashes:

| volume | SHA-256 (source == recovered) | bytes |
|---|---|---:|
| c2-cmy8 | `f13c34db6c96796e65c812b7bb99e7618625e49a34640fcee58bc4627e38ecca` | 718,413 |
| c2-r0700 (K) | `e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9dd165787af` | 465,580 |
| c3-cmy7 | `4f68dbf932324aa85c1af576b9724504eb5dff85039a66a062ff9c9adc4e50c2` | 301,600 |
| c2-cmy7 (never recovered) | source `5963b9d16abca48d66a05f80eb137ce76624b8fdedb48ce13c3ee0cf8f24c993` | 686,859 |

### Captures, and how each state binds to one

Every state record's `capture` identifier **is the leading 12 hex of the
capture's SHA-256**, so each decode is provably bound to a specific file on
disk. Verified for all five:

| capture (`scratch/in/`) | bytes | SHA-256 | state `capture` |
|---|---:|---|---|
| `xerox-canon-c2-cmy8.tiff` | 6,875,455,728 | `cf6427d0d66a3cb9af0b74f7162f5b163dd2f2f75bcf162940326ef6cc8aec47` | `cf6427d0d66a` ✓ |
| `xerox-canon-c2-bw.tiff` | 2,291,818,718 | `57a261454cc04e66bd333310df4d17ede867eaa862fe6cff20e5395799d927e3` | `57a261454cc0` ✓ |
| `xerox-canon-c3-cmy7-2400dpi.tiff` | 1,718,864,112 | `20fc40cd483277a4cad81d3299e228b2f89a16058c64666d8953b00ab0b6babf` | `20fc40cd4832` ✓ |
| `xerox-canon-c2-cmy7.tiff` | 6,875,455,728 | `01abdd8785c55616faa89958632c84c5d66711492ef643d031af330773f7e426` | `01abdd8785c5` ✓ |
| `hp-canon-c2-cmy7.tiff` | 6,875,455,728 | `c05354349a4ba844b2c1d0d69686f4b97e3ca1f2c0b2ff4fca84cba7f76c0e32` | `c05354349a4b` ✓ |

Note `xerox-canon-c2-bw.tiff` is the **payload** K sheet, a different
physical sheet from e031's discovery B/W capture
(`xerox-canon-cal-bw.tiff`, sha `65e8bf50…`), despite the identical file
size — both are full-platen 4800-dpi greyscale.

## Per-run state records

### c2-cmy8 — VERIFIED (the headline)

Lane `r03-16ppc-4800dpi`, level 12/12, 16 px/cell, 4800 dpi, one capture.

- footprint mapped **99.7%** (7,423,168 / 7,443,072 cells)
- addressing: windows 1460/24, placements **1890 accepted**, 56 unresolved,
  0 quarantined; words 1198 match, 411 insufficient, 263 refused, 0 conflict
- LDPC: 14,476 calls (14,825 attempts folded), **5,370 certificates**
  (+80 BP150), 246 failed, 0 low, 5,370 divergences; mop-up drops 214,924
  (flips 74,122)
- fountain: **close VERIFIED**, 718,413 bytes

With 52×36 = 1,872 tiles and per-plane LDPC across C/M/Y, the certificate
ceiling is ~5,616; 5,370 is **95.6%** of it.

### c2-r0700 (K) — VERIFIED

Same lane. Emitted for the e029 ink-tight `hp-m281-ink` geometry at 4.5 mm
margins and printed on the AltaLink anyway; it closed.

- footprint **99.8%** (7,818,136 / 7,836,156)
- addressing: windows 1598/12, placements 2713 accepted, 82 unresolved;
  words 1027 match, 749 insufficient, 185 refused
- LDPC: 3,125 calls, **1,930 certificates** (+1 BP150), 31 failed;
  mop-up drops 10,498 (flips 1,942)
- fountain: **close VERIFIED**, 465,580 bytes

1,930 of 53×37 = 1,961 tiles = **98.4%**, and the e029 M281 print of this
same volume certified 1,940/1,961 = 98.9%. The two engines land within
0.5 pp of each other on the K coding.

### c3-cmy7 — VERIFIED

Lane `r03-12ppc-2400dpi`, 12 px/cell, **2400 dpi** capture (the only volume
of the five not captured at 4800).

- footprint **99.6%** (3,327,091 / 3,339,840)
- addressing: windows 640/12, placements 808 accepted, 18 unresolved;
  words 722 match, 94 insufficient, 24 refused
- LDPC: 3,766 calls, **720 certificates** (+8 BP150), 120 failed;
  mop-up drops 119,499 (flips 35,882)
- fountain: **close VERIFIED**, 301,600 bytes

720 of 35×24 = 840 tiles = **85.7%**.

### c2-cmy7 on the AltaLink — FAILED at the cell level, not at acquisition

This is the informative failure. Geometry and addressing were **healthy**:

- footprint **99.8%** (7,428,672 / 7,443,072) — as good as the volume that closed
- addressing: windows 1390/24, placements 1472 accepted, only 32 unresolved;
  words **1489 match**, 262 insufficient, 121 refused, 0 conflict — *more*
  word matches than the successful CMY8 run's 1198
- LDPC: 28,702 calls (29,131 folded), **83 certificates** (+5 BP150),
  **1,789 failed**; mop-up drops 413,389 (flips 125,525)
- fountain: received **83/920 K**, reach 83/920 over 1 block, metadata
  trusted, close deferred

So the page was found, posed, and addressed correctly — the receiver knew
exactly where every tile was — and then could not decode the payload cells.
83 of 1,872 tiles = **4.4%**, against CMY8's 95.6% on the same engine, same
print day, same cell size, same page geometry.

### c2-cmy7 on the M281 — FAILED at acquisition

A different failure mode entirely, and consistent with e030's "screened
mush" verdict for M281 colour at c2:

- footprint only **60.3%** (4,485,766 / 7,443,072)
- addressing: windows 4183/**880**, placements 808 accepted, **2,713
  unresolved**; words **47 match**, 1051 insufficient, 322 refused
- LDPC: **0 calls, 0 certificates** — the payload stage never ran
- fountain: received 0, K unavailable, **metadata rank 0/24**, +48 checks to
  trust, close deferred

The page never became addressable. This is not a payload-detector result; it
is the M281 colour channel failing before the receiver gets a chance.

## The finding: CMY8 survives at c2 where CMY7 collapses

Both c2 colour volumes are matched on everything that usually matters:

| | c2-cmy8 | c2-cmy7 |
|---|---|---|
| page cells | 3328×2304 | 3328×2304 |
| tiles | 52×36 | 52×36 |
| cell_dots | 2 | 2 |
| site family | `holo/v1/sites/p120` | `holo/v1/sites/p120` |
| margin | 6.0 mm | 6.0 mm |
| `q_dial` | **0.5** | **0.5** |
| `n_symbols_total` | 1872 | 1872 |
| `k_total` | 918 | 920 |
| codec | `cmy8-presence-p120-v0` | `cmy7-pack7-p120-v0` |
| states | W C M CM Y CY MY **CMY** (8) | W C M CM Y CY MY (7) |
| `symbol_bits` | 2087 | **5973** |
| **certificates** | **5370 / ~5616 (95.6%)** | **83 / 1872 (4.4%)** |

Redundancy is not the explanation — both are `q_dial` 0.5 with 1,872
symbols. The difference is the codec.

**And the discovery sheet ranked them the other way round.** From e031 §7,
same engine, same print day:

| candidate | whole-field | worst-window U95 | tier |
|---|---:|---:|---|
| `color-cmy7-g600x600-c2x2` | **7.74%** | 13.88% | fragile |
| `color-cmy8-g600x600-c2x2` | **12.17%** | 20.68% | fragile |

CMY7 measured *better* per cell and *failed*; CMY8 measured worse and
*closed*. This is the strongest available demonstration that discovery
candidate tiers are hard-decision channel numbers and not receiver
performance — not merely that the absolute level does not transfer, but
that **the ordering does not transfer either**.

### Leading hypothesis (INFERENCE, not measurement)

CMY8-presence codes each plane independently: C, M and Y each carry their
own LDPC, so a plane that reads badly costs only its own bits and the
fountain can still close from the other two. The certificate arithmetic is
consistent with this — 5,370 certificates against a ~5,616 per-plane
ceiling, i.e. the receiver was harvesting per-plane certificates.

CMY7-pack7 packs a base-7 symbol across the planes jointly. There is no
per-plane decomposition to fall back on: one plane reading badly poisons the
whole symbol. Its `symbol_bits` is 5973 against CMY8's 2087, so each CMY7
symbol also depends on ~2.9× more cells, and at equal per-cell error the
per-symbol survival probability falls steeply.

That would make CMY8 **gracefully degrading** and CMY7 **catastrophically
failing** at a marginal channel, regardless of which has the better per-cell
number — exactly the observed inversion. It also explains why CMY7 works at
c3 (85.7% certificates, closed) and dies at c2: the joint codec needs the
better channel that the larger cell provides.

**This is a hypothesis built from state counters and manifest fields. It has
not been tested.** The discriminating experiment is cheap and needs no
paper: re-decode the failed AltaLink c2-cmy7 capture with per-plane
diagnostics and check whether the certificate failures concentrate in one
plane (supports the hypothesis) or spread evenly across all three (refutes
it). e030's c3-cmy8 run on the M281 showed exactly such a concentration —
C 620 / M 43 / Y 0 — so the diagnostic exists.

## What this does and does not license

**Does:**
- CMY8 at c2 is recoverable from a real AltaLink print. That is a hardware
  fact, not a simulation.
- The AltaLink and the M281 land within 0.5 pp on the K coding
  (`c2-r0700`: 98.4% vs e029's 98.9%), so the engines are comparable where
  the M281's consumables are healthy.
- e030's Y-starvation diagnosis is supported: the same CMY7 coding that
  fails at *acquisition* on the M281 (60.3% footprint, 47 words) is fully
  acquired on the AltaLink (99.8%, 1489 words).

**Does not:**
- No registry promotion, no coding promotion, no margin change. Receiver is
  provisional on every run.
- Single copy per coding, single capture per volume, one print day, one
  scanner footing.
- The prints came off `lpr -o raw`, not socket 9100 (e031 §1).
- CMY7 at c2 is **not** established as unusable in general — it failed on
  one AltaLink sheet and one M281 sheet, for what appear to be two different
  reasons. c3-cmy7 closed on the same engine and day.

## Owed

1. **The per-plane diagnostic on the failed AltaLink c2-cmy7 capture** —
   the discriminating test for the hypothesis above. No paper.
2. Net-density figures for the three closed volumes, computed the way e029's
   64.7 b/mm² was, so they can be compared to the hardware record. Not done
   here: it needs the certified field area per volume, which is not in the
   status record.
3. If the hypothesis survives: state the graceful-degradation property in
   HOLO-DESIGN as a reason to prefer per-plane coding at marginal channels,
   and reconsider whether `cmy7-pack7` earns its density at c2 at all.
4. Print-date attribution for the M281 c2-cmy7 sheet is not established in
   this log — the capture was scanned 2026-08-06, but whether it was printed
   during the e030 wave or later was not determined.

## Artifacts

Captures (`scratch/in/`): `xerox-canon-c2-cmy8.tiff`,
`xerox-canon-c2-bw.tiff`, `xerox-canon-c3-cmy7-2400dpi.tiff`,
`xerox-canon-c2-cmy7.tiff`, `hp-canon-c2-cmy7.tiff`; hashes in
`scratch/e031/payload-capture-shas.txt`.
States and recovered volumes: `scratch/in/holo-*-receive.state`,
`scratch/in/holo-*-recovered.bin`, diag dirs `…-receive.state.diag/`.
Emitted volumes: `scratch/e030/holo-c2-cmy8-q05-counting`,
`scratch/e030/holo-c2-cmy7-q05-counting`,
`scratch/e030/holo-c3-cmy7-q05-counting`,
`scratch/e028/holo-c2-r0700-q07-ink-counting`.
