# PORT BRIEF — source re-authentication before a durable write

| | |
|---|---|
| Capability | Per-barrier source re-authentication |
| Status | **archived-for-port** |
| Ruling reference | Proposed, awaiting Gate B: `RULINGS-holo1-draft.md` → `payload-union-retry-intake-24`. The recommendation there is *archive for later port*; this brief is written so the ruling has something to accept or decline. |
| Map row | `HOLO1-MAP.md` → `payload-union-retry-intake-24` (ABSENT) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF — source re-authentication before a durable write
What it does: confirms that the scan file a run is about to attest to is still the file it hashed at ingest, so a snapshot never carries provenance it no longer has. Threat model on record: accidental mutation — an overwritten, re-exported or re-scanned file — not an adversary.
Inputs: the capture's recorded hash and file path, plus the (device, inode, size, modification time) tuple recorded at ingest.
Outputs: pass (the common case, one stat per capture), or a refusal naming the file and the two hashes.
Where its code lives today: src/holo/receive/scan.py:212-255 — the stat memo, the escalation to a full re-hash on any difference, and the refusal.
Where its evidence lives today: docs/PHASED-SCHEDULE.md:535-548 — eight naive re-authentications accounted for a whole 169-second residual, and one hash pass over a 6.8 GB scan costs about 19.1 seconds. That number is the reason the memo exists and must travel with the brief.
Tests today: exercised through v1's session and phased-schedule tests in tests/holo; there is no standalone test file for it.
Where it would attach in holo3: intake already hashes at src/holo/receiver/plugins/intake.py:35/:172/:225 and stores the id on the Capture; the check belongs immediately before the snapshot write in src/holo/receiver/snapshot.py, iterating the declared captures. The memo tuple would be a new field on Capture, recorded at ingest.
What evidence would show it paid: (a) a fixture where a declared file is modified mid-run and the snapshot is refused with the file named; (b) a control on both sims showing zero added wall when nothing changed, proving the memo works; (c) optionally, the memo tuple written into the run manifest so a later reader of a resume chain can see whether any scan changed between runs.
Why archived rather than ported now: holo3 keeps no evidence across runs, so a changed file damages only the current run's provenance record, not a retained store. The loss is real but bounded, and nothing on the archived corpus is affected.

