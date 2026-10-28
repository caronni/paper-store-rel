# Experiment 011 — PILOT-SIM-1: the M1 pilot system, end to end in simulation

**2026-07-08. Zero print.** First full implementation + sim measurement of the
L2 pilot system (DESIGN §5.2a, PILOTS-DESIGN v0.2): p60b6.v2 site lattice,
BCH-coded window addressing, `compose_page`, and a fully blind receiver
(lattice lock → site-phase search → address decode → pilot-anchored warp →
payload), gated by ghostscript as the printer RIP and the frozen M0 measured
channel. This is PILOTS-DESIGN's M-P1 (and the sim half of M-P6's motivation),
pulled forward and executed.

## What was built (all in `src/paperholo/`, suite 161 green)

| module | contents |
|---|---|
| `bch.py` | binary BCH(127,64,t=10) over GF(2^7) (prim 0x89), shortened to (100,37); BM + Chien; vectorized syndromes; **CORRECTED from PILOTS-DESIGN v0.1 §6.2** — the spec'd (127,36,t=15)→(100,36) is arithmetically impossible (shortening reduces k; (100,36,d≥31) exceeds best-known-code bounds) |
| `pilots.py` (v2 append) | `PilotLayout` p60b6.v2 (exactly 1/36, labels `pilot-sites-v2` / `pilot-values-v2/<plane>`), 36-bit message packing [lay:4|plane:2|page:18|ty:6|tx:6] + 1 pad bit, `encode_word`/`decode_word` (site-local ks_P scramble — the circularity fix), `coordinate_code` stub REPLACED. v1 pattern untouched |
| `compose.py` | `ComposeSpec`/`compose_page`/`extract_payload`/`payload_index_map`/`emit_composed`: payload bits → non-pilot cells in raster order XOR full-page keystream at absolute coords (== encodings binary convention, tested); pilot cells = word bits as ordinary c3 cells; single K imagemask; archive-style page (NO header/sentinel/marks — R3) |
| `acquire.py` | blind receiver: tiled gradient-FFT lattice lock w/ separable phase profiles + DD refinement (Stage 0); 3600-site-phase × rot90 (× mirror) search with BCH gate at t_acq=8 (Stage A); cross-tile word validation ≥0.85 over ≥30 sites, per-tile rates = slip diagnostics (Stage B); **pilot-word slip-vote layer** (±1-cell integer slips repaired by voting expected word bits under shifts — template anchors measurably cannot do this: confidently-wrong halo cells drag NCC to zero); sub-cell pilot anchors (2 rounds); coverage-trimmed payload extraction |
| `experiments/011-pilot-roundtrip/` | `gen_e011.py` (sha-gated A4 page: 2220×1500 cells kcell-c3 K, 925 word tiles, capacity 3,237,500 bits) + `analyze_e011.py` (RIP gate + footing gap + grain sweep + multi-scan probe + R3 spectrum → `build/e011_report.json`) |

**Format freeze:** layout_version 2, pinned by `tests/test_format_v2_golden.py`
(site-array sha `56696eec…`, one full word vector, generator-poly sha, page
sha `742c0358543485c6aec193ae4d90b3ed8c8ae94caa879c3728f225ed6e9a58bc`). A
failing golden test means the printed format changed: bump layout_version,
never edit the anchor. Payload derivation frozen as
`rng(SEED, b"e011/payload").integers(0, 2, capacity, dtype=np.uint8)`.

## Protocol ("gs as the printer")

`compose_page` → `build/e011.ps` → `gs -sDEVICE=pnggray -r600` → **RIP gate:
render must equal the composed bitmap pixel-exactly (measured: 0 differing
dots over 4500×6660)** → windows of the RIP output through the frozen M281
simulator (`geometry=True`, split print/scan seeds) → harness-applied crop +
rot90 (the sim itself has no global offset) → `acquire_and_decode`, fully
blind (inputs: image, public spec constants, seed). Footing baseline =
`geometry=False` with the SAME detector (detector-matched). Every decode
carries the shifted-GT null control (all read 0.49–0.50).

## RESULTS (post-review-fix numbers; suite 161; full run 232 s)

**Footing gap — the headline.** 600×600-cell interior windows, print seeds
{0,1,2}: blind end-to-end payload BER 3.07/3.19/3.39% vs detector-matched
geometry-free footing 1.24–1.25% ⇒ **mean gap +1.97 pp** (pre-fix +2.51).
Address exact, orientation exact, Stage-B match 0.967–0.980, word tiles
80–81/81 at t_full=10. Measured comparators on the same channel family:
strips-alone **+5.8 pp** (006.1), strips+between-strip **+3.4 pp** (007.7) —
**pilot-anchored tracking beats the strip architecture at its first sim
outing, while also delivering absolute addressing + orientation**, at 2.78%
overhead (2.86% per payload bit). Hardware confirmation = PILOT-1 (M-P3).

**Addressing grain curve.** 8 trials/size, random interior position + random
rot90, geometry=True; success = correct absolute address AND orientation:

| fragment | cells | acquired | median payload BER |
|---|---|---|---|
| 10 mm | 79 | 0/8 | — (below grain: a full 60-cell tile fits only by placement luck, ~11%) |
| 13 mm | 102 | 5/8 | 1.53% (placement lottery, rate ≈ combinatorial expectation) |
| 16 mm | 126 | 7/8 | 2.17% (guaranteed-fit starts 15.1 mm; the 1 failure = small-fragment Stage-0 pitch mislock, diagnosed, not an addressing failure) |
| 20/25/40/60 mm | 157–472 | 8/8 each | 1.66/2.66/2.28/2.56% |

Every acquisition had the correct address+orientation (no false accepts
anywhere; wrong seed / wrong plane / blank paper → clean `ok=False`; all 3
wrong rotations rejected by the BCH gate — **orientation resolution is free**).
PILOTS-DESIGN §6.5's ~13 mm guaranteed-grain ESTIMATE → measured 15.1 mm
placement-guaranteed / 13 mm ≈ 60% lottery at c3@600.

**Adversarial warp (sim seed 314, the fast-warp page-edge regime):** acquires
end-to-end; slip tiles correctly diagnosed by per-tile Stage-B rates; payload
5.80% single-scan → **2.12% with 3-scan majority** through the full blind
pipeline (per-scan fresh steps; 004.0b multi-scan lever replicates at L2).

**R3 accounting, quantified:** the 1/60 cyc/cell site-pattern line is the
composed page's global spectral peak at **88× median background** (block line
1/6 at 32×). This is the §10.2/DESIGN §5.2a conceded structure — but "88× line"
is the honest phrasing for the amendment, not "statistically hidden". Values
themselves never repeat (per-tile words), so the concession stays sites-only.

**Review round (same session):** 4-dimension adversarial review → 10 confirmed
findings (0 refuted), all fixed + regression-tested. Load-bearing ones: a
sign-asymmetric slip-fold boundary bug emitting silent ~50%-BER rows (fixed,
worst boundary row 42–50% → 3.6–4.0%); partially-covered edge cells emitted as
payload at 30–50% BER (fixed: blind content-extent trim; coverage now exactly
the complete-cell window); sha-gating had no committed anchor (fixed: golden
test); a fake-words test fallback that could mask a non-decodable page (fixed:
hard requirement). Numbers above are post-fix; nothing regressed.

## Deviations from PILOTS-DESIGN v0.1 (all declared, doc updated to v0.2)

1. **§6.2 code corrected**: BCH(127,64,t=10)→(100,37), t_acq=8 arithmetic
   re-derived (false accept ≈ 2.3e−8/hyp, measured 0/200k random words; and
   0 false accepts across the whole sweep). Consequence: c2-class words are
   WEAKER at t=10 (P(>10 err) ≈ 0.18 at 8% ctx BER) — the robust-mode word
   duplication (M-P6) is now load-bearing for B1, not optional margin.
2. **Stage-B pooling over clean tiles only** (naive all-site pooling vetoes
   correct addresses when a slip band crosses the fragment — measured); slip
   tiles are diagnostics, acceptance still needs ≥30 clean sites + the BCH
   false-accept gate.
3. **Integer slips are repaired by pilot-word voting, not anchors** (anchors
   remain the sub-cell stage). New measured fact: detected-halo template
   anchors CANNOT recover full-cell slips.
4. Composer/receiver details: coverage-trimmed payload (complete cells only),
   `mirrored` first-class in the result, `word_provider` injectable.

## Caveats / footing labels

- Sim-only (M0 frozen M281 model). The known M0 gaps (2-dot-white closure
  attenuation) do not touch c3 pilot fields (trusted regime, 3.56% sim vs
  3.74% hw anchor), but the simulator's r(y)/step statistics remain
  UNVALIDATED against hardware (M0 leftover) — the +1.97 pp gap number is a
  sim claim until PILOT-1.
- Harness rotations are exact rot90; platen skew beyond the lattice
  estimator's tolerance and real flatbed placement are hardware questions.
- geometry=False footing BER (~1.25%) is keystream-content on the RIP page,
  detector-matched — NOT comparable to the 3.74% CAL-1 hard anchor (different
  content, detector, and averaging); only the GAP is the claim.
- Runtime: ~8 s per 600×600-cell window, 0.2–9 s per fragment (unoptimized;
  slip-vote scan is python-loop over sites — fine at fragment scale).

## Durable artifacts

`src/paperholo/{bch,pilots,compose,acquire}.py`; tests
`test_{bch,pilots_v2,e011,acquire_grid,acquire_blind,format_v2_golden}.py`
(161 total suite); `experiments/011-pilot-roundtrip/{gen_e011,analyze_e011}.py`
+ `build/e011_report.json`; PILOTS-DESIGN v0.2. Scan-side: nothing (zero
print).

## Next

- **PILOT-1 (M-P3): the ONE-sheet-per-engine hardware validation** — p60b6
  pilots + strip skeleton on the same sheet, pilot-anchored vs strips vs genie;
  acceptance: within +1 pp of genie on interior bands (sim says +1.97 pp page
  scale incl. edges — the interior-band number should be tighter). Rides the
  next print session with the 007.9 batch.
- M-P6 (c2 duplicated-word combining) — now load-bearing for B1 (deviation 1).
- Small-fragment Stage-0 pitch robustness (the 16 mm 7/8) — decoder-axis
  hardening, no format impact.
- DESIGN.md §5 amendment per PILOTS-DESIGN §11 — staged, awaiting review.

| run | date | action | artifact | sha256 |
|---|---|---|---|---|
| 011.0 | 2026-07-08 | gen_e011.py (layout_version 2) | build/e011.ps | 742c0358543485c6aec193ae4d90b3ed8c8ae94caa879c3728f225ed6e9a58bc |
| 011.0 | 2026-07-08 | analyze_e011.py full sweep (sim, zero print) | build/e011_report.json | (timings nondeterministic; all measured fields deterministic) |
