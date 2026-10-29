# PORT BRIEF — the durable discovery root

| | |
|---|---|
| Capability | The durable discovery root: envelope, branch schemas, migrations, decoder-call census |
| Status | **archived-for-port** |
| Ruling reference | Proposed, awaiting Gate B: `RULINGS-holo1-draft.md` → `fields-discovery-continuation-operator-18`. The recommendation there is *archive for later port*; this brief is written so the ruling has something to accept or decline. |
| Map row | `HOLO1-MAP.md` → `fields-discovery-continuation-operator-18` (ABSENT) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF — the durable discovery root.
WHAT IT DOES. Holds one discovery round on disk — the envelope, the candidate branches, the survey facts and the status — so a discovery run can be resumed and validated rather than restarted.
INPUTS. The discovery request (captures, candidate rows, envelope) and the branches' own session states. OUTPUTS. One durable root with a schema version, an authoritative digest, a status, and a validation verdict.
WHERE THE CODE LIVES TODAY. src/holo/receive/discovery_state.py: schema and migrations :36-47, the state shape :97-140, validation :201-254, digest, save and load :255-366.
WHERE IT ATTACHES IN HOLO3. src/holo/receiver/snapshot.py is the nearest object, but the shapes differ: holo3's snapshot is a flat fact set, not a tree of sessions.
A port would most likely be a small sidecar next to the run dir naming the candidate rows, the envelope and one snapshot path per branch — not an extension of the fact snapshot.
INVARIANTS TO CARRY. Additive migration only, never rewriting a stored value.
Validation must be able to say WHICH clause failed. A discovery state is a short-lived identification artefact and stays outside any resume-forgiveness rule, however permissive the receiver becomes about ordinary snapshots.
SIZE. 395 lines, most of it validation clauses that a holo3 port would rewrite against holo3's own fact model rather than translate.
WHAT EVIDENCE WOULD SHOW IT PAID. The only honest measure is operator time: a discovery run that resumes rather than restarts saves the N-branch survey and cold placement it already paid for. Measurable once row 15's wrapper exists, from the run's own job counts.
TESTS. The v1 discovery lanes under tests/holo are the only executable record of the validation clauses; name them in PRESERVATION before the tree goes, since the clauses are the part worth keeping.
DEPENDENCY. Do not build this before rows 15-17; alone it stores nothing.

