# PORT BRIEF — row selection and the format-conflict terminal

| | |
|---|---|
| Capability | Row selection and the format-conflict terminal |
| Status | **archived-for-port** |
| Ruling reference | Proposed, awaiting Gate B: `RULINGS-holo1-draft.md` → `fields-discovery-continuation-operator-17`. The recommendation there is *archive for later port*; this brief is written so the ruling has something to accept or decline. |
| Map row | `HOLO1-MAP.md` → `fields-discovery-continuation-operator-17` (ABSENT) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF — row selection and the format-conflict terminal.
WHAT IT DOES. Turns a set of finished candidate branches into one answer, and refuses loudly when more than one candidate explains the sheet.
INPUTS. The per-candidate branch states of one discovery round. OUTPUTS. A derived selected row id or none; a terminal status when two or more branches hold certificates; a round-completion predicate; a census of CRC decoder invocations.
WHERE THE CODE LIVES TODAY. src/holo/receive/discovery_state.py:178-196 (selection and the terminal), :166-176 (round completion), and the bounded-round driver at src/holo/receive/discovery.py:372-401.
WHERE IT ATTACHES IN HOLO3. Nowhere yet — it belongs to the selection wrapper row 15's brief describes, above N engine runs. holo3's own close (verified against the envelope's embedded sha) is the backstop it complements, not a substitute: the close proves a payload, the terminal proves an identity.
INVARIANTS TO CARRY. Selection is DERIVED from which branches hold certificates, never stored, so it cannot go stale. Exactly one may certify. Do not report a winner before every candidate-and-capture pair is complete or excluded. Publish the decoder-invocation count so the cost of a discovery entry is auditable.
SIZE. About twenty lines of derived predicates, plus the status enum; the cost is in getting the predicates exactly right, not in the code.
WHAT EVIDENCE WOULD SHOW IT PAID. A deliberate conflict test: run discovery over a capture with two registry rows that share geometry and confirm the terminal fires rather than picking one.
That is a sim-lane test, seconds, and it is the only evidence this row can ever have — a fired terminal on real paper would be a format-design failure, not a success.
ORDER. Build with row 15's selection wrapper; it has no meaning without a candidate set.
RISK OF OMITTING. Silent misidentification: a sheet decoded under the wrong row can still produce certificates that fail the close, and without the terminal the operator learns only that 'the close failed', with no reason.

