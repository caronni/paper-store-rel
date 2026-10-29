# PORT BRIEF — the supplemental baseline arm ('off')

| | |
|---|---|
| Capability | The supplemental BASELINE lane — the `off` arm, which re-reads the residue on the pre-campaign A0/A1 skeleton |
| Status | **archived-for-port** |
| Ruling reference | Proposed, awaiting Gate B: `RULINGS-holo1-draft.md` → `colour-stack-12`. The recommendation there is *archive for later port*; this brief is written so the ruling has something to accept or decline. |
| Map row | `HOLO1-MAP.md` → `colour-stack-12` (ABSENT) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF — the supplemental baseline arm ('off').
What it does: gives the residue one more read through the receiver's pre-campaign colour path, so a tile stranded by a ladder-configuration change (not by evidence damage) can still be certified.
It is a configuration restored, not an arm added.
Inputs: the same region inputs every arm gets — a lane's committed poses, its windows, the page's certificates and the capture's planes.
Outputs: ordinary tile attempts on uncertified addresses only; no evidence is written, so it is monotone and cannot regress anything.
Where its code lives today: src/holo/receive/color_stack.py:183-200 (the constant and the ruling that motivates it).
Also :602 (the one line that collapses the ladder — force_null OR arm == off), and src/holo/receive/lane_uplift.py:74 (it is ordered first among the arms).
Its tests today: the campaign harness under measure/_color_uplift_harness plus the u-lane legs of the colour-uplift replays; there is no unit test of the arm itself, only its measured record.
What it would attach to in holo3: src/holo/receiver/plugins/color_arms.py:94-99 (a third entry in arms_for_family), a skeleton flag threaded into src/holo/receiver/plugins/color_region_head.py:419-520 that skips the seven-state head and the context matrix, a stage name and price in src/holo/receiver/plugins/uplift.py alongside the other two arms, and one existence test in the shape of src/holo/receiver/tests/test_h3_plugins_uplift.py — about thirty lines.
Ordering caveat: v1 runs it FIRST among the arms deliberately. holo3 prices arms by fire ordinal, so 'first' has to be spelled as a lower base cost than the other two, not as a plan position.
What would show it paid: on any real colour sheet, one or more certificates minted at stage uplift_off on addresses no other row reached.
Because holo3 arms every capture-level, the two footing losses v1 recorded (docs/COLOR-UPLIFT-MEASUREMENTS.md:2364-2367) are the specific addresses to look for.
Precondition: do not schedule this work until the supplemental row is shown to fire at all on paper (colour-stack-11). Today it would be dead code in a dead row.
Expected size of the prize, stated honestly: one address recovered corpus-wide in v1's own measurement, possibly three in holo3 if the footing losses convert.
This is a completeness port, not a yield port.

