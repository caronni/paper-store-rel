# Close-state port — the frozen spec (2026-08-29 night, both sessions agreed)

BASE: holo3 @ 9a15a51 (cell-class law landed). RULING CHANGE
(Germano, 2026-08-29 late): NO MERGE of f79e25c — read it, review it,
and NARROWLY apply only the needful, together with the P3-1 carry.
The interim batch-counting shape (d427dce's per-consult
close_count_progress wiring in engine.py) must NEVER exist on holo3.
Taken from f79e25c (read-only in <checkout>):
(1) conversion_docs/05-fountain.md with its Sec.6 amendment — carry the
file; (2) data.py CloseCheck.blocks_counting + the diag model/server
counting-display hunks (reviewed clean); (3) close_count_progress into
format/close.py AS THE TEST ORACLE ONLY — never called on the consult
path; (4) d427dce's seam-pinning test hunks, adapted; (5) the
conventions-test collection-clock fix. NOT taken: the engine.py batch
wiring; blocks_fresh (dies). holo3-diag stays diverged; paper-c2
rebases their branch onto holo3 after the port lands (coordinated).

PLAN SOURCE: holo3/conversion_docs/05-fountain.md §6 on holo3-diag
(f79e25c) — copy table with holo2/solve/close.py line ranges, engine
seam, test plan. Reference implementation: holo2 commit e638613
(_CloseState, _MetadataGate, close_is_new) + 2b024f0 — copy the
algebra, restyle the state.

SHAPE ("in our style"): a derived monotone close-state cell under the
accessor doctrine — NOT holo2's disposable per-consult _CloseState:
- incremental GF(2) metadata eliminator: one equation absorbed per
  certificate fold; rank-24 word unique; later equations check, never
  revise; contradiction TERMINAL AT FOLD (IntegrityError), replacing
  d427dce's swallow-into-no-rows;
- per-(stream, block) distinct-ESI shortfall counters bumped per fold;
  count-ready = monotone shortfall reaching zero; ZERO payload reads
  before a close attempt;
- VolumeCode built ONCE per stream at metadata-trust (kills the
  per-consult constructions d427dce added);
- close_is_new = the cell's change predicate (solved blocks never
  unsolve; an open attempt improves only when an unsolved block gains
  a distinct symbol or metadata turns terminal);
- ONE metadata authority: the carried decode_metadata called once at
  the trust transition; the per-consult decode in _emit_close_check
  AND the second decode inside close_count_progress both die.

DIAG SEAM (contract with paper-c2, final):
- CloseCheck stays THE close channel, per-consult cadence, shape
  unchanged EXCEPT blocks_fresh DELETED (zero production readers).
- Counting rows (have/needed) come from the incremental counters, free
  per fold; LAZY RANK is a standing ruling — counting rows carry
  have/needed only, rank belongs to solve rows.
- CloseBlockRow.rank -> int | None: counting rows carry rank=None
  (key kept, value null — verified safe against every pane consumer;
  fixes the fabricated rank=0 in the durable report).
- Metadata rank/n_unique ride CloseCheck, NEVER the gauge (one owner
  per number). EngineStat gains exactly one field: consult_cpu_s.
- close_count_progress (d427dce) SURVIVES AS THE TEST ORACLE only —
  the batch computation the incremental state must equal.
- Pane follow-ups (fixture rank spelling, blocks_fresh deletions,
  display-side shortfall sum) are paper-c2's, after I confirm the port.

TESTS (per §6 + this dialogue): new fast module test_h3_close_state.py
porting holo2's 11 close-state tests headed by the PREFIX-EQUIVALENCE
pin (incremental state after folding certs[0..n] equals the batch
close_count_progress/close_count_status on every prefix); engine
contract: CloseProgress stub + the two phase-C gate pins; contradiction
-at-fold pin; close_is_new pins (solved-stays-solved; open improves
only on distinct-symbol gain or metadata terminal).

GATES: byte-identical close results on all sims (mechanisms are exact
— divergence is a bug by definition); fast+slow lanes green; w1
payload+cert identity vs d6-baseline; consult CPU measured before/
after on the colour sim (report the delta); pyflakes.

Provenance lesson (for the intent audit): "pinned to v1" and
"identical to v1" are different claims; and d427dce's "No new cost"
commit-message claim was true pre-metadata-trust only — owned by the
diag session, corrected here.
