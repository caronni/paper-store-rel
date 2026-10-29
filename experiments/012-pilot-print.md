# Experiment 012 — ARCH-1: first physical archive-style pilot sheet (layout_version 3)

**2026-07-08.** The first sheet of the real format: kcell-c3 K payload
(3,237,500 random bits) + p60b6 pilots carrying the layout_version-3 window
code (PILOTS-DESIGN v0.3 §13: 18-bit flat counter + 5 zero pads in shortened
BCH(127,50,t=13)→(100,23); no version/plane fields — implicit format
signaling; t_acq = t_full = 13 single-stage). NO overt furniture anywhere on
the sheet: no header, no strips, no corner marks, no sentinel (R3
archive-style; identification is by the window code itself + this log).
This is NOT the M-P3 comparison sheet (PILOT-1, strips+bands, still queued);
it is the pure-format print + scan-side validation vehicle.

## Format provenance (layout_version 3, all frozen pre-print)

- Generator: experiments/012-pilot-print/gen_e012.py, SEED
  `paper-store/exp012-pilot1`, page 0; page geometry identical to e011
  (2220×1500 cells at c3, field 4500×6660 dots at (230,178), margins
  ≥7.5 mm; 925 word tiles, counters 0–924).
- **build/e012.ps sha256
  `8fcd89dd2a646b2c1d3adf092ca3f967d030f4d35d03e537bb943a14412540a1`** —
  regeneration byte-identical; anchored with the site/word/generator-poly
  vectors in tests/test_format_v3_golden.py (bump-don't-edit).
- v3 design decisions + measured basis: PILOTS-DESIGN v0.3 §13,
  REASONING-LOG "Session 2026-07-08". Notables: C_v3 ⊂ C_v2 (subcode
  nesting) so format identity rides the value-scramble labels alone
  (verified end-to-end both directions); page-283 counter edge handled.

## M0 sim gate (PASSED pre-print — ground rule: simulation before toner)

Full analyze_e012.py sweep (269 s, suite 195 green, RIP gate 0-pixel diff;
build/e012_report.json). v3 vs the recorded e011/v2 numbers:

| measurement | v3 (this page) | v2 (e011 record) |
|---|---|---|
| footing gap, 600×600-cell windows, mean of 3 print seeds | **+1.99 pp** (1.80/2.00/2.18) | +1.97 pp |
| grain 13 mm (8 trials) | **6/8**, med BER 1.49% | 5/8, 1.53% |
| grain 16 mm | 6/8, 2.35% (both fails = pre-existing Stage-0 pitch mislock; 24 paired fresh trials: 21/24 BOTH formats — no v3 effect) | 7/8, 2.17% |
| grain 20–60 mm | 8/8 each, 1.75–2.22% | 8/8, 1.66–2.66% |
| adversarial fast-warp seed 314, single scan | **3.73%** (t=13 decodes marginal slip tiles) | 5.80% |
| … + 3-scan majority | 2.09% | 2.12% |
| false accepts | 0/200k random words (raw and pad-gated); wrong seed/plane/phase/cross-format 100% reject | 0/200k |
| R3 site line | global spectral peak 44.9× median background | 88.1× |

A focused pre-print adversarial review of the format-axis delta (word
pack/unpack edges, generator/root-set re-derivation, emission bit-fidelity
at random tiles, subcode-nesting cross-accept probe, blind rehearsal on the
actual gs render) ran before printing — result recorded below in the run
table.

## Pre-registered envelope for the print + scan (BEFORE toner)

Protocol: ONE sheet, home M281 ("<host>"), raw 9100 via
`scripts/print_plane.sh experiments/012-pilot-print/build/e012.ps`, simplex,
plain paper, no driver path. Loupe check after print (bit-fidelity spot:
clean c3 texture, pilots invisible to the eye by design). Scan protocol:
1200 dpi grey, descreen/sharpen/auto-contrast OFF, 3–4 re-placed scans
(004.0b), rotated-scan orientation welcome (free with v3 pilots). Canon
4800 scans additionally welcome AFTER its characterization protocol.

Envelope (blind pipeline, public spec + seed only; GT used solely as the
scoring instrument):

- **Acquisition**: correct counter + orientation on every ≥25 mm software
  crop of a clean scan region; page-scale word-tile decode rate ≥ 95%.
- **Payload BER (blind, single scan)**: PASS ≤ 8%; MARGINAL 8–12%
  (investigate scan/print side before touching the pipeline); FAIL > 12%.
  Basis: sim says footing (~1.2%) + geometry gap (~2 pp) + real-channel
  excess over the sim's clean-c3 regime (hw c3 anchors 2.5–4.5%) —
  expected landing ~4–7%.
- **Null control** 0.50 ± 0.02 on every reported number.
- **Anchor precision** (PILOTS-DESIGN concern 1, the load-bearing hardware
  unknown): report measured single-pilot centroid noise; the §2.2 anchor
  math assumed 0.3–0.5 dots.
- **Multi-scan**: 3-scan combining expected to improve BER (sim +1.6 pp on
  the adversarial seed; 004.0b hardware precedent).
- Retraction rule: if the blind pipeline fails at page scale on a clean
  scan, the +1.97/+1.99 pp sim gap number is DEMOTED to sim-only in
  CLAUDE.md until diagnosed.

## RESULTS (012.3, scored 2026-07-09 — first physical archive sheet decoded)

**PRINT EVENT (reconstructed post hoc — the print itself went unlogged, a
protocol miss):** e012 ×2 printed 2026-07-08 ~16:00–19:30 on the office
Xerox AltaLink C8245 (engine 2, raw 9100, K-only ⇒ MIC-free) from the 012.2
bundle via its sha-gated print_office.sh (tarball member re-verified
8fcd89dd… = frozen build, byte-for-byte). Sheet A scanned; sheet B intact.

**PROTOCOL DEVIATION, declared:** scans were made on the NEW Canon flatbed
(grey; 1200/2400/4800 dpi = 2/4/8 px/dot) BEFORE its characterization
protocol — 012.2 registered home-flatbed scans, and the envelope admitted
Canon "after characterization". The numbers below beat the envelope anyway;
Canon characterization (002.0b rotated-scan attribution, MTF, step/comb
catalog) stays owed, and never-mix-scanners applies to all comparisons.

**Envelope verdict — PASS on every registered gate:**

| scan (px/dot) | window | tiles | word errs | blind payload BER | null |
|---|---|---|---|---|---|
| 1200 (2) | center | 20/20 | 19 | **1.77%** | 0.499 |
| 1200 (2) | off-center | 20/20 | 17 | **1.21%** | 0.499 |
| 1200 (2) | lower-right | 20/20 | 63 | **3.97%** | 0.502 |
| 2400 (4) | center | 20/20 | 12 | **1.38%** | 0.499 |
| 2400 (4) | off-center | 20/20 | 17 | **1.11%** | 0.499 |
| 4800 (8) | center | 20/20 | 9 | **0.64%** | 0.499 |
| 4800 (8) | off-center | 16/16 | 12 | **0.95%** | 0.499 |

(~40 mm blind windows via `score_canon_scans.py`; harness = full blind
`acquire_and_decode`, GT only as scoring instrument.)

- **Acquisition**: word-tile decode 100% everywhere (envelope ≥95%);
  orientation (rot 180°) + page counter blind and unanimous across all 3
  scans; fragment sweep during forensics: 13 mm+ windows acquire (10 mm
  fails Stage A, matching the sim grain). Origins self-consistent across
  scans; Canon scale measured +0.3–0.6% (pitch 6.014–6.036 px/cell), stable.
- **Payload BER ≤8% (PASS ≤8)**: 0.64–3.97% — better than the ~4–7%
  expected landing, ON ENGINE 2. Retraction rule NOT triggered; the
  +1.97/+1.99 pp sim-gap claim stands and is now hardware-corroborated.
  The 3.97% lower-right window (werr 63) is real within-page position
  variance (CAL-1 pattern) — rate ladders should see the worst position.
- **Oversampling**: 8 px/dot (4800) roughly halves BER vs 2 px/dot —
  0.64% is BELOW the genie-sync c3 hardware anchors (2.5–3.7%): blind
  geometry costs nothing here and Canon oversampling wins back more.
- **Anchor precision (envelope item, partially answered)**: the anchor
  stage is a near-no-op on these scans — `anchor_rounds=0` (stage off)
  reads 1.74% vs 1.77% with anchors, werr 15 vs 19; per-pilot centroid
  noise NOT yet extracted (open item; needs the 4800 scan + a dedicated
  pass). §2.2's 0.3–0.5 dot assumption is neither confirmed nor refuted.
- **Multi-scan (envelope expected improvement — NOT met, mechanism
  found)**: equal-weight 3-scan majority on 87,355 common bits = 1.41%,
  WORSE than best single (0.61% on the same bits). Per-scan on common
  bits 1.87/1.46/0.61%; independent errors would give ~0.05% ⇒ errors are
  strongly correlated across scans = PRINT-FROZEN (development dropouts),
  not scan noise. Hard-vote twin of 013.0's naive-LLR-summation negative;
  per-scan (pilot-agreement) weights or best-scan-selection are the fixes.
  Kept in the scorer as a correlation measurement, not a combiner.
- **Cross-scan consistency**: 1200/2400/4800 mutually agree 98.6–99.7%
  cell-for-cell (pilot and payload classes identically) — the ~0.6% floor
  at 8 px/dot is the print's error floor, not the scanner's.

**INCIDENT + RETRACTION (the reason scoring happened 2026-07-09): the
phantom-payload bug.** First scoring attempts read payload at exactly 50%
(null 0.500) with pilots at 0.55–1.7% BER across all scans, positions,
offsets and sub-cell phases — a 3-workflow forensics round (11 agents:
code readers, ink-level masked NCC, cross-scan consistency, git/session
archaeology, generation-convention sweep, adversarial verification)
excluded receiver bugs and print anomalies, then identified the cause: the
scoring reference had been re-derived as `integers(0,2,cap).astype(uint8)`
instead of gen_e012.py's frozen `integers(0,2,cap,dtype=np.uint8)` — the
dtype kwarg changes NumPy's bounded-integer stream, so the reference
payload was a statistically independent bitstream while pilots (payload-
independent) matched. Verified: the carried office file renders dot-exact
(29.97M dots) against the true regeneration; paper payload agrees 98.2–
98.8% blind. All "paper ≠ build" intermediate conclusions RETRACTED; the
paper always carried the frozen build. Lesson institutionalized: GT via
the gen module or extract-from-render, never a retyped draw (docstring
warning already existed in gen_e012.py; score_canon_scans.py embeds the
rule). Forensics artifacts: scratch/wf/*.{py,json} (session-local; the scripts
retired 2026-10-09, their result stands above).

**Receiver hardening shipped from the forensics (suite 226→228):**
`acquire_and_decode` gained (i) true `anchor_rounds=0` skip (was silently
≡1 via `max(rounds,1)`) + `anchor_rounds_run` diagnostic, and (ii) a
post-fold certification gate — if the post-fold full-strength word decode
collapses below half the visible tiles, the acquisition FAILS
(`failed_stage="post_fold_words"`) instead of emitting mis-addressed
payload (a one-cell mis-fold reads ~50% BER with ok=True otherwise; gate
threshold is c3-regime, must go layout-aware for c2). Tests:
tests/test_acquire_gates.py (clean skip + injected mis-fold vetoed);
adversarially reviewed, e012-scan regression byte-identical.

Remaining from this run: per-pilot centroid-noise extraction (4800 scan);
LDPC decode of the scans' payload_llr (M2 hardware moment); sheet B +
e014 + 007.9 batch scans; Canon characterization protocol.

## Run table

| run | date | action | artifact | sha256 |
|---|---|---|---|---|
| 012.0 | 2026-07-08 | gen_e012.py (layout_version 3) | build/e012.ps | 8fcd89dd2a646b2c1d3adf092ca3f967d030f4d35d03e537bb943a14412540a1 |
| 012.0 | 2026-07-08 | analyze_e012.py full sim sweep (M0 print gate) | build/e012_report.json | deterministic fields; timings excluded |
| 012.0 | 2026-07-08 | pre-print adversarial review (3 finders + verify): 0 confirmed; cross-accept probe (ks_v2^ks_v3 delta wt 45, v2-reject both seeds) + blind RIP rehearsal (--quick) + 195-test suite re-verified by orchestrator | — | — |
| 012.1 | 2026-07-08 | PRINT ATTEMPT: sha re-verified, sent via scripts/print_plane.sh — <host> unresolved (printer off); **print DEFERRED by user**, run when convenient | — | 8fcd89dd… re-verified on disk |
| 012.2 | 2026-07-08 | OFFICE print bundle staged (scratch/office-2026-07-08.tar.gz): e012 ×2 on the AltaLink (engine 2, raw 9100) + the queued 007.9 batch (e004/e006bw/e006c verbatim). Pre-registration: SAME envelope as the home print (PASS ≤8% blind BER, null 0.50±0.02, anchor-noise report), engine label "AltaLink"; sheets K-only ⇒ MIC-free (007.7/007.8); scans HOME FLATBED ONLY (office JPEG path cannot carry pilots, 007.2); e012 prints are content-identical — print order + this log = the disambiguator | scratch bundle | tarball 9f7c8986… |
| 012.3 | 2026-07-08 | PRINT (unlogged at the time, reconstructed): e012 ×2 on the AltaLink from the 012.2 bundle (member sha re-verified); sheet A scanned same evening on the NEW Canon flatbed (protocol deviation: pre-characterization; grey, descreen/sharpen OFF) | scans/xerox-e012-A-canon-1200.png | d1c9af81acf6af167a28523c425869e208bd18d7e7a3115219d9901331e6ddb4 |
| 012.3 | 2026-07-08 | Canon 2400 dpi grey scan, same sheet A, re-placed | scans/xerox-e012-A-canon-2400bw.png | 814701382f1c7a6b66be3d0e0f81ef026acf910e84ead68251b2b162392c031e |
| 012.3 | 2026-07-08 | Canon 4800 dpi grey scan, same sheet A, re-placed (8 px/dot) | scans/xerox-e012-A-canon-4800.tiff | 2d0c5a2192492b979d75a90bdb0dddd7b7029fb8f629c6eaacbb4f5dc640b1db |
| 012.3 | 2026-07-09 | Phantom-payload incident (wrong-dtype GT re-derivation → 50% reads) + 3-workflow forensics + RETRACTION of all "paper ≠ build" intermediates; true scoring via score_canon_scans.py: blind 0.64–3.97% BER, envelope PASS on all gates (RESULTS above) | build/e012_scan_report.json | deterministic fields |
| 012.3 | 2026-07-09 | Receiver hardening from forensics: anchor_rounds=0 skip + post-fold word-certification gate + tests/test_acquire_gates.py; adversarially reviewed; suite 228 green | src/paperholo/acquire.py | — |

## Addendum 2026-10-11 — the office print, re-read

From the genesis and office-machine reads of 2026-10-10 (evidence line,
docs/EVIDENCE-ARCHIVE-2026-10-08.md §8a). The 2026-07-08 office print bundle
was built between 15:43 and 15:56 CEST; e012 was printed between 15:56 and
about 20:02 CEST (the earliest e012 Canon scan file on machine 1,
`scans/xerox-e012-A-canon-1200.png`, mtime 20:02:19 CEST; the genesis
read's figure of 19:13 carried no time zone). (Corrected 2026-10-13, docs/GENESIS.md §8.6: the 07-08 18:37Z session
listing already shows `xerox-e012-A-7.8-canon-scan-4800.png` dated 19:13
local, a file that did not survive on machine 1; so e012 was home and on the
Canon by 19:13 CEST, and 20:02 is only the earliest surviving file. The
office files beside this log carry the printer's address as found since
`8af69c80`.) The reconstruction above, "via
its sha-gated print_office.sh", is UNCONFIRMED: the script uses `declare -A`
(bash 4), which macOS's bash 3.2 lacks, and the operator's recollection
(2026-10-10, a recollection, not a record) is that office printing very
likely went through `lpr -o raw`. The bundle was built twice: the first
(15:43, without e014) is tarball 9f7c8986…, the one this log cites (012.2);
the second (with e014) is tarball a07479ba…, the one e014 cites. e004, e006bw
and e006c, queued in both, were never printed. (Corrected 2026-10-13 by the owner, from his
printouts: "004 and 006 among many many others were printed both on the HP
and on the office printer with dates around 6.7 - 8.7." See docs/GENESIS.md §4.) Both bundle READMEs
(`README-bundle1.md`, `README-bundle2.md`) and the first bundle's
`print_office.sh` (no e014 in its sha table) are beside this log at
`office-2026-07-08/` (the printer's IP replaced by `<ip>`).
