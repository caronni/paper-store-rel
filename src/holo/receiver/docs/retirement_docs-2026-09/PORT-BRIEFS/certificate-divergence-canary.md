# PORT BRIEF — in-run certificate divergence canary

| | |
|---|---|
| Capability | The certificate divergence audit (non-gating, per observed cell) |
| Status | **archived-for-port** |
| Ruling reference | Proposed, awaiting Gate B: `RULINGS-holo1-draft.md` → `payload-union-retry-intake-19`. The recommendation there is *archive for later port*; this brief is written so the ruling has something to accept or decline. |
| Map row | `HOLO1-MAP.md` → `payload-union-retry-intake-19` (ABSENT) |
| Source | second-lens `port_brief`, verbatim below |

---

PORT BRIEF — in-run certificate divergence canary
What it does: while a decode runs, compares every observed cell against every certificate already minted at that address and counts the disagreements. It gates nothing. It is the number that lets a paper say 'zero wrong certificates in N cells'.
Inputs: the certified user bits at an address, the format row (to re-encode the printed field for that address), and the current capture's observed values at that address.
Outputs: per (capture, lane, address) counts of observed cells and disagreeing cells, folded into run totals and printed in the run report; on the colour side, the certified colour projection instead of a re-encoded black-and-white field.
Where its code lives today: src/holo/receive/records.py:375-425 (the single pairing loop plus per-codec kernel), src/holo/receive/color_divergence.py (the colour kernel), called once per lane at src/holo/receive/production_payload.py:515-517.
Where its evidence lives today: docs/COLOR-UPLIFT-MEASUREMENTS.md:3029 (zero wrong in 69,066,304 cells) and experiments/032-xerox-altalink-payload-volumes.md:86-88 (5,370 divergences against 5,370 certificates).
Tests today: the campaign-wide audit was the product; the surviving offline analogue with its own tests is measure/crop_parity.
Where it would attach in holo3: a new scheduler row born by a Certificate fact and priced above every decoding row so it can never displace work, reading the same evidence keys the scan row reads (src/holo/receiver/plugins/tiles.py:729-737). The truth side already exists — src/holo/receiver/plugins/tiles.py:499 re-encodes a certified tile's printed cells — and the fold would sit alongside the certificate fold in src/holo/receiver/store.py.
It must emit one event per (capture, address) so the count survives in the run's event log the way the crop batteries' verdicts do.
What evidence would show it paid: (a) a run on a real sheet reporting a large observed total with disagreements at or below the channel's own error rate, reproducing the offline battery verdict in-run; (b) a deliberately corrupted-certificate fixture where the count rises, proving the canary can see what it claims to see; (c) a measured processor-second share under 1% of the run, since a canary that competes with decoding will be turned off.
Why it is archived rather than ported now: no certificate is at risk without it, and the offline batteries already answer the question on crops. This is an instrument for the next paper, not a safety fix for the retirement.

