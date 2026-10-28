# PORT BRIEF — cell-family exclusion from the native survey vote

| | |
|---|---|
| Capability | Native E021 `c` vote as a cell-family exclusion |
| Status | **archived-for-port** |
| Ruling reference | Proposed, awaiting Gate B: `RULINGS-holo1-draft.md` → `fields-discovery-continuation-operator-16`. The recommendation there is *archive for later port*; this brief is written so the ruling has something to accept or decline. |
| Map row | `HOLO1-MAP.md` → `fields-discovery-continuation-operator-16` (ABSENT) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF — cell-family exclusion from the native survey vote.
WHAT IT DOES. Removes format-row candidates that the capture's own printed cell size rules out, before any expensive decoding.
INPUTS. One native-resolution survey per capture (already computed by holo3). OUTPUTS. For each candidate row, an exclusion verdict, plus a validation rule that a branch may not retain an excluded capture.
WHERE THE CODE LIVES TODAY. src/holo/receive/discovery_state.py:57-67 (the vote record), :148-164 (complete-by-exclusion), :245-260 (the validation clause); the survey call at src/holo/receive/discovery.py:349.
WHERE IT ATTACHES IN HOLO3. holo3/plugins/survey.py:701-710 already votes a printed pitch and raises on disagreement with the declared row.
A port keeps the measurement untouched and changes only what disagreement MEANS: today a refusal, in a discovery run an exclusion. The candidate list itself comes from row 15's missing row-domain function over holo3/format/identity.py.
INVARIANTS TO CARRY. The vote may only EXCLUDE, never select — a surviving row still earns its place by certifying. A capture with no vote excludes nothing. A branch that kept an excluded capture is invalid.
SIZE. Tens of lines; the expensive half — the native survey — is already built and running on holo3.
WHAT EVIDENCE WOULD SHOW IT PAID. The count of candidates excluded per capture on one archived sheet, against the registry's full row domain, and the survey-and-placement cost that count avoids. Measurable on existing captures once row 15's wrapper exists; no new scan.
ORDER. First of the discovery parts to build: it is the cheapest and it bounds the cost of everything after it.
RISK. Low: it is a pure narrowing of work with no effect on what certifies, and holo3's existing refusal is the same comparison at a stricter setting.

