# PORT BRIEF - refinement evidence namespacing (v1's `evidence_lane_id`)

| | |
|---|---|
| Capability | Refinement levels own their OWN evidence namespace (only certificates cross lanes) vs in-place evidence supersession |
| Status | **archived-for-port** |
| Ruling reference | Proposed, awaiting Gate B: `RULINGS-holo1-draft.md` → `scheduling-06`. The recommendation there is *archive for later port*; this brief is written so the ruling has something to accept or decline. |
| Map row | `HOLO1-MAP.md` → `scheduling-06` (CARRIED-DIFFERENT) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF - refinement evidence namespacing (v1's `evidence_lane_id`)
WHAT IT DOES: lets more than one read of the same window coexist, so a refined re-read cannot destroy the base read it was meant to improve on, and so the payload rows may use either.
The rule it enforces: only certificates cross between reads; soft evidence never does, because LLRs from correlated views must not be summed.
INPUTS: a window's committed pose, plus a refinement's revised pose for that same window.
OUTPUTS: a second, separately addressed evidence record - its own blocks, attempts, divergences and quarantine - with the base record left intact and still usable by the payload rows.
WHERE ITS CODE LIVES TODAY: src/holo/receive/cascade.py:319-336 (the refinement-level constructor that sets `evidence_lane_id` to its own lane id).
Also src/holo/receive/types.py:259-267 (the field and its contract) and src/holo/receive/production.py:644-671 (the consumer that lets certificates cross lanes while evidence does not).
WHERE ITS TESTS AND RECORD LIVE: no dedicated test names the invariant. The record is docs/PAYLOAD-MEASUREMENTS.md:288-291, the R-lane qualification - default flags 1,166 s CPU, 601 certificates, 95 windows parked across 8 mop-up lanes.
That thinness is itself a reason to write the brief: the capability is carried by prose and one measurement, and both leave with the tree.
WHAT IT WOULD ATTACH TO IN HOLO3: `_fold_evidence` (src/holo/receiver/store.py:702-748), today one mutable cell keyed by window id, reached from an adopted revision via plugins/refine.py:512-514 -> store.py:787-801.
Minimal shape: a generation key on that cell, plus a reader rule saying which generation each consumer cuts from at fire time.
Fuller shape: the same key also buys union across refinement generations, which holo3 cannot express at all today.
Note the pose side would need the same treatment - src/holo/receiver/data.py:118-120 ranks a refine-route pose above the base pose on its first term regardless of quality, so the base pose is unrecoverable too.
WHAT EVIDENCE WOULD SHOW IT PAID: on any volume where refinement actually adopts, the certificate set after adoption is a strict SUPERSET of the set before it.
That is untestable on paper today - zero adoptions on every archived volume - but testable now on the colour sim refinement lane at src/holo/receiver/docs/SCHEDULE.md:426-436, which adopts 2 of 14 fires.
WHY IT MATTERS LATER: about half the certificates on two archived colour sheets carry refinement lineage (src/holo/receiver/docs/conversion_docs/GAPS.md:405-422).
The moment holo3's refinement starts adopting - which the debt rows at src/holo/receiver/docs/SCHEDULE.md:105-124 exist to make happen - this is the protection that decides whether those tiles are gained or traded away.

