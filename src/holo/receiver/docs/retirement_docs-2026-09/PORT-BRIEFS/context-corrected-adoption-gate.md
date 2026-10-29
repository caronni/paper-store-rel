# PORT BRIEF — the context-corrected adoption gate (v1's _fixed_detector_logits arm)

| | |
|---|---|
| Capability | The detector the adoption gate scores: context-corrected logits vs marginal logits |
| Status | **PORTED 2026-09-04** on branch `rt/d3-context-gate` — `src/holo/receiver/plugins/refine.py:context_logits` behind `--refine-gate {context,marginal}`, default context. The brief below is the pre-port record; the landing note is in `RULINGS.md` D3. |
| Ruling reference | Proposed, awaiting Gate B: `RULINGS-holo1-draft.md` → `refinement-03`. The recommendation there is *archive for later port*; this brief is written so the ruling has something to accept or decline. |
| Map row | `HOLO1-MAP.md` → `refinement-03` (DIVERGED) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF — the context-corrected adoption gate (v1's _fixed_detector_logits arm)
WHAT IT DOES. Makes the refinement adoption gate score the same detector the decoder will actually read with. On a window whose region context has
been adopted, the provisional ink decisions are re-binned by neighbour count for the candidate pose's own cells and the region's adopted per-bin
offsets are added to the marginal LLR before the held-out logloss is computed, for the baseline and every candidate alike.
INPUTS. The window's marginal PAVA fit (knots, probs), its page cells, the region's adopted context offsets, and the candidate pose.
OUTPUTS. A per-cell logit vector; nothing durable — it changes only base_loss/candidate_loss and hence the adopt/refuse bit and the winning candidate.
WHERE IT LIVES TODAY. src/holo/receive/certified_refine.py:702-715 (the arm), :800 and :902 (its two call sites), :284-291 (the constructor refusal
that makes it mandatory once a ctx profile exists). The binning helper it needs is already in both trees: v1 detect.context_neighbour_counts, holo3
src/holo/receiver/plugins/calibrate.py:441-460.
WHERE IT WOULD ATTACH IN HOLO3. src/holo/receiver/plugins/refine.py:439-441 — logits_of becomes conditional on the region's standing RegionCtx, which the refine
row would have to read (a new declared read on the region ctx key, alongside the existing KEY_EVIDENCE_FIT/READ at :628-633). The colour lane's
analogue is src/holo/receiver/plugins/color_refine.py, which has no context head and is out of scope. The equivalent already exists downstream at
src/holo/receiver/plugins/calibrate.py:520-529 (apply_standing_context), so the port is mostly wiring, not new numerics.
WHAT EVIDENCE WOULD SHOW IT PAID. Two sim decodes (K and colour, src/holo/receiver/tests/_h3_sims.py) plus the crop batteries' still-missing tiles, run with the
arm on and off: a strict superset of certificates with no wrong certificate, or an adoption-flip count that moves at least one tile. The 2.5x wall
tripwire is the cost bar. Without refinement-16's events the flips are invisible, so this port should be sequenced after that one.

