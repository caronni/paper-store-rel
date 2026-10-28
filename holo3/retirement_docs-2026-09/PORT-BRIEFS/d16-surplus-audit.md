# PORT BRIEF - D16 post-solve surplus audit (advisory localizer for a wrong certificate)

| | |
|---|---|
| Capability | D16 post-solve surplus audit — certified symbols of SOLVED blocks that disagree with the reconstruction |
| Status | **archived-for-port** |
| Ruling reference | Proposed, awaiting Gate B: `RULINGS-holo1-draft.md` → `close-13`. The recommendation there is *archive for later port*; this brief is written so the ruling has something to accept or decline. |
| Map row | `HOLO1-MAP.md` → `close-13` (ABSENT) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF - D16 post-solve surplus audit (advisory localizer for a wrong certificate)
What it does. The GF(2) payload solve consults exactly K independent rows per block and never checks the dependent (surplus) ones. A wrong certified symbol sitting in a dependent row is therefore silently masked - the volume can verify with a bad certificate in it - and a wrong symbol in a pivot row produces an integrity failure that names nothing. The audit re-encodes every certified symbol of every solved block from the solved sources and reports the certificates that disagree.
Inputs. For each decoder that solved: the decoder itself, and the ESI -> certificate map that close_volume already builds while loading symbols. Nothing else; it never re-derives an ESI convention.
Outputs. A tuple of (stream_id, counter, page, ty, tx) rows. Advisory only: never read by status, payload or any gate.
Where its code lives today. src/holo/receive/fountain_close.py:557-594 (_surplus_audit, with the zero-outcome-change bare except at :581-593), the CloseResult field and its type guard at :304-308, the value type at src/holo/receive/close_progress.py:45-67, the kernel Decoder.audit_solved_symbols at src/holo/core/fountain.py:969, and the CLI epilogue at src/holo/cli.py:733 and :743.
Where its tests live today. tests/holo/test_close_surplus_audit.py - clean-repair localization, the exact-K case where zero surplus equations means nothing can be observed, the pivot-repair case that provably evades observation, the on/off matrix, and the detach/foreign-entry type guard.
Where it would attach in holo3. A new audit_solved_symbols on holo3/format/fountain.py's Decoder (it already keeps _solved per block and the loaded items), an ESI -> certificate map captured inside the three branches of holo3/format/close.py:553-619 (which already iterate certificates per decoder), one advisory field on CloseResult (holo3/format/close.py:37-45), one line on data.CloseCheck, and one line in holo3/diag/readout.py's close row. Off by default, behind the diag surface.
Two properties that must survive the port. It must be wrapped so a defect in it can never turn a decodable volume into an error, and it must never be consulted by status or payload. Both are stated in v1's own docstring and are the reason it was safe to run always.
What evidence would show it paid. A seeded sim in holo3's own lane that corrupts one certified symbol in a dependent row of a solved block and shows the close still VERIFIES while the audit names exactly that tile - and the negative control, a corrupted pivot row, where the audit correctly reports nothing. On paper it pays the first time a real volume fails its SHA on a complete solve and the audit names a tile instead of the run reporting an unlocalized failure.
Ordering. Cash this only after close-06's run-boundary fix; today an integrity_failure kills the run before anything is printed, so the audit's main occasion produces no output.
Related. v1's report-only certificate_divergence (src/holo/receive/records.py:375-425, re-encoded printed field against LLR sign) is the payload family's row, not this one, but the two belong in the same brief if either is ported.

