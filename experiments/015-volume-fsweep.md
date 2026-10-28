# Experiment 015 — the R2 f-sweep: multi-page holographic recovery (Layer 4, sim, zero print)

**2026-07-08.** First measurement of the archive's defining property (DESIGN
R2): an 8-page layout_version-3 volume, sampled as blind fragments, decodes
EXACTLY from a sufficient area fraction — any fragments, any pages, any
order. Layer 4 = paperholo.fountain (fountain-v1: systematic dense
random-linear fountain over GF(2), geometric ESI, GE decode; the DECLARED
RaptorQ stand-in — docs/FOUNTAIN-DESIGN.md). Harness analyze_e015.py
(--quick 248 s / full 265 s); report build/e015_report.json. Suite 226.

## Setup

8 pages × 600×600 cells (c3, v3 pilots), r0550 (the fragment rung, 013/F4),
S = 2090 bits/symbol, 81 interior tiles/page = 648 symbols, data 93 KB
filled to K/N = 357/648 = **0.551**. Pages sim'd with distinct print/scan
seeds; fragments = 72 disjoint 200×200-cell slots (25.4 mm), each
independently rot90'd and acquired FULLY BLIND (pilot counter identifies
page + tile; no headers anywhere). Slot acquisition: **71/72** (one edge
slot failed Stage 0 — the known small-fragment pitch item).

## RESULTS

**f-sweep (25 trials/point; success = byte-exact volume recovery):**

| f (area) | slots | success | median unique symbols (need 357) |
|---|---|---|---|
| 0.44–0.61 | 32–44 | 0/25 each | 229–310 |
| 0.67 | 48 | 0/25 | 343 |
| **0.78** | **56** | **25/25** | **402** |
| 0.89–1.00 | 64–72 | 25/25 | 459–516 |

**Measured threshold f\* ≈ 0.70–0.78** vs the ideal R2 bound K/N = 0.551.
The whole gap is accounted for by the **fragment-boundary symbol yield**:
25.4 mm slots certify 516/648 = 79.6% of printed symbols at full coverage
(tiles straddling un-selected slot boundaries lose their coverage; the
union recovers a straddled tile only when both neighbors are drawn).
Predicted threshold from yield alone: 0.551/0.796 = 0.69 — the transition
sits exactly there. The fountain itself contributes ~0 overhead (GE needs
K+~2; success flips where median symbols cross K). Levers that move f\*
toward K/N: larger fragments (yield → 1), whole-sheet recovery, certified-
tile feedback (F4/F10), multi-scan.

**Lost-whole-pages variant:** exact recovery from **6 of 8 pages** (399
symbols); insufficient at 5 (329 < 357) — consistent with the same yield
arithmetic (the "pages" here are still slot-partitioned; whole-page scans
would recover at 5 of 8). Rateless growth and source-first layout verified
in tests (repair pages addable later without re-encode).

**Integrity:** wrong-payload certifications **0** across the entire run
(every certified tile cross-checked against encode GT); the one failed slot
failed cleanly. Codec-level (from the L4 build, tests): overhead curve at
K/K+2/K+5/K+16 = 29.5/77.5/97.5/100% — matches random-matrix theory to a
point; GE 5,098 symbols/s at K=4096.

## Caveats

- Sim-only; fragments are crops of per-page scans (shared within-page warp
  — placement diversity under-modeled; per-fragment platen placement is a
  hardware question). Footing: geometry=True, fully blind, r0550.
- The analyzer's "certified tile results" console line sums per-slot
  duplicates (straddled tiles certified from two slots); unique-symbol
  counts are the honest currency (patched to print both going forward).
- f is measured in slot-area units over PRINTED area; K/N is the design
  dial: lower fill ⇒ lower f\*, linearly.

## Durable artifacts

src/paperholo/fountain.py (+ tests/test_fountain{,_roundtrip}.py — incl.
the FIRST full-stack blind recovery: modulation → pilots → LDPC → fountain,
2-page volume, one page rotated, byte-exact); docs/FOUNTAIN-DESIGN.md v0.1;
experiments/015-volume-fsweep/{analyze_e015.py, build/e015_report.json}.

## Next (M3 residue)

Whole-page-scan f-sweep variant (yield ~1 ⇒ f\* ≈ K/N directly); mixed-rate
volumes (r0700 data pages + r0550 repair pages); in-band volume-descriptor
replication (edge tiles); sub-symbol packing to reclaim the 2.6% inert
loss; RFC 6330 as a registry swap if ever warranted.

| run | date | action | artifact | sha256 |
|---|---|---|---|---|
| 015.0 | 2026-07-08 | analyze_e015.py full (f-sweep + lost-pages + F9) | build/e015_report.json | deterministic mod timings |
