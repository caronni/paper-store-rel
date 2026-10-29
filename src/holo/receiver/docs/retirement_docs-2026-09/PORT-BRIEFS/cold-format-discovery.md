# PORT BRIEF — cold format discovery (holo1 discovery.py + discovery_state.py)

| | |
|---|---|
| Capability | Discovery-first receive: receiver-wide orchestration over isolated exact-row branches |
| Status | **archived-for-port** |
| Ruling reference | **Ruled.** claude-plan.md §12 item 3 (Germano, 2026-09-02): cold format discovery — archive for later port / re-implementation. The same route is open to any other capability the maps show worth keeping. See `RULINGS-holo1-draft.md` → *Already ruled* → `fields-discovery-continuation-operator-15`. |
| Map row | `HOLO1-MAP.md` → `fields-discovery-continuation-operator-15` (ABSENT) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF — cold format discovery (holo1 discovery.py + discovery_state.py).
WHAT IT DOES. Given only captures, finds which registered printed format a sheet is, by running one isolated decode branch per candidate row and requiring exactly one to certify.
INPUTS. Scan paths with declared dpi; optionally a --printer narrowing; the registry's row domain. OUTPUTS. A selected row id (or a refusal), the per-branch session states, a decoder-invocation census, and a durable root that can be resumed.
WHERE THE CODE LIVES TODAY. src/holo/receive/discovery.py (860 lines: DiscoveryReceiveRequest :59-99, _candidate_layout :147-175, _new_state :221-252, run_discovery_receive :420) and src/holo/receive/discovery_state.py (395 lines: schema 12 and its migrations :36-47, survey and exclusion :57-67 / :148-164, selection and the conflict terminal :178-196, round completion :166-176, validation :201-254, digest and IO :255-366).
Entry point src/holo/cli.py:456-473. Tests: the discovery lanes under tests/holo; freeze their names in PRESERVATION before deletion.
WHAT IT WOULD ATTACH TO IN HOLO3. (1) Candidate enumeration — src/holo/receiver/format/identity.py already totals over L:/legacy/catalog/v2 refs and holds the fourteen fossils, so the row domain is a missing FUNCTION, not missing data.
(2) Per-candidate isolation — holo3's engine builds one store bound to one FormatRow, so a port is N engine runs plus a selection wrapper, not a format dimension inside the store. (3) The shared hypothesis envelope — holo3 prices the page domain per format row (docs/PAGE-DOMAIN.md §5), so a cross-row envelope is the one genuinely new object. (4) The entry point — src/holo/receiver/cli.py:56-58 is where 'format identity required' is raised today.
WHAT MUST NOT BE SIMPLIFIED. 'The first row that certifies wins' is a weaker and less safe receiver than 'exactly one row may certify' (row 17). Carry the conflict terminal, the round-completion rule and the decoder census.
ORDER. Build it after rows 16-18, which are its parts: the exclusion narrows the list, the terminal decides the answer, the root makes it resumable.
WHAT EVIDENCE WOULD SHOW IT PAID. There is none today (ARTEFACTS.md G-14). The port should be gated on a measured number it can generate cheaply: on one archived capture whose row is known, the cost of a discovery-first entry against the told entry, and the number of candidates the cell-family vote excludes before any address word is decoded. Both are minutes on holo3's sim lanes.
SIZE. 1,255 lines across two modules, plus the CLI branch; no production dependency outside src/holo/receive, so it lifts cleanly.
COST SHAPE. Roughly N times the survey and cold-placement cost, minus whatever the cell vote excludes; the branches share nothing but the envelope. Discovery states stay outside any resume-forgiveness rule — they are short-lived identification artefacts, not archives.

