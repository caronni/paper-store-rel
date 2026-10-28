# E023 — future work (post-v1 qualification)

Recorded 2026-07-15 from design review, qualification forensics, and the
thread that produced the v1 receiver. Decoder-axis only unless noted.
Normative v1 contract: `README.md`. This file is the ranked improvement
backlog and the honest concern register — not a commitment schedule.

## v1 baseline (what we are improving on)

Both footings qualified 2026-07-15 on the frozen v2.2 six-scan e018 states:

| footing | certified | gate (a) wrong | gate (b) yield | emitted BER vs GT |
|---|---|---|---|---|
| decimated 1600 | 741/840 | 0/741 | 629/641 = 98.1% | 1.92% |
| native 4800 | 740/840 | 0/740 | 674/690 = 97.7% | 2.64% |

Staged merge: 657 stage-1 per-scan union + 84 stage-2 cross-scan sum
(vs sum-only 736, best-single 340). Remaining failures are mostly
**coverage-bound at cut lines** (<~70% geometric ⇒ LDPC cliff per 013 F4),
not detection-bound.

---

## Ranked improvements (measured probes on the frozen state)

### 1. Adaptive BP retry at 150 iterations — **promote first**

**Idea:** keep `max_iters=60` for the first attempt; on
`attempted_failed` tiles with `n_informative >= k_eff`, retry decode at
150 iterations.

**Measured win (post-hoc on v1 failures, GT-verified):** +5 decimated,
+6 native tiles, all GT-correct.

**E023b.1 closure (2026-07-16):** the explicit, evidence-addressed retry
certifies +5 tiles on each E023b PAVA footing, all GT-correct, for 51/53 new
decoder calls and 14,731/15,518 iterations. The historical native `+6` was a
probe over E023's different final-union failure set; it is not the result of
E023b's append-prefix scheduler and current-frontier contract. The action is
implemented as `--bp-retry`, has a distinct max-150 ledger profile, and is an
exact no-op after that evidence identity has been tried.

**Why it should work:** e018 tile forensics placed many covered failures
on the r0550 operating cliff (~25% effective BER); most tiles decode in
a handful of iterations — failures are often "BP didn't finish," not
"not enough evidence."

**Concerns:**

- Do not raise the global default (wastes CPU on the ~657 easy stage-1
  certifications).
- Log `n_iters` on the retry path; if 150 is still insufficient, the
  tile is genuinely evidence-limited.
- CRC still the only certificate; retry spends attempt budget (ledgered).

**Effort:** tiny (codec knob + conditional retry in `payloaddec._attempt`).

---

### 2. Held-out-gated context threshold — **best detection lever**

**Idea:** keep per-window PAVA; add a scan/region-pooled monotone offset
`tau[ink_neighbor_count]` indexed by provisional 8-neighbor ink count from
the window's own hard field. Fit `tau` on search-parity pilot labels;
**retain only when validation-parity log-loss improves** (same honesty
doctrine as placement).

**Oracle probe (emitted-cell BER vs GT on frozen state):**

- decimated: 1.918% → 1.303%
- native: 2.644% → 1.889%

**Provenance correction (2026-07-16):** the original post-hoc probe used
qualification-GT central payload values to fit the per-context thresholds
(cross-fitted across odd/even scans). The 1.303%/1.889% variant used
provisional hard neighbor counts, but its threshold targets were still GT
payload labels. These numbers are therefore an oracle ceiling and evidence
that context contains recoverable signal, **not** a blind-legal qualification
of the proposed pilot-trained gate. E023b.1's `ctx-pava-v1` arm is the first
fully specified pilot-only measurement; see
`../023b-integrated-receiver/ALGORITHM-ARMS.md`.

**E023b.1 blind result (2026-07-16):** pilot-only context reduces emitted BER
to 1.351% decimated and 1.876% native, improves weighted validation-pilot log
loss on both footings, and changes certified yield by +7 and +4 respectively.
The decimated net is eight gains minus one lost baseline certificate. Combined
with adaptive BP the net gains are +15 and +10. All certificates are
GT-correct. The profile remains opt-in pending a genuinely independent
capture; native and decimated are two rasterizations of the same scans.

**Why it is cleaner than porting ctx+PAVA:** qualification already
measured the U-shaped context curve — BER 10.7% at 0 ink neighbors,
1.2% at 4, 9.9% at 8 — i.e. white-closure / isolated-ink erosion, not a
GMM problem. This is the right evolution of the registered
"context-binned PAVA" contingency (simpler: one monotone map, not
per-bin isotonic families).

**Concerns:**

- Provisional neighbors from the same window's hard bits can
  self-reinforce (wrong isolated call → wrong neighbors). Cross-fitting
  and scan/region pooling are load-bearing.
- Extreme bins (n=0, n=8) need enough pilot labels per pool.
- Must ship a disable path that is byte-identical when the gate fails.
- May flip marginal tiles to certify without showing up as "recovered
  failure #N" — re-run the coverage/certification curve, not just the
  failure census.

**Effort:** medium (detector extension in `emit_window`, ablation in
`qualify_e023.py`). Label as E023.1, not a silent v1 change.

---

### 3. Small residual scan-subset list — **stage 2.5**

**Idea:** after stage-1 per-scan union, before (or alongside) the full
cross-scan LLR sum, try a **small candidate list** of scan combinations:

- each single scan (stage 1, already done),
- full sum (current stage 2),
- leave-one-out sums (6 attempts for 6 scans),
- optionally 2–3 pairs ranked by held-out pilot log-loss.

**Measured win:** LOO sums recovered 3 failures; exhaustive subset search
only 4 total — **not worth 2^6−1 search**.

**Concerns:**

- Gains are small (3–4 tiles) but CRC-gated and low risk.
- Never drop stage-1 union — one bad scan can poison a blind sum (013
  F3, e023 ablation).
- This is the concrete form of the designed-but-unbuilt pilot-agreement
  per-scan weights.

**Effort:** small (decode scheduling in `decode_union` or a new
`decode_stragglers` pass).

---

### 4. GE erasure fallback — **parked pending threshold battery**

**Idea:** on tiles that fail syndrome after adaptive BP retry, run a
pre-registered confidence→erasure ladder, then exact GF(2) Gaussian
elimination on erasures (hard bits pinned); CRC still certifies.

**Measured win (post-hoc):** 5 failures recovered, all GT-correct; 3
overlap extended-BP wins ⇒ **~2 genuinely complementary**.

**Concerns:**

- Second decision policy on top of PAVA LLRs — threshold mis-set causes
  cascade errors (CRC catches wrong certs, but debugging cost is real).
- README already required a **fresh pre-registered threshold battery**
  before promotion — do not ship from post-hoc tuning alone.
- Net unique gain may be ~2 tiles after overlap with item 1.

**Effort:** medium (new `ldpc` path + frozen threshold table + ablation
row). E023.1 or E023.2.

---

## Radiometry / sampling (design debt, not yet measured as tile wins)

### Pose-aware integration aperture

v1 uses one **scan-axis-aligned** `uniform_filter` (~0.7 cell pitch) per
region crop, then pose-mapped subpixel reads. Pose controls **where** to
sample, not **how** to integrate.

The 0.7 ≈ 1/√2 sizing is a rotation-compromise for a non-rotating kernel
(stay inside one printed cell even at ~45°). It is **not** pose-aligned
integration over the printed cell square.

**When it might matter:** high-angle confetti scraps where scan-aligned
boxes bleed diagonal neighbors. e022/e023 qualified through 44° on
synthetics; real-scrap rotation-dependent BER has not been isolated.

**Cheapest pose-aware step:** per-window oriented box integration on the
raw crop (principal axes from `pose.matrix()`), without full-page rotation.

### PAVA: search/validation split vs all-label refit

v1 fits PAVA on search-parity pilots and uses validation-parity for
log-loss (window ownership + honesty). Validation pilots are **not** used
for the final calibration map.

A defensible upgrade: after ownership is frozen, refit PAVA on **all**
pilot labels for emission (cross-fitted variants exist). Qualification
showed 0 calibration refusals and good held-out log-loss — an unmeasured
small gain, not a proven win.

---

## Architecture items (out of v1 scope)

| Item | Notes |
|---|---|
| **E022↔E023 feedback loop** | Dense-certified-field placement for cut-line slivers; certified-label refit; partial-BCH confirmations. Substrate recorded in v1 (`user_bits` + rate per certified tile). |
| **Volume assembly** | Fountain over `TileOutcome`s — e023 deliberately does not close the archive. |
| **Multi-page / c2 arms** | Design supports; e016 c2 needs e022 c2 window arm first. |
| **`--diag` live viewer** | Shipped 2026-07-15 — see `e023_diag.py`, `run_e023.py --diag`. Per-**scan** refresh (+ union frame); scan-space pane stays with e022. |

---

## Meta-concerns (any promotion)

1. **Single-state overfitting:** items 1–4 were probed on one frozen
   six-scan session with GT verification. Re-qualify on **both footings**
   with gate (a) zero wrong + gate (b) yield.
2. **Overlap accounting:** report unique tile gains, not naive sums
   across improvements.
3. **Coverage floor is real:** items 1–4 will not fix tiles below ~70%
   geometric coverage at r0550 — that is the feedback loop's clientele
   (~15/27 unresolved windows in the sliver census).

---

## Suggested shipping order

1. ~~Adaptive 150 BP retry (item 1)~~ **SHIPPED + QUALIFIED in E023b.1**
2. ~~Context τ with held-out gate (item 2)~~ **SHIPPED + QUALIFIED as
   `ctx-pava-v1` in E023b.1**
3. LOO subset list for stragglers (item 3)
4. GE ladder after pre-registered battery (item 4)
5. Pose-aware aperture / PAVA refit — only if rotation-dependent BER or
   marginal-tile census justifies the complexity

The native/decimated complementarity discovered after items 1–2 is now
registered separately as the design-only E023c scale-space receiver:
[`../023c-scale-space-receiver/README.md`](../023c-scale-space-receiver/README.md).
Its first experiment isolates geometry from sampler/aperture before opening a
larger algorithm search.
