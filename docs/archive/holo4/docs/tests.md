# tests

A verification plane that cuts across every product domain. Not a
seventh module of the receiver.

## Four kinds (do not mix in one file)

| kind | asserts | lives | speed |
|---|---|---|---|
| **pins** | bit-identity of a kernel or format object | beside lib/format (`ldpc_data`, keystream vectors) | fast |
| **unit** | a function of mechanisms/lib | `tests/` per package | fast |
| **contract** | descriptor reads/produces, cell-class, single-writer, payload independent of `--workers`, close consult | engine/store tests | fast |
| **corpus** | certificate sets, verified SHA, wall, cpu-s/cert on named sheets | named, rare, not `pytest -q` | slow |

Pins are format law. They belong next to the bytes they pin. A pin
that lives in a 1,300-line plugin test will drift into "whatever the
last run did."

Unit tests do not open a 4800-dpi TIFF.

Contract tests are how the engine stays honest when plugins are
hostile: two descriptors producing the same fact type without a
re-arm declaration must fail at import; a decision cell must not
A→B→A; `--workers 1` and `--workers 8` on a sim must share payload
SHA.

Corpus tests are the retirement snapshot and the research
high-water mark. They are different files, with names that include
the sheet and the policy dials. They are not a default gate.

## Why this is a domain at all

holo3's token budget moved into tests (~29k lines next to ~34k
production). That is the right *place* and the wrong *shape* if
`test_h3_plugins_color.py` is 1,365 lines. A file over 1000 lines
is a split signal here too. Split by invariant, not by module:

- bit-identity of the cmy7 demap
- held-out refusal is a null
- pooled_ctx does not pool bins
- colour assembly at price 15 is not a head fit

Those can share a fixture. They should not share a narrative.

## Laws

- Test module basenames globally unique (pytest prepend import).
- No unseeded RNG. Sims take a seed.
- Profiling never via generic pytest (existing doctrine).
- A corpus test that cannot name its footing (geometry, training,
  captures, flags) is not a result.
- Goldens are bump-don't-edit. A mismatch is a fork or a deliberate
  amendment, never a quiet rewrite.

## What tests must not become

- A second receiver (reimplementing place "to check").
- Comments-as-law that production deleted. The assert is the law.
- A dumping ground for historical accidents as fixtures without a
  name. If e033's misdeclared-dpi lives here, the test is called
  that.

## Seams

Every product domain is a producer of tests. tests ↛ production
except through public functions. Verify scripts that import both
`src/holo` and holoN belong outside production packages
(holo3: `_distill/verify/`).

## holo4 stance

Pins and contracts are the collaborator-capacity tools: they are
what a worker cannot silently violate. Corpus is the user's
retirement snapshot. If the test tree needs a charter of its own,
the production tree has grown too much documentation again — split
the tests, don't write `TEST-DESIGN.md` first.
