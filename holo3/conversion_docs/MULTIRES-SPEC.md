# Multi-resolution intake — the frozen spec (2026-08-30, from archaeology)

RULING (verbatim): "do the multi-dimension intake, with high fidelity,
following carefully what holov1 and holov2 allow and do with it, use
right sized workers, and verify the work carefully."

Archaeology of record: workflow wf_f32486e4-40d (both readers, file:line
evidence). Decisive facts:
- v1 ACCEPTS mixed-DPI captures by design: per-scan --scan-dpi
  (append, required, "TRUE scanner dpi ... never guessed"), per-capture
  CaptureFacts/scale plans, SessionState has NO dpi field. The
  "one state freezes one DPI" invariant is legacy paperholo; in v1 it
  survives ONLY as per-capture immutability (same source sha may never
  be re-declared at a different dpi — CaptureConflictError; holo2's Q2
  refusal is the same law, fatal, by name).
- holo3's cli.py:67 mixed-DPI refusal has NO ancestor in either tree —
  an invented guard. It dies.
- v1 pairs cross-capture evidence by LANE-ID STRING equality
  (evidence_lane_id; same lane id + different source sha; own-capture
  excluded by key[0] != sha). holo2 pairs by EXACT RATIONAL ppc
  (union_tags: ppc values where >=2 DISTINCT capture shas observed the
  key; own-capture exclusion STRUCTURAL — strictly-ascending ladder =>
  one footing per ppc per capture; a single-capture ppc mints no
  descriptor at all).
- Ladders are per capture from its OWN dpi (both trees, same
  algorithm): floor 2 ppc, ~doubling preferring integer native box
  factors, native exactly once last, never upsample, GENERAL RATIONALS
  (1600 dpi -> 8/3, 16/3 ppc). Ladders are NOT nested (c3@1200 {2,3,6}
  vs c3@2400 {2,4,6,12}: shared {2,6}); only ppc 2 is guaranteed
  shared above the floor; sub-2ppc captures get a single native rung
  and may share NOTHING (legal; certificate-only interaction; no
  warning in v1 — holo3 SHOULD advisory-note it, report-only).
- holo2's reading set decides whether a mixed pair combines at all
  (READING_ALL unions at shared rungs; FINEST-only never meets).
  holo3 reads all rungs => READING_ALL semantics, stated.
- Mixed-DPI union is DESIGNED BUT UNEXERCISED in holo2 (every fixture
  one dpi; ledger row 51: union on paper unmeasured) and has never run
  on paper in any tree (all paper multi-capture runs were uniform).

## The law holo3 adopts

PAIRING BY EXACT RATIONAL ppc (holo2's law — cleaner than v1's
label-string coupling, provably equivalent where both define pairing):
- Internal lane keys stay (capture_id, level_index); the CROSS-CAPTURE
  join maps level -> ppc through the capture's own ladder
  (Fraction-exact; equality never closeness).
- tiles.union subjects become (tile x ppc): minted ONLY where >=2
  DISTINCT captures hold evidence at that exact ppc; a ppc reached by
  one capture mints no union subject (structural own-capture safety:
  one lane per ppc per capture, ascending ladder invariant asserted at
  intake).
- A capture's finer-than-shared rungs still contribute through its OWN
  scan/retry lanes (per capture-level, unchanged); no supplemental
  arms required for that.

INTAKE:
- cli.py:67 guard replaced by: count gate (n scans == n dpis, exists),
  finite/positive dpi (exists), and the Q2 law — the SAME source sha
  declared twice in one run with DIFFERENT dpi is a fatal refusal by
  name (both values printed); identical (sha, dpi) duplicate stays the
  existing duplicate-capture drop with its CaptureOpen(duplicate) event.
- Per-capture ladder from its own declared dpi (verify holo3's
  auto_ppc_levels matches the v1/v2 schedule EXACTLY — the drift
  corpus pinned c2/c3 ladders; add the non-dyadic pins: c2@1600 ->
  (2, 8/3, 16/3)).
- Audit every code site assuming one run-wide dpi (the request field,
  survey pitch snapping per capture at ITS dpi, diag capture rows).

PRESERVED REFUSAL CLASSES: misdeclared-dpi survey snap (per capture at
its own declared dpi); no upsampling; resolution unchanged elsewhere.

## Gates (the build's definition of done)

1. UNIFORM-RUN BYTE-IDENTITY: every existing decode unchanged — both
   sims w1 --complete payload+cert-set identical to d6-baseline, w8
   payloads identical, degraded sim goldens unmoved, churn goldens
   unmoved. On uniform runs level-ordinal and ppc keying are bijective;
   any drift is a bug.
2. MIXED SIM (new, in the sim fixture family): ONE emitted page, two
   captures with shared GT — capture A at the sim's native class,
   capture B the same render area-decimated 2:1 and declared at half
   dpi (deterministic, sha-pinned). E2E pins: decode VERIFIED
   byte-exact; union subjects exist exactly at the shared ppc set;
   certificates fed by both captures (assert via per-plugin/source
   accounting); workers 1 == 8 payload identity.
3. UNIT PINS: exact-rational pairing (8/3 == 8/3, 8/3 != 2.6667...);
   single-capture ppc mints no union subject; same-sha-two-dpis fatal
   refusal with both values in the message; disjoint-ladder capture
   ingests legally, unions nothing, advisory line names it;
   ascending-ladder invariant.
4. Fast lane <= budget, slow lane green, pyflakes clean; derived
   schedule table re-rendered if the union row's subject vocabulary
   line changes (deliberate golden update).
5. ADVERSARIAL VERIFY (separate worker): recount every claim in the
   build commit against the tree; re-run gates independently; hunt the
   specimen classes (phantom tests, unverified body claims).

ACCEPTANCE (after gates, when the machine is free, user-visible):
sheet H 1200-a/b + 2400-a/b in ONE run — the first measured mixed-DPI
union on paper in any generation. Expectations: unions at the shared
ppc set (4 and 2 for c2-class at these dpis... derive from the r0850
pitch class exactly in the report), certificates from all four
captures, byte-exact close vs the H payload if it closes; NO promotion
talk, existence evidence only.

OUT OF SCOPE (unchanged rulings): supplemental arms for native-fine
rungs; resume; any format change.
