# PORT BRIEF — refinement lineage (certificate-to-adoption attribution)

| | |
|---|---|
| Capability | Certificate/pose dependency lineage on refined poses and blocks |
| Status | **archived-for-port** |
| Ruling reference | Proposed, awaiting Gate B: `RULINGS-holo1-draft.md` → `refinement-07`. The recommendation there is *archive for later port*; this brief is written so the ruling has something to accept or decline. |
| Map row | `HOLO1-MAP.md` → `refinement-07` (ABSENT) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF — refinement lineage (certificate-to-adoption attribution)
WHAT IT DOES. Makes it possible to say, after a run, which certificates a given refined pose was fitted from and which certificates that refinement
subsequently enabled. It is the machinery behind every per-volume attribution in GAPS.md.
INPUTS. The certificate set a fit consulted (holo3 already has it: Revision.basis, holo3/plugins/refine.py:509 and color_refine.py:348) and the pose
generation in force when an attempt ran.
OUTPUTS. Two durable edges: adoption -> basis (forward, already half-present) and certificate -> enabling adoption (reverse, entirely absent).
WHERE IT LIVES TODAY. v1: src/holo/receive/certified_refine.py:334-337 (SegmentLabels.dependency_certificate_ids), :103-172 (frontier_id via
dependency_identity), src/holo/receive/production_refine.py:141-143 and :310-318 (the pose and block lineage union). Tests: the v1 refinement suite
under tests/holo covering the frontier identity and the mint.
WHERE IT WOULD ATTACH IN HOLO3. Forward edge: the RefineOutcome adoption event proposed in refinement-16 carries the basis tuple — no schema change,
just a field on a new event. Reverse edge: holo3/data.py's AttemptFact and Certificate gain a pose-generation stamp (store.pose_generation already
exists, holo3/store.py:225-226, and place_sched.py:72 already puts the generation in an anchor id), and the store folds it; the certificate then names
the pose generation it was read under, and the adoption events say when each generation began.
WHAT EVIDENCE WOULD SHOW IT PAID. Re-running the GAPS.md comparison on a holo3 run dir and getting a number where today there is only inference: the
refinement-driven share of certificates on xerox K and on one colour volume, and a direct answer to GAP G-10 (why refinement did not reach the five
column-0 rows). It pays in forensics, not certificates; the bar is that ARTEFACTS GAP G-10, G-11 and G-22 become answerable rather than permanently
open.

