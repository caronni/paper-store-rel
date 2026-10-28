# E023b fountain-volume scorer

E023b's authoritative receiver boundary is CRC-certified LDPC tiles. Raw
certificate count is not a volume-recovery result: partial edge tiles can
certify while carrying no fountain symbol, and a set with at least `K`
symbols can still be rank-deficient.

For the complete acquisition/BP/scoring command sequence, see
[`HOWTO.md`](HOWTO.md). The emitted E018b volumes and pinned first-take inputs
are recorded in
[`../018b-payload-sheet.md`](../018b-payload-sheet.md).

`score_e023b.py` performs the read-only handoff from an E023b state to the
volume descriptor stored in an emitted-sheet manifest:

```text
env/bin/python experiments/023b-integrated-receiver/score_e023b.py \
  experiments/023b-integrated-receiver/build/session.pkl \
  experiments/018b-payload-sheet/build/e018b-c3-..._manifest.json \
  --label c3-canon-native \
  --out experiments/023b-integrated-receiver/build/c3-canon-score.json
```

The scorer validates the complete format identity: format id, fixed seed,
cell size, page geometry, legal pages, LDPC rate, fountain version, data
length, symbol geometry, and expected payload SHA-256. It then reports:

- complete E023b tile-state counts and CRC-attempt cost;
- all certified LDPC tiles;
- certified interior fountain symbols, excluding inert edge certificates;
- actual fountain rank, required source rank, and rank shortfall;
- recovered length and SHA-256 when the solve closes.

An under-ranked state is reported as `OPEN` and exits successfully. A solved
payload whose length or SHA-256 disagrees with the manifest is an integrity
failure. `--require-recovered` changes an otherwise valid open score to exit
status 4. `--recovered-out FILE` writes bytes atomically only after successful
length and SHA verification.

For scanner comparisons, use one fresh state per scanner and the same
detector/BP schedule. Compare `symbol_yield`, `rank/source_symbols_needed`,
CRC calls, BP iterations, and the final SHA verdict. Compare C2 and C3 by
fractions rather than raw tile counts because their tile universes differ.
If scanner inputs use different native DPI, the result compares practical
scanner+footing performance, not a controlled scanner-only variable.

Do not score a state against a same-profile manifest for another E018b
payload. The public format key is intentionally reused; the manifest's data
length and SHA-256 bind the physical payload instance.

The scorer accepts one authoritative E023b state pickle. It does not yet
consume the terminal JSON emitted by `merge_e023b.py`; multiview branch
states must therefore be scored separately. Adding union-bundle scoring is a
separate outer-layer feature and must preserve certificate conflict checks
and source provenance.
