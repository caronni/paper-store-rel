# PORT BRIEF - the two-loser ledger (runner-up hints)

| | |
|---|---|
| Capability | The two-loser ledger (runner-up hints) |
| Status | **archived-for-port** |
| Ruling reference | Proposed, awaiting Gate B: `RULINGS-holo1-draft.md` → `k-placement-18`. The recommendation there is *archive for later port*; this brief is written so the ruling has something to accept or decline. |
| Map row | `HOLO1-MAP.md` → `k-placement-18` (ABSENT) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF - the two-loser ledger (runner-up hints).
What it does: when a window fails to place, it keeps the single best hypothesis it found - the one that passed the decode gates but missed a parity bar - as continuation geometry, so a smaller, finer or later window covering the same paper can start from that near-miss instead of from nothing.
Inputs: the refusing window's best candidate score (page, origin, rotation, held-out mismatch, search mismatch, support). Outputs: a ranked, capped per-region set of loser hypotheses offered to later windows below every committed pose.
Where the code lives today: src/holo/receive/place.py:92-93 (the two constants LOWER_RUNNERS_PER_REGION and LOWER_RUNNER_UP_RESERVE), place.py:306-343 (the ranking and the cap), place.py:1101-1132 (the harvest at refusal), place.py:147-182 (the reserved slots inside the 8-hint portfolio), place.py:1692-1695 (the carry to the mop-up level).
Tests today: none isolate it; it is exercised only through v1's placement path. Its one measurement is holo2's loser census, holo2/docs/kparity/K-PARITY-STATE.md:69-75.
Where it would attach in holo3: a LoserHypothesis fact folded into the store alongside LatticeSeed (holo3/store.py:690-700 is the pattern), surfaced through place_sched.consult_seeds (holo3/plugins/place_sched.py:76-92) ranked strictly below every committed pose, and charged to the window's tried set like any other seed (holo3/plugins/place.py:719-721). It needs no new pixel path and no format change.
Cap it the way v1 does - two per region - so it cannot flood the 8-slot consult.
What evidence would show it paid: on a fragment or confetti sheet (sheet J is the live candidate), the certificate count with the tier on against the same tree with it off, plus a counter of how many placements were seeded by a loser. On a dense sheet the expected delta is zero and that is the null control.
What would show it must not be built: a repeat of the dense-sheet census - loser hints that only ever anchor already-certified ground - or a measured increase in wrong certificates, which would be disqualifying on its own.
Risk if ported carelessly: a loser is by construction a hypothesis that failed a bar, so it must never be allowed to supersede a committed pose in the consult ordering, and it must never seed a lattice.
Scope: K placement only as written; nothing in it is colour-specific, and it would apply unchanged to every family.
Interaction to check at port time: holo3 charges every offered seed to the window tried set (holo3/plugins/place.py:719-721), so loser seeds would raise the tried count and, in principle, the support floor. Row 11 shows the floor cannot leave 30 below about 5,100 tried candidates, so two losers per region are free - but that bound should be re-checked if the cap is ever raised.
Prerequisite: holo3 currently computes runner-ups and drops them (holo3/plugins/pose.py:112-118), so the data already exists at the refusal site; the port is a fact, a fold and a consult ordering, not a new measurement path.
Do not bundle this with the retirement mechanics. It is its own gated line: design note, go, worktree build, measured record on sheet J plus a dense-sheet null, review.

